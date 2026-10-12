# -*- coding: utf-8 -*-
"""기존 글 보강 (2026-10-12 신설).

왜 만들었나 — 40편을 색인 27 / 미색인 13 으로 갈라 전수 비교했더니, 분량·H2·
내부링크는 **차이가 없었다**(3,593자 vs 3,685자 / 4.7 vs 5.2 / 6.2 vs 6.2).
갈린 것은 두 가지였다: **외부 1차 출처 인용 0.9 vs 0.2**, **목록 4.5 vs 1.6**.
구글 서치 센트럴 커뮤니티 가이드도 'Discovered - not indexed' 는 그 페이지의
문제가 아니라 **기존 콘텐츠가 더 크롤할 이유를 주지 못하는 것**이라고 말한다.
그래서 새 글을 늘리는 대신 있는 글을 끌어올린다.

무엇을 하나
  · 보강 대상 선정: 미색인 → 얇은 글 → 외부 인용 0 순서
  · 실제 검색으로 외부 출처를 찾아 **HTTP 200 으로 살아 있는 것만** 쓴다
  · 구조(목록·조건 분기·실수)와 수치를 보강한다
  · 상품 카드 마커·고지 문구·이미지는 그대로 보존한다(검증 실패 시 반영하지 않음)

환경: ENRICH_N(기본 2) · ENRICH_DRY(true면 계획만) · ENRICH_IDS(쉼표로 지정)
결과: dashboard/data/enrich_log.json
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import quality
from links import find_reference_links
from llm import chat
from publisher import _auth_header, update_post_content

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"}
DATA = os.path.join("dashboard", "data")
MARK = "<!--enriched:"
NOTICE = "쿠팡 파트너스 활동의 일환"


def _text(html):
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", html or ""))


def _profile(html):
    return {
        "chars": len(_text(html)),
        "h2": html.count("<h2"),
        "lists": html.count("<ul") + html.count("<ol"),
        "external": len([u for u in re.findall(r'href="(https?://[^"]+)"', html)
                         if "pickdam.com" not in u and "coupang" not in u]),
        "picklink": html.count("<!--picklink-->"),
        "img": html.count("<img"),
    }


def _alive(url):
    """실제로 살아 있는 주소만 인용한다. 죽은 링크는 보강이 아니라 흠이다."""
    try:
        r = requests.head(url, headers=UA, timeout=12, allow_redirects=True)
        if r.status_code >= 400:
            r = requests.get(url, headers=UA, timeout=15, stream=True)
        return r.status_code < 400
    except Exception:
        return False


def pick(posts, index_state, want):
    """미색인 → 외부 인용 0 → 얇은 순서. 이미 보강한 글은 건너뛴다."""
    rows = []
    for p in posts:
        raw = (p.get("content") or {}).get("raw") or ""
        if MARK in raw:
            continue
        pf = _profile(raw)
        st = index_state.get(p["link"].rstrip("/"), "")
        score = 0
        if st and st != "PASS":
            score += 100
        if pf["external"] == 0:
            score += 30
        if pf["lists"] < 3:
            score += 20
        if pf["chars"] < 2500:
            score += 25
        rows.append((score, p, pf, st))
    rows.sort(key=lambda x: (-x[0], x[2]["chars"]))
    return [r for r in rows if r[0] > 0][:want]


def enrich(p, pf, cfg, dry):
    title = re.sub("<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))
    raw = (p.get("content") or {}).get("raw") or ""
    refs = [r for r in find_reference_links(title, max_results=4) if _alive(r["url"])][:2]
    ref_text = ("\n".join(f"- {r['title'][:60]} : {r['url']}" for r in refs)
                if refs else "(검색으로 쓸 만한 출처를 못 찾았습니다 — 외부 링크는 넣지 마세요)")
    prompt = (
        "아래 한국어 블로그 글 HTML을 **보강**하세요. 새로 쓰는 게 아니라 있는 글을 끌어올리는 작업입니다.\n\n"
        "[반드시 지킬 것 — 어기면 반영하지 않습니다]\n"
        "- 기존 <img> 태그, <!--picklink--> … <!--/picklink--> 블록, 쿠팡 파트너스 고지 문단은 "
        "위치와 내용 그대로 둘 것. 지우거나 옮기지 마세요.\n"
        "- 기존 소제목(h2/h3)은 유지하고, 필요하면 추가만 하세요.\n"
        "- 분량은 줄이지 말 것.\n\n"
        "[보강할 것]\n"
        f"1. 아래 출처를 본문 안 적절한 자리에 <a href=\"...\" target=\"_blank\" rel=\"noopener\">제목</a> 으로 "
        f"인용하고, 그 출처가 말하는 내용을 한두 문장으로 요약해 붙이세요. 없는 주소를 지어내지 마세요.\n{ref_text}\n"
        "2. 비교·기준·체크리스트를 <ul> 또는 <table> 로 최소 2개 추가하세요(줄글을 목록으로 바꿔도 됩니다).\n"
        "3. 조건 분기를 최소 2개 넣으세요 (예: '벽이 석고보드라면 A, 콘크리트라면 B').\n"
        "4. 흔한 실수 또는 사기 전 후회 포인트를 한 소제목으로 넣으세요.\n"
        "5. 규격·가격대·시간·주기 같은 실측형 수치를 4개 이상 유지하거나 늘리세요. 모르면 범위로 쓰세요.\n"
        "6. 다음 상투 표현 금지: 알아보겠습니다, 살펴보겠습니다, 이번 글에서는, 도움이 되셨기를.\n\n"
        "[출력] 순수 HTML 본문만. 코드블록·설명 금지.\n\n[원문]\n" + raw)
    if dry:
        return None, f"출처 {len(refs)}건 · (dry_run)"
    neo = chat(prompt, cfg.get("llm", {}), max_tokens=16000, temperature=0.6)
    neo = re.sub(r"^```html?\s*|\s*```$", "", (neo or "").strip())
    if not (neo and neo.lstrip().startswith("<")):
        return None, "응답이 HTML 이 아님"
    quality.autofix({"html": neo})
    np = _profile(neo)
    # 보존 검증 — 하나라도 깨지면 반영하지 않는다
    if np["picklink"] != pf["picklink"]:
        return None, f"상품 카드 마커 손상({pf['picklink']}→{np['picklink']})"
    if (NOTICE in raw) and (NOTICE not in neo):
        return None, "고지 문구 소실"
    if np["img"] < pf["img"]:
        return None, f"이미지 소실({pf['img']}→{np['img']})"
    if np["chars"] < pf["chars"]:
        return None, f"분량 감소({pf['chars']}→{np['chars']})"
    if np["external"] <= pf["external"] and refs:
        return None, "외부 인용이 늘지 않음"
    for r in refs:
        if r["url"] not in neo:
            return None, "제시한 출처가 본문에 없음"
    stamp = MARK + datetime.date.today().isoformat() + "-->"
    return neo + "\n" + stamp, (f"{pf['chars']}→{np['chars']}자 · 목록 {pf['lists']}→{np['lists']} · "
                                f"외부인용 {pf['external']}→{np['external']}")


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    dry = (os.getenv("ENRICH_DRY") or "").lower() == "true"
    want = int(os.getenv("ENRICH_N") or "2")
    only = [x.strip() for x in (os.getenv("ENRICH_IDS") or "").split(",") if x.strip()]

    try:
        ix = json.load(open(os.path.join(DATA, "index_status.json"), encoding="utf-8"))
        state = {r["url"].rstrip("/"): r.get("verdict") for r in ix.get("results", [])}
    except Exception:
        state = {}

    posts, page = [], 1
    while page <= 3:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers, timeout=60,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit", "_fields": "id,link,title,content"})
        if r.status_code != 200:
            print(f"글 목록 조회 실패 HTTP {r.status_code}")
            break
        chunk = r.json()
        posts += chunk
        if len(chunk) < 50:
            break
        page += 1
    print(f"[enrich] 발행 {len(posts)}편 · 목표 {want}편 · dry_run={dry}")

    if only:
        sel = [(0, p, _profile((p.get("content") or {}).get("raw") or ""), "")
               for p in posts if str(p["id"]) in only]
    else:
        sel = pick(posts, state, want)
    if not sel:
        print("보강 대상 없음")
        return 0

    log, done, fail = [], 0, 0
    for score, p, pf, st in sel:
        t = re.sub("<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))[:36]
        print(f"\n· #{p['id']} {t} (점수 {score} · {st or '색인상태 미상'} · {pf['chars']}자 "
              f"목록 {pf['lists']} 외부 {pf['external']})")
        neo, note = enrich(p, pf, cfg, dry)
        if neo and update_post_content(wp, p["id"], neo):
            print(f"    보강 완료 — {note}")
            log.append({"id": p["id"], "title": t, "ok": True, "note": note})
            done += 1
        else:
            print(f"    보강 안 함 — {note}")
            log.append({"id": p["id"], "title": t, "ok": False, "note": note})
            if not dry:
                fail += 1

    os.makedirs(DATA, exist_ok=True)
    out = {"at": datetime.datetime.now().isoformat()[:19], "dry": dry,
           "done": done, "fail": fail, "rows": log}
    json.dump(out, open(os.path.join(DATA, "enrich_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[enrich] 보강 {done}편 · 실패 {fail}편")
    return 0


if __name__ == "__main__":
    sys.exit(main())
