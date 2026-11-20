# -*- coding: utf-8 -*-
"""원잇 비교표 → 픽담 비교 글 초안 (2026-11-20 신설, 로드맵 v3).

흐름(요일제):
  원잇이 _private_batch/wantit_share/epNN_*.md 에 비교표를 올린다
  → (수요일 밤) 이 스크립트가 초안 HTML + 「확인할 상품 주소 목록」을 만든다
  → (목요일 점심) 사용자가 그 목록을 열어 가격을 확인해 준다
  → 가격을 채우고 파트너스 링크를 당일 생성(채널 pickdamblog)해 발행한다

왜 가격을 비워 두나: 쿠팡 페이지를 자동으로 긁는 것은 이용약관 위반이다(로봇·스크레이퍼 금지).
사람이 본 값만 글에 들어간다. 그래서 초안은 가격 자리를 비우고 확인 목록을 따로 낸다.

사용: python3 scripts/build_compare_draft.py [비교표.md ...]
      (인자가 없으면 _private_batch/wantit_share/ 의 .md 를 전부)
출력: data/compare_drafts/<이름>.html · data/compare_drafts/<이름>_확인목록.md
"""
import datetime as dt
import glob
import html as html_mod
import os
import re
import sys

CANDS = ["~/Desktop/SolvUp_Workspace/_private_batch/wantit_share",
         "~/mnt/SolvUp_Workspace/_private_batch/wantit_share",
         "../_private_batch/wantit_share"]
SHARE = next((os.path.expanduser(p) for p in CANDS if os.path.isdir(os.path.expanduser(p))),
             os.path.expanduser(CANDS[0]))
OUT = os.path.join("data", "compare_drafts")
NOTICE = ('<p class="coupang-notice" style="font-size:12px;color:#98a2b3;margin:10px 0 4px;'
          'padding:8px 12px;background:#fafbfc;border-left:3px solid #ff5a5f">'
          '이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>')


def _josa(word, with_batchim, without):
    """받침에 맞는 조사를 고른다 — '3종는' 같은 말이 나오지 않게."""
    ch = (word or "").strip()[-1:]
    if not ch:
        return without
    if "가" <= ch <= "힣":
        return with_batchim if (ord(ch) - 0xAC00) % 28 else without
    if ch.isdigit():                       # 숫자는 읽는 소리로
        return with_batchim if ch in "0136780" else without
    return without


def parse(md):
    title = (re.search(r"^#\s*(.+)$", md, re.M) or [None, ""])[1].strip()
    rows, headers = [], []
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue
        if not headers:
            headers = cells
        else:
            rows.append(cells)
    items = []
    for r in rows:
        m = re.match(r"\[(.+?)\]\((https?://[^)]+)\)", r[0])
        items.append({"name": m.group(1) if m else r[0],
                      "url": m.group(2) if m else "", "cells": r})
    note = (re.search(r"\*\*핵심 차이 한 줄\*\*:\s*(.+)$", md, re.M) or [None, ""])[1].strip()
    asof = (re.search(r"가격 확인:\s*([0-9\-]+[^·\n]*)", md) or [None, ""])[1].strip()
    return title, headers, items, note, asof


def table_html(headers, items):
    th = "".join(f"<th style='text-align:left;padding:8px;border-bottom:2px solid #e5e7eb'>"
                 f"{html_mod.escape(h)}</th>" for h in headers)
    trs = ""
    for it in items:
        tds = ""
        for k, c in enumerate(it["cells"]):
            v = it["name"] if k == 0 else c
            if k == 1:
                v = "{{가격%d}}" % (items.index(it) + 1)
            tds += (f"<td style='padding:8px;border-bottom:1px solid #eef0f3'>"
                    f"{html_mod.escape(v)}</td>")
        trs += f"<tr>{tds}</tr>"
    return (f"<table style='border-collapse:collapse;width:100%;margin:16px 0'>"
            f"<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>")


