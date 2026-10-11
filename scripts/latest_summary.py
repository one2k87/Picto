# -*- coding: utf-8 -*-
"""latest.json 의 '생성일 생성편수'를 한 줄로 찍는다 (워크플로 중복 가드용).

왜 파일로 뺐나: 워크플로 `run: |` 블록 안에 여러 줄 파이썬을 넣으면 들여쓰기가
YAML 블록 스칼라를 깨서 워크플로 자체가 파싱되지 않는다(2026-10-08 실측).
"""
import json
import sys

# 2026-10-11: '생성 편수'를 세던 탓에 10/10·10/11 백업 실행이 또 막혔다.
# 품질 게이트에서 폐기된 글도 articles 에 남으므로 len() 은 1 이 되고,
# 가드는 '이미 1편 생성 완료'로 판단해 건너뛴다 — 그날 발행은 0편.
# 백업 실행의 목적은 '글이 실제로 올라갔는가'이므로 **게시된 것만** 센다.
try:
    d = json.load(open("dashboard/data/latest.json", encoding="utf-8"))
    arts = d.get("articles") or []
    published = sum(1 for a in arts if (a.get("status") or "") == "게시됨")
    print((d.get("generated_at") or "")[:10], published)
except Exception:
    print("", 0)
sys.exit(0)
