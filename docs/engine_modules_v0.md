# 픽담 자동 글쓰기 엔진 모듈 구조 v0 (2026-11-24, 픽토 초안)

스크립토의 「엔진 모듈화 요청」(11/23)에 대한 픽토 답이다. 견본은 `Scripto/docs/engine_modules_v0.md`.
**설계 문서일 뿐이다. 코드 이동·리팩터링은 하지 않았고, 적용은 사용자 승인 뒤에 한다.**

픽담이 원더랜드와 다른 점은 하나다. 글이 목적이 아니라 **쿠팡 링크가 눌리는 것**이 목적이라, 「수익 엔진」이 따로 있고
글 생산 라인이 둘이다(① 정기 글: 월·수·금 ② 유행템: 주간 리포트 → 아이템 페이지 → 톱3 비교 글).

## 모듈 9 + 공통 기반 3

| # | 모듈 | 입력 → 출력 | 지금 픽토 코드 | 성장 지표(기록) |
|---|---|---|---|---|
| 1 | 주제 엔진 | 유입 검색어·검색 추이·수요 → 주제 카드(검색어·몫 A/B/C/D·각도) | `portfolio.py`, `topics.py`, `strategy.py`, `demand.py`, `metrics.py`, `trends.py`, `scripts/naver_signals.py`, 지정 글감 `dashboard/data/topic_queue.json` | 몫(강화·에버그린·핫이슈·실험)별 30일 노출·순위 |
| 2 | 제목 엔진 | 주제 카드 → 제목 1개 + 주소(slug) | `generator.py`(`_seo_title`·`make_slug`), `scripts/naver_title_gap.py` | 유입어-제목 일치율, 클릭률(서치어드바이저 캡처) |
| 3 | 본문 엔진 | 제목·검색 의도 → 본문 HTML(요약·표·FAQ·체크리스트) | `generator.py`, `links.py`(실제 참고 링크), `price_ref.py`(기준가) | 근거 없는 수치 건수, 사람이 고친 횟수 |
| 4 | 시각 엔진 | 본문 → 그림 3장 + 대표 이미지 | `images.py`, `generator._convert_markers`, `scripts/make_featured.py`, `reimage_posts.py`, `topup_images.py` | 그림 검수 통과율, 글자 깨짐·자리 오류 건수 |
| 5 | 검수 엔진 | 초안 → 통과/수정/폐기 | `quality.py`, `accuracy.py`, `data/article_requirements.json`, `dashboard/data/adsense_rules.json` | 폐기율, 발행 뒤 고친 횟수 |
| 6 | 수익 엔진 | 글 ↔ 상품 → 상품 카드·쿠팡 링크·콕픽 블록 | `products.py`, `data/products.json`, `data/product_card_plan.json`, `scripts/insert_product_cards.py`, `kokpick.py`, `casto_link.py`, `coupang_api.py`(조건 충족 전 꺼짐) | 카드 노출 대비 클릭, 글당 클릭, 판매액 |
| 7 | 발행 엔진 | 통과본 → 워드프레스 게시·내부 링크·알림 | `publisher.py`, `main.py`(`_relink_old_posts`), `ramp.py`, `scripts/ping_new_posts.py`, `notify.py` | 발행 실패율, 예약 대비 실제 발행 시각 |
| 8 | 점검 엔진 | 발행 글 → 색인·노출·순위·오류 | `insights.py`, `monitor.py`, `scripts/selfcheck.py`, `scripts/naver_signals.py`(순위), `scripts/keyword_volume_audit.py`, `report.py` | 수집 성공률, 조용히 실패한 건수 |
| 9 | 개선 엔진 | 점검 결과 → 원인 모듈 지목 + 수정안 | `scripts/patch_posts.py`, `enrich_posts.py`, `merge_posts.py`, `trash_posts.py`, `scripts/portfolio_feedback.py` (지목은 아직 사람) | 수정 전후 순위·클릭 차이 |
| 기반 | LLM 라우터 | 모듈 요청 → 무료 키 우선, 막히면 전환 | `llm.py` | 1편당 호출 수·실패율·비용 |
| 기반 | 설정 파일 | Secrets → `config.json` 하나 | `build_config.py` | — |
| 기반 | 안전장치 | 공개 글 변경은 dry_run·휴지통·삭제 주소 등록 | 워크플로의 `dry_run` 입력, `data/removed_urls.json`, 워드프레스 리비전 | 되돌림 횟수 |

