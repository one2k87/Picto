#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""글을 휴지통으로 보낸다(영구 삭제 아님).

2026-11-22: 중복 확인 조회가 실패해 같은 글 5편이 두 벌 올라갔다.
같은 내용이 두 편이면 구글이 어느 쪽을 본편으로 볼지 헷갈려 둘 다 깎인다.
영구 삭제는 하지 않는다 — 휴지통은 워드프레스 관리자에서 되돌릴 수 있다.

  python3 scripts/trash_posts.py 878,879,880        # 계획만
  python3 scripts/trash_posts.py 878,879,880 --apply
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import publisher                      # noqa: E402


def main():
    ids = []
    for a in sys.argv[1:]:
        if a.startswith("--"):
            continue
        ids += [int(x) for x in a.replace(" ", "").split(",") if x.strip().isdigit()]
    apply = "--apply" in sys.argv
    if not ids:
        print("::error::글 ID를 쉼표로 주세요. 예: 878,879,880")
        return 1

    cfg = {}
    for p in ("config.json", "config.example.json"):
        if os.path.exists(p):
            cfg = json.load(open(p, encoding="utf-8"))
            break
    wp = dict(cfg.get("wordpress") or {})
    if not (wp.get("enabled") and wp.get("site_url")):
        print("::error::wordpress 설정 없음")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = publisher._auth_header(wp["username"], wp["app_password"])

    ok = fail = 0
    for pid in ids:
        r = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}",
                         params={"_fields": "id,slug,title,status"},
                         headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"  ✗ #{pid}: 못 읽음 {r.status_code}")
            fail += 1
            continue
        d = r.json()
        title = (d.get("title") or {}).get("rendered", "")
        print(f"  → #{pid} [{d.get('status')}] {d.get('slug')} — {title[:36]}"
              + ("" if apply else "   (계획만)"))
        if not apply:
            ok += 1
            continue
        # DELETE(force 없이) = 휴지통. force=true 가 영구 삭제인데 쓰지 않는다.
        w = requests.delete(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers, timeout=40)
        if w.status_code in (200, 201):
            print("     ✓ 휴지통으로")
            ok += 1
        else:
            print(f"     ✗ 실패 {w.status_code}: {w.text[:110]}")
            fail += 1
    print(f"\n휴지통 {ok}건 · 실패 {fail}"
          + ("" if apply else "   (--apply 를 붙이면 실제로 보냅니다)"))
    return 0 if not fail else 2


if __name__ == "__main__":
    raise SystemExit(main())
