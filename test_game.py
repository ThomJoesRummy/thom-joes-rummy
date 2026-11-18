"""Tests for the web app's game rooms (game.py).  Run:  python test_game.py"""
import json
import random
import time
import unittest

from game import GameError, Lobby, Room, arrange_run
from rummy import (ROUNDS, Meld, Rules, _usefulness, check_play_off, find_laydown,
                   hand_points, make_deck, parse_cards)


def room_with(n, seed=1):
    room = Room("TEST", seed=seed)
    seats = [room.add_player(f"P{i + 1}") for i in range(n)]
    return room, seats


def started(n, seed=1):
    room, seats = room_with(n, seed)
    room.act(seats[0].token, "start")
    return room, seats


def all_ids(obj):
    """Every card id anywhere in a view (any dict with an 'id' and 'rank')."""
    out = set()
    if isinstance(obj, dict):
        if "id" in obj and "rank" in obj:
            out.add(obj["id"])
        for v in obj.values():
            out |= all_ids(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= all_ids(v)
    return out


def total_cards(room):
    return (len(room.stock) + len(room.discard) + sum(len(p.hand) for p in room.players)
            + sum(len(m.cards) for m in room.table))


def rig(room, seat, text, ids_from=1000):
    """Give a seat a specific hand (ids kept unique from the real deck)."""
    cards = parse_cards(text)
    from rummy import Card
    room.players[seat].hand = [Card(ids_from + i, c.rank, c.suit) for i, c in enumerate(cards)]
    return room.players[seat].hand


def to_my_play_phase(room, seat):
    """Make it this seat's turn, already drawn (a later turn, not the first)."""
    room.current = seat
    room.phase = "play"
    room.players[seat].turns = 2


class LobbyTests(unittest.TestCase):
    def test_four_players_max_and_names(self):
        room, seats = room_with(4)
        with self.assertRaisesRegex(GameError, "four players"):
            room.add_player("P5")
        room2, _ = room_with(1)
        with self.assertRaisesRegex(GameError, "already has that name"):
            room2.add_player("p1")
        with self.assertRaisesRegex(GameError, "type a name"):
            room2.add_player("   ")

    def test_start_rules(self):
        room, seats = room_with(1)
        with self.assertRaisesRegex(GameError, "at least 2"):
            room.act(seats[0].token, "start")
        room.add_player("P2")
        with self.assertRaisesRegex(GameError, "Only the player who made the table"):
            room.act(room.players[1].token, "start")
        room.act(seats[0].token, "start")
        with self.assertRaisesRegex(GameError, "already started"):
            room.add_player("Late")

    def test_bad_token(self):
        room, _ = room_with(2)
        with self.assertRaises(PermissionError):
            room.act("nope", "start")
        with self.assertRaises(PermissionError):
            room.view_for("nope")

    def test_lobby_codes(self):
        lobby = Lobby(seed=3)
        room, p = lobby.create("Tom")
        self.assertEqual(len(room.code), 4)
        self.assertIs(lobby.get(room.code.lower()), room)
        with self.assertRaises(KeyError):
            lobby.get("ZZZZ" if room.code != "ZZZZ" else "YYYY")
        with self.assertRaises(GameError):
            lobby.create("")
        self.assertEqual(len(lobby.rooms), 1)


class DealTests(unittest.TestCase):
    def test_every_round_and_table_size(self):
        checked = 0
        for n in (2, 3, 4):
            room, seats = started(n, seed=n)
            for r in range(1, 17):
                room._start_round(r)
                dealt = ROUNDS[r][1]
                self.assertTrue(all(len(p.hand) == dealt for p in room.players), (n, r))
                self.assertEqual(len(room.discard), 1)
                self.assertEqual(total_cards(room), 108)          # two decks, 4 jokers
                self.assertEqual(room.dealer, (r - 1) % n)
                self.assertEqual(room.current, (room.dealer + 1) % n)
                ids = [c.id for p in room.players for c in p.hand] + [c.id for c in room.stock + room.discard]
                self.assertEqual(len(ids), len(set(ids)))
                checked += 1
        self.assertEqual(checked, 48)


class PrivacyTests(unittest.TestCase):
    def test_views_hide_other_hands_and_pile(self):
        room, seats = started(4)
        for p in seats:
            view = room.view_for(p.token)
            json.dumps(view)
            seen = all_ids(view)
            mine = {c.id for c in p.hand}
            hidden = {c.id for q in room.players if q is not p for c in q.hand} | {c.id for c in room.stock}
            self.assertEqual({c["id"] for c in view["hand"]}, mine)
            self.assertFalse(seen & hidden, "another player's card or a pile card leaked")
            self.assertEqual([q["cards"] for q in view["players"]], [len(q.hand) for q in room.players])
            self.assertNotIn("token", json.dumps(view["players"]))


class TurnTests(unittest.TestCase):
    def test_turn_order_and_phases(self):
        room, seats = started(3)
        first = room.players[room.current]
        other = room.players[(room.current + 1) % 3]
        with self.assertRaisesRegex(GameError, "turn"):
            room.act(other.token, "draw", {"source": "stock"})
        with self.assertRaisesRegex(GameError, "Draw a card first"):
            room.act(first.token, "discard", {"card": first.hand[0].id})
        with self.assertRaisesRegex(GameError, "pile or the discard"):
            room.act(first.token, "draw", {"source": "elsewhere"})
        res = room.act(first.token, "draw", {"source": "stock"})
        self.assertIn(res["drawn"], {c.id for c in first.hand})
        with self.assertRaisesRegex(GameError, "already drew"):
            room.act(first.token, "draw", {"source": "stock"})
        with self.assertRaisesRegex(GameError, "not in your hand"):
            room.act(first.token, "discard", {"card": other.hand[0].id})
        card = first.hand[0]
        room.act(first.token, "discard", {"card": card.id})
        self.assertIs(room.discard[-1], card)
        self.assertEqual(room.current, other.seat)
        before = len(other.hand)
        top = room.discard[-1]
        room.act(other.token, "draw", {"source": "discard"})
        self.assertIn(top, other.hand)
        self.assertEqual(len(other.hand), before + 1)
        with self.assertRaisesRegex(GameError, "Unknown action"):
            room.act(other.token, "cheat")

    def test_no_discard_pickup_after_laying_down_when_host_turns_it_off(self):
        # Third edition: allowed by default (see test_third_edition.py); the
        # first two editions' rule is still there as a table option.
        room, seats = started(2)
        room.discard_after_laydown = False
        room.current = 0
        room.players[0].laid = True
        with self.assertRaisesRegex(GameError, "draw from the pile"):
            room.act(seats[0].token, "draw", {"source": "discard"})
        self.assertFalse(room.view_for(seats[0].token)["can"]["take_discard"])

    def test_reshuffle_and_stop(self):
        room, seats = started(2)
        room.current = 0
        moved = room.stock[:]
        room.discard.extend(moved)
        room.stock = []
        top = room.discard[-1]
        room.act(seats[0].token, "draw", {"source": "stock"})
        self.assertEqual(room.discard, [top])
        self.assertEqual(total_cards(room), 108)
        # nothing left at all: the hand stops, unscored
        room2, s2 = started(2)
        room2.current = 0
        room2.stock = []
        room2.discard = room2.discard[-1:]
        room2.act(s2[0].token, "draw", {"source": "stock"})
        self.assertEqual(room2.status, "round_over")
        self.assertIsNone(room2.players[0].round_scores[1])
        self.assertEqual(room2.players[0].total, 0)


class LayDownTests(unittest.TestCase):
    def test_round1_two_sets(self):
        room, seats = started(2)
        hand = rig(room, 0, "KC KD KS 7H 7D Joker 3C 9S 10H")
        to_my_play_phase(room, 0)
        ids = [c.id for c in hand]
        with self.assertRaisesRegex(GameError, "Fill all 2 groups"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[:3]]})
        with self.assertRaisesRegex(GameError, "not allowed"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[3:5] + [ids[7]]]})
        with self.assertRaisesRegex(GameError, "picked twice|two groups"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[:3]]})
        room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[3:6]]})
        self.assertTrue(room.players[0].laid)
        self.assertEqual(len(room.table), 2)
        self.assertEqual([str(c) for c in room.players[0].hand], ["3C", "9S", "10H"])
        with self.assertRaisesRegex(GameError, "already laid down"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[6:7], ids[7:8]]})

    def test_same_rank_twice_and_no_discard_left(self):
        room, seats = started(2)
        hand = rig(room, 0, "KC KD KS KH KC KD")
        to_my_play_phase(room, 0)
        ids = [c.id for c in hand]
        with self.assertRaisesRegex(GameError, "no card would be left to discard|same rank"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[3:]]})
        hand = rig(room, 0, "KC KD KS 7H 7D 7S")
        ids = [c.id for c in hand]
        with self.assertRaisesRegex(GameError, "no card would be left to discard"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[3:]]})

    def test_first_turn_keeps_two(self):
        room, seats = started(2)
        hand = rig(room, 0, "KC KD KS 7H 7D 7S 9C")
        room.current, room.phase, room.players[0].turns = 0, "play", 1
        ids = [c.id for c in hand]
        with self.assertRaisesRegex(GameError, "first turn"):
            room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[3:6]]})

    def test_round3_runs_with_ace_low_and_three_wilds_refused(self):
        room, seats = started(2)
        room._start_round(3)
        hand = rig(room, 0, "AH 2C 3H 4H 9S 10S JS QS 3C 6D KC")
        to_my_play_phase(room, 0)
        ids = [c.id for c in hand]
        room.act(seats[0].token, "lay_down", {"groups": [ids[:4], ids[4:8]]})
        run = room.table[0]
        self.assertEqual((run.low, run.high), (1, 4))          # ace low
        self.assertEqual([str(c) for c in run.cards], ["AH", "2C", "3H", "4H"])
        room2, s2 = started(2)
        room2._start_round(3)
        hand = rig(room2, 0, "5H Joker 2C 2D 9S 10S JS QS 3C 6D KC")
        to_my_play_phase(room2, 0)
        ids = [c.id for c in hand]
        with self.assertRaisesRegex(GameError, "wild"):
            room2.act(s2[0].token, "lay_down", {"groups": [ids[:4], ids[4:8]]})

    def test_suggest_then_lay_down(self):
        room, seats = started(2)
        room._start_round(13)
        rig(room, 0, "3H 4H 5H 6H 7H 8H 9S 10S JS QS KS AS 5C 6C Joker 8C 9C 10C 3D 7D")
        to_my_play_phase(room, 0)
        res = room.act(seats[0].token, "suggest")
        self.assertEqual(len(res["groups"]), 3)
        v = room.version
        room.act(seats[0].token, "lay_down", {"groups": res["groups"]})
        self.assertGreater(room.version, v)
        self.assertTrue(room.players[0].laid)
        rig(room, 1, "3C 4D 9H")
        self.assertIsNone(room.act(seats[1].token, "suggest")["groups"])


