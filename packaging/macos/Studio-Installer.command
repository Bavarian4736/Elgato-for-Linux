#!/bin/bash
# Doppelklick-Installer für macOS (Terminal). Wählt HD60 und/oder Wave Link.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display dialog "Python 3 fehlt. Bitte python.org oder Homebrew (brew install python) nutzen und erneut starten." buttons {"OK"} default button 1 with title "Studio Installer"' || true
  echo "Python 3 fehlt." >&2
  exit 1
fi

python3 "${ROOT}/packaging/common/chooser.py" "$@"
status=$?

echo
echo "Fenster schließen oder Taste drücken…"
read -r -n 1 || true
exit "${status}"
