#!/usr/bin/env python3
"""Elgato for Linux — Installer: HD60 und/oder Wave Link Linux installieren oder entfernen."""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

PRODUCT = "Elgato for Linux"

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


@dataclass
class Selection:
    action: str  # "install" | "uninstall"
    programs: set[str]


def project_root() -> Path:
    """Repo- oder Payload-Wurzel: packaging/common/chooser.py → zwei Ebenen hoch."""
    here = Path(__file__).resolve()
    root = here.parents[2]
    if (root / "capture-card").is_dir() and (root / "wave-link-linux").is_dir():
        return root
    alt = here.parent / "payload"
    if (alt / "capture-card").is_dir():
        return alt
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=f"{PRODUCT}: HD60 und/oder Wave Link Linux installieren oder deinstallieren.",
    )
    p.add_argument("--hd60", action="store_true", help="HD60 einbeziehen")
    p.add_argument("--wavelink", action="store_true", help="Wave Link Linux einbeziehen")
    p.add_argument("--both", action="store_true", help="Beide Programme einbeziehen")
    p.add_argument(
        "--uninstall",
        action="store_true",
        help="Gewählte Programme deinstallieren statt installieren",
    )
    p.add_argument(
        "--install",
        action="store_true",
        help="Explizit installieren (Standard ohne --uninstall)",
    )
    p.add_argument(
        "--noninteractive",
        action="store_true",
        help="Keine Rückfragen (Auswahl muss per Flags kommen)",
    )
    return p.parse_args(argv)


def choose_interactive() -> Selection:
    try:
        return _choose_tk()
    except Exception:
        return _choose_cli()


def _choose_cli() -> Selection:
    print()
    print(f"{PRODUCT} — Installation oder Deinstallation?")
    print("  System: Linux (Nobara/Fedora)")
    print()
    print("  I) Installieren")
    print("  D) Deinstallieren")
    print("  0) Abbrechen")
    print()
    while True:
        mode = input("Auswahl [I/D/0]: ").strip().lower()
        if mode in ("0", "q", "a"):
            print("Abgebrochen.")
            sys.exit(0)
        if mode in ("i", "install", "1"):
            action = "install"
            break
        if mode in ("d", "u", "uninstall", "deinstall", "2"):
            action = "uninstall"
            break
        print("Bitte I, D oder 0 eingeben.")

    verb = "eingerichtet" if action == "install" else "entfernt"
    print()
    print(f"Welche Programme sollen {verb} werden?")
    print("  1) Nur HD60")
    print("  2) Nur Wave Link Linux (Spurwerk)")
    print("  3) Beides")
    print("  0) Abbrechen")
    print()
    while True:
        choice = input("Auswahl [1/2/3/0]: ").strip()
        if choice == "1":
            return Selection(action, {"hd60"})
        if choice == "2":
            return Selection(action, {"wavelink"})
        if choice == "3":
            return Selection(action, {"hd60", "wavelink"})
        if choice == "0":
            print("Abgebrochen.")
            sys.exit(0)
        print("Bitte 1, 2, 3 oder 0 eingeben.")


