"""Accounts: patients, coaches, coach links, runs (save files) and coach feedback, in one SQLite file.

  users     - a patient or a coach. Coaches have a bio, a specialty and a status: "open" (taking new
              patients) or "closed". Passwords are stored as salted PBKDF2 hashes, never as text.
  links     - each patient has at most one coach; a patient can only link to a coach whose status is open.
  runs      - a patient's save files, like worlds in Minecraft: each run has its own folder with its own
              progress (settings.json), session log (sessions.csv) and recorded videos. A patient picks an
              existing run to keep adding to it, or starts a new one.
  feedback  - notes a coach writes for one of their linked patients (optionally about one run).
  tokens    - sign-ins for the coach portal (portal.py).
A coach can only see the patients linked to them; a patient only sees their own data.
The tables are laid out so they move to Supabase (Postgres) one-to-one later.
"""
import hashlib
import hmac
import os
import re
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime

DATA_DIR = "data"
DB_NAME = "asterism.db"
ROLES = ("patient", "coach")
STATUSES = ("open", "closed")
USERNAME = re.compile(r"^[a-z0-9_]{3,20}$")
MIN_PASSWORD = 6
HASH_ROUNDS = 200_000
MAX_FEEDBACK = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('patient', 'coach')),
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    specialty TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    patient_id INTEGER PRIMARY KEY REFERENCES users(id),
    coach_id INTEGER NOT NULL REFERENCES users(id),
    linked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_played TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    coach_id INTEGER NOT NULL REFERENCES users(id),
    patient_id INTEGER NOT NULL REFERENCES users(id),
    run_id INTEGER REFERENCES runs(id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
"""


class AccountError(Exception):
    """Something the person can fix: shown to them as is."""


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: str
    bio: str = ""
    specialty: str = ""
    status: str = "open"


@dataclass(frozen=True)
class Run:
    id: int
    patient_id: int
    name: str
    created_at: str
    last_played: str | None


@dataclass(frozen=True)
class Feedback:
    id: int
    coach_id: int
    coach_name: str
    patient_id: int
    run_id: int | None
    text: str
    created_at: str
    read_at: str | None


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), HASH_ROUNDS).hex()


class Store:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        os.makedirs(os.path.join(data_dir, "runs"), exist_ok=True)
        self.db = sqlite3.connect(os.path.join(data_dir, DB_NAME), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # --- users
    def register(self, username, password, role, display_name="", bio="", specialty=""):
        """Create an account. Raises AccountError with a reason the person can fix."""
        username = username.strip().lower()
        if not USERNAME.match(username):
            raise AccountError("Username: 3 to 20 letters, numbers or _")
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"Password: at least {MIN_PASSWORD} characters")
        if role not in ROLES:
            raise AccountError("Choose patient or coach")
        if self.db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise AccountError("That username is taken")
        salt = secrets.token_hex(16)
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO users (username, display_name, role, password_hash, salt, bio, specialty, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (username, (display_name or username).strip()[:40], role, hash_password(password, salt), salt,
                 bio.strip()[:500], specialty.strip()[:80], now()))
        return self.user(cursor.lastrowid)

    def login(self, username, password):
        """The user if the username and password match, else None."""
        row = self.db.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        if row is None or not hmac.compare_digest(row["password_hash"], hash_password(password, row["salt"])):
            return None
        return self.to_user(row)

    def set_password(self, username, password):
        """Give an account a new password (the old one can't be read back, only replaced)."""
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"Password: at least {MIN_PASSWORD} characters")
        salt = secrets.token_hex(16)
        with self.db:
            changed = self.db.execute("UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                                      (hash_password(password, salt), salt, username.strip().lower())).rowcount
            self.db.execute("DELETE FROM tokens WHERE user_id = (SELECT id FROM users WHERE username = ?)",
                            (username.strip().lower(),))  # sign out of the portal everywhere
        if not changed:
            raise AccountError(f"No account called {username}")

    def user(self, user_id):
        row = self.db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return None if row is None else self.to_user(row)

    @staticmethod
    def to_user(row):
        return User(row["id"], row["username"], row["display_name"], row["role"], row["bio"], row["specialty"], row["status"])

    def coaches(self):
        """The coach catalog: every coach, open ones first."""
        rows = self.db.execute("SELECT * FROM users WHERE role = 'coach' ORDER BY status = 'closed', display_name")
        return [self.to_user(r) for r in rows]

    def set_status(self, coach, status):
        if coach.role != "coach":
            raise AccountError("Only coaches have a status")
        if status not in STATUSES:
            raise AccountError("Status is open or closed")
        with self.db:
            self.db.execute("UPDATE users SET status = ? WHERE id = ?", (status, coach.id))
        return self.user(coach.id)

    def update_profile(self, coach, bio, specialty):
        with self.db:
            self.db.execute("UPDATE users SET bio = ?, specialty = ? WHERE id = ?",
                            (bio.strip()[:500], specialty.strip()[:80], coach.id))
        return self.user(coach.id)

    # --- links
    def link(self, patient, coach_id):
        """Link a patient to a coach. Only open coaches take new patients; a patient has one coach."""
        coach = self.user(coach_id)
        if patient.role != "patient":
            raise AccountError("Only patients link to a coach")
        if coach is None or coach.role != "coach":
            raise AccountError("That coach doesn't exist")
        current = self.coach_of(patient)
        if current is not None and current.id == coach.id:
            return coach
        if coach.status != "open":
            raise AccountError(f"{coach.display_name} isn't taking new patients right now")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO links (patient_id, coach_id, linked_at) VALUES (?, ?, ?)",
                            (patient.id, coach.id, now()))
        return coach

    def unlink(self, patient):
        with self.db:
            self.db.execute("DELETE FROM links WHERE patient_id = ?", (patient.id,))

    def coach_of(self, patient):
        row = self.db.execute("SELECT coach_id FROM links WHERE patient_id = ?", (patient.id,)).fetchone()
        return None if row is None else self.user(row["coach_id"])

    def patients_of(self, coach):
        rows = self.db.execute("SELECT u.* FROM users u JOIN links l ON l.patient_id = u.id WHERE l.coach_id = ?"
                               " ORDER BY u.display_name", (coach.id,))
        return [self.to_user(r) for r in rows]

    def can_view(self, viewer, patient_id):
        """A patient sees their own data; a coach sees their linked patients'."""
        if viewer is None:
            return False
        if viewer.role == "patient":
            return viewer.id == patient_id
        row = self.db.execute("SELECT 1 FROM links WHERE patient_id = ? AND coach_id = ?", (patient_id, viewer.id))
        return row.fetchone() is not None

    # --- runs (save files)
    def create_run(self, patient, name):
        name = name.strip()[:30] or "New run"
        if patient.role != "patient":
            raise AccountError("Only patients have runs")
        with self.db:
            cursor = self.db.execute("INSERT INTO runs (patient_id, name, created_at) VALUES (?, ?, ?)",
                                     (patient.id, name, now()))
        run = self.run(cursor.lastrowid)
        os.makedirs(os.path.join(self.run_dir(run), "videos"), exist_ok=True)
        return run

    def runs(self, patient_id):
        """A patient's runs, most recently played first."""
        rows = self.db.execute("SELECT * FROM runs WHERE patient_id = ?"
                               " ORDER BY COALESCE(last_played, created_at) DESC, last_played IS NOT NULL DESC, id DESC", (patient_id,))
        return [Run(**dict(r)) for r in rows]

    def run(self, run_id):
        row = self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else Run(**dict(row))

    def touch_run(self, run):
        with self.db:
            self.db.execute("UPDATE runs SET last_played = ? WHERE id = ?", (now(), run.id))

    def run_dir(self, run):
        return os.path.join(self.data_dir, "runs", str(run.id))

    def run_paths(self, run):
        """(sessions.csv, settings.json, videos folder) for a run."""
        folder = self.run_dir(run)
        return (os.path.join(folder, "sessions.csv"), os.path.join(folder, "settings.json"),
                os.path.join(folder, "videos"))

    def import_legacy(self, patient, log_path="sessions.csv", settings_path="settings.json"):
        """Bring data from before accounts existed into a new run, once. Returns the run, or None if there was none."""
        if not os.path.exists(log_path):
            return None
        marker = os.path.join(self.data_dir, "legacy_imported")
        if os.path.exists(marker):
            return None
        run = self.create_run(patient, "Before accounts")
        log, settings, _ = self.run_paths(run)
        shutil.copyfile(log_path, log)
        if os.path.exists(settings_path):
            shutil.copyfile(settings_path, settings)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"imported into run {run.id} for {patient.username} at {now()}\n")
        return run

    # --- feedback
    def add_feedback(self, coach, patient_id, text, run_id=None):
        text = text.strip()
        if coach.role != "coach" or not self.can_view(coach, patient_id):
            raise AccountError("You can only write to your own patients")
        if not text:
            raise AccountError("Write something first")
        if run_id is not None:
            run = self.run(run_id)
            if run is None or run.patient_id != patient_id:
                raise AccountError("That run isn't this patient's")
        with self.db:
            self.db.execute("INSERT INTO feedback (coach_id, patient_id, run_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
                            (coach.id, patient_id, run_id, text[:MAX_FEEDBACK], now()))

    def feedback_for(self, patient_id, unread_only=False):
        """Feedback for a patient, newest first."""
        rows = self.db.execute(
            "SELECT f.*, u.display_name AS coach_name FROM feedback f JOIN users u ON u.id = f.coach_id"
            " WHERE f.patient_id = ?" + (" AND f.read_at IS NULL" if unread_only else "") + " ORDER BY f.id DESC",
            (patient_id,))
        return [Feedback(r["id"], r["coach_id"], r["coach_name"], r["patient_id"], r["run_id"], r["text"],
                         r["created_at"], r["read_at"]) for r in rows]

    def mark_read(self, patient_id):
        with self.db:
            self.db.execute("UPDATE feedback SET read_at = ? WHERE patient_id = ? AND read_at IS NULL", (now(), patient_id))

    # --- portal sign-ins
    def new_token(self, user):
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("INSERT INTO tokens (token, user_id, created_at) VALUES (?, ?, ?)", (token, user.id, now()))
        return token

    def user_for_token(self, token):
        if not token:
            return None
        row = self.db.execute("SELECT user_id FROM tokens WHERE token = ?", (token,)).fetchone()
        return None if row is None else self.user(row["user_id"])

    def drop_token(self, token):
        with self.db:
            self.db.execute("DELETE FROM tokens WHERE token = ?", (token,))


def main(args):
    """Command line:  .venv/bin/python -m accounts list            the accounts (no passwords: they're hashed)
                      .venv/bin/python -m accounts reset USERNAME  type a new password for USERNAME
    Add --data demo_data to use the demo accounts instead of data/."""
    import getpass
    data = args[args.index("--data") + 1] if "--data" in args else DATA_DIR
    args = [a for a in args if a not in ("--data", data)]
    store = Store(data)
    if args[:1] == ["reset"] and len(args) == 2:
        first = getpass.getpass(f"New password for {args[1]}: ")
        if first != getpass.getpass("Type it again: "):
            print("The two didn't match. Nothing changed.")
            return
        try:
            store.set_password(args[1], first)
            print(f"Password changed for {args[1]}.")
        except AccountError as error:
            print(error)
    else:
        for row in store.db.execute("SELECT username, display_name, role, status FROM users ORDER BY role, username"):
            status = f" ({row['status']})" if row["role"] == "coach" else ""
            print(f"{row['username']:20} {row['display_name']:20} {row['role']}{status}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
