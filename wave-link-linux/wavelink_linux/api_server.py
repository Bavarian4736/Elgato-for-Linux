from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from .channels import CHANNELS

if TYPE_CHECKING:
    from .audio import AudioEngine

API_HOST = "127.0.0.1"
API_PORT = 24772


class _Handler(BaseHTTPRequestHandler):
    engine: AudioEngine

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}


    def _safe(self, fn):
        try:
            fn()
        except Exception as exc:
            try:
                self._json(500, {"error": str(exc)})
            except Exception:
                pass

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._do_GET()
        except Exception as exc:
            try:
                self._json(500, {"error": str(exc)})
            except Exception:
                pass

    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        eng = self.engine

        if path in ("/", "/v1", "/v1/status"):
            self._json(
                200,
                {
                    "ok": True,
                    "name": "WaveLink Linux",
                    "port": API_PORT,
                },
            )
            return

        if path == "/v1/channels":
            channels = []
            for ch in CHANNELS:
                mon_peak = eng.get_channel_peak(ch.key, "monitor")
                str_peak = eng.get_channel_peak(ch.key, "stream")
                channels.append(
                    {
                        "key": ch.key,
                        "title": ch.title,
                        "accent": eng.get_channel_color(ch.key),
                        "is_mic": ch.is_mic,
                        "peak": max(
                            float(mon_peak.get("peak", 0.0) or 0.0),
                            float(str_peak.get("peak", 0.0) or 0.0),
                        ),
                        "peak_hold": max(
                            float(mon_peak.get("peak_hold", 0.0) or 0.0),
                            float(str_peak.get("peak_hold", 0.0) or 0.0),
                        ),
                        "signal": bool(mon_peak.get("signal") or str_peak.get("signal")),
                        "monitor": {
                            "volume": eng.get_channel_volume(ch.key, "monitor"),
                            "muted": eng.get_channel_mute(ch.key, "monitor"),
                            "peak": mon_peak.get("peak", 0.0),
                            "peak_hold": mon_peak.get("peak_hold", 0.0),
                            "signal": bool(mon_peak.get("signal", False)),
                        },
                        "stream": {
                            "volume": eng.get_channel_volume(ch.key, "stream"),
                            "muted": eng.get_channel_mute(ch.key, "stream"),
                            "peak": str_peak.get("peak", 0.0),
                            "peak_hold": str_peak.get("peak_hold", 0.0),
                            "signal": bool(str_peak.get("signal", False)),
                        },
                    }
                )
            mon_peak = eng.get_channel_peak("master", "monitor")
            str_peak = eng.get_channel_peak("master", "stream")
            self._json(
                200,
                {
                    "channels": channels,
                    "master": {
                        "monitor": {
                            "volume": eng.get_master_volume("monitor"),
                            "muted": eng.get_master_mute("monitor"),
                            "peak": mon_peak.get("peak", 0.0),
                            "peak_hold": mon_peak.get("peak_hold", 0.0),
                            "signal": bool(mon_peak.get("signal", False)),
                        },
                        "stream": {
                            "volume": eng.get_master_volume("stream"),
                            "muted": eng.get_master_mute("stream"),
                            "peak": str_peak.get("peak", 0.0),
                            "peak_hold": str_peak.get("peak_hold", 0.0),
                            "signal": bool(str_peak.get("signal", False)),
                        },
                    },
                },
            )
            return

        if path.startswith("/v1/channel/"):
            key = path.split("/v1/channel/", 1)[1]
            if "/" in key:
                self._json(404, {"error": "not found"})
                return
            ch = next((c for c in CHANNELS if c.key == key), None)
            if not ch:
                self._json(404, {"error": "unknown channel"})
                return
            mix = (qs.get("mix") or ["monitor"])[0]
            if mix not in ("monitor", "stream"):
                mix = "monitor"
            peak = eng.get_channel_peak(ch.key, mix)
            self._json(
                200,
                {
                    "key": ch.key,
                    "title": ch.title,
                    "accent": eng.get_channel_color(ch.key),
                    "mix": mix,
                    "volume": eng.get_channel_volume(ch.key, mix),
                    "muted": eng.get_channel_mute(ch.key, mix),
                    "max_volume": getattr(eng, "MAX_VOLUME", 2.0),
                    "peak": peak.get("peak", 0.0),
                    "peak_hold": peak.get("peak_hold", 0.0),
                    "signal": bool(peak.get("signal", False)),
                },
            )
            return

        if path == "/v1/master":
            mix = (qs.get("mix") or ["monitor"])[0]
            if mix not in ("monitor", "stream"):
                mix = "monitor"
            peak = eng.get_channel_peak("master", mix)
            self._json(
                200,
                {
                    "mix": mix,
                    "volume": eng.get_master_volume(mix),
                    "muted": eng.get_master_mute(mix),
                    "max_volume": getattr(eng, "MAX_VOLUME", 2.0),
                    "peak": peak.get("peak", 0.0),
                    "peak_hold": peak.get("peak_hold", 0.0),
                    "signal": bool(peak.get("signal", False)),
                },
            )
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._do_POST()
        except Exception as exc:
            try:
                self._json(500, {"error": str(exc)})
            except Exception:
                pass

    def _do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        data = self._read_json()
        eng = self.engine

        if path.startswith("/v1/channel/"):
            rest = path.split("/v1/channel/", 1)[1]
            parts = rest.split("/")
            if len(parts) < 2:
                self._json(400, {"error": "bad path"})
                return
            key, action = parts[0], parts[1]
            ch = next((c for c in CHANNELS if c.key == key), None)
            if not ch:
                self._json(404, {"error": "unknown channel"})
                return
            mix = data.get("mix", "monitor")
            if mix not in ("monitor", "stream"):
                mix = "monitor"
            max_v = getattr(eng, "MAX_VOLUME", 2.0)

            if action == "volume":
                value = float(data.get("value", eng.get_channel_volume(key, mix)))
                eng.set_channel_volume(key, mix, value)
            elif action == "adjust":
                delta = float(data.get("delta", 0.05))
                value = eng.get_channel_volume(key, mix) + delta
                eng.set_channel_volume(key, mix, value)
            elif action == "mute":
                muted = bool(data.get("muted", True))
                eng.set_channel_mute(key, mix, muted)
            elif action == "toggle-mute":
                eng.set_channel_mute(key, mix, not eng.get_channel_mute(key, mix))
            elif action == "color":
                color = str(data.get("color") or data.get("accent") or "")
                eng.set_channel_color(key, color)
            else:
                self._json(404, {"error": "unknown action"})
                return

            self._json(
                200,
                {
                    "key": key,
                    "mix": mix,
                    "volume": eng.get_channel_volume(key, mix),
                    "muted": eng.get_channel_mute(key, mix),
                    "accent": eng.get_channel_color(key),
                    "max_volume": max_v,
                },
            )
            return

        if path.startswith("/v1/master/"):
            action = path.split("/v1/master/", 1)[1]
            mix = data.get("mix", "monitor")
            if mix not in ("monitor", "stream"):
                mix = "monitor"
            max_v = getattr(eng, "MAX_VOLUME", 2.0)

            if action == "volume":
                value = float(data.get("value", eng.get_master_volume(mix)))
                eng.set_master_volume(mix, value)
            elif action == "adjust":
                delta = float(data.get("delta", 0.05))
                eng.set_master_volume(mix, eng.get_master_volume(mix) + delta)
            elif action == "mute":
                eng.set_master_mute(mix, bool(data.get("muted", True)))
            elif action == "toggle-mute":
                eng.set_master_mute(mix, not eng.get_master_mute(mix))
            else:
                self._json(404, {"error": "unknown action"})
                return

            self._json(
                200,
                {
                    "mix": mix,
                    "volume": eng.get_master_volume(mix),
                    "muted": eng.get_master_mute(mix),
                    "max_volume": max_v,
                },
            )
            return

        self._json(404, {"error": "not found"})


class WaveLinkApiServer:
    def __init__(self, engine: AudioEngine, host: str = API_HOST, port: int = API_PORT):
        self.engine = engine
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        handler = type("WaveLinkHandler", (_Handler,), {"engine": self.engine})
        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError:
            # Port busy — another WaveLink instance already serves the API
            return

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="wavelink-api",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            self._httpd = None
        self._thread = None
