"""Timestamped backups and one-click restore.

Layout:  <data>/terminal-experience-studio/backups/<kind>__<YYYYmmdd-HHMMSS-micro>.bak
If the original file did not exist, we store a '.absent' marker so restore can delete what we created.
GNOME Terminal settings are stored as '.json' snapshots (see adapters/gnome_terminal.py).
Backups made by the original MVP (~/.bashrc.terminal-experience-backup-*) are still recognised.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import paths
from .fsutil import atomic_write

LEGACY_PREFIX = ".bashrc.terminal-experience-backup-"

KIND_LABELS = {
    "bashrc": "Bash configuration",
    "kitty": "Kitty",
    "alacritty": "Alacritty",
    "konsole": "Konsole",
    "gnome-terminal": "GNOME Terminal",
}


@dataclass(frozen=True)
class BackupEntry:
    kind: str
    path: Path
    created: datetime
    absent: bool = False
    legacy: bool = False

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def backup_file(src: Path, kind: str) -> Path | None:
    """Back up `src` (or record that it was absent). Returns the backup path."""
    d = paths.backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    src = Path(src)
    if src.exists():
        dest = d / f"{kind}__{_stamp()}.bak"
        shutil.copy2(src, dest)
        return dest
    dest = d / f"{kind}__{_stamp()}.absent"
    dest.write_text("", encoding="utf-8")
    return dest


def write_snapshot(kind: str, text: str) -> Path:
    d = paths.backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{kind}__{_stamp()}.json"
    dest.write_text(text, encoding="utf-8")
    return dest


def _parse(p: Path) -> BackupEntry | None:
    name = p.name
    if name.startswith(LEGACY_PREFIX):
        try:
            when = datetime.strptime(name[len(LEGACY_PREFIX):], "%Y%m%d-%H%M%S")
        except ValueError:
            when = datetime.fromtimestamp(p.stat().st_mtime)
        return BackupEntry("bashrc", p, when, legacy=True)
    if "__" not in name:
        return None
    kind, rest = name.split("__", 1)
    stem, _, ext = rest.rpartition(".")
    if ext not in ("bak", "absent", "json"):
        return None
    try:
        when = datetime.strptime(stem, "%Y%m%d-%H%M%S-%f")
    except ValueError:
        return None
    return BackupEntry(kind, p, when, absent=(ext == "absent"))


def list_backups() -> list[BackupEntry]:
    found: list[BackupEntry] = []
    d = paths.backup_dir()
    if d.is_dir():
        found += [e for p in d.iterdir() if (e := _parse(p))]
    h = paths.home()
    if h.is_dir():
        found += [e for p in h.glob(LEGACY_PREFIX + "*") if (e := _parse(p))]
    return sorted(found, key=lambda e: e.created, reverse=True)


def target_for(kind: str) -> Path | None:
    from ..adapters import file_target  # local import: adapters import this module
    if kind == "bashrc":
        return paths.bashrc()
    return file_target(kind)


def restore(entry: BackupEntry) -> str:
    """Put a backup back. A safety backup of the current state is taken first."""
    if entry.kind == "gnome-terminal":
        from ..adapters.gnome_terminal import GnomeTerminal
        GnomeTerminal().restore_snapshot(entry.path)
        return "GNOME Terminal settings restored."
    target = target_for(entry.kind)
    if target is None:
        raise RuntimeError(f"Don't know where to restore '{entry.kind}' backups.")
    backup_file(target, entry.kind)  # safety net for the restore itself
    if entry.absent:
        if target.exists():
            target.unlink()
        return f"Removed {target.name} (it didn't exist before)."
    atomic_write(target, entry.path.read_text(encoding="utf-8"))
    return f"Restored {target.name}."


def entry_for(path: Path) -> BackupEntry | None:
    """Look up the BackupEntry for a path returned by backup_file()."""
    return _parse(Path(path)) if path else None
