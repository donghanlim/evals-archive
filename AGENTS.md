# evals-archive — AI 작업 규칙

상위 규칙: `~/Documents/AGENTS.md` 를 먼저 읽는다. 아래는 이 프로젝트 고유 사항만.

- **슬러그**: `evals-archive` (한글명 evals 수집 파이프라인)
- **구역**: _personal
- **GitHub**: `donghanlim/evals-archive`

## 정본 위치 (3계층)

| 계층 | 위치 |
|---|---|
| L1 지식·결정 | `~/Documents/_personal/my_brain` 의 관련 노트 (`#evals-archive` 태그) |
| L2 원본·증빙 | `./files/` (심볼릭 링크, git 제외) |
| L3 코드·증거 | 이 저장소의 `src/` `docs/` `evidence/` |

## 작업 순서

1. `README.md` 로 현재 상태 확인
2. `docs/` 에서 설계·계획 확인
3. 작업 수행 후 `evidence/` 에 실행 결과 기록
4. 결정이 바뀌면 `README.md` 상태 갱신 + `my_brain` 노트 동기화
5. 커밋 `<type>: <한국어 요약>`
