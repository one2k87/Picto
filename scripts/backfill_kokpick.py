# -*- coding: utf-8 -*-
"""기발행 글에 콕픽 구조화 블록을 소급 삽입한다 (2026-09-09 신설).

왜 지금인가:
  브리프 6-C 회신(2026-09-08)에서 "기존 글은 쿠팡 딥링크가 대장에 채워지는 시점에
  소급 워크플로로 한 번에 넣는다"고 약속했다. 9/9에 딥링크 10/10이 채워졌으므로
  그 조건이 충족됐다. 실측: 공개 15편 중 블록이 있는 건 3편뿐(9/8 이후 발행분).

무엇을 넣는가:
  `kokpick.SCHEMA` 그대로. 단 **본문에 실제로 쓰여 있는 내용만** 채운다.
  - product·price_band·coupang_url → 상품 대장(products.json) 우선(사람이 확인한 값)
  - condition_branch·size_install·maintenance·cautions → 그 글 본문에서만 추출(LLM)
  - alt_uses → **항상 빈 배열**. 소급 대상 글에는 '용도 외 활용' 근거가 없다.
    (브리프 안전 규칙: 근거 없는 활용법은 캐스토가 영상으로 만들면 안 된다)

보고서: 실행 결과를 `dashboard/data/kokpick_backfill.json`에 남긴다.
  (액션 로그는 압축 아티팩트라 세션에서 되읽기 어렵다 — 결과를 레포에 남겨야 검증이 된다)

재실행 안전: 이미 블록 + 메타가 둘 다 있으면 건너뛴다.
환경: KOKPICK_DRY(기본 true) / KOKPICK_LIMIT(기본 100) / KOKPICK_FORCE(true면 기존 블록도 재작성)
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import kokpick
import llm
import products
from publisher import _auth_header


def strip_tags(h):
    h = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    h = kokpick.strip_block(h)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


PROMPT = """당신은 블로그 글에서 **글에 이미 쓰여 있는 사실만** 뽑아 정리하는 추출기다.
지어내지 마라. 글에 없으면 빈 값으로 두어라. 이 데이터는 유튜브 영상 대본의 근거가 되므로
없는 사실이 들어가면 시청자에게 잘못된 정보가 나간다.

제목: {title}
본문:
{body}

아래 JSON만 출력하라(설명·코드펜스 금지):
{{"price_band":"", "condition_branch":[], "size_install":"",
  "maintenance":{{"cycle":"","cost_per_year":"","consumable_url":""}},
  "cautions":[]}}

