"""PipeWire-Spuren anlegen, wenn die Konfiguration noch fehlt."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "pipewire" / "99-wavelink.conf"
TARGET_DIR = Path.home() / ".config" / "pipewire" / "pipewire.conf.d"
TARGET = TARGET_DIR / "99-wavelink.conf"
OLD = TARGET_DIR / "10-virtual-sinks.conf"


def pipewire_missing() -> bool:
    if not SOURCE.is_file() or not TARGET.is_file():
        return True
    return TARGET.read_text(encoding="utf-8") != SOURCE.read_text(encoding="utf-8")


def ensure_pipewire(log=None) -> bool:
    """Write 99-wavelink.conf and restart PipeWire when the setup is missing.

    Returns True when something was applied.
    """
    if not SOURCE.is_file():
        raise FileNotFoundError(f"PipeWire-Konfiguration fehlt: {SOURCE}")

    stale = OLD.is_file()
    outdated = pipewire_missing()
    if not outdated and not stale:
        return False

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    if outdated:
        TARGET.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        if log:
            log("PipeWire-Konfiguration geschrieben")
    if stale:
        OLD.replace(TARGET_DIR / "10-virtual-sinks.conf.disabled-by-wavelink")
        if log:
            log("Alte 10-virtual-sinks.conf deaktiviert")
    if log:
        log("PipeWire wird neu gestartet…")
    subprocess.run(
        [
            "systemctl",
            "--user",
            "restart",
            "wireplumber",
            "pipewire",
            "pipewire-pulse",
        ],
        check=False,
        capture_output=True,
    )
    return True
