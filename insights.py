"""
insights.py - 성과·수익 실측 연동(무료 API).

세 가지를 각각 '선택적으로' 가져온다(설정 없으면 조용히 건너뜀):
  - Google Search Console : 유입 상위 글/검색어(클릭·노출)
  - Google Analytics 4    : 조회 상위 페이지
  - Google AdSense        : 실제 수익/노출/클릭

인증: 하나의 '서비스 계정' JSON 으로 세 API 를 함께 사용.
  config.insights = {
    "service_account_json": "...(JSON 문자열)...",   # 또는 파일경로
    "sc_site_url": "https://내블로그.com/",           # Search Console 속성
    "ga4_property_id": "123456789",                   # GA4 속성 ID(숫자)
    "adsense_account": "pub-XXXXXXXX"                 # 선택(없으면 계정 자동탐색)
  }
결과는 dashboard/data/insights.json 으로 저장하고, 상위 검색어는
주제 선정 피드백(잘 되는 주제 우대)에 재사용한다.
"""

import os
import json
from datetime import date, timedelta

_SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/adsense.readonly",
]


def _creds(cfg):
    raw = (cfg or {}).get("service_account_json") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
        if os.path.exists(str(raw)):
            info = json.load(open(raw, encoding="utf-8"))
        else:
            info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    except Exception as e:
        print(f"[insights] 서비스계정 로드 실패: {e}")
        return None


def _build(api, version, creds):
    from googleapiclient.discovery import build
    return build(api, version, credentials=creds, cache_discovery=False)


def _sc_forms(site):
    """속성 주소 후보. 도메인 속성은 `sc-domain:` 형식만 받는다.

    2026-09-30 실측: 기본값이 WP_SITE(=https://pickdam.com)라 **403 'You do not own
    this site'**로 조용히 실패하고 있었다. 그 결과 insights.json이 28일 넘게 `{}`였고,
    strategy.json은 `no_data`로 멈춰 있었으며, 주제 프롬프트의 '성과 피드백(winners)'도
    빈 채로 돌았다. URL 검사 쪽(scripts/inspect_recent.py)은 이미 같은 자동 판별을
    하고 있었는데 이쪽만 빠져 있었다 — 같은 함정을 두 번 밟았다.
    """
    import re as _re
    site = (site or "").strip()
    out = []
    if site:
        out.append(site)
    host = site[len("sc-domain:"):] if site.startswith("sc-domain:") else site
    host = _re.sub(r"^https?://", "", host).strip("/").split("/")[0]
    host = _re.sub(r"^www\.", "", host)
    if host:
        for f in (f"sc-domain:{host}", f"https://{host}/", f"https://www.{host}/"):
            if f not in out:
                out.append(f)
    return out


