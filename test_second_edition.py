"""Checks for the second edition's new moves.  Run:  python test_second_edition.py

Covers what Tom found in his first play-test (Nov 8-9, 2026):
  * extra new groups (for example three nines) after the goal is down
  * deuces and jokers added as wilds to groups on the table
  * natural cards added to OTHER players' groups
  * picking the goal's cards in one go, and discarding afterwards
"""
import unittest

from game import GameError, Room, play_off_where
from rummy import Card, Meld, Rules, meld_consistent, parse_cards


def started(n, seed=1):
    room = Room("TEST", seed=seed)
    seats = [room.add_player(f"P{i + 1}") for i in range(n)]
    room.act(seats[0].token, "start")
    return room, seats


def rig(room, seat, text, ids_from=1000):
    cards = parse_cards(text)
    room.players[seat].hand = [Card(ids_from + i, c.rank, c.suit) for i, c in enumerate(cards)]
    return {str(c): c.id for c in room.players[seat].hand}, room.players[seat].hand


def my_play(room, seat, turns=2):
    room.current, room.phase = seat, "play"
    room.players[seat].turns = turns


def ids_of(hand, names):
    """Card ids for names, using each card once (two decks have repeats)."""
    left = list(hand)
    out = []
    for n in names.split():
        c = next(c for c in left if str(c) == n)
        left.remove(c)
        out.append(c.id)
    return out


def total_cards(room):
    return (len(room.stock) + len(room.discard) + sum(len(p.hand) for p in room.players)
            + sum(len(m.cards) for m in room.table))


