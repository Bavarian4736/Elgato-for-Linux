from __future__ import annotations

import base64
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

ACCOUNTS = "https://accounts.spotify.com"
API = "https://api.spotify.com/v1"

REDIRECT_URI = "http://127.0.0.1:41837/callback"
LEGACY_REDIRECT_URI = "https://stream-controller/callback"

SCOPES = " ".join(
    [
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
        "user-library-read",
        "user-library-modify",
        "playlist-read-private",
        "playlist-modify-private",
        "playlist-modify-public",
    ]
)

_URI_RE = re.compile(
    r"(?:spotify:(track|album|artist|playlist):([a-zA-Z0-9]+))"
    r"|(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|artist|playlist)/([a-zA-Z0-9]+))",
    re.I,
)


def parse_spotify_ref(text: str) -> tuple[str, str] | None:
    """Return (type, id) from URI or open.spotify.com URL."""
    text = (text or "").strip()
    if not text:
        return None
    m = _URI_RE.search(text)
    if not m:
        # bare id + optional type prefix "album:xxx"
        if ":" in text and not text.startswith("http"):
            parts = text.split(":")
            if len(parts) >= 2 and parts[-2] in ("track", "album", "artist", "playlist"):
                return parts[-2].lower(), parts[-1]
        return None
    if m.group(1):
        return m.group(1).lower(), m.group(2)
    return m.group(3).lower(), m.group(4)


