from __future__ import annotations

import math
import threading
from typing import Any

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst


class PeakMeter:
    """Per-line peak meters via GStreamer `level` on Pulse monitors.

    Stores **raw linear** amplitude (0..~1). Display mapping and fader
    scaling happen in AudioEngine.get_channel_peak().
    """

    # Milder window than before (−45…0 dB) — less twitchy, still readable
    FLOOR_DB = -45.0
    CEIL_DB = 0.0

    def __init__(self):
        self._lock = threading.Lock()
        self._peaks: dict[str, float] = {}
        self._holds: dict[str, float] = {}
        self._pipelines: list[Any] = []
        self._loop: GLib.MainLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._raw_noise = 0.0015  # ~−56 dB

    def start(self, devices: dict[str, str]) -> None:
        if self._started or not devices:
            return

        Gst.init(None)
        self._started = True

        for key, device in devices.items():
            pipe = self._make_pipeline(key, device)
            if pipe is not None:
                self._pipelines.append(pipe)

        if not self._pipelines:
            self._started = False
            return

        self._thread = threading.Thread(
            target=self._run_loop, name="wavelink-peak-meter", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        loop = self._loop
        if loop is not None:
            try:
                GLib.idle_add(loop.quit)
            except Exception:
                pass
        for pipe in self._pipelines:
            try:
                pipe.set_state(Gst.State.NULL)
            except Exception:
                pass
        self._pipelines.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._loop = None

    @classmethod
    def to_display(cls, linear: float) -> float:
        """Map linear amplitude → 0..1 meter (dB scale, moderate sensitivity)."""
        if linear <= 1e-9 or not math.isfinite(linear):
            return 0.0
        db = 20.0 * math.log10(linear)
        if db <= cls.FLOOR_DB:
            return 0.0
        if db >= cls.CEIL_DB:
            return 1.0
        return (db - cls.FLOOR_DB) / (cls.CEIL_DB - cls.FLOOR_DB)

    def get_raw(self, key: str) -> float:
        with self._lock:
            peak = float(self._peaks.get(key, 0.0))
            hold = float(self._holds.get(key, 0.0))
            hold = max(peak, hold * 0.93)
            self._holds[key] = hold
            return peak

    def get_raw_hold(self, key: str) -> float:
        with self._lock:
            return float(self._holds.get(key, 0.0))

    def snapshot(self, key: str) -> dict[str, float | bool]:
        """Raw linear snapshot (no fader applied)."""
        peak = self.get_raw(key)
        hold = self.get_raw_hold(key)
        return {
            "peak_raw": round(peak, 5),
            "peak_hold_raw": round(hold, 5),
            "signal": peak >= self._raw_noise,
        }

    def _set_peak(self, key: str, linear: float) -> None:
        linear = max(0.0, min(1.5, float(linear)))
        if linear < self._raw_noise * 0.5:
            linear = 0.0
        with self._lock:
            prev = self._peaks.get(key, 0.0)
            if linear >= prev:
                smoothed = linear
            else:
                smoothed = prev * 0.62 + linear * 0.38
            self._peaks[key] = smoothed
            self._holds[key] = max(smoothed, self._holds.get(key, 0.0) * 0.96)

    def _make_pipeline(self, key: str, device: str):
        safe_name = "".join(c if c.isalnum() else "_" for c in key)
        desc = (
            f'pulsesrc device="{device}" '
            f"! audioconvert ! audioresample "
            f"! audio/x-raw,channels=2 "
            f"! level name=lvl_{safe_name} interval=40000000 post-messages=true "
            f"! fakesink sync=false async=false"
        )
        try:
            pipe = Gst.parse_launch(desc)
        except Exception:
            return None

        bus = pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message, key)
        pipe.set_state(Gst.State.PLAYING)
        return pipe

    def _on_bus_message(self, _bus, message, key: str):
        if message.type != Gst.MessageType.ELEMENT:
            return
        structure = message.get_structure()
        if structure is None or structure.get_name() != "level":
            return
        try:
            peaks = [float(v) for v in list(structure.get_value("peak"))]
            vals = [v for v in peaks if math.isfinite(v)]
            if not vals:
                return
            peak_db = max(vals)
            lin = 10.0 ** (peak_db / 20.0)
            if not math.isfinite(lin):
                lin = 0.0
            self._set_peak(key, lin)
        except Exception:
            return

    def _run_loop(self) -> None:
        self._loop = GLib.MainLoop()
        try:
            self._loop.run()
        except Exception:
            pass
        finally:
            for pipe in list(self._pipelines):
                try:
                    pipe.set_state(Gst.State.NULL)
                except Exception:
                    pass
