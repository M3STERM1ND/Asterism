"""Cloud: Asterism's link to Supabase (see supabase/SETUP.md and supabase/schema.sql).

The game keeps working offline from data/ exactly as before. This module copies a patient's runs, sessions
and videos up to Supabase, so their coach can follow them from any computer. Every query goes through
Supabase's row-level security as the signed-in user: the anon key alone can read nothing.

  .venv/bin/python -m cloud check       is the connection set up?
  .venv/bin/python -m cloud register    create a patient or coach account in Supabase
  .venv/bin/python -m cloud push        sign in as a patient and send a local account's runs up (safe to repeat)
  .venv/bin/python -m cloud coach       sign in as a coach and list your patients' sessions and feedback
  .venv/bin/python -m cloud link        sign in as a patient and link to an open coach

Settings come from .env (git-ignored): SUPABASE_URL and SUPABASE_ANON_KEY.
"""
import csv
import getpass
import json
import os
import sys
from datetime import datetime

from accounts import Store

ENV_FILE = ".env"
MAP_FILE = "cloud_map.json"     # in data/: which local run is which cloud run, so nothing is sent twice
BUCKET = "session-videos"
SERVICE_KEY_HINTS = ("service_role", "sb_secret_")


class CloudError(Exception):
    """Something the person can fix: shown as is."""


def read_env(path=ENV_FILE):
    """KEY=value lines from .env (no quotes needed); values already in the environment win."""
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    values.update({k: v for k, v in os.environ.items() if k.startswith("SUPABASE_")})
    return values


def settings(path=ENV_FILE):
    """(url, anon key), checked. Refuses a service key: it would skip every access rule."""
    env = read_env(path)
    url, key = env.get("SUPABASE_URL", ""), env.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise CloudError("Set SUPABASE_URL and SUPABASE_ANON_KEY in .env (see supabase/SETUP.md step 5)")
    if any(hint in key for hint in SERVICE_KEY_HINTS) or '"role":"service_role"' in decode_jwt_role(key):
        raise CloudError("That is the service_role (secret) key. Use the anon / publishable key instead, "
                         "and rotate the secret key in Supabase if it was shared anywhere.")
    if not url.startswith("https://"):
        raise CloudError("SUPABASE_URL should start with https://")
    return url, key


def decode_jwt_role(key):
    """The payload of a JWT-style key as text (empty if it isn't one), to spot a service_role key."""
    import base64
    parts = key.split(".")
    if len(parts) != 3:
        return ""
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.dumps(json.loads(base64.urlsafe_b64decode(payload)), separators=(",", ":"))
    except (ValueError, json.JSONDecodeError):
        return ""


def connect(path=ENV_FILE):
    url, key = settings(path)
    try:
        from supabase import create_client
    except ImportError as error:
        raise CloudError("Install the library first: .venv/bin/pip install supabase") from error
    return create_client(url, key)


# ------------------------------------------------------------------ pure helpers (tested without a network)
def session_payload(row, run_id, patient_id, video_path=None):
    """A sessions.csv row as a Supabase sessions record."""
    played = datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S")
    return {"run_id": run_id, "patient_id": patient_id, "played_at": played.astimezone().isoformat(),
            "mode": row.get("mode", ""), "constellation": row.get("constellation", ""),
            "result": row.get("result", ""), "row": {k: ("" if v is None else str(v)) for k, v in row.items()},
            "video_path": video_path}


def video_path(patient_id, run_id, file_name):
    """Where a session's video goes in the bucket: the patient's id first, so the access rules can read it."""
    return f"{patient_id}/{run_id}/{os.path.basename(file_name)}"


