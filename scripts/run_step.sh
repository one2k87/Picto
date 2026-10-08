#!/usr/bin/env bash
# 워크플로 단계를 감싸 실행하고, 출력을 공용 로그에 남긴다 (2026-10-08 신설).
#
# 왜: 많은 단계가 '|| true' 로 감싸여 있어 스크립트가 죽어도 실행은 초록색으로 끝난다.
#     실제로 scripts/ping_new_posts.py 가 sys.path 누락으로 **매일** 죽고 있었는데
#     몇 주 동안 아무에게도 보이지 않았다. 실행 로그를 GitHub API 로 내려받아
#     검사하려 했지만 워크플로 토큰으로는 로그 받기가 막힌다(실측 404).
#     그래서 파이프라인이 **스스로** 증거를 남긴다.
#
# 사용: bash scripts/run_step.sh <이름> <명령...>
#       항상 0 으로 끝난다('|| true' 와 같은 성격). 실패는 로그에 남는다.
set -o pipefail
NAME="$1"; shift
LOG="${PICTO_RUN_LOG:-$HOME/picto-run.log}"
{ echo "=== STEP $NAME ==="; } >> "$LOG"
"$@" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
echo "=== STEP $NAME rc=$rc ===" >> "$LOG"
exit 0
