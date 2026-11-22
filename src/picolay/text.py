"""Text measurement, wrapping and shrink-to-fit, shared by layout and rendering."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from PIL import ImageFont

from .fonts import load_font
from .style import Style


def font_for(style: Style, size: int | None = None) -> ImageFont.FreeTypeFont:
    return load_font(style.font_path, size or style.font_size)


# Pillow text mode to measure in: "" (anti-aliased) or "1" (hard-edged). Glyphs are hinted
# differently in the two, so text has to be measured the way it will be drawn.
_text_mode: ContextVar[str] = ContextVar("picolay_text_mode", default="")


@contextmanager
def measuring(antialias: bool):
    """Measure text as it is drawn with (or without) anti-aliasing, within this block."""
    token = _text_mode.set("" if antialias else "1")
    try:
        yield
    finally:
        _text_mode.reset(token)


def text_bbox(font: ImageFont.FreeTypeFont, text: str) -> tuple[float, float, float, float]:
    return font.getbbox(text, mode=_text_mode.get())


def text_width(font: ImageFont.FreeTypeFont, text: str) -> float:
    bbox = text_bbox(font, text)
    return bbox[2] - bbox[0]


def line_pitch(style: Style, size: int) -> int:
    """Distance between the tops of consecutive wrapped lines."""
    return size + style.line_spacing


def wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Greedy word wrap. A word too long for a line on its own is split with a hyphen."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if text_width(font, candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # Hyphenate a word that doesn't fit on an empty line
        while text_width(font, word) > max_width and len(word) > 1:
            cut = len(word) - 1
            while cut > 1 and text_width(font, word[:cut] + "-") > max_width:
                cut -= 1
            lines.append(word[:cut] + "-")
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def wrapped_height(style: Style, size: int, num_lines: int) -> float:
    return num_lines * line_pitch(style, size)


def fit_wrapped(style: Style, content: str, max_w: float, max_h: float | None) -> tuple[int, list[str]]:
    """Return (font_size, lines) for wrapped text.

    With font_shrink, steps the size down until every line fits max_w and the block
    fits max_h, stopping at min_font_size (where the text may overflow).
    """
    size = style.font_size
    lines = wrap_lines(content, font_for(style, size), max_w)
    if not style.font_shrink:
        return size, lines
    floor = max(1, style.min_font_size)
    while size > floor:
        too_tall = max_h is not None and wrapped_height(style, size, len(lines)) > max_h
        too_wide = any(text_width(font_for(style, size), ln) > max_w for ln in lines)
        if not (too_tall or too_wide):
            break
        size -= 1
        lines = wrap_lines(content, font_for(style, size), max_w)
    return size, lines
