"""Progressive Rummy engine: cards, the 16 round goals, a lay-down finder,
an explicit lay-down validator, leftover scoring, and a simple bot game.

Rules come from Tom's two rule sheets and his answers.  Anything still not
settled is a named option in Rules (see ASSUMPTIONS below).

Version 2 (Nov 8, 2026), rules Tom confirmed after version 1:
  * After you lay down you may add cards to OTHER players' sets, not only
    your own.
  * Aces go low (A-2-3-4-5) or high (J-Q-K-A).  No wrap-around (K-A-2).
  * You may not play a card into a spot a wild card (deuce/joker) already
    holds, e.g. a deuce standing in the ace spot of a run blocks a natural
    ace from going there.  No swapping a natural card for a wild.
"""
from __future__ import annotations

import itertools
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

SUITS = ("C", "D", "H", "S")
RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}
NAME_RANKS = {"J": 11, "Q": 12, "K": 13, "A": 14}
JOKER = 0

# Round goals, exactly as on the sheet: (list of (kind, size)), cards dealt.
ROUNDS = {
    1: ([("set", 3), ("set", 3)], 11),
    2: ([("set", 3), ("run", 4)], 11),
    3: ([("run", 4), ("run", 4)], 11),
    4: ([("set", 3), ("set", 3), ("set", 3)], 11),
    5: ([("set", 3), ("run", 7)], 13),
    6: ([("set", 3), ("run", 4), ("run", 4)], 13),
    7: ([("run", 4), ("run", 4), ("run", 4)], 15),
    8: ([("set", 3), ("run", 10)], 15),
    9: ([("set", 3), ("set", 3), ("set", 3), ("run", 5)], 17),
    10: ([("run", 5), ("run", 5), ("run", 5)], 17),
    11: ([("set", 3)] * 5, 17),
    12: ([("set", 4)] * 4, 19),
    13: ([("run", 6), ("run", 6), ("run", 6)], 20),
    14: ([("run", 5), ("set", 6), ("set", 6)], 20),
    15: ([("set", 6)] * 3, 22),
    16: ([("run", 12)], 12),
}


def describe_goal(req):
    c = Counter(req)
    parts = []
    for (kind, n), k in sorted(c.items(), key=lambda x: (x[0][0] != "set", x[0][1])):
        parts.append(f"{k} {kind}{'s' if k > 1 else ''} of {n}")
    return " & ".join(parts)


# Points for cards left in hand (lowest total wins).
# CONFIRMED by Tom (v3): joker 50, deuce 25, ace 15, face cards 10,
# everything else 5.
JOKER_POINTS = 50
DEUCE_POINTS = 25
ACE_POINTS = 15
FACE_POINTS = 10
LOW_CARD_POINTS = 5


@dataclass(frozen=True)
class Card:
    id: int
    rank: int          # 2..14, 0 = joker
    suit: str | None   # None for jokers

    @property
    def wild(self):
        return self.rank in (JOKER, 2)   # deuces and jokers are wild (sheet)

    @property
    def points(self):
        if self.rank == JOKER:
            return JOKER_POINTS
        if self.rank == 2:
            return DEUCE_POINTS
        if self.rank == 14:
            return ACE_POINTS
        if self.rank >= 11:
            return FACE_POINTS
        return LOW_CARD_POINTS

    def __str__(self):
        if self.rank == JOKER:
            return "Joker"
        return f"{RANK_NAMES.get(self.rank, self.rank)}{self.suit}"

    __repr__ = __str__


def hand_points(cards, scheme="house"):
    """Points left in hand.  "house" = Tom's sheet (used everywhere).
    "online_guide" = the scoring in the online guide Tom sent (joker 25,
    face 10, ace 15, 2-10 at face value).  Comparison only; never used in play."""
    if scheme == "house":
        return sum(c.points for c in cards)
    if scheme == "online_guide":
        def pts(c):
            if c.rank == JOKER:
                return 25
            if c.rank == 14:
                return 15
            if c.rank >= 11:
                return 10
            return c.rank
        return sum(pts(c) for c in cards)
    raise ValueError(scheme)


