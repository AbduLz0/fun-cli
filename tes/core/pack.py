"""Greetings and roasts: where they come from, how AI lines are parsed, and how shell files are rendered.

Design
  * Source of truth is built-in content plus an optional `pack.json` of AI-written lines.
  * Every line carries an *emotion* (not a face) and, for greetings, a *tip* flag.
  * Shell files are rendered from that at Apply time, so the "Show tips" and "Faces" switches
    work for built-in and AI lines alike, and a toggle never needs the AI again.
  * Rendered format is one line per entry: `FACE<TAB>TEXT` (FACE may be empty). The shell never evals it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import content, paths
from .content import EMOTIONS, clean_line
from .fsutil import atomic_write, read_text

KINDS = ("greeting", "tip")


@dataclass(frozen=True)
class Line:
    emotion: str
    text: str
    tip: bool = False
    level: str = ""

    @property
    def face(self) -> str:
        return content.face_for(self.emotion)


# ------------------------------------------------------------------ store
def _clean_item(d) -> dict | None:
    if not isinstance(d, dict):
        return None
    text = clean_line(str(d.get("t", "")), 140).replace("\t", " ")
    emo = str(d.get("e", "happy")).lower()
    if len(text) < 3:
        return None
    return {"e": emo if emo in EMOTIONS else "happy", "t": text, "tip": bool(d.get("tip", False)),
            "level": str(d.get("level", ""))[:20]}


def load() -> dict:
    data = {"greetings": [], "roasts": []}
    try:
        raw = json.loads(paths.pack_file().read_text(encoding="utf-8"))
        for key in data:
            data[key] = [i for i in (_clean_item(x) for x in raw.get(key, [])) if i][:60]
    except (OSError, ValueError, AttributeError):
        pass
    if not data["greetings"]:
        # v1.0 stored plain text lines in greetings.txt; adopt them once (our own rendered files contain tabs).
        legacy = [l for l in read_text(paths.greetings_file()).splitlines() if l.strip() and "\t" not in l]
        data["greetings"] = [{"e": "happy", "t": clean_line(l, 90), "tip": l.lower().startswith("tip"), "level": ""}
                             for l in legacy[:40]]
    return data


def save(data: dict) -> None:
    paths.config_dir().mkdir(parents=True, exist_ok=True)
    atomic_write(paths.pack_file(), json.dumps(data, indent=2, ensure_ascii=False), mode=0o600)


def set_ai_greetings(lines: list[dict]) -> None:
    d = load()
    d["greetings"] = lines
    save(d)


def set_ai_roasts(lines: list[dict], level: str) -> None:
    d = load()
    d["roasts"] = [r for r in d["roasts"] if r.get("level") != level] + [dict(l, level=level) for l in lines]
    save(d)


def clear_ai_greetings() -> None:
    d = load()
    d["greetings"] = []
    save(d)
    if paths.greetings_file().exists() and not any("\t" in l for l in read_text(paths.greetings_file()).splitlines()):
        paths.greetings_file().unlink()  # drop an adopted legacy file so it isn't re-imported


def ai_counts() -> tuple[int, int]:
    d = load()
    return len(d["greetings"]), len(d["roasts"])


# ------------------------------------------------------------------ selection
def greeting_lines(s: dict) -> list[Line]:
    items = load()["greetings"]
    lines = [Line(i["e"], i["t"], i["tip"]) for i in items] or [Line(e, t, tip) for e, t, tip in content.BUILTIN_GREETINGS]
    if not s.get("tips_enabled", True):
        lines = [l for l in lines if not l.tip]
        if not lines:  # an AI pack made only of tips: fall back to the friendly built-ins
            lines = [Line(e, t, False) for e, t, tip in content.BUILTIN_GREETINGS if not tip]
    return lines


def roast_lines(s: dict) -> list[Line]:
    level = s.get("roast_level", content.DEFAULT_ROAST_LEVEL)
    lines = [Line(e, t, False, level) for e, t in content.ROAST_LEVELS.get(level, content.ROAST_LEVELS["Spicy"])]
    lines += [Line(i["e"], i["t"], False, level) for i in load()["roasts"] if i.get("level") == level and "{cmd}" in i["t"]]
    return lines


def _render(lines: list[Line], faces: bool) -> str:
    out = []
    for l in lines:
        face = l.face.replace("\t", " ") if faces else ""
        out.append(f"{face}\t{l.text.replace(chr(9), ' ')}")
    return "\n".join(out) + "\n"


def render_greetings(s: dict) -> str:
    return _render(greeting_lines(s), bool(s.get("emotion_faces", True)))


def render_roasts(s: dict) -> str:
    return _render(roast_lines(s), bool(s.get("emotion_faces", True)))


def preview_pairs(s: dict) -> list[tuple[str, str]]:
    """(face, text) pairs for on-screen previews - same selection logic as the shell files."""
    faces = bool(s.get("emotion_faces", True))
    return [(l.face if faces else "", l.text) for l in greeting_lines(s)]


def roast_text(line: Line, cmd: str) -> str:
    return line.text.replace("{cmd}", re.sub(r"[\x00-\x1f\x7f]", "", cmd))


# ------------------------------------------------------------------ AI prompts and parsing
def greetings_prompt(s: dict) -> tuple[str, str]:
    name = s.get("name") or "Terminal friend"
    desc = content.PERSONALITIES.get(s.get("personality", "Cheerful"), content.PERSONALITIES["Cheerful"])
    tips = bool(s.get("tips_enabled", True))
    system = f"You are {name}, a terminal companion who is {desc}. You write very short lines shown when a Linux terminal opens."
    kinds = ("Each line is either a `greeting` or a practical Linux/Bash `tip`." if tips else
             "Do NOT include Linux tips or advice. Every line is a `greeting`: a mood, a joke, an encouraging or silly remark.")
    user = (f"Write 14 different one-line messages, each under 80 characters. {kinds}\n"
            f"Format EVERY line exactly as:  emotion | kind | text\n"
            f"emotion is one of: {', '.join(content.EMOTION_NAMES)}. kind is greeting or tip.\n"
            "Choose the emotion that matches the text. Plain text only: no numbering, no bullets, no markdown, no emoji.")
    return system, user


def roast_prompt(s: dict) -> tuple[str, str]:
    level = s.get("roast_level", content.DEFAULT_ROAST_LEVEL)
    name = s.get("name") or "Terminal friend"
    tone = {"Gentle teasing": "light, affectionate teasing", "Spicy": "sharp, sarcastic and funny",
            "Unhinged": content.PERSONALITIES["Unhinged"]}.get(level, "sarcastic and funny")
    system = (f"You are {name}, a terminal companion whose tone is {tone}. You react to the user mistyping a command. "
              "Roast the typo or the command only. Never insult the user's identity, body, health, background or intelligence "
              "in a hateful way; no slurs, no profanity, no threats.")
    user = ("Write 14 different one-line reactions (each under 110 characters) to the user typing a command that does not exist. "
            "Each line MUST contain the exact token {cmd}, which will be replaced by what they typed.\n"
            f"Format EVERY line exactly as:  emotion | text\nemotion is one of: {', '.join(content.EMOTION_NAMES)}.\n"
            "Plain text only: no numbering, no bullets, no markdown, no emoji.")
    return system, user


def _strip(line: str) -> str:
    return re.sub(r"^[\s\-*•>\d.)]+", "", line.strip()).strip().strip('"')


def parse_ai_lines(raw: str, kind: str, limit: int = 24) -> list[dict]:
    """kind='greetings' (emotion|kind|text) or 'roasts' (emotion|text). Tolerates sloppy model output."""
    out, seen = [], set()
    for line in raw.splitlines():
        line = _strip(line)
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        emo, text, tip = "happy", line, False
        if parts[0].lower() in EMOTIONS and len(parts) >= 2:
            emo = parts[0].lower()
            if kind == "greetings" and len(parts) >= 3 and parts[1].lower() in KINDS:
                tip, text = parts[1].lower() == "tip", " | ".join(parts[2:])
            else:
                text = " | ".join(parts[1:])
        elif len(parts) > 1:
            continue  # looks like a table/format line we don't understand
        text = clean_line(" ".join(text.split()), 110 if kind == "roasts" else 90).replace("\t", " ")
        if kind == "greetings" and text.lower().startswith("tip"):
            tip = True
        if len(text) < 4 or text.lower() in seen:
            continue
        if kind == "roasts" and "{cmd}" not in text:
            continue
        seen.add(text.lower())
        out.append({"e": emo, "t": text, "tip": tip, "level": ""})
    return out[:limit]
