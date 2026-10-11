"""Assisted learning off: preview, hidden stars, the larger hit radius, error recording and hints.
Run: .venv/bin/python -m unittest"""
import unittest

from game.difficulty import NORMAL
from sessions import reach as reach_module
from sessions.reach import Reach, load_constellation
from tests.helpers import CAL, FIGURE, SIZE, WHOLE_VIEW, hand_at


def new_reach(assisted):
    return Reach(load_constellation("constellations/aries.json"), SIZE, difficulty=NORMAL, assisted=assisted)


def hold(reach, point, start, seconds=0.5):
    """Keep a fingertip at a pixel from `start` for `seconds`; returns the end time."""
    t = start
    while t <= start + seconds:
        reach.update(hand_at(*point), None, FIGURE, WHOLE_VIEW, t, CAL)
        t += 0.05
    return t


class PreviewTest(unittest.TestCase):
    def test_assisted_never_hides_anything(self):
        reach = new_reach(True)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        self.assertFalse(reach.previewing(0.0))
        self.assertTrue(reach.target_visible(50.0))

    def test_unassisted_shows_the_whole_shape_for_three_seconds_then_hides_it(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 10.0, CAL)
        self.assertTrue(reach.previewing(10.0))
        self.assertTrue(reach.previewing(12.9))
        self.assertAlmostEqual(reach.preview_left(11.0), 2.0)
        self.assertFalse(reach.previewing(13.0))
        self.assertFalse(reach.target_visible(13.5))

    def test_the_shape_is_not_shown_before_the_player_is_there(self):
        reach = new_reach(False)
        reach.update([], None, None, WHOLE_VIEW, 0.0, CAL)
        self.assertFalse(reach.previewing(0.0))


