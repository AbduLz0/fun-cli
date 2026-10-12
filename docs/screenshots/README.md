<div align="center">

# Terminal Experience Studio

**Bring your command line to life.**

A friendly Linux desktop app that customises your terminal without editing config files.
Live previews, one-click Apply, and Undo for everything.

![Version](https://img.shields.io/badge/version-1.0.0-7bd88f)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![GTK](https://img.shields.io/badge/GTK4-Libadwaita-4a86cf)
![Platform](https://img.shields.io/badge/platform-Zorin%20%7C%20Ubuntu%20%7C%20GNOME-orange)

<img src="docs/screenshots/dashboard.png" alt="Terminal Experience Studio dashboard" width="860">

</div>

---

## Why this exists

Making a terminal feel personal usually means hunting through hidden config files, copying snippets from
forums, and hoping you can undo it later. Terminal Experience Studio gives you switches, sliders and
presets instead. You see exactly what you'll get before anything touches your system, and every change
can be undone.

It's made for two kinds of people:

- **Beginners** who want a welcoming, good-looking terminal without learning configuration syntax.
- **Advanced users** who want control over prompts, themes, startup behaviour and AI features.

## Features

### Welcome & MOTD
Choose how your terminal greets you. Write a greeting using `{user}`, `{host}` and `{daypart}`
(morning, afternoon, evening), pick one of 24 moods, add rotating tips, an extra message and an optional
Fastfetch summary. The preview types itself out just like the real thing.

<img src="docs/screenshots/welcome.png" alt="Welcome and MOTD page" width="760">

### Terminal Appearance
10 theme presets, colours, a 16-colour palette, font, size, cursor shape, opacity and background image.
Themes are applied the right way for each terminal, and the app tells you plainly when a terminal can't
do something (for example, GNOME Terminal has no background-image setting). Themes can be exported and
imported as small files.

| Terminal | Colours | Palette | Font | Cursor | Opacity | Background image |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| GNOME Terminal | yes | yes | yes | yes | yes | no |
| Kitty | yes | yes | yes | yes | yes | yes (PNG) |
| Alacritty | yes | yes | yes | yes | yes | no |
| Konsole | yes | yes | yes | yes | yes | no |

<img src="docs/screenshots/appearance.png" alt="Terminal Appearance page" width="760">

### Prompt Designer
Pick a prompt style with a live preview that shows both a normal command and a failed one. Minimal,
Classic and Two-line work in plain Bash with nothing to install. Two more styles use
[Starship](https://starship.rs) if you have it.

<img src="docs/screenshots/prompt.png" alt="Prompt Designer page" width="760">

### ASCII Art Studio
Start from the built-in gallery, or turn any picture into text art with live controls for width,
contrast, brightness, invert and character style. Conversion happens on your computer, and the art can
appear above your greeting when a terminal opens.

<img src="docs/screenshots/ascii.png" alt="ASCII Art Studio page" width="760">

### AI Companion
Everything here works offline: built-in tips and a command explainer that gives clear warnings for risky
commands such as `rm -rf /`. If you like, connect **Groq, OpenAI, OpenRouter** or a local **Ollama** to
write greetings in a personality you choose, or to explain commands in more detail. Greetings are saved
to a plain file, so opening a terminal never waits on the internet.

<img src="docs/screenshots/companion.png" alt="AI Companion page" width="760">

### Backups & Recovery
Restore any backup, remove everything the app added, switch between dark and light mode, or turn off
animations.

<img src="docs/screenshots/settings.png" alt="Backups and Settings page" width="760">

**Keyboard:** `Ctrl+1` to `Ctrl+7` jump between pages.

## Install

**Requirements:** a GNOME-based Linux desktop (built for Zorin OS 18 / Ubuntu 24.04), Python 3.10 or newer,
and Bash.

```bash
# 1. Dependencies (usually already installed on Zorin OS)
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 librsvg2-common

# 2. Get the app
git clone https://github.com/AbduLz0/fun-cli.git
cd fun-cli

# 3a. Try it straight from the folder...
./run.sh

# 3b. ...or install it for your user (menu entry + launcher, no sudo)
./install.sh
```

**Optional extras** (the app works fine without them): `starship` for the Starship prompts,
`fastfetch` for the system summary, and `libsecret-tools` to keep API keys in your desktop keyring.

## Quick start

1. Open **Welcome & MOTD**, pick a mood and write a greeting. The preview updates as you type.
2. Optionally visit **Prompt Designer** and **ASCII Art Studio**.
3. Press **Apply to Bash** and confirm. A backup is made first.
4. Open a new terminal to see the result. Changed your mind? Press **Undo**.

For terminal colours and fonts, open **Terminal Appearance**, choose your terminal and press
**Apply theme**.

## Safety

Changing a shell's startup file is a little risky, so the app is built to be careful.

- **Backup first.** Every change creates a timestamped backup, and every apply has an Undo.
- **Only our section.** `~/.bashrc` is edited only between marker lines. If the markers are damaged,
  the app stops with a clear message and changes nothing.
- **Safe writes.** Files are written atomically and symlinks are respected, so dotfile managers keep working.
- **No admin rights.** Nothing needs `sudo`. Only interactive shells are affected.
- **Fast and offline at startup.** Opening a terminal makes no network calls.
- **Text can't run code.** Anything you type is quoted and stripped of control characters. Git branch names
  shown in the prompt are filtered too, so a branch named `$(...)` can't execute anything.
- **Your Starship config is safe.** The app uses its own config file and never overwrites yours.
- **Keys stay private.** API keys are never written to settings or shell files. They live in memory, or in
  your desktop keyring if you switch that on.

**Undoing by hand.** The app only touches the lines between
`# >>> Terminal Experience Studio >>>` and `# <<< Terminal Experience Studio <<<`, plus an optional second
block ending in `: prompt`. Backups are in `~/.local/share/terminal-experience-studio/backups/`.

## Uninstall

1. Open the app, go to **Backups & Settings** and press **Remove from my shell** (this is undoable too).
2. Run `./uninstall.sh`. Add `--purge` to also delete saved settings and backups.

If the app is already gone, delete the Terminal Experience Studio blocks from `~/.bashrc` by hand.

## Project layout

```
tes/core/        logic with no GUI: settings, themes, bash config, prompts, backups, AI, explainer
tes/adapters/    one file per terminal, each declaring exactly what it supports
tes/ui/          GTK4 / Libadwaita window, pages, animations, custom widgets, style.css
tests/           unit tests plus a GUI end-to-end test
legacy/          the original v0.1.0 and v0.2.0 Tkinter prototypes
```

Support for another terminal is one new class in `tes/adapters/`.

## Development

```bash
# Unit tests (no display needed)
python3 -m unittest discover -s tests -p "test_*.py"

# End-to-end test that drives the real window (needs xvfb)
GSK_RENDERER=cairo xvfb-run -a python3 tests/gui_e2e.py
```

Contributions and bug reports are welcome. Please open an issue first for larger changes.

## Known limits

- Shell integration supports **Bash** only. Zsh and Fish are not implemented yet.
- The GNOME Terminal adapter has been tested against a simulated `gsettings`. If anything behaves oddly on
  your desktop, please open an issue.
- Konsole needs one manual step: choose the "Terminal Experience Studio" profile from Konsole's
  Settings menu.
- Starship styles only take effect once Starship is installed.
- AI is called only when you press a button, never when a terminal starts.

## Roadmap

- [ ] `.deb` and Flatpak packaging
- [ ] Zsh and Fish support
- [ ] More terminals (WezTerm, Ghostty)
- [ ] A companion that reacts to failed commands
- [ ] Time-of-day AI greetings

## Changelog

### 1.0.0
Complete rebuild on GTK4 and Libadwaita.

- New animated interface with live previews and a floating, blinking companion
- Terminal Appearance with adapters for GNOME Terminal, Kitty, Alacritty and Konsole
- Prompt Designer with Bash and Starship styles
- ASCII Art Studio with picture-to-ASCII conversion
- Offline-first AI Companion with optional Groq, OpenAI, OpenRouter and Ollama support
- Backups & Recovery with Undo for every change
- Old settings and backups from earlier versions are migrated automatically

### 0.2.0 and 0.1.0
Tkinter prototypes, kept in [`legacy/`](legacy/).

## License

Add your chosen license here (for example MIT) and include a `LICENSE` file in the repo.
