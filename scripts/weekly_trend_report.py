# -*- coding: utf-8 -*-
"""「이번 주 유행템」 주간 리포트 — 신호는 전자동, 쿠팡 링크만 주 1회 사람 손 (2026-11-12).

**지시**: famto 2026-11-11 — 주 1회 글 1편, 1~20만 원대 상위 5개, 상품마다 '왜 뜨는지'
근거 1~2개 + 쿠팡 링크(대가성 문구). **공식 API만 — 쿠팡 리뷰·인스타 크롤링 금지.**

**왜 반자동인가 (사용자 결정 2026-11-12)**
  쿠팡 파트너스 오픈API는 **누적 수익 ₩150,000 → 최종승인** 뒤에야 열린다(2026-09 가이드 실측).
  픽담은 파트너스 클릭 0이라 당분간 못 쓴다. 네이버 쇼핑 '검색' API도 2026-07-31 종료라
  **상품 가격·링크를 받을 공식 경로가 하나도 없다.** 그래서:
    · 신호(무엇이 뜨는가·찾는 사람이 있는가)는 **전부 무료 공식 API로 자동**
    · 쿠팡 링크만 주 1회 5개 사람이 만들어 붙인다(약 5분)
    · 붙인 링크는 `data/products.json`에 **누적**되어 과거 글에도 소급된다(backfill-links.yml)
      → 주가 갈수록 손이 줄고, 누적 15만 원을 넘기면 `coupang_api.py`가 그대로 켜진다.

**신호 4층 (없는 층은 조용히 빠지고 나머지로 진행한다)**
  ① 발굴  캐스토 `trend_board.json` (유튜브 실측)  — 공개 raw, 읽기만
  ② 검증  네이버 검색광고 `/keywordstool` 월간 검색량 — `demand.monthly_volume` (이미 배포됨)
  ③ 보조  구글 Suggest 자동완성 — `demand.suggest_hits` (키 없음)
  ④ 기준가 공공데이터 생필품 조사가격 — `price_ref` (활용신청 필요, 없으면 생략)

**가격 표기 (사용자 지시 2026-11-12 개정)**
  "가격대(만 원대)"로 뭉개면 **채널 신뢰도가 떨어진다** — 정확한 금액을 쓴다.
  금액의 출처는 `products.json`의 `price`/`price_at`이고, 그 값은 **세션이 사용자 크롬으로
  쿠팡 상품 페이지의 JSON-LD(`Product.offers.price`)를 읽어** 채운다(2026-11-12 실측으로 확인:
  price·availability·brand·rating 이 전부 들어 있다). 서버(Actions)에서는 하지 않는다 —
  쿠팡 봇 차단에 걸리고 약관 위험이 있다. 그래서 글에는 **반드시 조사일을 함께 적는다.**
  소비자원 조사가격은 "정상가 대비 얼마나 싼지"를 보여주는 보조선으로만 쓴다.

**'왜 뜨는지'는 LLM을 쓰지 않는다.** 실측 숫자만으로 문장을 조립한다. 모델이 쓰면
그럴듯한 거짓말이 되고, 이 레포에서 이미 세 번 당했다.

실행
  python scripts/weekly_trend_report.py              # ① 선정 + 링크 요청 블록 출력
  python scripts/weekly_trend_report.py --publish    # ② 링크가 찬 뒤 발행
"""
import datetime as dt
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import demand
import price_ref
import products as products_mod

