"""
strategy.py — 수익 최대화 전략 엔진 (주 1회 실행)

목적: "지금 쓰고 있는 글이 실제로 상위노출되고 돈이 되고 있는가"를 데이터로 판정하고,
      다음 주에 무엇을 어떤 비율로 쓸지 계획을 만들어 dashboard/data/strategy.json에 남긴다.
      main.py는 매일 이 파일을 읽어 그날 쓸 글의 의도·카테고리를 정한다.

글의 의도(intent)는 두 가지로 나눈다 — 사용자가 정의한 수익 구조 그대로다.
  · revenue   : 상위노출 시 광고 단가가 높은 '결정 직전' 검색 (비용·가격·비교·한도·조건)
  · evergreen : 시즌을 타지 않고 계속 찾는 '방법·절차' 검색 (누적될수록 고정수익이 됨)

⚠️ 정직한 한계
  - 애드센스 API는 '페이지별 수익'을 주지 않는다(사이트 단위). 그래서 글별 수익은
    Search Console 클릭 수 × 의도별 RPM 가중치로 '추정'한다. 실측이 아니다.
  - 데이터가 없으면(발행 전·승인 전) 추정도 불가능하므로 기본 계획(seed)을 그대로 쓴다.
    이때 data_status는 "no_data"가 되고, 앱에 '아직 학습할 데이터가 없음'으로 표시된다.
"""

import json
import os
import re
from datetime import datetime, timedelta

DATA = os.path.join("dashboard", "data")
OUT = os.path.join(DATA, "strategy.json")

# 의도 판정 키워드 — 제목·키워드에 이 표현이 있으면 그 의도로 본다
REVENUE_KW = ["비용", "가격", "얼마", "요금", "수수료", "금리", "한도", "비교", "추천",
              "후기", "순위", "best", "top", "저렴", "할인", "보험료", "견적", "환급",
              "지원금", "혜택", "이자", "수익률", "연봉", "월급", "대출", "카드"]
EVERGREEN_KW = ["방법", "절차", "신청", "발급", "조건", "기준", "확인", "차이", "뜻",
                "종류", "준비물", "서류", "자격", "등록", "해지", "변경", "조회", "계산"]

# 의도별 추정 RPM 배수(광고 단가 감각치). 실측 아님 — 상대 비교용.
INTENT_RPM = {"revenue": 1.0, "evergreen": 0.55}

# 데이터가 없을 때 쓰는 기본 주간 계획.
# 하루 5편 기준. 월·금은 결정형 검색이 몰려 revenue 비중을 높인다.
SEED_WEEKDAY = {
    "0": {"label": "월", "revenue": 4, "evergreen": 1},
    "1": {"label": "화", "revenue": 2, "evergreen": 3},
    "2": {"label": "수", "revenue": 3, "evergreen": 2},
    "3": {"label": "목", "revenue": 2, "evergreen": 3},
    "4": {"label": "금", "revenue": 4, "evergreen": 1},
    "5": {"label": "토", "revenue": 1, "evergreen": 1},
    "6": {"label": "일", "revenue": 1, "evergreen": 1},
}


def classify_intent(text):
    """제목·키워드 문자열 → 'revenue' | 'evergreen'. 둘 다 걸리면 수익형 우선."""
    t = (text or "").lower()
    if any(k in t for k in REVENUE_KW):
        return "revenue"
    if any(k in t for k in EVERGREEN_KW):
        return "evergreen"
    return "evergreen"          # 애매하면 누적형으로 본다(안전한 쪽)


def _load(name):
    p = os.path.join(DATA, name)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _slug_of(url):
    if not url:
        return ""
    s = re.sub(r"[?#].*$", "", str(url)).rstrip("/")
    return s.split("/")[-1]


def score_articles(hist, sc):
    """발행 글에 Search Console 실적을 붙여 (카테고리×의도) 버킷 성과를 집계한다."""
    pages = {}
    for p in (sc or {}).get("pages", []):
        pages[_slug_of(p.get("page"))] = p
    buckets = {}
    matched = 0
    for a in (hist or {}).get("articles", []):
        if a.get("status") != "게시됨":
            continue
        intent = a.get("intent") or classify_intent(f"{a.get('title','')} {a.get('keyword','')}")
        cat = a.get("category") or "기타"
        key = f"{cat}|{intent}"
        b = buckets.setdefault(key, {"category": cat, "intent": intent,
                                     "posts": 0, "clicks": 0, "impressions": 0, "scored": 0})
        b["posts"] += 1
        pg = pages.get(_slug_of(a.get("post_url")))
        if pg:
            matched += 1
            b["scored"] += 1
            b["clicks"] += pg.get("clicks", 0)
            b["impressions"] += pg.get("impressions", 0)
    # 버킷별 추정 수익력 = 클릭 × 의도 RPM 배수 ÷ 글 수
    for b in buckets.values():
        b["est_value"] = round(b["clicks"] * INTENT_RPM.get(b["intent"], 0.7), 1)
        b["value_per_post"] = round(b["est_value"] / max(1, b["posts"]), 2)
        b["ctr"] = round(b["clicks"] / b["impressions"] * 100, 2) if b["impressions"] else 0.0
    return buckets, matched


