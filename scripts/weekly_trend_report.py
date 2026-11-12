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


def candidates(board):
    """blocked·ignore 제외, 근거 하한 통과, peak → 상승 → 나머지 순. 노출 합 내림차순."""
    seen, pool = set(), []
    for item in (board.get("briefing") or []) + (board.get("all") or []):
        k = item.get("key")
        if not k or k in seen or item.get("blocked"):
            continue
        seen.add(k)
        if item.get("quadrant") == "ignore":
            continue
        if (item.get("videos") or 0) < MIN_VIDEOS or (item.get("channels") or 0) < MIN_CHANNELS:
            continue   # 영상 1~2개를 '이번 주 유행'이라고 쓸 수 없다
        tier = 0 if item.get("quadrant") == "peak" else (1 if item.get("delta") == "up" else 2)
        pool.append((tier, -(item.get("exposure") or 0), item))
    pool.sort(key=lambda x: (x[0], x[1]))
    return [p[2] for p in pool]


def enrich(items, cfg):
    """검색량·자동완성·대장 링크·기준가를 붙인다. 각 층은 실패해도 나머지로 진행."""
    mentions = load_mentions()
    kws = [(x.get("keyword") or x.get("name")) for x in items]
    vol = demand.monthly_volume(kws, cfg) or {}
    if vol:
        print(f"[demand] 검색광고 월간 검색량 {len(vol)}건 확보")
    else:
        print(f"[demand] 검색량 없음(키 미배포 또는 실패: {demand.LAST_ERR or '-'}) — 이 층은 빼고 진행")
    out = []
    for it in items:
        kw = it.get("keyword") or it.get("name")
        pr = products_mod.find_for({"title": it.get("name") or "", "keyword": kw})
        band = (pr or {}).get("price_band") or it.get("price_band") or ""
        ref = price_ref.lookup(it.get("name") or kw) if price_ref.ready() else None
        out.append({"item": it, "kw": kw, "volume": vol.get(kw),
                    "product": pr, "band": band, "ref": ref,
                    "mention": pick_mention(mentions, kw, it.get("name")),
                    "link": (pr or {}).get("coupang_url") or ""})
    if vol:
        # 검색량이 잡힌 품목은 수요 순으로 올린다 — '찾아오는 사람'이 유입의 전부다.
        out.sort(key=lambda r: (r["volume"] is None, -(r["volume"] or 0)))
        out = [r for r in out if r["volume"] is None or r["volume"] >= MIN_VOLUME]
    return out[:WANT]


# ─── 본문 ────────────────────────────────────────────────────────────────────
def reasons(row, days):
    it = row["item"]
    out = []
    v, c, ex = it.get("videos"), it.get("channels"), it.get("exposure")
    if v and c and ex:
        out.append(f"최근 {days}일 동안 이 품목을 다룬 유튜브 영상이 {v}개, "
                   f"올린 채널이 {c}곳입니다. 합산 노출은 약 {int(ex):,}회입니다.")
    mn = row.get("mention")
    if mn and mn.get("channels"):
        out.append(f"이 상품을 영상 설명란에 직접 건 유튜브 채널이 "
                   f"{int(mn['channels'])}곳입니다(영상 {int(mn.get('videos') or 0)}개). "
                   f"한 채널이 밀어준 게 아니라 여러 사람이 같은 물건을 집었다는 뜻입니다.")
    if row["volume"]:
        out.append(f"네이버에서 이 키워드를 한 달에 약 {int(row['volume']):,}번 검색합니다. "
                   f"영상으로만 뜬 게 아니라 직접 찾아보는 사람이 있다는 뜻입니다.")
    mv = it.get("median_views")
    if mv and len(out) < 2:
        if (c or 0) >= SPREAD_CHANNELS:
            out.append(f"영상 한 편의 중앙 조회수가 {int(mv):,}회입니다. "
                       f"여러 채널에 퍼져 있어 한두 곳이 끌어올린 수치가 아닙니다.")
        else:
            out.append(f"영상 한 편의 중앙 조회수가 {int(mv):,}회입니다. "
                       f"다만 올린 채널이 {c or 0}곳뿐이라 아직 한쪽에 쏠린 관심입니다.")
    mn = it.get("mentions")
    if mn and len(out) < 2:
        out.append(f"네이버 블로그·카페 언급이 {int(mn):,}건 잡힙니다.")
    if it.get("delta") == "up" and len(out) < 2:
        out.append("직전 집계보다 지표가 올라왔습니다.")
    return out[:2]


