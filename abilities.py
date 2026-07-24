"""
Module 9: Abilities
---------------------
Gives cards actual rules text: "when you play this, draw a card",
"whenever this quests, gain 1 lore", and so on.

HOW IT WORKS
An ability is declared as data on the card, not as code:

    "abilities": [
        {"trigger": "on_play",  "effect": "draw",      "amount": 1},
        {"trigger": "on_quest", "effect": "gain_lore", "amount": 1}
    ]

At game start, `register_card_abilities()` walks every card and
subscribes its abilities to the Event Bus. When the Rules Engine
publishes "on_quest", every questing ability fires. This is what the
Event Bus was built for - previously it fired events that nothing
listened to; now it carries the whole ability system.

THE HONEST LIMIT - PLEASE READ
LorcanaJSON gives ability text as ENGLISH PROSE ("Whenever this
character quests, you may draw a card"), not as structured data. There
is no machine-readable encoding of what a card actually does. So:

  * Cards only get abilities if someone hand-writes the declaration
    above, or if the text matches one of the simple patterns in
    `parse_ability_text()` below.
  * When you switch on the live database, the vast majority of real
    cards will have NO abilities in this simulator, because their text
    is unique prose that nothing here can interpret.
  * This is a framework plus a starter library, not a card-text
    interpreter. Building the latter is a much larger project.

Everything below is deliberately small and readable so you can add new
effects yourself: write a function, add it to EFFECTS, done.
"""

import re

# ---------------------------------------------------------------- triggers
# The moments an ability can hook into. The Rules Engine publishes these.
ON_PLAY = "on_play"                 # this card was just played
ON_QUEST = "on_quest"               # this character just quested
ON_BANISH = "on_banish"             # this card was just banished
ON_CHALLENGE = "on_challenge"       # this character challenged
ON_SING = "on_sing"                 # this character sang a song
START_OF_TURN = "start_of_turn"     # controller's turn began

ALL_TRIGGERS = [ON_PLAY, ON_QUEST, ON_BANISH, ON_CHALLENGE, ON_SING, START_OF_TURN]


# ----------------------------------------------------------------- effects
# Each effect is a small function with the same signature. `source` is the
# CardInstance whose ability fired; `controller` and `opponent` are
# PlayerStates; `amount` is the ability's numeric parameter.

def effect_draw(source, controller, opponent, amount=1, **_):
    """Draw `amount` cards."""
    controller.draw(amount)


def effect_gain_lore(source, controller, opponent, amount=1, **_):
    """Gain `amount` lore."""
    controller.lore += amount


def effect_lose_lore(source, controller, opponent, amount=1, **_):
    """Opponent loses `amount` lore (never below zero)."""
    opponent.lore = max(0, opponent.lore - amount)


def effect_damage(source, controller, opponent, amount=1, **_):
    """Deal `amount` damage to the opponent's biggest threat (highest lore,
    then highest strength). Banishes it if that's lethal."""
    targets = [c for c in opponent.in_play if c.type == "character"]
    if not targets:
        return
    target = max(targets, key=lambda c: (c.lore, c.strength))
    target.damage += amount
    if target.damage >= target.willpower:
        opponent.in_play.remove(target)
        opponent.discard.append(target)


def effect_heal(source, controller, opponent, amount=1, **_):
    """Remove `amount` damage from your most damaged character."""
    damaged = [c for c in controller.in_play if c.damage > 0]
    if not damaged:
        return
    target = max(damaged, key=lambda c: c.damage)
    target.damage = max(0, target.damage - amount)


def effect_ready(source, controller, opponent, amount=1, **_):
    """Ready (untap) `amount` of your exerted characters."""
    exerted = [c for c in controller.in_play
               if c.type == "character" and c.exerted]
    for card in exerted[:amount]:
        card.exerted = False


def effect_ramp(source, controller, opponent, amount=1, **_):
    """Put the top `amount` cards of your deck into your inkwell, ready.
    (Models Sapphire-style ink ramp.)"""
    for _i in range(amount):
        if not controller.deck:
            return
        card = controller.deck.pop()
        card.exerted = False
        controller.inkwell.append(card)


def effect_buff_strength(source, controller, opponent, amount=1, **_):
    """Permanently add `amount` strength to the source character.
    (Simplification: real Lorcana buffs are usually 'this turn'.)"""
    source.strength_bonus = getattr(source, "strength_bonus", 0) + amount


EFFECTS = {
    "draw": effect_draw,
    "gain_lore": effect_gain_lore,
    "lose_lore": effect_lose_lore,
    "damage": effect_damage,
    "heal": effect_heal,
    "ready": effect_ready,
    "ramp": effect_ramp,
    "buff_strength": effect_buff_strength,
}


