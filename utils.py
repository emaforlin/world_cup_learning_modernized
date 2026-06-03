import numpy as np
import pandas as pd


RAW_MATCHES_FILE = 'raw_matches.csv'
RAW_WINNERS_FILE = 'raw_winners.csv'
TEAM_RENAMES_FILE = 'team_renames.csv'
RAW_INTERNATIONAL_FILE = 'raw_international.csv'

# Weight per 4-year World Cup cycle: older tournaments count less
RECENCY_DECAY = 0.8
# Number of recent matches used for recent_form and recent_avg_goal_diff
RECENT_FORM_MATCHES = 10

# Elo rating constants
DEFAULT_ELO = 1000
K_WORLD_CUP = 60
K_COMPETITIVE = 40
K_FRIENDLY = 20

# Host teams per World Cup year
HOSTS = {
    1930: {'Uruguay'},
    1934: {'Italy'},
    1938: {'France'},
    1950: {'Brazil'},
    1954: {'Switzerland'},
    1958: {'Sweden'},
    1962: {'Chile'},
    1966: {'England'},
    1970: {'Mexico'},
    1974: {'Germany'},
    1978: {'Argentina'},
    1982: {'Spain'},
    1986: {'Mexico'},
    1990: {'Italy'},
    1994: {'United States'},
    1998: {'France'},
    2002: {'South Korea', 'Japan'},
    2006: {'Germany'},
    2010: {'South Africa'},
    2014: {'Brazil'},
    2018: {'Russia'},
    2022: {'Qatar'},
    2026: {'United States', 'Canada', 'Mexico'},
}


def apply_renames(column):
    with open(TEAM_RENAMES_FILE) as renames_file:
        renames = dict(l.strip().split(',')
                       for l in renames_file.readlines()
                       if l.strip())

        def renamer(team):
            return renames.get(team, team)

    return column.map(renamer)


def get_matches(with_team_stats=False, duplicate_with_reversed=False):
    """Create a dataframe with World Cup matches."""
    matches = pd.read_csv(RAW_MATCHES_FILE)
    for column in ('team1', 'team2'):
        matches[column] = apply_renames(matches[column])

    if duplicate_with_reversed:
        id_offset = len(matches)
        matches2 = matches.copy()
        matches2.rename(columns={'team1': 'team2', 'team2': 'team1',
                                 'score1': 'score2', 'score2': 'score1'},
                        inplace=True)
        matches2.index = matches2.index.map(lambda x: x + id_offset)
        matches = pd.concat((matches, matches2))

    matches = matches[matches.score1 != matches.score2]  # remove ties
    matches['winner'] = matches.score1 > matches.score2

    # Compute host feature after duplication so team1/team2 are correctly assigned
    matches['is_host'] = matches.apply(
        lambda r: 1.0 if r['team1'] in HOSTS.get(r['year'], set()) else 0.0, axis=1)
    matches['is_host_2'] = matches.apply(
        lambda r: 1.0 if r['team2'] in HOSTS.get(r['year'], set()) else 0.0, axis=1)

    if with_team_stats:
        stats = get_team_stats()
        matches = matches.join(stats, on='team1') \
                         .join(stats, on='team2', rsuffix='_2')

    return matches


def get_winners():
    """Create a dataframe with podium positions info."""
    winners = pd.read_csv(RAW_WINNERS_FILE)
    winners.team = apply_renames(winners.team)
    return winners


def get_international_matches():
    """Load full international match history for Elo and recent form.
    Returns None if raw_international.csv is not present (run fetch_international.py first).
    """
    try:
        df = pd.read_csv(RAW_INTERNATIONAL_FILE, parse_dates=['date'])
        df['home_team'] = apply_renames(df['home_team'])
        df['away_team'] = apply_renames(df['away_team'])
        return df
    except FileNotFoundError:
        return None


def compute_elo_ratings(intl):
    """Compute current Elo ratings for all teams from the full international match history."""
    ratings = {}

    for row in intl.sort_values('date').itertuples(index=False):
        home, away = row.home_team, row.away_team

        r_h = ratings.get(home, DEFAULT_ELO)
        r_a = ratings.get(away, DEFAULT_ELO)

        expected_home = 1 / (1 + 10 ** ((r_a - r_h) / 400))

        if row.home_score > row.away_score:
            result_home = 1.0
        elif row.home_score < row.away_score:
            result_home = 0.0
        else:
            result_home = 0.5

        tournament = str(row.tournament).lower()
        if 'world cup' in tournament and 'qualif' not in tournament:
            K = K_WORLD_CUP
        elif 'friendly' in tournament:
            K = K_FRIENDLY
        else:
            K = K_COMPETITIVE

        ratings[home] = r_h + K * (result_home - expected_home)
        ratings[away] = r_a + K * ((1 - result_home) - (1 - expected_home))

    return ratings


