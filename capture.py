"""Screenshot region selection overlay.

Flow: pre-grab the whole virtual desktop, show a translucent fullscreen
overlay, let the user drag a selection rectangle, then crop the pre-grabbed
image to that region. Pre-grabbing avoids a visible flash and sidesteps
ImageGrab/Qt coordinate-timing issues.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from PIL import Image, ImageGrab

from ui import styles

MIN_SELECTION = 10  # px (logical) below which a selection is treated as a cancel


class ScreenCapture(QObject):
    """Orchestrates a single region-selection capture."""

    captured = pyqtSignal(object)  # emits a PIL.Image
    cancelled = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._overlay: _CaptureOverlay | None = None

    def start(self) -> None:
        """Grab the full screen and present the selection overlay."""
        try:
            full = ImageGrab.grab(all_screens=True)
        except Exception:  # pragma: no cover - platform fallback
            full = ImageGrab.grab()

        self._overlay = _CaptureOverlay(full)
        self._overlay.region_selected.connect(self._on_selected)
        self._overlay.selection_cancelled.connect(self._on_cancelled)
        self._overlay.show_overlay()

    def _cleanup(self) -> None:
        if self._overlay is not None:
            self._overlay.close()
            self._overlay.deleteLater()
            self._overlay = None

    def _on_selected(self, image: object) -> None:
        self._cleanup()
        self.captured.emit(image)

    def _on_cancelled(self) -> None:
        self._cleanup()
        self.cancelled.emit()


class _CaptureOverlay(QWidget):
    """Fullscreen translucent overlay that captures a drag rectangle."""

    region_selected = pyqtSignal(object)
    selection_cancelled = pyqtSignal()

    def __init__(self, full_screenshot: Image.Image) -> None:
        super().__init__()
        self._full = full_screenshot
        self._origin: QPoint | None = None
        self._current: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Cover the entire virtual desktop (all monitors).
        self._virtual_geo = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(self._virtual_geo)

    def show_overlay(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ------------------------------------------------------------- painting

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark dim over the whole overlay.
        dim = QColor(0, 0, 0, 110)
        painter.fillRect(self.rect(), dim)

        rect = self._selection_rect()
        if rect is not None and not rect.isNull():
            # Punch a transparent hole so the selected region is at full
            # brightness (the live desktop shows through).
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )

            # Selection border.
            accent = QColor(styles.ACCENT)
            pen = QPen(accent, 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Dimension label.
            painter.setPen(QColor(255, 255, 255, 220))
            label = f"{rect.width()} × {rect.height()}"
            painter.drawText(rect.left(), max(rect.top() - 6, 12), label)

    def _selection_rect(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    # --------------------------------------------------------------- mouse

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        rect = self._selection_rect()
        if rect is None or rect.width() < MIN_SELECTION or rect.height() < MIN_SELECTION:
            self.selection_cancelled.emit()
            return
        image = self._crop(rect)
        if image is None:
            self.selection_cancelled.emit()
        else:
            self.region_selected.emit(image)

    # ----------------------------------------------------------- keyboard

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.selection_cancelled.emit()

    # --------------------------------------------------------------- crop

    def _crop(self, rect: QRect) -> Image.Image | None:
        """Crop the pre-grabbed full screenshot to the selection rectangle.

        Selection is in Qt logical coordinates relative to the overlay
        (which spans the virtual desktop). The grabbed image is in physical
        pixels, so scale by the device pixel ratio.
        """
        dpr = self.devicePixelRatioF()
        # rect is relative to the overlay's top-left, which equals the
        # virtual desktop's top-left, so it already maps to image space.
        left = int(round(rect.left() * dpr))
        top = int(round(rect.top() * dpr))
        right = int(round(rect.right() * dpr))
        bottom = int(round(rect.bottom() * dpr))

        # Clamp to image bounds.
        w, h = self._full.size
        left = max(0, min(left, w))
        top = max(0, min(top, h))
        right = max(0, min(right, w))
        bottom = max(0, min(bottom, h))
        if right - left < 1 or bottom - top < 1:
            return None
        return self._full.crop((left, top, right, bottom))
