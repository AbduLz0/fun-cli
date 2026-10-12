"""All filesystem locations in one place. Everything honours $HOME / XDG so tests can sandbox it."""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "dev.tes.TerminalExperienceStudio"
APP_NAME = "Terminal Experience Studio"
VERSION = "0.2.0"

# Shell expression for our config dir, usable inside ~/.bashrc (no trailing quote).
SHELL_CONFIG_DIR = "${XDG_CONFIG_HOME:-$HOME/.config}/terminal-experience-studio"


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
