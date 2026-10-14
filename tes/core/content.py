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

# ---------------------------------------------------------------- emotions
# The AI tags what it says with one of these names; the app turns the tag into a face.
EMOTIONS = {
    "happy": "(•‿•)", "excited": "٩(◕‿◕)۶", "proud": "(ง •̀_•́)ง", "cool": "(⌐■_■)",
    "calm": "(◑‿◐)", "love": "(♥‿♥)", "sad": "(╥_╥)", "angry": "(ò_ó)",
    "shocked": "(⊙_⊙)", "confused": "(◔_◔)", "thinking": "(¬_¬)", "smug": "(¬‿¬)",
    "sleepy": "(-_-) zzZ", "mischievous": "(◕‿↼)", "laugh": "(≧▽≦)", "dead": "(✖_✖)",
    "facepalm": "(－‸ლ)",
}
EMOTION_NAMES = list(EMOTIONS)


def face_for(emotion: str, default: str = "happy") -> str:
    return EMOTIONS.get((emotion or "").strip().lower(), EMOTIONS[default])


# ---------------------------------------------------------------- built-in lines
# (emotion, text, is_tip) - tips can be switched off without losing the friendly lines.
BUILTIN_GREETINGS = [
    ("happy", "Ready when you are.", False),
    ("proud", "You've got this.", False),
    ("calm", "The terminal is just a conversation. Say something nice.", False),
    ("excited", "Small commands, big adventures.", False),
    ("love", "Welcome back. I kept your cursor warm.", False),
    ("sleepy", "Coffee first, commands second.", False),
    ("happy", "Today's forecast: 100% chance of working commands.", False),
    ("cool", "Another day, another directory.", False),
    ("smug", "Take a breath. Then take sudo. Carefully.", False),
    ("calm", "No rush. I'll be here, blinking.", False),
    ("thinking", "Tip: press Tab twice to see every completion.", True),
    ("happy", "Tip: Ctrl+R searches your command history.", True),
    ("cool", "Tip: type !! to repeat your last command.", True),
    ("thinking", "Tip: 'cd -' jumps back to the previous folder.", True),
    ("calm", "Tip: Ctrl+L clears the screen without losing history.", True),
    ("proud", "Tip: 'man <command>' opens the manual for anything.", True),
    ("happy", "Tip: 'ls -lah' shows hidden files with friendly sizes.", True),
    ("cool", "Tip: Ctrl+A and Ctrl+E jump to the start and end of a line.", True),
    ("calm", "Tip: Ctrl+C stops almost anything that's running.", True),
]
# Kept for older callers: plain text only.
OFFLINE_GREETINGS = [t for _e, t, _tip in BUILTIN_GREETINGS]

# Roasts about the *command you typed*, never about who you are. {cmd} is replaced at runtime.
ROAST_LEVELS = {
    "Gentle teasing": [
        ("confused", "Hmm, '{cmd}'? I don't know that one. Typo?"),
        ("happy", "'{cmd}' isn't a command, but I admire the confidence."),
        ("thinking", "Did you mean something else? Keyboards are hard."),
        ("calm", "No such command: {cmd}. It happens to the best of us."),
        ("laugh", "Bless. '{cmd}' does not exist. Try again!"),
        ("smug", "Close, but '{cmd}' isn't it."),
        ("love", "I still believe in you, even though '{cmd}' is not real."),
        ("calm", "Tab completion exists, friend. Just saying."),
        ("happy", "'{cmd}'... bold. Wrong, but bold."),
    ],
    "Spicy": [
        ("smug", "'{cmd}'? Did your cat walk across the keyboard?"),
        ("laugh", "Ah yes, '{cmd}', the famous command that has never existed."),
        ("smug", "I've seen better typing from a toaster. '{cmd}' isn't a thing."),
        ("confused", "Are you typing with oven mitts? '{cmd}' not found."),
        ("thinking", "'{cmd}' not found. Neither is your accuracy."),
        ("smug", "Autocomplete is free, you know. '{cmd}' is not a command."),
        ("laugh", "Brave of you to ship '{cmd}' straight to production."),
        ("angry", "Read the man page. Or any page. '{cmd}' isn't real."),
        ("smug", "That's not a command, that's a cry for help: '{cmd}'."),
        ("dead", "'{cmd}'. Wow. Just wow."),
    ],
    "Unhinged": [
        ("dead", "'{cmd}'?? The shell just filed a restraining order against your fingers."),
        ("laugh", "I asked the kernel about '{cmd}'. It laughed, then cried, then rebooted."),
        ("shocked", "Bold of you to assume '{cmd}' is a command. Bold. Wrong. Spectacular."),
        ("mischievous", "Somewhere a sysadmin felt a disturbance in the force. '{cmd}'."),
        ("smug", "'{cmd}' not found. Neither is your will to learn spelling."),
        ("dead", "Your keyboard is crying. I can hear it. '{cmd}'."),
        ("angry", "I've seen cats type better. Actual cats. Named Steve. '{cmd}'."),
        ("laugh", "Sir, this is a terminal, not a Ouija board. '{cmd}' summons nothing."),
        ("shocked", "'{cmd}'?! I'm calling the Linux police. They're also confused."),
        ("mischievous", "Fun fact: '{cmd}' has never worked and never will. Congrats on the streak."),
        ("smug", "Even Windows wouldn't recognise '{cmd}', and it recognises everything."),
        ("dead", "Plot twist: the command was your confidence all along. Not found."),
    ],
}
DEFAULT_ROAST_LEVEL = "Spicy"

PERSONALITIES = {
    "Cheerful": "warm, upbeat and encouraging, like a friendly sidekick",
    "Calm": "calm, gentle and minimalist, like a quiet zen garden",
    "Witty": "dry and witty with light, harmless humour",
    "Wise mentor": "a patient Linux mentor who shares one practical tip at a time",
    "Pirate": "a cheerful pirate captain (light touch, still easy to read)",
    "Unhinged": ("chaotic, theatrical and absurdly savage about the user's *mistakes* (typos, wrong commands, "
                 "bad ideas). It is playful, never cruel: no slurs, no profanity, no jokes about the user's identity, "
                 "body, health or background, and no real threats. It still gives correct, useful answers."),
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


def clean_text(text: str, limit: int = 160) -> str:
    """Single line, no control characters - for anything that will be printed in a terminal."""
    return clean_line(" ".join(text.split()), limit)
