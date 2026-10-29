# Packaging — Elgato for Linux Installer

Baut **`Elgato-for-Linux-Installer.sh`** für GitHub Releases. Beim Start **Installieren** oder **Deinstallieren**, danach HD60 und/oder Wave Link Linux wählen.

Beide Programme sind für **Nobara/Fedora (Linux)**.

## Lokal bauen

```bash
./packaging/linux/build-installer.sh dist
```

## Release

```bash
git tag v1.1.0
git push origin v1.1.0
```

Oder Actions → **Release Linux installer** → Run workflow.

Workflow: `.github/workflows/release.yml` — baut den Linux-Installer und hängt ihn an das GitHub Release.
