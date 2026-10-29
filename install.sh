#!/bin/bash
# Installiert HD60 und Wave Link Linux auf Nobara oder Fedora.
# HD60 holt sich Root-Rechte selbst über pkexec.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
status=0

echo "==> HD60 (Kernel-Treiber, v4l2loopback, Programm)"
"${ROOT}/capture-card/install.sh" || status=$?

echo "==> Wave Link Linux (Mixer und PipeWire-Spuren)"
"${ROOT}/wave-link-linux/install.sh" || status=$?

if [[ "${status}" -ne 0 ]]; then
  printf 'Installation unvollständig (Exit %s).\n' "${status}" >&2
  exit "${status}"
fi

cat << 'EOF'

Beides ist installiert.

  hd60s
  wavelink-linux

Fehlen der HD60-Treiber oder die virtuelle Kamera, holt hd60s sie über pkexec nach.
Fehlt die PipeWire-Konfiguration, legt Wave Link sie beim Start an.
EOF
