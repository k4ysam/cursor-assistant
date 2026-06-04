"""Theme constants and QSS stylesheet for the Cursor Assistant window.

All colors and styling live here so the look can be tweaked in one place.
Dark theme, subtle dividers, no heavy borders.
"""

# --- Color palette -----------------------------------------------------------

BACKGROUND = "#1a1a1a"        # outer frame background
INPUT_BG = "#2a2a2a"          # input bar / fields
SURFACE = "#202020"           # secondary surfaces (image preview, etc.)
TEXT = "#e0e0e0"              # primary text
MUTED = "#666666"            # muted / placeholder text
ACCENT = "#4a9eff"           # buttons, selection border
ACCENT_HOVER = "#5fa9ff"      # accent hover state
CODE_BG = "#252525"          # code block background
DIVIDER = "#333333"          # subtle 1px dividers

# Inner frame opacity (~92%). Applied via the QFrame stylesheet alpha channel.
FRAME_ALPHA = "0.94"

# --- Geometry ----------------------------------------------------------------

BORDER_RADIUS = 12
DEFAULT_WIDTH = 340
DEFAULT_HEIGHT = 400
MIN_WIDTH = 280
MIN_HEIGHT = 220
PREVIEW_MAX_HEIGHT = 120

# --- Animation ---------------------------------------------------------------

ANIM_IN_MS = 150    # fade + slide in
ANIM_OUT_MS = 110   # fade out
SLIDE_PX = 10       # upward slide distance on appear


def _rgba(hex_color: str, alpha: str) -> str:
    """Convert a #rrggbb hex string into a CSS rgba() with the given alpha."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


# --- Stylesheet --------------------------------------------------------------

STYLESHEET = f"""
#OuterFrame {{
    background-color: {_rgba(BACKGROUND, FRAME_ALPHA)};
    border-radius: {BORDER_RADIUS}px;
    border: 1px solid {DIVIDER};
}}

QWidget {{
    color: {TEXT};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

/* --- Title bar --- */
#TitleBar {{
    background-color: transparent;
    border-bottom: 1px solid {DIVIDER};
}}

#TitleLabel {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 1px;
}}

#TitleButton, #CloseButton {{
    background-color: transparent;
    color: {MUTED};
    border: none;
    border-radius: 4px;
    font-size: 15px;
    padding: 0px;
}}
#TitleButton:hover {{
    background-color: {INPUT_BG};
    color: {TEXT};
}}
#CloseButton:hover {{
    background-color: #c0392b;
    color: #ffffff;
}}

/* --- Image preview --- */
#PreviewContainer {{
    background-color: {SURFACE};
    border: 1px solid {DIVIDER};
    border-radius: 8px;
}}
#PreviewRemove {{
    background-color: rgba(0, 0, 0, 0.6);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-size: 13px;
    font-weight: bold;
}}
#PreviewRemove:hover {{
    background-color: #c0392b;
}}

/* --- Response area --- */
#ResponseArea {{
    background-color: transparent;
    border: none;
    color: {TEXT};
    font-size: 13px;
}}
#ResponseArea QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
}}
#ResponseArea QScrollBar::handle:vertical {{
    background: {DIVIDER};
    border-radius: 4px;
    min-height: 24px;
}}
#ResponseArea QScrollBar::handle:vertical:hover {{
    background: {MUTED};
}}
#ResponseArea QScrollBar::add-line:vertical,
#ResponseArea QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* --- Input bar --- */
#InputBar {{
    background-color: {INPUT_BG};
    border-radius: 10px;
    border: 1px solid {DIVIDER};
}}

#InputField {{
    background-color: transparent;
    border: none;
    color: {TEXT};
    font-size: 13px;
    padding: 4px;
}}

#IconButton {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    color: {MUTED};
}}
#IconButton:hover {{
    background-color: {SURFACE};
    color: {TEXT};
}}
#IconButton:disabled {{
    color: #444444;
}}

#SendButton {{
    background-color: {ACCENT};
    border: none;
    border-radius: 6px;
    font-size: 16px;
    color: #ffffff;
}}
#SendButton:hover {{
    background-color: {ACCENT_HOVER};
}}
#SendButton:disabled {{
    background-color: #2f4a66;
    color: #88a;
}}

/* --- Resize grip --- */
#ResizeGrip {{
    background-color: transparent;
}}
"""


def response_html_styles() -> str:
    """Inline CSS injected into the QTextBrowser document for rendered markdown."""
    return f"""
    <style>
        body {{
            color: {TEXT};
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
            line-height: 1.5;
        }}
        code {{
            background-color: {CODE_BG};
            color: #f0c674;
            font-family: "Cascadia Code", "Consolas", monospace;
            font-size: 12px;
            padding: 1px 4px;
            border-radius: 3px;
        }}
        pre {{
            background-color: {CODE_BG};
            border: 1px solid {DIVIDER};
            border-radius: 6px;
            padding: 8px;
            margin: 6px 0px;
        }}
        pre code {{
            background-color: transparent;
            padding: 0px;
            color: {TEXT};
        }}
        b, strong {{ color: #ffffff; }}
        a {{ color: {ACCENT}; }}
        ul, ol {{ margin: 4px 0px; padding-left: 20px; }}
        .placeholder {{ color: {MUTED}; }}
        .thinking {{ color: {ACCENT}; font-style: italic; }}
        .error {{ color: #e74c3c; }}
    </style>
    """
