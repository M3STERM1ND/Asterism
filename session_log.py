"""Session log: one row in sessions.csv for every finished battle or practice constellation.

Columns: date, mode, time (seconds), max reach (shoulder widths, the same unit as calibration),
lean warnings, damage dealt (battles only), which constellation and how it ended; then, for review:
difficulty, assisted (on/off), spell (the spells cast), arm used, stars hit, average error (pixels and
shoulder widths), hints used, misses, and time per star (seconds spent drawing, per star hit);
then the rehab measures (see progress.py for what each means): reach pct, straightness, tremor sw,
slowdown, grip reps, grip holds, open s; and the patient's check-in after a battle: pain, tiredness,
mood (1 to 5, filled in on the same row once answered, see fill_row).
Max reach only counts while the player is not leaning, so it measures the arm, not the body.
Older logs keep their rows: the header is extended in place (see upgrade_log).
"""
import csv
import os
from datetime import datetime

import numpy as np

LOG_PATH = "sessions.csv"
OLD_COLUMNS = ["date", "mode", "time", "max reach", "lean warnings", "damage dealt", "constellation", "result"]
NEW_COLUMNS = ["difficulty", "assisted", "spell", "arm", "stars hit", "avg error px", "avg error sw",
               "hints used", "misses", "time per star"]
REHAB_COLUMNS = ["reach pct", "straightness", "tremor sw", "slowdown", "grip reps", "grip holds", "open s",
                 "pain", "tiredness", "mood"]
COLUMNS = OLD_COLUMNS + NEW_COLUMNS + REHAB_COLUMNS + ["video"]  # video: the session's recording, in the run's videos folder
SLOWDOWN_MIN_STARS = 6   # fewer stars than this: too few to compare the start of a session with its end


def arm_used(cal):
    """"left" or "right": the player's reaching arm. The image is mirrored, so the shoulder on the
    screen's left (Betelgeuse) is the player's left."""
    if cal is None:
        return ""
    return "left" if cal.side == "Betelgeuse" else "right"


