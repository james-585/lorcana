"""
Web App (Streamlit)
----------------------
The "end user" front end. Two tabs:
  1. Simulate Matchup - play two decks against each other N times
  2. Deck Optimiser   - build the best deck from cards you own

No new simulator logic lives here; this file only wires the other
modules to buttons and charts.
"""

import os

import pandas as pd
import streamlit as st

import ingestion
import formats
import optimiser
from monte_carlo import run_monte_carlo, build_turn_distribution_figure

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

st.set_page_config(page_title="Lorcana Deck Simulator", page_icon="🎴", layout="wide")
st.title("🎴 Lorcana Monte Carlo Deck Simulator")

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Card Database")
use_live_db = st.sidebar.checkbox(
    "Use the full official card database (live, ~2,700 cards)",
    value=False,
    help="Off = the 60-card sample bundled with this app. "
         "On = fetches every real Lorcana card from LorcanaJSON.",
)


@st.cache_data(ttl=60 * 60 * 24, show_spinner="Downloading the full card database...")
def get_live_card_database():
    return ingestion.fetch_card_database_live()


if use_live_db:
    try:
        CARD_DB = get_live_card_database()
        st.sidebar.success(f"Loaded {len(CARD_DB)} real cards.")
    except Exception as e:
        st.sidebar.error(f"Couldn't fetch the live database: {e}")
        st.stop()
else:
    CARD_DB = ingestion.load_local_card_database()
    st.sidebar.info(f"Using the {len(CARD_DB)}-card sample database.")

st.sidebar.header("Format")
fmt = st.sidebar.radio(
    "Tournament format",
    [formats.CORE, formats.INFINITY],
    help="Core rotates; Infinity allows every card ever printed.",
)
LEGAL_NAMES = formats.legal_card_names(CARD_DB, fmt)
st.sidebar.caption(f"{len(LEGAL_NAMES)} of {len(CARD_DB)} cards legal in {fmt}.")
st.sidebar.caption(formats.ROTATION_NOTE)

st.sidebar.header("Your Collection (optional)")
collection_file = st.sidebar.file_uploader(
    "Dreamborn collection export (.csv)", type=["csv"], key="collection"
)
COLLECTION = None
if collection_file is not None:
    try:
        COLLECTION = ingestion.load_collection_csv(collection_file, CARD_DB)
        unmatched = COLLECTION.pop("_unmatched", 0)
        st.sidebar.success(
            f"{len(COLLECTION)} card types owned "
            f"({sum(COLLECTION.values())} copies)."
        )
        if unmatched:
            st.sidebar.warning(
                f"{unmatched} rows didn't match a card name in the database "
                f"and were skipped."
            )
    except Exception as e:
        st.sidebar.error(f"Couldn't read that collection file: {e}")
        COLLECTION = None

BUILT_IN_DECKS = {
    "Sample Aggro Deck": os.path.join(DATA_DIR, "deck_aggro.txt"),
    "Sample Control Deck": os.path.join(DATA_DIR, "deck_control.txt"),
}


def load_deck(built_in_choice, uploaded_file):
    """Uploaded file wins; otherwise fall back to a built-in sample deck."""
    if uploaded_file is not None:
        text = uploaded_file.getvalue().decode("utf-8")
        temp_path = os.path.join(DATA_DIR, "_uploaded_temp.txt")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
        return ingestion.load_decklist(temp_path, CARD_DB)
    if built_in_choice is None:
        raise ValueError("Please upload a decklist file.")
    return ingestion.load_decklist(BUILT_IN_DECKS[built_in_choice], CARD_DB)


def show_legality(deck, label):
    """Renders a pass/fail legality panel for a deck."""
    result = formats.check_deck_legality(deck, CARD_DB, fmt)
    if result["legal"]:
        st.success(f"{label}: legal in {fmt} "
                   f"({len(deck)} cards, ink: {'/'.join(result['ink_colors'])})")
    else:
        st.warning(f"{label}: NOT legal in {fmt}")
        for problem in result["problems"][:10]:
            st.caption(f"• {problem}")
        if len(result["problems"]) > 10:
            st.caption(f"...and {len(result['problems']) - 10} more.")
    return result


tab_sim, tab_opt = st.tabs(["⚔️ Simulate Matchup", "🔧 Deck Optimiser"])

