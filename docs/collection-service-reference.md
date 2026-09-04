# AI Evals 자동 수집 서비스 — 운영·구현·코드 레퍼런스

> 이 문서는 AI 에이전트와 AI 서비스의 Evals(검증·평가) 자료를 4시간 단위로 수집하고, 중복·관련성·근거를 보존하면서 한국어 Markdown 학습자료로 축적하는 현재 수집 서비스의 단일 참조 문서입니다.

## 1. 서비스 목적

이 서비스는 초보 AI 개발자, 데이터사이언티스트, PM이 평가 대상·성공 기준·측정 지표·검증 방법을 학습할 수 있도록 공개 RSS/Atom 출처를 폭넓게 수집합니다. 단순히 결과만 남기지 않고 수용 자료, 정확 중복, 유사 중복, 무관 자료, 발췌문 부족, 피드 실패, LLM fallback을 실행 기록과 Markdown에 남겨 수집 품질을 검토할 수 있게 합니다.

## 2. 현재 운영 기준

| 항목 | 현재 기준 |
|---|---|
| 실행 방식 | Manus Heartbeat HTTP cron |
| 단일 작업 | `ai-evals-collector-recovery` |
| Task UID | `C5oMCa5z7uCr8hYTRDrFjA` |
| 주기 | `0 0 */4 * * *` — 4시간마다, UTC, 6-field cron |
| Callback | `POST /api/scheduled/collect-evals` |
| 후보 상한 | 실행당 최대 60건, 피드별 round-robin |
| LLM 예산 | 실행당 최대 1회 구조화 노트 생성 |
| 최소 근거 | 발췌문 100자 이상 |
| 논리 저장 경로 | `evals 업데이트 자료/YYYY-MM-DD_HH-mm.md` |
| 물리 저장 | S3에는 ASCII object key, DB에는 논리 경로 보존 |

## 3. 전체 데이터 흐름

```text
Heartbeat POST
  → cron 세션 인증 및 task UID로 archive_settings 조회
  → 활성 RSS/Atom 출처 병렬 로드
  → 피드별 round-robin 후보 선택
  → Evals 직접 관련성 + 발췌문 길이 필터
  → URL hash / 정규화 제목 / 태그·제목 유사도 중복 판정
  → 신규 후보만 LLM 구조화 노트 또는 deterministic fallback
  → articles + article_notes + duplicate_decisions 저장
  → Markdown 생성 → S3 업로드 → learning_documents 등록
  → run ledger 완료 및 신규 수용 시에만 소유자 알림
```

## 4. 판정·품질·중복 규칙

후보는 제목·URL·발췌문과 출처 메타데이터를 바탕으로 직접적인 Evals 관련성을 먼저 판정합니다. 관련성이 없거나 발췌문이 100자 미만이면 노트 생성 대상에서 제외하고 사유를 `duplicate_decisions`에 기록합니다. 정확 중복은 canonical URL hash 또는 정규화 제목 일치로 판단합니다. 정확 중복이 아니어도 제목 토큰과 핵심 주제 태그의 가중 유사도가 72% 이상이면 유사 중복으로 건너뜁니다.

자료가 수용되면 첫 번째 신규 자료에만 구조화 LLM을 호출합니다. 이후 신규 자료는 deterministic fallback note로 보존해 Heartbeat 2분 제한을 넘지 않도록 합니다. LLM 응답은 summary, practicalMeaning, tags, keyTerms, learningPoints 구조를 요구하고, 파싱 실패·필수 필드 누락·네트워크 오류는 fallback과 ledger의 `fallbackNoteCount`로 남깁니다.

## 5. 저장 모델

| 테이블 | 책임 |
|---|---|
| `archive_sources` | RSS/Atom 출처, 활성 상태, 마지막 오류 |
| `archive_settings` | singleton 설정, Heartbeat UID, 마지막 수집 시각 |
| `collection_runs` | 실행 시각, 후보·수용·제외·fallback·실패 통계 |
| `articles` | 원문 URL, 제목, 발췌문, 태그, 관련성 점수 |
| `article_notes` | 한국어 요약, 실무 의미, 핵심 용어, 학습 포인트, 유사 링크 |
| `duplicate_decisions` | accepted/skipped 결정, 매칭 문서, 점수, 근거 |
| `learning_documents` | 논리 파일명, S3 key/URL, 문서 생성 시각 |
| `user_document_progress` | 사용자별 읽기 완료 상태 — 수집 서비스와 대시보드 연결 |

## 6. 운영·보안 기준

Heartbeat handler는 `/api/scheduled/` 경로에서만 동작하며 cron 세션의 `taskUid`로 설정 행을 찾습니다. 요청 본문을 소유권 식별자로 사용하지 않습니다. 세션 cookie가 없거나 task UID가 없으면 인증 실패로 처리합니다. 수집은 idempotent한 URL·제목·유사도 판정을 사용하며, 5xx·429 재시도에 대비해 동일 후보가 중복 저장되지 않도록 합니다.

현재 서비스는 예약 작업을 하나만 유지합니다. 변경 시 기존 task UID를 기준으로 갱신하고, 새 작업을 중복 생성하지 않습니다. callback handler 변경 후에는 배포된 URL이 먼저 갱신되어야 하며, Heartbeat 플랫폼은 로컬 개발 URL을 호출하지 않습니다.

## 7. 장애·실패 기록 방식

피드 하나가 실패해도 나머지 출처는 `Promise.allSettled`로 계속 처리합니다. 실패한 출처 이름은 실행 Markdown에 기록합니다. 관련성 부족, 짧은 발췌문, 정확 중복, 유사 중복, LLM fallback은 숨기지 않고 판정 기록과 실행 ledger에 함께 남깁니다. 신규 수용이 0건인 실행도 운영 검토 Markdown을 만들며, 소유자 알림은 신규 수용 자료가 있을 때만 발송합니다.

## 8. 테스트·검증 기준

수집기 테스트는 피드별 공정 배분, 직접 Evals 관련성, 100자 발췌문 기준, URL·제목·태그 유사도 중복 판정, LLM 1회 예산과 fallback, Markdown 감사 기록을 검증합니다. 예약 테스트는 인증된 세션 cookie 전달, task UID 소유권, 4시간 기본 cron을 검증합니다. 실행 전후에는 `pnpm test`, `pnpm check`, `pnpm build`를 사용합니다.

## 9. 코드 부록 파일 목록

이 문서의 코드 부록은 현재 저장소에서 수집 서비스에 직접 관여하는 **14개 파일**을 읽어 생성했습니다. 각 블록의 경로는 저장소 기준 상대 경로입니다.

### `docs/implementation-and-operations-guide.md`

````markdown
# AI Evals Learning Archive: 구현 및 운영 가이드

> **문서 목적**: 이 문서는 AI 에이전트·AI 서비스의 Evals(검증·평가) 자료를 수집하고, 초보 개발자·데이터사이언티스트·PM용 한국어 학습 노트로 축적하는 아카이브의 실제 코드 구조와 운영 방법을 설명합니다. 구현 현황은 2026-08-26 기준입니다.

## 1. 시스템 개요

아카이브는 공개 RSS/Atom 피드에서 후보 자료를 읽고, AI Evals 관련성 및 중복 여부를 판단한 뒤, 새 자료만 하나의 Markdown 학습 노트로 통합합니다. 문서는 사용자가 요구한 논리 경로인 `evals 업데이트 자료/YYYY-MM-DD_HH-mm.md`로 DB에 기록됩니다. 실제 오브젝트 스토리지에는 ASCII 키를 사용하지만, 다운로드 시에는 논리 경로의 한글 파일명을 유지합니다.

| 구분 | 구현 선택 | 역할 |
| --- | --- | --- |
| 프런트엔드 | React 19, TypeScript, Tailwind CSS 4 | 인증된 운영 대시보드와 수동 제어 화면 |
| API | Express 4 + tRPC 11 | 대시보드 조회, 즉시 수집, 예약 연결, 일시정지 |
| 데이터 | Drizzle ORM + MySQL/TiDB | 수집 이력, 기사, 학습 노트, 통합 문서, 중복 결정 저장 |
| 파일 저장 | Forge/S3 signed URL | Markdown 원문 저장 및 안전한 다운로드 |
| 요약 생성 | `gpt-5-mini` 구조화 출력 + 결정적 fallback | 초보자용 한국어 학습 노트 생성 |
| 예약 실행 | Manus Heartbeat HTTP cron | 매 4시간 수집 콜백 호출 |
| 알림 | 소유자 알림 API | 새 Markdown 생성 시 생성 시각·신규 건수 전달 |

```mermaid
flowchart LR
  A[공개 RSS/Atom 출처] --> B[archiveCollector]
  B --> C{AI Evals 관련성}
  C -- 제외 --> D[duplicate_decisions: skipped_irrelevant]
  C -- 통과 --> E{URL/제목/유사도 중복}
  E -- 중복 --> F[duplicate_decisions: skipped_exact or skipped_similar]
  E -- 신규 --> G[LLM 학습 노트 또는 fallback]
  G --> H[articles + article_learning_notes]
  H --> I[통합 Markdown 생성]
  I --> J[S3 ASCII object key]
  J --> K[learning_documents: 논리 경로 유지]
  K --> L[소유자 알림]
  M[Heartbeat 4시간 cron] --> N[/api/scheduled/collect-evals]
  N --> B
  O[인증 대시보드] --> P[tRPC archive router]
  P --> B
  P --> K
```

## 2. 주요 파일과 책임

| 파일 | 주요 책임 |
| --- | --- |
| `server/archiveCollector.ts` | 피드 로드, 관련성·중복 판단, 학습 노트 생성, Markdown 통합, 알림, 실행 상태 기록 |
| `server/archiveUtils.ts` | URL·제목 정규화, 태그 추론, 관련성 필터, 유사도 점수, Markdown 본문 생성 |
| `server/archiveDb.ts` | 아카이브 DB CRUD, 단일 설정 행 보장, 대시보드 데이터 조립 |
| `server/archiveDownload.ts` | ID 기반 Markdown 다운로드와 UTF-8 파일명 응답 |
| `server/scheduledCollector.ts` | cron 전용 콜백 인증, task UID 대조, 수집 실행 |
| `server/routers.ts` | 인증된 대시보드 API, 즉시 수집, 4시간 예약 생성·토글 |
| `server/_core/heartbeat.ts` | Heartbeat 작업 생성·수정·조회용 Forge RPC 래퍼 |
| `drizzle/schema.ts` | 수집·문서·중복·설정 스키마 |
| `client/src/pages/Home.tsx` | 브루탈리즘 운영 대시보드, 문서 열기, 실행 ledger |
| `client/src/lib/archiveLinks.ts` | 배포 게이트웨이에 안전한 ASCII 문서 다운로드 경로 생성 |
| `client/src/lib/dashboardDisplay.ts` | 실행 ledger에 표시할 최신 이력 12건 제한 |

## 3. 데이터 모델

아카이브는 실행 단위와 기사 단위, 통합 문서 단위를 분리합니다. 이 구조 덕분에 수집 과정에서 걸러진 후보까지 `duplicate_decisions`에 남기면서, 사용자에게는 신뢰할 수 있는 통합 Markdown만 제공합니다.

| 테이블 | 핵심 컬럼 | 용도 |
| --- | --- | --- |
| `archive_settings` | `singletonKey`, `collectorEnabled`, `scheduleCronTaskUid`, `lastCollectedAt` | 전역 운영 설정. `singletonKey = archive`의 유일 제약으로 활성 설정을 하나만 유지 |
| `source_feeds` | `name`, `feedUrl`, `sourceType`, `enabled` | Atom/RSS 수집 출처 목록 |
| `collection_runs` | `status`, 건수 지표, `startedAt`, `completedAt` | 한 번의 수집 실행 이력 |
| `articles` | URL hash, 정규화 제목, 출처, 태그 | 통과한 원문 후보의 정규화 메타데이터 |
| `article_learning_notes` | 요약, 실무 의미, 용어, 학습 포인트 | 기사별 한국어 학습 노트 |
| `learning_documents` | `logicalPath`, `storageKey`, `storageUrl` | 한 실행에서 생성된 통합 Markdown |
| `duplicate_decisions` | 판정, 유사도, 매칭 기사, 사유 | 수용·정확 중복·유사 중복·무관 자료의 감사 ledger |

### 단일 설정 행 보호

초기 구현은 기본 설정을 삽입할 때 고유 키가 없어 여러 설정 행이 쌓일 수 있었습니다. 최신 행을 읽는 방식은 Heartbeat UID가 다른 행으로 이동한 것처럼 보이게 할 위험이 있었습니다. 이를 해결하기 위해 `archive_settings.singletonKey`에 고유 제약을 추가했고, 앱은 항상 `archive` 키의 행만 upsert·조회합니다.

```ts
// server/archiveDb.ts의 핵심 패턴
export const ARCHIVE_SETTINGS_SINGLETON_KEY = "archive";

await db.insert(archiveSettings)
  .values({ singletonKey: ARCHIVE_SETTINGS_SINGLETON_KEY })
  .onDuplicateKeyUpdate({ set: { updatedAt: new Date() } });

const settings = await db.select().from(archiveSettings)
  .where(eq(archiveSettings.singletonKey, ARCHIVE_SETTINGS_SINGLETON_KEY))
  .limit(1);
```

마이그레이션 `drizzle/0003_pretty_tiger_shark.sql`은 기존 행을 `legacy-{id}`로 보존하고, 예약 UID가 있는 최신 행을 `archive`로 승격한 뒤 유일 제약을 추가합니다. 따라서 기존 예약이 유실되지 않습니다.

## 4. 수집 파이프라인

### 4.1 출처와 파싱

