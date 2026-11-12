# -*- coding: utf-8 -*-
"""「이번 주 유행템」 주간 리포트 — 캐스토 실측 트렌드 + 쿠팡 공식API 가격/링크 (2026-11-12 신설).

**지시 근거**: famto 2026-11-11 — 주 1회 글 1편, 1~20만 원대 상위 5개, 상품마다 '왜 뜨는지'
근거 1~2개 + 쿠팡 링크(대가성 문구). **공식 API만 — 쿠팡 리뷰·인스타 크롤링 금지.**

**왜 이 글이 수익 축인가**
  픽담의 실측 병목은 색인(31/37)이 아니라 **유입(주 41세션)과 클릭(카드 노출 53·클릭 0)**이다.
  개별 제품 글은 '검색해서 오는 사람'을 기다리지만, 유행템 리포트는 **지금 뜨는 품목**을
  묶어서 다루므로 ①검색 수요가 아직 안 생긴 품목도 태울 수 있고 ②한 글에 5개 링크가 들어가
  노출당 클릭 기회가 5배다. 캐스토 쇼츠 CTA의 착지점으로도 개별 글보다 어울린다.

**근거는 전부 실측치만 쓴다**
  '왜 뜨는지'를 LLM이 쓰면 그럴듯한 거짓말이 된다(이 레포의 상습 실패). 그래서 근거 문장은
  캐스토 `trend_board.json`의 숫자(영상 수·채널 수·노출 합·중앙 조회수·언급량·직전 대비)와
  쿠팡 API의 가격·리뷰 수로만 조립한다. LLM은 쓰지 않는다.

**데이터 경계**
  캐스토 레포는 **읽기만** 한다(공개 레포 raw, 토큰 불필요). 캐스토 파일을 수정하지 않는다.

실행:  python scripts/weekly_trend_report.py            # dry-run(파일로만 출력)
       python scripts/weekly_trend_report.py --publish  # 실제 발행
"""
import datetime as dt
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import coupang_api
import products as products_mod

RAW = "https://raw.githubusercontent.com/one2k87/Casto/main/data/trend_board.json"
LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "..", "Casto", "data", "trend_board.json")
PREVIEW = "data/trend_report_preview.html"
LOG = "data/trend_report_log.json"
NOTICE = ("이 포스팅은 쿠팡 파트너스 활동의 일환으로, "
          "이에 따른 일정액의 수수료를 제공받습니다.")
BAND_LO, BAND_HI = 10_000, 200_000
CHEAP_HI = 30_000          # 하단 '같이 담는 것들' 비교표 상한
WANT = 5
MIN_VIDEOS, MIN_CHANNELS = 3, 3   # 근거 하한 — 영상 1개·채널 1곳은 "유행"이 아니다
SPREAD_CHANNELS = 5                  # 이보다 적으면 "대형 채널 탓이 아니다"라고 말할 수 없다
QUADRANT_KO = {"peak": "정점(노출·실수요 둘 다 높음)",
               "bubble": "노출 과열(실수요는 아직 덜 따라옴)",
               "ignore": "관심 낮음",
               "rising": "상승 중"}


def load_board():
    """원격(공개 raw) 우선, 실패 시 로컬 체크아웃. 둘 다 없으면 None — 추측으로 글을 쓰지 않는다."""
    try:
        r = requests.get(RAW, timeout=25)
        if r.status_code == 200:
            print("[board] 캐스토 raw 에서 받음")
            return r.json()
        print(f"[board] raw HTTP {r.status_code}")
    except Exception as e:
        print(f"[board] raw 실패: {str(e)[:90]}")
    try:
        with open(LOCAL, encoding="utf-8") as f:
            print("[board] 로컬 체크아웃에서 읽음")
            return json.load(f)
    except Exception:
        return None


def rank(board):
    """peak 먼저, 그다음 상승(delta=up), 그 안에서 노출 합 큰 순. ignore·차단은 버린다."""
    seen, pool = set(), []
    for item in (board.get("briefing") or []) + (board.get("all") or []):
        k = item.get("key")
        if not k or k in seen or item.get("blocked"):
            continue
        seen.add(k)
        q, d = item.get("quadrant"), item.get("delta")
        if q == "ignore":
            continue
        if (item.get("videos") or 0) < MIN_VIDEOS or (item.get("channels") or 0) < MIN_CHANNELS:
            continue   # 근거가 영상 1~2개면 '이번 주 유행'이라고 쓸 수 없다
        tier = 0 if q == "peak" else (1 if d == "up" else 2)
        pool.append((tier, -(item.get("exposure") or 0), item))
    pool.sort(key=lambda x: (x[0], x[1]))
    return [p[2] for p in pool]


