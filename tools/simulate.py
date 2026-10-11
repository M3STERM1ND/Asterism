"""Simulate two bot patients playing Asterism's battles over several weeks, and report how each responds.

The bots play the real game logic (game.battle.Battle, sessions.reach.Reach, sessions.grip.Grip and the
session log), frame by frame at 30 FPS, through fake hands. Only the camera is replaced. Each bot has a
simple motor model whose numbers change across sessions, standing in for recovery:
  reaching   - minimum-jerk movement from star to star, bowed sideways by `curve` (less straight), with
               endpoint error and a corrective sub-movement when it lands outside the star, and tremor
  leaning    - on some stars the bot leans with its trunk first (the lean guard warns and blocks the star)
  grip       - Block turns: the fist is held for the full 3 s with some probability, then the hand opens
               over `open_s` seconds (slow release after a stroke)
  fatigue    - movement slows by `fatigue` per minute played
  check-in   - after each battle the bot answers pain / tiredness / mood from its profile
Bot A responds well to therapy; bot B responds slowly and reports rising pain (so the report should flag it).
Bot A's movements are tracked: every fingertip sample goes to bot_a_movements.csv, and its report draws
an early and a late reach of the same spell.

Run:  .venv/bin/python -m tools.simulate [output folder]      (default: simulation/)
These are made-up patients for testing the game and its reports, not real data.
"""
import contextlib
import csv
import io
import math
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np

import events
import progress
import therapy_report
from calibration import Calibration
from game import difficulty as levels
from game import spells as magic
from game.battle import BATTLES, Battle
from game.report import CHECKIN
from session_log import COLUMNS, SessionRecord
from sessions.grip import FINGERTIPS

FPS = 30
DT = 1 / FPS
SIZE = (1280, 720)
SHOULDER, WIDTH = (715.0, 418.0), 150.0   # the bot's resting right shoulder on screen, and shoulder width (px)
REST_TIP = (700.0, 560.0)                 # where the fingertip rests between moves
THINK_SECONDS = 1.2                       # time the bot takes to choose a move
BATTLES_PER_DAY = 2
UNASSISTED_EVERY = 4                      # every 4th session is played from memory (assisted learning off)
MEMORY_ERROR = 1.4                        # from memory, the bot lands this much farther from the star
MAX_BATTLE_MINUTES = 12                   # a battle that runs longer than this is stopped (safety for the sim)


@dataclass(frozen=True)
class Profile:
    """A bot patient: each tuple is (first session, last session); values in between follow a learning curve."""
    name: str
    story: str
    sessions: int
    reach_sw: tuple       # true comfortable reach, shoulder widths (calibration measures it each day)
    move_s: tuple         # seconds to move one full reach distance
    curve: tuple          # sideways bow of a movement, as a share of its length (0 = straight)
    tremor_px: tuple      # fingertip wobble, px
    error_px: tuple       # endpoint error of a movement, px
    lean_p: tuple         # chance of leaning on a star
    hold_p: tuple         # chance of holding the fist the full 3 s
    open_s: tuple         # seconds to open the hand after the hold
    fatigue: tuple        # slowdown per minute played
    pain: tuple           # baseline pain answer (1 to 5)
    block_p: float        # chance of choosing Block when health is low
    learning: float       # how fast the curve rises (higher = early gains)


BOT_A = Profile("Bot A", "Moderate arm weakness, responding well to home practice", 16,
                reach_sw=(1.45, 2.10), move_s=(2.4, 1.2), curve=(0.32, 0.07), tremor_px=(6.0, 2.0),
                error_px=(24.0, 9.0), lean_p=(0.35, 0.04), hold_p=(0.45, 0.92), open_s=(3.0, 1.0),
                fatigue=(0.07, 0.02), pain=(2.6, 1.3), block_p=0.7, learning=2.5)
BOT_B = Profile("Bot B", "Severe weakness, slow response, shoulder pain rising", 16,
                reach_sw=(1.25, 1.40), move_s=(2.8, 2.4), curve=(0.40, 0.31), tremor_px=(8.0, 7.0),
                error_px=(30.0, 24.0), lean_p=(0.45, 0.38), hold_p=(0.35, 0.45), open_s=(3.8, 3.3),
                fatigue=(0.08, 0.09), pain=(1.8, 3.8), block_p=0.5, learning=1.2)


def level_at(pair, k, learning, rng, noise=0.05):
    """A profile value at progress k (0 to 1 through the sessions), with a little day-to-day noise."""
    curve = (1 - math.exp(-learning * k)) / (1 - math.exp(-learning)) if learning > 0 else k
    start, end = pair
    return (start + (end - start) * curve) * (1 + rng.gauss(0, noise))


