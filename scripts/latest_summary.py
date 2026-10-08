# -*- coding: utf-8 -*-
"""latest.json 의 '생성일 생성편수'를 한 줄로 찍는다 (워크플로 중복 가드용).

왜 파일로 뺐나: 워크플로 `run: |` 블록 안에 여러 줄 파이썬을 넣으면 들여쓰기가
YAML 블록 스칼라를 깨서 워크플로 자체가 파싱되지 않는다(2026-10-08 실측).
"""
import json
import sys

try:
    d = json.load(open("dashboard/data/latest.json", encoding="utf-8"))
    print((d.get("generated_at") or "")[:10], len(d.get("articles") or []))
except Exception:
    print("", 0)
sys.exit(0)
