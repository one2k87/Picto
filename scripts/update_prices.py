# -*- coding: utf-8 -*-
"""쿠팡 가격·품절을 대장(products.json)에 기록 (2026-11-12 신설).

**출처**: 쿠팡 상품 페이지의 JSON-LD(`script[type="application/ld+json"]` 중 `@type=Product`).
  `offers.price`(원) · `offers.availability`(InStock/OutOfStock) · `aggregateRating.ratingValue`.
  2026-11-12 실측 확인 — 문풍지 링크에서 price=5900, availability=InStock, rating=4.5 가 나왔다.

**누가 읽는가**: **픽토 세션이 사용자 크롬으로** 연다. GitHub Actions 에서는 하지 않는다 —
  쿠팡 봇 차단에 걸리고 약관 위험이 있다. 쿠팡 파트너스 오픈API 는 **누적 수익 15만 원** 달성
  후에야 발급되므로(2026-09 가이드 실측), 그 전까지 이 경로가 유일하다.

**왜 날짜를 같이 적는가**: 날짜 없는 금액은 언제부터 틀렸는지 알 수 없다. 글에는 항상
  `price_at` 을 함께 쓴다. '만 원대' 로 뭉개는 건 채널 신뢰도를 깎으므로 하지 않는다(사용자 지시).

입력(JSON): {"<제품 key 또는 name>": {"price": 5900, "availability": "InStock", "rating": 4.5}, ...}
실행: python scripts/update_prices.py prices.json
"""
import datetime as dt
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, "data", "products.json")


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/update_prices.py <가격.json>")
        return 1
    with open(sys.argv[1], encoding="utf-8") as f:
        incoming = json.load(f)
    with open(PATH, encoding="utf-8") as f:
        doc = json.load(f)
    today = dt.date.today().isoformat()
    hit, miss, changed = 0, [], []
    for ident, v in incoming.items():
        row = next((p for p in doc.get("products", [])
                    if p.get("key") == ident or p.get("name") == ident), None)
        if not row:
            miss.append(ident)
            continue
        before = row.get("price")
        price = v.get("price")
        if price:
            row["price"] = int(price)
            row["price_at"] = today
            if before and int(before) != int(price):
                changed.append(f"{ident}: {int(before):,} → {int(price):,}")
        if v.get("availability"):
            row["availability"] = v["availability"]
        if v.get("rating"):
            row["rating"] = v["rating"]
        hit += 1
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"[price] 기록 {hit}건 / 못 찾음 {len(miss)}건 {miss if miss else ''}")
    for c in changed:
        print(f"        가격 변동 — {c}")
    out = [p for p in doc.get("products", [])
           if str(p.get("availability") or "").lower() in ("outofstock", "soldout")]
    if out:
        print("::warning::품절 상품 " + str(len(out)) + "건 — "
              + ", ".join(p.get("key", "?") for p in out) + " (링크 교체 필요)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
