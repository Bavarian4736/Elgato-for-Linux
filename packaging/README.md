# Packaging — Elgato for Linux Installer

Baut **`Elgato-for-Linux-Installer.sh`** für GitHub Releases. Beim Start **Installieren** oder **Deinstallieren**, danach HD60 und/oder Wave Link Linux wählen.

Beide Programme sind für **Nobara/Fedora (Linux)**.

## Lokal bauen

```bash
./packaging/linux/build-installer.sh dist
```

## Release

Die Suite-Version steht in `VERSION` im Repo-Root und muss zum Tag passen. Komponenten (Wave Link, HD60-Programm, Plugins, Treiber `hd60s/0.1`) haben eigene `VERSION`-Dateien und werden nicht auf den Suite-Tag gesetzt.

```bash
# Der Tag muss VERSION entsprechen. Steht dort 1.3.3:
git tag v1.3.3
git push origin v1.3.3
```

Oder Actions → **Release Linux installer** → Run workflow.

Workflow: `.github/workflows/release.yml` — baut den Linux-Installer und hängt ihn an das GitHub Release.
