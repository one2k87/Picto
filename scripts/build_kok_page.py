# -*- coding: utf-8 -*-
"""콕픽 모아보기 페이지(pickdam.com/kok) 생성·갱신 (2026-10-14 신설, famto 10/13 지시 ①).

왜 — 쇼츠 설명란의 URL 은 유튜브 정책상 클릭이 안 된다(캐스토 보고). 그래서 영상에서
     나온 사람이 한 군데로 모일 **짧은 주소 한 장**이 필요하다. 그 페이지가 클릭 허브다.

무엇을 — data/products.json 에서 링크가 살아 있는 품목만 카드로 깔고,
     ①고지 문구를 **맨 앞**에 ②시즌(10~11월 난방·김장) 품목을 위로
     ③subid 는 글별이 아니라 `kokpick-hub` 로 통일해 영상 유입을 따로 센다.

환경: KOK_DRY(true면 HTML 만 출력) · KOK_SLUG(기본 kok)
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from products import card_html
from publisher import _auth_header

SUBID = "kokpick_hub"      # with_subid 가 영숫자·밑줄만 남기므로 처음부터 그 형태로 둔다
MAX_CARDS = 8              # famto 지시: 모바일 첫 화면 중심으로 5~8종. 24장을 깔면 아무도 안 내린다
# 10~11월에 먼저 보여 줄 품목(사용자 결정 2026-10-01: 중가 필요형 우선, 난방·김장)
SEASON = ["문풍지", "창문단열시트", "전기장판", "가습기", "제습기", "김치통", "온풍기"]


def _notice():
    return ('<p style="margin:0 0 18px;padding:12px 14px;background:#fff7ed;'
            'border:1px solid #fed7aa;border-radius:10px;font-size:14px;color:#7c2d12">'
            '이 페이지는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.'
            '</p>')


def build(items):
    live = [p for p in items if (p.get("coupang_url") or "").strip()]
    order = {k: i for i, k in enumerate(SEASON)}
    live.sort(key=lambda p: (order.get(p.get("key", ""), 99), p.get("name", "")))
    today = datetime.date.today()
    head = (
        f'<p style="font-size:15px;color:#475467;margin:0 0 10px">'
        f'영상에서 다룬 제품을 한곳에 모았습니다. 가격·재고는 수시로 바뀌니 '
        f'누르기 전에 상세페이지에서 확인하세요. '
        f'<span style="color:#98a2b3">({today.year}년 {today.month}월 {today.day}일 갱신)</span></p>'
    )
    cards = []
    for p in live:
        if len(cards) >= MAX_CARDS:
            break
        c = card_html(p, SUBID, with_notice=False)
        if c:
            cards.append(c)
    body = _notice() + head + "\n".join(cards)
    body += ('<p style="margin-top:26px;font-size:14px;color:#667085">'
             f'여기 없는 품목({max(0, len(live) - len(cards))}종)과 고르는 기준은 '
             '<a href="https://pickdam.com/">픽담 글 목록</a>에서 품목별 글로 보세요.</p>')
    return body, len(cards)


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    slug = (os.getenv("KOK_SLUG") or "kok").strip()
    dry = (os.getenv("KOK_DRY") or "").lower() == "true"

    raw = json.load(open(os.path.join("data", "products.json"), encoding="utf-8"))
    items = raw if isinstance(raw, list) else (raw.get("products") or raw.get("items") or [])
    body, n = build(items)
    print(f"[kok] 카드 {n}장 · {len(body)}자 · dry_run={dry}")
    if dry:
        print(body[:600])
        return 0

    r = requests.get(f"{base}/wp-json/wp/v2/pages", headers=headers, timeout=30,
                     params={"slug": slug, "status": "publish,draft", "_fields": "id,link"})
    found = r.json() if r.status_code == 200 else []
    payload = {"title": "콕픽 모아보기 — 영상에서 다룬 제품", "slug": slug,
               "content": body, "status": "publish",
               "meta": {"rank_math_title": "콕픽 모아보기 — 영상에서 다룬 제품",
                        "rank_math_description": "콕픽 영상에서 다룬 생활·주방 제품을 한곳에 모았습니다. 품목별 고르는 기준과 구매 링크를 정리했습니다."}}
    if found:
        pid = found[0]["id"]
        res = requests.post(f"{base}/wp-json/wp/v2/pages/{pid}", headers=headers,
                            json=payload, timeout=40)
        action = "갱신"
    else:
        res = requests.post(f"{base}/wp-json/wp/v2/pages", headers=headers,
                            json=payload, timeout=40)
        action = "생성"
    if res.status_code not in (200, 201):
        print(f"[kok] {action} 실패 HTTP {res.status_code}: {res.text[:200]}")
        return 1
    link = res.json().get("link")
    print(f"[kok] {action} 완료 → {link}")
    os.makedirs(os.path.join("dashboard", "data"), exist_ok=True)
    json.dump({"at": datetime.datetime.now().isoformat()[:19], "cards": n, "link": link},
              open(os.path.join("dashboard", "data", "kok_page.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
