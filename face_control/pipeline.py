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
from face_control import profile_store
from face_control.profile_store import ProfileStore
from face_control.rules import RulesConfig, Verdict, evaluate
from face_control.sound import AlertPolicy
from face_control.smoothing import MetricsSmoother

log = logging.getLogger(__name__)


PROFILE_POLL_SECONDS = 1.0


def _mtime() -> float | None:
    try:
        return profile_store.profiles_path().stat().st_mtime
    except OSError:
        return None  # missing file = no profiles


def run_pipeline(
    camera_index: int,
    fps: float,
    on_result: Callable[[np.ndarray, FrameResult, Verdict, State], None],
    stop: threading.Event | None = None,
    store: ProfileStore | None = None,
    config: RulesConfig = RulesConfig(),
    debounce: DebounceConfig = DebounceConfig(),
    alerts: AlertPolicy | None = None,
    watch_profiles: bool = False,
) -> None:
    """Capture + detect until `stop` is set or KeyboardInterrupt. May raise CameraError.

    With `watch_profiles`, `store` is refreshed in place whenever profiles.json changes.
    """
    start = time.monotonic()
    detector = Detector()
    smoother = MetricsSmoother()
    store = store or ProfileStore()
    profiles = list(store.profiles.values())
    tracker = ViolationTracker(debounce)
    watched = _mtime() if watch_profiles else None
    last_check = start
    try:

        def on_frame(frame: np.ndarray) -> bool:
            nonlocal profiles, watched, last_check
            now = time.monotonic()
            if watch_profiles and now - last_check >= PROFILE_POLL_SECONDS:
                last_check = now
                mtime = _mtime()
                if mtime != watched:
                    watched = mtime
                    try:
                        store.profiles = profile_store.load().profiles
                        profiles = list(store.profiles.values())
                        log.info("Reloaded profiles: %s", ", ".join(store.profiles) or "none")
                    except RuntimeError as e:
                        log.error("%s", e)  # keep the previous profiles
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
