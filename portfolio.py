# -*- coding: utf-8 -*-
"""키워드 포트폴리오 (2026-11-23 신설) — 글감을 네 몫으로 나눠 배분한다.

왜 만들었나
  주제 선정에 **성과가 되돌아오는 길이 없었다.** 네이버에서 「가전 할부·구독·렌탈」이 유입 검색어
  TOP30 의 12자리를 차지하는데도 그 광맥을 파는 글은 #63 한 편뿐이었다 — 매 회차 LLM 이
  백지에서 주제를 발명했기 때문이다. 반대로 먹히는 것만 쓰면 글끼리 같은 말을 두고 다투고
  (#448·#663 욕실 온풍기) 새 키워드가 발굴되지 않는다. 그래서 **비율로 묶는다.**

    A 강화      40%  이미 유입이 확인된 말의 연관 검색어(네이버 키워드도구)
    B 에버그린  30%  연관어 중 검색량 1,000↑ · 1년 내내 고른 것(데이터랩 추이)
    C 핫이슈    15%  지금 뜨는 말(급상승·시즌진입)의 연관 검색어
    D 실험      15%  아직 다루지 않은 주제군 — 새 광맥을 찾는 몫. **10% 아래로 내리지 않는다.**

  픽담은 한 번에 1~2편만 쓰므로 한 회차 안에서 나누지 않고 **회차를 돌아가며** 맞춘다:
  최근 20편의 실제 배분을 보고 목표에 가장 모자란 몫을 이번 차례로 잡는다.

하는 일은 '씨앗'을 주는 것까지다. 씨앗(짧은 검색어)을 주제 프롬프트에 넣으면 LLM 이 그 말을 품은
주제 문장을 만들고, 그 뒤의 금지어·중복·수요 게이트는 기존 그대로 지난다.
어느 단계가 실패해도 **기존 흐름으로 되돌아간다**(발행은 멈추면 안 된다).

파일
  dashboard/data/keyword_portfolio.json        배분 기록(이 모듈이 쓴다 — 매일 생성 워크플로가 커밋)
  dashboard/data/keyword_portfolio_stats.json  성적·비중·승격/제외(scripts/portfolio_feedback.py 가 쓴다)
  dashboard/data/topic_queue.json              사람이 지정한 글감(먼저 소화한다)
"""
import datetime as _dt
import html
import json
import os
import re

DATA = os.path.join("dashboard", "data")
STATE = os.path.join(DATA, "keyword_portfolio.json")
STATS = os.path.join(DATA, "keyword_portfolio_stats.json")
QUEUE = os.path.join(DATA, "topic_queue.json")
SEED = os.path.join("data", "naver_seed_keywords.json")
SIGNALS = os.path.join(DATA, "naver_signals.json")
SHARES = {"A": 40, "B": 30, "C": 15, "D": 15}
NAMES = {"A": "강화", "B": "에버그린", "C": "핫이슈", "D": "실험", "P": "지정", "X": "자유"}
D_FLOOR = 10


