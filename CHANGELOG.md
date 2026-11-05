# Changelog

## v1.3.2 – 2026-11-05

### Wave Link Linux (wave-link-linux)
- StreamController ChannelDial: Stummschaltung reagiert jetzt auch auf Short- und Long-Touch am Drehregler (Touchscreen), nicht nur auf klassischen Dial-/Key-Down.

## v1.3.1 – 2026-11-04

### Repo
- Changelog ergänzt: Hinweis auf das private Archiv [hd60s-archive](https://github.com/Bavarian4736/hd60s-archive) mit den HD60-Releases 1.0.0 und 1.1.0.
- Keine Änderungen am Programmcode; Installer und RPM-Paket entsprechen v1.3.0.

## v1.3.0 – 2026-11-02

### HD60 (capture-card) – Stand HD60 1.1.0
- Vorschau überarbeitet: HDMI-Modus der Karte wird erkannt und übernommen.
- Virtuelle Kamera für Discord entfernt. Discord und andere Programme nehmen das Eingabegerät „Game Capture HD60 S“ und übertragen das HD60-Fenster wie jedes andere Fenster. Eine früher angelegte v4l2loopback-Kamera wird bei der Installation entfernt.
- Workaround gegen hängende Bildschirmübertragung in Discord (DMA-Puffer deaktiviert).
- RPM-Paket für Nobara und Fedora: `capture-card/packaging/build-rpm.sh` und `hd60s.spec`.
- Automatische Treiber-Installation über pkexec bleibt erhalten, prüft jetzt nur noch den HD60-S-Treiber.

### Wave Link Linux (wave-link-linux)
- Änderungen aus dem früheren Repo Spurwerk übernommen: Regler und Stummschaltung bleiben mit dem StreamController-Drehregler synchron, ohne Rückkopplung.

### Repo
- HD60 und Wave Link Linux werden nur noch in Elgato for Linux gepflegt; Verweise auf die alten Einzelrepos entfernt.
- Die ältere HD60-Historie mit den Releases HD60 1.0.0 und 1.1.0 liegt im privaten Archiv [hd60s-archive](https://github.com/Bavarian4736/hd60s-archive).
