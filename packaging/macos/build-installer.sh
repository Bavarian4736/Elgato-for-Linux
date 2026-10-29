#!/usr/bin/env bash
# Baut Studio-macOS-Installer.zip (unsigned .command + Payload).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${1:-"${ROOT}/dist"}"
VERSION="${STUDIO_VERSION:-dev}"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

APP_NAME="Studio Installer"
STAGE_APP="${STAGE}/${APP_NAME}"
mkdir -p "${OUT_DIR}" "${STAGE_APP}/packaging"

rsync -a \
  --exclude '.git' \
  --exclude '.github' \
  --exclude 'dist' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'packaging/linux' \
  --exclude 'packaging/windows' \
  --exclude 'packaging/macos' \
  "${ROOT}/" "${STAGE_APP}/"

rsync -a "${ROOT}/packaging/common/" "${STAGE_APP}/packaging/common/"
cp "${ROOT}/packaging/macos/Studio-Installer.command" "${STAGE_APP}/Studio-Installer.command"
chmod +x "${STAGE_APP}/Studio-Installer.command" \
  "${STAGE_APP}/packaging/common/chooser.py"

cat > "${STAGE_APP}/LIESMICH-macOS.txt" << EOF
Studio macOS Installer (${VERSION})
===================================

Doppelklick auf „Studio-Installer.command“.
Beim ersten Start ggf. Rechtsklick → Öffnen (Gatekeeper, unsigned).

Im Fenster (oder Terminal-Menü) HD60, Wave Link Linux oder beides wählen.

Hinweis: Beide Programme laufen vollständig nur unter Linux (Nobara/Fedora).
Unter macOS kopiert der Installer das gewählte Paket nach
~/Applications/Studio — zum Übertragen auf einen Linux-Rechner oder in eine VM.

Für die echte Installation den Linux-Installer von GitHub Releases nutzen:
https://github.com/Bavarian4736/studio/releases
EOF

OUT="${OUT_DIR}/Studio-macOS-Installer.zip"
rm -f "${OUT}"
# zip von innerhalb der Stage, damit der Ordnername im Archiv liegt
(
  cd "${STAGE}"
  zip -r "${OUT}" "${APP_NAME}" -x '*.pyc' -x '*__pycache__*'
)

echo "Geschrieben: ${OUT}"
ls -lh "${OUT}"
