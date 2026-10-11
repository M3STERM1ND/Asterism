"""Camera: reads the webcam on a background thread so the game never waits for a frame."""
import os
import sys
import threading

os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"  # makes Media Foundation open much faster
import cv2  # noqa: E402  (must come after the env var above)


class Camera:
    def __init__(self, width=1280, height=720):
        """Open the default webcam (Media Foundation gives 30 fps here; DirectShow only gave 10)."""
        backend = cv2.CAP_MSMF if sys.platform == "win32" else cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
        self.cam = cv2.VideoCapture(0, backend)
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cam.isOpened():
            raise SystemExit("Could not open the webcam. Is another app using it?")
        self.frame = None
        self.frame_id = 0
        self.running = True
        self.ready = threading.Condition()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self):
        """Keep grabbing frames and store only the newest one."""
        while self.running:
            ok, frame = self.cam.read()
            if not ok:
                continue
            with self.ready:
                self.frame, self.frame_id = frame, self.frame_id + 1
                self.ready.notify_all()

    def read(self, last_id=0):
        """Wait for a frame newer than last_id and return (frame_id, mirrored frame), or (last_id, None) after 2 s."""
        with self.ready:
            if not self.ready.wait_for(lambda: self.frame_id > last_id, timeout=2):
                return last_id, None
            return self.frame_id, cv2.flip(self.frame, 1)  # mirror, so moving right moves right on screen

    def close(self):
        """Stop the reader thread and release the webcam."""
        self.running = False
        self.thread.join(timeout=1)
        self.cam.release()
