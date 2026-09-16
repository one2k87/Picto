# -*- coding: utf-8 -*-
"""콕픽 교집합 판정을 갱신한다 (2026-09-16).

캐스토가 **찍기 전에** CTA 목적지(픽담 개별 글 vs 쿠팡 직링크)를 정할 수 있도록
판정 결과를 `dashboard/data/casto_cross.json`에 올려둔다. 캐스토는 이 파일만 보면 된다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import casto_link

cfg = json.load(open("config.json", encoding="utf-8"))
if not (cfg.get("demand") or {}).get("api_key"):
    print("네이버 키 없음 — 판정 불가(건너뜀)"); raise SystemExit(0)
res = casto_link.save(cfg)
for r in res.get("rows", [])[:40]:
    b = r.get("best") or {}
    print(f"  {r['tier']:<5} {r['product'][:20]:<22} {r['cta']:<10}"
          + (f" {b.get('keyword','')[:14]} {b.get('volume',0):,}" if b else ""))
