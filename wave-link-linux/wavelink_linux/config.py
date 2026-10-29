from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "wavelink-linux"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "monitor_device": "",
    "mic_device": "",
    "volumes": {},
    # Mic → Headset standardmäßig stumm (kein Selbsthören)
    "mutes": {"mic:monitor": True},
    "assignments": {},  # app_key -> channel_key
    "colors": {},  # channel_key -> "#RRGGBB"
    "ui": {
        "sidebar_width": 280,
    },
}


def load() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save(DEFAULTS.copy())
        return DEFAULTS.copy()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    merged = DEFAULTS.copy()
    merged.update(data)
    merged["volumes"] = {**DEFAULTS["volumes"], **data.get("volumes", {})}
    # Defaults first, then user overrides (so existing installs keep choices)
    merged["mutes"] = {**DEFAULTS["mutes"], **data.get("mutes", {})}
    # If user never set mic:monitor mute, keep default True
    if "mic:monitor" not in data.get("mutes", {}):
        merged["mutes"]["mic:monitor"] = True
    merged["assignments"] = {**DEFAULTS["assignments"], **data.get("assignments", {})}
    merged["colors"] = {**DEFAULTS["colors"], **data.get("colors", {})}
    merged["ui"] = {**DEFAULTS["ui"], **data.get("ui", {})}
    return merged


def save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
