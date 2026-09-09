# -*- coding: utf-8 -*-
"""기발행 글에서 빈 「[ 광고 자리 ]」 상자를 걷어낸다 (2026-09-09 신설).

왜: generator._ad_slot()이 광고 코드가 없어도 점선 상자를 그리고 그 안에
    "[ 광고 자리 ]"를 **독자에게 보이는 텍스트로** 찍었다. 픽담은 애드센스
    미신청이라 채울 코드가 없는데 공개 14편 전부에 빈 상자가 나갔다(실측 19개).
    독자 신뢰를 깎고, 나중에 애드센스 심사에서 '가치 낮은 콘텐츠' 신호가 된다.

안전장치:
  - **광고 코드가 들어 있는 상자는 건드리지 않는다.** 비어 있는 것만 지운다.
  - 상자와 함께 붙어 있던 CTA 문구도 상자 안에 있으므로 같이 사라진다.
  - dry(기본 true)면 계획만 출력한다.

환경: STRIP_DRY(기본 true) / STRIP_LIMIT(기본 100)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from publisher import _auth_header, update_post_content

# 광고 상자 한 덩어리. 안에 실제 코드가 있으면 뒤에서 걸러낸다.
BOX = re.compile(r'<div class="ad-slot"[^>]*>.*?</div>\s*</div>|<div class="ad-slot"[^>]*>.*?</div>',
                 re.S | re.I)
HAS_REAL_AD = re.compile(r'<ins\b|adsbygoogle|<iframe\b|<script\b', re.I)
PLACEHOLDER = "[ 광고 자리 ]"


def strip_boxes(html):
    """빈 광고 상자만 제거. (새 html, 제거 개수, 남긴 개수)"""
    removed = kept = 0
    out, pos = [], 0
    for m in BOX.finditer(html or ""):
        block = m.group(0)
        if HAS_REAL_AD.search(block):          # 진짜 광고가 들어 있으면 보존
            kept += 1
            continue
        out.append(html[pos:m.start()])
        pos = m.end()
        removed += 1
    out.append(html[pos:])
    neo = "".join(out)
    neo = re.sub(r"\n{3,}", "\n\n", neo)
    return neo, removed, kept


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    dry = (os.getenv("STRIP_DRY") or "true").lower() == "true"
    limit = int(os.getenv("STRIP_LIMIT") or "100")

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers,
                         params={"per_page": 50, "page": page, "status": "publish,draft,future",
                                 "context": "edit"}, timeout=30)
        if r.status_code != 200:
            print(f"글 조회 실패 {r.status_code}: {r.text[:200]}"); return
        b = r.json(); posts += b
        if len(b) < 50:
            break
        page += 1
    print(f"글 {len(posts)}개 (dry={dry}, limit={limit})")

    done = total_removed = total_kept = fail = 0
    for p in posts[:limit]:
        pid = p["id"]
        html = (p.get("content") or {}).get("raw") or ""
        if not html or ("ad-slot" not in html and PLACEHOLDER not in html):
            continue
        neo, removed, kept = strip_boxes(html)
        total_kept += kept
        if PLACEHOLDER in neo:                 # 상자 밖에 남은 자리표시 텍스트도 제거
            neo = neo.replace(PLACEHOLDER, "")
        if neo == html:
            continue
        title = re.sub(r"<[^>]+>", "", (p.get("title") or {}).get("rendered") or "")[:30]
        print(f"[{pid}] 빈 광고상자 {removed}개 제거"
              + (f" · 실제 광고 {kept}개 보존" if kept else "") + f" · {title}")
        total_removed += removed
        if dry:
            done += 1
            continue
        if update_post_content(wp, pid, neo):
            done += 1
        else:
            fail += 1
            print(f"  ✗ 저장 실패 {pid}")

    print(f"광고 자리 정리: 대상 {done}편 · 제거 {total_removed}개 · "
          f"실제 광고 보존 {total_kept}개 · 실패 {fail}편")
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat and not dry:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat,
                                "text": f"🧹 빈 광고자리 {total_removed}개 제거({done}편)"}, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
