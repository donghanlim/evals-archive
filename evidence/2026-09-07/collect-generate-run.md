# 2026-09-07 collect + generate 실행 기록

## 환경
- worktree: evals-search (branch `donghanlim/evals-search`, main과 동일 커밋 `54e40f7`)
- 최초 실행 — 이 worktree의 `evals.db` 는 이전까지 0건 상태였음

## init
```
$ python3 evals.py init
초기화 완료: .../evals.db
  [on ] arXiv — Agent Evals (arxiv)
  [on ] arXiv — LLM & AI Service Evals (arxiv)
  [on ] AWS Machine Learning Blog (rss)
  [on ] Hugging Face Blog (atom)
```

## collect --limit 60
```
{
 "candidates": 140,
 "new": 60,
 "dup_url": 0,
 "dup_similar": 0,
 "low_relevance": 80,
 "short_excerpt": 0,
 "feed_failures": 0,
 "errors": [],
 "run_id": 1,
 "status": "ok"
}
```
- 후보 140건 중 60건 신규 채택(적합), 80건 관련성 낮음으로 제외. 중복·오류 0건.

## generate
- 실행 시간: 약 8분 (백그라운드 폴링으로 확인, 240s 시점까지 진행 중 → 480s 근처 완료)
- 결과: notes 60건 전부 생성 완료
  - fallback(결정적 생성): 52건
  - groq:qwen/qwen3.8-27b: 4건
  - ollama:exaone3.5:7.8b: 4건
- LLM 공급자 다수가 fallback으로 빠진 원인은 미조사 (429/timeout 등 추정) — 다음 실행에서 공급자별 실패 사유 로그 확인 필요

## report (최종)
```
수집 140건 / 적합 후보 60건 / high 33건 / 사람 수용 0건 (검토 대기 60건)
모델: fallback 노트 52건 — LLM 미설정 또는 생성 실패
최근 실행 #1 ok · 2026-09-07T00:30:18+00:00
```

## 다음 행동
- `python3 evals.py review --port 8765` 로 60건 검토 대기 항목 사람 수용/반려 진행
- fallback 비중이 높은 원인(공급자 오류) 확인
