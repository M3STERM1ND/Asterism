"""Lean test: a guided check of the lean guard, run from the start screen (key T).

After calibration the player does each step in order, never skipped: sit still, reach with the
arm only, then lean. Each step starts with a short "get ready" countdown, then records the lean
guard's readings and counts its warnings. At the end it shows (and prints) a summary.
"""
STEPS = [
    ("still", "Sit straight and still", 10.0),
    ("reach", "Sit straight and reach around with your arm only", 10.0),
    ("lean", "Now lean your body down and to the right", 10.0),
]
READY_SECONDS = 3.0  # countdown before each step records, so moving into position doesn't count


class LeanTest:
    def __init__(self):
        self.step = 0
        self.step_start = None
        self.readings = {name: [] for name, _, _ in STEPS}  # lean guard readings per step
        self.warnings = {name: 0 for name, _, _ in STEPS}   # how many times the guard started warning
        self.was_leaning = False
        self.done = False

    def instruction(self):
        """The current step's name and what to do."""
        name, text, _ = STEPS[self.step]
        return name, text

    def timing(self, now):
        """(seconds left in the get-ready countdown, fraction of the step recorded so far)."""
        if self.step_start is None:
            return READY_SECONDS, 0.0
        elapsed = now - self.step_start
        length = STEPS[self.step][2]
        return max(0.0, READY_SECONDS - elapsed), min(1.0, max(0.0, elapsed - READY_SECONDS) / length)

    def update(self, guard, now):
        """Record this frame's readings for the current step, and move on when the step is done."""
        if self.done:
            return
        self.step_start = self.step_start or now
        name, _, length = STEPS[self.step]
        elapsed = now - self.step_start
        if elapsed < READY_SECONDS:
            self.was_leaning = guard.leaning
            return
        if guard.ratios:
            self.readings[name].append(dict(guard.ratios))
        if guard.leaning and not self.was_leaning:
            self.warnings[name] += 1
        self.was_leaning = guard.leaning
        if elapsed >= READY_SECONDS + length:
            self.step += 1
            self.step_start = None
            if self.step == len(STEPS):
                self.step, self.done = len(STEPS) - 1, True
                print(self.report())

    def summary(self):
        """Per step: the highest reading of each check, and the number of warnings."""
        rows = {}
        for name, readings in self.readings.items():
            checks = sorted({key for r in readings for key in r})
            rows[name] = {"max": {key: max(r.get(key, 0.0) for r in readings) for key in checks},
                          "warnings": self.warnings[name], "frames": len(readings)}
        return rows

    def verdict(self):
        """Did the guard stay quiet while still and reaching, and warn while leaning?"""
        w = self.warnings
        if w["still"] == 0 and w["reach"] == 0 and w["lean"] > 0:
            return "Pass: quiet while still and reaching, warned while leaning"
        problems = []
        if w["still"] or w["reach"]:
            problems.append("warned without a lean (too strict)")
        if w["lean"] == 0:
            problems.append("missed the lean (too loose)")
        return "Needs tuning: " + " and ".join(problems)

    def report(self):
        """The summary as text for the console log."""
        lines = ["Lean test results (highest reading per check, 1.0 = threshold):"]
        for name, row in self.summary().items():
            checks = "  ".join(f"{k} {v:.2f}" for k, v in row["max"].items())
            lines.append(f"  {name:5s}: {checks}  | warnings {row['warnings']} | {row['frames']} frames")
        lines.append("  " + self.verdict())
        return "\n".join(lines)