class ArrangeRunTests(unittest.TestCase):
    def arr(self, text):
        ordered, lo, hi = arrange_run(parse_cards(text), Rules())
        return [str(c) for c in ordered], lo, hi

    def test_arrangements(self):
        self.assertEqual(self.arr("5D Joker 7D 8D"), (["5D", "Joker", "7D", "8D"], 5, 8))   # gap
        self.assertEqual(self.arr("4D 5D 6D Joker"), (["4D", "5D", "6D", "Joker"], 4, 7))   # high end
        self.assertEqual(self.arr("JS QS KS 2C"), (["JS", "QS", "KS", "2C"], 11, 14))      # deuce as ace
        self.assertEqual(self.arr("QS KS AS Joker"), (["Joker", "QS", "KS", "AS"], 11, 14))  # no room above ace
        self.assertEqual(self.arr("4H AH 3H 2C"), (["AH", "2C", "3H", "4H"], 1, 4))
        with self.assertRaises(GameError):
            arrange_run(parse_cards("KH AH 2C 3H"), Rules())                                 # wrap-around


class PlayOffTests(unittest.TestCase):
    def setup_table(self):
        room, seats = started(2)
        room._start_round(3)
        hand = rig(room, 1, "4D 5D 6D Joker 9S 10S JS QS 3C 7D 3D 8H", ids_from=2000)
        to_my_play_phase(room, 1)
        ids = [c.id for c in hand]
        room.act(seats[1].token, "lay_down", {"groups": [ids[:4], ids[4:8]]})
        room.phase, room.current = "draw", 0
        return room, seats

    def test_wild_spot_closed_and_ends_open_on_other_players_run(self):
        room, seats = self.setup_table()
        run_idx = next(i for i, m in enumerate(room.table) if m.suit == "D")
        # seat 0 has laid down too
        hand = rig(room, 0, "7D 3D AS 8S Joker KC 9C 4C", ids_from=3000)
        room.players[0].laid = True
        to_my_play_phase(room, 0)
        ids = {str(c): c.id for c in hand}
        with self.assertRaisesRegex(GameError, "already holds that spot"):
            room.act(seats[0].token, "play_off", {"card": ids["7D"], "meld": run_idx})
        room.act(seats[0].token, "play_off", {"card": ids["3D"], "meld": run_idx})
        self.assertEqual(str(room.table[run_idx].cards[0]), "3D")
        spade = next(i for i, m in enumerate(room.table) if m.suit == "S")
        room.act(seats[0].token, "play_off", {"card": ids["8S"], "meld": spade})
        with self.assertRaisesRegex(GameError, "not next to either end"):
            room.act(seats[0].token, "play_off", {"card": ids["AS"], "meld": spade})
        # Second edition (Tom, Nov 9): wilds may be added after laying down.
        room.act(seats[0].token, "play_off", {"card": ids["Joker"], "meld": spade})
        self.assertEqual(str(room.table[spade].cards[-1]), "Joker")
        with self.assertRaisesRegex(GameError, "wrong suit"):
            room.act(seats[0].token, "play_off", {"card": ids["KC"], "meld": spade})
        with self.assertRaisesRegex(GameError, "Pick a group"):
            room.act(seats[0].token, "play_off", {"card": ids["KC"], "meld": 99})

    def test_must_lay_down_first_and_keep_a_discard(self):
        room, seats = self.setup_table()
        hand = rig(room, 0, "3D 7S", ids_from=3000)
        to_my_play_phase(room, 0)
        run_idx = next(i for i, m in enumerate(room.table) if m.suit == "D")
        with self.assertRaisesRegex(GameError, "Lay down your round.s goal"):
            room.act(seats[0].token, "play_off", {"card": hand[0].id, "meld": run_idx})
        room.players[0].laid = True
        room.act(seats[0].token, "play_off", {"card": hand[0].id, "meld": run_idx})
        hand = rig(room, 0, "8S", ids_from=3100)
        spade = next(i for i, m in enumerate(room.table) if m.suit == "S")
        with self.assertRaisesRegex(GameError, "Keep a card to discard"):
            room.act(seats[0].token, "play_off", {"card": hand[0].id, "meld": spade})

    def test_add_to_set(self):
        room, seats = started(2)
        hand = rig(room, 0, "KC KD KS 7H 7D Joker 3C 9S 10H")
        to_my_play_phase(room, 0)
        ids = [c.id for c in hand]
        room.act(seats[0].token, "lay_down", {"groups": [ids[:3], ids[3:6]]})
        room.phase, room.current = "draw", 1
        h1 = rig(room, 1, "KH 7S 4C", ids_from=4000)
        room.players[1].laid = True
        to_my_play_phase(room, 1)
        kh, s7 = h1[0].id, h1[1].id
        room.act(seats[1].token, "play_off", {"card": kh, "meld": 0})
        room.act(seats[1].token, "play_off", {"card": s7, "meld": 1})
        self.assertEqual(len(room.table[0].cards), 4)
        self.assertEqual(len(room.table[1].cards), 4)


