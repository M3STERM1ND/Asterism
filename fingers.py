"""Fingers: where the player's index fingertips are, from Hands and from Pose.

Hands gives the precise fingertip but drops a hand that is blurred or partly outside the
camera (common at full stretch). Pose follows the whole arm, so its index-finger point is a
backup that keeps working there. Positions are in pixels.
"""
import numpy as np

INDEX_TIP = 8                   # Hands: the index fingertip
POSE_INDEX_FINGERS = (19, 20)   # Pose: the left and right index-finger points
SAME_FINGER_PX = 80             # a Pose point this close to a Hands fingertip is the same finger


def hand_tips(hands, size):
    """Index fingertips from Hands, in pixels."""
    return [np.array([hand[INDEX_TIP].x, hand[INDEX_TIP].y]) * size for hand in hands]


def pose_tips(pose, size):
    """Index-finger points from Pose that are visible and on screen, in pixels."""
    if pose is None:
        return []
    tips = []
    for i in POSE_INDEX_FINGERS:
        lm = pose[i]
        if (lm.visibility or 0) > 0.5 and 0 < lm.x < 1 and 0 < lm.y < 1:
            tips.append(np.array([lm.x, lm.y]) * size)
    return tips


def backup_tips(hands, pose, size):
    """Pose fingertips for hands that Hands has lost (ones not already next to a Hands fingertip)."""
    precise = hand_tips(hands, size)
    return [tip for tip in pose_tips(pose, size)
            if all(np.hypot(*(tip - other)) > SAME_FINGER_PX for other in precise)]


def fingertips(hands, pose, size):
    """Every index fingertip we can find: precise ones from Hands, plus Pose backups for lost hands."""
    return hand_tips(hands, size) + backup_tips(hands, pose, size)