def decks_for(players):
    return 3 if players >= 5 else 2   # sheet: 5 players 3 decks, fewer 2 decks


def make_deck(decks):
    cards, i = [], 0
    for _ in range(decks):
        for s in SUITS:
            for r in range(2, 15):
                cards.append(Card(i, r, s)); i += 1
        for _ in range(2):
            cards.append(Card(i, JOKER, None)); i += 1
    return cards


def parse_cards(text, decks=2):
    """'KH KH 10S Joker' -> Cards.  Repeated tokens are separate physical
    cards (one from each deck); more copies than the decks hold is an error."""
    out, seen = [], Counter()
    for i, tok in enumerate(text.split()):
        t = tok.upper()
        if t in ("JOKER", "JK"):
            card = Card(i, JOKER, None)
            key, limit = "Joker", 2 * decks
        else:
            r, s = t[:-1], t[-1]
            if s not in SUITS:
                raise ValueError(f"bad card {tok}")
            rank = NAME_RANKS.get(r) or int(r)
            if not 2 <= rank <= 14:
                raise ValueError(f"bad card {tok}")
            card = Card(i, rank, s)
            key, limit = str(card), decks
        seen[key] += 1
        if seen[key] > limit:
            raise ValueError(f"{key} appears {seen[key]} times but {decks} decks hold only {limit}")
        out.append(card)
    return out


@dataclass
class Rules:
    """Points the sheets leave open, each a named, switchable assumption."""
    max_wilds_per_group: int = 2   # sheet
    # CONFIRMED by Tom (v2): aces play low (A-2-3-4-5) or high (J-Q-K-A).
    # Set False only to compare with version 1.
    ace_low: bool = True
    # ASSUMPTION B (deuces): a deuce always counts as one of the two wilds, even
    # when it stands in the 2 spot.  Under this reading "if you use a wild as a
    # 2 you can only have one more wild" holds automatically.
    # Play-offs after laying down:
    #   "sets_and_runs" = CONFIRMED by Tom (v3, the normal rule): natural
    #                 cards onto your own and other players' sets, AND onto
    #                 either open end of your own or other players' runs.
    #                 ("sets_and_run_ends" is the old name and still works.)
    #   "any_sets"  = version 2 only, for comparison: sets only, no runs.
    #   "own_sets"  = version 1 only: natural cards onto your own sets.
    play_off: str = "sets_and_runs"
    # CONFIRMED by Tom (v2): a spot a wild already holds is closed.  Cards
    # only go into open spots: past either end of a run, or onto a set.
    # (Reading for sets: a set has no fixed spots, so adding another natural
    # card of the rank never takes a wild's place and stays allowed.)
    # CONFIRMED by Tom (v2): a run may be longer than the round's minimum,
    # also in the first lay-down.  Sets are laid down at their required size
    # (ASSUMPTION H); extra cards of the rank go on as play-offs.
    longer_runs: bool = True
    # ASSUMPTION J: the 2-wild limit applies to a whole run, however long.
    # ASSUMPTION I: a run holds at most one card of each rank, so at most 13
    # cards (A-K or 2-A); it cannot hold both aces.
    # CONFIRMED by Tom (v2): you go out only by discarding your last card.
    # Laying down or playing off every card with nothing left to discard is
    # not allowed, so a lay-down must leave at least one card in hand.
    keep_for_discard: int = 1
    # (Version 1 had this as ASSUMPTION E; Tom has now confirmed it.)
    # ASSUMPTION D: wild cards (deuces, jokers) cannot be added to melds after
    # the lay-down; only natural cards are played off.
    # ASSUMPTION F: "2nd time around" = a player may not go out on his own
    # first turn of the hand; on that turn he may not lay down if doing so
    # would leave him nothing after the discard.
    # ASSUMPTION G: empty draw pile -> reshuffle the discard pile except its
    # top card into a new draw pile.
    # Not a game rule, a computer-player habit for the practice games: in an
    # all-run round where nothing can be added to runs, wait to lay down until
    # the lay-down leaves just one card (the discard to go out).
    bot_waits_in_run_rounds: bool = False
    max_turns: int = 800           # safety stop; a hand that hits it is "stalled"


