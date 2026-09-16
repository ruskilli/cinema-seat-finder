"""Zone and adjacency matching over ebillett.no (eBillett/DX) seatmap data.

Input seat shape (built by ebillett_checkout.py's seats_from_seatmap(),
decoding the compact colon/comma-separated `seatplan` encoding):
{"row": int, "column": int, "state": "available"|"booked", "type": str,
...other fields ignored}. `type` is always "" here - ebillett.no's seat
state codes don't cleanly separate "special category" from "availability"
the way Filmgrail's/ODEON's do (see ebillett_checkout.py's module
docstring), so there is no meaningful majority-type split to make; every
seat is treated as the same type and only `state` matters.

Logic (zone bucketing, contiguous-run search) is otherwise identical to
filmgrail_zone_match.py/odeon_zone_match.py - kept as its own module rather
than shared so each chain's matcher can diverge independently if any one
vendor's seat shape changes later.
"""
import argparse
import json
import sys


def standard_seats(seats):
    """ebillett.no's decoded seats have no distinct "type" field (always
    ""), so every seat is standard - no special-category exclusion to make
    here, unlike Filmgrail/ODEON."""
    return list(seats)


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
        description='Find N contiguous available seats in a zone from extracted ebillett.no seatmap JSON (read from stdin)')
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--zone-row', choices=['front', 'middle', 'back'], default=None)
    parser.add_argument('--zone-col', choices=['left', 'center', 'right'], default=None)
    args = parser.parse_args()
    seats = json.load(sys.stdin)
    result = find_match(seats, args.count, zone_row=args.zone_row, zone_col=args.zone_col)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
