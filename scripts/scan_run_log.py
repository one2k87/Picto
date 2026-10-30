# -*- coding: utf-8 -*-
"""실행 로그에서 '조용히 죽은 단계'를 찾아 dashboard/data/run_errors.json 에 적는다.

워크플로 토큰으로는 GitHub 로그 API 를 못 읽는다(2026-10-08 실측 404).
그래서 run_step.sh 가 남긴 공용 로그를 그 자리에서 읽는다. 작동 점검은 이 파일만 본다.
"""
import json
import os
import re
import sys

OUT = os.path.join("dashboard", "data", "run_errors.json")
# 2026-10-30: 열흘을 통째로 놓친 뒤 추가. 10/23~10/30 매일 실행이 LLM 결제
# 문제로 죽었는데(429 prepayment credits are depleted) run_errors 는 계속
# "예외 흔적 없음"이었다. 파이썬 예외가 아니라 **정상 종료 경로의 치명적
# 메시지**였기 때문이다. 결제·한도 차단은 예외보다 더 자주 파이프라인을
# 멈추게 하는데 패턴에 없었다.
PAT = re.compile(r"Traceback \(most recent call last\)|ModuleNotFoundError|ImportError"
                 r"|^\w*Error: |^::error"
                 r"|\[치명적"
                 r"|prepayment credits|credits are depleted|quota exceeded"
                 r"|RESOURCE_EXHAUSTED|PERMISSION_DENIED")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/picto-run.log")
    rows, step = [], "(시작 전)"
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except Exception as e:
        lines = []
        rows.append({"step": "(로그 없음)", "line": str(e)[:100]})
    seen = set()
    for ln in lines:
        m = re.match(r"=== STEP (.+?) (?:rc=(\d+) )?===$", ln.strip())
        if m:
            if m.group(2) and m.group(2) != "0":
                key = ("rc", m.group(1))
                if key not in seen:
                    seen.add(key)
                    rows.append({"step": m.group(1), "line": f"종료 코드 {m.group(2)}"})
            else:
                step = m.group(1)
            continue
        if PAT.search(ln.strip()):
            key = (step, ln.strip()[:80])
            if key not in seen:
                seen.add(key)
                rows.append({"step": step, "line": ln.strip()[:140]})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"at": __import__("datetime").datetime.now().isoformat()[:19],
               "log_lines": len(lines), "errors": rows},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[run_errors] 로그 {len(lines)}줄 · 흔적 {len(rows)}건")
    for r in rows[:10]:
        print(f"  · [{r['step']}] {r['line']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
