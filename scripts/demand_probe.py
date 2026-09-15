# -*- coding: utf-8 -*-
"""검색 수요 조회가 실제로 쓸 만한지 **믿기 전에 확인**한다 (2026-09-15 신설).

왜: 게이트를 켜 놓고 실제 신호를 본 적이 없으면, 좋은 주제를 조용히 버리게 된다.
    이 레포에서 액션 로그는 되읽기 어려우므로 결과를 파일로 남긴다(콕픽 소급 때와 같은 이유).
결과: dashboard/data/demand_probe.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import demand

SAMPLES = [
    "제습기 20L",                    # 대장 제품 — 수요가 있어야 정상
    "음식물처리기 탈취필터",
    "비데 자가설치",
    "창문 단열 뽁뽁이",
    "현관문 문풍지",
    "정수기 필터 교체",
    "포장이사 비용",                 # 비커머스지만 수요는 큼
    "비데 분기밸브 설치 공구 세트",   # 대장의 긴 검색어 — 수요 0에 가까울 것
    "음식물처리기 렌탈 36개월 약정 위약금",  # 우리가 실제로 쓴 롱테일 제목형
]

cfg = json.load(open("config.json", encoding="utf-8"))
naver = bool((cfg.get("demand") or {}).get("api_key"))
vol = demand.monthly_volume(SAMPLES, cfg) if naver else {}
sug = {k: demand.suggest_hits(k) for k in SAMPLES}

rows = [{"keyword": k, "naver_monthly": vol.get(k), "suggest": sug.get(k)} for k in SAMPLES]
cid = str((cfg.get("demand") or {}).get("customer_id", ""))
out = {"naver_key": naver, "min_volume": (cfg.get("demand") or {}).get("min_volume"),
       "last_error": demand.LAST_ERR,
       "key_shape": {"api_key_len": len((cfg.get("demand") or {}).get("api_key", "")),
                     "secret_len": len((cfg.get("demand") or {}).get("secret", "")),
                     "customer_id_len": len(cid), "customer_id_digits": cid.isdigit()},
       "rows": rows}
os.makedirs("dashboard/data", exist_ok=True)
json.dump(out, open("dashboard/data/demand_probe.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"네이버 키 {'있음' if naver else '없음'} · 마지막 오류: {demand.LAST_ERR[:200]}")
for r in rows:
    print(f"  {r['keyword'][:28]:<30} 네이버={r['naver_monthly']} 자동완성={r['suggest']}")
