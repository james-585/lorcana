"""
Module 1: Ingestion
--------------------
Responsible for getting raw information INTO the simulator:
  1. Card data (stats, cost, keywords) - normally from the LorcanaJSON API.
  2. Decklists (which cards, and how many copies) - from a plain text file
     in the same format Dreamborn.ink exports ("4 Card Name").

NOTE ON LIVE DATA:
This sandbox cannot reach lorcanajson.org, so `fetch_card_database_live()`
is provided for YOU to run on your own machine (it will work there, since
it's a normal internet request). For all local testing and the Monte Carlo
runs in this project, we use `load_local_card_database()`, which reads the
bundled data/sample_cards.json file instead. Both functions return the
exact same shape of data, so the rest of the program doesn't care which
one you used.
"""

import json
import os
import urllib.request

import abilities

LORCANAJSON_URL = "https://lorcanajson.org/files/current/en/allCards.json"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def fetch_card_database_live(url: str = LORCANAJSON_URL) -> dict:
    """
    Downloads the full card database from LorcanaJSON over the internet.
    Run this yourself, on your own computer, with an internet connection -
    this sandbox's network can't reach lorcanajson.org to test it directly.

    Field names below (fullName, type, cost, color, inkwell, strength,
    willpower, lore, keywordAbilities) were checked against LorcanaJSON's
    own field documentation, not guessed - but a live API can still change
    or add fields after this was written, so the first real run is worth
    a quick sanity check (print a card or two and compare to the real card).

    Returns a dict mapping card name -> card info dict.
    """
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = json.loads(response.read().decode("utf-8"))

    cards = {}
    for card in raw.get("cards", []):
        name = card.get("fullName") or card.get("name")
        if not name:
            continue
        subtypes = [str(s).lower() for s in (card.get("subtypes") or [])]
        ability_text = " ".join(
            a.get("fullText", "") for a in (card.get("abilities") or [])
        )

        cards[name] = {
            "name": name,
            "type": card.get("type", "character").lower(),
            "cost": card.get("cost", 0),
            "ink_color": card.get("color", "Unknown"),
            "inkable": card.get("inkwell", True),
            "strength": card.get("strength", 0),
            "willpower": card.get("willpower", 0),
            "lore": card.get("lore", 0),
            "keywords": card.get("keywordAbilities", []),
            # setCode is what formats.py uses to decide Core legality.
            # Illumineer's Quest cards use "Q1" rather than a number.
            "set_code": str(card.get("setCode", "")),
            # Songs are the Action subtype that characters can sing.
            "song": "song" in subtypes,
            # Locations use moveCost for characters moving onto them.
            "move_cost": card.get("moveCost", 1),
            # LorcanaJSON gives ability text as English prose, not
            # structured effects. parse_ability_text() recognises only a
            # few common phrasings and returns [] for everything else,
            # so most real cards will have no abilities in this sim.
            "abilities": abilities.parse_ability_text(ability_text),
        }
    return cards


def load_local_card_database(path: str = None) -> dict:
    """
    Loads the small bundled sample card database from data/sample_cards.json.
    Returns a dict mapping card name -> card info dict (same shape as the
    live fetch function above).
    """
    if path is None:
        path = os.path.join(DATA_DIR, "sample_cards.json")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    cards = {}
    for card in raw["cards"]:
        cards[card["name"]] = card
    return cards


def load_decklist(path: str, card_database: dict) -> list:
    """
    Reads a plain-text decklist file where each line looks like:
        4 Simba - Protective Cub
    (this is the same format Dreamborn.ink exports to your clipboard).

    Returns a flat list of card-info dicts, one entry per physical card,
    e.g. 4 copies of Simba show up as 4 separate dict entries in the list.
    This flat list is exactly what we need to build a 60-card deck object.
    """
    deck = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            count_str, _, card_name = line.partition(" ")
            if not count_str.isdigit():
                raise ValueError(
                    f"Line {line_number} in {path} doesn't start with a "
                    f"number of copies: '{line}'"
                )
            count = int(count_str)

            if card_name not in card_database:
                raise KeyError(
                    f"Line {line_number}: '{card_name}' was not found in "
                    f"the card database. Check spelling against the JSON."
                )

            card_info = card_database[card_name]
            deck.extend([card_info] * count)

    return deck


NAME_COLUMN_CANDIDATES = [
    "name", "card name", "cardname", "card", "full name", "fullname", "card_name",
]
COUNT_COLUMN_CANDIDATES = [
    "count", "quantity", "qty", "normal", "amount", "owned", "have", "total",
]
FOIL_COLUMN_CANDIDATES = ["foil", "foils", "foil count", "foil quantity"]


def load_collection_csv(path_or_file, card_database: dict = None) -> dict:
    """
    Reads a collection export (the CSV you download from Dreamborn.ink)
    and returns a dict mapping card name -> number of copies you own.

    WHY THIS IS FLEXIBLE RATHER THAN HARD-CODED:
    Dreamborn's exact export column names aren't publicly documented, and
    they've changed their site before. So instead of guessing one fixed
    layout and breaking when it's wrong, this sniffs the header row for a
    name-ish column and a count-ish column (see the candidate lists above).
    If it can't find them, it raises a clear error telling you which
    columns it DID see, so you can tell me and I'll add them.

    Foil and non-foil counts are added together, since for deckbuilding
    purposes a foil copy is still a playable copy.

    If `card_database` is given, names not present in it are ignored
    (with the count of skipped rows available via the '_unmatched' key).
    """
    import csv
    import io

    if hasattr(path_or_file, "read"):
        raw = path_or_file.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig", errors="replace")
        handle = io.StringIO(raw)
    else:
        handle = open(path_or_file, "r", encoding="utf-8-sig")

    try:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("That CSV appears to be empty.")

        lookup = {(f or "").strip().lower(): f for f in reader.fieldnames}

        def find(candidates):
            for cand in candidates:
                if cand in lookup:
                    return lookup[cand]
            return None

        name_col = find(NAME_COLUMN_CANDIDATES)
        count_col = find(COUNT_COLUMN_CANDIDATES)
        foil_col = find(FOIL_COLUMN_CANDIDATES)

        if name_col is None:
            raise ValueError(
                "Couldn't find a card-name column in that CSV. "
                f"Columns found: {reader.fieldnames}"
            )

        collection = {}
        unmatched = 0
        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue

            def as_int(value):
                try:
                    return int(float(str(value).strip() or 0))
                except (TypeError, ValueError):
                    return 0

            total = as_int(row.get(count_col)) if count_col else 1
            if foil_col:
                total += as_int(row.get(foil_col))
            if total <= 0:
                continue

            if card_database is not None and name not in card_database:
                unmatched += 1
                continue

            collection[name] = collection.get(name, 0) + total

        if unmatched:
            collection["_unmatched"] = unmatched
        return collection
    finally:
        handle.close()


if __name__ == "__main__":
    # Quick manual test: load the sample database and both sample decks.
    db = load_local_card_database()
    print(f"Loaded {len(db)} unique cards into the database.")

    aggro = load_decklist(os.path.join(DATA_DIR, "deck_aggro.txt"), db)
    control = load_decklist(os.path.join(DATA_DIR, "deck_control.txt"), db)
    print(f"Aggro deck: {len(aggro)} cards")
    print(f"Control deck: {len(control)} cards")
