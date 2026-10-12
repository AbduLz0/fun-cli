"""Generate and apply everything that lives in ~/.bashrc.

Design rules
  * We only ever touch two marked blocks. Everything else in .bashrc is left alone.
  * One timestamped backup is made before any change.
  * Startup must stay fast: no subprocesses unless the user asked for one (fastfetch).
  * Only interactive shells are affected.
  * Anything the user typed is single-quoted, and control characters are stripped,
    so text can never be executed or inject terminal escape sequences.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import backups, paths, prompts
from .content import clean_art, clean_line
from .fsutil import atomic_write, read_text
from .shellblock import BlockError, get_block, set_block
from .themes import nearest_256

MOTD_START = "# >>> Terminal Experience Studio >>>"
MOTD_END = "# <<< Terminal Experience Studio <<<"
PROMPT_START = "# >>> Terminal Experience Studio: prompt >>>"
PROMPT_END = "# <<< Terminal Experience Studio: prompt <<<"

_PLACEHOLDERS = {"{user}": '"${USER:-}"', "{host}": '"${HOSTNAME:-}"', "{daypart}": '"${_tes_dp:-}"'}


def sq(text: str) -> str:
    """Shell single-quote."""
    return "'" + text.replace("'", "'\\''") + "'"


def template(text: str) -> str:
    """Turn 'Hi {user}!' into a safe shell word: 'Hi '"${USER}"'!'"""
    text = clean_line(text, 200)
    parts = re.split(r"(\{user\}|\{host\}|\{daypart\})", text)
    words = [_PLACEHOLDERS[p] if p in _PLACEHOLDERS else sq(p) for p in parts if p != ""]
    return "".join(words) or "''"


# ------------------------------------------------------------------ blocks
def motd_block(s: dict) -> str:
    L = [MOTD_START, "# Managed by Terminal Experience Studio - edit these settings in the app."]
    if not s.get("enabled", True):
        return "\n".join(L + ["# Startup greeting is switched off.", MOTD_END])
    ac = nearest_256(s["accent"])
    greeting = s.get("greeting") or "Welcome back, {user}!"
    cfg = paths.SHELL_CONFIG_DIR
    L.append("if [[ $- == *i* ]]; then")
    L.append(f"  _tes_c=$'\\e[1;38;5;{ac}m'; _tes_r=$'\\e[0m'; _tes_d=$'\\e[2m'")
    if "{daypart}" in greeting:
        L.append("  printf -v _tes_h '%(%H)T' -1; _tes_h=$((10#$_tes_h))")
        L.append('  if (( _tes_h < 5 )); then _tes_dp=night; elif (( _tes_h < 12 )); then _tes_dp=morning;')
        L.append("  elif (( _tes_h < 18 )); then _tes_dp=afternoon; else _tes_dp=evening; fi")
    if s.get("art_enabled") and s.get("art_text", "").strip():
        L.append(f'  if [[ -r "{cfg}/art.txt" ]]; then printf "%s" "$_tes_c"; cat -- "{cfg}/art.txt"; printf "%s" "$_tes_r"; fi')
    if s.get("show_date", True):
        L.append("  printf '%s%(%a %d %b %H:%M)T%s  ' \"$_tes_d\" -1 \"$_tes_r\"")
    L.append(f"  printf '%s%s%s  %s\\n' \"$_tes_c\" {sq(clean_line(s.get('face', '(•‿•)'), 60))} \"$_tes_r\" {template(greeting)}")
    if s.get("greeting_pack"):
        L.append(f'  if [[ -r "{cfg}/greetings.txt" ]]; then')
        L.append(f'    mapfile -t _tes_g < "{cfg}/greetings.txt"')
        L.append('    (( ${#_tes_g[@]} )) && printf \'%s%s%s\\n\' "$_tes_d" "${_tes_g[RANDOM % ${#_tes_g[@]}]}" "$_tes_r"')
        L.append("  fi")
    for line in s.get("custom_motd", "").strip().splitlines()[:5]:
        L.append(f"  printf '%s\\n' {sq(clean_line(line, 200))}")
    if s.get("show_host", False):
        L.append("  printf '  Host: %s | Shell: %s\\n' \"${HOSTNAME}\" \"${SHELL##*/}\"")
    if s.get("fastfetch", False):
        L.append("  if command -v fastfetch >/dev/null 2>&1; then fastfetch; fi")
    L.append("  unset _tes_c _tes_r _tes_d _tes_h _tes_dp _tes_g")
    L.append("fi")
    L.append(MOTD_END)
    return "\n".join(L)


def prompt_block(s: dict) -> str | None:
    snippet = prompts.bash_snippet(s)
    if not snippet:
        return None
    return "\n".join([PROMPT_START, "# Managed by Terminal Experience Studio.", *snippet, PROMPT_END])


def render_bashrc(current: str, s: dict) -> str:
    out = set_block(current, MOTD_START, MOTD_END, motd_block(s))
    return set_block(out, PROMPT_START, PROMPT_END, prompt_block(s))


# ------------------------------------------------------------------ side files
def _side_files(s: dict) -> dict[Path, str | None]:
    """Files we own inside our config dir. None means 'should not exist'."""
    art = clean_art(s.get("art_text", "")) if s.get("art_enabled") else ""
    return {
        paths.art_file(): (art + "\n") if art else None,
        paths.starship_file(): prompts.starship_toml(s),
    }


# ------------------------------------------------------------------ status
def status(s: dict) -> str:
    """'none' (never applied) | 'synced' | 'pending'"""
    cur = read_text(paths.bashrc())
    try:
        has = get_block(cur, MOTD_START, MOTD_END) is not None or get_block(cur, PROMPT_START, PROMPT_END) is not None
        if not has:
            return "none"
        want = render_bashrc(cur, s)
    except BlockError:
        return "pending"
    return "synced" if want == cur else "pending"


def is_installed() -> bool:
    try:
        cur = read_text(paths.bashrc())
        return get_block(cur, MOTD_START, MOTD_END) is not None
    except BlockError:
        return True


# ------------------------------------------------------------------ apply
@dataclass
class ApplyReport:
    backup: Path | None
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def describe(s: dict) -> list[str]:
    """Plain-language list of what Apply will do (for the confirmation dialog)."""
    items = ["Update the Terminal Experience Studio section of ~/.bashrc (everything else stays untouched)."]
    if not s.get("enabled", True):
        items.append("Welcome message: switched off.")
    else:
        items.append(f"Welcome message: {s.get('face', '')}  {s.get('greeting', '')}")
    if s.get("art_enabled") and s.get("art_text", "").strip():
        items.append("Startup art: saved to a file in the app's config folder.")
    p = prompts.get(s.get("prompt_preset", "keep"))
    if p.engine == "none":
        items.append("Prompt: unchanged.")
    elif p.engine == "starship":
        items.append(f"Prompt: {p.name} (only active if Starship is installed; uses the app's own config file).")
    else:
        items.append(f"Prompt: {p.name}.")
    items.append("A timestamped backup is created first, so you can undo this.")
    return items


def apply(s: dict) -> ApplyReport:
    bashrc = paths.bashrc()
    current = read_text(bashrc)
    new = render_bashrc(current, s)  # may raise BlockError before anything is touched
    if not (MOTD_START in new and MOTD_END in new):
        raise RuntimeError("Generated configuration failed validation; nothing was changed.")
    report = ApplyReport(backup=backups.backup_file(bashrc, "bashrc"))
    for path, content in _side_files(s).items():
        if content is None:
            if path.exists():
                path.unlink()
        else:
            atomic_write(path, content, mode=0o600)
            report.changes.append(path.name)
    if new != current:
        atomic_write(bashrc, new)
        report.changes.append(".bashrc")
    p = prompts.get(s.get("prompt_preset", "keep"))
    if p.engine == "starship" and not shutil.which("starship"):
        report.warnings.append("Starship isn't installed yet, so your normal prompt will be used until it is.")
    if s.get("fastfetch") and not shutil.which("fastfetch"):
        report.warnings.append("Fastfetch isn't installed; that line is skipped until it is.")
    return report


def remove_all() -> ApplyReport:
    """Remove everything this app added to ~/.bashrc (after a backup)."""
    bashrc = paths.bashrc()
    current = read_text(bashrc)
    new = set_block(set_block(current, MOTD_START, MOTD_END, None), PROMPT_START, PROMPT_END, None)
    report = ApplyReport(backup=backups.backup_file(bashrc, "bashrc"))
    if new != current:
        atomic_write(bashrc, new)
        report.changes.append(".bashrc")
    return report


# ------------------------------------------------------------------ greeting pack
def write_greetings(lines: list[str]) -> None:
    clean = [clean_line(l, 90) for l in lines]
    clean = [l for l in clean if l]
    f = paths.greetings_file()
    if clean:
        atomic_write(f, "\n".join(clean) + "\n", mode=0o600)
    elif f.exists():
        f.unlink()


def read_greetings() -> list[str]:
    return [l for l in read_text(paths.greetings_file()).splitlines() if l.strip()]
