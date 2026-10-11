"""Session log: rows in sessions.csv. Run: .venv\\Scripts\\python -m unittest"""
import csv
import os
import tempfile
import unittest
from datetime import datetime

from calibration import Calibration
from session_log import COLUMNS, OLD_COLUMNS, SessionRecord, append_row, fill_row, upgrade_log
from sessions.reach import Reach, load_constellation

CAL = Calibration(reach=2.0, side="Bellatrix", shoulder=(700.0, 400.0), width=100.0, tilt=0.0,
                  mid=(650.0, 400.0), heights=(400.0, 400.0), nose=None)


class SessionRecordTest(unittest.TestCase):
    def test_max_reach_skips_leaning_frames(self):
        record = SessionRecord("practice", "Aries", warnings_at_start=2)
        record.update([(900.0, 400.0)], CAL, blocked=False, now=10.0)  # 2 shoulder widths away
        record.update([(1100.0, 400.0)], CAL, blocked=True, now=11.0)  # 4 widths, but leaning
        row = record.row(25.5, warnings_now=5, result="completed", date=datetime(2026, 10, 10, 14, 30))
        self.assertEqual({k: row[k] for k in OLD_COLUMNS},
                         {"date": "2026-10-10 14:30:00", "mode": "practice", "time": "15.5",
                          "max reach": "2.00", "lean warnings": 3, "damage dealt": "",
                          "constellation": "Aries", "result": "completed"})
        self.assertEqual(list(row), COLUMNS)
        self.assertEqual((row["stars hit"], row["avg error px"], row["time per star"]), (0, "", ""))

    def test_row_carries_the_new_progress_columns(self):
        reach = Reach(load_constellation("constellations/aries.json"), (1280, 720))
        reach.points, reach.started_at = [(0, 0)] * 4, 10.0
        for t, err in ((11.0, 10.0), (12.0, 20.0), (13.0, 30.0)):
            reach.lit_at.append(t)
            reach.errors_px.append(err)
            reach.errors_sw.append(err / 100)
        reach.hints, reach.misses = 2, 1
        record = SessionRecord("practice", "Aries", 0, difficulty="Hard", assisted=False, arm="left")
        record.absorb(reach)
        record.absorb(reach)  # counting the same drawing twice changes nothing
        row = record.row(30.0, 0, "completed")
        self.assertEqual((row["difficulty"], row["assisted"], row["spell"], row["arm"]), ("Hard", "off", "Aries", "left"))
        self.assertEqual((row["stars hit"], row["avg error px"], row["avg error sw"]), (3, "20.0", "0.200"))
        self.assertEqual((row["hints used"], row["misses"], row["time per star"]), (2, 1, "1.00"))

    def test_rehab_columns(self):
        from types import SimpleNamespace
        reach = Reach(load_constellation("constellations/aries.json"), (1280, 720))
        reach.points, reach.started_at = [(0, 0)] * 4, 0.0
        reach.lit_at = [1.0 * i for i in range(1, 7)]
        reach.errors_px = [10.0] * 6
        reach.straightness, reach.tremor_px = [0.8, 0.9] * 3, [5.0] * 6
        reach.move_seconds = [1.0, 1.0, 1.5, 1.5, 2.0, 2.0]
        record = SessionRecord("battle", "Warm-up", 0)
        record.update([(900.0, 400.0)], CAL, False, 0.0)  # 2.0 shoulder widths = the full calibrated reach
        record.absorb(reach)
        record.absorb_grip(SimpleNamespace(result="block", open_seconds=1.5))
        record.absorb_grip(SimpleNamespace(result="early", open_seconds=None))
        record.absorb_grip(SimpleNamespace(result=None, open_seconds=None))  # never finished: not counted
        row = record.row(10.0, 0, "won")
        self.assertEqual((row["reach pct"], row["straightness"], row["tremor sw"], row["slowdown"]), ("100", "0.85", "0.050", "2.00"))
        self.assertEqual((row["grip reps"], row["grip holds"], row["open s"]), (2, 1, "1.50"))
        self.assertEqual((row["pain"], row["tiredness"], row["mood"]), ("", "", ""))

    def test_slowdown_needs_enough_stars(self):
        record = SessionRecord("battle", "Warm-up", 0)
        record.move_seconds = [1.0] * 5
        self.assertIsNone(record.slowdown())

    def test_a_battle_row_lists_every_spell_cast(self):
        record = SessionRecord("battle", "Warm-up", 0)
        for name in ("Aries", "Taurus", "Aries"):
            reach = Reach({"name": name, "stars": [(0, 0), (1, 1)]}, (1280, 720))
            reach.lit_at.append(1.0)
            record.absorb(reach)
        self.assertEqual(record.row(1.0, 0, "won")["spell"], "Aries+Taurus")

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

    def test_an_old_log_gets_the_new_columns_and_keeps_every_row(self):
        path = os.path.join(tempfile.mkdtemp(), "sessions.csv")
        old_rows = [["2026-10-01 10:00:00", "battle", "61.0", "1.90", "2", "180", "Scorpius", "won"],
                    ["2026-10-02 10:00:00", "practice", "20.5", "1.40", "0", "", "Aries", "completed"]]
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([OLD_COLUMNS] + old_rows)
        upgrade_log(path)
        upgrade_log(path)  # idempotent
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), COLUMNS)
        self.assertEqual([[r[c] for c in OLD_COLUMNS] for r in rows], old_rows)
        self.assertEqual({r["difficulty"] for r in rows}, {""})
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_appending_to_an_old_log_upgrades_it_first(self):
        path = os.path.join(tempfile.mkdtemp(), "sessions.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([OLD_COLUMNS, ["2026-10-01 10:00:00", "battle", "1", "1", "0", "5", "Orion", "won"]])
        append_row(SessionRecord("battle", "Orion", 0, difficulty="Easy").row(0.0, 0, "won", damage=50), path)
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r["difficulty"] for r in rows], ["", "Easy"])
        self.assertEqual(rows[0]["constellation"], "Orion")

    def test_the_checkin_fills_in_its_own_row(self):
        path = os.path.join(tempfile.mkdtemp(), "sessions.csv")
        first = SessionRecord("battle", "Warm-up", 0).row(0.0, 0, "won", date=datetime(2026, 10, 10, 9, 0))
        second = SessionRecord("battle", "Scorpius", 0).row(0.0, 0, "won", date=datetime(2026, 10, 10, 9, 5))
        append_row(first, path)
        append_row(second, path)
        self.assertTrue(fill_row("2026-10-10 09:05:00", {"pain": "2", "mood": "5", "nonsense": "x"}, path))
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([(r["pain"], r["mood"]) for r in rows], [("", ""), ("2", "5")])
        self.assertNotIn("nonsense", rows[0])
        self.assertFalse(fill_row("1999-01-01 00:00:00", {"pain": "1"}, path))

    def test_missing_or_empty_logs_are_left_alone(self):
        folder = tempfile.mkdtemp()
        upgrade_log(os.path.join(folder, "nothing.csv"))
        empty = os.path.join(folder, "empty.csv")
        open(empty, "w").close()
        upgrade_log(empty)
        self.assertEqual(os.path.getsize(empty), 0)

    def test_unwritable_path_does_not_raise(self):
        self.assertFalse(append_row({}, os.path.join(tempfile.mkdtemp(), "missing", "sessions.csv")))


if __name__ == "__main__":
    unittest.main()