활성 기본 출처는 **arXiv Agent Evals**, **arXiv LLM & AI Service Evals**, [AWS Machine Learning Blog](https://aws.amazon.com/blogs/machine-learning/feed/), [Hugging Face Blog](https://huggingface.co/blog/feed.xml)입니다. 이전의 지나치게 넓은 arXiv 검색 피드는 중복 후보 스캔을 줄이기 위해 비활성화했습니다. Atom은 `<entry>`, RSS는 `<item>` 블록에서 제목, 링크, 발행일, 발췌문을 추출합니다. 각 피드 요청은 18초 timeout과 식별용 user-agent를 사용합니다.

수집기는 `Promise.allSettled()`로 출처를 병렬 로드합니다. 한 피드가 실패해도 나머지 출처의 후보는 계속 처리하고, 실패 출처 수는 실행 결과를 `partial`로 기록하는 근거가 됩니다. 전역 후보 상한은 60건이지만, 단순히 피드 결과를 이어 붙이지 않고 피드별로 한 건씩 교차 선택합니다. 따라서 AWS·Hugging Face처럼 먼저 반환되는 대형 피드가 상한을 모두 차지해 후순위의 arXiv 직접 Evals 피드가 판정 기회를 잃는 현상을 방지합니다.

### 4.2 AI Evals 관련성 필터

일반적인 AI 뉴스가 섞이는 문제를 막기 위해 다음 세 조건과 최소 100자의 원문 발췌문을 모두 만족해야 자료를 수용합니다. 제목의 Evals 용어는 `eval` 단어 자체 또는 `evaluation`·`benchmarking`·`testing` 등의 실제 파생형을 확인하며, `retrieval` 안의 `eval` 같은 부분 문자열은 Evals 신호로 해석하지 않습니다.

| 조건 | 예시 키워드 |
| --- | --- |
| 본문 또는 발췌문의 평가 용어 | `eval`, `evaluation`, `benchmark`, `grader`, `testing`, `quality`, `regression`, `observability`, `safety` |
| 본문 또는 발췌문의 AI 앵커 | `AI agent`, `LLM`, `language model`, `AI service`, `assistant`, `MCP`, `RAG`, `tool use` |
| 제목의 평가 용어 | `eval`, `benchmark`, `grading`, `testing`, `regression`, `observability` |

조건을 통과하지 못한 후보도 버려지지 않고 `duplicate_decisions`에 `skipped_irrelevant`로 남습니다. 따라서 대시보드의 ledger는 왜 자료가 수집되지 않았는지 설명할 수 있습니다.

### 4.3 중복 및 유사도 판정

중복 판정은 비용이 낮고 확실한 검사부터 순서대로 수행합니다.

1. URL의 UTM·ref 파라미터와 fragment를 제거하고 SHA-256 hash를 생성합니다.
2. 제목을 소문자·공백·한글/영문/숫자 중심으로 정규화합니다.
3. URL hash 또는 정규화 제목이 일치하면 `skipped_exact`로 기록합니다.
4. 일치하지 않으면 제목 토큰 Jaccard 유사도 65%와 태그 Jaccard 유사도 35%를 가중합합니다.
5. 최종 점수가 **72 이상**이면 `skipped_similar`로 기록합니다.

수식은 다음과 같습니다.

```text
similarity = round((Jaccard(title_tokens) × 0.65 + Jaccard(tags) × 0.35) × 100)
```

수용된 후보는 한 실행에서 최대 5건입니다. 각 노트에는 **직접 Evals 관련성 및 100자 이상 발췌문**을 통과한 과거 기사만 대상으로 연관도를 계산하며, 유사도 28 이상 또는 공통 태그 2개 이상인 자료를 최대 3개까지 연결합니다.

## 5. 한국어 학습 노트 생성

수용 후보는 `gpt-5-mini`에 JSON schema 응답 형식으로 전달됩니다. Heartbeat 콜백의 실행 제한을 지키기 위해 한 실행에서 첫 수용 후보에만 LLM을 호출하고, 같은 실행에서 추가 수용된 후보는 즉시 결정적 fallback으로 정리합니다. 이 방식은 여러 신규 자료가 한꺼번에 들어와도 Markdown·중복 ledger·알림의 완결성을 유지하면서 콜백 지연을 줄입니다. 스키마는 다음 필드를 강제합니다.

| 필드 | 제약 |
| --- | --- |
| `summary` | 200자 이하 핵심 요약 |
| `practicalMeaning` | 260자 이하 실무 의미 |
| `tags` | 허용 토픽 태그 1~5개 |
| `keyTerms` | 용어·정의 2~4개 |
| `learningPoints` | 학습 포인트 2~4개 |

LLM 출력이 잘리거나 JSON 파싱에 실패해도 수집이 중단되지 않습니다. `fallbackNote()`이 결정적인 한국어 요약, 실무 의미, 기본 용어와 학습 포인트를 반환하므로, 운영의 연속성을 유지합니다. 이 fallback은 품질을 과장하지 않고 원문을 확인하도록 안내하는 보수적 문구를 사용합니다.

## 6. Markdown 생성과 저장 경로

통합 Markdown에는 업데이트 요약, 태그, 자료별 원문 링크, 핵심 요약, 초보자를 위한 실무 의미, 용어 표, 학습 포인트, 이전 자료 연결, 생성 시각과 논리 경로가 포함됩니다.

```text
논리 경로: evals 업데이트 자료/YYYY-MM-DD_HH-mm.md
실제 키:    evals-update-materials/YYYY-MM-DD_HH-mm-<random-hash>.md
```

한글 논리 경로는 사용 경험과 요구사항을 위해 `learning_documents.logicalPath`에 그대로 저장합니다. 반면 저장 서비스는 ASCII object key를 요구하므로 `toStorageObjectKey()`가 영문·숫자·`.`·`_`·`-`만 사용하도록 변환합니다. 저장 도우미는 같은 파일명 충돌을 막기 위해 8자리 hash 접미사도 추가합니다.

### 다운로드와 한글 URL 404 대응

초기 대시보드는 논리 경로를 URL 인코딩한 `/<한글 경로>`를 직접 열었습니다. 일부 배포 게이트웨이에서는 이 한글 경로가 Express 라우트에 도달하기 전에 404가 날 수 있었습니다. 현재 대시보드는 아래의 배포 안전 경로만 사용합니다.

```ts
// client/src/lib/archiveLinks.ts
getLearningDocumentDownloadPath(documentId)
// => /api/archive/documents/:id/download
```

서버 `downloadLearningDocument()`는 인증 뒤 DB의 `storageKey`로 presigned GET URL을 받아 Markdown을 스트리밍합니다. `Content-Disposition`에는 원래 논리 경로의 한글 파일명을 UTF-8로 넣어 사용자가 받는 파일 이름은 유지합니다.

## 7. 4시간 예약 실행

대시보드의 `Link 4H Schedule`은 아래 Heartbeat 작업을 생성합니다.

| 항목 | 값 |
| --- | --- |
| 기본 작업 이름 | `ai-evals-collector` |
| 현재 운영 작업 이름 | `ai-evals-collector-recovery` |
| 현재 운영 task UID | `C5oMCa5z7uCr8hYTRDrFjA` |
| cron | `0 0 */4 * * *` |
| 시간대 | UTC, 초·분·시를 포함한 6필드 cron |
| 콜백 | `POST /api/scheduled/collect-evals` |
| 주기 | UTC 정각 기준 매 4시간 |

예약은 배포된 공개 사이트에서만 생성할 수 있습니다. `configureSchedule`은 이미 저장된 `scheduleCronTaskUid`가 있으면 새 작업을 만들지 않으므로 중복 예약을 방지합니다. 예약 생성과 pause/resume은 현재 로그인 사용자의 `app_session_id`를 Heartbeat API에 전달합니다. 세션 쿠키가 없으면 요청은 `UNAUTHORIZED`로 끝나며 project-owner identity로 fallback하지 않습니다. 따라서 작업을 실제로 생성·관리하는 사용자와 DB에 저장되는 task UID의 소유자 컨텍스트가 일치합니다. pause/resume은 Heartbeat 활성 상태와 DB의 `collectorEnabled`를 함께 갱신합니다.

콜백은 단순한 공개 HTTP endpoint가 아닙니다. `runScheduledEvalsCollector()`는 다음을 확인합니다.

1. 요청 인증 결과가 `isCron = true`인지 확인합니다.
2. 요청의 `taskUid`가 있는지 확인합니다.
3. 단일 설정 행에 저장된 `scheduleCronTaskUid`와 일치하는지 확인합니다.
4. 수집기가 pause 상태면 정상 응답과 함께 건너뜁니다.
5. 일치하지 않는 고아 작업은 수집하지 않고 `skipped: orphan`으로 끝냅니다.

이 확인 과정 덕분에 일반 로그인 사용자나 오래된 예약 task가 수집기를 호출할 수 없습니다.

## 8. 소유자 알림과 실패 처리

새 통합 Markdown이 생성되면 `notifyOwner()`에 논리 경로, 신규 자료 수, UTC 생성 시각을 포함한 알림을 보냅니다. 첫 호출이 `false`이면 한 번 더 재시도합니다. 두 번 모두 실패하거나 예외가 발생하면 수집 자체는 보존하되 실행 상태를 `partial`로 기록합니다.

| 상황 | 실행 결과 |
| --- | --- |
| 모든 출처·알림 정상 | `success` |
| 일부 피드 실패 | `partial` |
| 알림 두 차례 실패 | `partial` |
| 수집 처리 중 예외 | `failed` |

## 9. 운영 대시보드와 최근 UI 개선

대시보드는 굵은 검정 타이포그래피, 흰 배경, 두꺼운 선, 비대칭 그리드를 사용하는 타이포그래픽 브루탈리즘으로 구성했습니다. 로그인한 사용자는 다음 상태를 볼 수 있습니다.

| 영역 | 표시 내용 |
| --- | --- |
| 상단 상태 | Collector 활성/일시정지, 마지막 수집 시각 |
| Manual control | 즉시 수집, 예약 연결, pause/resume |
| Generated learning notes | 통합 Markdown 이력과 안전한 다운로드 버튼 |
| Run status | 실행 결과, 신규 건수, skip 수, 시작 시각 |
| Duplicate decision ledger | 수용·중복·무관 판정과 사유·태그 |

### Run status 고정 높이 개선

기존에는 최근 실행을 큰 카드 여러 장으로 세로 나열해서 이력이 쌓일수록 오른쪽 열이 길어졌습니다. 현재는 `Execution ledger`로 변경했습니다.

- 고정 높이 `ScrollArea`(`h-[20rem]`) 안에서만 실행 목록을 스크롤합니다.
- 최신 12건만 `getRunLedgerRows()`로 제한합니다.
- 각 행은 실행 ID, 상태·시각·skip 수, 신규 건수의 3열 구조입니다.
- 데스크톱과 모바일 화면에서 고정 높이가 유지되는 것을 확인했습니다.

## 10. 검증 및 테스트

현재 테스트 구성은 Vitest **10개 파일, 23개 테스트**입니다.

| 테스트 범주 | 검증 내용 |
| --- | --- |
| 유틸리티 | URL 정규화, 태그, 관련성, 유사도, 논리 경로, Markdown, ASCII 저장 키 |
| 수집기 | 통합 Markdown 생성, DB 기록, 알림 재시도와 partial 상태, 피드별 후보 공정 배분 |
| 예약 | 4시간 cron 생성, 중복 생성 방지, cron-only 콜백 인증 |
| 다운로드 | UTF-8 파일명, 논리 경로 해석 |
| 설정 singleton | 설정 행 1개 유지와 Heartbeat UID 지속성 |
| 프런트엔드 링크 | ASCII 문서 다운로드 경로 생성 |
| 실행 ledger | 최신 12건 제한과 빈 이력 처리 |

검증 명령은 다음과 같습니다.

```bash
pnpm test
pnpm check
pnpm build
```

최근 검증에서 세 명령은 모두 통과했습니다. Vite는 JavaScript 번들 크기 경고를 출력하지만 빌드는 성공합니다.

## 11. 운영 점검 절차

| 상황 | 확인 순서 |
| --- | --- |
| 문서 다운로드 문제 | 대시보드에서 ↗ 버튼을 사용하고 `/api/archive/documents/:id/download` 요청 여부를 확인 |
| 예약이 연결되지 않음 | 공개 배포 여부 확인 → `archive_settings.scheduleCronTaskUid` 확인 → Heartbeat 목록 확인 |
| 예약이 실행되지 않음 | task UID, `collectorEnabled`, Heartbeat 활성 상태, cron 콜백 로그를 순서대로 확인 |
| 수집 결과가 없음 | `collection_runs`의 `scannedCount`·수용/중복 건수와 `duplicate_decisions`의 `skipped_irrelevant` 사유를 확인 |
| LLM 노트 품질 저하 | fallback 사용 여부를 로그에서 확인하고 원문·태그·관련성 규칙을 점검 |
| 대시보드가 길어짐 | Run status는 고정 높이 ledger이므로 내부 스크롤과 표시 행 제한을 먼저 확인 |

### 현재 운영 상태

공개 운영 주소는 [https://aievals-vmsjksfp.manus.space](https://aievals-vmsjksfp.manus.space)입니다. 기존 작업의 실행 시각이 정체된 것을 확인한 뒤 해당 작업은 제거했으며, 현재 Heartbeat 작업 `ai-evals-collector-recovery`(UID `C5oMCa5z7uCr8hYTRDrFjA`) **1개만** `0 0 */4 * * *` UTC로 활성화합니다. AI 에이전트·AI 서비스의 다양한 직접 Evals 자료를 폭넓게 수집하고, 초보 개발자·데이터사이언티스트·PM이 검증·평가 역량을 쌓을 수 있는 근거 중심 학습 노트를 만드는 것을 운영 목표로 둡니다.

### 교체 전 품질 비교 기준선

교체 후 검증은 단순히 실행 성공 여부가 아니라, 아래 기준선과의 비교를 포함합니다. 품질 필터가 적용되기 전 최근 기준 실행 `300001`, `330001`은 각각 60건을 스캔해 59건을 무관으로 제외하고 1건을 정확 중복으로 처리했습니다. 필터 강화 직후의 수동 품질 점검 실행 `360001`, `390001`은 각각 1건을 수용했지만, 생성 문서의 원문 발췌 길이가 새 100자 기준을 충족하지 않아 대시보드에서 숨겨집니다.

교체 후에는 **임시 cron 검증 창에서** 플랫폼이 시작한 두 실행이 모두 `is_manual_trigger = false`, HTTP 200, `success`로 끝났습니다. 이는 새 task UID·cron 인증·콜백·수집 파이프라인의 연결이 작동함을 보여 줍니다. 임시 검증 창을 마친 뒤 작업은 즉시 원래의 매 4시간 cron으로 복원했고, 플랫폼 목록에서 마지막 실행 시각과 다음 실행 시각(`2026-08-27 00:00 UTC`)도 확인했습니다. 다만 이 두 실행은 자연 발생한 4시간 주기 자체의 연속성 증거와는 구분하며, 해당 검증은 이후의 원래 cron 실행 로그로 별도 완료해야 합니다.

| 구분 | 실행 ID | 스캔 | 수용 | 정확 중복 | 무관 제외 | 결과와 품질 확인 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 교체 전 기준 | `300001` | 60 | 0 | 1 | 59 | 성공, 적격 신규 자료 없음 |
| 교체 전 기준 | `330001` | 60 | 0 | 1 | 59 | 성공, 적격 신규 자료 없음 |
| 교체 후 임시 검증 1차 | `420001` | 60 | 1 | 1 | 58 | AWS의 **Amazon Bedrock AgentCore Evaluations** 자료를 수용했고, 발췌문 길이 352자로 100자 기준을 충족. `evals 업데이트 자료/2026-08-27_05-47.md` 생성 |
| 교체 후 임시 검증 2차 | `450001` | 60 | 0 | 2 | 58 | 성공. 수용 가능한 새 자료는 없었으나 모든 후보가 무관 또는 정확 중복 ledger 사유로 남음 |

두 교체 후 실행의 합계는 120건 스캔, 1건 수용, 3건 정확 중복, 116건 무관 제외이며 오류 판정은 0건입니다. 이는 수집기가 단순히 자료 수를 늘리는 대신, 직접 Evals 기준과 발췌문 품질 조건을 충족하지 못한 후보를 보수적으로 제외하고 있음을 보여 줍니다. 수용 건수가 0인 실행도 적격 신규 자료가 없고 ledger가 근거를 남긴 경우에는 정상 결과로 해석합니다.

### 직접 arXiv 출처 공급성 확인

피드별 라운드로빈 배분을 배포한 뒤의 검증 실행 `480001`에서는 네 활성 출처가 각각 15건씩, 총 60건의 판정 기회를 받았습니다. 특히 새 `arXiv — LLM & AI Service Evals` 출처는 **RAG 평가** 자료 1건을 수용했고, 원문 발췌문은 1,319자로 최소 근거 기준을 충분히 넘었습니다. `arXiv — Agent Evals`도 에이전트 워크플로 벤치마크·trace-aware 평가 관련 3건을 수용했습니다.

| 출처 | 판정 후보 | 수용 | 무관 제외 | 정확 중복 | 확인 결과 |
| --- | ---: | ---: | ---: | ---: | --- |
| arXiv — Agent Evals | 15 | 3 | 12 | 0 | Agent workflow benchmark·trace-aware 평가 자료 수용 |
| arXiv — LLM & AI Service Evals | 15 | 1 | 14 | 0 | **The RAT: A Unified Bayesian Model for RAG Evaluation** 수용 |
| AWS Machine Learning Blog | 15 | 0 | 13 | 2 | 기존 자료는 중복으로 보존, 비직접 후보는 제외 |
| Hugging Face Blog | 15 | 0 | 15 | 0 | 직접 Evals 기준을 만족한 신규 후보 없음 |

이 실행은 피드 공정 배분과 새 직접 출처의 실제 후보 공급을 검증했다. 다만 네 자료가 한 번에 수용되어 기존 콜백의 LLM 처리 시간이 길어졌으므로, 이후 배포본은 실행당 LLM 생성 1건 예산을 적용한다. 다음 4시간 수집에서는 이 시간 보호가 적용된 상태의 성공 로그와 출처 ledger를 다시 확인한다.

LLM 시간 예산 보완 뒤의 비수동 실행 `540001`은 HTTP 200으로 7,435ms 안에 완료됐습니다. 이번 실행은 60건 중 수용 자료가 없었지만, 이는 수집 실패가 아니라 이미 저장된 자료와의 중복 또는 직접 Evals 기준 미충족을 ledger에 남긴 결과입니다.

| 출처 | 검토 후보 | 수용 | 무관 제외 | 정확 중복 | 해석 |
| --- | ---: | ---: | ---: | ---: | --- |
| arXiv — Agent Evals | 15 | 0 | 12 | 3 | 이전 실행에서 수용한 직접 자료와의 중복을 보존 |
| arXiv — LLM & AI Service Evals | 15 | 0 | 14 | 1 | 새 직접 출처를 실제로 전수 검토했으며, 이번 창에는 신규 적격 자료 없음 |
| AWS Machine Learning Blog | 15 | 0 | 13 | 2 | 중복과 비직접 후보를 분리해 제외 |
| Hugging Face Blog | 15 | 0 | 15 | 0 | 직접 Evals 기준에 맞는 신규 후보 없음 |

따라서 시간 예산 보완은 수용 자료가 없어도 빠르게 판정을 끝내며, 새 arXiv 출처도 전역 후보 상한에 가려지지 않고 매 실행마다 15건의 검토 기회를 받는 것을 확인했습니다.

## 12. 유지보수 원칙

새 출처를 추가할 때는 `DEFAULT_SOURCES`에 RSS/Atom URL과 타입을 정의하고, 관련성 필터가 해당 출처의 제목 형식에도 과도하게 좁거나 넓지 않은지 점검합니다. 기본 출처에는 AI 에이전트 평가 전용 arXiv 검색과 LLM·AI 서비스 평가 전용 arXiv 검색을 함께 둡니다. 태그 규칙과 72점 유사도 임계값은 운영 ledger를 살펴본 뒤 조정해야 하며, 임계값 변경 전후의 skip 비율과 수용 자료의 직접성을 함께 비교하는 것이 좋습니다.

예약 실행 코드는 `setInterval`이나 `node-cron`으로 대체하지 않습니다. 배포 인스턴스는 항상 실행되지 않을 수 있으므로, Heartbeat와 `/api/scheduled/` 콜백의 인증 계약을 유지해야 합니다. DB 설정은 반드시 singleton key를 통해 읽고 갱신해야 하며, 예약 task UID를 새 설정 행에 분산시키지 않아야 합니다.

---

## 참고 코드 및 운영 문서

- [`server/archiveCollector.ts`](../server/archiveCollector.ts): 수집·학습 노트·알림 핵심 구현
- [`server/archiveUtils.ts`](../server/archiveUtils.ts): 관련성·중복·Markdown 유틸리티
- [`server/scheduledCollector.ts`](../server/scheduledCollector.ts): 예약 콜백 인증
- [`server/routers.ts`](../server/routers.ts): 대시보드·예약 tRPC API
- [`docs/operations-handoff.md`](./operations-handoff.md): 배포·예약 인수인계 요약
````

### `docs/operations-handoff.md`

````markdown
# 운영 인수인계: AI Evals Learning Archive

## 현재 준비 상태

수집, URL·제목·주제 태그 기반 중복 방지, 한국어 학습 Markdown 생성, 논리 경로 다운로드, 소유자 알림, 운영 대시보드, 예약 콜백은 구현되어 있다. `pnpm test`, `pnpm check`, `pnpm build`는 2026-08-26에 통과했으며, 테스트는 10개 파일·23개 항목을 포함한다. `archive_settings`는 `singletonKey = archive`의 유일 제약으로 단일 활성 설정을 유지하므로, 예약 UID가 새 설정 행에 의해 유실되지 않는다.

## 프로덕션 전제 조건

4시간 수집은 프로덕션 사이트의 `/api/scheduled/collect-evals` 콜백으로 실행되는 Heartbeat 작업이다. 개발 미리보기 URL은 예약 작업의 대상이 될 수 없으므로, **현재 체크포인트를 먼저 Publish한 뒤** 예약을 생성해야 한다. cron 식은 UTC 기준 `0 0 */4 * * *`이다.

현재 배포된 공개 운영 URL은 [https://aievals-vmsjksfp.manus.space](https://aievals-vmsjksfp.manus.space)이다. 이 URL의 루트 경로는 로그인 화면으로 정상 응답하며, `manus-webdev://…` 형식은 일반 웹 브라우저에서 여는 공개 URL이 아니라 프로젝트 관리 화면 안에서 사용하는 체크포인트 식별자다.

기존 `ai-evals-collector` 작업은 다음 실행 시각이 갱신되지 않아 2026-08-26에 제거했다. 현재 `ai-evals-collector-recovery` Heartbeat 예약이 활성화되어 있으며, task UID는 `C5oMCa5z7uCr8hYTRDrFjA`이다. 이 UID는 `archive_settings.scheduleCronTaskUid`에 저장돼 있고, 사용자 요청에 따라 cron 식은 **`0 0 */4 * * *`**로 전환됐다. 갱신 명령은 플랫폼 시간 초과를 표시했지만, 직후 목록 조회에서 cron·설명·활성 상태가 모두 새 값으로 반영된 것을 확인했다. 4시간 주기는 폭넓은 직접 Evals 자료의 수집·정리와 제외 근거 보존을 우선하는 운영 기준이다.

공정 배분 배포 후 검증 실행 `480001`은 arXiv Agent Evals에서 3건, 새 arXiv LLM & AI Service Evals에서 1건을 수용해 후순위 직접 출처가 실제 판정·수용 대상에 포함됨을 확인했다. 이 실행은 여러 LLM 호출로 애플리케이션 수집 완료 시각이 늦어졌으므로, 최신 배포본은 실행당 LLM 호출을 첫 수용 자료 1건으로 제한한다. 다음 자연 발생 실행에서는 이 시간 예산 보호가 적용된 HTTP 성공 상태를 확인한다.

시간 예산 보완 뒤의 예약 실행 `540001`은 HTTP 200·7,435ms로 완료됐다. 4개 활성 출처는 각각 15건씩 공정하게 검토됐으며, 특히 `arXiv — LLM & AI Service Evals`는 15건 중 신규 수용 0건, 무관 제외 14건, 정확 중복 1건으로 기록됐다. 신규 학습자료가 없는 실행도 다음 배포본에서는 검색 범위·중복·제외 근거를 담은 운영 검토 Markdown으로 보존한다.

| 항목 | 값 |
| --- | --- |
| 콜백 경로 | `/api/scheduled/collect-evals` |
| 주기 | 매 4시간 정각, UTC |
| 인증 | cron 전용 `isCron` 및 저장된 `taskUid` 대조 |
| 작업 소유자 | 예약 생성·pause/resume 시 로그인 사용자의 `app_session_id`를 Heartbeat API에 전달하며, 쿠키가 없으면 owner fallback 없이 `UNAUTHORIZED` 반환 |
| 실행 제한 | 2분, 재시도 가능하므로 수집기는 멱등적으로 동작 |
| 알림 | 새 Markdown 생성 후 소유자 알림, 실패 시 1회 재시도 |
| LLM 시간 예산 | 실행당 첫 수용 후보 1건만 구조화 LLM 노트 생성, 나머지는 결정적 fallback으로 즉시 처리 |

## 게시 뒤 운영 확인 순서

게시가 확인되면 예약을 한 번 생성하고 `manus-heartbeat list`로 task UID·활성 상태·다음 실행 시각을 확인한다. 첫 예약 실행 뒤에는 실행 이력, 생성된 `evals 업데이트 자료/YYYY-MM-DD_HH-mm.md` 논리 경로, 중복 결정 기록, 소유자 알림 결과를 함께 확인한다. 인증된 브라우저 세션에서 대시보드의 문서 목록·수집 이력·중복 ledger·예약 상태도 검증한다.
````

### `drizzle/schema.ts`

````typescript
import { boolean, index, int, mysqlEnum, mysqlTable, text, timestamp, uniqueIndex, varchar } from "drizzle-orm/mysql-core";

/**
 * Core user table backing auth flow.
 * Extend this file with additional tables as your product grows.
 * Columns use camelCase to match both database fields and generated types.
 */
export const users = mysqlTable("users", {
  /**
   * Surrogate primary key. Auto-incremented numeric value managed by the database.
   * Use this for relations between tables.
   */
  id: int("id").autoincrement().primaryKey(),
  /** Manus OAuth identifier (openId) returned from the OAuth callback. Unique per user. */
  openId: varchar("openId", { length: 64 }).notNull().unique(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

export const archiveSettings = mysqlTable("archive_settings", {
  id: int("id").autoincrement().primaryKey(),
  singletonKey: varchar("singletonKey", { length: 32 }).notNull().default("archive"),
  collectorEnabled: boolean("collectorEnabled").notNull().default(true),
  scheduleCronTaskUid: varchar("scheduleCronTaskUid", { length: 65 }),
  lastCollectedAt: timestamp("lastCollectedAt"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
}, table => [uniqueIndex("archive_settings_singleton_key_unique").on(table.singletonKey)]);

export const sourceFeeds = mysqlTable("source_feeds", {
  id: int("id").autoincrement().primaryKey(),
  name: varchar("name", { length: 120 }).notNull(),
  feedUrl: varchar("feedUrl", { length: 2048 }).notNull(),
  sourceType: mysqlEnum("sourceType", ["atom", "rss"]).notNull(),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
}, table => [uniqueIndex("source_feeds_feed_url_unique").on(table.feedUrl)]);

export const collectionRuns = mysqlTable("collection_runs", {
  id: int("id").autoincrement().primaryKey(),
  status: mysqlEnum("status", ["running", "success", "partial", "failed"]).notNull().default("running"),
  scannedCount: int("scannedCount").notNull().default(0),
  acceptedCount: int("acceptedCount").notNull().default(0),
  skippedExactCount: int("skippedExactCount").notNull().default(0),
  skippedSimilarCount: int("skippedSimilarCount").notNull().default(0),
  errorMessage: text("errorMessage"),
  startedAt: timestamp("startedAt").defaultNow().notNull(),
  completedAt: timestamp("completedAt"),
});

export const articles = mysqlTable("articles", {
  id: int("id").autoincrement().primaryKey(),
  collectionRunId: int("collectionRunId"),
  urlHash: varchar("urlHash", { length: 64 }).notNull(),
  canonicalUrl: varchar("canonicalUrl", { length: 2048 }).notNull(),
  title: text("title").notNull(),
  normalizedTitle: varchar("normalizedTitle", { length: 512 }).notNull(),
  sourceName: varchar("sourceName", { length: 120 }).notNull(),
  sourceFeedUrl: varchar("sourceFeedUrl", { length: 2048 }).notNull(),
  publishedAt: timestamp("publishedAt"),
  contentExcerpt: text("contentExcerpt"),
  tagsJson: text("tagsJson").notNull(),
  relevanceScore: int("relevanceScore").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
}, table => [
  uniqueIndex("articles_url_hash_unique").on(table.urlHash),
  index("articles_created_at_idx").on(table.createdAt),
]);

export const learningDocuments = mysqlTable("learning_documents", {
  id: int("id").autoincrement().primaryKey(),
  collectionRunId: int("collectionRunId").notNull(),
  logicalPath: varchar("logicalPath", { length: 512 }).notNull(),
  storageKey: varchar("storageKey", { length: 1024 }).notNull(),
  storageUrl: varchar("storageUrl", { length: 2048 }).notNull(),
  summary: text("summary").notNull(),
  practicalMeaning: text("practicalMeaning").notNull(),
  keyTermsJson: text("keyTermsJson").notNull(),
  learningPointsJson: text("learningPointsJson").notNull(),
  similarityLinksJson: text("similarityLinksJson").notNull(),
  generatedAt: timestamp("generatedAt").defaultNow().notNull(),
}, table => [
  uniqueIndex("learning_documents_run_unique").on(table.collectionRunId),
  uniqueIndex("learning_documents_path_unique").on(table.logicalPath),
  index("learning_documents_generated_at_idx").on(table.generatedAt),
]);

export const userDocumentProgress = mysqlTable("user_document_progress", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull(),
  learningDocumentId: int("learningDocumentId").notNull(),
  completedAt: timestamp("completedAt").defaultNow().notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
}, table => [
  uniqueIndex("user_document_progress_user_document_unique").on(table.userId, table.learningDocumentId),
  index("user_document_progress_user_updated_idx").on(table.userId, table.updatedAt),
]);

export const articleLearningNotes = mysqlTable("article_learning_notes", {
  id: int("id").autoincrement().primaryKey(),
  articleId: int("articleId").notNull(),
  summary: text("summary").notNull(),
  practicalMeaning: text("practicalMeaning").notNull(),
  keyTermsJson: text("keyTermsJson").notNull(),
  learningPointsJson: text("learningPointsJson").notNull(),
  similarityLinksJson: text("similarityLinksJson").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
}, table => [uniqueIndex("article_learning_notes_article_unique").on(table.articleId)]);

export const duplicateDecisions = mysqlTable("duplicate_decisions", {
  id: int("id").autoincrement().primaryKey(),
  collectionRunId: int("collectionRunId").notNull(),
  candidateUrlHash: varchar("candidateUrlHash", { length: 64 }).notNull(),
  candidateTitle: text("candidateTitle").notNull(),
  sourceName: varchar("sourceName", { length: 120 }).notNull(),
  decision: mysqlEnum("decision", ["accepted", "skipped_exact", "skipped_similar", "skipped_irrelevant", "error"]).notNull(),
  similarityScore: int("similarityScore"),
  matchedArticleId: int("matchedArticleId"),
  tagsJson: text("tagsJson").notNull(),
  reason: text("reason").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
}, table => [index("duplicate_decisions_run_idx").on(table.collectionRunId)]);

export type ArchiveSettings = typeof archiveSettings.$inferSelect;
export type SourceFeed = typeof sourceFeeds.$inferSelect;
export type CollectionRun = typeof collectionRuns.$inferSelect;
export type Article = typeof articles.$inferSelect;
export type LearningDocument = typeof learningDocuments.$inferSelect;
export type UserDocumentProgress = typeof userDocumentProgress.$inferSelect;
export type ArticleLearningNote = typeof articleLearningNotes.$inferSelect;
````

### `package.json`

````json
{
  "name": "ai-evals-learning-archive",
  "version": "1.0.0",
  "type": "module",
  "license": "MIT",
  "scripts": {
    "dev": "NODE_ENV=development tsx watch server/_core/index.ts",
    "build": "vite build && esbuild server/_core/index.ts --platform=node --packages=external --bundle --format=esm --outdir=dist",
    "start": "NODE_ENV=production node dist/index.js",
    "check": "tsc --noEmit",
    "format": "prettier --write .",
    "test": "vitest run",
    "db:push": "drizzle-kit generate && drizzle-kit migrate"
  },
  "dependencies": {
    "@aws-sdk/client-s3": "^3.693.0",
    "@aws-sdk/s3-request-presigner": "^3.693.0",
    "@hookform/resolvers": "^5.2.2",
    "@radix-ui/react-accordion": "^1.2.12",
    "@radix-ui/react-alert-dialog": "^1.1.15",
    "@radix-ui/react-aspect-ratio": "^1.1.7",
    "@radix-ui/react-avatar": "^1.1.10",
    "@radix-ui/react-checkbox": "^1.3.3",
    "@radix-ui/react-collapsible": "^1.1.12",
    "@radix-ui/react-context-menu": "^2.2.16",
    "@radix-ui/react-dialog": "^1.1.15",
    "@radix-ui/react-dropdown-menu": "^2.1.16",
    "@radix-ui/react-hover-card": "^1.1.15",
    "@radix-ui/react-label": "^2.1.7",
    "@radix-ui/react-menubar": "^1.1.16",
    "@radix-ui/react-navigation-menu": "^1.2.14",
    "@radix-ui/react-popover": "^1.1.15",
    "@radix-ui/react-progress": "^1.1.7",
    "@radix-ui/react-radio-group": "^1.3.8",
    "@radix-ui/react-scroll-area": "^1.2.10",
    "@radix-ui/react-select": "^2.2.6",
    "@radix-ui/react-separator": "^1.1.7",
    "@radix-ui/react-slider": "^1.3.6",
    "@radix-ui/react-slot": "^1.2.3",
    "@radix-ui/react-switch": "^1.2.6",
    "@radix-ui/react-tabs": "^1.1.13",
    "@radix-ui/react-toggle": "^1.1.10",
    "@radix-ui/react-toggle-group": "^1.1.11",
    "@radix-ui/react-tooltip": "^1.2.8",
    "@tanstack/react-query": "^5.90.2",
    "@trpc/client": "^11.6.0",
    "@trpc/react-query": "^11.6.0",
    "@trpc/server": "^11.6.0",
    "axios": "^1.12.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "cmdk": "^1.1.1",
    "cookie": "^1.0.2",
    "date-fns": "^4.1.0",
    "dotenv": "^17.2.2",
    "drizzle-orm": "^0.44.5",
    "embla-carousel-react": "^8.6.0",
    "express": "^4.21.2",
    "framer-motion": "^12.23.22",
    "input-otp": "^1.4.2",
    "jose": "6.1.0",
    "lucide-react": "^0.453.0",
    "mysql2": "^3.15.0",
    "nanoid": "^5.1.5",
    "next-themes": "^0.4.6",
    "react": "^19.2.1",
    "react-day-picker": "^9.11.1",
    "react-dom": "^19.2.1",
    "react-hook-form": "^7.64.0",
    "react-resizable-panels": "^3.0.6",
    "recharts": "^2.15.2",
    "sonner": "^2.0.7",
    "streamdown": "^1.4.0",
    "superjson": "^1.13.3",
    "tailwind-merge": "^3.3.1",
    "tailwindcss-animate": "^1.0.7",
    "vaul": "^1.1.2",
    "wouter": "^3.3.5",
    "zod": "^4.1.12"
  },
  "devDependencies": {
    "@builder.io/vite-plugin-jsx-loc": "^0.1.1",
    "@tailwindcss/typography": "^0.5.15",
    "@tailwindcss/vite": "^4.1.3",
    "@types/express": "4.17.21",
    "@types/google.maps": "^3.58.1",
    "@types/node": "^24.7.0",
    "@types/react": "^19.2.1",
    "@types/react-dom": "^19.2.1",
    "@vitejs/plugin-react": "^5.0.4",
    "add": "^2.0.6",
    "autoprefixer": "^10.4.20",
    "drizzle-kit": "^0.31.4",
    "esbuild": "^0.25.0",
    "pnpm": "^10.15.1",
    "postcss": "^8.4.47",
    "prettier": "^3.6.2",
    "tailwindcss": "^4.1.14",
    "tsx": "^4.19.1",
    "tw-animate-css": "^1.4.0",
    "typescript": "5.9.3",
    "vite": "^7.1.7",
    "vite-plugin-manus-runtime": "0.0.59",
    "vitest": "^2.1.4"
  },
  "packageManager": "pnpm@10.4.1+sha512.c753b6c3ad7afa13af388fa6d808035a008e30ea9993f58c6663e2bc5ff21679aa834db094987129aa4d488b86df57f7b634981b2f827cdcacc698cc0cfb88af",
  "pnpm": {
    "patchedDependencies": {
      "wouter@3.7.1": "patches/wouter@3.7.1.patch"
    },
    "overrides": {
      "tailwindcss>nanoid": "3.3.7"
    }
  }
}
````

### `server/_core/heartbeat.ts`

````typescript
import { TRPCError } from "@trpc/server";
import { ENV } from "./env";

export type HeartbeatJob = {
  name: string;
  /**
   * 6-field cron with seconds (`sec min hour dom mon dow`), UTC, min interval 60s.
   * Use `0` for the seconds field — e.g. `"0 0 9 * * *"` is daily 09:00 UTC.
   * See /home/ubuntu/skills/webdev-periodic-updates/SKILL.md.
   */
  cron: string;
  /** Callback path. MUST start with `/api/scheduled/`. */
  path: string;
  method?: "POST" | "PUT";
  payload?: unknown;
  description?: string;
};

/**
 * Update patch. All fields optional; unset = leave unchanged.
 * `enable`: true = resume, false = pause; omit = unchanged.
 * `name` is the (project, owner)-scope key and cannot be changed.
 */
export type HeartbeatJobUpdate = Partial<Omit<HeartbeatJob, "name">> & {
  enable?: boolean;
};

export type HeartbeatJobInfo = {
  taskUid: string;
  name: string;
  userId: string;
  description: string;
  cronExpression: string;
  callbackPath: string;
  callbackMethod: string;
  callbackPayload: string;
  isEnable: boolean;
  createdAt?: string | null;
  lastExecutedAt?: string | null;
  nextExecutionAt?: string | null;
};

const SERVICE = "webdevtoken.v1.WebDevService";

const buildEndpoint = (rpc: string): string => {
  if (!ENV.forgeApiUrl) {
    throw new TRPCError({
      code: "INTERNAL_SERVER_ERROR",
      message: "Heartbeat service URL is not configured (BUILT_IN_FORGE_API_URL).",
    });
  }
  if (!ENV.forgeApiKey) {
    throw new TRPCError({
      code: "INTERNAL_SERVER_ERROR",
      message: "Heartbeat service API key is not configured (BUILT_IN_FORGE_API_KEY).",
    });
  }
  const baseUrl = ENV.forgeApiUrl;
  const normalizedBase = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  return new URL(`${SERVICE}/${rpc}`, normalizedBase).toString();
};

const callForge = async <T>(
  rpc: string,
  body: Record<string, unknown>,
  userSession: string
): Promise<T> => {
  const endpoint = buildEndpoint(rpc);
  const headers: Record<string, string> = {
    accept: "application/json",
    authorization: `Bearer ${ENV.forgeApiKey}`,
    "content-type": "application/json",
    "connect-protocol-version": "1",
  };
  // userSession is the decoded `app_session_id` cookie value (NOT the raw
  // Cookie header). Empty string falls back to the project owner identity.
  if (userSession) {
    headers["x-manus-user-session"] = userSession;
  }

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch (error) {
    throw new TRPCError({
      code: "INTERNAL_SERVER_ERROR",
      message: `Heartbeat ${rpc} network error: ${String(error)}`,
    });
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw mapForgeError(response, detail, rpc);
  }
  return (await response.json()) as T;
};

const mapForgeError = (
  response: Response,
  detail: string,
  rpc: string
): TRPCError => {
  const status = response.status;
  let code: TRPCError["code"] = "INTERNAL_SERVER_ERROR";
  if (status === 401) code = "UNAUTHORIZED";
  else if (status === 403) code = "FORBIDDEN";
  else if (status === 404) code = "NOT_FOUND";
  else if (status === 400 || status === 422) code = "BAD_REQUEST";
  else if (status === 409) code = "CONFLICT";
  else if (status === 429) code = "TOO_MANY_REQUESTS";
  return new TRPCError({
    code,
    message: `Heartbeat ${rpc} failed (${status})${detail ? `: ${detail}` : ""}`,
  });
};

const stringifyPayload = (payload: unknown): string => {
  if (payload === undefined || payload === null) return "{}";
  if (typeof payload === "string") return payload;
  return JSON.stringify(payload);
};

const validateCallbackPath = (path: string): void => {
  if (!path || !path.startsWith("/api/scheduled/")) {
    throw new TRPCError({
      code: "BAD_REQUEST",
      message: "callback path must start with /api/scheduled/",
    });
  }
};

/**
 * Create a new HTTP cron job. Returns the assigned `taskUid` to persist on
 * your business row so callbacks can dereference it.
 */
export async function createHeartbeatJob(
  job: HeartbeatJob,
  userSession: string
): Promise<{ taskUid: string; nextExecutionAt?: string | null }> {
  validateCallbackPath(job.path);
  return callForge<{ taskUid: string; nextExecutionAt?: string | null }>(
    "CreateHeartbeatJob",
    {
      name: job.name,
      cronExpression: job.cron,
      callbackPath: job.path,
      callbackMethod: job.method ?? "POST",
      callbackPayload: stringifyPayload(job.payload),
      description: job.description ?? "",
    },
    userSession
  );
}

/**
 * Update an existing cron located by `taskUid`. Only fields you pass in
 * `patch` are mutated. `enable` flips resume/pause; omit to leave alone.
 */
export async function updateHeartbeatJob(
  taskUid: string,
  patch: HeartbeatJobUpdate,
  userSession: string
): Promise<{ nextExecutionAt?: string | null }> {
  if (patch.path !== undefined) validateCallbackPath(patch.path);
  const body: Record<string, unknown> = { taskUid };
  if (patch.cron !== undefined) body.cronExpression = patch.cron;
  if (patch.path !== undefined) body.callbackPath = patch.path;
  if (patch.method !== undefined) body.callbackMethod = patch.method;
  if (patch.payload !== undefined) {
    body.callbackPayload = stringifyPayload(patch.payload);
  }
  if (patch.description !== undefined) body.description = patch.description;
  if (patch.enable !== undefined) body.enable = patch.enable;
  return callForge<{ nextExecutionAt?: string | null }>(
    "UpdateHeartbeatJob",
    body,
    userSession
  );
}

/** Delete a cron located by `taskUid`. Idempotent on caller side. */
export async function deleteHeartbeatJob(
  taskUid: string,
  userSession: string
): Promise<void> {
  await callForge("DeleteHeartbeatJob", { taskUid }, userSession);
}

/**
 * List cron jobs owned by the resolved actor (end-user when `userSession`
 * is set, project owner otherwise) within the current project.
 *
 * `actorUserId` in the response echoes whose cron list you got back. End-users
 * cannot list other users' crons via this SDK; cross-user inspection is
 * owner-only via the sandbox CLI (`manus-heartbeat list --user-id <uid>`).
 */
export async function listHeartbeatJobs(
  userSession: string,
  pagination?: { page?: number; pageSize?: number }
): Promise<{ total: number; actorUserId: string; jobs: HeartbeatJobInfo[] }> {
  const body: Record<string, unknown> = {};
  if (pagination?.page !== undefined) body.page = pagination.page;
  if (pagination?.pageSize !== undefined) body.pageSize = pagination.pageSize;
  return callForge<{
    total: number;
    actorUserId: string;
    jobs: HeartbeatJobInfo[];
  }>("ListHeartbeatJobs", body, userSession);
}
````

### `server/_core/index.ts`

````typescript
import "dotenv/config";
import express from "express";
import { createServer } from "http";
import net from "net";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { registerOAuthRoutes } from "./oauth";
import { registerStorageProxy } from "./storageProxy";
import { appRouter } from "../routers";
import { downloadLearningDocument, downloadLearningDocumentByLogicalPath } from "../archiveDownload";
import { runScheduledEvalsCollector } from "../scheduledCollector";
import { createContext } from "./context";
import { serveStatic, setupVite } from "./vite";

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);
  // Configure body parser with larger size limit for file uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));
  registerStorageProxy(app);
  registerOAuthRoutes(app);
  app.get("/evals 업데이트 자료/:filename", downloadLearningDocumentByLogicalPath);
  app.get("/api/archive/documents/:id/download", downloadLearningDocument);
  app.post("/api/scheduled/collect-evals", runScheduledEvalsCollector);
  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );
  // development mode uses Vite, production mode uses static files
  if (process.env.NODE_ENV === "development") {
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  const preferredPort = parseInt(process.env.PORT || "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using port ${port} instead`);
  }

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
````

### `server/_core/llm.ts`

````typescript
import { ENV } from "./env";

export type Role = "system" | "user" | "assistant" | "tool" | "function";

export type TextContent = {
  type: "text";
  text: string;
};

export type ImageContent = {
  type: "image_url";
  image_url: {
    url: string;
    detail?: "auto" | "low" | "high";
  };
};

export type FileContent = {
  type: "file_url";
  file_url: {
    url: string;
    mime_type?: "audio/mpeg" | "audio/wav" | "application/pdf" | "audio/mp4" | "video/mp4" ;
  };
};

export type MessageContent = string | TextContent | ImageContent | FileContent;

export type Message = {
  role: Role;
  content: MessageContent | MessageContent[];
  name?: string;
  tool_call_id?: string;
};

export type Tool = {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
  };
};

export type ToolChoicePrimitive = "none" | "auto" | "required";
export type ToolChoiceByName = { name: string };
export type ToolChoiceExplicit = {
  type: "function";
  function: {
    name: string;
  };
};

export type ToolChoice =
  | ToolChoicePrimitive
  | ToolChoiceByName
  | ToolChoiceExplicit;

export type InvokeParams = {
  messages: Message[];
  tools?: Tool[];
  toolChoice?: ToolChoice;
  tool_choice?: ToolChoice;
  maxTokens?: number;
  max_tokens?: number;
  outputSchema?: OutputSchema;
  output_schema?: OutputSchema;
  responseFormat?: ResponseFormat;
  response_format?: ResponseFormat;
  model?: string;
  thinking?: Record<string, unknown>;
  reasoning?: Record<string, unknown>;
};

export type ToolCall = {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
};

export type InvokeResult = {
  id: string;
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: {
      role: Role;
      content: string | Array<TextContent | ImageContent | FileContent>;
      tool_calls?: ToolCall[];
    };
    finish_reason: string | null;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
};

export type JsonSchema = {
  name: string;
  schema: Record<string, unknown>;
  strict?: boolean;
};

export type OutputSchema = JsonSchema;

export type ResponseFormat =
  | { type: "text" }
  | { type: "json_object" }
  | { type: "json_schema"; json_schema: JsonSchema };

const ensureArray = (
  value: MessageContent | MessageContent[]
): MessageContent[] => (Array.isArray(value) ? value : [value]);

const normalizeContentPart = (
  part: MessageContent
): TextContent | ImageContent | FileContent => {
  if (typeof part === "string") {
    return { type: "text", text: part };
  }

  if (part.type === "text") {
    return part;
  }

  if (part.type === "image_url") {
    return part;
  }

  if (part.type === "file_url") {
    return part;
  }

  throw new Error("Unsupported message content part");
};

const normalizeMessage = (message: Message) => {
  const { role, name, tool_call_id } = message;

  if (role === "tool" || role === "function") {
    const content = ensureArray(message.content)
      .map(part => (typeof part === "string" ? part : JSON.stringify(part)))
      .join("\n");

    return {
      role,
      name,
      tool_call_id,
      content,
    };
  }

  const contentParts = ensureArray(message.content).map(normalizeContentPart);

  // If there's only text content, collapse to a single string for compatibility
  if (contentParts.length === 1 && contentParts[0].type === "text") {
    return {
      role,
      name,
      content: contentParts[0].text,
    };
  }

  return {
    role,
    name,
    content: contentParts,
  };
};

const normalizeToolChoice = (
  toolChoice: ToolChoice | undefined,
  tools: Tool[] | undefined
): "none" | "auto" | ToolChoiceExplicit | undefined => {
  if (!toolChoice) return undefined;

  if (toolChoice === "none" || toolChoice === "auto") {
    return toolChoice;
  }

  if (toolChoice === "required") {
    if (!tools || tools.length === 0) {
      throw new Error(
        "tool_choice 'required' was provided but no tools were configured"
      );
    }

    if (tools.length > 1) {
      throw new Error(
        "tool_choice 'required' needs a single tool or specify the tool name explicitly"
      );
    }

    return {
      type: "function",
      function: { name: tools[0].function.name },
    };
  }

  if ("name" in toolChoice) {
    return {
      type: "function",
      function: { name: toolChoice.name },
    };
  }

  return toolChoice;
};

const resolveApiUrl = () =>
  ENV.forgeApiUrl && ENV.forgeApiUrl.trim().length > 0
    ? `${ENV.forgeApiUrl.replace(/\/$/, "")}/v1/chat/completions`
    : "https://forge.manus.im/v1/chat/completions";

const assertApiKey = () => {
  if (!ENV.forgeApiKey) {
    throw new Error("OPENAI_API_KEY is not configured");
  }
};

const normalizeResponseFormat = ({
  responseFormat,
  response_format,
  outputSchema,
  output_schema,
}: {
  responseFormat?: ResponseFormat;
  response_format?: ResponseFormat;
  outputSchema?: OutputSchema;
  output_schema?: OutputSchema;
}):
  | { type: "json_schema"; json_schema: JsonSchema }
  | { type: "text" }
  | { type: "json_object" }
  | undefined => {
  const explicitFormat = responseFormat || response_format;
  if (explicitFormat) {
    if (
      explicitFormat.type === "json_schema" &&
      !explicitFormat.json_schema?.schema
    ) {
      throw new Error(
        "responseFormat json_schema requires a defined schema object"
      );
    }
    return explicitFormat;
  }

  const schema = outputSchema || output_schema;
  if (!schema) return undefined;

  if (!schema.name || !schema.schema) {
    throw new Error("outputSchema requires both name and schema");
  }

  return {
    type: "json_schema",
    json_schema: {
      name: schema.name,
      schema: schema.schema,
      ...(typeof schema.strict === "boolean" ? { strict: schema.strict } : {}),
    },
  };
};

const RETRY_MAX_RETRIES = 4;
const RETRY_BASE_DELAY_MS = 500;
const RETRY_MAX_DELAY_MS = 30_000;

type FetchInit = NonNullable<Parameters<typeof fetch>[1]>;

const sleep = (ms: number) =>
  new Promise<void>(resolve => setTimeout(resolve, ms));

const parseRetryAfter = (value: string | null): number | undefined => {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const at = Date.parse(value);
  return Number.isNaN(at) ? undefined : Math.max(0, at - Date.now());
};

// Equal-jitter exponential backoff. The cap/2 floor guarantees a minimum
// delay so a misbehaving caller loop slows down instead of hammering the
// upstream while it keeps returning errors.
const computeBackoffDelay = (
  attempt: number,
  retryAfterMs?: number
): number => {
  const cap = Math.min(RETRY_BASE_DELAY_MS * 2 ** attempt, RETRY_MAX_DELAY_MS);
  const jittered = cap / 2 + Math.random() * (cap / 2);
  return Math.min(Math.max(jittered, retryAfterMs ?? 0), RETRY_MAX_DELAY_MS);
};

// Retries non-2xx responses and network errors with exponential backoff, then
// returns the final Response so callers keep their existing error handling.
const fetchWithBackoff = async (
  url: string,
  init: FetchInit
): Promise<Response> => {
  let lastError: unknown;

  for (let attempt = 0; attempt <= RETRY_MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(url, init);
      if (response.ok || attempt === RETRY_MAX_RETRIES) {
        return response;
      }

      const retryAfterMs = parseRetryAfter(
        response.headers.get("retry-after")
      );
      try {
        await response.body?.cancel();
      } catch {
        // Body already settled; nothing to clean up.
      }
      console.warn(
        `LLM request retry ${attempt + 1}/${RETRY_MAX_RETRIES} after status ${response.status}`
      );
      await sleep(computeBackoffDelay(attempt, retryAfterMs));
    } catch (error) {
      lastError = error;
      if (attempt === RETRY_MAX_RETRIES) throw error;
      console.warn(
        `LLM request retry ${attempt + 1}/${RETRY_MAX_RETRIES} after network error`
      );
      await sleep(computeBackoffDelay(attempt));
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("LLM request failed after exhausting retries");
};

export async function invokeLLM(params: InvokeParams): Promise<InvokeResult> {
  assertApiKey();

  const {
    messages,
    tools,
    toolChoice,
    tool_choice,
    outputSchema,
    output_schema,
    responseFormat,
    response_format,
    model,
    thinking,
    reasoning,
    maxTokens,
    max_tokens,
  } = params;

  const payload: Record<string, unknown> = {
    messages: messages.map(normalizeMessage),
  };

  if (model) {
    payload.model = model;
  }

  if (tools && tools.length > 0) {
    payload.tools = tools;
  }

  const normalizedToolChoice = normalizeToolChoice(
    toolChoice || tool_choice,
    tools
  );
  if (normalizedToolChoice) {
    payload.tool_choice = normalizedToolChoice;
  }

  const resolvedMaxTokens = max_tokens ?? maxTokens;
  if (typeof resolvedMaxTokens === "number") {
    payload.max_tokens = resolvedMaxTokens;
  }

  if (thinking) {
    payload.thinking = thinking;
  }
  if (reasoning) {
    payload.reasoning = reasoning;
  }

  const normalizedResponseFormat = normalizeResponseFormat({
    responseFormat,
    response_format,
    outputSchema,
    output_schema,
  });

  if (normalizedResponseFormat) {
    payload.response_format = normalizedResponseFormat;
  }

  const response = await fetchWithBackoff(resolveApiUrl(), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${ENV.forgeApiKey}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `LLM invoke failed: ${response.status} ${response.statusText} – ${errorText}`
    );
  }

  return (await response.json()) as InvokeResult;
}

export type ModelInfo = {
  id: string;
  object: string;
  created: number;
  owned_by: string;
};

export type ModelsResponse = {
  object: string;
  data: ModelInfo[];
};

export async function listLLMModels(): Promise<ModelsResponse> {
  assertApiKey();

  const url = ENV.forgeApiUrl && ENV.forgeApiUrl.trim().length > 0
    ? `${ENV.forgeApiUrl.replace(/\/$/, "")}/v1/models`
    : "https://forge.manus.im/v1/models";

  const response = await fetchWithBackoff(url, {
    headers: { authorization: `Bearer ${ENV.forgeApiKey}` },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `List LLM models failed: ${response.status} ${response.statusText} – ${errorText}`
    );
  }

  return (await response.json()) as ModelsResponse;
}
````

### `server/archiveCollector.ts`

````typescript
import { invokeLLM } from "./_core/llm";
import { notifyOwner } from "./_core/notification";
import { storagePut } from "./storage";
import {
  createArticle,
  createArticleNote,
  createDuplicateDecision,
  createLearningDocument,
  createRun,
  finishRun,
  getActiveSources,
  getRecentArticles,
  setLastCollectedAt,
} from "./archiveDb";
import type { ArticleWithNote, CollectorOutcome, FeedCandidate, KeyTerm, LearningNote, TopicTag } from "./archiveTypes";
import {
  buildLearningMarkdown,
  canonicalizeUrl,
  decodeHtml,
  findRelatedArticles,
  formatArchiveTimestamp,
  inferEvalsTags,
  isEvalsRelevant,
  normalizeTitle,
  toStorageObjectKey,
  similarityScore,
  urlHash,
} from "./archiveUtils";

const getTagValue = (block: string, tag: string): string => {
  const match = block.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return match ? decodeHtml(match[1]) : "";
};

const getBlocks = (xml: string, tag: string): string[] => xml.match(new RegExp(`<${tag}(?:\\s[^>]*)?>[\\s\\S]*?<\\/${tag}>`, "gi")) ?? [];
const MIN_EXCERPT_LENGTH = 100;
const MAX_CANDIDATES_PER_RUN = 60;
const MAX_LLM_NOTES_PER_RUN = 1;

/**
 * 후보 상한이 있어도 먼저 반환된 피드만 독점하지 않도록 피드별로 한 건씩 교차 선택한다.
 * 후순위에 등록된 직접 Evals 피드도 매 실행에서 최소한의 판정 기회를 갖는다.
 */
export function selectFairFeedCandidates(candidateGroups: FeedCandidate[][], limit = MAX_CANDIDATES_PER_RUN): FeedCandidate[] {
  const selected: FeedCandidate[] = [];
  let offset = 0;

  while (selected.length < limit) {
    let selectedInRound = 0;
    for (const group of candidateGroups) {
      const candidate = group[offset];
      if (!candidate) continue;
      selected.push(candidate);
      selectedInRound += 1;
      if (selected.length >= limit) break;
    }
    if (!selectedInRound) break;
    offset += 1;
  }

  return selected;
}

function parseDate(value: string): Date | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function hasSufficientExcerpt(candidate: FeedCandidate): boolean {
  return decodeHtml(candidate.excerpt).length >= MIN_EXCERPT_LENGTH;
}

function isDirectEvalsArticle(article: { title: string; canonicalUrl: string; publishedAt: Date | null; contentExcerpt: string | null; sourceName: string; sourceFeedUrl: string }): boolean {
  return isEvalsRelevant({
    title: article.title,
    url: article.canonicalUrl,
    publishedAt: article.publishedAt,
    excerpt: article.contentExcerpt ?? "",
    sourceName: article.sourceName,
    sourceFeedUrl: article.sourceFeedUrl,
  });
}

function parseAtom(xml: string, sourceName: string, sourceFeedUrl: string): FeedCandidate[] {
  return getBlocks(xml, "entry").flatMap(block => {
    const title = getTagValue(block, "title");
    const summary = getTagValue(block, "summary") || getTagValue(block, "content");
    const href = block.match(/<link[^>]+href=["']([^"']+)["'][^>]*>/i)?.[1] ?? "";
    if (!title || !href) return [];
    return [{ title, url: canonicalizeUrl(href), publishedAt: parseDate(getTagValue(block, "published") || getTagValue(block, "updated")), excerpt: summary.slice(0, 5500), sourceName, sourceFeedUrl }];
  });
}

function parseRss(xml: string, sourceName: string, sourceFeedUrl: string): FeedCandidate[] {
  return getBlocks(xml, "item").flatMap(block => {
    const title = getTagValue(block, "title");
    const link = getTagValue(block, "link") || getTagValue(block, "guid");
    const excerpt = getTagValue(block, "description") || getTagValue(block, "content:encoded");
    if (!title || !link) return [];
    return [{ title, url: canonicalizeUrl(link), publishedAt: parseDate(getTagValue(block, "pubDate") || getTagValue(block, "dc:date")), excerpt: excerpt.slice(0, 5500), sourceName, sourceFeedUrl }];
  });
}

async function loadFeed(source: { name: string; feedUrl: string; sourceType: "atom" | "rss" }): Promise<FeedCandidate[]> {
  const response = await fetch(source.feedUrl, { signal: AbortSignal.timeout(18_000), headers: { "user-agent": "AI-Evals-Learning-Archive/1.0" } });
  if (!response.ok) throw new Error(`${source.name} returned HTTP ${response.status}`);
  const xml = await response.text();
  return source.sourceType === "atom" ? parseAtom(xml, source.name, source.feedUrl) : parseRss(xml, source.name, source.feedUrl);
}

function fallbackNote(candidate: FeedCandidate, tags: TopicTag[]): LearningNote {
  return {
    summary: `${candidate.title}은(는) AI 시스템의 검증·평가와 관련된 최신 자료입니다. 원문을 읽으며 평가 대상, 측정 기준, 검증 방법이 무엇인지 먼저 확인하세요.`,
    practicalMeaning: "개발자는 기대 동작을 테스트 케이스와 측정 지표로 바꾸고, 데이터사이언티스트는 측정의 신뢰성과 재현성을 점검하며, PM은 사용자가 체감하는 성공 기준과 출시 기준을 합의해야 합니다.",
    tags,
    keyTerms: [
      { term: "Evals", definition: "AI 시스템이 기대한 품질과 행동을 보이는지 측정하는 반복 가능한 평가 과정입니다." },
      { term: "회귀 검증", definition: "변경 후 기존 품질이 나빠지지 않았는지 확인하는 테스트입니다." },
    ],
    learningPoints: ["원문에서 평가 대상과 성공 기준을 구분해 기록하세요.", "정량 지표와 사람의 검토가 각각 무엇을 놓칠 수 있는지 비교하세요."],
  };
}

async function generateLearningNote(candidate: FeedCandidate, inferredTags: TopicTag[]): Promise<{ note: LearningNote; usedFallback: boolean }> {
  const schema = {
    type: "object",
    properties: {
      summary: { type: "string" },
      practicalMeaning: { type: "string" },
      tags: { type: "array", items: { type: "string", enum: ["agent-evals", "benchmark", "grading", "trajectory", "tool-use", "safety", "observability", "rag", "regression", "product-quality"] }, minItems: 1, maxItems: 5 },
      keyTerms: { type: "array", items: { type: "object", properties: { term: { type: "string" }, definition: { type: "string" } }, required: ["term", "definition"], additionalProperties: false }, minItems: 2, maxItems: 4 },
      learningPoints: { type: "array", items: { type: "string" }, minItems: 2, maxItems: 4 },
    },
    required: ["summary", "practicalMeaning", "tags", "keyTerms", "learningPoints"],
    additionalProperties: false,
  } as const;
  try {
    const response = await invokeLLM({
      model: "gpt-5-mini",
      messages: [
        { role: "system", content: "당신은 AI Evals 학습 편집자입니다. 초보 AI 개발자·데이터사이언티스트·PM에게 정확하고 쉬운 한국어로 설명합니다. 원문에 없는 사실을 단정하지 말고, 제공한 정보의 한계를 분명히 반영합니다." },
        { role: "user", content: `다음 Evals 관련 자료의 발췌문을 학습 노트 JSON으로 정리하세요. 제목: ${candidate.title}\n출처: ${candidate.sourceName}\n초기 태그: ${inferredTags.join(", ")}\n발췌문: ${candidate.excerpt}\n제한: summary는 200자 이하, practicalMeaning은 260자 이하, 용어 정의는 각 90자 이하, 학습 포인트는 각 80자 이하의 한국어 문장으로 작성하세요.` },
      ],
      response_format: { type: "json_schema", json_schema: { name: "evals_learning_note", strict: true, schema } },
      maxTokens: 1800,
    });
    const content = response.choices[0]?.message?.content;
    const parsed = JSON.parse(typeof content === "string" ? content : "{}") as LearningNote;
    if (!parsed.summary || !parsed.practicalMeaning || !Array.isArray(parsed.tags) || !Array.isArray(parsed.keyTerms) || !Array.isArray(parsed.learningPoints)) throw new Error("Incomplete structured LLM output");
    return {
      usedFallback: false,
      note: {
        ...parsed,
        tags: parsed.tags.filter(tag => typeof tag === "string") as TopicTag[],
        keyTerms: parsed.keyTerms.filter(term => term?.term && term?.definition) as KeyTerm[],
        learningPoints: parsed.learningPoints.filter(Boolean),
      },
    };
  } catch (error) {
    console.warn("[Archive] LLM note generation fell back to deterministic note:", error);
    return { note: fallbackNote(candidate, inferredTags), usedFallback: true };
  }
}

export async function collectEvalsLearningMaterials(): Promise<CollectorOutcome> {
  const runId = await createRun();
  let scannedCount = 0;
  let acceptedCount = 0;
  let skippedExactCount = 0;
  let skippedSimilarCount = 0;
  let skippedIrrelevantCount = 0;
  let skippedShortExcerptCount = 0;
  let notificationFailed = false;
  let llmAttempts = 0;
  let fallbackNoteCount = 0;
  const accepted: ArticleWithNote[] = [];
  const now = new Date();

  try {
    const sources = await getActiveSources();
    const settled = await Promise.allSettled(sources.map(source => loadFeed(source)));
    const candidates = selectFairFeedCandidates(settled.flatMap(result => result.status === "fulfilled" ? [result.value] : []));
    const prior = await getRecentArticles();
    const known = prior.filter(isDirectEvalsArticle);

    for (const candidate of candidates) {
      scannedCount += 1;
      const candidateHash = urlHash(candidate.url);
      const inferredTags = inferEvalsTags(`${candidate.title} ${candidate.excerpt}`);
      if (!isEvalsRelevant(candidate)) {
        skippedIrrelevantCount += 1;
        await createDuplicateDecision({ collectionRunId: runId, candidateUrlHash: candidateHash, candidateTitle: candidate.title, sourceName: candidate.sourceName, decision: "skipped_irrelevant", tagsJson: JSON.stringify(inferredTags), reason: "Evals 및 AI 관련성 키워드가 함께 확인되지 않았습니다." });
        continue;
      }

      if (!hasSufficientExcerpt(candidate)) {
        skippedIrrelevantCount += 1;
        skippedShortExcerptCount += 1;
        await createDuplicateDecision({ collectionRunId: runId, candidateUrlHash: candidateHash, candidateTitle: candidate.title, sourceName: candidate.sourceName, decision: "skipped_irrelevant", tagsJson: JSON.stringify(inferredTags), reason: `원문 발췌문이 ${MIN_EXCERPT_LENGTH}자 미만이어서 근거 기반 학습 노트를 만들 수 없습니다.` });
        continue;
      }

      const exact = known.find(article => article.urlHash === candidateHash || article.normalizedTitle === normalizeTitle(candidate.title));
      if (exact) {
        skippedExactCount += 1;
        await createDuplicateDecision({ collectionRunId: runId, candidateUrlHash: candidateHash, candidateTitle: candidate.title, sourceName: candidate.sourceName, decision: "skipped_exact", matchedArticleId: exact.id, similarityScore: 100, tagsJson: JSON.stringify(inferredTags), reason: "정규화 URL 또는 정규화 제목이 기존 자료와 일치합니다." });
        continue;
      }

      const comparisons = known.map(article => ({ article, score: similarityScore(candidate.title, inferredTags, article.title, JSON.parse(article.tagsJson) as string[]) })).sort((a, b) => b.score - a.score);
      const nearest = comparisons[0];
      if (nearest && nearest.score >= 72) {
        skippedSimilarCount += 1;
        await createDuplicateDecision({ collectionRunId: runId, candidateUrlHash: candidateHash, candidateTitle: candidate.title, sourceName: candidate.sourceName, decision: "skipped_similar", matchedArticleId: nearest.article.id, similarityScore: nearest.score, tagsJson: JSON.stringify(inferredTags), reason: "제목 토큰과 핵심 주제 태그의 가중 유사도가 72% 이상입니다." });
        continue;
      }

      if (accepted.length >= 5) break;
      // Heartbeat 콜백은 2분 제한이 있으므로, 여러 신규 자료가 동시에 발견되어도
      // 첫 자료만 LLM으로 정리하고 나머지는 즉시 결정적 fallback으로 보존한다.
      const generated = llmAttempts < MAX_LLM_NOTES_PER_RUN
        ? await generateLearningNote(candidate, inferredTags)
        : { note: fallbackNote(candidate, inferredTags), usedFallback: true };
      if (llmAttempts < MAX_LLM_NOTES_PER_RUN) llmAttempts += 1;
      if (generated.usedFallback) fallbackNoteCount += 1;
      const note = generated.note;
      const related = findRelatedArticles(candidate.title, note.tags, known.map(article => ({ id: article.id, title: article.title, tags: JSON.parse(article.tagsJson) as string[] })));
      const articleId = await createArticle({
        collectionRunId: runId,
        urlHash: candidateHash,
        canonicalUrl: candidate.url,
        title: candidate.title,
        normalizedTitle: normalizeTitle(candidate.title),
        sourceName: candidate.sourceName,
        sourceFeedUrl: candidate.sourceFeedUrl,
        publishedAt: candidate.publishedAt,
        contentExcerpt: candidate.excerpt,
        tagsJson: JSON.stringify(note.tags),
        relevanceScore: 100 - (nearest?.score ?? 0),
      });
      await createArticleNote({ articleId, summary: note.summary, practicalMeaning: note.practicalMeaning, keyTermsJson: JSON.stringify(note.keyTerms), learningPointsJson: JSON.stringify(note.learningPoints), similarityLinksJson: JSON.stringify(related) });
      await createDuplicateDecision({ collectionRunId: runId, candidateUrlHash: candidateHash, candidateTitle: candidate.title, sourceName: candidate.sourceName, decision: "accepted", similarityScore: nearest?.score ?? 0, matchedArticleId: nearest?.article.id ?? null, tagsJson: JSON.stringify(note.tags), reason: "Evals 관련성이 확인되었고 정확 또는 고유사 중복 기준을 통과했습니다." });
      accepted.push({ id: articleId, title: candidate.title, canonicalUrl: candidate.url, sourceName: candidate.sourceName, publishedAt: candidate.publishedAt, tags: note.tags, note, related });
      known.unshift({ id: articleId, collectionRunId: runId, urlHash: candidateHash, canonicalUrl: candidate.url, title: candidate.title, normalizedTitle: normalizeTitle(candidate.title), sourceName: candidate.sourceName, sourceFeedUrl: candidate.sourceFeedUrl, publishedAt: candidate.publishedAt, contentExcerpt: candidate.excerpt, tagsJson: JSON.stringify(note.tags), relevanceScore: 100, createdAt: now });
      acceptedCount += 1;
    }

    const failedSourceNames = settled.flatMap((result, index) => result.status === "rejected" ? [sources[index]?.name ?? "알 수 없는 출처"] : []);
    const documentArticles: ArticleWithNote[] = accepted;
    const timestamp = formatArchiveTimestamp(now);
    const logicalPath = `evals 업데이트 자료/${timestamp}.md`;
    const markdown = buildLearningMarkdown(now, documentArticles, {
      scannedCount,
      acceptedCount,
      skippedExactCount,
      skippedSimilarCount,
      skippedIrrelevantCount,
      skippedShortExcerptCount,
      failedSourceNames,
      llmAttempts,
      fallbackNoteCount,
    });
    const uploaded = await storagePut(toStorageObjectKey(logicalPath), markdown, "text/markdown; charset=utf-8");
    const allTerms = documentArticles.flatMap(article => article.note.keyTerms);
    const allPoints = documentArticles.flatMap(article => article.note.learningPoints);
    const allLinks = documentArticles.flatMap(article => article.related.map(link => ({ ...link, fromArticleId: article.id })));
    await createLearningDocument({ collectionRunId: runId, logicalPath, storageKey: uploaded.key, storageUrl: uploaded.url, summary: accepted.length ? `신규 Evals 학습자료 ${accepted.length}건과 수집 검토 기록을 하나의 업데이트 노트로 생성했습니다.` : "신규 학습자료는 없었지만 검색 범위와 제외 근거를 기록한 운영 검토 노트를 생성했습니다.", practicalMeaning: "수집 자료와 제외 근거를 개발·데이터·제품 관점에서 함께 검토할 수 있도록 통합했습니다.", keyTermsJson: JSON.stringify(allTerms), learningPointsJson: JSON.stringify(allPoints), similarityLinksJson: JSON.stringify(allLinks) });
    const document: CollectorOutcome["document"] = { logicalPath, storageUrl: uploaded.url };
    if (accepted.length) {
      const notification = { title: "AI Evals 학습 노트 생성", content: `${logicalPath} 파일을 생성했습니다. 신규 자료 ${documentArticles.length}건, 수집 시각 ${now.toISOString()}입니다.` };
      try {
        const delivered = await notifyOwner(notification);
        notificationFailed = !delivered && !(await notifyOwner(notification));
      } catch (error) {
        console.warn("[Archive] Owner notification failed:", error);
        notificationFailed = true;
      }
    }
    await setLastCollectedAt(now);
    const issues = [
      failedSourceNames.length ? `${failedSourceNames.length}개 출처 피드 수집에 실패했습니다.` : null,
      notificationFailed ? "소유자 알림 전송이 두 차례 실패했습니다." : null,
    ].filter(Boolean);
    await finishRun({ id: runId, status: issues.length ? "partial" : "success", scannedCount, acceptedCount, skippedExactCount, skippedSimilarCount, errorMessage: issues.join(" ") || null });
    return { runId, scannedCount, acceptedCount, skippedExactCount, skippedSimilarCount, skippedIrrelevantCount, document };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await finishRun({ id: runId, status: "failed", scannedCount, acceptedCount, skippedExactCount, skippedSimilarCount, errorMessage: message });
    throw error;
  }
}
````

### `server/archiveDb.ts`

````typescript
import { and, asc, desc, eq, isNull } from "drizzle-orm";
import {
  archiveSettings,
  articleLearningNotes,
  articles,
  collectionRuns,
  duplicateDecisions,
  learningDocuments,
  sourceFeeds,
  userDocumentProgress,
} from "../drizzle/schema";
import { getDb } from "./db";
import type { FeedType } from "./archiveTypes";
import { decodeHtml, isEvalsRelevant } from "./archiveUtils";

export const DEFAULT_SOURCES: Array<{ name: string; feedUrl: string; sourceType: FeedType }> = [
  {
    name: "arXiv — Agent Evals",
    feedUrl: "https://export.arxiv.org/api/query?search_query=all%3A%22AI%20agent%22%20AND%20all%3A%28evaluation%20OR%20benchmark%20OR%20evals%29&start=0&max_results=18&sortBy=submittedDate&sortOrder=descending",
    sourceType: "atom",
  },
  {
    name: "arXiv — LLM & AI Service Evals",
    feedUrl: "https://export.arxiv.org/api/query?search_query=all%3A%28LLM%20OR%20%22language%20model%22%20OR%20%22AI%20service%22%29%20AND%20all%3A%28evaluation%20OR%20benchmark%20OR%20grader%20OR%20regression%29&start=0&max_results=18&sortBy=submittedDate&sortOrder=descending",
    sourceType: "atom",
  },
  { name: "AWS Machine Learning Blog", feedUrl: "https://aws.amazon.com/blogs/machine-learning/feed/", sourceType: "rss" },
  { name: "Hugging Face Blog", feedUrl: "https://huggingface.co/blog/feed.xml", sourceType: "rss" },
];

export const ARCHIVE_SETTINGS_SINGLETON_KEY = "archive";

function parseLearningPoints(value: string): string[] {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((point): point is string => typeof point === "string") : [];
  } catch {
    return [];
  }
}

export async function ensureArchiveDefaults() {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  await db.insert(archiveSettings).values({ singletonKey: ARCHIVE_SETTINGS_SINGLETON_KEY }).onDuplicateKeyUpdate({ set: { updatedAt: new Date() } });
  for (const source of DEFAULT_SOURCES) {
    await db.insert(sourceFeeds).values(source).onDuplicateKeyUpdate({
      set: { name: source.name, feedUrl: source.feedUrl, sourceType: source.sourceType, enabled: true, updatedAt: new Date() },
    });
  }
}

export async function getSettings() {
  await ensureArchiveDefaults();
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const settings = await db.select().from(archiveSettings).where(eq(archiveSettings.singletonKey, ARCHIVE_SETTINGS_SINGLETON_KEY)).limit(1);
  if (!settings[0]) throw new Error("Archive settings singleton is unavailable.");
  return settings[0];
}

export async function setScheduleTaskUid(taskUid: string) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const settings = await getSettings();
  await db.update(archiveSettings).set({ scheduleCronTaskUid: taskUid, collectorEnabled: true }).where(eq(archiveSettings.id, settings.id));
}

export async function setCollectorEnabled(enabled: boolean) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const settings = await getSettings();
  await db.update(archiveSettings).set({ collectorEnabled: enabled }).where(eq(archiveSettings.id, settings.id));
}

export async function setLastCollectedAt(date: Date) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const settings = await getSettings();
  await db.update(archiveSettings).set({ lastCollectedAt: date }).where(eq(archiveSettings.id, settings.id));
}

