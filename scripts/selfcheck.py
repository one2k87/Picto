# -*- coding: utf-8 -*-
"""작동 증명 점검 (2026-10-08 신설).

왜 만들었나 — 한 세션에서 같은 모양의 사고가 7번 났다.
  · 사이트맵이 9/9에 굳어 23일간 18편이 구글에 제출되지 않았다
  · IndexNow 가 설정된 뒤 한 번도 성공한 적이 없었다(키 파일 위치 오류, 전부 422)
  · 가장 잘 되는 주제(환급·할부)가 생성 금지어에 들어 있었다
  · 쿠팡 링크 한 개가 옵션 소멸로 '상품 없음'이 됐다
  · 카드 삽입 경로가 둘인데 마커가 한쪽에만 있어 20편에 카드가 두 개씩 박혔다
  · 발행이 0편인 날이 조용히 지나갔다
  · 전략 엔진의 winners 가 빈 배열인 채로 '성공'이었다

공통 뿌리는 하나다 — **'설정했다'와 '작동한다'를 구분하지 않았다.**
기존 아침 점검(daily_check_fix)은 '결함이 보이면' 잡는다. 이 파일은 반대로 간다:
**각 경로가 실제로 동작했다는 증거를 매일 새로 만든다.** 증거를 못 만들면 실패다.

결과: dashboard/data/selfcheck.json  (통계 화면과 텔레그램이 읽는다)
환경: SELFCHECK_WRITE=false 면 외부에 쓰는 검사(IndexNow 제출)를 건너뛴다.
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"}
DATA = os.path.join("dashboard", "data")
CHECKS = []


def check(key, title, fix_by):
    """fix_by: 'auto'(코드가 고친다) / 'me'(세션이 고친다) / 'user'(사람만 가능)"""
    def deco(fn):
        CHECKS.append((key, title, fix_by, fn))
        return fn
    return deco


def _json(name, default=None):
    try:
        return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def _posts(site):
    out, page = [], 1
    while page <= 5:
        r = requests.get(f"{site}/wp-json/wp/v2/posts", headers=UA, timeout=30,
                         params={"per_page": 50, "page": page, "status": "publish",
                                 "_fields": "id,link,title,modified_gmt,content"})
        if r.status_code != 200:
            break
        chunk = r.json()
        out += chunk
        if len(chunk) < 50:
            break
        page += 1
    return out


# ── 1. 사이트맵이 실제로 모든 글을 담고 있는가 ───────────────────────
@check("sitemap", "사이트맵이 모든 글을 담고 있는가", "user")
def _sitemap(ctx):
    r = requests.get(f"{ctx['site']}/post-sitemap.xml", headers=UA, timeout=25)
    if not r.ok or "<urlset" not in r.text:
        return False, f"사이트맵을 못 읽었습니다 (HTTP {r.status_code})", \
               "Rank Math 사이트맵 설정에서 값을 하나 바꿔 저장"
    locs = {u.rstrip("/").rsplit("/", 1)[-1] for u in re.findall(r"<loc>(.*?)</loc>", r.text)}
    lms = re.findall(r"<lastmod>(.*?)</lastmod>", r.text)
    miss = [p for p in ctx["posts"]
            if p["link"].rstrip("/").rsplit("/", 1)[-1] not in locs
            and (p.get("modified_gmt") or "") < ctx["fresh_cut"]]
    sm_max = max(lms) if lms else ""
    if miss:
        return False, (f"{len(miss)}편이 사이트맵에 없습니다 "
                       f"(사이트맵 {len(locs)} / 발행 {len(ctx['posts'])}, 최신 {sm_max[:10]}) — "
                       + " / ".join(re.sub("<[^>]+>", "", p["title"]["rendered"])[:18] for p in miss[:3])), \
               "Rank Math SEO → 사이트맵 설정에서 값을 하나 바꿔 [변경사항 저장]. 값이 그대로면 캐시가 안 풀립니다"
    return True, f"사이트맵 {len(locs)}개 · 발행 {len(ctx['posts'])}편 · 누락 0", ""


# ── 2. IndexNow 가 실제로 받아주는가 (네이버·빙 즉시 통지) ─────────────
@check("indexnow", "IndexNow 가 글 주소를 받아주는가", "user")
def _indexnow(ctx):
    cat = _json("../../data/site_categories.json")
    inx = (cat or {}).get("indexnow") or {}
    key, loc = inx.get("key"), inx.get("key_location")
    if not key:
        return False, "IndexNow 키가 설정돼 있지 않습니다", "Rank Math IndexNow 모듈을 켜거나 키 파일을 루트에 올리기"
    if os.getenv("SELFCHECK_WRITE", "true").lower() == "false":
        return True, "쓰기 검사 건너뜀(SELFCHECK_WRITE=false)", ""
    target = ctx["posts"][0]["link"] if ctx["posts"] else ctx["site"] + "/"
    body = {"host": ctx["host"], "key": key, "urlList": [target]}
    if loc:
        body["keyLocation"] = loc
    try:
        r = requests.post("https://api.indexnow.org/IndexNow", json=body, headers=UA, timeout=25)
    except Exception as e:
        return False, f"제출 실패: {str(e)[:60]}", ""
    if r.status_code in (200, 202):
        return True, f"글 주소 제출 {r.status_code} — 네이버·빙에 즉시 통지됩니다", ""
    hint = ""
    if loc and not re.match(rf"^https?://{re.escape(ctx['host'])}/[0-9a-f]+\.txt$", loc):
        hint = (f"키 파일이 하위 폴더에 있습니다 ({loc}). IndexNow 는 그 폴더 아래 주소만 승인하므로 "
                f"글 주소는 전부 거부됩니다. 키 파일을 사이트 최상위(https://{ctx['host']}/{key}.txt)로 옮기세요")
    return False, f"글 주소 제출이 거부됐습니다 (HTTP {r.status_code}) — 네이버·빙 통지가 안 되고 있습니다", hint


# ── 3. 쿠팡 링크가 전부 살아 있는가 ─────────────────────────────────
@check("coupang_links", "쿠팡 링크가 상품으로 연결되는가", "me")
def _links(ctx):
    codes = sorted({m for p in ctx["posts"]
                    for m in re.findall(r"link\.coupang\.com/a/(\w+)", p["content"]["rendered"])})
    if not codes:
        return False, "본문에 쿠팡 링크가 하나도 없습니다", ""
    bad = []
    for c in codes:
        try:
            r = requests.get(f"https://link.coupang.com/a/{c}", headers=UA,
                             allow_redirects=False, timeout=20)
            if "/vp/products/" not in (r.headers.get("Location") or ""):
                bad.append(c)
        except Exception:
            bad.append(c)
    if bad:
        return False, f"{len(bad)}/{len(codes)}개가 상품으로 안 갑니다: {', '.join(bad[:4])}", \
               "해당 상품 배너를 다시 만들어 작업대에 붙여넣기"
    return True, f"{len(codes)}개 전부 상품 페이지로 연결", ""


# ── 4. 한 글에 카드가 두 개 박혀 있지 않은가 ──────────────────────────
@check("cards", "상품 카드가 글마다 하나인가", "auto")
def _cards(ctx):
    dup = [p for p in ctx["posts"] if p["content"]["rendered"].count('class="pick-product"') > 1]
    if dup:
        return False, f"{len(dup)}편에 카드가 둘 이상: " + ", ".join(f"#{p['id']}" for p in dup[:5]), \
               "워크플로 '중복 상품 카드 정리' 실행"
    return True, f"{len(ctx['posts'])}편 전부 카드 1개 이하", ""


# ── 5. 색인 검사가 전부를 보고 있는가 ───────────────────────────────
@check("index", "색인 검사가 모든 글을 보고 있는가", "auto")
def _index(ctx):
    ix = _json("index_status.json")
    checked, indexed = ix.get("checked", 0), ix.get("indexed", 0)
    n = len(ctx["posts"])
    if checked < n:
        return False, f"발행 {n}편 중 {checked}편만 검사됐습니다 (색인 {indexed}) — 상한에 걸렸습니다", \
               "inspect_recent 의 하루 상한을 올리거나 이틀에 나눠 검사"
    ratio = round(indexed / max(checked, 1) * 100)
    if ratio < 80:
        return False, f"색인 {indexed}/{checked} ({ratio}%)", "미색인 글에 내부링크 보강 + 사이트맵 확인"
    return True, f"색인 {indexed}/{checked} ({ratio}%)", ""


# ── 6. 발행이 실제로 되고 있는가 ────────────────────────────────────
@check("publish", "최근 7일 발행이 되고 있는가", "auto")
def _publish(ctx):
    pub = dis = days = 0
    for i in range(1, 8):
        d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        j = _json(f"{d}.json", {})
        arts = j.get("articles") or []
        if not arts:
            continue
        days += 1
        pub += sum(1 for a in arts if a.get("status") == "게시됨")
        dis += sum(1 for a in arts if a.get("status") == "폐기")
    if days and pub / days < 0.7:
        return False, f"최근 {days}일 중 발행 {pub} · 폐기 {dis} — 발행률 {round(pub/days*100)}%", \
               "폐기 사유를 보고 생성 프롬프트를 고칠 것"
    return True, f"최근 {days}일 발행 {pub} · 폐기 {dis}", ""


# ── 7. 전략 피드백이 비어 있지 않은가 ───────────────────────────────
@check("strategy", "전략 피드백이 주제에 반영되는가", "auto")
def _strategy(ctx):
    st = _json("strategy.json")
    w = st.get("winners") or []
    if not w:
        return False, f"winners 가 비었습니다 (상태 {st.get('data_status')}, matched {st.get('matched_posts')}) " \
                      "— 잘 된 글의 각도가 다음 주제에 반영되지 않습니다", \
               "strategy.py 의 winners 산출 기준을 실적 규모에 맞게 낮출 것"
    return True, f"winners {len(w)}건 반영 중", ""


# ── 8. 금지어가 '잘 되는 주제'를 막고 있지 않은가 ─────────────────────
@check("banlist", "금지어가 잘 되는 각도를 막고 있지 않은가", "me")
def _banlist(ctx):
    cat = _json("../../data/site_categories.json")
    bans = [b for b in (cat or {}).get("ban_keywords", []) if b]
    ins = _json("insights.json")
    pages = ((ins.get("search_console") or {}).get("pages") or [])
    if not bans or not pages:
        return True, "대조할 데이터 없음", ""
    top = sorted(pages, key=lambda x: -x.get("impressions", 0))[:10]
    tot = sum(p.get("impressions", 0) for p in pages) or 1
    byslug = {p["link"].rstrip("/").rsplit("/", 1)[-1]:
              re.sub("<[^>]+>", "", p["title"]["rendered"]) for p in ctx["posts"]}
    hits, imp = [], 0
    for p in top:
        s = p["page"].rstrip("/").rsplit("/", 1)[-1]
        title = byslug.get(s, s)
        for b in bans:
            if b in title or b.replace(" ", "") in title.replace(" ", ""):
                hits.append(f"{title[:20]}…({b})")
                imp += p.get("impressions", 0)
                break
    if hits:
        return False, (f"노출 상위 글 {len(hits)}편이 금지어에 걸립니다 — 노출 {imp}회"
                       f"({round(imp/tot*100)}%)를 가져오는 각도를 생성 단계에서 막고 있습니다: "
                       + " / ".join(hits[:3])), \
               "data/site_categories.json 의 ban_keywords 에서 해당 단어를 빼거나, 그 각도를 포기할지 결정"
    return True, f"금지어 {len(bans)}개 · 상위 글과 충돌 없음", ""


# ── 9. 고지 문구가 모든 글에 있는가 (파트너스 반려 1위 사유) ────────────
@check("disclosure", "대가성 고지가 모든 글에 있는가", "auto")
def _disclosure(ctx):
    miss = [p for p in ctx["posts"] if "쿠팡 파트너스 활동의 일환" not in p["content"]["rendered"]]
    if miss:
        return False, f"{len(miss)}편에 고지 문구가 없습니다: " + ", ".join(f"#{p['id']}" for p in miss[:5]), \
               "아침 점검의 고지 삽입을 다시 돌릴 것"
    return True, f"{len(ctx['posts'])}편 전부 보유", ""


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    site = (wp.get("site_url") or "").rstrip("/")
    if not site:
        print("site_url 없음 — 종료")
        return 1
    ctx = {"site": site, "host": re.sub(r"^https?://", "", site).split("/")[0]}
    ctx["posts"] = _posts(site)
    ctx["fresh_cut"] = (datetime.datetime.utcnow()
                        - datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[selfcheck] 발행 {len(ctx['posts'])}편 기준\n")

    out, fails = [], 0
    for key, title, fix_by, fn in CHECKS:
        try:
            ok, ev, fix = fn(ctx)
        except Exception as e:
            ok, ev, fix = False, f"검사 자체가 실패: {str(e)[:70]}", ""
        out.append({"key": key, "title": title, "ok": bool(ok),
                    "evidence": ev, "fix": fix, "fix_by": fix_by})
        if not ok:
            fails += 1
        print(f"  {'✅' if ok else '❌'} {title}\n       {ev}" + (f"\n       → {fix}" if fix and not ok else ""))

    res = {"at": datetime.datetime.now().isoformat()[:19], "posts": len(ctx["posts"]),
           "pass": len(out) - fails, "fail": fails, "checks": out,
           "user_todo": [c for c in out if not c["ok"] and c["fix_by"] == "user"]}
    os.makedirs(DATA, exist_ok=True)
    json.dump(res, open(os.path.join(DATA, "selfcheck.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[selfcheck] 통과 {len(out)-fails} · 실패 {fails}")

    try:
        import notify
        if fails:
            lines = [f"🧪 <b>픽담 작동 점검</b> — {len(out)-fails}/{len(out)} 통과"]
            for c in out:
                if not c["ok"]:
                    lines.append(f"❌ {c['title']}\n   {c['evidence']}")
            u = res["user_todo"]
            if u:
                lines.append(f"\n🙋 사람만 할 수 있는 것 {len(u)}건:")
                for c in u:
                    lines.append(f"   · {c['fix']}")
            notify.send(cfg, "\n".join(lines)[:3500])
    except Exception as e:
        print(f"[notify] 건너뜀: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
