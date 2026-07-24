"""
Module 2: Game State
---------------------
The physical "board": each player's zones (Deck, Hand, Inkwell, In-Play,
Discard) plus a CardInstance wrapper tracking the live status of one
physical card, separate from its static printed stats.

Now supports four card types:
  character - quests, challenges, can be shifted onto, can sing
  item      - stays in play, provides abilities, never quests/challenges
  location  - stays in play, gains lore at start of turn, can be
              challenged but never exerts and never quests
  action    - one-shot effect then straight to discard (Songs are the
              Action subtype that characters can sing)
"""

import random

import abilities as abilities_module


def _keyword_value(keywords, name, default=0):
    """
    Lorcana keywords can carry a number, e.g. 'Shift 5', 'Singer 5',
    'Challenger +2'. LorcanaJSON stores them as those full strings, so
    this pulls the number back out. Returns `default` if absent.
    """
    for kw in keywords or []:
        text = str(kw).strip()
        if text.lower().startswith(name.lower()):
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                return int(digits)
            return default
    return default


def _has_keyword(keywords, name):
    return any(str(kw).strip().lower().startswith(name.lower())
               for kw in (keywords or []))


class CardInstance:
    """One physical copy of a card somewhere in the game."""

    def __init__(self, info: dict):
        self.info = info
        self.exerted = False
        self.wet_ink = True            # played this turn -> can't act yet
        self.damage = 0
        self.strength_bonus = 0        # from Support and buff effects
        self.location = None           # which location this character is at
        self.shifted_onto = None       # the card this was shifted on top of
        self.abilities = abilities_module.abilities_for_card(info)

    # --- static stats, read from the printed card -------------------
    @property
    def name(self):
        return self.info["name"]

    @property
    def cost(self):
        return self.info.get("cost", 0)

    @property
    def type(self):
        return self.info.get("type", "character")

    @property
    def strength(self):
        return self.info.get("strength", 0) + self.strength_bonus

    @property
    def willpower(self):
        return self.info.get("willpower", 0)

    @property
    def lore(self):
        return self.info.get("lore", 0)

    @property
    def keywords(self):
        return self.info.get("keywords", [])

    @property
    def inkable(self):
        return self.info.get("inkable", True)

    @property
    def move_cost(self):
        """Locations cost this much for a character to move there."""
        return self.info.get("move_cost", 1)

    @property
    def is_song(self):
        """Songs are the Action subtype that characters can sing."""
        return bool(self.info.get("song", False))

    # --- keyword helpers --------------------------------------------
    def has_keyword(self, keyword: str) -> bool:
        return _has_keyword(self.keywords, keyword)

    @property
    def shift_cost(self):
        """Shift N: pay N to play this on top of a same-named character.
        Returns None if this card has no Shift."""
        if not self.has_keyword("Shift"):
            return None
        return _keyword_value(self.keywords, "Shift", default=self.cost)

    @property
    def singer_value(self):
        """Singer N: sings songs as though its cost were N. Falls back to
        the card's own cost, which is the normal singing rule."""
        if self.has_keyword("Singer"):
            return _keyword_value(self.keywords, "Singer", default=self.cost)
        return self.cost

    # --- live status -------------------------------------------------
    def can_act(self) -> bool:
        """Can quest / challenge / sing this turn?
        Locations and items never act. Characters need to be ready and
        either dry (in play since start of turn) or have Rush."""
        if self.type != "character":
            return False
        if self.exerted:
            return False
        if self.wet_ink and not self.has_keyword("Rush"):
            return False
        return True

    def can_sing(self, song) -> bool:
        """A character can sing a song if it's ready, dry, and its cost
        (or Singer value) is at least the song's cost."""
        if self.type != "character" or self.exerted:
            return False
        if self.wet_ink and not self.has_keyword("Rush"):
            return False
        return self.singer_value >= song.cost

    def __repr__(self):
        return f"<{self.name} ({self.type}) dmg={self.damage} exerted={self.exerted}>"


class PlayerState:
    """The five zones for one player, plus lore."""

    def __init__(self, name: str, deck_cards: list):
        self.name = name
        self.lore = 0

        self.deck = [CardInstance(info) for info in deck_cards]
        random.shuffle(self.deck)

        self.hand = []
        self.inkwell = []
        self.in_play = []
        self.discard = []

        self.inked_this_turn = False
        self.has_mulliganed = False

    # --- drawing and mulligan ---------------------------------------
    def draw(self, n: int = 1):
        """Move n cards from deck to hand. False if the deck ran out."""
        for _ in range(n):
            if not self.deck:
                return False
            self.hand.append(self.deck.pop())
        return True

    def mulligan(self, keep_predicate=None):
        """
        The real Lorcana mulligan: put any number of your opening hand on
        the bottom of your deck, draw that many replacements, then shuffle.
        Once per game.

        `keep_predicate(card) -> bool` decides which cards to keep. If not
        given, uses `default_mulligan_policy` below.

        Returns the number of cards swapped.
        """
        if self.has_mulliganed:
            return 0
        self.has_mulliganed = True

        if keep_predicate is None:
            keep_predicate = default_mulligan_policy

        keeping = [c for c in self.hand if keep_predicate(c)]
        tossing = [c for c in self.hand if not keep_predicate(c)]
        if not tossing:
            return 0

        self.hand = keeping
        # Bottom of deck: our deck list treats the END as the top (we pop),
        # so the bottom is the front of the list.
        for card in tossing:
            self.deck.insert(0, card)
        self.draw(len(tossing))
        random.shuffle(self.deck)
        return len(tossing)

    # --- turn bookkeeping --------------------------------------------
    def available_ink(self) -> int:
        return sum(1 for c in self.inkwell if not c.exerted)

    def ready_all(self):
        """Start of turn: untap everything, clear summoning sickness.
        Locations never exert, so they're unaffected either way."""
        for card in self.inkwell:
            card.exerted = False
        for card in self.in_play:
            card.exerted = False
            card.wet_ink = False
            card.strength_bonus = 0     # Support buffs last one turn

    def characters_in_play(self):
        return [c for c in self.in_play if c.type == "character"]

    def locations_in_play(self):
        return [c for c in self.in_play if c.type == "location"]

    def items_in_play(self):
        return [c for c in self.in_play if c.type == "item"]

    def collect_location_lore(self):
        """Locations gain their lore value at the start of your turn,
        instead of questing (they can't quest)."""
        gained = 0
        for loc in self.locations_in_play():
            gained += loc.lore
        self.lore += gained
        return gained

    def __repr__(self):
        return (f"<Player {self.name}: lore={self.lore}, hand={len(self.hand)}, "
                f"deck={len(self.deck)}, board={len(self.in_play)}>")


def default_mulligan_policy(card) -> bool:
    """
    Keep a card if it's cheap enough to actually cast early, or if it's
    inkable (so it can at least fuel the inkwell). Tosses expensive,
    uninkable cards, which is roughly how a real player mulligans.
    """
    if card.cost <= 3:
        return True
    if card.inkable and card.cost <= 5:
        return True
    return False
