"""ASCII Art Studio: built-in gallery + image conversion with live controls."""
from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from ...core import asciiart, content
from ..common import Page, combo_row, group, label
from ..widgets import TerminalPreview

MAX_BYTES = 30 * 1024 * 1024


class AsciiPage(Page):
    page_id = "ascii"
    title = "ASCII Art Studio"
    subtitle = "Pick a piece from the gallery, or turn any picture into text art for your startup screen."
    icon = "tes-art-symbolic"

    def __init__(self, win):
        super().__init__(win)
        s = self.state.s
        self._loading = True
        self._pixbuf: GdkPixbuf.Pixbuf | None = None
        self._debounce = 0

        self.term = TerminalPreview("startup art", max_height=300, min_height=150)
        self.pin(self.term)
        self.header("Draw something")

        # ---- gallery
        self.add(label("Gallery", "tes-section"))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6, min_children_per_line=2,
                           column_spacing=8, row_spacing=8, homogeneous=True)
        for name, art in content.ART_GALLERY.items():
            b = Gtk.Button(label=name)
            b.add_css_class("tes-face-btn")
            b.connect("clicked", lambda _b, n=name, a=art: self._use_text(a, n))
            flow.append(b)
        self.add(flow)

        # ---- image
        ig = group("From a picture", "PNG, JPEG, WebP, GIF and more. Photos with a plain background work best.")
        r = Adw.ActionRow(title="Picture", subtitle="Nothing is uploaded - conversion happens on your computer.")
        self.pick = Gtk.Button(label="Choose picture...", valign=Gtk.Align.CENTER)
        self.pick.add_css_class("suggested-action")
        self.pick.connect("clicked", self._choose)
        r.add_suffix(self.pick)
        ig.add(r)
        self.charset = combo_row("Character style", list(asciiart.CHARSETS), 0)
        self.width = Adw.SpinRow(title="Width (characters)", adjustment=Gtk.Adjustment(value=48, lower=16, upper=120, step_increment=2))
        self.contrast = self._scale_row("Contrast", 0.5, 2.5, 1.0, 0.05)
        self.bright = self._scale_row("Brightness", -0.5, 0.5, 0.0, 0.05)
        self.invert = Adw.SwitchRow(title="Invert", subtitle="Swap light and dark - try this on a light background image.")
        for w in (self.charset, self.width, self.invert):
            ig.add(w)
        ig.add(self.contrast[0])
        ig.add(self.bright[0])
        self.charset.connect("notify::selected", lambda *_: self._reconvert())
        self.width.connect("notify::value", lambda *_: self._reconvert())
        self.invert.connect("notify::active", lambda *_: self._reconvert())
        self.image_group = ig
        self.add(ig)
        self._set_image_controls(False)

        # ---- use it
        ug = group("Use it")
        self.use = Adw.SwitchRow(title="Show this art when a terminal opens", subtitle="Appears above your greeting. Apply to Bash to save it.",
                                 active=s["art_enabled"])
        self.use.connect("notify::active", self._use_toggled)
        ug.add(self.use)
        ar = Adw.ActionRow(title="Copy or save")
        cp = Gtk.Button(label="Copy", valign=Gtk.Align.CENTER)
        sv = Gtk.Button(label="Save as .txt", valign=Gtk.Align.CENTER)
        cl = Gtk.Button(label="Clear", valign=Gtk.Align.CENTER)
        cl.add_css_class("destructive-action")
        cp.connect("clicked", self._copy)
        sv.connect("clicked", self._save)
        cl.connect("clicked", lambda _b: self._set_art("", ""))
        for b in (cl, sv, cp):
            ar.add_suffix(b)
        ug.add(ar)
        self.add(ug)

        self._loading = False
        self._render(animate=False)

    # ------------------------------------------------------------------ helpers
    def _scale_row(self, title, lo, hi, val, step):
        row = Adw.ActionRow(title=title)
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        sc.set_value(val)
        sc.set_size_request(230, -1)
        sc.set_valign(Gtk.Align.CENTER)
        sc.set_draw_value(False)
        sc.connect("value-changed", lambda *_: self._reconvert())
        row.add_suffix(sc)
        return row, sc

    def _set_image_controls(self, on: bool) -> None:
        for w in (self.charset, self.width, self.invert, self.contrast[0], self.bright[0]):
            w.set_sensitive(on)

    def _set_art(self, text: str, name: str) -> None:
        text = content.clean_art(text)
        self.state.update("ascii", art_text=text, art_name=name, art_enabled=bool(text))  # choosing art switches it on
        self._loading = True
        self.use.set_active(self.state.s["art_enabled"])
        self._loading = False
        self._render()

    def _use_text(self, art: str, name: str) -> None:
        self._pixbuf = None
        self._set_image_controls(False)
        self._set_art(art, name)

    def _use_toggled(self, row, _p) -> None:
        if not self._loading:
            self.state.update("ascii", art_enabled=row.get_active())
            self._render()

    # ------------------------------------------------------------------ conversion
    def _choose(self, _b) -> None:
        dlg = Gtk.FileDialog(title="Choose a picture")
        flt = Gtk.FileFilter(name="Pictures")
        flt.add_pixbuf_formats()
        from gi.repository import Gio
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)

        def done(d, res):
            try:
                path = d.open_finish(res).get_path()
            except GLib.Error:
                return
            self._load(path)

        dlg.open(self.win, None, done)

    def _load(self, path: str) -> None:
        try:
            if Path(path).stat().st_size > MAX_BYTES:
                raise ValueError("That picture is larger than 30 MB. Try a smaller one.")
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
        except (GLib.Error, OSError, ValueError) as exc:
            self.win.alert("Couldn't open that picture", getattr(exc, "message", None) or str(exc))
            return
        self._pixbuf = pb
        self._set_image_controls(True)
        self._reconvert(now=True)

    def _reconvert(self, now: bool = False) -> None:
        if self._loading or self._pixbuf is None:
            return
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(1 if now else 140, self._convert)

    def _convert(self) -> bool:
        self._debounce = 0
        pb = self._pixbuf
        if pb is None:
            return GLib.SOURCE_REMOVE
        cols, rows = asciiart.target_size(pb.get_width(), pb.get_height(), int(self.width.get_value()))
        small = pb.scale_simple(cols, rows, GdkPixbuf.InterpType.BILINEAR)
        text = asciiart.pixels_to_ascii(
            small.get_pixels(), small.get_width(), small.get_height(), small.get_rowstride(), small.get_n_channels(),
            small.get_has_alpha(), list(asciiart.CHARSETS)[self.charset.get_selected()],
            self.contrast[1].get_value(), self.bright[1].get_value(), self.invert.get_active())
        self._set_art(text, "From picture")
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ output
    def _render(self, animate: bool = True) -> None:
        s = self.state.s
        self.term.set_accent(s["accent"])
        art = s["art_text"]
        if art:
            lines = [[(l, "accent")] for l in art.splitlines()]
            lines += [[], [("(art shown above your greeting)" if s["art_enabled"] else "(not shown at startup yet - switch it on below)", "dim")]]
        else:
            lines = [[("No art chosen yet.", "dim")], [("Pick something from the gallery or choose a picture.", "dim")]]
        self.term.set_lines(lines, animate=animate and len(art) < 700)

    def _copy(self, _b) -> None:
        text = self.state.s["art_text"]
        if text:
            self.get_clipboard().set(text)
            self.win.toast("Art copied.")

    def _save(self, _b) -> None:
        text = self.state.s["art_text"]
        if not text:
            return
        dlg = Gtk.FileDialog(title="Save art", initial_name="terminal-art.txt")

        def done(d, res):
            try:
                Path(d.save_finish(res).get_path()).write_text(text + "\n", encoding="utf-8")
                self.win.toast("Saved.")
            except GLib.Error:
                return
            except OSError as exc:
                self.win.alert("Couldn't save the file", str(exc))

        dlg.save(self.win, None, done)

    def on_shown(self) -> None:
        super().on_shown()
        self.term.set_theme(self.win.current_theme(), animate=False)
        self._render()

    def on_state(self, source: str) -> None:
        if source != "ascii":
            self._loading = True
            self.use.set_active(self.state.s["art_enabled"])
            self._loading = False
            self._render(animate=False)
