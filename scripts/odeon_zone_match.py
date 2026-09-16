"""Zone and adjacency matching over ODEON (Cinema API) seatmap data.

Input seat shape (built by odeon_checkout.py by joining screen/layout's
static seats with show/ticketstatus's live per-seat status):
{"row": int, "column": int, "state": "available"|"booked", "type": str,
...other fields ignored}. Seats whose type differs from the room's majority
type (e.g. "HCP" wheelchair spots) are excluded - they're a different
ticket category than the standard seats being searched for. The exact
string used for the standard category varies by room (typically "REGULAR"
here, vs. "" for Filmgrail rooms), so the majority value is used rather
than a hardcoded string.

Logic is identical to filmgrail_zone_match.py - ODEON's row/column grid
shape happens to match Filmgrail's exactly, confirmed live 2026-09-16, even
though the two vendors are unrelated. Kept as a separate module rather than
shared so each chain's matcher can diverge independently if one vendor's
seat shape changes later (see filmgrail_zone_match.py's docstring for the
contrast with Bergen kino, which is on the Filmgrail platform but uses a
different, incompatible pixel-coordinate shape).
"""
import argparse
import json
import sys


def standard_seats(seats):
    """Standard (bookable) seats are those with the room's most common
    `type` value. Special categories (wheelchair, etc.) are always a
    minority within a room, and the exact type string used for standard
    seats varies by room - so the majority value, not a hardcoded string,
    is the robust signal."""
    if not seats:
        return []
    type_counts = {}
    for s in seats:
        t = s.get('type', '')
        type_counts[t] = type_counts.get(t, 0) + 1
    majority_type = max(type_counts, key=type_counts.get)
    return [s for s in seats if s.get('type', '') == majority_type]


def zone_bounds(seats):
    rows = [s['row'] for s in seats]
    cols = [s['column'] for s in seats]
    min_row, max_row = min(rows), max(rows)
    min_col, max_col = min(cols), max(cols)
    return {
        'min_row': min_row, 'max_row': max_row, 'row_third': (max_row - min_row + 1) / 3.0,
        'min_col': min_col, 'max_col': max_col, 'col_third': (max_col - min_col + 1) / 3.0,
    }


def row_zone(row, bounds):
    if bounds['row_third'] == 0:
        return 'middle'
    if row < bounds['min_row'] + bounds['row_third']:
        return 'front'
    if row >= bounds['max_row'] + 1 - bounds['row_third']:
        return 'back'
    return 'middle'


def col_zone(col, bounds):
    if bounds['col_third'] == 0:
        return 'center'
    if col < bounds['min_col'] + bounds['col_third']:
        return 'left'
    if col >= bounds['max_col'] + 1 - bounds['col_third']:
        return 'right'
    return 'center'


def find_contiguous_run(row_seats, n):
    """row_seats: seats in one row, any order. Returns a list of n seats with
    consecutive column values, all available, or None if no such run exists."""
    if n <= 0:
        return None
    sorted_row = sorted(row_seats, key=lambda s: s['column'])
    run = []
    for seat in sorted_row:
        if seat['state'] != 'available':
            run = []
            continue
        if run and seat['column'] - run[-1]['column'] != 1:
            run = []
        run.append(seat)
        if len(run) >= n:
            return run[-n:]
    return None


def find_match(seats, n, zone_row=None, zone_col=None):
    """Find rows within the requested zone containing n contiguous available seats."""
    candidates = standard_seats(seats)
    if not candidates:
        return {'matched': False, 'matches': []}
    bounds = zone_bounds(candidates)
    rows = sorted(set(s['row'] for s in candidates))
    matches = []
    for row in rows:
        if zone_row and row_zone(row, bounds) != zone_row:
            continue
        row_seats = [s for s in candidates if s['row'] == row]
        if zone_col:
            row_seats = [s for s in row_seats if col_zone(s['column'], bounds) == zone_col]
        run = find_contiguous_run(row_seats, n)
        if run:
            matches.append({'row': row, 'rowSymbol': run[0].get('rowSymbol'), 'seats': run})
    return {'matched': len(matches) > 0, 'matches': matches}


def main():
    parser = argparse.ArgumentParser(
        description='Find N contiguous available seats in a zone from extracted ODEON seatmap JSON (read from stdin)')
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--zone-row', choices=['front', 'middle', 'back'], default=None)
    parser.add_argument('--zone-col', choices=['left', 'center', 'right'], default=None)
    args = parser.parse_args()
    seats = json.load(sys.stdin)
    result = find_match(seats, args.count, zone_row=args.zone_row, zone_col=args.zone_col)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
