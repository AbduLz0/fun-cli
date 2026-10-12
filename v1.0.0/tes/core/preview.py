"""Builds the on-screen preview of the welcome display from the same settings that produce the real Bash output."""
from __future__ import annotations

import os
import random
from datetime import datetime

from .content import OFFLINE_GREETINGS, clean_art, clean_line


def daypart(hour: int) -> str:
    return "night" if hour < 5 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


def fill(text: str, user: str, host: str, hour: int) -> str:
    return clean_line(text, 200).replace("{user}", user).replace("{host}", host).replace("{daypart}", daypart(hour))


def welcome_lines(s: dict, pack: list[str] | None = None, now: datetime | None = None,
                  user: str | None = None, host: str | None = None, rng: random.Random | None = None):
    now = now or datetime.now()
    user = user or os.environ.get("USER", "you")
    host = host or os.uname().nodename
    rng = rng or random
    if not s.get("enabled", True):
        return [[("(The welcome message is switched off.)", "dim")]]
    lines: list[list[tuple[str, str]]] = []
    art = clean_art(s.get("art_text", "")) if s.get("art_enabled") else ""
    for l in art.splitlines():
        lines.append([(l, "accent")])
    first: list[tuple[str, str]] = []
    if s.get("show_date", True):
        first.append((now.strftime("%a %d %b %H:%M") + "  ", "dim"))
    first.append((clean_line(s.get("face", ""), 60), "accent"))
    first.append(("  " + fill(s.get("greeting", ""), user, host, now.hour), "fg"))
    lines.append(first)
    if s.get("greeting_pack"):
        pool = pack or OFFLINE_GREETINGS
        lines.append([(rng.choice(pool), "dim")])
    for l in s.get("custom_motd", "").strip().splitlines()[:5]:
        lines.append([(clean_line(l, 200), "fg")])
    if s.get("show_host"):
        lines.append([(f"  Host: {host} | Shell: bash", "fg")])
    if s.get("fastfetch"):
        lines.append([("[ Fastfetch system summary appears here ]", "dim")])
    lines.append([])
    lines.append([(f"{user}@{host}", "p2"), (":", "fg"), ("~", "p4"), ("$ ", "fg")])
    return lines
