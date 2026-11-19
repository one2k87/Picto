# -*- coding: utf-8 -*-
"""쿠팡 링크 블록을 '필요해지는 지점'으로 옮긴다 (2026-11-19 신설).

왜 전용 스크립트인가: patch_posts 의 문자열 치환으로 하려 했더니 **삭제 쪽이 한 곳도
안 맞았다**(삽입만 맞아 링크가 두 번 나올 뻔했다). 공개 REST 가 주는 rendered HTML 과
워드프레스가 보관하는 raw 가 공백·개행에서 달라서다. 그래서 여기서는 raw 를 읽어
블록을 **그 자리에서 찾아** 옮긴다 — 바깥에서 긁어 온 문자열에 기대지 않는다.

입력: data/link_moves.json
  [{"post_id": 379, "after_h2": "세탁기 거름망 청소 후, 더 완벽한 위생을 위한 추가 팁"}]
  블록은 그 h2 **앞**으로 간다(= 그 절을 읽기 직전).
환경변수: MOVE_DRY=true 면 계획만.
재실행 안전: 블록이 이미 목표 h2 앞에 있으면 건너뛴다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

from publisher import _auth_header, update_post_content

PLAN = os.path.join("data", "link_moves.json")


def block_span(h):
    """대가성 문구 + 상품 카드를 한 덩어리로 보고 (시작, 끝) 을 돌려준다.
    div 중첩을 세어 끝을 찾는다 — 정규식으로 </div> 를 세면 안쪽에서 끊긴다."""
    start = h.find('<div class="pick-product"')
    if start < 0:
        return None
    head = h.rfind('<p class="coupang-notice"', 0, start)
    # 고지가 카드 바로 앞(1,000자 이내)에 있을 때만 같이 옮긴다.
    if head < 0 or start - head > 1000:
        head = start
    depth, k = 0, start
    while k < len(h):
        m = re.compile(r"</?div\b").search(h, k)
        if not m:
            return None
        if h[m.start():m.start() + 5] == "</div":
            depth -= 1
            if depth == 0:
                return head, m.end() + 1
        else:
            depth += 1
        k = m.end()
    return None


def main():
    dry = (os.getenv("MOVE_DRY", "true").lower() != "false")
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    wp = dict(cfg.get("wordpress") or {})
    base = (wp.get("site_url") or wp.get("site") or "").rstrip("/")
    if not base:
        print("::error::wordpress.site_url 이 없습니다")
        return 2
    headers = _auth_header(wp)
    with open(PLAN, encoding="utf-8") as f:
        plan = json.load(f)

    done, skipped, failed = [], [], []
    for item in plan:
        pid, h2text = item["post_id"], item["after_h2"]
        r = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers,
                         params={"context": "edit", "_fields": "id,content"}, timeout=30)
        if r.status_code == 404:
            skipped.append(f"#{pid}(글 없음)")
            continue
        if r.status_code != 200:
            failed.append(f"#{pid}(조회 HTTP {r.status_code})")
            continue
        raw = (r.json().get("content") or {}).get("raw") or ""
        if not raw:
            failed.append(f"#{pid}(본문 비어 있음 — context=edit 권한 확인)")
            continue

        span = block_span(raw)
        if not span:
            skipped.append(f"#{pid}(상품 카드가 없음)")
            continue
        i, j = span
        block = raw[i:j]

        m = re.search(r"<h2[^>]*>\s*" + re.escape(h2text) + r"[^<]*</h2>", raw)
        if not m:
            failed.append(f"#{pid}(목표 h2 를 못 찾음: {h2text[:20]}…)")
            continue
        if i < m.start() and m.start() - j < 200:
            skipped.append(f"#{pid}(이미 그 자리에 있음)")
            continue

        rest = raw[:i] + raw[j:]
        m2 = re.search(r"<h2[^>]*>\s*" + re.escape(h2text) + r"[^<]*</h2>", rest)
        if not m2:
            failed.append(f"#{pid}(블록을 뺀 뒤 h2 를 못 찾음)")
            continue
        neo = rest[:m2.start()] + block + "\n" + rest[m2.start():]

        was = round(100 * i / len(raw))
        now = round(100 * m2.start() / len(neo))
        line = f"#{pid} {was}% → {now}% 「{h2text[:22]}」 앞 (블록 {len(block)}자)"
        if dry:
            print("  [계획]", line)
            done.append(line)
            continue
        if update_post_content(wp, pid, neo):
            print("  [적용]", line)
            done.append(line)
        else:
            failed.append(f"#{pid}(업로드 실패)")

    print(f"\n옮김 {len(done)} · 건너뜀 {len(skipped)} · 실패 {len(failed)}"
          + ("  (dry_run — 저장 안 함)" if dry else ""))
    for x in skipped:
        print("  건너뜀:", x)
    for x in failed:
        print("  실패:", x)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
