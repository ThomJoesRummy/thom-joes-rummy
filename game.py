"""Interactive Progressive Rummy rooms for the web app.

The server owns everything: shuffling, dealing, whose turn it is, which moves
are legal, every player's hand and the score.  Each browser only ever gets
its own hand; other players' hands go out as a card count.

The rules themselves come unchanged from rummy.py (Tom's house rules):
  * cards dealt per round from ROUNDS, clockwise starting left of the dealer
  * all of the round's groups at once to lay down (validate_laydown)
  * one draw a turn: the top of the draw pile or the top discard.  Third
    edition: the top discard may be taken after you have laid down too (a
    table option; the host can switch back to "draw pile only after laying
    down", the rule in the first two editions)
  * after laying down, natural cards onto anyone's sets and onto either open
    end of anyone's runs (check_play_off); a spot a wild holds stays closed
  * aces low or high, no wrap-around
  * you go out only by discarding your last card
  * leftover points: joker 50, deuce 25, ace 15, face cards 10, others 5;
    lowest total wins
"""
from __future__ import annotations

import random
import secrets
import threading
import time

from dataclasses import replace

from rummy import (ROUNDS, SUITS, Card, Meld, Rules, check_group, check_play_off, decks_for,
                   describe_goal, find_laydown, hand_points, make_deck,
                   meld_consistent, validate_laydown, _run_positions, _usefulness)

# Second edition (Nov 9, 2026), from Tom's play-test of the first table:
#  * After you have laid down your round's goal, you may lay down MORE new
#    groups (for example three nines) on any later play, all round long.
#  * After you have laid down, deuces and jokers may be added to groups on
#    the table, yours or anyone else's, as wilds (the old assumption D, "no
#    wild play-offs", is dropped).  The sheet's limit of two wilds in one
#    group still holds.
#  * Natural cards still go onto anyone's sets and either open end of
#    anyone's runs.
NEW_SET_MIN = 3          # our guess: a new extra set needs at least 3 cards
NEW_RUN_MIN = 4          # our guess: a new extra run needs at least 4 (the shortest run on the sheet)

MAX_PLAYERS = 4
MIN_PLAYERS = 2          # humans needed to deal without computers (our guess)
LOBBY_SECONDS = 30       # Tom: 30 seconds to fill the seats...
LOBBY_WINDOWS = 2        # ...and if they aren't all filled, the clock starts over once
FULL_TABLE_PAUSE = 3     # seconds before dealing once all four seats are taken
BOT_DELAY = 1.2          # seconds between a computer player's moves, so people can follow
SLOW_BOT_DELAY = 2.4     # third edition: the "slower computers" button doubles it
LOG_LINES = 40           # lines kept for "What happened"
# Online version (Nov 18, 2026): on a website anyone with the link can make a
# table, so keep the number of tables sensible and close tables nobody is
# looking at any more (everyone closed the browser without pressing Exit).
MAX_ROOMS = 40
ROOM_IDLE_SECONDS = 2 * 60 * 60
BOT_NAMES = ["Betty", "Max", "Sam", "Rosie"]
LAST_ROUND = 16
SUIT_SYMBOL = {"C": "\u2663", "D": "\u2666", "H": "\u2665", "S": "\u2660"}
RANK_LABEL = {11: "J", 12: "Q", 13: "K", 14: "A"}
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # no I or O


class GameError(Exception):
    """A move the rules or the game state do not allow.  The message is
    shown to the player as it is."""


def card_view(c: Card) -> dict:
    if c.rank == 0:
        label, suit = "Joker", None
    else:
        label, suit = str(RANK_LABEL.get(c.rank, c.rank)), c.suit
    return {"id": c.id, "rank": c.rank, "suit": suit, "label": label,
            "symbol": SUIT_SYMBOL.get(suit, "\u2605"), "wild": c.wild,
            "points": c.points, "name": card_name(c)}


def card_name(c: Card) -> str:
    if c.rank == 0:
        return "Joker"
    return f"{RANK_LABEL.get(c.rank, c.rank)}{SUIT_SYMBOL[c.suit]}"


