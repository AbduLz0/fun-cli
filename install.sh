#!/usr/bin/env bash
# Per-user install: no sudo needed. Adds a launcher, menu entry and icons under ~/.local.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.local/share/terminal-experience-studio/app"
BIN="$HOME/.local/bin"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ID="dev.tes.TerminalExperienceStudio"

if ! python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null; then
  echo "Missing requirements. Please run:"
  echo "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 librsvg2-common"
  exit 1
fi

rm -rf "$APP"; mkdir -p "$APP" "$BIN" "$ICONS" "$APPS"
cp -r "$SRC/tes" "$SRC/app.py" "$APP/"
mkdir -p "$APP/data" && cp -r "$SRC/data/icons" "$APP/data/"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
cp -r "$SRC/data/icons/hicolor" "$ICONS/"

cat > "$BIN/terminal-experience-studio" <<LAUNCH
#!/usr/bin/env bash
exec python3 "$APP/app.py" "\$@"
LAUNCH
chmod +x "$BIN/terminal-experience-studio"
sed "s|@EXEC@|$BIN/terminal-experience-studio|" "$SRC/data/$ID.desktop" > "$APPS/$ID.desktop"

command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$ICONS/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" 2>/dev/null || true

echo "Installed. Find 'Terminal Experience Studio' in your app menu, or run: terminal-experience-studio"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "(Note: $BIN isn't on your PATH yet; the menu entry works regardless.)";; esac
