# -*- coding: utf-8 -*-
"""형제 사이트(원더랜드) 제목 목록 갱신 — 사이트 간 주제 중복 방지 (2026-09-07 신설).

왜 필요한가:
  픽담과 원더랜드는 같은 파이프라인·같은 LLM을 쓰고 니치가 일부 겹친다(픽담 '생활·주방'
  vs 원더랜드 '셀프 인테리어'). 실제로 2026-09-01 두 사이트가 **똑같은 제목**을
  생성했다(둘 다 품질 게이트에 걸려 폐기됐을 뿐, 발행됐다면 중복 콘텐츠가 됐다).

왜 history.json에 넣지 않는가:
  history.json은 내부링크 풀로도 쓰인다. 거기에 남의 사이트 글을 넣으면 픽담 글이
  원더랜드로 링크를 걸게 된다(2026-09-07에 실제로 그랬고, 그래서 걷어냈다).
  이 파일은 **중복 회피 전용**이며 링크 후보로는 절대 쓰이지 않는다.

왜 스크립토 저장소를 읽지 않는가:
  공유_경계 원칙 — 앱은 서로의 저장소에 의존하지 않는다. 공개 웹(WP REST)에서 읽는다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

# 워크플로의 '결과 커밋' 단계가 dashboard/data/*.json만 add하므로 여기에 둔다
# (여기 있어야 실행 간에 축적이 유지되고 앱도 읽을 수 있다)
OUT = "dashboard/data/sibling_titles.json"
CONF = "data/sibling_sites.json"


def strip_tags(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()


def fetch(site):
    """공개 WP REST로 제목만 가져온다(인증 불필요). 실패해도 파이프라인은 계속된다."""
    base = site.rstrip("/")
    out, page = [], 1
    while page <= 6:                       # 최대 300편이면 중복 회피에 충분
        try:
            r = requests.get(f"{base}/wp-json/wp/v2/posts",
                             params={"per_page": 50, "page": page, "_fields": "title,slug"},
                             headers={"User-Agent": "Mozilla/5.0 (PictoBot)"}, timeout=20)
            if not r.ok:
                break
            batch = r.json()
            out += [strip_tags((p.get("title") or {}).get("rendered", "")) for p in batch]
            if len(batch) < 50:
                break
            page += 1
        except Exception as e:
            print(f"[sibling] {base} 조회 실패: {e}")
            break
    return [t for t in out if t]


def main():
    try:
        conf = json.load(open(CONF, encoding="utf-8"))
    except Exception:
        conf = {"sites": ["https://wontheland.com"]}
    titles = []
    for s in conf.get("sites") or []:
        got = fetch(s)
        print(f"[sibling] {s} — 제목 {len(got)}건")
        titles += got
    if not titles:
        print("[sibling] 가져온 제목이 없어 기존 파일을 유지합니다")
        return
    prev = []
    try:
        prev = json.load(open(OUT, encoding="utf-8")).get("titles") or []
    except Exception:
        pass
    # 축적: 형제 사이트가 옛 글을 내려도 중복 회피 목록은 남긴다
    merged = sorted(set(prev) | set(titles))
    os.makedirs("dashboard/data", exist_ok=True)
    json.dump({"_설명": "형제 사이트 제목 — 주제 중복 회피 전용. 내부링크에는 절대 쓰지 않는다.",
               "sites": conf.get("sites"), "n": len(merged), "titles": merged},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[sibling] 저장 {len(prev)} → {len(merged)}건")


if __name__ == "__main__":
    main()
