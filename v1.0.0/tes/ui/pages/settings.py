"""Settings, Backups & Recovery."""
from __future__ import annotations

import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from ...core import backups, bashconfig, paths, settings
from ...core.paths import VERSION
from ..common import Page, combo_row, group, label

SCHEMES = [("Dark", "dark"), ("Light", "light"), ("Match my system", "system")]

SAFETY = [
    ("Backup first", "Every change makes a timestamped backup, so you can always go back."),
    ("Only our section", "We edit only the marked blocks in ~/.bashrc. Everything else is left exactly as it was."),
    ("No administrator access", "Nothing here needs sudo. It all lives in your own home folder."),
    ("Your key stays private", "API keys are never saved in settings or shell files."),
    ("Honest about limits", "If a terminal can't do something, we tell you instead of pretending."),
]


class SettingsPage(Page):
    page_id = "settings"
    title = "Settings, Backups & Recovery"
    subtitle = "Undo anything, restore an older version, or remove everything this app added."
    icon = "tes-backup-symbolic"
    show_apply_bar = False

    def __init__(self, win):
        super().__init__(win)
        s = self.state.s
        self._loading = True
        self.header("Safety net")

        # ---- backups
        self.bk_group = group("Backups", "Newest first. Restoring first saves your current version too, so even a restore can be undone.")
        self.add(self.bk_group)
        self._bk_rows: list[Adw.ActionRow] = []

        # ---- recovery
        rg = group("Recovery")
        r1 = Adw.ActionRow(title="Back up my Bash configuration now", subtitle="A manual snapshot of ~/.bashrc.")
        b1 = Gtk.Button(label="Back up", valign=Gtk.Align.CENTER)
        b1.connect("clicked", self._manual_backup)
        r1.add_suffix(b1)
        rg.add(r1)
        r2 = Adw.ActionRow(title="Remove Terminal Experience Studio from my shell", subtitle="Takes out only what this app added to ~/.bashrc.")
        b2 = Gtk.Button(label="Remove", valign=Gtk.Align.CENTER)
        b2.add_css_class("destructive-action")
        b2.connect("clicked", self._remove)
        r2.add_suffix(b2)
        rg.add(r2)
        r3 = Adw.ActionRow(title="Open backups folder")
        b3 = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        b3.connect("clicked", lambda _b: self._open(paths.backup_dir()))
        r3.add_suffix(b3)
        rg.add(r3)
        r4 = Adw.ActionRow(title="Open my Bash configuration", subtitle=str(paths.bashrc()))
        b4 = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        b4.connect("clicked", lambda _b: self._open_bashrc())
        r4.add_suffix(b4)
        rg.add(r4)
        self.add(rg)

        # ---- app prefs
        pg = group("This app")
        self.scheme = combo_row("Colour scheme", [n for n, _ in SCHEMES], [v for _, v in SCHEMES].index(s["color_scheme"]))
        self.scheme.connect("notify::selected", lambda r, _p: self._opt(color_scheme=SCHEMES[r.get_selected()][1]))
        pg.add(self.scheme)
        self.motion = Adw.SwitchRow(title="Reduce motion", subtitle="Turns off animations. Also follows your system's setting.", active=s["reduce_motion"])
        self.motion.connect("notify::active", lambda r, _p: self._opt(reduce_motion=r.get_active()))
        pg.add(self.motion)
        r5 = Adw.ActionRow(title="Reset app settings", subtitle="Back to defaults. Your shell and terminal are not changed.")
        b5 = Gtk.Button(label="Reset", valign=Gtk.Align.CENTER)
        b5.connect("clicked", self._reset_settings)
        r5.add_suffix(b5)
        pg.add(r5)
        self.add(pg)

        # ---- safety explainer
        sg = group("Safe by design")
        for title, desc in SAFETY:
            row = Adw.ActionRow(title=title, subtitle=desc, subtitle_lines=3)
            row.add_prefix(Gtk.Image.new_from_icon_name("emblem-ok-symbolic"))
            sg.add(row)
        self.add(sg)
        self.add(label(f"Terminal Experience Studio {VERSION}", "tes-note"))
        self._loading = False
        self.refresh()

    # ------------------------------------------------------------------ backups list
    def refresh(self) -> None:
        for r in self._bk_rows:
            self.bk_group.remove(r)
        self._bk_rows = []
        entries = backups.list_backups()[:25]
        if not entries:
            row = Adw.ActionRow(title="No backups yet", subtitle="One is created automatically the first time you apply a change.")
            self.bk_group.add(row)
            self._bk_rows.append(row)
            return
        for e in entries:
            note = " - was empty/missing" if e.absent else " - from the original app" if e.legacy else ""
            row = Adw.ActionRow(title=f"{e.label}", subtitle=e.created.strftime("%a %d %b %Y, %H:%M:%S") + note)
            btn = Gtk.Button(label="Restore", valign=Gtk.Align.CENTER)
            btn.connect("clicked", lambda _b, e=e: self._restore(e))
            row.add_suffix(btn)
            self.bk_group.add(row)
            self._bk_rows.append(row)

    def _restore(self, e) -> None:
        def go():
            try:
                msg = backups.restore(e)
            except Exception as exc:  # noqa: BLE001
                self.win.alert("Couldn't restore", str(exc))
                return
            self.win.after_change()
            self.win.toast(msg)
            self.refresh()

        self.win.confirm(f"Restore {e.label} from {e.created.strftime('%d %b, %H:%M')}?",
                         "Your current version is backed up first, so you can switch back.", "Restore", go)

    def _manual_backup(self, _b) -> None:
        p = backups.backup_file(paths.bashrc(), "bashrc")
        self.refresh()
        self.win.toast("Backup saved." if p else "Nothing to back up.")

    def _remove(self, _b) -> None:
        def go():
            try:
                rep = bashconfig.remove_all()
            except Exception as exc:  # noqa: BLE001
                self.win.alert("Couldn't remove", str(exc))
                return
            self.win.after_change()
            self.refresh()
            self.win.toast("Removed from your shell. Open a new terminal to see it.", undo_backup=rep.backup)

        self.win.confirm("Remove from my shell?", "Your greeting and prompt styling will stop appearing. A backup is made first.", "Remove", go, destructive=True)

    def _reset_settings(self, _b) -> None:
        def go():
            self.state.s = settings.sanitize({})
            self.state.flush()
            self.state.reload()
            self.win.apply_accent()
            self.win.toast("App settings reset.")

        self.win.confirm("Reset app settings?", "Only this app's preferences are reset.", "Reset", go)

    def _opt(self, **kw) -> None:
        if self._loading:
            return
        self.state.update("settings", **kw)
        self.win.apply_scheme()

    # ------------------------------------------------------------------ opening things
    def _open(self, path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
        except Exception:  # noqa: BLE001
            self.win.alert("Couldn't open the folder", str(path))

    def _open_bashrc(self) -> None:
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        for cand in ([editor] if editor and shutil.which(editor.split()[0]) and not editor.split()[0] in ("vi", "vim", "nano", "emacs") else []) + \
                    ["xed", "gnome-text-editor", "gedit", "mousepad", "kate"]:
            if shutil.which(cand.split()[0]):
                subprocess.Popen([*cand.split(), str(paths.bashrc())])
                return
        self.win.alert("Open this file in your text editor", str(paths.bashrc()))

    def on_shown(self) -> None:
        super().on_shown()
        self.refresh()
