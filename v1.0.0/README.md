# Terminal Experience Studio  v0.2

Bring your command line to life: a friendly GTK4 / Libadwaita app that customises your terminal
without editing config files. Live previews, one-click Apply, and Undo for everything.

## Run it

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 librsvg2-common   # usually already present on Zorin OS
./run.sh                    # run from this folder
./install.sh                # or: install for your user (menu entry + launcher, no sudo)
./uninstall.sh [--purge]    # remove the app (see "Uninstalling")
```

Optional extras (the app works without them): `starship`, `fastfetch`, `libsecret-tools` (keyring for API keys).

## What's inside

| Page | What it does |
|---|---|
| **Dashboard** | Animated companion, live status chips, quick actions. |
| **Welcome & MOTD** | Greeting with `{user}`, `{host}`, `{daypart}`; 24 moods; rotating tips; extra message; Fastfetch. Live typing preview. |
| **Terminal Appearance** | 10 theme presets, colours, 16-colour palette, font, size, cursor, opacity, background image. Adapters for **GNOME Terminal, Kitty, Alacritty, Konsole**. Theme import/export. The UI tells you what each terminal can't do. |
| **Prompt Designer** | Minimal / Classic / Two-line (pure Bash, no installs) and two Starship styles. Preview shows success and failed-command states. |
| **ASCII Art Studio** | Gallery + picture-to-ASCII (GdkPixbuf, no extra dependency) with contrast, brightness, width, invert, 4 character sets. |
| **AI Companion** | Works offline: built-in tips and a command explainer with risk warnings. Optional AI (Groq, OpenAI, OpenRouter, local Ollama) writes greetings and explains commands. |
| **Backups & Settings** | List and restore backups, remove everything, reduce motion, light/dark. |

Shortcuts: `Ctrl+1` ... `Ctrl+7` jump between pages.

## Safety model

* One timestamped backup before every change; **Undo** button on the toast and in the apply bar.
* `.bashrc` is edited only between marker lines. Damaged markers abort with a clear message, nothing is changed.
* Writes are atomic and follow symlinks (stow/chezmoi-friendly).
* Never needs `sudo`. Only interactive shells are affected. Shell startup does no network access and no forks
  (unless Fastfetch is on).
* User text is single-quoted and stripped of control characters, so it cannot run code or inject terminal escapes.
  Git branch names in the prompt are whitelisted (a branch called `$(...)` is a known prompt-injection vector).
* Starship uses the app's own config file; your `~/.config/starship.toml` is never overwritten.
* API keys never touch settings or shell files: memory only, or the desktop keyring if you opt in.
* Backups from the original Tkinter MVP (`~/.bashrc.terminal-experience-backup-*`) are still recognised.

## Uninstalling

Open the app: **Backups & Settings -> Remove from my shell** (undoable), then run `./uninstall.sh`.
If the app is already gone, delete the `# >>> Terminal Experience Studio` blocks from `~/.bashrc`.

## Layout

```
tes/core/      pure Python, no GTK: settings, themes, bashconfig, prompts, backups, ai, explain, asciiart
tes/adapters/  one file per terminal (common interface, declared feature support)
tes/ui/        GTK4/Libadwaita: window, pages, animation toolkit, custom widgets, style.css
tests/         unit tests (core + adapters) and a GUI end-to-end test
```

Adding a terminal = one new class in `tes/adapters/`. Adding a shell = a sibling of `core/bashconfig.py`.

## Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"             # 49 tests, no display needed
GSK_RENDERER=cairo xvfb-run -a python3 tests/gui_e2e.py          # 20 checks driving the real window
```

## Migration notes (from the Tkinter MVP)

The Tkinter UI was replaced; the safe-apply behaviour was kept and hardened. Old `settings.json` files are
migrated automatically (`prompt_style` -> `prompt_preset`, `ai_greeting` -> `greeting_pack`).

## Roadmap

* `.deb` / Flatpak packaging (install.sh is the interim route).
* More shells (zsh, fish) and terminals (WezTerm, Ghostty).
* Companion that reacts to command failures; cached AI greetings by time of day.
* Verify on a real Zorin OS 18.1 desktop: GNOME Terminal adapter (uses `gsettings`) is tested against a fake
  `gsettings` here, so please try Apply + Undo once on the real thing.
