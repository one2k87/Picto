"""
monitor.py - 운영 안전망(헬스체크 + 사용량/비용 집계)용 초경량 수집기.

- 각 연동(gemini/naver/wordpress/indexnow)이 '성공'하면 mark()로 시각 기록 → 헬스체크.
- LLM/유료 이미지 호출 수를 bump 로 집계 → 비용 추적.
- 메모리에만 쌓고, 실행 끝에 main 이 status.json 으로 병합 저장한다.
스레드에서 호출돼도 안전하도록 단순 정수 증가만 사용(GIL).
"""

from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

_state = {
    "marks": {},        # {"gemini": iso, "naver": iso, ...} 마지막 성공 시각
    "llm_calls": 0,     # 텍스트 생성 호출 수
    "image_paid": 0,    # 유료 이미지 생성 수(비용 발생)
    "image_free": 0,    # 무료 이미지(스톡/썸네일) 수
}


def now_kst():
    return datetime.now(KST).isoformat(timespec="seconds")


def mark(name):
    """연동 성공 기록(헬스체크용)."""
    _state["marks"][name] = now_kst()


def bump_llm(n=1):
    _state["llm_calls"] += n


def bump_image(paid=False, n=1):
    _state["image_paid" if paid else "image_free"] += n


def snapshot():
    return {
        "marks": dict(_state["marks"]),
        "llm_calls": _state["llm_calls"],
        "image_paid": _state["image_paid"],
        "image_free": _state["image_free"],
    }
