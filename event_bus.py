"""
Module 4: Event Bus
---------------------
Lorcana keywords like Rush, Bodyguard, Ward, and Reckless don't change the
*normal* flow of a turn - they each break ONE specific rule. Rather than
littering the Rules Engine with "if card.has_keyword(...)" checks scattered
everywhere, we use an event bus: the Rules Engine announces things that are
happening ("a character just entered play", "a challenge is being declared")
and any keyword that cares about that moment reacts to it.

This keeps rules_engine.py focused on the *normal* rules, and keeps each
keyword's special-case logic in one place, named after the keyword.
"""

from collections import defaultdict


class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, event_name: str, handler):
        """Register a function to run whenever `event_name` is published."""
        self._subscribers[event_name].append(handler)

    def publish(self, event_name: str, **kwargs):
        """Announce that something happened. Every subscribed handler for
        this event name gets called, in the order they subscribed."""
        for handler in self._subscribers[event_name]:
            handler(**kwargs)


# --- Keyword handlers ------------------------------------------------
# Each of these gets wired up to the bus in rules_engine.py. They're kept
# here so all the "rule-breaking" logic lives in one readable place.

def handle_bodyguard_entry(card=None, controller=None, **_):
    """Bodyguard doesn't need to DO anything when it enters play - it's a
    passive restriction checked at challenge-declaration time (see
    rules_engine.get_valid_challenge_targets). This handler exists mostly
    to document that Bodyguard is event-driven at the 'declare challenge'
    moment, not the 'enters play' moment."""
    return


def handle_reckless_entry(card=None, controller=None, **_):
    """Reckless characters can't quest, ever. Like Bodyguard, this is a
    passive restriction enforced wherever we generate legal moves (see
    rules_engine.get_legal_moves), rather than something that 'fires'."""
    return


def register_default_keyword_handlers(bus: EventBus):
    """Wire up all the keyword handlers this simulator knows about.
    Call this once per game when you build the EventBus."""
    bus.subscribe("character_entered_play", handle_bodyguard_entry)
    bus.subscribe("character_entered_play", handle_reckless_entry)
