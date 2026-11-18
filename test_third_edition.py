"""Third edition checks, from Tom's play-test of the second edition (Nov 9, 2026).

  1. The top discard can be taken after you have laid down your goal (one
     draw a turn, pile OR top discard), e.g. the 7 of clubs onto your own
     3-4-5-6 of clubs in round 3.
  2. Computer moves are easy to follow: each player's moves this turn (or
     last turn), who discarded the top card, which table cards are new since
     your last turn, a longer "What happened" list and a slower-computers
     button.  Nothing private (a card drawn from the pile, a hand) shows.
  3. Nothing from the earlier editions is lost (the old tests still run).

Run:  python test_third_edition.py
"""
import json
import time
import unittest

from game import BOT_DELAY, SLOW_BOT_DELAY, GameError, Room
from rummy import Card, parse_cards


def new_room(n=4, seed=3, round_no=3):
    room = Room("TEST", seed=seed, bot_delay=0)
    seats = [room.add_player(f"P{i + 1}") for i in range(n)]
    room.act(seats[0].token, "start")
    with room.lock:
        room._start_round(round_no)
    return room, seats


def rig(room, seat, text, base):
    cards = [Card(base + i, c.rank, c.suit) for i, c in enumerate(parse_cards(text))]
    room.players[seat].hand = cards
    return cards


def ids(cards, text):
    want = [str(c) for c in parse_cards(text)]
    out, pool = [], list(cards)
    for w in want:
        c = next(c for c in pool if str(c) == w)
        pool.remove(c)
        out.append(c.id)
    return out


def play_phase(room, seat, turns=2):
    room.current, room.phase = seat, "play"
    room.players[seat].turns = turns


def draw_phase(room, seat, turns=2):
    room.current, room.phase = seat, "draw"
    room.players[seat].turns = turns


