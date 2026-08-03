-- Run this in Supabase Dashboard > SQL Editor.
-- This app uses Supabase Auth + RLS. Each user can access only their own rows.

create table if not exists public.body_measurements_private (
  user_id uuid not null references auth.users(id) on delete cascade,
  measurement_date date not null,
  sex text not null check (sex in ('female', 'male')),
  height_cm double precision not null check (height_cm between 100 and 230),
  weight_kg double precision not null check (weight_kg between 25 and 300),
  body_fat_pct double precision not null check (body_fat_pct between 2 and 70),
  visceral_fat_pct double precision not null check (visceral_fat_pct between 0 and 60),
  bone_mass_kg double precision not null check (bone_mass_kg between 0.5 and 10),
  bmr_kcal double precision not null,
  metabolic_age double precision not null check (metabolic_age between 18 and 90),
  updated_at timestamp with time zone not null default now(),
  primary key (user_id, measurement_date)
);

alter table public.body_measurements_private enable row level security;

-- Migrate the earlier Japanese storage values to stable ASCII values and
-- recreate the constraint when this script is rerun for an existing table.
alter table public.body_measurements_private
  drop constraint if exists body_measurements_private_sex_check;
update public.body_measurements_private
set sex = case btrim(sex)
  when '女性' then 'female'
  when '男性' then 'male'
  else lower(btrim(sex))
end;
alter table public.body_measurements_private
  add constraint body_measurements_private_sex_check
  check (sex in ('female', 'male'));

revoke all on table public.body_measurements_private from anon;
grant select, insert, update, delete
  on table public.body_measurements_private to authenticated;

drop policy if exists "Users can view own measurements"
  on public.body_measurements_private;
create policy "Users can view own measurements"
  on public.body_measurements_private for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can insert own measurements"
  on public.body_measurements_private;
create policy "Users can insert own measurements"
  on public.body_measurements_private for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update own measurements"
  on public.body_measurements_private;
create policy "Users can update own measurements"
  on public.body_measurements_private for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete own measurements"
  on public.body_measurements_private;
create policy "Users can delete own measurements"
  on public.body_measurements_private for delete
  to authenticated
  using ((select auth.uid()) = user_id);

-- Lock the old shared table. It is retained only so existing records are not
-- destroyed. The updated app never reads from it.
do $$
begin
  if to_regclass('public.body_measurements') is not null then
    alter table public.body_measurements enable row level security;
    revoke all on table public.body_measurements from anon, authenticated;
  end if;
end
$$;
