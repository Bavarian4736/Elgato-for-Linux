#!/usr/bin/env python3
"""HD60: Vorschau für die Elgato Game Capture HD60 S, ohne OBS.

Das Fenster zeigt das HDMI-Bild und spielt den Ton lokal ab. Solange es
offen ist, liegt der Ton am PipeWire-Gerät „HD60 S“. Mit „Discord“ wird
das Bild zusätzlich auf eine virtuelle Kamera gelegt, die Discord als
Kamera „HD60“ sieht.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gst, Gtk

APP_ID = "io.github.Bavarian4736.HD60"
LOOPBACK_NAMES = {"HD60", "OBS Virtual Camera"}
SETTINGS_VERSION = 1

Gst.init(None)


def config_file():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hd60s" / "settings.json"


def load_settings():
    defaults = {"discord": False, "hear": True, "volume": 1.0, "audio_input": 0}
    path = config_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    for key, value in defaults.items():
        data.setdefault(key, value)
    data["volume"] = max(0.0, min(1.5, float(data["volume"])))
    data["audio_input"] = 1 if int(data["audio_input"]) == 1 else 0
    data["discord"] = bool(data["discord"])
    data["hear"] = bool(data["hear"])
    return data


def save_settings(settings):
    path = config_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Einstellungen nicht gespeichert: {exc}", file=sys.stderr)


def video_devices():
    root = Path("/sys/class/video4linux")
    found = []
    if not root.is_dir():
        return found
    for node in sorted(root.glob("video*"), key=lambda item: item.name):
        try:
            name = (node / "name").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        driver = ""
        link = node / "device" / "driver"
        if link.exists():
            driver = os.path.basename(os.readlink(link))
        found.append({"path": f"/dev/{node.name}", "name": name, "driver": driver})
    return found


def find_capture(devices):
    for dev in devices:
        if dev["driver"] == "v4l2loopback" or dev["name"] in LOOPBACK_NAMES:
            continue
        if dev["driver"] == "hd60s" or "HD60 S" in dev["name"] or "Elgato" in dev["name"]:
            return dev
    return None


def find_loopback(devices):
    for dev in devices:
        if dev["driver"] == "v4l2loopback" or dev["name"] in LOOPBACK_NAMES:
            return dev
    return None


def find_audio_node():
    try:
        raw = subprocess.check_output(["pw-dump"], text=True, timeout=3)
        nodes = json.loads(raw)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    for obj in nodes:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = obj.get("info", {}).get("props", {})
        if props.get("media.class") != "Audio/Source":
            continue
        description = props.get("node.description", "")
        nick = props.get("node.nick", "")
        if "HD60" in description or "HD60" in nick:
            name = props.get("node.name")
            if name:
                return name
    return None


def set_audio_input(device, index):
    if not device or shutil_which("v4l2-ctl") is None:
        return
    subprocess.run(
        ["v4l2-ctl", "-d", device, f"--set-audio-input={index}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def shutil_which(cmd):
    from shutil import which

    return which(cmd)


def drivers_ready():
    if not Path("/sys/module/hd60s").is_dir():
        return False
    if not Path("/sys/module/v4l2loopback").is_dir():
        return False
    name = Path("/sys/class/video4linux/video10/name")
    try:
        return name.read_text(encoding="utf-8").strip() == "HD60"
    except OSError:
        return False


def install_script():
    beside = Path(__file__).resolve().parent / "install.sh"
    if beside.is_file():
        return beside
    system = Path("/usr/local/libexec/hd60s/install.sh")
    if system.is_file():
        return system
    return None


_ensure_attempted = False


def ensure_drivers():
    """Install kernel driver and v4l2loopback via pkexec when either is missing."""
    global _ensure_attempted
    if drivers_ready() or _ensure_attempted:
        return
    _ensure_attempted = True
    script = install_script()
    if script is None:
        print(
            "Kernel-Treiber oder v4l2loopback fehlt, install.sh wurde nicht gefunden.",
            file=sys.stderr,
        )
        return
    print(
        "Kernel-Treiber oder virtuelle Kamera fehlt. Installation über pkexec …",
        file=sys.stderr,
    )
    if shutil_which("notify-send"):
        subprocess.run(
            [
                "notify-send",
                "--app-name=HD60",
                "HD60",
                "Treiber fehlt. Im folgenden Fenster das Passwort eingeben.",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if shutil_which("pkexec") is None:
        print("pkexec fehlt. capture-card/install.sh ausführen.", file=sys.stderr)
        return
    subprocess.run(["pkexec", "/bin/bash", str(script), "--ensure"], check=False)


def make_element(factory, name):
    element = Gst.ElementFactory.make(factory, name)
    if element is None:
        raise RuntimeError(f"GStreamer-Element fehlt: {factory}")
    return element


class Hd60Window(Adw.ApplicationWindow):
    def __init__(self, app, settings):
        super().__init__(application=app, title="HD60")
        self.settings = settings
        self.video = None
        self.audio = None
        self.volume = None
        self.capture = None
        self.stopping = False
        self.closing = False
        self._guard = False
        self.audio_tries = 0
        self.last_notice = None

        self.set_default_size(1100, 680)
        self.connect("close-request", self.on_close)

        self.toast = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        self.toast.set_child(toolbar)
        self.set_content(self.toast)

        title = Adw.WindowTitle(title="HD60", subtitle="Elgato HD60 S")
        header = Adw.HeaderBar()
        header.set_title_widget(title)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Erneut verbinden")
        refresh.connect("clicked", lambda *_: self.start())
        header.pack_start(refresh)
        about = Gtk.Button(icon_name="help-about-symbolic", tooltip_text="Info")
        about.connect("clicked", self.on_about)
        header.pack_end(about)
        toolbar.add_top_bar(header)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        toolbar.set_content(self.stack)

        self.status_page = Adw.StatusPage(
            icon_name="video-display-symbolic",
            title="Keine HD60 S gefunden",
            description=(
                "Stecke die Karte an einen USB-3-Anschluss und schließe HDMI an."
            ),
        )
        retry = Gtk.Button(label="Erneut suchen")
        retry.set_halign(Gtk.Align.CENTER)
        retry.add_css_class("pill")
        retry.connect("clicked", lambda *_: self.start())
        self.status_page.set_child(retry)
        self.stack.add_named(self.status_page, "empty")

        video_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.picture = Gtk.Picture()
        self.picture.set_hexpand(True)
        self.picture.set_vexpand(True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.add_css_class("video-frame")
        self.picture.set_can_shrink(True)
        video_page.append(self.picture)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar.set_margin_start(12)
        bar.set_margin_end(12)
        bar.set_margin_top(8)
        bar.set_margin_bottom(8)
        self.status = Gtk.Label(label="Warte auf HDMI-Signal", xalign=0)
        self.status.set_hexpand(True)
        bar.append(self.status)

        self.input_drop = Gtk.DropDown(model=Gtk.StringList.new(["HDMI", "Klinke"]))
        self.input_drop.set_selected(self.settings["audio_input"])
        self.input_drop.connect("notify::selected", self.on_audio_input)
        bar.append(self.input_drop)

        self.hear_btn = Gtk.ToggleButton(icon_name="audio-volume-high-symbolic")
        self.hear_btn.set_tooltip_text("Ton hier abspielen")
        self.hear_btn.set_active(self.settings["hear"])
        self.hear_btn.connect("toggled", self.on_hear)
        bar.append(self.hear_btn)

        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1.5, 0.05)
        self.scale.set_draw_value(False)
        self.scale.set_size_request(140, -1)
        self.scale.set_value(self.settings["volume"])
        self.scale.connect("value-changed", self.on_volume)
        bar.append(self.scale)

        self.discord_btn = Gtk.ToggleButton(label="Discord")
        self.discord_btn.set_tooltip_text(
            "Bild an Discord senden. In Discord Kamera „HD60“ und Eingabegerät „HD60 S“ wählen."
        )
        self.discord_btn.set_active(self.settings["discord"])
        self.discord_btn.connect("toggled", self.on_discord)
        bar.append(self.discord_btn)
        video_page.append(bar)
        self.stack.add_named(video_page, "video")

        css = Gtk.CssProvider()
        css.load_from_string(".video-frame { background: black; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._sync_hear_icon()
        self._sync_discord_style()
        GLib.timeout_add_seconds(2, self.tick)
        GLib.idle_add(self.start)

    def on_about(self, *_args):
        dialog = Adw.AboutDialog()
        dialog.set_application_name("HD60")
        dialog.set_application_icon("hd60s")
        dialog.set_developer_name("Bavarian4736")
        dialog.set_version("1.0.0")
        dialog.set_comments("Bild und Ton der Elgato Game Capture HD60 S, ohne OBS.")
        dialog.set_website("https://github.com/Bavarian4736/studio")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.present(self)

    def on_close(self, *_args):
        self.closing = True
        self.stop_audio()
        self.stop_video()
        return False

    def tick(self):
        if self.closing:
            return False
        if self.video is None:
            self.start()
        elif self.capture and not Path(self.capture["path"]).exists():
            self.stop_audio()
            self.stop_video()
            self.capture = None
            self.show_empty(
                "Keine HD60 S gefunden",
                "Die Karte wurde getrennt. Stecke sie wieder an einen USB-3-Anschluss.",
            )
        elif self.settings["hear"] and self.audio is None:
            self.try_audio()
        elif not self.settings["hear"] and self.audio is not None:
            self.stop_audio()
        return True

    def show_empty(self, title, description):
        self.status_page.set_title(title)
        self.status_page.set_description(description)
        self.stack.set_visible_child_name("empty")

    def show_toast(self, text):
        if text == self.last_notice:
            return
        self.last_notice = text
        self.toast.add_toast(Adw.Toast(title=text, timeout=5))

    def start(self):
        if self.closing:
            return False
        devices = video_devices()
        capture = find_capture(devices)
        if capture is None:
            self.stop_audio()
            self.stop_video()
            self.capture = None
            if drivers_ready():
                detail = "Stecke die Karte an einen USB-3-Anschluss und schließe HDMI an."
            else:
                detail = (
                    "Der Kernel-Treiber oder die virtuelle Kamera ist nicht geladen. "
                    "hd60s installiert beides über pkexec, sobald das Passwort bestätigt wird."
                )
            self.show_empty("Keine HD60 S gefunden", detail)
            return False

        self.capture = capture
        set_audio_input(capture["path"], self.settings["audio_input"])
        try:
            self.start_video(capture, devices)
        except Exception as exc:
            self.stop_video()
            self.show_empty("Bild konnte nicht gestartet werden", str(exc))
            return False

        self.stack.set_visible_child_name("video")
        self.status.set_label("Warte auf HDMI-Signal")
        self.restart_audio()
        return False

    def start_video(self, capture, devices):
        self.stop_video()
        pipeline = Gst.Pipeline.new("hd60-video")
        src = make_element("v4l2src", "src")
        src.set_property("device", capture["path"])
        src.set_property("do-timestamp", True)
        preview_queue = make_element("queue", "preview-queue")
        self._tune_queue(preview_queue)
        convert = make_element("videoconvert", "preview-convert")
        sink = make_element("gtk4paintablesink", "view")
        sink.set_property("sync", False)
        pipeline.add(src, preview_queue, convert, sink)
        if not preview_queue.link(convert) or not convert.link(sink):
            raise RuntimeError("Vorschau konnte nicht verbunden werden.")

        if self.settings["discord"]:
            loop = find_loopback(devices)
            if loop is None:
                self._guard = True
                self.discord_btn.set_active(False)
                self._guard = False
                self.settings["discord"] = False
                save_settings(self.settings)
                self._sync_discord_style()
                self.show_toast("Virtuelle Kamera fehlt. hd60s neu starten und die Installation bestätigen.")
                if not src.link(preview_queue):
                    raise RuntimeError("Vorschau konnte nicht verbunden werden.")
            else:
                tee = make_element("tee", "tee")
                tee.set_property("allow-not-linked", True)
                discord_queue = make_element("queue", "discord-queue")
                self._tune_queue(discord_queue)
                discord_caps = make_element("capsfilter", "discord-caps")
                discord_caps.set_property("caps", Gst.Caps.from_string("video/x-raw,format=YUY2"))
                discord_sink = make_element("v4l2sink", "discord-sink")
                discord_sink.set_property("device", loop["path"])
                discord_sink.set_property("sync", False)
                discord_sink.set_property("async", False)
                pipeline.add(tee, discord_queue, discord_caps, discord_sink)
                if not src.link(tee):
                    raise RuntimeError("Bildquelle konnte nicht verbunden werden.")
                if tee.request_pad_simple("src_%u").link(preview_queue.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
                    raise RuntimeError("Vorschau konnte nicht verbunden werden.")
                if tee.request_pad_simple("src_%u").link(discord_queue.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
                    raise RuntimeError("Discord-Kamera konnte nicht verbunden werden.")
                if not discord_queue.link(discord_caps) or not discord_caps.link(discord_sink):
                    raise RuntimeError("Discord-Kamera konnte nicht verbunden werden.")
        elif not src.link(preview_queue):
            raise RuntimeError("Vorschau konnte nicht verbunden werden.")

        src_pad = src.get_static_pad("src")
        src_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_caps)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self.on_video_error)
        self.picture.set_paintable(sink.get_property("paintable"))
        self.video = pipeline
        change = pipeline.set_state(Gst.State.PLAYING)
        if change == Gst.StateChangeReturn.FAILURE:
            self.stop_video()
            raise RuntimeError(self.bus_error(pipeline) or "Die Karte lässt sich nicht öffnen.")

    def restart_audio(self):
        self.stop_audio()
        self.audio_tries = 0
        if self.settings["hear"]:
            GLib.timeout_add(400, self.try_audio)

    def try_audio(self):
        if self.closing or not self.settings["hear"] or self.video is None or self.audio is not None:
            return False
        node = find_audio_node()
        if node is None:
            self.audio_tries += 1
            if self.audio_tries == 8:
                self.show_toast("Ton der HD60 S noch nicht sichtbar. HDMI-Ton an der Quelle prüfen.")
            return False
        try:
            self.start_audio(node)
        except Exception as exc:
            self.show_toast(str(exc))
        return False

    def start_audio(self, node):
        self.stop_audio()
        pipeline = Gst.Pipeline.new("hd60-audio")
        src = make_element("pipewiresrc", "audio-src")
        src.set_property("target-object", node)
        src.set_property("client-name", "HD60")
        src.set_property("provide-clock", False)
        src.set_property("do-timestamp", True)
        queue = make_element("queue", "audio-queue")
        queue.set_property("max-size-buffers", 0)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 50 * Gst.MSECOND)
        queue.set_property("leaky", 2)
        convert = make_element("audioconvert", "audio-convert")
        resample = make_element("audioresample", "audio-resample")
        volume = make_element("volume", "volume")
        volume.set_property("volume", float(self.settings["volume"]))
        sink = make_element("pipewiresink", "audio-sink")
        sink.set_property("client-name", "HD60")
        sink.set_property("sync", False)
        pipeline.add(src, queue, convert, resample, volume, sink)
        if not (
            src.link(queue)
            and queue.link(convert)
            and convert.link(resample)
            and resample.link(volume)
            and volume.link(sink)
        ):
            raise RuntimeError("Ton konnte nicht verbunden werden.")
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self.on_audio_error)
        self.audio = pipeline
        self.volume = volume
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            message = self.bus_error(pipeline) or "Ton konnte nicht gestartet werden."
            self.stop_audio()
            raise RuntimeError(message)

    def on_caps(self, pad, info):
        event = info.get_event()
        if event is None or event.type != Gst.EventType.CAPS:
            return Gst.PadProbeReturn.OK
        caps = event.parse_caps()
        if caps is None or caps.get_size() == 0:
            return Gst.PadProbeReturn.OK
        structure = caps.get_structure(0)
        ok_w, width = structure.get_int("width")
        ok_h, height = structure.get_int("height")
        if not (ok_w and ok_h):
            return Gst.PadProbeReturn.OK
        text = f"{width}×{height}"
        try:
            ok_f, num, den = structure.get_fraction("framerate")
        except (TypeError, ValueError):
            ok_f, num, den = False, 0, 1
        if ok_f and den:
            text += f" · {round(num / den)} fps"
        GLib.idle_add(self.set_status, text)
        return Gst.PadProbeReturn.OK

    def set_status(self, text):
        if not self.closing:
            self.status.set_label(text)
        return False

    def on_video_error(self, bus, message):
        if self.stopping or self.closing:
            return
        error, debug = message.parse_error()
        print(f"Bild: {error.message} {debug or ''}", file=sys.stderr)
        self.stop_video()
        self.stop_audio()
        self.status.set_label(error.message)
        self.show_toast(error.message)

    def on_audio_error(self, bus, message):
        if self.stopping or self.closing:
            return
        error, debug = message.parse_error()
        print(f"Ton: {error.message} {debug or ''}", file=sys.stderr)
        self.stop_audio()
        self.show_toast(error.message)

    def on_discord(self, button):
        if self._guard:
            return
        self.settings["discord"] = button.get_active()
        save_settings(self.settings)
        self._sync_discord_style()
        if button.get_active():
            self.show_toast("In Discord Kamera „HD60“ und Eingabegerät „HD60 S“ wählen.")
        if self.capture is not None:
            self.start()

    def on_hear(self, button):
        if self._guard:
            return
        self.settings["hear"] = button.get_active()
        save_settings(self.settings)
        self._sync_hear_icon()
        if self.capture is None:
            return
        if self.settings["hear"]:
            self.audio_tries = 0
            GLib.timeout_add(200, self.try_audio)
        else:
            self.stop_audio()

    def on_volume(self, scale):
        self.settings["volume"] = scale.get_value()
        save_settings(self.settings)
        if self.volume is not None:
            self.volume.set_property("volume", float(self.settings["volume"]))

    def on_audio_input(self, dropdown, _pspec):
        if self._guard:
            return
        self.settings["audio_input"] = 1 if dropdown.get_selected() == 1 else 0
        save_settings(self.settings)
        if self.capture is not None:
            set_audio_input(self.capture["path"], self.settings["audio_input"])

    def _sync_hear_icon(self):
        icon = "audio-volume-high-symbolic" if self.settings["hear"] else "audio-volume-muted-symbolic"
        self.hear_btn.set_icon_name(icon)

    def _sync_discord_style(self):
        if self.settings["discord"]:
            self.discord_btn.add_css_class("suggested-action")
        else:
            self.discord_btn.remove_css_class("suggested-action")

    def stop_video(self):
        self.stopping = True
        pipeline = self.video
        self.video = None
        try:
            if pipeline is not None:
                bus = pipeline.get_bus()
                if bus is not None:
                    bus.remove_signal_watch()
                pipeline.set_state(Gst.State.NULL)
            self.picture.set_paintable(None)
        finally:
            self.stopping = False

    def stop_audio(self):
        self.stopping = True
        pipeline = self.audio
        self.audio = None
        self.volume = None
        try:
            if pipeline is not None:
                bus = pipeline.get_bus()
                if bus is not None:
                    bus.remove_signal_watch()
                pipeline.set_state(Gst.State.NULL)
        finally:
            self.stopping = False

    @staticmethod
    def _tune_queue(queue):
        queue.set_property("max-size-buffers", 2)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)
        queue.set_property("leaky", 2)

    @staticmethod
    def bus_error(pipeline):
        bus = pipeline.get_bus()
        if bus is None:
            return None
        message = bus.pop_filtered(Gst.MessageType.ERROR)
        if message is None:
            return None
        error, _debug = message.parse_error()
        return error.message


class Hd60Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = Hd60Window(self, load_settings())
        self.window.present()


def main():
    ensure_drivers()
    missing = [
        name
        for name in ("v4l2src", "gtk4paintablesink", "videoconvert", "pipewiresrc", "pipewiresink")
        if Gst.ElementFactory.find(name) is None
    ]
    if missing:
        print("Fehlende GStreamer-Elemente: " + ", ".join(missing), file=sys.stderr)
        print("install.sh ausführen, damit die Pakete installiert werden.", file=sys.stderr)
        return 1
    return Hd60Application().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
