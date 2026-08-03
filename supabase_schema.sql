-- Run this once in Supabase Dashboard > SQL Editor.
create table if not exists public.body_measurements (
  measurement_date date primary key,
  sex text not null check (sex in ('女性', '男性')),
  height_cm double precision not null check (height_cm between 100 and 230),
  weight_kg double precision not null check (weight_kg between 25 and 300),
  body_fat_pct double precision not null check (body_fat_pct between 2 and 70),
  visceral_fat_pct double precision not null check (visceral_fat_pct between 0 and 60),
  bone_mass_kg double precision not null check (bone_mass_kg between 0.5 and 10),
  bmr_kcal double precision not null,
  metabolic_age double precision not null check (metabolic_age between 18 and 90),
  updated_at timestamp with time zone not null default now()
);

alter table public.body_measurements enable row level security;

-- Recreate the constraint as well when this script is run for an existing
-- table. CREATE TABLE IF NOT EXISTS alone does not update old constraints.
alter table public.body_measurements
  drop constraint if exists body_measurements_sex_check;
alter table public.body_measurements
  add constraint body_measurements_sex_check
  check (btrim(sex) in ('女性', '男性'));

-- No public policies are created. The Streamlit server connects with the
-- service_role key stored in Secrets and bypasses RLS. Never put that key in
-- source control or expose it in browser-side code.
