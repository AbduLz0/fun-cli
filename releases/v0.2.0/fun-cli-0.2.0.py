#!/usr/bin/env python3
"""
Terminal Experience Studio
A friendly, animated Linux terminal customization studio.

Safe by default: preview first, back up ~/.bashrc, then replace only
this app's clearly marked block.
"""
import json
import os
import shutil
import socket
import subprocess
import urllib.request
import urllib.error
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime

APP_NAME = "Terminal Experience Studio"
CONFIG_DIR = Path.home() / ".config" / "terminal-experience-studio"
CONFIG_FILE = CONFIG_DIR / "settings.json"
BASHRC = Path.home() / ".bashrc"
BACKUP_GLOB = ".bashrc.terminal-experience-backup-*"
START_MARK = "# >>> Terminal Experience Studio >>>"
END_MARK = "# <<< Terminal Experience Studio <<<"

# ----------------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------------
BG          = "#0b0f14"
BG_2        = "#0f151d"
PANEL       = "#161d27"
PANEL_2     = "#1c2531"
PANEL_3     = "#232e3c"
BORDER      = "#26303d"
TEXT        = "#e7eef5"
TEXT_MUTED  = "#8b98a8"
TEXT_DIM    = "#5d6b7c"
ACCENT      = "#7bd88f"
ACCENT_DIM  = "#4b9b69"
ACCENT_HOV  = "#5cb478"
ACCENT_2    = "#66c9ff"
WARN        = "#f0b35a"
DANGER      = "#ef6f6c"

FONT       = ("Sans", 10)
FONT_SM    = ("Sans", 9)
FONT_BOLD  = ("Sans", 10, "bold")
FONT_TITLE = ("Sans", 22, "bold")
FONT_H1    = ("Sans", 15, "bold")
FONT_H2    = ("Sans", 12, "bold")
FONT_MONO  = ("Monospace", 11)
FONT_MONO_L= ("Monospace", 22, "bold")

# How long (ms) to let the AI test run before giving up and stopping the spinner
AI_REQUEST_TIMEOUT_MS = 25000
# Network timeout for the actual HTTP call
AI_SOCKET_TIMEOUT = 20

# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
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

DEFAULTS = {
    "enabled": True,
    "name": "Terminal friend",
    "greeting": "Welcome back, {user}!",
    "face": "(•‿•)",
    "show_date": True,
    "show_host": False,
    "fastfetch": False,
    "prompt_style": "Keep my existing prompt",
    "provider": "Groq",
    "model": "llama-3.3-70b-versatile",
    "ai_enabled": False,
    "ai_greeting": False,
    "custom_motd": "",
    "accent": "#7bd88f",
}

