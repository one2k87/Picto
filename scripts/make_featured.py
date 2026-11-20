#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""유행템 글의 대표 이미지(메인 사진)를 상품 사진으로 만든다.

사용자 지시(2026-11-20): "메인 사진도 상품들 사진을 바탕으로 만들어야 해"

AI 로 그린 그림은 특정 제품의 사진이 아니므로 대표 이미지로 쓰면 안 된다.
검색 결과와 SNS 미리보기에 뜨는 자리라 더 그렇다. 쿠팡 파트너스가 내주는
공식 상품 배너를 **원본 그대로** 흰 바탕에 나란히 놓고 제목만 얹는다.
배너 자체는 자르거나 덧칠하지 않는다 — 비율을 지켜 크기만 맞춘다.

  python3 scripts/make_featured.py            # data/featured/ 에 PNG 생성
  python3 scripts/make_featured.py --upload   # 워드프레스에 올리고 대표 이미지로 지정
"""
import datetime as dt
import io
import json
import os
import sys

import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import images as images_mod                # noqa: E402
import products as products_mod            # noqa: E402

ITEMS = "data/trend_items.json"
POSTS = "data/trend_item_posts.json"
OUT = "data/featured"
W, H = 1200, 675
BG = (255, 255, 255)
INK = (26, 32, 44)
SUB = (113, 128, 150)


def font(size, bold=True):
    p = images_mod._find_kr_font()
    if not p:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(p, size, index=(1 if p.endswith(".ttc") else 0))
    except Exception:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            return ImageFont.load_default()


def wrap(draw, text, f, width, lines=2):
    out, cur = [], ""
    for ch in text:
        t = cur + ch
        if draw.textlength(t, font=f) > width and cur:
            out.append(cur)
            cur = ch
            if len(out) == lines:
                break
        else:
            cur = t
    if cur and len(out) < lines:
        out.append(cur)
    if len(out) == lines and draw.textlength(out[-1], font=f) > width - 20:
        out[-1] = out[-1][:-2] + "…"
    return out


def fetch(url):
    try:
        r = requests.get(url, timeout=25)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"     ✗ 사진을 못 받았다: {str(e)[:60]}")
    return None


def compose(title, shots, sub, lines_right=None):
    """흰 바탕에 제목 + 상품 배너들. 배너는 비율을 지켜 크기만 맞춘다."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ft = font(54)
    fs = font(28)
    lines = wrap(d, title, ft, W - 120, lines=2)
    y = 56
    for ln in lines:
        d.text((60, y), ln, font=ft, fill=INK)
        y += 66
    y += 6
    if sub:
        d.text((60, y), sub, font=fs, fill=SUB)
        y += 44

    top = max(y + 16, 220)
    box_h = H - top - 46
    n = len(shots)
    if n == 1 and lines_right:
        # 한 장일 때 가운데에 덩그러니 놓으면 허전하다. 왼쪽에 사진, 오른쪽에 글.
        im = shots[0]
        s = min(360 / im.width, box_h / im.height)
        w2, h2 = int(im.width * s), int(im.height * s)
        img.paste(im.resize((w2, h2), Image.LANCZOS), (110, top + (box_h - h2) // 2))
        fr, fp = font(30), font(46)
        ty = top + max(0, (box_h - 150) // 2)
        for ln in wrap(d, lines_right[0], fr, W - 560, lines=2):
            d.text((110 + w2 + 54, ty), ln, font=fr, fill=INK)
            ty += 40
        if len(lines_right) > 1:
            ty += 10
            d.text((110 + w2 + 54, ty), lines_right[1], font=fp, fill=(192, 57, 43))
        return img
    gap = 34
    each_w = (W - 120 - gap * (n - 1)) // n
    x = 60
    for im in shots:
        s = min(each_w / im.width, box_h / im.height)
        w2, h2 = int(im.width * s), int(im.height * s)
        im2 = im.resize((w2, h2), Image.LANCZOS)
        img.paste(im2, (x + (each_w - w2) // 2, top + (box_h - h2) // 2))
        x += each_w + gap
    return img


def resolve(entry):
    out = dict(entry)
    k = entry.get("product_key")
    if k:
        for p in products_mod.all_products():
            if p.get("key") == k:
                out.setdefault("name", p.get("banner_alt") or p.get("name"))
                for f in ("image", "price", "price_at"):
                    if p.get(f) and not out.get(f):
                        out[f] = p[f]
                break
    return out


def main():
    upload = "--upload" in sys.argv
    with open(ITEMS, encoding="utf-8") as f:
        items = json.load(f)
    os.makedirs(OUT, exist_ok=True)

    need_link = []          # 사진이 없어 대표 이미지를 못 만드는 제품
    made = []
    for key, it in items.items():
        disp = it.get("display") or key
        base = f"trend-{it.get('slug') or products_mod.safe_subid(key)}"
        top3 = [resolve(e) for e in (it.get("top3") or [])]
        for e in top3:
            if not e.get("image"):
                need_link.append((disp, e.get("name") or "(이름 없음)"))

        shots = [s for s in (fetch(e["image"]) for e in top3 if e.get("image")) if s]
        if not shots:
            print(f"  ✗ {disp}: 쓸 수 있는 상품 사진이 하나도 없다 — 대표 이미지를 만들지 않는다")
            continue
        today = dt.date.today()
        asof = f"{today.year}년 {today.month}월 {today.day}일 기준 가격"

        head = next((e for e in top3 if e.get("image")), {})
        right = [head.get("name") or ""]
        if head.get("price"):
            right.append(f"{int(head['price']):,}원")
        p1 = os.path.join(OUT, base + ".png")
        compose(f"{disp}, 지금 얼마에 살 수 있나", shots[:1], asof, right).save(p1)
        made.append((base, p1))
        print(f"  ✓ {p1}  (상품 사진 1장)")

        if len(shots) >= 2:
            p2 = os.path.join(OUT, base + "-top3.png")
            compose(f"{disp} 톱3 비교", shots[:3], asof).save(p2)
            made.append((base + "-top3", p2))
            print(f"  ✓ {p2}  (상품 사진 {len(shots[:3])}장)")

    for pr in products_mod.all_products():
        if pr.get("channel") == "pickdamblog" and not pr.get("image"):
            need_link.append(("대장 등록 유행템", pr.get("banner_alt") or pr.get("name") or pr.get("key")))

    if need_link:
        print("\n" + "=" * 62)
        print("상품 사진이 없어 대표 이미지에 넣지 못한 제품입니다.")
        print("쿠팡 파트너스 링크 생성 화면에서 채널 아이디를 pickdamblog 로 두고")
        print("「이미지+텍스트 → 블로그용 태그」 를 복사해 픽토 채팅에 붙여넣어 주세요.")
        print("  https://partners.coupang.com/#affiliate/ws/link")
        print("-" * 62)
        for disp, nm in need_link:
            print(f"  · [{disp}] {nm}")
        print("=" * 62)

    if not upload:
        print(f"\n대표 이미지 {len(made)}장. 워드프레스에 올리려면 --upload 를 붙인다.")
        return 0

    import publisher
    cfg = {}
    for p in ("config.json", "config.example.json"):
        if os.path.exists(p):
            cfg = json.load(open(p, encoding="utf-8"))
            break
    wp = dict(cfg.get("wordpress") or {})
    if not wp.get("enabled"):
        print("::warning::wordpress.enabled 가 False — 올리지 않는다")
        return 0
    try:
        posts = json.load(open(POSTS, encoding="utf-8"))
    except Exception:
        posts = {}
    for slug, path in made:
        rec = posts.get(slug)
        if not (rec and rec.get("id")):
            print(f"  · {slug}: 아직 발행되지 않아 대표 이미지를 붙일 글이 없다")
            continue
        url = publisher.upload_media(path, wp, alt=slug)
        if not url:
            print(f"  ✗ {slug}: 업로드 실패")
            continue
        mid = publisher.find_media_id(wp, url)
        if mid and publisher.set_featured(wp, rec["id"], mid):
            print(f"  ✓ #{rec['id']} 대표 이미지 지정")
        else:
            print(f"  ✗ #{rec['id']} 대표 이미지 지정 실패")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