def load_map(store):
    try:
        with open(os.path.join(store.data_dir, MAP_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_map(store, mapping):
    with open(os.path.join(store.data_dir, MAP_FILE), "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("date")]


# ------------------------------------------------------------------ talking to Supabase
def check_connection(client):
    """Reach the database as a signed-out visitor. Being refused a table (42501) is the right answer: it means
    the connection works and the access rules hold. Anything else (bad URL, bad key) is an error."""
    try:
        client.table("profiles").select("id").limit(1).execute()
    except Exception as error:
        if "42501" in str(error) or "permission denied" in str(error):
            return
        raise CloudError(f"Could not reach Supabase: {error}") from error
    raise CloudError("Signed-out visitors can read profiles: run supabase/grants.sql to lock that down")



def sign_in(client, email, password):
    try:
        answer = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as error:  # the library raises its own AuthApiError types
        raise CloudError(f"Sign-in failed: {error}") from error
    profile = client.table("profiles").select("*").eq("id", answer.user.id).single().execute().data
    return profile


def register(client, email, password, username, display_name, role, specialty="", bio=""):
    try:
        client.auth.sign_up({"email": email, "password": password, "options": {"data": {
            "username": username.lower(), "display_name": display_name, "role": role,
            "specialty": specialty, "bio": bio}}})
    except Exception as error:
        raise CloudError(f"Sign-up failed: {error}") from error


def push_runs(client, store, profile, local_patient, report=print):
    """Send a local patient's runs, sessions and videos up as the signed-in Supabase patient.
    Already-sent runs and sessions are skipped, so this is safe to run any number of times."""
    if profile["role"] != "patient":
        raise CloudError("Sign in as the patient whose runs these are")
    mapping = load_map(store)
    sent = {"runs": 0, "sessions": 0, "videos": 0}
    for run in reversed(store.runs(local_patient.id)):
        key = f"run:{run.id}"
        log, settings_path, videos = store.run_paths(run)
        progress = json.load(open(settings_path, encoding="utf-8")) if os.path.exists(settings_path) else {}
        if key not in mapping:
            created = client.table("runs").insert({"patient_id": profile["id"], "name": run.name,
                                                   "settings": progress}).execute().data[0]
            mapping[key] = created["id"]
            sent["runs"] += 1
            save_map(store, mapping)
        else:
            client.table("runs").update({"settings": progress}).eq("id", mapping[key]).execute()
        cloud_run = mapping[key]
        for row in read_rows(log):
            row_key = f"session:{run.id}:{row['date']}"
            if row_key in mapping:
                continue
            path = None
            if row.get("video") and os.path.exists(os.path.join(videos, row["video"])):
                path = video_path(profile["id"], cloud_run, row["video"])
                with open(os.path.join(videos, row["video"]), "rb") as f:
                    client.storage.from_(BUCKET).upload(path, f.read(), {"content-type": "video/mp4", "upsert": "true"})
                sent["videos"] += 1
            client.table("sessions").upsert(session_payload(row, cloud_run, profile["id"], path),
                                            on_conflict="run_id,played_at").execute()
            mapping[row_key] = True
            sent["sessions"] += 1
            save_map(store, mapping)
        report(f"  {run.name}: up to date")
    return sent


def coach_overview(client, profile):
    """A coach's patients with their session counts and latest feedback, as plain lines."""
    if profile["role"] != "coach":
        raise CloudError("Sign in as a coach")
    lines = [f"Coach {profile['display_name']} (status: {profile['status']})"]
    links = client.table("links").select("patient_id").eq("coach_id", profile["id"]).execute().data
    for link in links:
        patient = client.table("profiles").select("*").eq("id", link["patient_id"]).single().execute().data
        sessions = (client.table("sessions").select("played_at,constellation,result,video_path")
                    .eq("patient_id", patient["id"]).order("played_at", desc=True).execute().data)
        lines.append(f"- {patient['display_name']} @{patient['username']}: {len(sessions)} sessions")
        for s in sessions[:5]:
            video = "  [video]" if s["video_path"] else ""
            lines.append(f"    {s['played_at'][:16]}  {s['constellation']}  {s['result']}{video}")
    if not links:
        lines.append("No patients linked yet.")
    return lines


# ------------------------------------------------------------------ command line
def ask(prompt, secret=False):
    return (getpass.getpass if secret else input)(prompt).strip()


def main(args):
    command = args[0] if args else "check"
    try:
        client = connect()
        if command == "check":
            check_connection(client)
            print(f"Connected to {settings()[0]}")
        elif command == "register":
            role = ask("Role (patient or coach): ").lower()
            if role not in ("patient", "coach"):
                raise CloudError("Role must be patient or coach")
            email, username = ask("Email: "), ask("Username (3-20 letters, numbers or _): ")
            name = ask("Your name: ")
            specialty = ask("Specialty (coaches): ") if role == "coach" else ""
            password = ask("Password (6+ characters): ", secret=True)
            register(client, email, password, username, name, role, specialty)
            print("Account created. (If email confirmation is on, confirm it before signing in.)")
        elif command == "push":
            store = Store()
            local = store.db.execute("SELECT id FROM users WHERE username = ?", (ask("Local game username: ").lower(),)).fetchone()
            if local is None:
                raise CloudError("No local account with that username (see: python -m accounts list)")
            profile = sign_in(client, ask("Supabase email: "), ask("Supabase password: ", secret=True))
            sent = push_runs(client, store, profile, store.user(local["id"]))
            print(f"Sent {sent['runs']} runs, {sent['sessions']} sessions, {sent['videos']} videos.")
        elif command == "coach":
            profile = sign_in(client, ask("Coach email: "), ask("Password: ", secret=True))
            print("\n".join(coach_overview(client, profile)))
        elif command == "link":
            profile = sign_in(client, ask("Patient email: "), ask("Password: ", secret=True))
            coaches = client.table("profiles").select("*").eq("role", "coach").order("display_name").execute().data
            for c in coaches:
                print(f"  {c['username']:20} {c['display_name']:20} {c['status']}  {c['specialty']}")
            choice = next((c for c in coaches if c["username"] == ask("Coach username: ").lower()), None)
            if choice is None:
                raise CloudError("No coach with that username")
            if choice["status"] != "open":
                raise CloudError(f"{choice['display_name']} isn't taking new patients right now")
            client.table("links").upsert({"patient_id": profile["id"], "coach_id": choice["id"]}).execute()
            print(f"Linked to {choice['display_name']}.")
        else:
            print(__doc__)
    except CloudError as error:
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
