"""The companion's brain (no GUI): prompts, reply parsing, conversation memory, AI themes.

Safety rules baked in
  * The AI never runs anything. Suggested commands are only *shown*, each checked for risk.
  * Replies are untrusted text: control characters are stripped before display or storage.
  * Generated themes are validated (strict colour format, minimum contrast) before use.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from . import ai, content, explain, paths, themes
from .content import EMOTIONS, clean_line
from .fsutil import atomic_write

MAX_TURNS = 12  # messages kept for `tes reply`


# ------------------------------------------------------------------ keys
def resolve_key(s: dict) -> str:
    """Key for command-line use: env var first, then the desktop keyring (only if the user opted in)."""
    env = os.environ.get("TES_API_KEY", "").strip()
    if env:
        return env
    if s.get("keyring_remember"):
        return ai.keyring_lookup(s.get("provider", ""))
    return ""


def readiness(s: dict, key: str) -> str | None:
    """None when AI can be used, otherwise a friendly reason why not."""
    if not s.get("ai_enabled"):
        return "AI features are switched off. Turn them on in Terminal Experience Studio > AI Companion."
    info = ai.PROVIDERS.get(s.get("provider", ""), None)
    if info is None:
        return "No AI provider is chosen yet. Pick one in AI Companion."
    if info["needs_key"] and not key:
        return ("No API key available here. In AI Companion switch on 'Remember key in my desktop keyring' "
                "(needs libsecret-tools), or set TES_API_KEY in this shell.")
    return None


# ------------------------------------------------------------------ prompts
def system_prompt(s: dict, mode: str = "chat") -> str:
    name = s.get("name") or "Terminal friend"
    desc = content.PERSONALITIES.get(s.get("personality", "Cheerful"), content.PERSONALITIES["Cheerful"])
    faces = bool(s.get("emotion_faces", True))
    parts = [
        f"You are {name}, a companion that lives in the user's Linux terminal (Zorin OS / Ubuntu, Bash). Your tone: {desc}.",
        "Be correct and useful first, entertaining second. Keep answers short: this is a terminal.",
        "Plain text only: no markdown, no bullet lists, no code fences.",
    ]
    if faces:
        parts.append("Start your reply with your emotion in square brackets, one of: " + ", ".join(content.EMOTION_NAMES)
                     + ". Example: [smug] That works, but there's a cleaner way.")
    parts.append("When a shell command helps, put it on its own line starting with 'CMD: ' (one command per line, "
                 "at most 3). Never put anything else on a CMD line. Never claim you ran anything: the user runs it.")
    parts.append("Warn plainly before anything destructive (deleting, overwriting, formatting, chmod -R, sudo).")
    if mode == "cmd":
        parts.append("The user describes a task. Reply with a one-sentence explanation and the best command(s) as CMD lines.")
    if mode == "fix":
        parts.append("The user's last command failed or misbehaved. Say the most likely cause in one or two sentences, "
                     "then give a corrected command as a CMD line. If you can't be sure, say what to check.")
    return " ".join(parts)


# ------------------------------------------------------------------ reply parsing
@dataclass
class Reply:
    emotion: str
    text: str
    commands: list[str] = field(default_factory=list)
    warnings: dict[str, list[str]] = field(default_factory=dict)  # command -> warnings

    @property
    def face(self) -> str:
        return EMOTIONS.get(self.emotion, EMOTIONS["happy"])


_TAG = re.compile(r"^\s*\[\s*([A-Za-z]+)\s*\]\s*")


def parse_reply(raw: str, faces: bool = True) -> Reply:
    emotion = "happy"
    lines = []
    commands: list[str] = []
    fenced = False
    fence_cmds: list[str] = []
    for line in raw.replace("\r", "").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            if stripped and len(fence_cmds) < 3:
                fence_cmds.append(re.sub(r"^\$\s+", "", stripped))
            continue
        m = re.match(r"^\s*CMD:\s*(.+)$", line)
        if m:
            cmd = clean_line(m.group(1).strip().strip("`"), 300)
            if cmd and len(commands) < 3:
                commands.append(cmd)
            continue
        lines.append(line)
    if not commands:  # model ignored the CMD: convention and used a code fence
        commands = [clean_line(c, 300) for c in fence_cmds if clean_line(c, 300)]
    text = "\n".join(lines).strip()
    m = _TAG.match(text)
    if m:
        if m.group(1).lower() in EMOTIONS:
            emotion = m.group(1).lower()
        text = text[m.end():]
    text = re.sub(r"\*\*|__|`", "", text)  # models love markdown even when told not to
    text = "\n".join(clean_line(l, 400) for l in text.splitlines()).strip()
    reply = Reply(emotion if faces else "happy", text, commands)
    for c in commands:
        w = explain.explain(c).warnings
        if w:
            reply.warnings[c] = w
    return reply


# ------------------------------------------------------------------ conversation memory (for `tes reply`)
def load_convo() -> list[dict]:
    try:
        data = json.loads(paths.convo_file().read_text(encoding="utf-8"))
        return [{"role": m["role"], "content": str(m["content"])[:4000]} for m in data
                if m.get("role") in ("user", "assistant")][-MAX_TURNS:]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def save_convo(msgs: list[dict]) -> None:
    paths.cache_dir().mkdir(parents=True, exist_ok=True)
    atomic_write(paths.convo_file(), json.dumps(msgs[-MAX_TURNS:], ensure_ascii=False), mode=0o600)


def clear_convo() -> None:
    try:
        paths.convo_file().unlink()
    except FileNotFoundError:
        pass


def ask(s: dict, key: str, user_text: str, history: list[dict] | None = None, mode: str = "chat") -> tuple[Reply, list[dict]]:
    """One round trip. Returns the parsed reply and the updated history (to persist or discard)."""
    history = list(history or [])
    history.append({"role": "user", "content": user_text[:4000]})
    msgs = [{"role": "system", "content": system_prompt(s, mode)}] + history[-MAX_TURNS:]
    raw = ai.chat_messages(s["provider"], s["model"], key, msgs, max_tokens=350, temperature=0.8)
    reply = parse_reply(raw, bool(s.get("emotion_faces", True)))
    history.append({"role": "assistant", "content": raw[:4000]})
    return reply, history[-MAX_TURNS:]


# ------------------------------------------------------------------ AI themes
class ThemeGenError(Exception):
    pass


def theme_prompt(description: str) -> tuple[str, str]:
    system = ("You design terminal colour themes. Reply with ONE JSON object and nothing else. Keys: "
              '"name" (short string), "fg", "bg", "cursor" (hex like #1a2b3c), and "palette": exactly 16 hex colours '
              "in ANSI order: black, red, green, yellow, blue, magenta, cyan, white, then the 8 bright versions. "
              "Text must be easy to read: strong contrast between fg and bg.")
    return system, f"Theme idea: {clean_line(description, 120)}"


def parse_theme(raw: str, base: themes.Theme) -> themes.Theme:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ThemeGenError("The AI didn't send a theme. Try describing it differently.")
    try:
        data = json.loads(m.group(0))
        data = {k: data[k] for k in ("name", "fg", "bg", "cursor", "palette") if k in data}
        theme = base.with_(**{k: v for k, v in themes.from_dict({**base.to_dict(), **data}).to_dict().items()
                              if k in ("name", "fg", "bg", "cursor", "palette")})
    except (ValueError, themes.ThemeError) as exc:
        raise ThemeGenError(f"The AI's theme wasn't valid ({exc}). Try again.") from exc
    if themes.contrast_ratio(theme.fg, theme.bg) < 4.0:
        raise ThemeGenError("That theme would be hard to read (text and background too similar). Try again.")
    return theme
