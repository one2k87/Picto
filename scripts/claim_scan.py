# -*- coding: utf-8 -*-
"""발행 글 주장 검사 (2026-11-26 신설) — 읽기 전용. 아무것도 고치지 않는다.

왜 만들었나
  11/24 #951 에서 「총비용 약 15만~30만 원 차이」 같은 근거 없는 수치가 검수를 통과해 발행된 것을 뒤늦게 찾았다.
  famto 11/24 지시: 키토가 정한 세 가지 금지 — ①지어낸 출처 ②겪지 않은 체험 표현 ③근거 없는 금액 — 을
  최근 30일 발행 글에 한 번 적용해 걸린 편수를 센다(고치는 것은 사용자 확인 뒤).

무엇을 세나 (문단 단위. 상품 카드·고지문·그림 설명은 뺀다)
  ① 출처   「~에 따르면·조사 결과·통계·전문가들은·공식 기준」처럼 출처를 내세우는데 그 문단에 링크가 없다
  ② 체험   「직접 써보니·제가·내돈내산·솔직 후기」 같은 1인칭 경험 표현
  ③ 금액   금액·비율 범위(「10만~15만 원」「월 1만 5천 원에서 3만 원」)나 「최소·최대·평균 N만 원」을 단정하는데 그 문단에 링크가 없다
  + 제목에 금액이 박혀 있으면 따로 센다(가장 눈에 띄는 자리라서)

낱말 검사라 놓치는 것도, 잘못 잡는 것도 있다. 결과는 「사람이 읽어 볼 글의 목록」이지 판정이 아니다.

환경변수: SITE_DOMAIN(기본 pickdam.com) · SCAN_DAYS(기본 30)
출력: dashboard/data/claim_scan.json · data/claim_scan.md
"""
import datetime as dt
import html
import json
import os
import re
import sys

import requests

DOMAIN = (os.getenv("SITE_DOMAIN") or "pickdam.com").strip()
DAYS = int(os.getenv("SCAN_DAYS") or 30)
OUT_JSON = os.path.join("dashboard", "data", "claim_scan.json")
OUT_MD = os.path.join("data", "claim_scan.md")

NUM = r"\d[\d,.]*\s*(?:천|만|억)?(?:\s*\d*\s*천)?"
MONEY_RANGE = re.compile(rf"{NUM}\s*(?:원|%)?\s*(?:~|∼|에서|부터|내지)\s*(?:최대\s*)?{NUM}\s*(?:원|%)")
MONEY_BOUND = re.compile(rf"(?:최소|최대|평균|약|대략|통상|보통)\s*{NUM}\s*(?:원|%)|{NUM}\s*원\s*(?:이상|이하|안팎|내외|대|수준|가량|정도)")
SOURCE = re.compile(r"에 따르면|조사 ?결과|통계(?:에|상|로)|연구 ?결과|전문가(?:들은|에 따르면|들이)|공식 기준|공식 자료|공식 발표|보고서에|발표(?:한|된) 자료")
EXPERIENCE = re.compile(r"직접 (?:써|사용해|구매해|설치해|해) ?(?:보니|봤|본 결과)|써 ?보니|사용해 ?보니|(?:^|[\s,(])(?:제가|저는|저희 집|저희는) |내돈내산|솔직 ?후기|한 달 ?(?:써|사용)|실사용 후기|체험해")
TITLE_MONEY = re.compile(rf"{NUM}\s*원")
SKIP = re.compile(r"쿠팡 파트너스|수수료를 제공받|기준 가격입니다|가격·재고는|생성형 AI|기준으로 내용을 확인|참고용 글|정보 제공을 목적")


