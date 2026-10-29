"""Installation von Spurwerk und der StreamController-Erweiterung."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = Path.home() / ".local/share/wavelink-linux"
BIN = Path.home() / ".local/bin/wavelink-linux"
DESKTOP_DIR = Path.home() / ".local/share/applications"
SC_ROOT = Path.home() / ".var/app/com.core447.StreamController"
SC_PLUGINS = SC_ROOT / "data/plugins"


class InstallError(Exception):
    pass


def streamcontroller_present() -> bool:
    return SC_ROOT.is_dir()


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        shown = " ".join(cmd)
        raise InstallError(detail or f"Befehl fehlgeschlagen: {shown}")


def _rsync(src: Path, dst: Path) -> None:
    if not src.is_dir():
        raise InstallError(f"Quelle fehlt: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "rsync",
            "-a",
            "--delete",
            "--exclude",
            ".git",
            "--exclude",
            "__pycache__",
            "--exclude",
            "*.pyc",
            f"{src}/",
            f"{dst}/",
        ]
    )


def _ensure_pulsectl(log) -> None:
    probe = subprocess.run(
        [sys.executable, "-c", "import pulsectl"],
        capture_output=True,
    )
    if probe.returncode == 0:
        return
    log("Installiere pulsectl…")
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "-r",
            str(ROOT / "requirements.txt"),
        ]
    )


def _write_launcher() -> None:
    BIN.parent.mkdir(parents=True, exist_ok=True)
    BIN.write_text(
        "#!/usr/bin/env bash\n"
        'export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"\n'
        'export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"\n'
        f'cd "{APP_DIR}"\n'
        'exec python3 -m wavelink_linux "$@"\n',
        encoding="utf-8",
    )
    BIN.chmod(0o755)
    run_sh = APP_DIR / "run.sh"
    if run_sh.is_file():
        run_sh.chmod(0o755)


def _write_desktop() -> None:
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    (DESKTOP_DIR / "com.wavelink.linux.desktop").write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Name=WaveLink Linux",
                "Comment=Audio-Mixer für PipeWire",
                f"Exec={BIN}",
                "Icon=audio-speakers-symbolic",
                "Terminal=false",
                "Type=Application",
                "Categories=AudioVideo;Audio;",
                "StartupNotify=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["update-desktop-database", str(DESKTOP_DIR)],
        check=False,
        capture_output=True,
    )


def _install_pipewire(log) -> None:
    from wavelink_linux.pipewire_setup import SOURCE, ensure_pipewire

    if not SOURCE.is_file():
        raise InstallError(f"PipeWire-Konfiguration fehlt: {SOURCE}")
    try:
        applied = ensure_pipewire(log)
    except OSError as exc:
        raise InstallError(str(exc)) from exc
    if not applied:
        log("PipeWire-Setup ist schon vorhanden.")


def install_plugins(log) -> None:
    if not streamcontroller_present():
        raise InstallError(
            "StreamController ist nicht installiert. "
            "Zuerst das Flatpak com.core447.StreamController einrichten."
        )
    log("Installiere die Drehregler…")
    _rsync(
        ROOT / "streamcontroller_plugin" / "com_wavelink_linux",
        SC_PLUGINS / "com_wavelink_linux",
    )
    log("Installiere das Spotify-Plugin…")
    _rsync(ROOT / "Spotify", SC_PLUGINS / "Spotify")
    log("Erweiterung liegt in StreamController.")


def install_app(include_plugin: bool, log) -> None:
    log("Lege den Programmordner an…")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_pulsectl(log)
    if ROOT.resolve() != APP_DIR.resolve():
        log("Kopiere die Programmdateien…")
        _rsync(ROOT, APP_DIR)
    else:
        log("Die Dateien liegen schon im Programmordner.")
    log("Lege den Starter an…")
    _write_launcher()
    _write_desktop()
    _install_pipewire(log)
    if include_plugin:
        install_plugins(log)
    log("Installation ist fertig.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spurwerk installieren")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-plugin",
        action="store_true",
        help="Nur den Mixer installieren",
    )
    group.add_argument(
        "--plugin-only",
        action="store_true",
        help="Nur die StreamController-Erweiterung installieren",
    )
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        print(message, flush=True)

    try:
        if args.plugin_only:
            install_plugins(log)
            print("StreamController danach neu starten.")
        elif args.no_plugin:
            install_app(False, log)
            print("Start: wavelink-linux  oder im Menü WaveLink Linux")
        else:
            install_app(streamcontroller_present(), log)
            if streamcontroller_present():
                print("StreamController danach neu starten.")
            else:
                print("StreamController nicht gefunden — Erweiterung übersprungen.")
            print("Start: wavelink-linux  oder im Menü WaveLink Linux")
    except InstallError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