def arrange_run(cards, rules: Rules):
    """Put a legal run in order and decide which spot each wild holds.
    Wilds fill gaps first; a wild with no gap to fill goes on the high end
    when there is room, else the low end.  Returns (ordered, low, high)."""
    nat = [c for c in cards if not c.wild]
    wild = [c for c in cards if c.wild]
    m = len(cards)
    lo = 1 if rules.ace_low else 2
    best = None
    for start in range(lo, 14 - m + 2):
        window = range(start, start + m)
        spots = {}
        ok = True
        for c in nat:
            p = next((p for p in _run_positions(c.rank, rules.ace_low) if p in window), None)
            if p is None or p in spots:
                ok = False
                break
            spots[p] = c
        if not ok:
            continue
        wilds_below = min(spots) - start
        if best is None or wilds_below < best[0]:
            best = (wilds_below, start, spots)
    if best is None:
        raise GameError("Those cards do not make a run.")
    _, start, spots = best
    pool = list(wild)
    ordered = [spots[p] if p in spots else pool.pop(0) for p in range(start, start + m)]
    return ordered, start, start + m - 1


def play_off_where(card: Card, meld: Meld, rules: Rules, end: str | None = None):
    """Can this card go onto a group already on the table (anyone's)?
    Natural cards follow check_play_off from rummy.py.  Wild cards (Tom,
    Nov 9) may be added too, up to the two-wild limit for one group; on a
    run a wild goes past the high end when there is room, else the low end,
    unless `end` asks for one.  Returns (where, reason)."""
    if not card.wild:
        return check_play_off(card, meld, rules)
    limit = rules.max_wilds_per_group
    if sum(c.wild for c in meld.cards) >= limit:
        return None, f"that group already has {limit} wild cards, the most one group can hold"
    if meld.kind == "set":
        return "add", "ok"
    if len(meld.cards) >= 13:
        return None, "that run is already as long as a run can be"
    lo = 1 if rules.ace_low else 2
    ends = []
    if meld.high < 14:
        ends.append("high")
    if meld.low > lo:
        ends.append("low")
    if end in ("high", "low"):
        if end not in ends:
            return None, "that end of the run is already full"
        return end, "ok"
    if not ends:
        return None, "both ends of that run are full"
    return ends[0], "ok"


def meld_label(m: Meld) -> str:
    if m.kind == "set":
        r = RANK_LABEL.get(m.rank, m.rank)
        return f"Set of {r}s"
    def pos(p):
        return "A" if p in (1, 14) else str(RANK_LABEL.get(p, p))
    return f"Run {pos(m.low)} to {pos(m.high)} {SUIT_SYMBOL.get(m.suit, '')}"


class Seat:
    def __init__(self, seat: int, name: str, bot: bool = False):
        self.seat = seat
        self.name = name
        self.bot = bot           # a computer player keeps its seat for the whole game
        self.token = secrets.token_urlsafe(16)
        self.hand: list[Card] = []
        self.laid = False
        self.turns = 0
        self.moves: list[str] = []   # what this player did on this turn, or the last one (public moves only)
        self.total = 0
        self.round_scores: dict[int, int | None] = {}
        self.last_seen = time.time()


