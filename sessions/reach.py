"""Reach session: draw a constellation by touching its stars, one at a time, with an index fingertip.

A star is hit when a fingertip stays within the hit radius of it for DWELL_SECONDS (a swipe through
doesn't count). While the lean guard says the player is leaning, hits are blocked.
The stars are placed once, when the session starts (see placement.py). Positions are in pixels.

Assisted learning (on by default): the next star glows, as always. Off: the whole constellation is
shown for MEMORY_SHOW_SECONDS, then hidden; the player draws it from memory, a star counts when the
fingertip dwells within a slightly larger radius, and H shows the next star for HINT_SECONDS (counted).
Each lit star's error (fingertip to star centre) is recorded in pixels and in shoulder widths.

Movement quality, per star, for the therapist (the fingertip followed is the one nearest the target):
  move seconds - from the previous star (or the start) to this one being lit
  straightness - straight-line distance / the path the fingertip actually travelled (1 = perfectly direct)
  tremor       - how much the fingertip wobbles while holding on the star, px: the RMS distance from a
                 straight-line fit over the hold, so the last of a quick arrival (smooth drift) isn't
                 mistaken for shaking
The fingertip's path is also kept (trace), so a session's movements can be drawn later.
"""
import json

import numpy as np

import events
from fingers import fingertips
from game.difficulty import NORMAL, reach_limit
from sessions import placement

HIT_RADIUS = NORMAL.hit_radius  # pixels: how close the fingertip must be (the difficulty may change it)
MIN_GAP_SCALE = 1.75          # consecutive stars closer than this many hit radii get pushed apart
DWELL_SECONDS = 0.3           # how long it must stay there
WIN_HOLD_SECONDS = 5.0        # how long the finished constellation stays on screen
MEMORY_SHOW_SECONDS = 3.0     # unassisted: how long the full constellation is shown before it hides
MEMORY_RADIUS_SCALE = 1.3     # unassisted: a star counts within this much more than the hit radius
HINT_SECONDS = 2.0            # how long a hint shows the next star
STUCK_SECONDS = 8.0           # on one star this long (unassisted) the screen suggests the hint key
MISS_STILL_PIXELS = 15        # a fingertip that moves less than this is holding still
MISS_STILL_SECONDS = 1.0      # holding still this long away from the star is a miss
JUMP_PIXELS = 150             # a fingertip that moves farther than this in one frame is a tracking glitch, not movement


