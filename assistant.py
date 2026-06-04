"""Claude Code CLI subprocess wrapper.

The entire LLM backend is `claude -p "<prompt>"`. We run it in a QThread,
stream stdout back to the UI via signals, and maintain a short rolling
conversation context (Claude Code has no memory between invocations, so the
full context is re-sent each turn).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from PIL import Image

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_MAX_PAIRS = 10  # rolling history window (user+assistant pairs)
_CLAUDE_NOT_FOUND = (
    "Claude Code not found. Install it: "
    "npm install -g @anthropic-ai/claude-code"
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class _Worker(QThread):
    """Runs a single `claude -p` invocation and streams its stdout."""

    token_received = pyqtSignal(str)
    response_complete = pyqtSignal(str)  # full response text
    error_occurred = pyqtSignal(str)

    def __init__(self, argv: list[str], cwd: str) -> None:
        super().__init__()
        self._argv = argv
        self._cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._stopped = False

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            self._proc = subprocess.Popen(
                self._argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self._cwd,
                creationflags=_no_window_flag(),
            )
        except FileNotFoundError:
            self.error_occurred.emit(_CLAUDE_NOT_FOUND)
            return
        except Exception as exc:  # pragma: no cover - defensive
            self.error_occurred.emit(f"Failed to start Claude Code: {exc}")
            return

        chunks: list[str] = []
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if self._stopped:
                break
            clean = _strip_ansi(line)
            chunks.append(clean)
            self.token_received.emit(clean)

        stderr = ""
        if self._proc.stderr is not None:
            stderr = _strip_ansi(self._proc.stderr.read())
        code = self._proc.wait()

        if self._stopped:
            return
        if code != 0 and not chunks:
            msg = stderr.strip() or f"Claude Code exited with status {code}."
            self.error_occurred.emit(msg)
            return
        self.response_complete.emit("".join(chunks).strip())

    def stop(self) -> None:
        self._stopped = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:  # pragma: no cover - defensive
                pass


def _no_window_flag() -> int:
    """Avoid spawning a console window for the subprocess on Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Assistant(QObject):
    """Public backend facade. Holds conversation history and the temp dir."""

    token_received = pyqtSignal(str)
    response_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._history: list[dict[str, str]] = []
        self._worker: _Worker | None = None
        self._temp_dir = tempfile.mkdtemp(prefix="cursor-assistant-")
        self._image_path: str | None = None
        self._pending_user = ""
        self._cwd = os.getcwd()

    # ------------------------------------------------------------- lifecycle

    @staticmethod
    def claude_available() -> bool:
        return shutil.which("claude") is not None

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    # --------------------------------------------------------------- sending

    def send(self, user_text: str, image: Image.Image | None) -> None:
        """Start a new request, terminating any in-flight one first."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None

        image_path = self._save_image(image) if image is not None else None
        self._pending_user = self._display_text(user_text, image_path)

        prompt = self._build_prompt(user_text, image_path)
        argv = ["claude", "-p", prompt]
        if image_path is not None:
            # Let Claude Code read the screenshot non-interactively.
            argv += ["--allowed-tools", "Read", "--add-dir", self._temp_dir]

        worker = _Worker(argv, self._cwd)
        worker.token_received.connect(self.token_received.emit)
        worker.response_complete.connect(self._on_complete)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_complete(self, full_text: str) -> None:
        if self._pending_user:
            self._history.append({"role": "user", "content": self._pending_user})
            self._history.append({"role": "assistant", "content": full_text})
            self._trim_history()
            self._pending_user = ""
        self.response_complete.emit()

    def _on_error(self, message: str) -> None:
        self._pending_user = ""
        self.error_occurred.emit(message)

    # ------------------------------------------------------------- prompting

    def _build_prompt(self, user_text: str, image_path: str | None) -> str:
        current = self._display_text(user_text, image_path)
        if not self._history:
            return current

        parts: list[str] = [
            "Continue this conversation. Reply only as the assistant.",
            "",
        ]
        for msg in self._history:
            who = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{who}: {msg['content']}")
        parts.append(f"User: {current}")
        parts.append("Assistant:")
        return "\n".join(parts)

    @staticmethod
    def _display_text(user_text: str, image_path: str | None) -> str:
        user_text = user_text.strip()
        if image_path is None:
            return user_text
        note = (
            f"[A screenshot is attached at: {image_path} — "
            f"use the Read tool to view it.]"
        )
        if user_text:
            return f"{user_text}\n\n{note}"
        return f"Describe and analyze this screenshot.\n\n{note}"

    def _trim_history(self) -> None:
        max_msgs = _MAX_PAIRS * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

    def reset_history(self) -> None:
        self._history.clear()

    # ---------------------------------------------------------------- images

    def _save_image(self, image: Image.Image) -> str:
        # Reuse a single rolling temp file to avoid clutter.
        path = os.path.join(self._temp_dir, "capture.png")
        image.convert("RGB").save(path, format="PNG")
        self._image_path = path
        return path
