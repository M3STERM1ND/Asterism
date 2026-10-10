"""Lean guard: notices when the player moves their body instead of reaching with their arm.

Lifting an arm really does move that shoulder up and out (the shoulder blade rotates with the arm),
so the reaching shoulder can't tell an honest reach from a lean. Instead the guard watches the parts
that stay put during a clean one-arm reach, compared with calibration:
  head  - the nose slides sideways (the trunk leaning carries the head with it)
  rise  - the other shoulder (not the reaching one) moves up or down
  shift - the other shoulder slides sideways
  shrug - the reaching shoulder lifts far more than a reach alone does
The reaching arm is the one used in calibration. Distances are in resting shoulder widths,
so they mean the same at any distance from the laptop.
"""
import events
from calibration import shoulder_metrics

HEAD_WIDTHS = 0.45    # about 18 cm. Lean test: honest reaching moved the head up to ~0.45 widths, leans 0.57 to 1.05
RISE_WIDTHS = 0.30    # about 12 cm: the other shoulder dropping or lifting means the trunk is tilting. Tested at
                      # 0.15 first: MediaPipe's shoulder height wobbles so much it warned 42% of the time in play
SHIFT_WIDTHS = 0.35   # about 14 cm. Lean test: honest reaching up to ~0.15 widths (with the right arm), leans 0.50 to 0.88
SHRUG_WIDTHS = 0.35   # about 14 cm: the reaching shoulder moved ~0.18 widths in honest reaches in testing; this allows double
HOLD_SECONDS = 0.4    # past a threshold this long before it counts, so a moment's wobble never triggers it
CLEAR_FRACTION = 0.7  # must come back under 70% of every threshold to clear, so it doesn't flicker at the edge
WARN_COOLDOWN = 2.0   # seconds between WARN LEAN events, so the tone doesn't repeat while still leaning


class LeanGuard:
    def __init__(self):
        self.enabled = True
        self.leaning = False
        self.reason = ""          # which measure is worst: "head", "rise", "shift" or "shrug"
        self.ratios = {}          # the latest measures, kept for the tuning display
        self.over_since = None
        self.last_warn = float("-inf")
        self.warnings = 0         # WARN LEAN events so far, for the session log

    def measure(self, figure, cal, size):
        """Each measure as a fraction of its threshold (1.0 means exactly at the threshold)."""
        now = shoulder_metrics(figure, size)
        reaching_left = cal.side == "Betelgeuse"
        other, other_rest_y = (now["right"], cal.heights[1]) if reaching_left else (now["left"], cal.heights[0])
        reacher, reacher_rest_y = (now["left"], cal.heights[0]) if reaching_left else (now["right"], cal.heights[1])
        other_rest_x = cal.mid[0] + (cal.width / 2 if reaching_left else -cal.width / 2)
        ratios = {
            "rise": abs(other[1] - other_rest_y) / cal.width / RISE_WIDTHS,
            "shift": abs(other[0] - other_rest_x) / cal.width / SHIFT_WIDTHS,
            "shrug": max(0.0, reacher_rest_y - reacher[1]) / cal.width / SHRUG_WIDTHS,
        }
        if cal.nose is not None and figure.nose is not None:
            ratios["head"] = abs(now["nose"][0] - cal.nose[0]) / cal.width / HEAD_WIDTHS
        return ratios

    def update(self, figure, cal, size, now):
        """Return True while the player is leaning; fire WARN LEAN when a lean starts."""
        if not self.enabled or cal is None or figure is None:
            self.leaning, self.over_since = False, None
            return False
        ratios = self.ratios = self.measure(figure, cal, size)
        self.reason = max(ratios, key=ratios.get)
        worst = ratios[self.reason]
        if self.leaning:
            self.leaning = worst >= CLEAR_FRACTION
            return self.leaning
        if worst < 1.0:
            self.over_since = None
            return False
        self.over_since = self.over_since or now
        if now - self.over_since >= HOLD_SECONDS:
            self.leaning = True
            if now - self.last_warn >= WARN_COOLDOWN:
                print("Lean: " + ", ".join(f"{k} {v:.1f}x" for k, v in ratios.items()) + " of threshold")
                events.emit("WARN LEAN")
                self.last_warn = now
                self.warnings += 1
        return self.leaning