PROVIDERS = {
    "Groq": {
        "url": "https://console.groq.com/keys",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
    },
    "OpenAI": {
        "url": "https://platform.openai.com/api-keys",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
    "OpenRouter": {
        "url": "https://openrouter.ai/keys",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openai/gpt-4o-mini",
    },
}

TERMINAL_DETECT = [
    ("GNOME Terminal", "gnome-terminal"),
    ("Kitty", "kitty"),
    ("Konsole", "konsole"),
    ("Alacritty", "alacritty"),
    ("Xfce Terminal", "xfce4-terminal"),
    ("Tilix", "tilix"),
    ("WezTerm", "wezterm"),
]


# ----------------------------------------------------------------------------
# Settings I/O
# ----------------------------------------------------------------------------
def load_settings():
    data = DEFAULTS.copy()
    try:
        data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _shell_escape(s):
    return (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
         .replace("$", "\\$")
         .replace("`", "\\`")
    )


def make_shell_block(settings):
    if not settings.get("enabled", True):
        return (
            START_MARK
            + "\n# Startup greeting disabled in Terminal Experience Studio.\n"
            + END_MARK
        )

    lines = [START_MARK,
             "# Managed by Terminal Experience Studio. Edit settings in the GUI."]

    if settings.get("show_date", True):
        lines.append(
            'printf "\\033[1;32m%s\\033[0m  " "$(date \'+%a %d %b %H:%M\')"'
        )

    face = settings.get("face", "(•‿•)")
    greeting = settings.get("greeting", "Welcome back, {user}!").replace(
        "{user}", "__TES_USER_PLACEHOLDER__"
    )
    greeting = _shell_escape(greeting).replace(
        "__TES_USER_PLACEHOLDER__", "${USER}"
    )
    lines.append(
        'printf "\\033[1;36m%s\\033[0m  %s\\n" "'
        + _shell_escape(face) + '" "' + greeting + '"'
    )

    custom = settings.get("custom_motd", "").strip()
    if custom:
        for line in custom.splitlines()[:5]:
            lines.append('printf "%s\\n" "' + _shell_escape(line) + '"')

    if settings.get("show_host", False):
        lines.append(
            'printf "  Host: %s | Shell: %s\\n" "$(hostname)" "${SHELL##*/}"'
        )

    if settings.get("fastfetch", False):
        lines.append(
            'if command -v fastfetch >/dev/null 2>&1; then fastfetch; fi'
        )

    lines.append(END_MARK)
    return "\n".join(lines)


def preview_text(settings):
    user = os.environ.get("USER", "you")
    greeting = settings.get("greeting", "Welcome back, {user}!").replace(
        "{user}", user
    )
    out = []
    if settings.get("show_date", True):
        out.append(datetime.now().strftime("%a %d %b %H:%M"))
    out.append(f'{settings.get("face", "(•‿•)")}  {greeting}')
    if settings.get("custom_motd", "").strip():
        out.extend(settings["custom_motd"].strip().splitlines()[:5])
    if settings.get("show_host", False):
        out.append(
            f'Host: {os.uname().nodename} | '
            f'Shell: {Path(os.environ.get("SHELL", "/bin/bash")).name}'
        )
    if settings.get("fastfetch", False):
        out.append("[Fastfetch will run here if installed]")
    return "\n".join(out)


def list_backups():
    if not BASHRC.parent.exists():
        return []
    return sorted(BASHRC.parent.glob(BACKUP_GLOB), reverse=True)


# ----------------------------------------------------------------------------
# Small UI helpers / custom widgets
# ----------------------------------------------------------------------------
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def draw_gradient(canvas, width, height, c1, c2):
    """Vertical gradient from c1 (top) to c2 (bottom)."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    for i in range(height):
        t = i / max(height - 1, 1)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        canvas.create_line(0, i, width, i,
                           fill=f"#{r:02x}{g:02x}{b:02x}")


class Card(tk.Frame):
    """A flat card: solid panel colour, subtle border, optional accent strip."""

    def __init__(self, master, accent=None, pad=(16, 16), **kw):
        super().__init__(master, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDER, bd=0, **kw)
        if accent:
            tk.Frame(self, bg=accent, height=3).pack(fill="x", side="top")
        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill="both", expand=True,
                       padx=pad[0], pady=pad[1])


def make_button(parent, text, command=None, kind="ghost", font=FONT_BOLD):
    palette = {
        "primary": (ACCENT_DIM, ACCENT_HOV, "#06210f"),
        "ghost":   (PANEL_2,   PANEL_3,   TEXT),
        "subtle":  (PANEL,     PANEL_2,   TEXT_MUTED),
        "danger":  ("#4a2020", "#632c2c", "#ffd7d7"),
    }
    bg, hover, fg = palette.get(kind, palette["ghost"])
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
        relief="flat", bd=0, padx=16, pady=9, cursor="hand2",
        font=font, highlightthickness=0,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def pulse_widget(widget, base=22, peak=30, step=2, delay=18):
    """Gentle font-size 'breathing' animation for a label."""
    def run(size, direction):
        try:
            widget.configure(font=("Monospace", size, "bold"))
        except tk.TclError:
            return
        if direction > 0 and size < peak:
            widget.after(delay, lambda: run(size + step, 1))
        elif direction < 0 and size > base:
            widget.after(delay, lambda: run(size - step, -1))
        else:
            try:
                widget.configure(font=("Monospace", base, "bold"))
            except tk.TclError:
                pass
    run(base, 1)


class TypewriterPreview(tk.Text):
    """Read-only text widget that types its content in character by character."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._type_job = None
        self._debounce_job = None
        self._full = ""
        self._idx = 0

    def show(self, text, animate=True):
        self._full = text
        if self._debounce_job:
            try:
                self.after_cancel(self._debounce_job)
            except tk.TclError:
                pass
        if self._type_job:
            try:
                self.after_cancel(self._type_job)
            except tk.TclError:
                pass
        if animate:
            self._debounce_job = self.after(140, self._start)
        else:
            self._start()

    def _start(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self._idx = 0
        self._type()

    def _type(self):
        if self._idx >= len(self._full):
            self.configure(state="disabled")
            self._type_job = None
            return
        chunk = self._full[self._idx:self._idx + 2]
        self.insert("end", chunk)
        self.see("end")
        self._idx += 2
        self._type_job = self.after(14, self._type)


class Toast(tk.Toplevel):
    """Small animated notification that fades in and out in the corner."""

    def __init__(self, master, text, kind="info", duration=2800):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        colors = {
            "info": ACCENT_2,
            "success": ACCENT,
            "warn": WARN,
            "error": DANGER,
        }
        accent = colors.get(kind, ACCENT_2)

        wrapper = tk.Frame(self, bg=PANEL_2, highlightthickness=1,
                           highlightbackground=accent)
        wrapper.pack(fill="both", expand=True)
        tk.Frame(wrapper, bg=accent, width=4).pack(side="left", fill="y")
        tk.Label(
            wrapper, text=text, bg=PANEL_2, fg=TEXT, font=FONT_SM,
            padx=14, pady=10, wraplength=320, justify="left",
        ).pack(side="left", fill="both", expand=True)

        self.update_idletasks()
        w = max(self.winfo_reqwidth(), 240)
        h = self.winfo_reqheight()
        try:
            mx = master.winfo_rootx() + master.winfo_width()
            my = master.winfo_rooty() + master.winfo_height()
        except tk.TclError:
            mx, my = self.winfo_screenwidth(), self.winfo_screenheight()
        x = mx - w - 26
        y = my - h - 26
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._alpha = 0.0
        self._fade_in(duration)

    def _fade_in(self, duration):
        if self._alpha < 0.96:
            self._alpha = min(0.96, self._alpha + 0.08)
            try:
                self.attributes("-alpha", self._alpha)
            except tk.TclError:
                pass
            self.after(16, lambda: self._fade_in(duration))
        else:
            self.after(duration, self._fade_out)

    def _fade_out(self):
        if self._alpha > 0.0:
            self._alpha = max(0.0, self._alpha - 0.08)
            try:
                self.attributes("-alpha", self._alpha)
            except tk.TclError:
                self.destroy()
                return
            self.after(16, self._fade_out)
        else:
            self.destroy()


# ----------------------------------------------------------------------------
# Main application
# ----------------------------------------------------------------------------
class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1080x780")
        self.minsize(940, 680)
        self.configure(bg=BG)

        self.settings = load_settings()
        self.api_key = ""

        # AI state — all kept here so we can always stop the spinner cleanly
        self._ai_spin = 0
        self._ai_spin_active = False
        self._ai_spin_deadline_job = None
        self._ai_request_generation = 0  # ignore results from stale requests

        self._build_style()
        self._build_ui()
        self._load_widgets()
        self.refresh_preview(animate=False)

        # Ambient animations
        self._tick_clock()
        self._ambient_pulse()

        # Keyboard shortcuts
        self.bind("<Control-s>", lambda e: self.save_only())
        self.bind("<Control-S>", lambda e: self.save_only())
        self.bind("<Control-p>", lambda e: self.refresh_preview())
        self.bind("<Control-P>", lambda e: self.refresh_preview())
        self.bind("<Control-Return>", lambda e: self.apply_bash())
        self.bind("<Control-r>", lambda e: self.refresh_backups())
        self.bind("<Control-R>", lambda e: self.refresh_backups())
        self.bind("<Escape>", lambda e: self._cancel_ai_spinner())

    # ------------------------------------------------------------------ style
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=FONT)

        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=TEXT_MUTED,
                        font=FONT_SM)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("PanelMuted.TLabel", background=PANEL,
                        foreground=TEXT_MUTED, font=FONT_SM)

        style.configure("TNotebook", background=BG, borderwidth=0,
                        tabmargins=(4, 4, 4, 0))
        style.configure("TNotebook.Tab", padding=(18, 11),
                        background=PANEL, foreground=TEXT_MUTED,
                        font=FONT_BOLD, borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", PANEL_2)],
                  foreground=[("selected", ACCENT)])

        style.configure("TCheckbutton", background=PANEL, foreground=TEXT,
                        font=FONT, focuscolor=PANEL)
        style.map("TCheckbutton",
                  background=[("active", PANEL)],
                  foreground=[("active", ACCENT)])

        style.configure("TRadiobutton", background=PANEL, foreground=TEXT)

        style.configure("TCombobox", padding=6, fieldbackground=PANEL_2,
                        background=PANEL_2, foreground=TEXT,
                        arrowcolor=TEXT_MUTED, bordercolor=BORDER)
        style.map("TCombobox",
                  fieldbackground=[("readonly", PANEL_2)],
                  foreground=[("readonly", TEXT)])

        style.configure("TEntry", padding=8, fieldbackground=PANEL_2,
                        bordercolor=BORDER, foreground=TEXT,
                        insertcolor=ACCENT)
        style.configure("TSpinbox", padding=6, fieldbackground=PANEL_2,
                        foreground=TEXT)

        style.configure("Horizontal.TProgressbar",
                        background=ACCENT, troughcolor=PANEL_2,
                        bordercolor=PANEL_2, lightcolor=ACCENT,
                        darkcolor=ACCENT)

    # --------------------------------------------------------------------- UI
    def _build_ui(self):
        self._build_header()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=22, pady=(12, 6))

        self.dash_tab = tk.Frame(self.notebook, bg=BG)
        self.welcome_tab = tk.Frame(self.notebook, bg=BG)
        self.look_tab = tk.Frame(self.notebook, bg=BG)
        self.prompt_tab = tk.Frame(self.notebook, bg=BG)
        self.ai_tab = tk.Frame(self.notebook, bg=BG)
        self.safety_tab = tk.Frame(self.notebook, bg=BG)

        self.notebook.add(self.dash_tab, text="  Dashboard  ")
        self.notebook.add(self.welcome_tab, text="  Welcome & MOTD  ")
        self.notebook.add(self.look_tab, text="  Appearance  ")
        self.notebook.add(self.prompt_tab, text="  Prompt Designer  ")
        self.notebook.add(self.ai_tab, text="  AI Companion  ")
        self.notebook.add(self.safety_tab, text="  Safety & Recovery  ")

        self._build_dashboard()
        self._build_welcome()
        self._build_look()
        self._build_prompt()
        self._build_ai()
        self._build_safety()

        self._build_footer()

    # ---------------------------------------------------------------- header
    def _build_header(self):
        header = tk.Frame(self, bg=BG_2, height=92)
        header.pack(fill="x")
        header.pack_propagate(False)

        canvas = tk.Canvas(header, bg=BG_2, highlightthickness=0, height=92)
        canvas.pack(fill="both", expand=True)
        canvas.update_idletasks()
        draw_gradient(canvas, 1200, 92, "#182433", "#0b0f14")
        canvas.create_line(0, 91, 2400, 91, fill=ACCENT_DIM)

        title_lbl = tk.Label(
            canvas, text=APP_NAME, bg="#182433", fg=TEXT, font=FONT_TITLE,
        )
        title_lbl.place(x=24, y=18)

        sub = tk.Label(
            canvas,
            text="Bring your command line to life — preview first, apply when you're ready.",
            bg="#182433", fg=TEXT_MUTED, font=FONT_SM,
        )
        sub.place(x=26, y=56)

        self.header_pill = tk.Frame(canvas, bg=PANEL_2, highlightthickness=1,
                                    highlightbackground=BORDER)
        self.header_pill.place(relx=1.0, x=-28, y=28, anchor="ne")

        self.pill_dot = tk.Canvas(self.header_pill, width=14, height=14,
                                  bg=PANEL_2, highlightthickness=0)
        self.pill_dot.pack(side="left", padx=(12, 6), pady=8)
        self._pill_dot_id = self.pill_dot.create_oval(
            3, 3, 11, 11, fill=ACCENT, outline=""
        )
        self.pill_label = tk.Label(self.header_pill, text="Active",
                                   bg=PANEL_2, fg=TEXT, font=FONT_SM)
        self.pill_label.pack(side="left", padx=(0, 14), pady=8)

    # -------------------------------------------------------------- dashboard
    def _build_dashboard(self):
        wrap = tk.Frame(self.dash_tab, bg=BG)
        wrap.pack(fill="both", expand=True)

        hero = Card(wrap, accent=ACCENT)
        hero.pack(fill="x", pady=(0, 14))

        tk.Label(hero.body, text="Welcome to your terminal studio",
                 bg=PANEL, fg=TEXT, font=FONT_H1).pack(anchor="w")
        tk.Label(hero.body,
                 text="Everything here is safe: preview, save, and apply whenever you like. "
                      "The app only ever edits its own marked section of ~/.bashrc.",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=780, justify="left").pack(anchor="w", pady=(6, 0))

        quick = tk.Frame(hero.body, bg=PANEL)
        quick.pack(anchor="w", pady=(14, 0))
        make_button(quick, "▶  Preview",
                    lambda: (self.notebook.select(self.welcome_tab),
                             self.refresh_preview()),
                    kind="primary").pack(side="left", padx=(0, 8))
        make_button(quick, "Apply to Bash",
                    self.apply_bash).pack(side="left", padx=(0, 8))
        make_button(quick, "Open settings file",
                    self.open_config_file).pack(side="left", padx=(0, 8))
        make_button(quick, "Open .bashrc",
                    self.open_bashrc).pack(side="left")

        row = tk.Frame(wrap, bg=BG)
        row.pack(fill="x", pady=(0, 14))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        row.columnconfigure(2, weight=1)

        self.stat_face_card = self._stat_card(row, "Current mood", "(•‿•)")
        self.stat_face_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.stat_status_card = self._stat_card(row, "Greeting", "Enabled")
        self.stat_status_card.grid(row=0, column=1, sticky="nsew", padx=8)

        self.stat_backup_card = self._stat_card(row, "Backups", "—")
        self.stat_backup_card.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        tips = Card(wrap, accent=ACCENT_2)
        tips.pack(fill="both", expand=True)
        tk.Label(tips.body, text="Tips & shortcuts",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")
        tip_lines = [
            ("Ctrl + P", "Re-run the live preview"),
            ("Ctrl + S", "Save settings (no shell changes)"),
            ("Ctrl + Enter", "Apply to Bash (backs up first)"),
            ("Ctrl + R", "Refresh the backup list"),
            ("Escape", "Cancel a stuck AI test / dismiss popups"),
        ]
        for key, desc in tip_lines:
            r = tk.Frame(tips.body, bg=PANEL)
            r.pack(fill="x", pady=3)
            tk.Label(r, text=key, bg=PANEL, fg=ACCENT_2, font=FONT_MONO,
                     width=12, anchor="w").pack(side="left")
            tk.Label(r, text=desc, bg=PANEL, fg=TEXT_MUTED,
                     font=FONT_SM).pack(side="left")

    def _stat_card(self, parent, label, value):
        c = Card(parent, pad=(14, 12))
        tk.Label(c.body, text=label.upper(), bg=PANEL, fg=TEXT_DIM,
                 font=("Sans", 8, "bold")).pack(anchor="w")
        v = tk.Label(c.body, text=value, bg=PANEL, fg=ACCENT,
                     font=("Sans", 15, "bold"))
        v.pack(anchor="w", pady=(6, 0))
        c.value_label = v
        return c

    # ----------------------------------------------------------- welcome tab
    def _build_welcome(self):
        canvas = tk.Canvas(self.welcome_tab, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=inner, anchor="nw", tags="inner")

        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure("inner", width=e.width),
        )

        c1 = Card(inner, accent=ACCENT)
        c1.pack(fill="x", pady=(0, 12))
        tk.Label(c1.body, text="Make your terminal say hello",
                 bg=PANEL, fg=TEXT, font=FONT_H1).pack(anchor="w")
        tk.Label(c1.body,
                 text="Choose a mood, write a greeting, and pick what details "
                      "show up when a new Bash shell opens.",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w", pady=(4, 14))

        row = tk.Frame(c1.body, bg=PANEL)
        row.pack(fill="x")
        tk.Label(row, text="Greeting", bg=PANEL, fg=TEXT,
                 font=FONT_BOLD).pack(side="left", padx=(0, 12))
        self.greeting_var = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.greeting_var, font=FONT)
        e.pack(side="left", fill="x", expand=True)
        tk.Label(c1.body,
                 text="Tip: put {user} anywhere you want the Linux username to appear.",
                 bg=PANEL, fg=TEXT_DIM, font=FONT_SM).pack(anchor="w",
                                                           pady=(6, 0))

        c2 = Card(inner, accent=ACCENT_2)
        c2.pack(fill="x", pady=(0, 12))
        tk.Label(c2.body, text="Terminal mood",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")

        face_row = tk.Frame(c2.body, bg=PANEL)
        face_row.pack(fill="x", pady=(10, 0))

        self.face_var = tk.StringVar()
        self.face_combo = ttk.Combobox(
            face_row, textvariable=self.face_var, state="readonly",
            width=30, values=[f"{n}   {f}" for n, f in FACES],
        )
        self.face_combo.pack(side="left")
        self.face_combo.bind("<<ComboboxSelected>>", self._face_changed)

        self.face_sample = tk.Label(face_row, text="(•‿•)",
                                    bg=PANEL, fg=ACCENT,
                                    font=FONT_MONO_L)
        self.face_sample.pack(side="left", padx=22)

        toggles = tk.Frame(c2.body, bg=PANEL)
        toggles.pack(fill="x", pady=(14, 0))
        self.enabled_var = tk.BooleanVar()
        self.date_var = tk.BooleanVar()
        self.host_var = tk.BooleanVar()
        self.fastfetch_var = tk.BooleanVar()

        ttk.Checkbutton(toggles, text="Enable welcome message",
                        variable=self.enabled_var,
                        command=self.refresh_preview).grid(
            row=0, column=0, sticky="w", padx=(0, 24), pady=5)
        ttk.Checkbutton(toggles, text="Show date and time",
                        variable=self.date_var,
                        command=self.refresh_preview).grid(
            row=0, column=1, sticky="w", pady=5)
        ttk.Checkbutton(toggles, text="Show host and shell",
                        variable=self.host_var,
                        command=self.refresh_preview).grid(
            row=1, column=0, sticky="w", padx=(0, 24), pady=5)
        ttk.Checkbutton(toggles, text="Run Fastfetch if installed",
                        variable=self.fastfetch_var,
                        command=self.refresh_preview).grid(
            row=1, column=1, sticky="w", pady=5)

        c3 = Card(inner)
        c3.pack(fill="x", pady=(0, 12))
        tk.Label(c3.body, text="Extra message (optional, up to 5 lines)",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")
        self.motd_text = tk.Text(
            c3.body, height=3, wrap="word", bg=PANEL_2, fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            padx=10, pady=8, font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT_DIM,
        )
        self.motd_text.pack(fill="x", pady=(10, 0))
        self.motd_text.bind("<KeyRelease>", lambda e: self.refresh_preview())

        c4 = Card(inner, accent=ACCENT)
        c4.pack(fill="both", expand=True)
        hdr = tk.Frame(c4.body, bg=PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Live preview", bg=PANEL, fg=TEXT,
                 font=FONT_H2).pack(side="left")
        self.clock_label = tk.Label(hdr, text="", bg=PANEL, fg=TEXT_DIM,
                                    font=FONT_MONO)
        self.clock_label.pack(side="right")

        self.preview = TypewriterPreview(
            c4.body, height=7, wrap="word", bg="#070a0e", fg=ACCENT,
            insertbackground=ACCENT, relief="flat", padx=14, pady=12,
            font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.preview.pack(fill="both", expand=True, pady=(10, 0))
        self.preview.configure(state="disabled")

        self.greeting_var.trace_add("write", lambda *_: self.refresh_preview())

    # -------------------------------------------------------------- look tab
    def _build_look(self):
        wrap = tk.Frame(self.look_tab, bg=BG)
        wrap.pack(fill="both", expand=True)

        c = Card(wrap, accent=ACCENT_2)
        c.pack(fill="x", pady=(0, 12))
        tk.Label(c.body, text="Terminal appearance",
                 bg=PANEL, fg=TEXT, font=FONT_H1).pack(anchor="w")
        tk.Label(c.body,
                 text="Colors, fonts, transparency, and background images are "
                      "configured by each terminal emulator. The app detects "
                      "what you have installed and shows safe next steps.",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w", pady=(4, 12))

        detected = [name for name, exe in TERMINAL_DETECT if shutil.which(exe)]
        if detected:
            tk.Label(c.body, text="Detected on your system:",
                     bg=PANEL, fg=TEXT, font=FONT_BOLD).pack(anchor="w")
            pill_row = tk.Frame(c.body, bg=PANEL)
            pill_row.pack(anchor="w", pady=(6, 0))
            for name in detected:
                pill = tk.Label(pill_row, text=name, bg=PANEL_2, fg=ACCENT,
                                font=FONT_SM, padx=10, pady=5)
                pill.pack(side="left", padx=(0, 6))
        else:
            tk.Label(c.body,
                     text="No known terminal emulator detected on PATH.",
                     bg=PANEL, fg=WARN, font=FONT_SM).pack(anchor="w")

        c2 = Card(wrap)
        c2.pack(fill="x", pady=(0, 12))
        tk.Label(c2.body, text="Shell prompt behaviour",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")
        pr = tk.Frame(c2.body, bg=PANEL)
        pr.pack(fill="x", pady=(10, 0))
        tk.Label(pr, text="Behaviour", bg=PANEL, fg=TEXT,
                 font=FONT).pack(side="left", padx=(0, 12))
        self.prompt_var = tk.StringVar()
        ttk.Combobox(
            pr, textvariable=self.prompt_var, state="readonly", width=44,
            values=["Keep my existing prompt",
                    "Recommend Starship (safe setup guide)"],
        ).pack(side="left")
        tk.Label(c2.body,
                 text="The app does not replace your prompt automatically.",
                 bg=PANEL, fg=TEXT_DIM, font=FONT_SM).pack(anchor="w",
                                                           pady=(8, 0))

        c3 = Card(wrap)
        c3.pack(fill="x", pady=(0, 12))
        tk.Label(c3.body, text="Helpful projects",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")
        links = tk.Frame(c3.body, bg=PANEL)
        links.pack(anchor="w", pady=(10, 0))
        make_button(links, "Starship website",
                    lambda: self.open_url("https://starship.rs/")).pack(
            side="left", padx=(0, 8))
        make_button(links, "Fastfetch project",
                    lambda: self.open_url(
                        "https://github.com/fastfetch-cli/fastfetch")).pack(
            side="left")

        c4 = Card(wrap, accent=WARN)
        c4.pack(fill="both", expand=True)
        tk.Label(c4.body, text="Coming soon — ASCII image converter",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")
        tk.Label(c4.body,
                 text="A future update will let you pick an image, tune its "
                      "width and contrast, preview the ASCII result, and add "
                      "it to your startup display.",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------ prompt tab
    def _build_prompt(self):
        wrap = tk.Frame(self.prompt_tab, bg=BG)
        wrap.pack(fill="both", expand=True)

        c = Card(wrap, accent=ACCENT)
        c.pack(fill="x", pady=(0, 12))
        tk.Label(c.body, text="Prompt designer",
                 bg=PANEL, fg=TEXT, font=FONT_H1).pack(anchor="w")
        tk.Label(c.body,
                 text="Starship is the recommended way to get a beautiful, "
                      "fast, cross-shell prompt. We'll guide you to a safe "
                      "setup without ever overwriting your existing prompt "
                      "behind your back.",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w", pady=(4, 14))

        presets = [
            ("Minimal",   "Just the essentials — user, host, path, and git."),
            ("Developer", "Adds language versions and git status at a glance."),
            ("Powerline", "Nerd-font glyphs with a colourful prompt line."),
            ("Playful",   "Adds the mood face and a short greeting before the prompt."),
        ]
        for name, desc in presets:
            row = tk.Frame(c.body, bg=PANEL_2, highlightthickness=1,
                           highlightbackground=BORDER)
            row.pack(fill="x", pady=4)
            left = tk.Frame(row, bg=PANEL_2)
            left.pack(side="left", fill="x", expand=True, padx=14, pady=10)
            tk.Label(left, text=name, bg=PANEL_2, fg=TEXT,
                     font=FONT_BOLD).pack(anchor="w")
            tk.Label(left, text=desc, bg=PANEL_2, fg=TEXT_MUTED,
                     font=FONT_SM).pack(anchor="w", pady=(2, 0))
            make_button(row, "Learn more", kind="subtle",
                        command=lambda: self.open_url("https://starship.rs/")
                        ).pack(side="right", padx=12, pady=10)

        c2 = Card(wrap, accent=ACCENT_2)
        c2.pack(fill="both", expand=True)
        tk.Label(c2.body, text="Installing Starship (when you're ready)",
                 bg=PANEL, fg=TEXT, font=FONT_H2).pack(anchor="w")
        steps = [
            "1.  Visit starship.rs and follow the short install instructions.",
            "2.  Add the init line to the very end of ~/.bashrc.",
            "3.  Open a new terminal to see it in action.",
            "4.  If anything looks wrong, remove the init line — nothing else changes.",
        ]
        for s in steps:
            tk.Label(c2.body, text=s, bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                     anchor="w", justify="left").pack(anchor="w", pady=3)
        make_button(c2.body, "Open starship.rs", kind="primary",
                    command=lambda: self.open_url("https://starship.rs/")
                    ).pack(anchor="w", pady=(14, 0))

    # ---------------------------------------------------------------- ai tab
    def _build_ai(self):
        wrap = tk.Frame(self.ai_tab, bg=BG)
        wrap.pack(fill="both", expand=True)

        c = Card(wrap, accent=ACCENT_2)
        c.pack(fill="x", pady=(0, 12))
        tk.Label(c.body, text="Give your terminal a personality",
                 bg=PANEL, fg=TEXT, font=FONT_H1).pack(anchor="w")
        tk.Label(c.body,
                 text="AI greetings are completely optional. Your terminal "
                      "works perfectly without an API key. Keys are held only "
                      "in memory for this session — never written to disk.",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w", pady=(4, 14))

        self.provider_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.ai_enabled_var = tk.BooleanVar()
        self.ai_greeting_var = tk.BooleanVar()

        prov_row = tk.Frame(c.body, bg=PANEL)
        prov_row.pack(fill="x", pady=4)
        tk.Label(prov_row, text="Provider", bg=PANEL, fg=TEXT, width=11,
                 anchor="w", font=FONT_BOLD).pack(side="left")
        prov_combo = ttk.Combobox(prov_row, textvariable=self.provider_var,
                                  state="readonly", values=list(PROVIDERS),
                                  width=16)
        prov_combo.pack(side="left")
        prov_combo.bind("<<ComboboxSelected>>", self._provider_changed)

        tk.Label(prov_row, text="Model", bg=PANEL, fg=TEXT,
                 font=FONT_BOLD).pack(side="left", padx=(20, 8))
        ttk.Entry(prov_row, textvariable=self.model_var).pack(
            side="left", fill="x", expand=True)

        tk.Label(c.body, text="API key (kept in memory for this session only)",
                 bg=PANEL, fg=TEXT, font=FONT_BOLD).pack(anchor="w",
                                                         pady=(14, 4))
        self.api_entry = ttk.Entry(c.body, show="•", font=FONT)
        self.api_entry.pack(fill="x")

        key_btns = tk.Frame(c.body, bg=PANEL)
        key_btns.pack(anchor="w", pady=10)
        make_button(key_btns, "Get Groq key", kind="subtle",
                    command=lambda: self.open_url(PROVIDERS["Groq"]["url"])
                    ).pack(side="left", padx=(0, 6))
        make_button(key_btns, "Get OpenAI key", kind="subtle",
                    command=lambda: self.open_url(PROVIDERS["OpenAI"]["url"])
                    ).pack(side="left", padx=(0, 6))
        make_button(key_btns, "Get OpenRouter key", kind="subtle",
                    command=lambda: self.open_url(PROVIDERS["OpenRouter"]["url"])
                    ).pack(side="left")

        ttk.Checkbutton(c.body,
                        text="Enable AI companion features (prototype)",
                        variable=self.ai_enabled_var).pack(anchor="w", pady=3)
        ttk.Checkbutton(c.body,
                        text="Use AI for the greeting (future feature — not "
                             "called automatically yet)",
                        variable=self.ai_greeting_var).pack(anchor="w", pady=3)

        actions = tk.Frame(c.body, bg=PANEL)
        actions.pack(anchor="w", pady=14)
        make_button(actions, "Test API key", kind="primary",
                    command=self.test_api).pack(side="left", padx=(0, 8))
        make_button(actions, "Preview a greeting",
                    command=self.preview_ai_greeting).pack(side="left", padx=(0, 8))
        make_button(actions, "Cancel", kind="subtle",
                    command=self._cancel_ai_spinner).pack(side="left")

        self.ai_status = tk.Label(
            c.body,
            text="No API request will be made until you press Test API key.",
            bg=PANEL, fg=TEXT_MUTED, font=FONT_SM, wraplength=820,
            justify="left",
        )
        self.ai_status.pack(anchor="w", pady=(4, 0))

        warn = Card(wrap, accent=WARN)
        warn.pack(fill="x")
        tk.Label(warn.body, text="🔒  Security",
                 bg=PANEL, fg=WARN, font=FONT_H2).pack(anchor="w")
        tk.Label(warn.body,
                 text="Keys are not saved to disk or added to shell startup "
                      "files. A future persistent setup will use the desktop "
                      "keyring (Secret Service / libsecret).",
                 bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------ safety tab
    def _build_safety(self):
        wrap = tk.Frame(self.safety_tab, bg=BG)
        wrap.pack(fill="both", expand=True)

        c = Card(wrap, accent=ACCENT)
        c.pack(fill="x", pady=(0, 12))
        tk.Label(c.body, text="Safe by design",
                 bg=PANEL, fg=TEXT, font=FONT_H1).pack(anchor="w")

        items = [
            ("Backup first",
             "Before applying changes, a timestamped backup of your current "
             "~/.bashrc is created."),
            ("Only edit our section",
             "The app replaces only the block between its own marker "
             "comments. Everything else is left alone."),
            ("No sudo required",
             "Your personal shell configuration belongs to you. The app never "
             "needs administrator privileges."),
            ("API key privacy",
             "The AI key lives in memory for this session and is never "
             "written to settings or ~/.bashrc."),
            ("Bash only for this MVP",
             "The welcome message targets interactive Bash shells. Zsh and "
             "Fish support will come later."),
        ]
        for title, desc in items:
            row = tk.Frame(c.body, bg=PANEL)
            row.pack(fill="x", pady=6)
            tk.Label(row, text="✓", bg=PANEL, fg=ACCENT,
                     font=("Sans", 14, "bold")).pack(side="left",
                                                     padx=(0, 10), anchor="n")
            body = tk.Frame(row, bg=PANEL)
            body.pack(side="left", fill="x", expand=True)
            tk.Label(body, text=title, bg=PANEL, fg=TEXT,
                     font=FONT_BOLD).pack(anchor="w")
            tk.Label(body, text=desc, bg=PANEL, fg=TEXT_MUTED, font=FONT_SM,
                     wraplength=760, justify="left").pack(anchor="w",
                                                          pady=(2, 0))

        c2 = Card(wrap, accent=ACCENT_2)
        c2.pack(fill="both", expand=True)

        hdr = tk.Frame(c2.body, bg=PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Backups & recovery", bg=PANEL, fg=TEXT,
                 font=FONT_H2).pack(side="left")
        make_button(hdr, "⟳  Refresh", kind="subtle",
                    command=self.refresh_backups).pack(side="right")
        make_button(hdr, "Restore selected", kind="primary",
                    command=self.restore_backup).pack(side="right",
                                                      padx=(0, 8))

        tk.Label(c2.body,
                 text="Restoring will first back up your current .bashrc, then "
                      "copy the selected backup over it.",
                 bg=PANEL, fg=TEXT_DIM, font=FONT_SM,
                 wraplength=820, justify="left").pack(anchor="w",
                                                      pady=(8, 8))

        self.backup_list = tk.Listbox(
            c2.body, bg=PANEL_2, fg=TEXT, selectbackground=ACCENT_DIM,
            selectforeground="#06210f", relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            font=FONT_MONO, activestyle="none",
        )
        self.backup_list.pack(fill="both", expand=True)

        row2 = tk.Frame(c2.body, bg=PANEL)
        row2.pack(fill="x", pady=(10, 0))
        make_button(row2, "Open .bashrc", command=self.open_bashrc).pack(
            side="left", padx=(0, 8))
        make_button(row2, "Open config folder",
                    command=self.open_config_dir).pack(side="left")

    # ---------------------------------------------------------------- footer
    def _build_footer(self):
        footer = tk.Frame(self, bg=BG_2, height=58)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        tk.Frame(footer, bg=BORDER, height=1).pack(fill="x", side="top")

        left = tk.Frame(footer, bg=BG_2)
        left.pack(side="left", fill="x", expand=True, padx=22)

        self.status_dot = tk.Canvas(left, width=12, height=12, bg=BG_2,
                                    highlightthickness=0)
        self.status_dot.pack(side="left", pady=22)
        self._status_dot_id = self.status_dot.create_oval(
            2, 2, 10, 10, fill=ACCENT, outline="")

        self.status = tk.Label(left, text="Ready", bg=BG_2, fg=TEXT_MUTED,
                               font=FONT_SM)
        self.status.pack(side="left", padx=(8, 0))

        right = tk.Frame(footer, bg=BG_2)
        right.pack(side="right", padx=18, pady=10)
        make_button(right, "Preview", command=self.refresh_preview).pack(
            side="right", padx=(8, 0))
        make_button(right, "Save settings",
                    command=self.save_only).pack(side="right", padx=(8, 0))
        make_button(right, "Apply to Bash", kind="primary",
                    command=self.apply_bash).pack(side="right")

    # ------------------------------------------------------------ animations
    def _tick_clock(self):
        try:
            self.clock_label.configure(
                text=datetime.now().strftime("%a %d %b  %H:%M:%S"))
        except (AttributeError, tk.TclError):
            pass
        self.after(1000, self._tick_clock)

    def _ambient_pulse(self):
        try:
            self._dot_phase = getattr(self, "_dot_phase", 0) + 1
            t = (self._dot_phase % 60) / 60.0
            v = 1 - abs(2 * t - 1)
            colour = ACCENT if v >= 0.5 else ACCENT_DIM
            self.pill_dot.itemconfigure(self._pill_dot_id, fill=colour)
        except (AttributeError, tk.TclError):
            pass
        self.after(80, self._ambient_pulse)

    # -------------------------------------------------------------- loading
    def _load_widgets(self):
        s = self.settings
        self.greeting_var.set(s.get("greeting", DEFAULTS["greeting"]))
        self.enabled_var.set(s.get("enabled", True))
        self.date_var.set(s.get("show_date", True))
        self.host_var.set(s.get("show_host", False))
        self.fastfetch_var.set(s.get("fastfetch", False))
        self.prompt_var.set(s.get("prompt_style", DEFAULTS["prompt_style"]))
        self.provider_var.set(s.get("provider", "Groq"))
        self.model_var.set(s.get("model", PROVIDERS["Groq"]["model"]))
        self.ai_enabled_var.set(s.get("ai_enabled", False))
        self.ai_greeting_var.set(s.get("ai_greeting", False))
        self.motd_text.insert("1.0", s.get("custom_motd", ""))
        self._select_face(s.get("face", "(•‿•)"))
        self._update_pill()
        self.refresh_backups()

    def _select_face(self, face):
        for name, value in FACES:
            if value == face:
                self.face_var.set(f"{name}   {value}")
                self.face_sample.configure(text=value)
                return
        self.face_var.set(f"Happy   {FACES[0][1]}")
        self.face_sample.configure(text=FACES[0][1])

    def _face_changed(self, _event=None):
        value = self.face_var.get()
        face = value.split("   ", 1)[1] if "   " in value else FACES[0][1]
        self.face_sample.configure(text=face)
        pulse_widget(self.face_sample, base=22, peak=30)
        self.refresh_preview()

    # ------------------------------------------------------------- collecting
    def collect(self):
        raw = self.face_var.get()
        face = raw.split("   ", 1)[1] if "   " in raw else "(•‿•)"
        return {
            "enabled": self.enabled_var.get(),
            "greeting": self.greeting_var.get() or "Welcome back, {user}!",
            "face": face,
            "show_date": self.date_var.get(),
            "show_host": self.host_var.get(),
            "fastfetch": self.fastfetch_var.get(),
            "prompt_style": self.prompt_var.get(),
            "provider": self.provider_var.get() or "Groq",
            "model": self.model_var.get().strip()
                     or PROVIDERS.get(self.provider_var.get(),
                                      PROVIDERS["Groq"])["model"],
            "ai_enabled": self.ai_enabled_var.get(),
            "ai_greeting": self.ai_greeting_var.get(),
            "custom_motd": self.motd_text.get("1.0", "end-1c").strip()[:1000],
        }

    # ----------------------------------------------------------- preview flow
    def refresh_preview(self, animate=True):
        try:
            settings = self.collect()
        except (AttributeError, tk.TclError):
            return

        content = (preview_text(settings) if settings["enabled"]
                   else "(Welcome message is disabled)")
        try:
            self.preview.show(content, animate=animate)
        except tk.TclError:
            pass

        try:
            self.stat_face_card.value_label.configure(text=settings["face"])
            self.stat_status_card.value_label.configure(
                text="Enabled" if settings["enabled"] else "Disabled")
            if not settings["enabled"]:
                self.stat_status_card.value_label.configure(fg=WARN)
            else:
                self.stat_status_card.value_label.configure(fg=ACCENT)
        except (AttributeError, tk.TclError):
            pass

        self._update_pill()

    def _update_pill(self):
        try:
            enabled = self.enabled_var.get()
        except (AttributeError, tk.TclError):
            enabled = True
        try:
            self.pill_label.configure(text="Active" if enabled else "Disabled")
        except tk.TclError:
            pass

    # --------------------------------------------------------------- actions
    def _set_status(self, text, colour=ACCENT):
        try:
            self.status.configure(text=text)
            self.status_dot.itemconfigure(self._status_dot_id, fill=colour)
        except tk.TclError:
            pass

    def save_only(self):
        self.settings = self.collect()
        save_settings(self.settings)
        self._set_status(f"Settings saved to {CONFIG_FILE}", ACCENT)
        self.toast("Settings saved. Your shell was not changed.", "success")

    def apply_bash(self):
        settings = self.collect()
        if not messagebox.askyesno(
            "Apply welcome display?",
            "This will back up ~/.bashrc and update only the "
            "Terminal Experience Studio section.\n\nContinue?",
        ):
            return

        self._set_status("Applying…", ACCENT_2)
        self.update_idletasks()

        try:
            old = BASHRC.read_text(encoding="utf-8") if BASHRC.exists() else ""
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = None
            if BASHRC.exists():
                backup = BASHRC.with_name(
                    f".bashrc.terminal-experience-backup-{stamp}")
                shutil.copy2(BASHRC, backup)

            block = make_shell_block(settings)

            if START_MARK in old and END_MARK in old:
                before, rest = old.split(START_MARK, 1)
                _, after = rest.split(END_MARK, 1)
                updated = before.rstrip() + "\n\n" + block + after
            else:
                updated = (old.rstrip()
                           + ("\n\n" if old.strip() else "")
                           + block + "\n")

            if START_MARK not in updated or END_MARK not in updated:
                raise RuntimeError("Generated configuration failed validation.")

            BASHRC.write_text(updated, encoding="utf-8")
            save_settings(settings)
            self.refresh_backups()

            self._set_status(
                "Applied successfully. Open a new Bash terminal to see it.",
                ACCENT,
            )
            msg = "Your Bash startup display has been updated."
            if backup:
                msg += f"\n\nBackup created at:\n{backup}"
            msg += "\n\nOpen a new terminal to test it."
            self.toast("Applied. Open a new terminal to see it.", "success")
            messagebox.showinfo("Applied successfully", msg)

        except Exception as exc:
            self._set_status("Apply failed.", DANGER)
            self.toast("Could not apply changes.", "error")
            messagebox.showerror("Could not apply changes",
                                 f"No success was reported.\n\nError: {exc}")

    def _provider_changed(self, _event=None):
        provider = self.provider_var.get()
        self.model_var.set(PROVIDERS.get(provider, PROVIDERS["Groq"])["model"])

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception:
            self.toast("Could not open browser.", "warn")

    def open_config_file(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            save_settings(self.collect())
        self._open_path(CONFIG_FILE)

    def open_config_dir(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._open_path(CONFIG_DIR)

    def open_bashrc(self):
        if not BASHRC.exists():
            BASHRC.touch()
        self._open_path(BASHRC)

    def _open_path(self, path):
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor:
            try:
                subprocess.Popen([editor, str(path)])
                return
            except Exception:
                pass
        for candidate in ("xdg-open", "xed", "gnome-text-editor",
                          "mousepad", "gedit"):
            if shutil.which(candidate):
                try:
                    subprocess.Popen([candidate, str(path)])
                    return
                except Exception:
                    continue
        messagebox.showinfo("Open file",
                            f"Open this in your preferred editor:\n{path}")

    # ------------------------------------------------------------ backups
    def refresh_backups(self):
        try:
            self.backup_list.delete(0, "end")
        except (AttributeError, tk.TclError):
            return
        backups = list_backups()
        for b in backups:
            size = b.stat().st_size if b.exists() else 0
            self.backup_list.insert(
                "end", f"{b.name}   ({size} bytes)")
        if not backups:
            self.backup_list.insert(
                "end", "  No backups yet — apply the welcome display first.")
        try:
            self.stat_backup_card.value_label.configure(
                text=str(len(backups)))
        except (AttributeError, tk.TclError):
            pass

    def restore_backup(self):
        sel = self.backup_list.curselection()
        if not sel:
            self.toast("Select a backup to restore first.", "warn")
            return
        text = self.backup_list.get(sel[0])
        if text.strip().startswith("No backups"):
            return
        name = text.split("   ", 1)[0].strip()
        backup = BASHRC.parent / name
        if not backup.exists():
            self.toast("That backup no longer exists.", "error")
            return
        if not messagebox.askyesno(
            "Restore backup?",
            f"This will replace ~/.bashrc with:\n{name}\n\n"
            "Your current .bashrc will be backed up first. Continue?",
        ):
            return
        try:
            if BASHRC.exists():
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy2(
                    BASHRC,
                    BASHRC.with_name(
                        f".bashrc.terminal-experience-backup-{stamp}"),
                )
            shutil.copy2(backup, BASHRC)
            self.refresh_backups()
            self._set_status("Backup restored.", ACCENT)
            self.toast("Backup restored successfully.", "success")
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc))

    # ============================================================
    # AI HELPERS
    # ============================================================
    def _start_ai_spinner(self):
        """Begin the animated 'Testing…' spinner and schedule a watchdog."""
        self._cancel_ai_spinner(quiet=True)
        self._ai_spin = 0
        self._ai_spin_active = True
        self.ai_status.configure(
            text="Testing connection…", fg=ACCENT_2)
        self._ai_spin_step()
        # Watchdog: if the worker thread never reports back, stop the spinner.
        self._ai_spin_deadline_job = self.after(
            AI_REQUEST_TIMEOUT_MS, self._ai_spin_timeout)

    def _ai_spin_step(self):
        if not self._ai_spin_active:
            return
        self._ai_spin = (self._ai_spin + 1) % 4
        try:
            self.ai_status.configure(
                text="Testing connection" + "." * self._ai_spin,
                fg=ACCENT_2,
            )
        except tk.TclError:
            return
        self.after(320, self._ai_spin_step)

    def _cancel_ai_spinner(self, quiet=False):
        """Stop the spinner and cancel any pending watchdog."""
        self._ai_spin_active = False
        if self._ai_spin_deadline_job is not None:
            try:
                self.after_cancel(self._ai_spin_deadline_job)
            except (tk.TclError, ValueError):
                pass
            self._ai_spin_deadline_job = None
        if not quiet:
            try:
                self.ai_status.configure(
                    text="Test cancelled.", fg=TEXT_MUTED)
            except tk.TclError:
                pass
            self.toast("AI test cancelled.", "info")

    def _ai_spin_timeout(self):
        """Called by the watchdog if the worker never comes back."""
        if not self._ai_spin_active:
            return
        # Bump generation so any late worker reply is ignored.
        self._ai_request_generation += 1
        self._ai_spin_active = False
        self._ai_spin_deadline_job = None
        try:
            self.ai_status.configure(
                text=("Request timed out after "
                      f"{AI_REQUEST_TIMEOUT_MS // 1000}s. Check your network, "
                      "firewall, proxy, or endpoint."),
                fg=WARN,
            )
        except tk.TclError:
            pass
        self.toast("AI request timed out.", "warn")

    def test_api(self):
        provider = self.provider_var.get()
        key = self.api_entry.get().strip()
        if not key:
            messagebox.showwarning(
                "API key needed",
                "Paste an API key first. You can get one from the provider "
                "buttons above.",
            )
            return

        settings = self.collect()
        endpoint = PROVIDERS.get(provider, PROVIDERS["Groq"])["endpoint"]
        model = settings["model"]

        # Each test gets a generation number so stale replies can be ignored.
        self._ai_request_generation += 1
        generation = self._ai_request_generation

        self._start_ai_spinner()

        def worker(gen=generation):
            payload = {
                "model": model,
                "messages": [
                    {"role": "system",
                     "content": "You are a friendly terminal companion. "
                                "Reply in one short sentence."},
                    {"role": "user",
                     "content": "Greet me with a short, friendly Linux "
                                "terminal welcome. Do not use markdown."},
                ],
                "temperature": 0.7,
                "max_tokens": 100,
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    # Cloudflare in front of Groq (and some other providers)
                    # blocks Python's default "Python-urllib/x.y" User-Agent
                    # with HTTP 403 / error code 1010. A normal-looking UA
                    # string avoids that filter.
                    "User-Agent": "TerminalExperienceStudio/2.0",
                    "Accept": "application/json",
                },
                method="POST",
            )

            # Every except block below turns the error into a plain string
            # BEFORE scheduling a UI update — Python deletes the `as exc`
            # name when the except block exits, and the lambda runs later.

            try:
                with urllib.request.urlopen(
                    req, timeout=AI_SOCKET_TIMEOUT
                ) as response:
                    raw = response.read().decode("utf-8", "replace")
                try:
                    data = json.loads(raw)
                    answer = (data.get("choices", [{}])[0]
                                  .get("message", {})
                                  .get("content", "") or "").strip()
                except (ValueError, KeyError, IndexError, TypeError):
                    answer = ""
                if not answer:
                    answer = "(The provider returned an empty reply.)"
                self.after(0, lambda g=gen, a=answer:
                           self._ai_result(g, a, ok=True))

            except urllib.error.HTTPError as exc:
                try:
                    detail = exc.read().decode("utf-8", "replace")[:400]
                except Exception:
                    detail = ""
                code = exc.code
                reason = exc.reason
                # Detect Cloudflare 1010 body: {"error":{"code":1010,...}}
                cf_hint = ""
                if code == 403 and "1010" in (detail or ""):
                    cf_hint = (" — Cloudflare blocked the request "
                               "(error 1010). This usually means the client "
                               "User-Agent was rejected. If you see this, "
                               "please report it.")
                elif code == 401:
                    cf_hint = " — key is invalid or was not accepted."
                elif code == 403:
                    cf_hint = " — key lacks access to this model."
                elif code == 404:
                    cf_hint = (" — endpoint or model name not found. Try "
                               "reselecting the provider to reset the model.")
                elif code == 429:
                    cf_hint = " — rate limit reached. Wait a moment and retry."
                elif 500 <= code < 600:
                    cf_hint = " — provider is having trouble. Try again shortly."
                msg = f"HTTP {code} {reason}{cf_hint}"
                if detail:
                    msg += f"\n\n{detail}"
                self.after(0, lambda g=gen, m=msg:
                           self._ai_result(g, m, ok=False))

            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", exc)
                msg = f"Network error: {reason}"
                self.after(0, lambda g=gen, m=msg:
                           self._ai_result(g, m, ok=False))

            except (socket.timeout, TimeoutError):
                msg = (f"Network timeout after {AI_SOCKET_TIMEOUT}s. The "
                       "request never reached the provider.")
                self.after(0, lambda g=gen, m=msg:
                           self._ai_result(g, m, ok=False))

            except Exception as exc:
                msg = f"Unexpected error: {exc.__class__.__name__}: {exc}"
                self.after(0, lambda g=gen, m=msg:
                           self._ai_result(g, m, ok=False))

        threading.Thread(target=worker, daemon=True).start()

    def _ai_result(self, generation, message, ok):
        """Called on the Tk main thread when a request finishes."""
        if generation != self._ai_request_generation:
            return

        self._cancel_ai_spinner(quiet=True)

        if ok:
            try:
                self.ai_status.configure(
                    text=f"Connection works! Sample greeting: {message}",
                    fg=ACCENT,
                )
            except tk.TclError:
                return
            self.toast("AI connection successful.", "success")
            messagebox.showinfo("AI connection successful", message)
        else:
            try:
                self.ai_status.configure(text=message, fg=DANGER)
            except tk.TclError:
                return
            self.toast("AI connection failed.", "error")
            messagebox.showerror("AI connection failed", message)

    def preview_ai_greeting(self):
        messagebox.showinfo(
            "AI greeting preview",
            "When you press Test API key, the app asks your selected model "
            "for a short greeting.\n\n"
            "Automatic daily AI greetings are a later feature — this MVP does "
            "not call AI at terminal startup.",
        )

    # ---------------------------------------------------------------- toasts
    def toast(self, text, kind="info"):
        try:
            Toast(self, text, kind=kind)
        except tk.TclError:
            pass


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    App().mainloop()
