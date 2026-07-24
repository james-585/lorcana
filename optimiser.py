"""
Module 8: Deck Optimiser
--------------------------
Builds the best 60-card deck it can from the cards you actually own,
respecting the real Lorcana deckbuilding rules:
    - exactly 60 cards
    - at most 4 copies of any one card name
    - at most 2 ink colors
    - only cards legal in the chosen format
    - only cards you own, in the quantities you own them

Two modes, because "optimal" can mean two different things:

  HEURISTIC (fast, seconds)
      Scores every available card with a persona-weighted formula and
      fills a target cost curve with the best-scoring cards. No games are
      played. Good for a strong starting list.

  SIMULATION (slow, minutes)
      Builds several candidate decks (one per viable ink-color pair),
      then actually plays each one against a benchmark deck using the
      Monte Carlo engine and returns them ranked by measured win rate.
      Slower, but the ranking is evidence rather than opinion.

An honest note on what this is NOT: the heuristic scores cards on stats,
curve, and keywords. It does not read card text, so it cannot spot combos
or synergies between specific cards. Simulation mode measures real
outcomes, but only within this simulator's simplified ruleset.
"""

import itertools
import random

from ai import AGGRO, CONTROL

# Target cost curves - roughly how many cards of each ink cost we want in
# a 60-card deck. Aggro wants a low, fast curve; Control is happy to go
# bigger and later. These sum to 60.
CURVE_TARGETS = {
    AGGRO:   {1: 8, 2: 14, 3: 14, 4: 10, 5: 8, 6: 4, 7: 2, 8: 0},
    CONTROL: {1: 4, 2: 8,  3: 10, 4: 12, 5: 10, 6: 8, 7: 5, 8: 3},
}

MAX_COPIES = 4
DECK_SIZE = 60
MAX_INK_COLORS = 2


def _kw(keywords, name):
    """
    Matches a keyword by prefix, because Lorcana keywords can carry a
    number: 'Shift 5', 'Singer 4', 'Challenger +2'. A plain
    `"Shift" in keywords` check would miss all of those.
    """
    return any(str(k).strip().lower().startswith(name.lower())
               for k in (keywords or []))


def score_card(info: dict, persona: str) -> float:
    """
    Rates a single card's standalone quality for a given persona.
    Higher is better. Deliberately simple and readable - you can tune
    these numbers and immediately see the effect on the built deck.

    Non-character types are scored on their own terms, because judging a
    Location or an Item by strength/willpower would score them at zero
    and they'd never make a deck.
    """
    cost = max(info.get("cost", 1), 1)
    card_type = info.get("type", "character")
    keywords = info.get("keywords", [])
    ability_count = len(info.get("abilities", []) or [])

    if card_type == "location":
        # Locations earn lore passively every turn - excellent in long
        # games, close to useless if the game ends on turn 12.
        score = (info.get("lore", 0) / cost) * 26
        score += info.get("willpower", 0) * 0.8   # survives being attacked
        score += ability_count * 4
        return score * (1.25 if persona == CONTROL else 0.7)

    if card_type == "item":
        # Items do nothing on their own; their whole value is their text.
        score = 6 + ability_count * 12 - cost * 1.5
        return score * (1.2 if persona == CONTROL else 0.85)

    if card_type == "action":
        # One-shot effects. Songs are better than plain actions because a
        # character can sing them for free.
        score = 8 + ability_count * 10 - cost * 1.2
        if info.get("song", False):
            score += 5
        return score * (1.1 if persona == CONTROL else 0.95)

    # --- characters -------------------------------------------------
    strength = info.get("strength", 0)
    willpower = info.get("willpower", 0)
    lore = info.get("lore", 0)

    # Raw stats-per-ink: how much board presence you get for the price.
    efficiency = (strength + willpower) / cost
    # Lore rate is what actually wins the game.
    lore_rate = lore / cost

    if persona == AGGRO:
        score = lore_rate * 22 + efficiency * 4 + strength * 1.2
        if _kw(keywords, "Rush"):
            score += 6      # attacks the turn it lands
        if _kw(keywords, "Evasive"):
            score += 6      # hard to block, keeps questing
        if _kw(keywords, "Reckless"):
            score -= 5      # can't quest, so it fights the gameplan
        if _kw(keywords, "Shift"):
            score += 4      # cheap way to redeploy a bigger body
        if info.get("inkable", True):
            score += 2
    else:  # CONTROL
        score = lore_rate * 10 + efficiency * 5 + willpower * 1.6
        if _kw(keywords, "Bodyguard"):
            score += 7      # protects the rest of the board
        if _kw(keywords, "Ward"):
            score += 5      # dodges removal
        if _kw(keywords, "Reckless"):
            score -= 3
        if _kw(keywords, "Support"):
            score += 4      # makes your other characters bigger
        if _kw(keywords, "Singer"):
            score += 3      # lets cheap bodies cast big songs
        if info.get("inkable", True):
            score += 2

    score += ability_count * 5      # printed card text is worth something
    return score


def _available_pool(card_database: dict, collection: dict = None,
                     legal_names: set = None) -> dict:
    """
    Works out which cards can actually go in a deck, and how many copies
    of each are available.

    Returns dict: card name -> (info, max_copies_available)
    """
    pool = {}
    for name, info in card_database.items():
        if name.startswith("_"):
            continue
        if legal_names is not None and name not in legal_names:
            continue

        if collection is None:
            available = MAX_COPIES          # assume you own a playset
        else:
            owned = collection.get(name, 0)
            if owned <= 0:
                continue
            available = min(owned, MAX_COPIES)

        pool[name] = (info, available)
    return pool


