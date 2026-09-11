"""OCR 결과에서 소비기한 후보를 판별하고 날짜를 정규화하는 로직

전략:
  1. '유통기한/소비기한/까지' 등 앵커 키워드가 포함된 텍스트를 우선 탐색
     - 같은 박스 안에 날짜까지 있으면 바로 채택 (가장 신뢰도 높음)
     - 라벨과 날짜가 분리된 박스라면, 위치상 가장 가까운 날짜 박스를 채택
  2. 앵커 키워드로 못 찾으면, 기존 방식(첫 번째로 발견된 유효 날짜)으로 대체 (recall 확보용 fallback)
"""
import math
import re
from datetime import datetime
from typing import List, Optional, Tuple

from .ocr_engine import TextBox

NONE_RESULT: Tuple[str, str, str] = ("NONE", "NONE", "NONE")
# 원래 베이스라인 값(2023~2030)을 그대로 썼었는데, 검증셋 라벨링 중 2020~2022년도
# 소비기한이 실제로 다수 존재하는 걸 확인해서 넓힘. PIPELINE.md 2026-09-09 항목 참고.
YEAR_MIN, YEAR_MAX = 2015, 2032

# 각 패턴 + 그룹 순서("ymd" 또는 "dmy"). 구분자 클래스는 '+'로 한 글자 이상 반복 허용
# (OCR이 "2026. 9.24"처럼 마침표+공백을 같이 찍는 경우 등). ','도 구분자에 포함:
# OCR이 마침표(.)를 쉼표(,)로 오인식하는 경우가 있음 (예: "2027,06.26")
_SEP = r"[.\-/,:\s]+"  # OCR이 마침표를 콜론으로 잘못 읽는 경우 대응 (예: "2022.11:02")
DATE_PATTERNS = [
    # 연도가 먼저 오는 한국식: YYYY.MM.DD / YY.MM.DD
    (re.compile(rf"(?<!\d)(\d{{4}}){_SEP}(\d{{1,2}}){_SEP}(\d{{1,2}})(?!\d)"), "ymd"),
    (re.compile(rf"(?<!\d)(\d{{2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{1,2}})(?!\d)"), "ymd"),
    # 일이 먼저 오는 수입상품 표기: DD.MM.YYYY / DD/MM/YYYY (연도가 4자리라 뒤에서 구분 가능)
    (re.compile(rf"(?<!\d)(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{4}})(?!\d)"), "dmy"),
    # 일-월-2자리연도 (예: "13/03/22", "04-11-23"). y<100은 validate_date에서 +2000 처리.
    (re.compile(rf"(?<!\d)(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{2}})(?!\d)"), "dmy"),
    (re.compile(r"(?<!\d)(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"), "ymd"),
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), "ymd"),
]

# 영문 월 이름 표기 (예: "MAY 12 2026", "07 SEP 21", "07FEB2022"). 대소문자 무시.
_MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = "|".join(_MONTH_NUM)
_MSEP = r"[.\-/,\s]*"  # 붙여쓴 "07FEB2022"도 잡히도록 구분자 없음(0글자)도 허용
MONTH_NAME_PATTERNS = [
    # 일 - 월이름 - 연도(2~4자리): "07 SEP 21", "07FEB2022", "FEB/26/21"(뒤 숫자가 연도인 dMy는 아래 별도)
    # 각 숫자 그룹 뒤에 (?!\d)를 둬서, "Nov 2021"처럼 일자가 아예 없는 경우 "20"+"21"로
    # 잘못 쪼개 억지로 일자를 만들어내는 것을 방지 (연도 자리는 통째로 매칭되어야 함)
    (re.compile(rf"(?<!\d)(\d{{1,2}})(?!\d){_MSEP}({_MONTH_RE}){_MSEP}(\d{{2,4}})(?!\d)", re.I), "dMy"),
    # 월이름 - 일 - 연도: "MAY 12 2026", "APR 14 2022"
    (re.compile(rf"(?<!\d)({_MONTH_RE}){_MSEP}(\d{{1,2}})(?!\d){_MSEP}(\d{{2,4}})(?!\d)", re.I), "Mdy"),
    # 연도 - 월이름 - 일: "2021 OCT 15" (연도가 4자리라 순서 구분 가능)
    (re.compile(rf"(?<!\d)(\d{{4}}){_MSEP}({_MONTH_RE}){_MSEP}(\d{{1,2}})(?!\d)", re.I), "yMd"),
]

