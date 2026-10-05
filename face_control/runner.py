"""Runs the pipeline in a background thread with pause/resume (pause releases the camera)."""

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)


class PipelineRunner:
    """`run(stop)` must return promptly once `stop` is set; it owns the camera while running."""

    def __init__(
        self,
        run: Callable[[threading.Event], None],
        on_error: Callable[[BaseException], None],
        start_paused: bool = False,
    ) -> None:
        self._run = run
        self._on_error = on_error
        self._lock = threading.Lock()
        self._paused = start_paused
        self._quit = False
        self._run_stop = threading.Event()
        self._wake = threading.Event()
        self._idle = threading.Event()  # set whenever `run` is not executing
        self._thread = threading.Thread(target=self._loop, name="pipeline", daemon=True)

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            self._run_stop.set()

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._run_stop.clear()
        self._wake.set()

    def shutdown(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._quit = True
            self._run_stop.set()
        self._wake.set()
        self._thread.join(timeout)

    def wait_idle(self, timeout: float) -> bool:
        """Wait until the camera is released (the run has returned or never started)."""
        return self._idle.wait(timeout)

    def _loop(self) -> None:
        while True:
            with self._lock:
                if self._quit:
                    break
                paused = self._paused
            if paused:
                self._idle.set()
                self._wake.wait()
                self._wake.clear()
                continue
            self._idle.clear()
            try:
                self._run(self._run_stop)
            except BaseException as e:  # reported, then the runner ends
                self._idle.set()
                self._on_error(e)
                return
            self._idle.set()
        self._idle.set()
