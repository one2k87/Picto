"""
supabase_client.py - Supabase(PostgREST) 연동, requests만 사용(추가 패키지 불필요).
용도: 초안 백로그(content_queue 테이블)를 Supabase에 동기화하고,
      다음 방출 대상을 조회/완료 처리하는 최소 클라이언트.

config에 supabase.url / supabase.service_key가 없으면 모든 함수가 조용히 건너뛴다
(sheets.py/notify.py와 동일한 '선택 연동' 패턴).
"""

import requests


def _cfg(cfg):
    sb = (cfg or {}).get("supabase") or {}
    url = (sb.get("url") or "").rstrip("/")
    key = sb.get("service_key") or ""
    return url, key


def _headers(key):
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def is_configured(cfg):
    url, key = _cfg(cfg)
    return bool(url and key)


def sync_backlog(cfg, articles, source="daily_run"):
    """생성된 글 목록을 content_queue에 upsert(wp_post_id 기준 중복 방지).
    post_id/post_url이 없는 글(품질보류·게시실패 등, 실제 WP 글이 없는 경우)은 건너뛴다.
    실패해도 전체 파이프라인은 계속 진행(best-effort)."""
    url, key = _cfg(cfg)
    if not (url and key):
        return {"ok": False, "reason": "not-configured"}
    rows = []
    for a in articles or []:
        post_id = a.get("post_id")
        if not post_id:
            continue
        rows.append({
            "wp_post_id": post_id,
            "title": a.get("title", ""),
            "slug": a.get("slug", ""),
            "category": a.get("category", ""),
            "keyword": a.get("keyword", ""),
            "kind": a.get("kind", ""),
            "status": "draft",
            "generated_at": a.get("generated_at") or a.get("date"),
            "source": source,
        })
    if not rows:
        return {"ok": True, "count": 0}
    try:
        r = requests.post(
            f"{url}/rest/v1/content_queue",
            headers={**_headers(key), "Prefer": "resolution=merge-duplicates,return=minimal"},
            params={"on_conflict": "wp_post_id"},
            json=rows, timeout=20,
        )
        ok = r.status_code in (200, 201, 204)
        if ok:
            print(f"[supabase] content_queue 동기화 {len(rows)}건 완료")
        else:
            print(f"[supabase] 동기화 실패({r.status_code}): {r.text[:200]}")
        return {"ok": ok, "count": len(rows), "status": r.status_code}
    except Exception as e:
        print(f"[supabase] 동기화 예외(무시하고 계속): {e}")
        return {"ok": False, "reason": str(e)}


def next_release_batch(cfg, n=5):
    """다음에 실제 발행 전환할 대상 n개(우선순위·오래된 순)를 반환. 실패 시 빈 리스트."""
    url, key = _cfg(cfg)
    if not (url and key):
        return []
    try:
        r = requests.post(f"{url}/rest/v1/rpc/next_release_batch",
                           headers=_headers(key), json={"n": n}, timeout=20)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print(f"[supabase] next_release_batch 실패: {e}")
        return []


def mark_published(cfg, ids):
    """id 목록을 published로 표시(실제 워드프레스 발행 전환 성공 후 호출)."""
    url, key = _cfg(cfg)
    if not (url and key) or not ids:
        return {"ok": False}
    try:
        r = requests.post(f"{url}/rest/v1/rpc/mark_published",
                           headers=_headers(key), json={"ids": ids}, timeout=20)
        return {"ok": r.status_code in (200, 204)}
    except Exception as e:
        print(f"[supabase] mark_published 실패: {e}")
        return {"ok": False}