class DiscardAfterLayingDown(unittest.TestCase):
    """Tom's report: rounds 3 and 4, after laying down only the draw pile was
    offered.  The second edition refused it on purpose (game.py and the page
    both followed an earlier rule); the third edition allows it."""

    def lay_down_round3(self):
        room, s = new_room(round_no=3)
        hand = rig(room, 0, "3C 4C 5C 6C 8H 9H 10H JH KD 4H QS", 5000)
        play_phase(room, 0)
        room.act(s[0].token, "lay_down", {"groups": [ids(hand, "3C 4C 5C 6C"), ids(hand, "8H 9H 10H JH")]})
        room.act(s[0].token, "discard", {"card": ids(hand, "QS")[0]})
        self.assertTrue(room.players[0].laid)
        return room, s

    def test_before_laying_down_both_offered(self):
        room, s = new_room(round_no=3)
        rig(room, 0, "3C 4C 5C 8H 9H KD QS", 5000)
        room.discard.append(Card(5100, 6, "C"))
        draw_phase(room, 0)
        v = room.view_for(s[0].token)
        self.assertTrue(v["can"]["draw"])
        self.assertTrue(v["can"]["take_discard"])
        room.act(s[0].token, "draw", {"source": "discard"})
        self.assertIn("6C", [str(c) for c in room.players[0].hand])

    def test_after_laying_down_seven_of_clubs_onto_own_run(self):
        room, s = self.lay_down_round3()
        # The others play; then the 7 of clubs is on top at Tom's next turn.
        seven = Card(5200, 7, "C")
        room.discard.append(seven)
        draw_phase(room, 0, turns=3)
        v = room.view_for(s[0].token)
        self.assertTrue(v["can"]["draw"], "draw pile offered")
        self.assertTrue(v["can"]["take_discard"], "top discard offered after laying down")
        before_stock = len(room.stock)
        room.act(s[0].token, "draw", {"source": "discard"})
        self.assertEqual(len(room.stock), before_stock, "pile untouched")
        self.assertIn(seven, room.players[0].hand)
        self.assertEqual(room.phase, "play")
        run = next(i for i, m in enumerate(room.table) if m.owner == 0 and m.suit == "C")
        v = room.view_for(s[0].token)
        self.assertIn(run, v["targets"]["5200"], "7C glows on the clubs run")
        room.act(s[0].token, "play_off", {"card": 5200, "meld": run})
        self.assertEqual([str(c) for c in room.table[run].cards], ["3C", "4C", "5C", "6C", "7C"])
        room.act(s[0].token, "discard", {"card": room.players[0].hand[0].id})
        self.assertEqual(room.current, 1)

    def test_only_one_draw_a_turn(self):
        room, s = self.lay_down_round3()
        room.discard.append(Card(5200, 7, "C"))
        draw_phase(room, 0, turns=3)
        room.act(s[0].token, "draw", {"source": "discard"})
        for source in ("discard", "stock"):
            with self.assertRaises(GameError):
                room.act(s[0].token, "draw", {"source": source})
        v = room.view_for(s[0].token)
        self.assertFalse(v["can"]["draw"])
        self.assertFalse(v["can"]["take_discard"])
        # and the other way round: pile first, then no discard
        room2, s2 = self.lay_down_round3()
        room2.discard.append(Card(5200, 7, "C"))
        draw_phase(room2, 0, turns=3)
        room2.act(s2[0].token, "draw", {"source": "stock"})
        with self.assertRaises(GameError):
            room2.act(s2[0].token, "draw", {"source": "discard"})

    def test_not_on_someone_elses_turn(self):
        room, s = self.lay_down_round3()
        room.discard.append(Card(5200, 7, "C"))
        draw_phase(room, 1)
        self.assertFalse(room.view_for(s[0].token)["can"]["take_discard"])
        with self.assertRaisesRegex(GameError, "turn"):
            room.act(s[0].token, "draw", {"source": "discard"})
        self.assertEqual(str(room.discard[-1]), "7C")

    def test_top_card_only(self):
        room, s = self.lay_down_round3()
        room.discard.extend([Card(5300, 7, "C"), Card(5301, 13, "S")])
        draw_phase(room, 0, turns=3)
        room.act(s[0].token, "draw", {"source": "discard", "card": 5300})   # asks for the one underneath
        self.assertIn(5301, [c.id for c in room.players[0].hand], "got the top card, the KS")
        self.assertNotIn(5300, [c.id for c in room.players[0].hand])
        self.assertEqual(room.discard[-1].id, 5300)

    def test_round4_sets_too(self):
        room, s = new_room(round_no=4)
        hand = rig(room, 0, "5S 5H 5D 9C 9D 9H KC KD KH 4C QS", 5000)
        play_phase(room, 0)
        room.act(s[0].token, "lay_down", {"groups": [ids(hand, "5S 5H 5D"), ids(hand, "9C 9D 9H"),
                                                      ids(hand, "KC KD KH")]})
        room.act(s[0].token, "discard", {"card": ids(hand, "QS")[0]})
        room.discard.append(Card(5400, 9, "S"))
        draw_phase(room, 0, turns=3)
        self.assertTrue(room.view_for(s[0].token)["can"]["take_discard"])
        room.act(s[0].token, "draw", {"source": "discard"})
        nines = next(i for i, m in enumerate(room.table) if m.owner == 0 and m.rank == 9)
        room.act(s[0].token, "play_off", {"card": 5400, "meld": nines})
        self.assertEqual(len(room.table[nines].cards), 4)

    def test_host_can_switch_back_to_old_rule(self):
        room, s = self.lay_down_round3()
        with self.assertRaisesRegex(GameError, "made the table"):
            room.act(s[1].token, "options", {"discard_after_laydown": False})
        room.act(s[0].token, "options", {"discard_after_laydown": False})
        self.assertIn("draw from the pile only", room.log[-1])
        room.discard.append(Card(5200, 7, "C"))
        draw_phase(room, 0, turns=3)
        v = room.view_for(s[0].token)
        self.assertFalse(v["can"]["take_discard"])
        self.assertFalse(v["options"]["discard_after_laydown"])
        with self.assertRaisesRegex(GameError, "draw from the pile"):
            room.act(s[0].token, "draw", {"source": "discard"})
        # not-yet-laid players still may take it
        draw_phase(room, 1, turns=3)
        room.players[1].laid = False
        self.assertTrue(room.view_for(s[1].token)["can"]["take_discard"])

    def test_computer_takes_a_discard_that_fits_after_laying_down(self):
        room, s = new_room(n=2, round_no=3)
        bot = room.players[1]
        bot.bot = True
        hand = rig(room, 1, "3C 4C 5C 6C 8H 9H 10H JH KD QS", 6000)
        play_phase(room, 1)
        room.act(bot.token, "lay_down", {"groups": [ids(hand, "3C 4C 5C 6C"), ids(hand, "8H 9H 10H JH")]})
        room.act(bot.token, "discard", {"card": ids(hand, "QS")[0]})
        room.discard.append(Card(6100, 7, "C"))
        draw_phase(room, 1, turns=3)
        room._bot_step(bot)
        self.assertIn(6100, [c.id for c in bot.hand])
        self.assertIn("took 7♣ from the discard pile", bot.moves[0])


