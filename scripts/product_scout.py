# -*- coding: utf-8 -*-
"""쿠팡 대장에 넣을 제품을 **숫자로** 고른다 (2026-09-15 신설).

왜: 지금까지 상품을 감으로 골랐고, 그 결과 대장 제품의 실제 검색어가 월 20회인 것도 있었다.
    이제 키워드도구가 붙었으니 후보마다 수요·경쟁·클릭을 붙여 줄을 세운다.

고르는 기준(수익 관점):
  - 적정 구간 = 월 검색량 300~30,000, 경쟁 '높음' 제외
      · 하한 아래: 1위를 해도 클릭이 안 난다
      · 상한 위: 3개월 클릭 3회인 신규 도메인이 넘볼 자리가 아니다
      · 경쟁 높음: 광고주가 몰린 자리는 자연검색도 레드오션
  - 그 안에서 **월평균 클릭수**가 큰 것을 위로 — '검색만 하는 말'과 '살 마음으로 치는 말'을 가른다.
  - 이미 대장에 있는 제품은 뺀다.

결과: dashboard/data/product_scout.json
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import demand
import products

cfg = json.load(open("config.json", encoding="utf-8"))
dc = cfg.get("demand") or {}
if not dc.get("api_key"):
    print("네이버 키 없음 — 종료"); raise SystemExit(0)

FLOOR = int(dc.get("min_volume", 300))
CEIL = int(dc.get("max_volume", 30000))
BLOCK = set(dc.get("block_comp") or ["높음"])

cands = (json.load(open("data/product_candidates.json", encoding="utf-8")) or {}).get("candidates", [])
have = " ".join(re.sub(r"\s", "", json.dumps(p, ensure_ascii=False)) for p in products.all_products())

rows = []
for c in cands:
    if re.sub(r"\s", "", c) in have:
        print(f"{c:<14} (이미 대장에 있음 — 건너뜀)")
        continue
    got = demand.keyword_rows([c], cfg, limit=25)
    core = re.sub(r"\s", "", c)
    rel = [r for r in got if core[:3] in re.sub(r"\s", "", r["keyword"])]
    fit = [r for r in rel if FLOOR <= r["volume"] <= CEIL and r["comp"] not in BLOCK]
    fit.sort(key=lambda r: -r["clicks"])
    head = max(rel, key=lambda r: r["volume"]) if rel else None
    rows.append({
        "candidate": c,
        "head": {"keyword": head["keyword"], "volume": head["volume"], "comp": head["comp"]} if head else None,
        "best": fit[0] if fit else None,
        "fit_n": len(fit),
    })
    b = fit[0] if fit else None
    print(f"{c:<14} 적정 {len(fit):>2}개" + (f" · 최적 {b['keyword'][:14]:<16}{b['volume']:>7,} {b['comp']} 클릭 {b['clicks']}" if b else " · (적정 구간 없음)"))
    time.sleep(0.4)

rows.sort(key=lambda r: -((r["best"] or {}).get("clicks") or 0))
os.makedirs("dashboard/data", exist_ok=True)
json.dump({"at": time.strftime("%Y-%m-%d %H:%M"), "floor": FLOOR, "ceil": CEIL,
           "block_comp": sorted(BLOCK), "rows": rows},
          open("dashboard/data/product_scout.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n저장 완료 — 후보 {len(rows)}종, 적정 구간 보유 {sum(1 for r in rows if r['best'])}종")
