#!/usr/bin/env python3
"""Grafische Einrichtung für Spurwerk, ohne Terminal."""

from __future__ import annotations

import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

import install_core


class InstallerWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, plugin_only: bool):
        super().__init__(application=app)
        self.set_default_size(520, 560)
        self._busy = False
        self._plugin_only = plugin_only
        self.set_title(
            "StreamController-Erweiterung" if plugin_only else "Spurwerk einrichten"
        )

        header = Adw.HeaderBar()
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.add_named(self._build_main_page(), "main")
        self._stack.add_named(self._build_plugin_page(), "plugin")

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self._stack)
        self.set_content(view)

        if plugin_only:
            self._stack.set_visible_child_name("plugin")
        self._stack.connect("notify::visible-child-name", self._sync_title)

    def _build_main_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        title = Gtk.Label(label="Spurwerk einrichten", xalign=0)
        title.add_css_class("title-1")
        intro = Gtk.Label(
            label=(
                "Installiert den Mixer für Nobara. PipeWire startet dabei neu, "
                "der Ton setzt kurz aus."
            ),
            xalign=0,
            wrap=True,
        )
        intro.add_css_class("dim-label")

        present = install_core.streamcontroller_present()
        group = Adw.PreferencesGroup(title="Umfang")
        self.plugin_switch = Adw.SwitchRow(title="StreamController-Erweiterung")
        self.plugin_switch.set_subtitle(
            "Drehregler und Spotify auf dem Stream Deck"
            if present
            else "StreamController ist nicht installiert"
        )
        self.plugin_switch.set_active(present)
        self.plugin_switch.set_sensitive(present)
        group.add(self.plugin_switch)

        self.install_button = Gtk.Button(label="Installieren")
        self.install_button.add_css_class("suggested-action")
        self.install_button.set_halign(Gtk.Align.START)
        self.install_button.connect("clicked", self._on_install_app)

        branch = Gtk.Label(label="Nur die Erweiterung", xalign=0)
        branch.add_css_class("title-4")
        branch_text = Gtk.Label(
            label="Damit lässt sich das Stream-Deck-Plugin einrichten, ohne den Mixer noch einmal zu installieren.",
            xalign=0,
            wrap=True,
        )
        branch_text.add_css_class("dim-label")
        self.branch_button = Gtk.Button(label="Nur die Erweiterung installieren")
        self.branch_button.set_halign(Gtk.Align.START)
        self.branch_button.connect(
            "clicked", lambda *_: self._stack.set_visible_child_name("plugin")
        )

        self.main_status = Gtk.Label(label="", xalign=0, wrap=True)
        self.main_spinner = Gtk.Spinner()

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_row.append(self.main_spinner)
        status_row.append(self.main_status)

        page.append(title)
        page.append(intro)
        page.append(group)
        page.append(self.install_button)
        page.append(Gtk.Separator())
        page.append(branch)
        page.append(branch_text)
        page.append(self.branch_button)
        page.append(status_row)
        return page

    def _build_plugin_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_top(24)
        page.set_margin_bottom(24)
        page.set_margin_start(24)
        page.set_margin_end(24)

        title = Gtk.Label(label="StreamController-Erweiterung", xalign=0)
        title.add_css_class("title-1")
        intro = Gtk.Label(
            label=(
                "Kopiert die Drehregler und das Spotify-Plugin nach StreamController. "
                "Der Mixer bleibt unangetastet. Danach StreamController neu starten."
            ),
            xalign=0,
            wrap=True,
        )
        intro.add_css_class("dim-label")

        self.plugin_banner = Adw.Banner()
        self.plugin_banner.set_title(
            "StreamController ist nicht installiert (Flatpak com.core447.StreamController)."
        )
        self.plugin_banner.set_revealed(not install_core.streamcontroller_present())

        self.plugin_button = Gtk.Button(label="Erweiterung installieren")
        self.plugin_button.add_css_class("suggested-action")
        self.plugin_button.set_halign(Gtk.Align.START)
        self.plugin_button.set_sensitive(install_core.streamcontroller_present())
        self.plugin_button.connect("clicked", self._on_install_plugin)

        self.back_button = Gtk.Button(label="Zurück")
        self.back_button.set_halign(Gtk.Align.START)
        self.back_button.set_visible(not self._plugin_only)
        self.back_button.connect(
            "clicked", lambda *_: self._stack.set_visible_child_name("main")
        )

        self.plugin_status = Gtk.Label(label="", xalign=0, wrap=True)
        self.plugin_spinner = Gtk.Spinner()
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_row.append(self.plugin_spinner)
        status_row.append(self.plugin_status)

        page.append(title)
        page.append(intro)
        page.append(self.plugin_banner)
        page.append(self.plugin_button)
        page.append(self.back_button)
        page.append(status_row)
        return page

    def _sync_title(self, *_args) -> None:
        if self._plugin_only or self._stack.get_visible_child_name() == "plugin":
            self.set_title("StreamController-Erweiterung")
        else:
            self.set_title("Spurwerk einrichten")

    def _set_busy(self, busy: bool, plugin_page: bool) -> None:
        self._busy = busy
        spinner = self.plugin_spinner if plugin_page else self.main_spinner
        if busy:
            spinner.start()
        else:
            spinner.stop()
        self.install_button.set_sensitive(not busy)
        self.branch_button.set_sensitive(not busy)
        self.back_button.set_sensitive(not busy)
        self.plugin_switch.set_sensitive(
            not busy and install_core.streamcontroller_present()
        )
        self.plugin_button.set_sensitive(
            not busy and install_core.streamcontroller_present()
        )

    def _status(self, plugin_page: bool, message: str) -> None:
        label = self.plugin_status if plugin_page else self.main_status
        label.set_text(message)

    def _run(self, plugin_page: bool, work, success: str) -> None:
        if self._busy:
            return
        self._set_busy(True, plugin_page)
        self._status(plugin_page, "Installation läuft…")

        def log(message: str) -> None:
            GLib.idle_add(self._status, plugin_page, message)

        def worker() -> None:
            try:
                work(log)
            except Exception as exc:
                text = str(exc).strip() or exc.__class__.__name__
                GLib.idle_add(self._finish, plugin_page, text, False)
                return
            GLib.idle_add(self._finish, plugin_page, success, True)

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, plugin_page: bool, message: str, ok: bool) -> bool:
        self._set_busy(False, plugin_page)
        self._status(plugin_page, message if ok else "")
        dialog = Adw.AlertDialog(
            heading="Fertig" if ok else "Installation fehlgeschlagen",
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)
        return False

    def _on_install_app(self, *_args) -> None:
        include_plugin = bool(self.plugin_switch.get_active())
        if include_plugin:
            success = (
                "Spurwerk und die Erweiterung sind installiert. "
                "Die App startest du im Menü unter „WaveLink Linux“. "
                "StreamController einmal neu starten."
            )
        else:
            success = (
                "Spurwerk ist installiert. "
                "Die App startest du im Menü unter „WaveLink Linux“."
            )
        self._run(
            False,
            lambda log: install_core.install_app(include_plugin, log),
            success,
        )

    def _on_install_plugin(self, *_args) -> None:
        self._run(
            True,
            install_core.install_plugins,
            "Die Erweiterung ist installiert. StreamController neu starten. "
            "Die Regler greifen, sobald der Mixer läuft.",
        )


class InstallerApp(Adw.Application):
    def __init__(self, plugin_only: bool):
        super().__init__(application_id="com.wavelink.linux.installer")
        self.plugin_only = plugin_only

    def do_activate(self) -> None:
        windows = self.get_windows()
        if windows:
            windows[0].present()
            return
        InstallerWindow(self, self.plugin_only).present()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    plugin_only = "--plugin-only" in args
    app = InstallerApp(plugin_only)
    return app.run([args[0]])


if __name__ == "__main__":
    raise SystemExit(main())
