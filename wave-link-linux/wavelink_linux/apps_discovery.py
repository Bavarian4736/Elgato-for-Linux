from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SKIP_NAMES = {
    "gnome-shell",
    "xwayland",
    "Xwayland",
    "pipewire",
    "wireplumber",
    "pulseaudio",
    "gsd-media-keys",
    "gsd-power",
    "xdg-desktop-portal",
    "xdg-document-portal",
    "xdg-permission-store",
    "ibus-daemon",
    "ibus-x11",
    "evolution-alarm",
    "wavelink-linux",
    "python3",
    "python3.14",
    "pw-loopback",
    "pw-dump",
    "pw-cli",
    "bash",
    "zsh",
    "sh",
    "systemd",
    "dbus-daemon",
    "cursor-sandbox",
}

SKIP_DESKTOP_IDS = {
    "org.gnome.Shell",
    "org.gnome.SettingsDaemon",
}


@dataclass
class RunningApp:
    key: str
    label: str
    icon_name: str
    binary: str
    pid: str
    desktop_id: str = ""


def _desktop_dirs() -> list[Path]:
    dirs = [
        Path.home() / ".local/share/applications",
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
    ]
    xdg = os.environ.get("XDG_DATA_DIRS", "")
    for part in xdg.split(":"):
        if part:
            dirs.append(Path(part) / "applications")
    # unique preserve order
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d)
        if key in seen:
            continue
        seen.add(key)
        if d.is_dir():
            out.append(d)
    return out


def _parse_desktop(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if "NoDisplay=true" in text or "Hidden=true" in text:
        return None
    if "[Desktop Entry]" not in text:
        return None
    data: dict[str, str] = {}
    in_entry = False
    for line in text.splitlines():
        if line.strip() == "[Desktop Entry]":
            in_entry = True
            continue
        if line.startswith("[") and in_entry:
            break
        if not in_entry or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if (
            k in ("Name", "Icon", "Exec", "StartupWMClass", "TryExec", "X-Flatpak", "Type")
            and k not in data
        ):
            data[k] = v
    if "Name" not in data or "Exec" not in data:
        return None
    if data.get("Type", "Application") != "Application":
        return None
    exec_bin = data["Exec"].split()[0]
    parts = data["Exec"].replace("\\\\", " ").split()
    parts = [p for p in parts if not p.startswith("%") and p not in ("@@", "@@u", "@@i")]

    flatpak_id = data.get("X-Flatpak", "")
    if not flatpak_id and parts and Path(parts[0]).name == "flatpak" and "run" in parts:
        # Prefer reverse scan for reverse-DNS app id (com.spotify.Client)
        for token in reversed(parts):
            if token.startswith("-") or token in ("run", "flatpak"):
                continue
            if "." in token and not token.startswith("."):
                flatpak_id = token
                break

    if flatpak_id:
        data["flatpak_id"] = flatpak_id
        data["bin"] = flatpak_id
    else:
        data["bin"] = Path(exec_bin).name
    data["desktop_id"] = path.stem
    data["path"] = str(path)
    return data


def _running_processes() -> list[tuple[str, str, str]]:
    """Return list of (pid, comm, cmdline)."""
    rows: list[tuple[str, str, str]] = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            comm = (p / "comm").read_text(encoding="utf-8", errors="ignore").strip()
            cmdline = (
                (p / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="ignore")
                .strip()
            )
        except OSError:
            continue
        rows.append((p.name, comm, cmdline))
    return rows


def list_running_apps() -> list[RunningApp]:
    desktops: list[dict] = []
    for d in _desktop_dirs():
        for f in d.glob("*.desktop"):
            parsed = _parse_desktop(f)
            if parsed:
                desktops.append(parsed)

    procs = _running_processes()
    found: dict[str, RunningApp] = {}

    for desk in desktops:
        name = desk["Name"]
        icon = desk.get("Icon") or desk["bin"]
        desktop_id = desk["desktop_id"]
        if desktop_id in SKIP_DESKTOP_IDS:
            continue
        flatpak_id = desk.get("flatpak_id", "")
        bin_name = desk["bin"]
        wm = desk.get("StartupWMClass", "")

        matched_pid = ""
        matched_comm = ""
        for pid, comm, cmdline in procs:
            if comm in SKIP_NAMES:
                continue
            hit = False
            if flatpak_id and flatpak_id in cmdline:
                hit = True
            elif bin_name and (comm == bin_name or bin_name in cmdline.split()):
                hit = True
            elif wm and wm.lower() == comm.lower():
                hit = True
            elif desktop_id and desktop_id in cmdline:
                hit = True
            if hit:
                matched_pid = pid
                matched_comm = comm
                break

        if not matched_pid:
            continue

        # Prefer flatpak id / desktop id as stable key
        key_base = flatpak_id or desktop_id or bin_name or matched_comm
        key = key_base
        if key in found:
            continue
        if matched_comm in SKIP_NAMES and not flatpak_id:
            continue

        found[key] = RunningApp(
            key=key,
            label=name,
            icon_name=icon,
            binary=flatpak_id or bin_name or matched_comm,
            pid=matched_pid,
            desktop_id=desktop_id,
        )

    # Also add PipeWire / notable audio clients not covered by desktop match
    # (handled by caller via pulse clients)

    return sorted(found.values(), key=lambda a: a.label.lower())
