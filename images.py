"""
images.py - 글에 들어갈 이미지를 '자동 생성'.

제공자(config.images.provider):
  - "free"     : (권장·무료) 무료 스톡 사진 시도 → 실패 시 코드 썸네일. 비용 0.
  - "stock"    : 무료 스톡 사진만(Pexels/Unsplash). 키 필요(무료 발급).
  - "thumbnail": 코드로 제목 썸네일 생성만. 키 불필요, 항상 성공, 완전 무료.
  - "openai"   : OpenAI 이미지(gpt-image-1). OPENAI 키 필요(유료).
  - "gemini"   : Google Imagen. Gemini 키(이미지 모델 권한) 필요(유료).
  - "none"     : 생성 안 함 → generator가 자리 표시(placeholder)로 대체.

생성된 PNG는 out_dir에 저장하고, 상황에 맞게:
  - WordPress 게시 시: 미디어로 업로드해 URL 사용(publisher.upload_media)
  - 그 외: base64 data URI로 본문에 인라인 삽입(복붙/미리보기에서 바로 보임)
실패해도 파이프라인이 멈추지 않도록 항상 안전하게 None을 반환한다.
"""

import os
import re
import time
import base64


def build_prompt(desc, category, style):
    style = style or "clean modern flat vector illustration, soft professional colors, minimal text, no watermark"
    return f"{style}. Topic: {category} 블로그용 이미지 - {desc}"


def generate_image(desc, cfg_images, out_dir, idx=0, category=""):
    """desc(한국어 설명)로 이미지 1장 생성 → 저장 경로 반환(실패 시 None)."""
    cfg_images = cfg_images or {}
    provider = cfg_images.get("provider", "none")
    if provider in ("none", None, ""):
        return None
    size = cfg_images.get("size", "1024x1024")

    data = None
    if provider == "free":
        # 무료 우선: 스톡 → (실패 시) 코드 썸네일. 항상 무언가는 나옴.
        data = _stock(desc, category, cfg_images, size) or _thumbnail(desc, category, size)
    elif provider in ("stock", "pexels", "unsplash"):
        data = _stock(desc, category, cfg_images, size)
    elif provider in ("thumbnail", "thumb", "code"):
        data = _thumbnail(desc, category, size)
    elif provider == "openai":
        data = _openai(build_prompt(desc, category, cfg_images.get("style")), cfg_images, size)
    elif provider in ("gemini", "imagen", "google"):
        data = _gemini(build_prompt(desc, category, cfg_images.get("style")), cfg_images)
    if not data:
        return None

    # 사용량/비용 집계(유료 provider만 비용 발생)
    try:
        import monitor
        monitor.bump_image(paid=provider in ("openai", "gemini", "imagen", "google"))
    except Exception:
        pass

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"img_{int(time.time()*1000)}_{idx}.png")
    with open(path, "wb") as f:
        f.write(data)
    return path


# ── 무료 스톡 사진 (Pexels / Unsplash) ─────────────────────────────
_STOCK_KW = {
    "금융": "finance money savings", "재테크": "finance investment savings",
    "건강": "health wellness lifestyle", "생활": "daily life home",
    "경제": "economy business chart", "IT": "technology laptop office",
    "부동산": "real estate house", "대출": "money loan finance",
    "보험": "insurance protection", "투자": "investment stock market",
    "다이어트": "diet healthy food", "여행": "travel trip",
}


def _stock_query(desc, category):
    """한국어 desc/카테고리 → 스톡 검색용 영어 키워드."""
    text = f"{category} {desc}"
    for k, v in _STOCK_KW.items():
        if k in text:
            return v
    return "business abstract background"


def _http_get(url, headers=None, params=None, timeout=15):
    import requests
    return requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)


def _stock(desc, category, cfg, size):
    """무료 스톡 사진 1장의 바이트를 반환(실패 시 None)."""
    query = _stock_query(desc, category)
    pexels = cfg.get("pexels_key") or os.getenv("PEXELS_API_KEY")
    unsplash = cfg.get("unsplash_key") or os.getenv("UNSPLASH_ACCESS_KEY")
    try:
        if pexels:
            r = _http_get("https://api.pexels.com/v1/search",
                          headers={"Authorization": pexels},
                          params={"query": query, "per_page": 1, "orientation": "landscape"})
            if r.status_code == 200:
                photos = r.json().get("photos", [])
                if photos:
                    src = photos[0]["src"].get("large") or photos[0]["src"].get("original")
                    img = _http_get(src)
                    if img.status_code == 200:
                        print(f"[images] 무료 스톡(Pexels) 사용: {query}")
                        return img.content
            else:
                print(f"[images] Pexels 응답 {r.status_code}")
        if unsplash:
            r = _http_get("https://api.unsplash.com/search/photos",
                          headers={"Authorization": f"Client-ID {unsplash}"},
                          params={"query": query, "per_page": 1, "orientation": "landscape"})
            if r.status_code == 200:
                res = r.json().get("results", [])
                if res:
                    src = res[0]["urls"].get("regular")
                    img = _http_get(src)
                    if img.status_code == 200:
                        print(f"[images] 무료 스톡(Unsplash) 사용: {query}")
                        return img.content
    except Exception as e:
        print(f"[images] 스톡 사진 실패(무시): {e}")
    return None


