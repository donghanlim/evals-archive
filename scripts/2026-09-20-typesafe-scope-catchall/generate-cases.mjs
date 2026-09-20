// FarmLog work_type 확장 평가셋 v2: 11종(실제 제품) vs 8종(농작업만) 동시 비교
// 정정: R5의 "core.mjs 5종" 은 M0 합성 lab 전용이고 실제 농민앱(app/store.mjs)은 11종이다.
// 이번엔 실제 제품 기준(11종)과, 그중 농작업만 추린 8종(출하·자재구매·기타 제외)을 나란히 측정한다.
import { writeFile } from 'node:fs/promises';
import { workTypes as FULL11 } from '/Users/justimmacbook/Documents/_work/farm-log/src/app/store.mjs';

const SEED = 20260920;
const OUT = '/Users/justimmacbook/.aside/u/0/sessions/2026-09-20_FgKOcF6DhvVhJwzv/tmp/cases_v2_1000.jsonl';

const FARM8 = FULL11.filter((w) => !['출하', '자재구매', '기타'].includes(w));
console.log('FULL11:', FULL11.join('·'));
console.log('FARM8 :', FARM8.join('·'));

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

// 동의어: allowlist 단어를 문자 그대로 포함하지 않는 구어 표현. 기타는 신호가 없어 제외.
const SYNONYM = {
  관수: ['물 줬다', '물 주기 했다', '물을 뿌렸다', '급수했다'],
  파종: ['씨 뿌렸다', '씨앗 뿌렸다', '종자 뿌렸다'],
  정식: ['모종 심었다', '아주심기 했다', '옮겨 심었다'],
  방제: ['약 쳤다', '농약 뿌렸다', '병해충 잡았다'],
  수확: ['거뒀다', '따냈다', '수거했다', '땄다'],
  시비: ['비료 줬다', '거름 줬다', '비료 뿌렸다', '거름 넣었다'],
  제초: ['풀 뽑았다', '김맸다', '잡초 제거했다'],
  적심: ['순 땄다', '순 쳤다', '곁가지 잘랐다', '생장점 제거했다'],
  출하: ['출고했다', '시장에 냈다', '거래처에 보냈다'],
  자재구매: ['농자재 샀다', '비닐 구입했다', '농약을 샀다'],
};
const TARGET_TYPES = Object.keys(SYNONYM); // 기타 제외 10종

// 실제 11종 어디에도 안 속하는 진짜 목록 밖 행동
const OUT_OF_LIST = [
  '밭을 갈았다', '지주를 세웠다', '하우스 비닐을 교체했다',
  '온도를 측정했다', '설비를 점검했다', '전지가위를 손질했다', '배수로를 정비했다',
];

const UNITS = ['L', 'kg', 'g', '개', '포기'];
const PARCELS = ['합성 1번 밭', '합성 2번 밭'];
const CROPS = ['상추', '토마토', '고추'];
const pad = (n) => String(n).padStart(2, '0');
function randDate() {
  const m = 1 + Math.floor(rand() * 12);
  const d = 1 + Math.floor(rand() * 28);
  return `2026-${pad(m)}-${pad(d)}`;
}

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
  if (chance(0.8)) parts.push(pick(PARCELS));
  if (chance(0.75)) parts.push(pick(CROPS));

  let type = null; // 의미상 정답 (11종 중 하나 또는 null)
  if (category === 'literal-single') {
    type = pick(FULL11.filter((w) => w !== '기타')); // 기타는 텍스트 신호가 없어 생성 대상에서 제외
    parts.push(type);
  } else if (category === 'literal-multi') {
    const a = pick(FULL11.filter((w) => w !== '기타'));
    let b = pick(FULL11.filter((w) => w !== '기타'));
    while (b === a) b = pick(FULL11.filter((w) => w !== '기타'));
    parts.push(`${a}와 ${b}을 했다`);
    type = null; // 둘 이상 -> 단일 선택 계약상 불명
  } else if (category === 'synonym') {
    type = pick(TARGET_TYPES);
    parts.push(pick(SYNONYM[type]));
  } else if (category === 'out-of-list') {
    parts.push(pick(OUT_OF_LIST));
    type = null;
  } else {
    type = null;
  }

  if (chance(0.6)) parts.push(`${Math.floor(rand() * 200) + 1} ${pick(UNITS)}`);
  return { text: parts.join(' ').trim(), type };
}

function literalGolden(text, list) {
  const ws = list.filter((w) => text.includes(w));
  return ws.length === 1 ? ws[0] : null;
}

const rows = [];
let i = 0;
for (const [category, count] of PLAN) {
  for (let k = 0; k < count; k++) {
    const { text, type } = buildText(category);
    rows.push({
      id: `v${String(++i).padStart(4, '0')}`,
      category,
      text,
      golden_semantic_11: type,
      golden_semantic_8: FARM8.includes(type) ? type : null, // 8종 범위 밖이면 8종 실험에선 '불명'이 정답
      golden_literal_11: literalGolden(text, FULL11),
      golden_literal_8: literalGolden(text, FARM8),
    });
  }
}

for (let j = rows.length - 1; j > 0; j--) {
  const k = Math.floor(rand() * (j + 1));
  [rows[j], rows[k]] = [rows[k], rows[j]];
}

// 무결성: synonym/out-of-list/no-work 에 allowlist 단어가 새어들면 안 됨
const leaked = rows.filter(
  (r) => ['synonym', 'out-of-list', 'no-work'].includes(r.category) && r.golden_literal_11 !== null
);
if (leaked.length) {
  console.error('무결성 위반:', leaked.slice(0, 5));
  process.exit(1);
}

await writeFile(OUT, rows.map((r) => JSON.stringify(r)).join('\n') + '\n');

const tally = (key) => rows.reduce((a, r) => ((a[r[key] ?? 'null'] = (a[r[key] ?? 'null'] || 0) + 1), a), {});
console.log('\n생성 완료:', rows.length, '건 ->', OUT);
console.log('카테고리:', tally('category'));
console.log('golden_semantic_11 분포:', tally('golden_semantic_11'));
console.log('golden_semantic_8  분포:', tally('golden_semantic_8'));
const gap = rows.filter((r) => r.golden_semantic_11 !== null && r.golden_semantic_8 === null).length;
console.log(`\n11종에서는 답이 있는데 8종 범위 밖이라 8종에선 '불명'이 정답인 케이스: ${gap}건`);
