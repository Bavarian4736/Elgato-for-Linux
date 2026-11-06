# HD60

Eigenes Programm für die Elgato Game Capture HD60 S (`0fd9:005e`) auf Nobara und Fedora. Es zeigt das HDMI-Bild und spielt den Ton ab. OBS wird dafür nicht gebraucht.

Die Karte ist kein normales USB-Videogerät. `install.sh` installiert deshalb den Treiber von [dougg3/hd60s-linux-driver](https://github.com/dougg3/hd60s-linux-driver) (GPL-2.0, Doug Brown, Stand `34621f7`) und das Programm HD60.

## Voraussetzungen

- Nobara oder Fedora
- HD60 S an einem USB-3-Anschluss
- HDMI-Signal an der Karte

## Installation

Am einfachsten über den Installer von Elgato for Linux im Hauptverzeichnis (HD60, Wave Link oder beides):

```bash
git clone https://github.com/Bavarian4736/Elgato-for-Linux.git
cd Elgato-for-Linux
./install.sh --hd60
```

Oder nur HD60 aus diesem Ordner:

```bash
./capture-card/install.sh
```

Nur das Programm austauschen, ohne den Treiber neu zu bauen oder Audio-Dienste neu zu starten:

```bash
./capture-card/install.sh --userspace
```

Das Skript fragt über pkexec nach dem Passwort. Danach liegt HD60 im Anwendungsmenü und unter `hd60s`. Fehlt der Kernel-Treiber später (zum Beispiel nach einem Kernel-Update), startet `hd60s` dieselbe Installation noch einmal.

### Als RPM

Die RPM liegt bei den [Releases](https://github.com/Bavarian4736/Elgato-for-Linux/releases/latest):

```bash
sudo dnf install ./hd60s-1.1.0-1.fc44.noarch.rpm
```

Sie legt das Programm ins Anwendungsmenü und baut den Treiber für den laufenden Kernel. Dafür muss `kernel-devel` zu diesem Kernel passen. Bei aktivem Secure Boot muss der Signierschlüssel einmal eingeschrieben werden. Die Ausgabe von `dnf` sagt, falls das nötig ist.

Selbst bauen (ohne Root, braucht `rpm-build`): `./capture-card/packaging/build-rpm.sh`

## Bedienung

HD60 öffnen. Unten im Fenster:

- **HDMI / Klinke** wählt die Tonquelle der Karte.
- Der Lautsprecher schaltet den Ton an diesem Rechner an oder aus. Die Lautstärke daneben gilt nur für diese Wiedergabe.
- Der Vollbild-Knopf, **F11** oder ein Doppelklick legt das Bild über den ganzen Bildschirm. **Escape** beendet das.

Das Fenster muss offen bleiben, sonst bleibt die Karte stumm. Der Ton heißt dann **Game Capture HD60 S**. Discord und jedes andere Programm nehmen dasselbe Eingabegerät. Das Bild überträgst du, indem du das HD60-Fenster auswählst, so wie jedes andere Fenster.

## Entfernen

```bash
./capture-card/install.sh --uninstall
```

Das entfernt HD60, den Treiber und eine früher angelegte virtuelle Kamera.

## Lizenz

HD60, `install.sh` und diese Anleitung stehen unter der MIT-Lizenz. Der HD60-S-Treiber steht unter der GPL-2.0.
