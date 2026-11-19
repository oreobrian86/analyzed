-- TikTok Channel Intelligence — schema khởi tạo
-- Chạy file này trong Supabase Dashboard → SQL Editor → New query → Run.
-- Backend kết nối Postgres trực tiếp (role postgres) nên bỏ qua RLS;
-- RLS được bật và KHÔNG có policy => trình duyệt (anon key) không đọc/ghi được bảng nào.

create extension if not exists pgcrypto;

-- ---------- USERS ----------
create table if not exists public.profiles (
  id uuid primary key,                       -- = auth.users.id
  email text,
  display_name text,
  role text not null default 'user' check (role in ('user','admin')),
  quota_overrides jsonb not null default '{}'::jsonb,   -- vd {"max_videos_per_day": 100}
  created_at timestamptz not null default now()
);

-- ---------- CHANNELS / ANALYSES ----------
create table if not exists public.channels (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  platform text not null default 'tiktok',
  handle text not null,
  profile_url text,
  display_name text,
  created_at timestamptz not null default now(),
  unique (user_id, platform, handle)
);

create table if not exists public.analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  channel_id uuid references public.channels(id) on delete set null,
  title text,
  source text not null check (source in ('profile','urls','upload','import')),
  status text not null default 'queued'
    check (status in ('draft','queued','collecting','processing','aggregating','done','partial','failed','cancelled')),
  stage text,
  progress real not null default 0,
  options jsonb not null default '{}'::jsonb,
  error text,
  video_count int not null default 0,
  videos_done int not null default 0,
  videos_failed int not null default 0,
  videos_skipped int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  expires_at timestamptz
);
create index if not exists analyses_user_idx on public.analyses(user_id, created_at desc);

-- ---------- VIDEOS ----------
create table if not exists public.videos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  analysis_id uuid not null references public.analyses(id) on delete cascade,
  ref text not null,                          -- mã ngắn V01, V02... dùng trong prompt và báo cáo
  platform_video_id text,
  url text,
  caption text,
  posted_at timestamptz,
  duration_sec real,
  views bigint, likes bigint, comments bigint, shares bigint, saves bigint,
  metrics_source text not null default 'none' check (metrics_source in ('collector','user_import','none')),
  thumbnail_url text,
  upload_path text,                           -- file người dùng upload (Supabase Storage, xoá sau khi xử lý)
  upload_bytes bigint not null default 0,
  keyframe_paths text[] not null default '{}',
  media_meta jsonb not null default '{}'::jsonb,
  content_hash text,
  status text not null default 'pending'
    check (status in ('pending','processing','done','failed','skipped','cancelled')),
  stage text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists videos_analysis_idx on public.videos(analysis_id);
create index if not exists videos_user_idx on public.videos(user_id, created_at desc);
create unique index if not exists videos_analysis_pvid_uniq
  on public.videos(analysis_id, platform_video_id) where platform_video_id is not null;

create table if not exists public.video_analyses (
  video_id uuid primary key references public.videos(id) on delete cascade,
  user_id uuid not null,
  transcript text,
  ocr_text text,
  analysis jsonb not null,
  provider text, model text, prompt_version text,
  input_mode text,                            -- 'video' | 'frames+transcript'
  confidence real,
  from_cache boolean not null default false,
  created_at timestamptz not null default now()
);

-- Cache dùng chung: cùng 1 video TikTok + cùng model + cùng prompt version => không gọi AI lại
create table if not exists public.analysis_cache (
  cache_key text primary key,
  transcript text, ocr_text text,
  analysis jsonb not null,
  media_meta jsonb,
  provider text, model text, prompt_version text, input_mode text,
  created_at timestamptz not null default now(),
  last_used_at timestamptz not null default now()
);

create table if not exists public.video_embeddings (
  video_id uuid primary key references public.videos(id) on delete cascade,
  analysis_id uuid not null references public.analyses(id) on delete cascade,
  provider text, model text, dims int,
  embedding real[] not null
);

create table if not exists public.clusters (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analyses(id) on delete cascade,
  kind text not null check (kind in ('topic','pillar')),
  key text not null,                          -- T1.. / P1..
  name text, description text,
  data jsonb not null default '{}'::jsonb,
  video_ids uuid[] not null default '{}',
  created_at timestamptz not null default now()
);
create index if not exists clusters_analysis_idx on public.clusters(analysis_id);

create table if not exists public.reports (
  analysis_id uuid primary key references public.analyses(id) on delete cascade,
  user_id uuid not null,
  report jsonb not null,
  markdown text,
  created_at timestamptz not null default now()
);

