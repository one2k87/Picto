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
    if changed:
        json.dump(cfg, open("config.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
else:
    print("data/site_categories.json 없음 — 시크릿/기본값 사용")