class TomsHand(unittest.TestCase):
    """Round 1: Tom lays eights and kings, later holds three nines and two deuces."""

    def setUp(self):
        self.room, self.seats = started(2)
        r, s = self.room, self.seats
        _, hand = rig(r, 0, "8C 8D 8S KC KD KH 5S 6H 10C", 1000)
        my_play(r, 0)
        r.act(s[0].token, "lay_down", {"cards": ids_of(hand, "8C 8D 8S KC KD KH")})
        self.assertTrue(r.players[0].laid)
        r.current, r.phase = 1, "draw"

    def test_three_nines_then_deuces_then_discard(self):
        r, s = self.room, self.seats
        _, hand = rig(r, 0, "9C 9D 9H 2S 2H 4C", 2000)
        my_play(r, 0)
        v = r.view_for(s[0].token)
        self.assertTrue(v["can"]["new_group"])
        # deuces can go on the eights and the kings
        deuce = ids_of(hand, "2S")[0]
        self.assertEqual(sorted(v["targets"][str(deuce)]), [0, 1])
        r.act(s[0].token, "new_group", {"cards": ids_of(hand, "9C 9D 9H")})
        self.assertEqual(len(r.table), 3)
        self.assertEqual(r.table[2].kind, "set")
        self.assertEqual(r.table[2].owner, 0)
        r.act(s[0].token, "play_off", {"card": deuce, "meld": 2})       # deuce on the nines
        r.act(s[0].token, "play_off", {"card": ids_of(hand, "2H")[0], "meld": 2})
        self.assertEqual(len(r.table[2].cards), 5)
        self.assertEqual([str(c) for c in r.players[0].hand], ["4C"])
        r.act(s[0].token, "discard", {"card": ids_of(hand, "4C")[0]})   # goes out
        self.assertEqual(r.status, "round_over")
        self.assertEqual(r.last_round["winner"], 0)

    def test_nines_with_deuces_in_one_new_group(self):
        r, s = self.room, self.seats
        _, hand = rig(r, 0, "9C 9D 9H 2S 2H 4C", 2000)
        my_play(r, 0)
        r.act(s[0].token, "new_group", {"cards": ids_of(hand, "9C 9D 9H 2S 2H")})
        self.assertEqual(len(r.table[2].cards), 5)
        r.act(s[0].token, "discard", {"card": ids_of(hand, "4C")[0]})
        self.assertEqual(r.status, "round_over")

    def test_third_wild_refused(self):
        r, s = self.room, self.seats
        _, hand = rig(r, 0, "2S 2H Joker 4C 5C", 2000)
        my_play(r, 0)
        r.act(s[0].token, "play_off", {"card": ids_of(hand, "2S")[0], "meld": 0})
        r.act(s[0].token, "play_off", {"card": ids_of(hand, "2H")[0], "meld": 0})
        with self.assertRaisesRegex(GameError, "already has 2 wild cards"):
            r.act(s[0].token, "play_off", {"card": ids_of(hand, "Joker")[0], "meld": 0})
        v = r.view_for(s[0].token)
        self.assertEqual(v["targets"][str(ids_of(hand, "Joker")[0])], [1])   # kings still open

    def test_natural_and_wild_on_other_players_set(self):
        r, s = self.room, self.seats
        r.players[1].laid = True
        _, hand = rig(r, 1, "8H KS Joker 7D 7C", 3000)
        my_play(r, 1)
        v = r.view_for(s[1].token)
        self.assertEqual(v["targets"][str(ids_of(hand, "8H")[0])], [0])
        r.act(s[1].token, "play_off", {"card": ids_of(hand, "8H")[0], "meld": 0})
        r.act(s[1].token, "play_off", {"card": ids_of(hand, "KS")[0], "meld": 1})
        r.act(s[1].token, "play_off", {"card": ids_of(hand, "Joker")[0], "meld": 1})
        self.assertEqual(r.table[0].owner, 0)            # still Tom's group
        self.assertEqual(len(r.table[0].cards), 4)
        self.assertEqual(len(r.table[1].cards), 5)
        self.assertIn("P2 added Joker to P1's Set of Ks", r.log[-1])

    def test_new_group_needs_goal_first_and_a_card_kept(self):
        r, s = self.room, self.seats
        _, hand = rig(r, 1, "9C 9D 9H 4C", 3000)
        my_play(r, 1)
        with self.assertRaisesRegex(GameError, "First lay down this round's goal"):
            r.act(s[1].token, "new_group", {"cards": ids_of(hand, "9C 9D 9H")})
        r.players[1].laid = True
        with self.assertRaisesRegex(GameError, "Keep a card"):
            r.act(s[1].token, "new_group", {"cards": ids_of(hand, "9C 9D 9H 4C")})

    def test_bad_new_groups(self):
        r, s = self.room, self.seats
        _, hand = rig(r, 0, "9C 9D 5H 6H 7H 2S Joker 4C 10D", 2000)
        my_play(r, 0)
        with self.assertRaisesRegex(GameError, "at least 3"):
            r.act(s[0].token, "new_group", {"cards": ids_of(hand, "9C 9D")})
        with self.assertRaisesRegex(GameError, "at least 4"):
            r.act(s[0].token, "new_group", {"cards": ids_of(hand, "5H 6H 7H")})
        with self.assertRaisesRegex(GameError, "a set is 3 or more"):
            r.act(s[0].token, "new_group", {"cards": ids_of(hand, "9C 5H 4C")})
        with self.assertRaisesRegex(GameError, "don't make a new group"):
            r.act(s[0].token, "new_group", {"cards": ids_of(hand, "9C 9D 2S Joker")[:2] + ids_of(hand, "10D")})
        self.assertEqual(len(r.table), 2)
        self.assertEqual(len(r.players[0].hand), 9)       # nothing left the hand
        r.act(s[0].token, "new_group", {"cards": ids_of(hand, "5H 6H 7H Joker")})
        self.assertEqual(r.table[2].kind, "run")
        self.assertTrue(meld_consistent(r.table[2], r.rules))