규칙:
- price_band: 글에 가격대가 나오면 "20만원대"처럼. 없으면 "".
- condition_branch: "이런 조건이면 A, 저런 조건이면 B" 식의 **조건부 판단**만. 최대 4개. 각 40자 이내.
- size_install: 설치 규격·공간 조건(치수·여유 공간·배관 등). 글에 없으면 "".
- maintenance.cycle: 소모품·점검 주기(예: "필터 6개월"). cost_per_year: 연 유지비. 둘 다 글에 있을 때만.
- cautions: 고장·사고·후회로 이어지는 **주의점**만. 최대 4개. 각 40자 이내.
- 모든 문자열에서 연속 하이픈(--)을 쓰지 마라."""


LAST_ERR = ""


def _loads_lenient(t):
    """잘린 JSON도 살린다.

    실측(2026-09-09): gemini-2.5-flash는 생각 토큰을 함께 소모해 1500 토큰에서
    응답이 **중간에 끊겼다**. 여는 괄호는 있는데 닫는 괄호가 없어 파서가 통째로 버렸고,
    멀쩡히 뽑힌 앞부분(조건분기 2~3개)까지 같이 날아갔다. 그래서 토큰을 4000으로 올리되,
    그래도 끊기면 마지막 완결 항목까지만 살려 닫는다.
    """
    t = t.strip()
    i = t.find("{")
    if i < 0:
        return None
    t = t[i:]
    try:
        return json.loads(t[:t.rfind("}") + 1]) if t.rfind("}") > 0 else json.loads(t)
    except Exception:
        pass
    # 꼬리를 한 글자씩 줄이며 열린 괄호를 닫아 본다(최대 400회)
    for cut in range(len(t), max(len(t) - 4000, 1), -1):
        frag = t[:cut].rstrip().rstrip(",")
        close = ""
        depth = []
        instr = esc = False
        for ch in frag:
            if esc:
                esc = False; continue
            if ch == "\\" and instr:
                esc = True; continue
            if ch == '"':
                instr = not instr; continue
            if instr:
                continue
            if ch in "{[":
                depth.append(ch)
            elif ch in "}]" and depth:
                depth.pop()
        if instr:
            continue
        for ch in reversed(depth):
            close += "}" if ch == "{" else "]"
        try:
            return json.loads(frag + close)
        except Exception:
            continue
    return None


def extract(title, body, llm_cfg):
    """본문에서 근거 필드를 뽑는다. 실패하면 빈 dict(= 캐스토가 폴백).

    주의(2026-09-09 실측): 처음엔 Gemini REST를 직접 때렸는데 12편 전부 빈 값이 나왔다.
    이 레포에는 제공자 분기·일일한도 폴백·재시도를 담은 `llm.chat()`이 이미 있고,
    설정의 provider가 gemini가 아닐 수도 있다. 직접 호출은 그걸 전부 우회해
    **조용히 실패**한다. 그래서 공용 경로만 쓴다.
    """
    global LAST_ERR
    LAST_ERR = ""
    try:
        t = llm.chat(PROMPT.format(title=title, body=body[:6000]),
                     llm_cfg, max_tokens=4000, temperature=0.1)
        t = re.sub(r"^```(json)?\s*|\s*```$", "", (t or "").strip(), flags=re.M)
        d = _loads_lenient(t)
        if not isinstance(d, dict):
            LAST_ERR = "JSON 파싱 실패: " + (t or "")[:100]
            return {}
        return d
    except Exception as e:
        LAST_ERR = f"{type(e).__name__}: {e}"[:160]
        print(f"  [llm] 추출 실패(빈 블록으로 진행): {LAST_ERR}")
        return {}


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료"); return
    llm_cfg = cfg.get("llm") or {}
    key = llm_cfg.get("api_key", "")
    dry = (os.getenv("KOKPICK_DRY") or "true").lower() == "true"
    limit = int(os.getenv("KOKPICK_LIMIT") or "100")
    force = (os.getenv("KOKPICK_FORCE") or "false").lower() == "true"

    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])

    posts, page = [], 1
    while True:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit"}, timeout=30)
        if r.status_code != 200:
            print(f"글 조회 실패 {r.status_code}: {r.text[:200]}"); return
        b = r.json(); posts += b
        if len(b) < 50:
            break
        page += 1
    print(f"발행 글 {len(posts)}개 (dry={dry}, limit={limit}, force={force} · "
          f"llm={llm_cfg.get('provider','?')}/{llm_cfg.get('model','?')} key={'O' if key else 'X'})")

    done = skip = fail = empty = nolink = 0
    report = []
    for p in posts:
        if done >= limit:
            break
        pid = p["id"]
        html = (p.get("content") or {}).get("raw") or ""
        meta = p.get("meta") or {}
        title = re.sub(r"<[^>]+>", "", (p.get("title") or {}).get("rendered") or "").strip()
        if not force and kokpick.has_block(html) and (meta.get("kokpick") or "").strip():
            skip += 1
            report.append({"id": pid, "title": title[:40], "action": "skip"})
            continue

        art = {"title": title, "slug": p.get("slug") or "",
               "focus_keyword": meta.get("rank_math_focus_keyword") or ""}
        prod = products.find_for(art)
        url = ""
        if prod:
            sid = products.safe_subid(art["slug"], pid, art["focus_keyword"])
            url = products.with_subid(prod.get("coupang_url") or "", sid)
        if not url:
            nolink += 1

        art["kokpick"] = extract(title, strip_tags(html), llm_cfg) if key else {}
        art["kokpick"]["alt_uses"] = []          # 소급분은 근거가 없다 — 안전 규칙
        art["kokpick"]["alt_uses_source"] = ""
        data = kokpick.build(art, prod, url)
        if kokpick.is_empty(data):
            empty += 1
        row = {"id": pid, "title": title[:40], "action": "plan" if dry else "write",
               "product": data.get("product", ""), "price_band": data.get("price_band", ""),
               "condition_branch": len(data["condition_branch"]),
               "cautions": len(data["cautions"]),
               "size_install": bool(data.get("size_install")),
               "maintenance": bool(data["maintenance"]["cycle"] or
                                   data["maintenance"]["cost_per_year"]),
               "coupang": bool(url), "empty": kokpick.is_empty(data),
               "llm_error": LAST_ERR}
        report.append(row)
        print(f"[{pid}] {title[:34]} — 제품 '{data.get('product','')}' · "
              f"조건 {len(data['condition_branch'])} · 주의 {len(data['cautions'])} · "
              f"링크 {'O' if url else 'X'}")
        if dry:
            done += 1
            continue

        new_html = kokpick.strip_block(html) + kokpick.block_html(data)
        rr = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}",
                           json={"content": new_html,
                                 "meta": {"kokpick": kokpick.to_json(data)}},
                           headers={**headers, "Content-Type": "application/json"},
                           timeout=60)
        if rr.status_code in (200, 201):
            done += 1
        else:
            fail += 1
            row["action"] = "fail"
            row["http"] = rr.status_code
            print(f"  ✗ 저장 실패 {rr.status_code}: {rr.text[:150]}")
        time.sleep(1)

    summary = (f"콕픽 블록 소급: 처리 {done}편 · 이미있음 {skip}편 · 실패 {fail}편 | "
               f"근거 없음(캐스토 폴백) {empty}편 · 쿠팡링크 없음 {nolink}편")
    print(summary)
    try:
        os.makedirs("dashboard/data", exist_ok=True)
        with open("dashboard/data/kokpick_backfill.json", "w", encoding="utf-8") as f:
            json.dump({"ran_at": time.strftime("%Y-%m-%d %H:%M"), "dry": dry,
                       "llm": f"{llm_cfg.get('provider','?')}/{llm_cfg.get('model','?')}",
                       "summary": summary, "rows": report}, f,
                      ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"보고서 저장 실패: {e}")
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat and not dry:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": f"🎬 {summary}"}, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
