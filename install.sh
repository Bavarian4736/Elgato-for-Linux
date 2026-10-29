#!/bin/bash
# Installiert HD60 und/oder Wave Link Linux auf Nobara oder Fedora.
# Ohne Argumente: beides. Mit --choose: interaktive Auswahl.
# HD60 holt sich Root-Rechte selbst über pkexec.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

if [[ "${1:-}" == "--choose" || "${1:-}" == "--select" ]]; then
  shift
  exec python3 "${ROOT}/packaging/common/chooser.py" "$@"
fi

if [[ "${1:-}" == "--hd60" || "${1:-}" == "--wavelink" || "${1:-}" == "--both" ]]; then
  exec python3 "${ROOT}/packaging/common/chooser.py" "$@"
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat << 'EOF'
Usage: ./install.sh [--choose | --both | --hd60 | --wavelink]

  (ohne Flags)  beide Programme nacheinander
  --choose      interaktive Auswahl (CLI oder GUI)
  --both        beide Programme
  --hd60        nur HD60
  --wavelink    nur Wave Link Linux
EOF
  exit 0
fi

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
