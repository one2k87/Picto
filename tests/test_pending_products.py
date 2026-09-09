# -*- coding: utf-8 -*-
"""products.pending() — 링크 있는데 글 없는 제품 자동 검출 (2026-09-08)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import products
import topics

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("  ✗", name)


products._CACHE = {"products": [
    {"key": "가", "name": "가제품", "search": "가 검색", "match": ["가제품"],
     "coupang_url": "https://link.coupang.com/a/AAA"},
    {"key": "나", "name": "나제품", "search": "나 검색", "match": ["나제품"],
     "coupang_url": "https://link.coupang.com/a/BBB"},
    {"key": "다", "name": "다제품", "search": "다 검색", "match": ["다제품"],
     "coupang_url": ""},                      # 링크 없음 → 대기 목록에서 제외
]}

arts = [{"title": "가제품 고르는 법", "keyword": ""}]
pend = products.pending(arts)
keys = [p["key"] for p in pend]
check("글 있는 제품은 빠진다", "가" not in keys)
check("글 없는 제품은 잡힌다", "나" in keys)
check("링크 없는 제품은 제외된다", "다" not in keys)

check("글이 하나도 없으면 링크 있는 것 전부", 
      [p["key"] for p in products.pending([])] == ["가", "나"])

pr = topics.build_topic_prompt("생활", "설명", "long", 3, must_products=pend)
check("프롬프트에 제품명 주입", "나제품" in pr)
check("프롬프트에 구매 검색어 주입", "나 검색" in pr)
check("must_products 없으면 블록 없음",
      "최우선" not in topics.build_topic_prompt("생활", "설명", "long", 3))
check("링크 없는 제품은 프롬프트에도 안 뜬다", "다제품" not in pr)

# ── 안전망: match를 부속품에 뺏긴 제품이 무한 대기로 남지 않는가 (2026-09-09) ──
products._CACHE = {"products": [
    {"key": "본체", "name": "본체", "search": "비데 자가설치형", "match": ["비데"],
     "coupang_url": "https://link.coupang.com/a/AAA"},
    {"key": "부속", "name": "부속", "search": "비데 분기밸브", "match": ["비데 자가 설치"],
     "coupang_url": "https://link.coupang.com/a/BBB"},
]}
arts2 = [{"title": "비데 자가 설치 비용 절약", "keyword": "비데 자가설치형 고르는 법"}]
check("긴 match가 이긴다(전제 확인)", products.find_for(arts2[0])["key"] == "부속")
check("검색어가 이미 나온 제품은 대기에서 빠진다",
      "본체" not in [x["key"] for x in products.pending(arts2)])
check("정말 안 다룬 제품은 남는다",
      "부속" not in [x["key"] for x in products.pending(arts2)])

products._CACHE = {"products": [
    {"key": "가", "name": "가", "search": "제습기 20L", "match": ["제습기"],
     "coupang_url": "https://link.coupang.com/a/CCC"},
]}
check("무관한 글이면 대기 유지",
      [x["key"] for x in products.pending([{"title": "정수기 필터", "keyword": ""}])] == ["가"])

products._CACHE = None
print(f"test_pending_products: {ok} pass / {fail} fail")
sys.exit(1 if fail else 0)
