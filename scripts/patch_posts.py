# -*- coding: utf-8 -*-
"""기발행 글에 '손으로 정한 섹션'을 소급 삽입한다 (2026-10-02 신설).

왜 필요했나: 전략 엔진이 "이 글에 이 섹션을 넣어라"는 액션을 내놓는데, 그걸 반영할
통로가 없어 사람이 워드프레스에 로그인해 붙여넣는 수밖에 없었다. 비밀값은 GitHub
시크릿에만 있으므로, 패치 내용을 저장소에 파일로 두고 이 워크플로가 대신 올린다.

사용법
  1) data/post_patches/<이름>.json 을 만든다.
     {
       "post_id": 63,
       "marker": "<!--patch:subs-vs-installment-->",   # 재실행 안전장치(필수)
       "position": {"before_nth_h2": 2},               # 또는 {"append": true}
       "html": "<h2>…</h2><p>…</p>",
       "byline_date": "2026년 10월 2일"                  # 선택: 최종 업데이트 날짜 교체
     }
  2) 워크플로 '글 섹션 소급 삽입'을 수동 실행한다(dry_run=true로 먼저 확인).

재실행 안전: marker 가 본문에 이미 있으면 건너뛴다. 삽입할 때 marker 를 함께 넣는다.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from publisher import _auth_header, update_post_content

PATCH_DIR = os.path.join("data", "post_patches")
BYLINE_RE = re.compile(r"(최종 업데이트\s*)\d{4}년\s*\d{1,2}월\s*\d{1,2}일")


def insert_before_nth_h2(html, block, nth):
    idxs = [m.start() for m in re.finditer(r"<h2\b", html)]
    if len(idxs) >= nth:
        pos = idxs[nth - 1]
        return html[:pos] + block + html[pos:], f"{nth}번째 h2 앞"
    return html + block, "h2 부족 → 본문 끝"


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    dry = (os.getenv("PATCH_DRY") or "").lower() == "true"
    only = (os.getenv("PATCH_ONLY") or "").strip()

    files = sorted(glob.glob(os.path.join(PATCH_DIR, "*.json")))
    if only:
        files = [f for f in files if only in os.path.basename(f)]
    if not files:
        print(f"패치 파일 없음({PATCH_DIR})")
        return 0
    print(f"패치 파일 {len(files)}개 · dry_run={dry}")

    done, skipped, failed = [], [], []
    for path in files:
        name = os.path.basename(path)
        try:
            p = json.load(open(path, encoding="utf-8"))
            pid = int(p["post_id"])
            mark = (p.get("marker") or "").strip()
            block = p.get("html") or ""
            if not mark or not block:
                failed.append(f"{name}(marker/html 누락)")
                continue

            r = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers,
                             params={"context": "edit", "_fields": "id,title,content"}, timeout=30)
            if r.status_code != 200:
                failed.append(f"{name}(조회 HTTP {r.status_code})")
                continue
            raw = (r.json().get("content") or {}).get("raw") or ""
            if not raw:
                failed.append(f"{name}(본문 비어 있음 — context=edit 권한 확인)")
                continue
            if mark in raw:
                skipped.append(f"{name}(이미 적용됨)")
                continue

            payload = mark + block
            pos = p.get("position") or {}
            if pos.get("append"):
                neo, where = raw + payload, "본문 끝"
            else:
                neo, where = insert_before_nth_h2(raw, payload, int(pos.get("before_nth_h2") or 2))

            bd = (p.get("byline_date") or "").strip()
            if bd and BYLINE_RE.search(neo):
                neo = BYLINE_RE.sub(lambda m: m.group(1) + bd, neo, count=1)

            print(f"  · #{pid} {name}: {where} · {len(raw)} → {len(neo)}자")
            if dry:
                skipped.append(f"{name}(dry_run)")
                continue
            if update_post_content(wp, pid, neo):
                done.append(f"#{pid} {name}")
            else:
                failed.append(f"{name}(업로드 실패)")
        except Exception as e:
            failed.append(f"{name}({str(e)[:60]})")

    print(f"\n적용 {len(done)} · 건너뜀 {len(skipped)} · 실패 {len(failed)}")
    for x in done:
        print("  적용:", x)
    for x in skipped:
        print("  건너뜀:", x)
    for x in failed:
        print("  실패:", x)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
