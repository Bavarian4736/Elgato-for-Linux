# Studio

Nobara-Werkzeuge für Aufnahme und Ton, in einem Verzeichnis.

| Ordner | Inhalt |
| --- | --- |
| `capture-card/` | **HD60**: Vorschau für die Elgato Game Capture HD60 S, plus Installer für den Kernel-Treiber und v4l2loopback |
| `wave-link-linux/` | **Wave Link Linux (Spurwerk)**: PipeWire-Mixer mit Monitor- und Stream-Mix |

Die älteren Einzelrepos bleiben bestehen und werden von diesem Repo nicht ersetzt:

- [Bavarian4736/hd60s-nobara](https://github.com/Bavarian4736/hd60s-nobara)
- [Bavarian4736/spurwerk](https://github.com/Bavarian4736/spurwerk)

## Download (GitHub Releases)

Fertige Installer — **ein Download pro Betriebssystem**. Beim Start wählen, ob HD60, Wave Link oder beides eingerichtet werden soll:

| OS | Datei |
| --- | --- |
| Linux | [Studio-Linux-Installer.sh](https://github.com/Bavarian4736/studio/releases/latest) |
| macOS | [Studio-macOS-Installer.zip](https://github.com/Bavarian4736/studio/releases/latest) |
| Windows | [Studio-Windows-Setup.exe](https://github.com/Bavarian4736/studio/releases/latest) |

➡️ Alle Assets: **[Releases](https://github.com/Bavarian4736/studio/releases/latest)**

Linux (empfohlen für die echte Installation auf Nobara/Fedora):

```bash
chmod +x Studio-Linux-Installer.sh
./Studio-Linux-Installer.sh
```

macOS: ZIP entpacken, Rechtsklick auf `Studio-Installer.command` → Öffnen.  
Windows: `Studio-Windows-Setup.exe` starten (unsigned — SmartScreen ggf. „Trotzdem ausführen“).

**Hinweis:** Beide Programme laufen vollständig unter Linux. macOS-/Windows-Installer legen ein Dateipaket ab (z. B. zum Übertragen auf Linux oder in eine VM). Details und Release-Workflow: `packaging/README.md`.

## Beides installieren (aus dem Repo)

```bash
git clone https://github.com/Bavarian4736/studio.git
cd studio
./install.sh
```

`./install.sh` installiert nacheinander HD60 und Wave Link. Mit Auswahlmenü: `./install.sh --choose`. Für den Kernel-Treiber erscheint einmal der pkexec-Dialog.

## Starten

Nach der Installation, aus dem Anwendungsmenü oder so:

```bash
hd60s
wavelink-linux
```

Direkt aus diesem Checkout, auch bevor die Programme im Menü liegen:

```bash
./hd60s
./wavelink-linux
```

`./hd60s` startet die Vorschau. `./wavelink-linux` startet den Mixer. Wave Link lässt sich zusätzlich über `./wave-link-linux/run.sh` starten.

## Treiber, die von selbst nachgezogen werden

HD60 braucht das Kernelmodul `hd60s` und eine virtuelle Kamera (`v4l2loopback`, Gerät `/dev/video10`, Name `HD60`). Wave Link braucht die PipeWire-Datei `~/.config/pipewire/pipewire.conf.d/99-wavelink.conf`.

| Befehl | Was passiert, wenn etwas fehlt |
| --- | --- |
| `./install.sh` | HD60-Installer über pkexec: Kernel-Treiber und v4l2loopback. Danach Wave Link, inklusive PipeWire-Setup |
| `./capture-card/install.sh` | derselbe HD60-Installer über pkexec |
| `hd60s` oder `./hd60s` | prüft Modul und virtuelle Kamera und startet `install.sh --ensure` über pkexec, falls eines von beiden fehlt |
| `./wave-link-linux/install.sh` | schreibt die PipeWire-Konfiguration, falls sie fehlt, und startet PipeWire neu |
| `wavelink-linux`, `./wavelink-linux` oder `./wave-link-linux/run.sh` | dieselbe PipeWire-Einrichtung beim Start, falls sie fehlt |

Secure Boot kann das Laden von `hd60s` blockieren. Der Installer sagt dann, wie der Nobara-Schlüssel mit `pkexec mokutil --import` eingeschrieben wird.

## Verzeichnis

```
studio/
├── install.sh
├── hd60s
├── wavelink-linux
├── README.md
├── packaging/          # OS-Installer + Release-Builds
├── capture-card/
│   ├── hd60s.py
│   ├── install.sh
│   ├── hd60s.desktop
│   └── hd60s.svg
└── wave-link-linux/
    ├── install.sh
    ├── run.sh
    ├── installer.py
    ├── pipewire/99-wavelink.conf
    └── wavelink_linux/
```

Details stehen in `capture-card/README.md` und `wave-link-linux/README.md`.

## Lizenz

HD60, die Installer und diese Anleitung stehen unter der MIT-Lizenz (`capture-card/LICENSE`). Der HD60-S-Treiber, den der Installer von [dougg3/hd60s-linux-driver](https://github.com/dougg3/hd60s-linux-driver) holt, steht unter der GPL-2.0.
