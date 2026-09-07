# -*- coding: utf-8 -*-
"""기발행 글에서 '남의 사이트' 링크를 걷어낸다 (2026-09-07 신설).

배경(실측):
  픽토 저장소가 스크립토에서 포크될 때 history.json에 원더랜드 글 914편이 딸려왔고,
  내부링크 생성기가 그걸 '내 과거 글'로 착각해 픽담 글 본문에서 wontheland.com으로
  링크를 걸었다. 픽담이 모은 방문자를 남의 사이트로 보내고 있었다.
  또 픽담이 구 도메인(one2k.mycafe24.com)으로 발행되던 시기의 링크도 남아 있다.

처리 규칙:
  - 구 도메인(one2k.mycafe24.com) → pickdam.com 으로 **주소만 교체**. 같은 사이트다.
  - 원더랜드(wontheland.com) → 링크를 **풀어낸다**(앵커 제거, 글자는 남김).
    지우지 않고 푸는 이유: 문장 흐름이 깨지지 않고, 잘못 지워 본문이 상하는 일이 없다.
  - 링크가 문단 전체를 차지하는 '함께 보면 좋은 글' 박스는 통째로 제거한다.

환경: CLEAN_LIMIT(기본 100) / CLEAN_DRY(true면 계획만)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from publisher import _auth_header, update_post_content

OLD_HOST = "one2k.mycafe24.com"
FOREIGN_HOSTS = ["wontheland.com"]


def strip_tags(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()


def clean(html, site_host):
    """(정리된 html, 변경내역) 반환."""
    log = {"구도메인_교체": 0, "외부링크_해제": 0, "관련글박스_제거": 0}

    # ① 구 도메인 → 현재 도메인 (같은 사이트이므로 주소만 교체)
    n = len(re.findall(OLD_HOST, html))
    if n:
        html = html.replace("https://" + OLD_HOST, "https://" + site_host)
        html = html.replace("http://" + OLD_HOST, "https://" + site_host)
        html = html.replace(OLD_HOST, site_host)
        log["구도메인_교체"] = n

    for host in FOREIGN_HOSTS:
        # ② 남의 사이트 링크만 든 '관련글' 박스는 통째로 제거
        box = re.compile(
            r"<(div|aside|p)[^>]*>(?:(?!</\1>).)*?" + re.escape(host) + r"(?:(?!</\1>).)*?</\1>",
            re.S | re.I)
        while True:
            m = box.search(html)
            if not m:
                break
            seg = m.group(0)
            # 통째로 지워도 되는 건 '링크 상자'뿐이다. 문장 속 링크를 지우면 본문이 상한다.
            # 길이 기준은 한국어에서 너무 헐거웠다(실측: 멀쩡한 문장이 27자로 통과했다).
            # 진짜 판별 신호는 '문장인가'다 — 링크 상자에는 문장이 없고 라벨만 있다.
            # 조건 ①링크가 전부 남의 사이트 ②앵커 글자를 뺀 나머지가 짧고(12자 이하)
            #      ③마침표·물음표·느낌표나 종결어미가 없다(있으면 문장이므로 건드리지 않는다)
            hrefs = re.findall(r'href=["\']([^"\']+)', seg)
            anchor_text = " ".join(re.findall(r"<a\b[^>]*>(.*?)</a>", seg, re.S | re.I))
            rest = strip_tags(seg).replace(strip_tags(anchor_text), "").strip()
            looks_like_sentence = bool(re.search(r"[.!?]|다$|요$|니다|습니다", rest))
            if (hrefs and all(host in h for h in hrefs)
                    and len(rest) <= 12 and not looks_like_sentence):
                html = html[:m.start()] + html[m.end():]
                log["관련글박스_제거"] += 1
            else:
                break

        # ③ 남은 개별 앵커는 '푼다' — 글자는 남기고 링크만 제거
        anchor = re.compile(r'<a\b[^>]*href=["\'][^"\']*' + re.escape(host) + r'[^"\']*["\'][^>]*>(.*?)</a>',
                            re.S | re.I)
        html, cnt = anchor.subn(lambda m: m.group(1), html)
        log["외부링크_해제"] += cnt

    return html, log


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    base = wp["site_url"].rstrip("/")
    site_host = re.sub(r"^https?://", "", base).split("/")[0]
    headers = _auth_header(wp["username"], wp["app_password"])
    limit = int(os.getenv("CLEAN_LIMIT") or "100")
    dry = (os.getenv("CLEAN_DRY") or "").lower() == "true"

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
    print(f"발행 글 {len(posts)}개 · 기준 도메인 {site_host} (dry={dry})")

    changed, total = 0, {"구도메인_교체": 0, "외부링크_해제": 0, "관련글박스_제거": 0}
    for p in posts:
        if changed >= limit:
            break
        pid = p["id"]
        title = strip_tags((p.get("title") or {}).get("rendered") or "")
        content = (p.get("content") or {}).get("raw") or (p.get("content") or {}).get("rendered", "")
        neo, log = clean(content, site_host)
        if neo == content:
            continue
        for k in total:
            total[k] += log[k]
        print(f"[{pid}] {title[:38]} — " + " · ".join(f"{k} {v}" for k, v in log.items() if v))
        if dry:
            changed += 1
            continue
        if update_post_content(wp, pid, neo):
            changed += 1
        else:
            print(f"  ✗ 업로드 실패 {pid}")

    summary = (f"외부 링크 정리: {changed}편 수정 — 구도메인 교체 {total['구도메인_교체']}"
               f" · 링크 해제 {total['외부링크_해제']} · 관련글박스 제거 {total['관련글박스_제거']}")
    print(summary)
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat and not dry and changed:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": f"🧹 {summary}"}, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
