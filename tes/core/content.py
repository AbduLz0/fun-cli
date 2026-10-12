"""Built-in content: companion faces, small ASCII art pieces, offline greetings, personalities."""
from __future__ import annotations

import re

FACES = [
    ("Happy", "(•‿•)"), ("Calm", "(◑‿◐)"), ("Sunny", "(-‿◦☀)"),
    ("Crying", "ಥ‿ಥ"), ("Hug", "(づ ◕‿◕ )づ"), ("Cheering", "٩(◕‿◕)۶"),
    ("Sleepy", "(≚ᄌ≚) ƶ Ƶ"), ("Cool", "(⌐■_■)"),
    ("Deal with it", "( •_•)>⌐■-■"), ("Shrug", "ツ"),
    ("Surprised", "⊙▂⊙"), ("Confused", "( ؕؔʘ̥ ه ؔʘ̥ )?"),
    ("Angry", "(ง'̀-'́)ง"), ("Facepalm", "(シ_ _)シ"),
    ("Love", "（。ˇ ⊖ˇ）♡"), ("Thinking", "( ͡° ͜ʖ ͡° )"),
    ("Excited", "(ᵒ̤̑ ₀̑ ᵒ̤̑)wow!*✰"), ("Cat", "=＾● ⋏ ●＾="),
    ("Bear", "(✪㉨✪)"), ("Tired", "(－_－) zzZ"),
    ("Victory", "(✌ﾟ∀ﾟ)☞"), ("Working hard", "ᕙ(⇀‸↼‶)ᕗ"),
    ("Tea break", "( ˘▽˘)っ♨"), ("Oops", "ಠ_ರೃ"),
]

# Faces the dashboard companion cycles through while idle (all plain, widely-rendered glyphs).
IDLE_FACES = ["(•‿•)", "(◑‿◐)", "(⌐■_■)", "(づ ◕‿◕ )づ", "٩(◕‿◕)۶", "( ˘▽˘)っ♨"]
BLINK_FACE = "(-‿-)"

ART_GALLERY = {
    "Tux": r"""
    .--.
   |o_o |
   |:_/ |
  //   \ \
 (|     | )
/'\_   _/`\
\___)=(___/
""",
    "Cat": r"""
 /\_/\
( o.o )
 > ^ <
""",
    "Coffee": r"""
    ( (
     ) )
  .______.
  |      |]
  \      /
   `----'
""",
    "Rocket": r"""
     ^
    /^\
    |-|
    | |
   /| |\
  / | | \
 |__|_|__|
    /_\
""",
    "Terminal": r"""
 .------------------.
 | >_               |
 |                  |
 |  hello, world    |
 '------------------'
""",
}

OFFLINE_GREETINGS = [
    "Ready when you are.",
    "Tip: press Tab twice to see every completion.",
    "Tip: Ctrl+R searches your command history.",
    "Tip: type !! to repeat your last command.",
    "Tip: 'cd -' jumps back to the previous folder.",
    "Tip: Ctrl+L clears the screen without losing history.",
    "Tip: 'man <command>' opens the manual for anything.",
    "Tip: 'ls -lah' shows hidden files with friendly sizes.",
    "Tip: Ctrl+A and Ctrl+E jump to the start and end of a line.",
    "Tip: Ctrl+C stops almost anything that's running.",
    "Take a breath. Then take sudo. Carefully.",
    "You've got this.",
    "The terminal is just a conversation. Say something nice.",
    "Small commands, big adventures.",
]

PERSONALITIES = {
    "Cheerful": "warm, upbeat and encouraging, like a friendly sidekick",
    "Calm": "calm, gentle and minimalist, like a quiet zen garden",
    "Witty": "dry and witty with light, harmless humour",
    "Wise mentor": "a patient Linux mentor who shares one practical tip at a time",
    "Pirate": "a cheerful pirate captain (light touch, still easy to read)",
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean_line(text: str, limit: int = 100) -> str:
    """Strip control characters (incl. ESC) so text from any source can never inject terminal escapes."""
    return _CONTROL.sub("", text).strip()[:limit]


def clean_art(text: str, max_lines: int = 60, max_cols: int = 160) -> str:
    lines = [_CONTROL.sub("", l).rstrip() for l in text.replace("\t", "    ").splitlines()]
    lines = [l[:max_cols] for l in lines][:max_lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)
