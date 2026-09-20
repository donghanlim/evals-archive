// TypeSafe Choice 1000건 실행 (병렬 제한 + 재개 지원)
import { readFile, writeFile, access } from 'node:fs/promises';

const KEY = process.env.TYPESAFE_API_KEY;
if (!KEY) { console.error('TYPESAFE_API_KEY 없음'); process.exit(1); }

const TMP = '/Users/justimmacbook/.aside/u/0/sessions/2026-09-20_FgKOcF6DhvVhJwzv/tmp';
const IN = `${TMP}/cases_1000.jsonl`;
const OUT = `${TMP}/raw_1000.jsonl`;
const CONCURRENCY = 10;

const criteria = {
  관수: '물을 주는 작업. 관수, 물주기',
  파종: '씨앗을 뿌리는 작업. 파종, 씨뿌리기',
  정식: '모종을 옮겨 심는 작업. 정식, 아주심기',
  방제: '병해충을 막는 작업. 방제, 약제 살포',
  수확: '작물을 거두는 작업. 수확, 수거',
  불명: '위 5가지 중 하나로 확정할 수 없음. 작업이 언급되지 않았거나, 목록에 없는 작업이거나, 두 가지 이상이 함께 언급되어 하나로 정할 수 없는 경우',
};
const INSTRUCTIONS =
  '이 영농 기록 문장에서 농민이 수행한 작업은 무엇인가? 문장에 명시되지 않았거나 목록에 없는 작업이거나 두 개 이상이면 불명을 고른다.';

const cases = (await readFile(IN, 'utf8')).trim().split('\n').map(JSON.parse);

// 재개: 이미 받은 id 는 건너뜀
let done = new Map();
try {
  await access(OUT);
  const prev = (await readFile(OUT, 'utf8')).trim();
  if (prev) for (const l of prev.split('\n')) { const r = JSON.parse(l); done.set(r.id, r); }
  console.log(`재개: 기존 ${done.size}건 건너뜀`);
} catch { /* 첫 실행 */ }

const todo = cases.filter((c) => !done.has(c.id));
console.log(`실행 대상: ${todo.length}건 (병렬 ${CONCURRENCY})`);

async function callOne(c, attempt = 1) {
  const t0 = performance.now();
  try {
    const res = await fetch('https://api.typesafe.ai/v1/systemone', {
      method: 'POST',
      headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state: c.text,
        model: 'jev-latest',
        questions: { work_type: { type: 'choice', instructions: INSTRUCTIONS, criteria } },
      }),
    });
    if (res.status === 429 || res.status >= 500) throw new Error(`HTTP ${res.status}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const j = await res.json();
    const a = j.answers.work_type;
    return {
      id: c.id,
      choice: a.choice,
      confidence: a.confidence ?? null,
      probabilities: a.probabilities ?? null,
      input_tokens: j.usage?.input_tokens ?? 0,
      output_tokens: j.usage?.output_tokens ?? 0,
      ms: Number((performance.now() - t0).toFixed(1)),
    };
  } catch (e) {
    if (attempt <= 4) {
      await new Promise((r) => setTimeout(r, 400 * attempt * attempt));
      return callOne(c, attempt + 1);
    }
    return { id: c.id, error: String(e.message ?? e) };
  }
}

const results = [];
let idx = 0, finished = 0;
const started = performance.now();

async function worker() {
  while (idx < todo.length) {
    const c = todo[idx++];
    const r = await callOne(c);
    results.push(r);
    if (++finished % 100 === 0) {
      const el = (performance.now() - started) / 1000;
      console.log(`  ${finished}/${todo.length} 완료 (${el.toFixed(1)}s)`);
    }
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker));

const all = [...done.values(), ...results];
all.sort((a, b) => a.id.localeCompare(b.id));
await writeFile(OUT, all.map((r) => JSON.stringify(r)).join('\n') + '\n');

const errs = all.filter((r) => r.error);
const inTok = all.reduce((s, r) => s + (r.input_tokens || 0), 0);
const outTok = all.reduce((s, r) => s + (r.output_tokens || 0), 0);
const msList = all.filter((r) => !r.error).map((r) => r.ms).sort((a, b) => a - b);
const pct = (p) => msList[Math.floor(msList.length * p)] ?? 0;

console.log('\n=== 실행 요약 ===');
console.log(JSON.stringify({
  총건수: all.length,
  성공: all.length - errs.length,
  실패: errs.length,
  벽시계초: Number(((performance.now() - started) / 1000).toFixed(1)),
  지연ms: { p50: pct(0.5), p90: pct(0.9), p99: pct(0.99) },
  토큰: { input: inTok, output: outTok },
  예상비용USD: Number(((inTok / 1e6) * 0.042).toFixed(4)),
}, null, 2));
if (errs.length) console.log('실패 샘플:', errs.slice(0, 3));
