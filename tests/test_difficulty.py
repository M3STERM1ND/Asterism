"""Difficulty: scaling, the reach limit (never past the patient's calibrated reach), enemy choices.
Run: .venv/bin/python -m unittest"""
import unittest

import numpy as np

from game import difficulty as levels
from game.battle import BATTLES, Battle
from sessions.reach import Reach, load_constellation
from tests.helpers import CAL, FIGURE, SIZE, WHOLE_VIEW


class ScalingTest(unittest.TestCase):
    def test_enemy_health_and_strike_scale_with_difficulty(self):
        base = BATTLES[1]
        health = [Battle(base, SIZE, d).enemy_max for d in levels.DIFFICULTIES]
        strike = [Battle(base, SIZE, d).strike_base for d in levels.DIFFICULTIES]
        self.assertEqual(health, [126, 180, 234])
        self.assertEqual(strike, [18, 25, 32])
        self.assertTrue(health == sorted(health) and strike == sorted(strike))

    def test_the_enemy_blocks_more_often_on_harder_levels(self):
        chances = [d.enemy_guard_chance for d in levels.DIFFICULTIES]
        self.assertEqual(chances, sorted(chances))
        self.assertLess(chances[0], chances[-1])

    def test_easier_means_a_bigger_hit_radius_and_more_mana(self):
        self.assertGreater(levels.EASY.hit_radius, levels.NORMAL.hit_radius)
        self.assertGreater(levels.NORMAL.hit_radius, levels.HARD.hit_radius)
        self.assertGreater(levels.EASY.mana_refill, levels.NORMAL.mana_refill)
        self.assertGreater(levels.NORMAL.mana_refill, levels.HARD.mana_refill)

    def test_enemies_attack_or_block_and_only_hard_ones_heal_or_attack_twice(self):
        for d in (levels.EASY, levels.NORMAL):
            self.assertEqual({levels.choose_enemy_action(r / 100, d) for r in range(100)}, {"strike", "guard"})
        self.assertEqual({levels.choose_enemy_action(r / 100, levels.HARD) for r in range(100)},
                         {"strike", "double", "heal", "guard"})

    def test_enemy_action_shares_match_the_difficulty(self):
        for d in levels.DIFFICULTIES:
            actions = [levels.choose_enemy_action(r / 1000, d) for r in range(1000)]
            self.assertAlmostEqual(actions.count("guard") / 1000, d.enemy_guard_chance, delta=0.002)
            self.assertAlmostEqual(actions.count("heal") / 1000, d.heal_chance, delta=0.002)

    def test_ladder_gets_harder_and_every_enemy_is_new(self):
        self.assertGreater(len(BATTLES), 2)
        self.assertEqual(sorted(b["health"] for b in BATTLES), [b["health"] for b in BATTLES])
        self.assertEqual(sorted(b["strike"] for b in BATTLES), [b["strike"] for b in BATTLES])
        self.assertEqual(len({b["enemy"] for b in BATTLES}), len(BATTLES))

    def test_difficulty_cycles_and_unknown_names_are_normal(self):
        self.assertEqual([levels.next_difficulty(d).name for d in levels.DIFFICULTIES], ["Normal", "Hard", "Easy"])
        self.assertIs(levels.by_name("nonsense"), levels.NORMAL)


class ReachLimitTest(unittest.TestCase):
    def placed(self, difficulty, name):
        reach = Reach(load_constellation(f"constellations/{name}.json"), SIZE, difficulty=difficulty)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        return reach

    def test_stars_stay_within_the_difficultys_share_of_calibrated_reach(self):
        full = CAL.reach * CAL.width
        for d, share in ((levels.EASY, 0.80), (levels.NORMAL, 0.95), (levels.HARD, 1.10)):
            for name in ("aries", "orion", "scorpius", "leo"):
                far = max(np.hypot(*(np.array(p) - CAL.shoulder)) for p in self.placed(d, name).points)
                self.assertLessEqual(far, full * share + 1e-6, f"{d.name} {name}")

    def test_no_difficulty_can_go_past_110_percent(self):
        wild = levels.Difficulty("Wild", 3.0, 40, 1, 1, 10, 0, 0)
        self.assertEqual(levels.reach_fraction(wild), levels.MAX_REACH_FRACTION)
        full = CAL.reach * CAL.width
        far = max(np.hypot(*(np.array(p) - CAL.shoulder)) for p in self.placed(wild, "scorpius").points)
        self.assertLessEqual(far, full * 1.10 + 1e-6)

    def test_spacing_and_the_reach_limit_hold_together_even_for_a_short_reach(self):
        """Clamping to the reach after spreading the stars used to pull them back together (Pisces ended up
        24 px apart on Easy). Every spell, every difficulty, short and long reaches: both rules must hold."""
        from calibration import Calibration
        from game.spells import SPELLS
        from sessions import placement
        for reach_sw, width in ((2.32, 149.0), (2.0, 100.0), (1.0, 120.0)):
            cal = Calibration(reach_sw, "Bellatrix", (715.0, 418.0), width, 0.0, (640.0, 418.0), (418.0, 418.0), None)
            for d in levels.DIFFICULTIES:
                for spell in SPELLS:
                    reach = Reach(load_constellation(f"constellations/{spell.constellation}.json"), SIZE, difficulty=d)
                    reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, cal)
                    label = f"{spell.name} {d.name} reach {reach_sw}x{width}"
                    self.assertGreaterEqual(placement.closest_step(reach.points), 1.75 * d.hit_radius - 0.5, label)
                    far = max(np.hypot(*(np.array(p) - cal.shoulder)) for p in reach.points)
                    self.assertLessEqual(far, levels.reach_limit(cal, d) + 1e-6, label)

    def test_easy_sits_closer_than_hard(self):
        def farthest(d):
            return max(np.hypot(*(np.array(p) - CAL.shoulder)) for p in self.placed(d, "scorpius").points)
        self.assertLess(farthest(levels.EASY), farthest(levels.NORMAL))
        self.assertLess(farthest(levels.NORMAL), farthest(levels.HARD))


if __name__ == "__main__":
    unittest.main()