# ── 코드 썸네일 (Pillow, 완전 무료·키 불필요) ────────────────────────
_CAT_COLOR = {
    "금융": (124, 92, 255), "재테크": (124, 92, 255),
    "건강": (46, 179, 127), "생활": (46, 179, 127),
    "경제": (255, 138, 76), "IT": (74, 144, 226),
}


def _find_kr_font():
    """시스템에서 한글 지원 폰트 경로를 찾는다(없으면 None)."""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "C:\\Windows\\Fonts\\malgunbd.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _short_title(desc):
    t = re.sub(r"\s+", " ", str(desc or "")).strip()
    t = re.sub(r"[\"'“”‘’]", "", t)
    return t[:40] if len(t) > 40 else t


def _thumbnail(desc, category, size):
    """제목을 얹은 브랜드 썸네일 이미지 바이트 생성(완전 무료)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        print(f"[images] Pillow 없음(썸네일 건너뜀): {e}")
        return None
    try:
        w, h = (int(x) for x in str(size).lower().split("x"))
    except Exception:
        w, h = 1024, 1024
    base = next((c for k, c in _CAT_COLOR.items() if k in f"{category}"), (124, 92, 255))
    # 세로 그라데이션 배경
    img = Image.new("RGB", (w, h), base)
    top = tuple(min(255, int(v * 0.55)) for v in base)   # 위는 진하게
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(top[i] + (base[i] - top[i]) * t) for i in range(3))
        for x in range(0, w, w):  # 한 줄씩
            pass
        img.paste(Image.new("RGB", (w, 1), row), (0, y))
    draw = ImageDraw.Draw(img)

    font_path = _find_kr_font()
    title = _short_title(desc)
    if font_path:
        # 제목 폰트 크기: 이미지 폭에 맞춰 조정
        fsize = max(28, int(w / 12))
        try:
            font = ImageFont.truetype(font_path, fsize)
            small = ImageFont.truetype(font_path, max(16, int(w / 34)))
        except Exception:
            font = ImageFont.load_default(); small = font
        # 제목 줄바꿈(폭 기준)
        lines, cur = [], ""
        for ch in title:
            test = cur + ch
            if draw.textlength(test, font=font) > w * 0.82 and cur:
                lines.append(cur); cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
        lines = lines[:4]
        line_h = fsize + int(fsize * 0.35)
        total_h = line_h * len(lines)
        y = (h - total_h) // 2
        for ln in lines:
            tw = draw.textlength(ln, font=font)
            x = (w - tw) // 2
            draw.text((x + 2, y + 2), ln, font=font, fill=(0, 0, 0))       # 그림자
            draw.text((x, y), ln, font=font, fill=(255, 255, 255))
            y += line_h
        # 상단 카테고리 태그
        tag = f"{category}".strip() or "Scripto"
        draw.text((int(w * 0.06), int(h * 0.06)), tag, font=small, fill=(255, 255, 255))
        # 하단 브랜드
        draw.text((int(w * 0.06), int(h * 0.90)), "Scripto", font=small, fill=(255, 255, 255))
    else:
        print("[images] 한글 폰트 없음 → 글자 없는 배경 썸네일 생성")

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    print(f"[images] 코드 썸네일 생성: {title[:20]}")
    return buf.getvalue()


def to_data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def figure_html(src, alt):
    a = (alt or "").replace('"', "'")
    return (f'<figure style="margin:22px 0;text-align:center">'
            f'<img src="{src}" alt="{a}" loading="lazy" '
            f'style="max-width:100%;height:auto;border-radius:10px">'
            f'<figcaption style="font-size:13px;color:#98a2b3;margin-top:6px">{a}</figcaption>'
            f'</figure>')


def _openai(prompt, cfg, size):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.get("api_key") or os.getenv("OPENAI_API_KEY"))
        r = client.images.generate(model=cfg.get("model", "gpt-image-1"),
                                    prompt=prompt, size=size, n=1)
        return base64.b64decode(r.data[0].b64_json)
    except Exception as e:
        print(f"[images] openai 생성 실패: {e}")
        return None


def _gemini(prompt, cfg):
    try:
        import google.generativeai as genai
        genai.configure(api_key=cfg.get("api_key"))
        model = genai.ImageGenerationModel(cfg.get("model", "imagen-3.0-generate-001"))
        res = model.generate_images(prompt=prompt, number_of_images=1)
        img = res.images[0]
        # 라이브러리 버전에 따라 바이트 접근 경로가 다를 수 있어 방어적으로 처리
        for attr in ("_image_bytes", "image_bytes"):
            b = getattr(img, attr, None)
            if b:
                return b
        if hasattr(img, "_pil_image"):
            import io
            buf = io.BytesIO()
            img._pil_image.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:
        print(f"[images] gemini(imagen) 생성 실패: {e}")
    return None
