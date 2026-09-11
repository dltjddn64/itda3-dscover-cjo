# ITDA 3rd 학술제 - 메인 추론 스크립트 (predict.py)
from __future__ import annotations

import argparse
import glob
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import torch

# ============================================================
# 기본 상수 및 설정
# ============================================================
NONE_RESULT: Tuple[str, str, str] = ("NONE", "NONE", "NONE")
YEAR_MIN, YEAR_MAX = 2023, 2030
MAX_SIDE = 1280
IMAGE_EXTS = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')

DATE_PATTERNS = [
    re.compile(r'(?<!\d)(\d{4})[.\-/\s](\d{1,2})[.\-/\s](\d{1,2})(?!\d)'),
    re.compile(r'(?<!\d)(\d{2})[.\-/\s](\d{1,2})[.\-/\s](\d{1,2})(?!\d)'),
    re.compile(r'(?<!\d)(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'),
    re.compile(r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)'),
]

# ============================================================
# 기본 베이스라인 추론 파이프라인 Class
# ============================================================
@dataclass
class TextBox:
    bbox: list
    text: str
    confidence: float

class BasicOCREngine:
    def __init__(self, gpu: bool = torch.cuda.is_available()):
        import easyocr
        print("OCR 엔진 초기화 중...")
        self.reader = easyocr.Reader(['ko', 'en'], gpu=gpu)
        print("OCR 엔진 준비 완료")

    def read(self, image_path: str | Path) -> List[TextBox]:
        try:
            img_array = np.fromfile(str(image_path), np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                return []

            h, w = img.shape[:2]
            max_dim = max(h, w)

            if max_dim > MAX_SIDE:
                scale = MAX_SIDE / float(max_dim)
                resized_img = cv2.resize(img, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
            else:
                scale = 1.0
                resized_img = img

            results = self.reader.readtext(resized_img)
            text_boxes = []
            for bbox, text, conf in results:
                orig_bbox = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in bbox] if scale != 1.0 else [[float(pt[0]), float(pt[1])] for pt in bbox]
                text_boxes.append(TextBox(bbox=orig_bbox, text=text, confidence=float(conf)))
            return text_boxes
        except Exception:
            return []

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
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            validated = validate_date(*match.groups())
            if validated:
                return validated
    return None

def run_predict(input_dir: str, output_path: str):
    paths = []
    for ext in IMAGE_EXTS:
        paths.extend(glob.glob(os.path.join(input_dir, ext)))
    paths = sorted(set(paths))

    if not paths:
        print(f"[경고] {input_dir} 에서 이미지를 찾지 못했습니다.")
        df_empty = pd.DataFrame(columns=["image_id", "year", "month", "day"])
        df_empty.to_csv(output_path, index=False, encoding='utf-8-sig')
        return

    print(f"총 {len(paths)}장 추론 시작")
    ocr_engine = BasicOCREngine()
    rows = []
    start_time = time.time()

    for idx, path in enumerate(paths, 1):
        boxes = ocr_engine.read(path)
        found_date = NONE_RESULT
        for box in boxes:
            date_res = parse_first_date(box.text)
            if date_res:
                found_date = date_res
                break
        
        rows.append({
            "image_id": Path(path).stem,
            "year": found_date[0],
            "month": found_date[1],
            "day": found_date[2]
        })

        if idx % 50 == 0 or idx == len(paths):
            print(f"  [{idx}/{len(paths)}] 진행 중... ({time.time() - start_time:.1f}초)")

    df = pd.DataFrame(rows, columns=["image_id", "year", "month", "day"])
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n추론 완료! 결과 저장 : {output_path}")

# ============================================================
# 메인 CLI 실행부
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="ITDA OCR 소비기한 추출 추론 스크립트")
    parser.add_argument(
        "--input_dir", "--image_dir", type=str, required=True, help="입력 이미지 폴더 경로"
    )
    parser.add_argument(
        "--output_path", "--output", type=str, default="submission.csv", help="출력 CSV 결과 파일 경로"
    )
    args = parser.parse_args()

    run_predict(args.input_dir, args.output_path)

if __name__ == "__main__":
    main()