def plan_from(buckets, min_posts=8):
    """버킷 성과 → 다음 주 의도 비율·카테고리 가중치. 데이터가 얇으면 seed를 유지한다."""
    usable = {k: b for k, b in buckets.items() if b["scored"] >= min_posts}
    if not usable:
        return None
    tot = {}
    for b in usable.values():
        tot[b["intent"]] = tot.get(b["intent"], 0) + b["value_per_post"]
    s = sum(tot.values())
    if s <= 0:
        return None
    ratio = {k: round(v / s, 2) for k, v in tot.items()}
    ratio.setdefault("revenue", 0.0)
    ratio.setdefault("evergreen", 0.0)
    # 한쪽으로 쏠려도 최소 20%는 남긴다(포트폴리오 붕괴 방지)
    for k in ("revenue", "evergreen"):
        ratio[k] = min(0.8, max(0.2, ratio[k]))
    n = sum(ratio.values())
    ratio = {k: round(v / n, 2) for k, v in ratio.items()}

    cats = {}
    for b in usable.values():
        cats[b["category"]] = cats.get(b["category"], 0) + b["value_per_post"]
    if cats:
        avg = sum(cats.values()) / len(cats)
        cats = {k: round(min(1.6, max(0.5, v / avg)), 2) for k, v in cats.items()} if avg > 0 else {}
    return {"intent_ratio": ratio, "category_weights": cats}


def weekday_plan(ratio, per_day=5):
    """의도 비율 → 요일별 편수. 월·금은 결정형(revenue) 쪽으로 한 편 더 기울인다.

    한쪽이 아무리 잘 나와도 **하루에 최소 1편은 반대 의도를 남긴다.**
    수익형만 쓰면 단기 수익은 오르지만 누적 트래픽 기반이 사라져
    다음 분기에 전체가 함께 꺼진다(포트폴리오 붕괴 방지).
    """
    out = {}
    tilt = {"0": +1, "4": +1, "1": -1, "3": -1}      # 월/금 +, 화/목 −
    for d, seed in SEED_WEEKDAY.items():
        base = per_day if d not in ("5", "6") else 2
        rev = round(base * ratio.get("revenue", 0.5)) + tilt.get(d, 0)
        rev = max(0, min(base, rev))
        if base >= 2:                       # 두 편 이상 쓰는 날은 양쪽 다 최소 1편
            rev = max(1, min(base - 1, rev))
        out[d] = {"label": seed["label"], "revenue": rev, "evergreen": base - rev}
    return out


def build(cfg=None, per_day=5):
    hist = _load("history.json")
    ins = _load("insights.json")
    sc = ins.get("search_console") or {}
    buckets, matched = score_articles(hist, sc)
    learned = plan_from(buckets)

    if learned:
        status, ratio = "ok", learned["intent_ratio"]
        cat_w = learned["category_weights"]
        verdict = ("실측 데이터로 조정했습니다. "
                   + " · ".join(f"{k} {int(v*100)}%" for k, v in ratio.items()))
    else:
        status = "no_data" if matched == 0 else "partial"
        ratio = {"revenue": 0.6, "evergreen": 0.4}
        cat_w = {}
        verdict = ("아직 성과 데이터가 없어 기본 계획으로 운영합니다. "
                   "발행·색인이 쌓이면 자동으로 실측 기반으로 바뀝니다."
                   if status == "no_data" else
                   f"실적이 붙은 글이 {matched}편뿐이라 판단을 보류하고 기본 계획을 유지합니다.")

    winners = [q["query"] for q in sorted(sc.get("queries", []),
               key=lambda x: -x.get("clicks", 0))[:10] if q.get("clicks", 0) > 0]

    # 노출은 되는데 클릭이 없는 검색어 = 제목이 약한 것 → 제목 재작성 후보
    weak = [q["query"] for q in sc.get("queries", [])
            if q.get("impressions", 0) >= 50 and q.get("clicks", 0) == 0][:10]

    actions = []
    if status == "no_data":
        actions.append("애드센스 승인 후 발행을 시작하면 다음 주부터 실측 학습이 시작됩니다.")
    if weak:
        actions.append(f"노출은 있는데 클릭이 0인 검색어 {len(weak)}건 — 해당 글 제목을 다시 쓰세요.")
    if learned and ratio.get("revenue", 0) >= 0.7:
        actions.append("수익형 비중이 높습니다. 누적형을 최소 20%는 유지해 트래픽 기반을 지키세요.")

    out = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "next_review": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "data_status": status,
        "verdict": verdict,
        "matched_posts": matched,
        "intent_ratio": ratio,
        "category_weights": cat_w,
        "weekday_plan": weekday_plan(ratio, per_day),
        "winners": winners,
        "weak_queries": weak,
        "buckets": sorted(buckets.values(), key=lambda b: -b["value_per_post"])[:12],
        "actions": actions,
        "note": "글별 수익은 애드센스 API로 조회할 수 없어 '클릭 × 의도별 RPM 배수'로 추정한 값입니다.",
    }
    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[전략] {status} · {verdict}")
    print(f"[전략] 의도 비율 {ratio} · 요일 계획 저장 → {OUT}")
    return out


def load_plan():
    """main.py가 매일 읽는다. 파일이 없으면 기본 계획을 돌려준다."""
    s = _load("strategy.json")
    if not s:
        return {"data_status": "no_data",
                "intent_ratio": {"revenue": 0.6, "evergreen": 0.4},
                "weekday_plan": weekday_plan({"revenue": 0.6, "evergreen": 0.4}),
                "category_weights": {}, "winners": []}
    return s


def today_intents(plan=None, today=None):
    """오늘 써야 할 의도별 편수. 예: {'revenue': 4, 'evergreen': 1}"""
    p = plan or load_plan()
    d = str((today or datetime.now()).weekday())
    wd = (p.get("weekday_plan") or {}).get(d) or {"revenue": 3, "evergreen": 2}
    return {"revenue": int(wd.get("revenue", 0)), "evergreen": int(wd.get("evergreen", 0))}


if __name__ == "__main__":
    build()
