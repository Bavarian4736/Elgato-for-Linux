from __future__ import annotations

from .base import SpotifyAction


class Favourite(SpotifyAction):
    def on_key_down(self) -> None:
        ok = self.client().toggle_favourite()
        self.refresh()
        if not ok:
            self.set_bottom_label("Re-Login!")
            self.ok_or_error(False)

    def refresh(self) -> None:
        liked = self.client().is_favourite()
        self.set_icon("favourite.png" if liked else "favourite_off.png")
        self.set_top_label("Like")
        self.set_bottom_label("♥" if liked else "")
