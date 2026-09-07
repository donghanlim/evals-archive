# evals-archive · evals 수집 파이프라인

| 항목 | 값 |
|---|---|
| 슬러그 | `evals-archive` |
| 구역 | _personal |
| 로컬 | `/Users/justimmacbook/Documents/_personal/evals-archive` |
| GitHub | `donghanlim/evals-archive` |
| 상태 | 수집 파이프라인 첫 실행 완료 |
| 최종 갱신 | 2026-09-07 |

## 현재 상태

- `evals.py` (stdlib only, 1308줄) + `test_evals.py` 44/44 통과.
- 2026-09-07 첫 `collect` + `generate` 실행 (evals-search worktree, `evidence/2026-09-07/collect-generate-run.md`):
  후보 140건 → 적합 60건 채택(고관련 33건) → notes 60건 생성(fallback 52 · groq 4 · ollama 4).
  사람 검토(`review`)는 아직 미실행 — 60건 검토 대기.

## 다음 행동

- [ ] `python3 evals.py review --port 8765` 로 60건 사람 수용/반려 검토
- [ ] fallback 비중(52/60)이 높은 원인 — 공급자 실패 로그 확인
- [ ] 기존 자료를 `docs/` 로 이관
- [ ] `files/` 링크 대상 원본 정리

## 정본 링크

- 지식·결정: `~/Documents/_personal/my_brain` (`#evals-archive`)
- 원본·증빙: `./files/`
