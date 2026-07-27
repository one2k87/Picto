"""
main.py - 카테고리 집중 애드센스 수익형 파이프라인 (한국어 전용).

하루 흐름:
1) 히스토리(과거 발행 제목) 로드 → 중복 방지용
2) 선택한 고단가 카테고리 안에서 주제 생성
     long   = 저경쟁 롱테일 (상위노출 쉬움)
     season = 시즌/이벤트 선점 (2~4주 미리)
3) (옵션) 네이버 검색량 실측으로 저경쟁 후보 선별
4) 각 주제로 수익형 글 생성 (이전 글로 내부링크 → 카테고리 클러스터)
5) (옵션) WordPress 게시 / 복붙 HTML 저장
6) 히스토리 갱신 + 구글시트 로깅 + 대시보드 데이터 저장

실행: python main.py   설정: config.json
"""

import os
import json
import html as html_mod
from datetime import datetime

import random
import topics
import metrics
import images
import quality
import accuracy
from llm import chat
from generator import generate_article, generate_series
from publisher import publish_to_wordpress, upload_media, add_update_banner, submit_indexnow
from sheets import log_rows

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "output")
DASH_DATA = os.path.join(BASE, "dashboard", "data")
HISTORY = os.path.join(DASH_DATA, "history.json")


def load_config():
    path = os.path.join(BASE, "config.json")
    if not os.path.exists(path):
        raise SystemExit("config.json 이 없습니다. config.example.json 을 복사해 만드세요.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_history():
    if os.path.exists(HISTORY):
        try:
            with open(HISTORY, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"articles": []}   # [{title, slug, url, kind, keyword, date}]


def save_history(hist):
    os.makedirs(DASH_DATA, exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


def get_categories(cfg):
    """config에서 카테고리 목록을 만든다(구버전 site.category 호환)."""
    if cfg.get("categories"):
        return [{"name": c.get("name", ""), "desc": c.get("desc", ""),
                 "wp_category": c.get("wp_category", c.get("name", "")),
                 "wp_slug": c.get("wp_slug", "")} for c in cfg["categories"]]
    site = cfg.get("site", {})
    return [{"name": site.get("category", ""), "desc": site.get("category_desc", ""),
             "wp_category": site.get("category", ""), "wp_slug": ""}]


def collect_lane(cfg, cat, lane, n_slots, exclude):
    """
    한 카테고리(cat) 안에서 한 갈래(lane)의 주제를 n_slots개 확보한다.
      1) 후보 생성 → 2) 저경쟁/시즌 지속 판별 → 3) long은 네이버 실측 선별
    """
    mcfg = cfg.get("metrics", {}) or {}
    measured = mcfg.get("provider", "none") not in ("none", None)
    pool = max(3, n_slots + 2)

    raw = chat(topics.build_topic_prompt(cat["name"], cat["desc"], lane, pool, exclude=exclude),
               cfg["llm"], max_tokens=900, temperature=0.9)
    cand = topics.parse_topics(raw, pool)
    # 금지·위험 주제 필터(성인/도박/과장의료/저작권/전쟁 등 자동 제외)
    extra_block = (cfg.get("safety", {}) or {}).get("blocklist_extra", [])
    before = len(cand)
    cand = [c for c in cand if not topics.is_blocked(c["keyword"], extra_block)]
    if len(cand) < before:
        print(f"  · 금지·위험 주제 {before - len(cand)}개 제외")
    # 일반인이 클릭 안 하는 기업·전문가·B2B 주제 제거(안전망)
    before = len(cand)
    cand = [c for c in cand if not topics.is_corporate(c["keyword"])]
    if len(cand) < before:
        print(f"  · 기업·전문가용 주제 {before - len(cand)}개 제외(일반인 관점 유지)")

    # 지속 판별(저경쟁 vs 시즌). 속도 위해 perf.classify=false 면 건너뜀
    # (이미 lane별 프롬프트로 생성했으므로 끄더라도 분류 자체는 유지됨)
    if cfg.get("perf", {}).get("classify", True):
        print(f"  · 주제 판별(저경쟁/시즌) 중…")
        topics.classify_topics(cand, cat["name"], chat, cfg["llm"])
        match = [c for c in cand if c.get("lane_ai") == lane]
        ordered = match + [c for c in cand if c.get("lane_ai") != lane]  # 부족하면 나머지로 보충
    else:
        ordered = cand

    # 3) long은 네이버 실측 + '비율(traffic_ratio)'로 선별
    #    traffic_ratio: 검색량 우선의 비율(0~100). 0=상위노출만, 100=검색량만, 30=상위노출 위주+검색량 약간
    ratio = cfg.get("traffic_ratio")
    if ratio is None:  # 구버전 keyword_strategy 호환
        ratio = {"rankable": 0, "traffic": 100, "balanced": 30}.get(
            (cfg.get("keyword_strategy") or "balanced").lower(), 30)
    ratio = max(0, min(100, int(ratio)))
    traffic_set = set()

    if lane == "long" and measured:
        print(f"  · 저경쟁 후보 검색량 측정(네이버)… (검색량 비율={ratio}%)")
        metrics.enrich(ordered, mcfg, geo="KR", want_steadiness=True)
        floor = mcfg.get("low_volume_floor", 1000)
        comp_rank = {"낮음": 0, "중간": 1, "높음": 2, "": 1}

        def v(x):
            return x.get("volume") if x.get("volume") is not None else (x.get("interest") or 0)

        above = [x for x in ordered if (x.get("volume") is None or v(x) >= floor)] or ordered
        n_traffic = round(n_slots * ratio / 100.0)          # 검색량 우선으로 뽑을 개수
        n_rank = n_slots - n_traffic                        # 상위노출(경쟁낮음) 우선 개수
        rank_sorted = sorted(above, key=lambda x: (comp_rank.get(str(x.get("competition", "")), 1), -v(x)))
        traffic_sorted = sorted(above, key=lambda x: -v(x))

        picked = []
        for x in rank_sorted:                               # 상위노출 몫 먼저
            if len(picked) >= n_rank:
                break
            if x not in picked:
                picked.append(x)
        for x in traffic_sorted:                            # 검색량 몫
            if len([p for p in picked if id(p) in traffic_set]) >= n_traffic:
                break
            if x not in picked:
                picked.append(x); traffic_set.add(id(x))
        for x in rank_sorted + traffic_sorted:              # 모자라면 채우기
            if len(picked) >= n_slots:
                break
            if x not in picked:
                picked.append(x)
        print("  · 선별(검색량/경쟁):", [(p["keyword"], p.get("volume"), p.get("competition")) for p in picked[:n_slots]])
        ordered = picked

    sel = ordered[:n_slots]
    # 상위노출 강화 대상 표시: 검색량 몫으로 뽑혔거나 경쟁도 중간/높음이면 강화 글로 작성
    for kw in sel:
        comp = str(kw.get("competition", ""))
        kw["competitive"] = (id(kw) in traffic_set) or (comp in ("중간", "높음")) or (ratio >= 60 and not measured)
    return sel


def make_image_resolver(cfg, auto_publish, category="", budget=None):
    """[[IMG:설명]] → 실제 이미지 자동 생성 후 <figure> 반환하는 콜백(카테고리별).
    budget={"used":n,"max":N} 로 실행 1회당 이미지 개수를 제한(비용 상한)."""
    imgcfg = dict(cfg.get("images", {}) or {})
    if imgcfg.get("provider") in ("gemini", "imagen", "google") and not imgcfg.get("api_key"):
        imgcfg["api_key"] = cfg["llm"].get("api_key", "")   # Gemini 키 재사용
    wp_cfg = cfg.get("wordpress", {})
    out = os.path.join(OUT_DIR, "images")

    if imgcfg.get("provider", "none") in ("none", None, ""):
        return None

    def resolver(desc, idx):
        if budget is not None and budget.get("used", 0) >= budget.get("max", 10 ** 9):
            return None                      # 비용 상한 초과 → 자리표시로 대체
        path = images.generate_image(desc, imgcfg, out, idx, category=category)
        if not path:
            return None
        if budget is not None:
            budget["used"] = budget.get("used", 0) + 1
        src = None
        if auto_publish and wp_cfg.get("enabled"):
            src = upload_media(path, wp_cfg, alt=desc)
        if not src:
            src = images.to_data_uri(path)     # 미게시/업로드 실패 시 인라인
        return images.figure_html(src, desc)

    return resolver


def save_copy_html(article):
    os.makedirs(OUT_DIR, exist_ok=True)
    safe = "".join(c for c in article["keyword"][:40] if c.isalnum() or c in " _-").strip()
    cat = "".join(c for c in article.get("category", "")[:10] if c.isalnum())
    fname = f"{datetime.now():%Y%m%d}_{cat}_{article['kind']}_{safe}.html"
    path = os.path.join(OUT_DIR, fname)
    doc = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
           f'<title>{html_mod.escape(article["title"])}</title>'
           f'<meta name="description" content="{html_mod.escape(article["meta"])}"></head>'
           f'<body>{article["html"]}</body></html>')
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path


def _plan_slots(cfg):
    """각 갈래의 슬롯을 (series/single)로 계획. 시리즈=1슬롯(여러 편 생성)."""
    c = cfg.get("counts", {})
    smin = c.get("series_min_parts", 2)
    smax = c.get("series_max_parts", 3)

    def parts():
        return random.randint(smin, smax)

    slots = []
    for _ in range(c.get("long_series", 2)):
        slots.append(("long", "series", parts()))
    for _ in range(c.get("long_single", 2)):
        slots.append(("long", "single", 1))
    for _ in range(c.get("season_series", 1)):
        slots.append(("season", "series", parts()))
    for _ in range(c.get("season_single", 1)):
        slots.append(("season", "single", 1))
    return slots


def _run_category(cfg, cat, hist, auto_publish, img_budget=None):
    """한 카테고리에 대해 슬롯 계획대로 글을 생성해 리스트로 반환."""
    name = cat["name"]
    blog_url = cfg.get("blog_url", "") or cfg.get("site", {}).get("blog_url", "")
    insert_ads = cfg.get("ads", {}).get("insert_slots", True)
    author = cfg.get("author") or "편집부"
    wp_cfg = cfg.get("wordpress", {})
    resolver = make_image_resolver(cfg, auto_publish, name, img_budget)

    # 이 카테고리의 과거 글만으로 중복방지 + 내부링크
    cat_hist = [a for a in hist["articles"] if a.get("category") == name]
    exclude = [a["title"] for a in cat_hist] + [a.get("keyword", "") for a in cat_hist]
    related_pool = list(reversed(cat_hist))[:6]

    print(f"\n########## [{name}] ##########")
    slots = _plan_slots(cfg)
    need = {"long": sum(1 for s in slots if s[0] == "long"),
            "season": sum(1 for s in slots if s[0] == "season")}
    topic_q = {}
    for lane in ("long", "season"):
        if need[lane] <= 0:
            continue
        label = "저경쟁 롱테일" if lane == "long" else "시즌 선점"
        print(f"[{label}] 슬롯 {need[lane]}개용 주제 확보…")
        got = collect_lane(cfg, cat, lane, need[lane], exclude)
        topic_q[lane] = got
        print(f"  · 주제:", [t["keyword"] for t in got])
        exclude += [t["keyword"] for t in got]

    # 슬롯 → 작업 목록 구성(주제 배정). 내부링크는 과거 글 기준(병렬 안전).
    related = [{"title": r["title"], "slug": r.get("slug", ""),
                "url": r.get("post_url") or r.get("url", "")} for r in related_pool[:3]]
    jobs = []
    slot_count = {"long": 0, "season": 0}
    for lane, mode, n_parts in slots:
        q = topic_q.get(lane, [])
        if not q:
            continue
        kw = q.pop(0)
        if not kw["keyword"]:
            continue
        slot_count[lane] += 1
        jobs.append((lane, mode, n_parts, kw))

    def gen_job(job):
        lane, mode, n_parts, kw = job
        comp = bool(kw.get("competitive"))
        try:
            if mode == "series":
                print(f"-> [시리즈 {n_parts}편][{lane}]{'[상위노출강화]' if comp else ''} {kw['keyword']}")
                arts = generate_series(kw["keyword"], lane, n_parts, cfg["llm"],
                                       category=name, related=related, blog_url=blog_url,
                                       insert_ads=insert_ads, image_resolver=resolver, author=author,
                                       competitive=comp)
            else:
                print(f"-> [단일][{lane}]{'[상위노출강화]' if comp else ''} {kw['keyword']}")
                arts = generate_article(kw["keyword"], lane, cfg["llm"],
                                        category=name, related=related, blog_url=blog_url,
                                        insert_ads=insert_ads, image_resolver=resolver, author=author,
                                        competitive=comp)
        except Exception as e:
            print(f"[오류] '{kw['keyword']}' 글 생성 실패(건너뜀): {e}")
            return []
        for a in arts:
            a["category"] = name
            a["wp_category"] = cat.get("wp_category", name)
            a["wp_category_slug"] = cat.get("wp_slug", "")
            a["volume"] = kw.get("volume")
            a["competition"] = kw.get("competition", "")
            a["steadiness"] = kw.get("steadiness")
            a["interest"] = kw.get("interest")
            a["lane_reason"] = kw.get("lane_reason", "")
        return arts

    # 생성은 병렬(이미지·글 대기시간 겹치기), 게시/저장은 순차(WP 안정)
    workers = max(1, int(cfg.get("perf", {}).get("workers", 3)))
    generated = []
    if workers > 1 and len(jobs) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for arts in ex.map(gen_job, jobs):
                generated += arts
    else:
        for job in jobs:
            generated += gen_job(job)

    # 품질 게이트: 분량·구조·키워드 스터핑·중복 검사 (같은 실행 글끼리 유사도 비교)
    safety = cfg.get("safety", {}) or {}
    force_draft = safety.get("force_draft", True)
    for i, a in enumerate(generated):
        others = [b["html"] for j, b in enumerate(generated) if j != i]
        ok, reason = quality.check(a, others, safety)
        a["quality"] = "통과" if ok else "보류"
        a["quality_reason"] = reason
        # 최신성·정확성 검증(연도/진행상태/불확실 주장) → 문제 있으면 '글을 다시 씀'
        try:
            hold, summ = accuracy.check(a, chat, cfg.get("llm", {}), safety)
            a["accuracy_summary"] = summ
            # 점검에서 끝내지 않고 실제 재작성(자동). safety.auto_revise=false면 표시만.
            auto_revise = safety.get("auto_revise", True) and str(safety.get("verify_accuracy", "flag")).lower() != "off"
            if auto_revise and (a.get("accuracy") in ("warn", "stale") or a.get("accuracy_issues")):
                if accuracy.revise(a, chat, cfg.get("llm", {})):
                    print(f"  · 최신성 재작성 완료: {a['keyword']}")
                    # 재작성 후 다시 점검해 상태 갱신
                    hold, summ = accuracy.check(a, chat, cfg.get("llm", {}), safety)
                    a["accuracy_summary"] = summ
                    # 재작성으로 분량 등이 바뀌었을 수 있어 품질도 재확인
                    others2 = [b["html"] for b in generated if b is not a]
                    ok2, reason2 = quality.check(a, others2, safety)
                    a["quality"] = "통과" if ok2 else "보류"
                    a["quality_reason"] = reason2
            if hold and a["quality"] == "통과":
                a["quality"] = "보류"
                a["quality_reason"] = (a.get("quality_reason") or "") + ("; " if a.get("quality_reason") else "") + "최신성 문제(" + summ + ")"
        except Exception as e:
            print(f"  · 정확도 검증/재작성 건너뜀: {e}")

    out = []
    for a in generated:
        if auto_publish and a["quality"] == "통과":
            # 초안 강제: 사람이 검토 후 발행(대량 자동 발행 방지)
            wp = dict(wp_cfg, status="draft") if force_draft else wp_cfg
            url = publish_to_wordpress(a, wp)
            a["status"] = ("초안저장됨" if force_draft else "게시됨") if url else "게시실패"
            a["post_url"] = url or ""
        elif auto_publish and a["quality"] == "보류":
            a["status"] = "품질보류"      # 발행 안 함(검토 필요)
            a["post_url"] = ""
            print(f"  · 품질보류(발행 제외): {a['keyword']} — {a['quality_reason']}")
        else:
            a["status"] = "복붙대기"
            a["post_url"] = ""
        a["copy_file"] = save_copy_html(a)
        out.append(a)
    print(f"  → [{name}] 슬롯 {sum(slot_count.values())}건 · 글 {len(out)}편"
          f"(품질보류 {sum(1 for a in out if a.get('quality')=='보류')}편)")
    return out


def _kw_set(s):
    import re as _re
    return set(w for w in _re.findall(r"[가-힣A-Za-z0-9]+", str(s or "")) if len(w) > 1)


def _relink_old_posts(new_articles, hist, wp_cfg):
    """이번에 새로 쓴 글과 '같은 주제'인 과거 발행글을 찾아, 옛 글 상단에 최신글 링크 배너를 단다."""
    olds = [h for h in hist.get("articles", []) if h.get("post_id") and h.get("url")]
    if not olds:
        return
    done = 0
    for a in new_articles:
        if not a.get("post_url") or not a.get("post_id"):
            continue
        ka = _kw_set(a.get("keyword", ""))
        if not ka:
            continue
        for h in olds:
            if h.get("category") != a.get("category"):
                continue
            kb = _kw_set(h.get("keyword", ""))
            if not kb:
                continue
            sim = len(ka & kb) / len(ka | kb)
            # 주제가 충분히 겹치고(70%+), 서로 다른 글일 때만
            if sim >= 0.7 and h.get("post_id") != a.get("post_id"):
                if add_update_banner(wp_cfg, h["post_id"], a["post_url"], a["title"]):
                    done += 1
                break
    if done:
        print(f"  · 예전글 {done}건에 최신글 링크 배너 추가")


def run():
    cfg = load_config()
    wp_cfg = cfg.get("wordpress", {})
    auto_publish = wp_cfg.get("enabled", False)
    cats = get_categories(cfg)

    print(f"=== {datetime.now():%Y-%m-%d %H:%M} 수익형 글 생성 시작 · 카테고리 {len(cats)}개 ===")

    # --- LLM 사전 점검: 키/모델이 유효한지 먼저 확인(문제 시 명확히 실패) ---
    lcfg = cfg.get("llm", {})
    if not lcfg.get("api_key") or "여기에" in str(lcfg.get("api_key")):
        raise SystemExit("[치명적] LLM api_key 가 비어 있습니다. GitHub 시크릿 LLM_API_KEY 를 확인하세요.")
    try:
        t = chat("한 단어로 'OK' 만 답하세요.", lcfg, max_tokens=8, temperature=0)
        print(f"[preflight] LLM OK (provider={lcfg.get('provider')}, model={lcfg.get('model')}) → {str(t)[:30]!r}")
    except Exception as e:
        print("=" * 64)
        print("[치명적] LLM 호출 실패 — 키 또는 모델명을 확인하세요.")
        print(f"  provider={lcfg.get('provider')}  model={lcfg.get('model')}")
        print(f"  오류: {e}")
        print("  힌트: 모델을 'gemini-2.5-flash' → 'gemini-1.5-flash' 로 바꿔보거나,")
        print("        LLM_API_KEY 가 올바른 Gemini API 키(AIza...)인지 확인하세요.")
        print("=" * 64)
        raise SystemExit(1)

    hist = load_history()

    # 이미지 비용 상한: 실행 1회당 최대 개수(카테고리 합산)
    img_budget = {"used": 0, "max": int(cfg.get("images", {}).get("max_per_run", 10 ** 9))}

    all_articles = []
    for cat in cats:
        if not cat["name"]:
            continue
        try:
            all_articles += _run_category(cfg, cat, hist, auto_publish, img_budget)
        except Exception as e:
            import traceback
            print(f"[오류] '{cat['name']}' 카테고리 생성 실패(건너뜀): {e}")
            traceback.print_exc()

    # 예전글 → 최신글 링크: 이번에 발행한 글이 과거 글을 대체하면 옛 글 상단에 배너 추가
    if cfg.get("safety", {}).get("relink_old") and auto_publish:
        _relink_old_posts(all_articles, hist, wp_cfg)

    today = datetime.now().strftime("%Y-%m-%d")
    for a in all_articles:
        hist["articles"].append({
            "title": a["title"], "slug": a.get("slug", ""), "url": a.get("post_url", ""),
            "post_id": a.get("post_id"),
            "kind": a["kind"], "keyword": a["keyword"], "category": a.get("category", ""),
            "date": today, "series_id": a.get("series_id", ""),
        })
    save_history(hist)
    log_rows(all_articles, cfg.get("sheets"))

    # 네이버·빙에 새 글 즉시 등록(IndexNow). 실제 '게시됨'(공개) 글만, 키가 있을 때만.
    inkey = wp_cfg.get("indexnow_key")
    if inkey:
        pub_urls = [a.get("post_url") for a in all_articles
                    if a.get("post_url") and a.get("status") == "게시됨"]
        if pub_urls:
            submit_indexnow(pub_urls, inkey, wp_cfg.get("site_url", ""))
        else:
            print("  · IndexNow: 공개 게시된 글이 없어 건너뜀(초안은 색인 대상 아님)")

    # 카테고리별 집계
    from collections import Counter
    per_cat = Counter(a.get("category", "") for a in all_articles)

    os.makedirs(DASH_DATA, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "categories": [c["name"] for c in cats],
        "auto_publish": auto_publish,
        "per_category": dict(per_cat),
        "total_all": len(hist["articles"]),
        "articles": all_articles,
    }
    for p in (os.path.join(DASH_DATA, f"{today}.json"), os.path.join(DASH_DATA, "latest.json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    n_series = len({a.get("series_id") for a in all_articles if a.get("series_id")})
    print(f"\n=== 완료: 카테고리 {len(cats)}개 · 실제 글 {len(all_articles)}편"
          f"(시리즈 {n_series}개) · 전체 누적 {len(hist['articles'])}편 ===")


if __name__ == "__main__":
    run()
