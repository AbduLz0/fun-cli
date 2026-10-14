"""Welcome & MOTD: greeting, mood, extras - with a typing live preview."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ...core import content, pack, preview
from .. import anim
from ..common import Page, group, label
from ..widgets import TerminalPreview


class WelcomePage(Page):
    page_id = "welcome"
    title = "Welcome & MOTD"
    subtitle = "Choose how your terminal greets you each time it opens."
    icon = "tes-welcome-symbolic"

    def __init__(self, win):
        super().__init__(win)
        s = self.state.s
        self._loading = True

        self.term = TerminalPreview("Live preview - new terminal", max_height=230, min_height=130)
        self.pin(self.term)

        self.header("Make it yours")

        # ---- greeting text
        g = group("Message", "Use {user}, {host} and {daypart} (morning, afternoon...) in your greeting.")
        self.greeting = Adw.EntryRow(title="Greeting")
        self.greeting.set_text(s["greeting"])
        self.greeting.connect("changed", lambda r: self._set(greeting=r.get_text() or "Welcome back, {user}!"))
        g.add(self.greeting)
        self.add(g)

        # ---- mood grid
        self.add(label("Terminal mood", "tes-section"))
        self.big = label(s["face"], "tes-hero-face", wrap=False)
        self.big_motion = anim.Motion(self.big)
        stage = Gtk.Box(halign=Gtk.Align.CENTER)
        stage.set_size_request(-1, 90)
        stage.append(self.big_motion)
        self.add(stage)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6, min_children_per_line=2,
                           column_spacing=8, row_spacing=8, homogeneous=True)
        self._faces: dict[str, Gtk.ToggleButton] = {}
        first = None
        for name, face in content.FACES:
            b = Gtk.ToggleButton(child=Gtk.Label(label=face), tooltip_text=name)
            b.add_css_class("tes-face-btn")
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._face_toggled, face)
            self._faces[face] = b
            flow.append(b)
        self.add(flow)

        # ---- toggles
        t = group("Show on startup")
        self.sw = {}
        for key, title, sub in [
            ("enabled", "Welcome message", "Turn the whole greeting on or off."),
            ("show_date", "Date and time", "A small timestamp before the greeting."),
            ("show_host", "Computer name and shell", "Handy if you use several machines."),
            ("fastfetch", "System summary (Fastfetch)", "Shows only if Fastfetch is installed."),
            ("greeting_pack", "Rotating tips &amp; greetings", "A fresh line each time. Edit them in AI Companion."),
        ]:
            row = Adw.SwitchRow(title=title, subtitle=sub, active=bool(s[key]))
            row.connect("notify::active", lambda r, _p, k=key: self._set(**{k: r.get_active()}))
            t.add(row)
            self.sw[key] = row
        self.add(t)

        # ---- extra text
        x = group("Extra message", "Optional - up to 5 lines shown under the greeting.")
        self.motd = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10,
                                 left_margin=12, right_margin=12)
        self.motd.get_buffer().set_text(s["custom_motd"])
        self.motd.get_buffer().connect("changed", self._motd_changed)
        frame = Gtk.ScrolledWindow(child=self.motd, min_content_height=84, max_content_height=140,
                                   propagate_natural_height=True)
        frame.add_css_class("card")
        x.add(frame)
        self.add(x)

        self._loading = False
        self._select_face(s["face"])
        self.refresh(animate=False)

    # --------------------------------------------------------------- events
    def _set(self, **kw) -> None:
        if self._loading:
            return
        self.state.update("welcome", **kw)
        self.refresh()

    def _motd_changed(self, buf) -> None:
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)[:1000]
        self._set(custom_motd=text)

    def _face_toggled(self, btn, face) -> None:
        if self._loading or not btn.get_active():
            return
        self.big.set_text(face)
        self.big_motion.pop()
        self._set(face=face)

    def _select_face(self, face: str) -> None:
        self._loading = True
        btn = self._faces.get(face)
        if btn:
            btn.set_active(True)
        self._loading = False
        self.big.set_text(face)

    # --------------------------------------------------------------- preview
    _debounce = 0

    def refresh(self, animate: bool = True) -> None:
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(120 if animate else 1, self._render, animate)

    def _render(self, animate: bool) -> bool:
        self._debounce = 0
        s = self.state.s
        self.term.set_accent(s["accent"])
        self.term.set_lines(preview.welcome_lines(s, pack.preview_pairs(s)), animate=animate)
        return GLib.SOURCE_REMOVE

    def on_shown(self) -> None:
        super().on_shown()
        self.term.set_theme(self.win.current_theme(), animate=False)
        self.big_motion.bob(amplitude=4)
        self.refresh()

    def on_state(self, source: str) -> None:
        if source in ("welcome", ""):
            return
        self._loading = True
        self.greeting.set_text(self.state.s["greeting"])
        for k, row in self.sw.items():
            row.set_active(bool(self.state.s[k]))
        self._loading = False
        self._select_face(self.state.s["face"])
        self.refresh(animate=False)
