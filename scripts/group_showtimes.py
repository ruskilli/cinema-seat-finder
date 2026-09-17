"""Group discover_shows.py's flat show list by movie, for listing requests.

A nationwide listing with no `--movie-title` filter can return hundreds
of flat show records. Grouping and sorting that many records by hand
(mentally, in Claude's own reasoning) is exactly the kind of deterministic
data-shuffling a script should do instead - this hoists the repeated
`movieTitle` key out of each showtime record (grouped once per film
instead of repeated per showing) and does the sorting up front, so Claude
only has to read an already-grouped, already-sorted structure and phrase
the final answer.
"""
import argparse
import json
import sys


def group_showtimes(shows):
    """Group `shows` (discover_shows.py's output shape) by `movieTitle`.
    Returns a list of {"movieTitle": str, "showtimes": [...]}, sorted
    alphabetically by `movieTitle`; each group's showtimes sorted by
    `showStart` ascending. Each showtime entry is the original show dict
    minus its now-redundant `movieTitle` key."""
    groups = {}
    for show in shows:
        groups.setdefault(show["movieTitle"], []).append(show)

    result = []
    for movie_title in sorted(groups):
        showtimes = sorted(groups[movie_title], key=lambda s: s["showStart"])
        result.append({
            "movieTitle": movie_title,
            "showtimes": [{k: v for k, v in s.items() if k != "movieTitle"} for s in showtimes],
        })
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Group discover_shows.py's flat show list by movie, sorted by title and start time (reads a JSON array from stdin)")
    parser.parse_args()
    shows = json.load(sys.stdin)
    print(json.dumps(group_showtimes(shows)))


if __name__ == "__main__":
    main()
