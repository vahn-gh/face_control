"""Pure geometry: raw posture metrics from landmarks (no I/O, no judgement)."""

import math
from dataclasses import dataclass

import numpy as np

# MediaPipe pose landmark indices
NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 2, 5, 7, 8
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 11, 12, 23, 24

VISIBILITY_MIN = 0.5

Point = tuple[float, float]  # normalized image coords (x right, y down)


@dataclass(frozen=True)
class Metrics:
    """All angles in degrees; None when the inputs weren't visible."""

    head_pitch: float | None = None  # + looking up, - looking down
    head_yaw: float | None = None  # + turned to the image-right
    head_roll: float | None = None  # + tilted toward image-right shoulder
    shoulder_tilt: float | None = None  # 0 = level; + right shoulder lower in image
    shoulder_width: float | None = None  # fraction of frame width (distance proxy)
    head_y: float | None = None  # nose y, 0 = top of frame, 1 = bottom
    torso_lean: float | None = None  # 0 = upright; + leaning toward image-right


def head_pose_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    """(pitch, yaw, roll) in degrees from a 4x4 face transformation matrix."""
    r = np.asarray(m, dtype=float)[:3, :3]
    r = r / np.linalg.norm(r, axis=0)  # strip the uniform scale
    pitch = math.degrees(math.atan2(-r[1, 2], r[2, 2]))
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, r[0, 2]))))
    roll = math.degrees(math.atan2(-r[0, 1], r[0, 0]))
    return pitch, yaw, roll


def _angle_from_horizontal(a: Point, b: Point, aspect: float) -> float:
    """Angle of a->b vs. the horizontal, in pixel space (aspect = width/height)."""
    dx = (b[0] - a[0]) * aspect
    dy = b[1] - a[1]
    # Fold into [-90, 90] so left/right ordering of a and b doesn't matter.
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    return angle


def shoulder_tilt(left: Point, right: Point, aspect: float) -> float:
    # Subject's left shoulder appears on image-right (unmirrored frame), so order by x.
    a, b = sorted((left, right), key=lambda p: p[0])
    return _angle_from_horizontal(a, b, aspect)


def torso_lean(shoulder_mid: Point, hip_mid: Point, aspect: float) -> float:
    """Angle of the hip->shoulder axis from vertical (+ = shoulders right of hips)."""
    dx = (shoulder_mid[0] - hip_mid[0]) * aspect
    dy = hip_mid[1] - shoulder_mid[1]  # up is positive
    return math.degrees(math.atan2(dx, dy))


def pose_metrics(pts: list[tuple[float, float, float]], aspect: float) -> Metrics:
    """pts: (x, y, visibility) per pose landmark, normalized."""

    def vis(i: int) -> bool:
        return pts[i][2] >= VISIBILITY_MIN

    def xy(i: int) -> Point:
        return pts[i][0], pts[i][1]

    tilt = width = lean = head_y = None
    if vis(L_SHOULDER) and vis(R_SHOULDER):
        ls, rs = xy(L_SHOULDER), xy(R_SHOULDER)
        tilt = shoulder_tilt(ls, rs, aspect)
        width = abs(ls[0] - rs[0])
        if vis(L_HIP) and vis(R_HIP):
            lh, rh = xy(L_HIP), xy(R_HIP)
            lean = torso_lean(
                ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2),
                ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2),
                aspect,
            )
    if vis(NOSE):
        head_y = pts[NOSE][1]
    return Metrics(shoulder_tilt=tilt, shoulder_width=width, head_y=head_y, torso_lean=lean)
