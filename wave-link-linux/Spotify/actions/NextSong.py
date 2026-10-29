from __future__ import annotations

from .base import SpotifyAction


class NextSong(SpotifyAction):
    def on_ready(self) -> None:
        self.set_icon("next.png")
        self.set_top_label("Next")
        self.set_bottom_label("")

    def on_key_down(self) -> None:
        ok = self.client().next()
        self.set_icon("next.png")
        if not ok:
            self.ok_or_error(False)
