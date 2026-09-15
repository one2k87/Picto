# -*- coding: utf-8 -*-
"""네이버 검색광고 API 403 원인 가르기 (2026-09-15).

키 값 자체는 절대 기록하지 않는다 — 길이·공백 여부·서명 변형별 응답 코드만 남긴다.
(403 응답 본문에 액세스라이선스가 그대로 들어오는 것을 실측했다.)
결과: dashboard/data/demand_auth_check.json
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

cfg = json.load(open("config.json", encoding="utf-8"))
c = cfg.get("demand") or {}
raw_key, raw_sec, raw_cid = c.get("api_key", ""), c.get("secret", ""), str(c.get("customer_id", ""))
key, sec, cid = raw_key.strip(), raw_sec.strip(), raw_cid.strip()

BASE, PATH = "https://api.searchad.naver.com", "/keywordstool"


def call(ts, msg, signer_name, sig):
    try:
        r = requests.get(BASE + PATH, params={"hintKeywords": "제습기", "showDetail": "1"},
                         headers={"X-Timestamp": ts, "X-API-KEY": key, "X-Customer": cid,
                                  "X-Signature": sig}, timeout=15)
        body = ""
        try:
            j = r.json()
            body = f"{j.get('type','')}|{j.get('title','')}"
        except Exception:
            body = "(json 아님)"
        n = None
        if r.status_code == 200:
            n = len((r.json() or {}).get("keywordList") or [])
        return {"variant": signer_name, "http": r.status_code, "err": body[:90], "rows": n}
    except Exception as e:
        return {"variant": signer_name, "http": None, "err": f"{type(e).__name__}"[:60]}


results = []
ts = str(int(time.time() * 1000))
msg = f"{ts}.GET.{PATH}"
# ① 표준: base64(hmac-sha256(secret, msg))
sig1 = base64.b64encode(hmac.new(sec.encode(), msg.encode(), hashlib.sha256).digest()).decode()
results.append(call(ts, msg, "표준(digest→b64)", sig1))
# ② hexdigest를 b64로(잘못 구현했을 때 흔한 형태) — 대조용
time.sleep(0.5)
ts2 = str(int(time.time() * 1000))
msg2 = f"{ts2}.GET.{PATH}"
sig2 = base64.b64encode(hmac.new(sec.encode(), msg2.encode(), hashlib.sha256).hexdigest().encode()).decode()
results.append(call(ts2, msg2, "hexdigest→b64", sig2))
# ③ 공백 제거 안 한 원본 값으로 — 붙여넣기 공백이 범인인지 가른다
time.sleep(0.5)
ts3 = str(int(time.time() * 1000))
msg3 = f"{ts3}.GET.{PATH}"
sig3 = base64.b64encode(hmac.new(raw_sec.encode(), msg3.encode(), hashlib.sha256).digest()).decode()
key_bak = key
key = raw_key
results.append(call(ts3, msg3, "원본(strip 안 함)", sig3))
key = key_bak

out = {
    "shape": {
        "api_key_len": len(raw_key), "api_key_stripped_len": len(key),
        "secret_len": len(raw_sec), "secret_stripped_len": len(sec),
        "customer_id_len": len(raw_cid), "customer_id_digits": cid.isdigit(),
        "공백_딸려옴": (len(raw_key) != len(key)) or (len(raw_sec) != len(sec)) or (len(raw_cid) != len(cid)),
    },
    "results": results,
}
os.makedirs("dashboard/data", exist_ok=True)
json.dump(out, open("dashboard/data/demand_auth_check.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