def build(path):
    md = open(path, encoding="utf-8").read()
    title, headers, items, note, asof = parse(md)
    if not items:
        return None
    topic = re.sub(r"^원잇\s*\d*호\s*비교표\s*[—-]\s*", "", title)
    topic = re.sub(r"\s*\(공유용.*$", "", topic).strip()
    today = dt.date.today()

    lead = ('<p class="lead-answer" style="font-size:16px;line-height:1.75;padding:12px 14px;'
            'border-left:3px solid #7c5cff;background:#f6f4ff;margin:0 0 16px">'
            f"<strong>{html_mod.escape(topic)}{_josa(topic, '은', '는')} 가격과 "
            "「필수 표기 정보」에 뭐가 적혀 있느냐로 갈립니다.</strong> "
            + html_mod.escape(note) + "</p>")

    how = ("<h2>이 표를 만든 방법</h2><ul>"
           "<li>스펙은 쿠팡 상품페이지의 「필수 표기 정보」에 적힌 것만 옮겼습니다. "
           "「표기 없음」은 그 칸에 적혀 있지 않다는 뜻이지, 그 기능이 없다는 뜻이 아닙니다.</li>"
           f"<li>가격은 {html_mod.escape(asof)} 기준이며 쿠폰·회원 할인에 따라 수시로 바뀝니다. "
           "구매 전 상세페이지에서 꼭 다시 보세요.</li>"
           "<li>써 보고 쓴 글이 아니라, 공개된 표기만 나란히 놓고 비교한 글입니다.</li></ul>")

    picks = "".join(
        f"<h3>{html_mod.escape(it['name'])}</h3><p>{html_mod.escape(it['cells'][-1])}</p>"
        for it in items)

    links = "".join(
        '<div style="margin:6px 0"><a href="{{링크%d}}" '
        'target="_blank" rel="nofollow sponsored noopener">%s 쿠팡에서 보기</a></div>'
        % (k, html_mod.escape(it["name"])) for k, it in enumerate(items, 1))
    cards = (NOTICE + '<div class="pick-product" style="margin:22px 0;padding:14px 16px;'
             'border:1px solid #e5e7eb;border-radius:12px;background:#fafbfc">'
             '<div style="font-size:12px;color:#98a2b3;margin-bottom:10px">이 글에서 비교한 제품</div>'
             + links
             + '<div style="font-size:12px;color:#98a2b3;margin-top:10px">'
               '가격·재고는 수시로 바뀌므로 구매 전 상세페이지에서 확인하세요.</div></div>')

    body = (lead
            + f"<h2>{html_mod.escape(topic)} 한눈에 비교</h2>" + table_html(headers, items)
            + "<h2>어떤 걸 고르면 되나</h2>" + picks
            + cards + how)

    os.makedirs(OUT, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    hp = os.path.join(OUT, base + ".html")
    open(hp, "w", encoding="utf-8").write(body)

    lines = [f"# {topic} — 가격 확인 목록 ({today})", "",
             "아래 주소를 열어 **지금 보이는 판매가**를 적어 주세요(쿠폰·와우 할인 반영된 값).", ""]
    for it in items:
        lines += [f"- [ ] **{it['name']}**", f"      {it['url']}",
                  "      가격: ______________ 원", ""]
    lines += ["확인이 끝나면 픽토 채팅에 그대로 붙여넣어 주세요.",
              "가격을 채우고 파트너스 링크를 당일 생성(채널 pickdamblog)해 발행합니다."]
    cp = os.path.join(OUT, base + "_확인목록.md")
    open(cp, "w", encoding="utf-8").write("\n".join(lines))

    meta = {"title": f"{topic} 비교 — 가격·표기 기준으로 고르면 이렇게 갈립니다",
            "slug": f"compare-{base.split('_')[0]}-{today:%Y%m%d}",
            "meta": f"{topic}{_josa(topic, '을', '를')} 가격과 쿠팡 「필수 표기 정보」 기준으로 나란히 비교했습니다. "
                    "표기 없음은 기능이 없다는 뜻이 아닙니다.",
            "category": "비교", "wp_category": "비교",
            "placeholders": [f"{{{{가격{k}}}}}" for k in range(1, len(items) + 1)]
                            + [f"{{{{링크{k}}}}}" for k in range(1, len(items) + 1)],
            "products": [{"n": k, "name": it["name"], "url": it["url"]}
                         for k, it in enumerate(items, 1)]}
    mp = os.path.join(OUT, base + "_meta.json")
    import json as _json
    open(mp, "w", encoding="utf-8").write(_json.dumps(meta, ensure_ascii=False, indent=1))
    return topic, len(items), hp, cp


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = args or sorted(glob.glob(os.path.join(SHARE, "*.md")))
    if not files:
        print(f"::warning::비교표가 없습니다 — {SHARE}")
        return 0
    n = 0
    for p in files:
        r = build(p)
        if not r:
            print(f"  건너뜀(표를 못 읽음): {os.path.basename(p)}")
            continue
        topic, cnt, hp, cp = r
        print(f"✅ {topic} — 상품 {cnt}개\n   초안   {hp}\n   확인표 {cp}")
        n += 1
    print(f"\n초안 {n}편")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
