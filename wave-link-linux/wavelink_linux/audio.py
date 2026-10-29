from __future__ import annotations

import os
import signal
import threading
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable

import pulsectl

from .apps_discovery import list_running_apps
from .channels import (
    CHANNELS,
    CHANNEL_BY_SINK,
    MIC_CHANNEL,
    MONITOR_SINK,
    SINK_CHANNELS,
    STREAM_SINK,
)
from . import config as app_config
from .levels import PeakMeter

# Discord ignores sink monitors — expose a real Audio/Source:
MIC_SOURCE_NAME = "wavelink_mic_source"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    uid = os.getuid()
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    env["XDG_RUNTIME_DIR"] = runtime
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
    return env


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        env=_env(),
        check=check,
        capture_output=True,
        text=True,
    )


@dataclass
class AppStream:
    index: int  # sink-input index, or -1 if idle (no audio stream yet)
    name: str
    application: str
    media_name: str
    sink: int
    sink_name: str
    icon_name: str
    pid: str
    binary: str
    assign_key: str = ""  # stable key for drag/drop + persistence
    channel_key: str | None = None  # assigned channel (even without live stream)
    is_live: bool = True

    @property
    def key(self) -> str:
        if self.assign_key:
            return self.assign_key
        base = self.binary or self.application or self.name
        return base

    @property
    def label(self) -> str:
        return self.application or self.media_name or self.name


@dataclass
class Device:
    name: str
    description: str
    index: int


