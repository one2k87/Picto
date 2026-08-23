-- Scripto · 기기 간 설정 동기화
--
-- 왜 필요한가
--   Scripto 설정은 브라우저 localStorage에 있어 폰과 PC가 서로 다른 값을 갖는다.
--   워드프레스 앱 비밀번호, Gemini 키, GitHub 토큰을 기기마다 다시 넣어야 했다.
--
-- 보안 설계 (중요)
--   ① 앱은 **publishable(공개) 키**만 쓴다. service_role 키를 브라우저에 두면
--      그 키를 얻은 사람이 DB 전체를 읽고 지울 수 있다. 이 앱은 GitHub Pages에
--      공개돼 있으므로 절대 그렇게 하지 않는다.
--   ② 표에는 RLS를 켜고 정책을 만들지 않는다 → 공개 키로 표에 직접 접근 불가.
--   ③ 대신 security definer 함수 두 개만 열어 준다. 함수는 slot을 정확히 알아야
--      동작하므로 목록을 훑을(enumerate) 수 없다.
--   ④ slot은 사용자의 암호 문구를 SHA-256 해시한 64자리다. 추측이 불가능하다.
--   ⑤ payload는 클라이언트에서 AES-GCM으로 암호화한 문자열이다. 서버도, 키를
--      가진 제3자도 내용을 읽을 수 없다. 복호화 열쇠는 DB에 저장하지 않는다.

create table if not exists public.device_settings (
  slot        text primary key,                       -- SHA-256(암호문구) 64자
  payload     text not null,                          -- AES-GCM 암호문. 평문 금지
  device      text,                                   -- 마지막으로 올린 기기
  app_version text,
  updated_at  timestamptz not null default now()
);

comment on table  public.device_settings is 'Scripto 설정 동기화. payload는 클라이언트 암호문이며 서버는 복호화할 수 없다.';
comment on column public.device_settings.slot    is '암호 문구의 SHA-256 해시. 추측 불가능해야 하므로 64자 미만은 거부한다.';
comment on column public.device_settings.payload is 'AES-GCM(256) 암호문. 절대 평문을 넣지 말 것.';

-- 표 직접 접근은 전면 차단(정책을 만들지 않는다)
alter table public.device_settings enable row level security;
drop policy if exists device_settings_all on public.device_settings;

-- ── 읽기 ─────────────────────────────────────────────────────
-- slot을 정확히 아는 경우에만 한 줄을 돌려준다. 전체 조회 경로가 없다.
create or replace function public.settings_get(p_slot text)
returns table(payload text, device text, app_version text, updated_at timestamptz)
language sql
security definer
set search_path = public
as $$
  select d.payload, d.device, d.app_version, d.updated_at
  from public.device_settings d
  where d.slot = p_slot;
$$;

-- ── 쓰기 ─────────────────────────────────────────────────────
create or replace function public.settings_put(
  p_slot text, p_payload text, p_device text, p_version text)
returns timestamptz
language plpgsql
security definer
set search_path = public
as $$
declare ts timestamptz;
begin
  -- 짧은 slot은 추측이 가능해지므로 거부한다(해시는 항상 64자)
  if p_slot is null or length(p_slot) < 64 then
    raise exception '유효하지 않은 slot입니다';
  end if;
  -- 암호문이 아닌 값이 들어오는 사고를 막는다(형식: base64.base64)
  if p_payload is null or p_payload !~ '^[A-Za-z0-9+/=]+\.[A-Za-z0-9+/=]+$' then
    raise exception 'payload는 암호문이어야 합니다';
  end if;
  if length(p_payload) > 300000 then
    raise exception '설정이 너무 큽니다';
  end if;

  insert into public.device_settings as d (slot, payload, device, app_version)
  values (p_slot, p_payload, left(coalesce(p_device,''),40), left(coalesce(p_version,''),20))
  on conflict (slot) do update
    set payload     = excluded.payload,
        device      = excluded.device,
        app_version = excluded.app_version,
        updated_at  = now()
  returning d.updated_at into ts;

  return ts;
end;
$$;

-- 공개 키(anon)에게 이 두 함수만 허용한다
revoke all on function public.settings_get(text) from public;
revoke all on function public.settings_put(text, text, text, text) from public;
grant execute on function public.settings_get(text) to anon, authenticated;
grant execute on function public.settings_put(text, text, text, text) to anon, authenticated;