# ---------------------------------------------------------------- validator

def _run_positions(rank, ace_low):
    if rank == 14 and ace_low:
        return (1, 14)
    return (rank,)


def check_group(kind, n, cards, rules=Rules()):
    """Is this list of cards one legal set of n / run of at least n?
    Returns (ok, reason)."""
    if kind == "run" and rules.longer_runs:
        if len(cards) < n:
            return False, f"run needs at least {n} cards, got {len(cards)}"
        if len(cards) > 13:
            return False, "a run holds at most 13 cards (assumption I)"
    elif len(cards) != n:
        return False, f"{kind} needs {n} cards, got {len(cards)}"
    wild = [c for c in cards if c.wild]
    nat = [c for c in cards if not c.wild]
    if len(wild) > rules.max_wilds_per_group:
        return False, f"{len(wild)} wild cards (limit {rules.max_wilds_per_group})"
    if not nat:
        return False, "no natural card"
    if kind == "set":
        if len({c.rank for c in nat}) != 1:
            return False, "set cards are not all the same rank"
        return True, "ok"
    if len({c.suit for c in nat}) != 1:
        return False, "run cards are not all one suit"
    ranks = [c.rank for c in nat]
    if len(set(ranks)) != len(ranks):
        return False, "run repeats a card"
    lo = 1 if rules.ace_low else 2
    m = len(cards)
    for start in range(lo, 14 - m + 2):
        window = range(start, start + m)
        if all(any(p in window for p in _run_positions(r, rules.ace_low)) for r in ranks):
            return True, "ok"
    return False, "cards are not consecutive"


def validate_laydown(hand, req, groups, rules=Rules()):
    """Check an explicit lay-down: groups[i] is the list of Cards for req[i].
    Every required group must be there together (confirmed), and at least one
    card must stay in hand for the discard (confirmed)."""
    if len(groups) != len(req):
        return False, f"all {len(req)} required groups must be laid down together, got {len(groups)}"
    hand_ids = {c.id for c in hand}
    used = [c.id for g in groups for c in g]
    if len(used) != len(set(used)):
        return False, "a card is used in two groups"
    if not set(used) <= hand_ids:
        return False, "a card is not in the hand"
    if len(hand) - len(used) < rules.keep_for_discard:
        return False, "no card would be left to discard (you go out only by discarding)"
    set_ranks, run_suits = [], []
    for (kind, n), g in zip(req, groups):
        ok, why = check_group(kind, n, g, rules)
        if not ok:
            return False, why
        nat = [c for c in g if not c.wild]
        (set_ranks if kind == "set" else run_suits).append(nat[0].rank if kind == "set" else nat[0].suit)
    if len(set_ranks) != len(set(set_ranks)):
        return False, "two sets have the same rank"
    if len(run_suits) != len(set(run_suits)):
        return False, "two runs are in the same suit"
    return True, "ok"


# ------------------------------------------------------------------- finder

@dataclass
class Meld:
    kind: str
    cards: list
    rank: int | None = None      # sets
    suit: str | None = None      # runs
    low: int | None = None       # run positions covered
    high: int | None = None
    owner: int | None = None
    wilds_at_laydown: int = 0

    def __str__(self):
        if self.kind == "set":
            return f"set of {RANK_NAMES.get(self.rank, self.rank)}s: " + " ".join(map(str, self.cards))
        return f"run in {self.suit}: " + " ".join(map(str, self.cards))


