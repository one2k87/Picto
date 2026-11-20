#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기발행 글에 쿠팡 파트너스 상품 카드(공식 상품 사진)를 넣는다.

사용자 지시(2026-11-20): "배너를 받았으면 상품사진이 있을 거고 그걸 이용하는 게 맞을 거야"

AI 로 그린 그림은 특정 제품의 사진이 아니다. 실제 그 제품을 보여주는 자리에는
쿠팡 파트너스가 링크 생성 화면에서 내주는 공식 상품 배너만 쓴다.

글과 제품을 자동으로 맞추지 않는다. products.find_for 로 돌려 봤더니
「전동 채칼」 글에 전동 야채다지기가 붙었다(11/20 실측). 엉뚱한 제품을 걸면
그 글은 그 순간 신뢰를 잃으므로, 사람이 확인한 쌍만 data/product_card_plan.json 에 적는다.

  [{"post_id": 832, "product_key": "미니LP자석"}]

  python3 scripts/insert_product_cards.py            # 계획만 출력
  python3 scripts/insert_product_cards.py --apply    # 실제 반영
"""
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import products as products_mod            # noqa: E402
import publisher                           # noqa: E402

PLAN = "data/product_card_plan.json"
MARK = "<!--pcard-->"


def load_config():
    for p in ("config.json", "config.example.json"):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


def esc(x):
    import html as _h
    return _h.escape(str(x or ""))


def card_html(pr, slug):
    """상품 사진 + 이름 + 가격 + 링크. weekly_trend_report.product_card 와 같은 모양."""
    img = pr.get("image")
    if not img:
        return ""
    link = pr.get("banner_link") or pr.get("coupang_url") or ""
    if link:
        link = products_mod.with_subid(link, products_mod.safe_subid(slug))
    alt = esc(pr.get("banner_alt") or pr.get("name"))
    bits = [f'<p style="margin:0 0 6px">{alt}</p>']
    if pr.get("price"):
        line = f'<strong style="font-size:1.15em">{int(pr["price"]):,}원</strong>'
        if pr.get("origin_price") and pr.get("discount_rate"):
            line += (f' <span style="color:#888;text-decoration:line-through">'
                     f'{int(pr["origin_price"]):,}원</span>'
                     f' <span style="color:#c0392b">{int(pr["discount_rate"])}%</span>')
        bits.append(f'<p style="margin:0 0 6px">{line}</p>')
    if (pr.get("note") or "").startswith("🚀"):
        bits.append('<p style="margin:0 0 6px">🚀 로켓배송 상품입니다.</p>')
    if pr.get("price_at"):
        bits.append(f'<p style="margin:0 0 6px;color:#777;font-size:.92em">'
                    f'{esc(pr["price_at"])} 기준 가격입니다. 쿠팡 가격은 수시로 바뀝니다.</p>')
    if link:
        bits.append(f'<p style="margin:0"><a href="{link}" target="_blank" '
                    f'rel="nofollow sponsored noopener">쿠팡에서 현재 가격 보기</a></p>')
    tag = (f'<img src="{esc(img)}" alt="{alt}" width="150" height="300" '
           f'style="border:1px solid #e8e8e8;border-radius:8px;display:block">')
    if link:
        tag = f'<a href="{link}" target="_blank" rel="nofollow sponsored noopener">{tag}</a>'
    return (MARK + '<div style="display:flex;gap:18px;align-items:flex-start;margin:20px 0;'
            'flex-wrap:wrap">'
            f'{tag}<div style="flex:1;min-width:230px">{"".join(bits)}</div></div>')


def main():
    apply = "--apply" in sys.argv
    try:
        with open(PLAN, encoding="utf-8") as f:
            plan = json.load(f)
    except Exception:
        print(f"::error::{PLAN} 이 없다 — 글과 제품을 자동으로 맞추지 않는다")
        return 1

    cfg = load_config()
    wp = dict(cfg.get("wordpress") or {})
    if not (wp.get("enabled") and wp.get("site_url")):
        print("::error::wordpress 설정 없음")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = publisher._auth_header(wp["username"], wp["app_password"])

    by_key = {p.get("key"): p for p in products_mod.all_products()}
    ok = skip = fail = 0
    for row in plan:
        pid, key = row.get("post_id"), row.get("product_key")
        pr = by_key.get(key)
        if not pr:
            print(f"  ✗ #{pid}: 대장에 '{key}' 가 없다"); fail += 1; continue
        if not pr.get("image"):
            print(f"  · #{pid}: '{key}' 에 아직 상품 사진이 없다 — 건너뜀"); skip += 1; continue

        # raw 를 읽는다. rendered 는 줄바꿈이 달라 문자열 치환이 조용히 빗나간다(11/19 실측).
        r = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}?context=edit",
                         headers=headers, timeout=40)
        if r.status_code != 200:
            print(f"  ✗ #{pid}: 글을 못 읽음 {r.status_code}"); fail += 1; continue
        d = r.json()
        html_raw = d["content"]["raw"]
        slug = d.get("slug") or f"post-{pid}"

        if MARK in html_raw or (pr.get("banner_link") or "@@") in html_raw:
            print(f"  · #{pid}: 이미 들어 있다 — 건너뜀"); skip += 1; continue

        card = card_html(pr, slug)
        if not card:
            print(f"  ✗ #{pid}: 카드를 만들지 못했다"); fail += 1; continue

        # 첫 소제목 바로 뒤. 글 맨 위는 대가성 문구 자리라 건드리지 않는다.
        m = re.search(r"</h2>", html_raw)
        new = (html_raw[:m.end()] + card + html_raw[m.end():]) if m else (html_raw + card)
        print(f"  → #{pid} '{key}' {int(pr['price']):,}원 카드 삽입"
              + ("" if apply else "  (계획만)"))
        if not apply:
            ok += 1
            continue
        w = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}",
                          headers={**headers, "Content-Type": "application/json"},
                          json={"content": new}, timeout=60)
        if w.status_code in (200, 201):
            print("     ✓ 반영"); ok += 1
        else:
            print(f"     ✗ 실패 {w.status_code}: {w.text[:110]}"); fail += 1

    print(f"\n카드 {ok}건 · 건너뜀 {skip} · 실패 {fail}"
          + ("" if apply else "   (--apply 를 붙이면 실제로 반영한다)"))
    return 0 if not fail else 2


if __name__ == "__main__":
    raise SystemExit(main())
