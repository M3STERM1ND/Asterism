# Putting Asterism on Supabase

Supabase gives Asterism one shared database in the cloud: accounts, coach links, runs, sessions, feedback
and session videos. The game and the coach portal then work from any computer, not only this one.

Do every step below **twice**: once for a project called `asterism-test` (for trying things) and once for
`asterism` (for real patients). Start with `asterism-test`.

> **Before real patients use it:** sessions, pain answers and videos are health data. In the US that means
> HIPAA. Supabase only signs the required agreement (a BAA) on paid plans. Use the free plan for testing
> with made-up or your own data only.

---

## 1. Create the project (about 3 minutes)

1. Go to **https://supabase.com** and click **Start your project**. Sign in with GitHub (the M3STERM1ND account is fine).
2. Click **New project**.
3. Fill in:
   - **Organization:** your personal one.
   - **Project name:** `asterism-test`
   - **Database password:** click **Generate a password**, then save it in your password manager. You
     won't need it day to day, but you can't see it again later.
   - **Region:** the one closest to you (for example *East US (North Virginia)*).
   - **Plan:** Free.
4. Click **Create new project** and wait until the dashboard says the project is ready (1–2 minutes).

## 2. Create the tables and the access rules (1 minute)

1. In the left sidebar, click **SQL Editor** (the `>_` icon).
2. Click **New query**.
3. Open `supabase/schema.sql` from this repo, copy **all** of it, and paste it into the editor.
4. Click **Run** (bottom right). You should see **Success. No rows returned**.
5. Check: left sidebar → **Table Editor**. You should see `profiles`, `links`, `runs`, `sessions` and
   `feedback`, each with a green **RLS enabled** label. Left sidebar → **Storage**: a bucket called
   `session-videos`, marked private.

If **Run** shows an error, copy the red message and send it to me.

## 3. Turn off email confirmation for testing (30 seconds)

By default Supabase emails every new account a confirmation link, and the free plan only sends a few
emails an hour. For `asterism-test`:

1. Left sidebar → **Authentication** → **Sign In / Providers** (in older dashboards: **Providers**).
2. Click **Email**.
3. Turn **Confirm email** **off**, and click **Save**.

For the real `asterism` project, leave it **on**: patients and coaches then confirm their email address.

## 4. Copy the two connection values (1 minute)

1. Left sidebar → **Project Settings** (gear icon) → **Data API** (in older dashboards: **API**).
2. Copy the **Project URL**. It looks like `https://abcdefghijkl.supabase.co`.
3. Then **API Keys**: copy the **anon public** key (a long text starting `eyJ...`), or the
   **publishable** key (starting `sb_publishable_...`) if that's what your dashboard shows.

**Never copy or share the `service_role` key (or `sb_secret_...` key).** It skips every access rule. The
game doesn't need it, and it must never go in the code, GitHub or a chat.

The anon/publishable key is safe to put in the app: on its own it can't read anything, because the access
rules from step 2 decide what each signed-in person sees.

## 5. Connect this computer (1 minute)

In the project folder, create a file called `.env` (it is git-ignored, so it never goes to GitHub):

```
SUPABASE_URL=https://abcdefghijkl.supabase.co
SUPABASE_ANON_KEY=eyJ...your anon or publishable key...
```

Then install the Supabase library once:

```bash
cd /Users/shanthit./Downloads/Asterism-main && .venv/bin/pip install supabase
```

And check the connection:

```bash
cd /Users/shanthit./Downloads/Asterism-main && .venv/bin/python -m cloud check
```

It should print `Connected to https://...supabase.co`.

## 6. Use it

- **Create accounts:** `python -m cloud register` (asks for email, username, name, role and password).
- **Send this computer's runs to the cloud:** `python -m cloud push` (sessions and videos, run by run; safe to
  run again: nothing is sent twice).
- **See what a coach sees:** `python -m cloud coach` (a coach's patients, their sessions and feedback).

---

## What the access rules guarantee

| Who | Can read | Can write |
|---|---|---|
| Anyone signed in | Their own profile, and every coach's profile (the catalog) | Their own profile (not their role) |
| A patient | Their own runs, sessions, videos and feedback | Their own runs, sessions and videos; a link to an **open** coach; leaving their coach; marking feedback read |
| A coach | Their linked patients' profiles, runs, sessions and videos; feedback they wrote | Feedback for their linked patients; their own status (open/closed) |

A coach who isn't linked to a patient gets nothing back: not an error, just no rows. That is the database
refusing, so it holds even if the app has a bug.

## Changing the database later

- **Adding** a table or column: write the change as SQL, run it on `asterism-test`, check the game, then run it
  on `asterism`. Add matching RLS policies for any new table: a table without policies is unreadable, and a
  table without RLS is readable by everyone.
- **Renaming or removing** something: never on `asterism` first. Copy the data out (Table Editor → Export to
  CSV) before you change it.
