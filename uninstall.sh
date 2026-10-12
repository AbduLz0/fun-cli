#!/usr/bin/env bash
# Removes the app. Your shell files are NOT touched: open the app first and use
# Backups & Settings > "Remove from my shell" if you also want the greeting/prompt gone.
# Add --purge to also delete saved settings and backups.
set -euo pipefail
ID="dev.tes.TerminalExperienceStudio"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$DATA/terminal-experience-studio/app"
rm -f "$HOME/.local/bin/terminal-experience-studio" "$DATA/applications/$ID.desktop"
rm -f "$DATA/icons/hicolor/scalable/apps/$ID.svg" "$DATA"/icons/hicolor/symbolic/apps/tes-*-symbolic.svg
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$DATA/terminal-experience-studio" "${XDG_CONFIG_HOME:-$HOME/.config}/terminal-experience-studio"
  echo "Settings and backups deleted."
else
  echo "Settings and backups kept (add --purge to delete them)."
fi
echo "Uninstalled. If your shell still shows the greeting, remove it from within the app first next time,"
echo "or delete the '# >>> Terminal Experience Studio' blocks from ~/.bashrc."
