"""Calibration (seated): measures the player's resting shoulders and comfortable reach.

Phases:
  settle - shoulders and a hand must be visible for SETTLE_SECONDS; then the framing freezes,
           so from here on a lean shows up as the shoulders moving on screen.
  rest   - "Sit tall and still": records resting shoulder tilt, height and midpoint, and which
           shoulder the raised hand is next to: that is the reaching arm.
  sweep  - "Slowly sweep your arm as far as is comfortable": records the farthest the fingertip
           gets from the nearer shoulder, in shoulder widths. A sweeping hand blurs and Hands often
           loses it, so Pose's index-finger points are used too (Pose follows a moving arm better).
All measurements are in screen pixels.
"""
from dataclasses import dataclass

import numpy as np

from fingers import fingertips

SETTLE_SECONDS = 1.0
REST_SECONDS = 1.5
SWEEP_SECONDS = 5.0
MIN_REACH = 1.0   # shoulder widths: a floor, so a very small sweep still gives a playable range


@dataclass(frozen=True)
class Calibration:
    reach: float      # comfortable max reach from the shoulder, in shoulder widths
    side: str         # the reaching shoulder: "Betelgeuse" (screen left) or "Bellatrix" (screen right)
    shoulder: tuple   # that shoulder's resting position, pixels
    width: float      # resting shoulder width, pixels
    tilt: float       # resting shoulder tilt, degrees
    mid: tuple        # resting middle of the shoulders, pixels
    heights: tuple    # resting height (y) of the left and right shoulder, pixels
    nose: tuple | None  # resting head position, pixels (None if the nose wasn't seen)


def shoulder_metrics(figure, size):
    """Both shoulders in pixels, plus shoulder width, tilt in degrees and midpoint."""
    left = np.array(figure.stars["Betelgeuse"]) * size
    right = np.array(figure.stars["Bellatrix"]) * size
    dx, dy = right - left
    nose = np.array(figure.nose) * size if figure.nose else np.array([np.nan, np.nan])
    return {"left": left, "right": right, "width": float(np.hypot(dx, dy)),
            "tilt": float(np.degrees(np.arctan2(dy, dx))), "mid": (left + right) / 2, "nose": nose}


class Calibrator:
    def __init__(self, size):
        self.size = np.array(size, dtype=float)
        self.phase = "settle"
        self.phase_start = None
        self.rest = []                 # shoulder metrics recorded while resting
        self.best = {"Betelgeuse": 0.0, "Bellatrix": 0.0}  # farthest reach seen from each shoulder
        self.side_votes = {"Betelgeuse": 0, "Bellatrix": 0}  # which shoulder the raised hand is next to while resting
        self.trail = []                # fingertip positions during the sweep, for drawing
        self.sweep_frames = 0          # frames during the sweep, and how many of them saw a hand
        self.hand_frames = 0
        self.result = None
        self.done_at = None

    def progress(self, now):
        """How far through the current phase we are, 0 to 1."""
        if self.phase_start is None:
            return 0.0
        length = {"settle": SETTLE_SECONDS, "rest": REST_SECONDS, "sweep": SWEEP_SECONDS}[self.phase]
        return min(1.0, (now - self.phase_start) / length)

    def resting_shoulders(self):
        """Middle of the resting shoulder measurements (the median ignores one-off glitches)."""
        rest = {key: np.median([m[key] for m in self.rest], axis=0) for key in self.rest[0] if key != "nose"}
        noses = [m["nose"] for m in self.rest if not np.isnan(m["nose"][0])]
        rest["nose"] = np.median(noses, axis=0) if noses else np.array([np.nan, np.nan])
        return rest

    def update(self, hands, pose, figure, now, view):
        """Advance calibration by one frame; returns the Calibration once the sweep is done."""
        if self.phase == "settle":
            if figure is None or not hands:
                self.phase_start = None
                return None
            self.phase_start = self.phase_start or now
            if now - self.phase_start >= SETTLE_SECONDS and view.settled():  # freeze only once framing has caught up
                view.frozen = True
                self.phase, self.phase_start = "rest", now
        elif self.phase == "rest":
            if figure is not None:
                self.rest.append(shoulder_metrics(figure, self.size))
                self.vote_side(fingertips(hands, pose, self.size), figure)
            if now - self.phase_start >= REST_SECONDS and self.rest:
                self.phase, self.phase_start = "sweep", now
        elif self.phase == "sweep":
            tips = fingertips(hands, pose, self.size)
            self.sweep_frames += 1
            self.hand_frames += 1 if tips else 0
            if figure is not None:
                self.record_reach(tips, figure)
            if now - self.phase_start >= SWEEP_SECONDS:
                self.result, self.done_at = self.finish(), now
                return self.result
        return None

    def vote_side(self, tips, figure):
        """While resting, count which shoulder each raised fingertip is closest to."""
        for tip in tips:
            side = min(self.side_votes, key=lambda n: np.hypot(*(np.array(figure.stars[n]) * self.size - tip)))
            self.side_votes[side] += 1

    def reaching_side(self):
        """The reaching arm: the shoulder the raised hand was next to while resting (ties go to the right)."""
        votes = self.side_votes
        return "Betelgeuse" if votes["Betelgeuse"] > votes["Bellatrix"] else "Bellatrix"

    def record_reach(self, tips, figure):
        """Keep the farthest each fingertip has reached from each shoulder, in resting shoulder widths.
        Only the reaching shoulder's number is used; the other is printed to help check the setup."""
        width = self.resting_shoulders()["width"]
        shoulders = {"Betelgeuse": np.array(figure.stars["Betelgeuse"]) * self.size,
                     "Bellatrix": np.array(figure.stars["Bellatrix"]) * self.size}
        for tip in tips:
            self.trail.append(tuple(tip))
            for side, shoulder in shoulders.items():
                self.best[side] = max(self.best[side], float(np.hypot(*(shoulder - tip))) / width)

    def finish(self):
        """Turn the recordings into a Calibration: resting shoulders plus the best reach."""
        rest = self.resting_shoulders()
        side = self.reaching_side()
        shoulder = rest["left"] if side == "Betelgeuse" else rest["right"]
        return Calibration(reach=max(MIN_REACH, self.best[side]), side=side, shoulder=tuple(shoulder),
                           width=float(rest["width"]), tilt=float(rest["tilt"]), mid=tuple(rest["mid"]),
                           heights=(float(rest["left"][1]), float(rest["right"][1])),
                           nose=None if np.isnan(rest["nose"][0]) else tuple(rest["nose"]))
