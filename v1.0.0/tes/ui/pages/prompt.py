"""Prompt Designer: presets with a live preview. Applied together with the welcome message."""
from __future__ import annotations

import os
import shutil

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ...core import prompts
from ..common import Page, group, label
from ..widgets import TerminalPreview, rgba

ACCENTS = [("Mint", "#7bd88f"), ("Sky", "#6ea8fe"), ("Violet", "#b794f6"), ("Amber", "#f4b942"),
           ("Coral", "#ff7a7a"), ("Aqua", "#4fd1c5"), ("Pink", "#f78fb3")]


class PromptPage(Page):
    page_id = "prompt"
    title = "Prompt Designer"
    subtitle = "The prompt is the line you type on. Make it clear, useful and a little bit beautiful."
    icon = "tes-prompt-symbolic"

    def __init__(self, win):
        super().__init__(win)
        s = self.state.s
        self._loading = True
        self.term = TerminalPreview("you@zorin: ~/projects/demo", max_height=240, min_height=190)
        self.pin(self.term)
        self.header("Your prompt")

        # ---- presets
        pg = group("Style")
        self.checks: dict[str, Gtk.CheckButton] = {}
        lead = None
        for p in prompts.PRESETS:
            row = Adw.ActionRow(title=p.name, subtitle=p.blurb, activatable=True)
            row.add_css_class("tes-preset-row")
            chk = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if lead is None:
                lead = chk
            else:
                chk.set_group(lead)
            chk.connect("toggled", self._chosen, p.id)
            row.add_prefix(chk)
            row.set_activatable_widget(chk)
            self.checks[p.id] = chk
            pg.add(row)
        self.add(pg)

        # ---- starship status
        self.star = label("", "tes-callout", "warn")
        self.add(self.star)

        # ---- options
        og = group("Details")
        self.git = Adw.SwitchRow(title="Show Git branch", subtitle="Appears when you're inside a Git project.", active=s["prompt_git"])
        self.clock = Adw.SwitchRow(title="Show the time", subtitle="A small clock on the prompt.", active=s["prompt_time"])
        self.git.connect("notify::active", lambda r, _p: self._opt(prompt_git=r.get_active()))
        self.clock.connect("notify::active", lambda r, _p: self._opt(prompt_time=r.get_active()))
        og.add(self.git)
        og.add(self.clock)
        self.add(og)

        # ---- accent
        ag = group("Accent colour", "Used for your folder name, the greeting face and the app itself.")
        row = Adw.ActionRow(title="Accent")
        box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.dots: dict[str, Gtk.ToggleButton] = {}
        first = None
        for name, hexv in ACCENTS:
            b = Gtk.ToggleButton(tooltip_text=name)
            b.add_css_class("tes-accent-dot")
            b.add_css_class("flat")
            prov = Gtk.CssProvider()
            prov.load_from_string(f"button {{ background: {hexv}; }}")
            b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._accent, hexv)
            self.dots[hexv] = b
            box.append(b)
        row.add_suffix(box)
        ag.add(row)
        self.add(ag)

        self.add(label("Your original prompt is never lost: pick \"Keep my current prompt\" or use Backups & Recovery any time.", "tes-note"))

        self._loading = False
        self._sync()

    # ------------------------------------------------------------------ events
    def _chosen(self, chk, pid) -> None:
        if self._loading or not chk.get_active():
            return
        self.state.update("prompt", prompt_preset=pid)
        self._render()

    def _opt(self, **kw) -> None:
        if not self._loading:
            self.state.update("prompt", **kw)
            self._render()

    def _accent(self, btn, hexv) -> None:
        if self._loading or not btn.get_active():
            return
        self.state.update("prompt", accent=hexv)
        self.win.apply_accent()
        self._render()

    # ------------------------------------------------------------------ view
    def _sync(self) -> None:
        s = self.state.s
        self._loading = True
        self.checks.get(s["prompt_preset"], self.checks["keep"]).set_active(True)
        self.git.set_active(s["prompt_git"])
        self.clock.set_active(s["prompt_time"])
        if s["accent"] in self.dots:
            self.dots[s["accent"]].set_active(True)
        else:
            for d in self.dots.values():
                d.set_active(False)
        self._loading = False
        self._render()

    def _render(self) -> None:
        s = self.state.s
        self.term.set_accent(s["accent"])
        self.term.set_lines(prompts.preview_lines(s, os.environ.get("USER", "you"), os.uname().nodename.split(".")[0]), animate=True)
        starship = prompts.get(s["prompt_preset"]).engine == "starship"
        have = bool(shutil.which("starship"))
        self.star.set_visible(starship and not have)
        if starship and not have:
            self.star.set_text("Starship isn't installed on this computer yet. You can apply this style now - it switches on automatically once "
                               "Starship is installed (see starship.rs). Until then your normal prompt is used.")

    def on_shown(self) -> None:
        super().on_shown()
        self.term.set_theme(self.win.current_theme(), animate=False)
        self._sync()

    def on_state(self, source: str) -> None:
        if source != "prompt":
            self._sync()