# TODO: 실제 데이터 샘플을 더 보면서 표현을 보강할 것 (예: "품질유지기한", "EXP", "제조일로부터")
ANCHOR_KEYWORDS = ["유통기한", "소비기한", "품질유지기한", "까지", "EXP", "exp"]

# 소비기한이 아닌 다른 종류의 날짜 라벨. 이 키워드 근처의 날짜는 오답 후보로 보고 제외한다.
# '부터': "2025.09.10 부터 ~ 2026.06.09 까지"처럼 시작일/종료일이 함께 적힌 라벨에서
# 시작일을 소비기한으로 잘못 채택하는 걸 방지 (실제 사례로 발견됨, PIPELINE.md 참고)
NEGATIVE_KEYWORDS = ["제조일자", "제조일", "생산일자", "생산일", "소분일", "포장일", "충전일", "부터"]


def validate_date(year: str, month: str, day: str) -> Optional[Tuple[str, str, str]]:
    try:
        y, m, d = int(year), int(month), int(day)
        if y < 100:
            y += 2000
        if not (YEAR_MIN <= y <= YEAR_MAX):
            return None
        datetime(y, m, d)
        return (f"{y:04d}", f"{m:02d}", f"{d:02d}")
    except (ValueError, TypeError):
        return None


def parse_first_date(text: str) -> Optional[Tuple[str, str, str]]:
    for pattern, order in DATE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if order == "dmy":
                d, m, y = groups
                validated = validate_date(y, m, d)
                # "4.13.2026"처럼 미국식(월-일-연도)일 수도 있으니, 일-월 순으로 실패하면
                # 월-일로 바꿔서 한 번 더 시도 (day/month 자리가 서로 바뀐 경우 구제)
                if not validated:
                    validated = validate_date(y, d, m)
            else:
                y, m, d = groups
                validated = validate_date(y, m, d)
            if validated:
                return validated

    for pattern, order in MONTH_NAME_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if order == "dMy":
                d, mon, y = groups
            elif order == "yMd":
                y, mon, d = groups
            else:
                mon, d, y = groups
            m = _MONTH_NUM.get(mon.lower())
            if m is None:
                continue
            validated = validate_date(y, m, d)
            if validated:
                return validated
    return None


def validate_year_month(year: str, month: str) -> Optional[Tuple[str, str]]:
    try:
        y, m = int(year), int(month)
        if y < 100:
            y += 2000
        if not (YEAR_MIN <= y <= YEAR_MAX) or not (1 <= m <= 12):
            return None
        return (f"{y:04d}", f"{m:02d}")
    except (ValueError, TypeError):
        return None


_DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # 2월은 29일까지 관대하게 허용


def validate_month_day(month: str, day: str) -> Optional[Tuple[str, str]]:
    try:
        m, d = int(month), int(day)
        if not (1 <= m <= 12) or not (1 <= d <= _DAYS_IN_MONTH[m - 1]):
            return None
        return (f"{m:02d}", f"{d:02d}")
    except (ValueError, TypeError):
        return None


