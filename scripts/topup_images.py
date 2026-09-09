# -*- coding: utf-8 -*-
"""기발행 글의 이미지를 3장으로 채운다 (2026-09-09 신설).

왜: 예전 파이프라인은 글당 이미지를 **1장만** 넣었다. 거기에 오늘 대표이미지를
    붙이면서 같은 그림이 위아래로 두 번 나왔고, 글이 통째로 단조로워 보였다
    (사용자 지적 → single 템플릿의 대표이미지 블록 제거로 중복은 해소).
    남은 문제는 "본문에 그림이 한 장뿐"이라 밋밋하다는 것이라, 모자란 만큼 채운다.

규칙:
  - 이미 3장 이상이면 건드리지 않는다(재실행 안전).
  - 기존 이미지와 **다른 스타일·다른 장면**을 고른다(같은 걸 또 넣으면 의미가 없다).
  - 소제목(H2) 뒤에 흩어 넣는다. 한 자리에 몰면 그것대로 단조롭다.
  - 첫 이미지는 대표이미지로 승격돼 있으므로 **건드리지 않는다**.

환경: TOPUP_DRY(기본 true) / TOPUP_LIMIT(기본 100) / TOPUP_TARGET(기본 3)
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import images
from publisher import _auth_header, upload_media
from reimage_posts import NOTES, strip_html

MARK = "<!--imgtop-->"          # 이 스크립트가 넣은 이미지 표시(재실행 시 참고)
STYLE_ORDER = ["object", "diagram", "photo", "illust"]


def existing_count(html):
    """본문에 이미 들어 있는 이미지 수."""
    return len(re.findall(r"<figure\b", html or "")) or len(re.findall(r"<img\b", html or ""))


def existing_styles(html):
    """이미 쓴 스타일 추정 — 캡션 문구로 되짚는다(정확하지 않아도 중복만 피하면 된다)."""
    used = set()
    for style, note in NOTES.items():
        if note and note in (html or ""):
            used.add(style)
    return used


def llm_scenes(title, text, avoid, n, key, model):
    """부족한 장수만큼 (스타일, 장면묘사)를 받는다. 실패하면 휴리스틱 폴백."""
    prompt = (
        "당신은 블로그 본문 이미지 기획자다. 한 글에 들어갈 이미지 여러 장을 "
        "**서로 다른 각도**로 기획한다.\n"
        f"제목: {title}\n본문 일부: {text[:900]}\n"
        f"이미 쓴 스타일(피할 것): {', '.join(avoid) or '없음'}\n"
        f"{n}장을 기획하라. 규칙:\n"
        "- 각 장의 스타일은 서로 다르게: object(제품 정물 클로즈업) / "
        "diagram(구조·비교·조건 분기 도해) / photo(실제 사용하는 생활 장면) / illust(비유·감성).\n"
        "- 장면 묘사에는 이 글의 핵심 소재 명칭을 그대로 넣고, '무엇이·어디서·어떤 상태로'를 담아 "
        "한국어 1~2문장. 글과 무관한 배경·인물·풍경 금지.\n"
        "- 이미지 안에 글자·숫자·가격·간판·라벨을 그리라는 묘사 금지(글자 깨짐 방지).\n"
        '순수 JSON 배열만 출력: [{"style":"diagram","desc":"..."}, ...]')
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.7}},
                          timeout=60)
        t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        t = re.sub(r"^```(json)?\s*|\s*```$", "", t.strip(), flags=re.M)
        out = []
        for ms, md in re.findall(r'"style"\s*:\s*"(\w+)"[^}]*?"desc"\s*:\s*"([^"\n]{5,300})', t):
            if ms in images.STYLE_PRESETS:
                out.append((ms, md.strip()))
        if out:
            return out[:n]
    except Exception as e:
        print(f"  [llm] 장면 기획 실패(폴백): {e}")
    # 폴백: 안 쓴 스타일을 순서대로
    left = [s for s in STYLE_ORDER if s not in avoid] or STYLE_ORDER
    tail = {"object": "제품 정물 클로즈업", "diagram": "조건별 선택 기준을 정리한 도해",
            "photo": "집에서 실제로 쓰는 생활 장면", "illust": "핵심을 비유로 표현한 일러스트"}
    return [(s, f"{title[:40]} — {tail[s]}") for s in left[:n]]


def insert_after_h2(html, fig, nth):
    """nth번째 소제목 뒤에 넣는다. 소제목이 모자라면 맨 뒤."""
    spots = [m.end() for m in re.finditer(r"</h2>", html)]
    if not spots:
        return html + fig
    at = spots[min(nth, len(spots) - 1)]
    return html[:at] + fig + html[at:]


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    llm = cfg.get("llm") or {}
    key = llm.get("api_key", "")
    model = llm.get("model") or "gemini-2.5-flash"
    img_key = (cfg.get("images") or {}).get("api_key") or key
    dry = (os.getenv("TOPUP_DRY") or "true").lower() == "true"
    limit = int(os.getenv("TOPUP_LIMIT") or "100")
    target = int(os.getenv("TOPUP_TARGET") or "3")

    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit"}, timeout=30)
        if r.status_code != 200:
            print(f"글 조회 실패 {r.status_code}"); return
        b = r.json(); posts += b
        if len(b) < 50:
            break
        page += 1
    print(f"발행 글 {len(posts)}개 (target={target}장, dry={dry}, limit={limit})")

    done = skipped = added = failed = 0
    for p in posts:
        if done >= limit:
            break
        pid = p["id"]
        title = strip_html((p.get("title") or {}).get("rendered") or "")
        html = (p.get("content") or {}).get("raw") or ""
        have = existing_count(html)
        need = target - have
        if need <= 0:
            skipped += 1
            continue
        avoid = existing_styles(html)
        print(f"\n[{pid}] {title[:38]} — 현재 {have}장, {need}장 추가")
        scenes = llm_scenes(title, strip_html(html), avoid, need, key, model)
        for i, (style, desc) in enumerate(scenes):
            print(f"  + {style} / {desc[:56]}")
            if dry:
                continue
            path = images.generate_image(f"{style}|{desc}",
                                         {"provider": "gemini", "api_key": img_key},
                                         "output/topup", f"{pid}_{i}", category="")
            if not path:
                print(f"  ✗ 생성 실패: {getattr(images,'LAST_ERR','')[:90]}")
                failed += 1; time.sleep(6); continue
            url = upload_media(path, wp, alt=desc)
            if not url:
                print("  ✗ 업로드 실패"); failed += 1; time.sleep(6); continue
            fig = images.figure_html(url, desc, NOTES.get(style)) + MARK
            html = insert_after_h2(html, fig, have + i)   # 첫 이미지 자리는 건드리지 않는다
            added += 1
            time.sleep(3)
        if dry:
            done += 1; continue
        rr = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}",
                           json={"content": html},
                           headers={**headers, "Content-Type": "application/json"}, timeout=60)
        if rr.status_code in (200, 201):
            done += 1
        else:
            failed += 1
            print(f"  ✗ 저장 실패 {rr.status_code}: {rr.text[:150]}")

    summary = (f"이미지 보강: 처리 {done}편 · 추가 {added}장 · "
               f"이미 충분 {skipped}편 · 실패 {failed}")
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