def _choose_tk() -> Selection:
    import tkinter as tk
    from tkinter import messagebox, ttk

    result: dict[str, Selection | None] = {"value": None}

    root = tk.Tk()
    root.title(f"{PRODUCT} Installer")
    root.minsize(440, 340)
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")

    ttk.Label(frame, text=PRODUCT, font=("", 16, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        frame,
        text="Linux (Nobara/Fedora)\nAktion und Programme wählen:",
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(8, 12))

    action_var = tk.StringVar(value="install")
    action_row = ttk.Frame(frame)
    action_row.grid(row=2, column=0, sticky="w", pady=(0, 8))
    ttk.Radiobutton(
        action_row, text="Installieren", variable=action_var, value="install"
    ).grid(row=0, column=0, padx=(0, 16))
    ttk.Radiobutton(
        action_row, text="Deinstallieren", variable=action_var, value="uninstall"
    ).grid(row=0, column=1)

    vars_map = {
        "hd60": tk.BooleanVar(value=True),
        "wavelink": tk.BooleanVar(value=True),
    }
    row = 3
    for key, meta in PROGRAMS.items():
        ttk.Checkbutton(
            frame,
            text=f"{meta['name']} — {meta['blurb']}",
            variable=vars_map[key],
            wraplength=400,
        ).grid(row=row, column=0, sticky="w", pady=4)
        row += 1

    ttk.Label(frame, text=LINUX_NOTE, wraplength=400, justify="left").grid(
        row=row, column=0, sticky="w", pady=(12, 8)
    )
    row += 1

    def on_ok() -> None:
        chosen = {k for k, v in vars_map.items() if v.get()}
        if not chosen:
            messagebox.showwarning(
                PRODUCT,
                "Bitte mindestens ein Programm auswählen.",
            )
            return
        result["value"] = Selection(action_var.get(), chosen)
        root.destroy()

    def on_cancel() -> None:
        result["value"] = None
        root.destroy()

    btns = ttk.Frame(frame)
    btns.grid(row=row, column=0, sticky="e", pady=(8, 0))
    ttk.Button(btns, text="Abbrechen", command=on_cancel).grid(row=0, column=0, padx=4)
    ttk.Button(btns, text="Weiter", command=on_ok).grid(row=0, column=1, padx=4)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    value = result["value"]
    if value is None:
        print("Abgebrochen.")
        sys.exit(0)
    return value


def resolve_selection(args: argparse.Namespace) -> Selection:
    chosen: set[str] = set()
    if args.both:
        chosen = {"hd60", "wavelink"}
    if args.hd60:
        chosen.add("hd60")
    if args.wavelink:
        chosen.add("wavelink")

    if args.uninstall and args.install:
        print("Fehler: --install und --uninstall gleichzeitig.", file=sys.stderr)
        sys.exit(2)

    if chosen:
        action = "uninstall" if args.uninstall else "install"
        return Selection(action, chosen)

    if args.noninteractive:
        print(
            "Fehler: --noninteractive braucht --hd60, --wavelink und/oder --both.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.uninstall or args.install:
        sel = choose_interactive()
        if args.uninstall:
            sel.action = "uninstall"
        elif args.install:
            sel.action = "install"
        return sel

    return choose_interactive()


def run_linux_install(root: Path, programs: set[str]) -> int:
    status = 0
    if "hd60" in programs:
        script = root / "capture-card" / "install.sh"
        print("\n==> HD60 installieren")
        if not script.is_file():
            print(f"Fehler: {script} fehlt.", file=sys.stderr)
            status = 1
        else:
            r = subprocess.run(["bash", str(script)], check=False)
            if r.returncode != 0:
                status = r.returncode or 1
    if "wavelink" in programs:
        script = root / "wave-link-linux" / "install.sh"
        print("\n==> Wave Link Linux installieren")
        if not script.is_file():
            print(f"Fehler: {script} fehlt.", file=sys.stderr)
            status = 1
        else:
            r = subprocess.run(["bash", str(script)], check=False)
            if r.returncode != 0:
                status = r.returncode or 1
    return status


def run_linux_uninstall(root: Path, programs: set[str]) -> int:
    status = 0
    if "hd60" in programs:
        script = root / "capture-card" / "install.sh"
        print("\n==> HD60 deinstallieren")
        if not script.is_file():
            print(f"Fehler: {script} fehlt.", file=sys.stderr)
            status = 1
        else:
            r = subprocess.run(["bash", str(script), "--uninstall"], check=False)
            if r.returncode != 0:
                status = r.returncode or 1
    if "wavelink" in programs:
        script = root / "wave-link-linux" / "install.sh"
        print("\n==> Wave Link Linux deinstallieren")
        if not script.is_file():
            print(f"Fehler: {script} fehlt.", file=sys.stderr)
            status = 1
        else:
            r = subprocess.run(["bash", str(script), "--uninstall"], check=False)
            if r.returncode != 0:
                status = r.returncode or 1
    return status


def print_summary(sel: Selection, status: int) -> None:
    print()
    if status != 0:
        print(f"Abgeschlossen mit Fehlern (Exit {status}).")
    elif sel.action == "uninstall":
        print("Deinstallation abgeschlossen.")
    else:
        print("Installation abgeschlossen.")
    for key in sorted(sel.programs):
        print(f"  • {PROGRAMS[key]['name']}")
    if sel.action == "install" and status == 0:
        if "hd60" in sel.programs:
            print("  Start HD60:        hd60s")
        if "wavelink" in sel.programs:
            print("  Start Wave Link:   wavelink-linux")


def main(argv: list[str] | None = None) -> int:
    if not sys.platform.startswith("linux"):
        print(
            f"Dieser Installer ({PRODUCT}) ist nur für Linux (Nobara/Fedora).",
            file=sys.stderr,
        )
        return 1

    args = parse_args(argv)
    root = project_root()
    sel = resolve_selection(args)

    print(textwrap.fill(LINUX_NOTE, width=78))
    print()
    print("Aktion:", "Deinstallieren" if sel.action == "uninstall" else "Installieren")
    print("Auswahl:")
    for key in sorted(sel.programs):
        print(f"  • {PROGRAMS[key]['name']}")

    if sel.action == "uninstall":
        status = run_linux_uninstall(root, sel.programs)
    else:
        status = run_linux_install(root, sel.programs)
    print_summary(sel, status)
    return status


if __name__ == "__main__":
    sys.exit(main())
