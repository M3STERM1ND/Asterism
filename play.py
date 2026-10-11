"""Play: the flow of the app, in six modes.

  start    - the start menu: P play (battles), R practice, E editor, T lean test, G progress;
             D changes the difficulty and A turns assisted learning on or off (both are saved)
  battle   - calibrate (seated), then turn-based battles: Orion's warm-up, then the Scorpius boss
  practice - calibrate, then draw the zodiac one constellation after another with Reach
  editor   - click stars onto the sky to craft a new constellation (no calibration needed)
  test     - calibrate, then the guided lean test (still, reach, lean) and its results
  progress - the Progress screen: charts from sessions.csv (no calibration needed)
The lean guard watches the body in every mode. Won constellations join the sky for the session.
Every finished battle and practice constellation is written to sessions.csv.
Keys: M start screen, C recalibrate, L lean guard on/off, N next, R restart, Space take the hit,
1-8 attack with a spell, B block, 0 rest (battle, your turn), H hint (assisted learning off),
1-5 answer the check-in after a battle (S skips), Enter or Space through the battle report.
"""
import os
from datetime import datetime

import numpy as np

from calibration import Calibrator
from editor import Editor
from fingers import fingertips
from game import difficulty as levels
from game.battle import BATTLES, Battle
from game.spells import newly_unlocked
from lean import LeanGuard
from lean_test import LeanTest
from lobby import Lobby
from recording import Recorder, video_name
import cloud
import progress
import therapy_report
from session_log import LOG_PATH, SessionRecord, append_row, arm_used, fill_row
from sessions.reach import Reach, load_constellation
from settings import SETTINGS_PATH, load_settings, save_settings

# The zodiac in order, starting with small, easy Aries; Orion, the player's own constellation, comes last.
PRACTICE = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpius",
            "sagittarius", "capricornus", "aquarius", "pisces", "orion"]
START_KEYS = {ord("p"): "battle", ord("r"): "practice", ord("e"): "editor", ord("t"): "test", ord("g"): "progress"}
SPELL_KEYS = {ord(str(n + 1)): n for n in range(8)}  # keys 1-8 pick the spell with that number
REST_KEY = ord("0")
FEEDBACK_SHOWN = 2   # the coach's latest notes on the start screen
FOLDER = "constellations"
EDITOR_INSET = (48, 130, 48, 120)  # editor canvas: room left, top, right, bottom for the title, hints and messages


def practice_list(folder=FOLDER):
    """The zodiac in order, then any constellations crafted in the editor, alphabetically."""
    try:
        files = os.listdir(folder)
    except OSError:
        files = []
    custom = sorted(f[:-5] for f in files if f.endswith(".json") and f[:-5] not in PRACTICE)
    return PRACTICE + custom


