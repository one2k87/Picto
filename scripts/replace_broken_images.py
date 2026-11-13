# -*- coding: utf-8 -*-
"""본문에 남은 깨진 이미지를 **코드 썸네일**로 바꾼다 (2026-11-13 신설).

**왜 AI 재생성이 아니라 코드 썸네일인가**
  11/13 사고 수습에서 AI 로 다시 그렸더니 **또 깨졌다**(1차는 말풍선 도배, 2차는 액자에 작은
  깨진 글자). Cloudflare FLUX 는 한글을 쓰지 못하고, 글자 금지 프롬프트도 장면에 따라 샌다.
  코드 썸네일은 Pillow 가 한글 폰트로 직접 그리므로 **구조적으로 깨질 수 없다.**
  덜 화려하지만 깨진 글자가 박힌 그림보다 낫다 — 사람이 보면 바로 닫는다.

`reimage` 는 글당 **대표 이미지 1장만** 바꾼다(`count=1`). 본문에 남은 나머지를 여기서 처리한다.

환경변수
  FIXIMG_TARGETS  "글ID:파일명,파일명;글ID:파일명" 형식. 예)
                  "746:img_a.png,img_b.png;738:img_c.png"
  FIXIMG_DRY      true 면 계획만
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import requests

import images
from publisher import _auth_header, upload_media


def parse_targets(raw):
    out = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        pid, files = part.split(":", 1)
        names = [f.strip() for f in files.split(",") if f.strip()]
        if pid.strip().isdigit() and names:
            out[int(pid.strip())] = names
    return out


def main():
    targets = parse_targets(os.getenv("FIXIMG_TARGETS", ""))
    dry = (os.getenv("FIXIMG_DRY") or "").lower() == "true"
    if not targets:
        print("FIXIMG_TARGETS 가 비어 있다 — 할 일 없음")
        return 0
    cfg = json.load(open("config.json", encoding="utf-8"))
    wp = cfg.get("wordpress") or {}
    if not (wp.get("enabled") and wp.get("site_url")):
        print("WP 설정 없음 — 종료")
        return 1
    base = wp["site_url"].rstrip("/")
    headers = _auth_header(wp["username"], wp["app_password"])
    ok = bad = 0

    for pid, names in targets.items():
        r = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers, timeout=40,
                         params={"context": "edit", "_fields": "id,title,content"})
        if r.status_code != 200:
            print(f"✗ #{pid} 조회 실패 {r.status_code}")
            bad += 1
            continue
        p = r.json()
        content = (p.get("content") or {}).get("raw") or ""
        # 상단 라벨용 카테고리 — 빈 값이면 썸네일 위아래가 모두 '픽담' 으로 찍힌다(2026-11-13 실측)
        cat = ""
        try:
            cr = requests.get(f"{base}/wp-json/wp/v2/posts/{pid}", headers=headers, timeout=20,
                              params={"_fields": "categories", "_embed": "wp:term"})
            if cr.status_code == 200:
                terms = (cr.json().get("_embedded") or {}).get("wp:term") or []
                cat = next((t[0].get("name", "") for t in terms if t), "")
        except Exception:
            pass
        title = re.sub("<[^>]+>", "", (p.get("title") or {}).get("raw", ""))
        new = content
        for name in names:
            # 이 파일을 쓰는 <img> 의 alt 를 제목으로 삼는다 — 장면 설명이 들어 있어 서로 달라진다.
            m = re.search(r'<img\b[^>]*src="([^"]*' + re.escape(name) + r')"[^>]*>', new)
            if not m:
                print(f"  · #{pid} {name} — 본문에 없음(이미 치웠거나 주소가 다름)")
                continue
            tag = m.group(0)
            alt = (re.search(r'alt="([^"]*)"', tag) or [None, ""])[1]
            cap = alt or title
            data = images._thumbnail(cap, cat, "1200x675")
            if not data:
                print(f"  ✗ #{pid} {name} — 썸네일 생성 실패")
                bad += 1
                continue
            print(f"  · #{pid} {name} → 코드 썸네일 『{images._short_title(cap)}』")
            if dry:
                ok += 1
                continue
            tmp = os.path.join("output", "fiximg")
            os.makedirs(tmp, exist_ok=True)
            base_name = re.sub(r"^(?:\d+_)+", "", name)   # 이미 교체된 파일은 접두사가 붙어 있다
            fp = os.path.join(tmp, f"{pid}_{base_name}")
            with open(fp, "wb") as f:
                f.write(data)
            url = upload_media(fp, wp, alt=cap)
            if not url:
                print(f"  ✗ #{pid} {name} — 업로드 실패")
                bad += 1
                continue
            new = new.replace(m.group(1), url)      # src 만 바꾼다(figure·alt 구조 유지)
            ok += 1
        if dry or new == content:
            continue
        r2 = requests.post(f"{base}/wp-json/wp/v2/posts/{pid}",
                           headers={**headers, "Content-Type": "application/json"},
                           json={"content": new}, timeout=60)
        print(f"  {'✓' if r2.status_code in (200, 201) else '✗'} #{pid} 글 수정 {r2.status_code}")
        if r2.status_code not in (200, 201):
            bad += 1

    print(f"\n교체 {ok}장 · 실패 {bad}장 (dry={dry})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
