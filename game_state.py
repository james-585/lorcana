"""
Module 2: Game State
---------------------
Defines the physical "board" of a Lorcana game: the zones (Deck, Hand,
Inkwell, In-Play, Discard) for each player, and a CardInstance wrapper
that tracks the live status of one physical card (e.g. is it exerted,
does it have summoning sickness) separately from its static stats.
"""

import random


class CardInstance:
    """
    One physical copy of a card sitting somewhere in the game.
    `info` holds the static stats (cost, strength, etc.) that came from
    ingestion.py. Everything else here is state that changes during play.
    """

    def __init__(self, info: dict):
        self.info = info
        self.exerted = False          # True = tapped / already used this turn
        self.wet_ink = True           # True = played this turn, can't act yet
        self.damage = 0                # damage marked on a character in play

    @property
    def name(self):
        return self.info["name"]

    @property
    def cost(self):
        return self.info["cost"]

    @property
    def type(self):
        return self.info["type"]

    @property
    def strength(self):
        return self.info["strength"]

    @property
    def willpower(self):
        return self.info["willpower"]

    @property
    def lore(self):
        return self.info["lore"]

    @property
    def keywords(self):
        return self.info["keywords"]

    @property
    def inkable(self):
        return self.info["inkable"]

    def has_keyword(self, keyword: str) -> bool:
        return keyword in self.keywords

    def can_act(self) -> bool:
        """A character can quest/challenge if it's not exerted, and either
        it's been in play since the start of this turn OR it has Rush."""
        if self.exerted:
            return False
        if self.wet_ink and not self.has_keyword("Rush"):
            return False
        return True

    def __repr__(self):
        return f"<{self.name} dmg={self.damage} exerted={self.exerted}>"


class PlayerState:
    """
    Holds the five zones for one player, plus their lore total.
    """

    def __init__(self, name: str, deck_cards: list):
        self.name = name
        self.lore = 0

        # Shuffle the deck once at the start of the game.
        self.deck = [CardInstance(info) for info in deck_cards]
        random.shuffle(self.deck)

        self.hand = []
        self.inkwell = []
        self.in_play = []
        self.discard = []

        self.inked_this_turn = False

    def draw(self, n: int = 1):
        """Move n cards from the top of the deck into hand.
        Returns False if the deck ran out (a loss condition)."""
        for _ in range(n):
            if not self.deck:
                return False
            self.hand.append(self.deck.pop())
        return True

    def available_ink(self) -> int:
        """How much ink is ready to spend right now."""
        return sum(1 for c in self.inkwell if not c.exerted)

    def ready_all(self):
        """Start-of-turn: untap everything and clear 'just played' status."""
        for zone in (self.inkwell, self.in_play):
            for card in zone:
                card.exerted = False
        for card in self.in_play:
            card.wet_ink = False

    def characters_in_play(self):
        return [c for c in self.in_play if c.type == "character"]

    def __repr__(self):
        return (f"<Player {self.name}: lore={self.lore}, "
                f"hand={len(self.hand)}, deck={len(self.deck)}, "
                f"board={len(self.in_play)}>")
