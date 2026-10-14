"""Terminal themes: a common model every terminal adapter understands."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
CURSOR_SHAPES = ("block", "beam", "underline")
PALETTE_NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


# ---------------------------------------------------------------- colour helpers
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % (max(0, min(255, round(r))), max(0, min(255, round(g))), max(0, min(255, round(b))))


def mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return rgb_to_hex(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t)


def luminance(h: str) -> float:
    r, g, b = (c / 255 for c in hex_to_rgb(h))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def nearest_256(h: str) -> int:
    """Nearest xterm-256 colour index (cube + greyscale ramp), so prompts work in any terminal."""
    r, g, b = hex_to_rgb(h)
    steps = (0, 95, 135, 175, 215, 255)

    def near(v: int) -> int:
        return min(range(6), key=lambda i: abs(steps[i] - v))

    ri, gi, bi = near(r), near(g), near(b)
    cube = 16 + 36 * ri + 6 * gi + bi
    cr, cg, cb = steps[ri], steps[gi], steps[bi]
    grey_i = max(0, min(23, round(((r + g + b) / 3 - 8) / 10)))
    gv = 8 + 10 * grey_i
    d_cube = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
    d_grey = (r - gv) ** 2 + (g - gv) ** 2 + (b - gv) ** 2
    return 232 + grey_i if d_grey < d_cube else cube


# ---------------------------------------------------------------- the model
@dataclass(frozen=True)
class Theme:
    name: str
    fg: str
    bg: str
    cursor: str
    palette: tuple[str, ...]  # 16 colours: 8 normal + 8 bright
    font: str = "Monospace"
    font_size: float = 11.0
    cursor_shape: str = "block"
    opacity: int = 100  # percent opaque, 30..100
    bg_image: str = ""

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["palette"] = list(self.palette)
        return d

    def with_(self, **kw) -> "Theme":
        if "palette" in kw:
            kw["palette"] = tuple(kw["palette"])
        return replace(self, **kw)


def _p(normal: str, bright: str) -> tuple[str, ...]:
    return tuple(normal.split()) + tuple(bright.split())


PRESETS: dict[str, Theme] = {t.name: t for t in [
    Theme("Studio Dark", "#a8e6b1", "#0d1218", "#7bd88f",
          _p("#1b2430 #ff6b6b #7bd88f #f4d35e #6ea8fe #c792ea #5ad1c4 #cfd8e3",
             "#3a4757 #ff8787 #9be8ab #ffe08a #8fbcff #dba8f5 #7fe3d8 #ffffff")),
    Theme("Dracula", "#f8f8f2", "#282a36", "#f8f8f2",
          _p("#21222c #ff5555 #50fa7b #f1fa8c #bd93f9 #ff79c6 #8be9fd #f8f8f2",
             "#6272a4 #ff6e6e #69ff94 #ffffa5 #d6acff #ff92df #a4ffff #ffffff")),
    Theme("Nord", "#d8dee9", "#2e3440", "#d8dee9",
          _p("#3b4252 #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #88c0d0 #e5e9f0",
             "#4c566a #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #8fbcbb #eceff4")),
    Theme("Tokyo Night", "#c0caf5", "#1a1b26", "#c0caf5",
          _p("#15161e #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #a9b1d6",
             "#414868 #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #c0caf5")),
    Theme("Catppuccin Mocha", "#cdd6f4", "#1e1e2e", "#f5e0dc",
          _p("#45475a #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #bac2de",
             "#585b70 #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #a6adc8")),
    Theme("Gruvbox Dark", "#ebdbb2", "#282828", "#ebdbb2",
          _p("#282828 #cc241d #98971a #d79921 #458588 #b16286 #689d6a #a89984",
             "#928374 #fb4934 #b8bb26 #fabd2f #83a598 #d3869b #8ec07c #ebdbb2")),
    Theme("One Dark", "#abb2bf", "#282c34", "#528bff",
          _p("#282c34 #e06c75 #98c379 #e5c07b #61afef #c678dd #56b6c2 #abb2bf",
             "#5c6370 #e06c75 #98c379 #e5c07b #61afef #c678dd #56b6c2 #ffffff")),
    Theme("Solarized Dark", "#839496", "#002b36", "#93a1a1",
          _p("#073642 #dc322f #859900 #b58900 #268bd2 #d33682 #2aa198 #eee8d5",
             "#002b36 #cb4b16 #586e75 #657b83 #839496 #6c71c4 #93a1a1 #fdf6e3")),
    Theme("Matrix", "#33ff66", "#020a04", "#33ff66",
          _p("#04140a #1f8f3a #33ff66 #9dff7a #1fbf55 #5cff9a #2de0a0 #b6ffcb",
             "#0b3a1c #2fbf55 #66ff8f #c8ffa6 #4cdf7c #86ffb8 #5cffc8 #e6fff0")),
    Theme("Solarized Light", "#586e75", "#fdf6e3", "#586e75",
          _p("#073642 #dc322f #859900 #b58900 #268bd2 #d33682 #2aa198 #eee8d5",
             "#002b36 #cb4b16 #586e75 #657b83 #839496 #6c71c4 #93a1a1 #fdf6e3")),
]}

DEFAULT_THEME = PRESETS["Studio Dark"]


# ---------------------------------------------------------------- validation / IO
class ThemeError(ValueError):
    pass


def _hex(v, field_name: str) -> str:
    if not isinstance(v, str) or not HEX_RE.match(v.strip()):
        raise ThemeError(f"'{field_name}' must be a colour like #1a2b3c")
    return v.strip().lower()


def from_dict(d: dict, strict: bool = True) -> Theme:
    """Build a Theme from untrusted data (imported file, settings). Never trusts types."""
    if not isinstance(d, dict):
        raise ThemeError("Theme must be a JSON object")
    base = DEFAULT_THEME
    try:
        pal = d.get("palette", list(base.palette))
        if not isinstance(pal, (list, tuple)) or len(pal) != 16:
            raise ThemeError("'palette' needs exactly 16 colours")
        font = d.get("font", base.font)
        if not isinstance(font, str) or not font.strip() or len(font) > 80 or re.search(r"[\x00-\x1f\n\"'\\]", font):
            raise ThemeError("'font' must be a plain font family name")
        size = float(d.get("font_size", base.font_size))
        opacity = int(d.get("opacity", base.opacity))
        shape = d.get("cursor_shape", base.cursor_shape)
        if shape not in CURSOR_SHAPES:
            raise ThemeError("'cursor_shape' must be block, beam or underline")
        img = d.get("bg_image", "")
        if not isinstance(img, str) or "\n" in img or len(img) > 1024:
            raise ThemeError("'bg_image' must be a file path")
        name = str(d.get("name", "Custom"))[:60] or "Custom"
        return Theme(
            name=re.sub(r"[\x00-\x1f]", "", name),
            fg=_hex(d.get("fg", base.fg), "fg"),
            bg=_hex(d.get("bg", base.bg), "bg"),
            cursor=_hex(d.get("cursor", base.cursor), "cursor"),
            palette=tuple(_hex(c, "palette") for c in pal),
            font=font.strip(),
            font_size=max(6.0, min(48.0, size)),
            cursor_shape=shape,
            opacity=max(30, min(100, opacity)),
            bg_image=img,
        )
    except ThemeError:
        if strict:
            raise
        return base
    except (TypeError, ValueError) as exc:
        if strict:
            raise ThemeError(f"Invalid theme value: {exc}") from exc
        return base


def dumps(theme: Theme) -> str:
    return json.dumps({"tes_theme": 1, **theme.to_dict()}, indent=2)


def loads(text: str) -> Theme:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ThemeError("That file isn't valid JSON") from exc
    if isinstance(data, dict):
        data.pop("tes_theme", None)
    return from_dict(data)
