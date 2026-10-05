"""Draw tracked landmarks onto a frame in a single state color."""

import cv2
import numpy as np

from face_control.detector import FrameResult
from face_control.metrics import VISIBILITY_MIN

GREEN = (0, 255, 0)  # BGR
RED = (0, 0, 255)
POSE_CONNECTIONS = [(11, 12), (11, 23), (12, 24), (23, 24), (0, 2), (0, 5), (2, 7), (5, 8)]
POSE_POINTS = [0, 2, 5, 7, 8, 11, 12, 23, 24]


def draw(
    frame: np.ndarray,
    result: FrameResult,
    color: tuple[int, int, int] = GREEN,
    mirror: bool = True,
) -> np.ndarray:
    """Return a copy of `frame` (mirrored like a selfie view) with landmarks drawn."""
    out = cv2.flip(frame, 1) if mirror else frame.copy()
    h, w = out.shape[:2]

    def px(p: tuple[float, float, float]) -> tuple[int, int]:
        x = 1.0 - p[0] if mirror else p[0]
        return int(x * w), int(p[1] * h)

    for p in result.face_landmarks[::4]:
        cv2.circle(out, px(p), 1, color, -1)
    pose = result.pose_landmarks
    if pose:
        for a, b in POSE_CONNECTIONS:
            if pose[a][2] >= VISIBILITY_MIN and pose[b][2] >= VISIBILITY_MIN:
                cv2.line(out, px(pose[a]), px(pose[b]), color, 2)
        for i in POSE_POINTS:
            if pose[i][2] >= VISIBILITY_MIN:
                cv2.circle(out, px(pose[i]), 4, color, -1)
    return out
