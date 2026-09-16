# -*- coding: utf-8 -*-
"""콕픽(캐스토) ↔ 픽담 연결 — 교집합에서만 잇는다 (2026-09-16 신설).

왜 이 모듈이 있나(실측 근거):
  콕픽 영상의 CTA가 픽담으로 오게 설계돼 있는데, 픽토가 9/15부터 검색 수요로
  주제를 고르기 시작하면서 두 앱의 주제가 갈라진다는 문제가 제기됐다.
  **얼마나 갈라지는지 재보니 캐스토 큐 36종 중 픽토 기준 통과는 10종(28%)**이었다.
  탈락한 26종은 에그크래커·계란흰자분리기 같은 쇼츠 신기템으로,
  개별로도 묶음('주방신기템' 월 20회)으로도 검색 수요가 없었다.

  원인: **쇼츠는 '보면 신기한 것'으로 뜨고 블로그는 '찾아서 오는 것'으로 뜬다.**
  축이 다르므로 억지로 맞추면 한쪽이 크게 손해본다. 그래서 맞추지 않고 나눈다.

세 층:
  ① 교집합      — 양쪽 1순위. 영상 CTA가 **픽담 개별 글**로 간다. 픽토가 먼저 쓴다.
  ② 영상 전용   — 픽토가 글을 쓰지 않는다. CTA는 **쿠팡 직링크**. 경유시키면 이탈만 는다.
                  (검색 수요 없음 = '블로그로 올 경로가 없다'지 '안 팔린다'가 아니다)
  ③ 글 전용     — 픽토 단독 검색 수요 제품. 영상 없이 간다.

캐스토 레포는 **읽기만** 한다(공유_경계). 공개 레포라 raw로 받으면 토큰이 필요 없다.
"""
import json
import os

import requests

import demand

RAW = "https://raw.githubusercontent.com/one2k87/Casto/main/data/"
OUT = "dashboard/data/casto_cross.json"


def _get(name):
    try:
        r = requests.get(RAW + name, timeout=20)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[casto] {name} 받기 실패: {str(e)[:70]}")
        return None


def casto_products():
    """캐스토가 다루려는 제품 이름들 — 요청서 우선, 없으면 촬영 큐."""
    names = []
    tr = _get("topic_requests.json") or {}
    for r in (tr.get("requests") or []):
        n = (r.get("category") or r.get("product") or "").strip()
        if n and n not in names:
            names.append(n)
    q = (_get("shot_queue.json") or {}).get("items") or {}
    for v in q.values():
        n = (v.get("name") or v.get("key") or "").strip()
        if n and n not in names:
            names.append(n)
    return names


def classify(cfg, limit=60):
    """제품마다 층을 판정한다. 네이버 키가 없으면 판정하지 않는다(빈 결과)."""
    c = (cfg or {}).get("demand") or {}
    floor, ceil = int(c.get("min_volume", 300)), int(c.get("max_volume", 30000))
    block = set(c.get("block_comp") or ["높음"])
    rows = []
    for name in casto_products()[:limit]:
        got = demand.keyword_rows([name], cfg, limit=25)
        core = demand._clean(name)[:3]
        rel = [r for r in got if core in demand._clean(r["keyword"])]
        fit = [r for r in rel if floor <= r["volume"] <= ceil and r["comp"] not in block]
        fit.sort(key=lambda r: -r["clicks"])
        best = fit[0] if fit else None
        rows.append({
            "product": name,
            "tier": "교집합" if best else "영상전용",
            "cta": "픽담 개별 글" if best else "쿠팡 직링크",
            "best": best,
        })
    return {"floor": floor, "ceil": ceil, "block_comp": sorted(block), "rows": rows}


def save(cfg):
    res = classify(cfg)
    if not res["rows"]:
        print("[casto] 판정할 제품이 없다 — 건너뜀")
        return res
    os.makedirs("dashboard/data", exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(1 for r in res["rows"] if r["tier"] == "교집합")
    print(f"[casto] 판정 {len(res['rows'])}종 — 교집합 {n} · 영상전용 {len(res['rows'])-n} → {OUT}")
    return res


def priority_topics(cfg, articles=None):
    """교집합 제품 중 **아직 픽담에 글이 없는 것**을 최우선 주제로 돌려준다.
    main이 must_products에 얹어 주제 목록 앞자리를 채우게 한다."""
    try:
        res = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else classify(cfg)
    except Exception:
        return []
    hay = " ".join(demand._clean((a.get("title") or "") + (a.get("keyword") or ""))
                   for a in (articles or []))
    out = []
    for r in res.get("rows", []):
        if r.get("tier") != "교집합":
            continue
        b = r.get("best") or {}
        if demand._clean(r["product"])[:3] in hay:      # 이미 쓴 주제면 뺀다
            continue
        out.append({"name": r["product"], "key": r["product"],
                    "search": b.get("keyword", ""), "_volume": b.get("volume", 0),
                    "_from": "casto"})
    out.sort(key=lambda x: -x["_volume"])
    return out
