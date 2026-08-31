"""data/site_categories.json이 있으면 config.json의 categories를 그 파일로 교체한다.
우선순위: 수동실행 입력(categories) > 이 파일 > CATEGORIES_JSON 시크릿.
(입력이 있을 때는 워크플로가 이 스크립트를 건너뛴다)"""
import json, os
P = "data/site_categories.json"
if os.path.exists(P):
    site = json.load(open(P, encoding="utf-8"))
    cfg = json.load(open("config.json", encoding="utf-8"))
    changed = False
    if site.get("categories"):
        cfg["categories"] = site["categories"]; changed = True
        print("저장소 카테고리 적용:", [c["name"] for c in site["categories"]])
    if site.get("images_provider"):
        cfg.setdefault("images", {})["provider"] = site["images_provider"]; changed = True
        print("이미지 provider 적용:", site["images_provider"])
    # 글 비율(mix) — 수익탭 결산이 기록한 트렌드/스테디/에버그린 비율로
    # '오늘의 주제 유형'을 날짜 시드로 뽑는다(하루 단위라 비율은 주 단위로 수렴).
    mix = site.get("mix")
    if mix:
        import datetime, random
        rng = random.Random(datetime.date.today().toordinal())
        roll = rng.uniform(0, 100)
        t, sd = float(mix.get("trend", 20)), float(mix.get("steady", 30))
        if roll < t:
            kind, hint = "season", "이번 달 기준의 시점성 주제(트렌드형). 확인 시점을 본문에 명시"
        elif roll < t + sd:
            kind, hint = "long", "계절·시기마다 반복 수요가 도는 주제(스테디형: 결로·장마철 습기·겨울 한파 대비 등)"
        else:
            kind, hint = "long", "시점과 무관하게 늘 검색되는 원리·방법 주제(에버그린형)"
        for c in cfg.get("categories", []):
            cnt = c.get("counts") or {}
            n = (cnt.get("long_single", 0) + cnt.get("season_single", 0)) or 1
            c["counts"] = {"long_series": 0, "season_series": 0,
                           "long_single": n if kind == "long" else 0,
                           "season_single": n if kind == "season" else 0}
            c["desc"] = (c.get("desc", "") + f" [오늘의 주제 유형 지시: {hint}]")
        changed = True
        print(f"글 비율 적용(트{t:.0f}/스{sd:.0f}/에{100-t-sd:.0f}) → 오늘: {hint[:30]}…")
    if changed:
        json.dump(cfg, open("config.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
else:
    print("data/site_categories.json 없음 — 시크릿/기본값 사용")
