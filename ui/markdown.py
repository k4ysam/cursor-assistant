"""Minimal regex-based markdown to HTML converter.

Intentionally tiny: handles fenced code blocks, inline code, bold, and lists.
No external dependency. Anything fancier is out of scope per the project plan.
"""

import html
import re

_FENCE_RE = re.compile(r"```[ \t]*([\w+-]*)\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ULIST_RE = re.compile(r"^[ \t]*[-*+] +(.*)$")
_OLIST_RE = re.compile(r"^[ \t]*\d+\. +(.*)$")


def to_html(text: str) -> str:
    """Convert a markdown string to a small, safe HTML fragment."""
    if not text:
        return ""

    # 1. Pull fenced code blocks out first so their contents are left untouched.
    code_blocks: list[str] = []

    def _stash_fence(match: re.Match) -> str:
        code = match.group(2)
        escaped = html.escape(code.rstrip("\n"))
        code_blocks.append(f"<pre><code>{escaped}</code></pre>")
        return f"\x00CODE{len(code_blocks) - 1}\x00"

    text = _FENCE_RE.sub(_stash_fence, text)

    # 2. Process the remaining text line by line for lists + paragraphs.
    lines = text.split("\n")
    out: list[str] = []
    list_mode: str | None = None  # "ul" or "ol"

    def _close_list() -> None:
        nonlocal list_mode
        if list_mode:
            out.append(f"</{list_mode}>")
            list_mode = None

    for line in lines:
        # Preserve code-block placeholders as their own blocks.
        if re.fullmatch(r"\x00CODE\d+\x00", line.strip()):
            _close_list()
            out.append(line.strip())
            continue

        ul = _ULIST_RE.match(line)
        ol = _OLIST_RE.match(line)
        if ul:
            if list_mode != "ul":
                _close_list()
                out.append("<ul>")
                list_mode = "ul"
            out.append(f"<li>{_inline(ul.group(1))}</li>")
        elif ol:
            if list_mode != "ol":
                _close_list()
                out.append("<ol>")
                list_mode = "ol"
            out.append(f"<li>{_inline(ol.group(1))}</li>")
        elif line.strip() == "":
            _close_list()
            out.append("<br>")
        else:
            _close_list()
            out.append(f"{_inline(line)}<br>")

    _close_list()
    result = "\n".join(out)

    # 3. Restore the stashed code blocks.
    for i, block in enumerate(code_blocks):
        result = result.replace(f"\x00CODE{i}\x00", block)

    return result


def _inline(text: str) -> str:
    """Escape HTML, then apply inline code and bold formatting."""
    # Stash inline code so escaping/bold don't touch it.
    spans: list[str] = []

    def _stash_code(match: re.Match) -> str:
        spans.append(html.escape(match.group(1)))
        return f"\x01C{len(spans) - 1}\x01"

    text = _INLINE_CODE_RE.sub(_stash_code, text)
    text = html.escape(text)
    text = _BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)

    for i, code in enumerate(spans):
        text = text.replace(f"\x01C{i}\x01", f"<code>{code}</code>")
    return text
