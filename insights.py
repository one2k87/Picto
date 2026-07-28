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


def search_console(cfg, creds, days=28, top=10):
    site = cfg.get("sc_site_url")
    if not site:
        return {}
    try:
        svc = _build("searchconsole", "v1", creds)
        end = date.today() - timedelta(days=2)     # 데이터 지연 반영
        start = end - timedelta(days=days)
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
                "dimensions": ["query"], "rowLimit": top}
        q = svc.searchanalytics().query(siteUrl=site, body=body).execute()
        queries = [{"query": r["keys"][0], "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0)} for r in q.get("rows", [])]
        body["dimensions"] = ["page"]
        p = svc.searchanalytics().query(siteUrl=site, body=body).execute()
        pages = [{"page": r["keys"][0], "clicks": r.get("clicks", 0),
                  "impressions": r.get("impressions", 0)} for r in p.get("rows", [])]
        print(f"[insights] Search Console: 검색어 {len(queries)} · 페이지 {len(pages)}")
        return {"queries": queries, "pages": pages}
    except Exception as e:
        print(f"[insights] Search Console 실패: {e}")
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


def adsense(cfg, creds, days=28):
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
    creds = _creds(icfg)
    if not creds:
        return {}
    out = {"updated_at": date.today().isoformat()}
    sc = search_console(icfg, creds)
    if sc:
        out["search_console"] = sc
    g = ga4(icfg, creds)
    if g:
        out["ga4"] = g
    a = adsense(icfg, creds)
    if a:
        out["adsense"] = a
    return out if len(out) > 1 else {}


def winner_topics(insights, limit=8):
    """유입 상위 검색어 → 주제 선정 피드백용 문자열 목록."""
    qs = (insights.get("search_console", {}) or {}).get("queries", [])
    return [q["query"] for q in qs[:limit] if q.get("query")]
