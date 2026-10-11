"""Pacing: keeps the main loop at a steady frame rate even though cv2.waitKey oversleeps.

On macOS, waitKey(n) often returns several milliseconds late (measured: about 3 ms during battles and
about 10 ms on the start screen, which held the game at 23 FPS instead of 30). The pacer keeps a running
average of that overshoot and asks for that much less, so the whole frame lands on time.
"""
SMOOTHING = 0.1      # how quickly the overshoot estimate follows changes (0 to 1)
MAX_OVERSHOOT_MS = 30.0


class FramePacer:
    def __init__(self, frame_seconds):
        self.frame_ms = frame_seconds * 1000
        self.overshoot_ms = 0.0

    def wait_ms(self, elapsed_seconds):
        """How long to ask waitKey to wait after a frame that took elapsed_seconds (at least 1 ms)."""
        return max(1, int(round(self.frame_ms - elapsed_seconds * 1000 - self.overshoot_ms)))

    def record(self, asked_ms, waited_ms):
        """Learn from one wait: how much longer than asked it really took."""
        late = min(MAX_OVERSHOOT_MS, max(0.0, waited_ms - asked_ms))
        self.overshoot_ms += SMOOTHING * (late - self.overshoot_ms)
