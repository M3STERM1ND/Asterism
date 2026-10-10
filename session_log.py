"""Session log: one row in sessions.csv for every finished battle or practice constellation.

Columns: date, mode, time (seconds), max reach (shoulder widths, the same unit as calibration),
lean warnings, damage dealt (battles only), then which constellation and how it ended.
Max reach only counts while the player is not leaning, so it measures the arm, not the body.
"""
import csv
import os
from datetime import datetime

import numpy as np

LOG_PATH = "sessions.csv"
COLUMNS = ["date", "mode", "time", "max reach", "lean warnings", "damage dealt", "constellation", "result"]


class SessionRecord:
    def __init__(self, mode, constellation, warnings_at_start):
        self.mode = mode
        self.constellation = constellation
        self.warnings_at_start = warnings_at_start
        self.started_at = None  # set on the first frame, like the battle's own clock
        self.max_reach = 0.0
        self.logged = False

    def update(self, tips, cal, blocked, now):
        """Start the clock, and keep the farthest honest reach from the calibrated shoulder."""
        if self.started_at is None:
            self.started_at = now
        if blocked or cal is None:
            return
        for tip in tips:
            self.max_reach = max(self.max_reach, float(np.hypot(*(np.array(tip) - cal.shoulder))) / cal.width)

    def row(self, now, warnings_now, result, damage=None, date=None):
        """The CSV row for this session as it ends."""
        seconds = 0.0 if self.started_at is None else now - self.started_at
        return {"date": (date or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
                "mode": self.mode,
                "time": f"{seconds:.1f}",
                "max reach": f"{self.max_reach:.2f}",
                "lean warnings": warnings_now - self.warnings_at_start,
                "damage dealt": "" if damage is None else damage,
                "constellation": self.constellation,
                "result": result}


def append_row(row, path=LOG_PATH):
    """Add one row to the log, writing the header first if the file is new. Returns True if it was written."""
    try:
        is_new = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except OSError as error:  # a locked file (open in Excel) must not stop the game
        print(f"Session log: could not write {path}: {error}")
        return False
    print(f"Session log: {row['mode']} {row['constellation']} {row['result']} in {row['time']} s")
    return True
