"""Pacing: asking waitKey for less when it oversleeps. Run: .venv/bin/python -m unittest"""
import unittest

from pacing import FramePacer


class PacerTest(unittest.TestCase):
    def test_without_overshoot_it_waits_out_the_rest_of_the_frame(self):
        pacer = FramePacer(1 / 30)
        self.assertEqual(pacer.wait_ms(0.006), 27)
        self.assertEqual(pacer.wait_ms(0.050), 1)  # a slow frame: no wait, but still let the window breathe

    def test_it_learns_a_steady_overshoot_and_the_frame_lands_on_time(self):
        pacer = FramePacer(1 / 30)
        work_ms, late_ms = 6.0, 10.0           # what the start screen measured on macOS
        for _ in range(200):
            asked = pacer.wait_ms(work_ms / 1000)
            pacer.record(asked, asked + late_ms)
        frame = work_ms + pacer.wait_ms(work_ms / 1000) + late_ms
        self.assertAlmostEqual(pacer.overshoot_ms, late_ms, delta=0.5)
        self.assertAlmostEqual(frame, 1000 / 30, delta=1.0)

    def test_early_returns_and_wild_values_do_not_break_it(self):
        pacer = FramePacer(1 / 30)
        pacer.record(20, 5)     # a key press returns early: not negative overshoot
        self.assertEqual(pacer.overshoot_ms, 0.0)
        for _ in range(100):
            pacer.record(20, 5000)  # a stall (window dragged): capped
        self.assertLessEqual(pacer.overshoot_ms, 30.0)


if __name__ == "__main__":
    unittest.main()