def reasons(item, prod, days):
    """'왜 뜨는지' 1~2개 — 실측치만. 없는 축은 문장을 만들지 않는다."""
    out = []
    v, c, ex = item.get("videos"), item.get("channels"), item.get("exposure")
    if v and c and ex:
        out.append(f"최근 {days}일 유튜브에서 이 품목을 다룬 영상이 {v}개, "
                   f"올린 채널이 {c}곳입니다. 합산 노출은 약 {int(ex):,}회입니다.")
    mv = item.get("median_views")
    if mv and len(out) < 2:
        # ⚠️ '대형 채널 탓이 아니다'는 채널이 여러 곳일 때만 참이다. 영상 1개·채널 1곳에
        #    이 문장을 붙였다가 거짓 주장이 됐다(2026-11-12 미리보기 실물 확인에서 잡음).
        if (c or 0) >= SPREAD_CHANNELS:
            out.append(f"영상 한 편의 중앙 조회수가 {int(mv):,}회입니다. "
                       f"여러 채널에 퍼져 있어 한두 곳이 끌어올린 수치가 아닙니다.")
        else:
            out.append(f"영상 한 편의 중앙 조회수가 {int(mv):,}회입니다. "
                       f"다만 올린 채널이 {c or 0}곳뿐이라 아직 한쪽에 쏠린 관심입니다.")
    mn = item.get("mentions")
    if mn and len(out) < 2:
        out.append(f"네이버 블로그·카페 언급이 {int(mn):,}건 잡힙니다.")
    if prod and prod.get("review_count") and len(out) < 2:
        out.append(f"쿠팡 리뷰가 {prod['review_count']:,}건입니다. "
                   f"리뷰는 구매해야만 남을 수 있어 꾸며내기 어려운 숫자입니다.")
    if item.get("delta") == "up" and len(out) < 2:
        out.append("직전 집계보다 지표가 올라왔습니다.")
    return out[:2]


def section(i, item, prod, days):
    name = html.escape(item.get("name") or item.get("keyword") or "")
    rs = "".join(f"<li>{html.escape(r)}</li>" for r in reasons(item, prod, days))
    q = QUADRANT_KO.get(item.get("quadrant"), item.get("quadrant") or "")
    h = [f'<h2>{i}. {name}</h2>',
         f'<p><strong>지금 상태</strong>: {html.escape(q)}</p>',
         f'<ul>{rs}</ul>']
    if prod:
        pn = html.escape(prod.get("name") or name)
        rocket = "이고 로켓배송" if prod.get("rocket") else ""
        h.append(f'<p>쿠팡 기준 가격은 <strong>{prod["price"]:,}원</strong>'
                 f'{rocket}입니다. (조회 시점 가격이라 바뀔 수 있습니다)</p>')
        h.append(f'<p><a href="{prod["url"]}" target="_blank" rel="nofollow sponsored noopener">'
                 f'{pn} 쿠팡에서 보기</a></p>')
    else:
        h.append('<p>이 품목은 가격대(1만~20만 원) 안에서 고를 만한 상품을 '
                 '이번 집계에서는 찾지 못했습니다. 링크를 넣지 않았습니다.</p>')
    return "".join(h)


def cheap_table(rows):
    if not rows:
        return ""
    tr = "".join(
        f'<tr><td>{html.escape(r["label"])}</td>'
        f'<td style="text-align:right">{r["price"]:,}원</td>'
        f'<td style="text-align:center">{"○" if r["rocket"] else "-"}</td>'
        f'<td><a href="{r["url"]}" target="_blank" rel="nofollow sponsored noopener">보기</a></td></tr>'
        for r in rows)
    return ('<h2>3만 원 이하, 같이 담으면 배송비가 안 아까운 것들</h2>'
            '<p>위 품목과 같은 집계에서 가격이 3만 원 이하로 확인된 것만 모았습니다.</p>'
            '<figure class="wp-block-table"><table>'
            '<thead><tr><th>제품</th><th style="text-align:right">가격</th>'
            '<th style="text-align:center">로켓</th><th>링크</th></tr></thead>'
            f'<tbody>{tr}</tbody></table></figure>')


