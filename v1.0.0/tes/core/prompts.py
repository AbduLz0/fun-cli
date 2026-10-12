"""Prompt presets.

Two engines:
  * "bash"     – pure Bash PS1, works everywhere with zero installs
  * "starship" – uses Starship if it's installed (we write our *own* config file, never the user's)

Each preset yields (a) shell code for the managed block and (b) preview lines for the GUI,
so what you see in the preview is what gets applied.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import paths
from .themes import nearest_256

# A preview "line" is a list of (text, colour-key) runs. Keys: fg, accent, dim, ok, bad, p0..p15


@dataclass(frozen=True)
class PromptPreset:
    id: str
    name: str
    blurb: str
    engine: str  # "none" | "bash" | "starship"


PRESETS = [
    PromptPreset("keep", "Keep my current prompt", "Don't touch my prompt at all.", "none"),
    PromptPreset("minimal", "Minimal", "Folder name and a prompt symbol that turns red when a command fails.", "bash"),
    PromptPreset("classic", "Classic", "user@host:folder$ - familiar, with a splash of colour.", "bash"),
    PromptPreset("two_line", "Two-line", "Info on top, a clean line to type on below.", "bash"),
    PromptPreset("starship_clean", "Starship - Clean", "Modern one-liner. Needs Starship installed.", "starship"),
    PromptPreset("starship_two_line", "Starship - Two-line", "Roomy two-line layout. Needs Starship installed.", "starship"),
]
BY_ID = {p.id: p for p in PRESETS}


def get(preset_id: str) -> PromptPreset:
    return BY_ID.get(preset_id, BY_ID["keep"])


# ------------------------------------------------------------------ preview
def preview_lines(s: dict, user: str = "you", host: str = "zorin", cwd: str = "~/projects/demo",
                  branch: str = "main") -> list[list[tuple[str, str]]]:
    pid = s.get("prompt_preset", "keep")
    git = bool(s.get("prompt_git", True))
    clock = bool(s.get("prompt_time", False))
    t = [("  14:32", "dim")] if clock else []
    gb = [("  (" + branch + ")", "p5")] if git else []
    folder = cwd.rsplit("/", 1)[-1]
    sample = [[("$ ", "dim"), ("ls", "fg")], [("src  README.md  notes.txt", "p4")]]

    if pid in ("minimal", "starship_clean"):
        if pid == "starship_clean":
            first = [(cwd, "accent")] + [(" " + branch, "p5")] * git + t[:1]
            prompt = [first, [("❯ ", "ok"), ("git status", "fg")]]
        else:
            prompt = [[(folder, "accent")] + gb + t, [("❯ ", "ok"), ("git status", "fg")]]
        bad = [[(folder, "accent")] + gb + t, [("❯ ", "bad"), ("oops-typo", "fg")]]
        return sample + [[]] + prompt + [[("command not found", "dim")]] + bad
    if pid == "classic":
        a = [(f"{user}@{host}", "accent"), (":", "dim"), (cwd, "p4")] + [(" (" + branch + ")", "p5")] * git + t
        return sample + [[]] + [a + [("$ ", "fg"), ("git status", "fg")]]
    if pid in ("two_line", "starship_two_line"):
        top = [("┌─[", "dim"), (f"{user}@{host}", "accent"), ("]─[", "dim"), (cwd, "p4"), ("]", "dim")] + gb + t
        return sample + [[]] + [top, [("└─", "dim"), ("❯ ", "ok"), ("git status", "fg")]]
    # keep
    return sample + [[]] + [[(f"{user}@{host}", "p2"), (":", "fg"), ("~", "p4"), ("$ ", "fg"), ("echo 'your prompt, unchanged'", "fg")]]


# ------------------------------------------------------------------ bash code
def _bash_function(pid: str, accent: str, git: bool, clock: bool) -> str:
    a = nearest_256(accent)
    # Escapes below are PS1 escapes (interpreted by Bash when drawing the prompt).
    head = [
        "_tes_set_prompt() {",
        "  local ec=$?",
        f"  local a='\\[\\e[1;38;5;{a}m\\]' r='\\[\\e[0m\\]' d='\\[\\e[2m\\]' b='\\[\\e[34m\\]' m='\\[\\e[35m\\]'",
        "  local sym='\\[\\e[32m\\]'",
        "  (( ec == 0 )) || sym='\\[\\e[31m\\]'",
        "  local g='' br=''",
    ]
    if git:
        head += [
            "  br=$(git symbolic-ref --short -q HEAD 2>/dev/null) && {",
            # Branch names are untrusted (a repo can name a branch $(...)); Bash expands PS1, so whitelist characters.
            "    br=${br//[^[:alnum:]._\\/-]/?}",
            "    g=\" ${m}(${br})${r}\"",
            "  }",
        ]
    clk = " ${d}\\A${r}" if clock else ""
    if pid == "minimal":
        ps1 = '"${a}\\W${r}${g}' + clk + '\\n${sym}❯${r} "'
    elif pid == "classic":
        ps1 = '"${a}\\u@\\h${r}:${b}\\w${r}${g}' + clk + '\\\\$ "'
    else:  # two_line
        ps1 = '"${d}┌─[${r}${a}\\u@\\h${r}${d}]─[${r}${b}\\w${r}${d}]${r}${g}' + clk + '\\n${d}└─${r}${sym}❯${r} "'
    head.append(f"  PS1={ps1}")
    head.append("}")
    return "\n".join(head)


_HOOK = r'''if [[ "${PROMPT_COMMAND[*]-}" != *_tes_set_prompt* ]]; then
  if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then
    PROMPT_COMMAND=(_tes_set_prompt "${PROMPT_COMMAND[@]}")
  else
    PROMPT_COMMAND="_tes_set_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
  fi
fi'''


def bash_snippet(s: dict) -> list[str]:
    """Lines (without markers) that install the chosen prompt. Empty list = leave the prompt alone."""
    pid = s.get("prompt_preset", "keep")
    p = get(pid)
    if p.engine == "bash":
        fn = _bash_function(pid, s["accent"], bool(s.get("prompt_git", True)), bool(s.get("prompt_time", False)))
        return ["if [[ $- == *i* ]]; then", *["  " + l for l in fn.split("\n")], *["  " + l for l in _HOOK.split("\n")], "fi"]
    if p.engine == "starship":
        cfg = f'"{paths.SHELL_CONFIG_DIR}/starship.toml"'
        return [
            "if [[ $- == *i* ]] && command -v starship >/dev/null 2>&1; then",
            f"  export STARSHIP_CONFIG={cfg}",
            '  eval "$(starship init bash)"',
            "fi",
        ]
    return []


# ------------------------------------------------------------------ starship
def starship_toml(s: dict) -> str | None:
    pid = s.get("prompt_preset", "keep")
    if get(pid).engine != "starship":
        return None
    ac = s["accent"]
    git = bool(s.get("prompt_git", True))
    clock = bool(s.get("prompt_time", False))
    mods = "$directory" + ("$git_branch$git_status" if git else "") + ("$time" if clock else "")
    if pid == "starship_clean":
        fmt = mods + "$character"
    else:
        fmt = "[┌─](dim white)" + mods + "\n[└─](dim white)$character"
    out = [
        "# Generated by Terminal Experience Studio - changes here are overwritten.",
        "# Your own ~/.config/starship.toml is never touched.",
        "add_newline = false",
        f'format = """{fmt}"""',
        "",
        "[character]",
        'success_symbol = "[❯](bold green)"',
        'error_symbol = "[❯](bold red)"',
        "",
        "[directory]",
        f'style = "bold {ac}"',
        "truncation_length = 3",
        "",
    ]
    if git:
        out += ["[git_branch]", 'format = "[$branch]($style) "', 'style = "purple"', "",
                "[git_status]", 'format = "[$all_status$ahead_behind]($style) "', 'style = "yellow"', ""]
    if clock:
        out += ["[time]", "disabled = false", 'format = "[$time]($style) "', 'time_format = "%H:%M"', 'style = "dimmed white"', ""]
    return "\n".join(out)
