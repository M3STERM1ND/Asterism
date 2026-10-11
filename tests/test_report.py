"""Report: round conclusions, rehab findings against earlier sessions, the conclusion, and the tips.
Run: .venv/bin/python -m unittest"""
import unittest

from game import report
from game.report import Round, SAFETY_TIP
from progress import Session


def drawn(number=1, error=0.05, leaned=0, path=0.9, **kw):
    r = Round(number, "attack", "Aries", total_stars=4, stars=4, damage=30, leaned=leaned, **kw)
    r.errors_sw, r.errors_px, r.straightness = [error] * 4, [error * 100] * 4, [path] * 4
    return r


def session(**kw):
    base = dict(date="2026-10-10 10:00:00", mode="battle", assisted=True, stars=20, time_per_star=2.0,
                lean_warnings=0, error_sw=0.08, error_px=12.0, hints=0, spell="Aries", result="won",
                reach_pct=97.0, straightness=0.9, tremor_sw=0.02, slowdown=1.0, grip_reps=2, grip_holds=2, open_s=0.8)
    base.update(kw)
    return Session(**base)


class RoundTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual([report.aim_word(e) for e in (0.05, 0.15, 0.3, None)], ["precise", "fair", "loose", None])
        self.assertEqual([report.path_word(p) for p in (0.9, 0.75, 0.5, None)], ["smooth", "fairly smooth", "wandering", None])

    def test_attack_conclusions(self):
        self.assertEqual(report.round_conclusion(drawn()), "Precise aim, smooth path, no leaning.")
        self.assertIn("2 leans", report.round_conclusion(drawn(leaned=2, error=0.3)))
        self.assertIn("guard halved", report.round_conclusion(drawn(enemy_blocked=True)))
        self.assertNotIn("guard", report.round_conclusion(drawn(enemy_blocked=True), with_block=False))

    def test_block_and_rest_conclusions(self):
        self.assertIn("Opened in 1.2 s", report.round_conclusion(Round(1, "block", shield="full", open_seconds=1.2)))
        self.assertIn("before the hold", report.round_conclusion(Round(1, "block", shield="cracked")))
        self.assertEqual(report.round_conclusion(Round(1, "block")), "Block given up.")
        self.assertIn("rested", report.round_conclusion(Round(1, "rest", rested=True)))

    def test_enemy_outcomes(self):
        self.assertEqual(report.enemy_outcome(drawn(results=["blocked"])), "attack blocked")
        self.assertEqual(report.enemy_outcome(drawn(results=["hit"], damage_taken=18)), "hit you -18")
        self.assertEqual(report.enemy_outcome(drawn(results=["half"], damage_taken=9)), "half got through -9")
        self.assertEqual(report.enemy_outcome(drawn(results=["blocked", "blocked"])), "both attacks blocked")
        self.assertEqual(report.enemy_outcome(drawn(enemy_action="guard")), "blocked (guard up)")
        self.assertEqual(report.enemy_outcome(drawn(enemy_action="heal", healed=20)), "healed 20")

    def test_stats(self):
        rounds = [drawn(1, results=["hit"], damage_taken=20), Round(2, "block", shield="full", results=["blocked"]),
                  Round(3, "rest", rested=True)]
        stats = report.battle_stats(rounds)
        self.assertEqual((stats["rounds"], stats["attacks"], stats["blocks made"], stats["full blocks"]), (3, 1, 1, 1))
        self.assertEqual((stats["stars hit"], stats["damage taken"], stats["attacks stopped"]), (4, 20, 1))


