"""Optional AI plumbing (no GUI).

Rules: the app is fully useful without any of this. AI is only called when the user asks
(a button, or the `tes` command). Nothing here runs at shell startup: greetings and roasts are
generated ahead of time and cached in plain files, so opening a terminal never waits on a network.

API keys are never written to settings.json or ~/.bashrc. They live in memory, or (opt-in) in the
desktop keyring via `secret-tool` (libsecret), or in the TES_API_KEY environment variable for the CLI.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request

from . import content
from .paths import VERSION

# Some providers (Groq sits behind Cloudflare) reject Python's default User-Agent with HTTP 403 / error 1010.
USER_AGENT = f"fun-cli/{VERSION} (+https://github.com/AbduLz0/fun-cli)"

PROVIDERS = {
    "Groq": {
        "url": "https://console.groq.com/keys",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-120b", "needs_key": True,
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
def _explain_http_error(code: int, body: str) -> str:
    low = body.lower()
    if code == 403 and ("1010" in low or "cloudflare" in low or "<html" in low):
        return ("The provider's firewall (Cloudflare) blocked the request - this is not a bad key. "
                "Try again in a minute, check any VPN or proxy, or switch provider.")
    if code in (401, 403):
        return f"The provider rejected the API key (HTTP {code}). Check it's correct and still active."
    if code == 404:
        return "The provider doesn't know that model name. Check the Model field."
    if code == 429:
        return "Rate limit reached (HTTP 429). Wait a moment and try again."
    return f"The provider answered HTTP {code}. {body[:200]}"


def chat_messages(provider: str, model: str, key: str, messages: list[dict], max_tokens: int = 400,
                  temperature: float = 0.8, timeout: int = 40) -> str:
    """One blocking chat completion over a full message list (call from a worker thread)."""
    info = PROVIDERS.get(provider)
    if info is None:
        raise AIError("Unknown provider.")
    if info["needs_key"] and not key:
        raise AIError("Add an API key first.")
    model = model or info["model"]
    payload = {"model": model, "temperature": temperature, "messages": messages, "max_tokens": max_tokens}
    if provider == "Groq" and "gpt-oss" in model:
        # Reasoning models spend tokens "thinking"; keep that small so the visible answer isn't cut off.
        payload["reasoning_effort"] = "low"
        payload["max_tokens"] = max(max_tokens * 2, 600)
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(info["endpoint"], data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = str(data["choices"][0]["message"].get("content") or "").strip()
    except urllib.error.HTTPError as exc:
        raise AIError(_explain_http_error(exc.code, exc.read().decode("utf-8", "replace"))) from exc
    except urllib.error.URLError as exc:
        local = " Is Ollama running?" if "localhost" in info["endpoint"] else " Check your internet connection."
        raise AIError(f"Couldn't reach the provider.{local}") from exc
    except (KeyError, IndexError, ValueError, AttributeError) as exc:
        raise AIError("The provider sent a reply we couldn't read.") from exc
    if not text:
        raise AIError("The model sent an empty reply (it may have spent its whole budget thinking). Try again.")
    return text


def chat(provider: str, model: str, key: str, system: str, user: str, max_tokens: int = 300,
         temperature: float = 0.8, timeout: int = 40) -> str:
    return chat_messages(provider, model, key, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                         max_tokens, temperature, timeout)


# ------------------------------------------------------------------ older single-purpose prompts
def explain_prompt(command: str, personality: str) -> tuple[str, str]:
    desc = content.PERSONALITIES.get(personality, content.PERSONALITIES["Cheerful"])
    system = (f"You explain Linux shell commands to beginners. Tone: {desc}, but clear first. "
              "Be concise (under 140 words). Say what each part does, then flag anything risky. Plain text, no markdown.")
    return system, f"Explain this command: {command}"


def parse_pack(raw: str, limit: int = 20) -> list[str]:
    """Plain-text lines (used by tests/older callers). Newer code uses core.pack.parse_ai_lines."""
    lines, seen = [], set()
    for line in raw.splitlines():
        line = line.strip().lstrip("-*•0123456789.) ").strip().strip('"')
        line = content.clean_line(line, 90)
        if len(line) >= 4 and line.lower() not in seen:
            seen.add(line.lower())
            lines.append(line)
    return lines[:limit]
