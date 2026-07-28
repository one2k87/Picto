"""
notify.py - 실행 결과/오류를 텔레그램으로 자동 전송(무료).

설정(config.notify 또는 환경변수):
  telegram_token   = @BotFather 로 만든 봇 토큰 (TELEGRAM_TOKEN)
  telegram_chat_id = 내 chat id (TELEGRAM_CHAT_ID, @userinfobot 로 확인)
둘 중 하나라도 없으면 조용히 건너뛴다(다른 기능엔 영향 없음).
"""

import os


def _creds(cfg):
    n = (cfg or {}).get("notify", {}) or {}
    token = n.get("telegram_token") or os.getenv("TELEGRAM_TOKEN")
    chat = n.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID")
    return token, chat


def send(cfg, text):
    """텔레그램 메시지 전송. 성공 True."""
    token, chat = _creds(cfg)
    if not token or not chat:
        return False
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15)
        if r.status_code == 200:
            print("[notify] 텔레그램 전송 완료")
            return True
        print(f"[notify] 텔레그램 응답 {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"[notify] 텔레그램 전송 실패: {e}")
    return False


def run_summary(cfg, stats):
    """실행 요약 메시지 문자열 만들기."""
    icon = "✅" if stats.get("ok") else "⚠️"
    lines = [
        f"{icon} <b>Scripto 실행 리포트</b>",
        f"🕖 {stats.get('at','')}",
        f"📝 생성 {stats.get('articles',0)}편 · 게시 {stats.get('published',0)} · "
        f"초안 {stats.get('draft',0)}",
        f"⛔ 품질보류 {stats.get('held',0)}편 · 실패 {stats.get('failed',0)}",
        f"⏱ 소요 {stats.get('duration_s',0)}초",
    ]
    cost = stats.get("cost") or {}
    if cost:
        lines.append(f"💸 이번 달 예상비용 ₩{cost.get('month_krw',0):,} "
                     f"(호출 {cost.get('llm_calls',0)}회)")
    bad = stats.get("health_bad") or []
    if bad:
        lines.append("🔴 점검필요: " + ", ".join(bad))
    return "\n".join(lines)
