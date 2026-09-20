#!/usr/bin/env python3
"""11종(실제 제품) vs 8종(농작업만) 선택지 세트 비교 분석"""
import json, math
from collections import defaultdict, Counter

TMP = '/Users/justimmacbook/.aside/u/0/sessions/2026-09-20_FgKOcF6DhvVhJwzv/tmp'
cases = {c['id']: c for c in (json.loads(l) for l in open(f'{TMP}/cases_v2_1000.jsonl'))}
raw = [json.loads(l) for l in open(f'{TMP}/raw_v2.jsonl')]

rows11, rows8 = [], []
for r in raw:
    c = cases[r['id']]
    pick = None if r['choice'] == '불명' else r['choice']
    row = {**c, 'pick': pick, 'raw_choice': r['choice'], 'confidence': r['confidence'], 'ms': r['ms']}
    if r['variant'] == 11:
        row['golden'] = c['golden_semantic_11']
        row['ok'] = pick == c['golden_semantic_11']
        rows11.append(row)
    else:
        row['golden'] = c['golden_semantic_8']
        row['ok'] = pick == c['golden_semantic_8']
        rows8.append(row)
rows11.sort(key=lambda r: r['id']); rows8.sort(key=lambda r: r['id'])

def wilson(k, n, z=1.96):
    if n == 0: return (0,0,0)
    p = k/n; d = 1+z*z/n
    c = (p+z*z/(2*n))/d; h = z/d*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return (p, max(0,c-h), min(1,c+h))
def fmt(k,n):
    p,lo,hi = wilson(k,n)
    return f'{k}/{n} = {p*100:5.1f}% [{lo*100:.1f}-{hi*100:.1f}]'

print('='*72); print('1. 전체 정확도: 11종(실제 제품) vs 8종(농작업만)'); print('='*72)
k11 = sum(r['ok'] for r in rows11); k8 = sum(r['ok'] for r in rows8)
print(f'11종 선택지: {fmt(k11, len(rows11))}')
print(f'8종 선택지 : {fmt(k8, len(rows8))}')

print(); print('='*72); print('2. 카테고리별'); print('='*72)
by11 = defaultdict(list); by8 = defaultdict(list)
for r in rows11: by11[r['category']].append(r)
for r in rows8: by8[r['category']].append(r)
print(f'{"카테고리":<16}{"건수":>5} | {"11종":>16} | {"8종":>16}')
for cat in ['literal-single','literal-multi','synonym','out-of-list','no-work']:
    g11, g8 = by11[cat], by8[cat]
    a11 = sum(r['ok'] for r in g11)/len(g11); a8 = sum(r['ok'] for r in g8)/len(g8)
    print(f'{cat:<16}{len(g11):>5} | {a11*100:>14.1f}% | {a8*100:>14.1f}%')

print(); print('='*72); print('3. 11종에서는 답이 있는데 8종 범위 밖인 133건 (범위축소 손실)'); print('='*72)
gap_ids = [r['id'] for r in rows11 if r['golden'] is not None and cases[r['id']]['golden_semantic_8'] is None]
g11 = [r for r in rows11 if r['id'] in gap_ids]
g8  = [r for r in rows8  if r['id'] in gap_ids]
print(f'해당 133건을 11종 선택지로 물으면: {sum(r["ok"] for r in g11)}/{len(g11)} 정확 (정상 인식)')
print(f'같은 133건을 8종 선택지로 물으면 : {sum(r["ok"] for r in g8)}/{len(g8)} 정확 (전부 불명이 정답)')
picks8 = Counter(r['pick'] for r in g8)
print(f'8종 조건에서 모델이 실제로 고른 값 분포: {dict(picks8)}')
forced = [r for r in g8 if r['pick'] is not None]
print(f'-> 8종 범위 밖 행동을 8종 중 하나로 억지로 끼워맞춘 비율: {len(forced)}/{len(g8)} = {len(forced)/len(g8)*100:.1f}%')
if forced:
    print('\n끼워맞춤 예시 5건:')
    for r in forced[:5]:
        print(f'  "{r["text"][:40]}" 실제={cases[r["id"]]["golden_semantic_11"]} -> 8종선택={r["pick"]} (확신도 {r["confidence"]:.2f})')

print(); print('='*72); print('4. 두 조건 모두에서 실패한 케이스 (선택지 크기와 무관한 진짜 실패)'); print('='*72)
common_fail = [r11 for r11 in rows11 if not r11['ok'] and r11['id'] not in gap_ids]
print(f'{len(common_fail)}건')
pat = Counter(f"{r['golden']}→{r['pick']}" for r in common_fail)
for mv, cnt in pat.most_common(10): print(f'  {mv:<20} {cnt}건')

summary = {
  'n': len(rows11),
  'accuracy_11': k11/len(rows11), 'accuracy_8': k8/len(rows8),
  'scope_loss_cases': len(gap_ids),
  'scope_loss_forced_rate': len(forced)/len(g8) if g8 else None,
  'by_category_11': {c: sum(r['ok'] for r in g)/len(g) for c,g in by11.items()},
  'by_category_8': {c: sum(r['ok'] for r in g)/len(g) for c,g in by8.items()},
}
json.dump(summary, open(f'{TMP}/summary_v2.json','w'), ensure_ascii=False, indent=2)
print(f'\n요약 저장: {TMP}/summary_v2.json')
