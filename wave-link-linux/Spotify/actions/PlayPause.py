from __future__ import annotations

from .base import SpotifyAction


class PlayPause(SpotifyAction):
    def on_key_down(self) -> None:
        ok = self.client().play_pause()
        self.refresh()
        if not ok:
            self.ok_or_error(False)

    def on_ready(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        playing = self.client().is_playing()
        self.set_icon("pause.png" if playing else "play.png")
        self.set_top_label("Pause" if playing else "Play")
        self.set_bottom_label("")
