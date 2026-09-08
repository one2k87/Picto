# 픽담 브랜드 이미지

`make_brand_images.py`로 생성한다(파이썬 + Noto Sans CJK). 손으로 고치지 말고 스크립트를 고쳐서 다시 만든다.

| 파일 | 크기 | 쓰이는 곳 |
|---|---|---|
| `pickdam-logo-512.png` | 512×512 | Rank Math → 구글에 표시될 로고(지식 그래프 JSON-LD `#logo`) |
| `pickdam-logo-192.png` | 192×192 | PWA·파비콘 예비 |
| `pickdam-logo-112.png` | 112×112 | 구글 최소 규격 확인용 |
| `pickdam-og-1200x630.png` | 1200×630 | Rank Math → 기본 소셜 공유 이미지(`og:image`·`twitter:image` 폴백) |

- 색: `#12503A`(바탕) · `#2E9E6B`(포인트 — 본문 상품 카드 CTA와 같은 색) · `#F7F5EF`(크림)
- 모티프: 가격표 + 체크 = "고른다(픽)" + "사기 전에 확인한다"
- 2026-09-08 픽담 미디어에 업로드하고 Rank Math에 등록 완료. 공개 페이지에서 `og:image`·JSON-LD `#logo` 반영 실측.
