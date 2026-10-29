from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, GLib, WebKit


def _extract_code(url: str) -> str | None:
    if not url:
        return None
    lower = url.lower()
    if not any(
        p in lower
        for p in (
            "stream-controller/callback",
            "127.0.0.1:41837/callback",
            "localhost:41837/callback",
        )
    ) and "stream-controller" not in lower:
        return None
    try:
        if "://" not in url and url.startswith("stream-controller"):
            url = "https://" + url
        qs = parse_qs(urlparse(url).query)
        code = (qs.get("code") or [None])[0]
        if code:
            return code.split("#", 1)[0].strip()
    except Exception:
        pass
    if "code=" in url:
        return url.split("code=", 1)[1].split("&", 1)[0].split("#", 1)[0].strip()
    return None


class WebAuthWindow(Adw.Window):
    """Captures Spotify OAuth redirect even when the custom host fails to load."""

    def __init__(self, initial_url: str, callback, application=None, **kwargs):
        super().__init__(application=application, **kwargs)
        self.callback = callback
        self._done = False
        self.set_title("Spotify Login")
        self.set_default_size(720, 820)
        self.set_modal(True)

        self.webview = WebKit.WebView()
        self.set_content(self.webview)
        self.webview.connect("load-changed", self._on_load_changed)
        self.webview.connect("decide-policy", self._on_decide_policy)
        self.webview.connect("load-failed", self._on_load_failed)
        self.webview.connect("notify::uri", self._on_uri_changed)
        self.webview.load_uri(initial_url)
        GLib.timeout_add(400, self._poll_uri)

    def _maybe_finish(self, uri: str) -> bool:
        code = _extract_code(uri or "")
        if not code or self._done:
            return False
        self._done = True
        try:
            self.close()
        except Exception:
            pass
        if self.callback:
            GLib.idle_add(self.callback, code)
        return True

    def _poll_uri(self):
        if self._done:
            return False
        try:
            if self._maybe_finish(self.webview.get_uri() or ""):
                return False
        except Exception:
            pass
        return True

    def _on_uri_changed(self, *_args):
        self._maybe_finish(self.webview.get_uri() or "")

    def _on_load_changed(self, webview, _load_event):
        self._maybe_finish(webview.get_uri() or "")

    def _on_load_failed(self, webview, _event, uri, _error):
        if self._maybe_finish(uri or ""):
            return True
        return False

    def _on_decide_policy(self, webview, decision, decision_type):
        uri = ""
        try:
            if decision_type == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
                uri = decision.get_navigation_action().get_request().get_uri()
            elif decision_type == WebKit.PolicyDecisionType.RESPONSE:
                uri = decision.get_request().get_uri()
        except Exception:
            return False
        if self._maybe_finish(uri):
            try:
                decision.ignore()
            except Exception:
                pass
            return True
        return False
