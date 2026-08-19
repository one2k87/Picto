# Supabase 연동 가이드 (Scripto SaaS)

> 목표: 로그인·구독/15일체험·다중 사용자·관리자 대시보드를 위한 백엔드 연결.
> 아키텍처: **컨트롤 플레인(웹앱=로그인·결제·설정) + 생성 워커(내 Gemini 키로 글 생성·발행)**.

## 0. 큰 그림
```
[사용자] → 웹앱 로그인(Supabase Auth: 구글)
        → 초기 세팅비 결제 → start_trial() → 15일 체험 시작
        → 블로그(WP) 연결 정보 저장(sites)
[생성 워커(매일)] → Supabase에서 '자격 있는 사용자' 조회 → 내 Gemini 키로 글 생성 → 각자 WP에 발행 → usage 기록
[관리자(one2k87)] → /admin → admin_stats 뷰로 가입자·플랜·매출 현황
```

## 1. 스키마 넣기 (2분)
1. Supabase 대시보드 → **SQL Editor → New query**.
2. `saas/supabase_schema.sql` 전체 복사 → 붙여넣기 → **Run**.
3. 테이블(profiles·subscriptions·sites·usage)과 뷰(admin_stats)가 생성됩니다.

## 2. 키 3개 위치 확인 (Project Settings → API)
- **Project URL**: `https://xxxx.supabase.co`
- **anon public key**: 웹앱(브라우저)에서 사용 — 공개돼도 됨(RLS가 보호).
- **service_role key**: ⚠️ **비밀**. 생성 워커(서버)에서만 사용 — 모든 사용자 데이터 접근용. 절대 브라우저/깃허브 공개코드에 넣지 말 것.

## 3. 구글 로그인 켜기
1. Supabase → **Authentication → Providers → Google → Enable**.
2. Google Cloud → OAuth 클라이언트(웹) 생성 → **Client ID/Secret**를 Supabase에 입력.
3. 승인된 리디렉션 URI에 Supabase가 알려주는 콜백 주소 등록.
4. **Authentication → URL Configuration**에 웹앱 주소 등록.

## 4. 키를 어디에 넣나
| 키 | 넣는 곳 | 용도 |
|---|---|---|
| Project URL | 웹앱 env + 워커 시크릿 | 공통 |
| anon key | 웹앱 env (`NEXT_PUBLIC_SUPABASE_ANON_KEY`) | 로그인·본인 데이터 |
| service_role key | 워커 GitHub 시크릿 (`SUPABASE_SERVICE_KEY`) | 전체 사용자 조회 |
| **내 Gemini 키** | 워커 GitHub 시크릿 (`LLM_API_KEY`) | 모든 사용자 글 생성 |

## 5. 관리자 지정
`one2k87@gmail.com`로 최초 로그인한 뒤, SQL Editor에서 1회:
```sql
update public.profiles set role = 'admin' where email = 'one2k87@gmail.com';
```
이제 그 계정은 `admin_stats` 뷰(전체 통계)를 볼 수 있습니다.

## 6. 생성 워커(내 API로 다중 사용자 글 생성) — 구현 예정
- GitHub Actions 매일 실행 → Supabase REST로 **자격 있는 사용자**(체험 중 or 유료 활성) 조회
  `GET /rest/v1/sites?select=*,subscriptions(*)` (service_role 헤더).
- 각 사용자마다 그 사람의 WP 정보 + 설정으로 **Scripto 엔진(main.py)**을 돌려 발행.
- 생성 후 `usage`에 호출수·글수·예상비용 기록(관리자 비용 파악).
- 내 **Gemini 키 1개**를 공유하므로, 사용량이 많으면 **유료 티어 필요**(비용은 아래).

## 7. 웹앱(컨트롤 플레인)
- 로그인 후: 블로그 연결 폼 → `sites` 저장 / 결제 → `start_trial()` → 15일 체험 표시 / 만료 임박 안내.
- 승인 후에만 스크립토 월 구독 결제 안내(상태 배지).
- 관리자: `/admin`에서 `admin_stats` 조회.

## 다음 단계(구현 순서)
1. ✅ 스키마(이 파일) — 지금 실행.
2. 웹앱에 Supabase 로그인 + 블로그 연결 저장(`sites`).
3. 결제(페이플/토스 또는 Lemon Squeezy) 웹훅 → `start_trial` / 구독 상태 갱신.
4. 생성 워커: Supabase에서 사용자 읽어 각자 WP에 발행(내 Gemini 키).
5. 관리자 대시보드(`admin_stats`).