# 연+월만 있고 일이 없는 경우 (예: "2026.01", "OCT.2021", "12/2020")
PARTIAL_YM_PATTERNS = [
    (re.compile(rf"(?<!\d)(\d{{4}}){_SEP}(\d{{1,2}})(?!\d)"), "ym"),
    # 월이 먼저 오는 경우 (연도가 4자리라 순서 구분 가능): "12/2020", "08/2021"
    (re.compile(rf"(?<!\d)(\d{{1,2}}){_SEP}(\d{{4}})(?!\d)"), "my"),
]
PARTIAL_YM_MONTH_NAME_PATTERNS = [
    # 월이름-연도: "OCT 2021", "OCT.2021", "OCT/2021"
    (re.compile(rf"(?<!\d)({_MONTH_RE}){_MSEP}(\d{{2,4}})(?!\d)", re.I), "my"),
    # 연도-월이름: "2021 OCT"
    (re.compile(rf"(?<!\d)(\d{{2,4}}){_MSEP}({_MONTH_RE})(?!\w)", re.I), "ym"),
]


def parse_year_month(text: str) -> Optional[Tuple[str, str]]:
    """일(day) 없이 연+월만 있는 경우를 추출한다. 못 찾으면 None."""
    for pattern, order in PARTIAL_YM_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            y, m = groups if order == "ym" else groups[::-1]
            validated = validate_year_month(y, m)
            if validated:
                return validated
    for pattern, order in PARTIAL_YM_MONTH_NAME_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if order == "my":
                mon, y = groups
            else:
                y, mon = groups
            m = _MONTH_NUM.get(mon.lower())
            if m is None:
                continue
            validated = validate_year_month(y, m)
            if validated:
                return validated
    return None


# 월+일만 있고 연도가 없는 경우 (예: "10.14", "11.20"). 앵커 키워드 근처에서만 사용 —
# 라벨 전체를 뒤지면 가격/전화번호/영양성분 같은 무관한 숫자쌍과 충돌 위험이 크다.
PARTIAL_MD_PATTERNS = [
    (re.compile(rf"(?<!\d)(\d{{1,2}}){_SEP}(\d{{1,2}})(?!\d)"), "md"),
]


def parse_month_day(text: str) -> Optional[Tuple[str, str]]:
    """연도 없이 월+일만 있는 경우를 추출한다. 못 찾으면 None."""
    for pattern, order in PARTIAL_MD_PATTERNS:
        for match in pattern.finditer(text):
            a, b = match.groups()
            validated = validate_month_day(a, b)
            if validated:
                return validated
            # 월/일 순서가 바뀐 경우(일-월)도 시도
            validated = validate_month_day(b, a)
            if validated:
                return validated
    return None


def _bbox_center(bbox: list) -> Tuple[float, float]:
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _bbox_height(bbox: list) -> float:
    ys = [pt[1] for pt in bbox]
    return max(ys) - min(ys)


def _edit_distance_le(a: str, b: str, max_dist: int) -> bool:
    """a, b의 편집거리가 max_dist 이하인지 (OCR 오독으로 한두 글자 달라진 경우 허용)"""
    if abs(len(a) - len(b)) > max_dist:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1] <= max_dist


def _fuzzy_contains(text: str, keyword: str, max_dist: int = 1) -> bool:
    """text 안에 keyword와 편집거리 max_dist 이하로 비슷한 부분문자열이 있는지 확인.
    OCR이 '소분일'을 '소문일'로 오독하는 것처럼 한 글자 정도 틀리는 경우를 잡기 위함."""
    n = len(keyword)
    for i in range(len(text) - n + 1):
        if _edit_distance_le(text[i:i + n], keyword, max_dist):
            return True
    return False


def _is_anchor_text(text: str) -> bool:
    return any(keyword in text for keyword in ANCHOR_KEYWORDS)


# 편집거리 유사매칭은 실제 OCR 오독 사례가 확인된 키워드에만 적용한다.
# 다른 키워드까지 전부 허용하면 "충전제"(식품첨가물) vs "충전일"처럼 편집거리 1짜리
# 흔한 단어와 충돌해서 정답 날짜를 오탐 제거해버리는 사고가 남 (실제 사례로 발견됨,
# PIPELINE.md 참고). 나머지 키워드는 정확히 일치할 때만 부정 키워드로 취급.
_FUZZY_NEGATIVE_KEYWORDS = {"소분일"}


