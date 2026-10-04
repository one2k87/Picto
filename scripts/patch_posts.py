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
       "meta": {"rank_math_title": "...", "rank_math_description": "..."}  # 선택
       "replace": [{"old": "낡은문자열", "new": "새문자열"}]            # 선택
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
            # SEO 메타(rank_math_*)도 같은 패치로 고친다. 섹션을 넣어 글이 답하는 질문이
            # 달라졌는데 검색결과에 보이는 제목·설명이 그대로면 클릭이 늘지 않는다.
            meta = p.get("meta") or {}
            if meta and not dry:
                rm = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers,
                                   json={"meta": meta}, timeout=30)
                if rm.status_code in (200, 201):
                    got = (rm.json().get("meta") or {})
                    bad = [k for k, v in meta.items() if (got.get(k) or "") != v]
                    print(f"    메타 {len(meta)}건 저장" + (f" · 반영 안 됨: {bad}" if bad else " · 전부 반영 확인"))
                    if bad:
                        failed.append(f"{name}(메타 미반영 {bad})")
                else:
                    print(f"    메타 저장 실패 HTTP {rm.status_code}")
                    failed.append(f"{name}(메타 HTTP {rm.status_code})")
            elif meta:
                print(f"    메타 {len(meta)}건 (dry_run — 저장 안 함): {list(meta)}")

            # 본문 안의 낡은 문자열 치환(깨진 링크 교체 등). marker 와 독립적으로 돌고,
            # 바꿀 게 없으면 조용히 지나간다.
            rep = p.get("replace") or []
            if rep:
                neo_r, hits = raw, 0
                for r in rep:
                    old, new = r.get("old") or "", r.get("new") or ""
                    if old and old in neo_r:
                        hits += neo_r.count(old)
                        neo_r = neo_r.replace(old, new)
                if hits and not dry:
                    if update_post_content(wp, pid, neo_r):
                        raw = neo_r
                        print(f"    치환 {hits}곳 적용")
                    else:
                        failed.append(f"{name}(치환 업로드 실패)")
                elif hits:
                    print(f"    치환 {hits}곳 (dry_run — 저장 안 함)")
                else:
                    print("    치환 대상 없음")

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
