# Picto 버전 기록

Picto(픽토)는 스크립토 패밀리의 픽 라인 전용 엔진입니다 — 쿠팡파트너스 커머스 블로그(pickdam.com) 자동화.
엔진은 Scripto v1.4에서 분기(2026-09-01). 공용 교훈·모듈은 Scripto CHANGELOG/docs 참조.

## v0.1 — 분기·개통 준비 (2026-09-01)

- Scripto v1.4 전체 임포트(히스토리 포함)
- 픽담 전용: localStorage 키 분리(picto_cfg — 같은 오리진의 Scripto와 설정 충돌 방지), 저장소 기본값 Picto, 브랜딩(Picto v0.1)
- data/site_categories.json: track=coupang(커머스 모드), 시작 카테고리 '생활·주방', 위험 소재 금지어
- 모든 크론 비활성(연결 전 실패 방지) — 시크릿 등록 후 재활성 예정
