"""Floating always-on-top mini window (PySide6). Frames arrive via a queued signal."""

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from face_control.detector import FrameResult
from face_control.rules import Verdict

ASPECT = 4 / 3


class MiniWindow(QWidget):
    frame_ready = Signal(QImage, str, bool)  # frame, status text, violating
    menu_requested = Signal(QPoint)  # right-click; the app shows its menu

    def __init__(self, width: int) -> None:
        super().__init__()
        self.setWindowTitle("face_control")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background: black;")
        self.resize(width, round(width / ASPECT))
        self.setMinimumSize(QSize(160, 120))
        self._image: QImage | None = None
        self._status = ""
        self._violating = False
        self._drag_offset: QPoint | None = None
        self.frame_ready.connect(self._on_frame)

    def _on_frame(self, image: QImage, status: str, violating: bool) -> None:
        self._image = image
        self._violating = violating
        self._status = status
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        if self._image is not None:
            # Cover: scale to fill the window, center, and let the overflow be clipped.
            scaled = self._image.size().scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding
            )
            target = QRect(QPoint(0, 0), scaled)
            target.moveCenter(self.rect().center())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(target, self._image)
        if self._status:
            # Drawn in window coordinates (not on the frame) so cover-mode cropping can't hide it.
            font = painter.font()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            for i, line in enumerate(self._status.split("\n")):
                y = 20 + i * 18
                painter.setPen(Qt.GlobalColor.black)
                painter.drawText(QPoint(9, y + 1), line)
                painter.setPen(QColor(255, 60, 60) if self._violating else QColor(0, 255, 0))
                painter.drawText(QPoint(8, y), line)

    # Drag to move
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag_offset = None

    def wheelEvent(self, e) -> None:  # scroll to resize
        dy = e.angleDelta().y()
        if dy == 0:  # horizontal scroll / trackpad momentum end: not a resize request
            return
        w = max(160, self.width() + (20 if dy > 0 else -20))
        self.resize(w, round(w / ASPECT))

    def contextMenuEvent(self, e) -> None:
        self.menu_requested.emit(e.globalPos())

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.hide()

    def set_idle(self, text: str) -> None:
        """Show a plain message instead of video (e.g. while paused)."""
        self._image = None
        self._violating = False
        self._status = text
        self.update()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()


def status_text(result: FrameResult, verdict: Verdict, has_profiles: bool) -> str:
    """Line 1: profile and pitch; line 2: why it's not OK."""
    if verdict.away:
        return "away" if verdict.ok else "away | NOT OK\nno person detected"
    profile = verdict.match.name or ("none" if has_profiles else "no profiles")
    pitch = result.metrics.head_pitch
    label = "pitch n/a" if pitch is None else f"pitch {pitch:+.0f}"
    line = f"{profile} | {label}  {'OK' if verdict.ok else 'NOT OK'}"
    if verdict.reasons:
        line += "\n" + "; ".join(verdict.reasons)
    return line
