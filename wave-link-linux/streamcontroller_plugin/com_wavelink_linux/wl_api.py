from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:24772"


class WaveLinkClient:
    def __init__(self, base: str = DEFAULT_BASE, timeout: float = 0.6):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict | None:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

    def status(self) -> bool:
        data = self._request("GET", "/v1/status")
        return bool(data and data.get("ok"))

    def channels(self) -> dict | None:
        return self._request("GET", "/v1/channels")

    def get_channel(self, key: str, mix: str) -> dict | None:
        if key == "master":
            return self._request("GET", f"/v1/master?mix={mix}")
        return self._request("GET", f"/v1/channel/{key}?mix={mix}")

    def adjust(self, key: str, mix: str, delta: float) -> dict | None:
        if key == "master":
            return self._request(
                "POST", "/v1/master/adjust", {"mix": mix, "delta": delta}
            )
        return self._request(
            "POST",
            f"/v1/channel/{key}/adjust",
            {"mix": mix, "delta": delta},
        )

    def toggle_mute(self, key: str, mix: str) -> dict | None:
        if key == "master":
            return self._request("POST", "/v1/master/toggle-mute", {"mix": mix})
        return self._request(
            "POST", f"/v1/channel/{key}/toggle-mute", {"mix": mix}
        )
