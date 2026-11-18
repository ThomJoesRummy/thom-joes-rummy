"""Tests for the Exit game button (fifth edition, update 1).  Run:  python test_exit_button.py"""
import json
import threading
import unittest
import urllib.error
import urllib.request

from game import GameError, Lobby, Room
from server import make_server


def started(n, seed=1):
    room = Room("TEST", seed=seed)
    seats = [room.add_player(f"P{i + 1}") for i in range(n)]
    room.act(seats[0].token, "start")
    return room, seats


class LeaveBeforeDealTests(unittest.TestCase):
    def test_seat_is_freed_and_seats_close_up(self):
        lobby = Lobby(seed=3)
        room, tom = lobby.create("Tom")
        wife = room.add_player("Wife")
        lobby.leave(room.code, tom.token)
        self.assertEqual([p.name for p in room.players], ["Wife"])
        self.assertEqual(room.players[0].seat, 0)
        # The Wife now runs the table: she can deal and change the rules.
        room.act(wife.token, "options", {"discard_after_laydown": True})
        self.assertIn(code := room.code, lobby.rooms)
        self.assertTrue(lobby.rooms[code].view_for(wife.token)["can"]["options"])
        room.act(wife.token, "fill_bots")
        self.assertEqual(room.status, "playing")

    def test_last_person_leaving_closes_the_table(self):
        lobby = Lobby(seed=3)
        room, tom = lobby.create("Tom")
        lobby.leave(room.code, tom.token)
        self.assertNotIn(room.code, lobby.rooms)

    def test_old_screen_is_no_longer_at_the_table(self):
        lobby = Lobby(seed=3)
        room, tom = lobby.create("Tom")
        room.add_player("Wife")
        lobby.leave(room.code, tom.token)
        with self.assertRaises(PermissionError):
            room.view_for(tom.token)


class LeaveDuringGameTests(unittest.TestCase):
    def test_computer_takes_the_seat_cards_and_score(self):
        room, seats = started(2)
        tom = room.players[0]
        hand_before = [c.id for c in tom.hand]
        tom.total = 85
        old_token = seats[0].token
        still_people = room.leave(old_token)
        self.assertTrue(still_people)
        p = room.players[0]
        self.assertTrue(p.bot)
        self.assertEqual(p.name, "P1 (computer)")
        self.assertEqual([c.id for c in p.hand], hand_before)
        self.assertEqual(p.total, 85)
        self.assertEqual(len(room.players), 2)
        self.assertIn("left the game", room.log[-1])
        with self.assertRaises(PermissionError):
            room.view_for(old_token)
        # The host's rule switch moved to the person still playing.
        self.assertEqual(room.host, 1)
        self.assertTrue(room.view_for(seats[1].token)["can"]["options"])

    def test_game_keeps_going_when_it_was_their_turn(self):
        room, seats = started(2, seed=5)
        room.bot_delay = 0
        cur = room.current
        leaver = seats[cur]
        room.leave(leaver.token)
        before = room.version
        for _ in range(50):
            room.bot_ready_at = 0
            room.tick()
            if room.current != cur or room.status != "playing":
                break
        self.assertGreater(room.version, before)
        self.assertTrue(room.current != cur or room.status != "playing")

    def test_everyone_leaving_closes_the_game(self):
        lobby = Lobby(seed=3)
        room, tom = lobby.create("Tom")
        wife = room.add_player("Wife")
        room.act(tom.token, "fill_bots")
        lobby.leave(room.code, tom.token)
        self.assertIn(room.code, lobby.rooms)
        lobby.leave(room.code, wife.token)
        self.assertNotIn(room.code, lobby.rooms)

    def test_a_non_host_cannot_change_rules(self):
        room, seats = started(3)
        with self.assertRaises(GameError):
            room.act(seats[1].token, "options", {"discard_after_laydown": True})


class LeaveOverTheWebTests(unittest.TestCase):
    def setUp(self):
        self.lobby = Lobby(seed=9)
        self.httpd = make_server("127.0.0.1", 0, self.lobby)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def post(self, path, data):
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_leave_endpoint(self):
        status, made = self.post("/api/create", {"name": "Tom"})
        self.assertEqual(status, 200)
        code, token = made["code"], made["token"]
        self.assertEqual(self.post("/api/leave", {"code": code, "token": token})[0], 200)
        self.assertNotIn(code, self.lobby.rooms)
        # Leaving again (the table is gone) is an error the page ignores.
        self.assertNotEqual(self.post("/api/leave", {"code": code, "token": token})[0], 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
