"""Session log: rows in sessions.csv. Run: .venv\\Scripts\\python -m unittest"""
import csv
import os
import tempfile
import unittest
from datetime import datetime

from calibration import Calibration
from session_log import COLUMNS, SessionRecord, append_row

CAL = Calibration(reach=2.0, side="Bellatrix", shoulder=(700.0, 400.0), width=100.0, tilt=0.0,
                  mid=(650.0, 400.0), heights=(400.0, 400.0), nose=None)


class SessionRecordTest(unittest.TestCase):
    def test_max_reach_skips_leaning_frames(self):
        record = SessionRecord("practice", "Aries", warnings_at_start=2)
        record.update([(900.0, 400.0)], CAL, blocked=False, now=10.0)  # 2 shoulder widths away
        record.update([(1100.0, 400.0)], CAL, blocked=True, now=11.0)  # 4 widths, but leaning
        row = record.row(25.5, warnings_now=5, result="completed", date=datetime(2026, 10, 10, 14, 30))
        self.assertEqual(row, {"date": "2026-10-10 14:30:00", "mode": "practice", "time": "15.5",
                               "max reach": "2.00", "lean warnings": 3, "damage dealt": "",
                               "constellation": "Aries", "result": "completed"})

    def test_battle_row_has_damage(self):
        record = SessionRecord("battle", "Scorpius", 0)
        record.update([], CAL, False, 0.0)
        self.assertEqual(record.row(1.0, 0, "won", damage=180)["damage dealt"], 180)


class AppendRowTest(unittest.TestCase):
    def test_header_is_written_once(self):
        path = os.path.join(tempfile.mkdtemp(), "sessions.csv")
        row = SessionRecord("battle", "Orion", 0).row(0.0, 0, "won", damage=50)
        self.assertTrue(append_row(row, path))
        self.assertTrue(append_row(row, path))
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual(len(rows), 3)

    def test_unwritable_path_does_not_raise(self):
        self.assertFalse(append_row({}, os.path.join(tempfile.mkdtemp(), "missing", "sessions.csv")))


if __name__ == "__main__":
    unittest.main()