# ------------------------------------------------------- tab 1: matchup
with tab_sim:
    st.write("Pick two decks and see which wins more often, and how fast.")
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Deck A")
        choice_a = None if use_live_db else st.selectbox(
            "Choose deck A", list(BUILT_IN_DECKS.keys()), key="deck_a")
        upload_a = st.file_uploader("Upload decklist (.txt)", key="up_a")
        persona_a = st.selectbox("Persona", ["Aggro", "Control"], key="pa")

    with c2:
        st.subheader("Deck B")
        choice_b = None if use_live_db else st.selectbox(
            "Choose deck B", list(BUILT_IN_DECKS.keys()), index=1, key="deck_b")
        upload_b = st.file_uploader("Upload decklist (.txt)", key="up_b")
        persona_b = st.selectbox("Persona", ["Aggro", "Control"], index=1, key="pb")

    num_games = st.slider("Games to simulate", 100, 20000, 5000, step=100)
    use_mull = st.checkbox(
        "Use mulligan phase", value=True,
        help="Both players bottom their unplayable cards and redraw, "
             "as per the real rules. Turning this off makes opening "
             "hands worse and measurably changes win rates.")

    if st.button("Run Simulation", type="primary", key="run_sim"):
        try:
            deck_a = load_deck(choice_a, upload_a)
            deck_b = load_deck(choice_b, upload_b)
        except (KeyError, ValueError) as e:
            st.error(f"Problem reading a decklist: {e}")
            st.stop()

        label_a = choice_a or "Deck A"
        label_b = choice_b or "Deck B"
        show_legality(deck_a, label_a)
        show_legality(deck_b, label_b)
        st.caption("Illegal decks are still simulated - the check is advisory.")

        with st.spinner(f"Simulating {num_games} games..."):
            df = run_monte_carlo(deck_a, persona_a, deck_b, persona_b,
                                 num_games=num_games, use_mulligan=use_mull)

        total = len(df)
        counts = df["winner"].value_counts()
        a_wins, b_wins = counts.get("A", 0), counts.get("B", 0)
        draws = counts.get("draw", 0)

        st.subheader("Results")
        r1, r2, r3 = st.columns(3)
        r1.metric(f"{label_a} (A)", f"{100*a_wins/total:.1f}%", f"{a_wins} wins")
        r2.metric(f"{label_b} (B)", f"{100*b_wins/total:.1f}%", f"{b_wins} wins")
        r3.metric("Draws", f"{100*draws/total:.1f}%", f"{draws} games")

        turn_table = (df[df["winner"] != "draw"]
                      .groupby(["turns", "winner"]).size().unstack(fill_value=0))
        st.pyplot(build_turn_distribution_figure(
            turn_table, f"{label_a} (A)", f"{label_b} (B)"))

# ----------------------------------------------------- tab 2: optimiser
with tab_opt:
    st.write(
        "Builds the best legal 60-card deck it can. Upload your collection "
        "in the sidebar to restrict it to cards you actually own."
    )

    if COLLECTION is None:
        st.info(
            "No collection uploaded - assuming you own 4 copies of every "
            "legal card. Upload a Dreamborn CSV in the sidebar to build "
            "only from your real cards."
        )

    o1, o2 = st.columns(2)
    with o1:
        opt_persona = st.selectbox(
            "Deck style to build", ["Aggro", "Control"], key="opt_persona")
    with o2:
        mode = st.radio(
            "How should 'best' be decided?",
            ["Heuristic (fast)", "Simulation (slow, evidence-based)"],
            key="opt_mode",
        )

    if mode.startswith("Simulation"):
        sc1, sc2 = st.columns(2)
        n_candidates = sc1.slider("Candidate decks to test", 2, 8, 4)
        games_each = sc2.slider("Games per candidate", 100, 2000, 300, step=100)
        st.caption(
            f"About {n_candidates} x {games_each} games total. "
            "300 games gives roughly ±3% accuracy on each win rate."
        )

    if st.button("Build Deck", type="primary", key="run_opt"):
        if mode.startswith("Heuristic"):
            with st.spinner("Scoring cards and building decks..."):
                results = optimiser.optimise_heuristic(
                    CARD_DB, opt_persona, collection=COLLECTION,
                    legal_names=LEGAL_NAMES, top_n=3)
        else:
            with st.spinner("Building candidates..."):
                bench_list = optimiser.optimise_heuristic(
                    CARD_DB, "Control" if opt_persona == "Aggro" else "Aggro",
                    collection=None, legal_names=LEGAL_NAMES, top_n=1)
            if not bench_list:
                st.error("Couldn't build a benchmark opponent deck.")
                st.stop()
            bench = bench_list[0]["deck"]
            bar = st.progress(0.0, text="Simulating candidates...")
            results = optimiser.optimise_by_simulation(
                CARD_DB, opt_persona, bench,
                "Control" if opt_persona == "Aggro" else "Aggro",
                collection=COLLECTION, legal_names=LEGAL_NAMES,
                candidates=n_candidates, games_per_candidate=games_each,
                progress=lambda d, t: bar.progress(d / t, text=f"Tested {d}/{t}"),
            )
            bar.empty()

        if not results:
            st.error(
                "Couldn't build a legal 60-card deck. Usually this means "
                "your collection doesn't have 60 available cards in any "
                "single pair of ink colors within this format."
            )
            st.stop()

        st.subheader("Best decks found")
        for rank, r in enumerate(results, start=1):
            colors = "/".join(r["colors"])
            if "win_rate" in r:
                header = f"#{rank} — {colors} — {r['win_rate']:.1f}% win rate"
            else:
                header = f"#{rank} — {colors} — quality score {r['score']:.1f}"

            with st.expander(header, expanded=(rank == 1)):
                check = formats.check_deck_legality(r["deck"], CARD_DB, fmt)
                if check["legal"]:
                    st.success(f"Legal in {fmt}")
                else:
                    for p in check["problems"][:5]:
                        st.warning(p)

                curve = optimiser.deck_curve(r["deck"])
                st.bar_chart(pd.DataFrame(
                    {"cards": list(curve.values())},
                    index=[f"{c} ink" for c in curve.keys()]))

                text = optimiser.deck_to_text(r["deck"])
                st.code(text, language=None)
                st.download_button(
                    "Download this decklist (.txt)", text,
                    file_name=f"optimised_{'_'.join(r['colors'])}.txt",
                    key=f"dl_{rank}",
                )
