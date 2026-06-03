# World Cup Learning

ML model that predicts World Cup match outcomes and scores. Built on historical World Cup data (1950–2022) plus full international match history for Elo ratings and recent form.

Originally by [fisadev](https://github.com/fisadev/world_cup_learning) — modernized and extended for the 2026 World Cup.

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Download international match history (for Elo ratings and recent form)
.venv/bin/python fetch_international.py
```

## After each matchday

The openfootball repo is updated with results within a day or two of each match. Run these steps to pull in new results and retrain:

**1. Fetch new World Cup results**
```bash
.venv/bin/python fetch_openfootball.py
```
This is idempotent — it skips years already present, so it's safe to run anytime. If the 2026 data isn't in the openfootball repo yet, it will simply skip without making changes.

**2. Refresh international match history** (optional but recommended weekly)
```bash
.venv/bin/python fetch_international.py
```
Updates `raw_international.csv` with the latest results, improving the Elo ratings and recent form features.

**3. Retrain the model**

Open `learn.ipynb`, restart the kernel, and run all cells. The two trained models are:
- `network` — predicts the winner (binary classifier)
- `goals_network` — predicts the exact score (regression)

## Making predictions

```python
# Winner only (+1 point if correct)
predict(2026, 'Brazil', 'Argentina')

# Exact score (+2 points if exact, +1 if just winner is correct)
predict_score(2026, 'Brazil', 'Argentina')
```

Team names must match the dataset. When in doubt, check `raw_matches.csv` for the canonical name.

## Data sources

| File | Source | Update frequency |
|------|--------|-----------------|
| `raw_matches.csv` | openfootball/world-cup (via `fetch_openfootball.py`) | After each matchday |
| `raw_winners.csv` | openfootball/world-cup (via `fetch_openfootball.py`) | After the Final |
| `raw_international.csv` | martj42/international_results (via `fetch_international.py`) | Weekly |