def load_constellation(path):
    """Read a constellation JSON file: name, stars (0 to 1) and optional star names."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if len(data["stars"]) < 2:
        raise ValueError(f"{path} needs at least 2 stars")
    return data


def tremor(samples):
    """Wobble of (time, x, y) samples around a straight-line fit of position over time, RMS in px."""
    if len(samples) < 3:
        return 0.0
    data = np.array(samples, dtype=float)
    t = data[:, 0] - data[0, 0]
    residuals = []
    for axis in (1, 2):
        if np.ptp(t) > 0:
            fit = np.polyval(np.polyfit(t, data[:, axis], 1), t)
        else:
            fit = data[:, axis].mean()
        residuals.append(data[:, axis] - fit)
    return float(np.sqrt(np.mean(residuals[0] ** 2 + residuals[1] ** 2)))


class Reach:
    def __init__(self, constellation, size, celebrate=True, unlit_color=None, difficulty=NORMAL, assisted=True):
        """celebrate=False: no WIN or name reveal when done (a battle decides that).
        unlit_color: if set, stars not yet lit are drawn in this color (Scorpius in red)."""
        self.celebrate = celebrate
        self.unlit_color = unlit_color
        self.difficulty = difficulty
        self.assisted = assisted
        self.hit_radius = difficulty.hit_radius
        self.accept_radius = self.hit_radius if assisted else self.hit_radius * MEMORY_RADIUS_SCALE
        self.name = constellation["name"]
        self.stars = constellation["stars"]
        self.size = size
        self.points = None   # star positions in pixels, set when the session starts
        self.started_at = None  # the first frame with the stars in place
        self.lit_at = []     # the time each star was lit, in order
        self.errors_px = []  # per lit star: distance from the fingertip to the star's centre, pixels
        self.errors_sw = []  # the same in shoulder widths (empty without a calibration)
        self.hints = 0       # hints used
        self.misses = 0      # unassisted: times the player held still away from the star
        self.hint_until = 0.0
        self.enabled = True  # False outside the player's turn: no star can be hit, no target shown
        self.inside_since = None
        self.dwell = 0.0     # 0 to 1: how far through the 0.3 s hold the fingertip is
        self.blocked = False  # True while the player is leaning: the target turns red and can't be hit
        self.won_at = None
        self.still_at = None  # unassisted: where and since when the fingertip has been holding still
        self.still_since = None
        self.miss_counted = False
        self.star_since = None  # when the current star became the target
        self.move_seconds = []  # per lit star: time to reach it
        self.straightness = []  # per lit star: straight distance / path travelled (0 to 1)
        self.tremor_px = []     # per lit star: wobble while holding on it
        self.trace = []         # (time, x, y) of the followed fingertip, for drawing the movement later
        self.path_px = 0.0      # path travelled toward the current star
        self.path_start = None  # where the movement toward the current star began
        self.last_tip = None
        self.dwell_tips = []    # fingertip positions during the current hold

    def target_index(self):
        """Index of the star to touch next, or None when all are lit or it isn't the player's turn."""
        return None if self.won_at is not None or not self.enabled else len(self.lit_at)

    def finished(self, now):
        """True once the win has been shown long enough to move on."""
        return self.won_at is not None and now - self.won_at > WIN_HOLD_SECONDS

    def previewing(self, now):
        """Unassisted, at the start: the full constellation is on show for a few seconds."""
        return (not self.assisted and self.started_at is not None and not self.lit_at
                and now - self.started_at < MEMORY_SHOW_SECONDS)

    def preview_left(self, now):
        """Seconds of the memory preview still to go (0 when it isn't showing)."""
        return max(0.0, MEMORY_SHOW_SECONDS - (now - self.started_at)) if self.previewing(now) else 0.0

    def target_visible(self, now):
        """Should the next star be drawn? Always when assisted; unassisted only during a hint."""
        return self.assisted or now < self.hint_until

    def stuck(self, now):
        """Unassisted and on one star for a long time: time to suggest the hint key."""
        return (not self.assisted and self.enabled and self.star_since is not None
                and self.won_at is None and now - self.star_since > STUCK_SECONDS and now >= self.hint_until)

    def hint(self, now):
        """Show the next star for a moment (unassisted only). Every hint is counted."""
        if self.assisted or self.target_index() is None or self.points is None or now < self.hint_until:
            return False
        self.hints += 1
        self.hint_until = now + HINT_SECONDS
        return True

    def draw_seconds(self):
        """How long the stars took, from the first frame to the last star lit."""
        return 0.0 if not self.lit_at or self.started_at is None else self.lit_at[-1] - self.started_at

    def place(self, figure, camera_rect, calibration):
        """Lay out the stars: within the difficulty's share of the calibrated reach if there is one,
        else a default box. Never farther than the reach limit from the shoulder."""
        bounds = placement.safe_bounds(camera_rect, self.size, self.hit_radius)
        min_gap = MIN_GAP_SCALE * self.hit_radius
        if calibration is not None:
            points = placement.place_calibrated(self.stars, calibration, bounds, edge=self.difficulty.reach_edge)
            limit = (calibration.shoulder, reach_limit(calibration, self.difficulty))
            points = placement.spread_out(points, bounds, min_gap, within=limit)
            points = placement.limit_to_reach(points, *limit)  # the reach limit always wins
        else:
            points = placement.fit_stars(self.stars, placement.comfortable_box(figure, bounds, self.size))
            points = placement.spread_out(points, bounds, min_gap)
        self.points = points
        print(f"Reach {self.name}: {'calibrated' if calibration else 'default'} placement, "
              f"consecutive stars at least {placement.closest_step(self.points):.0f} px apart")

    def update(self, hands, pose, figure, camera_rect, now, calibration=None, blocked=False):
        """Place the stars on the first frame with a player, then check the fingertips against the target."""
        if self.points is None:
            if figure is None:
                return
            self.place(figure, camera_rect, calibration)
            self.started_at = self.star_since = now
        self.blocked = blocked
        i = self.target_index()
        if i is None:
            return
        tips = fingertips(hands, pose, np.array(self.size))  # Pose backs up Hands at full stretch
        target = self.points[i]
        distances = [float(np.hypot(x - target[0], y - target[1])) for x, y in tips]
        self.count_misses(tips, distances, now)
        if tips:
            self.follow(tips[int(np.argmin(distances))], now)
        if blocked or not distances or min(distances) > self.accept_radius:
            self.inside_since, self.dwell = None, 0.0
            self.dwell_tips = []
            return
        if self.inside_since is None:
            self.inside_since = now
        self.dwell_tips.append((now, *tips[int(np.argmin(distances))]))
        self.dwell = min(1.0, (now - self.inside_since) / DWELL_SECONDS)
        if self.dwell >= 1.0:
            self.light_star(now, min(distances), calibration)

    def follow(self, tip, now):
        """Keep the fingertip's path: its trace, and the distance travelled toward the current star."""
        tip = (float(tip[0]), float(tip[1]))
        self.trace.append((now, *tip))
        if self.path_start is None:
            self.path_start = tip
        if self.last_tip is not None:
            step = float(np.hypot(tip[0] - self.last_tip[0], tip[1] - self.last_tip[1]))
            if step <= JUMP_PIXELS:
                self.path_px += step
        self.last_tip = tip

    def record_movement(self, now, target):
        """Movement quality for the star just lit (see the module notes)."""
        start = self.points[len(self.lit_at) - 2] if len(self.lit_at) > 1 else self.path_start
        began = self.lit_at[-2] if len(self.lit_at) > 1 else self.star_since
        self.move_seconds.append(max(0.0, now - (began if began is not None else now)))
        straight = 0.0 if start is None else float(np.hypot(target[0] - start[0], target[1] - start[1]))
        self.straightness.append(min(1.0, straight / self.path_px) if self.path_px > 1.0 else 1.0)
        self.tremor_px.append(tremor(self.dwell_tips))
        self.path_px, self.path_start, self.dwell_tips = 0.0, self.last_tip, []

    def count_misses(self, tips, distances, now):
        """Unassisted: a fingertip that holds still away from the star counts as one miss per stop."""
        if self.assisted or not tips:
            self.still_at = self.still_since = None
            return
        tip = np.array(tips[0], dtype=float)
        if self.still_at is None or np.hypot(*(tip - self.still_at)) > MISS_STILL_PIXELS:
            self.still_at, self.still_since, self.miss_counted = tip, now, False
        elif (not self.miss_counted and now - self.still_since >= MISS_STILL_SECONDS
              and min(distances) > self.accept_radius):
            self.misses += 1
            self.miss_counted = True

    def light_star(self, now, error_px=0.0, calibration=None):
        """Mark the target star as lit and fire STAR; fire WIN after the last one."""
        self.lit_at.append(now)
        self.record_movement(now, self.points[len(self.lit_at) - 1])
        self.errors_px.append(error_px)
        if calibration is not None:
            self.errors_sw.append(error_px / calibration.width)
        self.inside_since, self.dwell, self.star_since = None, 0.0, now
        self.still_at = None
        n = len(self.lit_at)
        events.emit("STAR", n, pos=self.points[n - 1])
        if n == len(self.points):
            self.won_at = now
            if self.celebrate:
                events.emit("WIN")
