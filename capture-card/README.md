# HD60

Eigenes Programm für die Elgato Game Capture HD60 S (`0fd9:005e`) auf Nobara und Fedora. Es zeigt das HDMI-Bild, spielt den Ton ab und kann das Bild an Discord weitergeben. OBS wird dafür nicht gebraucht.

Die Karte ist kein normales USB-Videogerät. `install.sh` installiert deshalb den Treiber von [dougg3/hd60s-linux-driver](https://github.com/dougg3/hd60s-linux-driver) (GPL-2.0, Doug Brown, Stand `34621f7`) und das Programm HD60. Fehlen der Kernel-Treiber oder v4l2loopback, holen `install.sh` und `hd60s` beides über pkexec nach.

## Voraussetzungen

- Nobara oder Fedora
- HD60 S an einem USB-3-Anschluss
- HDMI-Signal an der Karte

## Installation

Im Elgato-for-Linux-Monorepo:

```bash
git clone https://github.com/Bavarian4736/studio.git
cd studio
./install.sh
```

Nur HD60, aus dem Hauptverzeichnis des Monorepos:

```bash
./capture-card/install.sh
```

In diesem Ordner:

```bash
./install.sh
```

Das Skript fragt über pkexec nach dem Passwort. Danach liegt HD60 im Anwendungsmenü und unter `hd60s`. Startet man `hd60s`, solange der Kernel-Treiber oder die virtuelle Kamera fehlt, startet dieselbe Installation noch einmal.

Das frühere Einzelrepo bleibt unter https://github.com/Bavarian4736/hd60s-nobara bestehen.

## Bedienung

HD60 öffnen. Unten im Fenster:

- **HDMI / Klinke** wählt die Tonquelle der Karte.
- Der Lautsprecher schaltet den Ton an diesem Rechner an oder aus. Die Lautstärke daneben gilt nur für diese Wiedergabe.
- **Discord** legt das Bild auf eine virtuelle Kamera.

In Discord unter **Sprache & Video**:

- Kamera: **HD60**
- Eingabegerät: **HD60 S**

Das HD60-Fenster muss offen bleiben. Der Ton der Karte kommt nur an, solange das Bild läuft. Discord bekommt damit den HDMI-Ton, nicht das Mikrofon am Rechner.

## Entfernen

```bash
./install.sh --uninstall
```

Das entfernt HD60, den Treiber und die virtuelle Kamera.

## Lizenz

HD60, `install.sh` und diese Anleitung stehen unter der MIT-Lizenz. Der HD60-S-Treiber steht unter der GPL-2.0.
