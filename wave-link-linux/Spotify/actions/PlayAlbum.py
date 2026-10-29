from __future__ import annotations

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw

from .base import SpotifyAction


class PlayAlbum(SpotifyAction):
    def on_ready(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.set_icon("album.png")
        self.set_top_label("Album")
        q = (self.get_settings().get("query") or "").strip()
        self.set_bottom_label((q[:10] + "…") if len(q) > 10 else q)

    def on_key_down(self) -> None:
        q = (self.get_settings().get("query") or "").strip()
        if not q:
            self.set_bottom_label("URI?")
            self.ok_or_error(False)
            return
        ok = self.client().search_and_play(q, "album")
        self.refresh()
        if not ok:
            self.ok_or_error(False)

    def get_config_rows(self) -> list:
        self.query_row = Adw.EntryRow(title="Album-Name, Spotify-URL oder URI")
        self.query_row.set_text(self.get_settings().get("query", ""))
        self.query_row.set_show_apply_button(True)
        self.query_row.connect("apply", self._on_query)
        hint = Adw.ActionRow(
            title="Beispiele",
            subtitle="Nevermind  ·  https://open.spotify.com/album/…  ·  spotify:album:…",
        )
        return [self.query_row, hint]

    def _on_query(self, row):
        s = self.get_settings()
        s["query"] = row.get_text().strip()
        self.set_settings(s)
        self.refresh()