export async function getActiveSources() {
  await ensureArchiveDefaults();
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  return db.select().from(sourceFeeds).where(eq(sourceFeeds.enabled, true));
}

export async function createRun() {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const result = await db.insert(collectionRuns).values({ status: "running" });
  return Number(result[0].insertId);
}

export async function finishRun(input: {
  id: number;
  status: "success" | "partial" | "failed";
  scannedCount: number;
  acceptedCount: number;
  skippedExactCount: number;
  skippedSimilarCount: number;
  errorMessage?: string | null;
}) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  await db.update(collectionRuns).set({ ...input, completedAt: new Date() }).where(eq(collectionRuns.id, input.id));
}

export async function getRecentArticles(limit = 150) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  return db.select().from(articles).orderBy(desc(articles.createdAt)).limit(limit);
}

export async function getRecoverableArticleNotes() {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const unarchived = await db
    .select({ collectionRunId: articles.collectionRunId })
    .from(articles)
    .leftJoin(learningDocuments, eq(articles.collectionRunId, learningDocuments.collectionRunId))
    .where(isNull(learningDocuments.id))
    .orderBy(desc(articles.createdAt))
    .limit(1);
  const runId = unarchived[0]?.collectionRunId;
  if (!runId) return null;
  const rows = await db
    .select({ article: articles, note: articleLearningNotes })
    .from(articles)
    .innerJoin(articleLearningNotes, eq(articles.id, articleLearningNotes.articleId))
    .where(eq(articles.collectionRunId, runId))
    .orderBy(asc(articles.createdAt));
  return { runId, rows };
}

