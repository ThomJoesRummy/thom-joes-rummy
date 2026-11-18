"""Hand-validation tests for all 16 rounds.  Every expected answer is checked
twice: by find_laydown (fast search) and by brute_force_possible (slow,
independent search over every card combination).  Every lay-down the finder
returns is also re-checked by validate_laydown."""
import random
import sys
import time

from rummy import (ROUNDS, Rules, Card, Meld, brute_force_best_points, brute_force_possible, check_play_off, describe_goal,
                   find_laydown, hand_points, make_deck, parse_cards, validate_laydown, _may_play_on,
                   play_game)

X6 = lambda r: f"{r}C {r}D {r}S {r}H {r}C {r}D"   # six of a rank (two decks)

# (round, label, hand, expected, rules or None)
CASES = [
    (1, "two sets, joker fills one", "KC KD KS QC QD Joker 3C 6D 8H 10S AC", True),
    (1, "six fives = same rank twice", "5C 5D 5H 5S 5C 5D 3C 6D 8H 10S AC", False),
    (2, "kings + 5-8 hearts, joker as 7", "KC KD KS 5H 6H Joker 8H 3C 9D JS AC", True),
    (2, "KH needed in set and run", "KC KD KH JH QH AH 3C 5D 7S 9C 9D", False),

    (3, "5-8 hearts + 9-Q spades", "5H 6H 7H 8H 9S 10S JS QS 3C 6D KC", True),
    (3, "both runs in hearts", "3H 4H 5H 6H 9H 10H JH QH 3C 6D KC", False),
    (3, "one joker needed by both runs", "5H 6H Joker 8H 9S JS QS 3C 6D KC 4D", False),
    (3, "run would need 3 wilds", "5H Joker 2C 2D 9S 10S JS QS 3C 6D KC", False),

    (4, "K, Q+joker, 7", "KC KD KS QC QH Joker 7C 7D 7S 4H 9D", True),
    (4, "six kings = same rank twice", "KC KD KS KH KC KD 4H 9D 6S 8C 10H", False),
    (4, "one joker needed by two sets", "KC KD Joker QC QH 7C 7D 7S 4H 9D 6S", False),
    (4, "third set would be all wilds", "KC KD KS KH QC QD QH QS Joker Joker 2D", False),

    (5, "4-10 hearts (joker as 10) + aces", "4H 5H 6H 7H 8H 9H Joker AC AD AS 3C 9D QS", True),
    (5, "KH needed in set and run", "7H 8H 9H 10H JH QH KH KS KD 3C 5D 9S 4C", False),
    (5, "run of 7 would need 3 wilds", "4H 5H Joker 2C 2D 9H 10H AC AD AS 3C 9D QS", False),

    (6, "kings + hearts run + spades run", "5H 6H 7H 8H 9S 10S Joker QS KC KD KS 3C 6D", True),
    (6, "both runs in hearts", "3H 4H 5H 6H 9H 10H JH QH KC KD KS 3C 6D", False),
    (6, "KH needed in set and run", "10H JH QH KH 9S 10S JS QS KC KD 3C 6D 4S", False),
    (6, "run would need 3 wilds", "5H 2C 2D Joker 9S 10S JS QS KC KD KS 3C 6D", False),

    (7, "three runs incl. J-Q-K-A clubs", "5H 6H 7H 8H 9S 10S JS QS JC QC KC AC 3D 7D 10D", True),
    (7, "two of the runs in hearts", "3H 4H 5H 6H 7H 8H 9H 10H JC QC KC AC 3D 7D 10D", False),
    (7, "one joker needed by two runs", "5H 6H 8H 9S 10S JS QS JC QC AC Joker 3D 7D 10D 5D", False),
    (7, "run would need 3 wilds", "5H Joker 2C 2D 9S 10S JS QS JC QC KC AC 3D 8D KD", False),

    (8, "3-Q spades (joker as 9) + nines", "3S 4S 5S 6S 7S 8S Joker 10S JS QS 9C 9D 9H 4D KH", True),
    (8, "KS needed in set and run", "4S 5S 6S 7S 8S 9S 10S JS QS KS KC KD 3C 6D 8H", False),
    (8, "run of 10 would need 3 wilds", "3S 4S 5S 6S 7S Joker 2C 2D JS QS 9C 9D 9H 4D KH", False),

    (9, "K, Q+joker, 4 + 5-9 hearts", "5H 6H 7H 8H 9H KC KD KS QC QD Joker 4C 4D 4S 3S 7D 10C", True),
    (9, "two king sets = same rank", "5H 6H 7H 8H 9H KC KD KS KC KD KH 4C 4D 4S 3S 7D 10C", False),
    (9, "9H needed in set and run", "5H 6H 7H 8H 9H 9C 9D KC KD KS 4C 4D 4S 3S 7D 10C AC", False),
    (9, "run of 5 would need 3 wilds", "5H 9H Joker 2D 2S KC KD KS QC QD QS 4C 4D 4S 3S 7D 8C", False),

    (10, "three runs of 5", "4H 5H 6H 7H 8H 9S 10S JS QS KS 10C JC QC KC AC 3D 6D", True),
    (10, "two of the runs in hearts", "3H 4H 5H 6H 7H 8H 9H 10H JH QH 10C JC QC KC AC 3D 6D", False),
    (10, "one joker needed by two runs", "4H 5H 7H 8H 9S 10S QS KS 10C JC QC KC AC Joker 3D 6D 9D", False),
    (10, "run would need 3 wilds", "4H Joker 2C 2D 8H 9S 10S JS QS KS 10C JC QC KC AC 3D 6D", False),

    (11, "five sets, joker in jacks", "3C 3D 3S 5C 5D 5H 8C 8D 8S JC JD Joker AC AD AH 6S 9H", True),
    (11, "six threes = same rank twice", "3C 3D 3S 3H 3C 3D 5C 5D 5H 8C 8D 8S JC JD JH 6S 9H", False),
    (11, "one joker needed by two sets", "3C 3D 3S 5C 5D 8C 8D JC JD JH AC AD AH Joker 6S 9H KD", False),
    (11, "fifth set would be all wilds", "3C 3D 3S 3H 5C 5D 5H 5S 8C 8D 8S JC JD JH Joker 2D 2S", False),

    (12, "four sets of 4, two wilds in eights", "3C 3D 3S 3H 5C 5D 5H 5S 8C 8D Joker 2H JC JD JH JS 6S 9H KD", True),
    (12, "eights would need 3 wilds", "3C 3D 3S 3H 5C 5D 5H 5S JC JD JH JS 8C Joker 2H 2D 6S 9H KD", False),
    (12, "one joker needed by two sets", "3C 3D 3S 3H 5C 5D 5H 5S JC JD JH 8C 8D 8S Joker 6S 9H KD AC", False),

    (13, "three runs of 6, joker in clubs", "3H 4H 5H 6H 7H 8H 9S 10S JS QS KS AS 5C 6C Joker 8C 9C 10C 3D 7D", True),
    (13, "two of the runs in hearts", "3H 4H 5H 6H 7H 8H 9H 10H JH QH KH AH 5C 6C 7C 8C 9C 10C 3D 7D", False),
    (13, "one joker needed by two runs", "3H 4H 5H 7H 8H 9S 10S JS KS AS 5C 6C 7C 8C 9C 10C Joker 3D 7D 6D", False),
    (13, "run would need 3 wilds", "3H 4H 5H 6H 7H 8H 9S 10S JS QS KS AS 5C Joker 2D 2H 9C 10C 3D 7D", False),

    (14, "4-8 hearts + six kings + queens w/ 2 wilds", f"4H 5H 6H 7H 8H {X6('K')} QC QD QS QH Joker 2S 3S 9D 10C", True),
    (14, "KH needed in king set and run", "9H 10H JH QH KH KC KD KS KC KD QC QD QS QH QC QD 3S 7D 4C 6S", False),
    (14, "eight kings, queens short = same rank twice", "4H 5H 6H 7H 8H KC KD KS KH KC KD KS KH QC QD QS 3S 9D 10C 6C", False),
    (14, "queens would need 3 wilds", f"4H 5H 6H 7H 8H {X6('K')} QC QD QS Joker 2S 2D 3S 9D 10C", False),

    (15, "three sets of 6, two wilds in eights", f"{X6('3')} {X6('5')} 8C 8D 8S 8H Joker 2H 6S 9H KD AC", True),
    (15, "eights would need 3 wilds", f"{X6('3')} {X6('5')} 8C 8D 8S Joker 2H 2D 6S 9H KD AC", False),
    (15, "eight threes = same rank twice", f"{X6('3')} 3S 3H {X6('5')} 8C 8D 8S 6S 9H KD AC JC", False),

    (16, "3 through A of hearts", "3H 4H 5H 6H 7H 8H 9H 10H JH QH KH AH", True),
    (16, "two jokers inside the run", "3H 4H Joker 6H 7H 8H 9H Joker JH QH KH AH", True),
    (16, "run would need 3 wilds", "3H 4H Joker 6H 2C 8H 2D 10H JH QH KH AH", False),
    (16, "2 spot filled by a deuce (assumption B)", "2C 3S 4S 5S 6S 7S 8S 9S 10S JS QS KS", True),
    (16, "A-2-3...Q hearts with a deuce", "AH 2C 3H 4H 5H 6H 7H 8H 9H 10H JH QH", True),
    (2, "kings + A-2-3-4 hearts, ace-low switched off (version 1 rule)", "KC KD KS AH 2C 3H 4H 9D JS 6C 8D", False, Rules(ace_low=False, keep_for_discard=0)),
    (2, "kings + A-2-3-4 hearts, ace low (confirmed)", "KC KD KS AH 2C 3H 4H 9D JS 6C 8D", True),
]

