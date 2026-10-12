"""Optional AI companion plumbing.

Rules: the app is fully useful without any of this. AI is only called when the user presses a
button. Nothing here runs at shell startup: greetings are generated ahead of time and cached
in a plain text file, so your terminal never waits on the network.

API keys are never written to settings.json or ~/.bashrc. They live in memory, or (opt-in) in
the desktop keyring via `secret-tool` (libsecret).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request

from . import content

PROVIDERS = {
    "Groq": {
        "url": "https://console.groq.com/keys",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile", "needs_key": True,
    },
    "OpenAI": {
        "url": "https://platform.openai.com/api-keys",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini", "needs_key": True,
    },
    "OpenRouter": {
        "url": "https://openrouter.ai/keys",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openai/gpt-4o-mini", "needs_key": True,
    },
    "Ollama (on this computer)": {
        "url": "https://ollama.com/download",
        "endpoint": "http://localhost:11434/v1/chat/completions",
        "model": "llama3.2", "needs_key": False,
    },
}


class AIError(Exception):
    pass


# ------------------------------------------------------------------ keyring
def keyring_available() -> bool:
    return shutil.which("secret-tool") is not None


def keyring_store(provider: str, key: str) -> bool:
    if not keyring_available():
        return False
    r = subprocess.run(
        ["secret-tool", "store", "--label", f"Terminal Experience Studio ({provider})",
         "service", "terminal-experience-studio", "provider", provider],
        input=key, text=True, capture_output=True, timeout=15)
    return r.returncode == 0


def keyring_lookup(provider: str) -> str:
    if not keyring_available():
        return ""
    try:
        r = subprocess.run(["secret-tool", "lookup", "service", "terminal-experience-studio", "provider", provider],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def keyring_clear(provider: str) -> None:
    if keyring_available():
        subprocess.run(["secret-tool", "clear", "service", "terminal-experience-studio", "provider", provider],
                       capture_output=True, timeout=10)


# ------------------------------------------------------------------ requests
def chat(provider: str, model: str, key: str, system: str, user: str, max_tokens: int = 300,
         temperature: float = 0.8, timeout: int = 25) -> str:
    """One blocking chat completion (call from a worker thread)."""
    info = PROVIDERS.get(provider)
    if info is None:
        raise AIError("Unknown provider.")
    if info["needs_key"] and not key:
        raise AIError("Add an API key first.")
    payload = {"model": model or info["model"], "temperature": temperature, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(info["endpoint"], data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"]).strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        hint = " (check that the key is correct)" if exc.code in (401, 403) else ""
        raise AIError(f"The provider answered HTTP {exc.code}{hint}. {detail}") from exc
    except urllib.error.URLError as exc:
        local = " Is Ollama running?" if "localhost" in info["endpoint"] else " Check your internet connection."
        raise AIError(f"Couldn't reach the provider.{local}") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise AIError("The provider sent a reply we couldn't read.") from exc


def greeting_pack_prompt(name: str, personality: str) -> tuple[str, str]:
    desc = content.PERSONALITIES.get(personality, content.PERSONALITIES["Cheerful"])
    system = (f"You are {name or 'Terminal friend'}, a terminal companion who is {desc}. "
              "You write very short lines shown when a Linux terminal opens.")
    user = ("Write 12 different one-line messages, each under 80 characters. Mix warm greetings with practical "
            "Linux/Bash tips. Plain text only: no numbering, no bullets, no markdown, no emoji, no quotes.")
    return system, user


def parse_pack(raw: str, limit: int = 20) -> list[str]:
    lines, seen = [], set()
    for line in raw.splitlines():
        line = line.strip().lstrip("-*•0123456789.) ").strip().strip('"')
        line = content.clean_line(line, 90)
        if len(line) >= 4 and line.lower() not in seen:
            seen.add(line.lower())
            lines.append(line)
    return lines[:limit]


def explain_prompt(command: str, personality: str) -> tuple[str, str]:
    desc = content.PERSONALITIES.get(personality, content.PERSONALITIES["Cheerful"])
    system = (f"You explain Linux shell commands to beginners. Tone: {desc}, but clear first. "
              "Be concise (under 140 words). Say what each part does, then flag anything risky. Plain text, no markdown.")
    return system, f"Explain this command: {command}"
