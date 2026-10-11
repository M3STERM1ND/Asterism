"""Therapist report and the bot simulation. Run: .venv/bin/python -m unittest"""
import os
import random
import tempfile
import unittest
from unittest import mock

import therapy_report
from progress import Session
from tools import simulate


def sessions(n, **trends):
    """n sessions where each named measure moves linearly from its start to its end value."""
    out = []
    for i in range(n):
        k = i / max(1, n - 1)
        values = {key: start + (end - start) * k for key, (start, end) in trends.items()}
        out.append(Session(date=f"2026-09-{i + 1:02d} 10:00:00", mode="battle", assisted=i % 2 == 0, stars=20,
                           time_per_star=2.0, lean_warnings=int(values.pop("leans", 0)), error_sw=0.1, error_px=15.0,
                           hints=0, spell="Aries", result="won", grip_reps=2, grip_holds=2, **values))
    return out


class ObservationsTest(unittest.TestCase):
    def levels(self, notes):
        return {level for level, _ in notes}

    def test_improvement_is_reported_as_good(self):
        notes = therapy_report.observations(sessions(8, max_reach=(1.4, 2.0), straightness=(0.6, 0.9)))
        texts = " ".join(t for _, t in notes)
        self.assertIn("Active reach is growing", texts)
        self.assertIn("straighter", texts)
        self.assertNotIn("alert", self.levels(notes))

    def test_recent_high_pain_is_an_alert_and_rising_pain_a_watch(self):
        notes = therapy_report.observations(sessions(8, pain=(1.0, 5.0)))
        self.assertEqual(notes[0][0], "alert")
        self.assertIn("Pain answers are rising", " ".join(t for _, t in notes))

    def test_more_leaning_and_less_reach_are_watched(self):
        texts = " ".join(t for _, t in therapy_report.observations(sessions(8, leans=(0, 8), max_reach=(2.0, 1.5))))
        self.assertIn("Leaning", texts)
        self.assertIn("shrinking", texts)

    def test_no_sessions(self):
        self.assertEqual(therapy_report.observations([]), [("watch", "No sessions recorded yet.")])


class BuildTest(unittest.TestCase):
    def test_the_report_has_every_section_and_escapes_text(self):
        page = therapy_report.build_report(sessions(6, max_reach=(1.5, 1.9), pain=(2, 1), mood=(3, 4)),
                                           title="Report <x>", traces=[("early", [(0, 0), (100, 50)], [(0.0, 0, 0), (0.1, 50, 20), (0.2, 100, 50)])])
        for part in ("Worth a look", "Overall trend", "Each measure", "How the patient felt", "Movement", "Sessions",
                     "not a clinical assessment", "Report &lt;x&gt;"):
            self.assertIn(part, page)
        self.assertNotIn("Report <x>", page)

    def test_an_empty_log_still_builds_and_writes(self):
        path = os.path.join(tempfile.mkdtemp(), "out", "report.html")
        self.assertEqual(therapy_report.write_report([], path), path)
        self.assertIn("No data yet", open(path, encoding="utf-8").read())

    def test_the_game_key_writes_and_opens_the_report(self):
        folder = tempfile.mkdtemp()
        with mock.patch.object(therapy_report.webbrowser, "open") as opened:
            written = therapy_report.generate_and_open(os.path.join(folder, "none.csv"), os.path.join(folder, "r.html"))
        self.assertTrue(os.path.exists(written))
        opened.assert_called_once()

    def test_first_and_latest_averages(self):
        self.assertEqual(therapy_report.edge_averages([1, 2, 3, 4, 5, 6, 7]), (2.0, 6.0))
        self.assertEqual(therapy_report.edge_averages([1]), (None, None))


class SimulationTest(unittest.TestCase):
    def test_a_bot_battle_runs_the_real_game_to_a_result_with_reaches_and_grips(self):
        from calibration import Calibration
        from game.battle import BATTLES, Battle
        from session_log import SessionRecord
        rng = random.Random(3)
        bot = simulate.Bot(simulate.BOT_A, 12, rng)
        bot.block_p = 1.0
        cal = Calibration(bot.reach_sw, "Bellatrix", simulate.SHOULDER, simulate.WIDTH, 0.0,
                          (640.0, 418.0), (418.0, 418.0), None)
        battle = Battle(BATTLES[0], simulate.SIZE, rng=random.Random(1))
        battle.player_health = 40  # hurt: the bot will choose Block at once
        record = SessionRecord("battle", "Warm-up", 0)
        result, seconds = simulate.play_battle(bot, battle, cal, simulate.Guard(), record, 0.0)
        self.assertIn(result, ("won", "lost"))
        self.assertEqual(battle.phase, "report")
        self.assertEqual(set(battle.checkin), {"pain", "tiredness", "mood"})
        self.assertTrue(battle.grips and battle.grips[0].result in ("block", "early"))
        self.assertGreater(sum(len(c.lit_at) for c in battle.casts), 0)

    def test_profiles_move_from_start_to_end(self):
        rng = random.Random(0)
        self.assertAlmostEqual(simulate.level_at((1.0, 2.0), 0.0, 2.0, rng, 0.0), 1.0)
        self.assertAlmostEqual(simulate.level_at((1.0, 2.0), 1.0, 2.0, rng, 0.0), 2.0)
        self.assertGreater(simulate.level_at((1.0, 2.0), 0.5, 2.0, rng, 0.0), 1.5)  # early gains

    def test_a_fake_fist_reads_as_a_fist(self):
        from sessions.grip import CLOSED, OPEN, openness
        self.assertLess(openness(simulate.hand(600, 500, 0.85, pointing=False)[0]), CLOSED)
        self.assertGreater(openness(simulate.hand(600, 500, 1.7, pointing=False)[0]), OPEN)


if __name__ == "__main__":
    unittest.main()
