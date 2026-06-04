# Cursor Assistant — Floating AI Window

A lightweight, always-on-top floating panel that lets you screenshot a region
of your screen, ask a question, and get a Claude answer — without leaving your
current app. The backend is the **Claude Code CLI** (`claude -p`), so there are
no API keys or third-party services to configure.

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) on your `PATH`
  (`npm install -g @anthropic-ai/claude-code`, then run `claude` once to log in)

## Install

```powershell
pip install PyQt6 Pillow pynput
```

(Or `pip install .` to use the `pyproject.toml`.)

## Run

```powershell
python main.py
```

Or double-click **`run.bat`** (launches without a console window).

## Usage

| Action | How |
|---|---|
| Show / hide the window | **Double middle-click** (scroll wheel) anywhere |
| Ask a question | Type in the input bar, press **Enter** |
| Screenshot a region | Click 📷, or press **Ctrl+Shift+X** anywhere |
| Paste an image | **Ctrl+V** with an image on the clipboard |
| Hide the window | **Esc** |
| Collapse to title bar | the **–** button |
| Quit | the **✕** button |

- **Double-click the scroll wheel** anywhere to summon the window — it fades in
  **at your cursor**. Double-click (rather than single) so it doesn't clash with
  browser middle-click or Windows autoscroll. Double-click again or press **Esc**
  to dismiss it.
- Drag the window by its title bar; it stays where you put it.
- Resize from the bottom-right grip.
- The last 10 turns of conversation are kept as context (resets on quit).

## How it works

- `main.py` — entry point, global hotkeys (pynput), app wiring
- `ui/window.py` — the frameless translucent floating panel
- `ui/styles.py` — theme constants + QSS
- `ui/markdown.py` — tiny regex markdown → HTML renderer
- `capture.py` — fullscreen region-selection overlay (Pillow `ImageGrab`)
- `assistant.py` — `claude -p` subprocess wrapper (runs in a `QThread`)

Screenshots are written to a temp PNG and Claude Code reads them via its
`Read` tool (`--allowed-tools Read`).

## Notes

- Primary target: **Windows**. Frameless translucent windows and `ImageGrab`
  work natively with no extra permissions.
- Multi-monitor capture is supported (the overlay spans the virtual desktop;
  coordinates are scaled by the device pixel ratio for crisp crops).