export async function getArticleNotesForRun(runId: number) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  return db
    .select({ article: articles, note: articleLearningNotes })
    .from(articles)
    .innerJoin(articleLearningNotes, eq(articles.id, articleLearningNotes.articleId))
    .where(eq(articles.collectionRunId, runId))
    .orderBy(asc(articles.createdAt));
}

export async function getDirectEvalsArticleNotes(limit = 5) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const rows = await db
    .select({ article: articles, note: articleLearningNotes })
    .from(articles)
    .innerJoin(articleLearningNotes, eq(articles.id, articleLearningNotes.articleId))
    .orderBy(asc(articles.createdAt));
  return rows.filter(({ article }) => isEvalsRelevant({
    title: article.title,
    url: article.canonicalUrl,
    publishedAt: article.publishedAt,
    excerpt: article.contentExcerpt ?? "",
    sourceName: article.sourceName,
    sourceFeedUrl: article.sourceFeedUrl,
  })).slice(0, limit);
}

export async function createArticle(input: typeof articles.$inferInsert) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const result = await db.insert(articles).values(input);
  return Number(result[0].insertId);
}

export async function createArticleNote(input: typeof articleLearningNotes.$inferInsert) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  await db.insert(articleLearningNotes).values(input);
}

export async function createDuplicateDecision(input: typeof duplicateDecisions.$inferInsert) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  await db.insert(duplicateDecisions).values(input);
}

