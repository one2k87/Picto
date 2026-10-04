# -*- coding: utf-8 -*-
"""한 글에 쿠팡 상품 카드가 두 개 들어간 것을 정리한다 (2026-10-04 신설).

왜 생겼나: 카드를 넣는 경로가 둘인데 표시가 한쪽에만 있었다.
  ① 발행 파이프라인 main._apply_product_link  → 마커 없이 넣었다
  ② 소급 삽입 scripts/backfill_product_links  → <!--picklink-->…<!--/picklink--> 로 감싼다
그래서 ②를 force 로 다시 돌려도 ①이 넣어 둔 낡은 카드는 지워지지 않고 남아,
같은 글에 '배너 있는 새 카드'와 '배너 없는 옛 카드'가 함께 나왔다(#100 실측).

이 스크립트는 마커 **밖**에 있는 pick-product 블록만 지운다. 마커 안쪽(현행 카드)은 건드리지 않는다.
앞에 붙어 있는 고지 문단도 함께 지운다 — 카드가 사라지면 그 고지는 가리킬 대상이 없다.
환경: DEDUPE_DRY(true면 계획만) / DEDUPE_LIMIT
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import requests

from publisher import _auth_header, update_post_content

OPEN = '<div class="pick-product"'
NOTICE_RE = re.compile(r'<p[^>]*>\s*이 포스팅은 쿠팡 파트너스 활동의 일환[^<]*</p>\s*$')


def spans(html):
    """pick-product 블록의 (시작, 끝) 위치. 중첩 div 를 세어 정확히 닫는 곳을 찾는다."""
    out, i = [], 0
    while True:
        s = html.find(OPEN, i)
        if s < 0:
            return out
        depth, j = 0, s
        while j < len(html):
            if html.startswith("<div", j):
                depth += 1
                j += 4
            elif html.startswith("</div>", j):
                depth -= 1
                j += 6
                if depth == 0:
                    break
            else:
                j += 1
        out.append((s, j))
        i = j


def protected(html):
    """<!--picklink--> … <!--/picklink--> 구간 = 현행 카드. 건드리지 않는다."""
    return [(m.start(), m.end()) for m in
            re.finditer(r"<!--picklink-->[\s\S]*?<!--/picklink-->", html)]


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    dry = (os.getenv("DEDUPE_DRY") or "").lower() == "true"
    limit = int(os.getenv("DEDUPE_LIMIT") or "100")

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit", "_fields": "id,title,content"}, timeout=30)
        if r.status_code != 200:
            break
        chunk = r.json()
        posts += chunk
        if len(chunk) < 50:
            break
        page += 1
    print(f"대상 {len(posts)}편 · dry_run={dry}")

    fixed, failed = [], []
    for p in posts[:limit]:
        raw = (p.get("content") or {}).get("raw") or ""
        if raw.count(OPEN) < 2:
            continue
        keep = protected(raw)
        drops = [(s, e) for (s, e) in spans(raw)
                 if not any(ps <= s and e <= pe for ps, pe in keep)]
        if not drops:
            continue
        neo = raw
        for s, e in sorted(drops, reverse=True):      # 뒤에서부터 잘라야 위치가 안 밀린다
            head = neo[:s]
            m = NOTICE_RE.search(head)
            if m:
                head = head[:m.start()]
            neo = head + neo[e:]
        title = re.sub(r"<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))[:26]
        print(f"  · #{p['id']} {title}: 낡은 카드 {len(drops)}개 제거 · {len(raw)} → {len(neo)}자")
        if dry:
            continue
        if update_post_content(wp, p["id"], neo):
            fixed.append(p["id"])
        else:
            failed.append(p["id"])

    print(f"\n정리 {len(fixed)}편 · 실패 {len(failed)}편")
    if failed:
        print("  실패:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
