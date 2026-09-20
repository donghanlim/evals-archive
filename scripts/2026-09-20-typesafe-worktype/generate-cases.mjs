// FarmLog work_type 확장 평가셋 생성기 (시드 고정, 결정론적)
// 목적: 리터럴 golden(core.mjs 규칙) vs 의미 golden(사람 기준)의 괴리를 정량화
// 무결성: golden_literal 은 라벨링하지 않고 core.mjs 와 동일한 규칙으로 '계산'한다.
import { writeFile } from 'node:fs/promises';
import { workTypes, crops, parcels } from '/Users/justimmacbook/Documents/_work/farm-log/src/core.mjs';

const SEED = 20260920;
const N = 1000;
const OUT = '/Users/justimmacbook/.aside/u/0/sessions/2026-09-20_FgKOcF6DhvVhJwzv/tmp/cases_1000.jsonl';

// mulberry32: 시드 고정 난수
function rng(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = rng(SEED);
const pick = (a) => a[Math.floor(rand() * a.length)];
const chance = (p) => rand() < p;

// C: 동의어/구어 표현 -> 의미상 매핑되는 allowlist 작업
// 주의: 아래 문구에는 allowlist 단어(관수/파종/정식/방제/수확)가 절대 포함되면 안 된다.
const SYNONYM = {
  관수: ['물 줬다', '물 주기 했다', '물을 뿌렸다', '급수했다', '물 대줬다'],
  파종: ['씨 뿌렸다', '씨앗 뿌렸다', '종자 뿌렸다', '씨 넣었다'],
  정식: ['모종 심었다', '아주심기 했다', '옮겨 심었다', '모종 옮겼다'],
  방제: ['약 쳤다', '농약 뿌렸다', '병해충 잡았다', '약제 살포했다'],
  수확: ['거뒀다', '따냈다', '수거했다', '걷어들였다', '땄다'],
};
// D: allowlist 에 아예 없는 작업 (의미상으로도 5종 중 하나로 확정 불가 -> 불명)
const OUT_OF_LIST = ['김매기 했다', '비료 줬다', '순 땄다', '지주 세웠다', '밭 갈았다', '퇴비 넣었다', '하우스 비닐 갈았다'];

const UNITS = ['L', 'kg', 'g', '개', '포기'];
const pad = (n) => String(n).padStart(2, '0');
function randDate() {
  const m = 1 + Math.floor(rand() * 12);
  const d = 1 + Math.floor(rand() * 28);
  return `2026-${pad(m)}-${pad(d)}`;
}

// 카테고리 분포 (합 1000)
const PLAN = [
  ['literal-single', 400],
  ['synonym', 250],
  ['out-of-list', 150],
  ['literal-multi', 100],
  ['no-work', 100],
];

function buildText(category) {
  const parts = [];
  if (chance(0.85)) parts.push(randDate());
  if (chance(0.8)) parts.push(pick(parcels).name);
  if (chance(0.75)) parts.push(pick(crops));

  let semantic; // 의미 기준 정답 (null = 불명)
  if (category === 'literal-single') {
    const w = pick(workTypes);
    parts.push(w);
    semantic = w;
  } else if (category === 'literal-multi') {
    const a = pick(workTypes);
    let b = pick(workTypes);
    while (b === a) b = pick(workTypes);
    parts.push(`${a}와 ${b}을 했다`);
    semantic = null; // 둘 이상이라 하나로 확정 불가
  } else if (category === 'synonym') {
    const w = pick(workTypes);
    parts.push(pick(SYNONYM[w]));
    semantic = w; // 의미상으로는 확정 가능
  } else if (category === 'out-of-list') {
    parts.push(pick(OUT_OF_LIST));
    semantic = null; // 목록 밖 -> 불명
  } else {
    semantic = null; // 작업 언급 자체가 없음
  }

  if (chance(0.6)) parts.push(`${(Math.floor(rand() * 200) + 1)} ${pick(UNITS)}`);
  return { text: parts.join(' ').trim(), semantic };
}

// core.mjs 와 동일한 리터럴 규칙으로 golden 을 '계산'
function literalGolden(text) {
  const ws = workTypes.filter((w) => text.includes(w));
  return ws.length === 1 ? ws[0] : null;
}

const rows = [];
let i = 0;
for (const [category, count] of PLAN) {
  for (let k = 0; k < count; k++) {
    const { text, semantic } = buildText(category);
    rows.push({
      id: `c${String(++i).padStart(4, '0')}`,
      category,
      text,
      golden_literal: literalGolden(text),
      golden_semantic: semantic,
    });
  }
}

// 결정론적 셔플 (N=100/500 이 전체의 대표 표본이 되도록)
for (let j = rows.length - 1; j > 0; j--) {
  const k = Math.floor(rand() * (j + 1));
  [rows[j], rows[k]] = [rows[k], rows[j]];
}

// 무결성 점검: 동의어/목록밖/작업없음 카테고리에 allowlist 단어가 새어들면 안 됨
const leaked = rows.filter(
  (r) => ['synonym', 'out-of-list', 'no-work'].includes(r.category) && r.golden_literal !== null
);
if (leaked.length) {
  console.error('무결성 위반: allowlist 단어 누출', leaked.slice(0, 5));
  process.exit(1);
}

await writeFile(OUT, rows.map((r) => JSON.stringify(r)).join('\n') + '\n');

const tally = (key) =>
  rows.reduce((a, r) => ((a[r[key] ?? 'null'] = (a[r[key] ?? 'null'] || 0) + 1), a), {});
console.log('생성 완료:', rows.length, '건 ->', OUT);
console.log('카테고리 분포:', tally('category'));
console.log('리터럴 golden 분포:', tally('golden_literal'));
console.log('의미 golden 분포:', tally('golden_semantic'));
const diff = rows.filter((r) => r.golden_literal !== r.golden_semantic).length;
console.log(`두 golden 이 갈리는 케이스: ${diff}건 (${((diff / rows.length) * 100).toFixed(1)}%)`);
console.log('\n샘플 8건:');
rows.slice(0, 8).forEach((r) =>
  console.log(`  [${r.category}] "${r.text}" -> 리터럴=${r.golden_literal} 의미=${r.golden_semantic}`)
);
