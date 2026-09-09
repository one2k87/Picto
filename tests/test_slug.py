# -*- coding: utf-8 -*-
"""슬러그 생성 — 한글 제목에서 주소가 망가지던 버그 (2026-09-09).

배경: slugify()가 [a-z0-9]만 남겨 한글 제목이 통째로 지워졌다.
      그래서 픽담에 slug이 '3-2'·'post'·'post-2'인 글이 실제로 생겼다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generator import _slug_core, make_slug, romanize_ko, slugify

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("  ✗", name)


# ① 예전에 나왔던 쓰레기 슬러그는 전부 거부돼야 한다
for bad in ("3-2", "2026-9", "3mm-1mm", "3-5", "", "---", "1-2-3"):
    check(f"쓰레기 거부 {bad!r}", _slug_core(bad) == "")

# ② 정상 영문은 그대로 통과
check("영문 통과", _slug_core("bidet-self-installation-guide-2026")
      == "bidet-self-installation-guide-2026")

# ③ 한글 제목도 읽을 수 있는 주소가 나온다 — 'post'로 떨어지지 않는다
KO = "현관문 문풍지, 틈새 3mm 이상이라면 모헤어, 1mm 미만이라면 실리콘 틈막이"
s = make_slug("", KO, "현관문 문풍지 방풍")
check("한글 제목 → 로마자", s.startswith("hyeongwanmun-munpungji"))
check("'post'로 안 떨어짐", not s.startswith("post-"))

# ④ LLM이 준 영문 슬러그가 최우선
check("LLM 슬러그 우선",
      make_slug("bidet-self-installation-guide-2026", KO, "비데") ==
      "bidet-self-installation-guide-2026")

# ⑤ LLM이 쓰레기를 줘도 제목으로 폴백
check("LLM 쓰레기 → 폴백", make_slug("3-2", KO, "문풍지").startswith("hyeongwanmun"))

# ⑥ 아무 근거가 없으면 날짜+해시(그래도 유일하고 'post-2'가 아니다)
last = make_slug("", "", "")
check("최후 폴백 형식", re.fullmatch(r"post-\d{8}-[0-9a-f]{6}", last) is not None)

# ⑦ 길이·형식 안전장치
for t in (KO, "음식물처리기 보상 판매, 렌탈 약정 18개월 미만이라면 위약금 30%",
          "비데 자가설치, 생각보다 어려울까? 2026년 9월 기준"):
    s = make_slug("", t, "")
    check(f"60자 이하 ({len(s)})", len(s) <= 60)
    check("허용 문자만", re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) is not None)
    check("낱말 중간 절단 없음", not s.endswith("-"))

# ⑧ 서로 다른 글은 서로 다른 슬러그
a = make_slug("", "정수기 필터 교체 주기", "정수기 필터")
b = make_slug("", "제습기 20L 고르는 법", "제습기")
check("고유성", a != b)

# ⑨ 로마자 변환 자체
check("로마자 한글", romanize_ko("문풍지") == "munpungji")
check("로마자 비한글 보존", romanize_ko("20L 제습기").startswith("20L "))

# ⑩ 옛 이름(slugify) 호환 — 이제 실패 시 'post'가 아니라 빈 문자열
check("slugify 호환", slugify("3-2") == "")

print(f"test_slug: {ok} pass / {fail} fail")
sys.exit(1 if fail else 0)
