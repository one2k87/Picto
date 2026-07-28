"""
smoke_test.py - 배포 전 '핵심 함수가 안 깨졌는지' 빠르게 확인(무료·오프라인).
네트워크·API 키 없이 순수 로직만 검증한다. 실패하면 종료코드 1.
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

fails = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        fails.append(name)


# 1) config.json 이 유효한 JSON 이고 키가 자리표시자인지(실키 유출 방지)
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    cfg = json.load(f)
check("config.json 유효", isinstance(cfg, dict))
api = str(cfg.get("llm", {}).get("api_key", ""))
check("config.json 에 실제 키 없음(자리표시자)", ("여기에" in api) or api == "")

# 2) 금지·기업 주제 필터
import topics
check("전쟁 주제 차단", topics.is_blocked("우크라이나 전쟁 근황"))
check("도박 주제 차단", topics.is_blocked("카지노 후기"))
check("일반 주제 통과", not topics.is_blocked("무직자 대출 조건"))
check("기업 주제 차단", topics.is_corporate("국내 클라우드 시장 규모 분석"))
check("개인 주제 통과", not topics.is_corporate("구글 포토 용량 늘리는 법"))

# 3) 품질 게이트
import quality
good = {"html": "<h2>a</h2><h2>b</h2><h2>c</h2>" + ("가나다라 " * 200), "focus_keyword": "대출"}
bad = {"html": "<p>짧다</p>", "focus_keyword": "대출"}
check("좋은 글 통과", quality.check(good, [], cfg.get("safety", {}))[0])
check("나쁜 글 보류", not quality.check(bad, [], cfg.get("safety", {}))[0])

# 4) 최신성 휴리스틱
import accuracy
iss, stale = accuracy.heuristic({"title": "2019년 최신 대출", "html": "<p>올해 기준입니다.</p>"})
check("옛 연도 감지", stale)

# 5) 무료 코드 썸네일 생성(Pillow)
import images
data = images._thumbnail("무직자 비상금 대출 조건 총정리", "금융", "600x600")
check("코드 썸네일 생성", bool(data) and len(data) > 500)

print()
if fails:
    print(f"❌ 스모크 테스트 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 스모크 테스트 전체 통과")
