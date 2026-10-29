# WaveLink Linux

Wave-Link-ähnlicher Audio-Mixer für **Nobara / Fedora (GNOME)** mit **PipeWire**.

## Features

- Spuren wie in Wave Link: **System, Music, Browser, Voice Chat, Game, SFX, Auxiliary, Microphone**
- Zwei unabhängige Mixes: **Monitor Mix** (Headset) und **Stream Mix** (OBS). Discord nutzt **WaveLink Microphone** (nur Mic).
- Programme per **Drag & Drop** auf Spuren legen
- Pro Spur eigene Lautstärke für Monitor und Stream (+ Mute)
- **Stream Deck +** Steuerung über StreamController (4 Drehregler)

## Installation

Im Elgato-for-Linux-Monorepo richtet `./install.sh` im Hauptverzeichnis HD60 und Wave Link zusammen ein. Nur dieser Mixer, in diesem Ordner:

Doppelklick auf **Spurwerk-Setup.desktop**. Im Fenster lässt sich die StreamController-Erweiterung an- oder abwählen. Über „Nur die Erweiterung installieren“ kommt man zur Einrichtung ohne den Mixer.

Nur das Stream-Deck-Plugin, als eigenes Programm: **Spurwerk-Plugin-Setup.desktop**.

Im Terminal:

```bash
./install.sh
./install.sh --no-plugin
./install.sh --plugin-only
```

Die Installation schreibt `~/.config/pipewire/pipewire.conf.d/99-wavelink.conf`, wenn diese Datei fehlt, und startet PipeWire dann neu.

Danach im Menü **WaveLink Linux** starten oder:

```bash
wavelink-linux
```

Ohne Installation direkt aus dem Ordner:

```bash
./run.sh
```

`wavelink-linux` und `./run.sh` legen die PipeWire-Spuren ebenfalls an, falls die Konfiguration noch fehlt.

Das frühere Einzelrepo bleibt unter https://github.com/Bavarian4736/spurwerk bestehen.

## Nutzung

1. App starten — virtuelle Spuren und Loopbacks werden angelegt.
2. Unten **Monitor-Ausgang** auf dein Headset setzen.
3. Programme links greifen und auf eine Spur ziehen.
4. In **OBS** als Audio-Eingang den Monitor von **WaveLink Stream Mix** wählen  
   (technischer Name: `wavelink_stream.monitor`).
5. In **Discord** als Mikrofon **Monitor of WaveLink Microphone** wählen (nicht Stream Mix — der enthält Desktop-Audio).

## Stream Deck + (StreamController)

Voraussetzung: Flatpak **StreamController** (`com.core447.StreamController`). Die Erweiterung wird nur mitinstalliert, wenn du sie im Einrichtungsfenster anlässt — oder separat über **Spurwerk-Plugin-Setup.desktop**.

1. WaveLink starten (API: `http://127.0.0.1:24772`)
2. StreamController **neu starten**
3. Action **WaveLink → Channel Dial** auf die 4 Drehregler ziehen
4. Pro Regler Spur + Mix wählen (z. B. Music/Voice/Game/Mic)

| Regler | Wirkung |
|--------|---------|
| Drehen | Lautstärke |
| Drücken | Mute |

Details: `streamcontroller_plugin/README.md`

## Hinweis zu Easy Effects

Wenn Easy Effects dein Standard-Sink ist, laufen neue Apps zuerst dort. Ziehe sie in WaveLink auf die gewünschte Spur. Für den Monitor-Pfad kannst du Easy Effects später auf den Monitor-Mix legen — oder WaveLink direkt aufs Headset ausgeben.

## Deinstallation

```bash
./install.sh --uninstall
```

Entfernt Programmordner, Starter, Desktop-Eintrag, PipeWire-Konfiguration und (falls vorhanden) die StreamController-Plugins. PipeWire wird danach neu gestartet.

Über den Elgato-for-Linux-Installer: Deinstallieren wählen, oder `./install.sh --uninstall --wavelink` im Monorepo.
