"""Laufzeit-Version des HD60-Programms. Der Treiber bleibt eine eigene Angabe."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path


def component_dir() -> Path:
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _versions():
    here = component_dir()
    candidates = (
        here / "_elgato_versions.py",
        here.parent / "packaging" / "common" / "versions.py",
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("elgato_versions", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    raise FileNotFoundError("versions.py fehlt neben HD60 oder im Monorepo.")


def about_fields() -> dict[str, str]:
    info = _versions().load_identity(component_dir(), with_driver=True)
    comments = _versions().format_about(
        info,
        intro="Bild und Ton der Elgato Game Capture HD60 S, ohne OBS.",
        driver=True,
    )
    return {"version": info["component_version"], "comments": comments, **info}
