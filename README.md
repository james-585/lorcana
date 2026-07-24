# Lorcana Monte Carlo Simulator

A headless Python simulator that plays two decks against each other
thousands of times and reports win rates + a turn-by-turn win chart.

## How to run it

1. Install Python 3.10+ if you don't have it.
2. Open a terminal in this folder and run:
   ```
   pip install pandas matplotlib
   python3 monte_carlo.py
   ```
3. You'll see win rates printed to the terminal, and a chart saved as
   `win_distribution.png` in this folder.

This runs the two included sample decks (`data/deck_aggro.txt` vs.
`data/deck_control.txt`) against each other 10,000 times.

## The 6 modules, and where to find them

| # | Module | File | What it does |
|---|--------|------|---------------|
| 1 | Ingestion | `ingestion.py` | Loads card stats and reads decklist text files |
| 2 | Game State | `game_state.py` | The zones (Deck/Hand/Ink/Play/Discard) for each player |
| 3 | Rules Engine | `rules_engine.py` | Ink, play, quest, challenge, win condition |
| 4 | Event Bus | `event_bus.py` | Where keyword abilities (Rush, Bodyguard...) hook in |
| 5 | Heuristic AI | `ai.py` | Scores legal moves based on Aggro/Control persona |
| 6 | Monte Carlo Loop | `monte_carlo.py` | Runs many games, builds the pandas table + chart |
| 7 | Formats | `formats.py` | Which sets/cards are tournament-legal; deck rule checks |
| 8 | Optimiser | `optimiser.py` | Builds the best legal deck from cards you own |
| 9 | Abilities | `abilities.py` | Trigger/effect framework for card text |

Read them in that order - each one only depends on the ones before it.

## Reading order for learning

Start with `game_state.py` (it's just data), then `ingestion.py` (it's
just file reading), then `rules_engine.py` (the actual game logic - this
is the one worth reading slowly), then `event_bus.py`, `ai.py`, and
finally `monte_carlo.py` which wires everything together.

Every function has a docstring explaining what it does and why. If
anything doesn't make sense, ask me about that specific function/line -
I'd rather explain it than have you guess.

## Using your own decks

Export a decklist as plain text in this format (one line per card):
```
4 Simba - Protective Cub
2 Elsa - Snow Queen
```
This is the same format Dreamborn.ink puts on your clipboard when you
copy a deck. Save it as a `.txt` file, then point `ingestion.load_decklist()`
at it. **Important:** every card name in your decklist must exist in the
card database you load (see next section), spelled exactly the same way.

## Card data: sample vs. live

This project ships with `data/sample_cards.json` - 60 hand-picked cards
across the full cost curve (1 to 8), enough for two genuinely distinct
60-card decks without needing every card to repeat 4 times.

**Important caveat on the sample data:** these use real Lorcana card
names, but I approximated the stats, and the `set_code` values are
*invented* — assigned randomly across legal and rotated sets purely so
the format filter has something to filter. So the sample database
exercises the plumbing correctly, but it is not real card data and its
Core/Infinity legality results are meaningless. Switch on the live
database for anything real.

The web app (`app.py`) now has a sidebar toggle: **"Use the full official
card database (live, ~2,700 cards)"**. Turn it on and it fetches every
real Lorcana card from LorcanaJSON the first time, then caches it for 24
hours so it's not re-downloading on every click. When it's on, you must
upload your own decklist file(s) - the two built-in sample decks are made
up for testing and won't match real card names.

