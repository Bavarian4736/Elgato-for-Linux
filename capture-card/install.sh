#!/bin/bash
# Installiert den Elgato-HD60-S-Treiber und das Programm HD60
# auf Nobara und Fedora. Der Treiber selbst kommt von
# https://github.com/dougg3/hd60s-linux-driver (GPL-2.0).
set -euo pipefail

DRIVER_REPO="https://github.com/dougg3/hd60s-linux-driver.git"
DRIVER_COMMIT="34621f7184b602ae7797d206ab2c9627cc045d1a"
SCRIPT="$(readlink -f "$0")"
ROOT="$(cd "$(dirname "${SCRIPT}")" && pwd)"
SRC="/usr/local/src/hd60s-linux-driver"
LIBEXEC="/usr/local/libexec/hd60s"
KEY="/etc/pki/akmods/private/private_key.priv"
CERT="/etc/pki/akmods/certs/public_key.der"
SIGNING_CONF="/etc/dkms/framework.conf.d/hd60s-signing.conf"
LOOPBACK_CONF="/etc/modprobe.d/v4l2loopback-hd60.conf"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

if [[ "$(id -u)" -ne 0 ]]; then
  if ! command -v pkexec >/dev/null 2>&1; then
    die "pkexec fehlt. Polkit wird gebraucht, damit der Treiber installiert werden kann."
  fi
  exec pkexec /bin/bash "${SCRIPT}" "$@"
fi

driver_version() {
  sed -n 's/^PACKAGE_VERSION="\(.*\)"/\1/p' "${SRC}/dkms.conf"
}

drivers_ready() {
  [[ -d /sys/module/hd60s ]] || return 1
  [[ -d /sys/module/v4l2loopback ]] || return 1
  [[ -r /sys/class/video4linux/video10/name ]] || return 1
  [[ "$(tr -d '[:space:]' < /sys/class/video4linux/video10/name)" == "HD60" ]]
}

try_load_installed() {
  [[ -f "${LOOPBACK_CONF}" ]] || return 1
  modinfo hd60s >/dev/null 2>&1 || return 1
  modinfo v4l2loopback >/dev/null 2>&1 || return 1
  if ! drivers_ready; then
    modprobe -r v4l2loopback 2>/dev/null || true
    modprobe v4l2loopback || return 1
    if [[ ! -d /sys/module/hd60s ]]; then
      modprobe hd60s || return 1
    fi
  fi
  drivers_ready
}

