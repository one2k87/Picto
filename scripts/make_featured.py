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


# 2026-11-20 사용자 지시: "상품 사진만 빼서 세 개의 상품 사진이 중앙 좌우로
# 마치 순위 경쟁을 하는 듯하게".
# 파트너스 배너(240x480)는 구조가 일정하다. 세로 비율로 재면
#   0.00~0.11 쿠팡 로고 / 0.12~0.16 여백 / **0.165~0.615 상품 사진**
#   0.62 여백 / 0.63~0.80 상품명·배지 / 0.82~0.95 쇼핑하기 버튼
# 배너 3종을 재서 셋 다 같은 자리였다(11/20 실측). 그 구간만 떼어 쓴다.
# 뗀 사진은 쿠팡이 파트너스 소재로 내준 것이므로 출처를 이미지 안에 적는다.
SHOT_TOP, SHOT_BOT = 0.165, 0.615


def crop_shot(im):
    """배너에서 상품 사진 영역만 떼고, 둘레의 흰 여백을 잘라낸다."""
    w, h = im.size
    box = im.crop((0, int(h * SHOT_TOP), w, int(h * SHOT_BOT)))
    # 배너 바깥 테두리선을 먼저 깎는다. 11/20 실측: 좌우 맨 1열의 평균 밝기가 224 이고
    # 그 안쪽은 254~255 였다. 이 선을 남기면 ①비백색으로 잡혀 여백 제거가 통째로 빗나가고
    # ②테두리 흰색 비율이 0.52 로 떨어져 흰 배경 판정이 깨진다. 둘 다 "잘린 자국"으로 보인다.
    if box.width > 14:
        box = box.crop((3, 0, box.width - 3, box.height))
    try:
        import numpy as np
        a = np.asarray(box.convert("L"), dtype=float)
        ys, xs = np.where(a < 246)
        if len(ys) > 50:
            m = 4
            box = box.crop((max(0, xs.min() - m), max(0, ys.min() - m),
                            min(box.width, xs.max() + m), min(box.height, ys.max() + m)))
    except Exception:
        pass
    return box


# 2026-11-20 사용자 지시: "가격도 빼고 우선은 상품만 나오게 하고,
# 저렇게 자른 티가 안 나게 자연스럽게 보이도록".
# 잘라 낸 자국이 보이던 이유는 두 가지였다.
#   ① 배너가 JPEG 라 '흰' 배경이 실제로는 248~253 이어서 흰 캔버스 위에 네모가 떠 보였다.
#   ② 배너 안쪽 테두리선 1~2px 이 같이 잘려 들어왔다.
# 그래서 흰 배경 상품컷은 배경을 완전한 흰색으로 밀어 캔버스에 녹이고,
# 사진·그래픽 배경은 모서리를 둥글려 카드처럼 보이게 한다. 바닥에는 옅은 그림자를 깔아
# 물건이 떠 있지 않고 서 있는 것처럼 만든다.
def _arr(im):
    import numpy as np
    return np.asarray(im.convert("RGB")).astype("int16")


def _white_edge_ratio(im):
    """테두리 픽셀 중 거의 흰색인 비율 — 흰 배경 상품컷인지 가른다."""
    try:
        import numpy as np
        a = _arr(im)
        L = a.max(axis=2)
        b = np.concatenate([L[0, :], L[-1, :], L[:, 0], L[:, -1]])
        return float((b >= 234).mean())
    except Exception:
        return 0.0


def _round_corners(im, r=18):
    """사진 배경은 모서리를 둥글려 흰 바탕 위에 카드처럼 앉힌다."""
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1],
                                           radius=r, fill=255)
    out = Image.new("RGB", im.size, BG)
    out.paste(im, (0, 0), mask)
    return out


