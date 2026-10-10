"""Tracking: runs MediaPipe Hands and Pose on webcam frames, on a background thread.

The screen never waits for tracking: main.py draws every camera frame with the
newest landmarks available. Landmarks are normalized (x, y from 0 to 1 across the frame).
"""
import threading
import time
from collections import deque, namedtuple
from concurrent.futures import ThreadPoolExecutor

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

HAND_MODEL = "models/hand_landmarker.task"
POSE_MODEL = "models/pose_landmarker_lite.task"  # the lightest pose model (the old API's model_complexity=0)
POSE_EVERY = 2  # we only use the shoulders, which move slowly: run Pose every 2nd frame to give Hands more CPU
HAND_CONFIDENCE = 0.3  # how sure Hands must be to report a hand (default 0.5)
SMOOTH_FRAMES = 4  # hand landmarks are averaged over this many tracked frames to remove jitter

Point = namedtuple("Point", "x y visibility")


class Tracker:
    def __init__(self, camera, num_hands=2):
        """Load both models and start tracking frames from the camera in the background."""
        video = vision.RunningMode.VIDEO
        self.hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=HAND_MODEL),
            running_mode=video,
            num_hands=num_hands,
            # Lower than the 0.5 defaults so a blurred or half-visible hand at full stretch isn't dropped.
            min_hand_detection_confidence=HAND_CONFIDENCE,
            min_hand_presence_confidence=HAND_CONFIDENCE,
            min_tracking_confidence=HAND_CONFIDENCE,
        ))
        self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=POSE_MODEL),
            running_mode=video,
        ))
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.start = time.monotonic()
        self.last_ms = -1
        self.result = ([], None)
        self.pose_every = POSE_EVERY
        self.last_pose = None
        self.hand_history = deque(maxlen=SMOOTH_FRAMES)
        self.updates = 0  # how many frames have been tracked, for the tracking FPS
        self.camera = camera
        self.running = True
        self.thread = threading.Thread(target=self._track_loop, daemon=True)
        self.thread.start()

    def process(self, frame_bgr):
        """Return (hands, pose): hands is a list of 21-landmark lists, pose is a 33-landmark list or None."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # VIDEO mode needs strictly increasing timestamps in milliseconds.
        ms = max(int((time.monotonic() - self.start) * 1000), self.last_ms + 1)
        self.last_ms = ms
        # Run both models at the same time instead of one after the other; Pose only every few frames.
        hands_job = self.pool.submit(self.hands.detect_for_video, image, ms)
        if self.updates % self.pose_every == 0:
            poses = self.pool.submit(self.pose.detect_for_video, image, ms).result().pose_landmarks
            self.last_pose = poses[0] if poses else None
        return hands_job.result().hand_landmarks, self.last_pose

    def _track_loop(self):
        """Keep tracking the newest camera frame and store the result."""
        frame_id = 0
        while self.running:
            frame_id, frame = self.camera.read(frame_id)
            if frame is not None:
                hands, pose = self.process(frame)
                self.result = (self.smooth_hands(hands), pose)
                self.updates += 1

    def smooth_hands(self, hands):
        """Average each hand over the last few frames. Hands are sorted by wrist x so each one is
        averaged with itself; frames with a different number of hands are left out."""
        current = sorted((np.array([[lm.x, lm.y] for lm in hand]) for hand in hands), key=lambda a: a[0, 0])
        self.hand_history.append(current)
        same = [frame for frame in self.hand_history if len(frame) == len(current)]
        averaged = [np.mean([frame[i] for frame in same], axis=0) for i in range(len(current))]
        return [[Point(x, y, 1.0) for x, y in hand] for hand in averaged]

    def latest(self):
        """Return the newest (hands, pose) result."""
        return self.result

    def close(self):
        """Stop the tracking thread and free the models."""
        self.running = False
        self.thread.join(timeout=3)
        self.pool.shutdown()
        self.hands.close()
        self.pose.close()
