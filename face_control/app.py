"""Background app: menu-bar tray icon, optional mini window, pause/resume, calibrate.

Qt owns the main thread. The capture/detect pipeline runs in a PipelineRunner thread and
talks to the UI only through queued signals, so detection never blocks it.
"""

import logging
import os
import signal
import sys
import threading

import cv2
import numpy as np
from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from face_control import overlay, profile_store
from face_control.calibrate import calibrate
from face_control.camera import CameraError
from face_control.config import Config
from face_control.debounce import State
from face_control.detector import FrameResult
from face_control.pipeline import run_pipeline
from face_control.profiles import PROFILE_NAMES, CalibrationError
from face_control.rules import Verdict
from face_control.runner import PipelineRunner
from face_control.sound import make_alerts
from face_control.window import MiniWindow, status_text

log = logging.getLogger(__name__)

ICON_COLORS = {
    "ok": QColor(40, 200, 80),
    "violating": QColor(230, 50, 50),
    "paused": QColor(140, 140, 140),
    "away": QColor(110, 150, 200),
}


class Bridge(QObject):
    """Signals emitted from worker threads, delivered on the Qt main thread."""

    state_changed = Signal(str)  # ok | violating | away | paused
    notify = Signal(str, str)  # title, message
    fatal = Signal(int)  # exit code


def make_icon(state: str) -> QIcon:
    pix = QPixmap(44, 44)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(ICON_COLORS[state])
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(6, 6, 32, 32)
    p.end()
    return QIcon(pix)