def hand(x, y, openness=1.4, pointing=True):
    """Fake hand landmarks with the index fingertip at (x, y) pixels. pointing: the index finger is
    stretched out to touch stars; otherwise every fingertip sits `openness` palm lengths from the wrist
    (a fist is about 0.9, an open hand about 1.8; see grip.py)."""
    wrist_y = y / SIZE[1] + (0.12 if pointing else 0.05 * openness)
    lm = [SimpleNamespace(x=x / SIZE[0], y=wrist_y, visibility=1.0) for _ in range(21)]
    lm[9] = SimpleNamespace(x=x / SIZE[0], y=wrist_y - 0.05, visibility=1.0)  # palm length 0.05
    for tip in FINGERTIPS:
        lm[tip] = SimpleNamespace(x=x / SIZE[0], y=wrist_y - 0.05 * openness, visibility=1.0)
    if pointing:
        lm[8] = SimpleNamespace(x=x / SIZE[0], y=y / SIZE[1], visibility=1.0)
    return [lm]


class Guard:
    """Stands in for the lean guard: the bot itself says when it leans."""
    def __init__(self):
        self.last_warn = float("-inf")
        self.warnings = 0


class Bot:
    """One simulated patient for one session: decides moves and produces a fingertip each frame."""

    def __init__(self, profile, session_index, rng, assisted=True):
        k = session_index / max(1, profile.sessions - 1)
        p, self.rng = profile, rng
        self.reach_sw = level_at(p.reach_sw, k, p.learning, rng, 0.03)
        self.move_s = level_at(p.move_s, k, p.learning, rng)
        self.curve = max(0.0, level_at(p.curve, k, p.learning, rng, 0.1))
        self.tremor = max(0.5, level_at(p.tremor_px, k, p.learning, rng, 0.1))
        self.error = max(2.0, level_at(p.error_px, k, p.learning, rng, 0.1)) * (1 if assisted else MEMORY_ERROR)
        self.lean_p = min(1.0, max(0.0, level_at(p.lean_p, k, p.learning, rng, 0.15)))
        self.hold_p = min(1.0, max(0.0, level_at(p.hold_p, k, p.learning, rng, 0.05)))
        self.open_s = max(0.3, level_at(p.open_s, k, p.learning, rng, 0.08))
        self.fatigue = max(0.0, level_at(p.fatigue, k, p.learning, rng, 0.1))
        self.pain = level_at(p.pain, k, 1.0, rng, 0.12)
        self.block_p = p.block_p
        self.tip = np.array(REST_TIP)
        self.reset_move()

    def reset_move(self):
        """Between turns the hand goes back to rest, so the next spell starts from there."""
        self.tip = np.array(REST_TIP)
        self.target_i = None
        self.move = None        # (start, end, began, duration, bow)
        self.lean_until = 0.0
        self.grip_plan = None

    # --- deciding
    def choose(self, battle, now):
        """Attack with the strongest spell it can cast, Block when hurt (sometimes, never twice in a row), else Rest."""
        last = battle.rounds[-2].move if len(battle.rounds) > 1 else ""
        if battle.player_health < 50 and last != "block" and self.rng.random() < self.block_p:
            battle.block(now)
            return
        castable = [s for s in battle.book.spells if battle.book.can_cast(s)]
        if not castable:
            battle.rest(now)
            return
        best = max(castable, key=lambda s: (s.cost, s.stars))
        battle.choose(magic.SPELLS.index(best), now)

    # --- reaching
    def fingertip(self, reach, now, minutes):
        """Where the fingertip is this frame while drawing, and whether the bot is leaning."""
        i = reach.target_index()
        if i is None or reach.points is None:
            return self.tip, False
        target = np.array(reach.points[i])
        if self.target_i != i:
            self.target_i = i
            self.plan(target, now, minutes, first=True)
            if self.rng.random() < self.lean_p:
                self.lean_until = now + 0.9   # leans toward the star first, then straightens up
        start, end, began, duration, bow = self.move
        tau = min(1.0, (now - began) / duration)
        s = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5          # minimum-jerk progress
        along = end - start
        normal = np.array([-along[1], along[0]]) / (np.hypot(*along) + 1e-9)
        pos = start + along * s + normal * bow * math.sin(math.pi * tau)
        if tau >= 1.0 and np.hypot(*(end - target)) > reach.accept_radius * 0.8 and now - began > duration + 0.35:
            self.plan(target, now, minutes, first=False)               # landed off the star: a corrective move
        self.tip = pos + np.array([self.rng.gauss(0, self.tremor), self.rng.gauss(0, self.tremor)])
        return self.tip, now < self.lean_until

    def plan(self, target, now, minutes, first):
        start = self.tip.copy()
        distance = float(np.hypot(*(target - start)))
        error = self.error if first else self.error * 0.35
        end = target + np.array([self.rng.gauss(0, error), self.rng.gauss(0, error)])
        duration = max(0.25, self.move_s * (0.35 + distance / (self.reach_sw * WIDTH)) * (1 + self.fatigue * minutes))
        bow = (self.curve if first else self.curve * 0.3) * distance * self.rng.choice((-1, 1))
        self.move = (start, end, now, duration, bow)

    # --- gripping
    def grip_openness(self, battle, now):
        """Block: close the fist, hold (or give up early), then open over open_s seconds."""
        if self.grip_plan is None:
            held = self.rng.random() < self.hold_p
            self.grip_plan = (now, held, self.rng.uniform(1.0, 2.4))
        began, held, give_up = self.grip_plan
        t = now - began
        if t < 0.4:
            return 1.4
        if not held and t > 0.4 + give_up:
            return 1.9                                    # opened before the hold was done
        if battle.grip.state != "open":
            return 0.85                                   # the fist
        opened_for = now - battle.grip.held_at
        return 0.85 + (1.65 - 0.85) * min(1.0, opened_for / self.open_s)

    # --- check-in
    def answers(self, minutes, won):
        pain = self.pain + 0.08 * minutes + self.rng.gauss(0, 0.4)
        tired = 1.3 + 0.18 * minutes + 6 * self.fatigue + self.rng.gauss(0, 0.4)
        mood = 3.4 + (0.8 if won else -0.6) - 0.35 * (pain - 2) + self.rng.gauss(0, 0.4)
        clamp = lambda v: int(min(5, max(1, round(v))))
        return {"pain": clamp(pain), "tiredness": clamp(tired), "mood": clamp(mood)}


