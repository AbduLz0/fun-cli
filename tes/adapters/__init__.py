"""Terminal adapter registry."""
from __future__ import annotations

from pathlib import Path

from .alacritty import Alacritty
from .base import FEATURES, ApplyResult, TerminalAdapter  # noqa: F401
from .gnome_terminal import GnomeTerminal
from .kitty import Kitty
from .konsole import Konsole

ALL: list[TerminalAdapter] = [GnomeTerminal(), Kitty(), Alacritty(), Konsole()]
BY_ID = {a.id: a for a in ALL}


def detect_all() -> list[TerminalAdapter]:
    """Adapters whose terminal appears to be installed."""
    return [a for a in ALL if a.detect()]


def file_target(kind: str) -> Path | None:
    """Config file a backup of this kind restores to (None = not a plain file)."""
    if kind == "kitty":
        return Kitty.conf()
    if kind == "alacritty":
        return Alacritty.conf()
    return None