-- ---------- QUEUE ----------
create table if not exists public.jobs (
  id bigserial primary key,
  user_id uuid not null,
  analysis_id uuid not null references public.analyses(id) on delete cascade,
  video_id uuid references public.videos(id) on delete cascade,
  type text not null check (type in ('collect','process_video','aggregate')),
  status text not null default 'queued' check (status in ('queued','running','done','failed','cancelled')),
  priority int not null default 100,
  attempts int not null default 0,
  max_attempts int not null default 3,
  run_after timestamptz not null default now(),
  locked_by text,
  locked_at timestamptz,
  heartbeat_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists jobs_claim_idx on public.jobs(status, run_after, priority, id);
create index if not exists jobs_analysis_idx on public.jobs(analysis_id);

create table if not exists public.job_logs (
  id bigserial primary key,
  analysis_id uuid not null references public.analyses(id) on delete cascade,
  video_id uuid,
  level text not null default 'info',
  message text not null,
  created_at timestamptz not null default now()
);
create index if not exists job_logs_analysis_idx on public.job_logs(analysis_id, id);

-- ---------- USAGE ----------
-- user_id = '00000000-0000-0000-0000-000000000000' là dòng tổng của toàn project (global cap)
create table if not exists public.usage_daily (
  user_id uuid not null,
  day date not null,
  analyses int not null default 0,
  videos int not null default 0,
  ai_requests int not null default 0,
  ai_input_tokens bigint not null default 0,
  ai_output_tokens bigint not null default 0,
  upload_bytes bigint not null default 0,
  primary key (user_id, day)
);

-- Lấy 1 job an toàn khi có nhiều worker; mỗi user tối đa p_max_per_user job chạy cùng lúc
create or replace function public.claim_job(p_worker text, p_max_per_user int)
returns setof public.jobs
language plpgsql as $$
declare j public.jobs;
begin
  select q.* into j from public.jobs q
  where q.status = 'queued' and q.run_after <= now()
    and (select count(*) from public.jobs r
         where r.status = 'running' and r.user_id = q.user_id) < p_max_per_user
  order by q.priority, q.id
  for update skip locked
  limit 1;
  if not found then return; end if;
  update public.jobs
     set status = 'running', attempts = attempts + 1, locked_by = p_worker,
         locked_at = now(), heartbeat_at = now(), updated_at = now()
   where id = j.id
  returning * into j;
  return next j;
end $$;

-- Job "running" mà mất heartbeat (server bị restart/spin down) => trả về hàng đợi (resume)
create or replace function public.requeue_stale_jobs(p_stale_seconds int)
returns int language plpgsql as $$
declare n int;
begin
  update public.jobs
     set status = case when attempts >= max_attempts then 'failed' else 'queued' end,
         last_error = left(coalesce(last_error, '') || ' [recovered after lost heartbeat]', 2000),
         locked_by = null, updated_at = now(), run_after = now()
   where status = 'running'
     and heartbeat_at < now() - make_interval(secs => p_stale_seconds);
  get diagnostics n = row_count;
  return n;
end $$;

-- Cộng usage nguyên tử, kiểm tra cả giới hạn user và giới hạn toàn project.
-- Trả về true nếu được phép, false nếu vượt giới hạn (không cộng gì).
create or replace function public.consume_usage(
  p_user uuid, p_field text, p_amount bigint, p_user_limit bigint, p_global_limit bigint)
returns boolean language plpgsql as $$
declare
  g uuid := '00000000-0000-0000-0000-000000000000';
  cur_user bigint; cur_global bigint;
begin
  if p_field not in ('analyses','videos','ai_requests','ai_input_tokens','ai_output_tokens','upload_bytes') then
    raise exception 'invalid usage field %', p_field;
  end if;
  insert into public.usage_daily(user_id, day) values (p_user, current_date) on conflict do nothing;
  insert into public.usage_daily(user_id, day) values (g, current_date) on conflict do nothing;
  -- khoá theo thứ tự cố định để tránh deadlock
  perform 1 from public.usage_daily where day = current_date and user_id in (p_user, g)
    order by user_id for update;
  execute format('select %I from public.usage_daily where user_id=$1 and day=current_date', p_field)
    into cur_user using p_user;
  execute format('select %I from public.usage_daily where user_id=$1 and day=current_date', p_field)
    into cur_global using g;
  if p_user_limit is not null and p_user_limit >= 0 and cur_user + p_amount > p_user_limit then
    return false;
  end if;
  if p_global_limit is not null and p_global_limit >= 0 and cur_global + p_amount > p_global_limit then
    return false;
  end if;
  execute format('update public.usage_daily set %I = %I + $1 where day=current_date and user_id in ($2,$3)',
                 p_field, p_field) using p_amount, p_user, g;
  return true;
end $$;

-- ---------- RLS: khoá toàn bộ khỏi anon/authenticated ----------
alter table public.profiles enable row level security;
alter table public.channels enable row level security;
alter table public.analyses enable row level security;
alter table public.videos enable row level security;
alter table public.video_analyses enable row level security;
alter table public.analysis_cache enable row level security;
alter table public.video_embeddings enable row level security;
alter table public.clusters enable row level security;
alter table public.reports enable row level security;
alter table public.jobs enable row level security;
alter table public.job_logs enable row level security;
alter table public.usage_daily enable row level security;

revoke execute on function public.claim_job(text,int) from public;
revoke execute on function public.requeue_stale_jobs(int) from public;
revoke execute on function public.consume_usage(uuid,text,bigint,bigint,bigint) from public;
