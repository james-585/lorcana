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

## Deliberate simplifications (v1 scope)

To keep this buildable and readable, the rules engine does **not**
implement:
- Ink color restrictions (a card's `ink_color` is tracked but any ink
  pays for any cost - real Lorcana requires 2 chosen colors per deck)
- Card text / abilities beyond the keywords Rush, Evasive, Bodyguard,
  Ward, Reckless (no "when you play this, draw a card" style effects)
- Shift, Singer, Support, Sing (listed in your original module 4 spec
  as examples, but not yet wired up - the Event Bus is built so you can
  add a handler for each the same way Bodyguard/Reckless were added)
- Items and Locations (only Character and Action-type stats are modeled;
  the sample deck uses only Characters)
- Mulligan phase (both players just keep their opening 7)

None of these are hard to add later - the architecture (especially the
Event Bus) was built so each one is an isolated addition, not a rewrite.

## Running the web app locally

There's now a browser-based version, `app.py`, built with Streamlit. It
uses the exact same ingestion/monte_carlo code as the command line
version - it's just a different front end.

```
pip install -r requirements.txt
streamlit run app.py
```

This opens a page in your browser where you pick two decks (built-in or
uploaded), a persona for each, a number of games, and click "Run
Simulation" to see win rates and the chart live - no terminal output to
read, no editing the script.

## Putting it on the internet (so anyone with a link can use it, free)

Streamlit Community Cloud hosts apps like this for free. No server
management needed. Steps:

1. **Create a GitHub account** at github.com if you don't have one.
2. **Create a new repository** (the green "New" button), name it
   something like `lorcana-sim`, keep it Public.
3. **Upload these files** to that repository: on the repo page, click
   "Add file" → "Upload files", then drag in every file from this folder
   (all the `.py` files, `requirements.txt`, `README.md`, and the whole
   `data/` folder). Commit the changes. You do not need to install git or
   use the command line for this - the browser upload is enough.
4. Go to **share.streamlit.io** and sign in with your GitHub account.
5. Click **"New app"**, pick your `lorcana-sim` repository, set the
   main file path to `app.py`, and click **Deploy**.
6. After a minute or two, Streamlit gives you a public URL like
   `https://your-app-name.streamlit.app`. Anyone with that link can open
   it in a browser and run simulations - no install, no Python, nothing.

Whenever you update the code on GitHub, the hosted app updates itself
automatically within a minute or so.

## What the sample result means

With the bundled 20-card pool and simplified rules, the Aggro persona
currently wins ~80% of games against Control. That's a real result of
*this* simplified model, not a claim about real Lorcana metagame - the
AI's scoring weights in `ai.py` are hand-tuned starting points, and the
card pool is tiny. Once you're comfortable reading the code, tuning those
weights (or the card pool) and watching the win rate shift is a good way
to build intuition for both Python and game balance.
