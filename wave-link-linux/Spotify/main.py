from __future__ import annotations

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from .actions.Favourite import Favourite
from .actions.NextSong import NextSong
from .actions.PlayAlbum import PlayAlbum
from .actions.PlayArtist import PlayArtist
from .actions.PlayPause import PlayPause
from .actions.PreviousSong import PreviousSong
from .actions.Repeat import Repeat
from .actions.Shuffle import Shuffle
from .utils.auth_window import WebAuthWindow
from .utils.spotify_client import LEGACY_REDIRECT_URI, REDIRECT_URI, SpotifyClient

DEFAULT_CLIENT_ID = "bf750454b4ca41a1928e4efb3bc0683d"
DEFAULT_CLIENT_SECRET = "64f93409a7cc433fa1a9f2214148c224"


class SpotifyPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        settings = self.get_settings()
        changed = False
        if not settings.get("client_id"):
            settings["client_id"] = DEFAULT_CLIENT_ID
            changed = True
        if not settings.get("client_secret"):
            settings["client_secret"] = DEFAULT_CLIENT_SECRET
            changed = True
        if changed:
            self.set_settings(settings)

        self.client = SpotifyClient(
            get_settings=self.get_settings,
            set_settings=self.set_settings,
        )
        self._auth_window = None
        self._status_poll = None

        actions = [
            (PlayPause, "PlayPause", "Play / Pause"),
            (NextSong, "NextSong", "Next Song"),
            (PreviousSong, "PreviousSong", "Previous Song"),
            (Shuffle, "Shuffle", "Shuffle"),
            (Favourite, "Favourite", "Favourite"),
            (Repeat, "Repeat", "Repeat"),
            (PlayAlbum, "PlayAlbum", "Play Album"),
            (PlayArtist, "PlayArtist", "Play Artist"),
        ]
        for cls, suffix, name in actions:
            holder = ActionHolder(
                plugin_base=self,
                action_base=cls,
                action_id_suffix=suffix,
                action_name=name,
                action_support={
                    Input.Key: ActionInputSupport.SUPPORTED,
                    Input.Dial: ActionInputSupport.SUPPORTED,
                    Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
                },
            )
            self.add_action_holder(holder)

        self.register(
            plugin_name="Spotify",
            github_repo="https://github.com/local/wavelink-spotify",
            plugin_version="1.2.0",
            app_version="1.5.0-beta",
        )

    def get_settings_area(self):
        group = Adw.PreferencesGroup(title="Spotify Login")

        self.id_row = Adw.EntryRow(title="Client ID")
        self.id_row.set_text(self.get_settings().get("client_id", ""))
        self.id_row.set_show_apply_button(True)
        self.id_row.connect("apply", self._on_id)
        group.add(self.id_row)

        self.secret_row = Adw.PasswordEntryRow(title="Client Secret")
        self.secret_row.set_text(self.get_settings().get("client_secret", ""))
        self.secret_row.set_show_apply_button(True)
        self.secret_row.connect("apply", self._on_secret)
        group.add(self.secret_row)

        info = Adw.ActionRow(
            title="Redirect URI (im Spotify Dashboard eintragen)",
            subtitle=REDIRECT_URI,
        )
        copy = Gtk.Button(label="Kopieren", css_classes=["flat"])
        copy.connect("clicked", self._copy_redirect)
        info.add_suffix(copy)
        group.add(info)

        dash = Adw.ButtonRow(title="Spotify Dashboard öffnen")
        dash.connect("activated", self._open_dashboard)
        group.add(dash)

        login = Adw.ButtonRow(title="Anmelden (Browser — empfohlen bei 2FA)")
        login.connect("activated", self._on_browser_login)
        group.add(login)

        login_wk = Adw.ButtonRow(title="Anmelden (eingebettetes Fenster)")
        login_wk.connect("activated", self._on_webview_login)
        group.add(login_wk)

        self.paste_row = Adw.EntryRow(
            title="Fallback: Redirect-URL oder Code einfügen"
        )
        self.paste_row.set_show_apply_button(True)
        self.paste_row.connect("apply", self._on_paste_code)
        group.add(self.paste_row)

        status = "Verbunden ✓" if self.client.is_authenticated() else "Nicht verbunden"
        self.status_row = Adw.ActionRow(title="Status", subtitle=status)
        group.add(self.status_row)

        fav_hint = Adw.ActionRow(
            title="Favourite / Album / Artist",
            subtitle="Falls Like nicht geht: einmal neu anmelden (Browser), damit Playlist-Rechte greifen. Like nutzt sonst „StreamDeck Likes“.",
        )
        group.add(fav_hint)

        hint = Adw.ActionRow(
            title="Einmalig vor dem Login",
            subtitle=(
                f"Dashboard → Redirect URIs → {REDIRECT_URI} hinzufügen & speichern. "
                f"(Optional zusätzlich: {LEGACY_REDIRECT_URI})"
            ),
        )
        group.add(hint)
        return group

    def _on_id(self, row):
        s = self.get_settings()
        s["client_id"] = row.get_text().strip()
        self.set_settings(s)

    def _on_secret(self, row):
        s = self.get_settings()
        s["client_secret"] = row.get_text().strip()
        self.set_settings(s)

    def _copy_redirect(self, *_args):
        display = Gtk.Widget.get_display(self.status_row)
        if display:
            display.get_clipboard().set(REDIRECT_URI)

    def _open_dashboard(self, *_args):
        app_id = self.client.client_id or DEFAULT_CLIENT_ID
        uri = f"https://developer.spotify.com/dashboard/{app_id}/settings"
        Gtk.show_uri(None, uri, 0)

    def _set_status(self, text: str) -> None:
        if hasattr(self, "status_row") and self.status_row:
            self.status_row.set_subtitle(text)

    def _start_status_poll(self) -> None:
        if self._status_poll:
            GLib.source_remove(self._status_poll)
            self._status_poll = None

        ticks = {"n": 0}

        def _tick():
            ticks["n"] += 1
            if self.client.is_authenticated():
                self._set_status("Verbunden ✓")
                self._status_poll = None
                return False
            if ticks["n"] >= 180:
                self._set_status("Timeout — Redirect-URI prüfen oder Code einfügen")
                self._status_poll = None
                return False
            if ticks["n"] % 5 == 0:
                self._set_status(f"Warte auf Browser-Login… ({ticks['n']}s)")
            return True

        self._status_poll = GLib.timeout_add_seconds(1, _tick)

    def _on_browser_login(self, *_args):
        if not self.client.client_id or not self.client.client_secret:
            self._set_status("Client ID/Secret fehlen")
            return
        msg = self.client.start_browser_login()
        self._set_status(msg.split("\n", 1)[0])
        self._start_status_poll()

    def _on_webview_login(self, *_args):
        if not self.client.client_id or not self.client.client_secret:
            self._set_status("Client ID/Secret fehlen")
            return
        url = self.client.authorize_url(LEGACY_REDIRECT_URI)
        app = None
        try:
            import globals as gl

            app = getattr(gl, "app", None)
        except Exception:
            pass
        self._auth_window = WebAuthWindow(
            initial_url=url,
            callback=self._on_auth_code,
            application=app,
        )
        self._auth_window.present()
        self._set_status("Login-Fenster offen — nach 2FA kurz warten…")

    def _on_paste_code(self, row):
        text = row.get_text().strip()
        code = self.client.extract_code_from_text(text)
        if not code:
            self._set_status("Kein gültiger Code/URL erkannt")
            return
        ok = self.client.exchange_code(code)
        self._set_status("Verbunden ✓" if ok else "Token-Austausch fehlgeschlagen (URI?)")
        if ok:
            row.set_text("")

    def _on_auth_code(self, code: str) -> bool:
        ok = self.client.exchange_code(code, redirect_uri=LEGACY_REDIRECT_URI)
        self._set_status(
            "Verbunden ✓" if ok else "Token-Austausch fehlgeschlagen"
        )
        return False
