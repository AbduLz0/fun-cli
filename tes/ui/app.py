"""Adw.Application: loads styling, owns the live accent colour, creates the window."""
from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from ..core.paths import APP_ID, APP_NAME
from ..core.themes import luminance
from .state import AppState
from .window import MainWindow

HERE = Path(__file__).resolve().parent


class StudioApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.state: AppState | None = None
        self._accent_provider = Gtk.CssProvider()
        self.connect("startup", self._startup)
        self.connect("activate", self._activate)

    def _startup(self, _app) -> None:
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        css = Gtk.CssProvider()
        css.load_from_path(str(HERE / "style.css"))
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.StyleContext.add_provider_for_display(display, self._accent_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        # Find the icon when running from a source checkout (installed copies use the system icon path).
        theme = Gtk.IconTheme.get_for_display(display)
        icons = HERE.parents[1] / "data" / "icons"  # source checkout; installs use ~/.local/share/icons
        if icons.is_dir():
            theme.add_search_path(str(icons))
        Gtk.Window.set_default_icon_name(APP_ID)
        self.state = AppState()
        self.set_accent(self.state.s["accent"])

    def set_accent(self, hex_color: str) -> None:
        fg = "#0b1410" if luminance(hex_color) > 0.35 else "#ffffff"
        self._accent_provider.load_from_string(
            f"@define-color accent_bg_color {hex_color};\n"
            f"@define-color accent_color {hex_color};\n"
            f"@define-color accent_fg_color {fg};\n")

    def _activate(self, _app) -> None:
        win = self.props.active_window or MainWindow(self, self.state)
        win.present()


def main(argv: list[str] | None = None) -> int:
    Adw.init()
    return StudioApp().run(argv if argv is not None else sys.argv)
