from __future__ import annotations

import os

from src.backend.PluginManager.ActionBase import ActionBase

from ..utils.spotify_client import SpotifyClient


class SpotifyAction(ActionBase):
    def client(self) -> SpotifyClient:
        return self.plugin_base.client

    def set_icon(self, filename: str, size: float = 0.75) -> None:
        path = os.path.join(self.plugin_base.PATH, "assets", filename)
        if not os.path.isfile(path):
            return
        try:
            self.set_media(media_path=path, size=size)
        except Exception:
            try:
                from PIL import Image

                img = Image.open(path).convert("RGBA")
                self.set_media(image=img, size=size)
            except Exception:
                pass

    def on_ready(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        pass

    def ok_or_error(self, ok: bool) -> None:
        """Only flash error on hard failure; never leave error icon stuck."""
        if ok:
            return
        try:
            self.show_error(5)
        except TypeError:
            self.show_error()
