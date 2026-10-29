from __future__ import annotations

import os
import sys

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase

plugin_dir = os.path.dirname(__file__)
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from actions.ChannelDial.ChannelDial import ChannelDial  # noqa: E402


class WaveLinkPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        self.lm = self.locale_manager
        try:
            self.lm.set_to_os_default()
        except Exception:
            pass

        dial_holder = ActionHolder(
            plugin_base=self,
            action_base=ChannelDial,
            action_id_suffix="ChannelDial",
            action_name=self.lm.get("actions.channel-dial.name")
            if hasattr(self.lm, "get")
            else "Channel Dial",
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
            },
        )
        self.add_action_holder(dial_holder)

        self.register(
            plugin_name="WaveLink",
            github_repo="https://github.com/local/wavelink-linux",
            plugin_version="1.0.0",
            app_version="1.5.0-beta",
        )
