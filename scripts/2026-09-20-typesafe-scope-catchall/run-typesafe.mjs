// 11종 vs 8종 선택지 세트로 동일 1000건을 각각 실행 (총 2000콜)
import { readFile, writeFile, access } from 'node:fs/promises';

const KEY = process.env.TYPESAFE_API_KEY;
if (!KEY) { console.error('TYPESAFE_API_KEY 없음'); process.exit(1); }

const TMP = '/Users/justimmacbook/.aside/u/0/sessions/2026-09-20_FgKOcF6DhvVhJwzv/tmp';
const IN = `${TMP}/cases_v2_1000.jsonl`;
const OUT = `${TMP}/raw_v2.jsonl`;
const CONCURRENCY = 10;

const DESC = {
  관수: '물을 주는 작업. 관수, 물주기',
  파종: '씨앗을 뿌리는 작업. 파종, 씨뿌리기',
  정식: '모종을 옮겨 심는 작업. 정식, 아주심기',
  방제: '병해충을 막는 작업. 방제, 약제 살포',
  수확: '작물을 거두는 작업. 수확, 수거',
  시비: '비료나 거름을 주는 작업. 시비, 비료주기',
  제초: '잡초를 제거하는 작업. 제초, 풀뽑기',
  적심: '순이나 곁가지를 따내는 작업. 적심, 순따기',
  출하: '수확한 농산물을 시장이나 거래처로 내보내는 작업. 출하, 판매',
  자재구매: '농자재·농약·비닐 등을 구매하는 작업. 자재구매',
  기타: '위 항목 중 어디에도 속하지 않는 그 밖의 농작업',
};
const FULL11 = ['파종', '정식', '관수', '시비', '방제', '제초', '적심', '수확', '출하', '자재구매', '기타'];
const FARM8 = ['파종', '정식', '관수', '시비', '방제', '제초', '적심', '수확'];

function criteriaFor(list) {
  const c = {};
  for (const w of list) c[w] = DESC[w];
  c['불명'] = '위 목록 중 하나로 확정할 수 없음. 작업이 언급되지 않았거나, 목록에 없는 작업이거나, 두 가지 이상이 함께 언급되어 하나로 정할 수 없는 경우';
  return c;
}
const CRIT_11 = criteriaFor(FULL11);
const CRIT_8 = criteriaFor(FARM8);
const INSTR = '이 영농 기록 문장에서 농민이 수행한 작업은 무엇인가? 문장에 명시되지 않았거나 목록에 없는 작업이거나 두 개 이상이면 불명을 고른다.';

const cases = (await readFile(IN, 'utf8')).trim().split('\n').map(JSON.parse);

let done = new Map();
try {
  await access(OUT);
  const prev = (await readFile(OUT, 'utf8')).trim();
  if (prev) for (const l of prev.split('\n')) { const r = JSON.parse(l); done.set(r.key, r); }
  console.log(`재개: 기존 ${done.size}건 건너뜀`);
} catch {}

// 케이스당 두 콜(11종/8종) -> key = id:variant
const jobs = [];
for (const c of cases) {
  jobs.push({ key: `${c.id}:11`, id: c.id, variant: 11, text: c.text, criteria: CRIT_11 });
  jobs.push({ key: `${c.id}:8`, id: c.id, variant: 8, text: c.text, criteria: CRIT_8 });
}
const todo = jobs.filter((j) => !done.has(j.key));
console.log(`실행 대상: ${todo.length}건 (전체 ${jobs.length}건, 병렬 ${CONCURRENCY})`);

async function callOne(j, attempt = 1) {
  const t0 = performance.now();
  try {
    const res = await fetch('https://api.typesafe.ai/v1/systemone', {
      method: 'POST',
      headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state: j.text, model: 'jev-latest',
        questions: { work_type: { type: 'choice', instructions: INSTR, criteria: j.criteria } },
      }),
    });
    if (res.status === 429 || res.status >= 500) throw new Error(`HTTP ${res.status}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const jr = await res.json();
    const a = jr.answers.work_type;
    return {
      key: j.key, id: j.id, variant: j.variant,
      choice: a.choice, confidence: a.confidence ?? null,
      input_tokens: jr.usage?.input_tokens ?? 0, output_tokens: jr.usage?.output_tokens ?? 0,
      ms: Number((performance.now() - t0).toFixed(1)),
    };
  } catch (e) {
    if (attempt <= 4) { await new Promise((r) => setTimeout(r, 400 * attempt * attempt)); return callOne(j, attempt + 1); }
    return { key: j.key, id: j.id, variant: j.variant, error: String(e.message ?? e) };
  }
}

const results = [];
let idx = 0, finished = 0;
const started = performance.now();
async function worker() {
  while (idx < todo.length) {
    const j = todo[idx++];
    const r = await callOne(j);
    results.push(r);
    if (++finished % 200 === 0) console.log(`  ${finished}/${todo.length} (${((performance.now() - started) / 1000).toFixed(1)}s)`);
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker));

const all = [...done.values(), ...results];
all.sort((a, b) => a.key.localeCompare(b.key));
await writeFile(OUT, all.map((r) => JSON.stringify(r)).join('\n') + '\n');

const errs = all.filter((r) => r.error);
const inTok = all.reduce((s, r) => s + (r.input_tokens || 0), 0);
console.log('\n=== 요약 ===', JSON.stringify({
  총콜: all.length, 성공: all.length - errs.length, 실패: errs.length,
  벽시계초: Number(((performance.now() - started) / 1000).toFixed(1)),
  예상비용USD: Number(((inTok / 1e6) * 0.042).toFixed(4)),
}, null, 2));
if (errs.length) console.log('실패 샘플:', errs.slice(0, 3));
