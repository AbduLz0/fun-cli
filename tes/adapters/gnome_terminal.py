"""GNOME Terminal: settings live in dconf, edited with `gsettings` on the default profile.

Before any change we snapshot every key we may touch, so Undo / Restore can put the exact
previous values back.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..core import backups
from ..core.themes import Theme
from .base import ApplyResult, TerminalAdapter

PROFILE_SCHEMA = "org.gnome.Terminal.Legacy.Profile"
PROFILES_PATH = "/org/gnome/terminal/legacy/profiles:/"
LIST_SCHEMA = "org.gnome.Terminal.ProfilesList"

KEYS = [
    "use-theme-colors", "foreground-color", "background-color", "palette",
    "cursor-colors-set", "cursor-background-color", "cursor-foreground-color",
    "use-system-font", "font", "cursor-shape",
    "use-transparent-background", "background-transparency-percent",
    "bold-color-same-as-fg",
]


def _gs(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=8)


def _quote(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


class GnomeTerminal(TerminalAdapter):
    id = "gnome-terminal"
    name = "GNOME Terminal"
    binary = "gnome-terminal"
    features = frozenset({"colors", "palette", "font", "cursor_shape", "transparency"})

    def detect(self) -> bool:
        return bool(shutil.which(self.binary)) and bool(shutil.which("gsettings"))

    # ------------------------------------------------------------- profile
    def profile_id(self) -> str | None:
        try:
            cur = _gs("get", LIST_SCHEMA, "default")
            pid = cur.stdout.strip().strip("'")
            if cur.returncode == 0 and pid:
                return pid
            lst = _gs("get", LIST_SCHEMA, "list")
            if lst.returncode == 0:
                ids = [x.strip().strip("'") for x in lst.stdout.strip().strip("[]").split(",") if x.strip()]
                return ids[0] if ids else None
        except (OSError, subprocess.SubprocessError):
            pass
        return None

    def _schema(self, pid: str) -> str:
        return f"{PROFILE_SCHEMA}:{PROFILES_PATH}:{pid}/"

    def snapshot(self, pid: str) -> dict:
        values = {}
        for k in KEYS:
            r = _gs("get", self._schema(pid), k)
            if r.returncode == 0:
                values[k] = r.stdout.strip()
        return {"profile": pid, "values": values}

    def _save_snapshot(self, pid: str) -> Path:
        return backups.write_snapshot(self.id, json.dumps(self.snapshot(pid), indent=2))

    def restore_snapshot(self, path: Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pid = data["profile"]
        for k, v in data["values"].items():
            if k in KEYS:
                _gs("set", self._schema(pid), k, v)

    # ------------------------------------------------------------- actions
    def pairs(self, t: Theme) -> list[tuple[str, str]]:
        shape = {"block": "block", "beam": "ibeam", "underline": "underline"}[t.cursor_shape]
        return [
            ("use-theme-colors", "false"),
            ("foreground-color", _quote(t.fg)),
            ("background-color", _quote(t.bg)),
            ("palette", "[" + ", ".join(_quote(c) for c in t.palette) + "]"),
            ("cursor-colors-set", "true"),
            ("cursor-background-color", _quote(t.cursor)),
            ("cursor-foreground-color", _quote(t.bg)),
            ("bold-color-same-as-fg", "true"),
            ("use-system-font", "false"),
            ("font", _quote(f"{t.font} {t.font_size:g}")),
            ("cursor-shape", _quote(shape)),
            ("use-transparent-background", "true" if t.opacity < 100 else "false"),
            ("background-transparency-percent", str(100 - t.opacity)),
        ]

    def apply(self, theme: Theme) -> ApplyResult:
        pid = self.profile_id()
        if not pid:
            return ApplyResult(False, "GNOME Terminal has no profile yet. Open it once, then try again.")
        try:
            snap = self._save_snapshot(pid)
            for key, val in self.pairs(theme):
                r = _gs("set", self._schema(pid), key, val)
                if r.returncode != 0 and key not in ("bold-color-same-as-fg",):
                    return ApplyResult(False, f"GNOME Terminal refused the setting '{key}': {r.stderr.strip()}", backup=snap)
        except (OSError, subprocess.SubprocessError) as exc:
            return ApplyResult(False, f"Couldn't talk to GNOME settings: {exc}")
        res = ApplyResult(True, "GNOME Terminal theme applied.", applied=sorted(self.features), backup=snap)
        res.notes.append("New tabs and windows pick it up immediately; open ones update too.")
        self._skip_unsupported(theme, res)
        return res

    def reset(self) -> ApplyResult:
        pid = self.profile_id()
        if not pid:
            return ApplyResult(False, "GNOME Terminal has no profile to reset.")
        snap = self._save_snapshot(pid)
        for k in KEYS:
            _gs("reset", self._schema(pid), k)
        return ApplyResult(True, "GNOME Terminal is back to its default look.", backup=snap)
