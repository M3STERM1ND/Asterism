"""Play: the flow of the app, in five modes.

  start    - the start menu: P play (battles), R practice, E editor, T lean test
  battle   - calibrate (seated), then turn-based battles: Orion's warm-up, then the Scorpius boss
  practice - calibrate, then draw the zodiac one constellation after another with Reach
  editor   - click stars onto the sky to craft a new constellation (no calibration needed)
  test     - calibrate, then the guided lean test (still, reach, lean) and its results
The lean guard watches the body in every mode. Won constellations join the sky for the session.
Every finished battle and practice constellation is written to sessions.csv.
Keys: M start screen, C recalibrate, L lean guard on/off, N next, R restart, Space take the hit.
"""
import os

import numpy as np

from calibration import Calibrator
from editor import Editor
from fingers import fingertips
from game.battle import BATTLES, Battle
from lean import LeanGuard
from lean_test import LeanTest
from session_log import SessionRecord, append_row
from sessions.reach import Reach, load_constellation

# The zodiac in order, starting with small, easy Aries; Orion, the player's own constellation, comes last.
PRACTICE = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpius",
            "sagittarius", "capricornus", "aquarius", "pisces", "orion"]
START_KEYS = {ord("p"): "battle", ord("r"): "practice", ord("e"): "editor", ord("t"): "test"}
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
    def __init__(self, size, view):
        self.size = size
        self.view = view
        self.guard = LeanGuard()
        self.level = 0
        self.sky = []  # constellations won this session: (name, star points in pixels), drawn faintly
        self.go_to_start()

    def go_to_start(self):
        """Show the start screen: nothing is calibrated or running."""
        self.mode = "start"
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
        if mode == "editor":
            left, top, right, bottom = EDITOR_INSET
            self.editor = Editor((left, top, self.size[0] - right, self.size[1] - bottom), protected=PRACTICE)
            return
        self.recalibrate()

    def recalibrate(self):
        """Start calibration over: unfreeze the framing and put the constellation, test or battle away."""
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
            self.reach = Reach(constellation, self.size)
            self.record = SessionRecord("practice", self.reach.name, self.guard.warnings)
            return

    def start_battle(self):
        """Begin the current battle (or show the final victory once every battle is won)."""
        if self.battle_index >= len(BATTLES):
            self.battle, self.reach, self.victory = None, None, True
            return
        self.battle = Battle(BATTLES[self.battle_index], self.size)
        self.reach = self.battle.reach
        self.record = SessionRecord("battle", self.reach.name, self.guard.warnings)

    def log_session(self, now, result, damage=None):
        """Write the current session to sessions.csv, once."""
        if self.record is None or self.record.logged:
            return
        self.record.logged = True
        append_row(self.record.row(now, self.guard.warnings, result, damage))

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
        if self.mode in ("start", "editor"):
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
        if self.battle.phase in ("won", "lost"):
            self.log_session(now, self.battle.phase, self.battle.enemy_max - self.battle.enemy_health)
        if self.battle.finished(now):
            self.sky.append((self.reach.name, self.reach.points))
            self.battle_index += 1
            self.start_battle()

    def typing(self):
        """True while the editor is taking a name, so every key is a letter (Q and Esc don't quit)."""
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
        if self.mode == "start":
            if key in START_KEYS:
                self.begin(START_KEYS[key])
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
        elif self.mode == "practice" and key in (ord("n"), ord("r")):
            self.level += 1 if key == ord("n") else 0
            self.start_reach()
        elif self.mode == "battle" and key in (ord("n"), ord("r")):
            self.battle_index += 1 if key == ord("n") else 0
            self.start_battle()
        elif self.mode == "battle" and key == ord(" ") and self.battle is not None:
            self.battle.skip_block(now, figure)