# Version 2: aces low or high (confirmed by Tom), no wrap-around.
ACE_CASES = [
    (3, "A-2-3-4 hearts (deuce as 2) + 9-Q spades", "AH 2C 3H 4H 9S 10S JS QS 3C 6D KC", True),
    (3, "same hand with ace-low off", "AH 2C 3H 4H 9S 10S JS QS 3C 6D KC", False, Rules(ace_low=False, keep_for_discard=0)),
    (3, "K-A-2-3 hearts would wrap around", "KH AH 2C 3H 9S 10S JS QS 3C 6D KC", False),
    (5, "A-7 hearts + kings", "AH 2C 3H 4H 5H 6H 7H KC KD KS 9D JS 8C", True),
    (6, "kings + A-4 hearts + 9-Q spades", "AH 2C 3H 4H 9S 10S JS QS KC KD KS 3C 6D", True),
    (7, "A-2-3-4 clubs low and J-Q-K-A hearts high", "AC 2D 3C 4C JH QH KH AH 5S 6S 7S 8S 3D 7D 10D", True),
    (8, "A-10 spades + nines", "AS 2C 3S 4S 5S 6S 7S 8S 9S 10S 9C 9D 9H 4D KH", True),
    (9, "three sets + A-5 hearts", "AH 2C 3H 4H 5H KC KD KS QC QD QS 4C 4D 4S 3S 7D 10C", True),
    (10, "A-5 hearts low, 10-A clubs high, 9-K spades", "AH 3H 4H 5H 2C 9S 10S JS QS KS 10C JC QC KC AC 3D 6D", True),
    (13, "A-6 hearts low, 9-A spades high, 5-10 clubs", "AH 2C 3H 4H 5H 6H 9S 10S JS QS KS AS 5C 6C 7C 8C 9C 10C 3D 7D", True),
    (14, "A-5 hearts + six kings + queens with two wilds", f"AH 2C 3H 4H 5H {X6('K')} QC QD QS QH Joker 2S 3S 9D 10C", True),
    (16, "A through Q of spades (deuce as 2)", "AS 2D 3S 4S 5S 6S 7S 8S 9S 10S JS QS", True),
    (16, "Q-K-A-2-3...9 hearts would wrap around", "QH KH AH 2C 3H 4H 5H 6H 7H 8H 9H JD", False),
]
CASES = CASES + ACE_CASES

