"""
Module 3: Rules Engine
------------------------
The legal actions of a turn and what they do. Still a SIMPLIFIED ruleset
(see README), but now covers:

  ink       - put a card in your inkwell (once per turn)
  play      - pay ink to play a character, item, location or action
  shift     - pay Shift cost to play a character on top of a same-named
              character already in play, keeping its damage
  quest     - exert a character to gain its lore
  challenge - exert a character to fight an exerted enemy character, or
              an enemy location (locations can always be challenged)
  sing      - exert a character to play a Song for free, if the
              character's cost (or Singer value) is high enough
  move      - move a character to one of your locations

Every action publishes events to the Event Bus so card abilities
(abilities.py) fire at the right moments.
"""

from game_state import PlayerState
import abilities as ab

LORE_TO_WIN = 20


class Move:
    """A single legal action."""

    def __init__(self, kind, card=None, target=None, extra=None):
        self.kind = kind
        self.card = card
        self.target = target
        self.extra = extra          # e.g. the singer for a "sing" move

    def __repr__(self):
        if self.kind in ("ink", "play", "quest"):
            return f"{self.kind}({self.card.name})"
        if self.kind == "challenge":
            return f"challenge({self.card.name} -> {self.target.name})"
        if self.kind == "shift":
            return f"shift({self.card.name} onto {self.target.name})"
        if self.kind == "sing":
            return f"sing({self.card.name} by {self.target.name})"
        if self.kind == "move":
            return f"move({self.card.name} -> {self.target.name})"
        return self.kind


# ------------------------------------------------------------- targeting

def get_valid_challenge_targets(attacker, defender_player: PlayerState):
    """
    Who can this attacker challenge?

    Rules modelled:
      - characters may only be challenged while EXERTED
      - locations may ALWAYS be challenged (they never exert)
      - Evasive characters can only be challenged by Evasive attackers
      - if the defender has a ready Bodyguard, it must be challenged first
      - Ward doesn't restrict challenges (it only stops targeted effects)
    """
    targets = [c for c in defender_player.characters_in_play() if c.exerted]

    if attacker.has_keyword("Evasive"):
        targets = [c for c in targets if c.has_keyword("Evasive")]
    else:
        targets = [c for c in targets if not c.has_keyword("Evasive")]

    bodyguards = [c for c in defender_player.characters_in_play()
                  if c.has_keyword("Bodyguard") and not c.exerted]
    if bodyguards:
        return bodyguards

    # Locations are challengeable at any time and don't hide behind
    # the exerted requirement, since they never exert.
    targets = targets + defender_player.locations_in_play()
    return targets


def get_legal_moves(player: PlayerState, opponent: PlayerState) -> list:
    """Every legal action available right now."""
    moves = []
    ink = player.available_ink()

    # 1. Inking - once per turn, inkable cards only.
    if not player.inked_this_turn:
        for card in player.hand:
            if card.inkable:
                moves.append(Move("ink", card=card))

    # 2. Playing cards you can afford.
    for card in player.hand:
        if card.cost <= ink:
            moves.append(Move("play", card=card))

        # 2b. Shift: cheaper way to play a character on top of a
        # same-named one already in play.
        shift_cost = card.shift_cost
        if shift_cost is not None and shift_cost <= ink:
            for existing in player.characters_in_play():
                if existing.name == card.name:
                    moves.append(Move("shift", card=card, target=existing))

    # 3. Singing a song for free by exerting a big enough character.
    for card in player.hand:
        if not card.is_song:
            continue
        for singer in player.characters_in_play():
            if singer.can_sing(card):
                moves.append(Move("sing", card=card, target=singer))

    # 4. Questing and challenging.
    for card in player.characters_in_play():
        if not card.can_act():
            continue
        if not card.has_keyword("Reckless"):
            moves.append(Move("quest", card=card))
        for target in get_valid_challenge_targets(card, opponent):
            moves.append(Move("challenge", card=card, target=target))

    # 5. Moving a character to one of your locations.
    for loc in player.locations_in_play():
        for char in player.characters_in_play():
            if char.location is not loc and loc.move_cost <= ink:
                moves.append(Move("move", card=char, target=loc))

    moves.append(Move("pass"))
    return moves


