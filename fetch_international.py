"""
Download full international football match history from martj42/international_results
and save as raw_international.csv. Used by utils.py for Elo ratings and recent form.
"""
import urllib.request

URL = 'https://raw.githubusercontent.com/martj42/international_results/master/results.csv'
DEST = 'raw_international.csv'


def main():
    print(f"Downloading international match history from:\n  {URL}")
    urllib.request.urlretrieve(URL, DEST)

    # Quick sanity check
    with open(DEST) as f:
        lines = f.readlines()
    print(f"Saved {len(lines) - 1} matches to {DEST}")


if __name__ == '__main__':
    main()
