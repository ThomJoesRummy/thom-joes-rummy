"""Tests for the online version (Nov 18, 2026): tables nobody looks at close,
and the number of tables has a limit.  Run:  python test_online.py"""
import time
import unittest

import game
from game import GameError, Lobby


class OnlineTests(unittest.TestCase):
    def test_idle_table_closes(self):
        lobby = Lobby(seed=1)
        room, p = lobby.create("Tom")
        lobby.prune(time.time() + 60)
        self.assertIn(room.code, lobby.rooms)
        lobby.prune(time.time() + game.ROOM_IDLE_SECONDS + 5)
        self.assertNotIn(room.code, lobby.rooms)

    def test_looking_keeps_table_open(self):
        lobby = Lobby(seed=2)
        room, p = lobby.create("Tom")
        p.last_seen = time.time() - game.ROOM_IDLE_SECONDS - 10
        room.seat_for(p.token)            # the browser asks for the table
        lobby.prune()
        self.assertIn(room.code, lobby.rooms)

    def test_table_limit(self):
        lobby = Lobby(seed=3)
        for i in range(game.MAX_ROOMS):
            lobby.create(f"P{i}")
        with self.assertRaises(GameError):
            lobby.create("One too many")


if __name__ == "__main__":
    unittest.main()
