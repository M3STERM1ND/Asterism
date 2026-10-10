"""Reach session: draw a constellation by touching its stars, one at a time, with an index fingertip.

A star is hit when a fingertip stays within HIT_RADIUS of it for DWELL_SECONDS (a swipe through
doesn't count). While the lean guard says the player is leaning, hits are blocked.
The stars are placed once, when the session starts (see placement.py). Positions are in pixels.
"""
import json

import numpy as np

import events
from fingers import fingertips
from sessions import placement

HIT_RADIUS = 48               # pixels: how close the fingertip must be
MIN_GAP = 1.75 * HIT_RADIUS   # pixels: consecutive stars closer than this get pushed apart
DWELL_SECONDS = 0.3           # how long it must stay there
WIN_HOLD_SECONDS = 5.0        # how long the finished constellation stays on screen


def load_constellation(path):
    """Read a constellation JSON file: name, stars (0 to 1) and optional star names."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if len(data["stars"]) < 2:
        raise ValueError(f"{path} needs at least 2 stars")
    return data


class Reach:
    def __init__(self, constellation, size, celebrate=True, unlit_color=None):
        """celebrate=False: no WIN or name reveal when done (a battle decides that).
        unlit_color: if set, stars not yet lit are drawn in this color (Scorpius in red)."""
        self.celebrate = celebrate
        self.unlit_color = unlit_color
        self.name = constellation["name"]
        self.stars = constellation["stars"]
        self.size = size
        self.points = None   # star positions in pixels, set when the session starts
        self.lit_at = []     # the time each star was lit, in order
        self.inside_since = None
        self.dwell = 0.0     # 0 to 1: how far through the 0.3 s hold the fingertip is
        self.blocked = False  # True while the player is leaning: the target turns red and can't be hit
        self.won_at = None

    def target_index(self):
        """Index of the star to touch next, or None when all are lit."""
        return None if self.won_at is not None else len(self.lit_at)

    def finished(self, now):
        """True once the win has been shown long enough to move on."""
        return self.won_at is not None and now - self.won_at > WIN_HOLD_SECONDS

    def place(self, figure, camera_rect, calibration):
        """Lay out the stars: at the edge of the calibrated reach if there is one, else a default box."""
        bounds = placement.safe_bounds(camera_rect, self.size, HIT_RADIUS)
        if calibration is not None:
            points = placement.place_calibrated(self.stars, calibration, bounds)
        else:
            points = placement.fit_stars(self.stars, placement.comfortable_box(figure, bounds, self.size))
        self.points = placement.spread_out(points, bounds, MIN_GAP)
        print(f"Reach {self.name}: {'calibrated' if calibration else 'default'} placement, "
              f"closest stars {placement.closest_gap(self.points):.0f} px apart")

    def update(self, hands, pose, figure, camera_rect, now, calibration=None, blocked=False):
        """Place the stars on the first frame with a player, then check the fingertips against the target."""
        if self.points is None:
            if figure is None:
                return
            self.place(figure, camera_rect, calibration)
        self.blocked = blocked
        i = self.target_index()
        if i is None:
            return
        tips = fingertips(hands, pose, np.array(self.size))  # Pose backs up Hands at full stretch
        target = self.points[i]
        near = any(np.hypot(x - target[0], y - target[1]) <= HIT_RADIUS for x, y in tips)
        if blocked or not near:
            self.inside_since, self.dwell = None, 0.0
            return
        if self.inside_since is None:
            self.inside_since = now
        self.dwell = min(1.0, (now - self.inside_since) / DWELL_SECONDS)
        if self.dwell >= 1.0:
            self.light_star(now)

    def light_star(self, now):
        """Mark the target star as lit and fire STAR; fire WIN after the last one."""
        self.lit_at.append(now)
        self.inside_since, self.dwell = None, 0.0
        n = len(self.lit_at)
        events.emit("STAR", n, pos=self.points[n - 1])
        if n == len(self.points):
            self.won_at = now
            if self.celebrate:
                events.emit("WIN")
