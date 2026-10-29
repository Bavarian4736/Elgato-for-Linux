# Packaging — Studio-Installer

Baut **einen Download pro OS** für GitHub Releases. Jeder Installer lässt HD60 und/oder Wave Link Linux wählen.

| OS | Artefakt | Auswahl |
| --- | --- | --- |
| Linux | `Studio-Linux-Installer.sh` | CLI/GUI (`chooser.py`) |
| macOS | `Studio-macOS-Installer.zip` | `.command` → `chooser.py` |
| Windows | `Studio-Windows-Setup.exe` | Inno-Komponenten (+ ZIP-Fallback) |

## Lokal bauen

```bash
# Linux
./packaging/linux/build-installer.sh dist

# macOS
./packaging/macos/build-installer.sh dist

# Windows (PowerShell)
./packaging/windows/build-installer.ps1 -OutDir dist -Version 1.0.0
```

## Release

Tag pushen oder Workflow manuell starten:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Workflow: `.github/workflows/release.yml` — baut alle drei Installer und hängt sie an das GitHub Release.

## Hinweis zu macOS / Windows

Beide Programme brauchen Nobara/Fedora (Kernel-Treiber bzw. PipeWire). Die macOS-/Windows-Installer sind unsigned und legen ein **Dateipaket** ab; die volle Installation läuft über den Linux-Installer.
