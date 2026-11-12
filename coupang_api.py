# -*- coding: utf-8 -*-
"""쿠팡 파트너스 오픈API — 가격·링크·리뷰의 유일한 합법 경로 (2026-11-12 신설).

**왜 이 모듈이 필요했나**
  「이번 주 유행템」 리포트는 ①1~20만 원대라는 가격 필터와 ②상품마다 쿠팡 링크가
  필요하다. 둘 다 지금까지 없었다:
    · 가격: 네이버 쇼핑 검색 API가 **2026-07-31 종료**(대체 없음, API HUB에도 미포함).
            캐스토 `trend_sources.naver_shopping()`은 그래서 항상 None을 반환하도록 폐기됐다.
    · 링크: `data/products.json`의 24종만 수동 딥링크가 있다. 트렌드로 새로 뜬 제품은 링크가 없다.
  쿠팡 오픈API는 두 문제를 한 번에 푼다 — `productPrice`가 가격이고 `productUrl`이
  **이미 파트너스 추적이 붙은 링크**다. 쿠팡 리뷰·인스타 크롤링은 금지(famto 2026-11-11)이므로
  공식 API만 쓴다.

**구현은 캐스토 `trend_sources.py`의 `_coupang_auth`/`coupang_product`를 이식한 것이다**
  (공유 코드 이식 관행 — 캐스토 레포는 수정하지 않는다). 확장한 점:
    · 1건이 아니라 여러 건을 받고(limit), 가격대 필터를 여기서 걸 수 있게 했다
    · `isRocket`을 함께 돌려준다(로켓배송 비교표용)
    · 응답 필드는 **방어적으로 파싱**한다 — 미제공 필드는 0이 아니라 None이다
      (0은 '재보니 0', None은 '못 쟀다'. 이 구분을 잃으면 나중에 원인을 못 찾는다)

⚠️ 키가 없으면 조용히 None을 돌려준다. 호출부는 "키 없음"과 "검색 결과 없음"을
   구분해 보고해야 한다 — 빈손을 고장으로 오판하는 게 이 레포의 상습 실패다.
"""
import hashlib
import hmac
import os
import time

import requests

HOST = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"


def ready():
    return bool(os.getenv("COUPANG_ACCESS_KEY") and os.getenv("COUPANG_SECRET_KEY"))


def _auth(method, path, query=""):
    """CEA HmacSHA256. 서명 메시지 = signed-date + METHOD + path + query(?포함)."""
    ak, sk = os.getenv("COUPANG_ACCESS_KEY", ""), os.getenv("COUPANG_SECRET_KEY", "")
    if not (ak and sk):
        return None
    ts = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    sig = hmac.new(sk.encode(), (ts + method + path + query).encode(), hashlib.sha256).hexdigest()
    return {"Authorization": f"CEA algorithm=HmacSHA256, access-key={ak}, "
                             f"signed-date={ts}, signature={sig}"}


def _num(v):
    """'129,000원' 같은 문자열도 숫자로. 못 읽으면 None(0으로 떨구지 않는다)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    d = "".join(c for c in str(v) if c.isdigit())
    return int(d) if d else None


def search(keyword, limit=5):
    """상품 검색. 반환: [{name, price, url, image, review_count, rocket}] / 키 없거나 실패면 []."""
    query = f"?keyword={requests.utils.quote(keyword)}&limit={int(limit)}"
    h = _auth("GET", SEARCH_PATH, query)
    if not h:
        return []
    try:
        r = requests.get(HOST + SEARCH_PATH + query, headers=h, timeout=30)
        if r.status_code != 200:
            print(f"[coupang] '{keyword}' HTTP {r.status_code}: {r.text[:140]}")
            return []
        items = (r.json().get("data") or {}).get("productData") or []
    except Exception as e:
        print(f"[coupang] '{keyword}' 실패: {str(e)[:100]}")
        return []
    out = []
    for it in items:
        out.append({
            "name": it.get("productName"),
            "price": _num(it.get("productPrice")),
            "url": it.get("productUrl"),
            "image": it.get("productImage"),
            "review_count": _num(it.get("reviewCount")),
            "rocket": bool(it.get("isRocket")),
        })
    return out


def best_in_band(keyword, lo=10_000, hi=200_000, limit=10):
    """가격대 안에서 가장 그럴듯한 1건. 밴드 밖이면 None을 돌려 호출부가 탈락 이유를 쓸 수 있게 한다."""
    items = [x for x in search(keyword, limit=limit) if x["price"]]
    if not items:
        return None
    inband = [x for x in items if lo <= x["price"] <= hi]
    if not inband:
        return None
    # 리뷰 수가 있으면 많은 쪽, 없으면 검색 상위(= 쿠팡이 판단한 적합도) 유지
    inband.sort(key=lambda x: (x["review_count"] or 0), reverse=True)
    return inband[0]