# --------------------------------------------------------------- the class

class Ability:
    """One declared ability: a trigger, an effect, and an amount."""

    def __init__(self, trigger: str, effect: str, amount: int = 1, name: str = ""):
        if trigger not in ALL_TRIGGERS:
            raise ValueError(f"Unknown trigger '{trigger}'. Valid: {ALL_TRIGGERS}")
        if effect not in EFFECTS:
            raise ValueError(f"Unknown effect '{effect}'. Valid: {sorted(EFFECTS)}")
        self.trigger = trigger
        self.effect = effect
        self.amount = amount
        self.name = name or f"{trigger}:{effect}"

    def fire(self, source, controller, opponent):
        EFFECTS[self.effect](source, controller, opponent, amount=self.amount)

    def __repr__(self):
        return f"<Ability {self.name} x{self.amount}>"


def abilities_for_card(info: dict) -> list:
    """Builds Ability objects from a card's declared 'abilities' data.
    Cards with no declaration get an empty list (most real cards)."""
    result = []
    for decl in info.get("abilities", []) or []:
        try:
            result.append(Ability(
                trigger=decl["trigger"],
                effect=decl["effect"],
                amount=decl.get("amount", 1),
                name=decl.get("name", ""),
            ))
        except (KeyError, ValueError):
            # A malformed or unsupported declaration is skipped rather than
            # crashing a 10,000-game simulation.
            continue
    return result


# ------------------------------------------------------- optional text hints
# A few very common phrasings can be recognised automatically. This is a
# convenience, NOT a real parser - it handles a handful of shapes and
# ignores everything else.
_TEXT_PATTERNS = [
    (re.compile(r"when you play this.*?draw (\w+) card", re.I), ON_PLAY, "draw"),
    (re.compile(r"whenever this character quests.*?draw (\w+) card", re.I), ON_QUEST, "draw"),
    (re.compile(r"whenever this character quests.*?gain (\w+) lore", re.I), ON_QUEST, "gain_lore"),
    (re.compile(r"when you play this.*?gain (\w+) lore", re.I), ON_PLAY, "gain_lore"),
]

_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4}


def parse_ability_text(text: str) -> list:
    """
    Best-effort recognition of a few common ability phrasings, returning
    ability declarations. Deliberately conservative: if it isn't one of
    the handful of patterns above, it returns nothing rather than
    guessing wrong. Most real card text will return [].
    """
    found = []
    for pattern, trigger, effect in _TEXT_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        raw = match.group(1).lower()
        amount = _NUMBER_WORDS.get(raw, None)
        if amount is None:
            try:
                amount = int(raw)
            except ValueError:
                continue
        found.append({"trigger": trigger, "effect": effect, "amount": amount})
    return found


# ------------------------------------------------------------- registration

def register_card_abilities(bus, card_instance, controller, opponent):
    """
    Subscribes one card's abilities to the Event Bus.

    Two different matching rules, because two different kinds of event:

      * Card-targeted triggers (ON_PLAY, ON_QUEST, ON_CHALLENGE, ON_SING,
        ON_BANISH) carry the card they happened to. The handler fires only
        if that card is THIS card, so a "draw on quest" ability doesn't
        trigger when some other character quests.

      * START_OF_TURN carries no card - it's about the player. So the
        handler matches on controller instead, and additionally requires
        the card to actually be in play. Without that second check, an
        item still sitting in your deck would trigger every turn.
    """
    for ability in getattr(card_instance, "abilities", []):

        if ability.trigger == START_OF_TURN:
            def make_start_handler(ab_, owner_card):
                def handler(controller=None, **_):
                    if controller is not None and controller is not ctrl:
                        return
                    if owner_card not in ctrl.in_play:
                        return          # only works while on the board
                    ab_.fire(owner_card, ctrl, opponent)
                return handler

            ctrl = controller
            bus.subscribe(START_OF_TURN, make_start_handler(ability, card_instance))

        else:
            def make_handler(ab_, owner_card):
                def handler(card=None, **_):
                    if card is not owner_card:
                        return
                    ab_.fire(owner_card, controller, opponent)
                return handler

            bus.subscribe(ability.trigger, make_handler(ability, card_instance))


def register_start_of_turn_abilities(bus, player, opponent):
    """
    Deprecated. START_OF_TURN abilities are now handled inside
    register_card_abilities() above, which correctly matches on
    controller and checks the card is in play. Kept as a no-op so older
    code that called it doesn't break.
    """
    return
