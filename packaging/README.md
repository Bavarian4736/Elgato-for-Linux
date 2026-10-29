# Packaging — Studio Linux-Installer

Baut **`Studio-Linux-Installer.sh`** für GitHub Releases. Beim Start HD60 und/oder Wave Link Linux wählen.

Beide Programme sind für **Nobara/Fedora (Linux)**.

## Lokal bauen

```bash
./packaging/linux/build-installer.sh dist
```

## Release

```bash
git tag v1.0.0
git push origin v1.0.0
```

Oder Actions → **Release Linux installer** → Run workflow.

Workflow: `.github/workflows/release.yml` — baut den Linux-Installer und hängt ihn an das GitHub Release.
