# ITDA 3rd 학술제 - 소비기한 추출 베이스라인 📌

본 저장소는 ITDA 3rd 학술제 참가자를 위한 공식 규칙 기반(Rule-based) 베이스라인 코드를 제공합니다.

---

## 📋 대회 개요 및 과제 정의

* **주제**: OCR 기반 상품 소비기한 정보 추출 아키텍처 설계 및 도메인 활용 기획
* **주최**: 수도권 데이터사이언스 연합학회 ITDA (경희대 CODE, 서강대 INSIGHT, 성균관대 DScover, 인하대 IBAS, 한국외대 DAT)
* **입력 (Input)**: 소비기한, 제조일자, 바코드, 영양성분 등이 얽혀 있는 상품 뒷면 이미지 1장
* **출력 (Output)**: `submission.csv` (`image_id`, `year`, `month`, `day`) 형태의 정규화된 날짜 표 (미인식 시 "NONE")
* **핵심 난이도**: 수많은 숫자(제조일, 품목보고번호, 고객센터 번호 등) 중 위치, 앵커 키워드('까지', '유통기한'), 문맥을 통해 진짜 소비기한을 판별하는 해석 로직 구축

---

## 📁 파일 구성

* `ITDA_3rd_Baseline.ipynb`: 이미지 전처리, OCR, 정규식 파싱, 시각화 디버깅 툴이 포함된 통합 노트북
* `predict.py`: 평가 데이터셋 추론 및 제출 파일(`submission.csv`) 자동 생성 스크립트
* `requirements.txt`: 대회 실행 환경 패키지 목록 (NumPy 1.x 고정 버전 포함)

---

## 🚀 시작하기 및 실행 방법

1. 본 저장소를 **Fork** 또는 **Clone** 합니다.
2. 실행 환경 라이브러리를 설치합니다.
   ```bash
   pip install -r requirements.txt
ITDA_3rd_Baseline.ipynb 내 IMAGE_DIR 경로를 본인의 데이터셋 경로에 맞게 수정하여 실험을 진행합니다.
개발 완료 후 predict.py 터미널 명령어가 정상 동작하는지 테스트합니다.Bashpython predict.py --input_dir ./val_images --output_path ./submission.csv
💡 실행 환경 주의사항 (NumPy 버전 이슈)로컬 아나콘다 환경 실행 중 ImportError: numpy.core.multiarray... 관련 오류가 발생하는 경우, 
C-Extension 패키지 충돌 방지를 위해 아래 명령어로 NumPy 버전을 조정하고 커널을 재시작해 주세요.
Bashpip install "numpy<2"

✉️ 1차 예선 제출 규칙참가자 본인의 GitHub 저장소에 predict.py, requirements.txt, 모델 가중치 파일(필요 시), README.md를 포함하여 저장소 URL과 최종 Commit Hash를 이메일로 제출해야 합니다.제출 파일 생성 규격 (submission.csv) 예시:image_idyearmonthdayval_000120260529val_0002NONENONENONE