def build_deck_for_colors(pool: dict, colors: tuple, persona: str) -> list:
    """
    Builds the best 60-card deck using only the given ink colors.
    Returns a flat list of card-info dicts, or None if there aren't
    enough available cards in those colors to reach 60.
    """
    candidates = [
        (name, info, available)
        for name, (info, available) in pool.items()
        if info.get("ink_color") in colors
    ]

    total_available = sum(available for _, _, available in candidates)
    if total_available < DECK_SIZE:
        return None

    # Rank by quality once; we'll draw from this ordering repeatedly.
    ranked = sorted(
        candidates,
        key=lambda item: score_card(item[1], persona),
        reverse=True,
    )

    targets = dict(CURVE_TARGETS[persona])
    deck = []
    used = {}

    # Pass 1: fill the target curve slot by slot, best card first.
    for cost_slot in sorted(targets):
        need = targets[cost_slot]
        if need <= 0:
            continue
        for name, info, available in ranked:
            if need <= 0:
                break
            if info.get("cost") != cost_slot:
                continue
            can_take = min(available - used.get(name, 0), need)
            if can_take <= 0:
                continue
            deck.extend([info] * can_take)
            used[name] = used.get(name, 0) + can_take
            need -= can_take

    # Pass 2: the curve rarely fills perfectly (you may not own enough
    # 2-drops, say). Top up with the best remaining cards regardless of
    # cost until we hit 60.
    if len(deck) < DECK_SIZE:
        for name, info, available in ranked:
            if len(deck) >= DECK_SIZE:
                break
            can_take = min(available - used.get(name, 0), DECK_SIZE - len(deck))
            if can_take <= 0:
                continue
            deck.extend([info] * can_take)
            used[name] = used.get(name, 0) + can_take

    if len(deck) < DECK_SIZE:
        return None
    return deck[:DECK_SIZE]


def optimise_heuristic(card_database: dict, persona: str,
                        collection: dict = None, legal_names: set = None,
                        top_n: int = 3) -> list:
    """
    HEURISTIC MODE. Tries every viable pair of ink colors, builds the best
    deck for each, and returns the top_n ranked by total card quality.

    Returns a list of dicts:
        {"colors": (a, b), "deck": [...], "score": float}
    """
    pool = _available_pool(card_database, collection, legal_names)
    colors_present = sorted({
        info.get("ink_color", "Unknown") for info, _ in pool.values()
    })

    results = []
    for pair in itertools.combinations(colors_present, MAX_INK_COLORS):
        deck = build_deck_for_colors(pool, pair, persona)
        if deck is None:
            continue
        avg_quality = sum(score_card(c, persona) for c in deck) / len(deck)
        results.append({"colors": pair, "deck": deck, "score": avg_quality})

    # Also try single-color decks, which are legal and sometimes viable.
    for single in colors_present:
        deck = build_deck_for_colors(pool, (single,), persona)
        if deck is None:
            continue
        avg_quality = sum(score_card(c, persona) for c in deck) / len(deck)
        results.append({"colors": (single,), "deck": deck, "score": avg_quality})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]


def optimise_by_simulation(card_database: dict, persona: str,
                            benchmark_deck: list, benchmark_persona: str,
                            collection: dict = None, legal_names: set = None,
                            candidates: int = 5, games_per_candidate: int = 300,
                            seed: int = None, progress=None) -> list:
    """
    SIMULATION MODE. Takes the top candidate decks from the heuristic,
    then actually plays each one against `benchmark_deck` and ranks them
    by measured win rate.

    `games_per_candidate` is deliberately modest by default - 300 games
    gives a rough read in seconds. Push it higher for a tighter estimate;
    the statistical noise on 300 games is roughly +/- 3%.

    `progress` is an optional callback(done, total) for UI progress bars.

    Returns a list of dicts sorted by win rate:
        {"colors": (...), "deck": [...], "win_rate": float, "games": int}
    """
    from monte_carlo import run_monte_carlo   # imported here to avoid cycles

    shortlist = optimise_heuristic(
        card_database, persona, collection, legal_names, top_n=candidates
    )
    if not shortlist:
        return []

    if seed is not None:
        random.seed(seed)

    results = []
    for index, candidate in enumerate(shortlist):
        df = run_monte_carlo(
            candidate["deck"], persona,
            benchmark_deck, benchmark_persona,
            num_games=games_per_candidate,
        )
        wins = (df["winner"] == "A").sum()
        results.append({
            "colors": candidate["colors"],
            "deck": candidate["deck"],
            "win_rate": 100.0 * wins / len(df),
            "games": len(df),
        })
        if progress:
            progress(index + 1, len(shortlist))

    results.sort(key=lambda r: r["win_rate"], reverse=True)
    return results


def deck_to_text(deck: list) -> str:
    """Turns a built deck back into the '4 Card Name' text format, so you
    can paste it into Dreamborn or save it as a .txt decklist."""
    counts = {}
    for card in deck:
        counts[card["name"]] = counts.get(card["name"], 0) + 1
    lines = [f"{count} {name}" for name, count in sorted(counts.items())]
    return "\n".join(lines)


def deck_curve(deck: list) -> dict:
    """Returns {cost: number of cards} for displaying a curve chart."""
    curve = {}
    for card in deck:
        cost = card.get("cost", 0)
        curve[cost] = curve.get(cost, 0) + 1
    return dict(sorted(curve.items()))
