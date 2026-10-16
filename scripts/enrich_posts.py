# -*- coding: utf-8 -*-
"""기존 글 보강 (2026-10-12 신설).

왜 만들었나 — 40편을 색인 27 / 미색인 13 으로 갈라 전수 비교했더니, 분량·H2·
내부링크는 **차이가 없었다**(3,593자 vs 3,685자 / 4.7 vs 5.2 / 6.2 vs 6.2).
갈린 것은 두 가지였다: **외부 1차 출처 인용 0.9 vs 0.2**, **목록 4.5 vs 1.6**.
구글 서치 센트럴 커뮤니티 가이드도 'Discovered - not indexed' 는 그 페이지의
문제가 아니라 **기존 콘텐츠가 더 크롤할 이유를 주지 못하는 것**이라고 말한다.
그래서 새 글을 늘리는 대신 있는 글을 끌어올린다.

무엇을 하나
  · 보강 대상 선정: 미색인 → 얇은 글 → 외부 인용 0 순서
  · 실제 검색으로 외부 출처를 찾아 **HTTP 200 으로 살아 있는 것만** 쓴다
  · 구조(목록·조건 분기·실수)와 수치를 보강한다
  · 상품 카드 마커·고지 문구·이미지는 그대로 보존한다(검증 실패 시 반영하지 않음)

환경: ENRICH_N(기본 2) · ENRICH_DRY(true면 계획만) · ENRICH_IDS(쉼표로 지정)
결과: dashboard/data/enrich_log.json
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import quality
from links import find_reference_links
from llm import chat
from publisher import _auth_header, update_post_content

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"}
DATA = os.path.join("dashboard", "data")
MARK = "<!--enriched:"
NOTICE = "쿠팡 파트너스 활동의 일환"


def _text(html):
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", html or ""))


def _profile(html):
    return {
        "chars": len(_text(html)),
        "h2": html.count("<h2"),
        "lists": html.count("<ul") + html.count("<ol"),
        "external": len([u for u in re.findall(r'href="(https?://[^"]+)"', html)
                         if "pickdam.com" not in u and "coupang" not in u]),
        "picklink": html.count("<!--picklink-->"),
        "img": html.count("<img"),
    }


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
    return re.sub(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                  lambda m: un(m) if (("pickdam.com" not in m.group(1))
                                      and ("coupang" not in m.group(1))
                                      and not authoritative(m.group(1))) else m.group(0),
                  html, flags=re.S)


def _alive(url):
    """살아 있는 주소만 인용한다. 단 '못 열었다'와 '죽었다'는 다르다.

    2026-10-16 실측 — 이 함수가 보강 파이프라인을 두 번 통째로 무력화했다.
    같은 주소를 두 곳에서 동시에 열어 보면:
        standard.go.kr / law.go.kr / easylaw.go.kr / safetykorea.kr
        · 한국 IP(사용자 맥)      → 200
        · 해외 IP(깃허브 러너·컨테이너) → ConnectionError
    공공기관이 해외 IP 를 막는 것이지 주소가 죽은 게 아니다. 그런데 예외를
    전부 False 로 접어 버리니 DDG 가 제대로 찾아 준 go.kr 출처가 전멸했고,
    refs 가 비면 '외부 인용이 늘지 않음' 가드도 같이 꺼져서(enrich 의 elif refs)
    0건짜리 보강이 초록불로 통과했다 — 10/13·10/15 두 차례 모두 외부인용 0→0.
    그래서 4xx·5xx 만 죽음으로 보고, 네트워크 예외는 '확인 불가'로 돌려준다.
    """
    try:
        r = requests.head(url, headers=UA, timeout=12, allow_redirects=True)
        if r.status_code >= 400:
            r = requests.get(url, headers=UA, timeout=15, stream=True)
        return "ok" if r.status_code < 400 else "dead"
    except Exception:
        return "unknown"


def usable(url):
    """인용해도 되는 주소인가.

    '확인 불가'를 통과시키는 건 authoritative() 로 이미 공공기관·표준·제조사
    공식·백과로 좁혀 둔 뒤이기 때문이다. 아무 주소나 봐주는 게 아니라, 기관
    도메인인데 해외에서 안 열리는 경우만 봐준다. 404 는 그대로 떨어뜨린다.
    """
    # kca.go.kr 은 국내 CA 로 발급한 인증서라 파이썬·curl 이 'unknown CA' 로
    # 거절한다(한국 IP 에서도 동일). 2026-10-16 크롬으로 직접 열어 확인했다 —
    # 경고 없이 열리고 실제 PDF(1.2MB, application/pdf)가 내려온다. 독자에게는
    # 멀쩡한 주소이므로 '확인 불가'로 두고 통과시킨다(규칙 10, 실제로 열어 봄).
    return authoritative(url) and _alive(url) != "dead"


# 제목 전체로 검색하면 안 된다 (2026-10-16 실측).
#   "직수 정수기 필터 교체 주기"        → No results found
#   "1인 가구 미니세탁기 3kg 5kg"       → 쿠팡·다나와·네이버블로그
# 기관·제도 단어를 붙인 짧은 질의여야 1차 출처가 올라온다.
#   "전기히터 화재 한국소비자원"        → kca.go.kr
#   "정수기 위생 관리 고시"             → law.go.kr · easylaw.go.kr · standard.go.kr
#   "세탁기 KS 표준 고시"               → standard.go.kr
# 'site:go.kr' 연산자는 쓰지 않는다 — 도메인만 맞고 주제가 전혀 다른 지자체
# 무역포털·학회지가 올라온다(실측).
_STOP = {"추천", "비교", "방법", "이유", "가지", "정리", "선택", "구매", "사용", "차이",
         "가격", "후기", "최신", "제품", "기준", "요금", "경우", "효과", "관리", "확인",
         "이것", "그것", "얼마", "하는", "하면", "되는", "쓰는", "살때", "모델"}
# 사다리는 품목 성격에 맞는 단만 밟는다. 2026-10-16 실측 — 오일 스프레이
# (#348, 전기와 무관한 주방 용기) 글에 '에너지소비효율등급'이 붙었다.
# "{c} 소비전력 에너지효율" 단이 무조건 돌았기 때문이다. 기관 도메인이고
# 상세 문서라서 모든 필터를 통과했지만, 기름 스프레이와 아무 상관이 없다.
# 권위·관련성에 이어 **품목 적합성**까지가 출처의 조건이다.
_LADDER_BASE = ("{c} 안전주의보 한국소비자원", "{c} 기준 고시",
                "{c} 표준 규격", "{c} 소비자분쟁해결기준")
_LADDER_POWER = ("{c} 소비전력 에너지소비효율등급",)
_LADDER_FOOD = ("{c} 식품용기 기준 식품의약품안전처", "{c} 위생 기준 고시")
_POWER_WORD = ("전기", "전력", "요금", "가전", "충전", "플러그", "콘센트", "히터",
               "난방", "냉방", "에어컨", "세탁기", "냉장고", "건조기", "청소기",
               "정수기", "제습기", "가습기", "인덕션", "온풍기", "선풍기", "전열",
               "소비전력", "와트", "에너지")
_FOOD_WORD = ("주방", "식기", "용기", "도마", "밀폐", "보관", "조리", "food", "오일",
              "기름", "물통", "텀블러", "수저", "젓가락", "냄비", "프라이팬", "김치",
              "식품", "음식", "컵", "병", "빨대", "랩", "호일")


def _ladder_for(text):
    """품목 성격에 맞는 질의 단만 돌려준다."""
    t = text or ""
    lad = list(_LADDER_BASE)
    if any(w in t for w in _POWER_WORD):
        lad[2:2] = list(_LADDER_POWER)
    if any(w in t for w in _FOOD_WORD):
        lad[1:1] = list(_LADDER_FOOD)
    return tuple(lad)


def _core(title, focus=""):
    """제목에서 품목 명사 1~2개만 뽑는다. 검색어는 짧을수록 기관 문서가 나온다."""
    src = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", "%s %s" % (focus or "", title or ""))
    out = []
    for w in src.split():
        w = re.sub(r"(은|는|이|가|을|를|의|에|로|와|과|도|만)$", "", w)
        if len(w) < 2 or w in _STOP or w.isdigit():
            continue
        if w not in out:
            out.append(w)
        if len(out) >= 2:
            break
    return " ".join(out) or (title or "")[:12]


def _wiki(core):
    """위키백과 한국어판 — 공공기관과 달리 해외 IP 에서도 열리는 마지막 보루.

    1차 출처는 아니지만 품목 정의·작동 원리를 거는 데는 쓸 만하다. 다만 검색
    2순위부터는 전혀 다른 표제어가 섞이므로('전기장판' → '판타지 여동생!',
    2026-10-16 실측) 표제어가 핵심어와 겹칠 때만 채택한다.
    """
    import urllib.parse
    import urllib.request
    head = (core or "").split()[0] if core else ""
    if len(head) < 2 or head[0].isdigit():
        return None
    try:
        u = "https://ko.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "format": "json", "list": "search",
             "srsearch": head, "srlimit": 3})
        rq = urllib.request.Request(
            u, headers={"User-Agent": "pickdam-enrich/1.0 (+https://pickdam.com)"})
        data = json.loads(urllib.request.urlopen(rq, timeout=12).read().decode("utf-8"))
    except Exception as e:
        print("      [wiki] 실패: %s" % e)
        return None
    for it in data.get("query", {}).get("search", []):
        t = it.get("title") or ""
        if head and (head in t or t in head):
            return {"title": "%s - 위키백과" % t,
                    "url": "https://ko.wikipedia.org/wiki/"
                           + urllib.parse.quote(t.replace(" ", "_"))}
    return None


# 기관 도메인이라고 다 인용거리는 아니다 (2026-10-16 실측).
# 같은 질의를 두 번 돌렸더니 한 번은 kca.go.kr 의 '피해예방주의보 상세보기'가,
# 한 번은 '…주의보 목록'과 '한국소비자원 메인'이 올라왔다. 목록·메인을 거는 건
# 출처 인용이 아니라 링크 늘리기이고, 구글이 가장 싫어하는 종류다.
# 그래서 '문서인가 허브인가'로 거른다 — 주제어 일치로는 못 거른다. 쓸 만한
# 상세 페이지도 제목이 'OOO > 소비자뉴스 > 피해예방주의보 > 상세보기' 같은
# 빵부스러기라 본문 주제어가 안 들어 있기 때문이다.
_DOC_HINT = ("mode=view", "no=", "seq=", "idx=", "articleno", "admrul", "lsinfo",
             "stddetail", "cnpcls", "/wiki/", ".pdf", "/view", "bbsid", "ntt")
_HUB_PATH = ("/", "/index.do", "/main.do", "/home/main.do", "/home/", "/kr/", "/portal/")
_HUB_TAIL = ("목록", "메인", "> main", "home")


def _specific(url, title=""):
    """목록·메인 같은 허브 페이지는 출처로 쓰지 않는다. 상세 문서만 통과."""
    u = (url or "").lower()
    path = "/" + u.split("//", 1)[-1].split("/", 1)[-1] if "//" in u else u
    if "/" not in u.split("//", 1)[-1]:
        return False                              # 도메인 루트
    bare = path.split("?")[0]
    if bare in _HUB_PATH or bare.endswith(("/main.do", "/index.do", "/sub.do")):
        if not any(h in u for h in _DOC_HINT):
            return False
    t = (title or "").strip().lower()
    if any(t.endswith(x) for x in _HUB_TAIL):
        return False
    return any(h in u for h in _DOC_HINT) or len([x for x in bare.split("/") if x]) >= 2


def gather_refs(title, focus="", want=2):
    """기관 지향 질의를 사다리로 올라가며 권위 출처를 모은다. 실패하면 위키백과."""
    import time as _t
    core = _core(title, focus)
    ladder = _ladder_for(f"{focus or ''} {title or ''}")
    seen, pool, tried = set(), [], []
    # 사다리를 끝까지 걷지 않고 want 건 모이면 멈추면, 같은 기관 페이지 두 장을
    # 집게 된다(2026-10-16 실측: kca.go.kr 피해예방주의보 2장 / law.go.kr 2장).
    # 서로 다른 기관 두 곳을 인용해야 '여러 1차 출처를 확인한 글'이 되므로,
    # 최소 세 질의까지는 돌려 후보를 모아 두고 호스트별로 하나씩 고른다.
    for i, pat in enumerate(ladder):
        if len(pool) >= want and i >= 3:
            break
        q = pat.format(c=core)
        tried.append(q)
        try:
            cands = find_reference_links(q, max_results=5)
        except Exception:
            cands = []
        for r in cands:
            u = (r.get("url") or "").split("#")[0]
            if not u or u in seen:
                continue
            seen.add(u)
            if usable(u) and _specific(u, r.get("title")):
                pool.append({"title": r.get("title") or u, "url": u})
        _t.sleep(2)

    # 핵심어가 너무 좁으면 기관 문서가 안 걸린다('욕실 온풍기' → 후보 0,
    # 2026-10-16 실측). 빈손이면 품목 낱말 하나로 줄여 두 질의만 더 걸어 본다.
    # 여기서 뒷말을 집었던 게 위 사고의 방아쇠였다. core 가 '미니세탁기 1인'
    # 이면 head 가 '1인' 이 되고, "1인 기준 고시" 같은 질의가 영문 위키의
    # 숫자 1 문서를 물어 온다. 품목말은 언제나 앞말이다.
    head = core.split()[0] if core.split() else ""
    if len(head) < 2 or head[0].isdigit():
        head = ""
    if not pool and head and head != core:
        for pat in ladder[:2]:
            q = pat.format(c=head)
            tried.append(q)
            try:
                cands = find_reference_links(q, max_results=5)
            except Exception:
                cands = []
            for r in cands:
                u = (r.get("url") or "").split("#")[0]
                if not u or u in seen:
                    continue
                seen.add(u)
                if usable(u) and _specific(u, r.get("title")):
                    pool.append({"title": r.get("title") or u, "url": u})
            _t.sleep(2)

    def _host(u):
        return u.split("//", 1)[-1].split("/", 1)[0].lstrip("www.")

    refs, used = [], set()
    for r in pool:                       # 1순위: 기관이 서로 다른 것부터
        h = _host(r["url"])
        if h in used:
            continue
        used.add(h)
        refs.append(r)
        if len(refs) >= want:
            break
    if len(refs) < want:                 # 2순위: 그래도 모자라면 같은 기관이라도
        for r in pool:
            if r not in refs:
                refs.append(r)
            if len(refs) >= want:
                break
    if not refs:
        w = _wiki(core)
        if w:
            refs.append(w)
    print("      출처 검색: 핵심어 '%s' · 질의 %d개 · 후보 %d · 채택 %d건(기관 %d곳)"
          % (core, len(tried), len(pool), len(refs),
             len({_host(r["url"]) for r in refs})))
    return refs, core


def pick(posts, index_state, want):
    """미색인 → 외부 인용 0 → 얇은 순서. 이미 보강한 글은 건너뛴다."""
    rows = []
    for p in posts:
        raw = (p.get("content") or {}).get("raw") or ""
        if MARK in raw:
            continue
        pf = _profile(raw)
        st = index_state.get(p["link"].rstrip("/"), "")
        score = 0
        if st and st != "PASS":
            score += 100
        if pf["external"] == 0:
            score += 30
        if pf["lists"] < 3:
            score += 20
        if pf["chars"] < 2500:
            score += 25
        rows.append((score, p, pf, st))
    rows.sort(key=lambda x: (-x[0], x[2]["chars"]))
    return [r for r in rows if r[0] > 0][:want]


def _prompt(title, raw, pf, ref_text, prev_fail=""):
    nimg = pf["img"]
    return (
        "아래 한국어 블로그 글 HTML을 **보강**하세요. 새로 쓰는 게 아니라 있는 글을 끌어올리는 작업입니다.\n\n"
        + (f"[⚠️ 직전 시도는 이것 때문에 반려됐습니다. 이번엔 반드시 피하세요]\n{prev_fail}\n\n"
           if prev_fail else "")
        + "[반드시 지킬 것 — 하나라도 어기면 반영하지 않습니다]\n"
        f"- 원문에 <img> 태그가 {nimg}개 있습니다. **{nimg}개를 하나도 빠짐없이** src·alt까지 "
        "그대로 옮기세요. 설명을 늘리더라도 이미지는 지우거나 합치지 마세요.\n"
        "- <!--picklink--> … <!--/picklink--> 블록과 쿠팡 파트너스 고지 문단은 위치·내용 그대로.\n"
        "- 기존 소제목(h2/h3)은 유지하고 추가만 하세요. 분량은 줄이지 마세요.\n\n"
        "[보강할 것]\n"
        "1. 아래 출처를 본문에 인용하세요. 주소는 **한 글자도 바꾸지 말고 그대로 복사**해 "
        '<a href="주소" target="_blank" rel="noopener">제목</a> 형태로 넣고, 그 출처가 말하는 '
        f"내용을 한두 문장으로 요약해 붙이세요. 없는 주소를 지어내지 마세요.\n{ref_text}\n"
        "2. 비교·기준·체크리스트를 <ul> 또는 <table>로 최소 2개 추가하세요(줄글을 목록으로 바꿔도 됩니다).\n"
        "3. 조건 분기를 최소 2개 넣으세요 (예: '벽이 석고보드라면 A, 콘크리트라면 B').\n"
        "4. 흔한 실수 또는 사기 전 후회 포인트를 한 소제목으로 넣으세요.\n"
        "5. 규격·가격대·시간·주기 같은 실측형 수치를 4개 이상 유지하거나 늘리세요. 모르면 범위로.\n"
        "6. 다음 상투 표현 금지: 알아보겠습니다, 살펴보겠습니다, 이번 글에서는, 도움이 되셨기를.\n\n"
        "[출력] 순수 HTML 본문만. 코드블록·설명 금지.\n\n[원문]\n" + raw)


def enrich(p, pf, cfg, dry):
    title = re.sub("<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))
    raw = (p.get("content") or {}).get("raw") or ""
    # 2026-10-16: 품목에 안 맞는데 **권위는 있는** 출처가 붙은 경우
    # (#348 기름 스프레이 글의 '에너지소비효율등급'), strip_denied_links 로는
    # 못 뗀다 — 도메인이 허용 목록에 있기 때문이다. 사람이 콕 집어 떼는 길이
    # 하나는 있어야 한다. ENRICH_DROP 에 주소 조각을 쉼표로 넘기면 그것만 푼다.
    drop = [x.strip() for x in (os.getenv("ENRICH_DROP") or "").split(",") if x.strip()]
    if drop:
        def _unwrap(m):
            return m.group(2) if any(d in m.group(1) for d in drop) else m.group(0)
        raw2 = re.sub(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', _unwrap,
                      raw, flags=re.S)
        if raw2 != raw:
            print(f"      지정 출처 {len(drop)}건 제거")
            raw = raw2
    cleaned = strip_denied_links(raw)
    if cleaned != raw:
        print("      비권위 외부 링크 정리")
        raw = cleaned
        pf = _profile(raw)
    # 정리만 하고 끝내는 모드. 보강(LLM)이 반려로 끝나면 비권위 링크가 글에 그대로
    # 남는다(2026-10-13 #332 실측) — 링크 제거는 결정적인 작업이니 따로 떼어 둔다.
    if (os.getenv("ENRICH_CLEAN_ONLY") or "").lower() == "true":
        if cleaned == (p.get("content") or {}).get("raw"):
            return None, "정리할 비권위 링크 없음"
        return raw, "비권위 외부 링크만 정리(LLM 미사용)"
    refs, core = gather_refs(title, p.get("_focus", ""), want=2)
    ref_text = ("\n".join(f"- {r['title'][:60]} : {r['url']}" for r in refs)
                if refs else "(공공기관·표준·제조사 공식 같은 1차 출처를 못 찾았습니다 — "
                             "외부 링크는 **넣지 마세요**. 블로그·쇼핑몰 링크는 금지입니다)")
    if dry:
        return None, f"출처 {len(refs)}건 · 핵심어 '{core}' · (dry_run)"

    # 2026-10-13: 첫 실전에서 2편 모두 보존 검증에 걸렸다(이미지 1장 소실 / 출처 누락).
    # 검증을 느슨하게 푸는 건 답이 아니다 — 반려 사유를 그대로 돌려주고 한 번 더 시킨다.
    prev, last = "", ""
    for _round in (1, 2):
        neo = chat(_prompt(title, raw, pf, ref_text, prev), cfg.get("llm", {}),
                   max_tokens=16000, temperature=0.6)
        neo = re.sub(r"^```html?\s*|\s*```$", "", (neo or "").strip())
        if not (neo and neo.lstrip().startswith("<")):
            last = "응답이 HTML 이 아님"
            prev = last
            continue
        # 2026-10-13 2차 실측: 출처를 못 찾아 '외부 링크 금지'라고 했는데도 모델이
        # 블로그 주소를 **지어내서** 넣었다. 지시는 샌다 — 출력에서도 기계로 걷어내고,
        # 남은 외부 링크는 내가 건넨 주소이거나 원문에 이미 있던 권위 출처여야만 한다.
        neo = strip_denied_links(neo)
        quality.autofix({"html": neo})
        np = _profile(neo)
        allowed = {r["url"] for r in refs} | {
            u for u in re.findall(r'href="(https?://[^"]+)"', raw)
            if "pickdam.com" not in u and "coupang" not in u and authoritative(u)}
        stray = [u for u in re.findall(r'href="(https?://[^"]+)"', neo)
                 if "pickdam.com" not in u and "coupang" not in u and u not in allowed]
        why = ""
        if stray:
            why = f"건네지 않은 외부 링크를 넣었습니다({len(stray)}건: {stray[0][:46]})"
        if why:
            pass
        elif np["picklink"] != pf["picklink"]:
            why = f"상품 카드 마커 손상({pf['picklink']}→{np['picklink']})"
        elif (NOTICE in raw) and (NOTICE not in neo):
            why = "고지 문구 소실"
        elif np["img"] < pf["img"]:
            why = f"이미지 소실({pf['img']}→{np['img']})"
        elif np["chars"] < pf["chars"]:
            why = f"분량 감소({pf['chars']}→{np['chars']})"
        elif refs and np["external"] <= pf["external"]:
            why = "외부 인용이 늘지 않음"
        else:
            missing = [r["url"] for r in refs if r["url"] not in neo]
            if missing:
                why = f"제시한 출처가 본문에 없음({len(missing)}건)"
        if not why:
            stamp = MARK + datetime.date.today().isoformat() + "-->"
            return neo + "\n" + stamp, (f"{_round}회차 · {pf['chars']}→{np['chars']}자 · "
                                         f"목록 {pf['lists']}→{np['lists']} · "
                                         f"외부인용 {pf['external']}→{np['external']} · "
                                         f"출처 {len(refs)}건")
        print(f"      {_round}회차 반려: {why}")
        prev, last = why, why
    return None, f"{last} · 출처 {len(refs)}건"


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    dry = (os.getenv("ENRICH_DRY") or "").lower() == "true"
    want = int(os.getenv("ENRICH_N") or "2")
    only = [x.strip() for x in (os.getenv("ENRICH_IDS") or "").split(",") if x.strip()]

    try:
        ix = json.load(open(os.path.join(DATA, "index_status.json"), encoding="utf-8"))
        state = {r["url"].rstrip("/"): r.get("verdict") for r in ix.get("results", [])}
    except Exception:
        state = {}

    posts, page = [], 1
    while page <= 3:
        r = requests.get(f"{base}/wp-json/wp/v2/posts", headers=headers, timeout=60,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "context": "edit", "_fields": "id,link,title,content"})
        if r.status_code != 200:
            print(f"글 목록 조회 실패 HTTP {r.status_code}")
            break
        chunk = r.json()
        posts += chunk
        if len(chunk) < 50:
            break
        page += 1
    print(f"[enrich] 발행 {len(posts)}편 · 목표 {want}편 · dry_run={dry}")

    if only:
        sel = [(0, p, _profile((p.get("content") or {}).get("raw") or ""), "")
               for p in posts if str(p["id"]) in only]
    else:
        sel = pick(posts, state, want)
    if not sel:
        print("보강 대상 없음")
        return 0

    log, done, fail = [], 0, 0
    for score, p, pf, st in sel:
        t = re.sub("<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))[:36]
        print(f"\n· #{p['id']} {t} (점수 {score} · {st or '색인상태 미상'} · {pf['chars']}자 "
              f"목록 {pf['lists']} 외부 {pf['external']})")
        neo, note = enrich(p, pf, cfg, dry)
        if neo and update_post_content(wp, p["id"], neo):
            print(f"    보강 완료 — {note}")
            log.append({"id": p["id"], "title": t, "ok": True, "note": note})
            done += 1
        else:
            print(f"    보강 안 함 — {note}")
            log.append({"id": p["id"], "title": t, "ok": False, "note": note})
            if not dry:
                fail += 1

    os.makedirs(DATA, exist_ok=True)
    out = {"at": datetime.datetime.now().isoformat()[:19], "dry": dry,
           "done": done, "fail": fail, "rows": log}
    json.dump(out, open(os.path.join(DATA, "enrich_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[enrich] 보강 {done}편 · 실패 {fail}편")
    return 0


if __name__ == "__main__":
    sys.exit(main())
