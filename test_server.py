"""Tests for the web server (server.py), talking to it over real HTTP the way
separate phones would.  Run:  python test_server.py"""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from game import Lobby
from server import make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lobby = Lobby(seed=7)
        cls.httpd = make_server("127.0.0.1", 0, cls.lobby)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read(), r.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("Content-Type")

    def j(self, path, body=None):
        status, raw, _ = self.call(path, body)
        return status, json.loads(raw)

    def table_of_four(self):
        s, host = self.j("/api/create", {"name": "Tom"})
        self.assertEqual(s, 200)
        code = host["code"]
        players = [host]
        for name in ("Wife", "Buddy", "Buddy's wife"):
            s, p = self.j("/api/join", {"code": code.lower(), "name": name})
            self.assertEqual(s, 200, p)
            players.append(p)
        return code, players

    def state(self, code, p, since=None):
        q = f"/api/state?code={code}&token={p['token']}" + ("" if since is None else f"&since={since}")
        return self.j(q)

    def test_static_files(self):
        for path, kind in (("/", "text/html"), ("/static/app.js", "javascript"),
                           ("/static/style.css", "text/css"), ("/?table=ABCD", "text/html")):
            s, raw, ctype = self.call(path)
            self.assertEqual(s, 200, path)
            self.assertIn(kind, ctype)
            self.assertGreater(len(raw), 500)
        for bad in ("/static/../game.py", "/static/%2e%2e/server.py", "/nothing.html"):
            self.assertEqual(self.call(bad)[0], 404, bad)

    def test_full_table_and_privacy_over_http(self):
        code, players = self.table_of_four()
        s, err = self.j("/api/join", {"code": code, "name": "Fifth"})
        self.assertEqual((s, err["ok"]), (400, False))
        self.assertIn("four players", err["error"])
        s, err = self.j("/api/action", {"code": code, "token": players[1]["token"], "action": "start"})
        self.assertEqual(s, 400)
        s, res = self.j("/api/action", {"code": code, "token": players[0]["token"], "action": "start"})
        self.assertEqual(s, 200)
        room = self.lobby.get(code)
        views = [self.state(code, p)[1]["state"] for p in players]
        for seat, v in enumerate(views):
            self.assertEqual(v["you"], seat)
            self.assertEqual(len(v["hand"]), 11)          # round 1 deals 11
            raw = json.dumps(v)
            for other in room.players:
                if other.seat != seat:
                    for c in other.hand:
                        self.assertNotIn(f'"id": {c.id},', raw)
                    self.assertNotIn(other.token, raw)
            self.assertEqual([q["cards"] for q in v["players"]], [11, 11, 11, 11])
            self.assertEqual([q["total"] for q in v["players"]], [0, 0, 0, 0])

    def test_long_poll_wakes_other_players(self):
        code, players = self.table_of_four()
        self.j("/api/action", {"code": code, "token": players[0]["token"], "action": "start"})
        v = self.state(code, players[2])[1]["state"]
        mover = players[v["current"]]
        got = {}

        def watch():
            t0 = time.time()
            got["state"] = self.state(code, players[2], since=v["version"])[1]["state"]
            got["waited"] = time.time() - t0

        t = threading.Thread(target=watch)
        t.start()
        time.sleep(0.6)
        self.assertTrue(t.is_alive(), "the watcher should still be waiting")
        s, _ = self.j("/api/action", {"code": code, "token": mover["token"], "action": "draw", "source": "stock"})
        self.assertEqual(s, 200)
        t.join(10)
        self.assertFalse(t.is_alive())
        self.assertGreater(got["state"]["version"], v["version"])
        self.assertEqual(got["state"]["phase"], "play")
        self.assertLess(got["waited"], 5)
        self.assertGreater(got["waited"], 0.5)
        print(f"\n  long poll woke after {got['waited']:.2f}s (action sent at 0.6s)")

    def test_errors(self):
        code, players = self.table_of_four()
        tok = players[0]["token"]
        self.j("/api/action", {"code": code, "token": tok, "action": "start"})
        v = self.state(code, players[0])[1]["state"]
        not_turn = players[(v["current"] + 1) % 4]
        s, e = self.j("/api/action", {"code": code, "token": not_turn["token"], "action": "draw", "source": "stock"})
        self.assertEqual(s, 400)
        self.assertIn("turn", e["error"])
        self.assertEqual(self.state(code, {"token": "forged"})[0], 403)
        self.assertEqual(self.j("/api/action", {"code": code, "token": "forged", "action": "start"})[0], 403)
        self.assertEqual(self.j("/api/action", {"code": "QQQQ" if code != "QQQQ" else "WWWW",
                                                "token": tok, "action": "start"})[0], 404)
        self.assertEqual(self.j("/api/create", {"name": ""})[0], 400)
        s, raw, _ = self.call("/api/action", None)
        req = urllib.request.Request(self.base + "/api/action", data=b"not json", method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("bad JSON accepted")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_a_hand_played_over_http(self):
        """Each player draws and discards in turn through HTTP for one lap,
        and every player's view stays in step."""
        code, players = self.table_of_four()
        self.j("/api/action", {"code": code, "token": players[0]["token"], "action": "start"})
        for _ in range(4):
            v = self.state(code, players[0])[1]["state"]
            p = players[v["current"]]
            s, r = self.j("/api/action", {"code": code, "token": p["token"], "action": "draw", "source": "stock"})
            self.assertEqual(s, 200, r)
            mine = r["state"]["hand"]
            self.assertEqual(len(mine), 12)
            s, r = self.j("/api/action", {"code": code, "token": p["token"], "action": "discard",
                                          "card": r["result"]["drawn"]})
            self.assertEqual(s, 200, r)
            self.assertEqual(len(r["state"]["hand"]), 11)
        views = [self.state(code, p)[1]["state"] for p in players]
        self.assertEqual(len({v["version"] for v in views}), 1)
        self.assertEqual(len({json.dumps(v["discard_top"]) for v in views}), 1)
        self.assertEqual(views[0]["current"], 1)         # back to left of the dealer


if __name__ == "__main__":
    unittest.main(verbosity=2)
