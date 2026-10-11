"""Progress: reads sessions.csv and turns it into the numbers the Progress screen, the battle report and
the therapist report use. Pure logic, no drawing. Missing or blank values (older rows) are skipped.

METRICS is the one list of rehab measures, so every screen and report means the same thing by each:
  active reach  - farthest honest reach (not leaning) from the shoulder, in shoulder widths: the trend to watch
  range used    - that reach as a share of the day's calibrated reach (did the game use the range measured today?)
  accuracy      - average distance from fingertip to star centre when it was lit, shoulder widths
  straightness  - straight-line distance / path travelled between stars (1 = perfectly direct; smoothness)
  steadiness    - fingertip wobble while holding on a star, shoulder widths (tremor)
  speed         - seconds per star
  slowdown      - time per star in the last third of the session / the first third (fatigue; 1 = none)
  leaning       - lean warnings per 10 stars (trunk compensation instead of reaching with the arm)
  hand opening  - seconds to open the hand fully after holding a fist (release)
  grip holds    - share of Block reps with the full hold
  pain, tiredness, mood - the patient's own answers after the battle (1 to 5)
"""
import csv
from dataclasses import dataclass

import numpy as np

from session_log import LOG_PATH

MAX_SESSIONS = 20     # the screen shows the most recent sessions
COMPARE_WITH = 5      # a session is compared with the average of this many before it
SAME_SHARE = 0.05     # a change smaller than 5% of the value counts as "about the same"


@dataclass(frozen=True)
class Metric:
    key: str          # the Session attribute
    label: str
    unit: str
    better: str       # "higher" or "lower"
    fmt: str          # format for one value


METRICS = (
    Metric("max_reach", "Active reach", "shoulder widths", "higher", "{:.2f}"),
    Metric("reach_pct", "Range used", "% of today's calibrated reach", "higher", "{:.0f}%"),
    Metric("error_sw", "Accuracy (error)", "shoulder widths", "lower", "{:.3f}"),
    Metric("straightness", "Path straightness", "1 = direct", "higher", "{:.2f}"),
    Metric("tremor_sw", "Steadiness (tremor)", "shoulder widths", "lower", "{:.3f}"),
    Metric("time_per_star", "Time per star", "seconds", "lower", "{:.1f} s"),
    Metric("slowdown", "Slowdown (fatigue)", "late / early", "lower", "{:.2f}x"),
    Metric("lean_per_10", "Leaning", "warnings per 10 stars", "lower", "{:.1f}"),
    Metric("open_s", "Hand opening", "seconds", "lower", "{:.1f} s"),
    Metric("grip_hold_pct", "Grip holds", "% full holds", "higher", "{:.0f}%"),
    Metric("pain", "Pain", "1 none to 5 severe", "lower", "{:.0f}"),
    Metric("tiredness", "Tiredness", "1 fresh to 5 exhausted", "lower", "{:.0f}"),
    Metric("mood", "Mood", "1 low to 5 great", "higher", "{:.0f}"),
)
BY_KEY = {m.key: m for m in METRICS}


def number(text):
    """A float from a CSV cell, or None if it is blank or not a number."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@dataclass
class Session:
    date: str
    mode: str
    assisted: bool
    stars: int
    time_per_star: float | None
    lean_warnings: int
    error_sw: float | None
    error_px: float | None
    hints: int
    spell: str
    result: str
    difficulty: str = ""
    arm: str = ""
    minutes: float | None = None
    max_reach: float | None = None
    reach_pct: float | None = None
    straightness: float | None = None
    tremor_sw: float | None = None
    slowdown: float | None = None
    grip_reps: int = 0
    grip_holds: int = 0
    open_s: float | None = None
    pain: float | None = None
    tiredness: float | None = None
    mood: float | None = None

    @property
    def lean_per_10(self):
        return 10 * self.lean_warnings / self.stars if self.stars else None

    @property
    def grip_hold_pct(self):
        return 100 * self.grip_holds / self.grip_reps if self.grip_reps else None

    def value(self, key):
        return getattr(self, key)


def parse_row(r):
    """A Session from one sessions.csv row (a dict)."""
    seconds = number(r.get("time"))
    return Session(
        date=r.get("date", ""), mode=r.get("mode", ""), assisted=(r.get("assisted") or "on") != "off",
        stars=int(number(r.get("stars hit")) or 0), time_per_star=number(r.get("time per star")),
        lean_warnings=int(number(r.get("lean warnings")) or 0), error_sw=number(r.get("avg error sw")),
        error_px=number(r.get("avg error px")), hints=int(number(r.get("hints used")) or 0),
        spell=r.get("spell") or r.get("constellation", ""), result=r.get("result", ""),
        difficulty=r.get("difficulty", ""), arm=r.get("arm", ""),
        minutes=None if seconds is None else seconds / 60, max_reach=number(r.get("max reach")) or None,
        reach_pct=number(r.get("reach pct")),
        straightness=number(r.get("straightness")), tremor_sw=number(r.get("tremor sw")),
        slowdown=number(r.get("slowdown")), grip_reps=int(number(r.get("grip reps")) or 0),
        grip_holds=int(number(r.get("grip holds")) or 0), open_s=number(r.get("open s")),
        pain=number(r.get("pain")), tiredness=number(r.get("tiredness")), mood=number(r.get("mood")))


def load_sessions(path=LOG_PATH):
    """Every session in the log, oldest first. An unreadable or missing file gives an empty list."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return []
    return [parse_row(r) for r in rows if r.get("date")]


def recent(sessions, limit=MAX_SESSIONS):
    return sessions[-limit:]


def series(sessions, key):
    """The values of one metric, oldest first, skipping sessions that don't have it."""
    return [v for v in (s.value(key) for s in sessions) if v is not None]


def time_series(sessions):
    return series(sessions, "time_per_star")


def lean_series(sessions):
    return [s.lean_warnings for s in sessions]


def unassisted(sessions):
    """Sessions played with assisted learning off that recorded an error."""
    return [s for s in sessions if not s.assisted and s.error_sw is not None]


def last_unassisted(sessions):
    found = unassisted(sessions)
    return found[-1] if found else None


def direction(change, better, scale):
    """"better", "worse" or "same" for a change in a metric, given which way is better."""
    if scale <= 0 or abs(change) < SAME_SHARE * scale:
        return "same"
    return "better" if (change > 0) == (better == "higher") else "worse"


def trend(values, better):
    """How a series is going: the least-squares slope across it, as "better", "worse" or "same"
    (needs at least 3 values; fewer gives None)."""
    if len(values) < 3:
        return None
    x = np.arange(len(values), dtype=float)
    slope = np.polyfit(x, np.array(values, dtype=float), 1)[0]
    return direction(slope * (len(values) - 1), better, abs(float(np.mean(values))))


def compare(session, earlier, key):
    """This session's value against the average of up to COMPARE_WITH earlier sessions.
    Returns (value, earlier average, "better"/"worse"/"same") or None if either is missing."""
    metric = BY_KEY[key]
    value = session.value(key)
    before = series(earlier[-COMPARE_WITH:], key)
    if value is None or not before:
        return None
    average = float(np.mean(before))
    return value, average, direction(value - average, metric.better, abs(average))
