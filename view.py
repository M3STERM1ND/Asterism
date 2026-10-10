"""View: auto-framing, so the player can sit anywhere from about 2 to 4 feet from the laptop.

Everything the camera sees (shoulders and hands) is scaled and shifted so the shoulders always
land in the same place and size on screen. The framing follows the player slowly, so it feels
steady; calibration can freeze it so leaning still shows up as movement.
All coordinates are normalized (0 to 1). The screen and camera are both 16:9, so one scale fits x and y.
"""
from collections import namedtuple

import numpy as np

SHOULDERS = (11, 12)
TARGET_CENTER = (0.5, 0.58)  # where the middle of the shoulders goes: most of the room is above, for reaching
TARGET_WIDTH = 0.13          # shoulder width on screen (fraction of screen width); Orion's legs squash to fit below
FOLLOW_SECONDS = 1.5         # how quickly the framing catches up when the player moves
SETTLED = 0.05               # within 5% of where it is heading counts as settled

Point = namedtuple("Point", "x y visibility")


class View:
    def __init__(self):
        self.scale = 1.0
        self.anchor = (0.5, 0.5)  # the camera point that maps onto TARGET_CENTER
        self.ready = False
        self.target_scale = None  # where the framing is heading, to know when it has settled
        self.frozen = False
        self.last_time = None

    def follow(self, pose, now):
        """Ease the framing toward the player's current shoulders (unless frozen)."""
        dt = 0.0 if self.last_time is None else now - self.last_time
        self.last_time = now
        if self.frozen or pose is None:
            return
        a, b = pose[SHOULDERS[0]], pose[SHOULDERS[1]]
        if min(a.visibility or 0, b.visibility or 0) < 0.5:
            return
        width = abs(a.x - b.x)
        if width < 0.03:  # shoulders seen edge-on: no reliable size this frame
            return
        target_scale = self.target_scale = TARGET_WIDTH / width
        target_anchor = ((a.x + b.x) / 2, (a.y + b.y) / 2)
        ease = 1.0 if not self.ready else 1 - np.exp(-dt / FOLLOW_SECONDS)
        self.scale += (target_scale - self.scale) * ease
        self.anchor = tuple(o + (t - o) * ease for o, t in zip(self.anchor, target_anchor))
        self.ready = True

    def settled(self):
        """True once the framing has caught up with the player, so it is safe to freeze."""
        return self.target_scale is not None and abs(self.scale - self.target_scale) <= SETTLED * self.target_scale

    def origin(self):
        """Where the camera image's top-left corner lands on screen. When the image is smaller
        than the screen (sitting close), it is nudged so none of it hangs off an edge: anything
        the camera can see, including a raised hand, must stay visible."""
        x0 = TARGET_CENTER[0] - self.anchor[0] * self.scale
        y0 = TARGET_CENTER[1] - self.anchor[1] * self.scale
        if self.scale <= 1:
            x0 = min(max(x0, 0.0), 1 - self.scale)
            y0 = min(max(y0, 0.0), 1 - self.scale)
        return x0, y0

    def map_point(self, lm, origin):
        """Move one camera landmark into framed screen coordinates."""
        return Point(origin[0] + lm.x * self.scale, origin[1] + lm.y * self.scale, getattr(lm, "visibility", 1.0))

    def camera_rect(self):
        """The part of the screen the camera can see, as (left, top, right, bottom): a hand can only reach in here."""
        x0, y0 = self.origin()
        return max(x0, 0.0), max(y0, 0.0), min(x0 + self.scale, 1.0), min(y0 + self.scale, 1.0)

    def apply(self, hands, pose):
        """Return hands and pose moved into framed screen coordinates."""
        origin = self.origin()
        hands = [[self.map_point(lm, origin) for lm in hand] for hand in hands]
        pose = [self.map_point(lm, origin) for lm in pose] if pose else None
        return hands, pose
