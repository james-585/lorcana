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
        card = move.card

        if card.type == "location":
            # Locations generate passive lore every turn - very strong
            # over a long game, weak if the game ends fast.
            base = 14 + card.lore * 8
            return base + (6 if persona == CONTROL else -2)

        if card.type == "item":
            base = 12 + card.cost
            return base + (4 if persona == CONTROL else 0)

        if card.type == "action":
            # Actions are one-shot; value them by what they cost.
            return 10 + card.cost * 2

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

    if kind == "shift":
        # Shift is efficient: you get a bigger body for less ink, and it
        # keeps the base character's readiness. Usually strong.
        base = 25 + move.card.cost - move.card.shift_cost
        if persona == AGGRO:
            base += 5      # keeps tempo without losing a turn
        else:
            base += move.card.willpower
        return base

    if kind == "sing":
        # Singing gets exactly the same effect as playing the song, but
        # costs no ink - you exert a character instead. So singing should
        # always beat hard-casting the same song; the only question is
        # whether the singer had something better to do.
        song, singer = move.card, move.target
        effect_value = 10 + song.cost * 2      # same as the "play" score
        ink_saved = song.cost * 2.5            # not spending ink is real
        opportunity = singer.lore * 3          # the quest we're giving up
        base = effect_value + ink_saved - opportunity
        if persona == AGGRO:
            base -= 4      # aggro would still usually rather quest
        else:
            base += 4      # control values the effect over the lore
        return base

    if kind == "move":
        # Moving to a location is only worth it if the location earns
        # lore; otherwise it's a waste of ink in this simplified model.
        loc = move.target
        return 3 + loc.lore * 4 - loc.move_cost * 2

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
