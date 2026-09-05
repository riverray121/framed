"""Rendering of layer content into 64x64 RGB frames."""

from __future__ import annotations

import random

from PIL import Image, ImageEnhance, ImageOps

from framed.font import GLYPH_H, draw_centered

SIZE = 64
RGB = tuple[int, int, int]
BLACK: RGB = (0, 0, 0)
WHITE: RGB = (255, 255, 255)


def parse_color(value: str | list | tuple | None, default: RGB = WHITE) -> RGB:
    if value is None:
        return default
    if isinstance(value, list | tuple) and len(value) == 3:
        return tuple(max(0, min(255, int(v))) for v in value)  # type: ignore[return-value]
    if isinstance(value, str):
        s = value.lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    raise ValueError(f"bad color {value!r}")


def blank(color: RGB = BLACK) -> Image.Image:
    return Image.new("RGB", (SIZE, SIZE), color)


def fit_image(image: Image.Image, *, saturation: float = 1.0, contrast: float = 1.0) -> Image.Image:
    """Square-crop from the center, resample to the panel, apply optional lifts."""
    out = ImageOps.fit(image.convert("RGB"), (SIZE, SIZE), Image.LANCZOS, centering=(0.5, 0.5))
    if saturation != 1.0:
        out = ImageEnhance.Color(out).enhance(saturation)
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    return out


def text_frame(lines: list[str], color: RGB = WHITE, background: RGB = BLACK) -> Image.Image:
    """Up to five lines of text, vertically centered as a block."""
    lines = lines[:5]
    frame = blank(background)
    line_h = GLYPH_H + 2
    top = (SIZE - (len(lines) * line_h - 2)) // 2
    for i, line in enumerate(lines):
        draw_centered(frame, line, top + i * line_h, color)
    return frame


def _scaled(color: RGB, factor: float) -> RGB:
    return tuple(int(c * factor) for c in color)  # type: ignore[return-value]


def greeting_frames(
    name: str,
    color: RGB,
    *,
    frames: int = 16,
    headline: str = "WELCOME HOME",
) -> list[Image.Image]:
    """A short looping animation: the headline, the name fading in, drifting sparkles."""
    rng = random.Random(name)
    sparkles = [(rng.randrange(SIZE), rng.randrange(SIZE), rng.random()) for _ in range(28)]
    words = headline.split()
    out = []
    for i in range(frames):
        t = i / max(1, frames - 1)
        frame = blank()
        px = frame.load()
        for sx, sy, phase in sparkles:
            level = (phase + t) % 1.0
            bright = int(255 * (1 - abs(level * 2 - 1)))
            y = (sy - i) % SIZE
            px[sx, y] = _scaled(color, bright / 255 * 0.55)
        y = 10
        for word in words:
            draw_centered(frame, word, y, WHITE)
            y += GLYPH_H + 2
        fade = min(1.0, i / max(1, frames // 3))
        draw_centered(frame, name, 38, _scaled(color, fade), scale=2 if len(name) <= 5 else 1)
        bar_w = int(SIZE * t)
        for x in range((SIZE - bar_w) // 2, (SIZE + bar_w) // 2):
            px[x, 58] = color
        out.append(frame)
    return out
