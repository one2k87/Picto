# -*- coding: utf-8 -*-
"""생필품 조사가격(한국소비자원 참가격) — 글의 **기준가** (2026-11-12 신설).

**왜 이게 가격 경로가 됐나**
  쿠팡 파트너스 오픈API는 **누적 수익 ₩150,000 → 최종승인** 뒤에야 열린다(2026-09 가이드 실측).
  네이버 쇼핑 '검색' API는 2026-07-31 종료(대체 없음). 즉 **상품 실시간 가격을 받을 공식 경로가 없다.**
  그래서 글에 실시간 가격을 박는 설계를 버리고, 바뀌지 않는 **공식 조사가격을 기준선**으로 쓴다
  (사용자 결정 2026-11-12). "소비자원 조사 평균 ○○원" 한 줄은 다른 블로그가 쓰지 않는 출처다.

데이터: 공공데이터포털 「한국소비자원_생필품 가격 정보」(파일+오픈API, 무료, 이용허락 제한 없음).
  항목: 상품명·조사일·판매가격·판매업소·제조사·세일여부·1+1여부 / 월간 갱신.
  ⚠️ 품목 단위가 '생필품'(세제·휴지·식품 등)이라 가전·잡화는 **대개 안 잡힌다.**
     없으면 조용히 None — 그게 정상이고, 없는 걸 억지로 끼워 맞추면 틀린 글이 된다.

키: `PRICE_REF_API_KEY` (공공데이터포털 활용신청 후 발급). 없으면 전체 기능이 꺼진다.
"""
import os
import re

import requests

ENDPOINT = os.getenv("PRICE_REF_ENDPOINT",
                     "https://api.odcloud.kr/api/15083256/v1/uddi")
_CACHE = {}


def ready():
    return bool(os.getenv("PRICE_REF_API_KEY"))


def _norm(s):
    return re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())


def lookup(name, limit=100):
    """품목명과 겹치는 조사 기록에서 {평균가, 건수, 최저가, 조사일}. 못 찾으면 None."""
    key = os.getenv("PRICE_REF_API_KEY", "")
    if not key:
        return None
    n = _norm(name)
    if not n:
        return None
    if n in _CACHE:
        return _CACHE[n]
    try:
        r = requests.get(ENDPOINT, params={"serviceKey": key, "page": 1,
                                           "perPage": limit, "cond[상품명::LIKE]": name},
                         timeout=25)
        if r.status_code != 200:
            print(f"[price_ref] '{name}' HTTP {r.status_code}")
            return None
        rows = (r.json() or {}).get("data") or []
    except Exception as e:
        print(f"[price_ref] '{name}' 실패: {str(e)[:90]}")
        return None
    vals, days = [], []
    for row in rows:
        p = None
        for k, v in row.items():
            if "가격" in str(k):
                d = "".join(c for c in str(v) if c.isdigit())
                p = int(d) if d else None
            if "조사" in str(k) and v:
                days.append(str(v))
        if p:
            vals.append(p)
    if not vals:
        _CACHE[n] = None
        return None
    out = {"avg": sum(vals) // len(vals), "n": len(vals),
           "min": min(vals), "day": max(days) if days else None}
    _CACHE[n] = out
    return out