def find_laydown(hand, req, rules=Rules()):
    """Search every way to make the round's goal from this hand without
    reusing a card.  Returns (melds, leftover) for the way that leaves the
    fewest points in hand, or None when the goal cannot be made."""
    if rules.longer_runs and any(k == "run" for k, _ in req):
        # Quick gate: a longer run always contains a run of the minimum length,
        # so if the goal cannot be made with minimum-length runs, it cannot be
        # made at all.  Only then search the longer lengths.
        if find_laydown(hand, req, replace(rules, longer_runs=False)) is None:
            return None
    nat = defaultdict(list)
    for c in hand:
        if not c.wild:
            nat[(c.rank, c.suit)].append(c)
    counts = Counter({k: len(v) for k, v in nat.items()})
    wild_cards = sorted([c for c in hand if c.wild], key=lambda c: -c.points)
    W = len(wild_cards)
    wild_prefix = [0]
    for c in wild_cards:
        wild_prefix.append(wild_prefix[-1] + c.points)
    rank_pts = {r: Card(-1, r, "S").points for r in range(3, 15)}

    order = sorted(range(len(req)), key=lambda i: (req[i][0] != "run", -req[i][1]))
    best = {"pts": -1, "plan": None}
    lo_pos = 1 if rules.ace_low else 2
    maxw = rules.max_wilds_per_group

    def pos_rank(p):
        return 14 if p == 1 else p

    max_used = len(hand) - rules.keep_for_discard

    def rec(i, wl, used_ranks, used_suits, plan, nat_pts, prev_key, ncards=0):
        if ncards > max_used:
            return
        if i == len(order):
            pts = nat_pts + wild_prefix[W - wl]
            if pts > best["pts"]:
                best["pts"], best["plan"] = pts, list(plan)
            return
        kind, n = req[order[i]]
        same_prev = i > 0 and req[order[i - 1]] == (kind, n)
        if kind == "run":
            for si, suit in enumerate(SUITS):
                if suit in used_suits or (same_prev and si <= prev_key):
                    continue
                lengths = range(n, 14) if rules.longer_runs else (n,)
                for L, start in ((L, st) for L in lengths for st in range(lo_pos, 14 - L + 2)):
                    slots = list(range(start, start + L))
                    present = [p for p in slots if p != 2 and counts[(pos_rank(p), suit)] > 0]
                    missing = L - len(present)
                    if missing > maxw or missing > wl or len(present) == 0:
                        continue
                    for extra in range(0, min(maxw - missing, wl - missing) + 1):
                        if len(present) - extra < 1:
                            break
                        for repl in itertools.combinations(present, extra):
                            use = [p for p in present if p not in repl]
                            for p in use:
                                counts[(pos_rank(p), suit)] -= 1
                            w = missing + extra
                            plan.append((order[i], "run", suit, start, L, use, w))
                            rec(i + 1, wl - w, used_ranks, used_suits | {suit}, plan,
                                nat_pts + sum(rank_pts[pos_rank(p)] for p in use), si, ncards + L)
                            plan.pop()
                            for p in use:
                                counts[(pos_rank(p), suit)] += 1
        else:
            for rank in range(3, 15):
                if rank in used_ranks or (same_prev and rank <= prev_key):
                    continue
                avail = sum(counts[(rank, s)] for s in SUITS)
                for k in range(min(avail, n), 0, -1):
                    w = n - k
                    if w > maxw or w > wl:
                        break
                    take, need = [], k
                    for s in SUITS:
                        t = min(need, counts[(rank, s)])
                        take += [s] * t
                        need -= t
                    for s in take:
                        counts[(rank, s)] -= 1
                    plan.append((order[i], "set", rank, take, w))
                    rec(i + 1, wl - w, used_ranks | {rank}, used_suits, plan,
                        nat_pts + k * rank_pts[rank], rank, ncards + n)
                    plan.pop()
                    for s in take:
                        counts[(rank, s)] += 1

    rec(0, W, frozenset(), frozenset(), [], 0, -1)
    if best["plan"] is None:
        return None

    pools = {k: list(v) for k, v in nat.items()}
    wilds = list(wild_cards)          # jokers first: they cost most if kept
    melds = [None] * len(req)
    for step in best["plan"]:
        if step[1] == "run":
            idx, _, suit, start, n, use, w = step
            cards = []
            for p in range(start, start + n):
                if p in use:
                    cards.append(pools[(pos_rank(p), suit)].pop())
                else:
                    cards.append(wilds.pop(0))
            melds[idx] = Meld("run", cards, suit=suit, low=start, high=start + n - 1)
        else:
            idx, _, rank, take, w = step
            cards = [pools[(rank, s)].pop() for s in take] + [wilds.pop(0) for _ in range(w)]
            melds[idx] = Meld("set", cards, rank=rank)
    used = {c.id for m in melds for c in m.cards}
    leftover = [c for c in hand if c.id not in used]
    return melds, leftover


