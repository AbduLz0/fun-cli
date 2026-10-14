"""Terminal Appearance: themes, colours, font, cursor, transparency - via per-terminal adapters."""
from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from ... import adapters
from ...core import ai, assistant, backups, themes
from ...core.themes import PALETTE_NAMES, Theme
from ..common import Page, combo_row, group, icon_button, label, run_async
from ..widgets import ThemeCard, TerminalPreview, rgba

SHAPES = [("Block", "block"), ("Beam (thin line)", "beam"), ("Underline", "underline")]


def _hex(c: Gdk.RGBA) -> str:
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def _color_button(hex_color: str) -> Gtk.ColorDialogButton:
    b = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
    b.set_rgba(rgba(hex_color))
    return b


def sample_lines(user="you", host="zorin") -> list[list[tuple[str, str]]]:
    prompt = lambda cmd: [(f"{user}@{host}", "p2"), (":", "fg"), ("~/projects", "p4"), ("$ ", "fg"), (cmd, "fg")]
    return [
        prompt("ls --color"),
        [("src  ", "p4"), ("notes.txt  ", "fg"), ("run.sh  ", "p2"), ("backup.tar.gz", "p1")],
        prompt("git status -s"),
        [(" M ", "p3"), ("app.py", "fg")], [("?? ", "p1"), ("new-idea.md", "fg")],
        [("normal ", "dim")] + [("███", f"p{i}") for i in range(8)],
        [("bright ", "dim")] + [("███", f"p{i}") for i in range(8, 16)],
    ]


