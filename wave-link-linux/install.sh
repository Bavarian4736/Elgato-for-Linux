#!/usr/bin/env bash
# Terminal-Variante. Zum Doppelklick Spurwerk-Setup.desktop verwenden.
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec python3 "$DIR/install_core.py" "$@"
