"""The main floating window widget.

A frameless, always-on-top, translucent panel with a custom title bar,
optional image preview, a streaming response area, and an input bar.
"""

from __future__ import annotations

import io

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (
    QGuiApplication,
    QImage,
    QKeyEvent,
    QKeySequence,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizeGrip,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from PIL import Image

from ui import styles
from ui.markdown import to_html


class MainWindow(QWidget):
    """Floating assistant panel. Emits high-level signals; holds no LLM logic."""

    # (prompt_text, pil_image_or_None)
    send_requested = pyqtSignal(str, object)
    screenshot_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: QPoint | None = None
        self._current_image: Image.Image | None = None
        self._response_buffer = ""
        self._in_flight = False
        self._collapsed = False

        self._build_ui()
        self._position_center_right()
        self._show_placeholder()

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(styles.DEFAULT_WIDTH, styles.DEFAULT_HEIGHT)
        self.setMinimumSize(styles.MIN_WIDTH, styles.MIN_HEIGHT)

        # Outer transparent layout holds the rounded inner frame.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setObjectName("OuterFrame")
        outer.addWidget(self.frame)

        root = QVBoxLayout(self.frame)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._build_title_bar())
        self._body = self._build_body()
        root.addLayout(self._body)

        self.setStyleSheet(styles.STYLESHEET)

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(28)
        # The whole bar acts as the drag handle.
        bar.mousePressEvent = self._title_mouse_press
        bar.mouseMoveEvent = self._title_mouse_move
        bar.mouseReleaseEvent = self._title_mouse_release

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(4)

        title = QLabel("cursor")
        title.setObjectName("TitleLabel")
        lay.addWidget(title)
        lay.addStretch(1)

        self.collapse_btn = QPushButton("–")  # en dash (minimize)
        self.collapse_btn.setObjectName("TitleButton")
        self.collapse_btn.setFixedSize(22, 22)
        self.collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        lay.addWidget(self.collapse_btn)

        # CloseButton inherits the #TitleButton base look plus its own hover.
        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseButton")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Quit (Esc or Ctrl+Shift+Space to just hide)")
        close_btn.clicked.connect(self.close_requested.emit)
        lay.addWidget(close_btn)
        return bar

    def _build_body(self) -> QVBoxLayout:
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        # --- Image preview (hidden until an image is set) ---
        self.preview_container = QWidget()
        self.preview_container.setObjectName("PreviewContainer")
        pc = QVBoxLayout(self.preview_container)
        pc.setContentsMargins(4, 4, 4, 4)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMaximumHeight(styles.PREVIEW_MAX_HEIGHT)
        pc.addWidget(self.preview_label)

        # The remove button floats over the top-right of the preview.
        self.preview_remove = QPushButton("✕", self.preview_container)
        self.preview_remove.setObjectName("PreviewRemove")
        self.preview_remove.setFixedSize(20, 20)
        self.preview_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_remove.clicked.connect(self.clear_image)

        self.preview_container.hide()
        body.addWidget(self.preview_container)

        # --- Response area ---
        self.response = QTextBrowser()
        self.response.setObjectName("ResponseArea")
        self.response.setOpenExternalLinks(True)
        self.response.setFrameShape(QFrame.Shape.NoFrame)
        body.addWidget(self.response, stretch=1)

        # --- Input bar ---
        input_bar = QWidget()
        input_bar.setObjectName("InputBar")
        input_bar.setFixedHeight(40)
        ib = QHBoxLayout(input_bar)
        ib.setContentsMargins(6, 2, 6, 2)
        ib.setSpacing(4)

        self.shot_btn = QPushButton("\U0001f4f7")  # 📷
        self.shot_btn.setObjectName("IconButton")
        self.shot_btn.setFixedSize(30, 30)
        self.shot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shot_btn.setToolTip("Capture a screenshot region (Ctrl+Shift+X)")
        self.shot_btn.clicked.connect(self.screenshot_requested.emit)
        ib.addWidget(self.shot_btn)

        self.input = QLineEdit()
        self.input.setObjectName("InputField")
        self.input.setPlaceholderText("Ask anything...")
        self.input.returnPressed.connect(self._on_send)
        ib.addWidget(self.input, stretch=1)

        self.send_btn = QPushButton("→")  # →
        self.send_btn.setObjectName("SendButton")
        self.send_btn.setFixedSize(30, 30)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        ib.addWidget(self.send_btn)

        body.addWidget(input_bar)
        self._input_bar = input_bar

        # --- Resize grip (bottom-right) ---
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        self.grip = QSizeGrip(self.frame)
        self.grip.setObjectName("ResizeGrip")
        self.grip.setFixedSize(14, 14)
        grip_row.addWidget(self.grip, alignment=Qt.AlignmentFlag.AlignRight)
        body.addLayout(grip_row)

        return body

    # --------------------------------------------------------------- geometry

    def _position_center_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - self.width() - 30
        y = geo.center().y() - self.height() // 2
        self.move(max(geo.left(), x), max(geo.top(), y))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._reposition_preview_remove()

    def _reposition_preview_remove(self) -> None:
        if self.preview_container.isVisible():
            w = self.preview_container.width()
            self.preview_remove.move(w - 24, 4)
            self.preview_remove.raise_()

    # ----------------------------------------------------------- title drag

    def _title_mouse_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def _title_mouse_move(self, event) -> None:
        if self._drag_offset is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def _title_mouse_release(self, event) -> None:
        self._drag_offset = None
        event.accept()

    # ------------------------------------------------------------- collapse

    def toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        # Hide/show every widget in the body except keep the title bar.
        for i in range(self._body.count()):
            item = self._body.itemAt(i)
            w = item.widget()
            if w is not None and w is not self.preview_container:
                w.setVisible(not self._collapsed)
            elif w is self.preview_container:
                w.setVisible(not self._collapsed and self._current_image is not None)
        if self._collapsed:
            self._saved_height = self.height()
            self.setFixedHeight(46)
        else:
            self.setMinimumSize(styles.MIN_WIDTH, styles.MIN_HEIGHT)
            self.setMaximumSize(16777215, 16777215)
            self.resize(self.width(), getattr(self, "_saved_height", styles.DEFAULT_HEIGHT))
        self.collapse_btn.setText("+" if self._collapsed else "–")

    # --------------------------------------------------------------- images

    def set_image(self, image: Image.Image) -> None:
        """Display a PIL image in the preview area."""
        self._current_image = image.convert("RGB")
        qimg = self._pil_to_qimage(self._current_image)
        pix = QPixmap.fromImage(qimg)
        scaled = pix.scaledToHeight(
            styles.PREVIEW_MAX_HEIGHT,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_container.show()
        self._reposition_preview_remove()
        self.focus_input()

    def clear_image(self) -> None:
        self._current_image = None
        self.preview_label.clear()
        self.preview_container.hide()

    @staticmethod
    def _pil_to_qimage(image: Image.Image) -> QImage:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        qimg = QImage()
        qimg.loadFromData(buf.getvalue(), "PNG")
        return qimg

    # ------------------------------------------------------------- response

    def _show_placeholder(self) -> None:
        self.response.setHtml(
            styles.response_html_styles()
            + '<p class="placeholder">Screenshot or type a question</p>'
        )

    def start_response(self) -> None:
        """Mark a request in flight and show a thinking indicator."""
        self._in_flight = True
        self._response_buffer = ""
        self.send_btn.setEnabled(False)
        self.input.setEnabled(False)
        self.response.setHtml(
            styles.response_html_styles() + '<p class="thinking">thinking…</p>'
        )

    def append_response_token(self, text: str) -> None:
        """Append streamed text and re-render the accumulated markdown."""
        self._response_buffer += text
        self._render_buffer()

    def _render_buffer(self) -> None:
        html_body = to_html(self._response_buffer)
        self.response.setHtml(styles.response_html_styles() + html_body)
        sb = self.response.verticalScrollBar()
        sb.setValue(sb.maximum())

    def finish_response(self) -> None:
        self._in_flight = False
        self.send_btn.setEnabled(True)
        self.input.setEnabled(True)
        if not self._response_buffer.strip():
            self._show_placeholder()
        self.focus_input()

    def show_error(self, message: str) -> None:
        self._in_flight = False
        self.send_btn.setEnabled(True)
        self.input.setEnabled(True)
        self.response.setHtml(
            styles.response_html_styles()
            + f'<p class="error">{message}</p>'
        )
        self.focus_input()

    # --------------------------------------------------------------- actions

    def _on_send(self) -> None:
        if self._in_flight:
            return
        text = self.input.text().strip()
        if not text and self._current_image is None:
            return
        self.input.clear()
        image = self._current_image
        self.send_requested.emit(text, image)

    def focus_input(self) -> None:
        self.input.setFocus()

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.focus_input()

    # ----------------------------------------------------------- key + paste

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            if self._try_paste_clipboard():
                return
        super().keyPressEvent(event)

    def _try_paste_clipboard(self) -> bool:
        """Paste an image from the clipboard into the preview, if present.

        Returns True if an image was consumed; False to let normal text
        paste proceed.
        """
        clipboard = QApplication.clipboard()
        md = clipboard.mimeData()
        if md.hasImage():
            qimg = clipboard.image()
            if not qimg.isNull():
                self.set_image(self._qimage_to_pil(qimg))
                return True
        return False

    @staticmethod
    def _qimage_to_pil(qimg: QImage) -> Image.Image:
        qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.constBits()
        ptr.setsize(h * w * 4)
        return Image.frombuffer("RGBA", (w, h), bytes(ptr), "raw", "RGBA", 0, 1)
