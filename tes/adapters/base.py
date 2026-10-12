"""Terminal adapter contract.

The GUI exposes one common set of options. Each adapter says which it supports,
applies those, and reports what it had to skip - we never pretend something was applied.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..core import backups
from ..core.fsutil import atomic_write, read_text
from ..core.shellblock import get_block, set_block
from ..core.themes import Theme

FEATURES = {
    "colors": "Foreground, background & cursor colours",
    "palette": "16-colour palette",
    "font": "Font family & size",
    "cursor_shape": "Cursor shape",
    "transparency": "Transparency",
    "bg_image": "Background image",
}

START = "# >>> Terminal Experience Studio >>>"
END = "# <<< Terminal Experience Studio <<<"


@dataclass
class ApplyResult:
    ok: bool
    message: str
    applied: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # feature -> reason
    backup: Path | None = None
    notes: list[str] = field(default_factory=list)


class TerminalAdapter:
    id = ""
    name = ""
    binary = ""
    features: frozenset[str] = frozenset()
    hint = ""  # shown when the user needs a manual step

    # --- detection
    def config_exists(self) -> bool:
        return False

    def detect(self) -> bool:
        return bool(shutil.which(self.binary)) or self.config_exists()

    def unsupported(self) -> list[str]:
        return [f for f in FEATURES if f not in self.features]

    # --- actions
    def apply(self, theme: Theme) -> ApplyResult:
        raise NotImplementedError

    def reset(self) -> ApplyResult:
        raise NotImplementedError

    # --- helpers
    def _skip_unsupported(self, theme: Theme, res: ApplyResult) -> None:
        if theme.bg_image and "bg_image" not in self.features:
            res.skipped["bg_image"] = f"{self.name} has no background-image setting."


def managed_include(conf: Path, include_line: str, kind: str, *, top_level: bool = False) -> Path | None:
    """Ensure a managed block with `include_line` exists in `conf`. Returns the backup path."""
    bk = backups.backup_file(conf, kind)
    text = read_text(conf)
    block = f"{START}\n{include_line}\n{END}"
    if top_level and get_block(text, START, END) is None:
        # must come before any [table] for TOML top-level keys
        new = block + "\n\n" + text.lstrip("\n") if text.strip() else block + "\n"
    else:
        new = set_block(text, START, END, block)
    if new != text:
        atomic_write(conf, new)
    return bk


def remove_managed(conf: Path, kind: str) -> Path | None:
    if not conf.exists():
        return None
    bk = backups.backup_file(conf, kind)
    text = read_text(conf)
    new = set_block(text, START, END, None)
    if new != text:
        atomic_write(conf, new)
    return bk