def _is_negative_text(text: str) -> bool:
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in _FUZZY_NEGATIVE_KEYWORDS:
            if _fuzzy_contains(text, keyword):
                return True
        elif keyword in text:
            return True
    return False


def _y_range(bbox: list) -> Tuple[float, float]:
    ys = [pt[1] for pt in bbox]
    return min(ys), max(ys)


def _x_range(bbox: list) -> Tuple[float, float]:
    xs = [pt[0] for pt in bbox]
    return min(xs), max(xs)


def merge_same_line_boxes(boxes: List[TextBox], overlap_ratio: float = 0.5) -> List[TextBox]:
    """세로 위치가 겹치는(같은 줄로 보이는) 박스들을 x좌표 순으로 이어붙여 새 박스를 만든다.

    OCR이 '2022.02.14 16:01'처럼 한 줄짜리 텍스트를 '2022' / '02.14' / '16:01'
    여러 조각으로 쪼개 인식하는 경우, 조각 하나만 봐서는 날짜 패턴이 안 잡히므로 보완한다.
    """
    if not boxes:
        return []

    order = sorted(range(len(boxes)), key=lambda i: _y_range(boxes[i].bbox)[0])
    used = [False] * len(boxes)
    lines: List[List[int]] = []

    for i in order:
        if used[i]:
            continue
        y0, y1 = _y_range(boxes[i].bbox)
        line = [i]
        used[i] = True
        for j in order:
            if used[j]:
                continue
            jy0, jy1 = _y_range(boxes[j].bbox)
            overlap = min(y1, jy1) - max(y0, jy0)
            min_height = min(y1 - y0, jy1 - jy0) or 1.0
            if overlap / min_height >= overlap_ratio:
                line.append(j)
                used[j] = True
                y0, y1 = min(y0, jy0), max(y1, jy1)
        lines.append(line)

    merged_boxes = []
    for line in lines:
        if len(line) < 2:
            continue  # 단일 박스 줄은 원본 목록에 이미 있으므로 스킵
        line_sorted = sorted(line, key=lambda i: _x_range(boxes[i].bbox)[0])
        merged_text = " ".join(boxes[i].text for i in line_sorted)
        xs = [pt[0] for i in line_sorted for pt in boxes[i].bbox]
        ys = [pt[1] for i in line_sorted for pt in boxes[i].bbox]
        merged_bbox = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
        conf = min(boxes[i].confidence for i in line_sorted)
        merged_boxes.append(TextBox(bbox=merged_bbox, text=merged_text, confidence=conf))

    return merged_boxes


def _nearest_by_row(
    anchor_center: Tuple[float, float],
    anchor_height: float,
    max_distance: float,
    candidates: List[Tuple[TextBox, Tuple]],
) -> Optional[Tuple]:
    """앵커 위치 기준으로 가장 가까운 후보를 찾되, 같은 줄(세로 위치가 비슷한) 후보를 우선한다.
    "소비기한 [값1] ... 부터 [값2] 까지"처럼 라벨:값이 옆으로 넓게 배치된 표에서는
    다른 줄이지만 세로로만 가까운 오답이 순수 유클리드 거리로 더 가깝게 나올 수 있어서,
    같은 줄 후보를 먼저 찾고 없을 때만 전체 최근접으로 대체한다."""
    same_row_best, same_row_dist = None, None
    any_best, any_dist = None, None
    for cand_box, cand_result in candidates:
        cand_center = _bbox_center(cand_box.bbox)
        dist = math.dist(anchor_center, cand_center)
        if dist > max_distance:
            continue
        if dist < (any_dist if any_dist is not None else float("inf")):
            any_best, any_dist = cand_result, dist
        if abs(cand_center[1] - anchor_center[1]) <= anchor_height * 1.5:
            if dist < (same_row_dist if same_row_dist is not None else float("inf")):
                same_row_best, same_row_dist = cand_result, dist
    return same_row_best if same_row_best is not None else any_best


