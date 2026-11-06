# Changelog

## Unreleased

### Versionen
- Wave Link zeigt Komponentenversion 1.1.0 und die Suite Elgato for Linux (derzeit 1.3.3). Die stehengebliebene Angabe 1.0.0 ist entfernt.
- HD60-Programm bleibt 1.1.0. Der Treiber bleibt hd60s/0.1 und wird nicht auf die Suite- oder Programmversion gesetzt.
- Das StreamController-Plugin meldet seine VERSION-Datei 1.1.0. Spotify bleibt 1.2.0, die Touchbar-Hintergründe bleiben 1.0.0.
- Installer und RPM schreiben einen Build-Stempel. Ein Release-Tag, der nicht zur Datei `VERSION` passt, bricht den Build ab.

## v1.3.3 – 2026-11-06

### Wave Link Linux (wave-link-linux)
- Aktuellen Stand aus dem lokalen Wave-Link-Ordner übernommen (ohne den Ordner zu löschen).
- Pegelanzeige: eigene Peak-Meter an Monitor- und Stream-Regler, Farben und Stummschaltung wie am Stream-Deck-ChannelDial.
- Start hängt nicht mehr, wenn PipeWire nicht antwortet (Timeouts bei Verbindung und Bootstrap).
- Peak-Meter: eigener Polling-Thread statt GLib-Watch, damit die Anzeige nicht auf Null stehen bleibt.
- Wave Link erscheint in den GNOME-Schnelleinstellungen unter Hintergrundanwendungen.
- Neue Stream-Deck+-Touchbar-Hintergründe (teal/neon statt der Oktoberfest-Serie).
- Spurwerk-Installer, StreamController-Plugin, Spotify-Plugin und PipeWire-Setup aus dem Monorepo bleiben erhalten.

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