def section(i, row, days, slug):
    it = row["item"]
    name = html.escape(it.get("name") or row["kw"] or "")
    rs = "".join(f"<li>{html.escape(r)}</li>" for r in reasons(row, days))
    h = [f"<h2>{i}. {name}</h2>"]
    q = QUADRANT_KO.get(it.get("quadrant"))
    if q:
        h.append(f"<p><strong>지금 상태</strong>: {html.escape(q)}</p>")
    h.append(f"<ul>{rs}</ul>")
    pr = row["product"] or {}
    price, at = pr.get("price"), pr.get("price_at")
    if price:
        # 금액에는 **반드시 조사일**을 붙인다. 날짜 없는 금액은 언제 틀렸는지 알 수 없다.
        sold_out = str(pr.get("availability") or "").lower() in ("outofstock", "soldout")
        h.append(f"<p><strong>{int(price):,}원</strong>"
                 + (f" ({html.escape(str(at))} 기준)" if at else "")
                 + ("  — 현재 품절입니다." if sold_out else "") + "</p>")
    elif row["band"]:
        h.append(f"<p>가격대는 {html.escape(str(row['band']))}입니다.</p>")
    ref = row["ref"]
    if ref:
        h.append(f"<p>참고로 한국소비자원 참가격의 생필품 조사 기록에서 이 품목은 "
                 f"평균 {ref['avg']:,}원, 최저 {ref['min']:,}원으로 조사됐습니다"
                 f"({ref['n']}건{', ' + html.escape(str(ref['day'])) + ' 기준' if ref.get('day') else ''}). "
                 f"온라인 가격이 이보다 낮은지 보면 됩니다.</p>")
    if row["link"]:
        url = products_mod.with_subid(row["link"], products_mod.safe_subid(slug, keyword=row["kw"]))
        h.append(f'<p><a href="{url}" target="_blank" rel="nofollow sponsored noopener">'
                 f'{name} 쿠팡에서 보기</a></p>')
    # 링크가 없으면 **아무 문장도 넣지 않는다** — "아직 링크를 걸어두지 않았습니다"는
    # 독자에게 아무 쓸모가 없는 운영 사정이다. 발행 자체가 링크 3개 하한으로 막혀 있다.
    return "".join(h)


def build(board, rows, days):
    today = dt.date.today()
    slug = f"weekly-trend-{today:%Y%m%d}"
    linked = sum(1 for r in rows if r["link"])
    how = ["노출·공급: 유튜브 데이터 API로 최근 %d일 영상 집계" % days]
    if any(r["volume"] for r in rows):
        how.append("검색 수요: 네이버 검색광고 키워드 도구의 월간 검색수")
    if any(r["ref"] for r in rows):
        how.append("기준가: 공공데이터포털 「한국소비자원 생필품 가격 정보」")
    intro = (f"<p>{NOTICE}</p>"
             f"<p>느낌으로 고른 목록이 아닙니다. 최근 {days}일 동안 유튜브에 올라온 영상 수와 "
             f"채널 수, 노출량을 모으고, 거기에 네이버에서 실제로 몇 번 검색되는지를 겹쳐 "
             f"다섯 개를 골랐습니다. 품목마다 왜 올라왔는지를 숫자로 적었습니다.</p>"
             f"<p>집계 기준일은 {html.escape(str(board.get('updated')))}입니다. "
             f"가격은 글에 적힌 날짜 기준이며, 쿠팡에서 수시로 바뀝니다.</p>")
    body = "".join(section(i, r, days, slug) for i, r in enumerate(rows, 1))
    tail = ("<h2>이 목록을 만든 방법</h2><ul>"
            + "".join(f"<li>{html.escape(x)}</li>" for x in how)
            + "<li>순위는 노출과 실수요가 같이 높은 품목을 먼저, 그다음 올라오는 품목을 "
              "검색량 순으로 놓았습니다.</li></ul>"
              "<p>다음 주에 같은 기준으로 다시 집계합니다.</p>")
    return {"title": f"이번 주 유행템 5가지 ({today.month}월 {today.day}일 집계)",
            "slug": slug, "html": intro + body + tail,
            "meta": f"최근 {days}일 유튜브 노출과 네이버 검색량을 겹쳐 고른 유행템 5가지. "
                    f"품목마다 오른 이유를 숫자로 정리했습니다.",
            "seo_title": f"이번 주 유행템 5가지 — {today.month}/{today.day} 집계",
            "focus_keyword": "이번 주 유행템",
            "category": "트렌드", "wp_category": "트렌드", "wp_category_slug": "trend",
            "_linked": linked}