class FindingsTest(unittest.TestCase):
    def test_each_measure_is_compared_with_the_recent_average(self):
        earlier = [session(reach_pct=80.0, error_sw=0.15, open_s=2.0)] * 3
        rows = {m.key: (v, b, d) for m, v, b, d in report.findings(session(), earlier)}
        self.assertEqual(rows["reach_pct"], (97.0, 80.0, "better"))
        self.assertEqual(rows["error_sw"][2], "better")   # lower error is better
        self.assertEqual(rows["open_s"][2], "better")     # faster opening is better
        self.assertEqual(rows["straightness"][2], "same")

    def test_the_first_session_has_nothing_to_compare_with(self):
        rows = report.findings(session(), [])
        self.assertTrue(rows)
        self.assertTrue(all(b is None and d is None for _, _, b, d in rows))

    def test_missing_measures_are_left_out(self):
        keys = [m.key for m, *_ in report.findings(session(grip_reps=0, open_s=None, slowdown=None), [])]
        self.assertNotIn("open_s", keys)
        self.assertNotIn("grip_hold_pct", keys)
        self.assertNotIn("slowdown", keys)


class ConclusionTest(unittest.TestCase):
    def test_a_good_session_lists_strengths_and_improvements(self):
        stats = report.battle_stats([drawn(), Round(2, "block", shield="full")])
        lines = report.general_conclusion(stats, session(), True, {}, [session(reach_pct=80.0)] * 3)
        self.assertTrue(lines[0].startswith("Victory in 2 rounds: 4 reaches and 1 grip reps"))
        text = " ".join(lines)
        for word in ("used the full reach range", "precise aim", "smooth paths", "no leaning", "every grip held", "range used"):
            self.assertIn(word, text)

    def test_a_worse_day_is_reported_gently(self):
        stats = report.battle_stats([drawn()])
        text = " ".join(report.general_conclusion(stats, session(error_sw=0.3), False, {}, [session()] * 3))
        self.assertIn("fell", text)
        self.assertIn("Not as good as recently: accuracy", text)
        self.assertIn("watch the trend", text)

    def test_high_pain_is_called_out(self):
        stats = report.battle_stats([drawn()])
        self.assertIn("stop for today", " ".join(report.general_conclusion(stats, session(), True, {"pain": 4})))


class TipsTest(unittest.TestCase):
    def test_every_kind_of_round_gets_a_tip(self):
        for r in (drawn(), drawn(leaned=1), drawn(path=0.5), drawn(error=0.3), drawn(results=["hit"]), drawn(hints=1),
                  Round(1, "rest", rested=True), Round(1, "block", shield="full", open_seconds=3.0),
                  Round(1, "block", shield="full", open_seconds=0.5), Round(1, "block", shield="cracked")):
            self.assertGreater(len(report.round_tip(r)), 20)

    def test_the_round_tip_targets_the_main_problem(self):
        self.assertIn("shoulders level", report.round_tip(drawn(leaned=2, path=0.5)))
        self.assertIn("straight line", report.round_tip(drawn(path=0.5)))
        self.assertIn("Opening was slow", report.round_tip(Round(1, "block", shield="full", open_seconds=3.0)))

    def test_pain_comes_first_and_safety_comes_last(self):
        tips = report.rehab_tips(session(lean_warnings=10), {"pain": 5}, True)
        self.assertTrue(tips[0].startswith("Pain"))
        self.assertEqual(tips[-1], SAFETY_TIP)
        self.assertLessEqual(len(tips), 4)

    def test_tips_follow_the_measures(self):
        weak = session(lean_warnings=8, reach_pct=70.0, straightness=0.5, tremor_sw=0.12, open_s=3.0, grip_holds=1,
                       slowdown=1.5)
        text = " ".join(report.rehab_tips(weak, {}, True))
        self.assertIn("Tiredness", text)   # slowdown counts as tiredness
        self.assertIn("Posture", text)
        self.assertIn("Range", text)

    def test_never_blocking_is_noticed(self):
        stats = report.battle_stats([drawn(results=["hit"])])
        self.assertIn("never chose Block", " ".join(report.rehab_tips(session(grip_reps=0, grip_holds=0, open_s=None),
                                                                      {}, True, stats)))

    def test_a_strong_session_still_gets_a_tip_and_a_loss_gets_encouragement(self):
        self.assertGreaterEqual(len(report.rehab_tips(session(), {}, True)), 2)
        self.assertIn("still counted", " ".join(report.rehab_tips(session(), {}, False)))


if __name__ == "__main__":
    unittest.main()
