#!/usr/bin/env python3
"""Suite-, Komponenten- und Build-Versionen für Elgato for Linux.

Drei getrennte Angaben, die nicht ineinander geschrieben werden:

- Suite: Datei ``VERSION`` im Repo-Root. Das ist das Elgato-for-Linux-Release.
- Komponente: eigene ``VERSION`` je Programm oder Plugin. Wird nicht auf den
  Suite-Tag gesetzt.
- Installierter Build: ``build-info.json``, das Paketieren und Installieren
  neben die Programmdateien schreiben. Enthält Suite-Stand und Git-Revision
  dieses Builds. Die Komponente liest ihre Versionsnummer weiter aus ``VERSION``.

Der HD60-S-Treiber bleibt ``hd60s/<DRIVER_VERSION>`` aus dem Upstream-DKMS-Paket.
Diese Datei wird nicht aus der Programm- oder Suite-Version abgeleitet.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$"
)
DRIVER_VER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:[-+][0-9A-Za-z.-]+)?$"
)

COMPONENTS = {
    "wavelink": "wave-link-linux/VERSION",
    "hd60": "capture-card/VERSION",
    "streamcontroller": (
        "wave-link-linux/streamcontroller_plugin/com_wavelink_linux/VERSION"
    ),
    "spotify": "wave-link-linux/Spotify/VERSION",
    "bar": (
        "wave-link-linux/streamcontroller_plugin/"
        "sd_plus_bar_wallpapers/com_wavelink_linux_bar/VERSION"
    ),
}
MANIFESTS = {
    "streamcontroller": (
        "wave-link-linux/streamcontroller_plugin/com_wavelink_linux/manifest.json"
    ),
    "spotify": "wave-link-linux/Spotify/manifest.json",
    "bar": (
        "wave-link-linux/streamcontroller_plugin/"
        "sd_plus_bar_wallpapers/com_wavelink_linux_bar/manifest.json"
    ),
}
PLUGIN_MAINS = (
    "wave-link-linux/streamcontroller_plugin/com_wavelink_linux/main.py",
    "wave-link-linux/Spotify/main.py",
)
ABOUT_SOURCES = (
    "capture-card/hd60s.py",
    "wave-link-linux/wavelink_linux/app.py",
)


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def read_version_file(path: Path, *, driver: bool = False) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Versionsdatei fehlt: {path}")
    text = path.read_text(encoding="utf-8").strip()
    pattern = DRIVER_VER if driver else SEMVER
    if not text or pattern.fullmatch(text) is None:
        raise ValueError(f"Ungültige Version in {path}: {text!r}")
    return text


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def is_monorepo(root: Path) -> bool:
    return (
        (root / "capture-card").is_dir()
        and (root / "wave-link-linux").is_dir()
        and (root / "VERSION").is_file()
    )


def declared_suite_version(component_dir: Path) -> str | None:
    root = component_dir.parent
    if not is_monorepo(root):
        return None
    return read_version_file(root / "VERSION")


def _git_head(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return out or None


def git_revision(start: Path) -> str | None:
    """Revision nur aus dem Elgato-for-Linux-Checkout, nicht aus einem fremden Git darüber."""
    current = start.resolve()
    for _ in range(8):
        if (current / ".git").exists():
            if is_monorepo(current):
                return _git_head(current)
            return None
        if current.parent == current:
            break
        current = current.parent
    return None


def load_identity(component_dir: Path, *, with_driver: bool = False) -> dict[str, str]:
    """Identität der laufenden Komponente.

    ``component_version`` kommt immer aus der ``VERSION``-Datei neben dem
    Programm. Ein Stempel kann diese Angabe nicht überschreiben.
    """
    component_dir = Path(component_dir).resolve()
    component_version = read_version_file(component_dir / "VERSION")
    info = read_json(component_dir / "build-info.json") or {}
    declared = declared_suite_version(component_dir)
    live = git_revision(component_dir)
    if declared:
        suite = declared
    else:
        suite = str(info.get("suite_version") or "unbekannt")
    if live:
        revision = live
        installed = suite
    else:
        revision = str(info.get("revision") or "unbekannt")
        installed = str(info.get("suite_version") or suite)
    result = {
        "component_version": component_version,
        "suite_version": suite,
        "installed_build": installed,
        "revision": revision,
    }
    if with_driver:
        result["driver_version"] = read_version_file(
            component_dir / "DRIVER_VERSION", driver=True
        )
    return result


def format_about(identity: dict[str, str], *, intro: str, driver: bool = False) -> str:
    lines = [intro, "", f"Komponente {identity['component_version']}"]
    if driver:
        lines.append(f"Treiber hd60s/{identity['driver_version']} (unabhängig)")
    lines.append(f"Elgato for Linux {identity['suite_version']}")
    if identity["installed_build"] != identity["suite_version"]:
        lines.append(f"Installierter Build {identity['installed_build']}")
    lines.append(f"Stand {identity['revision']}")
    return "\n".join(lines)


def suite_matches_declared(suite: str, declared: str) -> bool:
    if suite.startswith("0.0.0-ci."):
        return SEMVER.fullmatch(suite) is not None
    return suite == declared


def _previous_stamp(root: Path, dest: Path, component: str) -> dict:
    names = {
        "wavelink": "wave-link-linux/build-info.json",
        "hd60": "capture-card/build-info.json",
    }
    for path in (dest / "build-info.json", root / names[component]):
        info = read_json(path)
        if info:
            return info
    return {}


def resolve_stamp(root: Path, dest: Path, component: str, suite: str | None) -> dict:
    root = root.resolve()
    declared = read_version_file(root / "VERSION")
    previous = _previous_stamp(root, dest, component)
    if suite:
        if not suite_matches_declared(suite, declared):
            raise ValueError(
                f"Suite {suite} stimmt nicht mit VERSION ({declared}) überein."
            )
        chosen = suite
    elif git_revision(root):
        chosen = declared
    else:
        chosen = str(previous.get("suite_version") or declared)
    if git_revision(root):
        revision = git_revision(root) or "unbekannt"
    else:
        revision = str(previous.get("revision") or "unbekannt")
    version_path = root / COMPONENTS[component]
    payload = {
        "component": component,
        "component_version": read_version_file(version_path),
        "revision": revision,
        "suite_version": chosen,
    }
    if component == "hd60":
        payload["driver_version"] = read_version_file(
            root / "capture-card" / "DRIVER_VERSION", driver=True
        )
    return payload


def stamp(root: Path, dest: Path, component: str, suite: str | None = None) -> Path:
    if component not in ("wavelink", "hd60"):
        raise ValueError(f"Unbekannte Komponente: {component}")
    dest.mkdir(parents=True, exist_ok=True)
    payload = resolve_stamp(root, dest, component, suite)
    target = dest / "build-info.json"
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def _manifest_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str):
        raise ValueError(f"{path} hat kein version-Feld")
    return version.strip()


def check(root: Path, suite: str | None = None) -> list[str]:
    root = root.resolve()
    problems: list[str] = []
    try:
        declared = read_version_file(root / "VERSION")
    except (OSError, ValueError) as exc:
        return [str(exc)]

    versions: dict[str, str] = {}
    for name, relative in COMPONENTS.items():
        path = root / relative
        try:
            versions[name] = read_version_file(path)
        except (OSError, ValueError) as exc:
            problems.append(str(exc))
    try:
        driver = read_version_file(root / "capture-card" / "DRIVER_VERSION", driver=True)
    except (OSError, ValueError) as exc:
        problems.append(str(exc))
        driver = ""

    for name, relative in MANIFESTS.items():
        path = root / relative
        try:
            found = _manifest_version(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            problems.append(str(exc))
            continue
        expected = versions.get(name)
        if expected and found != expected:
            problems.append(
                f"{relative} meldet {found}, VERSION sagt {expected}."
            )

    for relative in PLUGIN_MAINS:
        text = (root / relative).read_text(encoding="utf-8")
        if "read_plugin_version()" not in text:
            problems.append(f"{relative} liest die VERSION-Datei nicht.")
        if re.search(r"plugin_version\s*=\s*[\"']", text):
            problems.append(f"{relative} hat eine fest eingetragene plugin_version.")

    init_text = (root / "wave-link-linux/wavelink_linux/__init__.py").read_text(
        encoding="utf-8"
    )
    if re.search(r"__version__\s*=\s*[\"']", init_text):
        problems.append("wavelink_linux/__init__.py setzt __version__ als Literal.")
    if "component_version" not in init_text:
        problems.append("wavelink_linux/__init__.py liest die Komponentenversion nicht.")

    for relative in ABOUT_SOURCES:
        text = (root / relative).read_text(encoding="utf-8")
        if 'set_version(about["version"])' not in text:
            problems.append(f"{relative} zeigt die Version nicht aus den Versionsdaten.")
        if re.search(r"set_version\(\s*[\"']", text):
            problems.append(f"{relative} hat eine fest eingetragene Dialog-Version.")

    spec_path = root / "capture-card/packaging/hd60s.spec"
    spec = spec_path.read_text(encoding="utf-8")
    spec_version = re.search(r"^Version:\s*(\S+)", spec, re.M)
    if spec_version is None or spec_version.group(1) != versions.get("hd60"):
        problems.append("hd60s.spec Version weicht von capture-card/VERSION ab.")
    if driver:
        for needle in (f"hd60s-{driver}", f"-v {driver}"):
            if needle not in spec:
                problems.append(f"hd60s.spec enthält {needle} nicht.")
        userspace = versions.get("hd60", "")
        if userspace and userspace != driver:
            if f"hd60s-{userspace}" in spec or f"-v {userspace}" in spec:
                problems.append(
                    "hd60s.spec verwendet die Programmversion als Treiberversion."
                )
    for needle in (
        "version_info.py",
        "DRIVER_VERSION",
        "_elgato_versions.py",
        "build-info.json",
    ):
        if needle not in spec:
            problems.append(f"hd60s.spec paketiert {needle} nicht.")

    install_text = (root / "capture-card/install.sh").read_text(encoding="utf-8")
    if driver and f'local ver="{driver}"' not in install_text:
        problems.append("capture-card/install.sh fällt nicht auf DRIVER_VERSION zurück.")
    if "install_program_files" not in install_text or "--userspace" not in install_text:
        problems.append("capture-card/install.sh kann das Programm nicht getrennt aktualisieren.")

    build_rpm = (root / "capture-card/packaging/build-rpm.sh").read_text(encoding="utf-8")
    if "version_info.py" not in build_rpm or "stamp" not in build_rpm:
        problems.append("build-rpm.sh übernimmt die Versionsdateien nicht.")

    build_installer = (root / "packaging/linux/build-installer.sh").read_text(
        encoding="utf-8"
    )
    if "versions.py" not in build_installer or "stamp" not in build_installer:
        problems.append("build-installer.sh schreibt keinen Build-Stempel.")

    if suite and not suite_matches_declared(suite, declared):
        problems.append(
            f"Release-Suite {suite} stimmt nicht mit VERSION ({declared}) überein."
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    check_parser = sub.add_parser("check", help="Versionsdateien gegeneinander prüfen")
    check_parser.add_argument("--root", type=Path, default=None)
    check_parser.add_argument("--suite", default=None)

    stamp_parser = sub.add_parser("stamp", help="build-info.json schreiben")
    stamp_parser.add_argument("--root", type=Path, required=True)
    stamp_parser.add_argument("--dest", type=Path, required=True)
    stamp_parser.add_argument("--component", required=True, choices=("wavelink", "hd60"))
    stamp_parser.add_argument("--suite", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "check":
        root = (args.root or repo_root_from_here()).resolve()
        problems = check(root, suite=args.suite)
        if problems:
            for item in problems:
                print(item, file=sys.stderr)
            return 1
        print(f"Versionen sind konsistent (Suite {read_version_file(root / 'VERSION')}).")
        return 0

    try:
        target = stamp(args.root, args.dest, args.component, args.suite)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