# Version 2: runs may be longer than the minimum (confirmed).  Expected = the
# lay-down the finder should pick, checked against a slow brute force that
# tries every run length.  (round, label, hand, expected cards laid down)
LONG_RUN_CASES = [
    (3, "5-10 hearts goes down as a 6-card run", "5H 6H 7H 8H 9H 10H 9S 10S JS QS 3C 6D", 10),
    (3, "two long runs leave only the 3 of clubs", "4H 5H 6H 7H 8H 9H 8S 9S 10S JS QS 3C", 11),
    (5, "kings + 3-10 hearts (8 long) for a run of 7", "3H 4H 5H 6H 7H 8H 9H 10H KC KD KS 4C 9D 6S", 11),
    (16, "13 hearts 2-A: a 13-card run is legal but would leave no discard, so 12 go down", "2C 3H 4H 5H 6H 7H 8H 9H 10H JH QH KH AH", 12),
]


def long_run_cases(out):
    fails = 0
    for rnd, label, text, exp_laid in LONG_RUN_CASES:
        req, dealt = ROUNDS[rnd]
        hand = parse_cards(text)
        res = find_laydown(hand, req)
        best = brute_force_best_points(hand, req)
        if res is None:
            fails += 1
            out.append(f"long-run R{rnd} [MISMATCH] {label}: finder found nothing")
            continue
        melds, left = res
        laid = sum(len(m.cards) for m in melds)
        ok, why = validate_laydown(hand, req, [m.cards for m in melds])
        pts = hand_points(hand) - hand_points(left)
        st = "ok" if (ok and laid == exp_laid and pts == best) else "MISMATCH"
        fails += st != "ok"
        out.append(f"long-run R{rnd} [{st}] {label}: {len(hand)} cards, finder lays down {laid} "
                   f"(expected {exp_laid}), {pts} pts laid vs brute-force best {best}; "
                   f"{' ; '.join(map(str, melds))} | left {' '.join(map(str, left))}")
    # explicit validator: a run longer than required is accepted
    h = parse_cards("5H 6H 7H 8H 9H 10H 9S 10S JS QS 3C 6D")
    ok, why = validate_laydown(h, ROUNDS[3][0], [h[:6], h[6:10]])
    st = "ok" if ok else "MISMATCH"; fails += st != "ok"
    out.append(f"validator [{st}] round 3 with a 6-card and a 4-card run: {'accepted' if ok else 'rejected'} ({why})")
    return fails


