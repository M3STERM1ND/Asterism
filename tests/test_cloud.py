"""Cloud: settings checks, the session payload, and pushing runs without sending anything twice (fake Supabase).
Run: .venv/bin/python -m unittest"""
import base64
import json
import os
import tempfile
import unittest

import cloud
from accounts import Store
from session_log import SessionRecord, append_row


def env_file(text):
    path = os.path.join(tempfile.mkdtemp(), ".env")
    with open(path, "w") as f:
        f.write(text)
    return path


def jwt(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{body}.sig"


class SettingsTest(unittest.TestCase):
    def test_reads_url_and_anon_key(self):
        path = env_file('SUPABASE_URL=https://abc.supabase.co\nSUPABASE_ANON_KEY="' + jwt({"role": "anon"}) + '"\n')
        url, key = cloud.settings(path)
        self.assertEqual(url, "https://abc.supabase.co")
        self.assertTrue(key.startswith("eyJ"))

    def test_refuses_a_service_role_key(self):
        for key in (jwt({"role": "service_role"}), "sb_secret_abc123"):
            with self.assertRaises(cloud.CloudError) as caught:
                cloud.settings(env_file(f"SUPABASE_URL=https://abc.supabase.co\nSUPABASE_ANON_KEY={key}\n"))
            self.assertIn("service_role", str(caught.exception))

    def test_missing_or_insecure_settings(self):
        with self.assertRaises(cloud.CloudError):
            cloud.settings(env_file(""))
        with self.assertRaises(cloud.CloudError):
            cloud.settings(env_file("SUPABASE_URL=http://abc.supabase.co\nSUPABASE_ANON_KEY=sb_publishable_x\n"))


class Fake:
    """Just enough of the Supabase client: table inserts/updates/upserts and storage uploads, recorded."""

    def __init__(self):
        self.rows = {"runs": [], "sessions": []}
        self.uploads = []
        self.storage = self

    def from_(self, bucket):
        self.bucket = bucket
        return self

    def upload(self, path, data, options):
        self.uploads.append((self.bucket, path, len(data)))

    def table(self, name):
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, fake, name):
        self.fake, self.name, self.action = fake, name, None

    def insert(self, record):
        record = dict(record, id=f"{self.name}-{len(self.fake.rows[self.name]) + 1}")
        self.fake.rows[self.name].append(record)
        self.result = [record]
        return self

    def upsert(self, record, on_conflict=None):
        rows = self.fake.rows[self.name]
        rows[:] = [r for r in rows if not (r["run_id"] == record["run_id"] and r["played_at"] == record["played_at"])]
        rows.append(record)
        self.result = [record]
        return self

    def update(self, values):
        self.result = []
        return self

    def eq(self, *args):
        return self

    def execute(self):
        return type("Answer", (), {"data": self.result})()


class PushTest(unittest.TestCase):
    def test_runs_sessions_and_videos_go_up_once(self):
        store = Store(tempfile.mkdtemp())
        pat = store.register("sam", "hunter22", "patient", "Sam")
        run = store.create_run(pat, "World one")
        log, _, videos = store.run_paths(run)
        row = SessionRecord("battle", "Warm-up", 0).row(10.0, 0, "won")
        row["video"] = "clip.mp4"
        with open(os.path.join(videos, "clip.mp4"), "wb") as f:
            f.write(b"mp4data")
        append_row(row, log)
        fake = Fake()
        profile = {"id": "uuid-sam", "role": "patient"}
        sent = cloud.push_runs(fake, store, profile, pat, report=lambda line: None)
        self.assertEqual(sent, {"runs": 1, "sessions": 1, "videos": 1})
        session = fake.rows["sessions"][0]
        self.assertEqual((session["patient_id"], session["run_id"], session["row"]["constellation"]),
                         ("uuid-sam", "runs-1", "Warm-up"))
        self.assertEqual(fake.uploads, [("session-videos", "uuid-sam/runs-1/clip.mp4", 7)])
        again = cloud.push_runs(fake, store, profile, pat, report=lambda line: None)
        self.assertEqual(again, {"runs": 0, "sessions": 0, "videos": 0})   # nothing twice

    def test_only_a_patient_can_push(self):
        store = Store(tempfile.mkdtemp())
        pat = store.register("sam", "hunter22", "patient")
        with self.assertRaises(cloud.CloudError):
            cloud.push_runs(Fake(), store, {"id": "x", "role": "coach"}, pat)

    def test_video_paths_start_with_the_patient(self):
        self.assertEqual(cloud.video_path("p1", "r1", "../../x.mp4"), "p1/r1/x.mp4")


if __name__ == "__main__":
    unittest.main()
