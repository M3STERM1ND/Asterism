"""Report: what happened in a battle, in rehab terms, for the patient and the therapist. Pure logic;
battle_screen.py draws it and therapy_report.py builds the therapist's report from the same measures.

A round is one player turn (Attack, Block or Rest) plus the enemy's answer. The rehab measures come from
the session's row in sessions.csv (see progress.METRICS), so the screen and the log always agree.
Thresholds are in shoulder widths, the game's unit for distance, so they hold at any camera distance.
These are coaching thresholds for a home game, not clinical cut-offs: the therapist decides what matters.
"""
from dataclasses import dataclass, field

import numpy as np

from progress import BY_KEY, compare

PRECISE_SW, FAIR_SW = 0.10, 0.20      # average error: precise, fair, or loose above
SMOOTH, FAIR_PATH = 0.85, 0.70        # path straightness: smooth, fair, or wandering below
STEADY_SW, SHAKY_SW = 0.03, 0.08      # tremor while holding on a star
FULL_RANGE, SHORT_RANGE = 95, 80      # reach as % of calibrated: full range, or short below
SLOWDOWN_TIRED = 1.3                  # last third 30% slower than the first: fatigue
SLOW_OPEN_S = 2.0                     # hand opening slower than this after a fist
LEANS_OFTEN = 2.0                     # lean warnings per 10 stars
PAIN_ALERT = 4                        # pain answer at or above this: stop for today and tell the therapist
TIRED_ALERT = 4

# The check-in after each battle: (key, question, the five answers from 1 to 5).
CHECKIN = (
    ("pain", "Any pain in your arm or shoulder?", ("None", "A little", "Some", "A lot", "Severe")),
    ("tiredness", "How tired do you feel?", ("Fresh", "A little tired", "Tired", "Very tired", "Exhausted")),
    ("mood", "How do you feel about today's session?", ("Low", "Not great", "OK", "Good", "Great")),
)
SAFETY_TIP = "Stop and rest if anything hurts, and tell your therapist."


@dataclass
class Round:
    number: int
    move: str = ""                 # "attack", "block" or "rest"
    spell: str = ""
    total_stars: int = 0
    stars: int = 0                 # stars hit
    damage: int = 0                # damage that landed on the enemy (after its guard)
    enemy_blocked: bool = False    # the enemy's guard halved it
    leaned: int = 0                # stars lit while leaning
    errors_sw: list = field(default_factory=list)
    errors_px: list = field(default_factory=list)
    straightness: list = field(default_factory=list)
    tremor_px: list = field(default_factory=list)
    move_seconds: list = field(default_factory=list)
    hints: int = 0
    misses: int = 0
    rested: bool = False
    shield: str | None = None      # Block: "full", "cracked", or None if the rep was given up
    grip_held: bool = False        # Block: the 3-second hold was completed
    open_seconds: float | None = None  # Block: time to open the hand fully after the hold
    enemy_action: str = ""         # "strike", "double", "guard", "heal" or "" if the enemy never acted
    attacks: list = field(default_factory=list)   # names of the enemy's attacks this round
    results: list = field(default_factory=list)   # per attack: "blocked", "half" or "hit"
    damage_taken: int = 0
    healed: int = 0

    @property
    def complete(self):
        return self.total_stars > 0 and self.stars == self.total_stars

    @property
    def error_sw(self):
        return float(np.mean(self.errors_sw)) if self.errors_sw else None

    @property
    def path(self):
        return float(np.mean(self.straightness)) if self.straightness else None


def aim_word(error_sw):
    """"precise", "fair" or "loose" for an average error in shoulder widths (None: no stars hit)."""
    if error_sw is None:
        return None
    return "precise" if error_sw <= PRECISE_SW else "fair" if error_sw <= FAIR_SW else "loose"


def path_word(straightness):
    if straightness is None:
        return None
    return "smooth" if straightness >= SMOOTH else "fairly smooth" if straightness >= FAIR_PATH else "wandering"


