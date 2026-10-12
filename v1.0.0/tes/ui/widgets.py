"""Custom widgets: live terminal preview, ambient "code rain", theme swatches."""
from __future__ import annotations

import math
import random

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

from ..core import themes
from ..core.themes import Theme, hex_to_rgb, mix
from . import anim


def rgba(hex_color: str, alpha: float = 1.0) -> Gdk.RGBA:
    r, g, b = hex_to_rgb(hex_color)
    c = Gdk.RGBA()
    c.red, c.green, c.blue, c.alpha = r / 255, g / 255, b / 255, alpha
    return c


def _rect(x, y, w, h) -> Graphene.Rect:
    return Graphene.Rect().init(x, y, w, h)


def _point(x, y) -> Graphene.Point:
    return Graphene.Point().init(x, y)


def _circle(snap, cx: float, cy: float, r: float, color: Gdk.RGBA) -> None:
    """Filled circle. Path fills render reliably on every renderer (tiny rounded clips do not)."""
    pb = Gsk.PathBuilder.new()
    pb.add_circle(_point(cx, cy), r)
    snap.append_fill(pb.to_path(), Gsk.FillRule.WINDING, color)


def _lerp_hex(a: str, b: str, t: float) -> str:
    return mix(a, b, t)


# ======================================================================= preview
class _Backdrop(Gtk.Widget):
    """Paints the terminal window: wallpaper (visible through transparency), body, title bar."""

    __gtype_name__ = "TesTerminalBackdrop"

    def __init__(self, owner: "TerminalPreview"):
        super().__init__()
        self.owner = owner

    def do_snapshot(self, snap):
        o = self.owner
        w, h = self.get_width(), self.get_height()
        # "wallpaper" so translucency is visible
        wall_a, wall_b = rgba("#3b5b8c"), rgba("#8a4f7d")
        try:
            s1, s2 = Gsk.ColorStop(), Gsk.ColorStop()
            s1.offset, s1.color, s2.offset, s2.color = 0.0, wall_a, 1.0, wall_b
            snap.append_linear_gradient(_rect(0, 0, w, h), _point(0, 0), _point(w, h), [s1, s2])
        except Exception:  # noqa: BLE001 - very old PyGObject: flat fallback
            snap.append_color(wall_a, _rect(0, 0, w, h))
        c = o.cur
        snap.append_color(rgba(c["bg"], c["opacity"]), _rect(0, 0, w, h))
        bar = 34
        snap.append_color(rgba(_lerp_hex(c["bg"], c["fg"], 0.07), min(1.0, c["opacity"] + 0.1)), _rect(0, 0, w, bar))
        for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
            self._dot(snap, 14 + i * 18, 12, col)
        layout = self.create_pango_layout(o.title)
        layout.set_font_description(Pango.FontDescription.from_string("Sans 9"))
        pw, _ph = layout.get_pixel_size()
        snap.save()
        snap.translate(_point((w - pw) / 2, 9))
        snap.append_layout(layout, rgba(c["fg"], 0.55))
        snap.restore()

    @staticmethod
    def _dot(snap, x, y, color):
        _circle(snap, x + 5, y + 5, 5, rgba(color, 0.9))


