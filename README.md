# ITDA 3rd 연합학술제 — 소비기한 OCR 프로젝트

## 폴더 구조

```
.
├── predict.ipynb        # 채점 대상 메인 추론 노트북 (필수)
├── requirements.txt     # 실행 환경 패키지 목록 (필수)
├── README.md            # 이 문서
├── download_weights.sh  # 모델 가중치 사전 다운로드 스크립트 (오프라인 채점 대응, 실행 필수)
│
├── data/
│   ├── raw/              # 원본 이미지 3,352장 (git 미포함, 대회 제공)
│   └── sample_test/      # 검증용 샘플 이미지 5장
│
├── custom_data/          # 자체 수집·라벨링 데이터 (가산점 근거) — 구조는 custom_data/README.md 참고
│
├── src/                  # 재사용 파이프라인 모듈
│   ├── preprocess.py      # 이미지 전처리
│   ├── ocr_engine.py      # Detection + Recognition (PaddleOCR)
│   └── postprocess.py     # 날짜 판별 및 정규화
│
├── notebooks/            # 실험·분석용 노트북 (채점 대상 아님)
├── weights/              # 모델 가중치 (git 미포함, download_weights.sh로 받음)
├── outputs/              # submission.csv 등 결과물 (git 미포함)
├── docs/                 # 제출용 문서 (아키텍처 요약서 PDF 등)
└── reference/            # 대회 측 제공 원본 베이스라인 (수정하지 않고 보존)
```

## 실행 방법

```bash
pip install -r requirements.txt

# 가중치 사전 다운로드 (인터넷 연결 필요, 채점 전 1회만 실행)
bash download_weights.sh

# 제출 전 자가 검증 (오프라인 상태에서도 통과해야 함 — 아래 "오프라인 검증" 참고)
ITDA_INPUT_DIR=./data/raw ITDA_OUTPUT_PATH=./outputs/submission.csv \
  jupyter nbconvert --to notebook --execute predict.ipynb \
  --ExecutePreprocessor.timeout=2400 \
  --output /tmp/executed.ipynb
```

## ⚠️ 채점 서버는 오프라인입니다 — 가중치 처리 방식

채점 서버는 인터넷이 차단된 환경이라, PaddleOCR이 기본적으로 하는 "최초 실행 시 가중치 자동 다운로드"가 그대로면 실행이 실패합니다(정량 0점 위험). 그래서 이 프로젝트는 다음과 같이 대응했습니다:

1. **`download_weights.sh`**를 채점 전에 한 번 실행 — PaddleOCR 공식 다운로드 경로로 가중치를 받아서 `weights/PP-OCRv5_server_det/`, `weights/korean_PP-OCRv5_mobile_rec/`에 저장
2. **`src/ocr_engine.py`의 `PaddleEngine`**이 `weights/` 폴더가 존재하면 그 로컬 사본을 직접 가리키도록 설정됨 (`text_detection_model_dir`, `text_recognition_model_dir`) — 인터넷 접속 자체를 안 함
3. PaddleX의 "모델 호스트 연결 확인" 단계도 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`로 꺼둬서, 가중치가 로컬에 있어도 인터넷에 접속하려다 지연/실패하는 걸 방지

**오프라인 검증 방법** (제출 전 반드시 확인):
```bash
bash download_weights.sh   # 인터넷 연결 상태에서 1회 실행

# 이후 네트워크를 끄거나 아래처럼 프록시를 막아서 오프라인 상태를 흉내내고 실행
http_proxy=http://127.0.0.1:1 https_proxy=http://127.0.0.1:1 \
ITDA_INPUT_DIR=./data/raw ITDA_OUTPUT_PATH=./outputs/submission.csv \
  jupyter nbconvert --to notebook --execute predict.ipynb \
  --ExecutePreprocessor.timeout=2400 --output /tmp/executed.ipynb
```
`weights/` 폴더가 채워진 상태에서 이 명령이 에러 없이 끝까지 돌면 통과입니다.

## 제출 전 체크리스트

- [x] CONFIG 셀(`ITDA_INPUT_DIR`/`ITDA_OUTPUT_PATH`) 하드코딩 없음, `os.environ.get` 그대로 유지
- [x] `input()`/`getpass()` 등 대화형 코드 없음
- [x] CSV 저장 시 `index=False`
- [x] 결과 스키마 `image_id, year, month, day, final_date` 5개 컬럼 정확히 일치
- [x] `requirements.txt`에 `nbconvert`, `ipykernel` 포함
- [x] 가중치 로컬화 및 오프라인 실행 검증 완료 (위 섹션 참고)
- [x] GitHub 저장소 접근 권한 설정 — Public으로 생성 완료
- [x] `custom_data/` 폴더에 자체 라벨링 데이터 정리 완료 (가산점 심사용, 구조는 `custom_data/README.md` 참고)
- [ ] 최종 Commit Hash 확정 후 이메일 제출 (`dataitda5@gmail.com`)

## 자체 수집 데이터 (가산점)

`custom_data/`에 자체 라벨링한 587장 정답 CSV(`labels/master_labels.csv`)와 원본 라벨 후보가 있습니다. 세부 구조는 `custom_data/README.md` 참고.

## 참고

- 대회 공식 안내서(노션) 기준 제출 규격이 최우선입니다.
- `notebooks/`는 실험용이라 채점되지 않으며, 채점 대상은 `predict.ipynb` 하나뿐입니다.
- 파이프라인 개발 과정과 모든 실험/실패 기록은 `PIPELINE.md` 참고.

## 참고문헌

아키텍처 요약서 PDF는 A4 2장 분량 제한으로 본문에 인용번호만 표기했습니다. 상세 출처는 아래를 참고하세요.

[1] PaddleOCR — PaddlePaddle Authors. *PaddleOCR: Awesome multilingual OCR toolkits*. https://github.com/PaddlePaddle/PaddleOCR (검출: PP-OCRv5_server_det, 인식: korean_PP-OCRv5_mobile_rec 모델 사용)

[2] EasyOCR — JaidedAI. *EasyOCR: Ready-to-use OCR with 80+ supported languages*. https://github.com/JaidedAI/EasyOCR