def discard_rule_cases(out):
    """Version 2 (confirmed): every required group goes down together, and
    going out needs a final discard."""
    fails = 0
    h = parse_cards("5H 6H 7H 8H 9S 10S JS QS 3C 6D KC 4D")
    ok, why = validate_laydown(h, ROUNDS[3][0], [h[:4]])
    st = "ok" if not ok else "MISMATCH"; fails += st != "ok"
    out.append(f"lay-down rule [{st}] round 3, only one of the two runs put down: {'accepted' if ok else 'rejected'} ({why})")
    h16 = parse_cards("3H 4H 5H 6H 7H 8H 9H 10H JH QH KH AH")
    ok, why = validate_laydown(h16, ROUNDS[16][0], [h16])
    st = "ok" if not ok else "MISMATCH"; fails += st != "ok"
    out.append(f"discard rule [{st}] round 16, 12-card hand all laid down with nothing to discard: {'accepted' if ok else 'rejected'} ({why})")
    h16b = parse_cards("3H 4H 5H 6H 7H 8H 9H 10H JH QH KH AH 7C")
    ok, why = validate_laydown(h16b, ROUNDS[16][0], [h16b[:12]])
    st = "ok" if ok else "MISMATCH"; fails += st != "ok"
    out.append(f"discard rule [{st}] round 16, 13 cards, 12 laid down and the 7 of clubs kept to discard: {'accepted' if ok else 'rejected'} ({why})")
    res = find_laydown(h16, ROUNDS[16][0])
    st = "ok" if res is None else "MISMATCH"; fails += st != "ok"
    out.append(f"discard rule [{st}] finder on the 12-card round 16 hand: {'no lay-down (nothing would be left to discard)' if res is None else 'laid down'}")
    return fails


