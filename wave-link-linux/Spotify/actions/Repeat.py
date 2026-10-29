from __future__ import annotations

from .base import SpotifyAction


class Repeat(SpotifyAction):
    def on_key_down(self) -> None:
        ok = self.client().repeat()
        self.refresh()
        if not ok:
            self.ok_or_error(False)

    def refresh(self) -> None:
        state = self.client().repeat_state()
        if state == "track":
            self.set_icon("repeat_one.png")
            label = "ONE"
        elif state == "context":
            self.set_icon("repeat.png")
            label = "ALL"
        else:
            self.set_icon("no_repeat.png")
            label = "OFF"
        self.set_top_label("Repeat")
        self.set_bottom_label(label)