BOARD_RAW = "https://raw.githubusercontent.com/one2k87/Casto/main/data/trend_board.json"
# 일별 스냅샷. trend_board 는 갱신이 멈출 때가 있어(2026-11-13 실측: 11일 묵음) 이쪽을 먼저 본다.
# 구조도 더 좋다 — 상품 단위이고 evidence·demand(네이버 수요 지수)·overseas(해외 선행 판정)가 들어 있다.
DAILY_RAW = "https://raw.githubusercontent.com/one2k87/Casto/main/data/trends_daily/{d}.json"
# 상품 단위 언급 빈도 — 캐스토에 요청해 둔 파일(2026-11-12 P→F). 아직 없으면 조용히 건너뛴다.
MENTIONS_RAW = "https://raw.githubusercontent.com/one2k87/Casto/main/data/product_mentions.json"
BOARD_LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "..", "Casto", "data", "trend_board.json")
PICK = "data/weekly_trend_pick.json"
PREVIEW = "data/trend_report_preview.html"
NOTICE = ("이 포스팅은 쿠팡 파트너스 활동의 일환으로, "
          "이에 따른 일정액의 수수료를 제공받습니다.")
PARTNERS_LINK_UI = "https://partners.coupang.com/#affiliate/ws/link/dynamic"
WANT = 5
MIN_PUBLISH_LINKS = 3        # 링크가 이보다 적으면 발행하지 않는다 — 링크 없는 리포트는 수익이 0이다
MIN_VIDEOS, MIN_CHANNELS = 3, 3
SPREAD_CHANNELS = 5          # 이보다 적으면 "한두 채널 탓이 아니다"라고 말할 수 없다
MIN_VOLUME = 50              # 월간 검색량 하한(검색광고가 살아 있을 때만 적용)
QUADRANT_KO = {"peak": "노출과 실수요가 같이 높은 구간",
               "bubble": "노출이 앞서 간 구간(실수요는 아직 덜 따라왔습니다)",
               "rising": "올라오는 구간"}


# ─── 입력 ────────────────────────────────────────────────────────────────────
def load_board():
    try:
        r = requests.get(BOARD_RAW, timeout=25)
        if r.status_code == 200:
            print("[board] 캐스토 raw 에서 받음")
            return r.json()
        print(f"[board] raw HTTP {r.status_code}")
    except Exception as e:
        print(f"[board] raw 실패: {str(e)[:90]}")
    try:
        with open(BOARD_LOCAL, encoding="utf-8") as f:
            print("[board] 로컬 체크아웃에서 읽음")
            return json.load(f)
    except Exception:
        return None


def load_daily(back=7):
    """오늘부터 거슬러 올라가며 가장 최근 일별 스냅샷을 받는다. 없으면 None."""
    for i in range(back):
        day = (dt.date.today() - dt.timedelta(days=i)).isoformat()
        try:
            r = requests.get(DAILY_RAW.format(d=day), timeout=20)
            if r.status_code == 200:
                data = r.json()
                print(f"[daily] {day} 스냅샷 · 상품 {len(data.get('products') or [])}건")
                return data
        except Exception:
            pass
    print("[daily] 최근 7일 안에 일별 스냅샷이 없다 — trend_board 로 넘어간다")
    return None


def _trend(series):
    """수요 지수 배열에서 '지금 오르는가'를 뽑는다. (최근 7일 평균 ÷ 그 앞 30일 평균).

    1.0 보다 크면 상승. 데이터가 모자라면 None — 모르면 말하지 않는다.
    """
    v = [x for x in (series or []) if isinstance(x, (int, float))]
    if len(v) < 20:
        return None
    recent, before = v[-7:], v[-37:-7]
    if not before or sum(before) == 0:
        return None
    return (sum(recent) / len(recent)) / (sum(before) / len(before))