def play_battle(bot, battle, cal, guard, record, start, movements=None, tag=None):
    """Run one battle to its end at 30 FPS. Returns (result, seconds played)."""
    now, phase_seen, phase_since = start, None, start
    figure = SimpleNamespace(stars={"Betelgeuse": ((SHOULDER[0] - WIDTH) / SIZE[0], SHOULDER[1] / SIZE[1]),
                                    "Bellatrix": (SHOULDER[0] / SIZE[0], SHOULDER[1] / SIZE[1])})
    asked = 0
    while now - start < MAX_BATTLE_MINUTES * 60:
        minutes = (now - start) / 60
        if battle.phase != phase_seen:
            phase_seen, phase_since = battle.phase, now
            if battle.phase in ("select", "guard"):
                bot.reset_move()
        hands, leaning = [], False
        if battle.phase == "select":
            hands = hand(*REST_TIP, 1.4, pointing=False)
            if now - phase_since >= THINK_SECONDS:
                bot.choose(battle, now)
        elif battle.phase == "player":
            tip, leaning = bot.fingertip(battle.reach, now, minutes)
            hands = hand(*tip)
            if leaning and guard.last_warn < now - 2.0:
                guard.last_warn, guard.warnings = now, guard.warnings + 1
            if movements is not None and battle.reach.target_index() is not None:
                movements.append((*tag, battle.spell.name, battle.reach.target_index() + 1, round(now - start, 3),
                                  round(float(tip[0]), 1), round(float(tip[1]), 1), int(leaning)))
        elif battle.phase == "guard":
            hands = hand(*REST_TIP, bot.grip_openness(battle, now), pointing=False)
        elif battle.phase == "checkin":
            if now - phase_since > 1.0 + asked:
                answers = bot.answers(minutes, battle.outcome == "won")
                battle.answer(answers[battle.question[0]])
                asked += 1
        elif battle.phase == "report":
            return battle.outcome, now - start
        if hands:
            record.update([(hands[0][8].x * SIZE[0], hands[0][8].y * SIZE[1])], cal, leaning, now)
        battle.update(hands, None, figure, (0.0, 0.0, 1.0, 1.0), now, cal, guard, leaning)
        now += DT
    return "stopped", now - start