class ScoringTests(unittest.TestCase):
    def test_going_out_scores_and_next_round(self):
        room, seats = started(3)
        room.current = 1
        rig(room, 0, "Joker 2H AS KD 7C", ids_from=5000)          # 50+25+15+10+5 = 105
        rig(room, 2, "3C 4C", ids_from=5100)                      # 10
        last = rig(room, 1, "9H", ids_from=5200)
        room.players[1].laid = True
        room.phase, room.players[1].turns = "play", 3
        room.act(seats[1].token, "discard", {"card": last[0].id})
        self.assertEqual(room.status, "round_over")
        self.assertEqual(room.last_round["points"], {0: 105, 1: 0, 2: 10})
        self.assertEqual([p.total for p in room.players], [105, 0, 10])
        view = room.view_for(seats[2].token)
        self.assertEqual(view["players"][0]["rounds"], {"1": 105})
        self.assertEqual(view["players"][0]["total"], 105)
        self.assertTrue(view["can"]["next_round"])
        with self.assertRaisesRegex(GameError, "No hand"):
            room.act(seats[2].token, "draw", {"source": "stock"})
        room.act(seats[2].token, "next_round")
        self.assertEqual((room.round_no, room.dealer, room.current), (2, 1, 2))
        self.assertTrue(all(len(p.hand) == 11 and not p.laid for p in room.players))
        with self.assertRaisesRegex(GameError, "isn't over"):
            room.act(seats[0].token, "next_round")

    def test_cannot_go_out_on_first_turn(self):
        room, seats = started(2)
        last = rig(room, 1, "9H", ids_from=5200)
        room.current, room.phase, room.players[1].turns = 1, "play", 1
        with self.assertRaisesRegex(GameError, "first turn"):
            room.act(seats[1].token, "discard", {"card": last[0].id})

    def test_round_16_ends_game(self):
        room, seats = started(2)
        room._start_round(16)
        last = rig(room, 0, "9H", ids_from=5200)
        room.current, room.phase, room.players[0].turns = 0, "play", 4
        room.act(seats[0].token, "discard", {"card": last[0].id})
        self.assertEqual(room.status, "game_over")
        self.assertFalse(room.view_for(seats[0].token)["can"]["next_round"])


