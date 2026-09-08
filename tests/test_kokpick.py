# -*- coding: utf-8 -*-
"""kokpick(캐스토 6-C 구조화 블록) 검증. 실행: python3 tests/test_kokpick.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kokpick  # noqa: E402

fails = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        fails.append(name)
        print(f"  ✗ {name} {extra}")


print("[1] 키는 절대 생략되지 않는다(캐스토가 결측을 감지하려면 키가 있어야 함)")
d = kokpick.build({})
check("최상위 키 9개", sorted(d.keys()) == sorted(kokpick.SCHEMA.keys()), sorted(d.keys()))
check("maintenance 하위 키 3개",
      sorted(d["maintenance"].keys()) == ["consumable_url", "cost_per_year", "cycle"])

print("[2] 근거 없는 alt_uses는 버린다(안전 규칙)")
d = kokpick.build({"kokpick": {"alt_uses": ["빨래 건조기로 써도 됩니다"], "alt_uses_source": ""}})
check("source 없으면 alt_uses 비움", d["alt_uses"] == [] and d["alt_uses_source"] == "")
d = kokpick.build({"kokpick": {"alt_uses": ["신발 건조"], "alt_uses_source": "본문 3번째 소제목 실사용기"}})
check("source 있으면 유지", d["alt_uses"] == ["신발 건조"])

print("[3] 대장(products.json) 값이 LLM 값보다 우선한다")
prod = {"key": "음식물처리기", "name": "음식물처리기", "price_band": "40만원대"}
d = kokpick.build({"kokpick": {"price_band": "10만원대"}}, prod, "https://link.coupang.com/x?subid=a")
check("product는 대장 이름", d["product"] == "음식물처리기")
check("price_band는 대장 우선", d["price_band"] == "40만원대", d["price_band"])
check("coupang_url 주입", d["coupang_url"].startswith("https://link.coupang.com/"))

print("[4] 주석이 깨지지 않게 연속 하이픈을 없앤다(KSES 방어)")
d = kokpick.build({"kokpick": {"size_install": "폭 30cm -- 여유 5cm", "cautions": ["뼈 투입 금지---"]}})
check("문자열에서 -- 제거", "--" not in d["size_install"], d["size_install"])
check("리스트에서도 제거", "--" not in d["cautions"][0], d["cautions"][0])
html = kokpick.block_html(d)
check("블록 전체에 -- 없음(마커 제외)",
      "--" not in html.replace(kokpick.MARK_OPEN, "").replace(kokpick.MARK_CLOSE, ""))

print("[5] 왕복: 만들고 → 본문에 넣고 → 다시 읽는다")
d = kokpick.build({"kokpick": {"condition_branch": ["4인 이상이면 이득"], "cautions": ["뼈 투입 금지"]}},
                  {"key": "음식물처리기", "name": "음식물처리기"})
body = "<p>본문</p><h2>소제목</h2><p>내용</p>"
full = body + kokpick.block_html(d)
back = kokpick.parse_block(full)
check("파싱 성공", back is not None)
check("값 동일", back == d, json.dumps(back, ensure_ascii=False)[:120])
check("본문 앞부분 보존", full.startswith(body))

print("[6] 두 번 넣어도 블록은 하나만 남는다(소급 재실행 안전)")
again = kokpick.strip_block(full) + kokpick.block_html(d)
check("블록 1개", again.count(kokpick.MARK_OPEN) == 1, again.count(kokpick.MARK_OPEN))
check("재파싱 동일", kokpick.parse_block(again) == d)

print("[7] 결측 판정")
check("빈 블록은 is_empty", kokpick.is_empty(kokpick.build({}, {"key": "제습기", "name": "제습기"})))
check("근거 있으면 not empty", not kokpick.is_empty(d))

print("[8] 메타용 JSON은 한 줄·한글 그대로")
j = kokpick.to_json(d)
check("줄바꿈 없음", "\n" not in j)
check("한글 이스케이프 안 됨", "음식물처리기" in j)
check("되읽기 동일", json.loads(j) == d)

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
