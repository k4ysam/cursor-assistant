"""Cursor Assistant — entry point, global hotkeys, and app lifecycle.

Wires the floating window, the Claude Code backend, and the screenshot
capture overlay together, and installs system-wide hotkeys via pynput.
"""

from __future__ import annotations

import signal
import sys
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from pynput import keyboard, mouse

from assistant import Assistant
from capture import ScreenCapture
from ui.window import MainWindow

CAPTURE_DELAY_MS = 220       # let the window fully hide before grabbing the screen
DOUBLE_CLICK_SECS = 0.4      # max gap between the two middle-clicks that summon


class HotkeyBridge(QObject):
    """Marshals pynput callbacks (worker thread) into Qt signals (GUI thread).

    Emitting a Qt signal from a non-Qt thread is delivered via a queued
    connection, which safely crosses into the event loop.
    """

    screenshot = pyqtSignal()
    toggle = pyqtSignal()


class App:
    def __init__(self) -> None:
        self.qt = QApplication(sys.argv)
        self.qt.setApplicationName("Cursor Assistant")
        # Hiding the window or closing the overlay must not quit the app.
        self.qt.setQuitOnLastWindowClosed(False)

        self.window = MainWindow()
        self.assistant = Assistant()
        self.capture = ScreenCapture()
        self.bridge = HotkeyBridge()

        self._last_mid = 0.0  # timestamp of the previous middle-click

        self._wire_signals()
        self._listener = self._install_hotkeys()
        self._mouse = self._install_mouse()

    # --------------------------------------------------------------- wiring

    def _wire_signals(self) -> None:
        # Window -> backend
        self.window.send_requested.connect(self._on_send)
        self.window.screenshot_requested.connect(self.trigger_capture)
        self.window.close_requested.connect(self.quit)

        # Backend -> window
        self.assistant.token_received.connect(self.window.append_response_token)
        self.assistant.response_complete.connect(self.window.finish_response)
        self.assistant.error_occurred.connect(self.window.show_error)

        # Capture -> window
        self.capture.captured.connect(self._on_captured)
        self.capture.cancelled.connect(self._on_capture_cancelled)

        # Hotkeys -> actions
        self.bridge.screenshot.connect(self.trigger_capture)
        self.bridge.toggle.connect(self.window.toggle_visibility)

    # ------------------------------------------------------------- actions

    def _on_send(self, text: str, image: object) -> None:
        self.window.start_response()
        self.assistant.send(text, image)

    def trigger_capture(self) -> None:
        self.window.hide()
        QTimer.singleShot(CAPTURE_DELAY_MS, self.capture.start)

    def _on_captured(self, image: object) -> None:
        self.window.set_image(image)
        self.window.show_animated()

    def _on_capture_cancelled(self) -> None:
        self.window.show_animated()

    # ------------------------------------------------------------- hotkeys

    def _install_hotkeys(self) -> keyboard.GlobalHotKeys:
        listener = keyboard.GlobalHotKeys(
            {
                "<ctrl>+<shift>+x": self.bridge.screenshot.emit,
            }
        )
        listener.daemon = True
        listener.start()
        return listener

    def _install_mouse(self) -> mouse.Listener:
        listener = mouse.Listener(on_click=self._on_mouse_click)
        listener.daemon = True
        listener.start()
        return listener

    def _on_mouse_click(self, x: int, y: int, button, pressed: bool) -> None:
        # Double middle-click (scroll-wheel) toggles the window. Listener is
        # passive, so the click still reaches the underlying app.
        if not pressed or button != mouse.Button.middle:
            return
        now = time.monotonic()
        if now - self._last_mid <= DOUBLE_CLICK_SECS:
            self._last_mid = 0.0
            self.bridge.toggle.emit()
        else:
            self._last_mid = now

    # ------------------------------------------------------------ lifecycle

    def run(self) -> int:
        if not self.assistant.claude_available():
            self.window.show_error(
                "Claude Code not found. Install it: "
                "npm install -g @anthropic-ai/claude-code"
            )
        self.window.show()
        self.window.focus_input()

        # Allow Ctrl+C from a terminal to terminate cleanly.
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        # Keep the Python interpreter responsive to signals.
        timer = QTimer()
        timer.start(250)
        timer.timeout.connect(lambda: None)

        return self.qt.exec()

    def quit(self) -> None:
        for listener in (self._listener, self._mouse):
            try:
                listener.stop()
            except Exception:
                pass
        self.assistant.shutdown()
        self.qt.quit()


def main() -> int:
    return App().run()


if __name__ == "__main__":
    sys.exit(main())