class MemoryHitTest(unittest.TestCase):
    def test_a_slightly_larger_radius_counts_when_unassisted(self):
        assisted, memory = new_reach(True), new_reach(False)
        for r in (assisted, memory):
            r.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        self.assertGreater(memory.accept_radius, assisted.accept_radius)
        self.assertLess(memory.accept_radius, 2 * assisted.accept_radius)
        x, y = assisted.points[0]
        near = (x + assisted.hit_radius * 1.15, y)  # outside the normal radius, inside the memory radius
        hold(assisted, near, 1.0)
        hold(memory, near, 1.0)
        self.assertEqual(len(assisted.lit_at), 0)
        self.assertEqual(len(memory.lit_at), 1)

    def test_a_star_needs_a_dwell_not_a_swipe(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        hold(reach, reach.points[0], 1.0, seconds=0.1)
        self.assertEqual(len(reach.lit_at), 0)
        hold(reach, reach.points[0], 2.0, seconds=0.5)
        self.assertEqual(len(reach.lit_at), 1)

    def test_each_stars_error_is_recorded_in_pixels_and_shoulder_widths(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        x, y = reach.points[0]
        hold(reach, (x + 30, y), 1.0)
        self.assertEqual(len(reach.errors_px), 1)
        self.assertAlmostEqual(reach.errors_px[0], 30.0, places=3)
        self.assertAlmostEqual(reach.errors_sw[0], 30.0 / CAL.width, places=3)

    def test_errors_are_recorded_when_assisted_too(self):
        reach = new_reach(True)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        hold(reach, reach.points[0], 1.0)
        self.assertAlmostEqual(reach.errors_px[0], 0.0, places=3)

    def test_holding_still_away_from_the_star_is_a_miss_once_per_stop(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        far = (reach.points[0][0] + 300, reach.points[0][1] + 100)
        hold(reach, far, 1.0, seconds=reach_module.MISS_STILL_SECONDS + 1.5)
        self.assertEqual(reach.misses, 1)
        hold(reach, (far[0] + 200, far[1]), 5.0, seconds=2.0)  # moves on, stops again
        self.assertEqual(reach.misses, 2)

    def test_assisted_play_has_no_misses(self):
        reach = new_reach(True)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        hold(reach, (reach.points[0][0] + 300, reach.points[0][1]), 1.0, seconds=3.0)
        self.assertEqual(reach.misses, 0)


class HintTest(unittest.TestCase):
    def test_a_hint_shows_the_next_star_for_a_moment_and_is_counted(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        self.assertTrue(reach.hint(5.0))
        self.assertEqual(reach.hints, 1)
        self.assertTrue(reach.target_visible(5.5))
        self.assertFalse(reach.target_visible(5.0 + reach_module.HINT_SECONDS + 0.1))

    def test_pressing_hint_while_one_is_showing_does_not_count_twice(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        reach.hint(5.0)
        self.assertFalse(reach.hint(5.5))
        self.assertEqual(reach.hints, 1)
        self.assertTrue(reach.hint(8.0))
        self.assertEqual(reach.hints, 2)

    def test_no_hints_when_assisted_or_when_nothing_is_left_to_hint(self):
        assisted = new_reach(True)
        assisted.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        self.assertFalse(assisted.hint(1.0))
        self.assertEqual(assisted.hints, 0)
        done = new_reach(False)
        done.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        done.won_at = 3.0
        self.assertFalse(done.hint(4.0))

    def test_being_stuck_suggests_the_hint_key(self):
        reach = new_reach(False)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        self.assertFalse(reach.stuck(reach_module.STUCK_SECONDS - 1))
        self.assertTrue(reach.stuck(reach_module.STUCK_SECONDS + 1))


if __name__ == "__main__":
    unittest.main()


class MovementQualityTest(unittest.TestCase):
    def test_a_straight_reach_scores_1_and_a_detour_scores_lower(self):
        straight, detour = new_reach(True), new_reach(True)
        for r in (straight, detour):
            r.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        a, b = straight.points[0], straight.points[1]
        hold(straight, a, 1.0)
        hold(detour, a, 1.0)
        for t in range(10):  # straight: along the line from a to b
            k = (t + 1) / 10
            straight.update(hand_at(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k), None, FIGURE, WHOLE_VIEW, 3 + t * 0.05, CAL)
        mid = ((a[0] + b[0]) / 2 + 120, (a[1] + b[1]) / 2 + 120)
        for p in (mid, b):  # detour: out of the way, then to b
            detour.update(hand_at(*p), None, FIGURE, WHOLE_VIEW, 3.0, CAL)
        hold(straight, b, 4.0)
        hold(detour, b, 4.0)
        self.assertAlmostEqual(straight.straightness[1], 1.0, places=2)
        self.assertLess(detour.straightness[1], 0.8)
        self.assertEqual(len(straight.move_seconds), 2)

    def test_tremor_is_the_wobble_while_holding(self):
        steady, shaky = new_reach(True), new_reach(True)
        for r in (steady, shaky):
            r.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        x, y = steady.points[0]
        hold(steady, (x, y), 1.0)
        for i in range(12):
            shaky.update(hand_at(x + (8 if i % 2 else -8), y), None, FIGURE, WHOLE_VIEW, 1.0 + i * 0.05, CAL)
        self.assertAlmostEqual(steady.tremor_px[0], 0.0, places=3)
        self.assertGreater(shaky.tremor_px[0], 6)

    def test_a_smooth_drift_onto_the_star_is_not_tremor(self):
        from sessions.reach import tremor
        drift = [(i * 0.033, 100 + 3 * i, 200 - 2 * i) for i in range(10)]   # still gliding in, steadily
        shake = [(i * 0.033, 100 + (4 if i % 2 else -4), 200) for i in range(10)]
        self.assertAlmostEqual(tremor(drift), 0.0, places=6)
        self.assertAlmostEqual(tremor(shake), 4.0, delta=0.5)
        self.assertEqual(tremor([(0, 1, 1)]), 0.0)

    def test_tracking_glitches_do_not_count_as_movement(self):
        reach = new_reach(True)
        reach.update([], None, FIGURE, WHOLE_VIEW, 0.0, CAL)
        reach.follow((100, 100), 1.0)
        reach.follow((900, 600), 1.03)   # a jump across the screen in one frame
        self.assertEqual(reach.path_px, 0.0)
        self.assertEqual(len(reach.trace), 2)
