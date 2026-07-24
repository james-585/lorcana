"""
Module 3: Rules Engine
------------------------
Implements the core actions of a turn: inking a card, playing a card,
questing, and challenging. This is a SIMPLIFIED ruleset (see README for
the full list of simplifications) - enough to produce meaningful, decision-
driven games without implementing every card's unique text.

Every action here also publishes events to the EventBus, so keyword logic
in event_bus.py can react without this file needing to know keyword
details itself.
"""

from game_state import PlayerState

LORE_TO_WIN = 20


class Move:
    """A single legal action a player could take on their turn."""

    def __init__(self, kind, card=None, target=None):
        self.kind = kind      # "ink", "play", "quest", "challenge", "pass"
        self.card = card      # the CardInstance being acted with
        self.target = target  # for challenges: the CardInstance being hit

    def __repr__(self):
        if self.kind in ("ink", "play", "quest"):
            return f"{self.kind}({self.card.name})"
        if self.kind == "challenge":
            return f"challenge({self.card.name} -> {self.target.name})"
        return self.kind


def get_valid_challenge_targets(attacker, defender_player: PlayerState):
    """
    A character can only challenge an EXERTED enemy character - unless the
    attacker has Evasive, in which case it can only challenge other Evasive
    characters (mirroring the real rule that only Evasive can block/fight
    Evasive). Bodyguard characters that are in play and NOT exerted must
    be challenged first if any are available, protecting the rest of the
    board (this is the real Bodyguard rule).
    """
    candidates = [c for c in defender_player.characters_in_play() if c.exerted]

    if attacker.has_keyword("Evasive"):
        candidates = [c for c in candidates if c.has_keyword("Evasive")]

    ready_bodyguards = [
        c for c in defender_player.characters_in_play()
        if c.has_keyword("Bodyguard") and not c.exerted
    ]
    if ready_bodyguards:
        # Ready Bodyguards must be challenged before anything else, and
        # they can be challenged even while ready (that's the exception
        # Bodyguard grants).
        return ready_bodyguards

    return candidates


def get_legal_moves(player: PlayerState, opponent: PlayerState) -> list:
    """Builds the full list of legal Moves available right now."""
    moves = []

    if not player.inked_this_turn:
        for card in player.hand:
            if card.inkable:
                moves.append(Move("ink", card=card))

    for card in player.hand:
        if card.cost <= player.available_ink():
            moves.append(Move("play", card=card))

    for card in player.characters_in_play():
        if card.can_act() and not card.has_keyword("Reckless"):
            moves.append(Move("quest", card=card))
        if card.can_act():
            targets = get_valid_challenge_targets(card, opponent)
            for target in targets:
                moves.append(Move("challenge", card=card, target=target))

    moves.append(Move("pass"))
    return moves


def apply_move(move: Move, player: PlayerState, opponent: PlayerState, bus):
    """Mutates game state to reflect the chosen move. Also publishes
    events so keyword handlers on the bus can react."""

    if move.kind == "ink":
        player.hand.remove(move.card)
        player.inkwell.append(move.card)
        player.inked_this_turn = True
        bus.publish("card_inked", card=move.card, controller=player)

    elif move.kind == "play":
        cost = move.card.cost
        to_pay = cost
        for ink_card in player.inkwell:
            if to_pay == 0:
                break
            if not ink_card.exerted:
                ink_card.exerted = True
                to_pay -= 1
        player.hand.remove(move.card)
        player.in_play.append(move.card)
        bus.publish("character_entered_play", card=move.card, controller=player)

    elif move.kind == "quest":
        move.card.exerted = True
        player.lore += move.card.lore
        bus.publish("quested", card=move.card, controller=player)

    elif move.kind == "challenge":
        attacker, defender = move.card, move.target
        attacker.exerted = True
        defender.damage += attacker.strength
        attacker.damage += defender.strength
        bus.publish("challenge_resolved", attacker=attacker, defender=defender)

        if defender.damage >= defender.willpower:
            opponent.in_play.remove(defender)
            opponent.discard.append(defender)
            bus.publish("character_banished", card=defender, controller=opponent)
        if attacker.damage >= attacker.willpower:
            player.in_play.remove(attacker)
            player.discard.append(attacker)
            bus.publish("character_banished", card=attacker, controller=player)

    elif move.kind == "pass":
        pass


def check_winner(p1: PlayerState, p2: PlayerState):
    """Returns the winning player's name, or None if the game continues."""
    if p1.lore >= LORE_TO_WIN:
        return p1.name
    if p2.lore >= LORE_TO_WIN:
        return p2.name
    return None
