"""All filesystem locations in one place. Everything honours $HOME / XDG so tests can sandbox it."""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "dev.tes.TerminalExperienceStudio"
APP_NAME = "Terminal Experience Studio"
VERSION = "1.1.0"

# Shell expression for our config dir, usable inside ~/.bashrc (no trailing quote).
SHELL_CONFIG_DIR = "${XDG_CONFIG_HOME:-$HOME/.config}/terminal-experience-studio"
SHELL_TES_BIN = "${XDG_DATA_HOME:-$HOME/.local/share}/terminal-experience-studio/bin/tes"


def home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def _xdg(var: str, default: str) -> Path:
    v = os.environ.get(var, "")
    return Path(v) if v and os.path.isabs(v) else home() / default


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_home() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def config_dir() -> Path:
    return config_home() / "terminal-experience-studio"


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / "terminal-experience-studio"


def convo_file() -> Path:
    """Conversation memory for `tes reply` (cache, owner-only)."""
    return cache_dir() / "conversation.json"


def pack_file() -> Path:
    """User-editable store of AI-written greetings/roasts (the app renders shell files from it)."""
    return config_dir() / "pack.json"


def roasts_file() -> Path:
    return config_dir() / "roasts.txt"


def bin_dir() -> Path:
    return data_home() / "terminal-experience-studio" / "bin"


def tes_bin() -> Path:
    return bin_dir() / "tes"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def art_file() -> Path:
    return config_dir() / "art.txt"


def greetings_file() -> Path:
    return config_dir() / "greetings.txt"


def starship_file() -> Path:
    """Our own starship config. We never overwrite the user's ~/.config/starship.toml."""
    return config_dir() / "starship.toml"


def backup_dir() -> Path:
    return data_home() / "terminal-experience-studio" / "backups"


def bashrc() -> Path:
    return home() / ".bashrc"
