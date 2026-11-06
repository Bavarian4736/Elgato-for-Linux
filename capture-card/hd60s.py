#!/usr/bin/env python3
"""HD60: Vorschau für die Elgato Game Capture HD60 S, ohne OBS.

Das Fenster zeigt das HDMI-Bild und spielt den Ton lokal ab. Solange es
offen ist, liegt der Ton am Gerät „Game Capture HD60 S“. Discord
und jedes andere Programm nehmen dasselbe Eingabegerät und übertragen
das Fenster wie jedes andere.
"""

import errno
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from version_info import about_fields

# Discord liest das Fenster über den Bildschirmportal. DMA-Puffer darin lässt
# die Übertragung ewig laden und blockiert danach auch andere Übertragungen.
_disabled = [part for part in os.environ.get("GDK_DISABLE", "").split(",") if part]
if "dmabuf" not in _disabled:
    _disabled.append("dmabuf")
os.environ["GDK_DISABLE"] = ",".join(_disabled)

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
    defaults = {"hear": True, "volume": 1.0, "audio_input": 0}
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
    data["hear"] = bool(data["hear"])
    data.pop("discord", None)
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
    return Path("/sys/module/hd60s").is_dir()


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
    """Installiert den Kernel-Treiber über pkexec, wenn er fehlt."""
    global _ensure_attempted
    if drivers_ready() or _ensure_attempted:
        return
    _ensure_attempted = True
    script = install_script()
    if script is None:
        print("Kernel-Treiber fehlt, install.sh wurde nicht gefunden.", file=sys.stderr)
        return
    print("Kernel-Treiber fehlt. Installation über pkexec …", file=sys.stderr)
    if shutil_which("notify-send"):
        subprocess.run(
            ["notify-send", "--app-name=HD60", "HD60",
             "Treiber fehlt. Im folgenden Fenster das Passwort eingeben."],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    if shutil_which("pkexec") is None:
        print("pkexec fehlt. capture-card/install.sh ausführen.", file=sys.stderr)
        return
    subprocess.run(["pkexec", "/bin/bash", str(script), "--ensure"], check=False)


# linux/videodev2.h: struct v4l2_dv_timings ist 132 Byte, Breite und Höhe
# stehen direkt hinter dem Typ-Feld.
_DV_TIMINGS_SIZE = 132
_VIDIOC_QUERY_DV_TIMINGS = 0x80845663
_VIDIOC_S_DV_TIMINGS = 0xC0845657
_ENOLINK = getattr(errno, "ENOLINK", 67)


def _read_dv_timings(path, adopt):
    """HDMI-Modus der Karte.

    Liefert (Breite, Höhe), None ohne Signal, oder False wenn die Abfrage
    gerade nicht möglich ist. Mit adopt wird der erkannte Modus übernommen.
    Das darf nur passieren, solange nichts streamt: der Treiber verwirft
    sonst jedes Bild, bis das Gerät geschlossen und neu geöffnet wurde.
    """
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno in (errno.EBUSY, errno.EAGAIN):
            return False
        return None
    try:
        buf = bytearray(_DV_TIMINGS_SIZE)
        try:
            fcntl.ioctl(fd, _VIDIOC_QUERY_DV_TIMINGS, buf, True)
        except OSError as exc:
            if exc.errno in (errno.EBUSY, errno.EAGAIN):
                return False
            if exc.errno not in (_ENOLINK, errno.ENODEV, errno.ENOENT, errno.EIO):
                print(f"HDMI-Status: {exc.strerror}", file=sys.stderr)
            return None
        width = int.from_bytes(buf[4:8], "little")
        height = int.from_bytes(buf[8:12], "little")
        if width < 320 or height < 200:
            return None
        if adopt:
            try:
                fcntl.ioctl(fd, _VIDIOC_S_DV_TIMINGS, buf, True)
            except OSError as exc:
                if exc.errno not in (errno.EINVAL, errno.EBUSY, _ENOLINK):
                    print(f"HDMI-Modus: {exc.strerror}", file=sys.stderr)
        return width, height
    finally:
        os.close(fd)


def query_hdmi(path):
    return _read_dv_timings(path, adopt=False)


def adopt_hdmi(path):
    return _read_dv_timings(path, adopt=True)


def make_element(factory, name):
    element = Gst.ElementFactory.make(factory, name)
    if element is None:
        raise RuntimeError(f"GStreamer-Element fehlt: {factory}")
    return element


def add_elements(pipeline, *elements):
    # Gst.Bin.add nimmt hier genau ein Element. Mehrere Argumente werfen TypeError.
    for element in elements:
        pipeline.add(element)


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
        self.mode = None
        self.saw_frame = False
        self.play_started = 0.0
        self.frame_retries = 0
        self._syncing = False
        self._full_buttons = []
        self._bar_hide = 0
        self._blank_cursor = None
        self._frame_gen = 0
        self._frame_pending = False
        self._shown = 0.0
        self._quit_now = False
        self._retired = []

        self.set_default_size(1100, 680)
        self.connect("close-request", self.on_close)
        self.connect("notify::fullscreened", self.on_fullscreened)

        self.toast = Adw.ToastOverlay()
        self.toolbar = Adw.ToolbarView()
        self.toast.set_child(self.toolbar)
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
        header.pack_end(self._new_fullscreen_button())
        self.toolbar.add_top_bar(header)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.toolbar.set_content(self.stack)

        self.status_page = Adw.StatusPage(
            icon_name="video-display-symbolic",
            title="Keine HD60 S gefunden",
            description=(
                "Stecke die Karte an einen USB-3-Anschluss und schließe HDMI an. "
                "Fehlt der Treiber, hd60s neu starten und die Installation bestätigen."
            ),
        )
        retry = Gtk.Button(label="Erneut suchen")
        retry.set_halign(Gtk.Align.CENTER)
        retry.add_css_class("pill")
        retry.connect("clicked", lambda *_: self.start())
        self.status_page.set_child(retry)
        self.stack.add_named(self.status_page, "empty")

        video_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_page.add_css_class("video-page")
        self.picture = Gtk.Picture()
        self.picture.set_hexpand(True)
        self.picture.set_vexpand(True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.add_css_class("video-frame")
        self.picture.set_can_shrink(True)
        self.overlay = Gtk.Overlay()
        self.overlay.set_hexpand(True)
        self.overlay.set_vexpand(True)
        self.overlay.set_child(self.picture)
        self.wait_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.wait_box.set_halign(Gtk.Align.CENTER)
        self.wait_box.set_valign(Gtk.Align.CENTER)
        self.wait_box.set_margin_start(24)
        self.wait_box.set_margin_end(24)
        wait_title = Gtk.Label(label="Kein HDMI-Signal")
        wait_title.add_css_class("wait-title")
        wait_hint = Gtk.Label(
            label="Die Karte ist verbunden. Quelle einschalten oder das HDMI-Kabel prüfen.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
            max_width_chars=42,
        )
        wait_hint.add_css_class("wait-hint")
        self.wait_box.append(wait_title)
        self.wait_box.append(wait_hint)
        self.overlay.add_overlay(self.wait_box)
        self.wait_box.set_visible(False)
        click = Gtk.GestureClick()
        click.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        click.connect("pressed", self.on_picture_pressed)
        self.overlay.add_controller(click)
        video_page.append(self.overlay)

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

        bar.append(self._new_fullscreen_button())
        self.toolbar.add_bottom_bar(bar)
        self.stack.add_named(video_page, "video")
        self._sync_bars()

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_pointer_motion)
        self.add_controller(motion)

        css = Gtk.CssProvider()
        css.load_from_string(
            ".video-frame, .video-page { background: black; }"
            ".wait-title { color: white; font-size: 22px; font-weight: bold; }"
            ".wait-hint { color: #d0d0d0; }"
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._sync_hear_icon()
        GLib.timeout_add_seconds(1, self.tick)
        GLib.idle_add(self.start)

    def _new_fullscreen_button(self):
        button = Gtk.ToggleButton(icon_name="view-fullscreen-symbolic")
        button.set_tooltip_text("Vollbild")
        button.connect("toggled", self.on_fullscreen_toggled)
        self._full_buttons.append(button)
        return button

    def on_fullscreen_toggled(self, button):
        if self._guard:
            return
        if button.get_active() == self.is_fullscreen():
            return
        self._toggle_fullscreen()

    def on_fullscreened(self, *_args):
        full = self.is_fullscreen()
        self._guard = True
        icon = "view-restore-symbolic" if full else "view-fullscreen-symbolic"
        tip = "Vollbild verlassen" if full else "Vollbild"
        for button in self._full_buttons:
            button.set_active(full)
            button.set_icon_name(icon)
            button.set_tooltip_text(tip)
        self._guard = False
        self.toolbar.set_extend_content_to_top_edge(full)
        self.toolbar.set_extend_content_to_bottom_edge(full)
        if self._bar_hide:
            GLib.source_remove(self._bar_hide)
            self._bar_hide = 0
        if full:
            self._reveal_bars(False)
        else:
            self.set_cursor(None)
            self._sync_bars()

    def on_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_F11:
            self._toggle_fullscreen()
            return True
        if keyval == Gdk.KEY_Escape and self.is_fullscreen():
            self.unfullscreen()
            return True
        return False

    def on_picture_pressed(self, _gesture, n_press, _x, _y):
        if n_press == 2:
            self._toggle_fullscreen()

    def on_pointer_motion(self, *_args):
        if not self.is_fullscreen():
            return
        self.set_cursor(None)
        self._reveal_bars(True)
        if self._bar_hide:
            GLib.source_remove(self._bar_hide)
        self._bar_hide = GLib.timeout_add(2200, self._autohide_bars)

    def _toggle_fullscreen(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _blank_mouse(self):
        if self._blank_cursor is None:
            self._blank_cursor = Gdk.Cursor.new_from_name("none")
        return self._blank_cursor

    def _autohide_bars(self):
        self._bar_hide = 0
        if self.is_fullscreen():
            self._reveal_bars(False)
            cursor = self._blank_mouse()
            if cursor is not None:
                self.set_cursor(cursor)
        return False

    def _reveal_bars(self, show):
        on_video = self.stack.get_visible_child_name() == "video"
        if self.is_fullscreen():
            self.toolbar.set_reveal_top_bars(show)
            self.toolbar.set_reveal_bottom_bars(show and on_video)
            return
        self.toolbar.set_reveal_top_bars(True)
        self.toolbar.set_reveal_bottom_bars(on_video)

    def _sync_bars(self):
        if self.is_fullscreen():
            return
        self._reveal_bars(True)

    def on_about(self, *_args):
        about = about_fields()
        dialog = Adw.AboutDialog()
        dialog.set_application_name("HD60")
        dialog.set_application_icon("hd60s")
        dialog.set_developer_name("Bavarian4736")
        dialog.set_version(about["version"])
        dialog.set_comments(about["comments"])
        dialog.set_website("https://github.com/Bavarian4736/hd60s-nobara")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.present(self)

    def on_close(self, *_args):
        if self._quit_now:
            return False
        if self.closing:
            return True
        self.closing = True
        if self._bar_hide:
            GLib.source_remove(self._bar_hide)
            self._bar_hide = 0
        self.set_cursor(None)
        # Nicht hier anhalten: PipeWire und die Grafikkarte laufen auf dem
        # gleichen Hauptloop. Ein direktes Stoppen mitten im Schließen stürzt ab.
        GLib.idle_add(self._shutdown)
        return True

    def _shutdown(self):
        try:
            self.stop_audio()
            self.stop_video(wait=False)
        finally:
            self._quit_now = True
            self.close()
        return False

    def tick(self):
        if self.closing:
            return False
        if self.capture and not Path(self.capture["path"]).exists():
            self.stop_audio()
            self.stop_video()
            self.capture = None
            self.mode = None
            self.show_empty(
                "Keine HD60 S gefunden",
                "Die Karte wurde getrennt. Stecke sie wieder an einen USB-3-Anschluss.",
            )
        else:
            self.start()
        if self.settings["hear"] and self.video is not None and self.audio is None:
            self.try_audio()
        elif not self.settings["hear"] and self.audio is not None:
            self.stop_audio()
        return True

    def show_empty(self, title, description):
        self.status_page.set_title(title)
        self.status_page.set_description(description)
        self.stack.set_visible_child_name("empty")
        self._sync_bars()

    def show_picture(self):
        self.wait_box.set_visible(False)
        self.stack.set_visible_child_name("video")
        self._sync_bars()

    def show_waiting(self):
        self.wait_box.set_visible(True)
        self.status.set_label("Kein HDMI-Signal")
        self.stack.set_visible_child_name("video")
        self._sync_bars()

    def _map_picture(self):
        self.show_picture()
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def show_toast(self, text):
        if text == self.last_notice:
            return
        self.last_notice = text
        self.toast.add_toast(Adw.Toast(title=text, timeout=5))

    def start(self):
        if self.closing or self._syncing:
            return False
        self._syncing = True
        try:
            self._sync_capture()
        finally:
            self._syncing = False
        return False

    def _sync_capture(self):
        devices = video_devices()
        capture = find_capture(devices)
        if capture is None:
            self.stop_audio()
            self.stop_video()
            self.capture = None
            self.mode = None
            self.show_empty(
                "Keine HD60 S gefunden",
                "Stecke die Karte an einen USB-3-Anschluss und schließe HDMI an. "
                "Fehlt der Treiber, hd60s neu starten und die Installation bestätigen.",
            )
            return

        self.capture = capture
        mode = query_hdmi(capture["path"])
        if mode is False:
            return
        if mode is None:
            if self.video is not None:
                self.stop_audio()
                self.stop_video()
            self.mode = None
            self.saw_frame = False
            self.frame_retries = 0
            self.show_waiting()
            return

        if (
            self.video is not None
            and self.mode == mode
            and (
                self.saw_frame
                or self.frame_retries >= 3
                or time.monotonic() - self.play_started < 4
            )
        ):
            if self.saw_frame:
                self.frame_retries = 0
            self.show_picture()
            return

        if self.video is not None and self.mode == mode:
            self.frame_retries += 1
            if self.frame_retries == 3:
                self.show_toast("Die Karte liefert kein Bild. HDMI-Kabel und Quelle prüfen.")

        # Gerät ganz schließen, damit der Treiber den erkannten Modus übernimmt.
        # Sonst bleibt das Platzhalterformat (1280×720) aktiv und 1080p wird verworfen.
        self.stop_audio()
        self.stop_video()
        adopted = adopt_hdmi(capture["path"])
        if not adopted:
            self.mode = None
            self.show_waiting()
            return

        self.mode = adopted
        self.saw_frame = False
        self.play_started = time.monotonic()
        set_audio_input(capture["path"], self.settings["audio_input"])
        self._map_picture()
        try:
            self.start_video(capture)
        except Exception as exc:
            self.stop_video()
            self.mode = None
            self.show_empty("Bild konnte nicht gestartet werden", str(exc))
            return
        self.status.set_label("Verbinde…")
        self.restart_audio()

    def start_video(self, capture):
        self.stop_video()
        pipeline = Gst.Pipeline.new("hd60-video")
        src = make_element("v4l2src", "src")
        src.set_property("device", capture["path"])
        src.set_property("do-timestamp", True)
        # mmap statt DMA-Buf: die Karte liefert Speicher aus dem Kernel, und
        # gtk4paintablesink bleibt bei diesem DMA-Buf schwarz.
        src.set_property("io-mode", 2)
        preview_queue = make_element("queue", "preview-queue")
        self._tune_queue(preview_queue)
        convert = make_element("videoconvert", "preview-convert")
        preview_caps = make_element("capsfilter", "preview-caps")
        preview_caps.set_property("caps", Gst.Caps.from_string("video/x-raw,format=BGRA"))
        # Normales Bild im Fenster, keine GPU-Fläche. Discord bleibt sonst beim
        # Übertragen dieses Fensters hängen, und danach starten auch andere
        # Übertragungen nicht mehr.
        sink = make_element("appsink", "view")
        sink.set_property("sync", False)
        sink.set_property("max-buffers", 1)
        sink.set_property("drop", True)
        sink.set_property("enable-last-sample", False)
        sink.set_property("emit-signals", True)
        sink.connect("new-sample", self.on_sample)
        add_elements(pipeline, src, preview_queue, convert, preview_caps, sink)
        if (
            not preview_queue.link(convert)
            or not convert.link(preview_caps)
            or not preview_caps.link(sink)
        ):
            raise RuntimeError("Vorschau konnte nicht verbunden werden.")
        if not src.link(preview_queue):
            raise RuntimeError("Vorschau konnte nicht verbunden werden.")

        src_pad = src.get_static_pad("src")
        src_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_caps)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self.on_video_error)
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
        add_elements(pipeline, src, queue, convert, resample, volume, sink)
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

    def on_sample(self, sink):
        if self.closing:
            sink.emit("pull-sample")
            return Gst.FlowReturn.OK
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        if buffer is None or caps is None or caps.get_size() == 0:
            return Gst.FlowReturn.OK
        structure = caps.get_structure(0)
        ok_w, width = structure.get_int("width")
        ok_h, height = structure.get_int("height")
        if not (ok_w and ok_h) or self._frame_pending:
            self.saw_frame = True
            return Gst.FlowReturn.OK
        # 30 Bilder pro Sekunde reichen für die Vorschau und für die Übertragung.
        now = time.monotonic()
        if now - self._shown < 0.033:
            self.saw_frame = True
            return Gst.FlowReturn.OK
        self._shown = now
        ok, info = buffer.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK
        try:
            data = bytes(info.data)
        finally:
            buffer.unmap(info)
        stride = width * 4
        if len(data) < stride * height:
            return Gst.FlowReturn.OK
        self.saw_frame = True
        self._frame_pending = True
        GLib.idle_add(self.show_frame, self._frame_gen, width, height, stride, data)
        return Gst.FlowReturn.OK

    def show_frame(self, generation, width, height, stride, data):
        self._frame_pending = False
        if generation != self._frame_gen or self.closing:
            return False
        texture = Gdk.MemoryTexture.new(
            width,
            height,
            Gdk.MemoryFormat.B8G8R8A8,
            GLib.Bytes.new(data),
            stride,
        )
        self.picture.set_paintable(texture)
        return False

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

    def stop_video(self, wait=True):
        self.stopping = True
        self._frame_gen += 1
        self._frame_pending = False
        pipeline = self.video
        self.video = None
        try:
            if pipeline is None:
                self.picture.set_paintable(None)
                return
            sink = pipeline.get_by_name("view")
            if sink is not None:
                sink.set_property("emit-signals", False)
                try:
                    sink.disconnect_by_func(self.on_sample)
                except (TypeError, RuntimeError):
                    pass
            bus = pipeline.get_bus()
            if bus is not None:
                try:
                    bus.remove_signal_watch()
                except (TypeError, RuntimeError):
                    pass
            self.picture.set_paintable(None)
            pipeline.set_state(Gst.State.NULL)
            self._retired.append(pipeline)
            if wait and not self.closing:
                pipeline.get_state(2 * Gst.SECOND)
        finally:
            self.stopping = False

    def stop_audio(self):
        self.stopping = True
        pipeline = self.audio
        self.audio = None
        self.volume = None
        try:
            if pipeline is None:
                return
            bus = pipeline.get_bus()
            if bus is not None:
                try:
                    bus.remove_signal_watch()
                except (TypeError, RuntimeError):
                    pass
            pipeline.set_state(Gst.State.NULL)
            self._retired.append(pipeline)
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
        for name in ("v4l2src", "appsink", "videoconvert", "pipewiresrc", "pipewiresink")
        if Gst.ElementFactory.find(name) is None
    ]
    if missing:
        print("Fehlende GStreamer-Elemente: " + ", ".join(missing), file=sys.stderr)
        print("install.sh ausführen, damit die Pakete installiert werden.", file=sys.stderr)
        return 1
    return Hd60Application().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