def run_cases(out):
    fails = 0
    for case in CASES:
        rnd, label, text, expected = case[:4]
        # Hand tests are dealt-size hands and ask only "can this hand make the
        # goal?", so the keep-a-card-to-discard rule is off here and tested
        # separately in discard_rule_cases.
        rules = case[4] if len(case) > 4 else Rules(keep_for_discard=0)
        req, dealt = ROUNDS[rnd]
        hand = parse_cards(text)
        size_ok = len(hand) == dealt
        t0 = time.time()
        res = find_laydown(hand, req, rules)
        t1 = time.time()
        brute = brute_force_possible(hand, req, rules)
        t2 = time.time()
        got = res is not None
        extra = ""
        if res is not None:
            melds, left = res
            ok, why = validate_laydown(hand, req, [m.cards for m in melds], rules)
            if not ok:
                fails += 1
                extra += f" VALIDATOR REJECTED FINDER RESULT: {why}"
            extra += " | " + " ; ".join(map(str, melds))
            extra += f" | left {' '.join(map(str, left)) or '(none)'} = {hand_points(left)} pts"
        status = "ok" if (got == expected == brute and size_ok) else "MISMATCH"
        if status != "ok":
            fails += 1
        out.append(f"R{rnd:>2} [{status}] {label}: expected {'can' if expected else 'cannot'} lay down; "
                   f"finder={'yes' if got else 'no'}, brute force={'yes' if brute else 'no'}, "
                   f"{len(hand)} cards (deal {dealt}), {1000*(t1-t0):.1f} ms / {1000*(t2-t1):.0f} ms{extra}")
    return fails


def explicit_validator_cases(out):
    """Hand-built lay-downs the validator must reject or accept."""
    fails = 0
    h = parse_cards("KC KD KS KH 5H 6H 7H 3C 9D JS AC Joker")
    K = {str(c): c for c in h}
    req = ROUNDS[2][0]
    checks = [
        ("KH used in both the set and the run", [[K["KC"], K["KD"], K["KH"]], [K["KH"], K["5H"], K["6H"], K["7H"]]], False),
        ("same layout but legal (joker in the run)", [[K["KC"], K["KD"], K["KH"]], [K["Joker"], K["5H"], K["6H"], K["7H"]]], True),
        ("card not in the hand", [[K["KC"], K["KD"], K["KS"]], [Card(999, 8, "H"), K["5H"], K["6H"], K["7H"]]], False),
    ]
    for label, groups, exp in checks:
        ok, why = validate_laydown(h, req, groups)
        st = "ok" if ok == exp else "MISMATCH"
        fails += st != "ok"
        out.append(f"validator [{st}] {label}: {'accepted' if ok else 'rejected'} ({why})")
    h3 = parse_cards("8C Joker 2H 2D 5C 5D 5H 5S 7C")
    K3 = {str(c): c for c in h3}
    ok, why = validate_laydown(h3, [("set", 4), ("set", 4)],
                               [[K3["8C"], K3["Joker"], K3["2H"], K3["2D"]], [K3["5C"], K3["5D"], K3["5H"], K3["5S"]]])
    st = "ok" if not ok else "MISMATCH"; fails += st != "ok"
    out.append(f"validator [{st}] set of 4 with one 8 and three wilds: {'accepted' if ok else 'rejected'} ({why})")
    h4 = parse_cards("3H 4H 5H 6H 9H 10H JH QH 7C")
    ok, why = validate_laydown(h4, ROUNDS[3][0], [h4[:4], h4[4:8]])
    st = "ok" if not ok else "MISMATCH"; fails += st != "ok"
    out.append(f"validator [{st}] two runs both in hearts: {'accepted' if ok else 'rejected'} ({why})")
    h5 = parse_cards("KC KD KS KH KC KD 7C")
    ok, why = validate_laydown(h5, ROUNDS[1][0], [h5[:3], h5[3:6]])
    st = "ok" if not ok else "MISMATCH"; fails += st != "ok"
    out.append(f"validator [{st}] two sets both kings: {'accepted' if ok else 'rejected'} ({why})")
    try:
        parse_cards("KH KH KH")
        out.append("parser [MISMATCH] three KH accepted with two decks"); fails += 1
    except ValueError as e:
        out.append(f"parser [ok] three KH with two decks rejected ({e})")
    parse_cards("KH KH KH", decks=3)
    out.append("parser [ok] three KH with three decks accepted")
    return fails


