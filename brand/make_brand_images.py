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

# 마크가 제 캔버스에서 차지하는 폭(0.88-0.12). 아래 app_icon()의 축소 계산 기준.
MARK_SPAN = 0.76
# 크롭 안전 아이콘에서 마크가 차지할 폭. 0.76 그대로면 원·둥근사각 크롭에 잘린다.
MARK_RATIO_SAFE = 0.66


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


def app_icon(size):
    """크롭 안전 아이콘 — 플랫폼이 원·둥근사각으로 잘라도 형태가 온전히 남는다.

    왜 logo()와 따로 두는가. logo()는 마크가 캔버스의 76%라 가장자리에 거의 붙어 있어,
    핀터레스트처럼 원으로 잘라 보여주는 곳에서는 **가격표의 뾰족한 왼쪽 끝이 잘려
    체크만 남는다**(2026-09-09 핀터레스트 프로필, 2026-09-10 개발자 앱 아이콘에서 연속 실측
    — 마크토 세션 보고). 여기서는 마크를 66%로 줄여 가운데 놓는다.

    모서리를 직접 둥글리지 않는 것도 의도다 — 플랫폼 곡률과 어긋나면 흰 귀퉁이가 비친다.
    """
    im = Image.new("RGB", (size, size), BG)
    inner = int(round(size * MARK_RATIO_SAFE / MARK_SPAN))
    m = tag_mark(inner)                        # 투명 배경 + 구멍은 BG
    off = (size - inner) // 2
    im.paste(m, (off, off), m)
    return im


def crop_safety():
    """마크 모서리가 반지름의 몇 배 지점인지. 1.00 미만이면 원 크롭에 안 잘린다."""
    w = MARK_RATIO_SAFE
    h = w * (0.78 - 0.22) / (0.88 - 0.12)      # 마크의 세로/가로 비
    return ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5 / 0.5


for n in (512, 192, 112):
    logo(n).save(f"pickdam-logo-{n}.png", optimize=True)

# 크롭 안전판 — 핀터레스트·SNS 프로필/앱 아이콘용. 마크토가 이 파일을 가져다 쓴다.
for n in (512, 192):
    app_icon(n).save(f"pickdam-app-icon-{n}.png", optimize=True)
print(f"원 크롭 여유: 마크 모서리가 반지름의 {crop_safety():.2f}배 지점 (1.00 미만이면 안전)")

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