def enemy_outcome(r):
    """The enemy's answer in a few words."""
    if r.enemy_action == "heal":
        return f"healed {r.healed}" if r.healed else "tried to heal"
    if r.enemy_action == "guard":
        return "blocked (guard up)"
    if not r.results:
        return "-"
    taken = f" -{r.damage_taken}" if r.damage_taken else ""
    if all(x == "blocked" for x in r.results):
        return "attack blocked" if len(r.results) == 1 else "both attacks blocked"
    if all(x == "half" for x in r.results):
        return f"half got through{taken}"
    return f"hit you{taken}"


def round_conclusion(r, with_block=True):
    """One short sentence about the player's move (with_block=False leaves out the enemy's guard,
    which the report shows itself)."""
    if r.rested:
        return "You rested to recover mana."
    if r.move == "block":
        if r.shield == "full":
            return "Full grip: fist held and opened wide." + (
                f" Opened in {r.open_seconds:.1f} s." if r.open_seconds is not None else "")
        if r.shield == "cracked":
            return "Fist opened before the hold was done."
        return "Block given up."
    aim, path = aim_word(r.error_sw), path_word(r.path)
    form = "no leaning" if r.leaned == 0 else f"{r.leaned} lean{'s' if r.leaned != 1 else ''}"
    text = f"{(aim or 'no').capitalize()} aim, {path or 'no'} path, {form}."
    if r.enemy_blocked and with_block:
        text += " The enemy's guard halved it."
    return text


def battle_stats(rounds):
    """Game totals over every round, as a dict the screen can print."""
    results = [x for r in rounds for x in r.results]
    return {"rounds": len(rounds),
            "attacks": sum(1 for r in rounds if r.move == "attack"),
            "blocks made": sum(1 for r in rounds if r.move == "block"),
            "full blocks": sum(1 for r in rounds if r.shield == "full"),
            "damage dealt": sum(r.damage for r in rounds),
            "damage taken": sum(r.damage_taken for r in rounds),
            "stars hit": sum(r.stars for r in rounds),
            "attacks faced": len(results),
            "attacks stopped": results.count("blocked"),
            "enemy guards": sum(1 for r in rounds if r.enemy_blocked),
            "leans": sum(r.leaned for r in rounds),
            "hints": sum(r.hints for r in rounds),
            "healed": sum(r.healed for r in rounds),
            "spells": list(dict.fromkeys(r.spell for r in rounds if r.spell))}


def findings(session, earlier):
    """The rehab measures for this session, each with how it compares with the sessions before it:
    a list of (metric, value, earlier average or None, "better"/"worse"/"same"/None)."""
    rows = []
    for key in ("max_reach", "reach_pct", "error_sw", "straightness", "tremor_sw", "time_per_star", "slowdown",
                "lean_per_10", "open_s", "grip_hold_pct"):
        value = session.value(key)
        if value is None:
            continue
        compared = compare(session, earlier, key)
        rows.append((BY_KEY[key], value, compared[1] if compared else None, compared[2] if compared else None))
    return rows


def general_conclusion(stats, session, won, checkin, earlier=()):
    """A few plain sentences: how the battle went, the movement in rehab terms, and how it compares."""
    lines = []
    if won:
        lines.append(f"Victory in {stats['rounds']} round{'s' if stats['rounds'] != 1 else ''}: "
                     f"{stats['stars hit']} reaches and {stats['blocks made']} grip reps.")
    else:
        lines.append(f"Orion fell in round {stats['rounds']} after {stats['stars hit']} reaches and "
                     f"{stats['blocks made']} grip reps. The exercise still counts.")
    if session is not None:
        strong = []
        if session.reach_pct is not None and session.reach_pct >= FULL_RANGE:
            strong.append("used the full reach range")
        if aim_word(session.error_sw) == "precise":
            strong.append("precise aim")
        if path_word(session.straightness) == "smooth":
            strong.append("smooth paths")
        if session.stars and session.lean_warnings == 0:
            strong.append("no leaning")
        if session.grip_reps and session.grip_holds == session.grip_reps:
            strong.append("every grip held")
        if strong:
            lines.append("Strengths: " + ", ".join(strong) + ".")
        compared = findings(session, list(earlier))
        better = [m.label.lower() for m, _, _, d in compared if d == "better"]
        worse = [m.label.lower() for m, _, _, d in compared if d == "worse"]
        if better:
            lines.append("Better than your recent sessions: " + ", ".join(better[:4]) + ".")
        if worse:
            lines.append("Not as good as recently: " + ", ".join(worse[:3]) + ". Normal day to day; watch the trend.")
    if checkin.get("pain", 0) >= PAIN_ALERT:
        lines.append("You reported a lot of pain: please stop for today and tell your therapist.")
    return lines


