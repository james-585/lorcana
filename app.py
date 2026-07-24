"""
Web App (Streamlit)
----------------------
This is the "end user" front end: a browser page where someone picks two
decks, hits a button, and sees the win rate + chart. No terminal, no
Python knowledge required from them.

This file doesn't contain any NEW simulator logic - it just calls the same
ingestion / monte_carlo functions your command-line version uses, and
displays the results with Streamlit's UI widgets instead of print().
"""

import os

import streamlit as st

import ingestion
from monte_carlo import run_monte_carlo, summarize, build_turn_distribution_figure

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

st.set_page_config(page_title="Lorcana Deck Simulator", page_icon="🎴")
st.title("🎴 Lorcana Monte Carlo Deck Simulator")
st.write(
    "Pick two decks, choose how many games to simulate, and see which "
    "deck wins more often and how fast."
)

BUILT_IN_DECKS = {
    "Sample Aggro Deck": os.path.join(DATA_DIR, "deck_aggro.txt"),
    "Sample Control Deck": os.path.join(DATA_DIR, "deck_control.txt"),
}

st.sidebar.header("Card Database")
use_live_db = st.sidebar.checkbox(
    "Use the full official card database (live, ~2,700 cards)",
    value=False,
    help="Off = the small 20-card sample bundled with this app. "
         "On = fetches every real Lorcana card from LorcanaJSON.",
)


@st.cache_data(ttl=60 * 60 * 24, show_spinner="Downloading the full card database (first time only today)...")
def get_live_card_database():
    return ingestion.fetch_card_database_live()


if use_live_db:
    try:
        CARD_DB = get_live_card_database()
        st.sidebar.success(f"Loaded {len(CARD_DB)} real cards.")
    except Exception as e:
        st.sidebar.error(f"Couldn't fetch the live database: {e}")
        st.stop()
    st.info(
        "Live database is on. The two built-in sample decks were made up "
        "for testing and their card names won't match the real database, "
        "so please upload your own decklist file(s) below for both decks."
    )
else:
    CARD_DB = ingestion.load_local_card_database()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Deck A")
    if use_live_db:
        deck_a_choice = None
        uploaded_a = st.file_uploader("Upload decklist (.txt)", key="upload_a")
    else:
        deck_a_choice = st.selectbox("Choose deck A", list(BUILT_IN_DECKS.keys()), key="deck_a")
        uploaded_a = st.file_uploader("...or upload your own decklist (.txt)", key="upload_a")
    persona_a = st.selectbox("Deck A persona", ["Aggro", "Control"], key="persona_a")

with col2:
    st.subheader("Deck B")
    if use_live_db:
        deck_b_choice = None
        uploaded_b = st.file_uploader("Upload decklist (.txt)", key="upload_b")
    else:
        deck_b_choice = st.selectbox("Choose deck B", list(BUILT_IN_DECKS.keys()), index=1, key="deck_b")
        uploaded_b = st.file_uploader("...or upload your own decklist (.txt)", key="upload_b")
    persona_b = st.selectbox("Deck B persona", ["Aggro", "Control"], index=1, key="persona_b")

num_games = st.slider("Number of games to simulate", 100, 20000, 5000, step=100)


def load_deck(built_in_choice, uploaded_file):
    """Uses the uploaded file if the user provided one, otherwise falls
    back to whichever built-in sample deck they picked. In live-database
    mode there is no built-in fallback, so an upload is required."""
    if uploaded_file is not None:
        text = uploaded_file.getvalue().decode("utf-8")
        temp_path = os.path.join(DATA_DIR, "_uploaded_temp.txt")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
        return ingestion.load_decklist(temp_path, CARD_DB)
    if built_in_choice is None:
        raise ValueError("Please upload a decklist file - live database mode has no built-in decks.")
    return ingestion.load_decklist(BUILT_IN_DECKS[built_in_choice], CARD_DB)


if st.button("Run Simulation", type="primary"):
    try:
        deck_a = load_deck(deck_a_choice, uploaded_a)
        deck_b = load_deck(deck_b_choice, uploaded_b)
    except (KeyError, ValueError) as e:
        st.error(f"Problem reading a decklist: {e}")
        st.stop()

    with st.spinner(f"Simulating {num_games} games..."):
        df = run_monte_carlo(deck_a, persona_a, deck_b, persona_b, num_games=num_games)

    total = len(df)
    win_counts = df["winner"].value_counts()
    a_wins = win_counts.get("A", 0)
    b_wins = win_counts.get("B", 0)
    draws = win_counts.get("draw", 0)

    label_a = deck_a_choice or "Deck A (uploaded)"
    label_b = deck_b_choice or "Deck B (uploaded)"

    st.subheader("Results")
    r1, r2, r3 = st.columns(3)
    r1.metric(f"{label_a} (A)", f"{100 * a_wins / total:.1f}%", f"{a_wins} wins")
    r2.metric(f"{label_b} (B)", f"{100 * b_wins / total:.1f}%", f"{b_wins} wins")
    r3.metric("Draws", f"{100 * draws / total:.1f}%", f"{draws} games")

    turn_table = (
        df[df["winner"] != "draw"]
        .groupby(["turns", "winner"])
        .size()
        .unstack(fill_value=0)
    )
    fig = build_turn_distribution_figure(turn_table, f"{label_a} (A)", f"{label_b} (B)")
    st.pyplot(fig)

    with st.expander("Raw game-by-game data"):
        st.dataframe(df)
