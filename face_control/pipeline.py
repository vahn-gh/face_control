"""Camera + detector loop, independent of any UI."""

import dataclasses
import logging
import threading
import time
from collections.abc import Callable

import numpy as np

from face_control.camera import Camera
from face_control.detector import Detector, FrameResult
from face_control.debounce import DebounceConfig, State, ViolationTracker
from face_control.loop import run_loop
from face_control.profile_store import ProfileStore
from face_control.rules import RulesConfig, Verdict, evaluate
from face_control.sound import AlertPolicy
from face_control.smoothing import MetricsSmoother

log = logging.getLogger(__name__)


def run_pipeline(
    camera_index: int,
    fps: float,
    on_result: Callable[[np.ndarray, FrameResult, Verdict, State], None],
    stop: threading.Event | None = None,
    store: ProfileStore | None = None,
    config: RulesConfig = RulesConfig(),
    debounce: DebounceConfig = DebounceConfig(),
    alerts: AlertPolicy | None = None,
) -> None:
    """Capture + detect until `stop` is set or KeyboardInterrupt. May raise CameraError."""
    start = time.monotonic()
    detector = Detector()
    smoother = MetricsSmoother()
    store = store or ProfileStore()
    profiles = list(store.profiles.values())
    tracker = ViolationTracker(debounce)
    try:

        def on_frame(frame: np.ndarray) -> bool:
            result = detector.process(frame, int((time.monotonic() - start) * 1000))
            result = dataclasses.replace(result, metrics=smoother.update(result.metrics))
            verdict = evaluate(result.metrics, result.detected, profiles, config)
            log.debug("detected=%s %s -> %s", result.detected, result.metrics, verdict)
            event = tracker.update(verdict.ok)
            if event is not None:
                log.info("%s: %s", event.value, "; ".join(verdict.reasons) or "back to OK")
            if alerts is not None:
                alerts.update(event, tracker.state)
            on_result(frame, result, verdict, tracker.state)
            return stop is None or not stop.is_set()

        with Camera(camera_index) as camera:
            log.info("Capturing at target %.1f FPS. Press Ctrl+C to stop.", fps)
            run_loop(camera, fps, on_frame)
    finally:
        detector.close()