def find_anchor_based_date(boxes: List[TextBox]) -> Optional[Tuple[str, str, str]]:
    """앵커 키워드 근처에서 날짜를 찾는다. 못 찾으면 None."""
    date_boxes = [(box, parse_first_date(box.text)) for box in boxes]
    date_boxes = [(box, d) for box, d in date_boxes if d is not None]
    if not date_boxes:
        return None

    for box in boxes:
        if not _is_anchor_text(box.text):
            continue

        # 1) 같은 박스 안에 날짜까지 있으면 바로 채택.
        # 단, 같은 텍스트에 '부터' 등 부정 키워드도 같이 섞여 있으면(줄 병합 과정에서
        # "25.09.02 부터 까지"처럼 두 라벨이 한 줄로 합쳐지는 경우) 이 지름길을 건너뛰고
        # 아래 2)의 거리 기반 탐색으로 넘어간다 — 그래야 진짜 '까지'에 대응하는 날짜를 찾는다.
        same_box_date = parse_first_date(box.text)
        if same_box_date and not _is_negative_text(box.text):
            return same_box_date

        # 2) 라벨과 날짜가 분리된 경우: 가장 가까운 날짜 박스 채택 (같은 줄 우선)
        anchor_center = _bbox_center(box.bbox)
        anchor_height = _bbox_height(box.bbox) or 1.0
        max_distance = anchor_height * 8  # 텍스트 줄 높이의 8배 이내(대략 근처 줄/옆칸 수준)만 후보로 인정
        # 부정 키워드가 섞인 날짜 박스(예: 위 병합 박스)는 애초에 후보에서 제외
        candidates = [(db, dr) for db, dr in date_boxes if not _is_negative_text(db.text)]

        best_date = _nearest_by_row(anchor_center, anchor_height, max_distance, candidates)
        if best_date:
            return best_date

    return None


def find_anchor_based_partial(boxes: List[TextBox]) -> Optional[Tuple[str, str, str]]:
    """완전한 날짜를 못 찾았을 때, 앵커 근처에서 연+월 또는 월+일만이라도 찾는다.
    부분점수(연/월/일 각각 채점)가 있다는 채점 기준 확인 후 추가한 경로 — 완전한 날짜가
    없다고 전부 버리지 않고, 확실히 아는 필드만이라도 채택하고 나머지는 NONE으로 표시한다.
    라벨 전체가 아니라 앵커 키워드 근처로만 제한하는 이유: '월+일' 패턴은 가격/전화번호 같은
    무관한 숫자쌍과 충돌 위험이 커서, 앵커 없이 쓰면 오탐이 급증한다."""
    ym_boxes = [(box, parse_year_month(box.text)) for box in boxes]
    ym_boxes = [(b, r) for b, r in ym_boxes if r is not None and not _is_negative_text(b.text)]
    md_boxes = [(box, parse_month_day(box.text)) for box in boxes]
    md_boxes = [(b, r) for b, r in md_boxes if r is not None and not _is_negative_text(b.text)]

    if not ym_boxes and not md_boxes:
        return None

    for box in boxes:
        if not _is_anchor_text(box.text) or _is_negative_text(box.text):
            continue

        same_ym = parse_year_month(box.text)
        if same_ym:
            return (same_ym[0], same_ym[1], "NONE")
        same_md = parse_month_day(box.text)
        if same_md:
            return ("NONE", same_md[0], same_md[1])

        anchor_center = _bbox_center(box.bbox)
        anchor_height = _bbox_height(box.bbox) or 1.0
        max_distance = anchor_height * 8

        best_ym = _nearest_by_row(anchor_center, anchor_height, max_distance, ym_boxes)
        if best_ym:
            return (best_ym[0], best_ym[1], "NONE")
        best_md = _nearest_by_row(anchor_center, anchor_height, max_distance, md_boxes)
        if best_md:
            return ("NONE", best_md[0], best_md[1])

    return None


