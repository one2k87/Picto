# -*- coding: utf-8 -*-
"""검색 수요 조회 — 네이버 검색광고 키워드도구 (2026-09-15 신설).

왜 만들었나(실측):
  픽담은 3개월 동안 20편을 냈는데 **총 노출 51회·클릭 3회**였다.
  그런데 **평균 게재순위는 7위**다 — 순위가 1페이지 근처인데 노출이 안 나온다는 건
  보통 '그 검색어를 아무도 치지 않는다'는 뜻이다. 지금까지 주제는 제품 대장과 LLM이
  정했을 뿐 **실제 검색량을 한 번도 보지 않았다**. 그대로 100편을 써도 결과는 같다.

무엇을 하나:
  후보 키워드의 월간 검색량(PC+모바일)을 받아, 기준 미달 주제를 **생성 전에** 버린다.
  네이버를 쓰는 이유: 쿠팡 구매 검색은 네이버 비중이 크고, 키워드도구가 무료다.

안전 규칙(중요):
  - 키가 없거나 호출이 실패하면 **아무것도 거르지 않는다**(빈 dict 반환).
    수요 조회가 죽었다고 그날 발행이 멈추면 안 된다.
  - 조회 결과가 전부 기준 미달이어도 **최소 1건은 남긴다**(호출부 책임).
  - '< 10'처럼 문자열로 오는 값이 있어 숫자로 정규화한다.
"""
import hashlib
import hmac
import base64
import json
import os
import re
import time

import requests

BASE = "https://api.searchad.naver.com"
PATH = "/keywordstool"
_CACHE = {}
LAST_ERR = ""      # 조회 실패 사유(진단용) — 액션 로그를 되읽기 어려워 파일로 남긴다


def _redact(body):
    """오류 본문에서 자격증명을 지우고 종류만 남긴다."""
    try:
        j = json.loads(body or "{}")
        return f"{j.get('type','')} | {j.get('title','')}"[:120]
    except Exception:
        return re.sub(r"[0-9a-zA-Z+/=]{20,}", "<redacted>", (body or ""))[:120]


def _sig(ts, method, path, secret):
    msg = f"{ts}.{method}.{path}"
    return base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()


def _num(v):
    """'< 10' · '1,234' · 990 → 정수."""
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[^0-9]", "", str(v or ""))
    return int(s) if s else 0


def _clean(kw):
    """키워드도구는 공백·특수문자를 싫어한다. 조회용으로만 정리한다."""
    return re.sub(r"\s+", "", re.sub(r"[^0-9A-Za-z가-힣\s]", " ", kw or "")).strip()


def monthly_volume(keywords, cfg):
    """{키워드: 월간 검색량}. 조회 불가·실패면 빈 dict(= 거르지 않음)."""
    c = (cfg or {}).get("demand") or {}
    key, sec, cid = c.get("api_key", ""), c.get("secret", ""), str(c.get("customer_id", ""))
    if not (key and sec and cid):
        return {}
    out = {}
    for kw in keywords:
        q = _clean(kw)
        if not q:
            continue
        if q in _CACHE:
            out[kw] = _CACHE[q]
            continue
        try:
            ts = str(int(time.time() * 1000))
            r = requests.get(BASE + PATH,
                             params={"hintKeywords": q[:20], "showDetail": "1"},
                             headers={"X-Timestamp": ts, "X-API-KEY": key,
                                      "X-Customer": cid,
                                      "X-Signature": _sig(ts, "GET", PATH, sec)},
                             timeout=15)
            if r.status_code != 200:
                global LAST_ERR
                # ⚠️ 응답 본문을 그대로 남기면 안 된다 — 네이버 403 본문에는
                # **액세스라이선스 값이 그대로 들어온다**(2026-09-15 실측, 공개 레포에 커밋될 뻔했다).
                # 진단에 필요한 건 상태코드와 오류 종류뿐이므로 그것만 남긴다.
                LAST_ERR = f"HTTP {r.status_code} / {_redact(r.text)}"
                print(f"[demand] 조회 실패 {r.status_code} ({q[:14]}) — {_redact(r.text)}")
                continue
            rows = (r.json() or {}).get("keywordList") or []
            # 완전 일치가 있으면 그 값, 없으면 가장 비슷한 첫 줄
            hit = next((x for x in rows if _clean(x.get("relKeyword")) == q), rows[0] if rows else None)
            if not hit:
                continue
            v = _num(hit.get("monthlyPcQcCnt")) + _num(hit.get("monthlyMobileQcCnt"))
            _CACHE[q] = v
            out[kw] = v
            time.sleep(0.3)                      # 초당 호출 제한 회피
        except Exception as e:
            LAST_ERR = f"{type(e).__name__}: {e}"[:220]
            print(f"[demand] 조회 예외({q[:14]}): {str(e)[:100]} — 거르지 않음")
    return out


