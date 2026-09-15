# -*- coding: utf-8 -*-
"""대장 제품별 키워드 수요·경쟁 지도 (2026-09-15).

왜: 지금까지 쿠팡 상품과 주제를 **감으로** 골랐다. 실측 결과 수요가 큰 쪽은
    수수료 0원인 서비스 주제였고, 대장 제품은 월 400~1,000대였다.
    검색량만 보면 안 된다 — 많으면 경쟁이 세고, 없으면 클릭이 안 난다.
    그래서 제품별로 **검색량·경쟁정도·클릭수**를 함께 뽑아 고를 근거를 만든다.

결과: dashboard/data/keyword_report.json  (키 값은 기록하지 않는다)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import demand
import products

cfg = json.load(open("config.json", encoding="utf-8"))
if not (cfg.get("demand") or {}).get("api_key"):
    print("네이버 키 없음 — 종료"); raise SystemExit(0)

out = []
for p in products.all_products():
    hint = p.get("search") or p.get("name") or p.get("key")
    rows = demand.keyword_rows(hint, cfg, limit=25)
    out.append({"key": p.get("key"), "name": p.get("name"), "hint": hint,
                "has_link": bool((p.get("coupang_url") or "").strip()), "rows": rows})
    print(f"{p.get('key'):<16} {hint[:20]:<22} 후보 {len(rows)}개")
    time.sleep(0.4)

os.makedirs("dashboard/data", exist_ok=True)
json.dump({"at": time.strftime("%Y-%m-%d %H:%M"), "products": out},
          open("dashboard/data/keyword_report.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"저장 완료 — 제품 {len(out)}종")
