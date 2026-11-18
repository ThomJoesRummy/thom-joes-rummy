"""Tests for fifth edition update 4: "What happened" starts clean.  Run:  python test_update4.py"""
import unittest

from game import Room


def started(n, seed=1):
    room = Room("TEST", seed=seed)
    seats = [room.add_player(f"P{i + 1}") for i in range(n)]
    room.act(seats[0].token, "start")
    return room, seats


class CleanLogTests(unittest.TestCase):
    def test_first_round_drops_the_sign_in_lines(self):
        room = Room("TEST", seed=2)
        seats = [room.add_player(f"P{i + 1}") for i in range(3)]
        room.log.append("P2 sat down.")
        room.act(seats[0].token, "start")
        self.assertEqual(len(room.log), 1)
        self.assertTrue(room.log[0].startswith("Round 1:"), room.log)

    def test_next_round_starts_clean(self):
        room, seats = started(2)
        with room.lock:
            for i in range(30):
                room.log.append(f"line {i}")
            room.status = "round_over"
        room.act(seats[0].token, "next_round")
        self.assertEqual(room.round_no, 2)
        self.assertEqual(len(room.log), 1)
        self.assertTrue(room.log[0].startswith("Round 2:"), room.log)

    def test_log_still_grows_during_a_round(self):
        room, seats = started(2)
        with room.lock:
            room._bump("P1 drew a card.")
        self.assertEqual(len(room.log), 2)
        self.assertEqual(room.view_for(seats[0].token)["log"][-1], "P1 drew a card.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
