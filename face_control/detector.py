"""MediaPipe wrapper: frame -> FrameResult."""

import dataclasses
from dataclasses import dataclass, field

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from face_control.metrics import Metrics, head_pose_from_matrix, pose_metrics
from face_control.models import FACE_MODEL, POSE_MODEL, ensure_model

# (x, y, visibility) normalized to the frame; visibility is 1.0 for face points.
Landmarks = list[tuple[float, float, float]]


@dataclass(frozen=True)
class FrameResult:
    detected: bool = False
    face_landmarks: Landmarks = field(default_factory=list)
    pose_landmarks: Landmarks = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)


def _base_options(model: tuple[str, str]) -> BaseOptions:
    # CPU only (project decision); also avoids MediaPipe's Metal GPU path.
    return BaseOptions(
        model_asset_path=str(ensure_model(model)), delegate=BaseOptions.Delegate.CPU
    )


class Detector:
    def __init__(self) -> None:
        self._face = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=_base_options(FACE_MODEL),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_facial_transformation_matrixes=True,
            )
        )
        self._pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=_base_options(POSE_MODEL),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
            )
        )
        self._last_ts_ms = -1

    def process(self, frame_bgr: np.ndarray, timestamp_ms: int) -> FrameResult:
        # VIDEO mode needs strictly increasing timestamps.
        timestamp_ms = max(timestamp_ms, self._last_ts_ms + 1)
        self._last_ts_ms = timestamp_ms

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        face = self._face.detect_for_video(image, timestamp_ms)
        pose = self._pose.detect_for_video(image, timestamp_ms)

        h, w = frame_bgr.shape[:2]
        face_pts: Landmarks = (
            [(p.x, p.y, 1.0) for p in face.face_landmarks[0]] if face.face_landmarks else []
        )
        pose_pts: Landmarks = (
            [(p.x, p.y, p.visibility or 0.0) for p in pose.pose_landmarks[0]]
            if pose.pose_landmarks
            else []
        )

        m = Metrics()
        if pose_pts:
            m = pose_metrics(pose_pts, w / h)
        if face.facial_transformation_matrixes:
            pitch, yaw, roll = head_pose_from_matrix(face.facial_transformation_matrixes[0])
            m = dataclasses.replace(m, head_pitch=pitch, head_yaw=yaw, head_roll=roll)

        return FrameResult(
            detected=bool(face_pts or pose_pts),
            face_landmarks=face_pts,
            pose_landmarks=pose_pts,
            metrics=m,
        )

    def close(self) -> None:
        self._face.close()
        self._pose.close()
