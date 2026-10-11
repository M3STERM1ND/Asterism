"""Recording: saves each battle or practice round as a small video for the patient's coach.

It records the game screen, not the camera: the patient appears as Orion's stars and their hand as a
star chart, which shows the movement the coach needs without filming the patient's face or home.
Videos are H.264 MP4 (plays in any browser), 640x360 at 15 frames a second, in the run's videos folder.
"""
import os
import re

import cv2

VIDEO_SIZE = (640, 360)
VIDEO_FPS = 15
EVERY_NTH_FRAME = 2        # the game runs at 30 FPS; every 2nd frame makes 15
CODECS = ("avc1", "mp4v")  # H.264 first (browsers play it); mp4v only if H.264 is unavailable


def video_name(stamp, title):
    """A safe file name like 20261010-161900-scorpius.mp4."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "session"
    return f"{stamp}-{slug}.mp4"


class Recorder:
    def __init__(self):
        self.writer = None
        self.path = None
        self.frames = 0

    @property
    def active(self):
        return self.writer is not None

    def start(self, path):
        """Begin a new video (ending any that is still open)."""
        self.stop()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for codec in CODECS:
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*codec), VIDEO_FPS, VIDEO_SIZE)
            if writer.isOpened():
                self.writer, self.path, self.frames = writer, path, 0
                return True
            writer.release()
        print(f"Recording: could not open a video writer for {path}")
        return False

    def write(self, frame):
        """Add one game frame (only every EVERY_NTH_FRAME-th is kept)."""
        if self.writer is None:
            return
        self.frames += 1
        if self.frames % EVERY_NTH_FRAME == 0:
            self.writer.write(cv2.resize(frame, VIDEO_SIZE, interpolation=cv2.INTER_AREA))

    def stop(self):
        """Finish the video. Returns its file name (or None if nothing was recording)."""
        if self.writer is None:
            return None
        self.writer.release()
        self.writer = None
        return os.path.basename(self.path)

    def cancel(self):
        """Stop and delete the video (the session was abandoned, so it has no report row)."""
        path = self.path if self.writer is not None else None
        self.stop()
        if path and os.path.exists(path):
            os.remove(path)
