import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const output = path.join(root, "docs", "collection-service-reference.md");

const explicit = [
  "server/archiveCollector.ts",
  "server/archiveDb.ts",
  "server/archiveTypes.ts",
  "server/archiveUtils.ts",
  "server/routers.ts",
  "server/db.ts",
  "server/storage.ts",
  "server/_core/index.ts",
  "server/_core/heartbeat.ts",
  "server/_core/llm.ts",
  "drizzle/schema.ts",
  "package.json",
  "docs/implementation-and-operations-guide.md",
  "docs/operations-handoff.md",
];

const testFiles = fs.readdirSync(path.join(root, "server"))
  .filter((name) => /archive|schedule|collector/i.test(name) && /\\.(test|spec)\\.[cm]?[jt]sx?$/.test(name))
  .map((name) => path.join("server", name));

const migrationFiles = fs.existsSync(path.join(root, "drizzle"))
  ? fs.readdirSync(path.join(root, "drizzle"))
      .filter((name) => /\\.sql$/.test(name))
      .map((name) => path.join("drizzle", name))
  : [];

const files = [...new Set([...explicit, ...testFiles, ...migrationFiles])]
  .filter((relative) => fs.existsSync(path.join(root, relative)))
  .sort();

const lines = [];
lines.push("# AI Evals 자동 수집 서비스 — 운영·구현·코드 레퍼런스");
lines.push("");
lines.push("> 이 문서는 AI 에이전트와 AI 서비스의 Evals(검증·평가) 자료를 4시간 단위로 수집하고, 중복·관련성·근거를 보존하면서 한국어 Markdown 학습자료로 축적하는 현재 수집 서비스의 단일 참조 문서입니다.");
lines.push("");
lines.push("## 1. 서비스 목적");
lines.push("");
lines.push("이 서비스는 초보 AI 개발자, 데이터사이언티스트, PM이 평가 대상·성공 기준·측정 지표·검증 방법을 학습할 수 있도록 공개 RSS/Atom 출처를 폭넓게 수집합니다. 단순히 결과만 남기지 않고 수용 자료, 정확 중복, 유사 중복, 무관 자료, 발췌문 부족, 피드 실패, LLM fallback을 실행 기록과 Markdown에 남겨 수집 품질을 검토할 수 있게 합니다.");
lines.push("");
lines.push("## 2. 현재 운영 기준");
lines.push("");
lines.push("| 항목 | 현재 기준 |");
lines.push("|---|---|");
lines.push("| 실행 방식 | Manus Heartbeat HTTP cron |");
lines.push("| 단일 작업 | `ai-evals-collector-recovery` |");
lines.push("| Task UID | `C5oMCa5z7uCr8hYTRDrFjA` |");
lines.push("| 주기 | `0 0 */4 * * *` — 4시간마다, UTC, 6-field cron |");
lines.push("| Callback | `POST /api/scheduled/collect-evals` |");
lines.push("| 후보 상한 | 실행당 최대 60건, 피드별 round-robin |");
lines.push("| LLM 예산 | 실행당 최대 1회 구조화 노트 생성 |");
lines.push("| 최소 근거 | 발췌문 100자 이상 |");
lines.push("| 논리 저장 경로 | `evals 업데이트 자료/YYYY-MM-DD_HH-mm.md` |");
lines.push("| 물리 저장 | S3에는 ASCII object key, DB에는 논리 경로 보존 |");
lines.push("");
lines.push("## 3. 전체 데이터 흐름");
lines.push("");
lines.push("```text");
lines.push("Heartbeat POST");
lines.push("  → cron 세션 인증 및 task UID로 archive_settings 조회");
lines.push("  → 활성 RSS/Atom 출처 병렬 로드");
lines.push("  → 피드별 round-robin 후보 선택");
lines.push("  → Evals 직접 관련성 + 발췌문 길이 필터");
lines.push("  → URL hash / 정규화 제목 / 태그·제목 유사도 중복 판정");
lines.push("  → 신규 후보만 LLM 구조화 노트 또는 deterministic fallback");
lines.push("  → articles + article_notes + duplicate_decisions 저장");
lines.push("  → Markdown 생성 → S3 업로드 → learning_documents 등록");
lines.push("  → run ledger 완료 및 신규 수용 시에만 소유자 알림");
lines.push("```");
lines.push("");
lines.push("## 4. 판정·품질·중복 규칙");
lines.push("");
lines.push("후보는 제목·URL·발췌문과 출처 메타데이터를 바탕으로 직접적인 Evals 관련성을 먼저 판정합니다. 관련성이 없거나 발췌문이 100자 미만이면 노트 생성 대상에서 제외하고 사유를 `duplicate_decisions`에 기록합니다. 정확 중복은 canonical URL hash 또는 정규화 제목 일치로 판단합니다. 정확 중복이 아니어도 제목 토큰과 핵심 주제 태그의 가중 유사도가 72% 이상이면 유사 중복으로 건너뜁니다.");
lines.push("");
lines.push("자료가 수용되면 첫 번째 신규 자료에만 구조화 LLM을 호출합니다. 이후 신규 자료는 deterministic fallback note로 보존해 Heartbeat 2분 제한을 넘지 않도록 합니다. LLM 응답은 summary, practicalMeaning, tags, keyTerms, learningPoints 구조를 요구하고, 파싱 실패·필수 필드 누락·네트워크 오류는 fallback과 ledger의 `fallbackNoteCount`로 남깁니다.");
lines.push("");
lines.push("## 5. 저장 모델");
lines.push("");
lines.push("| 테이블 | 책임 |");
lines.push("|---|---|");
lines.push("| `archive_sources` | RSS/Atom 출처, 활성 상태, 마지막 오류 |");
lines.push("| `archive_settings` | singleton 설정, Heartbeat UID, 마지막 수집 시각 |");
lines.push("| `collection_runs` | 실행 시각, 후보·수용·제외·fallback·실패 통계 |");
lines.push("| `articles` | 원문 URL, 제목, 발췌문, 태그, 관련성 점수 |");
lines.push("| `article_notes` | 한국어 요약, 실무 의미, 핵심 용어, 학습 포인트, 유사 링크 |");
lines.push("| `duplicate_decisions` | accepted/skipped 결정, 매칭 문서, 점수, 근거 |");
lines.push("| `learning_documents` | 논리 파일명, S3 key/URL, 문서 생성 시각 |");
lines.push("| `user_document_progress` | 사용자별 읽기 완료 상태 — 수집 서비스와 대시보드 연결 |");
lines.push("");
lines.push("## 6. 운영·보안 기준");
lines.push("");
lines.push("Heartbeat handler는 `/api/scheduled/` 경로에서만 동작하며 cron 세션의 `taskUid`로 설정 행을 찾습니다. 요청 본문을 소유권 식별자로 사용하지 않습니다. 세션 cookie가 없거나 task UID가 없으면 인증 실패로 처리합니다. 수집은 idempotent한 URL·제목·유사도 판정을 사용하며, 5xx·429 재시도에 대비해 동일 후보가 중복 저장되지 않도록 합니다.");
lines.push("");
lines.push("현재 서비스는 예약 작업을 하나만 유지합니다. 변경 시 기존 task UID를 기준으로 갱신하고, 새 작업을 중복 생성하지 않습니다. callback handler 변경 후에는 배포된 URL이 먼저 갱신되어야 하며, Heartbeat 플랫폼은 로컬 개발 URL을 호출하지 않습니다.");
lines.push("");
lines.push("## 7. 장애·실패 기록 방식");
lines.push("");
lines.push("피드 하나가 실패해도 나머지 출처는 `Promise.allSettled`로 계속 처리합니다. 실패한 출처 이름은 실행 Markdown에 기록합니다. 관련성 부족, 짧은 발췌문, 정확 중복, 유사 중복, LLM fallback은 숨기지 않고 판정 기록과 실행 ledger에 함께 남깁니다. 신규 수용이 0건인 실행도 운영 검토 Markdown을 만들며, 소유자 알림은 신규 수용 자료가 있을 때만 발송합니다.");
lines.push("");
lines.push("## 8. 테스트·검증 기준");
lines.push("");
lines.push("수집기 테스트는 피드별 공정 배분, 직접 Evals 관련성, 100자 발췌문 기준, URL·제목·태그 유사도 중복 판정, LLM 1회 예산과 fallback, Markdown 감사 기록을 검증합니다. 예약 테스트는 인증된 세션 cookie 전달, task UID 소유권, 4시간 기본 cron을 검증합니다. 실행 전후에는 `pnpm test`, `pnpm check`, `pnpm build`를 사용합니다.");
lines.push("");
lines.push("## 9. 코드 부록 파일 목록");
lines.push("");
lines.push(`이 문서의 코드 부록은 현재 저장소에서 수집 서비스에 직접 관여하는 **${files.length}개 파일**을 읽어 생성했습니다. 각 블록의 경로는 저장소 기준 상대 경로입니다.`);
lines.push("");

