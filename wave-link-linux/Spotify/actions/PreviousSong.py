from __future__ import annotations

from .base import SpotifyAction


class PreviousSong(SpotifyAction):
    def on_ready(self) -> None:
        self.set_icon("previous.png")
        self.set_top_label("Prev")
        self.set_bottom_label("")

    def on_key_down(self) -> None:
        ok = self.client().previous()
        self.set_icon("previous.png")
        if not ok:
            self.ok_or_error(False)
