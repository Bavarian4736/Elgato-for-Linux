from __future__ import annotations

from .base import SpotifyAction


class Shuffle(SpotifyAction):
    def on_key_down(self) -> None:
        ok = self.client().shuffle()
        self.refresh()
        if not ok:
            self.ok_or_error(False)

    def refresh(self) -> None:
        on = self.client().shuffle_on()
        self.set_icon("shuffle.png" if on else "no_shuffle.png")
        self.set_top_label("Shuffle")
        self.set_bottom_label("ON" if on else "OFF")
