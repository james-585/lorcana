"""
Module 5: Heuristic AI
------------------------
A stateless bot: given the current game state and a list of legal moves
(from rules_engine.get_legal_moves), it scores each move and picks the
highest-scoring one. "Stateless" means it doesn't remember anything
between turns - every decision is made fresh from what's on the board
right now, based on the deck's Persona.

Two personas:
  AGGRO   - wants to end the game fast. Values lore gain and cheap
            board development very highly, avoids risky trades.
  CONTROL - wants to win the long game. Values removing opposing
            threats and developing high-willpower bodies, is patient
            about lore.
"""

AGGRO = "Aggro"
CONTROL = "Control"


def score_move(move, player, opponent, persona: str) -> float:
    kind = move.kind

    if kind == "pass":
        # Passing is always the worst option unless nothing else scores
        # higher - it's the fallback, never the goal.
        return -1000

    if kind == "ink":
        # Slightly prefer keeping ink flowing, but never above playing
        # or questing with something already on board.
        return 5

    if kind == "play":
        base = 10 + move.card.cost  # bigger plays are usually stronger
        if persona == AGGRO:
            # Aggro loves cheap, immediately-relevant bodies.
            base += (6 - move.card.cost) * 2
            if move.card.has_keyword("Rush") or move.card.has_keyword("Evasive"):
                base += 4
        else:  # CONTROL
            # Control loves tough bodies that survive challenges.
            base += move.card.willpower * 1.5
            if move.card.has_keyword("Bodyguard") or move.card.has_keyword("Ward"):
                base += 4
        return base

    if kind == "quest":
        base = 15 + move.card.lore * 5
        if persona == AGGRO:
            base += 8  # Aggro pushes lore relentlessly
        else:
            # Control only quests freely if it's safely ahead on board,
            # otherwise it would rather hold characters back to challenge.
            if len(player.characters_in_play()) <= len(opponent.characters_in_play()):
                base -= 6
        return base

    if kind == "challenge":
        attacker, defender = move.card, move.target
        trade_value = defender.strength - attacker.willpower  # how risky
        kills_defender = (defender.damage + attacker.strength) >= defender.willpower
        dies_to_defender = (attacker.damage + defender.strength) >= attacker.willpower

        base = 5
        if kills_defender:
            base += 20
        if dies_to_defender and not kills_defender:
            base -= 25  # a bad trade: we lose our character for nothing
        elif dies_to_defender and kills_defender:
            base -= 5   # an even trade, still fine but not free

        if persona == AGGRO:
            # Aggro avoids challenges that tie up a character which could
            # have quested instead, unless it's a clean, free kill.
            if not kills_defender:
                base -= 10
        else:  # CONTROL
            # Control actively wants to clear the opposing board.
            base += 8
            base -= trade_value  # prefers picking off big threats cheaply

        return base

    return 0


def choose_move(moves, player, opponent, persona: str):
    """Scores every legal move and returns the single best one."""
    best_move = None
    best_score = float("-inf")
    for move in moves:
        s = score_move(move, player, opponent, persona)
        if s > best_score:
            best_score = s
            best_move = move
    return best_move
