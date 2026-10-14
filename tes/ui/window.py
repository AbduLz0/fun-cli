"""Main window: sidebar navigation, animated page stack, apply bar, toasts and dialogs."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from ..core import backups, bashconfig, themes
from ..core.paths import APP_NAME, VERSION
from ..core.shellblock import BlockError
from . import anim
from .common import Page, label
from .pages.appearance import AppearancePage
from .pages.ascii import AsciiPage
from .pages.companion import CompanionPage
from .pages.dashboard import DashboardPage
from .pages.prompt import PromptPage
from .pages.settings import SettingsPage
from .pages.welcome import WelcomePage
from .state import AppState

PAGES = [DashboardPage, WelcomePage, AppearancePage, PromptPage, AsciiPage, CompanionPage, SettingsPage]

STATUS_TEXT = {
    "none": "Nothing applied to Bash yet",
    "synced": "Applied - up to date",
    "pending": "Changes not applied yet",
}


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, state: AppState):
        super().__init__(application=app, title=APP_NAME, default_width=1160, default_height=800)
        self.add_css_class("tes-window")
        self.set_size_request(360, 480)
        self._last_status = None
        self.state = state
        self.pages: dict[str, Page] = {}
        self._status_id = 0
        self._current: str | None = None

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        self.split = Adw.NavigationSplitView(min_sidebar_width=230, max_sidebar_width=270, sidebar_width_fraction=0.24)
        self.toasts.set_child(self.split)

        self.split.set_sidebar(self._build_sidebar())
        self.split.set_content(self._build_content())

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 780sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        self._install_actions()
        state.subscribe(self._on_state)
        self.apply_scheme()
        self.connect("close-request", self._on_close)
        self.nav.select_row(self.nav.get_row_at_index(0))
        GLib.idle_add(self._first_run)

    # ------------------------------------------------------------------ construction
    def _build_sidebar(self) -> Adw.NavigationPage:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("tes-sidebar")
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        brand.add_css_class("tes-brand")
        self.brand_face = label("(•‿•)", "tes-brand-face", wrap=False)
        self.brand_motion = anim.Motion(self.brand_face)
        holder = Gtk.Box(halign=Gtk.Align.START)
        holder.append(self.brand_motion)
        brand.append(holder)
        brand.append(label("Terminal Experience", "tes-brand-name", wrap=False))
        brand.append(label("Studio", "tes-brand-name", wrap=False))
        brand.append(label("Bring your command line to life", "tes-brand-sub"))
        box.append(brand)

        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav.add_css_class("navigation-sidebar")
        self.nav.add_css_class("tes-nav")
        self.nav.set_margin_top(10)
        self.nav_ids: list[str] = []
        for cls in PAGES:
            row = Gtk.ListBoxRow()
            h = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=10, margin_end=10)
            h.append(Gtk.Image.new_from_icon_name(cls.icon))
            h.append(Gtk.Label(label=cls.title.replace("Settings, Backups & Recovery", "Backups & Settings"), xalign=0))
            row.set_child(h)
            self.nav.append(row)
            self.nav_ids.append(cls.page_id)
        self.nav.connect("row-selected", self._row_selected)
        box.append(Gtk.ScrolledWindow(child=self.nav, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        box.append(label(f"v{VERSION}", "tes-note", margin_start=18, margin_bottom=14))
        page = Adw.NavigationPage(title=APP_NAME, child=box)
        return page

    def _build_content(self) -> Adw.NavigationPage:
        tv = Adw.ToolbarView()
        self.header = Adw.HeaderBar()
        self.title_label = Adw.WindowTitle(title="Dashboard", subtitle="")
        self.header.set_title_widget(self.title_label)
        tv.add_top_bar(self.header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=220, vexpand=True, hexpand=True)
        for cls in PAGES:
            page = cls(self)
            self.pages[cls.page_id] = page
            self.stack.add_named(page, cls.page_id)
        tv.set_content(self.stack)

        # apply bar
        self.bar = Gtk.Box(spacing=12)
        self.bar.add_css_class("tes-actionbar")
        self.dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self.dot.add_css_class("tes-dot")
        self.bar.append(self.dot)
        self.status_label = label("", "tes-note", wrap=False)
        self.status_label.set_hexpand(True)
        self.bar.append(self.status_label)
        self.undo_btn = Gtk.Button(label="Undo last apply", valign=Gtk.Align.CENTER)
        self.undo_btn.add_css_class("flat")
        self.undo_btn.connect("clicked", lambda _b: self._undo(self.state.last_backup))
        self.undo_btn.set_visible(False)
        self.bar.append(self.undo_btn)
        self.apply_btn = Gtk.Button(label="Apply to Bash", valign=Gtk.Align.CENTER)
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.add_css_class("tes-apply")
        self.apply_btn.connect("clicked", lambda _b: self.apply_bash())
        self.bar.append(self.apply_btn)
        tv.add_bottom_bar(self.bar)

        self.content_page = Adw.NavigationPage(title="Content", child=tv)
        return self.content_page

    def _install_actions(self) -> None:
        act = Gio.SimpleAction.new("goto", GLib.VariantType.new("s"))
        act.connect("activate", lambda _a, v: self.navigate(v.get_string()))
        self.add_action(act)
        app = self.get_application()
        for i, cls in enumerate(PAGES, start=1):
            app.set_accels_for_action(f"win.goto('{cls.page_id}')", [f"<Primary>{i}"])

    # ------------------------------------------------------------------ navigation
    def _row_selected(self, _lb, row) -> None:
        if row is None:
            return
        pid = self.nav_ids[row.get_index()]
        self._show(pid)

    def navigate(self, pid: str) -> None:
        if pid in self.nav_ids:
            self.nav.select_row(self.nav.get_row_at_index(self.nav_ids.index(pid)))
            self.split.set_show_content(True)

    def _show(self, pid: str) -> None:
        page = self.pages[pid]
        self.stack.set_visible_child_name(pid)
        self.title_label.set_title(page.title)
        self.title_label.set_subtitle("")
        self.bar.set_visible(page.show_apply_bar)
        self._current = pid
        self.split.set_show_content(True)
        GLib.idle_add(lambda: (page.on_shown(), GLib.SOURCE_REMOVE)[1])
        self._schedule_status()

    # ------------------------------------------------------------------ state
    def _on_state(self, source: str) -> None:
        for page in self.pages.values():
            page.on_state(source)
        self.brand_face.set_text(self.state.s["face"])
        self._schedule_status()

    def current_theme(self) -> themes.Theme:
        return themes.from_dict(self.state.s["theme"], strict=False)

    def _schedule_status(self) -> None:
        if self._status_id:
            GLib.source_remove(self._status_id)
        self._status_id = GLib.timeout_add(250, self.refresh_status)

    def refresh_status(self) -> bool:
        self._status_id = 0
        status = self.state.sync_status()
        for c in ("synced", "pending"):
            self.dot.remove_css_class(c)
        if status in ("synced", "pending"):
            self.dot.add_css_class(status)
        self.status_label.set_text(STATUS_TEXT[status])
        self.apply_btn.set_sensitive(status != "synced")
        self.apply_btn.set_label("Apply to Bash" if status != "pending" else "Apply changes")
        if status == "pending" and self._last_status != "pending" and anim.motion_ok(self):
            anim.flash_class(self.apply_btn, "glow", 1100)
        self._last_status = status
        dash = self.pages.get("dashboard")
        if dash:
            dash.refresh()
        return GLib.SOURCE_REMOVE

    def after_change(self) -> None:
        self.state.reload()
        self.apply_accent()
        self.refresh_status()

    # ------------------------------------------------------------------ theming
    def apply_scheme(self) -> None:
        sm = Adw.StyleManager.get_default()
        sm.set_color_scheme({"dark": Adw.ColorScheme.FORCE_DARK, "light": Adw.ColorScheme.FORCE_LIGHT,
                             "system": Adw.ColorScheme.DEFAULT}[self.state.s["color_scheme"]])
        anim.set_reduce_motion(self.state.s["reduce_motion"])

    def apply_accent(self) -> None:
        self.get_application().set_accent(self.state.s["accent"])

    # ------------------------------------------------------------------ feedback
    def toast(self, text: str, undo_backup=None) -> None:
        t = Adw.Toast(title=text, timeout=9 if undo_backup else 4)
        if undo_backup:
            t.set_button_label("Undo")
            t.connect("button-clicked", lambda _t: self._undo(undo_backup))
        self.toasts.add_toast(t)

    def alert(self, heading: str, body: str = "") -> None:
        d = Adw.AlertDialog(heading=heading, body=body)
        d.add_response("ok", "OK")
        d.set_default_response("ok")
        d.present(self)

    def confirm(self, heading: str, body: str, action: str, callback, destructive: bool = False) -> None:
        d = Adw.AlertDialog(heading=heading, body=body)
        d.add_response("cancel", "Cancel")
        d.add_response("go", action)
        d.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("cancel")
        d.set_close_response("cancel")
        d.connect("response", lambda _d, r: callback() if r == "go" else None)
        d.present(self)

    def celebrate(self, widget: Gtk.Widget) -> None:
        if anim.motion_ok(self):
            anim.flash_class(widget, "tes-pulse", 900)

    # ------------------------------------------------------------------ apply / undo
    def apply_bash(self) -> None:
        s = dict(self.state.s)
        try:
            bashconfig.render_bashrc(bashconfig_read(), s)  # validate markers before asking
        except BlockError as exc:
            self.alert("Your .bashrc needs a quick fix first", str(exc))
            return
        items = "\n".join(f"- {line}" for line in bashconfig.describe(s))
        self.confirm("Apply to Bash?", items, "Apply", self._do_apply)

    def _do_apply(self) -> None:
        self.state.flush()  # the `tes` command reads settings.json, so make sure it is current
        try:
            rep = bashconfig.apply(self.state.s)
        except Exception as exc:  # noqa: BLE001
            self.alert("Nothing was changed", str(exc))
            return
        self.state.last_backup = rep.backup
        self.undo_btn.set_visible(True)
        self.celebrate(self.apply_btn)
        msg = "Applied! Open a new terminal to see it."
        if rep.warnings:
            msg += " " + rep.warnings[0]
        self.toast(msg, undo_backup=rep.backup)
        self.refresh_status()
        self.pages["settings"].refresh()

    def _undo(self, backup_path) -> None:
        entry = backups.entry_for(backup_path) if backup_path else None
        if entry is None:
            return
        try:
            msg = backups.restore(entry)
        except Exception as exc:  # noqa: BLE001
            self.alert("Couldn't undo", str(exc))
            return
        self.undo_btn.set_visible(False)
        self.toast("Undone. " + msg)
        self.refresh_status()
        self.pages["settings"].refresh()

    # ------------------------------------------------------------------ lifecycle
    def _first_run(self) -> bool:
        if not self.state.s.get("onboarded"):
            self.toast("Welcome! Nothing changes on your computer until you press Apply.")
            self.state.update("app", onboarded=True)
        return GLib.SOURCE_REMOVE

    def _on_close(self, *_) -> bool:
        self.state.flush()
        return False


def bashconfig_read() -> str:
    from ..core.fsutil import read_text
    from ..core.paths import bashrc
    return read_text(bashrc())