def play_off_cases(out):
    """Version 2: adding cards to melds already on the table."""
    fails = 0
    c = {str(x): x for x in parse_cards("JH QH KH 2C AH 10H 9H 3S 4S Joker 6S 5S 7S AS 2D AD 3D 4D 5D KD KC KS QS")}
    run_jqk2 = Meld("run", [c["JH"], c["QH"], c["KH"], c["2C"]], suit="H", low=11, high=14, owner=1)
    run_joker = Meld("run", [c["3S"], c["4S"], c["Joker"], c["6S"]], suit="S", low=3, high=6, owner=1)
    run_a234 = Meld("run", [c["AD"], c["2D"], c["3D"], c["4D"]], suit="D", low=1, high=4, owner=1)
    set_k = Meld("set", [c["KC"], c["KS"], c["Joker"]], rank=13, owner=1)
    e = {str(x): x for x in parse_cards("Joker 2H 3D 4D 5D AD 6D AC")}
    run_jk_a5 = Meld("run", [e["Joker"], e["2H"], e["3D"], e["4D"], e["5D"]], suit="D", low=1, high=5, owner=1)
    clubs = parse_cards("Joker 2S 3C 4C 5C 6C 7C 8C 9C 10C JC QC KC")
    run_jk_ak = Meld("run", clubs, suit="C", low=1, high=13, owner=1)
    checks = [
        ("natural ace onto J-Q-K run where a deuce holds the ace spot", c["AH"], run_jqk2, None, None),
        ("same ace, asked for the low ace spot of J-Q-K-(deuce)", c["AH"], run_jqk2, 1, None),
        ("10 of hearts onto the open low end of J-Q-K-(deuce)", c["10H"], run_jqk2, None, "low"),
        ("5 of spades where a joker holds the 5 spot in 3-4-(joker)-6", c["5S"], run_joker, None, None),
        ("7 of spades onto the open high end of 3-4-(joker)-6", c["7S"], run_joker, None, "high"),
        ("ace of spades onto 3-4-(joker)-6 (2 spot is between, not open)", c["AS"], run_joker, None, None),
        ("5 of diamonds onto A-2-3-4 diamonds", c["5D"], run_a234, None, "high"),
        ("king of diamonds below A-2-3-4 diamonds (wrap-around)", c["KD"], run_a234, None, None),
        ("natural ace onto (joker as ace)-2-3-4-5 diamonds: joker holds the low ace spot", e["AD"], run_jk_a5, None, None),
        ("6 of diamonds onto the open high end of (joker)-2-3-4-5", e["6D"], run_jk_a5, None, "high"),
        ("ace of clubs onto 13-card (joker as A)-2-...-K clubs: no open spot left", e["AC"], run_jk_ak, None, None),
        ("same ace forced into the low spot the joker holds", e["AC"], run_jk_ak, 1, None),
        ("another king onto K-K-(joker) set (no wild replaced)", c["KD"], set_k, None, "add"),
        ("queen onto a set of kings", c["QS"], set_k, None, None),
        ("deuce (wild) onto a set after laying down (assumption D)", c["2D"], set_k, None, None),
    ]
    for label, card, meld, pos, exp in checks:
        where, why = check_play_off(card, meld, Rules(), pos)
        st = "ok" if where == exp else "MISMATCH"
        fails += st != "ok"
        out.append(f"play-off [{st}] {label}: {where or 'refused'} ({why})")
    own_set = Meld("set", [], rank=9, owner=0)
    other_set = Meld("set", [], rank=9, owner=1)
    other_run = Meld("run", [], suit="H", low=3, high=6, owner=1)
    own_run = Meld("run", [], suit="H", low=3, high=6, owner=0)
    table = [("sets_and_runs", own_set, True), ("sets_and_runs", other_set, True),
             ("sets_and_runs", own_run, True), ("sets_and_runs", other_run, True),
             ("own_sets", own_set, True), ("own_sets", other_set, False), ("own_sets", own_run, False),
             ("any_sets", own_set, True), ("any_sets", other_set, True), ("any_sets", other_run, False),
             ("any_sets", own_run, False),
             ("sets_and_run_ends", other_run, True), ("sets_and_run_ends", own_run, True)]
    for mode, meld, exp in table:
        got = _may_play_on(meld, 0, Rules(play_off=mode))
        st = "ok" if got == exp else "MISMATCH"; fails += st != "ok"
        whose = "own" if meld.owner == 0 else "another player's"
        out.append(f"who-can-play [{st}] rule '{mode}': {whose} {meld.kind} -> {'allowed' if got else 'not allowed'}")
    return fails


