"""Accounts, runs, coach links and feedback; the in-game lobby; recording; and the portal over HTTP.
Run: .venv/bin/python -m unittest"""
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

import numpy as np

import portal
from accounts import AccountError, Store
from lobby import Lobby
from recording import Recorder, video_name


def new_store():
    return Store(tempfile.mkdtemp())


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.store = new_store()
        self.pat = self.store.register("pat", "secret1", "patient", "Pat")
        self.coach = self.store.register("dr_lee", "secret2", "coach", "Dr Lee", "Upper limb", "Stroke rehab")

    def test_register_and_login(self):
        self.assertEqual(self.store.login("PAT", "secret1"), self.pat)
        self.assertIsNone(self.store.login("pat", "wrong!!"))
        self.assertIsNone(self.store.login("nobody", "secret1"))

    def test_passwords_are_hashed_not_stored(self):
        row = self.store.db.execute("SELECT password_hash FROM users WHERE id = ?", (self.pat.id,)).fetchone()
        self.assertNotIn("secret1", row[0])

    def test_a_forgotten_password_can_be_replaced_not_read(self):
        token = self.store.new_token(self.pat)
        self.store.set_password("PAT", "brand-new")
        self.assertIsNone(self.store.login("pat", "secret1"))
        self.assertEqual(self.store.login("pat", "brand-new"), self.pat)
        self.assertIsNone(self.store.user_for_token(token))  # signed out everywhere
        with self.assertRaises(AccountError):
            self.store.set_password("nobody", "brand-new")
        with self.assertRaises(AccountError):
            self.store.set_password("pat", "123")

    def test_bad_registrations_explain_themselves(self):
        for args, words in ((("pat", "secret9", "patient"), "taken"), (("x", "secret9", "patient"), "Username"),
                            (("newone", "123", "patient"), "Password"), (("newtwo", "secret9", "admin"), "patient or coach")):
            with self.assertRaises(AccountError) as caught:
                self.store.register(*args)
            self.assertIn(words, str(caught.exception))

    def test_patients_link_only_to_open_coaches(self):
        self.store.set_status(self.coach, "closed")
        with self.assertRaises(AccountError):
            self.store.link(self.pat, self.coach.id)
        self.store.set_status(self.coach, "open")
        self.assertEqual(self.store.link(self.pat, self.coach.id).id, self.coach.id)
        self.assertEqual(self.store.coach_of(self.pat).id, self.coach.id)
        self.assertEqual([p.id for p in self.store.patients_of(self.coach)], [self.pat.id])

    def test_closing_keeps_current_patients(self):
        self.store.link(self.pat, self.coach.id)
        closed = self.store.set_status(self.coach, "closed")
        self.assertEqual(self.store.coach_of(self.pat).id, closed.id)
        self.assertEqual(self.store.link(self.pat, closed.id).id, closed.id)  # already linked: no error

    def test_one_coach_at_a_time_and_unlink(self):
        other = self.store.register("dr_kim", "secret3", "coach", "Dr Kim")
        self.store.link(self.pat, self.coach.id)
        self.store.link(self.pat, other.id)
        self.assertEqual(self.store.coach_of(self.pat).id, other.id)
        self.assertEqual(self.store.patients_of(self.coach), [])
        self.store.unlink(self.pat)
        self.assertIsNone(self.store.coach_of(self.pat))

    def test_only_patients_link_and_only_to_coaches(self):
        with self.assertRaises(AccountError):
            self.store.link(self.coach, self.coach.id)
        other = self.store.register("pat2", "secret4", "patient")
        with self.assertRaises(AccountError):
            self.store.link(self.pat, other.id)

    def test_who_can_see_whom(self):
        stranger = self.store.register("dr_x", "secret5", "coach")
        self.store.link(self.pat, self.coach.id)
        self.assertTrue(self.store.can_view(self.pat, self.pat.id))
        self.assertTrue(self.store.can_view(self.coach, self.pat.id))
        self.assertFalse(self.store.can_view(stranger, self.pat.id))
        self.assertFalse(self.store.can_view(None, self.pat.id))

    def test_runs_are_separate_save_files_most_recent_first(self):
        first = self.store.create_run(self.pat, "First world")
        second = self.store.create_run(self.pat, "Second world")
        self.store.touch_run(first)
        self.assertEqual([r.name for r in self.store.runs(self.pat.id)], ["First world", "Second world"])
        a, b = self.store.run_paths(first), self.store.run_paths(second)
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.isdir(a[2]))
        with self.assertRaises(AccountError):
            self.store.create_run(self.coach, "nope")

    def test_feedback_only_from_the_patients_coach(self):
        with self.assertRaises(AccountError):
            self.store.add_feedback(self.coach, self.pat.id, "Nice work")
        self.store.link(self.pat, self.coach.id)
        run = self.store.create_run(self.pat, "Run")
        self.store.add_feedback(self.coach, self.pat.id, "Keep your shoulders level", run.id)
        notes = self.store.feedback_for(self.pat.id, unread_only=True)
        self.assertEqual((notes[0].text, notes[0].coach_name, notes[0].run_id), ("Keep your shoulders level", "Dr Lee", run.id))
        self.store.mark_read(self.pat.id)
        self.assertEqual(self.store.feedback_for(self.pat.id, unread_only=True), [])
        with self.assertRaises(AccountError):
            self.store.add_feedback(self.coach, self.pat.id, "   ")

    def test_earlier_data_is_imported_once(self):
        folder = tempfile.mkdtemp()
        log = os.path.join(folder, "sessions.csv")
        with open(log, "w") as f:
            f.write("date,mode\n2026-10-10 10:00:00,battle\n")
        run = self.store.import_legacy(self.pat, log, os.path.join(folder, "none.json"))
        self.assertEqual(run.name, "Before accounts")
        self.assertTrue(open(self.store.run_paths(run)[0]).read().startswith("date,mode"))
        self.assertIsNone(self.store.import_legacy(self.pat, log))

    def test_portal_tokens(self):
        token = self.store.new_token(self.pat)
        self.assertEqual(self.store.user_for_token(token), self.pat)
        self.store.drop_token(token)
        self.assertIsNone(self.store.user_for_token(token))
        self.assertIsNone(self.store.user_for_token(""))


