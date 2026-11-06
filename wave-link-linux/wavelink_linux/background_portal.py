"""Eintrag in den GNOME-Schnelleinstellungen unter Hintergrundanwendungen.

GNOME Shell liest diese Liste nur vom Hintergrund-Portal, und das Portal nimmt
dort ausschließlich laufende Flatpak-Instanzen auf. Wave Link legt deshalb
eine eigene Instanz für sich selbst an. Die Berechtigung wird vorher auf „ja“
gesetzt, damit das Portal den Prozess nicht beendet.
"""

from __future__ import annotations

import fcntl
import json
import os
import random
import shutil
from pathlib import Path

APP_ID = "com.wavelink.linux"


class BackgroundListing:
    def __init__(self) -> None:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        self.root = Path(runtime) / ".flatpak"
        self.directory: Path | None = None
        self._lock = None

    def publish(self) -> None:
        try:
            self._grant()
            self._write()
        except Exception:
            self.remove()

    def remove(self) -> None:
        if self._lock is not None:
            try:
                fcntl.lockf(self._lock, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                self._lock.close()
            except OSError:
                pass
            self._lock = None
        if self.directory is not None:
            shutil.rmtree(self.directory, ignore_errors=True)
            shutil.rmtree(Path(f"{self.directory}-private"), ignore_errors=True)
            self.directory = None

    def _grant(self) -> None:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.freedesktop.impl.portal.PermissionStore",
            "/org/freedesktop/impl/portal/PermissionStore",
            "org.freedesktop.impl.portal.PermissionStore",
            "SetPermission",
            GLib.Variant(
                "(sbssas)", ("background", True, "background", APP_ID, ["yes"])
            ),
            None,
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )

    def _write(self) -> None:
        # Jeder Start braucht eine neue Instanznummer. Das Portal merkt sich
        # die alte Nummer mitsamt dem beendeten Prozess und zeigt sie danach
        # nicht wieder an.
        pid = os.getpid()
        self.root.mkdir(parents=True, exist_ok=True)
        directory = None
        instance_id = ""
        for _ in range(30):
            instance_id = str(random.randrange(100_000_000, 2_000_000_000))
            candidate = self.root / instance_id
            try:
                candidate.mkdir(mode=0o700)
            except FileExistsError:
                continue
            directory = candidate
            break
        if directory is None:
            raise RuntimeError("Kein freies Instanzverzeichnis")
        self.directory = directory
        (directory / "info").write_text(
            "[Application]\n"
            f"name={APP_ID}\n"
            "\n"
            "[Instance]\n"
            f"instance-id={instance_id}\n",
            encoding="utf-8",
        )
        (directory / "pid").write_text(f"{pid}\n", encoding="utf-8")
        (directory / "bwrapinfo.json").write_text(
            json.dumps({"child-pid": pid}) + "\n",
            encoding="utf-8",
        )
        private = Path(f"{directory}-private")
        private.mkdir(mode=0o700, exist_ok=True)
        # Flatpak prüft die Instanz mit einer POSIX-Sperre (fcntl). flock()
        # sieht das Portal nicht und löscht das Verzeichnis nach wenigen Sekunden.
        self._lock = open(directory / ".ref", "a+")
        fcntl.lockf(self._lock, fcntl.LOCK_EX)