def table_play_cases(out):
    """Version 3: Tom confirmed cards can go on the ends of runs, his own and
    other players'.  These checks use the normal rules (Rules()) and the same
    two steps a player's turn uses: may I play on this meld, and does the card
    fit an open spot.  Seat 0 is 'me'; seat 1 is another player."""
    fails = 0
    st = "ok" if Rules().play_off == "sets_and_runs" else "MISMATCH"; fails += st != "ok"
    out.append(f"table [{st}] normal rule is now 'sets_and_runs' (cards on sets and run ends, anyone's)")
    c = {str(x): x for x in parse_cards("5H 6H 7H 8H 4H 9H 3H 10S JS QS KS 9S AS Joker 2C 4D 5D 6D 3D 7D 7C AD AH 10H")}
    mine = Meld("run", [c["5H"], c["6H"], c["7H"], c["8H"]], suit="H", low=5, high=8, owner=0)
    theirs = Meld("run", [c["10S"], c["JS"], c["QS"], c["KS"]], suit="S", low=10, high=13, owner=1)
    theirs_wild_top = Meld("run", [c["4D"], c["5D"], c["6D"], c["Joker"]], suit="D", low=4, high=7, owner=1)
    theirs_wild_low = Meld("run", [c["2C"], c["4D"], c["5D"], c["6D"]], suit="D", low=3, high=6, owner=1)
    rules = Rules()
    checks = [
        ("4 of hearts below MY 5-6-7-8 hearts", c["4H"], mine, "low"),
        ("9 of hearts above MY 5-6-7-8 hearts", c["9H"], mine, "high"),
        ("3 of hearts onto MY 5-8 hearts (gap, not next to an end)", c["3H"], mine, None),
        ("9 of spades below ANOTHER player's 10-J-Q-K spades", c["9S"], theirs, "low"),
        ("ace of spades above ANOTHER player's 10-J-Q-K spades", c["AS"], theirs, "high"),
        ("10 of hearts onto ANOTHER player's spade run (wrong suit)", c["10H"], theirs, None),
        ("7 of diamonds where a joker holds the 7 spot in ANOTHER player's 4-5-6-(joker)", c["7D"], theirs_wild_top, None),
        ("3 of diamonds below ANOTHER player's 4-5-6-(joker) diamonds", c["3D"], theirs_wild_top, "low"),
        ("3 of diamonds where a deuce holds the 3 spot in ANOTHER player's (deuce)-4-5-6", c["3D"], theirs_wild_low, None),
        ("7 of diamonds above ANOTHER player's (deuce)-4-5-6 diamonds", c["7D"], theirs_wild_low, "high"),
        ("joker onto the end of ANOTHER player's run (no wilds after laying down, assumption D)", c["Joker"], theirs, None),
    ]
    for label, card, meld, exp in checks:
        allowed = _may_play_on(meld, 0, rules)
        where, why = check_play_off(card, meld, rules) if allowed else (None, "this rule does not allow playing on that meld")
        s = "ok" if where == exp else "MISMATCH"; fails += s != "ok"
        out.append(f"table [{s}] {label}: {where or 'refused'} ({why})")
    # Ace low on someone else's run: A below 2-3-4-5 clubs is fine, but a
    # king can't wrap around under an A-2-3-4 run.
    d = {str(x): x for x in parse_cards("AC 3C 4C 5C 6C KC")}
    lowrun = Meld("run", [c["2C"], d["3C"], d["4C"], d["5C"]], suit="C", low=2, high=5, owner=1)
    for label, card, exp in [("ace of clubs below ANOTHER player's (deuce as 2)-3-4-5 clubs", d["AC"], "low"),
                             ("6 of clubs above the same run", d["6C"], "high")]:
        where, why = check_play_off(card, lowrun, rules)
        s = "ok" if where == exp else "MISMATCH"; fails += s != "ok"
        out.append(f"table [{s}] {label}: {where or 'refused'} ({why})")
    lowrun.cards.insert(0, d["AC"]); lowrun.low = 1
    where, why = check_play_off(d["KC"], lowrun, rules)
    s = "ok" if where is None else "MISMATCH"; fails += s != "ok"
    out.append(f"table [{s}] king of clubs below A-(deuce)-3-4-5 clubs (wrap-around): {where or 'refused'} ({why})")
    # A short game with the normal rules: in all-run round 3 (two runs, no
    # sets), players put cards on their own runs and on other players' runs.
    results, _ = play_game(4, 1, Rules(), rounds=[3])
    r3 = results[0]
    s = "ok" if r3["plays"]["own"] > 0 and r3["plays"]["other_run"] > 0 and not r3["stalled"] else "MISMATCH"
    fails += s != "ok"
    out.append(f"table [{s}] practice hand, round 3, normal rules: {r3['plays']['own']} cards played on the player's own runs, "
               f"{r3['plays']['other_run']} on other players' runs, hand {'stalled' if r3['stalled'] else 'finished'} "
               f"(every table check inside the game passed)")
    return fails


