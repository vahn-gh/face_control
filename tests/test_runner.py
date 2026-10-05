import threading
import time

from face_control.runner import PipelineRunner


class FakeCamera:
    """Stands in for the pipeline: 'owns the camera' between enter and exit."""

    def __init__(self):
        self.open = False
        self.opens = 0
        self.fail = None

    def run(self, stop):
        if self.fail:
            raise self.fail
        self.open = True
        self.opens += 1
        try:
            stop.wait()
        finally:
            self.open = False


def wait_for(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def make(**kw):
    cam, errors = FakeCamera(), []
    runner = PipelineRunner(cam.run, errors.append, **kw)
    return runner, cam, errors


def test_runs_pauses_releases_camera_and_resumes():
    runner, cam, _ = make()
    runner.start()
    assert wait_for(lambda: cam.open)
    runner.pause()
    assert runner.wait_idle(2) and not cam.open and runner.paused
    runner.resume()
    assert wait_for(lambda: cam.open) and cam.opens == 2
    runner.shutdown()
    assert not cam.open


def test_start_paused_never_opens_camera():
    runner, cam, _ = make(start_paused=True)
    runner.start()
    assert runner.wait_idle(2)
    time.sleep(0.05)
    assert cam.opens == 0
    runner.resume()
    assert wait_for(lambda: cam.open)
    runner.shutdown()


def test_rapid_pause_resume_ends_running():
    runner, cam, _ = make()
    runner.start()
    assert wait_for(lambda: cam.open)
    for _ in range(20):
        runner.pause()
        runner.resume()
    assert wait_for(lambda: cam.open)
    runner.shutdown()
    assert not cam.open


def test_error_is_reported_and_runner_stops():
    runner, cam, errors = make()
    cam.fail = RuntimeError("camera gone")
    runner.start()
    assert wait_for(lambda: errors)
    assert str(errors[0]) == "camera gone"
    assert runner.wait_idle(1)


def test_shutdown_while_paused():
    runner, _, _ = make(start_paused=True)
    runner.start()
    runner.shutdown(timeout=2)
    assert not runner._thread.is_alive()
