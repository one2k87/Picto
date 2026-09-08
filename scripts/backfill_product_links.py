# -*- coding: utf-8 -*-
"""기발행 글에 쿠팡 상품 링크를 소급 삽입한다 (2026-09-07 신설).

새로 쓰는 글은 파이프라인이 자동으로 붙이지만, 이미 나간 글은 그대로다.
링크를 대장(data/products.json)에 하나 채울 때마다 이 스크립트를 돌리면
그 제품을 다루는 과거 글 전부에 한 번에 반영된다.

재실행 안전: <!--picklink--> 마커가 있는 글은 건너뛴다(force=true면 교체).
안전장치: 링크가 비어 있는 제품은 절대 삽입하지 않는다.
환경: BACKFILL_LIMIT(기본 100) / BACKFILL_DRY(true면 계획만) / BACKFILL_FORCE
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import products
from publisher import _auth_header, update_post_content

MARK = "<!--picklink-->"


def strip_tags(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()


def insert_mid(html, block, nth_h2=2):
    idxs = [m.start() for m in re.finditer(r"<h2\b", html)]
    if len(idxs) >= nth_h2:
        pos = idxs[nth_h2 - 1]
        return html[:pos] + block + html[pos:]
    return html + block


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    limit = int(os.getenv("BACKFILL_LIMIT") or "100")
    dry = (os.getenv("BACKFILL_DRY") or "").lower() == "true"
    force = (os.getenv("BACKFILL_FORCE") or "").lower() == "true"

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit"}, timeout=30)
        if r.status_code != 200:
            break
        batch = r.json(); posts += batch
        if len(batch) < 50:
            break
        page += 1
    print(f"발행 글 {len(posts)}개 (limit={limit}, dry={dry}, force={force})")

    done = skipped = nolink = 0
    for p in posts:
        if done >= limit:
            break
        pid = p["id"]
        title = strip_tags((p.get("title") or {}).get("rendered") or "")
        slug = p.get("slug") or ""
        content = (p.get("content") or {}).get("raw") or (p.get("content") or {}).get("rendered", "")
        if MARK in content and not force:
            skipped += 1
            continue
        prod = products.find_for({"title": title, "keyword": slug})
        if not prod:
            nolink += 1
            continue
        card = products.card_html(prod, products.safe_subid(slug, pid, title))
        if not card:
            nolink += 1                      # 링크 미등록 제품 — 건너뛴다
            continue
        if MARK in content:                  # force: 기존 카드 제거 후 재삽입
            content = re.sub(r"<!--picklink-->[\s\S]*?<!--/picklink-->", "", content)
        block = MARK + card + "<!--/picklink-->"
        neo = insert_mid(content, block, nth_h2=2)
        print(f"[{pid}] {title[:40]} ← {prod.get('key')}")
        if dry:
            done += 1
            continue
        if update_post_content(wp, pid, neo):
            done += 1
        else:
            print(f"  ✗ 업로드 실패 {pid}")

    summary = f"상품 링크 소급: 삽입 {done}편 · 이미 있음 {skipped}편 · 링크 없음 {nolink}편"
    print(summary)
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat and not dry:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": f"🔗 {summary}"}, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
