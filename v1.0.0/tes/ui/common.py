"""Reusable UI scaffolding shared by every page."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from . import anim


def label(text: str, *classes: str, wrap: bool = True, xalign: float = 0.0, **kw) -> Gtk.Label:
    lb = Gtk.Label(label=text, xalign=xalign, wrap=wrap, **kw)
    for c in classes:
        lb.add_css_class(c)
    return lb


def group(title: str = "", description: str = "") -> Adw.PreferencesGroup:
    g = Adw.PreferencesGroup()
    if title:
        g.set_title(title)
    if description:
        g.set_description(description)
    return g


def combo_row(title: str, items: list[str], selected: int = 0, subtitle: str = "") -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(items), selected=selected)
    if subtitle:
        row.set_subtitle(subtitle)
    return row


def icon_button(icon: str, text: str, *classes: str) -> Gtk.Button:
    box = Gtk.Box(spacing=8)
    box.append(Gtk.Image.new_from_icon_name(icon))
    box.append(Gtk.Label(label=text))
    b = Gtk.Button(child=box)
    for c in classes:
        b.add_css_class(c)
    return b


class Page(Gtk.Box):
    """A page = optional pinned header (usually a live preview) + scrolling body of animated sections."""

    title = ""
    subtitle = ""
    icon = "user-home-symbolic"
    page_id = ""
    show_apply_bar = True

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.state = win.state
        self._motions: list[anim.Motion] = []
        self.pinned = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        pin_clamp = Adw.Clamp(maximum_size=900, tightening_threshold=700, child=self.pinned,
                              margin_start=24, margin_end=24, margin_top=18, margin_bottom=6)
        self.pin_clamp = pin_clamp
        self.pin_clamp.set_visible(False)
        self.append(pin_clamp)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        clamp = Adw.Clamp(maximum_size=900, tightening_threshold=700, child=self.body,
                          margin_start=24, margin_end=24, margin_top=14, margin_bottom=32)
        self.scroller = Gtk.ScrolledWindow(child=clamp, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.append(self.scroller)

    def header(self, eyebrow: str = "") -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        if eyebrow:
            box.append(label(eyebrow.upper(), "tes-eyebrow"))
        box.append(label(self.title, "tes-title"))
        box.append(label(self.subtitle, "tes-subtitle"))
        self.add(box)

    def pin(self, widget: Gtk.Widget) -> Gtk.Widget:
        self.pin_clamp.set_visible(True)
        self.pinned.append(widget)
        return widget

    def add(self, widget: Gtk.Widget) -> Gtk.Widget:
        m = anim.Motion(widget)
        self.body.append(m)
        self._motions.append(m)
        return widget

    # hooks
    def on_shown(self) -> None:
        anim.stagger(self._motions, step_ms=65)

    def on_state(self, source: str) -> None:
        """Called when settings change elsewhere."""


def run_async(fn, done) -> None:
    """Run fn() in a worker thread; call done(result, error) back on the GTK main loop."""
    import threading

    from gi.repository import GLib

    def work():
        try:
            res, err = fn(), None
        except Exception as exc:  # noqa: BLE001 - surfaced to the user by `done`
            res, err = None, exc
        GLib.idle_add(lambda: (done(res, err), GLib.SOURCE_REMOVE)[1])

    threading.Thread(target=work, daemon=True).start()