def bot_turn(room, p, rng):
    """One turn through the public actions, chosen with the engine's helpers."""
    req = ROUNDS[room.round_no][0]
    top = room.discard[-1] if room.discard else None
    take = (top is not None and not p.laid and
            (top.wild or find_laydown(p.hand + [top], req) is not None))
    room.act(p.token, "draw", {"source": "discard" if take else "stock"})
    if room.status != "playing":
        return
    keep = 2 if p.turns == 1 else 1
    if not p.laid:
        found = find_laydown(p.hand, req)
        if found and len(found[1]) >= keep:
            room.act(p.token, "lay_down", {"groups": [[c.id for c in m.cards] for m in found[0]]})
    if p.laid:
        progress = True
        while progress and len(p.hand) > keep:
            progress = False
            for c in sorted(p.hand, key=lambda c: -c.points):
                for i, m in enumerate(room.table):
                    if check_play_off(c, m)[0] is not None:
                        room.act(p.token, "play_off", {"card": c.id, "meld": i})
                        progress = True
                        break
                if progress:
                    break
    if p.laid:
        choice = max(p.hand, key=lambda c: (c.points, rng.random()))
    else:
        choice = min(p.hand, key=lambda c: (_usefulness(c, p.hand, req), -c.points, rng.random()))
    room.act(p.token, "discard", {"card": choice.id})


