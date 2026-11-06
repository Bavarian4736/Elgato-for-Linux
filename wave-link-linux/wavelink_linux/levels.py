from __future__ import annotations

import math
import threading
import time
from typing import Any

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


class PeakMeter:
    """Per-line peak meters via GStreamer `level` on Pulse monitors.

    Stores **raw linear** amplitude (0..~1). Display mapping and fader
    scaling happen in AudioEngine.get_channel_peak().

    The meter thread polls pipeline buses itself. A GLib watch on the default
    main context fights GTK and leaves pulsesrc corked, so the strips stay at
    zero even while audio is playing. If a pipeline stops posting levels it is
    kicked back to PLAYING.
    """

    # Milder window than before (−45…0 dB) — less twitchy, still readable
    FLOOR_DB = -45.0
    CEIL_DB = 0.0

    def __init__(self):
        self._lock = threading.Lock()
        self._peaks: dict[str, float] = {}
        self._holds: dict[str, float] = {}
        self._pipelines: list[Any] = []
        self._thread: threading.Thread | None = None
        self._started = False
        self._raw_noise = 0.0015  # ~−56 dB
        self._devices: dict[str, str] = {}

    def start(self, devices: dict[str, str]) -> None:
        if self._started or not devices:
            return
        self._devices = dict(devices)
        self._started = True
        self._thread = threading.Thread(
            target=self._run, name="wavelink-peak-meter", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._started = False
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None

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
            f'pulsesrc device="{device}" client-name="wavelink-meter" '
            f"! audioconvert ! audioresample "
            f"! audio/x-raw,channels=2 "
            f"! level name=lvl_{safe_name} interval=40000000 post-messages=true "
            f"! fakesink sync=false async=false"
        )
        try:
            pipe = Gst.parse_launch(desc)
        except Exception:
            return None
        pipe.set_state(Gst.State.PLAYING)
        pipe.get_state(500 * Gst.MSECOND)
        return pipe

    def _handle_message(self, message, key: str) -> None:
        if message.type == Gst.MessageType.ERROR:
            return
        if message.type != Gst.MessageType.ELEMENT:
            return
        structure = message.get_structure()
        if structure is None or structure.get_name() != "level":
            return
        try:
            peaks = structure.get_value("peak")
            vals = [float(v) for v in list(peaks) if math.isfinite(float(v))]
        except Exception:
            return
        if not vals:
            self._set_peak(key, 0.0)
            return
        lin = 10.0 ** (max(vals) / 20.0)
        if not math.isfinite(lin):
            lin = 0.0
        self._set_peak(key, lin)

    def _kick(self, pipe) -> None:
        """Uncork a pulsesrc that stalled in PAUSED or stopped posting levels."""
        try:
            _ret, state, _pending = pipe.get_state(0)
            if state == Gst.State.PLAYING:
                pipe.set_state(Gst.State.PAUSED)
                pipe.get_state(50 * Gst.MSECOND)
            pipe.set_state(Gst.State.PLAYING)
        except Exception:
            pass

    def _run(self) -> None:
        try:
            Gst.init(None)
        except Exception:
            self._started = False
            return

        pipes: dict[str, Any] = {}
        for key, device in self._devices.items():
            pipe = self._make_pipeline(key, device)
            if pipe is not None:
                pipes[key] = pipe
        self._pipelines = list(pipes.values())
        if not pipes:
            self._started = False
            return

        last_level = {key: time.monotonic() for key in pipes}
        try:
            while self._started:
                now = time.monotonic()
                for key, pipe in list(pipes.items()):
                    try:
                        bus = pipe.get_bus()
                        saw_level = False
                        while True:
                            msg = bus.pop()
                            if msg is None:
                                break
                            if (
                                msg.type == Gst.MessageType.ELEMENT
                                and msg.get_structure() is not None
                                and msg.get_structure().get_name() == "level"
                            ):
                                saw_level = True
                            self._handle_message(msg, key)
                        if saw_level:
                            last_level[key] = now
                            continue
                        if now - last_level.get(key, now) < 0.8:
                            continue
                        self._kick(pipe)
                        last_level[key] = now
                    except Exception:
                        last_level[key] = now
                time.sleep(0.03)
        finally:
            for pipe in pipes.values():
                try:
                    pipe.set_state(Gst.State.NULL)
                except Exception:
                    pass
            self._pipelines = []
