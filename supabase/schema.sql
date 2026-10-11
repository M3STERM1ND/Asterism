-- Asterism on Supabase: accounts, coach links, runs, sessions, feedback and session videos.
-- Paste this whole file into Supabase > SQL Editor > New query, and press Run. It is safe to run again.
--
-- Who can see what is enforced here, by row-level security (RLS), not by the app:
--   a patient reads and writes only their own runs, sessions and videos;
--   a coach reads only the patients linked to them, and writes feedback only for them;
--   a patient can link only to a coach whose status is 'open' (one coach at a time);
--   everyone signed in can read the coach catalog (coach profiles), nothing else of other people.

-- ---------------------------------------------------------------- tables
create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    username text not null unique check (username ~ '^[a-z0-9_]{3,20}$'),
    display_name text not null,
    role text not null check (role in ('patient', 'coach')),
    bio text not null default '',
    specialty text not null default '',
    status text not null default 'open' check (status in ('open', 'closed')),
    created_at timestamptz not null default now()
);

create table if not exists public.links (
    patient_id uuid primary key references public.profiles (id) on delete cascade,
    coach_id uuid not null references public.profiles (id) on delete cascade,
    linked_at timestamptz not null default now()
);

create table if not exists public.runs (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.profiles (id) on delete cascade,
    name text not null check (char_length(name) between 1 and 30),
    settings jsonb not null default '{}'::jsonb,   -- difficulty, assisted learning, battles won (the run's progress)
    created_at timestamptz not null default now(),
    last_played timestamptz
);

-- One row per finished battle or practice round: the same columns as sessions.csv.
create table if not exists public.sessions (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.runs (id) on delete cascade,
    patient_id uuid not null references public.profiles (id) on delete cascade,
    played_at timestamptz not null,
    mode text not null,
    constellation text not null default '',
    result text not null default '',
    row jsonb not null,                -- every sessions.csv column, as text, exactly as the game logged it
    video_path text,                   -- in the session-videos bucket: <patient id>/<run id>/<file>.mp4
    created_at timestamptz not null default now(),
    unique (run_id, played_at)         -- the game can safely send the same session twice
);

create table if not exists public.feedback (
    id uuid primary key default gen_random_uuid(),
    coach_id uuid not null references public.profiles (id) on delete cascade,
    patient_id uuid not null references public.profiles (id) on delete cascade,
    run_id uuid references public.runs (id) on delete set null,
    text text not null check (char_length(text) between 1 and 2000),
    created_at timestamptz not null default now(),
    read_at timestamptz
);

create index if not exists runs_patient on public.runs (patient_id);
create index if not exists sessions_run on public.sessions (run_id, played_at);
create index if not exists sessions_patient on public.sessions (patient_id, played_at);
create index if not exists feedback_patient on public.feedback (patient_id, created_at desc);
create index if not exists links_coach on public.links (coach_id);

-- ---------------------------------------------------------------- helpers
-- security definer: these read the tables without RLS, so policies can use them without recursion.
create or replace function public.is_coach_of(patient uuid) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (select 1 from links where patient_id = patient and coach_id = auth.uid());
$$;

create or replace function public.my_role() returns text
language sql stable security definer set search_path = public as $$
    select role from profiles where id = auth.uid();
$$;

create or replace function public.coach_is_open(coach uuid) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (select 1 from profiles where id = coach and role = 'coach' and status = 'open');
$$;

-- A new sign-up gets its profile from the details the app sends (username, display_name, role).
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
    insert into profiles (id, username, display_name, role, bio, specialty)
    values (new.id,
            lower(new.raw_user_meta_data ->> 'username'),
            coalesce(nullif(new.raw_user_meta_data ->> 'display_name', ''), new.raw_user_meta_data ->> 'username'),
            coalesce(new.raw_user_meta_data ->> 'role', 'patient'),
            coalesce(new.raw_user_meta_data ->> 'bio', ''),
            coalesce(new.raw_user_meta_data ->> 'specialty', ''));
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
    for each row execute function public.handle_new_user();

-- A user can't change their own role (patient <-> coach) after sign-up.
create or replace function public.keep_role() returns trigger
language plpgsql as $$
begin
    if new.role <> old.role or new.id <> old.id then
        raise exception 'role and id cannot be changed';
    end if;
    return new;
end;
$$;

drop trigger if exists profiles_keep_role on public.profiles;
create trigger profiles_keep_role before update on public.profiles
    for each row execute function public.keep_role();

-- ---------------------------------------------------------------- row-level security
alter table public.profiles enable row level security;
alter table public.links enable row level security;
alter table public.runs enable row level security;
alter table public.sessions enable row level security;
alter table public.feedback enable row level security;

drop policy if exists "read own profile, coaches, and my patients" on public.profiles;
create policy "read own profile, coaches, and my patients" on public.profiles for select to authenticated
    using (id = auth.uid() or role = 'coach' or public.is_coach_of(id));
drop policy if exists "update own profile" on public.profiles;
create policy "update own profile" on public.profiles for update to authenticated
    using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "see my links" on public.links;
create policy "see my links" on public.links for select to authenticated
    using (patient_id = auth.uid() or coach_id = auth.uid());
drop policy if exists "patients link to open coaches" on public.links;
create policy "patients link to open coaches" on public.links for insert to authenticated
    with check (patient_id = auth.uid() and public.my_role() = 'patient' and public.coach_is_open(coach_id));
drop policy if exists "patients switch to open coaches" on public.links;
create policy "patients switch to open coaches" on public.links for update to authenticated
    using (patient_id = auth.uid()) with check (patient_id = auth.uid() and public.coach_is_open(coach_id));
drop policy if exists "patients leave their coach" on public.links;
create policy "patients leave their coach" on public.links for delete to authenticated
    using (patient_id = auth.uid());

drop policy if exists "patients own their runs" on public.runs;
create policy "patients own their runs" on public.runs for all to authenticated
    using (patient_id = auth.uid()) with check (patient_id = auth.uid() and public.my_role() = 'patient');
drop policy if exists "coaches read their patients' runs" on public.runs;
create policy "coaches read their patients' runs" on public.runs for select to authenticated
    using (public.is_coach_of(patient_id));

drop policy if exists "patients write their sessions" on public.sessions;
create policy "patients write their sessions" on public.sessions for insert to authenticated
    with check (patient_id = auth.uid()
                and exists (select 1 from public.runs r where r.id = run_id and r.patient_id = auth.uid()));
drop policy if exists "patients update their sessions" on public.sessions;
create policy "patients update their sessions" on public.sessions for update to authenticated
    using (patient_id = auth.uid()) with check (patient_id = auth.uid());
drop policy if exists "read own or my patients' sessions" on public.sessions;
create policy "read own or my patients' sessions" on public.sessions for select to authenticated
    using (patient_id = auth.uid() or public.is_coach_of(patient_id));

drop policy if exists "read feedback I wrote or received" on public.feedback;
create policy "read feedback I wrote or received" on public.feedback for select to authenticated
    using (patient_id = auth.uid() or coach_id = auth.uid());
drop policy if exists "coaches write to their patients" on public.feedback;
create policy "coaches write to their patients" on public.feedback for insert to authenticated
    with check (coach_id = auth.uid() and public.is_coach_of(patient_id));
drop policy if exists "patients mark feedback read" on public.feedback;
create policy "patients mark feedback read" on public.feedback for update to authenticated
    using (patient_id = auth.uid()) with check (patient_id = auth.uid());

-- ---------------------------------------------------------------- session videos (private bucket)
insert into storage.buckets (id, name, public)
values ('session-videos', 'session-videos', false)
on conflict (id) do nothing;

-- Paths are <patient id>/<run id>/<file>.mp4, so the first folder says whose video it is.
drop policy if exists "patients upload their videos" on storage.objects;
create policy "patients upload their videos" on storage.objects for insert to authenticated
    with check (bucket_id = 'session-videos' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "read own or my patients' videos" on storage.objects;
create policy "read own or my patients' videos" on storage.objects for select to authenticated
    using (bucket_id = 'session-videos'
           and ((storage.foldername(name))[1] = auth.uid()::text
                or public.is_coach_of(((storage.foldername(name))[1])::uuid)));
