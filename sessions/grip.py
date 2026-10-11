"""Grip: one rep is clench the fist, hold it HOLD_SECONDS, then open the hand fully. Never timed:
it waits as long as the player needs. Opening before the hold is done ends the rep early.

How closed a hand is comes from its openness: the average distance from the wrist to the five
fingertips, divided by the palm length (wrist to the base of the middle finger). Dividing by the
palm makes it the same at any distance from the camera. Open hand: about 1.8. Fist: about 0.9.

For the therapist: open_seconds is how long the hand took to open fully after the hold was done
(slow release is common after a stroke, and getting faster is progress).
"""
import numpy as np

WRIST, MIDDLE_BASE = 0, 9
FINGERTIPS = (4, 8, 12, 16, 20)
CLOSED = 1.15        # openness below this is a fist (a fist measures ~0.9, a relaxed hand ~1.4)
RELEASED = 1.35      # rising past this during the hold means the fist has opened
OPEN = 1.55          # past this the hand is fully open (an open hand measures ~1.8)
HOLD_SECONDS = 3.0
LOST_GRACE = 1.0     # tracking can lose a fist for a moment; this long is still the same rep


def openness(hand):
    """How open one hand is: average wrist-to-fingertip distance in palm lengths."""
    wrist = np.array([hand[WRIST].x, hand[WRIST].y])
    palm = np.hypot(*(np.array([hand[MIDDLE_BASE].x, hand[MIDDLE_BASE].y]) - wrist))
    if palm < 1e-6:
        return None
    reach = [np.hypot(*(np.array([hand[i].x, hand[i].y]) - wrist)) for i in FINGERTIPS]
    return float(np.mean(reach) / palm)


class Grip:
    def __init__(self):
        self.state = "waiting"   # waiting for a fist -> holding -> open (waiting for the open hand) -> done
        self.result = None       # "block" for a full rep, "early" if the fist opened before the hold was done
        self.value = None        # latest openness, for the screen
        self.since = None        # when the fist closed
        self.last_seen = None
        self.progress = 0.0      # 0 to 1 through the hold
        self.held_at = None      # when the hold was completed
        self.open_seconds = None  # how long opening fully took after the hold

    def update(self, hands, now):
        """Advance the rep with this frame's hands (uses the most closed hand)."""
        if self.state == "done":
            return
        values = [v for v in (openness(h) for h in hands) if v is not None]
        if not values:
            if self.state == "holding" and self.last_seen is not None and now - self.last_seen > LOST_GRACE:
                self.state, self.progress = "waiting", 0.0  # lost the hand: start this rep over, no penalty
            return
        self.value, self.last_seen = min(values), now
        if self.state == "waiting" and self.value < CLOSED:
            self.state, self.since = "holding", now
        elif self.state == "holding":
            self.progress = min(1.0, (now - self.since) / HOLD_SECONDS)
            if self.value > RELEASED:
                self.finish("early")
            elif self.progress >= 1.0:
                self.state, self.held_at = "open", now
        elif self.state == "open" and self.value > OPEN:
            self.open_seconds = now - self.held_at
            self.finish("block")

    def finish(self, result):
        """End the rep with its result."""
        self.state, self.result = "done", result
