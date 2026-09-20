#!/usr/bin/env python3
"""FarmLog work_type: TypeSafe Choice 1000건 분석
- 두 채점 기준(리터럴 golden vs 의미 golden) 비교
- N=100/500/1000 중첩 표본으로 표본크기 효과 확인
- Wilson 95% 신뢰구간
- 카테고리별 실패 분류 + 확신도 calibration
"""
import json, math
from collections import defaultdict, Counter

TMP = '/Users/justimmacbook/.aside/u/0/sessions/2026-09-20_FgKOcF6DhvVhJwzv/tmp'

cases = [json.loads(l) for l in open(f'{TMP}/cases_1000.jsonl')]
raw = {r['id']: r for r in (json.loads(l) for l in open(f'{TMP}/raw_1000.jsonl'))}

rows = []
for c in cases:
    r = raw[c['id']]
    pick = None if r['choice'] == '불명' else r['choice']
    rows.append({
        **c,
        'pick': pick,
        'raw_choice': r['choice'],
        'confidence': r.get('confidence'),
        'ms': r.get('ms'),
        'ok_literal': pick == c['golden_literal'],
        'ok_semantic': pick == c['golden_semantic'],
    })

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z/d * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return (p, max(0.0, c-h), min(1.0, c+h))

def fmt(k, n):
    p, lo, hi = wilson(k, n)
    return f'{k}/{n} = {p*100:5.1f}%  [95% CI {lo*100:.1f}–{hi*100:.1f}]'

print('=' * 74)
print('1. 표본 크기별 정확도 (중첩 표본: 앞에서부터 N건)')
print('=' * 74)
print(f'{"N":>6} | {"리터럴 기준":<34} | {"의미 기준":<34}')
print('-' * 74)
for n in (20, 100, 500, 1000):
    sub = rows[:n]
    kl = sum(r['ok_literal'] for r in sub)
    ks = sum(r['ok_semantic'] for r in sub)
    print(f'{n:>6} | {fmt(kl, n):<34} | {fmt(ks, n):<34}')

print()
print('=' * 74)
print('2. 카테고리별 정확도 (N=1000)')
print('=' * 74)
by = defaultdict(list)
for r in rows: by[r['category']].append(r)
print(f'{"카테고리":<16} {"건수":>5} | {"리터럴 기준":>14} | {"의미 기준":>14}')
print('-' * 74)
for cat in ['literal-single', 'literal-multi', 'synonym', 'out-of-list', 'no-work']:
    g = by[cat]; n = len(g)
    kl = sum(r['ok_literal'] for r in g); ks = sum(r['ok_semantic'] for r in g)
    print(f'{cat:<16} {n:>5} | {kl:>5}/{n:<4} {kl/n*100:5.1f}% | {ks:>5}/{n:<4} {ks/n*100:5.1f}%')

print()
print('=' * 74)
print('3. 확신도 calibration  (모델이 X% 확신할 때 실제로 몇 % 맞았나)')
print('=' * 74)
bins = [(0.0,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,0.99),(0.99,1.01)]
for lbl, key in (('리터럴 기준', 'ok_literal'), ('의미 기준', 'ok_semantic')):
    print(f'\n[{lbl}]')
    print(f'{"확신도 구간":<14} {"건수":>5} {"실제정확도":>10}  {"격차":>8}')
    print('-' * 46)
    for lo, hi in bins:
        g = [r for r in rows if r['confidence'] is not None and lo <= r['confidence'] < hi]
        if not g: continue
        acc = sum(r[key] for r in g) / len(g)
        mc = sum(r['confidence'] for r in g) / len(g)
        print(f'{lo:.2f}–{hi:.2f}      {len(g):>5} {acc*100:9.1f}%  {(mc-acc)*100:+7.1f}p')

print()
print('=' * 74)
print('4. 의미 기준 실패 케이스 분류 (N=1000)')
print('=' * 74)
fails = [r for r in rows if not r['ok_semantic']]
print(f'총 실패: {len(fails)}건 ({len(fails)/len(rows)*100:.1f}%)\n')
pat = Counter((r['category'], f"{r['golden_semantic']}→{r['pick']}") for r in fails)
for (cat, mv), cnt in pat.most_common(12):
    print(f'  [{cat:<14}] {mv:<16} {cnt:>4}건')
print('\n실패 예시 6건:')
for r in fails[:6]:
    print(f'  "{r["text"][:44]}"')
    print(f'     의미golden={r["golden_semantic"]} / 모델={r["pick"]} / 확신도={r["confidence"]:.2f}')

print()
print('=' * 74)
print('5. 두 채점 기준이 갈리는 250건에서 무슨 일이 벌어졌나')
print('=' * 74)
div = [r for r in rows if r['golden_literal'] != r['golden_semantic']]
kl = sum(r['ok_literal'] for r in div); ks = sum(r['ok_semantic'] for r in div)
print(f'해당 케이스: {len(div)}건 (모두 synonym 카테고리)')
print(f'  리터럴 기준 정확도: {kl}/{len(div)} = {kl/len(div)*100:.1f}%')
print(f'  의미  기준 정확도: {ks}/{len(div)} = {ks/len(div)*100:.1f}%')
print(f'  -> 같은 답안, 같은 모델인데 채점 기준만 바꿔서 {abs(ks-kl)/len(div)*100:.1f}p 차이')
hi_conf = [r for r in div if r['confidence'] and r['confidence'] >= 0.9]
print(f'\n  이 중 확신도 90% 이상: {len(hi_conf)}건 ({len(hi_conf)/len(div)*100:.1f}%)')
print('  => 확신도 임계값으로는 이 불일치를 걸러낼 수 없음')

print()
print('=' * 74)
print('6. 확신도 임계값을 걸면 어떻게 되나 (의미 기준)')
print('=' * 74)
print(f'{"임계값":>8} {"자동처리":>9} {"자동처리 정확도":>16} {"사람확인 이관":>14}')
print('-' * 60)
for th in (0.0, 0.7, 0.8, 0.9, 0.95, 0.99):
    auto = [r for r in rows if (r['confidence'] or 0) >= th]
    if not auto: continue
    acc = sum(r['ok_semantic'] for r in auto) / len(auto)
    print(f'{th:>8.2f} {len(auto):>6}건 {acc*100:>14.1f}% {len(rows)-len(auto):>11}건')

summary = {
    'n': len(rows),
    'accuracy_literal': sum(r['ok_literal'] for r in rows) / len(rows),
    'accuracy_semantic': sum(r['ok_semantic'] for r in rows) / len(rows),
    'divergent_cases': len(div),
    'by_category': {c: {'n': len(g),
                        'literal': sum(r['ok_literal'] for r in g)/len(g),
                        'semantic': sum(r['ok_semantic'] for r in g)/len(g)}
                    for c, g in by.items()},
}
json.dump(summary, open(f'{TMP}/summary.json', 'w'), ensure_ascii=False, indent=2)
print(f'\n요약 저장: {TMP}/summary.json')
