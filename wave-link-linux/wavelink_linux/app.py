from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, GObject, Gtk, Pango

from . import __version__
from .api_server import WaveLinkApiServer
from .audio import AudioEngine
from .channels import CHANNELS, MIC_CHANNEL, SINK_CHANNELS


APP_ID = "com.wavelink.linux"
DND_MIME = "application/x-wavelink-app"


class AppChip(Gtk.Box):
    def __init__(self, assign_key: str, label: str, icon_name: str, is_live: bool = True):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.assign_key = assign_key
        self.add_css_class("app-chip")
        if not is_live:
            self.add_css_class("app-chip-idle")
        self.set_margin_top(2)
        self.set_margin_bottom(2)

        icon = Gtk.Image.new_from_icon_name(icon_name or "audio-x-generic")
        icon.set_pixel_size(16)
        name = Gtk.Label(label=label, xalign=0.0, hexpand=True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.add_css_class("caption")

        self.append(icon)
        self.append(name)

        drag = Gtk.DragSource()
        drag.set_actions(Gdk.DragAction.MOVE)
        drag.connect("prepare", self._on_prepare)
        drag.connect("drag-begin", self._on_drag_begin)
        self.add_controller(drag)

    def _on_prepare(self, _source, _x, _y):
        value = GObject.Value(GObject.TYPE_STRING, self.assign_key)
        return Gdk.ContentProvider.new_for_value(value)

    def _on_drag_begin(self, source, _drag):
        paintable = Gtk.WidgetPaintable.new(self)
        source.set_icon(paintable, 0, 0)


class DropZone(Gtk.Box):
    __gsignals__ = {
        "app-dropped": (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, placeholder: str = "Apps hierher ziehen"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("drop-zone")
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_size_request(-1, 88)

        self._placeholder = Gtk.Label(label=placeholder)
        self._placeholder.add_css_class("dim-label")
        self._placeholder.add_css_class("caption")
        self._placeholder.set_wrap(True)
        self.append(self._placeholder)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(60)
        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scrolled.set_child(self._list)
        self.append(scrolled)

        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop)
        drop.connect("enter", self._on_enter)
        drop.connect("leave", self._on_leave)
        self.add_controller(drop)

    def set_apps(self, chips: list[AppChip]) -> None:
        child = self._list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt
        self._placeholder.set_visible(not chips)
        for chip in chips:
            self._list.append(chip)

    def _on_drop(self, _target, value, _x, _y):
        if not value:
            return False
        self.emit("app-dropped", str(value))
        return True

    def _on_enter(self, _target, _x, _y):
        self.add_css_class("drop-hover")
        return Gdk.DragAction.MOVE

    def _on_leave(self, _target):
        self.remove_css_class("drop-hover")


class VuMeter(Gtk.DrawingArea):
    """Vertical peak meter with hold marker (sensitive dB-mapped 0..1)."""

    def __init__(self):
        super().__init__()
        self.peak = 0.0
        self.hold = 0.0
        self.signal = False
        self.set_content_width(14)
        self.set_hexpand(False)
        self.set_vexpand(True)
        self.set_size_request(14, 140)
        self.set_draw_func(self._draw)
        self.set_tooltip_text("Audio-Pegel der Spur")

    def set_levels(self, peak: float, hold: float, signal: bool = False) -> None:
        peak = max(0.0, min(1.0, float(peak)))
        hold = max(0.0, min(1.0, float(hold)))
        if (
            abs(peak - self.peak) < 0.008
            and abs(hold - self.hold) < 0.008
            and signal == self.signal
        ):
            return
        self.peak = peak
        self.hold = hold
        self.signal = signal
        self.queue_draw()

    def _color_for(self, level: float) -> tuple[float, float, float]:
        if level >= 0.92:
            return (0.92, 0.28, 0.28)
        if level >= 0.72:
            return (0.95, 0.78, 0.22)
        if self.signal or level > 0.04:
            return (0.30, 0.85, 0.72)
        return (0.35, 0.40, 0.45)

    def _draw(self, _area, cr, width: int, height: int) -> None:
        # Track
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.45)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.rectangle(0.5, 0.5, width - 1, height - 1)
        cr.stroke()

        # Segmented fill from bottom
        fill_h = int(height * self.peak)
        if fill_h > 0:
            y0 = height - fill_h
            # draw in 3 color bands
            bands = (
                (0.0, 0.72, (0.30, 0.85, 0.72)),
                (0.72, 0.92, (0.95, 0.78, 0.22)),
                (0.92, 1.01, (0.92, 0.28, 0.28)),
            )
            for lo, hi, color in bands:
                a = max(lo, 0.0)
                b = min(hi, self.peak)
                if b <= a:
                    continue
                y_bot = height - int(height * a)
                y_top = height - int(height * b)
                cr.set_source_rgb(*color)
                cr.rectangle(2, y_top, width - 4, max(1, y_bot - y_top))
                cr.fill()

        # Peak-hold tick
        if self.hold > 0.02:
            y = height - int(height * self.hold)
            y = max(1, min(height - 2, y))
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
            cr.rectangle(1, y, width - 2, 2)
            cr.fill()


class ChannelStrip(Gtk.Box):
    def __init__(self, engine: AudioEngine, channel_key: str, title: str, accent: str, is_mic: bool):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.engine = engine
        self.channel_key = channel_key
        self.is_mic = is_mic
        self._accent_css = None
        self.add_css_class("channel-strip")
        self.set_size_request(148, -1)

        self.accent_bar = Gtk.Box()
        self.accent_bar.set_size_request(-1, 6)
        self.accent_bar.add_css_class("accent-bar")
        self.accent_bar.set_name(f"accent-{channel_key}")
        self.accent_bar.set_tooltip_text("Farbe ändern")
        self.append(self.accent_bar)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title_lbl = Gtk.Label(label=title, hexpand=True, xalign=0.0)
        title_lbl.add_css_class("heading")
        title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        title_row.append(title_lbl)

        self.color_btn = Gtk.ColorDialogButton()
        self.color_btn.set_dialog(Gtk.ColorDialog(title=f"Farbe: {title}"))
        self.color_btn.set_tooltip_text("Spurfarbe")
        self.color_btn.set_size_request(28, 28)
        title_row.append(self.color_btn)
        self.append(title_row)

        self.drop = DropZone("Mic-Gerät wählen" if is_mic else "Apps droppen")
        self.drop.connect("app-dropped", self._on_dropped)
        self.append(self.drop)

        self.vu = VuMeter()
        self.mon_scale = self._make_scale("Monitor")
        self.str_scale = self._make_scale("Stream")
        faders = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        faders.set_vexpand(True)
        faders.set_homogeneous(False)
        vu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vu_lbl = Gtk.Label(label="VU")
        vu_lbl.add_css_class("caption")
        vu_lbl.add_css_class("dim-label")
        vu_box.append(vu_lbl)
        vu_box.append(self.vu)
        faders.append(vu_box)
        faders.append(self.mon_scale["box"])
        faders.append(self.str_scale["box"])
        self.mon_scale["box"].set_hexpand(True)
        self.str_scale["box"].set_hexpand(True)
        self.append(faders)

        self.mon_mute = Gtk.ToggleButton(label="M")
        self.mon_mute.set_tooltip_text("Monitor stumm")
        self.str_mute = Gtk.ToggleButton(label="S")
        self.str_mute.set_tooltip_text("Stream stumm")
        for btn in (self.mon_mute, self.str_mute):
            btn.add_css_class("circular")
            btn.add_css_class("flat")
        mute_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER)
        mute_row.append(self.mon_mute)
        mute_row.append(self.str_mute)
        self.append(mute_row)

        self._syncing_color = False
        self._load_levels()
        self.mon_scale["adj"].connect("value-changed", self._on_mon_vol)
        self.str_scale["adj"].connect("value-changed", self._on_str_vol)
        self.mon_mute.connect("toggled", self._on_mon_mute)
        self.str_mute.connect("toggled", self._on_str_mute)
        self.color_btn.connect("notify::rgba", self._on_color_changed)
        self.apply_accent(self.engine.get_channel_color(channel_key) or accent)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_accent_clicked)
        self.accent_bar.add_controller(click)

    def apply_accent(self, accent: str) -> None:
        rgba = Gdk.RGBA()
        if not rgba.parse(accent):
            rgba.parse("#8B9BB4")
            accent = "#8B9BB4"
        self._syncing_color = True
        self.color_btn.set_rgba(rgba)
        self._syncing_color = False

        css = Gtk.CssProvider()
        css.load_from_data(
            (
                f"#accent-{self.channel_key} {{"
                f" background: {accent}; border-radius: 3px; }}"
            ).encode()
        )
        display = Gdk.Display.get_default()
        if self._accent_css is not None:
            Gtk.StyleContext.remove_provider_for_display(display, self._accent_css)
        Gtk.StyleContext.add_provider_for_display(
            display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._accent_css = css

    def _rgba_to_hex(self, rgba: Gdk.RGBA) -> str:
        r = int(round(rgba.red * 255))
        g = int(round(rgba.green * 255))
        b = int(round(rgba.blue * 255))
        return f"#{r:02X}{g:02X}{b:02X}"

    def _on_color_changed(self, button, _pspec):
        if self._syncing_color:
            return
        color = self._rgba_to_hex(button.get_rgba())
        self.engine.set_channel_color(self.channel_key, color)
        self.apply_accent(color)

    def _on_accent_clicked(self, *_args):
        dialog = self.color_btn.get_dialog() or Gtk.ColorDialog(
            title=f"Farbe: {self.channel_key}"
        )
        dialog.choose(self.get_root(), None, self._on_accent_dialog_done)

    def _on_accent_dialog_done(self, dialog, result):
        try:
            rgba = dialog.choose_finish(result)
        except GLib.Error:
            return
        if rgba is None:
            return
        color = self._rgba_to_hex(rgba)
        self.engine.set_channel_color(self.channel_key, color)
        self.apply_accent(color)

    def _make_scale(self, label: str) -> dict:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("caption")
        lbl.add_css_class("dim-label")
        adj = Gtk.Adjustment(lower=0, upper=2.0, step_increment=0.01, page_increment=0.1, value=1.0)
        scale = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL, adjustment=adj)
        scale.set_vexpand(True)
        scale.set_draw_value(False)
        scale.set_inverted(True)
        scale.set_size_request(-1, 140)
        box.append(lbl)
        box.append(scale)
        return {"box": box, "adj": adj, "scale": scale}

    def _load_levels(self) -> None:
        self.mon_scale["adj"].set_value(self.engine.get_channel_volume(self.channel_key, "monitor"))
        self.str_scale["adj"].set_value(self.engine.get_channel_volume(self.channel_key, "stream"))
        self.mon_mute.set_active(self.engine.get_channel_mute(self.channel_key, "monitor"))
        self.str_mute.set_active(self.engine.get_channel_mute(self.channel_key, "stream"))

    def _on_mon_vol(self, adj):
        self.engine.set_channel_volume(self.channel_key, "monitor", adj.get_value())

    def _on_str_vol(self, adj):
        self.engine.set_channel_volume(self.channel_key, "stream", adj.get_value())

    def _on_mon_mute(self, btn):
        self.engine.set_channel_mute(self.channel_key, "monitor", btn.get_active())

    def _on_str_mute(self, btn):
        self.engine.set_channel_mute(self.channel_key, "stream", btn.get_active())

    def _on_dropped(self, _zone, assign_key: str):
        if self.is_mic:
            return
        self.engine.move_app_key(assign_key, self.channel_key)

    def refresh_apps(self, apps) -> None:
        if self.is_mic:
            mic = self.engine.settings.get("mic_device") or "Standard-Mikrofon"
            self.drop.set_apps([])
            short = mic.split(".")[-1][:28]
            mon_muted = self.engine.get_channel_mute("mic", "monitor")
            hint = f"{short}\n(Headset-Monitor aus)" if mon_muted else short
            self.drop._placeholder.set_label(hint)
            self.drop._placeholder.set_visible(True)
            return
        chips = []
        for app in apps:
            assigned = self.engine.assigned_channel(app)
            if assigned == self.channel_key:
                chips.append(
                    AppChip(app.key, app.label, app.icon_name, is_live=app.is_live)
                )
        self.drop.set_apps(chips)

    def refresh_meter(self) -> None:
        # Post-fader: take the louder of Monitor/Stream (signal × software volume)
        mon = self.engine.get_channel_peak(self.channel_key, "monitor")
        st = self.engine.get_channel_peak(self.channel_key, "stream")
        peak = max(float(mon.get("peak", 0.0) or 0.0), float(st.get("peak", 0.0) or 0.0))
        hold = max(
            float(mon.get("peak_hold", 0.0) or 0.0),
            float(st.get("peak_hold", 0.0) or 0.0),
        )
        signal = bool(mon.get("signal") or st.get("signal"))
        self.vu.set_levels(peak, hold, signal)


class WaveLinkWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, engine: AudioEngine):
        super().__init__(application=app, title="WaveLink Linux")
        self.engine = engine
        self.set_default_size(1280, 720)
        self.set_size_request(960, 560)

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window {
                background: linear-gradient(160deg, #1a1f27 0%, #12151b 55%, #0e1514 100%);
            }
            .channel-strip {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
                padding: 10px;
                margin: 4px;
            }
            .drop-zone {
                background: rgba(0,0,0,0.25);
                border: 1px dashed rgba(255,255,255,0.18);
                border-radius: 8px;
                padding: 6px;
            }
            .drop-zone.drop-hover {
                border-color: #4ECDC4;
                background: rgba(78,205,196,0.12);
            }
            .app-chip {
                background: rgba(255,255,255,0.08);
                border-radius: 6px;
                padding: 4px 6px;
            }
            .app-chip-idle {
                opacity: 0.75;
                border: 1px dashed rgba(255,255,255,0.15);
            }
            .pool-panel {
                background: rgba(255,255,255,0.03);
                padding: 12px;
            }
            paned > separator {
                background: rgba(255,255,255,0.12);
                min-width: 6px;
            }
            paned > separator:hover {
                background: rgba(78,205,196,0.45);
            }
            .accent-bar {
                cursor: pointer;
            }
            .footer-bar {
                background: rgba(0,0,0,0.35);
                border-top: 1px solid rgba(255,255,255,0.06);
                padding: 10px 16px;
            }
            .brand {
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            .hint {
                opacity: 0.7;
            }
            .vu-meter {
                min-width: 14px;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="WaveLink Linux", css_classes=["brand"]))
        root.append(header)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_hexpand(True)
        paned.set_vexpand(True)
        paned.set_wide_handle(True)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)
        paned.set_resize_end_child(True)
        paned.set_shrink_end_child(False)
        root.append(paned)
        self._paned = paned
        self._saving_sidebar = False

        # Left: unassigned apps
        pool = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pool.add_css_class("pool-panel")
        pool.set_size_request(180, -1)
        pool_title = Gtk.Label(label="Programme", xalign=0.0, css_classes=["heading"])
        pool_hint = Gtk.Label(
            label="Ziehen · Trenner verschieben für mehr Platz",
            xalign=0.0,
            css_classes=["caption", "hint"],
        )
        self.pool_zone = DropZone("Keine offenen Apps")
        self.pool_zone.connect("app-dropped", self._on_pool_drop)
        pool.append(pool_title)
        pool.append(pool_hint)
        pool.append(self.pool_zone)
        paned.set_start_child(pool)

        # Channels
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.channel_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.channel_box.set_margin_start(8)
        self.channel_box.set_margin_end(8)
        self.channel_box.set_margin_top(10)
        self.channel_box.set_margin_bottom(10)
        scroll.set_child(self.channel_box)
        paned.set_end_child(scroll)

        self.strips: dict[str, ChannelStrip] = {}
        for ch in CHANNELS:
            color = engine.get_channel_color(ch.key)
            strip = ChannelStrip(engine, ch.key, ch.title, color, ch.is_mic)
            self.strips[ch.key] = strip
            self.channel_box.append(strip)

        # Restore sidebar width after first layout pass
        saved_width = engine.get_sidebar_width()
        GLib.idle_add(self._apply_sidebar_width, saved_width)
        paned.connect("notify::position", self._on_sidebar_moved)

        # Footer: devices + masters
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        footer.add_css_class("footer-bar")
        root.append(footer)

        self.monitor_combo = Gtk.DropDown()
        self.mic_combo = Gtk.DropDown()
        self._fill_devices()

        mon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        mon_box.append(Gtk.Label(label="Monitor-Ausgang", xalign=0.0, css_classes=["caption"]))
        mon_box.append(self.monitor_combo)
        footer.append(mon_box)

        mic_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        mic_box.append(Gtk.Label(label="Mikrofon", xalign=0.0, css_classes=["caption"]))
        mic_box.append(self.mic_combo)
        footer.append(mic_box)

        footer.append(Gtk.Box(hexpand=True))

        self.master_mon = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 2.0, 0.01)
        self.master_str = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 2.0, 0.01)
        for scale, mix in ((self.master_mon, "monitor"), (self.master_str, "stream")):
            scale.set_value(self.engine.get_master_volume(mix))
            scale.set_draw_value(True)
            scale.set_value_pos(Gtk.PositionType.RIGHT)
            scale.set_size_request(160, -1)

        mm = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        mm.append(Gtk.Label(label="Monitor Mix", xalign=0.0, css_classes=["caption"]))
        mm.append(self.master_mon)
        footer.append(mm)

        sm = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sm_label = Gtk.Label(label="Stream Mix → OBS", xalign=0.0, css_classes=["caption"])
        sm.append(sm_label)
        sm.append(self.master_str)
        footer.append(sm)

        help_btn = Gtk.Button(label="OBS-Tipp", css_classes=["flat"])
        help_btn.connect("clicked", self._show_obs_tip)
        footer.append(help_btn)

        self.monitor_combo.connect("notify::selected", self._on_monitor_selected)
        self.mic_combo.connect("notify::selected", self._on_mic_selected)
        self.master_mon.connect("value-changed", lambda s: self.engine.set_master_volume("monitor", s.get_value()))
        self.master_str.connect("value-changed", lambda s: self.engine.set_master_volume("stream", s.get_value()))

        self.refresh()
        GLib.timeout_add_seconds(2, self._tick)
        GLib.timeout_add(50, self._meter_tick)

    def _apply_sidebar_width(self, width: int) -> bool:
        width = max(180, min(600, int(width)))
        self._saving_sidebar = True
        self._paned.set_position(width)
        self._saving_sidebar = False
        return False

    def _on_sidebar_moved(self, paned, _pspec) -> None:
        if self._saving_sidebar:
            return
        pos = paned.get_position()
        if pos > 0:
            self.engine.set_sidebar_width(pos)

    def _fill_devices(self) -> None:
        sinks = self.engine.hardware_sinks()
        sources = self.engine.hardware_sources()
        sink_names = [s.description for s in sinks]
        source_names = [s.description for s in sources]
        self._sinks = sinks
        self._sources = sources
        self.monitor_combo.set_model(Gtk.StringList.new(sink_names or ["Kein Gerät"]))
        self.mic_combo.set_model(Gtk.StringList.new(source_names or ["Kein Gerät"]))

        mon = self.engine.settings.get("monitor_device")
        if mon:
            for i, s in enumerate(sinks):
                if s.name == mon:
                    self.monitor_combo.set_selected(i)
                    break
        mic = self.engine.settings.get("mic_device")
        if mic:
            for i, s in enumerate(sources):
                if s.name == mic:
                    self.mic_combo.set_selected(i)
                    break

    def _on_monitor_selected(self, combo, _pspec):
        idx = combo.get_selected()
        if 0 <= idx < len(self._sinks):
            self.engine.set_monitor_device(self._sinks[idx].name)

    def _on_mic_selected(self, combo, _pspec):
        idx = combo.get_selected()
        if 0 <= idx < len(self._sources):
            self.engine.set_mic_device(self._sources[idx].name)
            self.strips[MIC_CHANNEL.key].refresh_apps([])

    def _on_pool_drop(self, _zone, assign_key: str):
        self.engine.unassign_app_key(assign_key)

    def _show_obs_tip(self, _btn):
        dialog = Adw.MessageDialog.new(
            self,
            "Discord & OBS",
            "Discord → Stimme & Video:\n\n"
            "• Mikrofon: „Monitor of WaveLink Microphone“\n"
            "  (nur Mic — KEIN Stream Mix, sonst hörst du Desktop)\n"
            "• Lautsprecher: „WaveLink Voice Chat“\n\n"
            f"Discord-Mic: {self.engine.mic_source_name()}\n"
            f"OBS-Mix: {self.engine.stream_source_name()}\n\n"
            "Selbsthören: Mic-Spur → Monitor „M“ (standardmäßig aus).\n"
            "QuadCast-Kopfhörer-Buchse wird stummgeschaltet (kein Desktop-Bleed).",
        )
        dialog.add_response("ok", "Verstanden")
        dialog.present()

    def refresh(self) -> None:
        apps = self.engine.list_apps()
        pool_chips = []
        for app in apps:
            assigned = self.engine.assigned_channel(app)
            if assigned:
                continue
            pool_chips.append(
                AppChip(app.key, app.label, app.icon_name, is_live=app.is_live)
            )
        self.pool_zone.set_apps(pool_chips)
        for key, strip in self.strips.items():
            strip.refresh_apps(apps)

    def _tick(self) -> bool:
        try:
            self.engine.maintain_routing()
            self.refresh()
        except Exception:
            pass
        return True

    def _meter_tick(self) -> bool:
        try:
            for strip in self.strips.values():
                strip.refresh_meter()
        except Exception:
            pass
        return True


class WaveLinkApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)
        self.engine = AudioEngine()
        self.api: WaveLinkApiServer | None = None

    def do_activate(self):
        try:
            self.engine.bootstrap()
            if self.api is None:
                self.api = WaveLinkApiServer(self.engine)
                self.api.start()
        except Exception as exc:
            win = Adw.ApplicationWindow(application=self, title="WaveLink Linux")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(24)
            box.set_margin_bottom(24)
            box.set_margin_start(24)
            box.set_margin_end(24)
            box.append(Gtk.Label(label="PipeWire-Verbindung fehlgeschlagen"))
            box.append(Gtk.Label(label=str(exc), wrap=True))
            win.set_content(box)
            win.present()
            return

        win = self.props.active_window
        if not win:
            win = WaveLinkWindow(self, self.engine)
        win.present()

    def do_shutdown(self):
        if self.api is not None:
            self.api.stop()
            self.api = None
        self.engine.close()
        Adw.Application.do_shutdown(self)


def main(argv: list[str] | None = None) -> int:
    from .pipewire_setup import ensure_pipewire

    try:
        ensure_pipewire(lambda message: print(message, flush=True))
    except (OSError, FileNotFoundError) as exc:
        print(f"PipeWire-Setup nicht angewendet: {exc}", file=sys.stderr)
    Adw.init()
    app = WaveLinkApp()
    return app.run(argv or sys.argv)