export async function createLearningDocument(input: typeof learningDocuments.$inferInsert) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  await db.insert(learningDocuments).values(input);
}

export async function getLearningDocumentsForStorageRepair() {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  return db.select().from(learningDocuments).orderBy(asc(learningDocuments.generatedAt));
}

export async function getLearningDocumentById(id: number) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const rows = await db.select().from(learningDocuments).where(eq(learningDocuments.id, id)).limit(1);
  return rows[0] ?? null;
}

export async function getLearningDocumentByLogicalPath(logicalPath: string) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const rows = await db.select().from(learningDocuments).where(eq(learningDocuments.logicalPath, logicalPath)).limit(1);
  return rows[0] ?? null;
}

export async function updateLearningDocumentStorage(id: number, storageKey: string, storageUrl: string) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  await db.update(learningDocuments).set({ storageKey, storageUrl }).where(eq(learningDocuments.id, id));
}

export async function setDocumentCompletion(userId: number, learningDocumentId: number, completed: boolean) {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const document = await getLearningDocumentById(learningDocumentId);
  if (!document) throw new Error("Learning document was not found.");
  if (!completed) {
    await db.delete(userDocumentProgress).where(and(eq(userDocumentProgress.userId, userId), eq(userDocumentProgress.learningDocumentId, learningDocumentId)));
    return;
  }
  await db.insert(userDocumentProgress).values({ userId, learningDocumentId, completedAt: new Date() }).onDuplicateKeyUpdate({
    set: { completedAt: new Date(), updatedAt: new Date() },
  });
}

