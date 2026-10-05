"""Webcam access via OpenCV."""

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when the camera cannot be opened or read."""


class Camera:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            raise CameraError(
                f"Cannot open camera {self.index}. Check that it is connected, "
                "not used by another app, and that camera permission is granted "
                "(macOS: System Settings > Privacy & Security > Camera)."
            )
        self._cap = cap
        log.info("Camera %d opened", self.index)

    def read(self) -> np.ndarray:
        if self._cap is None:
            raise CameraError("Camera is not open")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError(
                f"Failed to read a frame from camera {self.index}. "
                "It may have been unplugged or access was revoked."
            )
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            log.info("Camera %d released", self.index)

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
