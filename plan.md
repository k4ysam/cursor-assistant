# Cursor Assistant — Floating AI Window

## What it is

A lightweight, always-on-top floating window that lives on the user's screen. The user can screenshot a region of their screen, paste it into the window, type a question, and get a Claude response — all without leaving their current app/tab. The LLM backend is Claude Code CLI (`claude -p`), so no API keys or third-party services are needed.

## Tech stack

- **Python 3.11+**
- **PyQt6** for the GUI (transparency, frameless windows, good rendering)
- **Pillow** for screenshot capture and image handling
- **Claude Code CLI** (`claude -p`) as the LLM backend via subprocess
- Package with **pyproject.toml**

## Project structure

```
cursor-assistant/
├── pyproject.toml
├── main.py              # Entry point, global hotkeys, app lifecycle
├── assistant.py          # Claude Code subprocess wrapper
├── capture.py            # Screenshot region selection overlay
└── ui/
    ├── __init__.py
    ├── window.py         # Main floating window widget
    └── styles.py         # QSS stylesheets and theme constants
```

## Floating window (`ui/window.py`)

- Fixed default size: ~400×500px, resizable via drag handle at bottom-right corner
- Window flags: `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`
  - `Tool` flag keeps it off the taskbar/dock
- Use `setAttribute(Qt.WA_TranslucentBackground)` + a styled inner `QFrame` with border-radius for rounded corners
- Dark theme, ~92% opacity on the inner frame
- On launch, position at center-right of screen. User drags it wherever they want, it stays put. Does NOT follow the cursor — it's a persistent floating panel.

### Layout (top to bottom)

1. **Custom title bar**
   - Left: small label "cursor" in muted text
   - Right: collapse/expand toggle button, close button
   - Entire title bar is the drag handle — implement via `mousePressEvent`/`mouseMoveEvent` tracking

2. **Image preview area** (hidden when empty)
   - Shows captured screenshot as a scaled thumbnail (max height ~120px)
   - Small "×" button in the top-right corner of the thumbnail to remove the image
   - Only visible when an image has been captured/pasted

3. **Response area**
   - `QTextBrowser` that renders Claude's response
   - Render basic markdown as HTML (bold, code blocks, inline code, lists). Use a simple regex-based markdown-to-HTML converter — don't pull in a dependency for this.
   - Scrollable, auto-scrolls to bottom as new tokens stream in
   - Monospace font for code blocks, proportional font for prose
   - When empty, show muted placeholder text: "Screenshot or type a question"

4. **Input bar**
   - Horizontal layout: screenshot button (camera icon, use Unicode 📷 or a simple SVG), `QLineEdit` text input, send button (→ arrow)
   - Enter key sends the message
   - `QLineEdit` placeholder: "Ask anything..."
   - When a request is in-flight: disable the send button, show a small pulsing dot or "thinking..." text in the response area

### Keyboard shortcuts (within the window)

- `Enter` — send message
- `Ctrl+V` / `Cmd+V` — if clipboard contains an image, capture it into the image preview area. If text, paste into input as normal.
- `Escape` — hide the window

## Screenshot capture (`capture.py`)

Triggered by:
- Clicking the camera/screenshot button in the input bar
- Global hotkey (see below)

### Flow

1. Hide the floating window
2. Brief delay (~200ms) so the window is fully hidden before capture
3. Create a fullscreen translucent overlay widget (`Qt.WindowStaysOnTopHint | Qt.FullScreen`)
4. Overlay is a semi-transparent dark fill over the whole screen. Cursor changes to crosshair.
5. User clicks and drags to draw a selection rectangle — render the rectangle border in white/light color with 1-2px stroke, and keep the selected region at full brightness (cut out the dark overlay inside the selection)
6. On mouse release: grab the selected region using `Pillow.ImageGrab.grab(bbox=(x1, y1, x2, y2))`, close the overlay, show the floating window, and display the capture in the image preview area
7. Auto-focus the text input so the user can immediately type a question