uninstall_driver() {
  local ver="0.1"
  if [[ -f "${SRC}/dkms.conf" ]]; then
    ver="$(driver_version)"
  fi
  if lsmod | grep -q '^hd60s '; then
    for node in /sys/bus/usb/drivers/hd60s/*:*; do
      [[ -e "${node}" ]] || continue
      basename "${node}" > /sys/bus/usb/drivers/hd60s/unbind || true
    done
    modprobe -r hd60s || true
  fi
  modprobe -r v4l2loopback || true
  dkms remove "hd60s/${ver}" --all 2>/dev/null || true
  rm -rf "/usr/src/hd60s-${ver}" "${SRC}" /usr/local/share/hd60s-nobara "${LIBEXEC}"
  rm -f /etc/modules-load.d/hd60s.conf "${SIGNING_CONF}" "${LOOPBACK_CONF}" \
    /etc/modprobe.d/v4l2loopback-obs.conf \
    /usr/local/bin/hd60s \
    /usr/local/share/applications/hd60s.desktop \
    /usr/local/share/icons/hicolor/scalable/apps/hd60s.svg
  echo "HD60, Treiber und virtuelle Kamera sind entfernt."
}

ENSURE=0
if [[ "${1:-}" == "--uninstall" ]]; then
  uninstall_driver
  exit 0
fi
if [[ "${1:-}" == "--ensure" ]]; then
  ENSURE=1
elif [[ -n "${1:-}" ]]; then
  die "Unbekanntes Argument: $1  (erlaubt sind --ensure und --uninstall)"
fi

[[ -r /etc/os-release ]] || die "Keine /etc/os-release gefunden."
# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-} ${ID_LIKE:-}" in
  *nobara*|*fedora*) ;;
  *) die "Dieses Skript ist für Nobara und Fedora. Erkannt: ${PRETTY_NAME:-unbekannt}." ;;
esac

KVER="$(uname -r)"
if ! lsusb -d 0fd9:005e >/dev/null 2>&1; then
  echo "Hinweis: Die HD60 S (0fd9:005e) ist gerade nicht eingesteckt. Der Treiber wird trotzdem installiert."
fi

if [[ "${ENSURE}" -eq 1 ]]; then
  if drivers_ready || try_load_installed; then
    echo "Kernel-Treiber und virtuelle Kamera sind bereit."
    exit 0
  fi
  log "Kernel-Treiber oder v4l2loopback fehlt und wird installiert"
fi

log "Pakete installieren"
if [[ ! -d "/lib/modules/${KVER}/build" ]]; then
  dnf install -y "kernel-devel-uname-r = ${KVER}"
fi
dnf install -y git dkms gcc make zstd v4l-utils akmod-v4l2loopback \
  python3 python3-gobject gtk4 libadwaita \
  gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good \
  gstreamer1-plugin-gtk4 pipewire-gstreamer

log "Virtuelle Kamera bauen"
akmods --force --kernels "${KVER}"
cat > "${LOOPBACK_CONF}" << 'EOF'
options v4l2loopback devices=1 video_nr=10 card_label="HD60" exclusive_caps=1
EOF
rm -f /etc/modprobe.d/v4l2loopback-obs.conf
modprobe -r v4l2loopback 2>/dev/null || true
modprobe v4l2loopback

log "HD60-S-Treiber holen (${DRIVER_COMMIT})"
rm -rf "${SRC}"
mkdir -p "${SRC}"
git -C "${SRC}" init
git -C "${SRC}" remote add origin "${DRIVER_REPO}"
git -C "${SRC}" fetch --depth 1 origin "${DRIVER_COMMIT}"
git -C "${SRC}" checkout --detach FETCH_HEAD
install -d /usr/local/bin /usr/local/share/applications /usr/local/share/icons/hicolor/scalable/apps "${LIBEXEC}"
install -m 0755 "${ROOT}/hd60s.py" /usr/local/bin/hd60s
install -m 0755 "${SCRIPT}" "${LIBEXEC}/install.sh"
install -m 0755 "${ROOT}/hd60s.py" "${LIBEXEC}/hd60s.py"
install -m 0644 "${ROOT}/hd60s.desktop" /usr/local/share/applications/hd60s.desktop
install -m 0644 "${ROOT}/hd60s.desktop" "${LIBEXEC}/hd60s.desktop"
install -m 0644 "${ROOT}/hd60s.svg" /usr/local/share/icons/hicolor/scalable/apps/hd60s.svg
install -m 0644 "${ROOT}/hd60s.svg" "${LIBEXEC}/hd60s.svg"
update-desktop-database /usr/local/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache -f /usr/local/share/icons/hicolor >/dev/null 2>&1 || true

if [[ ! -f "${KEY}" || ! -f "${CERT}" ]]; then
  log "Signierschlüssel für Kernelmodule anlegen"
  kmodgenca -a
fi

enrolled=0
if mokutil --test-key "${CERT}" >/dev/null 2>&1; then
  enrolled=1
fi

log "Treiber per DKMS installieren"
mkdir -p /etc/dkms/framework.conf.d
if [[ "${enrolled}" -eq 1 ]]; then
  cat > "${SIGNING_CONF}" << EOF
try_sign_modules=true
mok_signing_key=${KEY}
mok_certificate=${CERT}
EOF
else
  cat > "${SIGNING_CONF}" << 'EOF'
try_sign_modules=false
EOF
fi

VER="$(driver_version)"
if lsmod | grep -q '^hd60s '; then
  for node in /sys/bus/usb/drivers/hd60s/*:*; do
    [[ -e "${node}" ]] || continue
    basename "${node}" > /sys/bus/usb/drivers/hd60s/unbind || true
  done
  modprobe -r hd60s || true
fi
dkms remove "hd60s/${VER}" --all 2>/dev/null || true
rm -rf "/usr/src/hd60s-${VER}"
mkdir -p "/usr/src/hd60s-${VER}"
cp "${SRC}/Makefile" "${SRC}/dkms.conf" "${SRC}/"*.c "${SRC}/"*.h "${SRC}/LICENSE.txt" "/usr/src/hd60s-${VER}/"
dkms install "hd60s/${VER}"
echo hd60s > /etc/modules-load.d/hd60s.conf

if [[ "${enrolled}" -ne 1 ]]; then
  rm -f "${SIGNING_CONF}"
fi

if ! modprobe hd60s; then
  if [[ "${enrolled}" -ne 1 ]]; then
    cat << EOF

Das Modul ist installiert, der Kernel verlangt aber eine Signatur.
Secure Boot ist aktiv und der Nobara-Schlüssel ist noch nicht eingeschrieben.

  pkexec mokutil --import ${CERT}

Merke dir das Passwort, starte neu und wähle im blauen Menü "Enroll MOK".
Die Tastatur ist dort QWERTY. Danach dieses Skript noch einmal ausführen.
EOF
    exit 1
  fi
  die "hd60s.ko konnte nicht geladen werden. dmesg zeigt den Grund."
fi

target_user=""
if [[ -n "${PKEXEC_UID:-}" ]]; then
  target_user="$(id -nu "${PKEXEC_UID}" 2>/dev/null || true)"
elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  target_user="${SUDO_USER}"
fi
if [[ -n "${target_user}" && "${target_user}" != "root" ]]; then
  usermod -aG video "${target_user}" || true
fi

cat << EOF

Fertig. HD60 starten:

  hd60s

oder im Anwendungsmenü „HD60“ öffnen. Das Fenster zeigt Bild und Ton.
Es muss offen bleiben, sonst bleibt die Karte stumm.

Fehlen der Kernel-Treiber oder die virtuelle Kamera später, installiert
hd60s beides über pkexec nach.

Discord, falls du das Bild weitergeben willst:
  Im HD60-Fenster „Discord“ einschalten.
  In Discord Kamera „HD60“ und Eingabegerät „HD60 S“ wählen.

HDMI an die Karte hängen und sie an einem USB-3-Port lassen.
EOF