def _nearby_negative_label(date_box: TextBox, boxes: List[TextBox]) -> bool:
    """date_box 주변(또는 자기 자신)에 '제조일자' 등 부정 키워드가 있는지 확인.
    같은 거리 안에 긍정 앵커 키워드가 더 가까이 있으면 부정으로 취급하지 않는다."""
    if _is_negative_text(date_box.text):
        return True

    center = _bbox_center(date_box.bbox)
    height = _bbox_height(date_box.bbox) or 1.0
    max_distance = height * 8

    best_label, best_dist = None, None
    for other in boxes:
        if other is date_box:
            continue
        if _is_anchor_text(other.text):
            label = "positive"
        elif _is_negative_text(other.text):
            label = "negative"
        else:
            continue
        dist = math.dist(center, _bbox_center(other.bbox))
        if dist <= max_distance and (best_dist is None or dist < best_dist):
            best_label, best_dist = label, dist

    return best_label == "negative"


def extract_expiry_date(boxes: List[TextBox]) -> Tuple[str, str, str, str]:
    """OCR 박스 목록에서 소비기한(year, month, day, final_date)을 추출한다."""
    all_boxes = boxes + merge_same_line_boxes(boxes)

    result = find_anchor_based_date(all_boxes)

    if result is None:
        # fallback: 앵커 키워드로 못 찾으면 유효 날짜 후보들 중 '가장 늦은 날짜'를 채택.
        # 소비기한은 항상 제조일자·시작일(부터)보다 미래이므로, "첫 번째로 찾은 것"보다
        # "가장 늦은 날짜"가 더 안전한 기본값이다 (예: "2025.09.10 부터 ~ 2026.06.09 까지"에서
        # '부터'/'까지' 글자 자체가 OCR에 안 잡혀도 최댓값을 고르면 올바른 날짜를 채택하게 됨).
        # 단, '제조일자/소분일' 등 다른 종류의 날짜로 보이면 애초에 후보에서 제외한다.
        candidates = []
        for box in all_boxes:
            candidate = parse_first_date(box.text)
            if candidate and not _nearby_negative_label(box, all_boxes):
                candidates.append(candidate)
        if candidates:
            result = max(candidates)

    if result is None:
        # 완전한 날짜가 없으면 앵커 근처에서 연+월 또는 월+일이라도 채택 (부분점수 대응).
        # 안내서 채점 기준 확인: 연/월/일을 각각 채점하며 부분점수가 있고, 모르는 필드는
        # 통째로 NONE 처리하지 말고 "NONE-MM-DD"처럼 해당 필드만 NONE으로 제출해야 함.
        partial = find_anchor_based_partial(all_boxes)
        if partial:
            result = partial
        else:
            # 앵커 자체가 안 잡히는 사진도 있음(예: 일자만 인식 과정에서 잘려나간 경우).
            # '연+월'은 4자리 연도가 필수라 가격/전화번호 등과 헷갈릴 위험이 낮으므로,
            # 앵커 없이 라벨 전체에서 찾아도 비교적 안전 — 이 경우에만 앵커 없는 전체 fallback 허용.
            # '월+일'(연도 없음)은 무관한 숫자쌍과 충돌 위험이 커서 앵커 근처로만 제한 유지.
            ym_candidates = []
            for box in all_boxes:
                ym = parse_year_month(box.text)
                if ym and not _nearby_negative_label(box, all_boxes):
                    ym_candidates.append(ym)
            if ym_candidates:
                y, m = max(ym_candidates)
                result = (y, m, "NONE")

    if result is None:
        return (*NONE_RESULT, "NONE")

    year, month, day = result
    final_date = f"{year}-{month}-{day}"
    return year, month, day, final_date
