"""Dashboard: a living hero, status chips and quick-action tiles."""
from __future__ import annotations

import os
import shutil
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

from ...core import content, pack, preview
from .. import anim
from ..common import Page, label
from ..widgets import Rain, TerminalPreview

TILES = [
    ("welcome", "tes-welcome-symbolic", "Welcome message", "Pick a mood and say hello every time a terminal opens."),
    ("appearance", "tes-appearance-symbolic", "Colours & fonts", "Themes, fonts, cursor and transparency for your terminal."),
    ("prompt", "tes-prompt-symbolic", "Prompt designer", "Make the line you type on clear, useful and pretty."),
    ("ascii", "tes-art-symbolic", "ASCII art studio", "Turn any picture into art for your startup screen."),
    ("companion", "tes-companion-symbolic", "AI companion", "Optional personality, tips and a command explainer."),
    ("settings", "tes-backup-symbolic", "Backups & recovery", "Undo anything, restore backups, or remove it all."),
]


class DashboardPage(Page):
    page_id = "dashboard"
    title = "Dashboard"
    subtitle = ""
    icon = "tes-dashboard-symbolic"

    def __init__(self, win):
        super().__init__(win)
        self._face_i = 0
        self._timer = 0
        self._build()
        self.connect("map", lambda *_: self._start())
        self.connect("unmap", lambda *_: self._stop())

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        user = os.environ.get("USER", "friend")
        part = preview.daypart(datetime.now().hour)

        # --- hero
        overlay = Gtk.Overlay()
        overlay.add_css_class("tes-hero")
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.set_size_request(-1, 170)
        self.rain = Rain(self.state.s["accent"])
        self.rain.set_hexpand(True)
        self.rain.set_vexpand(True)
        overlay.set_child(self.rain)
        row = Gtk.Box(spacing=26, margin_top=26, margin_bottom=26, margin_start=28, margin_end=28)
        self.face = label(self.state.s["face"], "tes-hero-face", wrap=False)
        self.face_motion = anim.Motion(self.face)
        face_holder = Gtk.Box(valign=Gtk.Align.CENTER)
        face_holder.set_size_request(150, -1)
        face_holder.append(self.face_motion)
        row.append(face_holder)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, hexpand=True)
        text.append(label(f"Good {part}, {user}", "tes-hero-title"))
        self.hero_sub = label("", "tes-hero-sub")
        text.append(self.hero_sub)
        row.append(text)
        overlay.add_overlay(row)
        overlay.set_measure_overlay(row, True)
        self.hero_motion = anim.Motion(overlay)
        self.body.append(self.hero_motion)
        self._motions.append(self.hero_motion)

        # --- status chips
        self.chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8,
                                 column_spacing=8, row_spacing=8, homogeneous=False)
        self.add(self.chips)

        # --- live mini preview
        self.mini = TerminalPreview("what your terminal says today", max_height=190, min_height=90)
        self.add(self.mini)

        # --- tiles
        self.add(label("Jump in", "tes-section"))
        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=3,
                           column_spacing=14, row_spacing=14, homogeneous=True)
        for pid, icon, title, desc in TILES:
            btn = Gtk.Button()
            btn.add_css_class("tes-tile")
            btn.add_css_class("flat")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            img = Gtk.Image.new_from_icon_name(icon)
            img.set_pixel_size(26)
            img.set_halign(Gtk.Align.START)
            img.add_css_class("tes-tile-icon")
            box.append(img)
            box.append(label(title, "tes-tile-title"))
            box.append(label(desc, "tes-tile-desc", max_width_chars=24))
            btn.set_child(box)
            btn.connect("clicked", lambda _b, p=pid: self.win.navigate(p))
            grid.append(btn)
        self.add(grid)
        self.refresh()

    # ------------------------------------------------------------------ data
    def _chip(self, text: str, kind: str) -> Gtk.Label:
        c = label(text, "tes-chip", kind, wrap=False)
        return c

    def refresh(self) -> None:
        s = self.state.s
        status = self.state.sync_status()
        self.hero_sub.set_text({
            "synced": "Your terminal greeting is live. Open a new terminal to see it.",
            "pending": "You have changes that haven't been applied to your terminal yet.",
            "none": "Let's make your terminal feel like yours. Everything is previewed before it's applied.",
        }[status])
        while (c := self.chips.get_first_child()):
            self.chips.remove(c)
        term = ", ".join(t.name for t in self.state.terminals)
        chips = [
            (f"Bash greeting: {'live' if status == 'synced' else 'not applied' if status == 'none' else 'changes pending'}",
             "ok" if status == "synced" else "warn" if status == "pending" else "off"),
            (f"Terminal: {term}" if term else "Terminal: none detected", "ok" if term else "off"),
            ("Starship installed" if shutil.which("starship") else "Starship not installed", "ok" if shutil.which("starship") else "off"),
            ("Fastfetch installed" if shutil.which("fastfetch") else "Fastfetch not installed", "ok" if shutil.which("fastfetch") else "off"),
            ("AI companion on" if s.get("ai_enabled") else "AI companion off (optional)", "ok" if s.get("ai_enabled") else "off"),
        ]
        if s.get("roast_mistakes"):
            chips.append((f"Roasts: {s.get('roast_level', 'Spicy')}", "warn"))
        for text, kind in chips:
            self.chips.append(self._chip(text, kind))
        self.mini.set_accent(s["accent"])
        self.rain.set_accent(s["accent"])
        self.face.set_text(s["face"])
        self.mini.set_lines(preview.welcome_lines(s, pack.preview_pairs(s)), animate=False)

    def on_state(self, source: str) -> None:
        self.refresh()

    def on_shown(self) -> None:
        super().on_shown()
        self.mini.set_theme(self.win.current_theme(), animate=False)
        self.mini.set_lines(preview.welcome_lines(self.state.s, pack.preview_pairs(self.state.s)), animate=True)
        self.face_motion.bob()

    # ------------------------------------------------------------------ idle personality
    def _start(self) -> None:
        if not self._timer and anim.motion_ok(self):
            self._timer = GLib.timeout_add(3800, self._idle)

    def _stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _idle(self) -> bool:
        """Blink, and every few blinks try on a different mood."""
        base = self.state.s["face"]
        self.face.set_text(content.BLINK_FACE)
        GLib.timeout_add(170, lambda: (self.face.set_text(base), GLib.SOURCE_REMOVE)[1])
        return GLib.SOURCE_CONTINUE
