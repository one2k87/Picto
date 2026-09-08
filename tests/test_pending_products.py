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

products._CACHE = None
print(f"test_pending_products: {ok} pass / {fail} fail")
sys.exit(1 if fail else 0)