def type_text(lobby, text):
    for ch in text:
        lobby.handle_key(ord(ch))


class LobbyTest(unittest.TestCase):
    def test_register_create_a_run_and_pick_it(self):
        store = new_store()
        lobby = Lobby(store)
        lobby.handle_key(ord("n"))
        self.assertTrue(lobby.typing())
        type_text(lobby, "sam")
        lobby.handle_key(13)
        type_text(lobby, "Sam q")  # q is a letter while typing
        lobby.handle_key(9)
        type_text(lobby, "hunter22")
        lobby.handle_key(13)
        self.assertEqual((lobby.state, lobby.user.display_name), ("runs", "Sam q"))
        lobby.handle_key(ord("n"))
        type_text(lobby, "Week one")
        lobby.handle_key(13)
        run = lobby.take_choice()
        self.assertEqual(run.name, "Week one")
        lobby.handle_key(ord("1"))
        self.assertEqual(lobby.take_choice().id, run.id)

    def test_wrong_password_and_coaches_are_turned_away(self):
        store = new_store()
        store.register("sam", "hunter22", "patient")
        store.register("dr_lee", "hunter22", "coach")
        for name, password, words in (("sam", "nope000", "Wrong"), ("dr_lee", "hunter22", "coach portal")):
            lobby = Lobby(store)
            lobby.handle_key(ord("l"))
            type_text(lobby, name)
            lobby.handle_key(13)
            type_text(lobby, password)
            lobby.handle_key(13)
            self.assertIsNone(lobby.user)
            self.assertIn(words, lobby.message)

    def test_backspace_escape_and_log_out(self):
        store = new_store()
        store.register("sam", "hunter22", "patient")
        lobby = Lobby(store)
        lobby.handle_key(ord("l"))
        type_text(lobby, "samx")
        lobby.handle_key(127)
        self.assertEqual(lobby.values["username"], "sam")
        lobby.handle_key(27)
        self.assertEqual(lobby.state, "welcome")
        lobby.handle_key(ord("l"))
        type_text(lobby, "sam")
        lobby.handle_key(13)
        type_text(lobby, "hunter22")
        lobby.handle_key(13)
        lobby.handle_key(ord("o"))
        self.assertEqual((lobby.state, lobby.user), ("welcome", None))


