"""
Module 7: Formats (set legality)
----------------------------------
Decides which cards are legal to play in which tournament format.

Lorcana has two constructed formats:
  CORE     - rotating. Only the current year's block of sets and the
             previous year's block are legal. Four sets rotate out
             once a year.
  INFINITY - eternal. Every card ever printed is legal.

THE ROTATION AS OF THIS FILE'S WRITING (24 July 2026):
The 2026 rotation happened on 24 July 2026, when Set 13 "Attack of the
Vine!" released. Sets 5-8 (Shimmering Skies, Azurite Sea, Archazia's
Island, Reign of Jafar) rotated OUT. Combined with the 2025 rotation
which removed Sets 1-4, that leaves Sets 9-13 legal in Core.

*** THIS WILL GO STALE. *** The next rotation is expected in 2027 with
Set 17, which will retire Sets 9-12. When that happens, update
CORE_LEGAL_SET_CODES below - that one list is the only thing that needs
changing.

THE REPRINT RULE (important, and why this module works by card NAME):
Rotation applies to cards, not just sets. If a card originally printed
in a rotated set was reprinted in a still-legal set, then EVERY printing
of that card stays legal - including your old copies. Because all
printings of a card share the same full name, we can implement this
correctly just by asking "does this card's name appear anywhere in the
legal set pool?" rather than tracking reprint IDs. A card reprinted into
a legal set automatically passes.
"""

CORE = "Core Constructed"
INFINITY = "Infinity Constructed"

# Set codes legal in Core Constructed after the 24 July 2026 rotation.
# LorcanaJSON exposes these as the string `setCode` field on each card.
CORE_LEGAL_SET_CODES = {"9", "10", "11", "12", "13"}

SET_NAMES = {
    "1": "The First Chapter",
    "2": "Rise of the Floodborn",
    "3": "Into the Inklands",
    "4": "Ursula's Return",
    "5": "Shimmering Skies",
    "6": "Azurite Sea",
    "7": "Archazia's Island",
    "8": "Reign of Jafar",
    "9": "Fabled",
    "10": "Whispers in the Well",
    "11": "Winterspell",
    "12": "Wilds Unknown",
    "13": "Attack of the Vine!",
}

ROTATION_NOTE = (
    "Core Constructed legality reflects the 24 July 2026 rotation "
    "(Sets 5-8 rotated out; Sets 9-13 legal). Verify against current "
    "official rules before relying on this for a real tournament."
)


def legal_card_names(card_database: dict, fmt: str = CORE) -> set:
    """
    Returns the set of card NAMES that are legal in the given format.

    Works by name deliberately, so the reprint rule is handled for free:
    if any printing of a card sits in a legal set, the name is legal.

    Cards without a 'set_code' field are treated as legal, so the small
    bundled sample database (which has no real set data) still works.
    """
    if fmt == INFINITY:
        return set(card_database.keys())

    legal = set()
    for name, info in card_database.items():
        set_code = str(info.get("set_code", "")).strip()
        if not set_code:
            legal.add(name)          # unknown provenance -> don't block it
        elif set_code in CORE_LEGAL_SET_CODES:
            legal.add(name)
    return legal


def filter_database(card_database: dict, fmt: str = CORE) -> dict:
    """Returns a copy of the card database containing only legal cards."""
    allowed = legal_card_names(card_database, fmt)
    return {name: info for name, info in card_database.items() if name in allowed}


def check_deck_legality(deck: list, card_database: dict, fmt: str = CORE) -> dict:
    """
    Checks a built deck (flat list of card-info dicts) against the format's
    deckbuilding rules. Returns a dict:
        {"legal": bool, "problems": [str, ...], "ink_colors": [...]}

    Rules checked (these are the real Lorcana constructed rules):
      - at least 60 cards
      - no more than 4 copies of any one card name
      - no more than 2 ink colors across the whole deck
      - every card legal in the chosen format
    """
    problems = []

    if len(deck) < 60:
        problems.append(f"Deck has {len(deck)} cards; minimum is 60.")

    counts = {}
    for card in deck:
        counts[card["name"]] = counts.get(card["name"], 0) + 1
    for name, count in sorted(counts.items()):
        if count > 4:
            problems.append(f"{count} copies of '{name}'; maximum is 4.")

    ink_colors = sorted({c.get("ink_color", "Unknown") for c in deck})
    if len(ink_colors) > 2:
        problems.append(
            f"Deck uses {len(ink_colors)} ink colors ({', '.join(ink_colors)}); "
            f"maximum is 2."
        )

    allowed = legal_card_names(card_database, fmt)
    illegal = sorted({c["name"] for c in deck if c["name"] not in allowed})
    for name in illegal:
        set_code = str(card_database.get(name, {}).get("set_code", "?"))
        set_label = SET_NAMES.get(set_code, f"Set {set_code}")
        problems.append(f"'{name}' is not legal in {fmt} (from {set_label}).")

    return {"legal": not problems, "problems": problems, "ink_colors": ink_colors}
