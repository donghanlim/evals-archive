# R1 · 쏜다 입금 대조 엔진 기준선

- 실험일: 2026-09-07 KST
- 상태: 실측 기준선
- SUT: `ssonda/src/core.mjs`의 `reconcile`
- 데이터: `ssonda/evals/golden.jsonl`, 44케이스, SHA-256 `8536dfc272c29ede15880dfb80aa84755b72129652e994070dad20b5ecd1d637`
- 실행 증거: `evals-archive/evidence/2026-09-07-week01-ssonda-baseline.json`

## 1. 질문·가설

기존 쏜다 golden dataset 44케이스를 원본 수정 없이 공통 스키마로 읽고, 실제 입금 대조 엔진의 기준선을 재현할 수 있는가?

## 2. 범위·제약

- 포함: 입금자명·금액·발급시각·ShotCode 기반 후보 대조
- 제외: 실제 송금, 계정 권한, 금융기관 연동, 실고객 데이터
- 이 리포트는 결정론적 대조 엔진의 기준선이며, 일반 AI agent 평가 성능을 의미하지 않음

## 3. 데이터·실행 조건

- 원본 golden.jsonl: 변경 없음
- adapter: `runner.py ssonda`가 `category`를 공통 `failure_type`으로 정규화
- bridge: `ssonda/evals/bridge.mjs`, SHA-256 `b557c037a38471e02aea701d8368c9026170686787b1d3b31e5678ec36c28804`
- runner: `golden-case/v1`, `week01-v1`, Python 표준 라이브러리와 Node 사용
- 실행 명령:

```bash
cd /Users/justimmacbook/Documents/_personal/evals-archive
python3 runner.py ssonda \
  --dataset /Users/justimmacbook/Documents/_work/_lab/ssonda/evals/golden.jsonl \
  --bridge /Users/justimmacbook/Documents/_work/_lab/ssonda/evals/bridge.mjs \
  --output evidence/2026-09-07-week01-ssonda-baseline.json
```

## 4. 측정 방법

- 정답: 각 케이스 `expected.match`
- 예측: 실제 `reconcile` 결과의 candidate ID 또는 `null`
- 지표: accuracy, precision, recall, F1, 혼동행렬, 실패유형별 통과 수
- 채점: 결정론적 exact match. LLM judge 미사용

## 5. 결과

| 지표 | 값 |
|---|---:|
| Accuracy | 34.1% (15/44) |
| Precision | 61.1% (11/18) |
| Recall | 30.6% (11/36) |
| F1 | 40.7% |
| TP / FP / FN / TN | 11 / 7 / 25 / 4 |

- 완전 통과: `clean_match` 8/8, `clean_no_match` 4/4
- 0/5: 수수료 금액 차이, 시간창 초과, 코드 위치·오타, 코드 누락 유일 후보
- 0/2: 대리입금
- 부분 통과: 코드 충돌 2/5, 이름 부분문자열 오식별 1/5

## 6. 실패 분류·원인 가설

- 금액 허용오차·시간창·코드 정규화·코드 누락 후보화·대리입금이 현재 엔진의 처리 범위 밖 또는 불완전한 것으로 관찰됨
- 44케이스는 실제 실패를 담은 유용한 회귀 기반이지만, 사례 수가 작고 합성 데이터라 실운영 분포를 대표한다고 말할 수 없음
- 이번 실행은 원인을 수정하거나 성능을 개선하지 않았음

## 7. 판정

- 공통 runner는 원본 44케이스를 변경하지 않고 실제 엔진 결과를 재현함
- 엔진은 깨끗한 일치·명확한 불일치에는 동작하지만, 현실적인 예외 조건에서는 현재 출시 판단 근거로 충분하지 않음
- 쏜다는 L3 보존 상태이므로, 이번 결과만으로 기능 개선이나 재개 결정을 내리지 않음

## 8. 한계·다음 단계

- runner v1은 현재 쏜다 adapter만 제공. 냥민도감·팜로그 adapter는 Week 2 이후 실제 실행 trace가 준비된 뒤 추가
- 냥민도감은 Week 1에 범위 명세와 도메인 규칙 8건을 확보했으며, 실제 agent/Supabase/미디어 기능은 미구현 또는 미연결 상태
- 다음 실험은 냥민도감 8건을 공통 schema의 trace·gate 형식으로 옮기기 전에, 실제 trace를 수집할 수 있는 최소 실행면을 확정하는 것
