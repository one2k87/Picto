# -*- coding: utf-8 -*-
"""글별 쿠팡 상품 링크 — 픽담 수익의 실제 엔진 (2026-09-07 신설).

왜 위젯이 아니라 이것인가:
  ①워드프레스가 REST 발행 시 <script>를 지운다(실측) — 위젯은 이 경로로 못 들어간다.
    <a> 태그는 통과한다.
  ②구매의도로 들어온 방문자에게 필요한 건 '그래서 어느 제품'이라는 답이다.
    쿠팡이 임의로 고르는 배너보다 글 주제와 맞는 링크의 전환율이 훨씬 높다.
  ③subid로 글별 성과를 구분할 수 있다 — 무엇을 더 쓸지 감이 아니라 데이터로 정한다.

제약(정책):
  쿠팡 제휴 링크는 파트너스 사이트나 오픈 API로만 생성된다. 상품 URL에 파라미터를
  붙여 만든 링크는 수수료가 잡히지 않는다. 그래서 링크 자체는 사람이 한 번 만들어
  data/products.json에 넣고, 그 뒤의 매칭·삽입·subid·소급은 전부 자동으로 한다.
  (오픈 API 확보 시 이 파일을 API 조회로 대체하면 완전 자동이 된다)
"""
import json
import os
import re

PATH = "data/products.json"
_CACHE = None


def load(path=PATH):
    global _CACHE
    if _CACHE is None:
        try:
            with open(path, encoding="utf-8") as f:
                _CACHE = json.load(f) or {}
        except Exception as e:
            print(f"[products] {path} 없음/무시: {e}")
            _CACHE = {}
    return _CACHE


def all_products(cfg=None):
    return [p for p in (load().get("products") or []) if isinstance(p, dict)]


def _norm(s):
    """띄어쓰기·기호를 없애 '음식물 처리기'와 '음식물처리기'를 같게 본다."""
    return re.sub(r"[\s\-_·/]", "", (s or "")).lower()


def find_for(article):
    """글에 맞는 제품을 찾는다. match 키워드가 제목·키워드에 있으면 매칭.
    여러 개가 걸리면 가장 긴 키워드(=더 구체적인 것)를 고른다."""
    hay = _norm((article.get("title") or "") + " " +
                (article.get("keyword") or "") + " " +
                (article.get("focus_keyword") or ""))
    best, best_len = None, 0
    for p in all_products():
        for kw in (p.get("match") or [p.get("key", "")]):
            k = _norm(kw)
            if k and k in hay and len(k) > best_len:
                best, best_len = p, len(k)
    return best


def with_subid(url, subid):
    """파트너스 링크에 subid를 붙인다 — 어느 글이 벌었는지 구분하는 유일한 수단.
    이미 subid가 있으면 건드리지 않는다."""
    if not url:
        return url
    if "subid=" in url:
        return url
    sid = re.sub(r"[^A-Za-z0-9_]", "_", (subid or ""))[:50].strip("_")
    if not sid:
        return url
    return url + ("&" if "?" in url else "?") + "subid=" + sid


NOTICE = ('<p class="coupang-notice" style="font-size:12px;color:#98a2b3;margin:10px 0 4px;'
          'padding:8px 12px;background:#fafbfc;border-left:3px solid #ff5a5f">'
          '이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>')


def card_html(product, subid, with_notice=True):
    """상품 링크 카드. 광고처럼 보이지 않게 '확인용 링크' 톤을 유지한다.
    rel='sponsored nofollow'는 검색엔진 정책 준수(제휴 링크 표기 의무)."""
    url = with_subid(product.get("coupang_url") or "", subid)
    if not url:
        return ""
    name = product.get("name") or product.get("key") or "추천 상품"
    band = product.get("price_band") or ""
    note = product.get("note") or "가격·재고는 수시로 바뀌므로 구매 전 상세페이지에서 확인하세요."
    card = (
        '<div class="pick-product" style="margin:22px 0;padding:14px 16px;border:1px solid #e5e7eb;'
        'border-radius:12px;background:#fafbfc">'
        f'<div style="font-size:12px;color:#98a2b3;margin-bottom:4px">이 글에서 다룬 제품</div>'
        f'<div style="font-weight:700;font-size:15px;margin-bottom:2px">{name}</div>'
        + (f'<div style="font-size:13px;color:#667085;margin-bottom:8px">{band}</div>' if band else '')
        + f'<a href="{url}" target="_blank" rel="sponsored nofollow noopener" '
          'style="display:inline-block;padding:9px 16px;border-radius:9px;background:#2e9e6b;'
          'color:#fff;font-size:14px;font-weight:600;text-decoration:none">쿠팡에서 가격 확인</a>'
        f'<div style="font-size:12px;color:#98a2b3;margin-top:8px">{note}</div>'
        '</div>'
    )
    return (NOTICE + card) if with_notice else card


def missing(articles):
    """제품은 식별됐는데 링크가 아직 없는 글 — 앱 '오늘 할 일'이 읽는다."""
    out = []
    for a in articles or []:
        p = find_for(a)
        if p and not (p.get("coupang_url") or "").strip():
            out.append({"title": (a.get("title") or "")[:40],
                        "slug": a.get("slug", ""),
                        "product": p.get("key", ""),
                        "search": "https://www.coupang.com/np/search?q=" +
                                  (p.get("search") or p.get("key") or "")})
    return out