@dataclass
class AudioEngine:
    settings: dict = field(default_factory=app_config.load)
    _pulse: pulsectl.Pulse | None = None
    _loopbacks: dict[str, subprocess.Popen] = field(default_factory=dict)
    _on_change: list[Callable[[], None]] = field(default_factory=list)
    _pulse_lock: threading.RLock = field(default_factory=threading.RLock)
    _thread_pulses: dict = field(default_factory=dict)
    peak_meter: PeakMeter = field(default_factory=PeakMeter)

    def connect(self) -> None:
        # Keep a primary connection for the creating/UI thread.
        if self._pulse is None:
            self._pulse = pulsectl.Pulse("wavelink-linux")

    def close(self) -> None:
        # Loopbacks bewusst weiterlaufen lassen, damit Monitor/Stream
        # nach dem Schließen der UI aktiv bleiben.
        try:
            self.peak_meter.stop()
        except Exception:
            pass
        self._loopbacks.clear()
        with self._pulse_lock:
            if self._pulse is not None:
                try:
                    self._pulse.close()
                except Exception:
                    pass
                self._pulse = None
            for pulse in list(self._thread_pulses.values()):
                try:
                    pulse.close()
                except Exception:
                    pass
            self._thread_pulses.clear()

    @property
    def pulse(self) -> pulsectl.Pulse:
        """Return a Pulse connection for *this* thread.

        pulsectl forbids using one connection from multiple threads (API server
        vs GTK). Each thread gets its own client under a process-wide lock.
        """
        tid = threading.get_ident()
        with self._pulse_lock:
            # Prefer dedicated per-thread clients for worker threads
            if tid in self._thread_pulses:
                return self._thread_pulses[tid]
            if self._pulse is None:
                self._pulse = pulsectl.Pulse("wavelink-linux")
                return self._pulse
            # First thread to call pulse keeps the primary; others get clones
            owner = getattr(self, "_pulse_owner_tid", None)
            if owner is None:
                self._pulse_owner_tid = tid
                return self._pulse
            if owner == tid:
                return self._pulse
            pulse = pulsectl.Pulse(f"wavelink-linux-{tid}")
            self._thread_pulses[tid] = pulse
            return pulse

    def _with_pulse(self, fn):
        """Run a Pulse operation with the engine lock held."""
        with self._pulse_lock:
            return fn(self.pulse)

    def subscribe(self, cb: Callable[[], None]) -> None:
        self._on_change.append(cb)

    def notify(self) -> None:
        for cb in list(self._on_change):
            try:
                cb()
            except Exception:
                pass

    # --- sink lifecycle -------------------------------------------------

    def ensure_sinks(self) -> None:
        """Create missing WaveLink adapter sinks at runtime."""
        existing = {s.name for s in self.pulse.sink_list()}
        needed = [c.sink_name for c in SINK_CHANNELS] + [
            MONITOR_SINK,
            STREAM_SINK,
            MIC_CHANNEL.sink_name,  # clean mic-only bus for Discord
        ]
        for name in needed:
            if name in existing:
                continue
            desc = {
                **{c.sink_name: f"WaveLink {c.title}" for c in SINK_CHANNELS},
                MONITOR_SINK: "WaveLink Monitor Mix",
                STREAM_SINK: "WaveLink Stream Mix",
                MIC_CHANNEL.sink_name: "WaveLink Microphone",
            }[name]
            props = (
                "{ "
                f'factory.name=support.null-audio-sink '
                f'node.name={name} '
                f'node.description="{desc}" '
                f'media.class=Audio/Sink '
                f"object.linger=true "
                f"audio.position=[FL,FR] "
                f"monitor.channel-volumes=true "
                "}"
            )
            _run(["pw-cli", "create-node", "adapter", props])
        # wait briefly for pulse to see them
        for _ in range(20):
            names = {s.name for s in self.pulse.sink_list()}
            if all(n in names for n in needed):
                break
            time.sleep(0.1)

    def sink_by_name(self, name: str):
        for s in self.pulse.sink_list():
            if s.name == name:
                return s
        return None

    def hardware_sinks(self) -> list[Device]:
        skip = {c.sink_name for c in SINK_CHANNELS} | {
            MONITOR_SINK,
            STREAM_SINK,
            MIC_CHANNEL.sink_name,
        }
        devices: list[Device] = []
        for s in self.pulse.sink_list():
            if s.name in skip:
                continue
            if s.name.startswith("wavelink_"):
                continue
            # Never offer USB mic headphone jacks as WaveLink monitor output
            # (desktop audio there bleeds back into the mic capsule / sidetone).
            blob = f"{s.name} {s.description}".lower()
            if any(k in blob for k in ("quadcast", "yeti", "blue_snowball", "usb_microphone")):
                if "blackshark" not in blob and "headset" not in blob:
                    continue
            devices.append(Device(s.name, s.description, s.index))
        return devices

    def hardware_sources(self) -> list[Device]:
        devices: list[Device] = []
        for s in self.pulse.source_list():
            if s.name.endswith(".monitor"):
                continue
            if s.name.startswith("wavelink_"):
                continue
            devices.append(Device(s.name, s.description, s.index))
        return devices

    # --- loopbacks ------------------------------------------------------

    def _loopback_cmd(
        self,
        name: str,
        capture: str,
        playback: str,
        *,
        capture_from_sink: bool = True,
    ) -> list[str]:
        # stream.capture.sink=true: capture from a sink's monitor ports.
        # node.dont-reconnect + target.object: stop WirePlumber/Easy Effects
        # from silently remapping capture to easyeffects_source (silent mic).
        cmd = [
            "pw-loopback",
            "-n",
            name,
            "-C",
            capture,
            "-P",
            playback,
            "-c",
            "2",
            "-m",
            "[ FL, FR ]",
            "-g",
            "wavelink",
        ]
        if capture_from_sink:
            props = (
                "{ stream.capture.sink=true "
                f'target.object="{capture}" node.dont-reconnect=true }}'
            )
            cmd.extend(["-i", props])
        else:
            props = (
                "{ "
                f'target.object="{capture}" node.dont-reconnect=true }}'
            )
            cmd.extend(["-i", props])
        return cmd

    def _spawn_loopback(
        self,
        name: str,
        capture: str,
        playback: str,
        *,
        capture_from_sink: bool = True,
        playback_as_source: bool = False,
        source_description: str = "WaveLink Microphone",
    ) -> None:
        if playback_as_source:
            # Virtual mic: capture a sink monitor, expose as Audio/Source for Discord
            cmd = [
                "pw-loopback",
                "-n",
                name,
                "-C",
                capture,
                "-c",
                "2",
                "-m",
                "[ FL, FR ]",
                "-g",
                "wavelink",
                "-i",
                (
                    "{ stream.capture.sink=true "
                    f'target.object="{capture}" node.dont-reconnect=true }}'
                ),
                "-o",
                (
                    "{ media.class=Audio/Source "
                    f'node.name={name} '
                    f'node.description="{source_description}" '
                    "audio.position=[FL,FR] }"
                ),
            ]
        else:
            cmd = self._loopback_cmd(
                name, capture, playback, capture_from_sink=capture_from_sink
            )
        proc = subprocess.Popen(
            cmd,
            env=_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._loopbacks[name] = proc

    def start_loopbacks(self) -> None:
        self.stop_loopbacks()
        self._disable_hardware_mic_monitor()

        # Channel → Monitor / Stream (capture FROM sink monitors)
        for ch in SINK_CHANNELS:
            for mix, sink in (("monitor", MONITOR_SINK), ("stream", STREAM_SINK)):
                name = f"wavelink_{ch.key}_to_{mix}"
                self._spawn_loopback(name, ch.sink_name, sink, capture_from_sink=True)

        # Physical mic → clean WaveLink Microphone bus (Discord should use this,
        # NOT Stream Mix — Stream Mix contains desktop audio).
        mic = self.settings.get("mic_device") or self._default_source_name()
        if mic:
            self._spawn_loopback(
                "wavelink_hw_to_mic",
                mic,
                MIC_CHANNEL.sink_name,
                capture_from_sink=False,
            )
            # Real Audio/Source for Discord (apps hide sink monitors)
            self._spawn_loopback(
                MIC_SOURCE_NAME,
                MIC_CHANNEL.sink_name,
                MIC_SOURCE_NAME,
                capture_from_sink=True,
                playback_as_source=True,
                source_description="WaveLink Microphone",
            )
            # Clean mic bus → Stream Mix (OBS / full broadcast mix)
            self._spawn_loopback(
                "wavelink_mic_to_stream",
                MIC_CHANNEL.sink_name,
                STREAM_SINK,
                capture_from_sink=True,
            )
            # Monitor mix: only if not muted (default: muted → no self-hear)
            if not self.get_channel_mute("mic", "monitor"):
                self._spawn_loopback(
                    "wavelink_mic_to_monitor",
                    MIC_CHANNEL.sink_name,
                    MONITOR_SINK,
                    capture_from_sink=True,
                )

        # Monitor mix → hardware headphones (never the USB mic jack)
        out = self.settings.get("monitor_device") or self._default_sink_name()
        if out and out not in {MONITOR_SINK, STREAM_SINK, MIC_CHANNEL.sink_name}:
            if "quadcast" not in out.lower():
                self._spawn_loopback(
                    "wavelink_monitor_to_hw",
                    MONITOR_SINK,
                    out,
                    capture_from_sink=True,
                )

        time.sleep(0.45)
        self.apply_saved_levels()
        self.pin_mic_capture()
        self.pin_discord_to_clean_mic()
        self._silence_usb_mic_headphones()

    def pin_mic_capture(self) -> None:
        """Force physical mic → clean mic bus; keep EE from stealing the capture."""
        mic = self.settings.get("mic_device") or self._default_source_name()
        if not mic:
            return
        # Hardware → clean mic sink
        for ch in ("FL", "FR"):
            src = f"{mic}:capture_{ch}"
            dst = "input.wavelink_hw_to_mic:input_" + ch
            _run(["pw-link", "-d", f"easyeffects_source:capture_{ch}", dst])
            _run(["pw-link", "-d", f"{STREAM_SINK}:monitor_{ch}", dst])
            _run(["pw-link", src, dst])
        # Clean mic bus → stream / monitor loopbacks
        for suffix in ("stream", "monitor"):
            name = f"wavelink_mic_to_{suffix}"
            if suffix == "monitor" and self.get_channel_mute("mic", "monitor"):
                continue
            for ch in ("FL", "FR"):
                src = f"{MIC_CHANNEL.sink_name}:monitor_{ch}"
                dst = f"input.{name}:input_{ch}"
                _run(["pw-link", "-d", f"easyeffects_source:capture_{ch}", dst])
                _run(["pw-link", "-d", f"{mic}:capture_{ch}", dst])
                _run(["pw-link", src, dst])

    def pin_discord_to_clean_mic(self) -> None:
        """Discord must hear ONLY the mic — never Stream Mix (that has desktop)."""
        try:
            sources = list(self.pulse.source_list())
        except Exception:
            sources = []
        mon = next((s for s in sources if s.name == MIC_SOURCE_NAME), None)
        if mon is None:
            mon = next(
                (s for s in sources if s.name == f"{MIC_CHANNEL.sink_name}.monitor"),
                None,
            )
        if mon is None:
            # Fallback: real hardware mic
            mic_name = self.settings.get("mic_device") or self._default_source_name()
            mon = next((s for s in sources if s.name == mic_name), None)
        if mon is None:
            return
        for o in self.pulse.source_output_list():
            app = o.proplist.get("application.name") or ""
            if "WEBRTC" not in app and "Discord" not in app:
                continue
            if o.source != mon.index:
                try:
                    self.pulse.source_output_move(o.index, mon.index)
                except Exception:
                    pass
        mic_hw = self.settings.get("mic_device") or ""
        for ch in ("FL", "FR"):
            dst = f"WEBRTC VoiceEngine:input_{ch}"
            # Drop desktop / EE / stream-mix feeds into Discord
            _run(["pw-link", "-d", f"easyeffects_source:capture_{ch}", dst])
            _run(["pw-link", "-d", f"{STREAM_SINK}:monitor_{ch}", dst])
            _run(["pw-link", "-d", f"{MONITOR_SINK}:monitor_{ch}", dst])
            if mic_hw:
                _run(["pw-link", "-d", f"{mic_hw}:capture_{ch}", dst])
            # Prefer virtual WaveLink Microphone source (visible in Discord)
            _run(["pw-link", "-d", f"{MIC_CHANNEL.sink_name}:monitor_{ch}", dst])
            _run(["pw-link", f"{MIC_SOURCE_NAME}:capture_{ch}", dst])

    def maintain_routing(self) -> None:
        self.pin_mic_capture()
        self.pin_discord_to_clean_mic()
        self._silence_usb_mic_headphones()
        self.apply_assignments()

    def _disable_hardware_mic_monitor(self) -> None:
        """Mute USB-mic sidetone + headphone jack playback (never capture)."""
        try:
            out = _run(["arecord", "-l"])
            for line in out.stdout.splitlines():
                lower = line.lower()
                if "card" not in lower:
                    continue
                if not any(
                    k in line
                    for k in ("QuadCast", "Wave:", "USB Microphone", "Yeti", "Snowball")
                ):
                    continue
                token = line.split(":")[0]
                card = "".join(ch for ch in token if ch.isdigit())
                if not card:
                    continue
                for ctl, val in (
                    ("name=Mic Playback Switch", "off"),
                    ("name=Mic Playback Volume", "0"),
                    ("name=Speaker Playback Switch", "off"),
                    ("name=Speaker Playback Volume", "0"),
                    ("name=Headphone Playback Switch", "off"),
                    ("name=Headphone Playback Volume", "0"),
                ):
                    _run(["amixer", "-c", card, "cset", ctl, val])
        except Exception:
            pass

    def _silence_usb_mic_headphones(self) -> None:
        """Mute PipeWire sinks that are USB mic headphone jacks."""
        try:
            for s in self.pulse.sink_list():
                blob = f"{s.name} {s.description}".lower()
                if not any(
                    k in blob for k in ("quadcast", "yeti", "snowball", "usb_microphone")
                ):
                    continue
                if "blackshark" in blob or "headset" in blob:
                    continue
                try:
                    self.pulse.mute(s, True)
                    self.pulse.volume_set_all_chans(s, 0.0)
                except Exception:
                    pass
                # Also disconnect any playback links into this sink
                for ch in ("FL", "FR"):
                    _run(
                        [
                            "pw-link",
                            "-d",
                            f"output.wavelink_monitor_to_hw:output_{ch}",
                            f"{s.name}:playback_{ch}",
                        ]
                    )
        except Exception:
            pass

    def _kill_named_loopback(self, name: str) -> None:
        proc = self._loopbacks.pop(name, None)
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        _run(["pkill", "-f", f"pw-loopback -n {name}"])

    def stop_loopbacks(self) -> None:
        for name, proc in list(self._loopbacks.items()):
            try:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
                    try:
                        proc.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:
                pass
        self._loopbacks.clear()
        # Also kill leftover loopbacks from previous runs
        _run(["pkill", "-f", "pw-loopback -n wavelink_"])

    def _default_sink_name(self) -> str:
        try:
            info = self.pulse.server_info()
            return info.default_sink_name or ""
        except Exception:
            return ""

    def _default_source_name(self) -> str:
        try:
            info = self.pulse.server_info()
            return info.default_source_name or ""
        except Exception:
            return ""

    def set_monitor_device(self, sink_name: str) -> None:
        self.settings["monitor_device"] = sink_name
        app_config.save(self.settings)
        self.start_loopbacks()

    def set_mic_device(self, source_name: str) -> None:
        self.settings["mic_device"] = source_name
        app_config.save(self.settings)
        self.start_loopbacks()

    # --- apps -----------------------------------------------------------

    def _stable_app_key(self, binary: str, application: str, desktop_hint: str = "") -> str:
        return desktop_hint or binary or application or "app"

    def list_apps(self) -> list[AppStream]:
        """Live audio streams + all currently open desktop apps."""
        sinks = {s.index: s.name for s in self.pulse.sink_list()}
        asg = self.settings.get("assignments") or {}
        by_key: dict[str, AppStream] = {}

        # 1) Active Pulse sink inputs
        for i in self.pulse.sink_input_list():
            props = i.proplist
            node = props.get("node.name", "")
            if node.startswith("output.wavelink_") or node.startswith("wavelink_"):
                continue
            if "wavelink_" in node and "to_" in node:
                continue
            if props.get("application.id") == "wavelink-linux":
                continue
            binary = props.get("application.process.binary", "")
            application = (
                props.get("application.name")
                or binary
                or i.name
                or "App"
            )
            key = self._stable_app_key(binary, application)
            channel = self.channel_for_sink_name(sinks.get(i.sink, ""))
            # Prefer saved assignment if present
            channel = asg.get(key) or asg.get(binary) or channel
            by_key[key] = AppStream(
                index=i.index,
                name=i.name or node or "Stream",
                application=application,
                media_name=props.get("media.name", ""),
                sink=i.sink,
                sink_name=sinks.get(i.sink, ""),
                icon_name=props.get("application.icon_name")
                or binary
                or "audio-x-generic",
                pid=props.get("application.process.id", ""),
                binary=binary,
                assign_key=key,
                channel_key=channel,
                is_live=True,
            )

        # 2) All open GUI apps (even without audio)
        for running in list_running_apps():
            key = running.key
            if key in by_key:
                # Enrich label/icon from desktop entry
                live = by_key[key]
                if running.label:
                    live.application = running.label
                if running.icon_name:
                    live.icon_name = running.icon_name
                continue
            # Merge with live stream under a different key (e.g. Spotify vs flatpak id)
            matched = False
            for live in by_key.values():
                same = False
                if live.binary and running.binary and live.binary == running.binary:
                    same = True
                elif live.application and running.label and live.application.lower() == running.label.lower():
                    same = True
                elif running.desktop_id and running.desktop_id.lower() in (
                    (live.binary or "").lower(),
                    (live.application or "").lower(),
                ):
                    same = True
                if same:
                    live.application = running.label or live.application
                    live.icon_name = running.icon_name or live.icon_name
                    # Keep pulse assignment keys working: also store flatpak id alias
                    if running.key and running.key not in asg and live.key in asg:
                        pass
                    matched = True
                    break
            if matched:
                continue
            channel = asg.get(key) or asg.get(running.binary)
            by_key[key] = AppStream(
                index=-1,
                name=running.label,
                application=running.label,
                media_name="",
                sink=-1,
                sink_name="",
                icon_name=running.icon_name or "audio-x-generic",
                pid=running.pid,
                binary=running.binary,
                assign_key=key,
                channel_key=channel,
                is_live=False,
            )

        return sorted(by_key.values(), key=lambda a: a.label.lower())

    def channel_for_sink_name(self, sink_name: str) -> str | None:
        ch = CHANNEL_BY_SINK.get(sink_name)
        return ch.key if ch else None

    def _assignment_lookup(self, *candidates: str) -> str | None:
        asg = self.settings.get("assignments") or {}
        if not asg:
            return None
        # exact
        for c in candidates:
            if c and c in asg:
                return asg[c]
        # case-insensitive / substring (Discord vs discord)
        lower_map = {k.lower(): v for k, v in asg.items()}
        for c in candidates:
            if not c:
                continue
            if c.lower() in lower_map:
                return lower_map[c.lower()]
        return None

    def assigned_channel(self, app: AppStream) -> str | None:
        return (
            self._assignment_lookup(app.key, app.binary, app.application)
            or app.channel_key
        )

    def move_app_key(self, assign_key: str, channel_key: str) -> None:
        ch = next((c for c in SINK_CHANNELS if c.key == channel_key), None)
        if ch is None or not assign_key:
            return
        self.settings.setdefault("assignments", {})[assign_key] = channel_key
        app_config.save(self.settings)

        sink = self.sink_by_name(ch.sink_name)
        if sink is None:
            self.notify()
            return
        # Move any live streams matching this key/binary
        for app in self.list_apps():
            if app.key != assign_key and app.binary != assign_key:
                continue
            if app.index < 0:
                continue
            try:
                self.pulse.sink_input_move(app.index, sink.index)
            except pulsectl.PulseOperationFailed:
                pass
        self.notify()

    def move_app(self, sink_input_index: int, channel_key: str) -> None:
        """Legacy: move by sink-input index (also persists assignment)."""
        app = next((a for a in self.list_apps() if a.index == sink_input_index), None)
        if app:
            self.move_app_key(app.key, channel_key)
            return
        ch = next((c for c in SINK_CHANNELS if c.key == channel_key), None)
        if ch is None:
            return
        sink = self.sink_by_name(ch.sink_name)
        if sink is None:
            return
        try:
            self.pulse.sink_input_move(sink_input_index, sink.index)
        except pulsectl.PulseOperationFailed:
            return
        self.notify()

    def unassign_app_key(self, assign_key: str) -> None:
        asg = self.settings.setdefault("assignments", {})
        asg.pop(assign_key, None)
        # Also clear binary alias if present
        for app in list(self.list_apps()):
            if app.key == assign_key and app.binary:
                asg.pop(app.binary, None)
        app_config.save(self.settings)

        default = self._default_sink_name()
        sink = self.sink_by_name(default) if default else None
        if sink is None:
            hardware = self.hardware_sinks()
            if hardware:
                sink = self.sink_by_name(hardware[0].name)
        if sink is not None:
            for app in self.list_apps():
                if app.key != assign_key and app.binary != assign_key:
                    continue
                if app.index < 0:
                    continue
                try:
                    self.pulse.sink_input_move(app.index, sink.index)
                except pulsectl.PulseOperationFailed:
                    pass
        self.notify()

    def unassign_app(self, sink_input_index: int) -> None:
        app = next((a for a in self.list_apps() if a.index == sink_input_index), None)
        if app:
            self.unassign_app_key(app.key)
            return

    def apply_assignments(self) -> None:
        asg = self.settings.get("assignments") or {}
        if not asg:
            return
        for app in self.list_apps():
            if app.index < 0:
                continue
            key = asg.get(app.key) or asg.get(app.binary)
            if not key:
                continue
            ch = next((c for c in SINK_CHANNELS if c.key == key), None)
            if not ch:
                continue
            if app.sink_name == ch.sink_name:
                continue
            sink = self.sink_by_name(ch.sink_name)
            if sink:
                try:
                    self.pulse.sink_input_move(app.index, sink.index)
                except pulsectl.PulseOperationFailed:
                    pass

    # --- volumes --------------------------------------------------------

    MAX_VOLUME = 2.0  # 200%

    def _vol_key(self, channel_key: str, mix: str) -> str:
        return f"{channel_key}:{mix}"

    def _level_key(self, channel_key: str, mix: str = "monitor") -> str:
        if channel_key == "master":
            return f"master:{mix}" if mix in ("monitor", "stream") else "master:monitor"
        return channel_key

    def get_channel_peak(self, channel_key: str, mix: str = "monitor") -> dict:
        """Post-fader meter: signal × software volume, relative to max scale.

        display = meter(signal) × (fader / 100%), clamped to 0..1.
        At 100% fader the VU follows the audio; at 50% it is half as high.
        Faders above 100% (up to MAX_VOLUME=200%) can push into the hot zone.
        Mute forces the meter to 0.
        """
        meter_key = self._level_key(channel_key, mix)
        snap = self.peak_meter.snapshot(meter_key)
        raw = float(snap.get("peak_raw", 0.0) or 0.0)
        raw_hold = float(snap.get("peak_hold_raw", 0.0) or 0.0)

        if channel_key == "master":
            vol = self.get_master_volume(mix)
            muted = self.get_master_mute(mix)
        else:
            vol = self.get_channel_volume(channel_key, mix)
            muted = self.get_channel_mute(channel_key, mix)

        max_possible = float(self.MAX_VOLUME) or 2.0
        # 1.0 = 100% (unity). Values up to max_possible allow 200% headroom on the meter.
        fader_scale = 0.0 if muted else max(0.0, min(float(vol), max_possible))

        signal = PeakMeter.to_display(raw)
        signal_hold = PeakMeter.to_display(raw_hold)
        peak = max(0.0, min(1.0, signal * fader_scale))
        hold = max(0.0, min(1.0, signal_hold * fader_scale))

        return {
            "peak": round(peak, 4),
            "peak_hold": round(hold, 4),
            "peak_raw": round(raw, 5),
            "volume": round(0.0 if muted else float(vol), 4),
            "max_volume": max_possible,
            "signal": (not muted) and peak >= 0.04,
        }

    def start_peak_meters(self) -> None:
        devices: dict[str, str] = {}
        for ch in CHANNELS:
            devices[ch.key] = f"{ch.sink_name}.monitor"
        devices["master:monitor"] = f"{MONITOR_SINK}.monitor"
        devices["master:stream"] = f"{STREAM_SINK}.monitor"
        try:
            self.peak_meter.start(devices)
        except Exception:
            # Metering is optional — volume control must keep working
            pass

    def get_channel_volume(self, channel_key: str, mix: str) -> float:
        key = self._vol_key(channel_key, mix)
        return float(self.settings.get("volumes", {}).get(key, 1.0))

    def get_channel_mute(self, channel_key: str, mix: str) -> bool:
        key = self._vol_key(channel_key, mix)
        if key == "mic:monitor" and key not in self.settings.get("mutes", {}):
            return True
        return bool(self.settings.get("mutes", {}).get(key, False))

    def get_channel_color(self, channel_key: str) -> str:
        custom = (self.settings.get("colors") or {}).get(channel_key)
        if custom:
            return custom
        ch = next((c for c in CHANNELS if c.key == channel_key), None)
        return ch.accent if ch else "#8B9BB4"

    def set_channel_color(self, channel_key: str, color: str) -> None:
        color = (color or "").strip()
        if not color.startswith("#"):
            color = f"#{color}"
        if len(color) not in (4, 7, 9):
            return
        self.settings.setdefault("colors", {})[channel_key] = color.upper() if len(color) != 4 else color
        # normalize short form later via UI; store as provided
        self.settings["colors"][channel_key] = color
        app_config.save(self.settings)
        self.notify()

    def get_sidebar_width(self) -> int:
        try:
            return int((self.settings.get("ui") or {}).get("sidebar_width", 280))
        except (TypeError, ValueError):
            return 280

    def set_sidebar_width(self, width: int) -> None:
        width = max(180, min(600, int(width)))
        self.settings.setdefault("ui", {})["sidebar_width"] = width
        app_config.save(self.settings)

    def set_channel_volume(self, channel_key: str, mix: str, value: float) -> None:
        value = max(0.0, min(self.MAX_VOLUME, float(value)))
        self.settings.setdefault("volumes", {})[self._vol_key(channel_key, mix)] = value
        app_config.save(self.settings)
        try:
            self._apply_loopback_volume(
                channel_key, mix, value, self.get_channel_mute(channel_key, mix)
            )
        except Exception:
            # Never let Pulse threading errors kill the API/UI thread
            pass

    def set_channel_mute(self, channel_key: str, mix: str, muted: bool) -> None:
        self.settings.setdefault("mutes", {})[self._vol_key(channel_key, mix)] = muted
        app_config.save(self.settings)

        # Mic → Monitor: hard-stop loopback when muted (volume mute alone was unreliable)
        if channel_key == "mic" and mix == "monitor":
            name = "wavelink_mic_to_monitor"
            if muted:
                self._kill_named_loopback(name)
            else:
                if name not in self._loopbacks:
                    self._spawn_loopback(
                        name,
                        MIC_CHANNEL.sink_name,
                        MONITOR_SINK,
                        capture_from_sink=True,
                    )
                    time.sleep(0.2)
                    self._apply_loopback_volume(
                        channel_key,
                        mix,
                        self.get_channel_volume(channel_key, mix),
                        False,
                    )
            return

        self._apply_loopback_volume(
            channel_key, mix, self.get_channel_volume(channel_key, mix), muted
        )

    def _find_loopback_input(self, loopback_name: str):
        needle = f"output.{loopback_name}"
        with self._pulse_lock:
            for i in self.pulse.sink_input_list():
                node = i.proplist.get("node.name", "")
                if node == needle or i.name == loopback_name or loopback_name in node:
                    return i
        return None

    def _apply_loopback_volume(
        self, channel_key: str, mix: str, volume: float, muted: bool
    ) -> None:
        name = f"wavelink_{channel_key}_to_{mix}"
        with self._pulse_lock:
            inp = None
            needle = f"output.{name}"
            try:
                for i in self.pulse.sink_input_list():
                    node = i.proplist.get("node.name", "")
                    if node == needle or i.name == name or name in node:
                        inp = i
                        break
            except Exception:
                inp = None
            if inp is None:
                return
            try:
                self.pulse.volume_set_all_chans(inp, 0.0 if muted else volume)
                self.pulse.mute(inp, muted)
            except Exception:
                pass

    def apply_saved_levels(self) -> None:
        for ch in CHANNELS:
            for mix in ("monitor", "stream"):
                self._apply_loopback_volume(
                    ch.key,
                    mix,
                    self.get_channel_volume(ch.key, mix),
                    self.get_channel_mute(ch.key, mix),
                )
        # Master mix volumes
        for sink_name, key in ((MONITOR_SINK, "master:monitor"), (STREAM_SINK, "master:stream")):
            sink = self.sink_by_name(sink_name)
            if not sink:
                continue
            vol = float(self.settings.get("volumes", {}).get(key, 1.0))
            muted = bool(self.settings.get("mutes", {}).get(key, False))
            try:
                self.pulse.volume_set_all_chans(sink, 0.0 if muted else vol)
                self.pulse.mute(sink, muted)
            except Exception:
                pass

    def set_master_volume(self, mix: str, value: float) -> None:
        value = max(0.0, min(self.MAX_VOLUME, float(value)))
        key = f"master:{mix}"
        self.settings.setdefault("volumes", {})[key] = value
        app_config.save(self.settings)
        sink_name = MONITOR_SINK if mix == "monitor" else STREAM_SINK
        sink = self.sink_by_name(sink_name)
        if sink:
            muted = self.get_master_mute(mix)
            try:
                self.pulse.volume_set_all_chans(sink, 0.0 if muted else value)
            except Exception:
                pass

    def get_master_volume(self, mix: str) -> float:
        return float(self.settings.get("volumes", {}).get(f"master:{mix}", 1.0))

    def set_master_mute(self, mix: str, muted: bool) -> None:
        self.settings.setdefault("mutes", {})[f"master:{mix}"] = muted
        app_config.save(self.settings)
        sink_name = MONITOR_SINK if mix == "monitor" else STREAM_SINK
        sink = self.sink_by_name(sink_name)
        if sink:
            try:
                self.pulse.mute(sink, muted)
                if not muted:
                    self.pulse.volume_set_all_chans(sink, self.get_master_volume(mix))
            except Exception:
                pass

    def get_master_mute(self, mix: str) -> bool:
        return bool(self.settings.get("mutes", {}).get(f"master:{mix}", False))

    def stream_source_name(self) -> str:
        return f"{STREAM_SINK}.monitor"

    def mic_source_name(self) -> str:
        """Clean mic-only source for Discord / voice chat (no desktop)."""
        return MIC_SOURCE_NAME

    def _pick_preferred_sink(self) -> str:
        sinks = self.hardware_sinks()
        if not sinks:
            return self._default_sink_name()
        preferred = ("blackshark", "headset", "headphone", "razr", "razer", "hyperx")
        lower = [(s, s.description.lower() + " " + s.name.lower()) for s in sinks]
        for key in preferred:
            for s, text in lower:
                if key in text and "quadcast" not in text:
                    return s.name
        default = self._default_sink_name()
        if default and any(s.name == default for s in sinks):
            return default
        return sinks[0].name

    def _pick_preferred_source(self) -> str:
        sources = self.hardware_sources()
        if not sources:
            return self._default_source_name()
        preferred = ("quadcast", "wave", "microphone", "hyperx", "mic")
        lower = [(s, s.description.lower() + " " + s.name.lower()) for s in sources]
        for key in preferred:
            for s, text in lower:
                if key in text:
                    return s.name
        default = self._default_source_name()
        if default and any(s.name == default for s in sources):
            return default
        return sources[0].name

    def bootstrap(self) -> None:
        self.connect()
        self.ensure_sinks()
        if not self.settings.get("monitor_device"):
            self.settings["monitor_device"] = self._pick_preferred_sink()
        if not self.settings.get("mic_device"):
            self.settings["mic_device"] = self._pick_preferred_source()
        # Ensure mic sidetone is off by default
        self.settings.setdefault("mutes", {}).setdefault("mic:monitor", True)
        app_config.save(self.settings)
        self.start_loopbacks()
        self.apply_assignments()
        self.start_peak_meters()