class Room:
    def __init__(self, code: str, rules: Rules | None = None, seed=None,
                 lobby_seconds: float = LOBBY_SECONDS, bot_delay: float = BOT_DELAY):
        self.code = code
        self.lobby_seconds = lobby_seconds
        self.bot_delay = bot_delay
        self.deadline = time.time() + lobby_seconds     # end of the joining clock
        self.window = 1                                  # which 30-second window we are in
        self.bot_ready_at = 0.0
        self.turns_this_round = 0
        self.rules = rules or Rules()
        self.rng = random.Random(seed)
        self.players: list[Seat] = []
        self.status = "lobby"           # lobby, playing, round_over, game_over
        self.round_no = 0
        self.dealer = 0
        self.stock: list[Card] = []
        self.discard: list[Card] = []
        self.table: list[Meld] = []
        self.current = 0
        self.phase = "draw"             # draw, play
        self.version = 0
        self.log: list[str] = []
        self.last_round: dict | None = None
        # Third edition (Nov 9, 2026), from Tom's play-test of the second:
        # Tom: after laying down you may still take the top discard instead of
        # drawing from the pile.  The host can switch this back off.
        self.discard_after_laydown = True
        self.slow_bots = False          # "slower computers" button
        self.turn_no = 0                # counts every draw in the round
        self.placed: dict[int, tuple[int, int]] = {}      # card id -> (turn_no, seat) it went on the table
        self.discarded_by: dict[int, int] = {}            # card id -> seat that discarded it
        # Fifth edition, update 1 (Nov 13, 2026): Tom asked for an exit button.
        # The host is the person who can change the table rules; it moves to
        # another person if the host leaves.
        self.host = 0
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)

    # ------------------------------------------------------------ helpers
    def _bump(self, event: str | None = None):
        delay = self.bot_delay * (SLOW_BOT_DELAY / BOT_DELAY if self.slow_bots else 1)
        self.bot_ready_at = time.time() + delay
        if event:
            self.log.append(event)
        self.log = self.log[-LOG_LINES:]
        with self.changed:              # re-entrant: fine if already held
            self.version += 1
            self.changed.notify_all()

    def seat_for(self, token: str) -> Seat:
        for p in self.players:
            if secrets.compare_digest(p.token, token or ""):
                p.last_seen = time.time()
                return p
        raise PermissionError("That player is not in this room.")

    def _req(self):
        return ROUNDS[self.round_no][0]

    def _my_turn(self, p: Seat, phase: str):
        if self.status != "playing":
            raise GameError("No hand is being played right now.")
        if p.seat != self.current:
            raise GameError(f"It is {self.players[self.current].name}'s turn.")
        if self.phase != phase:
            if phase == "draw":
                raise GameError("You already drew this turn.")
            raise GameError("Draw a card first: tap the pile, or the discard.")

    def _cards_from_hand(self, p: Seat, ids):
        by_id = {c.id: c for c in p.hand}
        out = []
        for i in ids:
            if i not in by_id:
                raise GameError("That card is not in your hand.")
            out.append(by_id[i])
        if len({c.id for c in out}) != len(out):
            raise GameError("The same card was picked twice.")
        return out

    def _min_keep(self, p: Seat):
        # Go out only by discarding (confirmed), so keep one card for the
        # discard.  Assumption F: nobody goes out on his first turn of the
        # hand, so on that turn keep two.
        return 2 if p.turns == 1 else 1

    # ------------------------------------------------------------ lobby
    def add_player(self, name: str) -> Seat:
        name = " ".join((name or "").split())[:20]
        if not name:
            raise GameError("Please type a name.")
        with self.lock:
            if self.status != "lobby":
                raise GameError("This game has already started. Computer players keep "
                                "the empty seats until the game ends.")
            if len(self.players) >= MAX_PLAYERS:
                raise GameError("This table already has four players.")
            if any(p.name.lower() == name.lower() for p in self.players):
                raise GameError("Someone at this table already has that name.")
            p = Seat(len(self.players), name)
            self.players.append(p)
            if len(self.players) == MAX_PLAYERS:            # full: deal shortly
                self.deadline = min(self.deadline, time.time() + FULL_TABLE_PAUSE)
            self._bump(f"{name} sat down.")
            return p

    def humans(self) -> list[Seat]:
        return [p for p in self.players if not p.bot]

    def leave(self, token: str) -> bool:
        """A person leaves the table (the Exit game button).
        Before the deal: their seat is freed.  During the game: a computer
        player takes over their seat, cards and score for the rest of the
        game, the same way computers keep empty seats.  Returns True while
        at least one person is still at the table."""
        with self.lock:
            p = self.seat_for(token)
            name = p.name
            if self.status == "lobby":
                self.players.remove(p)
                for i, q in enumerate(self.players):
                    q.seat = i
                self.host = 0
                note = f"{name} left the table."
                if p.seat == 0 and self.players:
                    note += f" {self.players[0].name} can deal now."
                self._bump(note)
            else:
                p.bot = True
                p.name = f"{name} (computer)"
                p.token = secrets.token_urlsafe(16)        # the old screen is no longer at the table
                if p.seat == self.host:
                    people = self.humans()
                    if people:
                        self.host = people[0].seat
                self._bump(f"{name} left the game. A computer player keeps {name}'s seat, "
                           f"cards and score for the rest of the game.")
            return bool(self.humans())

    def _fill_with_bots(self):
        taken = {p.name.lower() for p in self.players}
        names = [n for n in BOT_NAMES if f"{n} (computer)".lower() not in taken]
        while len(self.players) < MAX_PLAYERS:
            bot = Seat(len(self.players), f"{names.pop(0)} (computer)", bot=True)
            self.players.append(bot)
            self.log.append(f"{bot.name} sat down in an empty seat.")

    # ------------------------------------------------------------ actions
    def act(self, token: str, action: str, data: dict | None = None) -> dict:
        data = data or {}
        with self.lock:
            p = self.seat_for(token)
            handler = {
                "start": self._start, "draw": self._draw, "lay_down": self._lay_down,
                "play_off": self._play_off, "discard": self._discard,
                "new_group": self._new_group,
                "next_round": self._next_round, "suggest": self._suggest,
                "fill_bots": self._fill_and_start,
                "options": self._options, "speed": self._speed,
            }.get(action)
            if handler is None:
                raise GameError(f"Unknown action: {action}")
            return handler(p, data) or {}

    def _start(self, p: Seat, data):
        if self.status != "lobby":
            raise GameError("The game has already started.")
        if p.seat != 0:
            raise GameError("Only the player who made the table can start the game.")
        if len(self.players) < MIN_PLAYERS:
            raise GameError(f"You need at least {MIN_PLAYERS} players to start.")
        self._start_round(1)

    def _fill_and_start(self, p: Seat, data):
        if self.status != "lobby":
            raise GameError("The game has already started.")
        if p.seat != 0:
            raise GameError("Only the player who made the table can start the game.")
        self._fill_with_bots()
        self._start_round(1)

    def _options(self, p: Seat, data):
        """Host only: table rules that are a matter of house style."""
        if p.seat != self.host:
            raise GameError("Only the player who made the table can change the table rules.")
        if "discard_after_laydown" in data:
            on = bool(data["discard_after_laydown"])
            if on != self.discard_after_laydown:
                self.discard_after_laydown = on
                self._bump(f"{p.name} changed a table rule: after laying down, players "
                           + ("may take the top discard or draw from the pile." if on
                              else "draw from the pile only."))

    def _speed(self, p: Seat, data):
        """Any person at the table: normal or slower computer players."""
        slow = bool(data.get("slow"))
        if slow != self.slow_bots:
            self.slow_bots = slow
            self._bump(f"{p.name} set the computer players to "
                       + ("slower." if slow else "normal speed."))

    def _start_round(self, r: int):
        n = len(self.players)
        req, dealt = ROUNDS[r]
        self.round_no = r
        self.dealer = (r - 1) % n
        deck = make_deck(decks_for(n))
        self.rng.shuffle(deck)
        for p in self.players:
            p.hand, p.laid, p.turns, p.moves = [], False, 0, []
        self.turns_this_round = 0
        self.turn_no = 0
        self.placed = {}
        self.discarded_by = {}
        for _ in range(dealt):                      # one at a time, clockwise
            for k in range(1, n + 1):
                self.players[(self.dealer + k) % n].hand.append(deck.pop())
        self.stock = deck
        self.discard = [self.stock.pop()]
        self.table = []
        self.current = (self.dealer + 1) % n        # left of the dealer goes first
        self.phase = "draw"
        self.status = "playing"
        self.last_round = None
        # Update 4 (Nov 14, 2026), Tom: clear "What happened" so every deal
        # starts with a clean slate (round 1 of a new game too).
        self.log = []
        self._bump(f"Round {r}: {self.players[self.dealer].name} dealt {dealt} cards each. "
                   f"Goal: {describe_goal(req)}.")

    def _draw(self, p: Seat, data):
        self._my_turn(p, "draw")
        source = data.get("source")
        if source == "discard":
            if p.laid and not self.discard_after_laydown:
                raise GameError("At this table, after you lay down you draw from the pile.")
            if not self.discard:
                raise GameError("The discard pile is empty.")
            card = self.discard.pop()
            event = f"{p.name} took {card_name(card)} from the discard pile."
            move = f"took {card_name(card)} from the discard pile"
        elif source == "stock":
            if not self.stock:
                # Assumption G: reshuffle the discards, all but the top card.
                if len(self.discard) <= 1:
                    self._finish_round(None, "Nobody could draw a card, so this hand was stopped.")
                    return {}
                top = self.discard.pop()
                self.stock = self.discard
                self.rng.shuffle(self.stock)
                self.discard = [top]
                self.log.append("The discard pile was shuffled into a new draw pile.")
            card = self.stock.pop()
            event = f"{p.name} drew from the pile."
            move = "drew from the pile"
        else:
            raise GameError("Draw from the pile or the discard.")
        p.hand.append(card)
        p.turns += 1
        self.turn_no += 1
        p.moves = [move]
        self.turns_this_round += 1
        self.phase = "play"
        self._bump(event)
        return {"drawn": card.id}

    def _lay_down(self, p: Seat, data):
        self._my_turn(p, "play")
        if p.laid:
            raise GameError("You have already laid down this round.")
        req = self._req()
        if isinstance(data.get("cards"), list):
            # Second edition: the player just picks the cards; the table works
            # out how they make the round's goal.
            groups = self._groups_from_pick(p, data["cards"], req)
        else:
            groups_ids = data.get("groups")
            if not isinstance(groups_ids, list) or len(groups_ids) != len(req) or \
                    any(not isinstance(g, list) or not g for g in groups_ids):
                raise GameError(f"Fill all {len(req)} groups for this round before laying down.")
            groups = [self._cards_from_hand(p, g) for g in groups_ids]
        ok, why = validate_laydown(p.hand, req, groups, self.rules)
        if not ok:
            raise GameError("That lay-down is not allowed: " + why + ".")
        used = {c.id for g in groups for c in g}
        if len(p.hand) - len(used) < self._min_keep(p):
            raise GameError("On your first turn you can't go out, so keep at least two cards.")
        melds = []
        for (kind, _n), g in zip(req, groups):
            if kind == "set":
                rank = next(c.rank for c in g if not c.wild)
                m = Meld("set", list(g), rank=rank)
            else:
                ordered, low, high = arrange_run(g, self.rules)
                m = Meld("run", ordered, suit=next(c.suit for c in g if not c.wild), low=low, high=high)
            m.owner = p.seat
            m.wilds_at_laydown = sum(c.wild for c in m.cards)
            assert meld_consistent(m, self.rules), m
            melds.append(m)
        self.table.extend(melds)
        for m in melds:
            self._mark_placed(m.cards, p)
        p.hand = [c for c in p.hand if c.id not in used]
        p.laid = True
        p.moves.append("laid down the goal: " + ", ".join(meld_label(m) for m in melds))
        self._bump(f"{p.name} laid down {describe_goal(req)}: "
                   + ", ".join(meld_label(m) for m in melds) + ".")

    def _groups_from_pick(self, p: Seat, ids, req):
        """Turn a plain pick of cards into the round's groups.  Cards in the
        pick that the goal doesn't need simply stay in the hand."""
        if not ids:
            raise GameError("Pick the cards for your goal first: tap them in your hand.")
        picked = self._cards_from_hand(p, ids)
        others = len(p.hand) - len(picked)
        need_keep = max(0, self._min_keep(p) - others)
        found = find_laydown(picked, req, replace(self.rules, keep_for_discard=need_keep))
        if found is None:
            if find_laydown(picked, req, replace(self.rules, keep_for_discard=0)) is not None:
                raise GameError("You need to keep a card in your hand to discard "
                                + ("(two on your first turn)." if p.turns == 1 else "at the end of your turn."))
            raise GameError(f"Those cards don't make this round's goal ({describe_goal(req)}). "
                            "Check the cards you picked, or tap Find my goal.")
        return [list(m.cards) for m in found[0]]

    def _new_group(self, p: Seat, data):
        """Second edition: after laying down the goal, lay down another new
        set or run from your hand, any time you play during the round."""
        self._my_turn(p, "play")
        if not p.laid:
            raise GameError("First lay down this round's goal. After that you can put down extra groups.")
        ids = data.get("cards")
        if not isinstance(ids, list) or not ids:
            raise GameError("Pick the cards for the new group first.")
        cards = self._cards_from_hand(p, ids)
        if len(p.hand) - len(cards) < self._min_keep(p):
            raise GameError("Keep a card in your hand to discard: you go out only by discarding.")
        n = len(cards)
        ok_set, why_set = (check_group("set", n, cards, self.rules) if n >= NEW_SET_MIN
                           else (False, f"a new set needs at least {NEW_SET_MIN} cards"))
        ok_run, why_run = (check_group("run", NEW_RUN_MIN, cards, self.rules) if n >= NEW_RUN_MIN
                           else (False, f"a new run needs at least {NEW_RUN_MIN} cards"))
        if ok_set:
            rank = next(c.rank for c in cards if not c.wild)
            m = Meld("set", list(cards), rank=rank)
        elif ok_run:
            ordered, low, high = arrange_run(cards, self.rules)
            m = Meld("run", ordered, suit=next(c.suit for c in cards if not c.wild), low=low, high=high)
        else:
            nat = [c for c in cards if not c.wild]
            if nat and len({c.rank for c in nat}) == 1:
                why = why_set
            elif nat and len({c.suit for c in nat}) == 1:
                why = why_run
            else:
                why = (f"a set is {NEW_SET_MIN} or more of one rank; a run is {NEW_RUN_MIN} or more "
                       "in a row of one suit")
            raise GameError(f"Those cards don't make a new group: {why}.")
        m.owner = p.seat
        m.wilds_at_laydown = sum(c.wild for c in m.cards)
        assert meld_consistent(m, self.rules), m
        self.table.append(m)
        self._mark_placed(m.cards, p)
        used = {c.id for c in cards}
        p.hand = [c for c in p.hand if c.id not in used]
        p.moves.append(f"put down a new group: {meld_label(m)}")
        self._bump(f"{p.name} put down a new group: {meld_label(m)}.")

    def _play_off(self, p: Seat, data):
        self._my_turn(p, "play")
        if not p.laid:
            raise GameError("Lay down your round's goal before adding to the table.")
        (card,) = self._cards_from_hand(p, [data.get("card")])
        idx = data.get("meld")
        if not isinstance(idx, int) or not 0 <= idx < len(self.table):
            raise GameError("Pick a group on the table.")
        if len(p.hand) - 1 < self._min_keep(p):
            raise GameError("Keep a card to discard: you go out only by discarding."
                            if p.turns > 1 else
                            "On your first turn you can't go out, so keep at least two cards.")
        m = self.table[idx]
        where, why = play_off_where(card, m, self.rules, data.get("end"))
        if where is None:
            raise GameError(f"{card_name(card)} can't go there: {why}.")
        if where == "high":
            m.cards.append(card); m.high += 1
        elif where == "low":
            m.cards.insert(0, card); m.low -= 1
        else:
            m.cards.append(card)
        assert meld_consistent(m, self.rules), m
        p.hand.remove(card)
        self._mark_placed([card], p)
        owner = "their own" if m.owner == p.seat else f"{self.players[m.owner].name}'s"
        p.moves.append(f"added {card_name(card)} to {owner} {meld_label(m)}")
        self._bump(f"{p.name} added {card_name(card)} to {owner} {meld_label(m)}.")

    def _discard(self, p: Seat, data):
        self._my_turn(p, "play")
        (card,) = self._cards_from_hand(p, [data.get("card")])
        if len(p.hand) == 1 and p.turns == 1:
            raise GameError("You can't go out on your first turn.")
        p.hand.remove(card)
        self.discard.append(card)
        self.discarded_by[card.id] = p.seat
        if not p.hand:
            p.moves.append(f"discarded {card_name(card)} and went out")
            self.log.append(f"{p.name} discarded {card_name(card)} and went out!")
            self._finish_round(p.seat)
            return {}
        p.moves.append(f"discarded {card_name(card)}")
        self.current = (self.current + 1) % len(self.players)
        self.phase = "draw"
        self._bump(f"{p.name} discarded {card_name(card)}.")

    def _mark_placed(self, cards, p: Seat):
        for c in cards:
            self.placed[c.id] = (self.turn_no, p.seat)

    def _recent(self, card_id: int, me: Seat) -> bool:
        """A card someone else put on the table since your last turn."""
        when = self.placed.get(card_id)
        return (when is not None and when[1] != me.seat
                and when[0] > self.turn_no - len(self.players))

    def _finish_round(self, winner, note=None):
        points = {}
        for q in self.players:
            if winner is None:
                q.round_scores[self.round_no] = None     # stopped hand, not scored
            else:
                pts = hand_points(q.hand)
                q.round_scores[self.round_no] = pts
                q.total += pts
                points[q.seat] = pts
        self.last_round = {"round": self.round_no, "winner": winner, "points": points, "note": note}
        self.status = "game_over" if self.round_no >= LAST_ROUND else "round_over"
        self._bump(note or f"Round {self.round_no} is over.")

    def _next_round(self, p: Seat, data):
        if self.status != "round_over":
            raise GameError("The round isn't over yet.")
        self._start_round(self.round_no + 1)

    # ------------------------------------------------------------ clock and computer players
    def seconds_left(self, now=None):
        if self.status != "lobby":
            return None
        return max(0, int(round(self.deadline - (now or time.time()))))

    def tick(self, now=None) -> bool:
        """Run the joining clock and the computer players.  Called about four
        times a second by the server.  Returns True when something changed."""
        now = now or time.time()
        with self.lock:
            if self.status == "lobby":
                if now < self.deadline:
                    return False
                if len(self.players) < MAX_PLAYERS and self.window < LOBBY_WINDOWS:
                    self.window += 1                     # the clock starts over, once
                    self.deadline = now + self.lobby_seconds
                    self._bump(f"Not every seat is filled. The clock starts over: "
                               f"{int(self.lobby_seconds)} more seconds to join.")
                    return True
                empty = MAX_PLAYERS - len(self.players)
                self._fill_with_bots()
                if empty:
                    self.log.append(f"Time's up: computer players took {empty} empty "
                                    f"seat{'s' if empty > 1 else ''} for the whole game.")
                self._start_round(1)
                return True
            if self.status != "playing":
                return False
            p = self.players[self.current]
            if not p.bot or now < self.bot_ready_at:
                return False
            if self.turns_this_round >= self.rules.max_turns:
                self._finish_round(None, "This hand went on too long, so it was stopped without scoring.")
                return True
            self._bot_step(p)
            return True

    def _bot_step(self, p: Seat):
        """One move by a computer player, made through the same checked moves a
        person makes: draw, then lay down, add to the table, or discard."""
        req = self._req()
        try:
            if self.phase == "draw":
                top = self.discard[-1] if self.discard else None
                if top is None:
                    take = False
                elif not p.laid:
                    take = top.wild or find_laydown(p.hand + [top], req, self.rules) is not None
                else:
                    # Third edition: after laying down, take it when it goes
                    # straight onto a group on the table.
                    take = self.discard_after_laydown and any(
                        play_off_where(top, m, self.rules)[0] is not None for m in self.table)
                self._draw(p, {"source": "discard" if take else "stock"})
                return
            keep = self._min_keep(p)
            if not p.laid:
                found = find_laydown(p.hand, req, self.rules)
                if found and len(found[1]) >= keep:
                    self._lay_down(p, {"groups": [[c.id for c in m.cards] for m in found[0]]})
                    return
            if p.laid and len(p.hand) > keep:
                for c in sorted(p.hand, key=lambda c: -c.points):
                    for i, m in enumerate(self.table):
                        if play_off_where(c, m, self.rules)[0] is not None:
                            self._play_off(p, {"card": c.id, "meld": i})
                            return
                # Extra new groups after the goal (second edition).
                for goal in ([("set", NEW_SET_MIN)], [("run", NEW_RUN_MIN)]):
                    found = find_laydown(p.hand, goal, replace(self.rules, keep_for_discard=keep))
                    if found:
                        self._new_group(p, {"cards": [c.id for c in found[0][0].cards]})
                        return
            if p.laid:
                choice = max(p.hand, key=lambda c: (c.points, self.rng.random()))
            else:
                choice = min(p.hand, key=lambda c: (_usefulness(c, p.hand, req, self.rules.ace_low),
                                                    -c.points, self.rng.random()))
            self._discard(p, {"card": choice.id})
        except GameError:
            # Should not happen; fall back to the plainest legal move.
            try:
                if self.phase == "draw":
                    self._draw(p, {"source": "stock"})
                else:
                    self._discard(p, {"card": max(p.hand, key=lambda c: c.points).id})
            except GameError:
                self._finish_round(None, f"{p.name} got stuck, so this hand was stopped without scoring.")

    def _suggest(self, p: Seat, data):
        """Private helper: one legal way to make this round's goal from the
        player's hand, for the lay-down builder to fill in.  Changes nothing."""
        if self.status != "playing" or p.laid:
            raise GameError("There is nothing to lay down right now.")
        found = find_laydown(p.hand, self._req(), self.rules)
        if found is None:
            return {"groups": None}
        melds, left = found
        if len(left) < self._min_keep(p) and p.seat == self.current and self.phase == "play":
            return {"groups": None}
        return {"groups": [[c.id for c in m.cards] for m in melds]}

    # ------------------------------------------------------------ view
    def view_for(self, token: str) -> dict:
        """Everything this one player may see.  Other hands are counts only;
        the draw pile is a count only."""
        with self.lock:
            me = self.seat_for(token)
            req = ROUNDS[self.round_no][0] if self.round_no else []
            dealt = ROUNDS[self.round_no][1] if self.round_no else 0
            my_turn = self.status == "playing" and self.current == me.seat
            return {
                "room": self.code,
                "version": self.version,
                "status": self.status,
                "you": me.seat,
                "host": self.host,
                "min_players": MIN_PLAYERS,
                "seconds_left": self.seconds_left(),
                "window": self.window,
                "windows": LOBBY_WINDOWS,
                "max_players": MAX_PLAYERS,
                "players": [{
                    "seat": q.seat, "name": q.name, "cards": len(q.hand), "laid": q.laid,
                    "bot": q.bot,
                    "total": q.total,
                    "rounds": {str(k): v for k, v in sorted(q.round_scores.items())},
                    "dealer": self.status != "lobby" and q.seat == self.dealer,
                    "turn": self.status == "playing" and q.seat == self.current,
                    "moves": list(q.moves),
                } for q in self.players],
                "options": {"discard_after_laydown": self.discard_after_laydown,
                            "slow_bots": self.slow_bots},
                "round": {"number": self.round_no, "last": LAST_ROUND, "dealt": dealt,
                          "goal": describe_goal(req) if req else "",
                          "groups": [{"kind": k, "size": n} for k, n in req]},
                "phase": self.phase,
                "current": self.current,
                "stock_count": len(self.stock),
                "discard_top": card_view(self.discard[-1]) if self.discard else None,
                "discard_top_by": (self.discarded_by.get(self.discard[-1].id) if self.discard else None),
                "discard_count": len(self.discard),
                "table": [{"index": i, "kind": m.kind, "owner": m.owner, "label": meld_label(m),
                           "wilds": sum(c.wild for c in m.cards),
                           "cards": [dict(card_view(c), recent=self._recent(c.id, me)) for c in m.cards]}
                          for i, m in enumerate(self.table)],
                # For each card in my hand, the groups it could go on now.
                "targets": self._targets(me) if my_turn and self.phase == "play" and me.laid else {},
                "new_group_min": {"set": NEW_SET_MIN, "run": NEW_RUN_MIN},
                "must_keep": self._min_keep(me),
                "hand": [card_view(c) for c in me.hand],
                "laid": me.laid,
                "first_turn": me.turns <= 1,
                "can": {
                    "draw": my_turn and self.phase == "draw",
                    "take_discard": (my_turn and self.phase == "draw" and bool(self.discard)
                                     and (not me.laid or self.discard_after_laydown)),
                    "options": me.seat == self.host,
                    "lay_down": my_turn and self.phase == "play" and not me.laid,
                    "play_off": my_turn and self.phase == "play" and me.laid,
                    "new_group": my_turn and self.phase == "play" and me.laid,
                    "discard": my_turn and self.phase == "play",
                    "start": self.status == "lobby" and me.seat == 0 and len(self.players) >= MIN_PLAYERS,
                    "fill_bots": self.status == "lobby" and me.seat == 0 and len(self.players) < MAX_PLAYERS,
                    "next_round": self.status == "round_over",
                },
                "last_round": self.last_round,
                "log": list(self.log),
            }

    def _targets(self, me: Seat) -> dict:
        if len(me.hand) - 1 < self._min_keep(me):
            return {}
        out = {}
        for c in me.hand:
            idx = [i for i, m in enumerate(self.table) if play_off_where(c, m, self.rules)[0] is not None]
            if idx:
                out[str(c.id)] = idx
        return out

    def wait_for_change(self, since: int, timeout: float) -> None:
        with self.changed:
            self.changed.wait_for(lambda: self.version != since, timeout=timeout)


