# -*- coding: utf-8 -*-
"""기발행 글의 대표이미지·요약을 채운다 (2026-09-09 신설).

왜 필요한가:
  발행 파이프라인이 본문 이미지는 만들어 올리면서 `featured_media`는 지정하지 않았다.
  그래서 홈·목록의 카드 썸네일이 전부 빈 회색이었다(실측: 발행 12편 전부 featured_media=0).
  요약(excerpt)이 빈 글은 카드에 본문 첫 문장 대신 AI 고지문이 노출됐다.

하는 일(둘 다 이미 값이 있으면 건드리지 않는다):
  ① 대표이미지 — 본문의 첫 업로드 이미지를 승격.
     본문에 이미지가 아예 없으면 제목을 얹은 브랜드 카드를 만들어 올린다(안전망).
  ② 요약 — 비어 있으면 Rank Math 메타설명 → 없으면 본문 첫 문장으로 채운다.

환경: FEATURED_LIMIT(기본 100) / FEATURED_DRY(true면 계획만) / FEATURED_CARD(false면 카드 생성 끔)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import images
import publisher
from publisher import _auth_header

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "output", "featured")


def strip_tags(h):
    h = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def first_sentence(html, limit=150):
    """카드에 쓸 한 문장. 고지문·안내 문구는 건너뛴다(그게 노출되던 게 문제였다)."""
    text = strip_tags(html)
    for bad in ("이 포스팅은 쿠팡", "AI", "인공지능", "이 글은 정보 제공"):
        if text.startswith(bad):
            parts = re.split(r"(?<=[.!?])\s+", text)
            text = " ".join(parts[1:]) if len(parts) > 1 else text
            break
    out = re.split(r"(?<=[.!?])\s+", text)
    s = (out[0] if out else text).strip()
    if len(s) < 30 and len(out) > 1:          # 너무 짧으면 한 문장 더
        s = (s + " " + out[1]).strip()
    return s[:limit].strip()


def brand_card(post_id, title, wp_cfg, alt=""):
    """본문에 쓸 이미지가 없는 글용 — 제목을 얹은 브랜드 카드를 만들어 업로드.
    images._thumbnail은 경로가 아니라 PNG 바이트를 돌려준다(실측). 파일로 떨군 뒤 올린다."""
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        data = images._thumbnail(title, "생활·주방", "1200x630")
    except Exception as e:
        print(f"  · 카드 생성 실패: {e}")
        return None
    if not data:
        print("  · 카드 생성 실패(Pillow·한글폰트 확인)")
        return None
    path = os.path.join(OUT_DIR, f"featured-{post_id}.png")
    with open(path, "wb") as f:
        f.write(data)
    url = publisher.upload_media(path, wp_cfg, alt=alt or title)
    return publisher.MEDIA_ID_BY_URL.get(url) if url else None


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    limit = int(os.getenv("FEATURED_LIMIT") or "100")
    dry = (os.getenv("FEATURED_DRY") or "").lower() == "true"
    allow_card = (os.getenv("FEATURED_CARD") or "true").lower() != "false"

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit"}, timeout=30)
        if r.status_code != 200:
            print(f"글 조회 실패 {r.status_code}: {r.text[:200]}"); return
        batch = r.json(); posts += batch
        if len(batch) < 50:
            break
        page += 1
    print(f"발행 글 {len(posts)}개 (limit={limit}, dry={dry}, card={allow_card})")

    img_done = card_done = img_skip = img_fail = 0
    exc_done = exc_skip = 0
    for p in posts[:limit]:
        pid = p["id"]
        title = strip_tags((p.get("title") or {}).get("rendered") or "")
        html = (p.get("content") or {}).get("raw") or \
               (p.get("content") or {}).get("rendered", "")

        # ① 대표이미지
        if p.get("featured_media"):
            img_skip += 1
        else:
            url = publisher.first_uploaded_image(html, base)
            if url:
                mid = publisher.find_media_id(wp, url)
                if not mid:
                    img_fail += 1
                    print(f"[{pid}] 미디어 ID 못 찾음: {url[-40:]}")
                elif dry:
                    img_done += 1
                    print(f"[{pid}] 대표이미지 ← 본문 첫 이미지(미디어 {mid}) · {title[:30]}")
                elif publisher.set_featured(wp, pid, mid):
                    img_done += 1
                    print(f"[{pid}] 대표이미지 지정 {mid} · {title[:30]}")
                else:
                    img_fail += 1
            elif allow_card:
                if dry:
                    card_done += 1
                    print(f"[{pid}] 본문 이미지 없음 → 브랜드 카드 생성 예정 · {title[:30]}")
                else:
                    mid = brand_card(pid, title, wp, alt=title)
                    if mid and publisher.set_featured(wp, pid, mid):
                        card_done += 1
                        print(f"[{pid}] 브랜드 카드 {mid} 지정 · {title[:30]}")
                    else:
                        img_fail += 1
            else:
                img_fail += 1

        # ② 요약(카드에 AI 고지문이 노출되던 문제)
        cur = (p.get("excerpt") or {}).get("raw")
        if cur is None:
            cur = strip_tags((p.get("excerpt") or {}).get("rendered") or "")
        if (cur or "").strip():
            exc_skip += 1
        else:
            meta = (p.get("meta") or {}).get("rank_math_description") or ""
            text = meta.strip() or first_sentence(html)
            if not text:
                continue
            if dry:
                exc_done += 1
                print(f"[{pid}] 요약 ← {'메타설명' if meta else '본문 첫 문장'}: {text[:45]}")
                continue
            rr = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}",
                               json={"excerpt": text},
                               headers={**headers, "Content-Type": "application/json"},
                               timeout=30)
            if rr.status_code in (200, 201):
                exc_done += 1
            else:
                print(f"[{pid}] 요약 저장 실패 {rr.status_code}")

    summary = (f"대표이미지: 승격 {img_done}편 · 카드생성 {card_done}편 · "
               f"이미있음 {img_skip}편 · 실패 {img_fail}편 | "
               f"요약: 채움 {exc_done}편 · 이미있음 {exc_skip}편")
    print(summary)
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat and not dry:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": f"🖼 {summary}"}, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