class SpotifyClient:
    def __init__(self, get_settings: Callable[[], dict], set_settings: Callable[[dict], None]):
        self.get_settings = get_settings
        self.set_settings = set_settings
        self._lock = threading.Lock()
        self._callback_code: str | None = None
        self._httpd: HTTPServer | None = None
        self._active_redirect = REDIRECT_URI
        self._liked_cache: set[str] | None = None
        self._liked_cache_at = 0.0

    def _cfg(self) -> dict:
        return self.get_settings() or {}

    def _save(self, **kwargs) -> None:
        s = self._cfg()
        s.update(kwargs)
        self.set_settings(s)

    @property
    def client_id(self) -> str:
        return self._cfg().get("client_id", "")

    @property
    def client_secret(self) -> str:
        return self._cfg().get("client_secret", "")

    def authorize_url(self, redirect_uri: str | None = None) -> str:
        self._active_redirect = redirect_uri or REDIRECT_URI
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self._active_redirect,
            "scope": SCOPES,
            "state": secrets.token_urlsafe(16),
            "show_dialog": "true",
        }
        return f"{ACCOUNTS}/authorize?{urllib.parse.urlencode(params)}"

    def _decode_payload(self, raw: str) -> Any:
        if not raw or not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Spotify sometimes returns opaque non-JSON on 200 player cmds
            return {"_raw": raw}

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        form: dict | None = None,
        body: dict | None = None,
        auth_basic: tuple[str, str] | None = None,
        bearer: str | None = None,
        empty_body: bool = False,
    ) -> tuple[int, Any]:
        data = None
        hdrs = dict(headers or {})
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        elif empty_body:
            data = b""
            hdrs.setdefault("Content-Length", "0")
        if auth_basic:
            token = base64.b64encode(f"{auth_basic[0]}:{auth_basic[1]}".encode()).decode()
            hdrs["Authorization"] = f"Basic {token}"
        if bearer:
            hdrs["Authorization"] = f"Bearer {bearer}"
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return resp.status, self._decode_payload(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="ignore")
            return e.code, self._decode_payload(raw)
        except Exception as e:
            return 0, {"error": str(e)}

    @staticmethod
    def _ok(code: int) -> bool:
        return 200 <= code < 300

    def _access_token(self) -> str | None:
        with self._lock:
            s = self._cfg()
            access = s.get("access_token")
            expires_at = float(s.get("expires_at") or 0)
            if access and time.time() < expires_at - 30:
                return access
            refresh = s.get("refresh_token")
            if not refresh or not self.client_id or not self.client_secret:
                return None
            code, data = self._request(
                "POST",
                f"{ACCOUNTS}/api/token",
                form={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": self.client_id,
                },
                auth_basic=(self.client_id, self.client_secret),
            )
            if code != 200 or "access_token" not in data:
                return None
            update = {
                "access_token": data["access_token"],
                "expires_at": time.time() + int(data.get("expires_in", 3600)),
            }
            if data.get("refresh_token"):
                update["refresh_token"] = data["refresh_token"]
            self._save(**update)
            return data["access_token"]

    def _api(self, method: str, path: str, **kwargs) -> tuple[int, Any]:
        token = self._access_token()
        if not token:
            return 401, {"error": "not_authenticated"}
        return self._request(method, f"{API}{path}", bearer=token, **kwargs)

    def start_browser_login(self) -> str:
        if not self.client_id or not self.client_secret:
            return "Client ID/Secret fehlen"
        self._callback_code = None
        if not self._start_callback_server():
            return "Port 41837 belegt — bitte anderen Spotify-Login schließen"
        url = self.authorize_url(REDIRECT_URI)
        webbrowser.open(url)
        threading.Thread(target=self._wait_and_exchange, daemon=True).start()
        return (
            "Browser geöffnet. Nach 2FA landet Spotify auf einer OK-Seite.\n"
            f"Falls Fehler „redirect_uri“: im Dashboard eintragen:\n{REDIRECT_URI}"
        )

    def _start_callback_server(self) -> bool:
        if self._httpd is not None:
            return True
        client = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                qs = parse_qs(parsed.query)
                client._callback_code = (qs.get("code") or [None])[0]
                body = (
                    b"<html><body style='font-family:sans-serif;background:#121212;color:#fff;"
                    b"display:flex;align-items:center;justify-content:center;height:100vh'>"
                    b"<div><h1>Spotify verbunden</h1>"
                    b"<p>Du kannst dieses Fenster schliessen und zu StreamController zurueck.</p>"
                    b"</div></body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        try:
            self._httpd = HTTPServer(("127.0.0.1", 41837), Handler)
        except OSError:
            self._httpd = None
            return False
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return True

    def _wait_and_exchange(self) -> None:
        for _ in range(180):
            if self._callback_code:
                self.exchange_code(self._callback_code, redirect_uri=REDIRECT_URI)
                self._callback_code = None
                break
            time.sleep(1)
        self._stop_server()

    def _stop_server(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            self._httpd = None

    @staticmethod
    def extract_code_from_text(text: str) -> str | None:
        text = (text or "").strip()
        if not text:
            return None
        if "code=" in text:
            try:
                if "://" not in text and text.startswith("stream-controller"):
                    text = "https://" + text
                qs = parse_qs(urlparse(text).query)
                if qs.get("code"):
                    return qs["code"][0]
            except Exception:
                pass
            part = text.split("code=", 1)[1]
            return part.split("&", 1)[0].strip()
        if len(text) > 20 and " " not in text:
            return text
        return None

    def exchange_code(self, code: str, redirect_uri: str | None = None) -> bool:
        code = self.extract_code_from_text(code) or (code or "").split("&", 1)[0].strip()
        redirect = redirect_uri or self._active_redirect or REDIRECT_URI
        status, data = self._request(
            "POST",
            f"{ACCOUNTS}/api/token",
            form={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
            },
            auth_basic=(self.client_id, self.client_secret),
        )
        if status != 200 and redirect != LEGACY_REDIRECT_URI:
            status, data = self._request(
                "POST",
                f"{ACCOUNTS}/api/token",
                form={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": LEGACY_REDIRECT_URI,
                },
                auth_basic=(self.client_id, self.client_secret),
            )
        if status != 200 or "access_token" not in data:
            return False
        self._save(
            access_token=data["access_token"],
            refresh_token=data.get(
                "refresh_token", self._cfg().get("refresh_token", "")
            ),
            expires_at=time.time() + int(data.get("expires_in", 3600)),
        )
        self._liked_cache = None
        return True

    def is_authenticated(self) -> bool:
        return bool(self._access_token())

    def _ensure_device(self) -> None:
        code, data = self._api("GET", "/me/player/devices")
        if not self._ok(code) or not isinstance(data, dict):
            return
        devices = data.get("devices") or []
        if not devices:
            return
        if any(d.get("is_active") for d in devices):
            return
        # Transfer to first available device so player commands work
        did = devices[0].get("id")
        if did:
            self._api("PUT", "/me/player", body={"device_ids": [did], "play": False})
            time.sleep(0.25)

    def playback(self) -> dict | None:
        code, data = self._api("GET", "/me/player")
        if code == 204:
            return {}
        if not self._ok(code) or not isinstance(data, dict):
            return None
        return data

    def is_playing(self) -> bool:
        p = self.playback()
        return bool(p and p.get("is_playing"))

    def _player_cmd(self, method: str, path: str, **kwargs) -> bool:
        self._ensure_device()
        code, _ = self._api(method, path, **kwargs)
        if self._ok(code):
            return True
        # Restriction / race: verify via state when possible
        if code in (403, 404):
            return True  # command often still applied on desktop clients
        return False

    def play_pause(self) -> bool:
        playing = self.is_playing()
        if playing:
            ok = self._player_cmd("PUT", "/me/player/pause", empty_body=True)
        else:
            ok = self._player_cmd("PUT", "/me/player/play", body={})
        if ok:
            return True
        time.sleep(0.35)
        return self.is_playing() != playing

    def next(self) -> bool:
        return self._player_cmd("POST", "/me/player/next", empty_body=True)

    def previous(self) -> bool:
        return self._player_cmd("POST", "/me/player/previous", empty_body=True)

    def shuffle(self) -> bool:
        p = self.playback() or {}
        state = not bool(p.get("shuffle_state"))
        return self._player_cmd(
            "PUT", f"/me/player/shuffle?state={'true' if state else 'false'}", empty_body=True
        )

    def shuffle_on(self) -> bool:
        p = self.playback() or {}
        return bool(p.get("shuffle_state"))

    def repeat(self) -> bool:
        p = self.playback() or {}
        current = p.get("repeat_state") or "off"
        nxt = {"off": "context", "context": "track", "track": "off"}.get(current, "off")
        return self._player_cmd(
            "PUT", f"/me/player/repeat?state={nxt}", empty_body=True
        )

    def repeat_state(self) -> str:
        p = self.playback() or {}
        return p.get("repeat_state") or "off"

    def current_track_id(self) -> str | None:
        p = self.playback() or {}
        item = p.get("item") or {}
        return item.get("id")

    def play_context(self, uri_or_url: str) -> bool:
        parsed = parse_spotify_ref(uri_or_url)
        if not parsed:
            return False
        kind, sid = parsed
        if kind not in ("album", "artist", "playlist", "track"):
            return False
        uri = f"spotify:{kind}:{sid}"
        self._ensure_device()
        if kind == "track":
            return self._player_cmd("PUT", "/me/player/play", body={"uris": [uri]})
        return self._player_cmd("PUT", "/me/player/play", body={"context_uri": uri})

    def search_and_play(self, query: str, kind: str) -> bool:
        """kind: album|artist — search and play top result."""
        kind = kind.lower().strip()
        if kind not in ("album", "artist"):
            return False
        q = (query or "").strip()
        if not q:
            return False
        # If user pasted a URI/URL, play directly
        if parse_spotify_ref(q):
            return self.play_context(q)
        code, data = self._api(
            "GET",
            f"/search?{urllib.parse.urlencode({'q': q, 'type': kind, 'limit': 1})}",
        )
        if not self._ok(code) or not isinstance(data, dict):
            return False
        items = ((data.get(f"{kind}s") or {}).get("items")) or []
        if not items:
            return False
        uri = items[0].get("uri")
        if not uri:
            return False
        return self.play_context(uri)

    # --- favourites ---------------------------------------------------------

    def _likes_playlist_id(self) -> str | None:
        return self._cfg().get("likes_playlist_id") or None

    def _ensure_likes_playlist(self) -> str | None:
        existing = self._likes_playlist_id()
        if existing:
            return existing
        code, data = self._api(
            "POST",
            "/me/playlists",
            body={
                "name": "StreamDeck Likes",
                "public": False,
                "description": "Auto-Playlist für Stream Deck Favourites",
            },
        )
        if self._ok(code) and isinstance(data, dict) and data.get("id"):
            pid = data["id"]
            self._save(likes_playlist_id=pid)
            return pid
        # Find existing by name
        code, data = self._api("GET", "/me/playlists?limit=50")
        if self._ok(code) and isinstance(data, dict):
            for pl in data.get("items") or []:
                if (pl.get("name") or "") == "StreamDeck Likes":
                    pid = pl.get("id")
                    if pid:
                        self._save(likes_playlist_id=pid)
                        return pid
        return None

    def _library_contains(self, tid: str) -> bool | None:
        """True/False if known, None if endpoint forbidden."""
        code, data = self._api("GET", f"/me/tracks/contains?ids={tid}")
        if self._ok(code) and isinstance(data, list) and data:
            return bool(data[0])
        return None

    def _refresh_liked_cache(self, force: bool = False) -> set[str]:
        if (
            not force
            and self._liked_cache is not None
            and time.time() - self._liked_cache_at < 120
        ):
            return self._liked_cache
        liked: set[str] = set()
        # Library pages (read works even when contains/write 403)
        url_path = "/me/tracks?limit=50"
        for _ in range(40):  # up to ~2000 tracks
            code, data = self._api("GET", url_path)
            if not self._ok(code) or not isinstance(data, dict):
                break
            for item in data.get("items") or []:
                track = item.get("track") or {}
                if track.get("id"):
                    liked.add(track["id"])
            nxt = data.get("next")
            if not nxt:
                break
            # next is absolute URL — strip API prefix
            url_path = nxt.split("/v1", 1)[-1]
        # Playlist fallback items
        pid = self._likes_playlist_id()
        if pid:
            path = f"/playlists/{pid}/tracks?limit=50"
            for _ in range(20):
                code, data = self._api("GET", path)
                if not self._ok(code) or not isinstance(data, dict):
                    break
                for item in data.get("items") or []:
                    track = (item.get("track") or {})
                    if track.get("id"):
                        liked.add(track["id"])
                nxt = data.get("next")
                if not nxt:
                    break
                path = nxt.split("/v1", 1)[-1]
        self._liked_cache = liked
        self._liked_cache_at = time.time()
        return liked

    def is_favourite(self, track_id: str | None = None) -> bool:
        tid = track_id or self.current_track_id()
        if not tid:
            return False
        known = self._library_contains(tid)
        if known is not None:
            return known
        return tid in self._refresh_liked_cache()

    def toggle_favourite(self) -> bool:
        tid = self.current_track_id()
        if not tid:
            return False
        liked = self.is_favourite(tid)

        if liked:
            # Try native library remove
            code, _ = self._api("DELETE", f"/me/tracks?ids={tid}", empty_body=True)
            if not self._ok(code):
                code, _ = self._api("DELETE", "/me/tracks", body={"ids": [tid]})
            if self._ok(code):
                if self._liked_cache is not None:
                    self._liked_cache.discard(tid)
                return True
            # Playlist fallback
            pid = self._ensure_likes_playlist()
            if not pid:
                return False
            # Remove by URI
            code, _ = self._api(
                "DELETE",
                f"/playlists/{pid}/tracks",
                body={"tracks": [{"uri": f"spotify:track:{tid}"}]},
            )
            if self._ok(code):
                if self._liked_cache is not None:
                    self._liked_cache.discard(tid)
                return True
            return False

        # Add like
        code, _ = self._api("PUT", f"/me/tracks?ids={tid}", empty_body=True)
        if not self._ok(code):
            code, _ = self._api("PUT", "/me/tracks", body={"ids": [tid]})
        if self._ok(code):
            if self._liked_cache is not None:
                self._liked_cache.add(tid)
            return True
        pid = self._ensure_likes_playlist()
        if not pid:
            return False
        code, _ = self._api(
            "POST",
            f"/playlists/{pid}/tracks",
            body={"uris": [f"spotify:track:{tid}"]},
        )
        if self._ok(code):
            if self._liked_cache is not None:
                self._liked_cache.add(tid)
            return True
        return False
