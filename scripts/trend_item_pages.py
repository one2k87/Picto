#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""유행템 개별 아이템 페이지 + 톱3 비교 글 생성기.

사용자 지시(2026-11-20):
  "유행템을 모았으면 개별 아이템 페이지도 만들고, 개별 아이템에서는
   톱3 유사제품들을 비교분석하는 글로 각각 연결할 수 있게"

구조는 세 단이다.
  주간 유행템 리포트  →  아이템 페이지(품목 1개)  →  톱3 비교 글(같은 품목 상위 3개)
각 단은 서로를 링크한다. 내부 링크가 촘촘해야 색인도 체류도 올라간다.

사진·가격·링크는 전부 쿠팡 파트너스 링크 생성 화면에서 "이미지+텍스트 → 블로그용 태그"
로 받은 값이다(채널 pickdamblog). AI 로 그린 그림은 쓰지 않는다 — 한국 생활용품은
엉뚱한 물건이 나오고 한글이 깨진다(11/20 라이브 151장 전수 확인).

가격은 사람이 화면에서 읽어 적은 값만 쓴다. 쿠팡 이용약관상 상품 페이지 자동 수집은
금지이고, 제휴링크를 열어 확인하는 것도 무효클릭이라 하지 않는다.

  python3 scripts/trend_item_pages.py               # 초안만 (data/trend_item_drafts/)
  python3 scripts/trend_item_pages.py --publish     # 워드프레스 발행
  python3 scripts/trend_item_pages.py --only 자동디스펜서
