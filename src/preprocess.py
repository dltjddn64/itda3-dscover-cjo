"""이미지 전처리: 로드, 리사이즈 등"""
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np

MAX_SIDE = 640  # 채점 서버 40분 타임아웃(2400초) 안에 3,352장을 처리하기 위한 속도 최적화값. 1280 대비 정확도 손실은 거의 없음(자세한 내용은 PIPELINE.md 참고)


def load_image(image_path: str | Path) -> np.ndarray | None:
    """한글 경로에서도 안전하게 이미지를 읽는다."""
    img_array = np.fromfile(str(image_path), np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img


def resize_max_side(img: np.ndarray, max_side: int = MAX_SIDE) -> Tuple[np.ndarray, float]:
    """긴 변이 max_side를 넘으면 비율을 유지한 채 축소한다. (scale도 함께 반환)"""
    h, w = img.shape[:2]
    max_dim = max(h, w)
    if max_dim <= max_side:
        return img, 1.0

    scale = max_side / float(max_dim)
    resized = cv2.resize(img, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
    return resized, scale