# ---------------------------------------------------- brute-force cross-check

def brute_force_possible(hand, req, rules=Rules()):
    """Independent slow check used only by the tests: tries every combination
    of physical cards for every group, using check_group/validate_laydown."""
    order = sorted(range(len(req)), key=lambda i: (req[i][0] != "run", -req[i][1]))

    def rec(i, remaining, chosen, prev_key):
        if i == len(order):
            groups = [None] * len(req)
            for idx, g in chosen:
                groups[idx] = g
            return validate_laydown(hand, req, groups, rules)[0]
        kind, n = req[order[i]]
        same_prev = i > 0 and req[order[i - 1]] == (kind, n)
        for combo in itertools.combinations(remaining, n):
            if not check_group(kind, n, list(combo), rules)[0]:
                continue
            nat = next(c for c in combo if not c.wild)
            key = nat.rank if kind == "set" else SUITS.index(nat.suit)
            if same_prev and key <= prev_key:
                continue
            ids = {c.id for c in combo}
            rest = [c for c in remaining if c.id not in ids]
            if rec(i + 1, rest, chosen + [(order[i], list(combo))], key):
                return True
        return False

    return rec(0, list(hand), [], -1)


def brute_force_best_points(hand, req, rules=Rules()):
    """Slow, independent check for the tests: tries every combination of cards,
    runs of every allowed length, and returns the most points that can be laid
    down (None if the goal cannot be made).  Only practical for small rounds."""
    order = sorted(range(len(req)), key=lambda i: (req[i][0] != "run", -req[i][1]))
    best = [None]

    def rec(i, remaining, chosen, prev_key):
        if i == len(order):
            groups = [None] * len(req)
            for idx, g in chosen:
                groups[idx] = g
            if validate_laydown(hand, req, groups, rules)[0]:
                pts = sum(c.points for g in groups for c in g)
                if best[0] is None or pts > best[0]:
                    best[0] = pts
            return
        kind, n = req[order[i]]
        same_prev = i > 0 and req[order[i - 1]] == (kind, n)
        sizes = range(n, min(13, len(remaining)) + 1) if (kind == "run" and rules.longer_runs) else (n,)
        for size in sizes:
            for combo in itertools.combinations(remaining, size):
                if not check_group(kind, n, list(combo), rules)[0]:
                    continue
                nat = next(c for c in combo if not c.wild)
                key = nat.rank if kind == "set" else SUITS.index(nat.suit)
                if same_prev and key <= prev_key:
                    continue
                ids = {c.id for c in combo}
                rest = [c for c in remaining if c.id not in ids]
                rec(i + 1, rest, chosen + [(order[i], list(combo))], key)

    rec(0, list(hand), [], -1)
    return best[0]


# --------------------------------------------------------------- bot game

def check_play_off(card, meld, rules=Rules(), position=None):
    """Can this card be added to a meld already on the table?
    For a run, `position` is the spot asked for (1 = ace low, 2..13, 14 = ace
    high); None means any open spot.  Returns (where, reason): where is
    'add' (set), 'high' / 'low' (run end), or None when not allowed."""
    if card.wild:
        return None, "adding wild cards after laying down is not allowed (assumption D)"
    if meld.kind == "set":
        if card.rank != meld.rank:
            return None, "wrong rank for this set"
        return "add", "ok"
    if card.suit != meld.suit:
        return None, "wrong suit for this run"
    positions = _run_positions(card.rank, rules.ace_low)
    if position is not None:
        if position not in positions:
            return None, "that card does not belong in that spot"
        positions = (position,)
    lo = 1 if rules.ace_low else 2
    # Open spots first: an occupied spot never blocks a legal extension
    # beyond the run (Tom, v2).
    full = len(meld.cards) >= 13
    for p in positions:
        if full:
            break
        if p == meld.high + 1 and p <= 14:
            return "high", "ok"
        if p == meld.low - 1 and p >= lo:
            return "low", "ok"
    for p in positions:
        if meld.low <= p <= meld.high:
            holder = meld.cards[p - meld.low]
            if holder.wild:
                return None, f"{holder} already holds that spot (a wild's spot is closed; it cannot be replaced)"
            return None, f"{holder} already holds that spot"
    if full:
        return None, "a run holds at most 13 cards (assumption I)"
    return None, "not next to either end of the run"


