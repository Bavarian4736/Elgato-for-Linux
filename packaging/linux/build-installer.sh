#!/usr/bin/env bash
# Baut Studio-Linux-Installer.sh — selbstentpackendes Archiv mit Auswahl-Installer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${1:-"${ROOT}/dist"}"
VERSION="${STUDIO_VERSION:-dev}"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

mkdir -p "${OUT_DIR}" "${STAGE}/payload"

rsync -a \
  --exclude '.git' \
  --exclude '.github' \
  --exclude 'dist' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'packaging/linux' \
  "${ROOT}/" "${STAGE}/payload/"

mkdir -p "${STAGE}/payload/packaging"
rsync -a "${ROOT}/packaging/common/" "${STAGE}/payload/packaging/common/"

cat > "${STAGE}/payload/run-installer.sh" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${HERE}/packaging/common/chooser.py" "$@"
EOF

chmod +x "${STAGE}/payload/run-installer.sh" \
  "${STAGE}/payload/packaging/common/chooser.py"
chmod +x "${STAGE}/payload/install.sh" \
  "${STAGE}/payload/hd60s" \
  "${STAGE}/payload/wavelink-linux" \
  "${STAGE}/payload/capture-card/install.sh" \
  "${STAGE}/payload/wave-link-linux/install.sh" 2>/dev/null || true

ARCHIVE="${STAGE}/payload.tar.gz"
tar -C "${STAGE}" -czf "${ARCHIVE}" payload

MARKER="__STUDIO_ARCHIVE_BELOW__"
OUT="${OUT_DIR}/Studio-Linux-Installer.sh"

# Stub: Build-Zeit-Variablen expandieren, Laufzeit-Variablen escaped lassen.
cat > "${OUT}" << STUB
#!/usr/bin/env bash
# Studio Linux Installer (${VERSION})
# Entpackt das Paket und startet die Programmauswahl (HD60 / Wave Link / beides).
set -euo pipefail

VERSION="${VERSION}"
MARKER="${MARKER}"

echo "Studio Linux Installer \${VERSION}"
echo "Entpacke Paket…"

EXTRACT="\$(mktemp -d)"
cleanup() { rm -rf "\${EXTRACT}"; }
trap cleanup EXIT

ARCHIVE_LINE="\$(awk "/^\${MARKER}\$/{print NR+1; exit}" "\$0")"
if [[ -z "\${ARCHIVE_LINE}" ]]; then
  echo "Fehler: Archiv-Markierung nicht gefunden." >&2
  exit 1
fi
tail -n +"\${ARCHIVE_LINE}" "\$0" | tar -xz -C "\${EXTRACT}"

PAYLOAD="\${EXTRACT}/payload"
cd "\${PAYLOAD}"
bash "\${PAYLOAD}/run-installer.sh" "\$@"
exit \$?
STUB

# exit beendet die Shell, bevor Markierung/Binary als Code gelesen werden.
printf '%s\n' "${MARKER}" >> "${OUT}"
cat "${ARCHIVE}" >> "${OUT}"

chmod +x "${OUT}"
echo "Geschrieben: ${OUT}"
ls -lh "${OUT}"
