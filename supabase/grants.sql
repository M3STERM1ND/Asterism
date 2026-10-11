-- Asterism: let signed-in users reach the tables. Row-level security (schema.sql) still decides which rows
-- each person sees. Signed-out visitors (the anon role) get nothing. Safe to run again.
grant usage on schema public to authenticated;
grant select, insert, update, delete on public.profiles, public.links, public.runs, public.sessions, public.feedback
    to authenticated;
grant execute on function public.is_coach_of(uuid), public.my_role(), public.coach_is_open(uuid) to authenticated;
revoke all on public.profiles, public.links, public.runs, public.sessions, public.feedback from anon;