export async function getCompletedDocumentIds(userId: number): Promise<number[]> {
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const rows = await db.select({ learningDocumentId: userDocumentProgress.learningDocumentId })
    .from(userDocumentProgress)
    .where(eq(userDocumentProgress.userId, userId));
  return rows.map(row => row.learningDocumentId);
}

export async function getDashboardData(userId: number) {
  const settings = await getSettings();
  const db = await getDb();
  if (!db) throw new Error("Database connection is unavailable.");
  const [documents, runs, decisions, recentArticles] = await Promise.all([
    db.select().from(learningDocuments).orderBy(desc(learningDocuments.generatedAt)).limit(18),
    db.select().from(collectionRuns).orderBy(desc(collectionRuns.startedAt)).limit(12),
    db.select().from(duplicateDecisions).orderBy(desc(duplicateDecisions.createdAt)).limit(24),
    db.select().from(articles).orderBy(desc(articles.createdAt)).limit(20),
  ]);
  const completedDocumentIds = new Set(await getCompletedDocumentIds(userId));
  const documentVisibility = await Promise.all(documents.map(async document => {
    const documentArticles = await db.select().from(articles).where(eq(articles.collectionRunId, document.collectionRunId));
    const tags = Array.from(new Set(documentArticles.flatMap(article => JSON.parse(article.tagsJson) as string[])));
    const isDirectEvals = documentArticles.length > 0 && documentArticles.every(article => {
      const candidate = {
        title: article.title,
        url: article.canonicalUrl,
        publishedAt: article.publishedAt,
        excerpt: article.contentExcerpt ?? "",
        sourceName: article.sourceName,
        sourceFeedUrl: article.sourceFeedUrl,
      };
      return isEvalsRelevant(candidate) && decodeHtml(candidate.excerpt).length >= 100;
    });
    return { document, isDirectEvals, tags, learningPoints: parseLearningPoints(document.learningPointsJson) };
  }));
  return { settings, documents: documentVisibility.filter(item => item.isDirectEvals).map(item => ({ ...item.document, tags: item.tags, learningPoints: item.learningPoints, completed: completedDocumentIds.has(item.document.id) })), runs, decisions, articles: recentArticles, sources: await getActiveSources() };
}
````