def meld_consistent(meld, rules=Rules()):
    """Table check used during games: every natural card in a run sits in its
    own spot, the run has no gap, and no run passes the aces."""
    if meld.kind == "set":
        return all(c.wild or c.rank == meld.rank for c in meld.cards)
    if meld.high - meld.low + 1 != len(meld.cards) or len(meld.cards) > 13:
        return False
    if meld.low < (1 if rules.ace_low else 2) or meld.high > 14:
        return False
    return all(c.wild or (meld.low + i in _run_positions(c.rank, rules.ace_low) and c.suit == meld.suit)
               for i, c in enumerate(meld.cards))


def _fits(card, meld, rules):
    return check_play_off(card, meld, rules)[0]


def _may_play_on(meld, seat, rules):
    if rules.play_off == "own_sets":
        return meld.kind == "set" and meld.owner == seat
    if rules.play_off == "any_sets":
        return meld.kind == "set"
    if rules.play_off in ("sets_and_runs", "sets_and_run_ends"):
        return True
    raise ValueError(f"unknown play_off rule {rules.play_off}")


class Player:
    def __init__(self, seat):
        self.seat = seat
        self.hand = []
        self.laid = False
        self.turns = 0


def _usefulness(card, hand, req, ace_low=True):
    if card.wild:
        return 100
    kinds = {k for k, _ in req}
    u = 0
    others = [c for c in hand if c.id != card.id and not c.wild]
    if "set" in kinds:
        u += 3 * sum(1 for c in others if c.rank == card.rank)
    if "run" in kinds:
        reach = max(n for k, n in req if k == "run") - 1
        mine = _run_positions(card.rank, ace_low)
        near = set()
        for c in others:
            if c.suit != card.suit:
                continue
            if any(0 < abs(a - b) <= reach for a in mine for b in _run_positions(c.rank, ace_low)):
                near.add(c.rank)
        u += 2 * len(near)
    return u


