# -*- coding: utf-8 -*-
"""키워드 배분 되먹임 (2026-11-23 신설) — 몫별 성적을 재고 비중·힌트를 고친다.

읽는 것
  dashboard/data/keyword_portfolio.json   배분 기록(어느 주제를 어느 몫으로 썼나)
  dashboard/data/history.json             주제 → 발행 글(주소·글 ID)
  dashboard/data/insights.json            구글 서치콘솔 글별 노출·클릭(자동 수집)
  data/naver_seed_keywords.json           네이버 유입 검색어(사람이 옮긴 값 — 글 ID 가 붙은 것만 합산)
쓰는 것
  dashboard/data/keyword_portfolio_stats.json   성적·비중·승격/제외 → portfolio.py 가 다음 회차에 읽는다
  data/keyword_portfolio.md                     사람이 읽는 표

규칙(단순하게 시작한다 — 표본이 쌓이기 전에는 아무것도 바꾸지 않는다)
  · 실험(D)·자유(X) 글이 21일 지나 노출 500 이상 → 그 씨앗을 강화 힌트로 **승격**
  · 같은 힌트로 쓴 글이 2편 이상이고 전부 60일 지나 노출 50 미만 → 그 힌트를 **제외**
  · 강화(A)의 편당 노출이 세 번 연속 올랐다 → A 비중 +5%p(상한 50, B 에서 뗀다)
  · 실험(D)은 10% 아래로 내리지 않는다
성숙 기간: A 21일 · B 60일 · C 14일 · D 21일. 그 전의 글은 성적에 넣지 않는다.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import portfolio as pf

MATURE = {"A": 21, "B": 60, "C": 14, "D": 21, "P": 21, "X": 21}
OUT_MD = os.path.join("data", "keyword_portfolio.md")


def _slug(u):
    return (u or "").rstrip("/").rsplit("/", 1)[-1]


def main():
    state = pf._load(pf.STATE, {}) or {}
    hist = state.get("history") or []
    arts = (pf._load(os.path.join(pf.DATA, "history.json"), {}) or {}).get("articles") or []
    by_kw = {a.get("keyword"): a for a in arts if a.get("keyword")}
    gsc = {_slug(p.get("page")): p for p in
           ((pf._load(os.path.join(pf.DATA, "insights.json"), {}) or {}).get("search_console") or {}).get("pages") or []}
    naver = {}
    for k in (pf._load(pf.SEED, {}) or {}).get("keywords") or []:
        if k.get("post_id"):
            o = naver.setdefault(k["post_id"], {"impr": 0, "clicks": 0})
            o["impr"] += int(k.get("impr") or 0)
            o["clicks"] += int(k.get("clicks") or 0)

    today = dt.date.today()
    rows = []
    for h in hist:
        a = by_kw.get(h.get("keyword")) or {}
        g = gsc.get(_slug(a.get("url"))) or {}
        n = naver.get(a.get("post_id")) or {}
        try:
            age = (today - dt.date.fromisoformat(h.get("date"))).days
        except Exception:
            age = 0
        rows.append({**h, "post_id": a.get("post_id"), "url": a.get("url"), "age": age,
                     "published": bool(a.get("url")),
                     "impr": int(g.get("impressions") or 0) + int(n.get("impr") or 0),
                     "clicks": int(g.get("clicks") or 0) + int(n.get("clicks") or 0),
                     "mature": age >= MATURE.get(h.get("lane"), 21)})

    lanes = {}
    for k in ("A", "B", "C", "D", "X", "P"):
        rs = [r for r in rows if r.get("lane") == k]
        mt = [r for r in rs if r["mature"] and r["published"]]
        lanes[k] = {"posts": len(rs), "mature": len(mt),
                    "impr": sum(r["impr"] for r in mt), "clicks": sum(r["clicks"] for r in mt),
                    "per_post": round(sum(r["impr"] for r in mt) / len(mt), 1) if mt else None}

    stats = pf._load(pf.STATS, {}) or {}
    promoted = list(stats.get("promoted") or [])
    retired = list(stats.get("retired") or [])
    notes = []
    for r in rows:
        if r.get("lane") in ("D", "X") and r["mature"] and r["impr"] >= 500:
            seed = pf.norm(r.get("seed") or "") and r["seed"] or " ".join((r.get("keyword") or "").replace(",", " ").split()[:2])
            if seed and seed not in promoted:
                promoted.append(seed)
                notes.append(f"승격: 「{seed}」 — 실험 글이 노출 {r['impr']} (#{r.get('post_id')})")
    by_hint = {}
    for r in rows:
        if r.get("hint"):
            by_hint.setdefault(r["hint"], []).append(r)
    for h, rs in by_hint.items():
        if len(rs) >= 2 and all(r["age"] >= 60 and r["impr"] < 50 for r in rs) and h not in retired:
            retired.append(h)
            notes.append(f"제외: 「{h}」 — {len(rs)}편이 60일 넘도록 노출 50 미만")

    shares = pf.shares()
    snaps = list(stats.get("snapshots") or [])
    if lanes["A"]["per_post"] is not None:
        snaps.append({"date": today.isoformat(), "A": lanes["A"]["per_post"]})
        snaps = snaps[-12:]
        last = [s["A"] for s in snaps[-4:]]
        if len(last) == 4 and last[0] < last[1] < last[2] < last[3] and shares["A"] < 50:
            step = min(5, 50 - shares["A"], max(0, shares["B"] - 15))
            if step > 0:
                shares["A"] += step
                shares["B"] -= step
                notes.append(f"비중: 강화 +{step}%p (편당 노출 3회 연속 상승 {last})")
    if shares["D"] < pf.D_FLOOR:
        shares["D"] = pf.D_FLOOR

    out = {"updated": today.isoformat(), "shares": shares, "lanes": lanes,
           "promoted": promoted, "retired": retired, "snapshots": snaps, "notes": notes,
           "next_order": pf.lane_order(state)}
    pf._save(pf.STATS, out)

    recent = [h.get("lane") for h in hist if h.get("lane") in shares][-20:]
    L = [f"# 키워드 배분 현황 — {today.isoformat()}", "",
         "| 몫 | 목표 | 최근 20편 실제 | 쓴 글 | 성숙한 글 | 편당 노출 |", "|---|---:|---:|---:|---:|---:|"]
    for k in ("A", "B", "C", "D"):
        act = f"{int(round(recent.count(k) / len(recent) * 100))}%" if recent else "-"
        L.append(f"| {k} {pf.NAMES[k]} | {shares[k]}% | {act} | {lanes[k]['posts']} | {lanes[k]['mature']} | "
                 f"{lanes[k]['per_post'] if lanes[k]['per_post'] is not None else '아직 없음'} |")
    L += ["", f"자유(씨앗을 품지 못한 주제) {lanes['X']['posts']}편 · 지정 글감 {lanes['P']['posts']}편",
          f"다음 차례 순서: {' > '.join(out['next_order'])}",
          "", "강화 힌트: " + (", ".join(pf.hints()) or "(없음)"),
          "지금 뜨는 말: " + (", ".join(pf.rising()) or "(없음)")]
    q = [i for i in (pf._load(pf.QUEUE, {}) or {}).get("items") or []]
    if q:
        L += ["", "## 지정 글감", ""] + [f"- {i['keyword']} — {i.get('done') or '대기'}" for i in q]
    if notes:
        L += ["", "## 이번에 바뀐 것", ""] + [f"- {n}" for n in notes]
    if not hist:
        L += ["", "> 아직 배분 기록이 없습니다. 다음 자동 발행부터 쌓입니다."]
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