def simulate(profile, seed, out_dir, track=False):
    """All of one bot's sessions. Writes its sessions CSV (and movements CSV if tracked).
    Returns (sessions, traces for the report)."""
    rng = random.Random(seed)
    csv_path = os.path.join(out_dir, f"{profile.name.lower().replace(' ', '_')}_sessions.csv")
    rows, movements, casts, wins = [], ([] if track else None), {}, 0
    day = datetime(2026, 9, 1, 10, 0)
    battle_index = 0
    for session in range(profile.sessions):
        assisted = session % UNASSISTED_EVERY != UNASSISTED_EVERY - 1
        bot = Bot(profile, session, rng, assisted)
        cal = Calibration(reach=bot.reach_sw * (1 + rng.gauss(0, 0.02)), side="Bellatrix", shoulder=SHOULDER,
                          width=WIDTH, tilt=0.0, mid=(SHOULDER[0] - WIDTH / 2, SHOULDER[1]),
                          heights=(SHOULDER[1], SHOULDER[1]), nose=None)
        clock = 1000.0 * (session + 1)
        for b in range(BATTLES_PER_DAY):
            config = BATTLES[min(battle_index, len(BATTLES) - 1)]
            battle = Battle(config, SIZE, levels.NORMAL, assisted=assisted, wins=wins, rng=random.Random(rng.random()))
            guard = Guard()
            record = SessionRecord("battle", config["title"], 0, levels.NORMAL.name, assisted, "right")
            with contextlib.redirect_stdout(io.StringIO()):  # the game logs every spell's placement: too much here
                result, seconds = play_battle(bot, battle, cal, guard, record, clock, movements, (session + 1, b + 1))
            events.clear()
            for reach in battle.casts:
                record.absorb(reach)
                if reach.won_at is not None:
                    casts.setdefault((session, reach.name), (reach.points, reach.trace))
            for grip in battle.grips:
                record.absorb_grip(grip)
            row = record.row(clock + seconds, guard.warnings, result if result != "stopped" else "lost",
                             battle.enemy_max - battle.enemy_health, date=day + timedelta(minutes=14 * b))
            row.update({k: str(v) for k, v in battle.checkin.items()})
            rows.append(row)
            if result == "won":
                wins += 1
                battle_index += 1
            clock += seconds + 60
        day += timedelta(days=2 if session % 3 != 2 else 3)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    if track:
        with open(os.path.join(out_dir, "bot_a_movements.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["session", "battle", "spell", "target star", "seconds", "x", "y", "leaning"])
            writer.writerows(movements)
    return progress.load_sessions(csv_path), pick_traces(casts, profile.sessions)


def pick_traces(casts, sessions):
    """An early and a late drawing of the same spell (the first and last sessions that cast it)."""
    by_spell = {}
    for (session, name), (points, trace) in casts.items():
        by_spell.setdefault(name, []).append((session, points, trace))
    shared = [(name, items) for name, items in by_spell.items() if len(items) >= 2]
    if not shared:
        return []
    name, items = max(shared, key=lambda kv: (kv[1][-1][0] - kv[1][0][0], len(kv[1][0][1])))
    (s0, p0, t0), (s1, p1, t1) = items[0], items[-1]
    return [(f"{name}, session {s0 + 1} (early)", p0, t0), (f"{name}, session {s1 + 1} (late)", p1, t1)]


def comparison_html(results):
    """A table: each bot's first and latest sessions for the key measures."""
    keys = ("reach_pct", "error_sw", "straightness", "tremor_sw", "lean_per_10", "open_s", "grip_hold_pct", "pain")
    head = "".join(f"<th>{progress.BY_KEY[k].label}</th>" for k in keys)
    body = []
    for profile, sessions in results:
        cells = []
        for k in keys:
            m = progress.BY_KEY[k]
            start, end = therapy_report.edge_averages(progress.series(sessions, k))
            verdict = progress.trend(progress.series(sessions, k), m.better)
            cells.append(f'<td class="{verdict or ""}">{therapy_report.fmt(m, start)} → {therapy_report.fmt(m, end)}</td>')
        body.append(f"<tr><td><b>{profile.name}</b><br><span class=\"muted\">{profile.story}</span></td>{''.join(cells)}</tr>")
    return ("<h2>Simulation: both bot patients</h2><p class=\"muted\">First three sessions → latest three. "
            "Green: improving, red: getting worse.</p><div class=\"scroll\"><table><tr><th>Bot</th>"
            + head + "</tr>" + "".join(body) + "</table></div>")


def main(out_dir="simulation"):
    os.makedirs(out_dir, exist_ok=True)
    results, traces = [], None
    for profile, seed, track in ((BOT_A, 11, True), (BOT_B, 23, False)):
        sessions, picked = simulate(profile, seed, out_dir, track)
        results.append((profile, sessions))
        if track:
            traces = picked
        won = sum(1 for s in sessions if s.result == "won")
        print(f"{profile.name}: {len(sessions)} battles over {profile.sessions} days, {won} won, "
              f"{sum(s.stars for s in sessions)} reaches, {sum(s.grip_reps for s in sessions)} grip reps")
    compare = comparison_html(results)
    for (profile, sessions), with_traces in zip(results, (traces, None)):
        path = os.path.join(out_dir, f"{profile.name.lower().replace(' ', '_')}_report.html")
        therapy_report.write_report(sessions, path, title=f"Home rehab report: {profile.name} (simulated)",
                                    subtitle=profile.story, traces=with_traces, extra_html=compare)
        print("wrote", path)
    for profile, sessions in results:
        print(f"\n{profile.name} - {profile.story}")
        for level, text in therapy_report.observations(sessions):
            print(f"  [{level}] {text}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "simulation")
