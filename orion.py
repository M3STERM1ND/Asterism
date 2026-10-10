"""Orion: turns the player's shoulders into the Orion constellation (seated mode).

Only the shoulders are tracked: they become Betelgeuse (screen left) and Bellatrix (screen right).
The belt and feet are placed below them in Orion's real proportions, measured in shoulder widths
from a star chart, and the whole figure tilts with the shoulder line. If the screen has no room
below the shoulders (sitting close), the lower part is squashed vertically so it still fits.
Positions are normalized (0 to 1); render.py turns them into pixels.
"""
from dataclasses import dataclass

import numpy as np

NOSE, SHOULDERS = 0, (11, 12)
WRIST, INDEX_TIP = 0, 8
ASPECT = 16 / 9   # screen width / height: geometry is done in units where x and y are the same size
BOTTOM = 0.87     # the lowest a star may sit (fraction of screen height), above the bottom text row
CRAMPED = 0.45    # squashed more than this: suggest sitting back
TOO_FLAT = 0.25   # squashed more than this: draw only the shoulders, the rest would be a flat smear
SMOOTHING = 0.5   # 0 = frozen, 1 = raw; steadies the jitter in pose landmarks
NAMES_SECONDS = 3.0  # how long the star names show when a player appears
NAMES_FADE_IN, NAMES_FADE_OUT = 0.6, 0.8
GONE_SECONDS = 2.0   # absent this long, the next appearance counts as a new player

# Real star positions relative to the middle of the shoulders, in shoulder widths:
# (across: + is toward Bellatrix, down: + is away from the head). From right ascension and declination.
BODY_STARS = {
    "Alnitak": (-0.02, 1.17), "Alnilam": (0.13, 1.08), "Mintaka": (0.27, 0.96),
    "Saiph": (-0.25, 2.20), "Rigel": (0.85, 2.01),
}
LOWEST = max(down for _, down in BODY_STARS.values())

# Star chart lines: shoulders across, shoulders down to the belt ends, belt, belt ends down to the feet.
LINES = [("Betelgeuse", "Bellatrix"), ("Betelgeuse", "Alnitak"), ("Bellatrix", "Mintaka"),
         ("Alnitak", "Alnilam"), ("Alnilam", "Mintaka"), ("Alnitak", "Saiph"), ("Mintaka", "Rigel")]


@dataclass(frozen=True)
class Figure:
    stars: dict          # star name -> (x, y)
    lines: list          # (name, name) pairs to connect
    hand: tuple | None   # the reaching fingertip (farthest from the shoulders), or None
    arms: list           # (shoulder star name, wrist) for each hand: Orion's club and shield arms
    names_alpha: float   # opacity of the star names, 0 to 1
    cramped: bool        # True when the figure had to be squashed a lot (player should sit back)
    nose: tuple | None = None  # the head's position (smoothed), used by the lean guard


def visible(lm):
    """True if a landmark is confidently seen and inside the screen."""
    return (lm.visibility or 0) > 0.5 and 0 < lm.x < 1 and 0 < lm.y < 1


def shoulders_by_side(pose):
    """Return (screen-left, screen-right) shoulder positions, or None if either isn't visible.
    MediaPipe's left/right are anatomical, the opposite of screen side on our mirrored image, so we sort by x."""
    a, b = pose[SHOULDERS[0]], pose[SHOULDERS[1]]
    if not (visible(a) and visible(b)):
        return None
    pair = sorted([(a.x, a.y), (b.x, b.y)])
    return pair[0], pair[1]


