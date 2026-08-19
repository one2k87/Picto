-- Scripto SaaS · Supabase 스키마
-- 실행: Supabase 대시보드 → SQL Editor → New query → 전체 붙여넣기 → Run
-- 구성: 사용자(profiles) · 구독/체험(subscriptions) · 블로그연결(sites) · 사용량(usage)
-- 보안: RLS로 본인 데이터만. admin 롤은 전체 열람.

-- ── 1. 프로필 (auth.users와 1:1) ─────────────────────────────
create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  email text,
  role text not null default 'user',          -- 'user' | 'admin'
  created_at timestamptz not null default now()
);

-- 회원가입 시 프로필 자동 생성
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end; $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users for each row execute function public.handle_new_user();

-- ── 2. 구독/체험 ─────────────────────────────────────────────
create table if not exists public.subscriptions (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  plan text not null default 'basic',          -- basic | pro | max
  status text not null default 'trialing',     -- trialing | active | canceled | past_due
  setup_paid boolean not null default false,   -- 초기 세팅비 결제 여부
  trial_end timestamptz,                        -- 15일 무료 종료 시각
  current_period_end timestamptz,               -- 유료 결제 만료 시각
  updated_at timestamptz not null default now()
);

-- 초기 세팅비 결제 시 15일 체험 시작(결제 웹훅에서 호출)
create or replace function public.start_trial(uid uuid, p text default 'basic')
returns void language plpgsql security definer as $$
begin
  insert into public.subscriptions (user_id, plan, status, setup_paid, trial_end)
  values (uid, p, 'trialing', true, now() + interval '15 days')
  on conflict (user_id) do update
    set setup_paid = true, status = 'trialing',
        trial_end = coalesce(public.subscriptions.trial_end, now() + interval '15 days'),
        updated_at = now();
end; $$;

-- '지금 글을 생성해도 되는 사용자'인지 판단(체험 중이거나 유료 활성)
create or replace function public.is_entitled(s public.subscriptions)
returns boolean language sql immutable as $$
  select (s.status = 'active' and (s.current_period_end is null or s.current_period_end > now()))
      or (s.status = 'trialing' and s.trial_end is not null and s.trial_end > now());
$$;

-- ── 3. 블로그 연결 + 개인 설정 ───────────────────────────────
create table if not exists public.sites (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  wp_url text,
  wp_user text,
  wp_app_password text,          -- 운영 시 pgsodium 등으로 암호화 권장
  categories jsonb default '[]', -- [{name,desc,wp_slug}]
  settings jsonb default '{}',   -- 강도/드립/쿠팡/승인여부 등
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

-- ── 4. 사용량(월별) ──────────────────────────────────────────
create table if not exists public.usage (
  user_id uuid references public.profiles(id) on delete cascade,
  month text not null,           -- 'YYYY-MM'
  llm_calls int not null default 0,
  articles int not null default 0,
  est_cost_krw int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (user_id, month)
);

-- ── 5. RLS (본인만 · admin 전체) ─────────────────────────────
alter table public.profiles enable row level security;
alter table public.subscriptions enable row level security;
alter table public.sites enable row level security;
alter table public.usage enable row level security;

create or replace function public.is_admin()
returns boolean language sql stable security definer as $$
  select exists(select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

do $$ begin
  -- profiles
  create policy "own or admin read profiles" on public.profiles for select using (id = auth.uid() or public.is_admin());
  create policy "own update profiles" on public.profiles for update using (id = auth.uid());
  -- subscriptions
  create policy "own or admin read subs" on public.subscriptions for select using (user_id = auth.uid() or public.is_admin());
  -- sites
  create policy "own read sites" on public.sites for select using (user_id = auth.uid() or public.is_admin());
  create policy "own upsert sites" on public.sites for insert with check (user_id = auth.uid());
  create policy "own update sites" on public.sites for update using (user_id = auth.uid());
  -- usage
  create policy "own or admin read usage" on public.usage for select using (user_id = auth.uid() or public.is_admin());
exception when duplicate_object then null; end $$;

-- ── 6. 관리자 통계 뷰 (admin 전용, /admin 대시보드에서 사용) ──
create or replace view public.admin_stats as
select
  count(*)                                             as total_users,
  count(*) filter (where s.status = 'trialing')        as trialing,
  count(*) filter (where s.status = 'active')          as active_paid,
  count(*) filter (where s.plan = 'basic'  and s.status='active') as basic_paid,
  count(*) filter (where s.plan = 'pro'    and s.status='active') as pro_paid,
  count(*) filter (where s.plan = 'max'    and s.status='active') as max_paid,
  count(*) filter (where s.setup_paid)                 as setup_paid_count
from public.profiles p left join public.subscriptions s on s.user_id = p.id;

-- ── 7. 관리자 지정 (본인 계정) ───────────────────────────────
-- 아래는 one2k87@gmail.com 로 최초 로그인한 뒤 1회 실행하세요:
-- update public.profiles set role = 'admin' where email = 'one2k87@gmail.com';