class TerminalPreview(Gtk.Overlay):
    """A fake terminal that shows *your* theme, font, accent and content. Colour changes tween smoothly,
    and text types itself out with a blinking cursor."""

    def __init__(self, title: str = "you@zorin: ~", max_height: int = 280, min_height: int = 120):
        super().__init__()
        self.add_css_class("tes-term")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.title = title
        self._theme: Theme = themes.DEFAULT_THEME
        self._accent = "#7bd88f"
        self.cur = self._target(self._theme)
        self.cur["opacity"] = self._theme.opacity / 100
        self._tween = None
        self._type_id = 0
        self._blink_id = 0
        self._chars: list[tuple[str, str]] = []
        self._pos = 0
        self._has_cursor = False
        self._cursor_on = True

        self.set_child(_Backdrop(self))
        self.view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.NONE,
                                 left_margin=16, right_margin=16, top_margin=44, bottom_margin=16,
                                 can_target=False, focusable=False)
        self.view.add_css_class("tes-term-text")
        self.buf = self.view.get_buffer()
        self._tags: dict[str, Gtk.TextTag] = {}
        keys = ["fg", "dim", "accent", "ok", "bad", "cursor"] + [f"p{i}" for i in range(16)]
        for k in keys:
            self._tags[k] = self.buf.create_tag(k)
        self.scroller = Gtk.ScrolledWindow(child=self.view, propagate_natural_height=True,
                                           max_content_height=max_height, min_content_height=min_height,
                                           hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                           vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        self.scroller.add_css_class("tes-term-scroll")
        self.add_overlay(self.scroller)
        self.set_measure_overlay(self.scroller, True)
        self._apply_font()
        self._apply_colors()
        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    # ------------------------------------------------------------- state helpers
    @staticmethod
    def _target(t: Theme) -> dict:
        return {"bg": t.bg, "fg": t.fg, "cursor": t.cursor, "pal": list(t.palette), "opacity": t.opacity / 100}

    def _color_for(self, key: str) -> str:
        c = self.cur
        if key == "fg":
            return c["fg"]
        if key == "dim":
            return mix(c["fg"], c["bg"], 0.5)
        if key == "accent":
            return self._accent
        if key == "ok":
            return c["pal"][2]
        if key == "bad":
            return c["pal"][1]
        if key == "cursor":
            return c["cursor"]
        return c["pal"][int(key[1:])]

    def _apply_colors(self) -> None:
        for key, tag in self._tags.items():
            if key == "cursor":
                tag.set_property("background-rgba", rgba(self.cur["cursor"], 1.0 if self._cursor_on else 0.0))
            else:
                tag.set_property("foreground-rgba", rgba(self._color_for(key)))
        self.get_child().queue_draw()

    def _apply_font(self) -> None:
        for tag in self._tags.values():
            tag.set_property("family", self._theme.font)
            tag.set_property("size-points", float(self._theme.font_size))

    # ------------------------------------------------------------- public API
    def set_title(self, title: str) -> None:
        self.title = title
        self.get_child().queue_draw()

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._apply_colors()

    def set_theme(self, theme: Theme, animate: bool = True) -> None:
        font_changed = (theme.font, theme.font_size) != (self._theme.font, self._theme.font_size)
        self._theme = theme
        if font_changed:
            self._apply_font()
        target = self._target(theme)
        start = {k: (list(v) if isinstance(v, list) else v) for k, v in self.cur.items()}
        if self._tween is not None:
            self._tween.pause()

        def step(v: float) -> None:
            self.cur = {
                "bg": mix(start["bg"], target["bg"], v), "fg": mix(start["fg"], target["fg"], v),
                "cursor": mix(start["cursor"], target["cursor"], v),
                "pal": [mix(a, b, v) for a, b in zip(start["pal"], target["pal"])],
                "opacity": start["opacity"] + (target["opacity"] - start["opacity"]) * v,
            }
            self._apply_colors()

        self._tween = anim.tween(self, 0.0, 1.0, 380, step) if animate else step(1.0)

    def set_lines(self, lines: list[list[tuple[str, str]]], animate: bool = True) -> None:
        """lines = [[(text, colour_key), ...], ...]. Keys: fg dim accent ok bad p0..p15"""
        self._stop_typing()
        chars: list[tuple[str, str]] = []
        for i, line in enumerate(lines):
            for text, key in line:
                chars += [(ch, key) for ch in text]
            if i < len(lines) - 1:
                chars.append(("\n", "fg"))
        self._chars, self._pos, self._has_cursor = chars, 0, False
        self.buf.set_text("")
        if animate and anim.motion_ok(self) and len(chars) <= 700 and self.get_mapped():
            per_tick = max(1, math.ceil(len(chars) / 38))
            self._type_id = GLib.timeout_add(16, self._type_tick, per_tick)
        else:
            self._reveal(len(chars))
            self._finish_cursor()

    # ------------------------------------------------------------- typing engine
    def _stop_typing(self) -> None:
        if self._type_id:
            GLib.source_remove(self._type_id)
            self._type_id = 0

    def _type_tick(self, n: int) -> bool:
        self._reveal(n)
        if self._pos >= len(self._chars):
            self._type_id = 0
            self._finish_cursor()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _reveal(self, n: int) -> None:
        if self._has_cursor:
            end = self.buf.get_end_iter()
            start = end.copy()
            start.backward_char()
            self.buf.delete(start, end)
            self._has_cursor = False
        stop = min(len(self._chars), self._pos + n)
        run, key = "", None
        for ch, k in self._chars[self._pos:stop]:
            if k != key and run:
                self.buf.insert_with_tags(self.buf.get_end_iter(), run, self._tags[key])
                run = ""
            run += ch
            key = k
        if run:
            self.buf.insert_with_tags(self.buf.get_end_iter(), run, self._tags[key])
        self._pos = stop
        if stop < len(self._chars):
            self._put_cursor()

    def _put_cursor(self) -> None:
        self.buf.insert_with_tags(self.buf.get_end_iter(), " ", self._tags["cursor"], self._tags["fg"])
        self._has_cursor = True

    def _finish_cursor(self) -> None:
        if not self._has_cursor:
            self._put_cursor()
        self._start_blink()

    # ------------------------------------------------------------- cursor blink
    def _start_blink(self) -> None:
        if self._blink_id or not self.get_mapped() or not anim.motion_ok(self):
            self._cursor_on = True
            self._apply_colors()
            return
        self._blink_id = GLib.timeout_add(530, self._blink)

    def _blink(self) -> bool:
        self._cursor_on = not self._cursor_on
        self._apply_colors()
        return GLib.SOURCE_CONTINUE

    def _on_unmap(self, *_):
        self._stop_typing()
        if self._blink_id:
            GLib.source_remove(self._blink_id)
            self._blink_id = 0

    def _on_map(self, *_):
        if self._chars and self._pos >= len(self._chars):
            self._start_blink()


# ======================================================================= code rain
class Rain(Gtk.Widget):
    """Faint falling characters behind the dashboard hero. Pauses when hidden."""

    __gtype_name__ = "TesRain"
    GLYPHS = "01><{}[]/\\|=+-*#$%&;:~"
    CELL_W, CELL_H = 16, 20

    def __init__(self, accent: str = "#7bd88f"):
        super().__init__()
        self.accent = accent
        self._cols: list[dict] = []
        self._layouts: dict[str, Pango.Layout] = {}
        self._tick = 0
        self._last = 0
        self._frame = 0
        self.set_can_target(False)
        self.connect("map", lambda *_: self._start())
        self.connect("unmap", lambda *_: self._stop())

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.queue_draw()

    def _start(self) -> None:
        if not self._tick and anim.motion_ok(self):
            self._last = 0
            self._tick = self.add_tick_callback(self._on_tick)
        else:
            self.queue_draw()

    def _stop(self) -> None:
        if self._tick:
            self.remove_tick_callback(self._tick)
            self._tick = 0

    def _ensure_cols(self, w: int, h: int) -> None:
        n = max(1, w // self.CELL_W)
        if len(self._cols) != n:
            rows = max(1, h // self.CELL_H)
            self._cols = [{"y": random.uniform(-rows, rows), "v": random.uniform(2.5, 7.0),
                           "len": random.randint(5, 13),
                           "chars": [random.choice(self.GLYPHS) for _ in range(40)]} for _ in range(n)]

    def _on_tick(self, _w, clock) -> bool:
        t = clock.get_frame_time()
        dt = (t - self._last) / 1e6 if self._last else 0.0
        self._last = t
        h = self.get_height()
        rows = max(1, h // self.CELL_H)
        for c in self._cols:
            c["y"] += c["v"] * min(dt, 0.1)
            if c["y"] - c["len"] > rows:
                c["y"] = random.uniform(-6, 0)
                c["v"] = random.uniform(2.5, 7.0)
            if random.random() < 0.08:
                c["chars"][random.randrange(len(c["chars"]))] = random.choice(self.GLYPHS)
        self._frame += 1
        if self._frame % 2 == 0:  # ~30 fps is plenty for ambience
            self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _layout(self, ch: str) -> Pango.Layout:
        lay = self._layouts.get(ch)
        if lay is None:
            lay = self.create_pango_layout(ch)
            lay.set_font_description(Pango.FontDescription.from_string("Monospace 11"))
            self._layouts[ch] = lay
        return lay

    def do_snapshot(self, snap):
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        self._ensure_cols(w, h)
        rows = h // self.CELL_H + 1
        for i, c in enumerate(self._cols):
            head = int(c["y"])
            for k in range(c["len"]):
                row = head - k
                if row < 0 or row > rows:
                    continue
                fade = 1.0 - k / c["len"]
                alpha = (0.55 if k == 0 else 0.30) * fade
                snap.save()
                snap.translate(_point(i * self.CELL_W + 2, row * self.CELL_H))
                snap.append_layout(self._layout(c["chars"][(row + i) % 40]), rgba(self.accent, alpha))
                snap.restore()


# ======================================================================= swatches
class _SwatchArt(Gtk.Widget):
    __gtype_name__ = "TesSwatchArt"

    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.set_size_request(132, 74)
        self.add_css_class("tes-swatch-art")
        self.set_overflow(Gtk.Overflow.HIDDEN)

    def do_snapshot(self, snap):
        t = self.theme
        w, h = self.get_width(), self.get_height()
        snap.append_color(rgba(t.bg), _rect(0, 0, w, h))  # corners are rounded by CSS + overflow
        lay = self.create_pango_layout("Aa  ~$")
        lay.set_font_description(Pango.FontDescription.from_string("Monospace Bold 11"))
        snap.save()
        snap.translate(_point(10, 8))
        snap.append_layout(lay, rgba(t.fg))
        snap.restore()
        for i, idx in enumerate((1, 2, 3, 4, 5, 6)):
            _circle(snap, 17 + i * 19, 53, 7, rgba(t.palette[idx]))


class ThemeCard(Gtk.ToggleButton):
    """A selectable preset card (use group= to make a radio set)."""

    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.add_css_class("tes-card-btn")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6,
                      margin_start=6, margin_end=6)
        box.append(_SwatchArt(theme))
        lbl = Gtk.Label(label=theme.name, ellipsize=Pango.EllipsizeMode.END, max_width_chars=16)
        lbl.add_css_class("caption")
        box.append(lbl)
        self.set_child(box)
        self.set_tooltip_text(theme.name)
