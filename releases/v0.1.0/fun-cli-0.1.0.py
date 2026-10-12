#!/usr/bin/env python3
"""
Terminal Experience Studio — an approachable Linux terminal customization MVP.
Safe by default: preview first, back up ~/.bashrc, then replace only this app's marked block.
"""
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime

APP_NAME = "Terminal Experience Studio"
CONFIG_DIR = Path.home() / ".config" / "terminal-experience-studio"
CONFIG_FILE = CONFIG_DIR / "settings.json"
BASHRC = Path.home() / ".bashrc"
START_MARK = "# >>> Terminal Experience Studio >>>"
END_MARK = "# <<< Terminal Experience Studio <<<"

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
    os.chmod(CONFIG_FILE, 0o600)

def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"

def make_shell_block(settings):
    if not settings.get("enabled", True):
        return START_MARK + "\n# Startup greeting disabled in Terminal Experience Studio.\n" + END_MARK
    lines = [START_MARK, "# Managed by Terminal Experience Studio. Edit settings in the GUI."]
    if settings.get("show_date", True):
        lines.append('printf "\\033[1;32m%s\\033[0m  " "$(date \'+%a %d %b %H:%M\')"')
    face = settings.get("face", "(•‿•)")
    greeting = settings.get("greeting", "Welcome back, {user}!").replace("{user}", "__TES_USER_PLACEHOLDER__")
    # Keep the greeting plain text and shell-safe; no user-entered shell is evaluated.
    greeting = greeting.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    greeting = greeting.replace("__TES_USER_PLACEHOLDER__", "${USER}")
    lines.append('printf "\\033[1;36m%s\\033[0m  %s\\n" "' + face.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '" "' + greeting + '"')
    custom = settings.get("custom_motd", "").strip()
    if custom:
        for line in custom.splitlines()[:5]:
            safe = line.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
            lines.append('printf "%s\\n" "' + safe + '"')
    if settings.get("show_host", False):
        lines.append('printf "  Host: %s | Shell: %s\\n" "$(hostname)" "${SHELL##*/}"')
    if settings.get("fastfetch", False):
        lines.append('if command -v fastfetch >/dev/null 2>&1; then fastfetch; fi')
    lines.append(END_MARK)
    return "\n".join(lines)

