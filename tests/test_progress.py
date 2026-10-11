"""Progress: reading sessions.csv for the Progress screen. Run: .venv/bin/python -m unittest"""
import csv
import os
import tempfile
import unittest

import numpy as np

import progress
from progress_screen import draw_progress, plot_points
from session_log import COLUMNS, OLD_COLUMNS


def write(rows, header=COLUMNS):
    path = os.path.join(tempfile.mkdtemp(), "sessions.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, restval="")
        w.writeheader()
        w.writerows(rows)
    return path


def row(date, **kw):
    base = {"date": date, "mode": "practice", "lean warnings": 0, "constellation": "Aries", "result": "completed",
            "assisted": "on", "stars hit": 4, "time per star": "2.0"}
    return {**base, **kw}


class LoadTest(unittest.TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(progress.load_sessions("/nonexistent/sessions.csv"), [])

    def test_old_rows_without_the_new_columns_still_load(self):
        path = write([{"date": "2026-10-01 10:00:00", "mode": "battle", "lean warnings": 2, "result": "won"}], OLD_COLUMNS)
        (s,) = progress.load_sessions(path)
        self.assertEqual((s.lean_warnings, s.assisted, s.time_per_star, s.error_sw), (2, True, None, None))

    def test_series(self):
        path = write([row("2026-10-01 10:00:00", **{"time per star": "3.0", "lean warnings": 4}),
                      row("2026-10-02 10:00:00", assisted="off", **{"avg error sw": "0.250", "avg error px": "25.0",
                                                                    "time per star": "2.5", "lean warnings": 1}),
                      row("2026-10-03 10:00:00", assisted="off", **{"avg error sw": "0.100", "avg error px": "10.0",
                                                                    "time per star": "", "lean warnings": 0})])
        sessions = progress.load_sessions(path)
        self.assertEqual(progress.time_series(sessions), [3.0, 2.5])
        self.assertEqual(progress.lean_series(sessions), [4, 1, 0])
        self.assertEqual([s.error_sw for s in progress.unassisted(sessions)], [0.25, 0.1])
        self.assertEqual(progress.last_unassisted(sessions).date, "2026-10-03 10:00:00")

    def test_assisted_sessions_are_not_in_the_unassisted_accuracy(self):
        sessions = progress.load_sessions(write([row("2026-10-01 10:00:00", **{"avg error sw": "0.2"})]))
        self.assertEqual(progress.unassisted(sessions), [])
        self.assertIsNone(progress.last_unassisted(sessions))

    def test_only_the_most_recent_sessions_are_kept(self):
        sessions = progress.load_sessions(write([row(f"2026-10-{d:02d} 10:00:00") for d in range(1, 29)]))
        self.assertEqual(len(progress.recent(sessions)), progress.MAX_SESSIONS)
        self.assertEqual(progress.recent(sessions)[-1].date, "2026-10-28 10:00:00")


class DrawTest(unittest.TestCase):
    def test_points_rise_with_the_value_and_stay_inside_the_plot(self):
        pts = plot_points([1.0, 2.0, 4.0], (100, 100, 300, 300), top=4.0)
        self.assertEqual([p[0] for p in pts], [100, 200, 300])
        self.assertEqual([p[1] for p in pts], sorted((p[1] for p in pts), reverse=True))
        self.assertEqual(pts[2][1], 100)
        self.assertEqual(plot_points([0.0], (100, 100, 300, 300), top=1.0), [(200, 300)])

    def test_the_screen_draws_with_no_sessions_and_with_many(self):
        for sessions in ([], progress.load_sessions(write([row(f"2026-10-{d:02d} 10:00:00", assisted="off",
                                                                **{"avg error sw": f"0.{d}", "avg error px": "10"})
                                                          for d in range(1, 9)]))):
            frame = np.zeros((720, 1280, 3), np.uint8)
            draw_progress(frame, sessions, 0.0)
            self.assertGreater(frame.max(), 0)



if __name__ == "__main__":
    unittest.main()


class MetricsTest(unittest.TestCase):
    def test_every_metric_has_a_direction_and_parses_from_a_row(self):
        r = row("2026-10-01 10:00:00", **{"reach pct": "92", "straightness": "0.81", "tremor sw": "0.031",
                                          "slowdown": "1.10", "grip reps": "4", "grip holds": "3", "open s": "1.4",
                                          "pain": "2", "tiredness": "3", "mood": "4", "lean warnings": 2,
                                          "avg error sw": "0.12", "max reach": "1.9"})
        s = progress.parse_row(r)
        for m in progress.METRICS:
            self.assertIn(m.better, ("higher", "lower"))
            self.assertIsNotNone(s.value(m.key), m.key)
        self.assertEqual((s.lean_per_10, s.grip_hold_pct), (5.0, 75.0))

    def test_trend_direction_respects_which_way_is_better(self):
        self.assertEqual(progress.trend([80, 85, 90, 95], "higher"), "better")
        self.assertEqual(progress.trend([0.3, 0.25, 0.2, 0.15], "lower"), "better")
        self.assertEqual(progress.trend([0.15, 0.2, 0.3], "lower"), "worse")
        self.assertEqual(progress.trend([90, 91, 90, 90], "higher"), "same")
        self.assertIsNone(progress.trend([1, 2], "higher"))

    def test_compare_uses_the_last_five_earlier_sessions(self):
        earlier = [progress.parse_row(row(f"2026-10-0{d} 10:00:00", **{"reach pct": str(v)}))
                   for d, v in enumerate((10, 80, 80, 80, 80, 80), 1)]
        now = progress.parse_row(row("2026-10-09 10:00:00", **{"reach pct": "90"}))
        self.assertEqual(progress.compare(now, earlier, "reach_pct"), (90.0, 80.0, "better"))
        self.assertIsNone(progress.compare(now, [], "reach_pct"))