class FollowTheComputers(unittest.TestCase):
    def test_moves_listed_for_the_turn_and_kept_until_next_turn(self):
        room, s = new_room(n=2, round_no=3)
        p2 = room.players[1]
        hand = rig(room, 1, "3C 4C 5C 6C 8H 9H 10H JH KD QS", 7000)
        draw_phase(room, 1)
        room.act(p2.token, "draw", {"source": "stock"})
        room.act(p2.token, "lay_down", {"groups": [ids(hand, "3C 4C 5C 6C"), ids(hand, "8H 9H 10H JH")]})
        room.act(p2.token, "discard", {"card": ids(hand, "QS")[0]})
        v = room.view_for(s[0].token)
        moves = v["players"][1]["moves"]
        self.assertEqual(moves[0], "drew from the pile")
        self.assertTrue(moves[1].startswith("laid down the goal: Run 3 to 6 ♣"), moves[1])
        self.assertEqual(moves[2], "discarded Q♠")
        self.assertEqual(v["discard_top_by"], 1)
        self.assertIn("P2 laid down 2 runs of 4: Run 3 to 6 ♣", room.log[-2])

    def test_new_cards_marked_until_your_next_turn(self):
        room, s = new_room(n=2, round_no=3)
        p2 = room.players[1]
        hand = rig(room, 1, "3C 4C 5C 6C 8H 9H 10H JH KD QS", 7000)
        draw_phase(room, 1)
        room.act(p2.token, "draw", {"source": "stock"})
        room.act(p2.token, "lay_down", {"groups": [ids(hand, "3C 4C 5C 6C"), ids(hand, "8H 9H 10H JH")]})
        room.act(p2.token, "discard", {"card": ids(hand, "QS")[0]})
        mine = room.view_for(s[0].token)
        self.assertTrue(all(c["recent"] for m in mine["table"] for c in m["cards"]), "new to P1")
        theirs = room.view_for(s[1].token)
        self.assertFalse(any(c["recent"] for m in theirs["table"] for c in m["cards"]), "not new to P2")
        # P1 takes a turn, then P2 draws: P2's groups are no longer new to P1
        draw_phase(room, 0)
        room.act(s[0].token, "draw", {"source": "stock"})
        room.act(s[0].token, "discard", {"card": room.players[0].hand[0].id})
        room.act(p2.token, "draw", {"source": "stock"})
        mine = room.view_for(s[0].token)
        self.assertFalse(any(c["recent"] for m in mine["table"] for c in m["cards"]))

    def test_nothing_private_in_moves(self):
        room, s = new_room(n=2, round_no=3)
        draw_phase(room, 1)
        top_of_pile = room.stock[-1]
        room.act(room.players[1].token, "draw", {"source": "stock"})
        v = room.view_for(s[0].token)
        text = json.dumps(v["players"]) + json.dumps(v["log"])
        self.assertNotIn("card" + str(top_of_pile.id), text)
        self.assertEqual(v["players"][1]["moves"], ["drew from the pile"])
        from game import card_name
        self.assertNotIn(card_name(top_of_pile) + " from the pile", text)
        ids_seen = set()
        def walk(o):
            if isinstance(o, dict):
                if "id" in o and "rank" in o:
                    ids_seen.add(o["id"])
                for x in o.values():
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(v)
        self.assertNotIn(top_of_pile.id, ids_seen)
        self.assertFalse(ids_seen & {c.id for c in room.players[1].hand})

    def test_longer_history(self):
        room, s = new_room(n=2, round_no=3)
        for i in range(60):
            room._bump(f"line {i}")
        self.assertEqual(len(room.log), 40)
        self.assertEqual(room.log[-1], "line 59")

    def test_slower_computers_button(self):
        room, s = new_room(n=2, round_no=3)
        room.bot_delay = BOT_DELAY
        room.act(s[1].token, "speed", {"slow": True})      # anyone at the table may
        self.assertTrue(room.view_for(s[0].token)["options"]["slow_bots"])
        self.assertIn("slower", room.log[-1])
        wait = room.bot_ready_at - time.time()
        self.assertGreater(wait, BOT_DELAY + 0.5)
        self.assertLessEqual(wait, SLOW_BOT_DELAY + 0.05)
        room.act(s[0].token, "speed", {"slow": False})
        self.assertLessEqual(room.bot_ready_at - time.time(), BOT_DELAY + 0.05)

    def test_moves_cleared_each_round(self):
        room, s = new_room(n=2, round_no=3)
        room.players[1].moves = ["discarded Q♠"]
        room.placed = {1: (1, 1)}
        with room.lock:
            room._start_round(4)
        self.assertEqual(room.players[1].moves, [])
        self.assertEqual(room.placed, {})