def _load(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def norm(s):
    return re.sub(r"[^0-9a-z가-힣]", "", html.unescape(re.sub(r"<[^>]+>", " ", str(s or ""))).lower())


def grams(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def cover(keyword, text):
    """keyword 의 두 글자 조각 중 몇 %가 text 에 있는가(0~1). 띄어쓰기 차이를 무시한다."""
    g = grams(keyword)
    return (len(g & grams(text)) / len(g)) if g else 0.0


def covered(keyword, titles, at=0.8):
    """이미 쓴 글 제목이 그 말을 품고 있는가 — 같은 말을 두고 내 글끼리 다투지 않게."""
    g = grams(keyword)
    if not g:
        return True
    toks = [norm(t) for t in re.split(r"\s+", str(keyword)) if norm(t)]
    for t in titles:
        if not t:
            continue
        nt = norm(t)
        # 낱말이 전부 들어 있으면 사이에 다른 말이 끼어도 같은 말이다(「욕실 온풍기」 ↔ 「욕실 미니 온풍기 …」)
        if (len(g & grams(t)) / len(g)) >= at or (len(toks) >= 2 and all(k in nt for k in toks)):
            return True
    return False


def shares(cfg=None):
    s = dict(SHARES)
    s.update({k: v for k, v in ((_load(STATS, {}) or {}).get("shares") or {}).items() if k in s})
    s.update({k: v for k, v in (((cfg or {}).get("portfolio") or {}).get("shares") or {}).items() if k in s})
    if s["D"] < D_FLOOR:                       # 발굴 몫은 성과가 아무리 좋아도 없애지 않는다
        s["A"] -= (D_FLOOR - s["D"])
        s["D"] = D_FLOOR
    return s


def lane_order(state, cfg=None):
    """목표 비중에 가장 모자란 몫부터."""
    sh = shares(cfg)
    recent = [h.get("lane") for h in (state.get("history") or []) if h.get("lane") in sh][-20:]
    n = max(1, len(recent))
    deficit = {k: sh[k] / 100.0 - recent.count(k) / n for k in sh}
    return sorted(sh, key=lambda k: (-deficit[k], "ABCD".index(k)))


def hints():
    """강화의 출발점 — 유입이 확인된 말. 글마다 노출이 가장 큰 검색어 하나씩, 노출 큰 글부터."""
    st = _load(STATS, {}) or {}
    retired = {norm(x) for x in st.get("retired") or []}
    by_post = {}
    for k in (_load(SEED, {}) or {}).get("keywords") or []:
        kw = (k.get("keyword") or "").strip()
        if not kw or len(kw) > 16:             # 긴 문장은 키워드도구가 못 읽는다
            continue
        o = by_post.setdefault(k.get("post_id") or kw, {"impr": 0, "best": None, "best_impr": -1})
        o["impr"] += int(k.get("impr") or 0)
        if int(k.get("impr") or 0) > o["best_impr"]:
            o["best"], o["best_impr"] = kw, int(k.get("impr") or 0)
    out = [o["best"] for o in sorted(by_post.values(), key=lambda o: -o["impr"]) if o["best"]]
    # 사람이 주제군으로 묶어 적어 둔 짧은 말이 있으면 그것부터 쓴다. 유입 검색어는 「통돌이 삶음 기능」처럼
    # 구체적이라 키워드도구에 넣으면 연관어가 거의 안 나온다 — 「미니세탁기」 같은 줄기 말이 필요하다.
    out = list((_load(SEED, {}) or {}).get("hints") or []) + list(st.get("promoted") or []) + out
    seen, res = set(), []
    for h in out:
        if norm(h) and norm(h) not in seen and norm(h) not in retired:
            seen.add(norm(h))
            res.append(h)
    return res[:8]


def rising():
    """지금 뜨는 말 — 네이버 신호 수집이 '급상승'·'시즌진입'으로 판정한 것."""
    rows = (_load(SIGNALS, {}) or {}).get("rows") or []
    return [r["keyword"] for r in rows if r.get("label") in ("급상승", "시즌진입") and r.get("keyword")][:5]


def expand(hint_list, cfg, titles):
    """힌트마다 연관 검색어를 받아, 힌트와 낱말을 나누고 아직 안 쓴 것만 남긴다."""
    import demand
    dc = (cfg or {}).get("demand") or {}
    lo, hi = int(dc.get("min_volume", 300)), int(dc.get("max_volume", 30000))
    lo = min(lo, 1000)                         # 게이트 하한(기본 1,500)보다 조금 넓게 본다 — 여기서는 씨앗만 고른다
    block = set(dc.get("block_comp") or ["높음"])
    out, seen = [], set()
    for h in hint_list:
        toks = [norm(t) for t in re.split(r"\s+", h) if len(norm(t)) >= 2] or [norm(h)]
        for r in demand.keyword_rows([h], cfg, limit=300):
            kw, k = (r.get("keyword") or "").strip(), norm(r.get("keyword"))
            if not k or k in seen or not (lo <= int(r.get("volume") or 0) <= hi) or r.get("comp") in block:
                continue
            if not all(t in k for t in toks) and cover(h, kw) < 0.6:
                continue                        # 키워드도구는 느슨한 연관어도 준다(미니세탁기 → 세탁기건조기세트). 힌트의 낱말을 다 품은 것만
            if covered(kw, titles):
                continue
            seen.add(k)
            out.append({"keyword": kw, "volume": int(r.get("volume") or 0), "comp": r.get("comp") or "", "hint": h})
    # 힌트를 돌아가며 하나씩 뽑는다. 검색량순으로만 자르면 큰 주제군 하나(세탁기)가 씨앗을 다 차지하고
    # 정작 유입이 가장 넓은 주제군(가전 할부)이 밀려난다 — 2026-11-23 첫 미리보기에서 실제로 그랬다.
    by_hint = {}
    for o in sorted(out, key=lambda x: -x["volume"]):
        by_hint.setdefault(o["hint"], []).append(o)
    mixed, i = [], 0
    while any(by_hint.values()):
        for h in hint_list:
            if by_hint.get(h):
                mixed.append(by_hint[h].pop(0))
        i += 1
    return mixed


def seeds_for(lane, cfg, titles, log=print):
    if lane == "D":
        return []
    if lane == "C":
        hs = rising()
        if not hs:
            log("  · [배분] 지금 뜨는 말이 없다(네이버 신호 없음)")
            return []
        return expand(hs, cfg, titles)[:6]
    hs = hints()
    if not hs:
        log("  · [배분] 유입이 확인된 말이 없다(data/naver_seed_keywords.json 비어 있음)")
        return []
    pool = expand(hs, cfg, titles)
    if lane == "A":
        return pool[:6]
    # B: 검색량 1,000 이상 · 추이가 고른 것
    # 경쟁 '낮음'까지 요구하면 씨앗이 하나도 안 남는다(첫 미리보기 실측 — 살 물건이 있는 말은 거의 '중간').
    # '높음'은 expand 에서 이미 걸렀으니, 여기서는 검색량과 추이만 본다.
    cand = [p for p in pool if p["volume"] >= 1000]
    try:
        import naver_hub as nh
        if nh.available():
            keep = []
            for p in cand[:10]:
                prof = nh.trend_profile(p["keyword"])
                p["trend"] = prof.get("label")
                if prof.get("label") == "에버그린":
                    keep.append(p)
            return keep[:6]
    except Exception as e:
        log(f"  · [배분] 추이 확인 건너뜀({str(e)[:60]})")
    return [dict(p, trend="미확인") for p in cand[:6]]


def plan(cfg, titles, log=print):
    """이번 회차의 몫과 씨앗. 실패하면 None — 호출한 쪽은 기존 흐름대로 간다."""
    if not ((cfg or {}).get("portfolio") or {}).get("enabled", True):
        return None
    state = _load(STATE, {}) or {}
    queue = _load(QUEUE, {}) or {}
    pin = next((q for q in queue.get("items") or [] if not q.get("done") and (q.get("keyword") or "").strip()), None)
    if pin:
        log(f"  · [배분] 지정 글감 먼저: {pin['keyword']}")
        return {"lane": "P", "seeds": [{"keyword": pin["keyword"], "note": pin.get("note", "")}], "pin": pin["keyword"]}
    dc = (cfg or {}).get("demand") or {}
    if not (dc.get("api_key") and dc.get("secret") and dc.get("customer_id")):
        # 키워드도구를 못 쓰면 A·B·C 가 전부 빈손이라 매번 '실험'으로 떨어진다.
        # 그걸 실험 몫으로 적으면 기록이 거짓이 된다 — 배분을 아예 하지 않는다.
        log("  · [배분] 네이버 검색광고 키가 없어 건너뜁니다(기존 방식으로 주제 선정)")
        return None
    order = lane_order(state, cfg)
    for lane in order:
        try:
            seeds = seeds_for(lane, cfg, titles, log)
        except Exception as e:
            log(f"  · [배분] {NAMES[lane]} 씨앗 수집 실패({str(e)[:70]})")
            seeds = []
        if seeds or lane == "D":
            log(f"  · [배분] 이번 차례 = {lane} {NAMES[lane]} (모자란 순서 {' > '.join(order)})"
                + (" · 씨앗: " + ", ".join(f"{s['keyword']}({s.get('volume', '-')})" for s in seeds) if seeds else ""))
            return {"lane": lane, "seeds": seeds, "avoid": hints() if lane == "D" else []}
        log(f"  · [배분] {lane} {NAMES[lane]} — 씨앗이 없어 다음 몫으로")
    return None


def prompt_block(p):
    if not p:
        return ""
    if p["lane"] == "P":
        s = p["seeds"][0]
        return ("\n[🔴 지정 글감 — 운영자가 정했다]\n"
                f"- {s['keyword']}" + (f" ({s['note']})" if s.get("note") else "") + "\n"
                "→ **첫 번째 주제는 반드시 이 검색어를 글자 그대로 품어야 한다.** 낱말을 바꾸거나 순서를 뒤집지 않는다.\n")
    if p["lane"] == "D":
        av = "\n".join(f"- {a}" for a in p.get("avoid") or []) or "(없음)"
        return ("\n[🧪 키워드 배분 — 이번 차례는 '실험' 몫이다]\n"
                "아래 주제군은 이미 유입이 확인돼 따로 다루고 있다:\n" + av + "\n"
                "→ 이번에는 위와 **다른 품목·다른 상황**의 주제를 앞자리에 둔다. 새 광맥을 찾는 차례다.\n")
    lines = "\n".join(f"- {s['keyword']} (월 {s['volume']:,}회)" for s in p["seeds"])
    why = {"A": "이미 유입이 확인된 글의 연관 검색어다",
           "B": "1년 내내 고르게 찾는 말이다",
           "C": "지금 검색이 늘고 있는 말이다"}[p["lane"]]
    return (f"\n[📊 키워드 배분 — 이번 차례는 '{NAMES[p['lane']]}' 몫이다]\n"
            f"아래는 네이버에서 실제로 검색되는 말이고, {why}.\n{lines}\n"
            "→ 이 카테고리에 맞는 것이 있으면 **그 검색어를 글자 그대로 품은** 주제를 앞자리에 둔다"
            "(한 검색어에 주제 하나). 맞는 것이 없으면 무시한다.\n")


def match_seed(keyword, p):
    for s in (p or {}).get("seeds") or []:
        if cover(s["keyword"], keyword) >= 0.7:
            return s
    return None


def prefer(sel, pool, p, n_slots):
    """선별 단계가 씨앗 품은 후보를 밀어냈으면 첫 자리에 되돌려 놓는다 — 배분이 말로만 끝나지 않게."""
    if not p or not p.get("seeds") or any(match_seed(c.get("keyword"), p) for c in sel):
        return sel
    hit = next((c for c in pool if match_seed(c.get("keyword"), p)), None)
    if not hit:
        return sel
    return ([hit] + [c for c in sel if c is not hit])[:max(1, n_slots)]


def record(selected, p, category="", log=print):
    """고른 주제에 몫을 붙여 기록한다. 씨앗을 품지 못한 주제는 '자유'(X)로 적는다 — 속이지 않는다."""
    if not p:
        return
    state = _load(STATE, {}) or {}
    hist = state.setdefault("history", [])
    today = _dt.date.today().isoformat()
    used = []
    for c in selected:
        s = match_seed(c.get("keyword"), p)
        lane = p["lane"] if (s or p["lane"] == "D") else "X"
        c["pf_lane"], c["pf_seed"] = lane, (s or {}).get("keyword", "")
        hist.append({"date": today, "lane": lane, "intended": p["lane"], "seed": c["pf_seed"],
                     "hint": (s or {}).get("hint", ""), "keyword": c.get("keyword", ""), "category": category})
        if s:
            used.append(s["keyword"])
        log(f"  · [배분] 기록: {lane} {NAMES[lane]} ← {c.get('keyword', '')[:40]}"
            + (f" (씨앗 {c['pf_seed']})" if s else ""))
    p["seeds"] = [s for s in p.get("seeds") or [] if s["keyword"] not in used]     # 다음 카테고리가 같은 씨앗을 또 쓰지 않게
    state["history"] = hist[-400:]
    state["updated"] = today
    _save(STATE, state)
    if p.get("pin"):
        q = _load(QUEUE, {}) or {}
        for it in q.get("items") or []:
            if it.get("keyword") == p["pin"] and not it.get("done"):
                if p["pin"] in used:
                    it["done"] = today
                else:
                    # 주제로 뽑히지 못했다(금지어·중복 판정 등). 두 번 실패하면 내려놓는다 —
                    # 안 그러면 이 글감이 맨 앞을 막고 배분이 영영 돌지 않는다.
                    it["tries"] = int(it.get("tries") or 0) + 1
                    if it["tries"] >= 2:
                        it["done"] = f"{today} 건너뜀(주제로 뽑히지 못함 {it['tries']}회)"
                break
        _save(QUEUE, q)
        p["lane"], p["pin"], p["seeds"] = "X", None, []     # 지정 글감은 한 회차·한 카테고리에 한 번만


if __name__ == "__main__":
    # 미리보기: python portfolio.py  (키가 있으면 실제 연관 검색어까지 뽑는다. 아무것도 쓰지 않는다)
    import sys
    cfg = _load("config.json", {}) or {}
    arts = (_load(os.path.join(DATA, "history.json"), {}) or {}).get("articles") or []
    titles = [a.get("title", "") for a in arts]
    st = _load(STATE, {}) or {}
    print("목표 비중:", shares(cfg), "· 모자란 순서:", " > ".join(lane_order(st, cfg)))
    print("강화 힌트:", hints())
    print("지금 뜨는 말:", rising())
    for lane in ("A", "B", "C"):
        try:
            ss = seeds_for(lane, cfg, titles)
        except Exception as e:
            ss = []
            print(f"{lane} 실패: {e}")
        print(f"[{lane} {NAMES[lane]}] 씨앗 {len(ss)}개")
        for s in ss:
            print(f"   {s['keyword']} · 월 {s['volume']:,} · 경쟁 {s['comp']} · 힌트 {s['hint']}"
                  + (f" · 추이 {s['trend']}" if s.get('trend') else ""))
    p = plan(cfg, titles)
    print("이번 차례:", (p or {}).get("lane"), "\n" + prompt_block(p))
    sys.exit(0)