def play_hand(players, req, dealt, dealer, rules, rng, log=None):
    """Play one hand with simple bots.  Returns dict with winner, points per
    seat (cards left in hand), turns, and whether the hand stalled."""
    n = len(players)
    deck = make_deck(decks_for(n))
    rng.shuffle(deck)
    for p in players:
        p.hand, p.laid, p.turns = [], False, 0
    # deal one card at a time, clockwise, starting left of the dealer
    for _ in range(dealt):
        for k in range(1, n + 1):
            players[(dealer + k) % n].hand.append(deck.pop())
    stock = deck
    discard = [stock.pop()]
    table = []
    turn = 0
    seat = (dealer + 1) % n            # player to the dealer's left picks first
    reshuffles = 0
    plays = {"own": 0, "other_set": 0, "other_run": 0}
    while turn < rules.max_turns:
        p = players[seat]
        p.turns += 1
        turn += 1
        first_lap = p.turns == 1
        # 1. draw
        top = discard[-1] if discard else None
        take = False
        if top is not None and not p.laid:
            if top.wild or _usefulness(top, p.hand + [top], req, rules.ace_low) >= 3 or \
                    find_laydown(p.hand + [top], req, rules) is not None:
                take = True
        if take:
            assert not p.laid
            p.hand.append(discard.pop())
        else:
            if not stock:
                if len(discard) <= 1:
                    return {"stalled": True, "reason": "no cards left to draw", "turns": turn,
                            "reshuffles": reshuffles, "plays": plays, "laid_down": sum(q.laid for q in players),
                            "held": [len(q.hand) for q in players]}
                keep = discard.pop()
                stock = discard
                rng.shuffle(stock)
                discard = [keep]
                reshuffles += 1
            p.hand.append(stock.pop())
        # 2. lay down
        if not p.laid:
            res = find_laydown(p.hand, req, rules)
            if res is not None:
                melds, left = res
                stuck = (rules.bot_waits_in_run_rounds
                         and rules.play_off not in ("sets_and_runs", "sets_and_run_ends")
                         and all(k == "run" for k, _ in req) and len(left) > 1)
                if not (first_lap and len(left) <= 1) and not stuck:
                    ok, why = validate_laydown(p.hand, req, [m.cards for m in melds], rules)
                    assert ok, f"bot lay-down failed validation: {why}"
                    for m in melds:
                        m.owner = p.seat
                        m.wilds_at_laydown = sum(c.wild for c in m.cards)
                    table.extend(melds)
                    p.hand = left
                    p.laid = True
                    if log is not None:
                        log.append(f"turn {turn}: seat {seat} lays down " + "; ".join(map(str, melds)))
        # 3. play off (keep at least one card to discard; two on the first lap)
        if p.laid:
            min_keep = 2 if first_lap else 1
            played = True
            while played and len(p.hand) > min_keep:
                played = False
                for c in sorted(p.hand, key=lambda c: -c.points):
                    for m in table:
                        if not _may_play_on(m, p.seat, rules):
                            continue
                        where = _fits(c, m, rules)
                        if where is None:
                            continue
                        if m.owner == p.seat:
                            plays["own"] += 1
                        else:
                            plays["other_" + m.kind] += 1
                        if where == "high":
                            m.cards.append(c); m.high += 1
                        elif where == "low":
                            m.cards.insert(0, c); m.low -= 1
                        else:
                            m.cards.append(c)
                        p.hand.remove(c)
                        played = True
                        break
                    if played:
                        break
        # 4. discard
        if p.laid:
            choice = max(p.hand, key=lambda c: (c.points, rng.random()))
        else:
            choice = min(p.hand, key=lambda c: (_usefulness(c, p.hand, req, rules.ace_low), -c.points, rng.random()))
        p.hand.remove(choice)
        discard.append(choice)
        total = len(stock) + len(discard) + sum(len(q.hand) for q in players) + \
            sum(len(m.cards) for m in table)
        assert total == len(make_deck(decks_for(n))), "card count changed"
        for m in table:
            assert meld_consistent(m, rules), f"table meld broken: {m}"
            assert sum(c.wild for c in m.cards) == m.wilds_at_laydown, "a wild was moved or replaced"
        if not p.hand:
            assert p.turns >= 2, "went out on first time around"
            pts = {q.seat: hand_points(q.hand) for q in players}
            return {"stalled": False, "winner": seat, "points": pts, "turns": turn,
                    "reshuffles": reshuffles, "plays": plays,
                    "left": {q.seat: [str(c) for c in q.hand] for q in players}}
        seat = (seat + 1) % n
    return {"stalled": True, "reason": f"hit {rules.max_turns}-turn safety stop", "turns": turn,
            "reshuffles": reshuffles, "plays": plays, "laid_down": sum(q.laid for q in players),
            "held": [len(q.hand) for q in players]}


def play_game(n_players=4, seed=1, rules=Rules(), rounds=range(1, 17)):
    rng = random.Random(seed)
    players = [Player(i) for i in range(n_players)]
    totals = {i: 0 for i in range(n_players)}
    results = []
    for r in rounds:
        req, dealt = ROUNDS[r]
        dealer = (r - 1) % n_players
        res = play_hand(players, req, dealt, dealer, rules, rng)
        res["round"] = r
        if not res["stalled"]:
            for s, v in res["points"].items():
                totals[s] += v
        results.append(res)
    return results, totals
