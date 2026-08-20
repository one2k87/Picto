"""
import_backlog_to_supabase.py - 이미 쌓인 초안 백로그(dashboard/data/history.json)를
Supabase의 content_queue 테이블로 1회 가져오는 스크립트.

사용법(저장소 루트에서 실행):
  SUPABASE_URL="https://xxxx.supabase.co" \
  SUPABASE_SERVICE_KEY="eyJ..." \
  python3 saas/import_backlog_to_supabase.py

사전 준비:
  1) Supabase SQL Editor에서 saas/supabase_schema.sql 전체(특히 8번 섹션 content_queue)를 먼저 실행
  2) Project Settings → API에서 URL과 service_role 키를 확인해 위 환경변수로 전달

실제 워드프레스 글이 없는 항목(품질보류/게시실패, post_id 없음)은 건너뛴다.
같은 wp_post_id는 upsert되므로 여러 번 실행해도 안전하다(중복 안 쌓임).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import supabase_client  # noqa: E402

HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "data", "history.json",
)


def main():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY 환경변수가 필요합니다. 상단 사용법 참고.")
        sys.exit(1)

    if not os.path.exists(HISTORY_PATH):
        print(f"history.json을 찾을 수 없음: {HISTORY_PATH}")
        sys.exit(1)

    with open(HISTORY_PATH, encoding="utf-8") as f:
        hist = json.load(f)
    arts = hist.get("articles", [])

    # 실제 워드프레스 글(post_id)이 있는 것만 대상(품질보류/게시실패는 애초에 글이 없음)
    targets = [a for a in arts if a.get("post_id")]
    print(f"전체 {len(arts)}건 중 실제 WP 초안 {len(targets)}건을 백로그로 가져옵니다…")

    cfg = {"supabase": {"url": url, "service_key": key}}
    # 한 번에 너무 많이 보내면 타임아웃 나기 쉬워 500건씩 나눠 전송
    BATCH = 500
    total_ok = 0
    for i in range(0, len(targets), BATCH):
        chunk = targets[i:i + BATCH]
        # supabase_client.sync_backlog는 post_id/generated_at 등 article 스키마를 기대하므로
        # history.json의 date 필드를 generated_at으로 매핑해서 그대로 재사용한다.
        for a in chunk:
            a.setdefault("generated_at", a.get("date"))
        r = supabase_client.sync_backlog(cfg, chunk, source="backlog_import")
        if r.get("ok"):
            total_ok += r.get("count", 0)
        else:
            print(f"  · {i}~{i+len(chunk)} 배치 실패: {r}")
    print(f"완료: {total_ok}/{len(targets)}건 Supabase content_queue에 반영됨.")


if __name__ == "__main__":
    main()