def from_daily(data):
    """일별 스냅샷의 products 를 리포트가 쓰는 형태로. **같은 품목이 여러 줄로 들어오므로 합친다**
    (2026-11-13 실측: '도마 가위' 3줄, '다기능 채칼' 4줄). 이름 기준으로 묶고 영상·채널을 합산한다."""
    merged = {}
    for p in (data.get("products") or []):
        name = (p.get("name") or "").strip()
        if not name:
            continue
        m = merged.setdefault(name, {"name": name, "keyword": p.get("keyword") or name,
                                     "evidence": [], "price_band": p.get("price_band") or "",
                                     "chans": set(), "videos": 0, "views": 0, "age": 999,
                                     "mentions": p.get("mentions"), "demand": p.get("demand"),
                                     "overseas": p.get("overseas")})
        ev = (p.get("evidence") or "").strip()
        if ev and ev not in m["evidence"]:
            m["evidence"].append(ev)
        for v in (p.get("videos") or []):
            if v.get("channel_id"):
                m["chans"].add(v["channel_id"])
            m["videos"] += 1
            m["views"] += int(v.get("views") or 0)
            if v.get("age_days") is not None:
                m["age"] = min(m["age"], int(v["age_days"]))
    out = []
    for m in merged.values():
        m["channels"] = len(m["chans"])
        m.pop("chans")
        m["rise"] = _trend(m.get("demand"))
        out.append(m)
    out = _fold_similar(out)
    out.sort(key=lambda x: (-x["channels"], -x["views"]))
    return out


def _fold_similar(rows):
    """이름만 다른 같은 물건을 합친다.

    2026-11-13 실물 확인에서 '전동 다지기'와 '전동 야채다지기'가 4·5위로 나란히 나왔다.
    독자는 바로 '같은 거 아니냐'고 본다. **짧은 쪽 이름의 어절이 모두 긴 쪽에 들어 있으면**
    같은 물건으로 보고 긴 쪽(더 구체적인 이름)으로 합친다. 어절이 1개뿐인 이름은
    과하게 합쳐질 수 있어 제외한다.
    """
    rows = sorted(rows, key=lambda r: -len(r["name"]))
    kept = []
    for r in rows:
        w = [x for x in r["name"].split() if x]
        folded = False
        if len(w) >= 2:
            for k in kept:
                kn = k["name"].replace(" ", "")
                if all(x in kn for x in w):
                    k["videos"] += r["videos"]
                    k["views"] += r["views"]
                    k["channels"] = max(k["channels"], r["channels"])
                    for e in r.get("evidence") or []:
                        if e not in k["evidence"]:
                            k["evidence"].append(e)
                    k.setdefault("also", []).append(r["name"])
                    folded = True
                    break
        if not folded:
            kept.append(r)
    return kept


def load_mentions():
    """상품 단위 언급 빈도. 없으면 None — 품목 단위만으로도 글은 완성돼야 한다.

    **해외 상품 규칙(사용자 지시 2026-11-12)**: 해외에서 뜬 물건도 **한국에서 정식 판매 중이면**
    소개한다. 판정은 캐스토가 설명란 링크로 하고(`overseas_only`), 직구 전용은 여기서 뺀다.
    """
    try:
        r = requests.get(MENTIONS_RAW, timeout=20)
        if r.status_code != 200:
            print(f"[mentions] 아직 없음(HTTP {r.status_code}) — 품목 단위로만 진행")
            return None
        data = r.json()
    except Exception as e:
        print(f"[mentions] 못 받음: {str(e)[:70]} — 품목 단위로만 진행")
        return None
    rows = data.get("products") if isinstance(data, dict) else data
    rows = [x for x in (rows or []) if not x.get("overseas_only")]
    print(f"[mentions] 상품 {len(rows)}건(직구 전용 제외)")
    return rows


def pick_mention(rows, keyword, name):
    """품목에 해당하는 상품 중 **서로 다른 채널 수**가 가장 많은 것 — 유행의 폭이 곧 신호다."""
    if not rows:
        return None
    hay = (str(keyword or "") + " " + str(name or "")).replace(" ", "")
    best = None
    for r in rows:
        for cand in (r.get("name_candidates") or []):
            c = str(cand).replace(" ", "")
            if not c:
                continue
            if c in hay or any(w and w in c for w in str(name or "").split()):
                if not best or (r.get("channels") or 0) > (best.get("channels") or 0):
                    best = r
                break
    return best


