"""
Module 6: Monte Carlo Loop
-----------------------------
Runs a full game between two decks + personas, over and over (default
10,000 times), recording who won and on which turn. Then uses pandas to
summarize the results and matplotlib to draw a chart of the turn-by-turn
win distribution.
"""

import os
import random

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # write chart to a file, don't need a live display
import matplotlib.pyplot as plt

from game_state import PlayerState
from event_bus import EventBus, register_default_keyword_handlers
from rules_engine import get_legal_moves, apply_move, check_winner
from ai import choose_move

MAX_TURNS = 40  # safety valve so a weird stalemate can't loop forever


def play_one_game(deck_a, persona_a, deck_b, persona_b) -> dict:
    """Simulates a single full game and returns a small result dict:
    {'winner': 'A' or 'B' or 'draw', 'turns': int}"""

    player_a = PlayerState("A", deck_a)
    player_b = PlayerState("B", deck_b)
    bus = EventBus()
    register_default_keyword_handlers(bus)

    order = [(player_a, player_b, persona_a), (player_b, player_a, persona_b)]

    # Opening hands.
    player_a.draw(7)
    player_b.draw(7)

    turn_number = 0
    active_index = 0
    first_player_first_turn = True

    while turn_number < MAX_TURNS:
        turn_number += 1
        active, defender, persona = order[active_index]
        opponent_of_active = defender

        active.ready_all()
        active.inked_this_turn = False

        # The player going first skips their very first draw (real rule).
        if not (first_player_first_turn and active_index == 0):
            deck_ran_out = not active.draw(1)
            if deck_ran_out:
                winner_name = opponent_of_active.name
                return {"winner": winner_name, "turns": turn_number}

        # Main phase: keep taking the best-scoring move until "pass".
        safety = 0
        while safety < 50:
            safety += 1
            moves = get_legal_moves(active, opponent_of_active)
            move = choose_move(moves, active, opponent_of_active, persona)
            apply_move(move, active, opponent_of_active, bus)
            if move.kind == "pass":
                break

        winner_name = check_winner(player_a, player_b)
        if winner_name:
            return {"winner": winner_name, "turns": turn_number}

        if active_index == 0:
            first_player_first_turn = False
        active_index = 1 - active_index

    return {"winner": "draw", "turns": MAX_TURNS}


def run_monte_carlo(deck_a, persona_a, deck_b, persona_b,
                     num_games: int = 10000, seed: int = None) -> pd.DataFrame:
    """Runs num_games simulated games and returns a pandas DataFrame with
    one row per game: columns ['winner', 'turns']."""
    if seed is not None:
        random.seed(seed)

    results = []
    for _ in range(num_games):
        results.append(play_one_game(deck_a, persona_a, deck_b, persona_b))

    return pd.DataFrame(results)


def summarize(df: pd.DataFrame, name_a: str, name_b: str):
    """Prints win rates and returns a per-turn win-count table for charting."""
    total = len(df)
    win_counts = df["winner"].value_counts()

    print(f"\nSimulated {total} games:")
    for label, display_name in (("A", name_a), ("B", name_b), ("draw", "Draws")):
        count = win_counts.get(label, 0)
        pct = 100 * count / total
        print(f"  {display_name:20s}: {count:5d} wins ({pct:5.1f}%)")

    turn_table = (
        df[df["winner"] != "draw"]
        .groupby(["turns", "winner"])
        .size()
        .unstack(fill_value=0)
    )
    return turn_table


def build_turn_distribution_figure(turn_table: pd.DataFrame, name_a: str, name_b: str):
    """Builds and returns a matplotlib Figure (doesn't save or print anything).
    Used by both the CLI (which saves it) and the web app (which displays it)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    turn_table.rename(columns={"A": name_a, "B": name_b}).plot(
        kind="bar", stacked=True, ax=ax
    )
    ax.set_xlabel("Turn the game ended")
    ax.set_ylabel("Number of games won")
    ax.set_title(f"Win Distribution by Turn: {name_a} vs {name_b}")
    ax.legend(title="Winner")
    fig.tight_layout()
    return fig


def plot_turn_distribution(turn_table: pd.DataFrame, name_a: str, name_b: str,
                            output_path: str):
    """CLI convenience wrapper: builds the figure above and saves it to disk."""
    fig = build_turn_distribution_figure(turn_table, name_a, name_b)
    fig.savefig(output_path)
    print(f"\nChart saved to: {output_path}")


if __name__ == "__main__":
    import ingestion

    data_dir = os.path.join(os.path.dirname(__file__), "data")
    db = ingestion.load_local_card_database()
    deck_aggro = ingestion.load_decklist(os.path.join(data_dir, "deck_aggro.txt"), db)
    deck_control = ingestion.load_decklist(os.path.join(data_dir, "deck_control.txt"), db)

    df = run_monte_carlo(
        deck_aggro, "Aggro",
        deck_control, "Control",
        num_games=10000,
        seed=42,
    )

    turn_table = summarize(df, "Aggro Deck", "Control Deck")
    output_path = os.path.join(os.path.dirname(__file__), "win_distribution.png")
    plot_turn_distribution(turn_table, "Aggro Deck", "Control Deck", output_path)