class WildsOnRuns(unittest.TestCase):
    def meld(self, text, low, high):
        cards = parse_cards(text)
        return Meld("run", cards, suit="H", low=low, high=high)

    def test_wild_goes_high_then_low(self):
        rules = Rules()
        j = Card(900, 0, None)
        self.assertEqual(play_off_where(j, self.meld("5H 6H 7H 8H", 5, 8), rules)[0], "high")
        self.assertEqual(play_off_where(j, self.meld("JH QH KH AH", 11, 14), rules)[0], "low")
        self.assertEqual(play_off_where(j, self.meld("5H 6H 7H 8H", 5, 8), rules, "low")[0], "low")
        two = Meld("run", parse_cards("2C Joker 5H 6H"), suit="H", low=3, high=6)
        self.assertIsNone(play_off_where(j, two, rules)[0])          # two wilds already
        full = Meld("run", parse_cards("AH 2C 3H 4H 5H 6H 7H 8H 9H 10H JH QH KH"), suit="H", low=1, high=13)
        self.assertIsNone(play_off_where(j, full, rules)[0])         # 13 cards: as long as a run can be

    def test_wild_low_end_closed_at_ace(self):
        rules = Rules()
        j = Card(900, 0, None)
        m = Meld("run", parse_cards("AH 3H 4H 5H"), suit="H", low=1, high=4)
        # (not a real run, only checks the end choice)
        self.assertEqual(play_off_where(j, m, rules)[0], "high")
        self.assertEqual(play_off_where(j, m, rules, "low")[1], "that end of the run is already full")

    def test_wild_onto_run_in_game_and_spot_rules_kept(self):
        room, seats = started(2)
        room._start_round(3)
        _, h = rig(room, 1, "4D 5D 6D 7D 9S 10S JS QS 3C 8H", 2000)
        my_play(room, 1)
        room.act(seats[1].token, "lay_down", {"cards": ids_of(h, "4D 5D 6D 7D 9S 10S JS QS")})
        room.current, room.phase = 0, "draw"
        room.players[0].laid = True
        _, h0 = rig(room, 0, "Joker 2C 2H 8D KC", 3000)
        my_play(room, 0)
        d = next(i for i, m in enumerate(room.table) if m.suit == "D")
        room.act(seats[0].token, "play_off", {"card": ids_of(h0, "Joker")[0], "meld": d})   # takes the 8 spot
        self.assertEqual(room.table[d].high, 8)
        room.act(seats[0].token, "play_off", {"card": ids_of(h0, "2C")[0], "meld": d, "end": "low"})
        self.assertEqual(room.table[d].low, 3)
        with self.assertRaisesRegex(GameError, "already has 2 wild"):
            room.act(seats[0].token, "play_off", {"card": ids_of(h0, "2H")[0], "meld": d})
        with self.assertRaisesRegex(GameError, "already holds that spot"):
            room.act(seats[0].token, "play_off", {"card": ids_of(h0, "8D")[0], "meld": d})
        self.assertTrue(meld_consistent(room.table[d], room.rules))


class PickToLayDown(unittest.TestCase):
    def test_extra_picked_card_stays_in_hand(self):
        room, seats = started(2)
        _, h = rig(room, 0, "8C 8D 8S KC KD KH 8H 5S 6H", 1000)
        my_play(room, 0)
        room.act(seats[0].token, "lay_down", {"cards": ids_of(h, "8C 8D 8S KC KD KH 8H")})
        self.assertEqual(sum(len(m.cards) for m in room.table), 6)
        self.assertEqual(len(room.players[0].hand), 3)

    def test_whole_hand_pick_keeps_a_discard(self):
        room, seats = started(2)
        _, h = rig(room, 0, "8C 8D 8S KC KD KH 8H", 1000)
        my_play(room, 0)
        room.act(seats[0].token, "lay_down", {"cards": [c.id for c in h]})
        self.assertEqual(len(room.players[0].hand), 1)

    def test_exact_goal_with_nothing_left_refused(self):
        room, seats = started(2)
        _, h = rig(room, 0, "8C 8D 8S KC KD KH", 1000)
        my_play(room, 0)
        with self.assertRaisesRegex(GameError, "keep a card"):
            room.act(seats[0].token, "lay_down", {"cards": [c.id for c in h]})

    def test_wrong_pick_explains_goal(self):
        room, seats = started(2)
        _, h = rig(room, 0, "8C 8D KC KD KH 5S 6H", 1000)
        my_play(room, 0)
        with self.assertRaisesRegex(GameError, "don't make this round's goal \\(2 sets of 3\\)"):
            room.act(seats[0].token, "lay_down", {"cards": ids_of(h, "8C 8D KC KD KH")})
        with self.assertRaisesRegex(GameError, "Pick the cards"):
            room.act(seats[0].token, "lay_down", {"cards": []})

    def test_round_9_mixed_goal_by_pick(self):
        room, seats = started(3)
        room._start_round(9)
        _, h = rig(room, 0, "3C 3D 3H 7C 7S Joker QC QD QS 4H 5H 6H 2D 8H KS AC", 1000)
        my_play(room, 0)
        room.act(seats[0].token, "lay_down", {"cards": [c.id for c in h]})
        kinds = sorted(m.kind for m in room.table)
        self.assertEqual(kinds, ["run", "set", "set", "set"])
        self.assertTrue(all(meld_consistent(m, room.rules) for m in room.table))
        self.assertGreaterEqual(len(room.players[0].hand), 1)