def link_block(rows):
    """링크 없는 품목의 '사람이 할 일' 블록 — 복사해서 바로 쓸 수 있게."""
    need = [r for r in rows if not r["link"]]
    if not need:
        return "모든 품목에 링크가 있습니다 — 바로 발행할 수 있습니다."
    lines = [f"쿠팡 파트너스 딥링크가 필요한 품목 {len(need)}개 "
             f"(생성: {PARTNERS_LINK_UI})", ""]
    for r in need:
        lines.append(f"  · {r['item'].get('name')}   검색어: {r['kw']}")
    lines += ["", "만든 링크를 아래 형식으로 픽토 채팅에 붙여넣으면 대장에 넣고 발행합니다.", ""]
    for r in need:
        lines.append(f"{r['item'].get('name')} = ")
    return "\n".join(lines)


# ─── 실행 ────────────────────────────────────────────────────────────────────
def main():
    publish = "--publish" in sys.argv
    board = load_board()
    if not board:
        print("::error::캐스토 trend_board.json 을 못 받았다 — 추측으로 글을 쓰지 않는다")
        return 1
    days = int(board.get("snapshot_days") or 24)
    cfg = load_config()
    if not price_ref.ready():
        print("[price_ref] PRICE_REF_API_KEY 없음 — 소비자원 기준가 줄은 생략한다")

    rows = enrich(candidates(board), cfg)
    if len(rows) < MIN_PUBLISH_LINKS:
        print(f"::error::근거 하한을 통과한 품목이 {len(rows)}개뿐이다 — 집계가 묵었는지 확인할 것")
        return 3
    art = build(board, rows, days)
    os.makedirs("data", exist_ok=True)
    with open(PREVIEW, "w", encoding="utf-8") as f:
        f.write(f"<h1>{html.escape(art['title'])}</h1>" + art["html"])
    with open(PICK, "w", encoding="utf-8") as f:
        json.dump({"date": dt.date.today().isoformat(),
                   "board_updated": board.get("updated"),
                   "rows": [{"name": r["item"].get("name"), "keyword": r["kw"],
                             "volume": r["volume"], "band": r["band"],
                             "has_link": bool(r["link"])} for r in rows]},
                  f, ensure_ascii=False, indent=1)

    print(f"[pick] 선정 {len(rows)}개 · 링크 있음 {art['_linked']}개 · 미리보기 {PREVIEW}")
    print("─" * 60)
    print(link_block(rows))
    print("─" * 60)

    if not publish:
        return 0
    if art["_linked"] < MIN_PUBLISH_LINKS:
        print(f"::error::링크가 {art['_linked']}개뿐이다(하한 {MIN_PUBLISH_LINKS}) — "
              f"링크 없는 리포트는 수익이 0이라 발행하지 않는다")
        return 4
    import publisher
    wp = dict(cfg.get("wordpress") or {})
    if not wp.get("enabled"):
        print("::warning::wordpress.enabled 가 False — 발행 생략(로컬 config는 예시값이다)")
        return 0
    url = publisher.publish_to_wordpress(art, wp)
    print(f"[wp] 발행: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
