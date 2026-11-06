"""Laufzeit-Version von Wave Link Linux. Kein fest eingetragenes 1.0.0."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _versions():
    here = Path(__file__).resolve().parent
    candidates = (
        here / "_elgato_versions.py",
        here.parents[1] / "packaging" / "common" / "versions.py",
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
    raise FileNotFoundError("versions.py fehlt neben Wave Link oder im Monorepo.")


def component_version() -> str:
    return _versions().read_version_file(package_root() / "VERSION")


@lru_cache(maxsize=1)
def identity() -> dict[str, str]:
    return _versions().load_identity(package_root(), with_driver=False)


def about_fields() -> dict[str, str]:
    info = identity()
    comments = _versions().format_about(
        info,
        intro="PipeWire-Mixer mit Monitor- und Stream-Mix.",
    )
    return {"version": info["component_version"], "comments": comments, **info}


def public_versions() -> dict[str, str]:
    info = identity()
    return {
        "component_version": info["component_version"],
        "suite_version": info["suite_version"],
        "installed_build": info["installed_build"],
        "revision": info["revision"],
    }
