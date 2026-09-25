# 01. 쏜다 입금 대조 엔진 기준선. 44건으로 재현한 34.1%

* 날짜: 2026-09-07
* 원본: `../20-week-cycle-2026-09-07/reports/2026-09-07-r1-ssonda-baseline.md`
* 증거: `../../evidence/2026-09-07-week01-ssonda-baseline.json`
* 상태: 요약 발행

## 결론 3줄

1. 쏜다 golden 44건을 손대지 않고 공통 runner로 돌려 15/44를 재현했다.
2. 깨끗한 입금은 다 맞고, 수수료, 시간창, 오타, 누락, 대리입금은 다 틀렸다.
3. 이 엔진으로는 출시 판단이 안 된다. ssonda는 L3 보존이라 고치지 않는다.

## 무엇을 쟀나

* 대상: `ssonda/src/core.mjs`의 `reconcile` 함수
* 데이터: `ssonda/evals/golden.jsonl` 44건, SHA-256 `8536dfc...`
* 방법: exact match. LLM 심판 없음.
* 실행:

```bash
cd /Users/justimmacbook/Documents/_personal/evals-archive
python3 runner.py ssonda \
  --dataset /Users/justimmacbook/Documents/_work/_lab/ssonda/evals/golden.jsonl \
  --bridge /Users/justimmacbook/Documents/_work/_lab/ssonda/evals/bridge.mjs \
  --output evidence/2026-09-07-week01-ssonda-baseline.json
```

## 수치 1표

| 지표 | 값 |
|---|---:|
| Accuracy | 34.1% (15/44) |
| Precision | 61.1% (11/18) |
| Recall | 30.6% (11/36) |
| F1 | 40.7% |

완전 통과는 `clean_match` 8/8, `clean_no_match` 4/4뿐이다.
0점은 수수료 차이, 시간창 초과, 코드 위치/오타, 코드 누락, 대리입금이다.

## 실패에서 남은 것

* 엔진이 현실 예외를 못 다룬다는 게 확인됐다. 원인 수정은 안 했다.
* 44건은 합성 소수라 실운영 분포를 대표 못 한다. 회귀용으로는 유효하다.
* 공통 스키마 `golden.schema.json`와 `runner.py`가 이때 생겼다. 다음 로그의 바닥이다.

## 한계 2줄

1. ssonda adapter만 있다. 냥민도감, 팜로그 adapter는 trace 준비 뒤다.
2. 이 글은 결정론 엔진 기준선이다. AI agent 성능 일반화로 읽으면 안 된다.

## 다음 로그 예고

02편은 Spark vs Opus 5 High 파일럿이다. 모르면 비워라 업무에서 무료 모델이 유료 모델에 뒤지지 않은 실측 이야기다.
