#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""글이 잡고 있는 키워드의 실제 검색량을 재고, 서치콘솔 성과와 맞춰 본다.

왜 만들었나(2026-11-23 실측):
  노출이 잡힌 글 25편 중 20편이 이미 1페이지(10위 이내)인데 노출이 없다.
  2.0위에 월 1회, 3.8위에 월 6회. 순위 문제가 아니라 **그 말을 찾는 사람이 없는** 것이다.
  반대로 「창문 단열 뽁뽁이」(월 450회)는 4.6위에서 월 96회 노출이 나온다.
  원인은 config 의 traffic_ratio=15 — 85%를 저경쟁으로 골랐고, 저경쟁은 곧 저검색량이었다.

이 도구는 글마다 (검색량 × 순위)를 한 표에 놓아 다음 네 묶음으로 가른다.
  A 지킨다      검색량 있고 1페이지        → 건드리지 않는다
  B **밀어준다** 검색량 있는데 11위 밖      → 노출이 가장 크게 뛰는 자리
  C 빈 키워드   1페이지인데 검색량 없음     → 같은 종류를 더 쓰지 않는다
  D 확인 필요   노출 0                     → 색인 문제인지 검색량 0인지 가른다

  python3 scripts/keyword_volume_audit.py
"""
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import metrics                     # noqa: E402

OUT = "data/keyword_volume_audit.md"
OUT_JSON = "dashboard/data/keyword_volume_audit.json"
SITE = "https://pickdam.com"


def norm(k):
    return (k or "").replace(" ", "").upper()


def load_cfg():
    for p in ("config.json", "config.example.json"):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


def wp_posts():
    out = []
    for page in (1, 2, 3):
        try:
            u = (f"{SITE}/wp-json/wp/v2/posts?per_page=50&page={page}"
                 "&_fields=id,title,link,slug,date")
            with urllib.request.urlopen(u, timeout=40) as r:
                b = json.loads(r.read().decode("utf-8"))
            if not b:
                break
            out += b
        except Exception:
            break
    return out


def keywords_from_repo():
    """일별 생성 기록에 그 글을 쓸 때 쓴 keyword 가 남아 있다. 슬러그로 맞춘다."""
    import glob
    kw = {}
    for f in sorted(glob.glob("dashboard/data/2026-*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for a in (d.get("articles") or []):
            s = (a.get("slug") or "").strip("/")
            k = (a.get("keyword") or "").strip()
            if s and k:
                kw[s] = k
    return kw


def strip_tags(h):
    return re.sub(r"<[^>]+>", "", h or "").strip()


def core_terms(text):
    """제목에서 검색어가 될 만한 앞 3어절을 뽑는다. 긴 제목은 그대로 재면 0 이 나온다."""
    t = re.split(r"[,·|:(\[]", text)[0]
    w = [x for x in t.split() if len(x) > 1][:3]
    return " ".join(w)


def main():
    cfg = load_cfg()
    ncfg = ((cfg.get("metrics") or {}).get("naver") or {})
    if not (ncfg.get("api_key") and ncfg.get("secret_key") and ncfg.get("customer_id")):
        print("::error::네이버 검색광고 키가 없다 — 워크플로에서 돌려야 한다")
        return 1

    posts = wp_posts()
    if not posts:
        print("::error::글을 못 읽었다")
        return 1
    repo_kw = keywords_from_repo()

    # 서치콘솔 성과
    perf = {}
    try:
        sc = json.load(open("dashboard/data/insights.json", encoding="utf-8"))["search_console"]
        for p in (sc.get("pages") or []):
            perf[p["page"].rstrip("/")] = p
    except Exception:
        print("::warning::insights.json 을 못 읽었다 — 순위 없이 검색량만 잰다")

    rows = []
    for p in posts:
        title = strip_tags((p.get("title") or {}).get("rendered", ""))
        slug = (p.get("slug") or "")
        kw = repo_kw.get(slug) or title
        rows.append({"id": p["id"], "slug": slug, "title": title,
                     "keyword": core_terms(kw), "raw_keyword": kw,
                     "link": p.get("link", "").rstrip("/")})

    # 5개씩 묶어 조회
    vol = {}
    for i in range(0, len(rows), 5):
        chunk = [r["keyword"] for r in rows[i:i + 5] if r["keyword"]]
        if not chunk:
            continue
        try:
            got = metrics.naver_volumes(chunk, ncfg)
            vol.update(got or {})
        except Exception as e:
            print(f"::warning::검색량 조회 실패({i}): {str(e)[:70]}")
        time.sleep(0.4)          # 분당 한도 보호
    print(f"[조회] 글 {len(rows)}편 · 검색량 응답 {len(vol)}건")

    for r in rows:
        v = vol.get(norm(r["keyword"]))
        r["volume"] = (v or {}).get("volume")
        pf = perf.get(r["link"])
        r["impr"] = (pf or {}).get("impressions", 0)
        r["clicks"] = (pf or {}).get("clicks", 0)
        r["pos"] = (pf or {}).get("position")

    def bucket(r):
        v, pos, im = r.get("volume"), r.get("pos"), r.get("impr", 0)
        if im == 0:
            return "D 확인 필요(노출 0)"
        if v is None:
            return "D 확인 필요(검색량 미측정)"
        if v >= 300 and pos and pos > 10:
            return "B 밀어준다"
        if v >= 300:
            return "A 지킨다"
        return "C 빈 키워드"

    for r in rows:
        r["bucket"] = bucket(r)

    order = {"B 밀어준다": 0, "A 지킨다": 1, "C 빈 키워드": 2}
    rows.sort(key=lambda r: (order.get(r["bucket"], 3), -(r.get("impr") or 0)))

    lines = ["# 글별 키워드 검색량 × 순위 — " + time.strftime("%Y-%m-%d"), "",
             "검색량은 네이버 검색광고 월간치, 순위·노출은 서치콘솔 28일치입니다.", ""]
    for b in ("B 밀어준다", "A 지킨다", "C 빈 키워드", "D 확인 필요(노출 0)",
              "D 확인 필요(검색량 미측정)"):
        sel = [r for r in rows if r["bucket"] == b]
        if not sel:
            continue
        lines += [f"## {b} — {len(sel)}편", "",
                  "| 글 | 키워드 | 월 검색량 | 노출 | 순위 |",
                  "|---|---|---:|---:|---:|"]
        for r in sel[:30]:
            v = f"{r['volume']:,}" if r.get("volume") is not None else "—"
            ps = f"{r['pos']:.1f}" if r.get("pos") else "—"
            lines.append(f"| #{r['id']} {r['title'][:28]} | {r['keyword'][:20]} | "
                         f"{v} | {r.get('impr', 0)} | {ps} |")
        lines.append("")
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.makedirs("dashboard/data", exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows},
                  f, ensure_ascii=False, indent=1)

    from collections import Counter
    c = Counter(r["bucket"] for r in rows)
    print("\n".join(f"  {k}: {v}편" for k, v in sorted(c.items())))
    got = [r for r in rows if r.get("volume") is not None]
    if got:
        import statistics as st
        vals = [r["volume"] for r in got]
        print(f"\n측정 {len(got)}편 · 중앙값 {st.median(vals):,.0f} · "
              f"300 미만 {sum(1 for v in vals if v < 300)}편")
    print(f"\n표: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