class StillTheSameRules(unittest.TestCase):
    """Spot checks that the house rules Tom confirmed did not change."""

    def test_two_wilds_most_per_group(self):
        room, s = new_room(round_no=3)
        hand = rig(room, 0, "3C 2D Joker 6C 8H 9H 10H JH 2S KD QS", 8000)
        play_phase(room, 0)
        room.act(s[0].token, "lay_down", {"groups": [ids(hand, "3C 2D Joker 6C"), ids(hand, "8H 9H 10H JH")]})
        clubs = next(i for i, m in enumerate(room.table) if m.owner == 0 and m.suit == "C")
        with self.assertRaisesRegex(GameError, "already has 2 wild cards"):
            room.act(s[0].token, "play_off", {"card": ids(hand, "2S")[0], "meld": clubs})

    def test_whole_goal_at_once(self):
        room, s = new_room(round_no=3)
        hand = rig(room, 0, "3C 4C 5C 6C 8H 9H KD QS", 8000)
        play_phase(room, 0)
        with self.assertRaises(GameError):
            room.act(s[0].token, "lay_down", {"groups": [ids(hand, "3C 4C 5C 6C")]})
        self.assertFalse(room.players[0].laid)

    def test_add_to_another_players_run_end(self):
        room, s = new_room(round_no=3)
        h1 = rig(room, 1, "3C 4C 5C 6C 8H 9H 10H JH KD QS", 8100)
        play_phase(room, 1)
        room.act(s[1].token, "lay_down", {"groups": [ids(h1, "3C 4C 5C 6C"), ids(h1, "8H 9H 10H JH")]})
        room.act(s[1].token, "discard", {"card": ids(h1, "QS")[0]})
        h0 = rig(room, 0, "5S 6S 7S 8S 9D 10D JD QD 7C 2C AS", 8200)
        play_phase(room, 0)
        room.act(s[0].token, "lay_down", {"groups": [ids(h0, "5S 6S 7S 8S"), ids(h0, "9D 10D JD QD")]})
        clubs = next(i for i, m in enumerate(room.table) if m.owner == 1 and m.suit == "C")
        room.act(s[0].token, "play_off", {"card": ids(h0, "7C")[0], "meld": clubs})
        self.assertEqual(str(room.table[clubs].cards[-1]), "7C")
        self.assertIn("added 7♣ to P2's Run 3 to 7 ♣", room.players[0].moves[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
