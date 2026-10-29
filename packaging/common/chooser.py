#!/usr/bin/env python3
"""Studio-Installer: HD60 und/oder Wave Link Linux auswählen und einrichten."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

PROGRAMS = {
    "hd60": {
        "name": "HD60",
        "blurb": "Vorschau und Treiber für die Elgato Game Capture HD60 S (Nobara/Fedora).",
    },
    "wavelink": {
        "name": "Wave Link Linux (Spurwerk)",
        "blurb": "PipeWire-Mixer mit Monitor- und Stream-Mix (Nobara/Fedora/GNOME).",
    },
}

LINUX_NOTE = (
    "Beide Programme sind für Nobara/Fedora (Linux) gebaut. "
    "HD60 braucht den Kernel-Treiber; Wave Link braucht PipeWire."
)
NONLINUX_NOTE = (
    "Dieses Studio-Paket läuft vollständig nur unter Linux (Nobara/Fedora). "
    "Auf diesem System werden die gewählten Programme als Dateipaket "
    "in den Zielordner kopiert — zum Übertragen auf einen Linux-Rechner "
    "oder zur Nutzung in einer Linux-VM / unter WSL2 (soweit möglich)."
)


def studio_root() -> Path:
    """Repo- oder Payload-Wurzel: packaging/common/chooser.py → zwei Ebenen hoch."""
    here = Path(__file__).resolve()
    # In Release-Payloads: <payload>/packaging/common/chooser.py
    # Im Checkout: dasselbe Layout
    root = here.parents[2]
    if (root / "capture-card").is_dir() and (root / "wave-link-linux").is_dir():
        return root
    # Fallback: neben dem Skript gebündeltes payload/
    alt = here.parent / "payload"
    if (alt / "capture-card").is_dir():
        return alt
    return root


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def detect_os_label() -> str:
    system = platform.system()
    if system == "Linux":
        return "Linux"
    if system == "Darwin":
        return "macOS"
    if system == "Windows":
        return "Windows"
    return system or "unbekannt"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Studio-Installer: HD60 und/oder Wave Link Linux wählen.",
    )
    p.add_argument(
        "--hd60",
        action="store_true",
        help="HD60 installieren",
    )
    p.add_argument(
        "--wavelink",
        action="store_true",
        help="Wave Link Linux installieren",
    )
    p.add_argument(
        "--both",
        action="store_true",
        help="Beide Programme installieren",
    )
    p.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Zielordner für Dateipaket (nicht-Linux bzw. --bundle-only)",
    )
    p.add_argument(
        "--bundle-only",
        action="store_true",
        help="Nur Dateien kopieren, Installer der Programme nicht ausführen",
    )
    p.add_argument(
        "--noninteractive",
        action="store_true",
        help="Keine Rückfragen (Auswahl muss per Flags kommen)",
    )
    return p.parse_args(argv)


def choose_interactive() -> set[str]:
    """CLI-Menü; optional tkinter, falls vorhanden."""
    try:
        return _choose_tk()
    except Exception:
        return _choose_cli()


def _choose_cli() -> set[str]:
    print()
    print("Studio — was soll eingerichtet werden?")
    print(f"  System: {detect_os_label()}")
    print()
    print("  1) Nur HD60")
    print("  2) Nur Wave Link Linux (Spurwerk)")
    print("  3) Beides")
    print("  0) Abbrechen")
    print()
    while True:
        choice = input("Auswahl [1/2/3/0]: ").strip()
        if choice == "1":
            return {"hd60"}
        if choice == "2":
            return {"wavelink"}
        if choice == "3":
            return {"hd60", "wavelink"}
        if choice == "0":
            print("Abgebrochen.")
            sys.exit(0)
        print("Bitte 1, 2, 3 oder 0 eingeben.")


def _choose_tk() -> set[str]:
    import tkinter as tk
    from tkinter import messagebox, ttk

    selected: set[str] = set()
    result: dict[str, set[str] | None] = {"value": None}

    root = tk.Tk()
    root.title("Studio Installer")
    root.minsize(420, 280)
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")

    ttk.Label(frame, text="Studio", font=("", 16, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        frame,
        text=f"System: {detect_os_label()}\nWähle die Programme zum Einrichten:",
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(8, 12))

    vars_map = {
        "hd60": tk.BooleanVar(value=True),
        "wavelink": tk.BooleanVar(value=True),
    }
    row = 2
    for key, meta in PROGRAMS.items():
        ttk.Checkbutton(
            frame,
            text=f"{meta['name']} — {meta['blurb']}",
            variable=vars_map[key],
            wraplength=380,
        ).grid(row=row, column=0, sticky="w", pady=4)
        row += 1

    note = LINUX_NOTE if is_linux() else NONLINUX_NOTE
    ttk.Label(frame, text=note, wraplength=380, justify="left").grid(
        row=row, column=0, sticky="w", pady=(12, 8)
    )
    row += 1

    def on_ok() -> None:
        chosen = {k for k, v in vars_map.items() if v.get()}
        if not chosen:
            messagebox.showwarning(
                "Studio",
                "Bitte mindestens ein Programm auswählen.",
            )
            return
        result["value"] = chosen
        root.destroy()

    def on_cancel() -> None:
        result["value"] = set()
        root.destroy()

    btns = ttk.Frame(frame)
    btns.grid(row=row, column=0, sticky="e", pady=(8, 0))
    ttk.Button(btns, text="Abbrechen", command=on_cancel).grid(row=0, column=0, padx=4)
    ttk.Button(btns, text="Installieren", command=on_ok).grid(row=0, column=1, padx=4)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    value = result["value"]
    if value is None or len(value) == 0:
        print("Abgebrochen.")
        sys.exit(0)
    selected |= value
    return selected


def resolve_selection(args: argparse.Namespace) -> set[str]:
    chosen: set[str] = set()
    if args.both:
        chosen = {"hd60", "wavelink"}
    if args.hd60:
        chosen.add("hd60")
    if args.wavelink:
        chosen.add("wavelink")
    if chosen:
        return chosen
    if args.noninteractive:
        print(
            "Fehler: --noninteractive braucht --hd60, --wavelink und/oder --both.",
            file=sys.stderr,
        )
        sys.exit(2)
    return choose_interactive()


def default_bundle_dest() -> Path:
    home = Path.home()
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", str(home)))
        return base / "Studio"
    if is_macos():
        return home / "Applications" / "Studio"
    return home / "Studio"


def copy_bundle(root: Path, dest: Path, programs: set[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    # Immer README und Meta mitnehmen
    for name in ("README.md", ".gitignore"):
        src = root / name
        if src.is_file():
            shutil.copy2(src, dest / name)

    mapping = {
        "hd60": [
            ("capture-card", "capture-card"),
            ("hd60s", "hd60s"),
        ],
        "wavelink": [
            ("wave-link-linux", "wave-link-linux"),
            ("wavelink-linux", "wavelink-linux"),
        ],
    }
    # Gemeinsamer Meta-Installer
    for name in ("install.sh",):
        src = root / name
        if src.is_file():
            shutil.copy2(src, dest / name)
            if not is_windows():
                (dest / name).chmod(0o755)

    for key in programs:
        for rel_src, rel_dst in mapping[key]:
            src = root / rel_src
            dst = dest / rel_dst
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(
                    src,
                    dst,
                    ignore=shutil.ignore_patterns(
                        ".git", "__pycache__", "*.pyc", ".venv", "venv"
                    ),
                )
            elif src.is_file():
                shutil.copy2(src, dst)
                if not is_windows():
                    dst.chmod(0o755)

    readme = dest / "INSTALL-HINWEIS.txt"
    lines = [
        "Studio — lokal entpacktes Paket",
        "================================",
        "",
        LINUX_NOTE if is_linux() else NONLINUX_NOTE,
        "",
        "Gewählt:",
    ]
    for key in sorted(programs):
        lines.append(f"  - {PROGRAMS[key]['name']}")
    lines.extend(
        [
            "",
            "Unter Linux (Nobara/Fedora) im entpackten Ordner:",
            "  ./install.sh",
            "oder einzeln:",
            "  ./capture-card/install.sh",
            "  ./wave-link-linux/install.sh",
            "",
            f"Quelle: {root}",
        ]
    )
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Dateien nach {dest} kopiert.")


def run_linux_install(root: Path, programs: set[str]) -> int:
    status = 0
    if "hd60" in programs:
        script = root / "capture-card" / "install.sh"
        print("\n==> HD60")
        if not script.is_file():
            print(f"Fehler: {script} fehlt.", file=sys.stderr)
            status = 1
        else:
            r = subprocess.run(["bash", str(script)], check=False)
            if r.returncode != 0:
                status = r.returncode or 1
    if "wavelink" in programs:
        script = root / "wave-link-linux" / "install.sh"
        print("\n==> Wave Link Linux")
        if not script.is_file():
            print(f"Fehler: {script} fehlt.", file=sys.stderr)
            status = 1
        else:
            r = subprocess.run(["bash", str(script)], check=False)
            if r.returncode != 0:
                status = r.returncode or 1
    return status


def print_summary(programs: set[str], mode: str, dest: Path | None) -> None:
    print()
    print("Fertig.")
    print(f"  Modus: {mode}")
    for key in sorted(programs):
        print(f"  • {PROGRAMS[key]['name']}")
    if dest is not None:
        print(f"  Ziel: {dest}")
    if is_linux() and mode == "install":
        if "hd60" in programs:
            print("  Start HD60:        hd60s")
        if "wavelink" in programs:
            print("  Start Wave Link:   wavelink-linux")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = studio_root()
    programs = resolve_selection(args)

    print(textwrap.fill(LINUX_NOTE if is_linux() else NONLINUX_NOTE, width=78))
    print()
    print("Auswahl:")
    for key in sorted(programs):
        print(f"  • {PROGRAMS[key]['name']}")

    bundle_only = bool(args.bundle_only) or not is_linux()
    dest = args.dest or (default_bundle_dest() if bundle_only else None)

    if bundle_only:
        assert dest is not None
        copy_bundle(root, dest, programs)
        print_summary(programs, "bundle", dest)
        if not is_linux():
            print()
            print(
                "Hinweis: Zum vollständigen Installieren das Paket auf "
                "Nobara/Fedora bringen und dort ./install.sh ausführen — "
                "oder den Linux-Installer von GitHub Releases nutzen."
            )
        return 0

    status = run_linux_install(root, programs)
    print_summary(programs, "install", None)
    return status


if __name__ == "__main__":
    sys.exit(main())
