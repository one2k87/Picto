# -*- coding: utf-8 -*-
"""콕픽(캐스토) 구조화 데이터 블록 — 브리프 6-C 구현 (2026-09-08 신설).

왜 필요한가:
  캐스토가 픽담 글에서 '조건분기·설치규격·유지비·주의점'을 읽어가지 못하면
  그 정보를 LLM으로 지어내게 되고, 영상과 글의 근거가 어긋나 채널 신뢰가 깨진다.
  (캐스토 브리프 6-C: "이게 없으면 …그 순간 채널 신뢰가 무너진다")

확정 형식 — 두 경로로 같은 값을 낸다(캐스토는 둘 중 편한 쪽을 쓴다):
  ① 본문 끝의 주석 블록  <!--KOKPICK { … } KOKPICK-->
     → wp-json .../posts 의 content.rendered 만으로 파싱 가능(추가 인증·플러그인 불필요).
  ② 글 메타 `kokpick` (JSON 문자열)
     → wp-json .../posts?_fields=id,link,meta 로 한 번에. HTML 파싱이 필요 없다.
     (픽담에 WPCode 스니펫 'Rank Math 메타 REST 등록'이 kokpick 키도 함께 등록한다)

결측 규칙(브리프 명시):
  - 값이 없는 필드도 **키는 남기고 빈 값**으로 둔다 → 캐스토가 결측을 감지해 폴백한다.
  - alt_uses(용도 외 활용)는 **근거가 있을 때만**. 없으면 빈 배열 + alt_uses_source 빈 문자열.
    캐스토는 이 값이 비면 「콕 딴짓」 영상을 만들지 않는다. 억지로 채우면 안전 사고 위험.

주의(측정된 제약):
  - 워드프레스 KSES는 주석 안의 연속 하이픈(--)을 한 개로 줄이고 꼬리 '-'를 지운다.
    그래서 값에서 '--'를 미리 없앤다(그대로 두면 주석이 깨질 수 있다).
  - 본문에 <script>는 REST 발행 시 삭제된다(실측). 그래서 JSON-LD가 아니라 주석을 쓴다.
"""
import json
import re

MARK_OPEN = "<!--KOKPICK"
MARK_CLOSE = "KOKPICK-->"
# 이미 블록이 들어간 글을 다시 처리하지 않기 위한 탐지용
BLOCK_RE = re.compile(r"<!--KOKPICK\s.*?KOKPICK-->", re.S)

# 캐스토가 기대하는 키 순서·기본값. 키는 절대 생략하지 않는다.
SCHEMA = {
    "product": "",
    "price_band": "",
    "condition_branch": [],
    "size_install": "",
    "maintenance": {"cycle": "", "cost_per_year": "", "consumable_url": ""},
    "cautions": [],
    "alt_uses": [],
    "alt_uses_source": "",
    "coupang_url": "",
}


# consumable_url(소모품 구매처)에 허용되는 호스트.
# 실측(2026-09-09): LLM이 글에 없던 **외부 쇼핑몰 링크**(kr.atomy.com)를 지어내 넣었다.
# 이 값은 캐스토가 영상 설명란에 그대로 쓸 수 있어, 남의 상점으로 트래픽을 보내거나
# 남의 제휴 링크를 대신 홍보하게 된다. 그래서 우리 라인 밖 호스트는 통째로 버린다.
ALLOWED_URL_HOSTS = ("pickdam.com", "link.coupang.com", "www.coupang.com")


def _safe_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    m = re.match(r"https?://([^/?#]+)", u, re.I)
    host = (m.group(1) if m else "").lower()
    if any(host == h or host.endswith("." + h) for h in ALLOWED_URL_HOSTS):
        return u
    return ""


def _clean(v):
    """주석 안전화: 연속 하이픈 제거, 제어문자 제거, 양끝 공백 정리."""
    if isinstance(v, str):
        v = re.sub(r"-{2,}", "-", v)
        v = re.sub(r"[\x00-\x1f\x7f]", " ", v)
        return v.strip()
    if isinstance(v, list):
        return [x for x in (_clean(i) for i in v) if x]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def build(article, product=None, coupang_url=""):
    """글(+매칭된 제품)에서 콕픽 블록 dict를 만든다. 없는 값은 빈 채로 남긴다."""
    raw = article.get("kokpick") or {}
    if not isinstance(raw, dict):
        raw = {}

    data = json.loads(json.dumps(SCHEMA))          # 깊은 복사
    for k in ("price_band", "size_install", "alt_uses_source"):
        if isinstance(raw.get(k), str):
            data[k] = raw[k]
    for k in ("condition_branch", "cautions", "alt_uses"):
        if isinstance(raw.get(k), list):
            data[k] = [str(x) for x in raw[k] if str(x).strip()]
    m = raw.get("maintenance")
    if isinstance(m, dict):
        for k in ("cycle", "cost_per_year", "consumable_url"):
            if isinstance(m.get(k), str):
                data["maintenance"][k] = m[k]

    # 제품명·가격대·링크는 대장(products.json)이 우선 — 사람이 확인한 값이기 때문.
    if product:
        data["product"] = product.get("name") or product.get("key") or ""
        if product.get("price_band"):
            data["price_band"] = product["price_band"]
    if not data["product"]:
        data["product"] = (article.get("focus_keyword") or "").strip()
    if coupang_url:
        data["coupang_url"] = coupang_url

    # 외부 쇼핑몰 링크는 버린다(위 ALLOWED_URL_HOSTS 주석 참조).
    data["maintenance"]["consumable_url"] = _safe_url(data["maintenance"]["consumable_url"])

    # 근거 없는 '용도 외 활용'은 통째로 버린다(브리프의 안전 규칙).
    if not data["alt_uses_source"]:
        data["alt_uses"] = []
    if not data["alt_uses"]:
        data["alt_uses_source"] = ""

    return _clean(data)


def to_json(data):
    """메타(`kokpick`)에 넣을 JSON 문자열."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def block_html(data):
    """본문 끝에 붙일 주석 블록. 화면에는 보이지 않는다."""
    body = json.dumps(data, ensure_ascii=False, indent=2)
    body = re.sub(r"-{2,}", "-", body)             # KSES 방어(이중 안전장치)
    return "\n" + MARK_OPEN + "\n" + body + "\n" + MARK_CLOSE + "\n"


def has_block(html):
    return bool(BLOCK_RE.search(html or ""))


def strip_block(html):
    """소급 적용 시 옛 블록을 지우고 새로 넣기 위한 제거기."""
    return BLOCK_RE.sub("", html or "").rstrip() + "\n"


def parse_block(html):
    """content.rendered에서 블록을 되읽는다(검증·테스트용). 없으면 None."""
    m = BLOCK_RE.search(html or "")
    if not m:
        return None
    inner = m.group(0)[len(MARK_OPEN):-len(MARK_CLOSE)].strip()
    try:
        return json.loads(inner)
    except Exception:
        return None


def is_empty(data):
    """제품명 말고는 아무 근거도 없는 블록인가(캐스토가 폴백할 상태인가)."""
    if not isinstance(data, dict):
        return True
    return not any([
        data.get("condition_branch"), data.get("cautions"),
        data.get("size_install"), data.get("alt_uses"),
        (data.get("maintenance") or {}).get("cycle"),
        (data.get("maintenance") or {}).get("cost_per_year"),
    ])