class SessionRecord:
    def __init__(self, mode, constellation, warnings_at_start, difficulty="", assisted=True, arm=""):
        self.mode = mode
        self.constellation = constellation
        self.warnings_at_start = warnings_at_start
        self.difficulty = difficulty
        self.assisted = assisted
        self.arm = arm
        self.started_at = None  # set on the first frame, like the battle's own clock
        self.max_reach = 0.0
        self.logged = False
        self.spells = []        # names of the constellations drawn, in order, without repeats
        self.errors_px, self.errors_sw = [], []
        self.hints = self.misses = 0
        self.draw_seconds = 0.0
        self.absorbed = []      # the Reach sessions already counted (by identity)
        self.straightness, self.tremor_px, self.move_seconds = [], [], []
        self.grip_reps = self.grip_holds = 0
        self.open_seconds = []
        self.calibrated_reach = None  # shoulder widths, for reach as a share of it
        self.width = None             # resting shoulder width in pixels, to put tremor in shoulder widths
        self.date = None              # the row's date once logged, so the check-in can find it

    def update(self, tips, cal, blocked, now):
        """Start the clock, and keep the farthest honest reach from the calibrated shoulder."""
        if self.started_at is None:
            self.started_at = now
        if cal is not None:
            self.calibrated_reach, self.width = cal.reach, cal.width
        if blocked or cal is None:
            return
        for tip in tips:
            self.max_reach = max(self.max_reach, float(np.hypot(*(np.array(tip) - cal.shoulder))) / cal.width)

    def absorb(self, reach):
        """Count one Reach drawing (a battle spell or a practice constellation), once, even if unfinished."""
        if reach is None or any(reach is r for r in self.absorbed):
            return
        self.absorbed.append(reach)
        if reach.lit_at and reach.name not in self.spells:
            self.spells.append(reach.name)
        self.errors_px += reach.errors_px
        self.errors_sw += reach.errors_sw
        self.hints += reach.hints
        self.misses += reach.misses
        self.draw_seconds += reach.draw_seconds()
        self.straightness += reach.straightness
        self.tremor_px += reach.tremor_px
        self.move_seconds += reach.move_seconds

    def absorb_grip(self, grip):
        """Count one Block's Grip rep: whether the hold was completed, and how long opening took."""
        if grip.result is None:
            return
        self.grip_reps += 1
        if grip.result == "block":
            self.grip_holds += 1
            if grip.open_seconds is not None:
                self.open_seconds.append(grip.open_seconds)

    def slowdown(self):
        """Fatigue: time per star in the last third of the session / the first third."""
        moves = self.move_seconds
        if len(moves) < SLOWDOWN_MIN_STARS:
            return None
        third = len(moves) // 3
        early, late = np.mean(moves[:third]), np.mean(moves[-third:])
        return float(late / early) if early > 0 else None

    def row(self, now, warnings_now, result, damage=None, date=None):
        """The CSV row for this session as it ends."""
        seconds = 0.0 if self.started_at is None else now - self.started_at
        stars = len(self.errors_px)
        return {"date": (date or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
                "mode": self.mode,
                "time": f"{seconds:.1f}",
                "max reach": f"{self.max_reach:.2f}",
                "lean warnings": warnings_now - self.warnings_at_start,
                "damage dealt": "" if damage is None else damage,
                "constellation": self.constellation,
                "result": result,
                "difficulty": self.difficulty,
                "assisted": "on" if self.assisted else "off",
                "spell": "+".join(self.spells),
                "arm": self.arm,
                "stars hit": stars,
                "avg error px": f"{np.mean(self.errors_px):.1f}" if stars else "",
                "avg error sw": f"{np.mean(self.errors_sw):.3f}" if self.errors_sw else "",
                "hints used": self.hints,
                "misses": self.misses,
                "time per star": f"{self.draw_seconds / stars:.2f}" if stars else "",
                "reach pct": (f"{100 * self.max_reach / self.calibrated_reach:.0f}"
                              if self.calibrated_reach and self.max_reach else ""),
                "straightness": f"{np.mean(self.straightness):.2f}" if self.straightness else "",
                "tremor sw": (f"{np.mean(self.tremor_px) / self.width:.3f}" if self.tremor_px and self.width else ""),
                "slowdown": "" if self.slowdown() is None else f"{self.slowdown():.2f}",
                "grip reps": self.grip_reps,
                "grip holds": self.grip_holds,
                "open s": f"{np.mean(self.open_seconds):.2f}" if self.open_seconds else "",
                "pain": "", "tiredness": "", "mood": "", "video": ""}


def upgrade_log(path=LOG_PATH):
    """Bring an older sessions.csv up to the current header in place: every existing row is kept, with
    the new columns left blank. The file is rewritten to a temporary file and swapped in, so a crash
    can't lose rows. Does nothing for a missing, empty or already-current file."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    if header == COLUMNS:
        return
    extra = [c for c in header if c not in COLUMNS]  # a column some other tool added: keep it, at the end
    columns = COLUMNS + extra
    temp = path + ".tmp"
    with open(temp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for values in rows[1:]:
            if values:
                writer.writerow(dict(zip(header, values)))
    os.replace(temp, path)


def fill_row(date, values, path=LOG_PATH):
    """Fill in cells of the row logged at `date` (the patient's check-in arrives after the row is written).
    Rewrites the file through a temporary copy. Returns True if the row was found and saved."""
    try:
        upgrade_log(path)
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            columns, rows = reader.fieldnames, list(reader)
        matches = [r for r in rows if r.get("date") == date]
        if not matches:
            return False
        matches[-1].update({k: v for k, v in values.items() if k in columns})
        temp = path + ".tmp"
        with open(temp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, path)
    except OSError as error:
        print(f"Session log: could not update {path}: {error}")
        return False
    return True


def append_row(row, path=LOG_PATH):
    """Add one row to the log, writing the header first if the file is new. Returns True if it was written."""
    try:
        upgrade_log(path)
        is_new = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except OSError as error:  # a locked file (open in Excel) must not stop the game
        print(f"Session log: could not write {path}: {error}")
        return False
    print(f"Session log: {row['mode']} {row['constellation']} {row['result']} in {row['time']} s")
    return True
