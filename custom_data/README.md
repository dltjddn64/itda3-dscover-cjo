# custom_data — 자체 수집/라벨링 데이터 (가산점 근거)

- `labels/master_labels.csv`: 최종 통합 라벨 (587장, `image_id, year, month, day, final_date, note`) — `data/raw/`의 동일 image_id 사진에 대응
- `labels/validation_labels.csv`: 팀원이 직접 눈으로 라벨링한 150장 원본
- `labels/500_candidates_resolved.csv`: 팀원이 수집한 500장 후보(`ITDA_500_image_date_candidates.csv`)를 규칙 기반으로 자동 정리한 결과
- `labels/LABELING_GUIDE.md`: 라벨링 형식 가이드
- `ITDA_500_image_date_candidates.csv`: 위 500장의 원본(가공 전) 라벨 후보

라벨링 과정에서 발견한 문제와 그걸로 개선한 내역은 `PIPELINE.md`, 설계 논리는 아키텍처 요약서 PDF 참고.