class AppearancePage(Page):
    page_id = "appearance"
    title = "Terminal Appearance"
    subtitle = "Colours, fonts, cursor and transparency. Preview first, then apply to your terminal."
    icon = "tes-appearance-symbolic"
    show_apply_bar = False

    def __init__(self, win):
        super().__init__(win)
        self._loading = True
        t = self.theme()

        self.term = TerminalPreview("you@zorin: ~/projects", max_height=230, min_height=170)
        self.pin(self.term)
        self.term.set_theme(t, animate=False)
        self.term.set_lines(sample_lines(), animate=False)

        self.header("Look & feel")

        # ---- target terminal
        tg = group("Which terminal?", "Each terminal stores its look differently. We use the right method for each one.")
        names = [a.name for a in self.state.terminals] or ["No supported terminal found"]
        saved = self.state.s.get("terminal_target", "")
        idx = next((i for i, a in enumerate(self.state.terminals) if a.id == saved), 0)
        self.target = combo_row("Apply to", names, idx)
        self.target.set_sensitive(bool(self.state.terminals))
        self.target.connect("notify::selected", self._target_changed)
        tg.add(self.target)
        self.caps = label("", "tes-note")
        self.add(tg)
        self.add(self.caps)

        # ---- presets
        self.add(label("Theme presets", "tes-section"))
        strip = Gtk.Box(spacing=10, margin_bottom=6)
        self._cards: dict[str, ThemeCard] = {}
        first = None
        for name, preset in themes.PRESETS.items():
            c = ThemeCard(preset)
            if first is None:
                first = c
            else:
                c.set_group(first)
            c.connect("toggled", self._preset_toggled, name)
            self._cards[name] = c
            strip.append(c)
        self.add(Gtk.ScrolledWindow(child=strip, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                    hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, propagate_natural_height=True))

        # ---- AI theme
        ig = group("Theme from an idea", "Describe a mood or place and the AI designs a colour theme. Checked for readability before use.")
        self.idea = Adw.EntryRow(title="Describe it, e.g. cozy autumn forest")
        self.idea.connect("entry-activated", lambda *_: self._gen_theme())
        ig.add(self.idea)
        gr = Adw.ActionRow(title="Design it", subtitle="Needs AI features switched on in AI Companion.")
        self.gen_theme_btn = Gtk.Button(label="Generate", valign=Gtk.Align.CENTER)
        self.gen_theme_btn.add_css_class("suggested-action")
        self.gen_theme_btn.connect("clicked", lambda _b: self._gen_theme())
        gr.add_suffix(self.gen_theme_btn)
        ig.add(gr)
        self.idea_status = label("", "tes-note")
        self.add(ig)
        self.add(self.idea_status)

        # ---- colours
        cg = group("Colours")
        self.fg_btn, self.bg_btn, self.cur_btn = _color_button(t.fg), _color_button(t.bg), _color_button(t.cursor)
        for title, btn, key in (("Text", self.fg_btn, "fg"), ("Background", self.bg_btn, "bg"), ("Cursor", self.cur_btn, "cursor")):
            row = Adw.ActionRow(title=title)
            row.add_suffix(btn)
            btn.connect("notify::rgba", lambda b, _p, k=key: self._color(k, b))
            cg.add(row)
        adv = Adw.ExpanderRow(title="Advanced: 16-colour palette", subtitle="Fine-tune every terminal colour.")
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
                        halign=Gtk.Align.CENTER)
        self.pal_btns: list[Gtk.ColorDialogButton] = []
        for i in range(16):
            b = _color_button(t.palette[i])
            b.set_tooltip_text(("Bright " if i >= 8 else "") + PALETTE_NAMES[i % 8].capitalize())
            b.connect("notify::rgba", lambda _b, _p, i=i: self._palette(i))
            grid.attach(b, i % 8, i // 8, 1, 1)
            self.pal_btns.append(b)
        adv.add_row(Gtk.ListBoxRow(child=grid, activatable=False, selectable=False))
        cg.add(adv)
        self.add(cg)

        # ---- font / cursor / transparency
        fg = group("Text &amp; cursor")
        self.font_btn = Gtk.FontDialogButton(dialog=Gtk.FontDialog(), level=Gtk.FontLevel.FAMILY, valign=Gtk.Align.CENTER)
        self.font_btn.set_font_desc(Pango.FontDescription.from_string(f"{t.font} 12"))
        self.font_btn.connect("notify::font-desc", self._font)
        r = Adw.ActionRow(title="Font", subtitle="Monospace fonts work best.")
        r.add_suffix(self.font_btn)
        fg.add(r)
        self.size = Adw.SpinRow(title="Font size", adjustment=Gtk.Adjustment(value=t.font_size, lower=6, upper=32, step_increment=1))
        self.size.connect("notify::value", lambda r, _p: self._set_theme(font_size=r.get_value()))
        fg.add(self.size)
        self.shape = combo_row("Cursor shape", [n for n, _ in SHAPES], [v for _, v in SHAPES].index(t.cursor_shape))
        self.shape.connect("notify::selected", lambda r, _p: self._set_theme(cursor_shape=SHAPES[r.get_selected()][1]))
        fg.add(self.shape)
        tr = Adw.ActionRow(title="Opacity", subtitle="Lower values let your desktop show through.")
        self.opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 30, 100, 1)
        self.opacity.set_value(t.opacity)
        self.opacity.set_draw_value(True)
        self.opacity.set_value_pos(Gtk.PositionType.LEFT)
        self.opacity.set_size_request(230, -1)
        self.opacity.set_valign(Gtk.Align.CENTER)
        self.opacity.connect("value-changed", lambda s: self._set_theme(opacity=int(s.get_value())))
        tr.add_suffix(self.opacity)
        fg.add(tr)
        self.bgrow = Adw.ActionRow(title="Background image")
        self.bg_choose = Gtk.Button(label="Choose...", valign=Gtk.Align.CENTER)
        self.bg_choose.connect("clicked", self._choose_bg)
        self.bg_clear = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Remove image")
        self.bg_clear.add_css_class("flat")
        self.bg_clear.connect("clicked", lambda _b: self._set_theme(bg_image=""))
        self.bgrow.add_suffix(self.bg_clear)
        self.bgrow.add_suffix(self.bg_choose)
        fg.add(self.bgrow)
        self.add(fg)

        # ---- actions
        ag = group("Apply, share &amp; undo")
        self.apply_row = Adw.ActionRow(title="Apply to terminal", subtitle="Writes the theme using that terminal's own method. Backed up first.")
        self.apply_btn = Gtk.Button(label="Apply theme", valign=Gtk.Align.CENTER)
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.add_css_class("pill")
        self.apply_btn.connect("clicked", lambda _b: self._apply())
        self.apply_row.add_suffix(self.apply_btn)
        ag.add(self.apply_row)
        sr = Adw.ActionRow(title="Share a theme", subtitle="Save your look as a small file, or load one a friend sent you.")
        exp = Gtk.Button(label="Export...", valign=Gtk.Align.CENTER)
        imp = Gtk.Button(label="Import...", valign=Gtk.Align.CENTER)
        exp.connect("clicked", self._export)
        imp.connect("clicked", self._import)
        sr.add_suffix(imp)
        sr.add_suffix(exp)
        ag.add(sr)
        rr = Adw.ActionRow(title="Reset terminal to defaults", subtitle="Removes what this app added. Other settings stay as they are.")
        rb = Gtk.Button(label="Reset", valign=Gtk.Align.CENTER)
        rb.add_css_class("destructive-action")
        rb.connect("clicked", self._reset)
        rr.add_suffix(rb)
        ag.add(rr)
        self.add(ag)

        self._loading = False
        self._sync_all(t)
        self._update_caps()

    # ------------------------------------------------------------------ model
    def theme(self) -> Theme:
        return themes.from_dict(self.state.s["theme"], strict=False)

    def adapter(self):
        i = self.target.get_selected()
        return self.state.terminals[i] if self.state.terminals and i < len(self.state.terminals) else None

    def _set_theme(self, **kw) -> None:
        if self._loading:
            return
        t = self.theme()
        if any(k in kw for k in ("fg", "bg", "cursor", "palette")):
            kw.setdefault("name", "Custom")
        t = t.with_(**kw)
        self.state.update("appearance", theme=t.to_dict())
        self.term.set_theme(t)
        self._update_caps()
        self._sync_cards(t)

    def _sync_cards(self, t: Theme) -> None:
        self._loading = True
        match = next((n for n, p in themes.PRESETS.items() if (p.fg, p.bg, p.cursor, p.palette) == (t.fg, t.bg, t.cursor, t.palette)), None)
        for n, c in self._cards.items():
            c.set_active(n == match)
        self._loading = False

    def _sync_all(self, t: Theme) -> None:
        self._loading = True
        for btn, col in ((self.fg_btn, t.fg), (self.bg_btn, t.bg), (self.cur_btn, t.cursor)):
            btn.set_rgba(rgba(col))
        for b, col in zip(self.pal_btns, t.palette):
            b.set_rgba(rgba(col))
        self.opacity.set_value(t.opacity)
        self.size.set_value(t.font_size)
        self.font_btn.set_font_desc(Pango.FontDescription.from_string(f"{t.font} 12"))
        self.shape.set_selected([v for _, v in SHAPES].index(t.cursor_shape))
        self._loading = False
        self._sync_cards(t)

    # ------------------------------------------------------------------ events
    def _preset_toggled(self, card, name) -> None:
        if self._loading or not card.get_active():
            return
        p = themes.PRESETS[name]
        t = self.theme().with_(fg=p.fg, bg=p.bg, cursor=p.cursor, palette=p.palette, name=name)
        self.state.update("appearance", theme=t.to_dict())
        self.term.set_theme(t)
        self._loading = True
        for btn, col in ((self.fg_btn, t.fg), (self.bg_btn, t.bg), (self.cur_btn, t.cursor)):
            btn.set_rgba(rgba(col))
        for b, col in zip(self.pal_btns, t.palette):
            b.set_rgba(rgba(col))
        self._loading = False

    def _color(self, key, btn) -> None:
        self._set_theme(**{key: _hex(btn.get_rgba())})

    def _palette(self, i) -> None:
        if self._loading:
            return
        pal = list(self.theme().palette)
        pal[i] = _hex(self.pal_btns[i].get_rgba())
        self._set_theme(palette=pal)

    def _font(self, btn, _p) -> None:
        fam = btn.get_font_desc().get_family() if btn.get_font_desc() else None
        if fam:
            self._set_theme(font=fam)

    def _target_changed(self, *_) -> None:
        a = self.adapter()
        if a:
            self.state.update("appearance", terminal_target=a.id)
        self._update_caps()

    def _update_caps(self) -> None:
        a = self.adapter()
        if a is None:
            self.caps.set_text("Install GNOME Terminal, Kitty, Alacritty or Konsole to apply themes. You can still design and export one here.")
            self.apply_btn.set_sensitive(False)
            self.bgrow.set_subtitle("Choose a terminal first.")
            self.bg_choose.set_sensitive(False)
            return
        self.apply_btn.set_sensitive(True)
        miss = [adapters.FEATURES[f].lower() for f in a.unsupported()]
        self.caps.set_text(f"{a.name} supports colours, palette, font, cursor and transparency" +
                           (f". Not supported by {a.name}: {', '.join(miss)}." if miss else " and background images."))
        ok = "bg_image" in a.features
        self.bg_choose.set_sensitive(ok)
        self.bg_clear.set_sensitive(ok)
        t = self.theme()
        self.bgrow.set_subtitle((Path(t.bg_image).name if t.bg_image else "PNG recommended.") if ok else f"{a.name} doesn't support background images.")

    # ------------------------------------------------------------------ AI theme
    def _gen_theme(self) -> None:
        idea = self.idea.get_text().strip()
        if not idea:
            self.idea_status.set_text("Type an idea first, for example: neon city at night.")
            return
        st = dict(self.state.s)
        why = assistant.readiness(st, self.state.api_key)
        if why:
            self.idea_status.set_text(why)
            return
        system, user = assistant.theme_prompt(idea)
        base = self.theme()
        self.gen_theme_btn.set_sensitive(False)
        self.idea_status.set_text("Designing your theme...")

        def work():
            raw = ai.chat(st["provider"], st["model"], self.state.api_key, system, user, max_tokens=700, temperature=0.9)
            return assistant.parse_theme(raw, base)

        def done(theme, err):
            self.gen_theme_btn.set_sensitive(True)
            if err:
                self.idea_status.set_text(str(err))
                return
            self.state.update("appearance", theme=theme.to_dict())
            self._sync_all(theme)
            self.term.set_theme(theme)
            self.idea_status.set_text(f"Made \"{theme.name}\". Not happy? Press Generate again for a different take.")

        run_async(work, done)

    # ------------------------------------------------------------------ files
    def _choose_bg(self, _b) -> None:
        dlg = Gtk.FileDialog(title="Choose a background image")
        f = Gtk.FileFilter(name="PNG images")
        f.add_mime_type("image/png")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dlg.set_filters(store)

        def done(d, res):
            try:
                path = d.open_finish(res).get_path()
            except GLib.Error:
                return
            self._set_theme(bg_image=path)

        dlg.open(self.win, None, done)

    def _export(self, _b) -> None:
        dlg = Gtk.FileDialog(title="Export theme", initial_name=f"{self.theme().name.lower().replace(' ', '-')}.tes-theme.json")

        def done(d, res):
            try:
                path = d.save_finish(res).get_path()
                Path(path).write_text(themes.dumps(self.theme()), encoding="utf-8")
                self.win.toast("Theme exported.")
            except GLib.Error:
                return
            except OSError as exc:
                self.win.alert("Couldn't save the file", str(exc))

        dlg.save(self.win, None, done)

    def _import(self, _b) -> None:
        dlg = Gtk.FileDialog(title="Import theme")

        def done(d, res):
            try:
                path = d.open_finish(res).get_path()
            except GLib.Error:
                return
            try:
                if Path(path).stat().st_size > 64_000:
                    raise themes.ThemeError("That file is too large to be a theme.")
                t = themes.loads(Path(path).read_text(encoding="utf-8"))
            except (themes.ThemeError, OSError, UnicodeDecodeError) as exc:
                self.win.alert("That isn't a usable theme", str(exc))
                return
            self.state.update("appearance", theme=t.to_dict())
            self._sync_all(t)
            self.term.set_theme(t)
            self._update_caps()
            self.win.toast(f"Imported \"{t.name}\".")

        dlg.open(self.win, None, done)

    # ------------------------------------------------------------------ apply / reset
    def _apply(self) -> None:
        a = self.adapter()
        if a is None:
            return
        t = self.theme()
        self.apply_btn.set_sensitive(False)
        run_async(lambda: a.apply(t), lambda res, err: self._applied(a, res, err))

    def _applied(self, a, res, err) -> None:
        self.apply_btn.set_sensitive(True)
        if err or not res.ok:
            self.win.alert(f"Couldn't apply to {a.name}", str(err) if err else res.message)
            return
        body = []
        if res.skipped:
            body.append("Skipped:\n" + "\n".join(f"- {r}" for r in res.skipped.values()))
        body += res.notes
        self.win.celebrate(self.apply_btn)
        self.win.toast(res.message, undo_backup=res.backup)
        if body:
            self.caps.set_text("\n".join(body))

    def _reset(self, _b) -> None:
        a = self.adapter()
        if a is None:
            return

        def go():
            run_async(a.reset, lambda res, err: self.win.toast(res.message, undo_backup=res.backup) if res else self.win.alert("Reset failed", str(err)))

        self.win.confirm(f"Reset {a.name}?", "This removes the look added by Terminal Experience Studio. A backup is made first, so you can undo it.",
                         "Reset", go, destructive=True)

    def on_shown(self) -> None:
        super().on_shown()
        self.term.set_accent(self.state.s["accent"])
        self.term.set_lines(sample_lines(), animate=True)

    def on_state(self, source: str) -> None:
        if source == "appearance":
            return
        self.term.set_accent(self.state.s["accent"])
