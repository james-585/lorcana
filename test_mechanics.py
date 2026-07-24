"""
Mechanic tests
----------------
Verifies that each newly added mechanic actually changes the game state
correctly - not merely that it runs without crashing.

Run with:  python3 test_mechanics.py
"""

import random

import ingestion
from game_state import PlayerState
from event_bus import build_bus_for_game
from rules_engine import get_legal_moves, apply_move, Move
import abilities as ab

DB = ingestion.load_local_card_database()
PASSED, FAILED = [], []


def check(label, condition, detail=""):
    (PASSED if condition else FAILED).append(label)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -- {detail}" if detail and not condition else ""))


def fresh(deck_names, counts=6):
    deck = []
    for n in deck_names:
        deck.extend([DB[n]] * counts)
    while len(deck) < 60:
        deck.append(DB[deck_names[0]])
    p = PlayerState("A", deck[:60])
    o = PlayerState("B", deck[:60])
    return p, o


def give_ink(player, amount):
    for _ in range(amount):
        if player.deck:
            card = player.deck.pop()
            card.exerted = False
            player.inkwell.append(card)


def put_in_play(player, name, dry=True):
    card = next(c for c in player.deck if c.name == name)
    player.deck.remove(card)
    player.in_play.append(card)
    card.wet_ink = not dry
    return card


def put_in_hand(player, name):
    card = next(c for c in player.deck if c.name == name)
    player.deck.remove(card)
    player.hand.append(card)
    return card


print("\n=== MULLIGAN ===")
p, o = fresh(["Maui - Half-Shark", "Hades - Infernal Schemer"], 30)
p.draw(7)
before_deck = len(p.deck)
swapped = p.mulligan()
check("expensive hand gets mulliganed", swapped > 0, f"swapped={swapped}")
check("hand still 7 after mulligan", len(p.hand) == 7, f"hand={len(p.hand)}")
check("deck size preserved", len(p.deck) == before_deck, f"deck={len(p.deck)}")
check("mulligan only once", p.mulligan() == 0)

p2, _ = fresh(["Belle - Strange but Special"], 60)
p2.draw(7)
check("cheap hand is kept", p2.mulligan() == 0)


