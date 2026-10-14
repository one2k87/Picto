# -*- coding: utf-8 -*-
"""기발행 글의 쿠팡 카드를 첫 h2 앞으로 올린다 (2026-10-14 신설).

왜 — 아이폰 390×844 실측(Playwright): 카드가 모든 글에서 2~3화면 아래에 있었다.
     환급 2,388px(2.8화면) · 할부 1,989(2.4) · 문풍지 1,778(2.1) · 비데 2,577(3.1).
     GSC 클릭은 월 10~15회인데 파트너스 클릭이 0이다 — 들어온 사람이 카드를
     보지도 못한다. 첫 h2 앞(도입부 직후)이면 1.3~1.6화면이 된다.
     LLM 없이 결정적으로 옮긴다. 마커 밖 카드는 건드리지 않는다.

환경: MOVE_DRY(true면 계획만) · MOVE_LIMIT(기본 100)
결과: dashboard/data/move_cards.json
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from publisher import _auth_header, update_post_content

DATA = os.path.join("dashboard", "data")
BLOCK = re.compile(r"\s*<!--picklink-->.*?<!--/picklink-->\s*", re.S)


def move(html):
    """(새 본문, 사유). 이미 첫 h2 앞이면 그대로 둔다."""
    m = BLOCK.search(html)
    if not m:
        return None, "마커로 감싼 카드가 없음"
    block = m.group(0).strip()
    rest = html[:m.start()] + html[m.end():]
    idxs = [x.start() for x in re.finditer(r"<h2\b", rest)]
    if not idxs:
        return None, "h2 가 없음"
    first = idxs[0]
    # 원래 위치가 첫 h2 앞이었으면 옮길 필요가 없다
    if m.start() <= first:
        return None, "이미 첫 h2 앞"
    neo = rest[:first] + "\n" + block + "\n" + rest[first:]
    return neo, f"{len([i for i in re.finditer(r'<h2', html[:m.start()])])}번째 h2 뒤 → 첫 h2 앞"


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    dry = (os.getenv("MOVE_DRY") or "").lower() == "true"
    limit = int(os.getenv("MOVE_LIMIT") or "100")

    posts, page = [], 1
    while page <= 3:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers, timeout=60,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit", "_fields": "id,title,content"})
        if r.status_code != 200:
            print(f"조회 실패 HTTP {r.status_code}")
            break
        chunk = r.json()
        posts += chunk
        if len(chunk) < 50:
            break
        page += 1
    print(f"[move] 발행 {len(posts)}편 · dry_run={dry}\n")

    rows, done, skip = [], 0, 0
    for p in posts[:limit]:
        raw = (p.get("content") or {}).get("raw") or ""
        t = re.sub("<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))[:34]
        neo, why = move(raw)
        if not neo:
            skip += 1
            continue
        # 안전 검증 — 길이와 카드 수가 그대로여야 한다
        if (len(neo) != len(raw) and abs(len(neo) - len(raw)) > 4) \
                or neo.count("pick-product") != raw.count("pick-product"):
            print(f"  ✖ #{p['id']} {t}: 검증 실패(길이 {len(raw)}→{len(neo)})")
            rows.append({"id": p["id"], "ok": False, "why": "검증 실패"})
            continue
        print(f"  · #{p['id']} {t} — {why}")
        if dry:
            skip += 1
            continue
        if update_post_content(wp, p["id"], neo):
            done += 1
            rows.append({"id": p["id"], "ok": True, "why": why})
        else:
            rows.append({"id": p["id"], "ok": False, "why": "업로드 실패"})

    os.makedirs(DATA, exist_ok=True)
    json.dump({"at": datetime.datetime.now().isoformat()[:19], "dry": dry,
               "moved": done, "skipped": skip, "rows": rows},
              open(os.path.join(DATA, "move_cards.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[move] 이동 {done} · 건너뜀 {skip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