def body_stars(left, right):
    """Place the belt and feet below the shoulders in Orion's proportions; return (stars, squash)."""
    lx, ly, rx, ry = left[0] * ASPECT, left[1], right[0] * ASPECT, right[1]
    width = np.hypot(rx - lx, ry - ly)
    across = np.array([rx - lx, ry - ly]) / width      # unit vector along the shoulders
    down = np.array([-across[1], across[0]])            # perpendicular, pointing away from the head
    middle = np.array([(lx + rx) / 2, (ly + ry) / 2])
    room = (BOTTOM - middle[1]) / (LOWEST * width * down[1])  # how much of the natural height fits
    squash = float(np.clip(room, 0.0, 1.0))
    stars = {}
    for name, (a, d) in BODY_STARS.items():
        x, y = middle + across * a * width + down * d * width * squash
        stars[name] = (x / ASPECT, y)
    return stars, squash


def reaching_tip(hands, stars):
    """The fingertip farthest from the middle of the shoulders: the hand that is reaching."""
    if not hands:
        return None
    (lx, ly), (rx, ry) = stars["Betelgeuse"], stars["Bellatrix"]
    cx, cy = (lx + rx) / 2, (ly + ry) / 2
    hand = max(hands, key=lambda h: (h[INDEX_TIP].x - cx) ** 2 + (h[INDEX_TIP].y - cy) ** 2)
    return hand[INDEX_TIP].x, hand[INDEX_TIP].y


def arm_lines(hands, stars):
    """Connect each hand's wrist to a shoulder star. Two hands: screen-left hand to Betelgeuse,
    screen-right to Bellatrix, so the arms never cross. One hand: the nearest shoulder."""
    wrists = sorted((h[WRIST].x, h[WRIST].y) for h in hands)
    if len(wrists) >= 2:
        return [("Betelgeuse", wrists[0]), ("Bellatrix", wrists[-1])]
    if wrists:
        w = wrists[0]
        nearest = min(("Betelgeuse", "Bellatrix"), key=lambda n: (stars[n][0] - w[0]) ** 2 + (stars[n][1] - w[1]) ** 2)
        return [(nearest, w)]
    return []


class Orion:
    def __init__(self):
        self.shoulders = None
        self.nose = None
        self.appeared_at = None
        self.last_seen = -GONE_SECONDS

    def names_alpha(self, now):
        """Star names fade in, hold, then fade out over NAMES_SECONDS after the player appears."""
        t = now - self.appeared_at
        return max(0.0, min(1.0, t / NAMES_FADE_IN, (NAMES_SECONDS - t) / NAMES_FADE_OUT))

    def smooth(self, left, right):
        """Ease both shoulders toward their new positions so the figure doesn't jitter."""
        if self.shoulders is None:
            self.shoulders = (left, right)
        (ol, orr) = self.shoulders
        ease = lambda old, new: (old[0] + (new[0] - old[0]) * SMOOTHING, old[1] + (new[1] - old[1]) * SMOOTHING)
        self.shoulders = (ease(ol, left), ease(orr, right))
        return self.shoulders

    def smooth_nose(self, pose):
        """Ease the nose toward its new position, or forget it when it isn't visible."""
        lm = pose[NOSE]
        if not visible(lm):
            self.nose = None
            return None
        old = self.nose or (lm.x, lm.y)
        self.nose = (old[0] + (lm.x - old[0]) * SMOOTHING, old[1] + (lm.y - old[1]) * SMOOTHING)
        return self.nose

    def update(self, pose, hands, now):
        """Build this frame's Orion figure from the shoulders, or return None if they aren't visible."""
        found = shoulders_by_side(pose) if pose else None
        if found is None:
            return None
        if self.appeared_at is None or now - self.last_seen > GONE_SECONDS:  # a new player (or one coming back)
            self.appeared_at = now
            self.shoulders = self.nose = None
        self.last_seen = now
        left, right = self.smooth(*found)
        lower, squash = body_stars(left, right)
        stars = {"Betelgeuse": left, "Bellatrix": right, **(lower if squash >= TOO_FLAT else {})}
        lines = [(a, b) for a, b in LINES if a in stars and b in stars]
        return Figure(stars, lines, reaching_tip(hands, stars), arm_lines(hands, stars),
                      self.names_alpha(now), squash < CRAMPED, self.smooth_nose(pose))
