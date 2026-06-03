"""
Fetch World Cup match and podium data from openfootball/world-cup on GitHub
and append new years to raw_matches.csv and raw_winners.csv.
"""
import csv
import re
import sys
import urllib.request

BASE_URL = 'https://raw.githubusercontent.com/openfootball/world-cup/master'

YEARS = {
    2018: '2018--russia',
    2022: '2022--qatar',
}

# Maps section headers in cup_finals.txt to what they mean
THIRD_PLACE_HEADER = 'match for third place'
FINAL_HEADER = 'final'


def fetch(path):
    url = f'{BASE_URL}/{path}'
    with urllib.request.urlopen(url) as r:
        return r.read().decode('utf-8')


def parse_match_line(line):
    """
    Parse a line like:
      18:00 UTC+3   Russia   5-0 (2-0)   Saudi Arabia   @ venue
      18:00   Japan   1-1 a.e.t (1-1, 1-0), 1-3 pen.   Croatia   @ venue
      Netherlands 2-0 (1-0)  Qatar   @ venue   (simultaneous match, no time prefix)

    Returns (team1, score1, score2, team2) using regulation/AET scores only
    (penalty results are ignored — those games are stored as draws).
    Returns None if the line is not a match result line.
    """
    # All match lines are indented, have a score, and have a venue marker
    if not re.match(r'^\s', line):
        return None
    if not re.search(r'\d+-\d+', line) or '@' not in line:
        return None
    # Goalscorer continuation lines start with '(' after whitespace
    if re.match(r'^\s+\(', line):
        return None

    has_time = bool(re.match(r'^\s+\d{1,2}:\d{2}', line))

    if has_time:
        # Strip time and optional timezone from front
        rest = re.sub(r'^\s+\d{1,2}:\d{2}(?:\s+UTC[+-]\d+)?\s+', '', line)
    else:
        rest = line.strip()
        # Must start with a letter (team name) — filters out stray lines
        if not rest or not rest[0].isalpha():
            return None

    # Find the first X-Y score (the main score, not penalty or halftime)
    score_match = re.search(r'(\d+)-(\d+)', rest)
    if not score_match:
        return None

    team1 = rest[:score_match.start()].strip()
    score1 = int(score_match.group(1))
    score2 = int(score_match.group(2))

    after = rest[score_match.end():]
    if '@' in after:
        after = after[:after.index('@')]

    # Strip penalty shootout result first (it contains X-Y which would confuse cleanup)
    after = re.sub(r',?\s*\d+-\d+\s*pen\.?', '', after, flags=re.IGNORECASE)
    # Strip parenthesized halftime/fulltime scores
    after = re.sub(r'\([^)]*\)', '', after)
    # Strip a.e.t. marker
    after = re.sub(r'a\.?e\.?t\.?', '', after, flags=re.IGNORECASE)
    team2 = after.strip().strip(',').strip()

    if not team1 or not team2:
        return None

    return team1, score1, score2, team2


def parse_penalty_winner(line):
    """
    Return which team won on penalties: 1 if team1, 2 if team2.
    Returns None if no penalty shootout in line.
    """
    pen_match = re.search(r',\s*(\d+)-(\d+)\s*pen\.?', line, flags=re.IGNORECASE)
    if not pen_match:
        return None
    p1, p2 = int(pen_match.group(1)), int(pen_match.group(2))
    return 1 if p1 > p2 else 2


def parse_matches(text, year):
    """Parse all match lines from a cup.txt or cup_finals.txt text."""
    rows = []
    for line in text.splitlines():
        result = parse_match_line(line)
        if result:
            team1, score1, score2, team2 = result
            rows.append({'year': year, 'team1': team1, 'score1': score1,
                         'score2': score2, 'team2': team2})
    return rows


def parse_podium(finals_text, year):
    """
    Extract podium positions from cup_finals.txt.
    Returns list of {'year', 'position', 'team'} dicts.
    """
    current_section = None
    third_match = None
    final_match = None

    for line in finals_text.splitlines():
        # Detect section headers like "▪ Final" or "▪ Match for third place"
        header_match = re.match(r'[▪•]\s+(.+)', line.strip())
        if header_match:
            header = header_match.group(1).lower().strip()
            if FINAL_HEADER in header and 'round' not in header and 'semi' not in header:
                current_section = 'final'
            elif THIRD_PLACE_HEADER in header:
                current_section = 'third'
            else:
                current_section = None
            continue

        if current_section not in ('final', 'third'):
            continue

        result = parse_match_line(line)
        if not result:
            continue

        team1, score1, score2, team2 = result

        if current_section == 'third':
            third_match = (team1, score1, score2, team2, line)
        elif current_section == 'final':
            final_match = (team1, score1, score2, team2, line)

    podium = []

    if final_match:
        team1, score1, score2, team2, raw_line = final_match
        pen_winner = parse_penalty_winner(raw_line)
        if pen_winner == 1 or (pen_winner is None and score1 > score2):
            podium += [{'year': year, 'position': 1, 'team': team1},
                       {'year': year, 'position': 2, 'team': team2}]
        else:
            podium += [{'year': year, 'position': 1, 'team': team2},
                       {'year': year, 'position': 2, 'team': team1}]

    if third_match:
        team1, score1, score2, team2, raw_line = third_match
        pen_winner = parse_penalty_winner(raw_line)
        if pen_winner == 1 or (pen_winner is None and score1 > score2):
            podium += [{'year': year, 'position': 3, 'team': team1},
                       {'year': year, 'position': 4, 'team': team2}]
        else:
            podium += [{'year': year, 'position': 3, 'team': team2},
                       {'year': year, 'position': 4, 'team': team1}]

    return podium


def load_existing_years(path, year_col='year'):
    years = set()
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                years.add(int(row[year_col]))
    except FileNotFoundError:
        pass
    return years


def append_matches(matches, matches_file='raw_matches.csv'):
    # Determine next id
    last_id = -1
    try:
        with open(matches_file) as f:
            for row in csv.DictReader(f):
                last_id = max(last_id, int(row['id']))
    except FileNotFoundError:
        pass

    with open(matches_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'year', 'team1', 'score1', 'score2', 'team2'])
        for match in matches:
            last_id += 1
            writer.writerow({'id': last_id, **match})

    print(f"  Appended {len(matches)} matches to {matches_file}")


def append_winners(podium, winners_file='raw_winners.csv'):
    with open(winners_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['year', 'position', 'team'])
        for row in podium:
            writer.writerow(row)

    print(f"  Appended {len(podium)} podium entries to {winners_file}")


def main():
    existing_match_years = load_existing_years('raw_matches.csv')
    existing_winner_years = load_existing_years('raw_winners.csv')

    for year, folder in sorted(YEARS.items()):
        print(f"\n=== {year} ===")

        if year not in existing_match_years:
            print(f"  Fetching match data...")
            group_text = fetch(f'{folder}/cup.txt')
            finals_text = fetch(f'{folder}/cup_finals.txt')
            matches = parse_matches(group_text, year) + parse_matches(finals_text, year)
            print(f"  Parsed {len(matches)} matches")
            append_matches(matches)
        else:
            print(f"  Matches already present, skipping.")

        if year not in existing_winner_years:
            print(f"  Fetching podium data...")
            finals_text = fetch(f'{folder}/cup_finals.txt')
            podium = parse_podium(finals_text, year)
            for p in podium:
                print(f"    Position {p['position']}: {p['team']}")
            append_winners(podium)
        else:
            print(f"  Podium already present, skipping.")

    print("\nDone.")


if __name__ == '__main__':
    main()