print("\n=== ON-PLAY ABILITY (draw) ===")
p, o = fresh(["Genie - On the Job", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
give_ink(p, 5)
genie = put_in_hand(p, "Genie - On the Job")
hand_before = len(p.hand)
apply_move(Move("play", card=genie), p, o, bus)
# played 1 card (-1), ability drew 1 (+1) => net same size
check("on-play draw fired", len(p.hand) == hand_before,
      f"before={hand_before} after={len(p.hand)}")


print("\n=== ON-QUEST ABILITY (draw) ===")
p, o = fresh(["Stitch - Rock Star", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
stitch = put_in_play(p, "Stitch - Rock Star")
hand_before = len(p.hand)
lore_before = p.lore
apply_move(Move("quest", card=stitch), p, o, bus)
check("quest gained lore", p.lore == lore_before + stitch.lore)
check("on-quest draw fired", len(p.hand) == hand_before + 1,
      f"before={hand_before} after={len(p.hand)}")


print("\n=== ON-PLAY DAMAGE ABILITY ===")
p, o = fresh(["Elsa - Snow Queen", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
give_ink(p, 8)
victim = put_in_play(o, "Belle - Strange but Special")
elsa = put_in_hand(p, "Elsa - Snow Queen")
apply_move(Move("play", card=elsa), p, o, bus)
banished = victim not in o.in_play
check("on-play damage hit opponent", victim.damage > 0 or banished,
      f"damage={victim.damage} banished={banished}")


print("\n=== SHIFT ===")
p, o = fresh(["Stitch - Rock Star", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
give_ink(p, 8)
base = put_in_play(p, "Stitch - Rock Star")
base.damage = 2
shifter = put_in_hand(p, "Stitch - Rock Star")
check("shift cost is cheaper than play cost",
      shifter.shift_cost < shifter.cost, f"shift={shifter.shift_cost} cost={shifter.cost}")
ink_before = p.available_ink()
apply_move(Move("shift", card=shifter, target=base), p, o, bus)
check("shifted card is in play", shifter in p.in_play)
check("base card left play", base not in p.in_play)
check("damage carried over", shifter.damage == 2, f"damage={shifter.damage}")
check("paid shift cost not full cost",
      p.available_ink() == ink_before - shifter.shift_cost)


print("\n=== SING ===")
p, o = fresh(["Cinderella - Ballroom Sensation", "Friends on the Other Side"])
bus = build_bus_for_game(p, o)
singer = put_in_play(p, "Cinderella - Ballroom Sensation")
song = put_in_hand(p, "Friends on the Other Side")
check("Singer value exceeds printed cost",
      singer.singer_value > singer.cost, f"singer={singer.singer_value} cost={singer.cost}")
check("singer can sing this song", singer.can_sing(song))
hand_before = len(p.hand)
ink_before = p.available_ink()
apply_move(Move("sing", card=song, target=singer), p, o, bus)
check("singer became exerted", singer.exerted)
check("no ink was spent singing", p.available_ink() == ink_before)
check("song went to discard", song in p.discard)
# song draws 2, and we removed the song from hand => net +1
check("song effect resolved (drew 2)", len(p.hand) == hand_before + 1,
      f"before={hand_before} after={len(p.hand)}")

# A small character must not be able to sing a big song
p2, o2 = fresh(["Belle - Strange but Special", "Let It Go"])
small = put_in_play(p2, "Belle - Strange but Special")
big_song = put_in_hand(p2, "Let It Go")
check("small character cannot sing big song", not small.can_sing(big_song),
      f"cost={small.cost} song={big_song.cost}")


print("\n=== SUPPORT ===")
p, o = fresh(["Lumiere - Fluid Performer", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
supporter = put_in_play(p, "Lumiere - Fluid Performer")
ally = put_in_play(p, "Belle - Strange but Special")
check("supporter has Support keyword", supporter.has_keyword("Support"))
ally_str_before = ally.strength
apply_move(Move("quest", card=supporter), p, o, bus)
check("Support buffed an ally", ally.strength > ally_str_before,
      f"before={ally_str_before} after={ally.strength}")
p.ready_all()
check("Support buff expires next turn", ally.strength == ally_str_before,
      f"after ready={ally.strength}")


print("\n=== LOCATIONS ===")
p, o = fresh(["Motunui - Island Paradise", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
give_ink(p, 8)
loc = put_in_hand(p, "Motunui - Island Paradise")
apply_move(Move("play", card=loc), p, o, bus)
check("location entered play", loc in p.in_play)
check("location has no summoning sickness", not loc.wet_ink)
lore_before = p.lore
gained = p.collect_location_lore()
check("location generated lore at start of turn", gained == loc.lore and p.lore > lore_before,
      f"gained={gained}")
# Locations can't quest
moves = get_legal_moves(p, o)
check("location cannot quest", not any(m.kind == "quest" and m.card is loc for m in moves))
# Locations are challengeable even though never exerted
attacker = put_in_play(o, "Belle - Strange but Special")
from rules_engine import get_valid_challenge_targets
targets = get_valid_challenge_targets(attacker, p)
check("location is challengeable while unexerted", loc in targets)


print("\n=== ITEMS ===")
p, o = fresh(["Sorcerer's Hat", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
give_ink(p, 6)
item = put_in_hand(p, "Sorcerer's Hat")
apply_move(Move("play", card=item), p, o, bus)
check("item entered play", item in p.in_play)
moves = get_legal_moves(p, o)
check("item cannot quest", not any(m.kind == "quest" and m.card is item for m in moves))
hand_before = len(p.hand)
bus.publish(ab.START_OF_TURN, controller=p)
check("item start-of-turn ability fired", len(p.hand) == hand_before + 1,
      f"before={hand_before} after={len(p.hand)}")


print("\n=== ACTIONS ===")
p, o = fresh(["Smash", "Belle - Strange but Special"])
bus = build_bus_for_game(p, o)
give_ink(p, 6)
victim = put_in_play(o, "Belle - Strange but Special")
action = put_in_hand(p, "Smash")
apply_move(Move("play", card=action), p, o, bus)
check("action went straight to discard", action in p.discard)
check("action did not stay in play", action not in p.in_play)
check("action effect resolved", victim.damage > 0 or victim not in o.in_play,
      f"damage={victim.damage}")


print("\n" + "=" * 50)
print(f"PASSED: {len(PASSED)}   FAILED: {len(FAILED)}")
if FAILED:
    print("\nFailures:")
    for f in FAILED:
        print("  -", f)
    raise SystemExit(1)
print("All mechanic tests passed.")
