"""
report.py - 운영자 주간 리포트(무료). 주 1회 실행해 텔레그램으로 요약 전송.
- 이번 주 생성/발행 편수(히스토리 기준)
- 유입 상위 글/검색어(insights.json, Search Console)
- 실측 수익(insights.json, AdSense)
- 이번 달 예상비용(status.json)
실행: python report.py   (config.json 필요)
"""

import os
import json
from datetime import datetime, timedelta

import notify

BASE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(BASE, "dashboard", "data")


def _load(name):
    try:
        with open(os.path.join(DASH, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build():
    hist = _load("history.json")
    ins = _load("insights.json")
    status = _load("status.json")

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    arts = [a for a in hist.get("articles", []) if str(a.get("date", "")) >= week_ago]
    from collections import Counter
    by_cat = Counter(a.get("category", "") for a in arts)
    cat_line = " · ".join(f"{k} {v}" for k, v in by_cat.items()) or "없음"

    lines = ["📊 <b>Scripto 주간 리포트</b>", f"🗓 최근 7일 · {datetime.now():%Y-%m-%d}",
             f"📝 생성 {len(arts)}편 ({cat_line})"]

    sc = (ins.get("search_console") or {}).get("queries") or []
    if sc:
        top = " / ".join(f"{q['query']}({int(q.get('clicks',0))})" for q in sc[:5])
        lines.append(f"🔎 유입 검색어 TOP5: {top}")
    pages = (ins.get("search_console") or {}).get("pages") or []
    if pages:
        lines.append(f"🏆 유입 1위 글: {pages[0]['page']} (클릭 {int(pages[0].get('clicks',0))})")

    ad = ins.get("adsense") or {}
    if ad:
        lines.append(f"💰 애드센스 {ad.get('days',28)}일: {ad.get('earnings','0')} {ad.get('currency','')} "
                     f"(클릭 {ad.get('clicks','0')})")

    cost = (status.get("usage") or {}).get("est_cost_krw")
    if cost is not None:
        lines.append(f"💸 이번 달 예상비용 ₩{int(cost):,}")

    return "\n".join(lines)


if __name__ == "__main__":
    try:
        with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    msg = build()
    print(msg)
    ok = notify.send(cfg, msg)
    print("전송:", "성공" if ok else "건너뜀(텔레그램 미설정)")
