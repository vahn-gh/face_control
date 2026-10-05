"""Fixed-rate capture loop."""

import logging
import time
from collections.abc import Callable

import numpy as np

from face_control.camera import Camera

log = logging.getLogger(__name__)

FPS_REPORT_INTERVAL = 3.0


def run_loop(
    camera: Camera,
    fps: float,
    on_frame: Callable[[np.ndarray], bool | None] | None = None,
) -> None:
    """Read frames at ~`fps` until KeyboardInterrupt (handled by the caller)
    or until `on_frame` returns False."""
    period = 1.0 / fps
    next_tick = time.monotonic()
    window_start = next_tick
    frames = 0
    while True:
        frame = camera.read()
        if on_frame is not None and on_frame(frame) is False:
            return
        frames += 1

        now = time.monotonic()
        if now - window_start >= FPS_REPORT_INTERVAL:
            log.info("Measured FPS: %.1f (target %.1f)", frames / (now - window_start), fps)
            window_start, frames = now, 0

        next_tick += period
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_tick = time.monotonic()  # fell behind; don't try to catch up