def naturalize(im):
    """자른 자국을 지운다. (손질한 이미지, 흰배경이었는지)"""
    wr = _white_edge_ratio(im)
    if wr >= 0.85:
        # 밝기 임계로 한 번에 밀면 **흰 제품이 같이 지워진다**(11/20 실측: 흰 디스펜서
        # 몸통이 240~252 라 236 임계에 통째로 날아갔다). 그래서 네 귀퉁이에서
        # 번져 나가는 방식으로 **배경에 닿아 있는 흰색만** 지운다. 제품 안쪽의
        # 밝은 면은 배경과 이어져 있지 않으므로 건드리지 않는다.
        try:
            im = im.convert("RGB").copy()
            w, h = im.size
            for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                         (w // 2, 0), (w // 2, h - 1)):
                try:
                    ImageDraw.floodfill(im, seed, (255, 255, 255), thresh=10)
                except Exception:
                    pass
            if w > 8 and h > 8:
                im = im.crop((2, 2, w - 2, h - 2))
        except Exception:
            pass
        return im, True
    return _round_corners(im), False


def _floor_shadow(img, cx, base_y, w):
    """바닥 그림자 — 물건이 서 있는 것처럼 보이게."""
    try:
        from PIL import ImageFilter
        sw, sh = int(w * 0.82), 26
        if sw < 10:
            return
        lay = Image.new("L", (sw + 40, sh + 40), 0)
        ImageDraw.Draw(lay).ellipse([20, 20, 20 + sw, 20 + sh], fill=46)
        lay = lay.filter(ImageFilter.GaussianBlur(11))
        dark = Image.new("RGB", lay.size, (120, 128, 138))
        img.paste(dark, (cx - lay.width // 2, base_y - 14), lay)
    except Exception:
        pass


def podium(title, shots, sub, labels=None):
    """1위를 가운데 크게, 2·3위를 좌우 작게. 상품만 보이게 하고 가격은 넣지 않는다."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ft, fs, fr = font(52), font(26), font(30)
    for ln in wrap(d, title, ft, W - 120, lines=1):
        d.text((60, 46), ln, font=ft, fill=INK)
    if sub:
        d.text((60, 110), sub, font=fs, fill=SUB)

    base = H - 96                      # 사진이 서는 바닥선(아래는 순위 뱃지·출처 자리)
    order = [1, 0, 2][:len(shots)]     # 왼쪽 2위 · 가운데 1위 · 오른쪽 3위
    slots = [(205, 285, 300), (615, 415, 410), (1020, 285, 300)][:len(shots)]
    if len(shots) == 1:
        order, slots = [0], [(600, 420, 450)]
    elif len(shots) == 2:
        order, slots = [0, 1], [(430, 415, 410), (840, 300, 320)]

    rank_bg = [(222, 170, 44), (168, 176, 186), (183, 138, 99)]
    for pos, idx in enumerate(order):
        if idx >= len(shots):
            continue
        im, was_white = naturalize(shots[idx])
        cx, maxh, maxw = slots[pos]
        s = min(maxw / im.width, maxh / im.height)
        w2, h2 = max(1, int(im.width * s)), max(1, int(im.height * s))
        y0 = base - h2
        if was_white:
            _floor_shadow(img, cx, base, w2)
        img.paste(im.resize((w2, h2), Image.LANCZOS), (cx - w2 // 2, y0))
        # 순위는 사진 아래 가운데에 작은 원으로. 사진 위에 얹으면 상품을 가린다.
        r = 19
        by = base + 30
        d.ellipse([cx - r, by - r, cx + r, by + r], fill=rank_bg[min(idx, 2)])
        n = str(idx + 1)
        d.text((cx - d.textlength(n, font=fr) / 2, by - 19), n, font=fr,
               fill=(255, 255, 255))
    fsrc = font(20)
    d.text((60, H - 34), "이미지: 쿠팡 파트너스 제공", font=fsrc, fill=(178, 186, 196))
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

        withimg = [e for e in top3 if e.get("image")]
        raw = [(e, fetch(e["image"])) for e in withimg]
        pairs = [(e, crop_shot(im)) for e, im in raw if im]
        if not pairs:
            print(f"  ✗ {disp}: 쓸 수 있는 상품 사진이 하나도 없다 — 대표 이미지를 만들지 않는다")
            continue
        today = dt.date.today()
        # 2026-11-20 사용자 지시로 대표 이미지에서 가격을 뺐다. 상품만 보이게 한다.
        # 가격은 본문 상품 카드에 날짜와 함께 적혀 있다.
        asof = f"{today.year}년 {today.month}월 {today.day}일 기준"
        shots = [im for _, im in pairs]

        p1 = os.path.join(OUT, base + ".png")
        podium(f"{disp}, 지금 얼마에 살 수 있나", shots[:1], asof).save(p1)
        made.append((base, p1))
        print(f"  ✓ {p1}  (상품 사진 1장)")

        if len(shots) >= 2:
            p2 = os.path.join(OUT, base + "-top3.png")
            podium(f"{disp} 톱3 비교", shots[:3], asof).save(p2)
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
