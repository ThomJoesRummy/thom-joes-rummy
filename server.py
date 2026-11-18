"""Progressive Rummy table server.  Uses only Python's standard library, so
there is nothing extra to install.

Run it with:   python server.py
Then open the address it prints.  Phones and other computers on the same
Wi-Fi open the second address it prints.
"""
from __future__ import annotations

import json
import mimetypes
import os
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from game import GameError, Lobby

STATIC = Path(__file__).resolve().parent / "static"
LONG_POLL_SECONDS = 20
# Online version: running on a website (Render sets RENDER=true), not on the
# desktop.  No browser to open and no Wi-Fi address to show.
HOSTED = bool(os.environ.get("RENDER")) or "--hosted" in sys.argv
MAX_BODY = 64 * 1024


def make_handler(lobby: Lobby):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ProgressiveRummy/0.1"

        def log_message(self, fmt, *args):      # keep the window quiet
            pass

        # ---------------------------------------------------------- output
        def _send(self, status, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            try:
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass    # the browser closed or left the page; nothing to do

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _error(self, status, msg):
            self._json(status, {"ok": False, "error": msg})

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("request too large")
            raw = self.rfile.read(n) if n else b"{}"
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            return data

        # ---------------------------------------------------------- GET
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/api/state":
                return self._state(parse_qs(url.query))
            if url.path == "/api/info":
                # Fourth edition: the computer's address on the Wi-Fi, so the
                # waiting screen can show phones a link that works for them.
                # Online, the website's own address is the link.
                if HOSTED:
                    return self._json(200, {"ok": True, "lan": None})
                lan = local_address()
                port = self.server.server_address[1]
                return self._json(200, {"ok": True, "lan": f"http://{lan}:{port}" if lan else None})
            name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            if name.startswith("static/"):
                name = name[len("static/"):]
            path = (STATIC / name).resolve()
            if STATIC not in path.parents or not path.is_file():
                return self._error(404, "not found")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, path.read_bytes(), ctype)

        def _state(self, q):
            code = (q.get("code") or [""])[0]
            token = (q.get("token") or [""])[0]
            try:
                room = lobby.get(code)
                room.seat_for(token)
                since = (q.get("since") or [None])[0]
                if since is not None and since.lstrip("-").isdigit():
                    room.wait_for_change(int(since), LONG_POLL_SECONDS)
                self._json(200, {"ok": True, "state": room.view_for(token)})
            except KeyError as e:
                self._error(404, e.args[0])
            except PermissionError as e:
                self._error(403, str(e))

        # ---------------------------------------------------------- POST
        def do_POST(self):
            try:
                data = self._body()
            except (ValueError, json.JSONDecodeError):
                return self._error(400, "Bad request.")
            path = urlparse(self.path).path
            try:
                if path == "/api/create":
                    room, p = lobby.create(data.get("name", ""))
                    return self._json(200, {"ok": True, "code": room.code, "token": p.token, "seat": p.seat})
                if path == "/api/join":
                    room = lobby.get(data.get("code", ""))
                    p = room.add_player(data.get("name", ""))
                    return self._json(200, {"ok": True, "code": room.code, "token": p.token, "seat": p.seat})
                if path == "/api/leave":
                    lobby.leave(data.get("code", ""), data.get("token", ""))
                    return self._json(200, {"ok": True})
                if path == "/api/action":
                    room = lobby.get(data.get("code", ""))
                    token = data.get("token", "")
                    result = room.act(token, str(data.get("action", "")), data)
                    return self._json(200, {"ok": True, "result": result, "state": room.view_for(token)})
                return self._error(404, "not found")
            except KeyError as e:
                self._error(404, e.args[0])
            except PermissionError as e:
                self._error(403, str(e))
            except GameError as e:
                self._error(400, str(e))

    return Handler


def local_address():
    """This computer's address on the home network (no data is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def make_server(host="0.0.0.0", port=8000, lobby=None):
    lobby = lobby or Lobby()
    lobby.start_ticker()             # joining clock and computer players
    httpd = ThreadingHTTPServer((host, port), make_handler(lobby))
    httpd.daemon_threads = True
    return httpd


def main():
    nums = [a for a in sys.argv[1:] if a.isdigit()]
    port = int(nums[0]) if nums else int(os.environ.get("PORT", 8000))
    try:
        httpd = make_server(port=port)
    except OSError:
        print()
        print("  The game is already running in another black window,")
        print("  maybe the first version. Close that other window, then")
        print("  double-click Start Progressive Rummy.bat again.")
        print()
        return
    here = f"http://localhost:{port}"
    lan = local_address()
    print()
    if HOSTED:
        print(f"  Progressive Rummy (online) is running on port {port}.", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return
    print("  Progressive Rummy (fifth edition, update 4) is running.")
    print(f"  On this computer, open:            {here}")
    if lan:
        print(f"  On phones on the same Wi-Fi, open: http://{lan}:{port}")
    print("  Leave this window open while you play. Close it to stop the game.")
    print()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(here)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
