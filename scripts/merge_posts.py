# -*- coding: utf-8 -*-
"""중복 주제 글 통합 (2026-10-12 신설, 사용자 승인).

왜 — 40편 중 서로 다른 제품군이 24개뿐이었다(음식물처리기 6·비데 4·양념통 2).
     색인 27 / 미색인 13 의 구조 차이는 없었고(분량·H2·내부링크 동일), 구글 서치
     센트럴 커뮤니티 가이드는 'Discovered - currently not indexed' 의 첫 처방으로
     **중복 통합**을 든다 — "Google doesn't like to see the same content on
     multiple URLs", "기존 콘텐츠가 더 크롤할 이유를 주지 못하는 것이 문제".

단계 (MERGE_PHASE)
  content : 원문의 알맹이를 기둥글 뒤에 새 섹션으로 붙인다. 원문은 그대로 둔다.
  retire  : 원문을 **휴지통**으로 보낸다(영구 삭제 아님). 리다이렉트를 건 뒤에 실행한다.
순서를 지켜야 주소가 404 로 비는 구간이 안 생긴다.

환경: MERGE_PHASE(content|retire) · MERGE_DRY(true면 계획만) · MERGE_ONLY(원문 ID 쉼표)
결과: dashboard/data/merge_log.json
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from publisher import _auth_header, update_post_content

PLAN = os.path.join("data", "merge_plan.json")
DATA = os.path.join("dashboard", "data")
NOTICE_RE = re.compile(r'<p[^>]*>\s*이 (?:포스팅|게시물)은 쿠팡 파트너스 활동의 일환[^<]*</p>')


def _spans(html, opener='<div class="pick-product"'):
    """중첩 div 를 세어 블록의 (시작, 끝) 을 정확히 찾는다."""
    out, i = [], 0
    while True:
        s = html.find(opener, i)
        if s < 0:
            return out
        depth, j = 0, s
        while j < len(html):
            if html.startswith("<div", j):
                depth += 1
            elif html.startswith("</div>", j):
                depth -= 1
                if depth == 0:
                    j += 6
                    break
            j += 1
        out.append((s, j))
        i = j


def strip_commerce(html):
    """원문에서 상품 카드·고지 문구를 걷어낸다 — 기둥글에 이미 제 것이 있다."""
    h = html
    for a, b in reversed(_spans(h)):
        h = h[:a] + h[b:]
    h = re.sub(r"<!--picklink-->.*?<!--/picklink-->", "", h, flags=re.S)
    h = NOTICE_RE.sub("", h)
    h = re.sub(r"(?:\s*<p>\s*</p>)+", "", h)
    return h.strip()


def demote(html):
    """흡수되는 글의 h2 는 기둥글 안에서 h3 가 된다 — 제목 계층을 지킨다."""
    return re.sub(r"<(/?)h2\b", r"<\1h3", html)


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress", {}) or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    phase = (os.getenv("MERGE_PHASE") or "content").strip()
    dry = (os.getenv("MERGE_DRY") or "").lower() == "true"
    only = {x.strip() for x in (os.getenv("MERGE_ONLY") or "").split(",") if x.strip()}
    plan = json.load(open(PLAN, encoding="utf-8"))["merges"]
    if only:
        plan = [m for m in plan if str(m["source"]) in only]
    print(f"[merge] 단계={phase} · {len(plan)}건 · dry_run={dry}\n")

    def get(pid):
        r = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers, timeout=40,
                         params={"context": "edit", "_fields": "id,link,title,content,status"})
        return r.json() if r.status_code == 200 else None

    log, ok, skip, bad = [], 0, 0, 0
    for m in plan:
        tid, sid = int(m["target"]), int(m["source"])
        t, s = get(tid), get(sid)
        if not t or not s:
            print(f"  ✖ #{sid}→#{tid}: 글 조회 실패")
            bad += 1
            continue
        st = re.sub("<[^>]+>", "", (s.get("title") or {}).get("rendered", ""))[:34]
        mark = f"<!--merged:{sid}-->"
        traw = (t.get("content") or {}).get("raw") or ""
        sraw = (s.get("content") or {}).get("raw") or ""

        if phase == "content":
            if mark in traw:
                print(f"  · #{sid}→#{tid} 이미 통합됨 — 건너뜀")
                skip += 1
                continue
            body = demote(strip_commerce(sraw))
            if len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", body))) < 400:
                print(f"  ✖ #{sid}→#{tid}: 옮길 본문이 너무 적습니다")
                bad += 1
                continue
            block = (f"\n{mark}\n<h2>{m['heading']}</h2>\n{body}\n")
            neo = traw + block
            print(f"  · #{sid} {st}\n      → #{tid} 뒤에 추가 ({len(traw)} → {len(neo)}자)")
            if dry:
                skip += 1
                continue
            if update_post_content(wp, tid, neo):
                ok += 1
                log.append({"phase": phase, "source": sid, "target": tid, "ok": True})
            else:
                bad += 1
                log.append({"phase": phase, "source": sid, "target": tid, "ok": False})

        elif phase == "retire":
            if mark not in traw:
                print(f"  ✖ #{sid}: 기둥글 #{tid} 에 통합 흔적이 없습니다 — 먼저 content 단계를 돌리세요")
                bad += 1
                continue
            if s.get("status") == "trash":
                print(f"  · #{sid} 이미 휴지통")
                skip += 1
                continue
            print(f"  · #{sid} {st} → 휴지통 (영구 삭제 아님)")
            if dry:
                skip += 1
                continue
            r = requests.delete(f"{base}/wp-json/wp/v2/posts/{sid}", headers=headers, timeout=40)
            if r.status_code == 200:
                # 없앤 주소를 기록해 둔다 — 작동 점검이 매일 301 인지 확인한다.
                # 휴지통 글은 나중에 REST 로 주소를 되찾을 수 없으므로 지금 적어야 한다.
                mu = os.path.join(DATA, "merge_urls.json")
                try:
                    cur = json.load(open(mu, encoding="utf-8"))
                except Exception:
                    cur = {"_doc": "중복 통합으로 없앤 주소. 작동 점검이 301 을 확인한다.",
                           "retired": []}
                if s.get("link") and s["link"] not in cur.get("retired", []):
                    cur.setdefault("retired", []).append(s["link"])
                os.makedirs(DATA, exist_ok=True)
                json.dump(cur, open(mu, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                ok += 1
                log.append({"phase": phase, "source": sid, "target": tid, "ok": True})
            else:
                print(f"      실패 HTTP {r.status_code}")
                bad += 1
                log.append({"phase": phase, "source": sid, "target": tid, "ok": False})
        else:
            print(f"알 수 없는 단계: {phase}")
            return 1

    os.makedirs(DATA, exist_ok=True)
    prev = []
    try:
        prev = json.load(open(os.path.join(DATA, "merge_log.json"), encoding="utf-8")).get("rows", [])
    except Exception:
        pass
    json.dump({"at": datetime.datetime.now().isoformat()[:19], "phase": phase, "dry": dry,
               "rows": (prev + log)[-200:]},
              open(os.path.join(DATA, "merge_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[merge] 적용 {ok} · 건너뜀 {skip} · 실패 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