def get_team_stats():
    """Create a dataframe with useful stats for each team."""
    winners = get_winners()
    matches = get_matches()
    intl = get_international_matches()

    max_year = matches.year.max()

    def recency_weight(year):
        return RECENCY_DECAY ** ((max_year - year) / 4)

    elo_ratings = compute_elo_ratings(intl) if intl is not None else {}

    teams = set(matches.team1.unique()).union(matches.team2.unique())
    stats = pd.DataFrame(list(teams), columns=['team'])
    stats = stats.set_index('team')

    for team in teams:
        team_wc = matches[(matches.team1 == team) | (matches.team2 == team)]

        # Recency-weighted historical WC stats
        weights = team_wc.year.map(recency_weight)
        stats.loc[team, 'matches_played'] = weights.sum()

        wins1 = team_wc[(team_wc.team1 == team) & (team_wc.score1 > team_wc.score2)]
        wins2 = team_wc[(team_wc.team2 == team) & (team_wc.score2 > team_wc.score1)]
        all_wins = pd.concat([wins1, wins2])
        stats.loc[team, 'matches_won'] = all_wins['year'].map(recency_weight).sum()

        stats.loc[team, 'years_played'] = len(team_wc.year.unique())

        team_podiums = winners[winners.team == team]
        to_score = lambda pos: 2 ** (5 - pos)
        stats.loc[team, 'podium_score'] = sum(
            to_score(row.position) * recency_weight(row.year)
            for row in team_podiums.itertuples()
        )
        stats.loc[team, 'cups_won'] = len(team_podiums[team_podiums.position == 1])

        # Recent form and goal difference from international matches (preferred)
        # Falls back to WC-only matches if raw_international.csv is missing
        if intl is not None:
            team_intl = intl[(intl.home_team == team) | (intl.away_team == team)]
            recent = team_intl.sort_values('date').tail(RECENT_FORM_MATCHES)
        else:
            recent = None

        if recent is not None and len(recent) > 0:
            won = ((recent.home_team == team) & (recent.home_score > recent.away_score)) | \
                  ((recent.away_team == team) & (recent.away_score > recent.home_score))
            stats.loc[team, 'recent_form'] = won.sum() / len(recent)

            goal_diff = recent.apply(
                lambda r: (r.home_score - r.away_score) if r.home_team == team
                          else (r.away_score - r.home_score),
                axis=1)
            stats.loc[team, 'recent_avg_goal_diff'] = goal_diff.mean()
        else:
            recent_wc = team_wc.sort_values('year').tail(RECENT_FORM_MATCHES)
            w1 = recent_wc[(recent_wc.team1 == team) & (recent_wc.score1 > recent_wc.score2)]
            w2 = recent_wc[(recent_wc.team2 == team) & (recent_wc.score2 > recent_wc.score1)]
            stats.loc[team, 'recent_form'] = (len(w1) + len(w2)) / len(recent_wc)

            gd = recent_wc.apply(
                lambda r: (r.score1 - r.score2) if r.team1 == team
                          else (r.score2 - r.score1),
                axis=1)
            stats.loc[team, 'recent_avg_goal_diff'] = gd.mean()

        stats.loc[team, 'elo_rating'] = elo_ratings.get(team, DEFAULT_ELO)

    stats['matches_won_percent'] = stats.matches_won / stats.matches_played
    stats['podium_score_yearly'] = stats.podium_score / stats.years_played
    stats['cups_won_yearly'] = stats.cups_won / stats.years_played

    return stats


def build_inputs_for_match(year, team1, team2, input_features):
    """Build the inputs for a single hypothetical match, real or not."""
    inputs = []
    team_stats = get_team_stats()

    for feature in input_features:
        from_team_2 = feature.endswith('_2')
        base = feature[:-2] if from_team_2 else feature
        team = team2 if from_team_2 else team1

        if base == 'year':
            value = year
        elif base == 'is_host':
            value = 1.0 if team in HOSTS.get(year, set()) else 0.0
        elif base in team_stats.columns:
            value = team_stats.loc[team, base]
        else:
            raise ValueError("Don't know where to get feature: " + feature)

        inputs.append(value)

    return np.array([inputs])