# --------------------------------------------------------------- helpers

def _pay(player: PlayerState, amount: int):
    """Exert `amount` ready ink."""
    remaining = amount
    for ink_card in player.inkwell:
        if remaining <= 0:
            break
        if not ink_card.exerted:
            ink_card.exerted = True
            remaining -= 1


def _banish(card, owner: PlayerState, bus):
    """Move a card from play to discard and fire its banish trigger."""
    if card in owner.in_play:
        owner.in_play.remove(card)
        owner.discard.append(card)
        bus.publish(ab.ON_BANISH, card=card, controller=owner)


def _apply_support(attacker_or_quester, player: PlayerState):
    """
    Support: when this character quests, add its Strength to another of
    your characters' Strength this turn. We give it to the strongest
    other character, which is the usual sensible choice.
    """
    if not attacker_or_quester.has_keyword("Support"):
        return
    others = [c for c in player.characters_in_play()
              if c is not attacker_or_quester]
    if not others:
        return
    best = max(others, key=lambda c: c.strength)
    best.strength_bonus += attacker_or_quester.strength


def _resolve_action(card, player, opponent, bus):
    """Actions and Songs resolve immediately, then go to the discard."""
    bus.publish(ab.ON_PLAY, card=card, controller=player)
    player.discard.append(card)


# ---------------------------------------------------------------- applying

def apply_move(move: Move, player: PlayerState, opponent: PlayerState, bus):
    """Mutates game state for the chosen move and publishes its events."""
    kind = move.kind

    if kind == "ink":
        player.hand.remove(move.card)
        player.inkwell.append(move.card)
        player.inked_this_turn = True

    elif kind == "play":
        card = move.card
        _pay(player, card.cost)
        player.hand.remove(card)

        if card.type == "action":
            _resolve_action(card, player, opponent, bus)
        else:
            player.in_play.append(card)
            # Locations never exert and have no summoning sickness.
            if card.type == "location":
                card.wet_ink = False
            bus.publish(ab.ON_PLAY, card=card, controller=player)

    elif kind == "shift":
        card, base = move.card, move.target
        _pay(player, card.shift_cost)
        player.hand.remove(card)

        # The shifted card inherits the base's damage and readiness, and
        # the base card goes underneath it.
        card.damage = base.damage
        card.exerted = base.exerted
        card.wet_ink = base.wet_ink     # inherits "dryness"
        card.location = base.location
        card.shifted_onto = base

        player.in_play.remove(base)
        player.in_play.append(card)
        bus.publish(ab.ON_PLAY, card=card, controller=player)

    elif kind == "sing":
        song, singer = move.card, move.target
        singer.exerted = True
        player.hand.remove(song)
        bus.publish(ab.ON_SING, card=singer, controller=player)
        _resolve_action(song, player, opponent, bus)

    elif kind == "quest":
        card = move.card
        card.exerted = True
        player.lore += card.lore
        _apply_support(card, player)
        bus.publish(ab.ON_QUEST, card=card, controller=player)

    elif kind == "challenge":
        attacker, defender = move.card, move.target
        attacker.exerted = True
        bus.publish(ab.ON_CHALLENGE, card=attacker, controller=player)

        if defender.type == "location":
            # Locations take damage but deal none back.
            defender.damage += attacker.strength
            if defender.damage >= defender.willpower:
                _banish(defender, opponent, bus)
        else:
            defender.damage += attacker.strength
            attacker.damage += defender.strength
            if defender.damage >= defender.willpower:
                _banish(defender, opponent, bus)
            if attacker.damage >= attacker.willpower:
                _banish(attacker, player, bus)

    elif kind == "move":
        char, loc = move.card, move.target
        _pay(player, loc.move_cost)
        char.location = loc

    elif kind == "pass":
        pass


def check_winner(p1: PlayerState, p2: PlayerState):
    """Winner's name, or None if the game continues."""
    if p1.lore >= LORE_TO_WIN:
        return p1.name
    if p2.lore >= LORE_TO_WIN:
        return p2.name
    return None
