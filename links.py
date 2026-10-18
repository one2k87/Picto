"""
links.py - 주제별 '실제로 존재하는' 참고 링크 1~2개를 검색해서 가져온다.
LLM이 만든 가짜 URL 대신 검색 결과의 진짜 링크를 쓰기 위함.
설치: pip install ddgs   (DuckDuckGo 검색, API 키 불필요)
검색 모듈이 없거나 실패하면 빈 리스트를 반환하고, generator가 안전하게 처리한다.
"""


def find_reference_links(query, max_results=2):
    """주어진 검색어로 실제 웹 링크 목록을 반환. [{title, url}]"""
    results = []
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results * 2):
                url = r.get("href") or r.get("url") or ""
                title = r.get("title") or ""
                if url.startswith("http"):
                    results.append({"title": title.strip(), "url": url.strip()})
                if len(results) >= max_results:
                    break
    except Exception as e:
        print(f"[links] 검색 실패('{query}'): {e}")
    return results


# ── 권위 판정 (2026-10-19, scripts/enrich_posts.py 에서 승격) ──────────
# 보강 경로에만 있던 필터를 leaf 모듈로 내린다. 생성 경로에는 필터가 아예
# 없어서, 새 글이 DDG 가 준 주소를 그대로 걸고 있었다 — 2026-10-19 전수 점검:
# 36편 중 15편(42%)이 비권위 외부 링크 28개를 달고 있었다. 내역은 경쟁 제휴
# 블로그(choicemon·ittemlab·homegrade·subir…), 네이버/티스토리/블로그스팟,
# 그리고 **모델이 지어낸 example.com·yourblog.com**. 한 곳에서 정의하고
# 생성·보강 양쪽이 같은 기준을 쓰게 한다.
import re as _re

# 어떤 출처를 '1차 출처'로 볼 것인가 (2026-10-13).
# 첫 실전에서 모델이 가져온 출처가 네이버 블로그·티스토리·팁 모음 사이트였다.
# 색인/미색인을 가른 지표는 '외부 링크 수'가 아니라 **권위 있는 출처를 인용했는가**다.
# 블로그를 걸면 숫자만 늘고 신뢰 신호는 안 생긴다 — 그래서 도메인으로 거른다.
_DENY = ("blog.naver.com", "cafe.naver.com", "tistory.com", "brunch.co.kr", "velog.io",
         "medium.com", "wordpress.com", "blogspot.", "post.naver.com", "in.naver.com",
         "namu.wiki", "pinterest.", "youtube.com", "facebook.com", "instagram.com",
         "coupang.com", "11st.co.kr", "gmarket.co.kr", "auction.co.kr", "smartstore.naver.com")
# 2026-10-16 실전 사고 — 러너(미국 IP)에서 돌린 보강이 본문에 이런 걸 걸었다:
#   #625 직수 정수기  → en.wikipedia.org/wiki/Microsoft · irs.gov/payments/...
#   #325 미니세탁기   → en.wikipedia.org/wiki/1 · simple.wikipedia.org/wiki/1_(number)
# 전부 authoritative() 와 _specific() 을 **정상 통과**했다(.gov 접미사 / '/wiki/' 포함).
# 권위와 관련성은 다른 축인데 권위만 봤다. 아무 출처도 없는 것보다 나쁘다.
# 픽담은 한국 소비자 블로그다 — 미 연방기관·영문 위키는 어떤 경우에도 출처가
# 아니다. 그래서 허용 목록 자체를 한국 출처로 좁힌다.
_ALLOW_SUFFIX = (".go.kr", ".or.kr", ".re.kr", ".ac.kr")
_ALLOW_HOST = ("kepco.co.kr", "energy.or.kr", "kemco.or.kr", "kca.go.kr", "ftc.go.kr",
               "kats.go.kr", "standard.go.kr", "data.go.kr", "law.go.kr", "nts.go.kr",
               "consumer.go.kr", "safetykorea.kr", "kssn.net",
               "samsung.com", "lge.co.kr", "coway.com", "cuckoo.co.kr", "winix.com",
               "ko.wikipedia.org")


def authoritative(url):
    """공공기관·법령·표준·제조사 공식·백과만 1차 출처로 본다. 블로그·쇼핑몰은 거른다."""
    u = (url or "").lower()
    host = u.split("//", 1)[-1].split("/", 1)[0]
    if any(d in host for d in _DENY):
        return False
    return host.endswith(_ALLOW_SUFFIX) or any(h in host for h in _ALLOW_HOST)


def strip_denied_links(html):
    """블로그·쇼핑몰로 걸린 외부 링크는 글자만 남기고 걷어낸다(재보강 때 자가 정리)."""
    def un(m):
        return m.group(2)
    return _re.sub(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                  lambda m: un(m) if (("pickdam.com" not in m.group(1))
                                      and ("coupang" not in m.group(1))
                                      and not authoritative(m.group(1))) else m.group(0),
                  html, flags=_re.S)
