"""`tes` - talk to your terminal companion from the shell.

    tes ask <question>      start a new conversation
    tes reply <message>     continue the last conversation
    tes cmd <what you want> find a command (also: howto ...)
    tes fix [code] [cmd]    why did my last command fail?
    tes explain <command>   offline first, AI for unknown commands
    tes status              what is configured

Safety: nothing the AI suggests is ever executed. Commands are printed with risk warnings.
No GTK is imported, so this starts fast and works over SSH.
"""
from __future__ import annotations

import shutil
import sys
import textwrap

from .core import ai, assistant, content, explain, settings
from .core.paths import VERSION
from .core.themes import nearest_256

HELP = __doc__


def _color(s: dict):
    on = sys.stdout.isatty()
    ac = f"\033[1;38;5;{nearest_256(s['accent'])}m" if on else ""
    dim, bold, warn, rst = ("\033[2m", "\033[1m", "\033[33m", "\033[0m") if on else ("", "", "", "")
    return ac, dim, bold, warn, rst


def _show(s: dict, reply: assistant.Reply) -> None:
    ac, dim, bold, warn, rst = _color(s)
    width = max(40, min(shutil.get_terminal_size((88, 20)).columns, 96)) - 2
    face = reply.face if s.get("emotion_faces", True) else ""
    lead = f"{ac}{face}{rst}  " if face else ""
    body = textwrap.fill(reply.text, width=width - (len(face) + 2 if face else 0)) if reply.text else ""
    print(lead + body.replace("\n", "\n" + " " * (len(face) + 2 if face else 0)))
    for cmd in reply.commands:
        print(f"\n  {bold}$ {cmd}{rst}")
        for w in reply.warnings.get(cmd, []):
            print(f"  {warn}! {w}{rst}")
    if reply.commands:
        print(f"\n{dim}(Nothing was run. Copy the command if you want it.){rst}")


def _need_ai(s: dict) -> str | None:
    key = assistant.resolve_key(s)
    why = assistant.readiness(s, key)
    if why:
        print(why, file=sys.stderr)
        return None
    return key


def _ask(s: dict, text: str, mode: str, keep: bool) -> int:
    key = _need_ai(s)
    if key is None:
        return 1
    history = assistant.load_convo() if keep else []
    if keep and not history:
        print("(No earlier conversation found, starting a new one.)", file=sys.stderr)
    print("thinking...", end="", file=sys.stderr, flush=True)
    try:
        reply, history = assistant.ask(s, key, text, history, mode)
    except ai.AIError as exc:
        print("\r\033[K" + str(exc), file=sys.stderr)
        return 2
    print("\r\033[K", end="", file=sys.stderr)
    assistant.save_convo(history)
    _show(s, reply)
    return 0


def _explain(s: dict, cmdline: str) -> int:
    e = explain.explain(cmdline)
    ac, dim, bold, warn, rst = _color(s)
    if e.known:
        print(f"{bold}{e.summary}{rst}")
        for ex, meaning in e.examples:
            print(f"  {ex}  {dim}- {meaning}{rst}")
        for w in e.warnings:
            print(f"  {warn}! {w}{rst}")
        return 0
    if e.warnings:
        for w in e.warnings:
            print(f"{warn}! {w}{rst}")
        return 0
    if assistant.readiness(s, assistant.resolve_key(s)) is None:
        return _ask(s, f"Explain this command: {cmdline}", "chat", keep=False)
    print("I don't know that one offline, and AI isn't set up here. Try: man " + cmdline.split()[0])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    s = settings.load()
    if not args or args[0] in ("-h", "--help", "help"):
        print(HELP.strip())
        return 0
    cmd, rest = args[0], args[1:]
    text = " ".join(rest).strip()
    if cmd in ("-V", "--version", "version"):
        print(f"tes {VERSION}")
        return 0
    if cmd == "status":
        key = assistant.resolve_key(s)
        why = assistant.readiness(s, key)
        print(f"AI: {'ready' if not why else 'not ready - ' + why}")
        print(f"Provider: {s['provider']}  Model: {s['model']}")
        print(f"Personality: {s['personality']}   Faces: {'on' if s['emotion_faces'] else 'off'}   "
              f"Tips: {'on' if s['tips_enabled'] else 'off'}   Roasts: {s['roast_level'] if s['roast_mistakes'] else 'off'}")
        return 0
    if cmd == "ask":
        return _ask(s, text, "chat", keep=False) if text else (print("Usage: tes ask <question>"), 1)[1]
    if cmd == "reply":
        return _ask(s, text, "chat", keep=True) if text else (print("Usage: tes reply <message>"), 1)[1]
    if cmd in ("cmd", "howto"):
        return _ask(s, text, "cmd", keep=False) if text else (print("Usage: tes cmd <what you want to do>"), 1)[1]
    if cmd == "fix":
        code = rest[0] if rest and rest[0].lstrip("-").isdigit() else "?"
        last = " ".join(rest[1:] if code != "?" else rest).strip()
        if not last:
            print("I couldn't see your last command. Usage: tes fix <exit-code> <command>")
            return 1
        if code == "0":
            print("That command succeeded (exit code 0), so there's nothing to fix. Ask me something with: tes ask ...")
            return 0
        msg = f"I ran this command: {last}\nIt exited with status {code}. What most likely went wrong, and how do I fix it?"
        return _ask(s, msg, "fix", keep=False)
    if cmd == "explain":
        return _explain(s, text) if text else (print("Usage: tes explain <command>"), 1)[1]
    print(f"Unknown command '{cmd}'.\n")
    print(HELP.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main())