def hide_dock_icon() -> None:
    """Make this a menu-bar-only app on macOS (no Dock icon)."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except ImportError:
        log.debug("pyobjc not available; Dock icon stays visible")


def run_app(config: Config, show_window: bool) -> int:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)  # the app lives in the tray
    hide_dock_icon()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("No system tray available; use `kill -USR1 <pid>` to toggle the window")

    alerts = make_alerts(config.sound)
    win = MiniWindow(config.window.width)
    bridge = Bridge()
    exit_code = [0]
    calibrating = threading.Event()
    fixed_profile: list[str | None] = [None]  # None = automatic switching

    def run(stop: threading.Event) -> None:
        store = profile_store.load()  # re-read each start so new calibrations apply
        last_state: list[str | None] = [None]

        def on_result(
            frame: np.ndarray, result: FrameResult, verdict: Verdict, state: State
        ) -> None:
            shown = "away" if verdict.away else state.value
            if shown != last_state[0]:
                last_state[0] = shown
                bridge.state_changed.emit(shown)
            if not win.isVisible():  # skip drawing while hidden
                return
            violating = state is State.VIOLATING
            color = overlay.RED if violating else overlay.GREEN
            rgb = cv2.cvtColor(overlay.draw(frame, result, color), cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
            win.frame_ready.emit(image, status_text(result, verdict, bool(store.profiles)), violating)

        run_pipeline(
            config.camera.index,
            config.camera.fps,
            on_result,
            stop,
            store,
            config.rules,
            config.debounce,
            alerts,
            watch_profiles=True,
            fixed_profile=lambda: fixed_profile[0],
        )

    def on_error(e: BaseException) -> None:
        if isinstance(e, CameraError):
            log.error("%s", e)
        else:
            log.error("Pipeline crashed", exc_info=e)
        exit_code[0] = 1
        bridge.fatal.emit(1)

    runner = PipelineRunner(run, on_error)

    # --- tray -----------------------------------------------------------------------
    tray = QSystemTrayIcon(make_icon("ok"))
    menu = QMenu()
    toggle_win = QAction("Show window")
    pause_act = QAction("Pause")
    profile_menu = menu.addMenu("Profile")
    profile_group = QActionGroup(profile_menu)
    calibrate_menu = menu.addMenu("Calibrate")
    quit_act = QAction("Quit")

    def sync_labels() -> None:
        toggle_win.setText("Hide window" if win.isVisible() else "Show window")
        pause_act.setText("Resume" if runner.paused else "Pause")

    def toggle_window() -> None:
        win.toggle()
        sync_labels()

    def place_under_icon() -> None:
        """Position the window just below the menu-bar icon, kept on screen."""
        geo = tray.geometry()
        if geo.isEmpty():
            return  # platform didn't report the icon position; keep the window where it is
        screen = app.screenAt(geo.center()) or app.primaryScreen()
        area = screen.availableGeometry()
        x = geo.center().x() - win.width() // 2
        x = max(area.left() + 4, min(x, area.right() - win.width() - 4))
        win.move(QPoint(x, geo.bottom() + 4))

    def on_tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left click toggles the window; right/ctrl click opens the menu.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if not win.isVisible():
                place_under_icon()
            toggle_window()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            show_menu(QCursor.pos())

    def sync_calibrate_menu() -> None:
        """List the profiles recorded in profiles.json (just Upright when there are none)."""
        try:
            names = list(profile_store.load().profiles)
        except RuntimeError as e:
            log.error("%s", e)
            names = []
        names = [n for n in PROFILE_NAMES if n in names] + [n for n in names if n not in PROFILE_NAMES]
        sync_profile_menu(names)
        calibrate_menu.clear()
        for name in names or [PROFILE_NAMES[0]]:
            act = calibrate_menu.addAction(name.replace("_", " ").capitalize())
            act.triggered.connect(lambda _checked=False, n=name: start_calibration(n))

    def select_profile(name: str | None) -> None:
        fixed_profile[0] = name
        log.info("Profile: %s", name or "auto")

    def sync_profile_menu(names: list[str]) -> None:
        """Auto plus one checkable entry per profile; a fixed profile is the only one counted."""
        if fixed_profile[0] is not None and fixed_profile[0] not in names:
            fixed_profile[0] = None  # profile was removed
        profile_menu.clear()
        for act in profile_group.actions():
            profile_group.removeAction(act)
        for name in [None, *names]:
            act = profile_menu.addAction("Auto" if name is None else name.replace("_", " ").capitalize())
            act.setCheckable(True)
            act.setChecked(fixed_profile[0] == name)
            profile_group.addAction(act)
            act.triggered.connect(lambda _checked=False, n=name: select_profile(n))

    def show_menu(pos: QPoint) -> None:
        sync_labels()
        sync_calibrate_menu()
        menu.popup(pos)

    def set_paused(paused: bool) -> None:
        if paused:
            runner.pause()
            win.set_idle("paused")
            on_state("paused")
        else:
            runner.resume()
        sync_labels()

    def on_pause_clicked() -> None:
        if calibrating.is_set():
            return
        set_paused(not runner.paused)

    def on_state(state: str) -> None:
        tray.setIcon(make_icon(state))
        tray.setToolTip(f"face_control: {state}")

    def start_calibration(name: str) -> None:
        if calibrating.is_set():
            return
        calibrating.set()
        was_paused = runner.paused

        def work() -> None:
            runner.pause()
            try:
                if not runner.wait_idle(10):
                    bridge.notify.emit("Calibration failed", "Could not release the camera")
                    return
                bridge.state_changed.emit("paused")
                bridge.notify.emit(
                    "Calibrating " + name, "Get into position; recording starts in 3 seconds"
                )
                calibrate(name, config.camera.index, config.camera.fps)
                bridge.notify.emit("Calibration saved", f"Profile '{name}' recorded")
            except (CameraError, CalibrationError, RuntimeError) as e:
                log.error("%s", e)
                bridge.notify.emit("Calibration failed", str(e))
            finally:
                calibrating.clear()
                if not was_paused:
                    runner.resume()

        threading.Thread(target=work, name="calibrate", daemon=True).start()

    toggle_win.triggered.connect(toggle_window)
    pause_act.triggered.connect(on_pause_clicked)
    quit_act.triggered.connect(app.quit)
    sync_calibrate_menu()
    menu.insertAction(profile_menu.menuAction(), toggle_win)
    menu.insertAction(profile_menu.menuAction(), pause_act)
    menu.addSeparator()
    menu.addAction(quit_act)
    # No setContextMenu: on macOS that makes a left click open the menu instead of
    # reporting it, and we want left click = toggle window.
    tray.activated.connect(on_tray_activated)
    win.menu_requested.connect(show_menu)

    bridge.state_changed.connect(on_state)
    bridge.notify.connect(lambda title, msg: tray.showMessage(title, msg))
    bridge.fatal.connect(app.exit)

    # Python signal handlers only run while the interpreter is active; tick a timer.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGUSR1, lambda *_: toggle_window())
    pump = QTimer()
    pump.timeout.connect(lambda: None)
    pump.start(200)

    tray.show()
    if show_window:
        win.show()
    log.info("Running in the menu bar (pid %d). Toggle window: kill -USR1 %d", os.getpid(), os.getpid())
    runner.start()
    try:
        app.exec()
    finally:
        runner.shutdown()
    return exit_code[0]
