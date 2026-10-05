"""`face_control calibrate <profile>`: record a posture and save it as a profile."""

import dataclasses
import logging
import time

import numpy as np

from face_control import profile_store
from face_control.camera import Camera
from face_control.detector import Detector
from face_control.loop import run_loop
from face_control.metrics import Metrics
from face_control.profiles import Profile, build_profile

log = logging.getLogger(__name__)


def record(camera_index: int, fps: float, countdown: float, seconds: float) -> list[Metrics]:
    """Capture raw (unsmoothed) metrics for `seconds`, after a `countdown` to get in position."""
    detector = Detector()
    samples: list[Metrics] = []
    start = time.monotonic()
    announced = -1
    try:

        def on_frame(frame: np.ndarray) -> bool:
            nonlocal announced
            elapsed = time.monotonic() - start
            result = detector.process(frame, int(elapsed * 1000))
            if elapsed < countdown:
                remaining = int(countdown - elapsed) + 1
                if remaining != announced:
                    announced = remaining
                    log.info("Get into position... %d", remaining)
                return True
            if announced != 0:
                announced = 0
                log.info("Recording for %.0f s — hold still", seconds)
            samples.append(result.metrics)
            return elapsed < countdown + seconds

        with Camera(camera_index) as camera:
            run_loop(camera, fps, on_frame)
    finally:
        detector.close()
    return samples


def calibrate(
    name: str, camera_index: int, fps: float, countdown: float = 3.0, seconds: float = 5.0
) -> Profile:
    samples = record(camera_index, fps, countdown, seconds)
    profile = build_profile(name, samples)  # may raise CalibrationError
    store = profile_store.load()
    old = store.profiles.get(name)
    if old is not None and old.pitch_range is not None:
        profile = dataclasses.replace(profile, pitch_range=old.pitch_range)
    store.profiles[name] = profile
    path = profile_store.save(store)
    log.info("Saved profile '%s' to %s", name, path)
    for metric, s in profile.stats.items():
        log.info("  %-15s mean %8.3f  std %6.3f", metric, s.mean, s.std)
    return profile