for (const relative of files) {
  const full = path.join(root, relative);
  const content = fs.readFileSync(full, "utf8");
  const ext = path.extname(relative).slice(1) || "text";
  const language = ext === "ts" || ext === "tsx" ? "typescript" : ext === "json" ? "json" : ext === "sql" ? "sql" : ext === "md" ? "markdown" : ext;
  lines.push("### `" + relative + "`");
  lines.push("");
  lines.push("````" + language);
  lines.push(content.replace(/\s+$/, ""));
  lines.push("````");
  lines.push("");
}

lines.push("## 10. 변경 시 체크리스트");
lines.push("");
lines.push("1. 수집 판정 규칙을 바꾸면 `archiveUtils.ts`와 관련 테스트를 함께 수정합니다.");
lines.push("2. DB 구조를 바꾸면 `drizzle/schema.ts`를 먼저 갱신하고 migration SQL을 생성·검토·적용합니다.");
lines.push("3. 예약 handler를 바꾸면 배포 후 단일 task UID의 callback과 인증을 확인합니다.");
lines.push("4. LLM 프롬프트나 모델을 바꾸면 JSON 구조, fallback, 실행 시간, 한국어 품질을 비교합니다.");
lines.push("5. 논리 파일명은 한글 경로를 유지하고 S3 object key는 ASCII 규칙을 지킵니다.");
lines.push("");
lines.push("---");
lines.push("");
lines.push("생성 기준: 현재 프로젝트 소스 및 운영 문서 스냅샷");
lines.push("");
fs.writeFileSync(output, lines.join("\n"), "utf8");
console.log(`Generated ${output} with ${files.length} source/document files.`);
