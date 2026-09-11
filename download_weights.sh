#!/bin/bash
# ITDA 3rd 학술제 - 모델 가중치 사전 다운로드 스크립트
#
# 채점 서버는 인터넷이 차단된 오프라인 환경이라, predict.ipynb의 Run All 도중에는
# 가중치를 새로 받을 수 없습니다. 이 스크립트를 실행 전에 한 번 실행해서
# 가중치를 로컬 weights/ 폴더에 미리 받아두세요.
#
# 사용법: bash download_weights.sh   (인터넷 연결된 상태에서 실행)
#
# 동작 방식: PaddleOCR 공식 다운로드 경로(paddlex 허브)에서 모델을 받아
# ~/.paddlex/official_models/ 에 캐시한 뒤, 그걸 이 프로젝트의 weights/ 폴더로
# 복사합니다. src/ocr_engine.py의 PaddleEngine은 weights/ 폴더가 존재하면
# 인터넷 접속 없이 이 로컬 사본을 직접 사용하도록 되어 있습니다.

set -e

echo "[1/3] PaddleOCR 공식 모델 다운로드 중 (인터넷 필요)..."
python3 -c "
from paddleocr import PaddleOCR
PaddleOCR(
    lang='korean',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
print('다운로드 완료')
"

echo "[2/3] weights/ 폴더로 복사 중..."
mkdir -p weights
cp -r ~/.paddlex/official_models/PP-OCRv5_server_det weights/
cp -r ~/.paddlex/official_models/korean_PP-OCRv5_mobile_rec weights/

echo "[3/3] 완료. weights/ 폴더 내용:"
du -sh weights/*

echo ""
echo "이제 network 없이도 predict.ipynb를 실행할 수 있습니다."
echo "오프라인 검증: PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True 환경변수가"
echo "src/ocr_engine.py에서 자동으로 설정되므로 별도 조치 불필요합니다."