SUGGEST = "https://suggestqueries.google.com/complete/search"


def suggest_hits(keyword, timeout=8):
    """키 없이 쓰는 **대리 신호** — 구글 자동완성에 이 말이 뜨는가.

    ⚠️ 이건 검색량이 아니다. 자동완성은 '실제로 입력된 적이 있는 질의'에서 만들어지므로
    **0건이면 아무도 안 친다는 쪽의 증거**가 되지만, 건수가 많다고 검색량이 크다는 뜻은 아니다.
    그래서 숫자 기준으로 자르지 않고 '신호가 아예 없는 후보'만 걸러내는 데만 쓴다.
    네이버 키가 등록되면 이 함수는 쓰이지 않는다(실측 검색량이 언제나 우선).
    """
    q = _clean(keyword)[:30]
    if not q:
        return 0
    try:
        r = requests.get(SUGGEST, params={"client": "firefox", "hl": "ko", "q": keyword},
                         timeout=timeout)
        if r.status_code != 200:
            return -1                      # -1 = 판단 불가(거르지 않는다)
        data = json.loads(r.text)
        return len(data[1]) if isinstance(data, list) and len(data) > 1 else 0
    except Exception:
        return -1


def _suggest_filter(cands, key):
    """자동완성 신호가 **0인 후보만** 버린다. 전부 0이면 손대지 않는다."""
    hits = {}
    for c in cands:
        hits[c.get(key, "")] = suggest_hits(c.get(key, ""))
        time.sleep(0.2)
    keep = [c for c in cands if hits.get(c.get(key, ""), -1) != 0]
    if not keep:
        return cands, hits, 0              # 전부 0이면 조회가 이상한 것 — 그냥 통과
    return keep, hits, len(cands) - len(keep)


def filter_by_demand(cands, cfg, key="keyword"):
    """검색량 기준 미달 후보를 버린다. 전부 미달이면 가장 큰 것 1건만 남긴다.
    반환: (남은 후보, 조회된 검색량 dict, 버린 수)"""
    c = (cfg or {}).get("demand") or {}
    if not c.get("enabled", True) or not cands:
        return cands, {}, 0
    vol = monthly_volume([x.get(key, "") for x in cands], cfg)
    if not vol:
        # 네이버 키가 없을 때의 대비책: 자동완성 신호가 0인 후보만 버린다.
        # 검색량이 아니라 대리 신호이므로 '전혀 안 뜨는 것'만 거른다(위 주석 참조).
        if c.get("suggest_fallback", True):
            keep, hits, cut = _suggest_filter(cands, key)
            if cut:
                print(f"[demand] 네이버 키 없음 → 자동완성 대리 신호로 {cut}개 제외")
            return keep, {}, cut
        return cands, {}, 0                      # 조회 자체가 안 됐으면 건드리지 않는다
    floor = int(c.get("min_volume", 100))
    keep = [x for x in cands if vol.get(x.get(key, ""), 0) >= floor]
    if not keep:
        best = max(cands, key=lambda x: vol.get(x.get(key, ""), 0))
        print(f"[demand] 전부 월 {floor}회 미만 — 그중 가장 큰 것 하나만 남긴다: "
              f"{best.get(key,'')[:22]}({vol.get(best.get(key,''),0)})")
        return [best], vol, len(cands) - 1
    return keep, vol, len(cands) - len(keep)