class Lobby:
    """All rooms on this server, kept in memory (a restart clears them)."""

    def __init__(self, seed=None, lobby_seconds: float = LOBBY_SECONDS, bot_delay: float = BOT_DELAY):
        self.rooms: dict[str, Room] = {}
        self.lock = threading.Lock()
        self.rng = random.Random(seed)
        self.seed = seed
        self.lobby_seconds = lobby_seconds
        self.bot_delay = bot_delay
        self._ticker = None

    def tick(self, now=None):
        self.prune(now)
        for room in list(self.rooms.values()):
            room.tick(now)

    def prune(self, now=None):
        """Close tables no person has looked at for ROOM_IDLE_SECONDS."""
        now = now or time.time()
        with self.lock:
            for code, room in list(self.rooms.items()):
                people = room.humans()
                seen = max((p.last_seen for p in people), default=0)
                if now - seen > ROOM_IDLE_SECONDS:
                    del self.rooms[code]

    def start_ticker(self, every: float = 0.25):
        """Run the clocks and computer players in the background."""
        if self._ticker:
            return

        def loop():
            while True:
                try:
                    self.tick()
                except Exception as e:          # keep the table running
                    print("ticker error:", e)
                time.sleep(every)

        self._ticker = threading.Thread(target=loop, daemon=True)
        self._ticker.start()

    def create(self, name: str) -> tuple[Room, Seat]:
        self.prune()
        with self.lock:
            if len(self.rooms) >= MAX_ROOMS:
                raise GameError("The game is full right now. Try again in a little while.")
            for _ in range(1000):
                code = "".join(self.rng.choice(CODE_LETTERS) for _ in range(4))
                if code not in self.rooms:
                    break
            room = Room(code, seed=None if self.seed is None else f"{self.seed}-{code}",
                        lobby_seconds=self.lobby_seconds, bot_delay=self.bot_delay)
            self.rooms[code] = room
        try:
            p = room.add_player(name)
        except GameError:
            with self.lock:
                del self.rooms[code]
            raise
        return room, p

    def leave(self, code: str, token: str) -> None:
        """A person leaves; a table with no people left is closed, so its
        computer players stop playing to an empty room."""
        room = self.get(code)
        if not room.leave(token):
            with self.lock:
                self.rooms.pop(room.code, None)

    def get(self, code: str) -> Room:
        room = self.rooms.get((code or "").strip().upper())
        if room is None:
            raise KeyError("No table with that code. Check the letters and try again.")
        return room
