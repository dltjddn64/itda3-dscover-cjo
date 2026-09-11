"""텍스트 검출(Detection) + 인식(Recognition): EasyOCR 래퍼"""
from dataclasses import dataclass
from pathlib import Path
from typing import List

from . import preprocess


@dataclass
class TextBox:
    bbox: list
    text: str
    confidence: float


class OCREngine:
    def __init__(self, use_gpu: bool = False):
        import easyocr

        print("OCR 엔진 초기화 중...")
        self.reader = easyocr.Reader(["ko", "en"], gpu=use_gpu)
        print("OCR 엔진 준비 완료")

    def read(self, image_path: str | Path) -> List[TextBox]:
        try:
            img = preprocess.load_image(image_path)
            if img is None:
                return []

            resized_img, scale = preprocess.resize_max_side(img)
            # low_text=0.3: 기본값(0.4)보다 낮춰 흐릿하거나 배경이 복잡한 텍스트도 더 적극적으로 탐지.
            # 실험 결과 이 값에서 탐지율이 가장 높았음(더 낮추면 오히려 텍스트가 과도하게 쪼개져 나빠짐). PIPELINE.md 참고
            results = self.reader.readtext(resized_img, low_text=0.3)

            text_boxes = []
            for bbox, text, conf in results:
                if scale != 1.0:
                    orig_bbox = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in bbox]
                else:
                    orig_bbox = [[float(pt[0]), float(pt[1])] for pt in bbox]
                text_boxes.append(TextBox(bbox=orig_bbox, text=text, confidence=float(conf)))
            return text_boxes
        except Exception:
            return []


DET_MODEL_NAME = "PP-OCRv5_server_det"
REC_MODEL_NAME = "korean_PP-OCRv5_mobile_rec"


class PaddleEngine:
    """PaddleOCR 래퍼. OCREngine과 동일한 인터페이스(read -> List[TextBox])를 제공한다.

    채점이 500장/40분(장당 4.8초) 기준이라는 것이 확인되어, EasyOCR(640, 장당 0.68초)보다
    느리지만(장당 ~3.4초) 훨씬 정확한(40장 샘플 기준 37.5% vs 22.5%) 이 엔진을 예산 안에서 쓸 수 있게 됨.
    PIPELINE.md 2026-09-08 항목 참고.

    채점 서버는 인터넷이 차단된 오프라인 환경이라, PaddleOCR이 최초 실행 시 인터넷에서
    가중치를 자동 다운로드하려는 기본 동작이 그대로면 실행 자체가 실패한다(정량 0점 위험).
    그래서 `weights/` 폴더에 미리 받아둔 가중치가 있으면 그걸 직접 가리키게 하고,
    PaddleX의 온라인 연결 확인 단계 자체를 꺼서 완전히 오프라인으로 동작하도록 한다.
    (weights/ 채우는 방법은 download_weights.sh 참고)
    """

    def __init__(self, max_side: int = 640, weights_dir: str | Path = "weights"):
        import os

        # PaddleX가 모델 로드 전에 하는 "호스트 연결 확인" 자체를 꺼서, 가중치가 이미
        # 로컬에 있어도 인터넷에 접속하려다 오프라인 환경에서 실패/지연되는 걸 방지.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        from paddleocr import PaddleOCR

        self.max_side = max_side
        weights_dir = Path(weights_dir)
        det_dir = weights_dir / DET_MODEL_NAME
        rec_dir = weights_dir / REC_MODEL_NAME

        kwargs = dict(
            lang="korean",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        if det_dir.exists() and rec_dir.exists():
            # 로컬에 미리 받아둔 가중치를 직접 지정 -> 인터넷 접속 시도 자체가 없어짐
            kwargs["text_detection_model_name"] = DET_MODEL_NAME
            kwargs["text_detection_model_dir"] = str(det_dir)
            kwargs["text_recognition_model_name"] = REC_MODEL_NAME
            kwargs["text_recognition_model_dir"] = str(rec_dir)
            print(f"로컬 가중치 사용: {weights_dir}/")
        else:
            print(f"경고: {weights_dir}/에 로컬 가중치가 없음 — 온라인 자동 다운로드에 의존함 "
                  f"(오프라인 채점 환경에서는 실패할 수 있음, download_weights.sh 먼저 실행 필요)")

        print("PaddleOCR 엔진 초기화 중...")
        self.ocr = PaddleOCR(**kwargs)
        print("PaddleOCR 엔진 준비 완료")

    def read(self, image_path: str | Path) -> List[TextBox]:
        try:
            img = preprocess.load_image(image_path)
            if img is None:
                return []

            resized_img, scale = preprocess.resize_max_side(img, max_side=self.max_side)
            result = self.ocr.predict(resized_img)
            if not result:
                return []
            r0 = result[0]

            text_boxes = []
            for poly, text, conf in zip(r0["rec_polys"], r0["rec_texts"], r0["rec_scores"]):
                if scale != 1.0:
                    orig_bbox = [[float(pt[0]) / scale, float(pt[1]) / scale] for pt in poly]
                else:
                    orig_bbox = [[float(pt[0]), float(pt[1])] for pt in poly]
                text_boxes.append(TextBox(bbox=orig_bbox, text=text, confidence=float(conf)))
            return text_boxes
        except Exception:
            return []