### `server/archiveTypes.ts`

````typescript
export type FeedType = "atom" | "rss";

export type FeedCandidate = {
  title: string;
  url: string;
  publishedAt: Date | null;
  excerpt: string;
  sourceName: string;
  sourceFeedUrl: string;
};

export type TopicTag =
  | "agent-evals"
  | "benchmark"
  | "grading"
  | "trajectory"
  | "tool-use"
  | "safety"
  | "observability"
  | "rag"
  | "regression"
  | "product-quality";

export type KeyTerm = {
  term: string;
  definition: string;
};

export type SimilarityLink = {
  articleId: number;
  title: string;
  score: number;
  sharedTags: string[];
};

export type LearningNote = {
  summary: string;
  practicalMeaning: string;
  tags: TopicTag[];
  keyTerms: KeyTerm[];
  learningPoints: string[];
};

export type ArticleWithNote = {
  id: number;
  title: string;
  canonicalUrl: string;
  sourceName: string;
  publishedAt: Date | null;
  tags: string[];
  note: LearningNote;
  related: SimilarityLink[];
};

export type CollectorOutcome = {
  runId: number;
  scannedCount: number;
  acceptedCount: number;
  skippedExactCount: number;
  skippedSimilarCount: number;
  skippedIrrelevantCount: number;
  document: { logicalPath: string; storageUrl: string } | null;
};
````

### `server/archiveUtils.ts`

````typescript
import { createHash } from "crypto";
import type { ArticleWithNote, FeedCandidate, SimilarityLink, TopicTag } from "./archiveTypes";

export type CollectionAudit = {
  scannedCount: number;
  acceptedCount: number;
  skippedExactCount: number;
  skippedSimilarCount: number;
  skippedIrrelevantCount: number;
  skippedShortExcerptCount: number;
  failedSourceNames: string[];
  llmAttempts: number;
  fallbackNoteCount: number;
};

const TAG_RULES: Array<{ tag: TopicTag; terms: string[] }> = [
  { tag: "agent-evals", terms: ["agent eval", "agent evaluation", "ai agent", "llm agent", "agentic"] },
  { tag: "benchmark", terms: ["benchmark", "leaderboard", "dataset", "test set"] },
  { tag: "grading", terms: ["grader", "judge", "llm-as-a-judge", "scoring", "rubric"] },
  { tag: "trajectory", terms: ["trajectory", "trajectories", "trace", "transcript", "multi-turn", "workflow"] },
  { tag: "tool-use", terms: ["tool use", "tool calling", "function calling", "mcp"] },
  { tag: "safety", terms: ["safety", "security", "alignment", "guardrail", "red team"] },
  { tag: "observability", terms: ["observability", "monitoring", "telemetry", "production"] },
  { tag: "rag", terms: ["rag", "retrieval", "grounded", "citation"] },
  { tag: "regression", terms: ["regression", "ci/cd", "continuous evaluation", "release gate"] },
  { tag: "product-quality", terms: ["quality", "reliability", "latency", "cost", "user experience"] },
];

const EVAL_TERMS = ["eval", "evaluation", "evaluate", "benchmark", "grader", "testing", "test", "quality", "regression", "observability", "safety"];
const AI_EVAL_ANCHORS = ["ai agent", "ai agents", "agent eval", "agent evaluation", "agent framework", "llm", "language model", "large language", "foundation model", "generative ai", "ai service", "ai services", "chatbot", "copilot", "assistant", "tool calling", "tool use", "mcp", "rag"];
const TITLE_EVAL_TERMS = ["eval", "evaluat", "benchmark", "grader", "grading", "testing", "test", "regression", "observability", "quality"];
const TITLE_AI_TERMS = ["agent", "llm", "language model", "rag", "mcp", "model"];

function containsKeyword(value: string, keyword: string): boolean {
  if (keyword === "eval") {
    return /(?:^|[^a-z0-9])evals?(?=$|[^a-z0-9])/i.test(value);
  }
  return value.includes(keyword);
}

function containsAnyKeyword(value: string, keywords: string[]): boolean {
  return keywords.some(keyword => containsKeyword(value, keyword));
}

