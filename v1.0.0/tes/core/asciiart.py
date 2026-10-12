"""Image -> ASCII conversion.

Pure Python on raw pixel bytes, so it has no dependency of its own: the GUI loads and scales
images with GdkPixbuf (already part of GTK) and hands the pixels to `pixels_to_ascii`.
"""
from __future__ import annotations

# Ordered from "empty" to "dense". On a dark terminal, bright pixels become dense characters.
CHARSETS = {
    "Classic": " .:-=+*#%@",
    "Blocks": " ░▒▓█",
    "Detailed": " .'`^,:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "Simple": " .oO@",
}
CHAR_ASPECT = 0.5  # terminal cells are about twice as tall as wide


def target_size(src_w: int, src_h: int, cols: int) -> tuple[int, int]:
    cols = max(8, min(200, cols))
    rows = max(1, round(src_h / max(1, src_w) * cols * CHAR_ASPECT))
    return cols, min(rows, 120)


def pixels_to_ascii(data: bytes, width: int, height: int, rowstride: int, channels: int,
                    has_alpha: bool, charset: str = "Classic", contrast: float = 1.0,
                    brightness: float = 0.0, invert: bool = False) -> str:
    ramp = CHARSETS.get(charset, CHARSETS["Classic"])
    top = len(ramp) - 1
    rows: list[str] = []
    for y in range(height):
        base = y * rowstride
        chars = []
        for x in range(width):
            i = base + x * channels
            r, g, b = data[i], data[i + 1], data[i + 2]
            if has_alpha and data[i + 3] < 40:
                chars.append(" ")
                continue
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            lum = (lum - 0.5) * contrast + 0.5 + brightness
            lum = 0.0 if lum < 0 else 1.0 if lum > 1 else lum
            if invert:
                lum = 1.0 - lum
            chars.append(ramp[round(lum * top)])
        rows.append("".join(chars).rstrip())
    while rows and not rows[-1]:
        rows.pop()
    return "\n".join(rows)