class PlayRunTest(unittest.TestCase):
    def test_each_run_keeps_its_own_progress(self):
        from play import Play
        from tests.test_play import FakeView
        store = new_store()
        pat = store.register("sam", "hunter22", "patient")
        a, b = store.create_run(pat, "A"), store.create_run(pat, "B")
        p = Play((1280, 720), FakeView(), store=store)
        self.assertEqual(p.mode, "lobby")
        p.update([], None, None, 0.0)  # a frame in the lobby: nothing to calibrate (this used to crash)
        p.lobby.user = pat
        p.use_run(a)
        p.settings.battles_won = 3
        from settings import save_settings
        save_settings(p.settings, p.settings_path)
        p.use_run(b)
        self.assertEqual(p.settings.battles_won, 0)   # a new world starts fresh
        p.use_run(a)
        self.assertEqual(p.settings.battles_won, 3)   # an old world keeps its progress
        self.assertEqual(p.log_path, store.run_paths(a)[0])
        coach = store.register("amy", "hunter22", "coach")
        store.link(pat, coach.id)
        store.add_feedback(coach, pat.id, "Written in the portal while the game is open")
        p.handle_key(ord("g"))  # to the Progress screen...
        p.handle_key(ord("m"))  # ...and back to the start screen: the new note shows
        self.assertEqual([n.text for n in p.feedback], ["Written in the portal while the game is open"])
        p.handle_key(ord("w"))
        self.assertEqual((p.mode, p.lobby.state), ("lobby", "runs"))


class RecordingTest(unittest.TestCase):
    def test_a_video_is_written_and_cancel_removes_it(self):
        folder = tempfile.mkdtemp()
        rec = Recorder()
        path = os.path.join(folder, "videos", video_name("20261010-161900", "Scorpius!"))
        self.assertTrue(rec.start(path))
        for i in range(20):
            rec.write(np.full((720, 1280, 3), i * 10, np.uint8))
        self.assertEqual(rec.stop(), "20261010-161900-scorpius.mp4")
        self.assertGreater(os.path.getsize(path), 0)
        rec.start(path + "2.mp4")
        rec.cancel()
        self.assertFalse(os.path.exists(path + "2.mp4"))
        self.assertIsNone(rec.stop())


class PortalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = new_store()
        portal.Portal.store = cls.store
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), portal.Portal)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def browser(self):
        # ProxyHandler({}): skip macOS's system proxy lookup, which adds about a second to every local request
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(CookieJar()))

    def post(self, b, path, **fields):
        return b.open(self.base + path, urllib.parse.urlencode(fields).encode()).read().decode()

    def get(self, b, path):
        return b.open(self.base + path).read().decode()

    def test_the_whole_coach_and_patient_journey(self):
        coach, patient, stranger = self.browser(), self.browser(), self.browser()
        page = self.post(coach, "/register", role="coach", username="dr_web", password="secret1",
                         display_name="Dr Web", specialty="Stroke rehab")
        self.assertIn("Coach dashboard", page)
        self.post(patient, "/register", role="patient", username="pat_web", password="secret1", display_name="Pat Web")
        self.post(stranger, "/register", role="coach", username="dr_other", password="secret1", display_name="Dr Other")
        self.post(stranger, "/coach/status", status="closed")
        home = self.get(patient, "/me")
        self.assertIn("Link to Dr Web", home)
        self.assertIn("Not taking patients", home)        # the closed coach can't be linked
        dr_other = self.store.login("dr_other", "secret1")
        refused = self.post(patient, "/link", coach=dr_other.id)
        self.assertIn("isn&#x27;t taking new patients", refused)
        dr_web = self.store.login("dr_web", "secret1")
        self.assertIn("Linked to Dr Web", self.post(patient, "/link", coach=dr_web.id))
        pat = self.store.login("pat_web", "secret1")
        run = self.store.create_run(pat, "World one")
        videos = self.store.run_paths(run)[2]
        with open(os.path.join(videos, "20261010-100000-warm-up.mp4"), "wb") as f:
            f.write(b"0123456789")
        self.assertIn("Pat Web", self.get(coach, "/coach"))
        detail = self.get(coach, f"/patient?id={pat.id}&run={run.id}")
        self.assertIn("World one", detail)
        self.assertIn("video", detail)
        self.assertIn("Write feedback", detail)
        self.assertIn("Home rehab report", self.get(coach, f"/report?patient={pat.id}&run=all"))
        self.assertIn("Feedback sent", self.post(coach, "/feedback", patient=pat.id, run=run.id, text="Great reach today <3"))
        self.assertIn("Great reach today &lt;3", self.get(patient, "/me"))
        ranged = urllib.request.Request(f"{self.base}/video?run={run.id}&file=20261010-100000-warm-up.mp4", headers={"Range": "bytes=2-5"})
        response = coach.open(ranged)
        self.assertEqual((response.status, response.read()), (206, b"2345"))
        for path in (f"/patient?id={pat.id}", f"/report?patient={pat.id}&run=all",
                     f"/video?run={run.id}&file=20261010-100000-warm-up.mp4", f"/video?run={run.id}&file=../../asterism.db"):
            with self.assertRaises(urllib.error.HTTPError) as denied:
                self.get(stranger, path)
            self.assertEqual(denied.exception.code, 403)

    def test_logged_out_visitors_see_the_login_page(self):
        b = self.browser()
        self.assertIn("Create an account", self.get(b, "/coach"))
        self.assertIn("Wrong username", self.post(b, "/login", username="nobody", password="secret1"))


if __name__ == "__main__":
    unittest.main()


class FakeCloud:
    """Stands in for cloud.GameCloud: remembers sign-ups, signs in by email."""
    def __init__(self):
        self.people = {}

    def sign_up(self, store, email, password, username, name):
        self.people[email] = (password, username, name)
        return store.register(username, password, "patient", name)

    def sign_in(self, store, email, password):
        if self.people.get(email, ("",))[0] != password:
            raise AccountError("Wrong email or password, or no internet")
        _, username, name = self.people[email]
        row = store.db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return store.user(row["id"]) if row else store.register(username, password, "patient", name)


class CloudLobbyTest(unittest.TestCase):
    def test_sign_up_asks_for_an_email_and_logs_in_anywhere(self):
        fake = FakeCloud()
        lobby = Lobby(new_store(), fake)
        lobby.handle_key(ord("n"))
        self.assertEqual([f[0] for f in lobby.fields()], ["email", "username", "name", "password"])
        for value in ("ana@example.com", "ana", "Ana", "hunter22"):
            type_text(lobby, value)
            lobby.handle_key(13)
        self.assertEqual((lobby.state, lobby.user.username), ("runs", "ana"))
        other_computer = Lobby(new_store(), fake)
        other_computer.handle_key(ord("l"))
        type_text(other_computer, "ana@example.com")
        other_computer.handle_key(13)
        type_text(other_computer, "hunter22")
        other_computer.handle_key(13)
        self.assertEqual(other_computer.user.username, "ana")

    def test_without_supabase_the_forms_stay_local(self):
        lobby = Lobby(new_store())
        lobby.handle_key(ord("n"))
        self.assertEqual([f[0] for f in lobby.fields()], ["username", "name", "password"])
