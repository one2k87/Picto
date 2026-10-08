# -*- coding: utf-8 -*-
"""워크플로 파일이 전부 파싱되는지 검사한다 (2026-10-08 신설).

왜: 워크플로의 `run: |` 블록 안에 여러 줄 파이썬을 넣었다가 들여쓰기가 YAML
    블록 스칼라를 깨서 daily-blog.yml **전체가 파싱 불가** 상태가 됐다.
    깃허브는 그걸 '실행 실패'로 기록하고 메일을 보낸다 — 35분 동안 푸시 5건이
    전부 실패했고, 그때 발행 크론이 걸렸다면 그날 글은 0편이 됐을 것이다.
    문법 검사는 .py 만 하고 있었다. 워크플로도 코드다.

추가로 흔한 함정 두 가지를 같이 잡는다.
  · `run: |` 안에 열 0부터 시작하는 줄이 있는지(블록 스칼라를 깨는 바로 그 패턴)
  · 잡에 timeout-minutes 가 없는지(한 단계가 멈추면 기본 6시간 매달린다)
"""
import glob
import sys

try:
    import yaml
except ImportError:
    print("PyYAML 없음 — 검사 생략"); sys.exit(0)

bad, warn = [], []
for path in sorted(glob.glob(".github/workflows/*.yml") + glob.glob(".github/workflows/*.yaml")):
    text = open(path, encoding="utf-8").read()
    try:
        doc = yaml.safe_load(text)
    except Exception as e:
        bad.append(f"{path}: 파싱 실패 — {str(e).splitlines()[0][:90]}")
        continue
    for i, line in enumerate(text.splitlines(), 1):
        if line and not line[0].isspace() and not line[0] in "#-" and ":" not in line.split("#")[0]:
            bad.append(f"{path}:{i}: 열 0 에서 시작하는데 키가 아닌 줄 — 블록 스칼라가 깨졌을 수 있음")
    for name, job in ((doc or {}).get("jobs") or {}).items():
        if isinstance(job, dict) and "timeout-minutes" not in job and "uses" not in job:
            warn.append(f"{path}: 잡 '{name}' 에 timeout-minutes 가 없습니다(멈추면 기본 6시간)")

for w in warn:
    print("  ⚠️ " + w)
if bad:
    print("\n❌ 워크플로 검사 실패")
    for b in bad:
        print("   " + b)
    sys.exit(1)
print(f"✅ 워크플로 {len(glob.glob('.github/workflows/*.yml'))}개 전부 파싱 OK")