def build(board, picks, cheap, days):
    today = dt.date.today()
    week = today.isocalendar()[1]
    title = f"이번 주 유행템 5가지 ({today.month}월 {today.day}일 기준)"
    intro = (f'<p>{NOTICE}</p>'
             f'<p>이 글은 느낌으로 고른 목록이 아닙니다. 최근 {days}일 동안 '
             f'유튜브에 올라온 영상 수·채널 수·노출량과 네이버 언급량을 모아 점수를 내고, '
             f'그중 쿠팡에서 1만~20만 원대로 살 수 있는 것만 다섯 개 골랐습니다. '
             f'품목마다 왜 올라왔는지를 숫자로 적었습니다.</p>'
             f'<p>집계 기준일은 {html.escape(str(board.get("updated")))}입니다.</p>')
    body = "".join(section(i, it, pr, days) for i, (it, pr) in enumerate(picks, 1))
    tail = (cheap_table(cheap) +
            '<h2>이 목록을 만든 방법</h2>'
            f'<ul><li>노출·공급: 유튜브 데이터 API로 최근 {days}일 영상 집계</li>'
            '<li>언급량: 네이버 검색 API</li>'
            '<li>가격·리뷰·링크: 쿠팡 파트너스 공개 API</li>'
            '<li>순위는 정점 품목을 먼저, 그다음 직전 집계보다 오른 품목을 노출 합 순으로 놓았습니다.</li></ul>'
            f'<p>다음 주 같은 기준으로 다시 집계합니다.</p>')
    return {
        "title": title,
        "slug": f"weekly-trend-{today:%Y%m%d}",
        "html": intro + body + tail,
        "meta": f"최근 {days}일 노출·언급 집계로 고른 1만~20만 원대 유행템 5가지. 품목마다 오른 이유를 숫자로 정리했습니다.",
        "seo_title": f"이번 주 유행템 5가지 — {today.month}/{today.day} 집계",
        "focus_keyword": "이번 주 유행템",
        "category": "트렌드",
        "wp_category": "트렌드",
        "wp_category_slug": "trend",
        "_week": week,
    }


def main():
    publish = "--publish" in sys.argv
    board = load_board()
    if not board:
        print("::error::캐스토 trend_board.json 을 못 받았다 — 글을 만들지 않는다")
        return 1
    days = int(board.get("snapshot_days") or 24)
    if not coupang_api.ready():
        print("::warning::COUPANG_ACCESS_KEY/SECRET 없음 — 가격·링크 없이 글을 만들 수 없다. "
              "금고에 키가 있으니 keys.sh apply 로 Picto 에 배포할 것(요청은 keys/requests.txt 에 적어 뒀다)")
        return 2

    picks, cheap, tried, skipped = [], [], 0, []
    for item in rank(board):
        if len(picks) >= WANT:
            break
        kw = item.get("keyword") or item.get("name")
        if not kw:
            continue
        tried += 1
        pr = coupang_api.best_in_band(kw, BAND_LO, BAND_HI)
        if not pr:
            skipped.append(kw)
            continue
        picks.append((item, pr))
        if pr["price"] <= CHEAP_HI:
            cheap.append({"label": item.get("name") or kw, "price": pr["price"],
                          "rocket": pr["rocket"], "url": pr["url"]})

    print(f"[pick] 후보 조회 {tried}건 · 채택 {len(picks)}건 · 가격대 밖/무결과 {len(skipped)}건")
    if skipped:
        print("       탈락: " + ", ".join(skipped[:8]))
    if len(picks) < 3:
        print(f"::error::채택이 {len(picks)}건뿐이다 — 5개 리포트로 쓰기 부족해 발행하지 않는다")
        return 3

    art = build(board, picks, cheap, days)
    os.makedirs("data", exist_ok=True)
    with open(PREVIEW, "w", encoding="utf-8") as f:
        f.write(f"<h1>{html.escape(art['title'])}</h1>" + art["html"])
    rec = {"date": dt.date.today().isoformat(), "board_updated": board.get("updated"),
           "picked": [p[0].get("name") for p in picks], "tried": tried,
           "skipped": skipped, "published": None}

    if publish:
        import publisher
        from main import load_config
        cfg = load_config()
        wp = dict(cfg.get("wordpress") or {})
        if not wp.get("enabled"):
            print("::warning::config 의 wordpress.enabled 가 False — 발행 생략(로컬 설정은 예시값이다)")
        else:
            url = publisher.publish_to_wordpress(art, wp)
            rec["published"] = url
            print(f"[wp] 발행: {url}")
    else:
        print(f"[dry] 미리보기만 저장: {PREVIEW}")

    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
