"""Plugin-Version. Maßgeblich ist die Datei VERSION neben diesem Modul."""

from __future__ import annotations

from pathlib import Path


def read_plugin_version() -> str:
    path = Path(__file__).resolve().parent / "VERSION"
    version = path.read_text(encoding="utf-8").strip()
    if not version:
        raise RuntimeError(f"Leere Plugin-Version: {path}")
    return version
