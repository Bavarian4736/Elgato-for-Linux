#!/usr/bin/env python3
"""Studio-Installer (Linux): HD60 und/oder Wave Link Linux auswählen und einrichten."""

from __future__ import annotations

import argparse
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


def studio_root() -> Path:
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
        description="Studio-Installer: HD60 und/oder Wave Link Linux wählen.",
    )
    p.add_argument("--hd60", action="store_true", help="HD60 installieren")
    p.add_argument("--wavelink", action="store_true", help="Wave Link Linux installieren")
    p.add_argument("--both", action="store_true", help="Beide Programme installieren")
    p.add_argument(
        "--noninteractive",
        action="store_true",
        help="Keine Rückfragen (Auswahl muss per Flags kommen)",
    )
    return p.parse_args(argv)


def choose_interactive() -> set[str]:
    try:
        return _choose_tk()
    except Exception:
        return _choose_cli()


def _choose_cli() -> set[str]:
    print()
    print("Studio — was soll eingerichtet werden?")
    print("  System: Linux (Nobara/Fedora)")
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
        text="Linux (Nobara/Fedora)\nWähle die Programme zum Einrichten:",
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

    ttk.Label(frame, text=LINUX_NOTE, wraplength=380, justify="left").grid(
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
    return value


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


def print_summary(programs: set[str]) -> None:
    print()
    print("Fertig.")
    for key in sorted(programs):
        print(f"  • {PROGRAMS[key]['name']}")
    if "hd60" in programs:
        print("  Start HD60:        hd60s")
    if "wavelink" in programs:
        print("  Start Wave Link:   wavelink-linux")


def main(argv: list[str] | None = None) -> int:
    if not sys.platform.startswith("linux"):
        print(
            "Dieser Installer ist nur für Linux (Nobara/Fedora).",
            file=sys.stderr,
        )
        return 1

    args = parse_args(argv)
    root = studio_root()
    programs = resolve_selection(args)

    print(textwrap.fill(LINUX_NOTE, width=78))
    print()
    print("Auswahl:")
    for key in sorted(programs):
        print(f"  • {PROGRAMS[key]['name']}")

    status = run_linux_install(root, programs)
    print_summary(programs)
    return status


if __name__ == "__main__":
    sys.exit(main())
