"""
Module 4: Event Bus
---------------------
The trigger system. The Rules Engine announces things that happen
("a card was played", "a character quested"), and anything that cares
reacts.

WHAT CHANGED: this module used to be architecture without cargo - it
fired events, but its only two handlers were no-ops that did nothing.
Now it carries the whole ability system from abilities.py. When a card
with "when you play this, draw a card" enters play, that ability is
subscribed here, and the ON_PLAY event actually makes the draw happen.

Keywords are handled in two different places, deliberately:

  * Restriction keywords (Rush, Evasive, Bodyguard, Reckless, Ward)
    are not events - they change what moves are LEGAL, so they live in
    rules_engine.get_legal_moves / get_valid_challenge_targets where
    legality is decided.

  * Triggered keywords (Support, and every card-text ability) DO fire at
    a moment in time, so they flow through this bus.
"""

from collections import defaultdict

import abilities as ab


class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, event_name: str, handler):
        """Register a function to run when `event_name` is published."""
        self._subscribers[event_name].append(handler)

    def publish(self, event_name: str, **kwargs):
        """Announce something happened; run every subscribed handler."""
        for handler in list(self._subscribers[event_name]):
            handler(**kwargs)

    def clear(self):
        self._subscribers.clear()


def build_bus_for_game(player_a, player_b):
    """
    Creates an EventBus and wires up every ability on every card in both
    players' decks.

    Abilities are registered for cards in ALL zones (deck, hand, play),
    because a card in the deck will later be played and needs its
    ability live at that moment. Each handler checks the event is about
    its own card, so registering early is harmless.
    """
    bus = EventBus()

    for owner, foe in ((player_a, player_b), (player_b, player_a)):
        for zone in (owner.deck, owner.hand, owner.in_play):
            for card in zone:
                if card.abilities:
                    ab.register_card_abilities(bus, card, owner, foe)
    return bus


# Backwards-compatible alias: earlier versions of this project called
# this function, and monte_carlo.py may still reference it.
def register_default_keyword_handlers(bus):
    """
    Kept so older code doesn't break. Restriction keywords are enforced
    in rules_engine.py rather than here, so there is nothing to register.
    """
    return bus
