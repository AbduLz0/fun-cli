"""Shared application state: settings, autosave, observers."""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from .. import adapters
from ..core import ai, bashconfig, settings


class AppState:
    def __init__(self):
        self.s: dict = settings.load()
        self.api_key = ""                       # memory only, unless the user opts in to the keyring
        self.terminals = adapters.detect_all()  # installed terminals we know how to configure
        self._listeners: list[Callable[[str], None]] = []
        self._save_id = 0
        self.last_backup = None                 # path of the most recent Apply backup (for Undo)
        if self.s.get("keyring_remember"):
            self.api_key = ai.keyring_lookup(self.s["provider"])

    # ----------------------------------------------------------- observers
    def subscribe(self, cb: Callable[[str], None]) -> None:
        self._listeners.append(cb)

    def update(self, source: str = "", **kw) -> None:
        changed = {k: v for k, v in kw.items() if self.s.get(k) != v}
        if not changed:
            return
        self.s.update(changed)
        self._schedule_save()
        for cb in list(self._listeners):
            cb(source)

    def reload(self) -> None:
        self.s = settings.load()
        for cb in list(self._listeners):
            cb("reload")

    # ----------------------------------------------------------- persistence
    def _schedule_save(self) -> None:
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(500, self.flush)

    def flush(self) -> bool:
        self._save_id = 0
        try:
            settings.save(self.s)
        except OSError:
            pass
        return GLib.SOURCE_REMOVE

    # ----------------------------------------------------------- derived
    def sync_status(self) -> str:
        return bashconfig.status(self.s)