def load_config():
    """워크플로에서는 build_config.py 가 만든 config.json. 없으면 빈 설정으로 진행."""
    try:
        with open("config.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def from_board(board):
    """trend_board 를 일별과 같은 형태로 — 일별 스냅샷을 못 받았을 때의 대비책."""
    seen, out = set(), []
    for it in (board.get("briefing") or []) + (board.get("all") or []):
        k = it.get("key")
        if not k or k in seen or it.get("blocked") or it.get("quadrant") == "ignore":
            continue
        seen.add(k)
        out.append({"name": it.get("name") or "", "keyword": it.get("keyword") or it.get("name") or "",
                    "evidence": [], "price_band": it.get("price_band") or "",
                    "channels": it.get("channels") or 0, "videos": it.get("videos") or 0,
                    "views": int(it.get("exposure") or 0), "age": 999,
                    "mentions": it.get("mentions"), "demand": None, "overseas": None,
                    "rise": (1.1 if it.get("delta") == "up" else None)})
    out.sort(key=lambda x: (-x["channels"], -x["views"]))
    return out


def rank(rows):
    """노출만 넓고 **검색이 식는** 품목을 1위로 올리지 않는다.

    2026-11-13 실측에서 '전동 스프레이'가 채널 13곳으로 노출 1위였는데 수요 추세는 0.83배(하락)였다.
    그걸 '이번 주 유행템' 맨 앞에 두면 글이 틀린다. 그래서 **수요가 빠지는 품목은 뒤로 미루고**,
    본문에 그 사실을 그대로 적는다(숨기지 않는다).
    """
    def key(r):
        falling = 1 if (r.get("rise") is not None and r["rise"] < 1.0) else 0
        return (falling, -(r.get("channels") or 0), -(r.get("views") or 0))
    return sorted(rows, key=key)


def eligible(rows):
    """근거 하한: 영상 3개·채널 3곳 미만은 '이번 주 유행'이라고 쓸 수 없다."""
    return [r for r in rows
            if (r.get("videos") or 0) >= MIN_VIDEOS and (r.get("channels") or 0) >= MIN_CHANNELS]


def enrich(rows, cfg):
    """대장 링크·기준가를 붙인다. 각 층은 실패해도 나머지로 진행."""
    for r in rows:
        pr = products_mod.find_for({"title": r["name"], "keyword": r["keyword"]})
        r["product"] = pr
        r["link"] = (pr or {}).get("coupang_url") or ""
        r["price"] = (pr or {}).get("price")
        r["price_at"] = (pr or {}).get("price_at")
        r["ref"] = price_ref.lookup(r["name"]) if price_ref.ready() else None
        if pr and pr.get("price_band") and not r.get("price_band"):
            r["price_band"] = pr["price_band"]
    return rows[:WANT]


def _overseas_line(r):
    """해외에서 먼저 떴는지. 사용자 지시: 해외 유행템도 **한국에서 살 수 있으면** 소개한다."""
    ov = r.get("overseas") or {}
    v, lead = ov.get("verdict"), ov.get("lead_days")
    if v == "overseas_first" and isinstance(lead, int) and lead >= 30:
        return (f"해외에서 약 {lead}일 먼저 올라온 품목입니다. "
                f"국내에 막 들어온 단계라 아직 아는 사람이 적습니다.")
    if v == "korea_only":
        return "해외에는 거의 없고 국내에서만 도는 품목입니다."
    return ""


def reasons(r, days):
    """'왜 뜨는지' — 실측 숫자만. 없는 축은 문장을 만들지 않는다. LLM 은 쓰지 않는다."""
    out = []
    c, v, w = r.get("channels") or 0, r.get("videos") or 0, r.get("views") or 0
    if c and v:
        line = f"최근 이 품목을 다룬 영상이 {v}개, 올린 채널이 {c}곳입니다."
        if w:
            line += f" 합산 조회수는 약 {w:,}회입니다."
        out.append(line)
    rise = r.get("rise")
    if rise is not None:
        if rise >= 1.1:
            out.append(f"네이버 쇼핑 검색 수요가 최근 일주일 들어 직전 한 달보다 "
                       f"{rise:.2f}배로 올라왔습니다.")
        elif rise < 0.95:
            # 불리한 숫자도 적는다. 숨기면 글이 광고가 된다.
            out.append(f"다만 네이버 쇼핑 검색 수요는 직전 한 달 대비 {rise:.2f}배로 "
                       f"오히려 줄고 있습니다. 영상에서 먼저 뜬 쪽에 가깝습니다.")
    ovl = _overseas_line(r)
    if ovl and len(out) < 3:
        out.append(ovl)
    mn = r.get("mentions")
    if mn and len(out) < 3:
        out.append(f"네이버 블로그·카페 언급이 {int(mn):,}건 잡힙니다.")
    ev = (r.get("evidence") or [None])[0]
    if ev and len(out) < 3:
        out.append(ev if ev.endswith(".") else ev + ".")
    return out[:3]


def section(i, r, days, slug):
    name = html.escape(r["name"])
    rs = "".join(f"<li>{html.escape(x)}</li>" for x in reasons(r, days))
    h = [f"<h2>{i}. {name}</h2>", f"<ul>{rs}</ul>"]
    if r.get("price"):
        h.append(f"<p><strong>{int(r['price']):,}원</strong>"
                 + (f" ({html.escape(str(r['price_at']))} 기준)" if r.get("price_at") else "") + "</p>")
    elif r.get("price_band"):
        h.append(f"<p>가격대는 {html.escape(str(r['price_band']))}입니다.</p>")
    ref = r.get("ref")
    if ref:
        h.append(f"<p>한국소비자원 참가격 조사에서는 평균 {ref['avg']:,}원, 최저 {ref['min']:,}원으로 "
                 f"잡힙니다({ref['n']}건). 온라인 가격이 이보다 낮은지 보면 됩니다.</p>")
    if r.get("link"):
        url = products_mod.with_subid(r["link"], products_mod.safe_subid(slug, keyword=r["keyword"]))
        h.append(f'<p><a href="{url}" target="_blank" rel="nofollow sponsored noopener">'
                 f'{name} 쿠팡에서 보기</a></p>')
    return "".join(h)


def build(src_label, rows, days):
    today = dt.date.today()
    slug = f"weekly-trend-{today:%Y%m%d}"
    linked = sum(1 for r in rows if r.get("link"))
    how = ["노출: 유튜브에 올라온 영상 수·채널 수·조회수 집계",
           "검색 수요: 네이버 쇼핑 검색 지수의 최근 일주일 대 직전 한 달 비교"]
    if any(r.get("overseas") for r in rows):
        how.append("해외 선행 여부: 같은 품목의 해외 영상이 국내보다 먼저 올라왔는지 비교")
    if any(r.get("ref") for r in rows):
        how.append("기준가: 공공데이터포털 「한국소비자원 생필품 가격 정보」")
    intro = (f"<p>{NOTICE}</p>"
             f"<p>느낌으로 고른 목록이 아닙니다. 유튜브에 올라온 영상 수와 채널 수를 세고, "
             f"거기에 네이버에서 실제로 검색이 늘고 있는지를 겹쳐 다섯 개를 골랐습니다. "
             f"<strong>검색이 줄고 있는 품목은 그 사실도 그대로 적었습니다.</strong></p>"
             f"<p>집계 기준일은 {html.escape(src_label)}입니다. "
             f"가격은 적힌 날짜 기준이며 수시로 바뀝니다.</p>")
    body = "".join(section(i, r, days, slug) for i, r in enumerate(rows, 1))
    tail = ("<h2>이 목록을 만든 방법</h2><ul>"
            + "".join(f"<li>{html.escape(x)}</li>" for x in how)
            + "<li>순위는 검색 수요가 빠지지 않는 품목을 먼저, 그 안에서 다룬 채널이 많은 순으로 놓았습니다.</li>"
              "<li>영상 3개·채널 3곳 미만은 '유행'이라고 보기 어려워 뺐습니다.</li></ul>"
              "<p>다음 주에 같은 기준으로 다시 집계합니다.</p>")
    return {"title": f"이번 주 유행템 5가지 ({today.month}월 {today.day}일 집계)",
            "slug": slug, "html": intro + body + tail,
            "meta": "유튜브 노출과 네이버 검색 수요를 겹쳐 고른 이번 주 유행템 5가지. "
                    "검색이 식고 있는 품목은 그 사실도 함께 적었습니다.",
            "seo_title": f"이번 주 유행템 5가지 — {today.month}/{today.day} 집계",
            "focus_keyword": "이번 주 유행템",
            "category": "트렌드", "wp_category": "트렌드", "wp_category_slug": "trend",
            "_linked": linked}


def link_block(rows):
    """링크 없는 품목의 '사람이 할 일' 블록 — 복사해서 바로 쓸 수 있게."""
    need = [r for r in rows if not r.get("link")]
    if not need:
        return "모든 품목에 링크가 있습니다 — 바로 발행할 수 있습니다."
    lines = [f"쿠팡 파트너스 딥링크가 필요한 품목 {len(need)}개 "
             f"(생성: {PARTNERS_LINK_UI})", ""]
    for r in need:
        lines.append(f"  · {r['name']}   검색어: {r['keyword']}")
    lines += ["", "만든 링크를 아래 형식으로 픽토 채팅에 붙여넣으면 대장에 넣고 발행합니다.", ""]
    for r in need:
        lines.append(f"{r['name']} = ")
    return "\n".join(lines)


# ─── 실행 ────────────────────────────────────────────────────────────────────
def main():
    publish = "--publish" in sys.argv
    cfg = load_config()
    if not price_ref.ready():
        print("[price_ref] PRICE_REF_API_KEY 없음 — 소비자원 기준가 줄은 생략한다")

    daily = load_daily()
    if daily:
        rows, src = from_daily(daily), str(daily.get("date") or "")
    else:
        board = load_board()
        if not board:
            print("::error::캐스토 트렌드 데이터를 못 받았다 — 추측으로 글을 쓰지 않는다")
            return 1
        rows, src = from_board(board), str(board.get("updated") or "")
        print(f"::warning::일별 스냅샷이 없어 trend_board({src})로 돌았다 — 집계가 묵었을 수 있다")

    rows = enrich(rank(eligible(rows)), cfg)
    if len(rows) < MIN_PUBLISH_LINKS:
        print(f"::error::근거 하한을 통과한 품목이 {len(rows)}개뿐이다")
        return 3

    art = build(src, rows, 0)
    os.makedirs("data", exist_ok=True)
    with open(PREVIEW, "w", encoding="utf-8") as f:
        f.write(f"<h1>{html.escape(art['title'])}</h1>" + art["html"])
    with open(PICK, "w", encoding="utf-8") as f:
        json.dump({"date": dt.date.today().isoformat(), "source": src,
                   "rows": [{"name": r["name"], "keyword": r["keyword"],
                             "channels": r["channels"], "videos": r["videos"],
                             "views": r["views"], "rise": r.get("rise"),
                             "band": r.get("price_band"), "has_link": bool(r.get("link"))}
                            for r in rows]}, f, ensure_ascii=False, indent=1)

    print(f"[pick] 집계 {src} · 선정 {len(rows)}개 · 링크 있음 {art['_linked']}개 · 미리보기 {PREVIEW}")
    print("-" * 60)
    print(link_block(rows))
    print("-" * 60)

    if not publish:
        return 0
    if art["_linked"] < MIN_PUBLISH_LINKS:
        print(f"::error::링크가 {art['_linked']}개뿐이다(하한 {MIN_PUBLISH_LINKS}) — "
              f"링크 없는 리포트는 수익이 0이라 발행하지 않는다")
        return 4
    import publisher
    wp = dict(cfg.get("wordpress") or {})
    if not wp.get("enabled"):
        print("::warning::wordpress.enabled 가 False — 발행 생략")
        return 0
    print(f"[wp] 발행: {publisher.publish_to_wordpress(art, wp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