def search_console(cfg, creds, days=28, top=25):
    site = cfg.get("sc_site_url")
    if not site:
        print("[insights] Search Console 건너뜀: sc_site_url 이 비어 있다"
              " (SC_SITE_URL / GSC_SITE_URL / WP_SITE 중 하나가 워크플로에 전달돼야 한다)")
        return {}
    svc = None
    end = date.today() - timedelta(days=2)     # 데이터 지연 반영
    start = end - timedelta(days=days)
    last = ""
    for form in _sc_forms(site):
        try:
            if svc is None:
                svc = _build("searchconsole", "v1", creds)
            body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
                    "dimensions": ["query"], "rowLimit": top}
            q = svc.searchanalytics().query(siteUrl=form, body=body).execute()
            queries = [{"query": r["keys"][0], "clicks": r.get("clicks", 0),
                        "impressions": r.get("impressions", 0)} for r in q.get("rows", [])]
            body["dimensions"] = ["page"]
            p = svc.searchanalytics().query(siteUrl=form, body=body).execute()
            pages = [{"page": r["keys"][0], "clicks": r.get("clicks", 0),
                      "impressions": r.get("impressions", 0),
                      "ctr": round(r.get("ctr", 0) * 100, 2),
                      "position": round(r.get("position", 0), 1)} for r in p.get("rows", [])]

            # 합계와 일자별 추이 (2026-10-07 추가).
            # 왜: 지금까지 상위 10줄만 저장해서 '사이트 전체가 늘고 있나'를 볼 수가 없었다.
            # 사용자가 워드프레스에서 통계를 찾다가 못 찾은 것도 같은 구멍이다.
            def _tot(d0, d1):
                try:
                    r = svc.searchanalytics().query(siteUrl=form, body={
                        "startDate": d0.isoformat(), "endDate": d1.isoformat(),
                        "dimensions": []}).execute()
                    rows = r.get("rows", [])
                    if not rows:
                        return {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
                    x = rows[0]
                    return {"clicks": int(x.get("clicks", 0)),
                            "impressions": int(x.get("impressions", 0)),
                            "ctr": round(x.get("ctr", 0) * 100, 2),
                            "position": round(x.get("position", 0), 1)}
                except Exception:
                    return {}

            daily = []
            try:
                d90 = end - timedelta(days=90)
                r = svc.searchanalytics().query(siteUrl=form, body={
                    "startDate": d90.isoformat(), "endDate": end.isoformat(),
                    "dimensions": ["date"], "rowLimit": 200}).execute()
                daily = [{"date": x["keys"][0], "clicks": int(x.get("clicks", 0)),
                          "impressions": int(x.get("impressions", 0))}
                         for x in r.get("rows", [])]
            except Exception as e:
                print(f"[insights] 일자별 추이 건너뜀: {str(e)[:60]}")

            totals = {"d28": _tot(start, end),
                      "d90": _tot(end - timedelta(days=90), end),
                      "prev28": _tot(start - timedelta(days=days), start - timedelta(days=1))}
            print(f"[insights] Search Console({form}): 검색어 {len(queries)} · 페이지 {len(pages)}"
                  f" · 28일 클릭 {totals['d28'].get('clicks')} 노출 {totals['d28'].get('impressions')}"
                  f" · 일자 {len(daily)}일")
            return {"queries": queries, "pages": pages, "site_form": form,
                    "totals": totals, "daily": daily,
                    "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days}}
        except Exception as e:
            last = f"{form} → {str(e)[:110]}"
            continue
    print(f"[insights] Search Console 실패(후보 전부): {last}")
    return {}


def ga4(cfg, creds, days=28, top=10):
    pid = cfg.get("ga4_property_id")
    if not pid:
        return {}
    try:
        svc = _build("analyticsdata", "v1beta", creds)
        body = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "dimensions": [{"name": "pageTitle"}],
            "metrics": [{"name": "screenPageViews"}, {"name": "totalUsers"}],
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
            "limit": top,
        }
        r = svc.properties().runReport(property=f"properties/{pid}", body=body).execute()
        rows = [{"title": row["dimensionValues"][0]["value"],
                 "views": int(row["metricValues"][0]["value"]),
                 "users": int(row["metricValues"][1]["value"])}
                for row in r.get("rows", [])]
        print(f"[insights] GA4: 상위 페이지 {len(rows)}")
        return {"top_pages": rows}
    except Exception as e:
        print(f"[insights] GA4 실패: {e}")
        return {}


def _adsense_creds(cfg):
    """애드센스는 서비스계정 사용자 추가가 안 되므로 OAuth 리프레시 토큰을 쓴다."""
    rt = cfg.get("adsense_refresh_token") or os.getenv("ADSENSE_REFRESH_TOKEN")
    cid = cfg.get("oauth_client_id") or os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    cs = cfg.get("oauth_client_secret") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    if not (rt and cid and cs):
        return None
    try:
        from google.oauth2.credentials import Credentials
        return Credentials(
            None, refresh_token=rt, client_id=cid, client_secret=cs,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/adsense.readonly"])
    except Exception as e:
        print(f"[insights] 애드센스 OAuth 자격 생성 실패: {e}")
        return None


def adsense(cfg, creds, days=28):
    if creds is None:
        return {}
    try:
        svc = _build("adsense", "v2", creds)
        acct = cfg.get("adsense_account")
        if not acct:
            accts = svc.accounts().list().execute().get("accounts", [])
            if not accts:
                return {}
            acct = accts[0]["name"]           # "accounts/pub-XXXX"
        elif not str(acct).startswith("accounts/"):
            acct = f"accounts/{acct}"
        end = date.today()
        start = end - timedelta(days=days)
        rep = svc.accounts().reports().generate(
            account=acct,
            dateRange="CUSTOM",
            **{"startDate.year": start.year, "startDate.month": start.month, "startDate.day": start.day,
               "endDate.year": end.year, "endDate.month": end.month, "endDate.day": end.day},
            metrics=["ESTIMATED_EARNINGS", "IMPRESSIONS", "CLICKS", "PAGE_VIEWS"],
        ).execute()
        totals = rep.get("totals", {}).get("cells", [])
        keys = ["earnings", "impressions", "clicks", "page_views"]
        vals = {keys[i]: (totals[i].get("value") if i < len(totals) else "0") for i in range(len(keys))}
        cur = rep.get("headers", [{}])[0].get("currencyCode", "")
        print(f"[insights] AdSense: 수익 {vals.get('earnings')} {cur}")
        return {"earnings": vals.get("earnings", "0"), "currency": cur,
                "impressions": vals.get("impressions", "0"), "clicks": vals.get("clicks", "0"),
                "page_views": vals.get("page_views", "0"), "days": days}
    except Exception as e:
        print(f"[insights] AdSense 실패: {e}")
        return {}


def collect(cfg):
    """설정된 소스만 모아 dict 반환. 아무것도 없으면 {} (조용히)."""
    icfg = (cfg or {}).get("insights", {}) or {}
    creds = _creds(icfg)                    # Search Console·GA4용 서비스계정
    out = {"updated_at": date.today().isoformat()}
    if creds:
        sc = search_console(icfg, creds)
        if sc:
            out["search_console"] = sc
        g = ga4(icfg, creds)
        if g:
            out["ga4"] = g
    a = adsense(icfg, _adsense_creds(icfg))  # 애드센스는 OAuth 리프레시 토큰
    if a:
        out["adsense"] = a
    return out if len(out) > 1 else {}


def winner_topics(insights, limit=8):
    """유입 상위 검색어 → 주제 선정 피드백용 문자열 목록."""
    qs = (insights.get("search_console", {}) or {}).get("queries", [])
    return [q["query"] for q in qs[:limit] if q.get("query")]


if __name__ == "__main__":
    # 단독 실행(주간 전략 워크플로용): config.json을 읽어 성과를 모으고 insights.json에 저장
    import os as _os
    _cfg_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "config.json")
    try:
        with open(_cfg_path, encoding="utf-8") as _f:
            _cfg = json.load(_f)
    except Exception as _e:
        print(f"[insights] config.json을 읽지 못했습니다: {_e}")
        raise SystemExit(0)
    _out = collect(_cfg)
    _dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dashboard", "data")
    _os.makedirs(_dir, exist_ok=True)
    with open(_os.path.join(_dir, "insights.json"), "w", encoding="utf-8") as _f:
        json.dump(_out, _f, ensure_ascii=False, indent=2)
    print(f"[insights] 저장 완료 · 키: {list(_out.keys()) or '(수집된 데이터 없음)'}")