def round_tip(r):
    """One tip after a move, aimed at what most needs work."""
    if r.rested:
        return "Resting is part of recovery: let the arm hang loose, shake it gently and breathe slowly."
    if r.move == "block":
        if r.shield == "full" and r.open_seconds is not None and r.open_seconds > SLOW_OPEN_S:
            return "Opening was slow: after the fist, spread your fingers as wide as you can, then relax them."
        if r.shield == "full":
            return "Good grip. Squeeze firmly without holding your breath, then open all five fingers wide."
        return "Keep the fist closed for the full count. If it is hard, use your other hand to help it open after."
    if r.leaned:
        return "Keep your shoulders level and your back against the chair: let the arm do the reaching."
    if path_word(r.path) == "wandering":
        return "Move in a straight line from star to star. Look at the next star first, then reach slowly."
    if aim_word(r.error_sw) == "loose":
        return "Slow down as you arrive and settle your fingertip right on the star."
    if r.results and "hit" in r.results:
        return "When the enemy is strong, Block: one slow fist hold and a wide open hand is great grip practice."
    if r.hints:
        return "Hints are fine. Trace the shape in the air once before you start, to help memory."
    return "Good work. Breathe out as you reach, and keep the movement slow and controlled."


def rehab_tips(session, checkin, won, stats=None):
    """Up to three tips for after the battle, most important first, then the safety line.
    Pain and tiredness come first: comfort and safety matter more than the score."""
    tips = []
    if checkin.get("pain", 0) >= PAIN_ALERT:
        tips.append("Pain: stop for today. Rest the arm in a comfortable position and tell your therapist "
                    "where it hurts and when it started.")
    if checkin.get("tiredness", 0) >= TIRED_ALERT or (session and session.slowdown and session.slowdown >= SLOWDOWN_TIRED):
        tips.append("Tiredness: you slowed down as the session went on. Shorter sessions spread through the "
                    "day work better than one long one. Rest before the next battle.")
    if session is not None:
        if session.lean_per_10 is not None and session.lean_per_10 >= LEANS_OFTEN:
            tips.append("Posture: sit tall with your back against the chair and keep the other shoulder still. "
                        "A smaller honest reach trains the arm; leaning trains the habit of leaning.")
        if session.reach_pct is not None and session.reach_pct < SHORT_RANGE:
            tips.append("Range: your reach was shorter than at calibration. Try the Easy level, or recalibrate (C) "
                        "if today is a stiffer day.")
        if path_word(session.straightness) == "wandering" or aim_word(session.error_sw) == "loose":
            tips.append("Control: go slower. Look at the target, reach in a straight line, and pause on the star. "
                        "Slow, accurate reps rebuild control better than fast ones.")
        if session.tremor_sw is not None and session.tremor_sw > SHAKY_SW:
            tips.append("Steadiness: your hand shook while holding on the stars. Rest your elbow if you can, "
                        "and breathe out slowly as you hold.")
        if session.grip_reps and session.open_s is not None and session.open_s > SLOW_OPEN_S:
            tips.append("Hand opening: practise opening the hand wide between battles; ask your therapist about "
                        "stretches for the finger muscles.")
        if session.grip_reps and session.grip_holds < session.grip_reps:
            tips.append("Grip: build up the fist hold a second at a time; a soft ball between turns helps.")
        if session.grip_reps == 0 and stats and stats["attacks faced"]:
            tips.append("Grip: you never chose Block. Mixing in Block turns (B, or hold a fist) trains the hand too.")
    if not tips:
        tips.append("Keep going: repeat this level until it feels easy, then try the next difficulty.")
    if not won:
        tips.append("Losing a battle is fine: every reach and grip still counted as exercise.")
    return tips[:3] + [SAFETY_TIP]
