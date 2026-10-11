"""Render screenshots of the new screens with demo data (no camera needed): the start menu settings,
the spell picker, an enemy's turn, the memory preview and hidden stars, and the Progress screen.
Run from the project folder:  .venv/bin/python -m tools.make_screenshots [folder]
(Run tools/simulate.py first so the report and Progress screenshots use the simulated patient's sessions.)
Nothing here touches sessions.csv or settings.json: it uses a temporary folder."""
import csv
import os
import sys
import tempfile
from unittest import mock

import cv2

import battle_screen
import orion
import progress
import render
import screens
from game import difficulty as levels
from game.battle import Battle, BATTLES
from game.report import Round
from play import Play
from session_log import COLUMNS
from tests.helpers import CAL, FIGURE

SHOULDERS = {"Betelgeuse": (0.469, 0.556), "Bellatrix": (0.547, 0.556), "Alnitak": (0.47, 0.78),
             "Alnilam": (0.51, 0.76), "Mintaka": (0.55, 0.74), "Saiph": (0.45, 0.93), "Rigel": (0.60, 0.92)}


class DemoView:
    frozen = False

    def camera_rect(self):
        return (0.0, 0.0, 1.0, 1.0)


def figure():
    return orion.Figure(stars=SHOULDERS, lines=orion.LINES, hand=None, arms=[], names_alpha=0.0, cramped=False)


def new_play(folder, difficulty="Normal", assisted=True, wins=0):
    play = Play((render.W, render.H), DemoView(), settings_path=os.path.join(folder, "settings.json"))
    play.settings.difficulty, play.settings.assisted, play.settings.battles_won = difficulty, assisted, wins
    return play


def frame(play, now, hands=()):
    fig = figure()
    world = None
    if play.mode == "battle":
        world = lambda f, g: battle_screen.draw_battle_world(f, g, play, fig, list(hands), now)
    with mock.patch.object(render.time, "monotonic", return_value=now):  # render.draw reads the clock itself
        image = render.draw(list(hands), None, fig, 30, 30, play, world)
    screens.draw_screens(image, play, False, now)
    if play.mode == "battle":
        battle_screen.draw_battle_hud(image, play, now)
    return image


def start_battle(play, index=1):
    play.mode, play.calibration, play.battle_index = "battle", CAL, index
    play.start_battle()
    play.reach = play.battle.reach
    return play.battle


def demo_rounds():
    """Six rounds of a made-up battle, to show the report."""
    def drawn(n, spell, stars, error, leaned, damage, path=0.86, **kw):
        r = Round(n, "attack", spell, total_stars=stars, stars=stars, damage=damage, leaned=leaned, **kw)
        r.errors_sw, r.errors_px, r.straightness = [error] * stars, [error * 166] * stars, [path] * stars
        return r
    return [drawn(1, "Gemini", 6, 0.08, 0, 54, enemy_action="strike", attacks=["Scorpius"], results=["hit"], damage_taken=19),
            Round(2, "block", shield="full", grip_held=True, open_seconds=1.4, enemy_action="strike",
                  attacks=["Gemini"], results=["blocked"]),
            drawn(3, "Pisces", 7, 0.14, 1, 31, enemy_blocked=True, path=0.72, enemy_action="guard"),
            drawn(4, "Taurus", 5, 0.11, 0, 40, enemy_action="strike", attacks=["Scorpius"], results=["hit"], damage_taken=19),
            Round(5, "block", shield="cracked", enemy_action="strike", attacks=["Scorpius"], results=["half"], damage_taken=10),
            drawn(6, "Gemini", 6, 0.09, 0, 58, enemy_action="")]