### Edge cases

- `Escape` during selection cancels — close overlay, re-show window, no image captured
- If the selection rectangle is tiny (< 10px either axis), treat as a cancel
- Multi-monitor: `ImageGrab.grab` handles coordinates across monitors on most platforms. Test and note any issues.

## LLM backend (`assistant.py`)

### How it works

Claude Code CLI supports non-interactive mode: `claude -p "prompt"` sends a prompt and prints the response to stdout. This is the entire backend — a subprocess call.

### Text-only flow

```python
process = subprocess.Popen(
    ["claude", "-p", prompt],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)
```

Read `stdout` line by line in a loop, emit each chunk to the UI via a `pyqtSignal`.

### Screenshot flow

Save the captured image to a temp file (PNG). Pass it alongside the prompt:

```python
process = subprocess.Popen(
    ["claude", "-p", prompt, temp_image_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)
```

At startup, run `claude --help` and parse the output to confirm the exact flag/syntax for file attachments. If the CLI doesn't support positional file args, try `--file` or `--image` flags. As a last-resort fallback, base64-encode the image and embed it as a data URI in the prompt text.

### Implementation details

- Run the subprocess in a `QThread` to keep the UI responsive
- The thread emits signals: `token_received(str)`, `response_complete()`, `error_occurred(str)`
- If the user sends a new message while a response is still streaming, call `process.terminate()` on the running subprocess, wait briefly for cleanup, then start the new one
- Strip any ANSI escape codes / CLI formatting from stdout before displaying (regex: `\x1b\[[0-9;]*m`)
- If `claude` is not found on PATH, show in the response area: "Claude Code not found. Install it: npm install -g @anthropic-ai/claude-code"
- Maintain conversation context: keep a list of the last 10 user/assistant message pairs. On each new message, format the full conversation as a single prompt string with clear `User:` / `Assistant:` delimiters and send it all to `claude -p`. Claude Code does not have multi-turn memory between invocations, so the full context must be included each time.

## Global hotkeys (`main.py`)

Use `pynput.keyboard.GlobalHotKeys` for system-wide shortcuts that work even when the app is not focused:

- `Ctrl+Shift+X` — trigger screenshot capture
- `Ctrl+Shift+Space` — toggle window show/hide

Run `pynput` listener in its own thread (it manages this internally). Connect hotkey callbacks to Qt slots via `QMetaObject.invokeMethod` with `Qt.QueuedConnection` to safely cross the thread boundary into the Qt event loop.

## Styling (`ui/styles.py`)

Dark theme. Define all colors and styles in one place.

- Background: `#1a1a1a` at ~92% opacity
- Input bar background: `#2a2a2a`
- Text color: `#e0e0e0`
- Muted text: `#666666`
- Accent (buttons, selection border): `#4a9eff`
- Code block background: `#252525`
- Font: system default sans-serif for UI, monospace for code blocks
- Border radius on outer frame: 12px
- No heavy borders anywhere — use subtle 1px `#333` dividers between sections

Export a single QSS string that gets applied to the main window.

## Config

None. No env vars, no config files, no settings UI. Claude Code handles its own auth. The only requirement is `claude` on PATH.

## What NOT to build

- No settings/preferences UI
- No conversation persistence across sessions (history resets on close)
- No tray icon or menu bar integration
- No auto-update mechanism
- No window snapping or magnetic screen edges
- No multiple conversation tabs
- No file drag-and-drop (only screenshot capture and clipboard paste)
- No markdown rendering library — keep the regex converter minimal and handle bold, inline code, code blocks, and lists only

## Platform notes

- Primary target: Windows
- PyQt6 frameless translucent windows work on Windows. If there are rendering issues, fall back to a regular `QFrame` with solid dark background and skip translucency.
- `ImageGrab.grab` from Pillow works natively on Windows with no extra permissions.
- `pynput` works on Windows without special permissions.
- Use `Ctrl` (not `Cmd`) for all hotkeys.