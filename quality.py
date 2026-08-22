"""
quality.py - 발행 전 자동 품질 게이트 (애드센스 '대량 저품질' 위험 완화).
- 최소 분량, 소제목 구조, 키워드 과다반복(스터핑), 다른 글과의 유사도(중복) 검사.
- 템플릿성 검사(제목 어미 반복 / 도입부 상투 구문) — 애드센스 반려 1순위 원인.
- 기준 미달이면 발행 보류(초안 유지) 대상으로 표시한다.

보류 사유는 두 갈래로 나뉜다(main.py가 이 분류를 보고 처리 방향을 정한다):
  · retry  = 고쳐서 다시 쓸 수 있음(분량·소제목·키워드·템플릿)  → 재생성 큐
  · discard = 고쳐도 같은 문제가 남음(주제 중복)                → 즉시 폐기
"""

import re

# 보류 사유 코드 → (분류, 사람이 읽는 설명, 자동 조치 힌트)
REASON_META = {
    "분량부족":     ("retry",   "본문이 기준보다 짧습니다. 내용이 얇으면 '가치 없는 콘텐츠'로 반려됩니다.",
                     "목표 분량을 올려 재생성"),
    "소제목부족":   ("retry",   "H2 소제목이 부족해 글 구조가 잡히지 않았습니다.",
                     "소제목 최소 개수를 프롬프트에 명시해 재생성"),
    "키워드과다반복": ("retry", "같은 키워드가 과도하게 반복됐습니다(스터핑). 검색엔진이 조작으로 봅니다.",
                     "키워드 반복 상한을 프롬프트에 명시해 재생성"),
    "제목템플릿":   ("retry",   "최근 쓴 글과 제목이 같은 말로 끝납니다. 양산형 사이트 신호입니다.",
                     "최근 사용한 제목 어미를 금지 목록으로 넘겨 재생성"),
    "도입부템플릿": ("retry",   "도입부가 최근 글과 같은 틀입니다. 심사관이 세 편만 읽어도 드러납니다.",
                     "도입 방식을 다른 유형으로 지정해 재생성"),
    "기존글과유사": ("discard", "이미 쓴 글과 내용이 겹칩니다. 주제 자체가 중복이라 고쳐도 또 겹칩니다.",
                     "폐기하고 주제를 교체"),
}

# 도입부 상투 구문(경험담 흉내 템플릿). 2개 이상 동시 검출 시 템플릿으로 판정.
_OPEN_CLICHE = [
    r"처음\s*(접했|알아봤|이용했|들었|봤|겪었)", r"줄\s*알았", r"생각했(습니다|던|어요)",
    r"실제로\s*(확인|진행|해보|알아)", r"가장\s*(중요|먼저)", r"느끼게\s*되었",
    r"알게\s*되었", r"헷갈리는", r"궁금해하는",
]
# 상투적 제목 표현
_TITLE_CLICHE = ["알아야 할", "알아보기", "총정리", "완벽 정리", "완벽 분석", "하는 방법",
                 "핵심 정보", "핵심 사항", "한 번에", "제대로", "활용법"]


def classify(reason_str):
    """보류 사유 문자열 → {code: (분류, 설명, 조치)} 목록. main.py/앱이 함께 쓴다."""
    out = []
    for code, meta in REASON_META.items():
        if code in (reason_str or ""):
            out.append({"code": code, "kind": meta[0], "why": meta[1], "fix": meta[2]})
    return out


def is_discard(reason_str):
    """폐기 대상이면 True(고쳐도 소용없는 사유가 하나라도 있으면 폐기)."""
    return any(c["kind"] == "discard" for c in classify(reason_str))


def title_ending(title):
    """제목의 마지막 어절(한국어는 여기서 템플릿성이 드러난다)."""
    w = re.findall(r"[가-힣A-Za-z0-9]+", title or "")
    return w[-1] if w else ""


def _first_sentence(text):
    m = re.match(r"^.{10,200}?[.!?。]", text or "", re.S)
    return (m.group(0) if m else (text or "")[:120]).strip()


def _bigrams(s):
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", s or "")
    return set(t[i:i + 2] for i in range(len(t) - 1))


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _words(t):
    return re.findall(r"[가-힣A-Za-z0-9]+", t or "")


def _shingles(words, n=3):
    return set(tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1)))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def check(article, other_texts, safety, recent=None):
    """(ok: bool, reason: str) 반환.

    recent: 최근 발행/생성된 글 목록 [{title, html|opening}] — 템플릿성 비교용(선택).
    """
    safety = safety or {}
    html = article.get("html", "")
    t = _text(html)
    words = _words(t)
    reasons = []

    min_chars = int(safety.get("min_chars", 700))
    if len(t) < min_chars:
        reasons.append(f"분량부족({len(t)}자<{min_chars})")

    if html.count("<h2") < int(safety.get("min_h2", 3)):
        reasons.append("소제목부족(H2<3)")

    # 키워드 스터핑
    fk = (article.get("focus_keyword") or "").strip()
    if fk and words:
        cnt = t.count(fk)
        density = cnt / max(1, len(words))
        if cnt >= int(safety.get("stuffing_count", 8)) and density > float(safety.get("max_keyword_density", 0.03)):
            reasons.append(f"키워드과다반복({cnt}회)")

    # 다른 글과 유사도(중복)
    sh = _shingles(words)
    thr = float(safety.get("max_similarity", 0.5))
    for ot in other_texts or []:
        if jaccard(sh, _shingles(_words(_text(ot)))) > thr:
            reasons.append("기존글과유사(중복위험)")
            break

    # ── 템플릿성 검사 (애드센스 반려 1순위 원인) ──────────────────────
    if safety.get("check_template", True):
        title = article.get("title") or ""

        # 1) 상투적 제목 표현
        if sum(1 for c in _TITLE_CLICHE if c in title) >= 1 and safety.get("block_title_cliche", True):
            reasons.append("제목템플릿(상투표현)")

        # 2) 최근 글과 제목 어미 중복
        recent = recent or []
        end = title_ending(title)
        if end and len(end) > 1:
            dup = sum(1 for r in recent if title_ending(r.get("title", "")) == end)
            if dup >= int(safety.get("max_same_title_ending", 2)):
                reasons.append(f"제목템플릿(어미'{end}' 최근 {dup}건)")

        # 3) 도입부 상투 구문
        opening = _first_sentence(_text(html))
        hits = sum(1 for p in _OPEN_CLICHE if re.search(p, opening))
        if hits >= 2:
            reasons.append("도입부템플릿(상투구문)")

        # 4) 최근 글과 도입부 서술부(문장 끝) 유사
        tail = re.sub(r"[.!?。]\s*$", "", opening)[-15:]
        if len(tail) >= 8:
            tg = _bigrams(tail)
            for r in recent:
                rt = r.get("opening") or _first_sentence(_text(r.get("html", "")))
                rt = re.sub(r"[.!?。]\s*$", "", rt)[-15:]
                if len(rt) >= 8:
                    og = _bigrams(rt)
                    inter = len(tg & og)
                    if inter and inter / max(1, len(tg | og)) >= 0.40:
                        reasons.append("도입부템플릿(최근글과 어미 유사)")
                        break

    return (len(reasons) == 0, "; ".join(reasons))
