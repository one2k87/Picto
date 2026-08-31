"""URL Inspection API로 '색인 요청'을 재발명한다 (2026-08-31).

왜 이 방식인가 — 색인 요청 버튼의 목적은 결국 두 가지다:
  ① 구글이 이 URL을 다시 가져가게(재크롤) 만드는 것
  ② 색인됐는지 확인하는 것
버튼에는 API가 없지만, URL Inspection API(하루 2,000회)는
  ①을 부분적으로 대체하고(검사가 구글의 페이지 fetch를 유발해 재크롤을
     앞당기는 효과가 보고돼 있다 — 보장은 아님),
  ②를 완전히 대체한다(verdict·마지막 크롤 시각·색인 상태를 그대로 준다).
게다가 insights.py가 쓰는 서비스 계정을 그대로 재사용하므로 추가 세팅이 0이다.

매일 실행: 최근 수정 글을 검사 → dashboard/data/index_status.json에 신호등 기록
(결과 커밋 단계가 저장소에 올려 대시보드가 읽는다).
덤: 사이트맵 재제출(sitemaps.submit)도 시도한다 — 쓰기 권한이 없으면 조용히 건너뜀.
"""
import json
import datetime

import requests

cfg = json.load(open("config.json", encoding="utf-8"))
ins = cfg.get("insights", {}) or {}
site = (cfg.get("wordpress", {}) or {}).get("site_url", "").rstrip("/")
sc_site = (ins.get("sc_site_url") or site).rstrip("/") + "/"

raw = ins.get("service_account_json") or ""
if not raw or not site or "your-blog" in site:
    print("[inspect] 서비스 계정 또는 site_url 없음 — 건너뜀")
    raise SystemExit(0)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = json.loads(raw) if raw.strip().startswith("{") else json.load(open(raw, encoding="utf-8"))
    # inspect는 readonly로 충분, sitemaps.submit은 쓰기 스코프 필요 → 둘 다 요청
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/webmasters"])
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
except Exception as e:
    print(f"[inspect] 인증 실패: {e}")
    raise SystemExit(0)

# 최근 14일 내 수정된 공개 글 (검사 우선순위 = 최근 손본 순, 최대 30개/일)
try:
    r = requests.get(f"{site}/wp-json/wp/v2/posts",
                     params={"per_page": 30, "status": "publish",
                             "orderby": "modified", "_fields": "link,modified"},
                     timeout=20)
    posts = r.json() if r.ok else []
except Exception as e:
    print(f"[inspect] 글 목록 실패: {e}")
    posts = []

cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
urls = [site + "/"] + [p["link"] for p in posts if p.get("modified", "") >= cutoff]

results, ok_n = [], 0
for u in urls[:30]:
    try:
        res = svc.urlInspection().index().inspect(
            body={"inspectionUrl": u, "siteUrl": sc_site}).execute()
        idx = (res.get("inspectionResult", {}) or {}).get("indexStatusResult", {}) or {}
        verdict = idx.get("verdict", "?")            # PASS = 색인됨
        results.append({"url": u, "verdict": verdict,
                        "state": idx.get("coverageState", ""),
                        "lastCrawl": (idx.get("lastCrawlTime") or "")[:10]})
        ok_n += 1
    except Exception as e:
        results.append({"url": u, "verdict": "ERROR", "state": str(e)[:100], "lastCrawl": ""})

passed = sum(1 for x in results if x["verdict"] == "PASS")
out = {"updated_at": datetime.datetime.now().isoformat()[:19],
       "site": site, "checked": ok_n, "indexed": passed, "results": results}
json.dump(out, open("dashboard/data/index_status.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[inspect] {ok_n}개 검사 — 색인됨 {passed} / 미색인 {ok_n - passed}")

# 사이트맵 재제출(크롤 넛지) — 권한 없으면 건너뜀
try:
    svc.sitemaps().submit(siteUrl=sc_site, feedpath=f"{site}/wp-sitemap.xml").execute()
    print("[inspect] 사이트맵 재제출 완료")
except Exception as e:
    print(f"[inspect] 사이트맵 재제출 건너뜀({str(e)[:60]})")