def scoring_cases(out):
    fails = 0
    cases = [("Joker 2H AS KD 7C", 50 + 25 + 15 + 10 + 5),
             ("QH JS 10D 3C", 10 + 10 + 5 + 5),
             ("Joker Joker", 100), ("AH AC 2S", 15 + 15 + 25), ("", 0)]
    for text, exp in cases:
        got = hand_points(parse_cards(text))
        st = "ok" if got == exp else "MISMATCH"; fails += st != "ok"
        out.append(f"score [{st}] left in hand: {text or '(nothing)'} = {got} (expected {exp})")
    for text, exp in [("Joker KD 5C", 25 + 10 + 5), ("Joker 2H AS KD 7C", 25 + 2 + 15 + 10 + 7)]:
        got = hand_points(parse_cards(text), "online_guide")
        house = hand_points(parse_cards(text))
        st = "ok" if got == exp else "MISMATCH"; fails += st != "ok"
        out.append(f"score [{st}] online guide's scoring, for comparison only: {text} = {got} "
                   f"(expected {exp}); your house scoring gives {house}")
    deck = make_deck(2)
    st = "ok" if len(deck) == 108 and sum(c.rank == 0 for c in deck) == 4 and sum(c.rank == 2 for c in deck) == 8 else "MISMATCH"
    fails += st != "ok"
    out.append(f"deck [{st}] two decks: {len(deck)} cards, {sum(c.rank == 0 for c in deck)} jokers, {sum(c.rank == 2 for c in deck)} deuces")
    return fails


def fuzz(out, per_round=150, seed=7, rounds=range(1, 17), budget_s=25, rules=Rules()):
    """Random hands (dealt size + 1 drawn card) from two shuffled decks:
    finder vs brute force.  Brute force is slow on big rounds, so each round
    gets a time budget and the number actually compared is reported."""
    rng = random.Random(seed)
    fails = 0
    for r in rounds:
        req, dealt = ROUNDS[r]
        start, n, yes = time.time(), 0, 0
        while n < per_round and time.time() - start < budget_s:
            deck = make_deck(2); rng.shuffle(deck)
            hand = deck[:dealt + 1]
            res = find_laydown(hand, req, rules)
            b = brute_force_possible(hand, req, rules)
            if (res is not None) != b:
                fails += 1
                out.append(f"fuzz MISMATCH round {r}: {' '.join(map(str, hand))}")
            if res is not None:
                yes += 1
                ok, why = validate_laydown(hand, req, [m.cards for m in res[0]], rules)
                if not ok:
                    fails += 1
                    out.append(f"fuzz VALIDATOR round {r}: {why}")
            n += 1
        out.append(f"fuzz round {r:>2} ({describe_goal(req)}): {n} random {dealt + 1}-card hands, "
                   f"{yes} could lay down, finder and brute force agreed on all {n}")
    return fails


if __name__ == "__main__":
    out = []
    f = run_cases(out)
    f += explicit_validator_cases(out)
    f += long_run_cases(out)
    f += discard_rule_cases(out)
    f += play_off_cases(out)
    f += table_play_cases(out)
    f += scoring_cases(out)
    if "--fuzz" in sys.argv:
        f += fuzz(out)
    print("\n".join(out))
    print(f"\nTOTAL MISMATCHES: {f}")