class FullGameTests(unittest.TestCase):
    """Whole 16-round games played only through room.act, checking card
    counts, table legality and privacy after every turn."""

    def play(self, n, seed, cap=500):
        room, seats = started(n, seed=seed)
        rng = random.Random(seed)
        finished = 0
        while room.status != "game_over":
            turns = 0
            while room.status == "playing" and turns < cap:
                bot_turn(room, room.players[room.current], rng)
                turns += 1
                self.assertEqual(total_cards(room), 108)
                for q in seats:
                    view = room.view_for(q.token)
                    hidden = {c.id for o in room.players if o is not q for c in o.hand}
                    self.assertFalse(all_ids(view) & hidden)
            if room.status == "playing":           # bots got stuck: stop it, unscored
                with room.lock:
                    room._finish_round(None, "test stop")
            elif room.last_round["winner"] is not None:
                finished += 1
                self.assertEqual(len(room.players[room.last_round["winner"]].hand), 0)
            if room.status == "round_over":
                room.act(seats[-1].token, "next_round")
        for q in room.players:
            scored = [v for v in q.round_scores.values() if v is not None]
            self.assertEqual(sum(scored), q.total)
            self.assertEqual(len(q.round_scores), 16)
        return finished

    def test_full_games(self):
        results = {}
        for n, seed in ((2, 11), (3, 12), (4, 13), (4, 14)):
            results[(n, seed)] = self.play(n, seed)
        print("\n  rounds that ended with a player going out (of 16):",
              ", ".join(f"{n} players seed {s}: {f}" for (n, s), f in results.items()))
        self.assertTrue(all(f >= 8 for f in results.values()), results)