export function decodeHtml(value: string): string {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

export function canonicalizeUrl(value: string): string {
  try {
    const url = new URL(decodeHtml(value));
    url.hash = "";
    ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"].forEach(key => url.searchParams.delete(key));
    return url.toString().replace(/\/$/, "");
  } catch {
    return decodeHtml(value).trim().replace(/\/$/, "");
  }
}

export function urlHash(url: string): string {
  return createHash("sha256").update(canonicalizeUrl(url)).digest("hex");
}

export function normalizeTitle(value: string): string {
  return decodeHtml(value)
    .toLowerCase()
    .replace(/[^a-z0-9가-힣\s]/gi, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 512);
}

export function inferEvalsTags(text: string): TopicTag[] {
  const lower = decodeHtml(text).toLowerCase();
  const tags = TAG_RULES.filter(rule => rule.terms.some(term => lower.includes(term))).map(rule => rule.tag);
  const fallback: TopicTag[] = ["agent-evals"];
  return (tags.length ? tags : fallback).slice(0, 5);
}

export function isEvalsRelevant(candidate: FeedCandidate): boolean {
  const lower = `${candidate.title} ${candidate.excerpt}`.toLowerCase();
  const title = candidate.title.toLowerCase();
  return containsAnyKeyword(lower, EVAL_TERMS)
    && containsAnyKeyword(lower, AI_EVAL_ANCHORS)
    && containsAnyKeyword(title, TITLE_EVAL_TERMS);
}

function tokenSet(value: string): Set<string> {
  return new Set(normalizeTitle(value).split(" ").filter(token => token.length > 2));
}

function jaccard<T>(left: Set<T>, right: Set<T>): number {
  const union = new Set<T>();
  left.forEach(value => union.add(value));
  right.forEach(value => union.add(value));
  if (!union.size) return 0;
  let intersection = 0;
  left.forEach(value => {
    if (right.has(value)) intersection += 1;
  });
  return intersection / union.size;
}

export function similarityScore(title: string, tags: string[], otherTitle: string, otherTags: string[]): number {
  const titleScore = jaccard(tokenSet(title), tokenSet(otherTitle));
  const tagScore = jaccard(new Set(tags), new Set(otherTags));
  return Math.round((titleScore * 0.65 + tagScore * 0.35) * 100);
}

export function sharedTags(tags: string[], otherTags: string[]): string[] {
  return tags.filter(tag => otherTags.includes(tag));
}

export function findRelatedArticles(
  title: string,
  tags: string[],
  priorArticles: Array<{ id: number; title: string; tags: string[] }>
): SimilarityLink[] {
  return priorArticles
    .map(article => ({
      articleId: article.id,
      title: article.title,
      score: similarityScore(title, tags, article.title, article.tags),
      sharedTags: sharedTags(tags, article.tags),
    }))
    .filter(link => link.score >= 28 || link.sharedTags.length >= 2)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
}

export function formatArchiveTimestamp(date: Date): string {
  const pieces = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const read = (type: string) => pieces.find(part => part.type === type)?.value ?? "00";
  return `${read("year")}-${read("month")}-${read("day")}_${read("hour")}-${read("minute")}`;
}

/** Object storage accepts ASCII paths; the user-facing logical path is preserved in the document metadata. */
export function toStorageObjectKey(logicalPath: string): string {
  const filename = logicalPath.split("/").pop()?.replace(/[^a-zA-Z0-9._-]/g, "-") || "evals-update.md";
  return `evals-update-materials/${filename}`;
}

export function buildLearningMarkdown(runDate: Date, articles: ArticleWithNote[], audit: CollectionAudit): string {
  const timestamp = formatArchiveTimestamp(runDate);
  const documentTags = Array.from(new Set(articles.flatMap(article => article.tags))).map(tag => `#${tag}`).join(" ");
  const sections = articles.length ? articles.map((article, index) => {
    const terms = article.note.keyTerms.map(term => `| ${term.term} | ${term.definition} |`).join("\n");
    const points = article.note.learningPoints.map(point => `- ${point}`).join("\n");
    const related = article.related.length
      ? article.related.map(link => `- **${link.title}** — 유사도 ${link.score}% · 공통 태그: ${link.sharedTags.join(", ") || "없음"}`).join("\n")
      : "- 이전 자료와 직접 연결되는 주제가 아직 없습니다. 이 자료가 이후 비교의 기준점이 됩니다.";
    return [
      `## ${index + 1}. ${article.title}`,
      "",
      `**출처:** ${article.sourceName}  `,
      `**원문:** [자료 열기](${article.canonicalUrl})  `,
      `**발행일:** ${article.publishedAt ? article.publishedAt.toISOString().slice(0, 10) : "출처 미표기"}  `,
      `**태그:** ${article.tags.map(tag => `\`${tag}\``).join(" · ")}`,
      "",
      "### 핵심 요약",
      "",
      article.note.summary,
      "",
      "### 초보자를 위한 실무 의미",
      "",
      article.note.practicalMeaning,
      "",
      "### 주요 용어",
      "",
      "| 용어 | 쉬운 정의 |",
      "| --- | --- |",
      terms,
      "",
      "### 학습 포인트",
      "",
      points,
      "",
      "### 이전 학습자료와의 연결",
      "",
      related,
    ].join("\n");
  }).join("\n\n---\n\n") : [
    "## 이번 실행에서 새 학습자료 없음",
    "",
    "이번 검색에서는 직접 Evals 기준과 발췌문 품질 기준을 동시에 충족하는 신규 자료가 없었습니다. 아래 검토 기록에서 중복·무관·발췌문 부족 등 제외 근거를 확인할 수 있습니다.",
  ].join("\n");

  const relevantExclusions = Math.max(0, audit.skippedIrrelevantCount - audit.skippedShortExcerptCount);
  const failedSources = audit.failedSourceNames.length ? audit.failedSourceNames.join(", ") : "없음";
  const review = [
    "## 수집·검토 기록",
    "",
    "> 이 기록은 수집량을 부풀리지 않기 위해 남깁니다. 제외·중복·fallback은 숨겨진 오류가 아니라, 원문 근거와 중복 방지 기준을 적용한 결과입니다.",
    "",
    "| 검토 항목 | 건수 | 처리·문제 근거 |",
    "| --- | ---: | --- |",
    `| 검색 후보 | ${audit.scannedCount} | 활성 피드에서 공정 배분해 검토한 후보 |`,
    `| 신규 학습자료 수용 | ${audit.acceptedCount} | 직접 Evals 관련성·100자 이상 발췌문·중복 기준을 모두 통과 |`,
    `| 정확 중복 제외 | ${audit.skippedExactCount} | URL 또는 정규화 제목이 기존 아카이브와 일치 |`,
    `| 유사 자료 제외 | ${audit.skippedSimilarCount} | 제목·태그 가중 유사도 72% 이상 |`,
    `| 직접성 부족 제외 | ${relevantExclusions} | AI Evals 관련성 키워드와 제목 기준을 함께 충족하지 못함 |`,
    `| 발췌문 부족 제외 | ${audit.skippedShortExcerptCount} | 100자 미만 원문 발췌문으로 근거 기반 노트 작성 불가 |`,
    `| 피드 수집 실패 | ${audit.failedSourceNames.length} | ${failedSources} |`,
    `| LLM 구조화 생성 시도 | ${audit.llmAttempts} | Heartbeat 시간 예산을 위해 실행당 첫 수용 자료에만 적용 |`,
    `| 결정적 fallback 노트 | ${audit.fallbackNoteCount} | LLM 실패·시간 예산 소진 시 보수적 템플릿으로 기록 |`,
    "",
    "### 해석 원칙",
    "",
    "- 신규 수용이 0건이어도 검색이 실패했다는 뜻은 아닙니다. 후보가 기존 자료와 중복되었거나 직접 Evals·발췌문 기준을 충족하지 못했다는 뜻입니다.",
    "- 개별 후보의 제목·출처·판정 사유는 대시보드의 **Duplicate decision ledger**에 보존합니다.",
    "- 피드 수집 실패가 있으면 실행 상태는 `partial`로 기록하며, 다음 주기에서 해당 피드를 다시 시도합니다.",
  ].join("\n");

  return [
    `# AI Evals 학습 업데이트 — ${timestamp}`,
    "",
    "> 이 문서는 AI 에이전트·AI 서비스의 검증 및 평가 관련 신규 자료를 초보 AI 개발자, 데이터사이언티스트, PM이 함께 학습할 수 있도록 정리한 운영용 노트입니다.",
    "",
    `**이번 업데이트:** 신규 자료 ${articles.length}건  `,
    `**주제 태그:** ${documentTags || "신규 수용 자료 없음"}`,
    "",
    "---",
    "",
    sections,
    "",
    "---",
    "",
    review,
    "",
    "---",
    "",
    "## 문서 정보",
    "",
    "| 항목 | 값 |",
    "| --- | --- |",
    `| 생성 시각 | ${runDate.toISOString()} |`,
    `| 논리 저장 경로 | \`evals 업데이트 자료/${timestamp}.md\` |`,
    "| 중복 처리 | URL·정규화 제목·주제 태그 유사도를 순차 비교 |",
    "| 편집 목적 | Evals 개념 학습, 실무 적용, 변화 추적 |",
    "",
  ].join("\n");
}
````

### `server/db.ts`

````typescript
import { eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/mysql2";
import { InsertUser, users } from "../drizzle/schema";
import { ENV } from './_core/env';

let _db: ReturnType<typeof drizzle> | null = null;

// Lazily create the drizzle instance so local tooling can run without a DB.
export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try {
      _db = drizzle(process.env.DATABASE_URL);
    } catch (error) {
      console.warn("[Database] Failed to connect:", error);
      _db = null;
    }
  }
  return _db;
}

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.openId) {
    throw new Error("User openId is required for upsert");
  }

  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot upsert user: database not available");
    return;
  }

  try {
    const values: InsertUser = {
      openId: user.openId,
    };
    const updateSet: Record<string, unknown> = {};

    const textFields = ["name", "email", "loginMethod"] as const;
    type TextField = (typeof textFields)[number];

    const assignNullable = (field: TextField) => {
      const value = user[field];
      if (value === undefined) return;
      const normalized = value ?? null;
      values[field] = normalized;
      updateSet[field] = normalized;
    };

    textFields.forEach(assignNullable);

    if (user.lastSignedIn !== undefined) {
      values.lastSignedIn = user.lastSignedIn;
      updateSet.lastSignedIn = user.lastSignedIn;
    }
    if (user.role !== undefined) {
      values.role = user.role;
      updateSet.role = user.role;
    } else if (user.openId === ENV.ownerOpenId) {
      values.role = 'admin';
      updateSet.role = 'admin';
    }

    if (!values.lastSignedIn) {
      values.lastSignedIn = new Date();
    }

    if (Object.keys(updateSet).length === 0) {
      updateSet.lastSignedIn = new Date();
    }

    await db.insert(users).values(values).onDuplicateKeyUpdate({
      set: updateSet,
    });
  } catch (error) {
    console.error("[Database] Failed to upsert user:", error);
    throw error;
  }
}

export async function getUserByOpenId(openId: string) {
  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot get user: database not available");
    return undefined;
  }

  const result = await db.select().from(users).where(eq(users.openId, openId)).limit(1);

  return result.length > 0 ? result[0] : undefined;
}

// TODO: add feature queries here as your schema grows.
````

### `server/routers.ts`

````typescript
import { COOKIE_NAME } from "@shared/const";
import { TRPCError } from "@trpc/server";
import { parse as parseCookie } from "cookie";
import { z } from "zod";
import { getSessionCookieOptions } from "./_core/cookies";
import { createHeartbeatJob, updateHeartbeatJob } from "./_core/heartbeat";
import { systemRouter } from "./_core/systemRouter";
import { protectedProcedure, publicProcedure, router } from "./_core/trpc";
import { collectEvalsLearningMaterials } from "./archiveCollector";
import { getDashboardData, getSettings, setCollectorEnabled, setDocumentCompletion, setScheduleTaskUid } from "./archiveDb";

export const appRouter = router({
    // if you need to use socket.io, read and register route in server/_core/index.ts, all api should start with '/api/' so that the gateway can route correctly
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(opts => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return {
        success: true,
      } as const;
    }),
  }),
  archive: router({
    dashboard: protectedProcedure.query(async ({ ctx }) => getDashboardData(ctx.user.id)),
    collectNow: protectedProcedure.mutation(async () => collectEvalsLearningMaterials()),
    configureSchedule: protectedProcedure.mutation(async ({ ctx }) => {
      const sessionToken = parseCookie(ctx.req.headers.cookie ?? "")[COOKIE_NAME];
      if (!sessionToken) throw new TRPCError({ code: "UNAUTHORIZED", message: "Heartbeat 예약에는 로그인 세션이 필요합니다." });
      const settings = await getSettings();
      if (settings.scheduleCronTaskUid) return { created: false, taskUid: settings.scheduleCronTaskUid };
      const job = await createHeartbeatJob({ name: "ai-evals-collector", cron: "0 0 */4 * * *", path: "/api/scheduled/collect-evals", description: "Collect diverse AI agent and AI service Evals learning articles and create an evidence-rich Markdown archive every four hours." }, sessionToken);
      await setScheduleTaskUid(job.taskUid);
      return { created: true, taskUid: job.taskUid, nextExecutionAt: job.nextExecutionAt ?? null };
    }),
    setCollectorEnabled: protectedProcedure.input(z.object({ enabled: z.boolean() })).mutation(async ({ input, ctx }) => {
      const sessionToken = parseCookie(ctx.req.headers.cookie ?? "")[COOKIE_NAME];
      if (!sessionToken) throw new TRPCError({ code: "UNAUTHORIZED", message: "Heartbeat 예약 변경에는 로그인 세션이 필요합니다." });
      const settings = await getSettings();
      if (settings.scheduleCronTaskUid) await updateHeartbeatJob(settings.scheduleCronTaskUid, { enable: input.enabled }, sessionToken);
      await setCollectorEnabled(input.enabled);
      return { success: true };
    }),
    setDocumentCompletion: protectedProcedure.input(z.object({ documentId: z.number().int().positive(), completed: z.boolean() })).mutation(async ({ input, ctx }) => {
      await setDocumentCompletion(ctx.user.id, input.documentId, input.completed);
      return { success: true, documentId: input.documentId, completed: input.completed };
    }),
  }),
});

export type AppRouter = typeof appRouter;
````

### `server/storage.ts`

````typescript
// Preconfigured storage helpers for Manus WebDev templates
// Uploads via Forge Server presigned URL to S3 (PUT direct).
// Downloads return /manus-storage/{key} paths served via 307 redirect.

import { ENV } from "./_core/env";

function getForgeConfig() {
  const forgeUrl = ENV.forgeApiUrl;
  const forgeKey = ENV.forgeApiKey;

  if (!forgeUrl || !forgeKey) {
    throw new Error(
      "Storage config missing: set BUILT_IN_FORGE_API_URL and BUILT_IN_FORGE_API_KEY",
    );
  }

  return { forgeUrl: forgeUrl.replace(/\/+$/, ""), forgeKey };
}

function normalizeKey(relKey: string): string {
  return relKey.replace(/^\/+/, "");
}

function appendHashSuffix(relKey: string): string {
  const hash = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  const lastDot = relKey.lastIndexOf(".");
  if (lastDot === -1) return `${relKey}_${hash}`;
  return `${relKey.slice(0, lastDot)}_${hash}${relKey.slice(lastDot)}`;
}

export async function storagePut(
  relKey: string,
  data: Buffer | Uint8Array | string,
  contentType = "application/octet-stream",
): Promise<{ key: string; url: string }> {
  const { forgeUrl, forgeKey } = getForgeConfig();
  const key = appendHashSuffix(normalizeKey(relKey));

  // 1. Get presigned PUT URL from Forge
  const presignUrl = new URL("v1/storage/presign/put", forgeUrl + "/");
  presignUrl.searchParams.set("path", key);

  const presignResp = await fetch(presignUrl, {
    headers: { Authorization: `Bearer ${forgeKey}` },
  });

  if (!presignResp.ok) {
    const msg = await presignResp.text().catch(() => presignResp.statusText);
    throw new Error(`Storage presign failed (${presignResp.status}): ${msg}`);
  }

  const { url: s3Url } = (await presignResp.json()) as { url: string };
  if (!s3Url) throw new Error("Forge returned empty presign URL");

  // 2. PUT file directly to S3
  const blob =
    typeof data === "string"
      ? new Blob([data], { type: contentType })
      : new Blob([data as any], { type: contentType });

  const uploadResp = await fetch(s3Url, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });

  if (!uploadResp.ok) {
    throw new Error(`Storage upload to S3 failed (${uploadResp.status})`);
  }

  return { key, url: `/manus-storage/${key}` };
}

export async function storageGet(relKey: string): Promise<{ key: string; url: string }> {
  const key = normalizeKey(relKey);
  return { key, url: `/manus-storage/${key}` };
}

export async function storageGetSignedUrl(relKey: string): Promise<string> {
  const { forgeUrl, forgeKey } = getForgeConfig();
  const key = normalizeKey(relKey);

  const getUrl = new URL("v1/storage/presign/get", forgeUrl + "/");
  getUrl.searchParams.set("path", key);

  const resp = await fetch(getUrl, {
    headers: { Authorization: `Bearer ${forgeKey}` },
  });

  if (!resp.ok) {
    const msg = await resp.text().catch(() => resp.statusText);
    throw new Error(`Storage signed URL failed (${resp.status}): ${msg}`);
  }

  const { url } = (await resp.json()) as { url: string };
  return url;
}
````

## 10. 변경 시 체크리스트

1. 수집 판정 규칙을 바꾸면 `archiveUtils.ts`와 관련 테스트를 함께 수정합니다.
2. DB 구조를 바꾸면 `drizzle/schema.ts`를 먼저 갱신하고 migration SQL을 생성·검토·적용합니다.
3. 예약 handler를 바꾸면 배포 후 단일 task UID의 callback과 인증을 확인합니다.
4. LLM 프롬프트나 모델을 바꾸면 JSON 구조, fallback, 실행 시간, 한국어 품질을 비교합니다.
5. 논리 파일명은 한글 경로를 유지하고 S3 object key는 ASCII 규칙을 지킵니다.

---

생성 기준: 현재 프로젝트 소스 및 운영 문서 스냅샷
