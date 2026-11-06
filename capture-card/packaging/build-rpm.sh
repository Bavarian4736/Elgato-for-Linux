#!/bin/bash
# Baut hd60s-<version>.noarch.rpm inklusive des HD60-S-Treibers.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
SPEC="${ROOT}/packaging/hd60s.spec"
VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$SPEC")"
DRIVER_REPO="https://github.com/dougg3/hd60s-linux-driver.git"
DRIVER_COMMIT="34621f7184b602ae7797d206ab2c9627cc045d1a"
WORKDIR="$(mktemp -d)"
TOP="${WORKDIR}/top"
TREE="${WORKDIR}/hd60s-${VERSION}"

cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

mkdir -p "$TREE/driver" "${TOP}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
install -m 0755 "${ROOT}/hd60s.py" "${TREE}/hd60s.py"
install -m 0644 "${ROOT}/version_info.py" "${TREE}/version_info.py"
install -m 0644 "${ROOT}/../packaging/common/versions.py" "${TREE}/_elgato_versions.py"
install -m 0644 "${ROOT}/VERSION" "${TREE}/VERSION"
install -m 0644 "${ROOT}/DRIVER_VERSION" "${TREE}/DRIVER_VERSION"
install -m 0755 "${ROOT}/hd60s-launch" "${TREE}/hd60s-launch"
install -m 0644 "${ROOT}/hd60s.desktop" "${TREE}/hd60s.desktop"
install -m 0644 "${ROOT}/hd60s.svg" "${TREE}/hd60s.svg"
install -m 0644 "${ROOT}/LICENSE" "${TREE}/LICENSE"
python3 "${ROOT}/../packaging/common/versions.py" stamp \
  --root "${ROOT}/.." --dest "${TREE}" --component hd60

mkdir -p "${WORKDIR}/driver-src"
git -C "${WORKDIR}/driver-src" init
git -C "${WORKDIR}/driver-src" remote add origin "${DRIVER_REPO}"
git -C "${WORKDIR}/driver-src" fetch --depth 1 origin "${DRIVER_COMMIT}"
git -C "${WORKDIR}/driver-src" checkout --detach FETCH_HEAD
cp "${WORKDIR}/driver-src/Makefile" "${WORKDIR}/driver-src/dkms.conf" \
   "${WORKDIR}/driver-src/"*.c "${WORKDIR}/driver-src/"*.h \
   "${WORKDIR}/driver-src/LICENSE.txt" "${TREE}/driver/"

tar -C "$WORKDIR" -czf "${TOP}/SOURCES/hd60s-${VERSION}.tar.gz" "hd60s-${VERSION}"
rpmbuild --define "_topdir ${TOP}" -bb "$SPEC"
find "${TOP}/RPMS" -type f -name '*.rpm' -exec cp -t "${ROOT}/packaging" {} +
echo "Fertig: ${ROOT}/packaging/hd60s-${VERSION}"*.rpm