def preview_text(settings):
    user = os.environ.get("USER", "you")
    greeting = settings.get("greeting", "Welcome back, {user}!").replace("{user}", user)
    out = []
    if settings.get("show_date", True):
        out.append(datetime.now().strftime("%a %d %b %H:%M"))
    out.append(f'{settings.get("face", "(•‿•)")}  {greeting}')
    if settings.get("custom_motd", "").strip():
        out.extend(settings["custom_motd"].strip().splitlines()[:5])
    if settings.get("show_host", False):
        out.append(f'Host: {os.uname().nodename} | Shell: {Path(os.environ.get("SHELL", "/bin/bash")).name}')
    if settings.get("fastfetch", False):
        out.append("[Fastfetch will run here if installed]")
    return "\n".join(out)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x720")
        self.minsize(760, 620)
        self.configure(bg="#10151c")
        self.settings = load_settings()
        self.api_key = ""
        self._build_style()
        self._build_ui()
        self._load_widgets()
        self.refresh_preview()

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Sans", 10))
        style.configure("TFrame", background="#10151c")
        style.configure("Panel.TFrame", background="#19222d")
        style.configure("TLabel", background="#10151c", foreground="#e8edf2")
        style.configure("Muted.TLabel", background="#10151c", foreground="#9aa8b6")
        style.configure("Panel.TLabel", background="#19222d", foreground="#e8edf2")
        style.configure("Title.TLabel", font=("Sans", 21, "bold"), foreground="#f4f7fa", background="#10151c")
        style.configure("Subtitle.TLabel", font=("Sans", 10), foreground="#a9b5c2", background="#10151c")
        style.configure("TButton", padding=(12, 8))
        style.configure("Accent.TButton", background="#4b9b69", foreground="#ffffff", padding=(14, 9))
        style.map("Accent.TButton", background=[("active", "#398454")])
        style.configure("TNotebook", background="#10151c", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 10), background="#202b37", foreground="#cbd5df")
        style.map("TNotebook.Tab", background=[("selected", "#344454")], foreground=[("selected", "#ffffff")])
        style.configure("TCheckbutton", background="#10151c", foreground="#e8edf2")
        style.configure("TRadiobutton", background="#10151c", foreground="#e8edf2")
        style.configure("TCombobox", padding=5)
        style.configure("TEntry", padding=7)
        style.configure("TLabelframe", background="#10151c", foreground="#e8edf2")
        style.configure("TLabelframe.Label", background="#10151c", foreground="#a9d8b5")

    def _build_ui(self):
        header = ttk.Frame(self, padding=(24, 20, 24, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Terminal Experience Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Bring your command line to life. Customize first, apply when you're ready.", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(8, 10))
        self.welcome_tab = ttk.Frame(self.notebook, padding=18)
        self.look_tab = ttk.Frame(self.notebook, padding=18)
        self.ai_tab = ttk.Frame(self.notebook, padding=18)
        self.about_tab = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(self.welcome_tab, text="  Welcome & MOTD  ")
        self.notebook.add(self.look_tab, text="  Prompt & Look  ")
        self.notebook.add(self.ai_tab, text="  AI Companion  ")
        self.notebook.add(self.about_tab, text="  Safety & Help  ")
        self._build_welcome()
        self._build_look()
        self._build_ai()
        self._build_about()
        footer = ttk.Frame(self, padding=(20, 6, 20, 16))
        footer.pack(fill="x")
        self.status = ttk.Label(footer, text="Ready", style="Muted.TLabel")
        self.status.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Preview", command=self.refresh_preview).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Save settings", command=self.save_only).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Apply to Bash", style="Accent.TButton", command=self.apply_bash).pack(side="right")

    def _build_welcome(self):
        ttk.Label(self.welcome_tab, text="Make your terminal say hello", font=("Sans", 16, "bold")).pack(anchor="w")
        ttk.Label(self.welcome_tab, text="Choose the mood, message, and useful details shown when Bash starts.", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))
        row = ttk.Frame(self.welcome_tab); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Greeting").pack(side="left", padx=(0, 12))
        self.greeting_var = tk.StringVar()
        self.greeting_entry = ttk.Entry(row, textvariable=self.greeting_var)
        self.greeting_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(self.welcome_tab, text="Tip: use {user} where you want the Linux username to appear.", style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        face_row = ttk.Frame(self.welcome_tab); face_row.pack(fill="x", pady=(0, 10))
        ttk.Label(face_row, text="Terminal mood").pack(side="left", padx=(0, 12))
        self.face_var = tk.StringVar()
        self.face_combo = ttk.Combobox(face_row, textvariable=self.face_var, state="readonly", width=34, values=[f"{name}   {face}" for name, face in FACES])
        self.face_combo.pack(side="left")
        self.face_combo.bind("<<ComboboxSelected>>", self._face_changed)
        self.face_sample = ttk.Label(face_row, text="(•‿•)", font=("Monospace", 16, "bold"), foreground="#8fe0a3")
        self.face_sample.pack(side="left", padx=16)
        toggles = ttk.Frame(self.welcome_tab); toggles.pack(fill="x", pady=4)
        self.enabled_var = tk.BooleanVar()
        self.date_var = tk.BooleanVar()
        self.host_var = tk.BooleanVar()
        self.fastfetch_var = tk.BooleanVar()
        ttk.Checkbutton(toggles, text="Enable welcome message", variable=self.enabled_var, command=self.refresh_preview).grid(row=0, column=0, sticky="w", padx=(0, 20), pady=5)
        ttk.Checkbutton(toggles, text="Show date and time", variable=self.date_var, command=self.refresh_preview).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Checkbutton(toggles, text="Show host and shell", variable=self.host_var, command=self.refresh_preview).grid(row=1, column=0, sticky="w", padx=(0, 20), pady=5)
        ttk.Checkbutton(toggles, text="Run Fastfetch if installed", variable=self.fastfetch_var, command=self.refresh_preview).grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(self.welcome_tab, text="Extra message (optional, up to 5 lines)").pack(anchor="w", pady=(10, 4))
        self.motd_text = tk.Text(self.welcome_tab, height=3, wrap="word", bg="#19222d", fg="#e8edf2", insertbackground="#ffffff", relief="flat", padx=10, pady=8)
        self.motd_text.pack(fill="x")
        ttk.Label(self.welcome_tab, text="Live preview", font=("Sans", 11, "bold")).pack(anchor="w", pady=(14, 6))
        self.preview = tk.Text(self.welcome_tab, height=6, wrap="word", bg="#080c11", fg="#a8e6b1", insertbackground="#ffffff", relief="flat", padx=12, pady=10, font=("Monospace", 11))
        self.preview.pack(fill="both", expand=True)
        self.preview.configure(state="disabled")
        self.greeting_var.trace_add("write", lambda *_: self.refresh_preview())

    def _build_look(self):
        ttk.Label(self.look_tab, text="Prompt & appearance", font=("Sans", 16, "bold")).pack(anchor="w")
        ttk.Label(self.look_tab, text="Start with safe, useful options. More terminal-specific controls can be added as adapters.", style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(3, 14))
        self.prompt_var = tk.StringVar()
        box = ttk.LabelFrame(self.look_tab, text="Shell prompt", padding=12); box.pack(fill="x", pady=5)
        ttk.Label(box, text="Prompt behavior").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Combobox(box, textvariable=self.prompt_var, state="readonly", width=42, values=[
            "Keep my existing prompt", "Recommend Starship (safe setup guide)"
        ]).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="We won't replace your prompt automatically in this first version.", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        box2 = ttk.LabelFrame(self.look_tab, text="Terminal appearance", padding=12); box2.pack(fill="x", pady=12)
        ttk.Label(box2, text="Colors, fonts, transparency, and background images are configured by each terminal app.").pack(anchor="w")
        ttk.Label(box2, text="Next adapters: GNOME Terminal, Kitty, Konsole, and Alacritty.", style="Muted.TLabel").pack(anchor="w", pady=(5, 10))
        links = ttk.Frame(box2); links.pack(anchor="w")
        ttk.Button(links, text="Starship website", command=lambda: self.open_url("https://starship.rs/")).pack(side="left", padx=(0, 8))
        ttk.Button(links, text="Fastfetch project", command=lambda: self.open_url("https://github.com/fastfetch-cli/fastfetch")).pack(side="left")
        imagebox = ttk.LabelFrame(self.look_tab, text="ASCII image converter — next feature", padding=12); imagebox.pack(fill="x", pady=5)
        ttk.Label(imagebox, text="The planned converter will let you choose an image, adjust width/contrast, preview the result, and add it to your startup display.").pack(anchor="w")
        ttk.Label(imagebox, text="For now, Fastfetch can display supported logos/images depending on your terminal setup.", style="Muted.TLabel", wraplength=750).pack(anchor="w", pady=(5, 0))

    def _build_ai(self):
        ttk.Label(self.ai_tab, text="Give your terminal a personality", font=("Sans", 16, "bold")).pack(anchor="w")
        ttk.Label(self.ai_tab, text="AI greetings are optional. Your terminal should still work perfectly without an API key.", style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(3, 14))
        self.provider_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.ai_enabled_var = tk.BooleanVar()
        self.ai_greeting_var = tk.BooleanVar()
        provider_row = ttk.Frame(self.ai_tab); provider_row.pack(fill="x", pady=5)
        ttk.Label(provider_row, text="AI provider", width=15).pack(side="left")
        provider_combo = ttk.Combobox(provider_row, textvariable=self.provider_var, state="readonly", values=list(PROVIDERS), width=18)
        provider_combo.pack(side="left")
        provider_combo.bind("<<ComboboxSelected>>", self._provider_changed)
        ttk.Label(provider_row, text="Model").pack(side="left", padx=(18, 8))
        ttk.Entry(provider_row, textvariable=self.model_var, width=34).pack(side="left", fill="x", expand=True)
        self.api_entry = ttk.Entry(self.ai_tab, show="•")
        ttk.Label(self.ai_tab, text="API key (only held in memory during this session)").pack(anchor="w", pady=(12, 4))
        self.api_entry.pack(fill="x")
        key_buttons = ttk.Frame(self.ai_tab); key_buttons.pack(fill="x", pady=8)
        ttk.Button(key_buttons, text="Get Groq API key", command=lambda: self.open_url(PROVIDERS["Groq"]["url"])).pack(side="left", padx=(0, 8))
        ttk.Button(key_buttons, text="Get OpenAI key", command=lambda: self.open_url(PROVIDERS["OpenAI"]["url"])).pack(side="left", padx=(0, 8))
        ttk.Button(key_buttons, text="Get OpenRouter key", command=lambda: self.open_url(PROVIDERS["OpenRouter"]["url"])).pack(side="left")
        ttk.Checkbutton(self.ai_tab, text="Enable AI companion features (prototype)", variable=self.ai_enabled_var).pack(anchor="w", pady=(6, 3))
        ttk.Checkbutton(self.ai_tab, text="Use AI for the greeting (future feature; not called automatically yet)", variable=self.ai_greeting_var).pack(anchor="w", pady=3)
        actions = ttk.Frame(self.ai_tab); actions.pack(anchor="w", pady=12)
        ttk.Button(actions, text="Test API key", command=self.test_api).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Preview a greeting", command=self.preview_ai_greeting).pack(side="left")
        self.ai_status = ttk.Label(self.ai_tab, text="No API request will be made until you press Test API key.", style="Muted.TLabel", wraplength=760)
        self.ai_status.pack(anchor="w", pady=(5, 0))
        warning = ttk.Label(self.ai_tab, text="Security: keys are not saved to disk or added to shell startup files. For a future persistent setup, we'll use the desktop keyring.", style="Muted.TLabel", wraplength=760)
        warning.pack(anchor="w", pady=(16, 0))

    def _build_about(self):
        ttk.Label(self.about_tab, text="Safe by design", font=("Sans", 16, "bold")).pack(anchor="w")
        items = [
            ("Backup first", "Before applying changes, the app creates a timestamped backup of your current ~/.bashrc."),
            ("Only edit our section", "The app replaces only the block between its own marker comments. Other Bash settings are left alone."),
            ("No sudo required", "Your personal shell configuration belongs to your user account. The app should not need administrator privileges."),
            ("API key privacy", "The AI key is kept in memory for this session and is never written to settings or ~/.bashrc."),
            ("Bash only for this MVP", "The welcome message currently targets interactive Bash shells. Zsh and Fish support will come later."),
        ]
        for title, desc in items:
            row = ttk.Frame(self.about_tab); row.pack(fill="x", pady=8)
            ttk.Label(row, text="✓", foreground="#8fe0a3", font=("Sans", 14, "bold")).pack(side="left", padx=(0, 10), anchor="n")
            body = ttk.Frame(row); body.pack(side="left", fill="x", expand=True)
            ttk.Label(body, text=title, font=("Sans", 11, "bold")).pack(anchor="w")
            ttk.Label(body, text=desc, style="Muted.TLabel", wraplength=700).pack(anchor="w", pady=(2, 0))
        ttk.Button(self.about_tab, text="Open my Bash configuration", command=self.open_bashrc).pack(anchor="w", pady=(18, 0))

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
        self.refresh_preview()

    def collect(self):
        face = self.face_var.get().split("   ", 1)[1] if "   " in self.face_var.get() else "(•‿•)"
        return {
            "enabled": self.enabled_var.get(),
            "greeting": self.greeting_var.get() or "Welcome back, {user}!",
            "face": face,
            "show_date": self.date_var.get(),
            "show_host": self.host_var.get(),
            "fastfetch": self.fastfetch_var.get(),
            "prompt_style": self.prompt_var.get(),
            "provider": self.provider_var.get() or "Groq",
            "model": self.model_var.get().strip() or PROVIDERS.get(self.provider_var.get(), PROVIDERS["Groq"])["model"],
            "ai_enabled": self.ai_enabled_var.get(),
            "ai_greeting": self.ai_greeting_var.get(),
            "custom_motd": self.motd_text.get("1.0", "end-1c").strip()[:1000],
        }

    def refresh_preview(self):
        try:
            settings = self.collect()
            content = preview_text(settings) if settings["enabled"] else "(Welcome message is disabled)"
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", content)
            self.preview.configure(state="disabled")
        except (AttributeError, tk.TclError):
            pass

    def save_only(self):
        self.settings = self.collect()
        save_settings(self.settings)
        self.status.configure(text=f"Settings saved to {CONFIG_FILE}")
        messagebox.showinfo("Settings saved", "Your preferences have been saved. Nothing has been changed in your shell yet.")

    def apply_bash(self):
        settings = self.collect()
        if not messagebox.askyesno("Apply welcome display?", "This will back up ~/.bashrc and update only the Terminal Experience Studio section. Continue?"):
            return
        try:
            old = BASHRC.read_text(encoding="utf-8") if BASHRC.exists() else ""
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            if BASHRC.exists():
                backup = BASHRC.with_name(f".bashrc.terminal-experience-backup-{stamp}")
                shutil.copy2(BASHRC, backup)
            else:
                backup = None
            block = make_shell_block(settings)
            if START_MARK in old and END_MARK in old:
                before, rest = old.split(START_MARK, 1)
                _, after = rest.split(END_MARK, 1)
                updated = before.rstrip() + "\n\n" + block + after
            else:
                updated = old.rstrip() + ("\n\n" if old.strip() else "") + block + "\n"
            # Verify that the generated block has its matching boundaries before writing.
            if START_MARK not in updated or END_MARK not in updated:
                raise RuntimeError("Generated configuration failed validation.")
            BASHRC.write_text(updated, encoding="utf-8")
            save_settings(settings)
            self.status.configure(text="Applied successfully. Open a new Bash terminal to see the greeting.")
            msg = "Your Bash startup display has been updated."
            if backup:
                msg += f"\n\nBackup created at:\n{backup}"
            msg += "\n\nOpen a new terminal to test it."
            messagebox.showinfo("Applied successfully", msg)
        except Exception as exc:
            messagebox.showerror("Could not apply changes", f"No success was reported. Error: {exc}")

    def _provider_changed(self, _event=None):
        provider = self.provider_var.get()
        self.model_var.set(PROVIDERS.get(provider, PROVIDERS["Groq"])["model"])

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def test_api(self):
        provider = self.provider_var.get()
        key = self.api_entry.get().strip()
        if not key:
            messagebox.showwarning("API key needed", "Paste an API key first. You can get one from the provider button above.")
            return
        settings = self.collect()
        endpoint = PROVIDERS.get(provider, PROVIDERS["Groq"])["endpoint"]
        model = settings["model"]
        self.ai_status.configure(text="Testing connection…")
        def worker():
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a friendly terminal companion. Reply in one short sentence."},
                    {"role": "user", "content": "Greet me with a short, friendly Linux terminal welcome. Do not use markdown."}
                ],
                "temperature": 0.7,
                "max_tokens": 100,
            }
            req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            }, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    data = json.loads(response.read().decode("utf-8"))
                answer = data["choices"][0]["message"]["content"].strip()
                self.after(0, lambda: self._api_success(answer))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                self.after(0, lambda: self.ai_status.configure(text=f"API returned HTTP {e.code}: {detail}"))
            except Exception as e:
                self.after(0, lambda: self.ai_status.configure(text=f"Connection failed: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _api_success(self, answer):
        self.ai_status.configure(text=f"Connection works! Sample greeting: {answer}")
        messagebox.showinfo("AI connection successful", answer)

    def preview_ai_greeting(self):
        messagebox.showinfo("AI greeting preview", "When you press Test API key, the app asks your selected model for a short greeting. Automatic daily AI greetings are a later feature; this MVP does not call AI at terminal startup.")

    def open_bashrc(self):
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor:
            try:
                subprocess.Popen([editor, str(BASHRC)])
                return
            except Exception:
                pass
        for candidate in ("xed", "gnome-text-editor", "mousepad", "gedit"):
            if shutil.which(candidate):
                subprocess.Popen([candidate, str(BASHRC)])
                return
        messagebox.showinfo("Bash configuration", f"Open this file in your preferred text editor:\n{BASHRC}")

if __name__ == "__main__":
    App().mainloop()
