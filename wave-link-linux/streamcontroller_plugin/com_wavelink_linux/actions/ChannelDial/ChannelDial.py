from __future__ import annotations

import os
import threading
import time

from PIL import Image, ImageDraw, ImageFont
from loguru import logger as log

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from src.backend.DeckManagement.InputIdentifier import Input, InputEvent
from src.backend.PluginManager.ActionBase import ActionBase

from wl_api import WaveLinkClient

CHANNEL_CHOICES = [
    ("music", "Music"),
    ("voice", "Voice Chat"),
    ("game", "Game"),
    ("browser", "Browser"),
    ("system", "System"),
    ("sfx", "SFX"),
    ("aux", "Auxiliary"),
    ("mic", "Microphone"),
    ("master", "Master"),
]

MIX_CHOICES = [
    ("monitor", "Monitor"),
    ("stream", "Stream"),
]

TITLES = {k: t for k, t in CHANNEL_CHOICES}


class ChannelDial(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = WaveLinkClient()
        self.volume = 1.0
        self.muted = False
        self.max_volume = 2.0
        self.accent = "#4ECDC4"
        self.online = False
        self.peak = 0.0
        self.peak_hold = 0.0
        self.signal = False
        self._update_loop_running = False
        self._last_state = None
        self._font_cache: dict[int, ImageFont.ImageFont] = {}
        self._poll_interval = 0.12


    def on_ready(self):
        self.force_redraw()
        self.start_update_loop()

    def on_update(self):
        # Called on page (re)load — must redraw even if volume unchanged
        self.force_redraw()
        self.start_update_loop()

    def on_tick(self):
        if not self._update_loop_running and self.get_is_present():
            self.force_redraw()
            self.start_update_loop()

    def force_redraw(self):
        """Invalidate cache and push media to the deck immediately."""
        self._last_state = None
        try:
            self.refresh_state()
            self.update_ui(force=True)
        except Exception as e:
            log.error(f"WaveLink dial redraw failed: {e}")

    def start_update_loop(self):
        if self._update_loop_running:
            return
        if not self.get_is_present():
            return
        self._update_loop_running = True
        threading.Thread(
            target=self._update_loop, daemon=True, name="wavelink-dial-loop"
        ).start()

    def _update_loop(self):
        try:
            # Always paint once when (re)joining a page
            self._last_state = None
            while True:
                if not self.get_is_present():
                    break
                try:
                    self.refresh_state()
                    self.update_ui()
                except Exception as e:
                    log.debug(f"WaveLink dial update: {e}")
                time.sleep(self._poll_interval)
        finally:
            self._update_loop_running = False

    def _settings_channel(self) -> str:
        return self.get_settings().get("channel", "music")

    def _settings_mix(self) -> str:
        mix = self.get_settings().get("mix", "monitor")
        return mix if mix in ("monitor", "stream") else "monitor"

    def _settings_step(self) -> float:
        try:
            step = float(self.get_settings().get("step", 0.05))
        except (TypeError, ValueError):
            step = 0.05
        return max(0.01, min(0.25, step))

    def _parse_accent(self, hex_color: str):
        try:
            h = hex_color.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            return (r, g, b, 255)
        except Exception:
            return (78, 205, 196, 255)

    def refresh_state(self):
        data = self.client.get_channel(self._settings_channel(), self._settings_mix())
        if not data:
            self.online = False
            self.peak = 0.0
            self.peak_hold = 0.0
            self.signal = False
            return
        self.online = True
        self.volume = float(data.get("volume", 1.0))
        self.muted = bool(data.get("muted", False))
        self.max_volume = float(data.get("max_volume", 2.0)) or 2.0
        self.peak = max(0.0, min(1.0, float(data.get("peak", 0.0) or 0.0)))
        self.peak_hold = max(
            0.0, min(1.0, float(data.get("peak_hold", self.peak) or 0.0))
        )
        self.signal = bool(data.get("signal", self.peak >= 0.012))
        if data.get("accent"):
            self.accent = data["accent"]

    def _meter_color(self, level: float):
        """Green → yellow → red like a classic VU meter."""
        if self.muted or not self.online:
            return (90, 90, 90, 255)
        if level >= 0.9:
            return (230, 70, 70, 255)
        if level >= 0.7:
            return (235, 190, 60, 255)
        accent = self._parse_accent(self.accent)
        return accent

    def _draw_vu_meter(self, draw, x0, y0, x1, y1, vertical: bool = False):
        """Draw signal peak + hold marker inside a meter track."""
        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=3,
            fill=(28, 28, 32, 255),
            outline=(0, 0, 0, 200),
            width=1,
        )
        peak = self.peak
        hold = self.peak_hold
        if peak <= 0.001 and hold <= 0.001:
            return
        color = self._meter_color(peak)
        if vertical:
            h = y1 - y0
            y_fill = y1 - int(h * peak)
            if y_fill < y1:
                draw.rounded_rectangle(
                    [x0, min(y_fill, y1 - 2), x1, y1],
                    radius=2,
                    fill=color,
                )
            y_hold = y1 - int(h * hold)
            y_hold = max(y0, min(y1 - 1, y_hold))
            draw.line([(x0, y_hold), (x1, y_hold)], fill=(255, 255, 255, 220), width=1)
        else:
            w = x1 - x0
            x_fill = x0 + int(w * peak)
            if x_fill > x0:
                draw.rounded_rectangle(
                    [x0, y0, max(x0 + 2, x_fill), y1],
                    radius=2,
                    fill=color,
                )
            x_hold = x0 + int(w * hold)
            x_hold = max(x0, min(x1 - 1, x_hold))
            draw.line([(x_hold, y0), (x_hold, y1)], fill=(255, 255, 255, 220), width=1)

    def get_font(self, size: int):
        if size in self._font_cache:
            return self._font_cache[size]
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size
            )
        except Exception:
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/gnu-free/FreeSansBold.otf", size
                )
            except Exception:
                font = ImageFont.load_default()
        self._font_cache[size] = font
        return font

    def update_ui(self, force: bool = False):
        img = self.render_image(force=force)
        if img is None:
            return
        try:
            self.set_label("")
            self.set_media(image=img, size=1.0, valign=0.0, halign=0.0)
        except Exception as e:
            log.debug(f"WaveLink dial set_media: {e}")

    def render_image(self, force: bool = False):
        is_dial = isinstance(self.input_ident, Input.Dial)
        width = 200 if is_dial else 100
        height = 100

        channel = self._settings_channel()
        mix = self._settings_mix()
        title = TITLES.get(channel, channel)
        # Show as absolute % of unity (100% = 1.0)
        display_pct = int(round(self.volume * 100))
        peak_q = int(round(self.peak * 40))  # quantize to limit redraw spam
        hold_q = int(round(self.peak_hold * 40))
        state = (
            channel,
            mix,
            display_pct,
            self.muted,
            self.online,
            is_dial,
            self.accent,
            peak_q,
            hold_q,
            self.signal,
        )
        if not force and self._last_state == state:
            return None
        self._last_state = state

        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        accent = self._parse_accent(self.accent)
        if self.muted or not self.online:
            accent = (180, 70, 70, 255) if self.muted else (90, 90, 90, 255)

        font_title = self.get_font(14)
        font_pct = self.get_font(18)
        font_small = self.get_font(11)

        if is_dial:
            draw.text(
                (100, 14),
                title,
                font=font_title,
                fill=(255, 255, 255, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
                anchor="mm",
            )
            if not self.online:
                mix_label, mix_color = "OFFLINE", (255, 120, 120, 255)
            elif self.signal:
                mix_label, mix_color = f"{mix.upper()}  ●", (120, 230, 180, 255)
            else:
                mix_label, mix_color = mix.upper(), (200, 200, 200, 255)
            draw.text(
                (100, 32),
                mix_label,
                font=font_small,
                fill=mix_color,
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
                anchor="mm",
            )

            # Icon circle
            icon_name = "channel_muted.png" if self.muted else "channel.png"
            icon_path = os.path.join(self.plugin_base.PATH, "assets", icon_name)
            try:
                icon = Image.open(icon_path).convert("RGBA").resize((36, 36))
                canvas.paste(icon, (12, 52), icon)
            except Exception:
                draw.ellipse([16, 56, 48, 88], fill=accent)

            # Signal VU (audio activity on the line)
            self._draw_vu_meter(draw, 58, 48, 188, 58, vertical=False)

            # Volume fader
            x0, y0, x1, y1 = 58, 68, 158, 82
            fill_pct = max(0.0, min(1.0, self.volume / self.max_volume))
            x_fill = x0 + int((x1 - x0) * fill_pct)
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=5,
                fill=(40, 40, 40, 255),
                outline=(0, 0, 0, 255),
                width=1,
            )
            if x_fill > x0:
                draw.rounded_rectangle(
                    [x0, y0, max(x0 + 8, x_fill), y1],
                    radius=5,
                    fill=accent,
                    outline=(0, 0, 0, 255),
                    width=1,
                )
            mid = x0 + int((x1 - x0) * (1.0 / self.max_volume))
            draw.line([(mid, y0), (mid, y1)], fill=(0, 0, 0, 180), width=1)

            draw.text(
                (188, 75),
                f"{display_pct}%",
                font=font_pct,
                fill=(255, 255, 255, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
                anchor="rm",
            )

            # Side peak LED strip
            self._draw_vu_meter(draw, 190, 42, 198, 90, vertical=True)
        else:
            try:
                icon_name = "channel_muted.png" if self.muted else "channel.png"
                icon_path = os.path.join(self.plugin_base.PATH, "assets", icon_name)
                icon = Image.open(icon_path).convert("RGBA").resize((40, 40))
                canvas.paste(icon, (30, 4), icon)
            except Exception:
                draw.ellipse([30, 6, 70, 46], fill=accent)
            # Vertical VU on key
            self._draw_vu_meter(draw, 8, 8, 18, 70, vertical=True)
            draw.text(
                (50, 58),
                title[:10],
                font=font_small,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
                anchor="mm",
            )
            draw.text(
                (50, 78),
                f"{display_pct}%",
                font=font_pct,
                fill=(255, 255, 255, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
                anchor="mm",
            )
            if self.signal and self.online and not self.muted:
                draw.ellipse([78, 10, 90, 22], fill=self._meter_color(self.peak))
        return canvas

    def event_callback(self, event: InputEvent, data: dict = None):
        # Accept enum or string form (page overrides / SC versions differ)
        name = str(event)
        if event in (Input.Key.Events.DOWN, Input.Dial.Events.DOWN) or name in (
            "Key Down",
            "Dial Down",
        ):
            self._toggle_mute()
            return
        ticks = 1
        if isinstance(data, dict):
            try:
                ticks = max(1, abs(int(data.get("ticks") or data.get("steps") or 1)))
            except (TypeError, ValueError):
                ticks = 1
        if event == Input.Dial.Events.TURN_CW or name == "Dial Turn CW":
            self._adjust(+self._settings_step() * ticks)
        elif event == Input.Dial.Events.TURN_CCW or name == "Dial Turn CCW":
            self._adjust(-self._settings_step() * ticks)

    def _adjust(self, delta: float):
        result = self.client.adjust(
            self._settings_channel(), self._settings_mix(), delta
        )
        if not result:
            self.show_error()
            self.online = False
            self.update_ui()
            return
        self.online = True
        self.volume = float(result.get("volume", self.volume))
        self.muted = bool(result.get("muted", self.muted))
        self.max_volume = float(result.get("max_volume", self.max_volume)) or 2.0
        if result.get("accent"):
            self.accent = result["accent"]
        self._last_state = None
        self.update_ui()

    def _toggle_mute(self):
        result = self.client.toggle_mute(
            self._settings_channel(), self._settings_mix()
        )
        if not result:
            self.show_error()
            self.online = False
            self.update_ui()
            return
        self.online = True
        self.volume = float(result.get("volume", self.volume))
        self.muted = bool(result.get("muted", self.muted))
        self._last_state = None
        self.update_ui()

    def get_config_rows(self) -> list:
        self.channel_model = Gtk.StringList()
        for _, title in CHANNEL_CHOICES:
            self.channel_model.append(title)
        self.channel_row = Adw.ComboRow(
            model=self.channel_model,
            title=self.plugin_base.lm.get("actions.channel-dial.channel"),
        )

        self.mix_model = Gtk.StringList()
        for _, title in MIX_CHOICES:
            self.mix_model.append(title)
        self.mix_row = Adw.ComboRow(
            model=self.mix_model,
            title=self.plugin_base.lm.get("actions.channel-dial.mix"),
        )

        self.step_row = Adw.SpinRow.new_with_range(1, 25, 1)
        self.step_row.set_title(self.plugin_base.lm.get("actions.channel-dial.step"))
        self.step_row.set_subtitle("% of full scale (100% = normal)")

        self._load_config_widgets()
        self.channel_row.connect("notify::selected", self._on_cfg_changed)
        self.mix_row.connect("notify::selected", self._on_cfg_changed)
        self.step_row.connect("changed", self._on_cfg_changed)
        return [self.channel_row, self.mix_row, self.step_row]

    def _load_config_widgets(self):
        settings = self.get_settings()
        channel = settings.get("channel", "music")
        mix = settings.get("mix", "monitor")
        step = float(settings.get("step", 0.05))

        ch_idx = next(
            (i for i, (k, _) in enumerate(CHANNEL_CHOICES) if k == channel), 0
        )
        mix_idx = 0 if mix != "stream" else 1
        self.channel_row.set_selected(ch_idx)
        self.mix_row.set_selected(mix_idx)
        self.step_row.set_value(max(1, min(25, int(round(step * 100)))))

    def _on_cfg_changed(self, *args):
        settings = self.get_settings()
        ch_i = self.channel_row.get_selected()
        mix_i = self.mix_row.get_selected()
        if 0 <= ch_i < len(CHANNEL_CHOICES):
            settings["channel"] = CHANNEL_CHOICES[ch_i][0]
        if 0 <= mix_i < len(MIX_CHOICES):
            settings["mix"] = MIX_CHOICES[mix_i][0]
        settings["step"] = float(self.step_row.get_value()) / 100.0
        self.set_settings(settings)
        self._last_state = None
        self.refresh_state()
        self.update_ui()