def demo_log(path):
    rows = []
    for i in range(14):
        unassisted = i >= 6
        rows.append({"date": f"2026-09-{10 + i:02d} 10:00:00", "mode": "battle" if i % 3 else "practice", "time": "60",
                     "max reach": "1.9", "lean warnings": max(0, 6 - i // 2 - (i % 3)), "result": "won",
                     "difficulty": "Normal", "assisted": "off" if unassisted else "on", "spell": "Aries+Taurus",
                     "arm": "right", "stars hit": 9, "time per star": f"{4.2 - i * 0.18:.2f}",
                     "avg error px": f"{max(8, 38 - i * 2.1):.1f}" if unassisted else f"{14 - i * 0.5:.1f}",
                     "avg error sw": f"{max(0.07, 0.38 - i * 0.022):.3f}" if unassisted else f"{0.14 - i * 0.005:.3f}",
                     "hints used": max(0, 3 - i // 4) if unassisted else 0, "misses": 1})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, restval="")
        writer.writeheader()
        writer.writerows(rows)


def main(out):
    os.makedirs(out, exist_ok=True)
    folder = tempfile.mkdtemp()
    shots = {}

    play = new_play(folder)
    shots["menu_default"] = frame(play, 1.0)
    play = new_play(folder, "Hard", False)
    shots["menu_hard_unassisted"] = frame(play, 1.0)

    play = new_play(folder, wins=2)
    battle = start_battle(play)
    battle.book.mana = 38
    battle.book.cooldowns["Taurus"] = 1
    shots["spell_picker"] = frame(play, 1.0)

    battle.choose(0, 1.0)
    battle.update([], None, figure(), (0, 0, 1, 1), 1.0, CAL, FIGURE_GUARD(), False)
    play.reach = battle.reach
    shots["your_turn_drawing"] = frame(play, 1.5)

    play = new_play(folder, "Hard")
    battle = start_battle(play, 2)
    battle.choose(1, 1.0)
    battle.reach.update([], None, figure(), (0, 0, 1, 1), 1.0, CAL)
    battle.reach.enabled = False
    battle.phase, battle.phase_at = "strike", 1.0
    play.reach = battle.reach
    shots["enemy_turn_strike"] = frame(play, 1.8)

    play = new_play(folder, "Hard")
    battle = start_battle(play, 2)
    battle.choose(1, 1.0)
    battle.reach.update([], None, figure(), (0, 0, 1, 1), 1.0, CAL)
    battle.reach.lit_at, battle.reach.won_at = [1.0] * 5, 1.0
    battle.round.leaned, battle.round.errors_sw = 1, [0.12] * 5
    battle.round.damage, battle.message = 42, "Taurus hits!"
    battle.phase, battle.phase_at = "result", 1.0
    play.reach = battle.reach
    shots["result_with_tip"] = frame(play, 1.5)

    play = new_play(folder, wins=1)
    battle = start_battle(play, 1)
    battle.phase = "select"
    battle.fist_since, battle.clock = 0.0, 0.6
    shots["select_fist_chooses_block"] = frame(play, 0.6)
    battle.block(1.0)
    battle.grip.state, battle.grip.progress, battle.grip.value = "holding", 0.55, 0.92
    shots["block_grip_hold"] = frame(play, 1.2, hands=demo_hand())
    battle.phase, battle.phase_at, battle.enemy_guarding = "brace", 1.0, True
    battle.message = "Scorpius blocks: your next spell does half"
    shots["enemy_guards"] = frame(play, 1.5)

    sim_log = os.path.join("simulation", "bot_a_sessions.csv")  # made by tools/simulate.py, if it has been run
    history = progress.load_sessions(sim_log) if os.path.exists(sim_log) else []
    play = new_play(folder, wins=1)
    battle = start_battle(play, 1)
    battle.rounds = demo_rounds()
    battle.enemy_health, battle.player_health = 0, 52
    battle.outcome, battle.phase, battle.new_spells = "won", "checkin", []
    battle.checkin = {"pain": 2}
    shots["checkin"] = frame(play, 9.0)
    battle.checkin = {"pain": 2, "tiredness": 3, "mood": 4}
    battle.phase = "report"
    battle.history = history[:-1]
    battle.session = history[-1] if history else None
    if battle.session is not None:
        battle.session.pain, battle.session.tiredness, battle.session.mood = 2.0, 3.0, 4.0
    shots["report_results"] = frame(play, 9.0)
    battle.report_page = 1
    shots["report_tips"] = frame(play, 9.0)

    play = new_play(folder, assisted=False)
    battle = start_battle(play, 0)
    battle.choose(0, 10.0)
    battle.reach.update([], None, figure(), (0, 0, 1, 1), 10.0, CAL)
    play.reach = battle.reach
    shots["memory_preview"] = frame(play, 11.0)
    shots["memory_hidden"] = frame(play, 14.0)

    play = new_play(folder)
    log = os.path.join(folder, "sessions.csv")
    demo_log(log)
    play.mode, play.sessions = "progress", progress.recent(history or progress.load_sessions(log))
    shots["progress"] = frame(play, 1.0)

    for name, image in shots.items():
        cv2.imwrite(os.path.join(out, f"{name}.png"), image)
        print("wrote", os.path.join(out, f"{name}.png"))


def demo_hand():
    """A fist near the bottom of the screen, for the Block screenshot."""
    from tools.simulate import hand
    return hand(560, 470, 0.9, pointing=False)


class FIGURE_GUARD:
    last_warn = float("-inf")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