"""
import datetime as dt
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import products as products_mod          # noqa: E402

ITEMS = "data/trend_items.json"
POSTS = "data/trend_item_posts.json"
DRAFTS = "data/trend_item_drafts"
PICK = "data/weekly_trend_pick.json"

# 공정위 개정 심사지침(2024-12-01 시행): 대가성 문구는 제목 또는 **첫 부분**.
NOTICE = ("이 포스팅은 쿠팡 파트너스 활동의 일환으로, "
          "이에 따른 일정액의 수수료를 제공받습니다.")


def esc(x):
    return html.escape(str(x or ""))


def won(n):
    return f"{int(n):,}원" if n else ""


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def resolve(entry):
    """톱3 한 줄을 실제 값으로 편다. product_key 가 있으면 대장에서 끌어온다."""
    out = dict(entry)
    key = entry.get("product_key")
    if key:
        for p in products_mod.all_products():
            if p.get("key") == key:
                out.setdefault("name", p.get("banner_alt") or p.get("name"))
                for f in ("image", "price", "origin_price", "discount_rate",
                          "price_at", "banner_link", "coupang_url"):
                    if p.get(f) and not out.get(f):
                        out[f] = p[f]
                if (p.get("note") or "").startswith("🚀"):
                    out.setdefault("rocket", True)
                break
    out["link"] = out.get("banner_link") or out.get("coupang_url") or out.get("link") or ""
    return out


def card(e, slug, big=False):
    """상품 카드 — 사진(쿠팡 공식 배너) + 이름 + 가격 + 링크."""
    link = e.get("link") or ""
    if link:
        link = products_mod.with_subid(link, products_mod.safe_subid(slug))
    w, h = (170, 340) if big else (130, 260)
    img = e.get("image")
    bits = [f'<p style="margin:0 0 6px"><strong>{esc(e.get("name"))}</strong></p>']
    if e.get("price"):
        line = f'<span style="font-size:1.15em;font-weight:700">{won(e["price"])}</span>'
        if e.get("origin_price") and e.get("discount_rate"):
            line += (f' <span style="color:#888;text-decoration:line-through">'
                     f'{won(e["origin_price"])}</span>'
                     f' <span style="color:#c0392b">{int(e["discount_rate"])}%</span>')
        bits.append(f'<p style="margin:0 0 6px">{line}</p>')
    if e.get("rocket"):
        bits.append('<p style="margin:0 0 6px">🚀 로켓배송</p>')
    if e.get("why"):
        bits.append(f'<p style="margin:0 0 6px">{esc(e["why"])}</p>')
    if e.get("price_at"):
        bits.append(f'<p style="margin:0 0 6px;color:#777;font-size:.92em">'
                    f'{esc(e["price_at"])} 기준입니다. 쿠팡 가격은 수시로 바뀝니다.</p>')
    if link:
        bits.append(f'<p style="margin:0"><a href="{link}" target="_blank" '
                    f'rel="nofollow sponsored noopener">쿠팡에서 현재 가격 보기</a></p>')
    if img:
        tag = (f'<img src="{esc(img)}" alt="{esc(e.get("name"))}" width="{w}" height="{h}" '
               f'style="border:1px solid #e8e8e8;border-radius:8px;display:block">')
        if link:
            tag = (f'<a href="{link}" target="_blank" rel="nofollow sponsored noopener">'
                   f'{tag}</a>')
    else:
        tag = ('<div style="width:%dpx;height:%dpx;border:1px dashed #ccc;border-radius:8px;'
               'display:flex;align-items:center;justify-content:center;color:#999;'
               'font-size:.9em;text-align:center;padding:8px">사진 준비 중</div>' % (w, h))
    return ('<div style="display:flex;gap:18px;align-items:flex-start;margin:20px 0;'
            'flex-wrap:wrap">'
            f'{tag}<div style="flex:1;min-width:230px">{"".join(bits)}</div></div>')


def compare_table(top3):
    """가격·배송·차이를 한 표로. 칸이 밀리지 않게 열을 넷으로만 둔다."""
    rows = []
    for i, e in enumerate(top3, 1):
        price = won(e.get("price")) or "—"
        if e.get("discount_rate"):
            price += f' <span style="color:#c0392b">({int(e["discount_rate"])}%↓)</span>'
        rows.append(
            "<tr>"
            f'<td style="padding:10px;border-bottom:1px solid #eee">{i}</td>'
            f'<td style="padding:10px;border-bottom:1px solid #eee">{esc(e.get("name"))}</td>'
            f'<td style="padding:10px;border-bottom:1px solid #eee;white-space:nowrap">{price}</td>'
            f'<td style="padding:10px;border-bottom:1px solid #eee;white-space:nowrap">'
            f'{"🚀 로켓" if e.get("rocket") else "일반"}</td>'
            "</tr>")
    return ('<table style="width:100%;border-collapse:collapse;margin:18px 0">'
            '<thead><tr style="background:#fafafa">'
            '<th style="padding:10px;text-align:left;border-bottom:2px solid #ddd">#</th>'
            '<th style="padding:10px;text-align:left;border-bottom:2px solid #ddd">제품</th>'
            '<th style="padding:10px;text-align:left;border-bottom:2px solid #ddd">가격</th>'
            '<th style="padding:10px;text-align:left;border-bottom:2px solid #ddd">배송</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def pick_row(key, display):
    """이번 주 집계에서 이 품목의 실측 숫자를 찾는다(없으면 None)."""
    data = load(PICK, {})
    for r in data.get("rows") or []:
        n = re.sub(r"\s+", "", r.get("name") or "")
        if n == re.sub(r"\s+", "", key) or n == re.sub(r"\s+", "", display):
            return r
    return None


def build_item(key, it, top3, links):
    """아이템 페이지 — 이게 뭔지, 왜 뜨는지, 어느 제품인지, 그리고 비교 글로."""
    display = it.get("display") or key
    slug = f"trend-{it.get('slug') or products_mod.safe_subid(key)}"
    today = dt.date.today()
    head = top3[0] if top3 else {}
    h = [f"<p>{NOTICE}</p>"]

    # 결론을 먼저 — 글을 끝까지 읽지 않는 사람이 훨씬 많다.
    lead = []
    if head.get("price"):
        lead.append(f"{display}은(는) 지금 {won(head['price'])}선에서 삽니다.")
    if head.get("rocket"):
        lead.append("로켓배송이라 주문하면 대체로 다음 날 받습니다.")
    if it.get("what"):
        lead.append(it["what"])
    if lead:
        h.append('<p style="padding:14px 16px;background:#f7f9fb;border-left:4px solid #3b82f6;'
                 'border-radius:4px">' + " ".join(esc(x) for x in lead) + "</p>")

    pr = pick_row(key, display)
    h.append(f"<h2>{esc(display)}, 왜 지금 보이나</h2>")
    why = []
    if pr:
        if pr.get("videos") and pr.get("channels"):
            why.append(f"최근 집계에서 영상 {pr['videos']}개, 채널 {pr['channels']}곳에서 다뤘습니다.")
        if pr.get("views"):
            why.append(f"그 영상들의 조회수를 합치면 {int(pr['views']):,}회입니다.")
        rise = pr.get("rise")
        if isinstance(rise, (int, float)):
            if rise >= 1.05:
                why.append(f"네이버 쇼핑 검색 지수는 직전 한 달 대비 {rise:.2f}배로 올라와 있습니다.")
            elif rise <= 0.95:
                why.append(f"다만 검색 지수는 직전 한 달 대비 {rise:.2f}배로 오히려 식고 있습니다. "
                           f"영상은 늘었는데 찾는 사람은 줄었다는 뜻입니다.")
            else:
                why.append(f"네이버 쇼핑 검색 지수는 직전 한 달과 비슷한 {rise:.2f}배입니다.")
    if it.get("why_extra"):
        why.append(it["why_extra"])
    if not why:
        why.append("이번 주 집계에서 영상 수와 채널 수가 하한을 넘어 목록에 들어온 품목입니다.")
    h.append("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in why) + "</ul>")
    h.append('<p>느낌으로 고른 목록이 아닙니다. 유튜브에 올라온 영상 수·채널 수를 세고 '
             '네이버에서 실제로 검색이 늘고 있는지를 겹쳐서 봅니다. '
             '<strong>검색이 식고 있으면 그 사실도 그대로 적습니다.</strong></p>')

    if it.get("detail"):
        h.append(f"<h2>어떤 물건인가</h2>")
        for para in it["detail"]:
            h.append(f"<p>{esc(para)}</p>")

    if head:
        h.append(f"<h2>지금 고른다면 이 제품</h2>")
        h.append(card(head, slug, big=True))

    # 톱3 비교 글로 — 사용자가 요구한 연결 지점이다.
    cmp_slug = f"{slug}-top3"
    cmp_url = links.get(cmp_slug)
    if len(top3) >= 2:
        h.append("<h2>비슷한 제품 셋을 나란히 놓으면</h2>")
        h.append(compare_table(top3))
        if cmp_url:
            h.append(f'<p><a href="{esc(cmp_url)}">'
                     f'{esc(display)} 톱3 비교 — 가격·배송·차이를 하나씩 뜯어봤습니다</a></p>')
        else:
            h.append(f'<p>셋의 차이를 하나씩 뜯어본 글을 따로 올립니다.</p>')

    weekly = links.get("weekly")
    if weekly:
        h.append(f'<p><a href="{esc(weekly)}">이번 주 유행템 5가지 전체 보기</a></p>')
    h.append('<h2>가격에 대해</h2>'
             '<p>가격은 글에 적힌 날짜에 쿠팡 화면에서 직접 읽은 값입니다. '
             '쿠팡 가격은 하루에도 바뀌므로, 사기 전에는 링크를 눌러 현재 가격을 확인하세요.</p>')
    return {
        "title": f"{display}, 지금 얼마에 살 수 있나 (가격·배송 정리)",
        "slug": slug,
        "html": "".join(h),
        "meta": f"{display}의 현재 가격과 배송, 그리고 비슷한 제품과의 차이를 "
                f"실제 화면에서 읽은 값으로 정리했습니다.",
        "seo_title": f"{display} 가격·배송 정리 — {today.month}/{today.day} 기준",
        "focus_keyword": it.get("keyword") or display,
        "category": "트렌드", "wp_category": "트렌드", "wp_category_slug": "trend",
    }


def build_compare(key, it, top3, links):
    """톱3 비교 글 — 셋을 같은 잣대로."""
    display = it.get("display") or key
    base = f"trend-{it.get('slug') or products_mod.safe_subid(key)}"
    slug = f"{base}-top3"
    today = dt.date.today()
    h = [f"<p>{NOTICE}</p>"]
    h.append('<p style="padding:14px 16px;background:#f7f9fb;border-left:4px solid #3b82f6;'
             f'border-radius:4px">{esc(display)}로 많이 팔리는 세 가지를 '
             f'가격·배송·쓰임으로 갈라 놓았습니다. 아래 표만 봐도 고를 수 있습니다.</p>')
    h.append("<h2>한눈에</h2>")
    h.append(compare_table(top3))
    # 가격이 실제로 얼마나 움직이는지 숫자로 보여 주면 "구매 전 확인" 이 공허한 말이 아니게 된다.
    if it.get("why_extra"):
        h.append(f'<p style="padding:12px 14px;background:#fff8f0;border-left:4px solid #e8a33d;'
                 f'border-radius:4px">{esc(it["why_extra"])}</p>')

    h.append("<h2>하나씩</h2>")
    for i, e in enumerate(top3, 1):
        h.append(f"<h3>{i}. {esc(e.get('name'))}</h3>")
        h.append(card(e, slug))
        if e.get("detail"):
            h.append(f"<p>{esc(e['detail'])}</p>")

    if it.get("verdict"):
        h.append("<h2>그래서 어느 쪽인가</h2>")
        for para in it["verdict"]:
            h.append(f"<p>{esc(para)}</p>")
    else:
        # 근거 없는 추천을 지어내지 않는다. 표에서 읽히는 사실만 쓴다.
        cheap = min((e for e in top3 if e.get("price")), key=lambda e: e["price"], default=None)
        rocket = next((e for e in top3 if e.get("rocket")), None)
        lines = []
        if cheap:
            lines.append(f"가장 싼 것은 {cheap['name']}로 {won(cheap['price'])}입니다.")
        if rocket:
            lines.append(f"빨리 받고 싶으면 로켓배송인 {rocket['name']}입니다.")
        if lines:
            h.append("<h2>그래서 어느 쪽인가</h2>")
            h.append("<p>" + " ".join(esc(x) for x in lines) +
                     " 나머지는 쓰임이 갈리는 부분이라, 위 표에서 본인 조건에 맞는 쪽을 고르면 됩니다.</p>")

    back = links.get(base)
    if back:
        h.append(f'<p><a href="{esc(back)}">{esc(display)}가 어떤 물건이고 왜 뜨는지 보기</a></p>')
    weekly = links.get("weekly")
    if weekly:
        h.append(f'<p><a href="{esc(weekly)}">이번 주 유행템 5가지 전체 보기</a></p>')
    h.append('<p style="color:#777;font-size:.93em">가격은 글에 적힌 날짜에 쿠팡 화면에서 '
             '직접 읽은 값입니다. 사기 전에 링크를 눌러 현재 가격을 확인하세요.</p>')
    return {
        "title": f"{display} 톱3 비교 — 가격·배송·차이점",
        "slug": slug,
        "html": "".join(h),
        "meta": f"{display} 상위 세 제품을 가격·배송·쓰임으로 갈라 비교했습니다. "
                f"가격은 실제 화면에서 읽은 값입니다.",
        "seo_title": f"{display} 톱3 비교 ({today.month}/{today.day} 가격)",
        "focus_keyword": f"{display} 비교",
        "category": "트렌드", "wp_category": "트렌드", "wp_category_slug": "trend",
    }


def load_config():
    for p in ("config.json", "config.example.json"):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


def main():
    publish = "--publish" in sys.argv
    # 2026-11-22 사용자 선택("나눠서 발행"): 하루에 8편을 쏟으면 신규 도메인에서
    # 색인에 불리하다. 비교 글을 먼저 올리고 아이템 페이지는 다음 차례에 올린다.
    compare_only = "--compare-only" in sys.argv
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1]

    items = load(ITEMS, {})
    if not items:
        print(f"::error::{ITEMS} 이 없다 — 어떤 품목을 쓸지 추측하지 않는다")
        return 1
    posts = load(POSTS, {})
    links = {k: v.get("url") for k, v in posts.items() if isinstance(v, dict) and v.get("url")}

    os.makedirs(DRAFTS, exist_ok=True)
    # 비교 글을 먼저 만들고 먼저 발행한다. 아이템 페이지가 비교 글 주소를 받아
    # "톱3 비교 보기" 링크를 달아야 하는데, 순서를 바꾸면 첫 발행에서 링크가 빈다.
    picked = []
    for key, it in items.items():
        if only and key != only:
            continue
        top3 = [resolve(e) for e in (it.get("top3") or [])]
        top3 = [e for e in top3 if e.get("name")]
        if not top3:
            print(f"  · {key}: top3 가 비어 있다 — 건너뜀")
            continue
        no_img = [e["name"] for e in top3 if not e.get("image")]
        if no_img:
            print(f"  · {key}: 사진 없는 제품 {len(no_img)}개 — {no_img[0][:30]}…")
        picked.append((key, it, top3))

    arts = []
    for key, it, top3 in picked:
        if len(top3) >= 2:
            arts.append(build_compare(key, it, top3, links))
    if not compare_only:
        for key, it, top3 in picked:
            arts.append(build_item(key, it, top3, links))

    if not arts:
        print("::warning::만들 글이 없다")
        return 0

    for a in arts:
        p = os.path.join(DRAFTS, a["slug"] + ".html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"<h1>{esc(a['title'])}</h1>" + a["html"])
        print(f"  초안 {p}")

    if not publish:
        print(f"\n초안 {len(arts)}편. 발행하려면 --publish 를 붙인다.")
        return 0

    import publisher
    cfg = load_config()
    wp = dict(cfg.get("wordpress") or {})
    if not wp.get("enabled"):
        print("::warning::wordpress.enabled 가 False — 발행 생략")
        return 0
    import requests as _rq

    def find_posted(slug):
        """이미 올라간 글이면 (id, link). 중복 발행을 막고 기록만 채운다."""
        try:
            base = wp["site_url"].rstrip("/")
            # status 를 붙이면 안 된다. publish 외의 상태는 인증이 필요해
            # 인증 없는 조회가 통째로 400 으로 떨어지고, 그러면 '없음'으로 읽혀
            # 같은 글을 또 올린다(11/22 에 이것으로 5편이 두 벌 올라갔다).
            r = _rq.get(f"{base}/wp-json/wp/v2/posts",
                        params={"slug": slug, "_fields": "id,link"}, timeout=30)
            if r.status_code != 200:
                print(f"::warning::{slug} 중복 확인 실패 {r.status_code} — 발행을 건너뛴다")
                return -1, None          # 확인 못 하면 올리지 않는다(중복이 더 나쁘다)
            j = r.json()
            if isinstance(j, list) and j:
                return j[0].get("id"), j[0].get("link")
        except Exception:
            pass
        return None, None

    done_cmp = False
    for a in arts:
        # 비교 글을 다 올린 다음, 그 주소를 들고 아이템 페이지를 다시 짓는다.
        if not a["slug"].endswith("-top3") and not done_cmp:
            done_cmp = True
            links.update({k: v.get("url") for k, v in posts.items()
                          if isinstance(v, dict) and v.get("url")})
            rebuilt = {}
            for key, it, top3 in picked:
                r = build_item(key, it, top3, links)
                rebuilt[r["slug"]] = r
            for i, x in enumerate(arts):
                if x["slug"] in rebuilt:
                    arts[i] = rebuilt[x["slug"]]
            a = arts[arts.index(next(x for x in arts if x["slug"] == a["slug"]))]
        pid, url = find_posted(a["slug"])
        if pid == -1:
            continue                      # 확인 실패 — 이번 실행에서는 건드리지 않는다
        if url:
            # 같은 슬러그가 이미 라이브에 있다. 다시 올리면 같은 글이 두 편이 된다.
            print(f"[wp] {a['slug']} — 이미 있음 #{pid}, 발행 건너뛰고 기록만 채운다")
        else:
            res = publisher.publish_to_wordpress(a, wp)
            # publish_to_wordpress 는 **URL 문자열**을 돌려준다(dict 아님).
            # 11/22 에 dict 로 받으려다 기록이 비었고, 그래서 대표 이미지가 안 붙었다.
            url = res if isinstance(res, str) else ((res or {}).get("link")
                                                    if isinstance(res, dict) else None)
            print(f"[wp] {a['slug']} → {url}")
            if url:
                pid, _ = find_posted(a["slug"])
        if url:
            posts[a["slug"]] = {"url": url, "id": pid,
                                "at": dt.date.today().isoformat(), "title": a["title"]}
    save(POSTS, posts)
    print(f"[기록] {POSTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