I verified the field names used in `ingestion.fetch_card_database_live()`
(`fullName`, `type`, `cost`, `color`, `inkwell`, `strength`, `willpower`,
`lore`, `keywordAbilities`) against LorcanaJSON's own published field
documentation - so this isn't a guess. That said, I still couldn't run
this fetch myself (my sandbox can't reach that domain), so when you try
it for the first time, it's worth checking that one or two cards look
right before trusting a big simulation on it.

To use the live database from the command line instead of the web app:
```python
import ingestion
db = ingestion.fetch_card_database_live()   # needs internet, run on your machine
```

## Card abilities

`abilities.py` gives cards actual rules text. An ability is declared as
data on the card, not as code:

```json
"abilities": [
  {"trigger": "on_play",  "effect": "draw",      "amount": 1},
  {"trigger": "on_quest", "effect": "gain_lore", "amount": 1}
]
```

**Triggers:** `on_play`, `on_quest`, `on_challenge`, `on_sing`,
`on_banish`, `start_of_turn`.
**Effects:** `draw`, `gain_lore`, `lose_lore`, `damage`, `heal`, `ready`,
`ramp`, `buff_strength`.

Adding a new effect is one function plus one dictionary entry — see the
`EFFECTS` table in `abilities.py`.

This is what the Event Bus was built for. It previously fired events that
nothing listened to; abilities are now its cargo.

### The honest limit — please read
LorcanaJSON supplies ability text as **English prose** ("Whenever this
character quests, you may draw a card"), not as structured effects. There
is no machine-readable encoding of what a card does. So:

- Cards get abilities only if someone hand-writes the declaration above,
  or if their text matches one of four simple patterns in
  `parse_ability_text()`.
- **When you switch on the live database, the overwhelming majority of
  real cards will have no abilities in this simulator.** Their text is
  unique prose nothing here can interpret.
- This is a framework plus a starter library, not a card-text
  interpreter. Building the latter is a much larger project.

The bundled sample database has 20 cards with hand-written abilities so
the system is actually exercised.

## Card types

All four Lorcana card types are now modelled:

| Type | Behaviour |
|------|-----------|
| **Character** | Quests, challenges, sings, can be shifted onto |
| **Item** | Stays in play, provides abilities, never quests or challenges |
| **Location** | Gains lore at the start of your turn *instead of* questing. Never exerts, has no summoning sickness, and can be challenged at any time |
| **Action** | One-shot effect, then straight to discard. **Songs** are the Action subtype a character can sing |

## Keywords

| Keyword | Status | Where it lives |
|---------|--------|----------------|
| Rush | Enforced | `game_state.can_act()` |
| Evasive | Enforced | `rules_engine.get_valid_challenge_targets()` |
| Bodyguard | Enforced | `rules_engine.get_valid_challenge_targets()` |
| Reckless | Enforced | `rules_engine.get_legal_moves()` |
| **Shift N** | Enforced | Play a same-named character for N ink, inheriting damage and readiness |
| **Singer N** | Enforced | Sing songs as though your cost were N |
| **Sing** | Enforced | Exert a ready character whose cost ≥ the song's cost; the song costs no ink |
| **Support** | Enforced | On quest, adds this character's Strength to an ally until end of turn |
| Ward | **Inert** | Ward stops opponents *targeting* a character. This engine has no targeted effects, so there is nothing for it to stop |

Note that keywords with numbers arrive from LorcanaJSON as strings like
`"Shift 5"`, so the code matches by prefix and parses the number out —
a plain `"Shift" in keywords` check would silently miss every one.

## Mulligan

Both players draw 7, then may bottom any number of cards and draw that
many replacements, reshuffling afterwards. Once per game, per the real
rules. The keep/toss policy lives in
`game_state.default_mulligan_policy()` and is deliberately simple: keep
anything costing 3 or less, or inkable and costing 5 or less.

It measurably matters — in the bundled sample matchup, turning mulligan
off shifts the Aggro win rate from 64.0% to 69.9%.

Disable it with `run_monte_carlo(..., use_mulligan=False)`.

## Testing

`test_mechanics.py` verifies that each mechanic produces the correct
state change, rather than merely running without crashing — that
shifting carries damage over, that singing spends no ink, that Support
expires at end of turn, that locations can't quest but can be challenged
while unexerted, and so on.

```
python3 test_mechanics.py
```

35 checks, all passing. This suite caught two real bugs during
development: start-of-turn abilities silently never fired (the handler
matched on card identity, but that event carries no card), and the AI
scored hard-casting a song *above* singing it for free.

## Remaining simplifications

Still not modelled:

- **Most real card text.** See the honest limit above — the framework
  exists, the per-card content does not.
- **Targeted effects and choices.** Abilities auto-pick their targets
  (biggest threat, most damaged ally). No player choice, which is also
  why Ward has nothing to do.
- **Sing Together**, which lets several characters combine costs to sing
  one song.
- **Challenger +N**, and other numeric combat keywords.
- **Location abilities granting bonuses to characters stationed there.**
  Characters can move to locations, but locations don't yet buff them.
- **Ink color restrictions during play** — correctly, because no such
  rule exists. Ink in the inkwell is generic; any ink pays any cost. The
  2-color limit is a deckbuilding rule and *is* enforced.
- **The Bodyguard entry rule.** Bodyguard characters may optionally enter
  play exerted; this sim treats Bodyguard purely as a challenge
  redirect. Worth verifying against the Comprehensive Rules if you lean
  on Bodyguard-heavy results.

## What the sample result means

With the bundled 20-card pool and simplified rules, the Aggro persona
currently wins ~80% of games against Control. That's a real result of
*this* simplified model, not a claim about real Lorcana metagame - the
AI's scoring weights in `ai.py` are hand-tuned starting points, and the
card pool is tiny. Once you're comfortable reading the code, tuning those
weights (or the card pool) and watching the win rate shift is a good way
to build intuition for both Python and game balance.