class Play:
    def __init__(self, size, view, settings_path=SETTINGS_PATH, log_path=LOG_PATH, store=None):
        """store: the accounts store. With one, the game opens on the lobby (log in, pick a run) and every
        run keeps its own settings, session log and videos; without one it plays straight from the given files."""
        self.size = size
        self.settings_path = settings_path
        self.log_path = log_path
        self.store = store
        self.lobby = Lobby(store) if store is not None else None
        self.run = None          # the run (save file) being played, with accounts (set before go_to_start runs)
        self.videos_dir = None   # where this run's videos go (None: no recording)
        self.recorder = Recorder()
        self.feedback = []       # the coach's latest notes for this patient, shown on the start screen
        self.cloud_feedback = []  # notes from Supabase (connected accounts), fetched when a run is chosen
        self.view = view
        self.guard = LeanGuard()
        self.level = 0
        self.sky = []  # constellations won this session: (name, star points in pixels), drawn faintly
        self.settings = load_settings(settings_path)
        self.sessions = []  # the Progress screen's data, read when it opens
        self.message = ""   # a line for the Progress screen, e.g. where the report was written
        self.go_to_start()
        if self.lobby is not None:
            self.mode = "lobby"

    def use_run(self, run):
        """Play this run from now on: its progress, its session log, its videos. Like loading a world."""
        self.recorder.cancel()
        self.run = run
        self.log_path, self.settings_path, self.videos_dir = self.store.run_paths(run)
        self.settings = load_settings(self.settings_path)
        self.sky, self.level = [], 0
        self.store.touch_run(run)
        self.fetch_cloud_feedback()
        self.go_to_start()

    def fetch_cloud_feedback(self):
        """Get the coach's notes from Supabase in the background; they show on the start screen when they arrive."""
        if self.lobby is None or self.lobby.user is None:
            return
        import threading

        def fetch(data_dir=self.store.data_dir, username=self.lobby.user.username):
            notes = cloud.coach_feedback(data_dir, username)
            if notes:
                self.cloud_feedback = notes
                if self.mode == "start":
                    self.feedback = (notes + self.feedback)[:FEEDBACK_SHOWN]
        threading.Thread(target=fetch, daemon=True).start()

    def go_to_lobby(self):
        """Back to the run list (W on the start screen), to switch runs or log out."""
        self.recorder.cancel()
        self.go_to_start()
        self.mode, self.lobby.state, self.lobby.message = "lobby", "runs", ""

    @property
    def difficulty(self):
        return levels.by_name(self.settings.difficulty)

    @property
    def assisted(self):
        return self.settings.assisted

    def new_record(self, mode, name):
        """A session record carrying the settings the player is using now."""
        return SessionRecord(mode, name, self.guard.warnings, self.difficulty.name, self.assisted,
                             arm_used(self.calibration))

    def go_to_start(self):
        """Show the start screen: nothing is calibrated or running."""
        self.recorder.cancel()  # a session left halfway has no report row, so its video goes too
        self.mode = "start"
        if self.run is not None:  # the coach may have written since: the portal shares the same database
            local = self.store.feedback_for(self.run.patient_id)[:FEEDBACK_SHOWN]
            self.store.mark_read(self.run.patient_id)
            self.feedback = (self.cloud_feedback + local)[:FEEDBACK_SHOWN]
        self.view.frozen = False
        self.calibrator = None
        self.calibration = None
        self.reach = None
        self.test = None
        self.battle = None
        self.battle_index = 0
        self.victory = False
        self.editor = None
        self.record = None  # the session being timed for sessions.csv

    def begin(self, mode):
        """Leave the start screen for a mode; every mode but the editor begins with calibration."""
        self.mode = mode
        self.battle_index = 0
        self.victory = False
        if mode == "progress":
            self.sessions = progress.recent(progress.load_sessions(self.log_path))
            self.message = ""
            return
        if mode == "editor":
            left, top, right, bottom = EDITOR_INSET
            self.editor = Editor((left, top, self.size[0] - right, self.size[1] - bottom), protected=PRACTICE)
            return
        self.recalibrate()

    def recalibrate(self):
        """Start calibration over: unfreeze the framing and put the constellation, test or battle away."""
        self.recorder.cancel()
        self.view.frozen = False
        self.calibrator = Calibrator(self.size)
        self.calibration = None
        self.reach = None
        self.test = None
        self.battle = None
        self.record = None

    def start_reach(self):
        """Begin a fresh Reach session for the current constellation in the practice list.
        A crafted file that can't be read is skipped (the built-in ones always can)."""
        names = practice_list()
        for _ in names:
            name = names[self.level % len(names)]
            try:
                constellation = load_constellation(f"{FOLDER}/{name}.json")
            except (OSError, ValueError, KeyError, TypeError) as error:
                print(f"Skipping {name}.json: {error}")
                self.level += 1
                continue
            self.reach = Reach(constellation, self.size, difficulty=self.difficulty, assisted=self.assisted)
            self.record = self.new_record("practice", self.reach.name)
            self.start_recording(self.reach.name)
            return

    def start_battle(self):
        """Begin the current battle (or show the final victory once every battle is won)."""
        if self.battle_index >= len(BATTLES):
            self.battle, self.reach, self.victory = None, None, True
            return
        config = BATTLES[self.battle_index]
        self.battle = Battle(config, self.size, self.difficulty, self.assisted, self.settings.battles_won)
        self.reach = self.battle.reach
        self.record = self.new_record("battle", config["title"])
        self.start_recording(config["title"])

    def start_recording(self, title):
        """Record this session's screen for the coach (only when playing a run)."""
        if self.videos_dir is not None:
            self.recorder.start(os.path.join(self.videos_dir, video_name(datetime.now().strftime("%Y%m%d-%H%M%S"), title)))

    def log_session(self, now, result, damage=None):
        """Write the current session to sessions.csv, once."""
        if self.record is None or self.record.logged:
            return
        self.record.logged = True
        for reach in (self.battle.casts if self.battle is not None else [self.reach]):
            self.record.absorb(reach)
        if self.battle is not None:
            for grip in self.battle.grips:
                self.record.absorb_grip(grip)
        earlier = progress.load_sessions(self.log_path)  # read before this row is added: the report compares with these
        checkin_follows = self.battle is not None
        row = self.record.row(now, self.guard.warnings, result, damage)
        row["video"] = self.recorder.stop() or ""
        self.record.date = row["date"]
        append_row(row, self.log_path)
        if self.battle is not None:
            self.battle.history, self.battle.session = earlier, progress.parse_row(row)
        if not checkin_follows:   # practice: no check-in, so upload now (battles upload after the check-in)
            self.sync_cloud()

    def save_checkin(self):
        """The patient answered how they feel: put it on this battle's row in sessions.csv, once."""
        battle = self.battle
        if battle.checkin_saved or self.record is None or self.record.date is None:
            return
        battle.checkin_saved = True
        if not battle.checkin:
            return
        fill_row(self.record.date, {k: str(v) for k, v in battle.checkin.items()}, self.log_path)
        for key, value in battle.checkin.items():
            setattr(battle.session, key, float(value))
        self.sync_cloud()

    def sync_cloud(self):
        """Send this run's new sessions and videos to Supabase in the background (only for a connected
        account, see python -m cloud connect). The game never waits for it and keeps working offline."""
        if self.run is not None and self.lobby is not None and self.lobby.user is not None:
            cloud.sync_in_background(self.store.data_dir, self.lobby.user.username)

    def calibrated(self):
        """Report the calibration in the log, then start the chosen mode."""
        c, k = self.calibration, self.calibrator
        print(f"Calibrated: reach {c.reach:.2f} shoulder widths from {c.side}, "
              f"shoulders {c.width:.0f} px wide, tilt {c.tilt:.1f} degrees | "
              f"hand seen in {k.hand_frames} of {k.sweep_frames} sweep frames, best reach "
              + ", ".join(f"{side} {best:.2f}" for side, best in k.best.items()))
        if self.mode == "practice":
            self.start_reach()
        elif self.mode == "battle":
            self.start_battle()
        else:
            self.test = LeanTest()

    def update(self, hands, pose, figure, now):
        """One frame: nothing on the start screen or in the editor; otherwise calibrate, then battle, practice or test."""
        if self.mode in ("lobby", "start", "editor", "progress"):  # screens with no calibration
            return
        if self.calibration is None:
            self.calibration = self.calibrator.update(hands, pose, figure, now, self.view)
            if self.calibration is not None:
                self.calibrated()
            return
        blocked = self.guard.update(figure, self.calibration, self.size, now)
        if self.record is not None:
            self.record.update(fingertips(hands, pose, np.array(self.size)), self.calibration, blocked, now)
        if self.mode == "test":
            self.test.update(self.guard, now)
        elif self.mode == "battle":
            self.update_battle(hands, pose, figure, now, blocked)
        else:
            self.update_practice(hands, pose, figure, now, blocked)

    def update_practice(self, hands, pose, figure, now, blocked):
        """Practice: draw constellations in turn; each one won joins the sky."""
        self.reach.update(hands, pose, figure, self.view.camera_rect(), now, self.calibration, blocked)
        if self.reach.won_at is not None:
            self.log_session(now, "completed")
        if self.reach.finished(now):
            self.sky.append((self.reach.name, self.reach.points))
            self.level += 1
            self.start_reach()

    def update_battle(self, hands, pose, figure, now, blocked):
        """Battle: run the current battle; a win adds its constellation to the sky and moves on."""
        if self.battle is None:
            return
        self.battle.update(hands, pose, figure, self.view.camera_rect(), now, self.calibration, self.guard, blocked)
        self.reach = self.battle.reach
        if self.battle.phase == "won" and not self.battle.counted:
            self.record_win()
        if self.battle.phase in ("won", "lost"):
            self.log_session(now, self.battle.phase, self.battle.enemy_max - self.battle.enemy_health)
        if self.battle.phase == "report":
            self.save_checkin()
        if self.battle.finished(now):
            self.sky.append((self.reach.name, self.reach.points))
            self.battle_index += 1
            self.start_battle()
        elif self.battle.phase == "report" and self.battle.dismissed:  # a fall: the report was read, try again
            self.start_battle()

    def record_win(self):
        """A battle was won: remember it (it unlocks spells) and note which spells are new."""
        self.battle.counted = True
        wins = max(self.settings.battles_won, self.battle_index + 1)
        self.battle.new_spells = newly_unlocked(wins) if wins > self.settings.battles_won else []
        self.settings.battles_won = wins
        save_settings(self.settings, self.settings_path)

    def typing(self):
        """True while the editor or a lobby form is taking text, so every key is a letter (Q and Esc don't quit)."""
        if self.mode == "lobby":
            return self.lobby.typing()
        return self.mode == "editor" and self.editor.typing is not None

    def handle_click(self, x, y, now, right=False):
        """Mouse clicks only matter in the editor: left places a star, right removes the last one."""
        if self.mode != "editor":
            return
        if right:
            self.editor.undo()
        else:
            self.editor.click(x, y, now)

    def handle_key(self, key, now=0.0, figure=None):
        """Start-menu choices; editor keys; then M, C, L anywhere, N/R in practice and battle, Space to take a hit."""
        if self.mode == "lobby":
            self.lobby.handle_key(key)
            run = self.lobby.take_choice()
            if run is not None:
                self.use_run(run)
            return
        if self.mode == "start":
            if key == ord("w") and self.lobby is not None:
                self.go_to_lobby()
            elif key in START_KEYS:
                self.begin(START_KEYS[key])
            elif key == ord("d"):
                self.settings.difficulty = levels.next_difficulty(self.difficulty).name
                save_settings(self.settings, self.settings_path)
            elif key == ord("a"):
                self.settings.assisted = not self.settings.assisted
                save_settings(self.settings, self.settings_path)
            return
        if self.mode == "progress":
            if key == ord("m"):
                self.go_to_start()
            elif key == ord("r"):
                written = therapy_report.generate_and_open(self.log_path)
                self.message = f"Report written to {written}" if written else "Could not write the report"
            return
        if self.mode == "editor":
            if key == ord("m") and not self.typing():
                self.go_to_start()
            else:
                self.editor.handle_key(key, now)
            return
        if key == ord("m"):
            self.go_to_start()
        elif key == ord("c"):
            self.recalibrate()
        elif key == ord("l"):
            self.guard.enabled = not self.guard.enabled
            print(f"Lean guard {'on' if self.guard.enabled else 'off'}")
        elif key == ord("t") and self.mode == "test" and self.test is not None and self.test.done:
            self.test = LeanTest()  # run the steps again with the same calibration
        elif self.calibration is None:
            return
        elif self.mode == "practice" and key == ord("h") and self.reach is not None:
            self.reach.hint(now)
        elif self.mode == "practice" and key in (ord("n"), ord("r")):
            self.level += 1 if key == ord("n") else 0
            self.start_reach()
        elif self.mode == "battle" and key in (ord("n"), ord("r")):
            self.battle_index += 1 if key == ord("n") else 0
            self.start_battle()
        elif self.mode == "battle" and self.battle is not None:
            self.battle_key(key, now, figure)

    def battle_key(self, key, now, figure):
        """Your turn: a spell (1-8), Block (B) or Rest (0); Space gives up a Block; H hint.
        After the battle: 1-5 answer the check-in (S skips it), then Enter or Space through the report."""
        if self.battle.phase == "checkin":
            if ord("1") <= key <= ord("5"):
                self.battle.answer(key - ord("0"))
            elif key == ord("s"):
                self.battle.skip_checkin()
            return
        if key in (ord(" "), 13):
            if self.battle.phase == "report":
                self.battle.dismiss()
            elif key == ord(" "):
                self.battle.lower_guard(now, figure)
        elif key == ord("b"):
            self.battle.block(now)
        elif key == ord("h") and self.battle.reach is not None and self.battle.phase == "player":
            self.battle.reach.hint(now)
        elif key in SPELL_KEYS:
            self.battle.choose(SPELL_KEYS[key], now)
        elif key == REST_KEY:
            self.battle.rest(now)
