#!/usr/bin/env bash
# Run straight from this folder (no install needed).
cd "$(dirname "$0")" || exit 1
if ! python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null; then
  echo "Missing GTK4/Libadwaita bindings. Install them with:"
  echo "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 librsvg2-common"
  exit 1
fi
exec python3 app.py "$@"
