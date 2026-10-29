from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelDef:
    key: str
    title: str
    sink_name: str
    accent: str
    is_mic: bool = False


# Klassische Wave-Link-Spuren + Aux
CHANNELS: list[ChannelDef] = [
    ChannelDef("system", "System", "wavelink_system", "#5B9FD4"),
    ChannelDef("music", "Music", "wavelink_music", "#E8A23A"),
    ChannelDef("browser", "Browser", "wavelink_browser", "#6BCB8A"),
    ChannelDef("voice", "Voice Chat", "wavelink_voice", "#D46BCB"),
    ChannelDef("game", "Game", "wavelink_game", "#E85D5D"),
    ChannelDef("sfx", "SFX", "wavelink_sfx", "#F0C94A"),
    ChannelDef("aux", "Auxiliary", "wavelink_aux", "#8B9BB4"),
    ChannelDef("mic", "Microphone", "wavelink_mic", "#4ECDC4", is_mic=True),
]

MONITOR_SINK = "wavelink_monitor"
STREAM_SINK = "wavelink_stream"

SINK_CHANNELS = [c for c in CHANNELS if not c.is_mic]
MIC_CHANNEL = next(c for c in CHANNELS if c.is_mic)

CHANNEL_BY_SINK = {c.sink_name: c for c in SINK_CHANNELS}
