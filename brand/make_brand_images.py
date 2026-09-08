# -*- coding: utf-8 -*-
"""픽담 브랜드 이미지 생성 — 로고(정사각) + 기본 소셜 공유 이미지(1200x630).

색: 딥 그린 #12503A(바탕) · #2E9E6B(포인트, 본문 상품 CTA와 같은 색) · #F7F5EF(크림)
모티프: 가격표(price tag) + 체크 — '고른다(픽)'와 '사기 전에 확인한다'를 한 형태에 담는다.
재생성: python3 brand/make_brand_images.py
"""
from PIL import Image, ImageDraw, ImageFont
import os

BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
REG  = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
KR = 2                                    # ttc 안의 KR 페이스

BG    = (18, 80, 58)
ACC   = (46, 158, 107)
CREAM = (247, 245, 239)
MUTED = (168, 199, 185)
SS = 4                                    # 슈퍼샘플링 배율(가장자리 계단 제거)


def f(path, size):
    return ImageFont.truetype(path, size, index=KR)


def tag_mark(size, bg=None):
    """가격표 + 체크 마크를 size×size 이미지로. bg=None이면 투명."""
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0) if bg is None else bg + (255,))
    d = ImageDraw.Draw(im)
    # 가격표 몸통: 왼쪽이 뾰족한 오각형 + 둥근 오른쪽
    L, T, R, B = int(S*0.12), int(S*0.22), int(S*0.88), int(S*0.78)
    tip = int(S*0.12)
    d.rounded_rectangle((L + tip//2, T, R, B), radius=int(S*0.10), fill=ACC)
    d.polygon([(L, (T+B)//2), (L + tip, T + int(S*0.02)), (L + tip, B - int(S*0.02))], fill=ACC)
    # 끈 구멍
    hx, hy, hr = L + int(S*0.13), (T+B)//2, int(S*0.038)
    d.ellipse((hx-hr, hy-hr, hx+hr, hy+hr), fill=BG if bg is None else bg)
    # 체크 — 구멍을 뺀 남은 폭의 한가운데에 놓는다
    cx = (hx + hr + R) // 2
    cy = (T + B) // 2
    s = int(S*0.30)
    w = int(S*0.055)
    d.line([(cx-s*0.46, cy+s*0.02), (cx-s*0.10, cy+s*0.36)], fill=CREAM, width=w, joint="curve")
    d.line([(cx-s*0.10, cy+s*0.36), (cx+s*0.50, cy-s*0.38)], fill=CREAM, width=w, joint="curve")
    return im.resize((size, size), Image.LANCZOS)


def logo(size):
    im = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size, size), radius=int(size*0.22), fill=BG)
    im.paste(tag_mark(size, BG), (0, 0))
    return im


for n in (512, 192, 112):
    logo(n).save(f"pickdam-logo-{n}.png", optimize=True)

# ── 기본 소셜 공유 이미지 1200x630
W, H = 1200, 630
og = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(og)
d.ellipse((W-330, H-330, W+150, H+150), fill=(22, 96, 70))     # 은은한 브랜드 원
og.paste(tag_mark(132, BG), (72, 62))
d.text((222, 92), "픽담", font=f(BOLD, 58), fill=CREAM)
d.text((72, 232), "사기 전에 확인하는 곳", font=f(BOLD, 78), fill=CREAM)
d.text((72, 342), "생활·주방 제품의 규격·유지비·주의점을", font=f(REG, 40), fill=MUTED)
d.text((72, 398), "사기 전에 한 번에 정리합니다", font=f(REG, 40), fill=MUTED)
d.rectangle((72, 492, 168, 498), fill=ACC)
d.text((72, 528), "pickdam.com", font=f(BOLD, 34), fill=ACC)
og.save("pickdam-og-1200x630.png", optimize=True)

for p in sorted(os.listdir(".")):
    if p.endswith(".png"):
        print(p, os.path.getsize(p), Image.open(p).size)