유행템 라인(`scripts/weekly_trend_report.py`, `trend_item_pages.py`, `data/trend_items.json`)은 1(캐스토 트렌드 데이터가 주제)·6(상품이 먼저 정해짐)을
거꾸로 타는 같은 모듈의 다른 경로로 본다. 모듈을 따로 만들지 않는다.

## 모듈로 나눠야 하는 이유 — 실제로 난 사고

| 날짜 | 무슨 일 | 원인 모듈 | 지금까지는 |
|---|---|---|---|
| 11/10~11/20 | 그림 24장이 전부 못 쓸 그림 | 4 시각 | 열흘 동안 아무도 몰랐다 |
| 11/23 | 지정 글감의 각도 메모가 제목에 통째로 들어감(#951) | 2 제목 | 발행 뒤 손으로 고침 |
| 11/23 | 그림이 낱말 한가운데 끼어듦(#951·#901) | 4 시각 | 하루 뒤 수치 검증하다 발견 |
| 11/23 | 「총비용 약 15만~30만 원 차이」 등 근거 없는 수치(#951) | 3 본문 · 5 검수 | 검수를 통과해 발행됨 |
| 11/24 | 순위 조회 78건 전부 실패했는데 로그에 한 줄도 없음 | 8 점검 | 사람이 결과 파일을 열어 보고 앎 |

공통점은 **어느 모듈의 어느 변경이 만든 글인지 기록이 없어서** 사고를 글 단위로만 고치고 끝났다는 것이다.

## 성장 구조(기록 → 학습 → 승격)

1. 모듈마다 `modules/<이름>/rules.json`(프롬프트·임계값)과 `CHANGELOG.md`(버전·바꾼 이유·근거)를 둔다. 코드는 고정하고 규칙 파일이 자란다.
2. 글마다 `dashboard/data/history.json` 항목에 `module_versions`(예: `topic@1.0, title@1.1, visual@1.2`)를 남긴다.
   포트폴리오가 이미 글마다 몫(A/B/C/D)을 적으므로 같은 자리에 붙이면 된다.
3. 개선안은 새 글 절반에만 적용 → 2주 비교 → 이기면 승격. **픽담은 주 3편이라 2주에 6편, 한쪽 3편뿐이다.**
   숫자로 가르기엔 표본이 작으므로 픽담에서는 「4주·한쪽 6편 이상」으로 늘리거나, 수치 대신 사고 건수(위 표)로 판정한다.
4. 순위(매주 월요일 `naver_signals.json`)와 서치어드바이저 캡처를 `module_versions`와 묶어 본다.

## 1차 범위 제안

| 구분 | 모듈 | 이유 |
|---|---|---|
| 지금 자동으로 도는 것 | 1 주제 · 2 제목 · 3 본문 · 4 시각 · 5 검수 · 7 발행 + 기반 3 | 월·수·금 정기 발행이 이미 이 순서로 돈다 |
| 반자동으로 둘 것 | 6 수익 | 글과 상품을 자동으로 맞추면 틀린다(11/20 실측: 전동 채칼 글에 야채다지기). 쿠팡은 약관상 자동 수집 금지라 링크·가격은 사람이 본 값만 |
| 점검만 자동 | 8 점검 | 순위·추이는 자동, 노출·클릭은 서치어드바이저에 API가 없어 캡처 |
| 수동(체크리스트)으로 시작 | 9 개선 | 원인 모듈 지목은 사람이 하고, 고치는 도구(패치·보강·통합·휴지통)만 자동 |

## 적용 순서(승인 뒤)

1. `module_versions` 태깅부터(기록만 추가, 동작 변화 없음). 전 모듈 `@1.0`으로 시작.
2. 사고가 잦았던 순서로 규칙 파일 분리: 4 시각 → 3 본문·5 검수(근거 없는 수치 차단) → 2 제목.
3. 9 개선의 「원인 모듈 지목」을 주간 리포트에 한 줄로 추가.

## 스크립토 견본과 다른 점

- 모듈 6(수익)이 추가됐다. 원더랜드는 애드센스라 본문이 곧 수익이지만 픽담은 상품 카드가 수익이다.
- 원본 규칙: `naver_hub.py`·`scripts/naver_signals.py`·`scripts/naver_title_gap.py`는 픽토가 원본이고 스크립토에 복사해 쓴다. 모듈 1·2·8에 걸쳐 있으니, 공통 기반으로 올릴 후보다.
- A/B 2주는 픽담 표본(주 3편)으로는 모자란다(위 3항).
