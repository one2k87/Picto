"""reimage_posts.py — 기발행 글 이미지를 4스타일 시스템(2026-09-04)으로 전량 교체.

동작: 발행 글을 wp-json으로 순회 → LLM이 글에 어울리는 스타일(photo/object/diagram/illust)과
장면 묘사를 선택 → 새 이미지를 생성·미디어 업로드 → 본문 첫 이미지(figure/자리표시)를 교체.
이미 교체된 글은 <!--imgv2--> 마커로 건너뛴다(재실행 안전).

환경: GitHub Actions에서 build_config.py로 config.json 생성 후 실행.
  REIMAGE_LIMIT: 이번 실행에서 처리할 최대 글 수(기본 100)
  REIMAGE_DRY:   "true"면 실제 게시 수정 없이 계획만 출력
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

MARK = "<!--imgv2-->"
NOTES = {"diagram": "이해를 돕기 위한 도해입니다",
         "illust": "내용을 표현한 일러스트입니다",
         "photo": "AI로 연출한 참고 이미지입니다",
         "object": "AI로 연출한 참고 이미지입니다"}
# 본문에서 교체할 기존 이미지: 우리가 심은 figure(스타일 인라인) 또는 이미지 자리표시 div
RE_FIGURE = re.compile(r'<figure style="margin:22px 0;[^>]*>.*?</figure>', re.S)
RE_SLOT = re.compile(r'<div[^>]*>\s*📷 이미지 삽입:.*?</div>', re.S)



# 2026-11-20: 한 글에 3장이 들어 있는데 매번 첫 장만 바꾸고 끝났다(count=1).
# 그래서 11/20 시험 실행에서 #800 은 1/3 장만 교체됐다. 아직 안 바꾼 블록을 찾아
# 글당 REIMAGE_PER_POST(기본 3)장까지 이어서 교체한다.
# 쿠팡 파트너스 배너(image/affiliate/banner/…)는 상품 사진이므로 절대 건드리지 않는다.
_TARGET_RX = [
    RE_FIGURE,
    RE_SLOT,
    re.compile(r"<figure\b.*?</figure>", re.S),
    re.compile(r"<img\b[^>]*>"),
]

def next_target(html):
    """아직 교체하지 않은 첫 이미지 블록의 (시작, 끝, 원래 묘사)."""
    for rx in _TARGET_RX:
        for m in rx.finditer(html):
            blk = m.group(0)
            if "image/affiliate" in blk:        # 쿠팡 제공 상품 배너는 그대로 둔다
                continue
            if html[m.end():m.end() + len(MARK)] == MARK:
                continue                        # 이번 실행에서 이미 바꾼 자리
            alt = re.search(r'alt="([^"]*)"', blk)
            cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", blk, re.S)
            d = (alt.group(1) if alt else "") or (strip_html(cap.group(1)) if cap else "")
            return m.start(), m.end(), d.strip()
    return None

def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def llm_pick(title, text, key, model):
    """글 내용 → (스타일, 장면 묘사). 실패 시 휴리스틱 폴백.
    v2(9/5): 글의 '핵심 소재'를 먼저 찾게 하고 묘사에 강제 포함 — 무관 이미지 재발 방지."""
    prompt = (
        "당신은 블로그 대표 이미지 기획자다. 이미지만 봐도 무슨 글인지 알 수 있어야 한다.\n"
        f"제목: {title}\n본문 일부: {text[:900]}\n"
        "1) 이 글이 다루는 '구체적 핵심 소재'(특정 제품·도구·작업·공간·재료의 명칭)를 본문에서 찾아라.\n"
        "2) 스타일 1개 선택 — photo(실사: 그 소재를 다루는 생활 장면·작업 모습), object(정물: 그 소재 클로즈업), "
        "diagram(도해: 그 소재의 구조·과정·비교), illust(일러스트: 감성·비유).\n"
        "3) 장면 묘사 규칙: 반드시 핵심 소재 명칭을 그대로 포함하고, '무엇이·어디서·어떤 상태로'를 담아 "
        "한국어 1~2문장. 글과 무관한 배경·인물·풍경 금지. "
        "이미지 안에 글자·숫자·가격 표기·간판·라벨 문구를 그리라는 묘사는 금지 — 글자 없이 사물과 장면만으로 전달.\n"
        '순수 JSON만 출력: {"style":"photo","desc":"...","subject":"핵심 소재 명사"}')
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": 300, "temperature": 0.6}},
                          timeout=60)
        t = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        t = re.sub(r"^```(json)?\s*|\s*```$", "", t, flags=re.M).strip()
        # 정규식 추출 우선 — LLM이 JSON 규격(이스케이프·줄바꿈)을 자주 어겨 json.loads가 깨진다(9/4 실측)
        ms = re.search(r'"style"\s*:\s*"(\w+)"', t)
        md = re.search(r'"desc"\s*:\s*"([^"\n]{5,300})', t)
        mj = re.search(r'"subject"\s*:\s*"([^"\n]{1,60})', t)
        style = ms.group(1) if (ms and ms.group(1) in images.STYLE_PRESETS) else None
        desc = md.group(1).strip() if md else ""
        subj = mj.group(1).strip() if mj else ""
        if style and desc:
            if subj and subj not in desc:      # 핵심 소재가 빠졌으면 앞에 박는다
                desc = f"{subj} — {desc}"
            return style, desc
    except Exception as e:
        print(f"  [llm] 스타일 선택 실패(폴백): {e}")
    return images.pick_style(title), title


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {})
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    # 2026-11-20: 이미지 생성에 무료 LLM 키를 쓰던 것을 유료 키 우선으로 바꾼다.
    # 무료 등급 키는 이미지 요청에서 429 로 막혀 조용히 코드 썸네일로 떨어진다(11/9 실측).
    # 그 결과가 글자만 남은 보라·녹색 카드 10장이었다(11/20 전수 확인).
    llm_key = ((cfg.get("llm") or {}).get("api_key_paid")
               or (cfg.get("llm") or {}).get("api_key", ""))
    llm_model = (cfg.get("llm") or {}).get("model") or "gemini-2.5-flash"
    img_key = (cfg.get("images") or {}).get("api_key") or llm_key
    limit = int(os.getenv("REIMAGE_LIMIT") or "100")
    per_post = int(os.getenv("REIMAGE_PER_POST") or "3")   # 글당 교체할 최대 장수
    dry = (os.getenv("REIMAGE_DRY") or "").lower() == "true"
    force = (os.getenv("REIMAGE_FORCE") or "").lower() == "true"   # imgv2 마커 무시하고 재교체

    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts",
                         headers=headers, params={"per_page": 50, "page": page,
                                                  "status": "publish", "context": "edit"},
                         timeout=30)
        if r.status_code != 200:
            break
        batch = r.json()
        posts += batch
        if len(batch) < 50:
            break
        page += 1
    # 특정 글만 정밀 교체 — 전수 재생성은 비용·시간이 크고, 사고 수습은 보통 몇 편뿐이다.
    # (2026-11-13 신설: 깨진 한글 이미지 3편 9장을 골라 교체하려고 만들었다.
    #  backfill_product_links 의 BACKFILL_IDS 와 같은 방식이다.)
    only = {x.strip() for x in (os.getenv("REIMAGE_IDS") or "").split(",") if x.strip()}
    if only:
        posts = [x for x in posts if str(x.get("id")) in only]
        missing = only - {str(x.get("id")) for x in posts}
        print(f"[ids] 지정 {len(only)}건 → 대상 {len(posts)}건"
              + (f" · 못 찾음 {sorted(missing)}" if missing else ""))
    print(f"발행 글 {len(posts)}개 발견 (limit={limit}, dry={dry})")

    done = skipped = failed = 0
    for p in posts:
        if done >= limit:
            break
        pid = p["id"]
        title = strip_html(p["title"].get("rendered") or p["title"].get("raw", ""))
        content = p["content"].get("raw") or p["content"].get("rendered", "")
        if MARK in content:
            if not force:
                skipped += 1
                continue
            content = content.replace(MARK, "")   # 강제 모드: 마커 제거 후 기존 v2 figure를 다시 교체
        print(f"\n[{pid}] {title[:40]}")
        style, desc = llm_pick(title, strip_html(content), llm_key, llm_model)
        print(f"  스타일={style} / 묘사={desc[:60]}")
        if dry:
            done += 1
            continue
        # ⚠️ 2026-11-13: 여기는 provider 가 "gemini" 로 **하드코딩**돼 있었다. 그래서
        #    11/10 에 세운 무료 경로(Pexels→CF FLUX→코드썸네일)를 전혀 타지 않고
        #    무료 Gemini 만 때리다 429 로 3건 전부 실패했다(실측 로그).
        #    본편과 같은 free 경로를 쓰고, CF 키와 검수용 키를 함께 넘긴다.
        imgcfg = dict((cfg.get("images") or {}))
        imgcfg["provider"] = imgcfg.get("provider") or "free"
        imgcfg["api_key"] = img_key
        # 검수는 유료 키 우선 — 무료 키면 429 로 검수가 조용히 죽는다(2026-11-13 실측)
        imgcfg["check_api_key"] = ((cfg.get("llm") or {}).get("api_key_paid")
                                   or (cfg.get("images") or {}).get("api_key") or img_key)
        # 2026-11-20: 글 하나에 3장이 들어 있으므로 글당 여러 장을 이어서 교체한다.
        # 원래 묘사(alt/figcaption)가 남아 있으면 그 장면을 그대로 다시 그린다.
        made = 0
        for _slot in range(per_post):
            tgt = next_target(content)
            if tgt is None and _slot:
                break                                   # 더 바꿀 자리가 없다
            d = (tgt[2] if (tgt and tgt[2]) else desc)
            path = images.generate_image(f"{style}|{d}", imgcfg,
                                         "output/reimg", f"{pid}_{_slot}", category="")
            if not path:
                print(f"  ✗ {_slot+1}장째 생성 실패: {images.LAST_ERR[:90]}")
                time.sleep(8); break
            url = upload_media(path, wp, alt=d)
            if not url:
                print(f"  ✗ {_slot+1}장째 업로드 실패"); time.sleep(8); break
            fig = images.figure_html(url, d, NOTES.get(style)) + MARK
            if tgt:
                content = content[:tgt[0]] + fig + content[tgt[1]:]
            elif "</h2>" in content:                    # 이미지가 아예 없던 글
                content = content.replace("</h2>", "</h2>" + fig, 1)
            else:
                content = fig + content
            made += 1
            print(f"  · {_slot+1}장째 교체 — {d[:44]}")
            time.sleep(8)   # 이미지 모델 분당 한도 보호
        if not made:
            failed += 1
            continue
        r = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}",
                          headers={**headers, "Content-Type": "application/json"},
                          json={"content": content}, timeout=60)
        if r.status_code in (200, 201):
            print(f"  ✓ {made}장 교체 완료"); done += 1
        else:
            print(f"  ✗ 글 수정 실패 {r.status_code}: {r.text[:120]}"); failed += 1

    summary = f"이미지 재생성: 성공 {done} · 스킵(기교체) {skipped} · 실패 {failed} / 전체 {len(posts)}"
    print("\n" + summary)
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": f"🖼 {wp['site_url']} {summary}"}, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
