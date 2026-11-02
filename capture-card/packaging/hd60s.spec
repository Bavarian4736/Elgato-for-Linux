Name:           hd60s
Version:        1.1.0
Release:        1%{?dist}
Summary:        Bild und Ton der Elgato Game Capture HD60 S

License:        MIT AND GPL-2.0-only
URL:            https://github.com/Bavarian4736/hd60s-nobara
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       gstreamer1
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Requires:       pipewire-gstreamer
Requires:       v4l-utils
Requires:       dkms
Requires:       gcc
Requires:       make
Requires:       kmod
Recommends:     kernel-devel

%description
Zeigt das HDMI-Bild der Elgato Game Capture HD60 S und spielt den Ton ab.
Der Treiber von Doug Brown (GPL-2.0) wird beim Installieren für den
laufenden Kernel gebaut.

%prep
%autosetup

%build

%install
install -D -m 0755 hd60s.py %{buildroot}%{_bindir}/hd60s
install -D -m 0644 hd60s.desktop %{buildroot}%{_datadir}/applications/hd60s.desktop
install -D -m 0644 hd60s.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/hd60s.svg
mkdir -p %{buildroot}/usr/src/hd60s-0.1
cp -a driver/. %{buildroot}/usr/src/hd60s-0.1/
chmod 0644 %{buildroot}/usr/src/hd60s-0.1/*

%post
KEY=/etc/pki/akmods/private/private_key.priv
CERT=/etc/pki/akmods/certs/public_key.der
SIGNING=/etc/dkms/framework.conf.d/hd60s-signing.conf
KVER=$(uname -r)
mkdir -p /etc/dkms/framework.conf.d /etc/modules-load.d
if [ -f "$KEY" ] && [ -f "$CERT" ] && command -v mokutil >/dev/null 2>&1 && mokutil --test-key "$CERT" >/dev/null 2>&1; then
    printf 'try_sign_modules=true\nmok_signing_key=%s\nmok_certificate=%s\n' "$KEY" "$CERT" > "$SIGNING"
else
    printf 'try_sign_modules=false\n' > "$SIGNING"
fi
if [ ! -d "/lib/modules/${KVER}/build" ]; then
    echo "kernel-devel für ${KVER} fehlt." >&2
    echo "Paket installieren und danach ausführen: sudo dkms install hd60s/0.1 && sudo modprobe hd60s" >&2
    exit 0
fi
dkms add -m hd60s -v 0.1 >/dev/null 2>&1 || true
if dkms install -m hd60s -v 0.1; then
    echo hd60s > /etc/modules-load.d/hd60s.conf
    if ! modprobe hd60s; then
        echo "Der Treiber ist gebaut, wurde aber nicht geladen." >&2
        if [ -f "$CERT" ]; then
            echo "Bei aktivem Secure Boot den Schlüssel einschreiben, neu starten und Enroll MOK wählen:" >&2
            echo "  sudo mokutil --import ${CERT}" >&2
        fi
    fi
else
    echo "Der Treiber konnte nicht gebaut werden." >&2
    echo "Danach erneut: sudo dkms install hd60s/0.1 && sudo modprobe hd60s" >&2
fi

%preun
if [ "$1" = 0 ]; then
    if lsmod | grep -q '^hd60s '; then
        modprobe -r hd60s >/dev/null 2>&1 || true
    fi
    dkms remove -m hd60s -v 0.1 --all >/dev/null 2>&1 || true
    rm -f /etc/modules-load.d/hd60s.conf /etc/dkms/framework.conf.d/hd60s-signing.conf
fi

%files
%license LICENSE
%{_bindir}/hd60s
%{_datadir}/applications/hd60s.desktop
%{_datadir}/icons/hicolor/scalable/apps/hd60s.svg
/usr/src/hd60s-0.1

%changelog
* Mon Nov 02 2026 Bavarian4736 <Bavarian4736@users.noreply.github.com> - 1.1.0-1
- Erstes RPM-Paket mit Programm und DKMS-Treiber.