class ViewAndBots(unittest.TestCase):
    def test_view_labels_and_ownership(self):
        room, seats = started(2)
        _, h = rig(room, 0, "8C 8D 2S KC KD KH 5S 6H", 1000)
        my_play(room, 0)
        room.act(seats[0].token, "lay_down", {"cards": ids_of(h, "8C 8D 2S KC KD KH")})
        v = room.view_for(seats[1].token)
        self.assertEqual([m["owner"] for m in v["table"]], [0, 0])
        self.assertEqual(sorted(m["label"] for m in v["table"]), ["Set of 8s", "Set of Ks"])
        self.assertEqual(sorted(m["wilds"] for m in v["table"]), [0, 1])
        self.assertEqual(v["targets"], {})                 # not P2's turn
        self.assertNotIn("hand", [k for k in v["players"][0]])

    def test_bots_lay_extra_groups_and_wilds_whole_games(self):
        from game import Lobby
        extra_groups = wild_adds = finished = stopped = 0
        import time
        for seed in (21, 22):
            room = Room("BOTS", seed=seed, lobby_seconds=0, bot_delay=0)
            person = room.add_player("Tom")
            room.act(person.token, "fill_bots")
            room.players[0].bot = True               # let a computer play Tom's seat too
            before = total_cards(room)
            t = time.time() + 1e6
            steps = 0
            while room.status != "game_over":
                steps += 1
                self.assertLess(steps, 200000)
                if room.status == "round_over":
                    room.act(person.token, "next_round")
                    before = total_cards(room)
                    continue
                t += 10
                n_table = len(room.table)
                wilds = sum(c.wild for m in room.table for c in m.cards)
                if room.status == "round_over" or room.status == "game_over":
                    continue
                was = room.status
                room.tick(now=t)
                if room.status in ("round_over", "game_over") and was == "playing":
                    finished += room.last_round["winner"] is not None
                    stopped += room.last_round["winner"] is None
                if room.status == "playing":
                    self.assertEqual(total_cards(room), before)
                    self.assertTrue(all(meld_consistent(m, room.rules) for m in room.table))
                    self.assertTrue(all(sum(c.wild for c in m.cards) <= 2 for m in room.table))
                    if len(room.table) == n_table + 1 and any(p.laid for p in room.players) and \
                            room.log and "new group" in room.log[-1]:
                        extra_groups += 1
                    if sum(c.wild for m in room.table for c in m.cards) > wilds and "added" in room.log[-1]:
                        wild_adds += 1
        print(f"\n  two 16-round all-computer games: {finished} of 32 rounds ended with someone "
              f"going out, {stopped} stopped; extra groups laid {extra_groups}, wilds added {wild_adds}")
        self.assertGreater(extra_groups, 0)
        self.assertGreater(wild_adds, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
