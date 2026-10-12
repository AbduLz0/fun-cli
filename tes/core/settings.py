"""Persistent preferences. Never contains secrets (API keys go to the desktop keyring or stay in memory)."""
from __future__ import annotations

import copy
import json
import os
import re

from . import paths, themes
from .fsutil import atomic_write

DEFAULTS: dict = {
    # --- welcome / MOTD (keys kept compatible with the original Tkinter MVP)
    "enabled": True,
    "name": "Terminal friend",
    "greeting": "Good {daypart}, {user}!",
    "face": "(•‿•)",
    "show_date": True,
    "show_host": False,
    "fastfetch": False,
    "custom_motd": "",
    "accent": "#7bd88f",
    "greeting_pack": False,
    # --- ascii art
    "art_enabled": False,
    "art_text": "",
    "art_name": "",
    # --- prompt
    "prompt_preset": "keep",
    "prompt_git": True,
    "prompt_time": False,
    # --- terminal appearance
    "theme": themes.DEFAULT_THEME.to_dict(),
    "terminal_target": "",
    # --- AI (no secrets here)
    "provider": "Groq",
    "model": "llama-3.3-70b-versatile",
    "ai_enabled": False,
    "personality": "Cheerful",
    "keyring_remember": False,
    # --- app
    "color_scheme": "dark",
    "reduce_motion": False,
    "onboarded": False,
}

_LEGACY_PROMPT = {
    "Keep my existing prompt": "keep",
    "Recommend Starship (safe setup guide)": "keep",
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def sanitize(raw: dict) -> dict:
    """Merge `raw` over defaults, discarding anything with the wrong type."""
    out = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return out
    for key, default in DEFAULTS.items():
        if key not in raw or key == "theme":
            continue
        val = raw[key]
        if isinstance(default, bool):
            if isinstance(val, bool):
                out[key] = val
        elif isinstance(default, str):
            if isinstance(val, str):
                out[key] = val
        else:
            out[key] = val
    # legacy migration: the old app stored the prompt as a sentence
    if "prompt_style" in raw and "prompt_preset" not in raw:
        out["prompt_preset"] = _LEGACY_PROMPT.get(str(raw["prompt_style"]), "keep")
    if "ai_greeting" in raw and "greeting_pack" not in raw and isinstance(raw["ai_greeting"], bool):
        out["greeting_pack"] = raw["ai_greeting"]
    # a legacy greeting without {daypart} stays exactly as the user wrote it
    if not _HEX.match(out["accent"]):
        out["accent"] = DEFAULTS["accent"]
    out["color_scheme"] = out["color_scheme"] if out["color_scheme"] in ("dark", "light", "system") else "dark"
    out["custom_motd"] = out["custom_motd"][:1000]
    out["greeting"] = (out["greeting"] or DEFAULTS["greeting"])[:200]
    out["art_text"] = out["art_text"][:24000]
    out["theme"] = themes.from_dict(raw.get("theme", {}), strict=False).to_dict()
    return out


def load() -> dict:
    try:
        raw = json.loads(paths.settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return sanitize(raw)


def save(data: dict) -> None:
    f = paths.settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(f, json.dumps(data, indent=2, ensure_ascii=False), mode=0o600)
    os.chmod(f, 0o600)