class ClockAndBotTests(unittest.TestCase):
    """Tom's joining rules: 30 seconds to fill the seats; if they aren't all
    filled, the clock starts over once; then computer players take the empty
    seats and keep them for the whole game."""

    def lobby_room(self, humans=1, seed=5):
        room = Room("TEST", seed=seed, lobby_seconds=30, bot_delay=0)
        seats = [room.add_player(f"P{i + 1}") for i in range(humans)]
        return room, seats

    def test_clock_resets_once_then_bots_fill_and_deal(self):
        room, seats = self.lobby_room(humans=2)
        t0 = room.deadline - 30
        self.assertEqual(room.seconds_left(t0 + 10), 20)
        self.assertFalse(room.tick(t0 + 29))
        self.assertEqual(room.status, "lobby")
        self.assertTrue(room.tick(t0 + 30.1))                 # first 30 s over: clock starts over
        self.assertEqual((room.status, room.window, len(room.players)), ("lobby", 2, 2))
        self.assertEqual(room.seconds_left(t0 + 31), 29)
        self.assertIn("starts over", room.log[-1])
        room.add_player("P3")                                 # someone joins in the second window
        self.assertFalse(room.tick(t0 + 59))
        self.assertTrue(room.tick(t0 + 60.2))                 # second window over: computer fills seat 4
        self.assertEqual(room.status, "playing")
        self.assertEqual([p.bot for p in room.players], [False, False, False, True])
        self.assertEqual(room.players[3].name, "Betty (computer)")
        self.assertTrue(all(len(p.hand) == 11 for p in room.players))
        with self.assertRaisesRegex(GameError, "keep the empty seats"):
            room.add_player("Late")
        view = room.view_for(seats[0].token)
        self.assertEqual([q["bot"] for q in view["players"]], [False, False, False, True])
        self.assertIsNone(view["seconds_left"])

    def test_one_person_gets_three_computers(self):
        room, seats = self.lobby_room(humans=1)
        t0 = room.deadline - 30
        room.tick(t0 + 31)
        room.tick(t0 + 62)
        self.assertEqual(sum(p.bot for p in room.players), 3)
        self.assertEqual(room.status, "playing")

    def test_full_table_deals_without_waiting(self):
        room, seats = self.lobby_room(humans=3)
        room.add_player("P4")
        self.assertLessEqual(room.deadline - time.time(), 3.01)
        room.tick(room.deadline + 0.1)
        self.assertEqual(room.status, "playing")
        self.assertFalse(any(p.bot for p in room.players))
        self.assertEqual(room.window, 1)

    def test_host_can_fill_now(self):
        room, seats = self.lobby_room(humans=2)
        self.assertTrue(room.view_for(seats[0].token)["can"]["fill_bots"])
        self.assertFalse(room.view_for(seats[1].token)["can"]["fill_bots"])
        with self.assertRaisesRegex(GameError, "Only the player who made the table"):
            room.act(seats[1].token, "fill_bots")
        room.act(seats[0].token, "fill_bots")
        self.assertEqual(room.status, "playing")
        self.assertEqual([p.name for p in room.players][2:], ["Betty (computer)", "Max (computer)"])

    def test_bots_hide_their_hands_and_wait_their_turn(self):
        room, seats = self.lobby_room(humans=1)
        room.act(seats[0].token, "fill_bots")
        view = room.view_for(seats[0].token)
        hidden = {c.id for q in room.players[1:] for c in q.hand}
        self.assertFalse(all_ids(view) & hidden)
        # round 1: seat 1 (a computer) is left of the dealer and goes first
        self.assertEqual(room.current, 1)
        moves = 0
        while room.current != 0 and room.status == "playing":
            self.assertTrue(room.tick(time.time() + 10))
            moves += 1
        self.assertGreaterEqual(moves, 6)                    # three computers drew and discarded
        self.assertFalse(room.tick(time.time() + 10))        # a person's turn: computers wait
        self.assertEqual(room.current, 0)

    def test_bot_pause_between_moves(self):
        room = Room("TEST", seed=2, lobby_seconds=30, bot_delay=1.2)
        host = room.add_player("Tom")
        room.act(host.token, "fill_bots")
        now = time.time()
        self.assertFalse(room.tick(now + 0.5))               # too soon after the deal
        self.assertTrue(room.tick(now + 1.5))

    def test_whole_game_one_person_three_computers(self):
        """16 rounds with three computers; the person's moves are made by
        the test bot.  Computer seats never change."""
        finished = 0
        room, seats = self.lobby_room(humans=1, seed=8)
        room.act(seats[0].token, "fill_bots")
        rng = random.Random(8)
        names = [p.name for p in room.players]
        while room.status != "game_over":
            steps = 0
            while room.status == "playing" and steps < 4000:
                if room.current == 0:
                    bot_turn(room, room.players[0], rng)
                else:
                    room.tick(time.time() + 10)
                steps += 1
                self.assertEqual(total_cards(room), 108)
                for c in room.table:
                    from rummy import meld_consistent
                    self.assertTrue(meld_consistent(c, room.rules))
            self.assertNotEqual(room.status, "playing", "a round never ended")
            if room.last_round["winner"] is not None:
                finished += 1
            if room.status == "round_over":
                room.act(seats[0].token, "next_round")
            self.assertEqual([p.name for p in room.players], names)
        print(f"\n  1 person + 3 computers: {finished} of 16 rounds ended with someone going out;"
              f" totals {[p.total for p in room.players]}")
        self.assertGreaterEqual(finished, 10)
        for q in room.players:
            self.assertEqual(len(q.round_scores), 16)


if __name__ == "__main__":
    unittest.main(verbosity=2)