def paragraphs(content):
    """본문을 문단(텍스트, 링크 유무)으로 쪼갠다. 상품 카드·그림·표·스크립트는 뺀다."""
    t = re.sub(r"<(script|style|figure|table)[\s\S]*?</\1>", " ", content)
    t = re.sub(r'<div[^>]*display:flex[\s\S]*?</div>\s*</div>', " ", t)      # 상품 카드
    out = []
    for m in re.finditer(r"<(p|li)\b[^>]*>([\s\S]*?)</\1>", t):
        raw = m.group(2)
        txt = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if len(txt) < 12 or SKIP.search(txt):
            continue
        linked = bool(re.search(r'<a\s[^>]*href="https?://(?!(?:www\.)?%s|link\.coupang)' % re.escape(DOMAIN), raw))
        out.append((txt, linked))
    return out


def scan(post):
    title = html.unescape((post.get("title") or {}).get("rendered") or "")
    hits = {"source": [], "experience": [], "money": []}
    for txt, linked in paragraphs((post.get("content") or {}).get("rendered") or ""):
        for sent in re.split(r"(?<=[.?!])\s+", txt):
            if EXPERIENCE.search(sent):
                hits["experience"].append(sent[:90])
            if linked:
                continue
            if SOURCE.search(sent):
                hits["source"].append(sent[:90])
            if MONEY_RANGE.search(sent) or MONEY_BOUND.search(sent):
                hits["money"].append(sent[:90])
    return {"id": post["id"], "date": (post.get("date") or "")[:10], "title": title, "link": post.get("link"),
            "title_money": bool(TITLE_MONEY.search(title)),
            "n": {k: len(v) for k, v in hits.items()}, "ex": {k: v[:2] for k, v in hits.items()}}


def main():
    since = (dt.datetime.now() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00")
    posts, page = [], 1
    while True:
        r = requests.get(f"https://{DOMAIN}/wp-json/wp/v2/posts", timeout=60,
                         params={"per_page": 50, "page": page, "after": since, "_fields": "id,date,title,link,content"})
        if r.status_code != 200:
            break
        j = r.json()
        posts += j
        if len(j) < 50:
            break
        page += 1
    if not posts:
        print("::warning::검사할 글을 받지 못했습니다.")
        return 0
    rows = sorted((scan(p) for p in posts), key=lambda x: x["date"], reverse=True)
    tot = {"posts": len(rows),
           "source": sum(1 for r in rows if r["n"]["source"]),
           "experience": sum(1 for r in rows if r["n"]["experience"]),
           "money": sum(1 for r in rows if r["n"]["money"]),
           "title_money": sum(1 for r in rows if r["title_money"]),
           "clean": sum(1 for r in rows if not any(r["n"].values()) and not r["title_money"])}
    out = {"at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "site": DOMAIN, "days": DAYS, "total": tot, "rows": rows}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = [f"# 발행 글 주장 검사 — {out['at']}", "",
         f"`{DOMAIN}` 최근 {DAYS}일 발행 {tot['posts']}편 · 낱말 검사(사람이 읽어 볼 목록이지 판정이 아니다)", "",
         f"- 출처를 내세우는데 링크 없음: **{tot['source']}편**",
         f"- 1인칭 체험 표현: **{tot['experience']}편**",
         f"- 근거 링크 없는 금액·비율: **{tot['money']}편**",
         f"- 제목에 금액: **{tot['title_money']}편**",
         f"- 하나도 안 걸림: {tot['clean']}편", "",
         "| 글 | 날짜 | 출처 | 체험 | 금액 | 제목 금액 | 제목 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| #{r['id']} | {r['date'][5:]} | {r['n']['source']} | {r['n']['experience']} | {r['n']['money']} | "
                 f"{'●' if r['title_money'] else ''} | [{r['title'][:34]}]({r['link']}) |")
    L += ["", "## 걸린 문장 예(글마다 종류별 2개까지)", ""]
    for r in rows:
        ex = [(k, s) for k in ("source", "experience", "money") for s in r["ex"][k]]
        if ex:
            L.append(f"**#{r['id']}** {r['title'][:40]}")
            L += [f"- ({ {'source': '출처', 'experience': '체험', 'money': '금액'}[k] }) {s}" for k, s in ex]
            L.append("")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(json.dumps(tot, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
