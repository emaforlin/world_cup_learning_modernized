# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About

A machine learning project that predicts World Cup match outcomes using a Keras neural network trained on historical match data. Originally used to win a bet; modernized for use in talks and courses.

## Commands

```bash
# Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Launch the notebook
.venv/bin/jupyter notebook learn.ipynb

# Update raw CSV data from openfootball/world-cup on GitHub (idempotent — skips years already present)
.venv/bin/python fetch_openfootball.py
```

There is no test suite or linter configured.

## Architecture

The project has two layers:

**Data pipeline (`utils.py`)** — loads and transforms three CSV files into pandas DataFrames:
- `raw_matches.csv` — historical match results with `team1`, `team2`, `score1`, `score2`, `year`
- `raw_winners.csv` — podium placements per World Cup
- `team_renames.csv` — maps historical team name variants to canonical names

Key behaviors to understand:
- Ties are stripped from all training data (`score1 != score2`)
- `get_matches(duplicate_with_reversed=True)` doubles the dataset by swapping team1/team2 and flipping scores, so the model sees each matchup from both sides
- `get_team_stats()` computes per-team features: `matches_won_percent`, `podium_score_yearly` (exponential: `2 ** (5 - position)`), `cups_won_yearly`
- When joining stats onto a match row, team2's stats get a `_2` suffix (e.g. `matches_won_percent_2`)

**Model (`learn.ipynb`)** — a Keras `Sequential` network:
- Input features (5): `year`, `matches_won_percent`, `podium_score_yearly` (team1), `matches_won_percent_2`, `podium_score_yearly_2` (team2)
- Architecture: `Input(5) → Normalization → Dense(10, sigmoid) → Dense(10, sigmoid) → Dense(1, sigmoid)`
- Target: `winner` (True if team1 wins)
- Training: Adam + binary crossentropy, 80/20 split via `train_test_split`
- Normalization layer is adapted on training data only (`network.layers[0].adapt(train[input_cols].values)`)

To predict a hypothetical match, `build_inputs_for_match(year, team1, team2, input_cols)` in `utils.py` pulls team stats and assembles the input array. The notebook's `predict()` function wraps this and prints the raw sigmoid score plus predicted winner.
