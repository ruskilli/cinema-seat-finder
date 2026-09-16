"""Read-only seat-availability client for ODEON Kino, via the public Cinema
API backend (services.cinema-api.com) their own booking pages call - not
Filmweb, not Filmgrail/Mars.

Reverse-engineered 2026-09-16 by watching www.odeonkino.no/booking/kjop/<id>
load in a real browser and reading performance.getEntriesByType('resource')
for cross-origin calls (the network-requests tool missed some on repeat
loads, apparently due to browser caching - the Performance API doesn't).
Every endpoint used here was then independently confirmed reachable via a
plain, unauthenticated `curl` with no special headers, no cookies, and no
challenge response - the same bar as discover_shows.py's Filmweb calls and
filmgrail_checkout.py's guest checkout calls (see README's "Only public
APIs" note). www.odeonkino.no itself is a different story: every page on
that domain returns HTTP 403 with a Cloudflare `cf-mitigated: challenge`
header to a plain client, and this module deliberately never talks to it -
the showtime UUID is parsed directly out of the `ticketSaleUrl` path
instead of fetching that page.

Endpoints:

  GET /show/Sys99-NO/<showId>/no
    -> {..., "auditoriumLayoutId": "<id>", "cinema": {...}, "screen": {...}}
       Movie/showtime/cinema metadata. "Sys99-NO" is Cinema API's tenant
       alias for ODEON Norway specifically (other chains on this platform,
       if any, would use a different alias) - hardcoded here since this
       module is ODEON-specific by design, same as filmgrail_checkout.py
       hardcodes nothing chain-specific but this one legitimately can't
       avoid it (there is no per-cinema domain to derive it from, unlike
       Filmgrail's base_url()).

  GET /screen/layout/no/<auditoriumLayoutId>
    -> {..., "seats": [{"remoteEntityId": "<id>", "row": int,
        "number": int, "seatType": "REGULAR"|"HCP"|..., ...}, ...]}
       The auditorium's static physical layout - one record per seat,
       every visit to this screen reuses the same layout. "number" is the
       seat's position within its row (an int, like Trondheim Kino's
       "column" - NOT the pixel coordinates Bergen kino uses; see
       filmgrail_checkout.py's docstring for that contrast).

  GET /show/ticketstatus/Sys99-NO/<showId>/
    -> [{"remoteEntityId": "<id>", "status": "Free"|"Locked"|"Sold"}, ...]
       Live per-seat status for this specific showtime, keyed by the same
       remoteEntityId as the layout. Confirmed live 2026-09-16 against a
       showtime with real sales: statuses seen were "Free", "Locked"
       (someone else mid-checkout) and "Sold" - build_seatmap() treats
       anything other than "Free" as unavailable, including any future
       status value not seen yet, rather than assuming availability.

No transaction, hold, or reservation is ever created by any of the above -
they're all plain GETs, confirmed by test_odeon_checkout.py asserting every
captured request has no body. This is a meaningful difference from
filmgrail_checkout.py's check_seats(), which must open (and always cancels)
a real transaction to see the seatmap at all - ODEON's ticketstatus is
queryable directly with no side effect.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

BASE = "https://services.cinema-api.com"
REMOTE_SYSTEM_ALIAS = "Sys99-NO"


def extract_show_id(ticket_sale_url):
    """Pull the showtime UUID out of an ODEON ticketSaleUrl, e.g.
    'https://www.odeonkino.no/booking/kjop/<uuid>' -> '<uuid>'. Never
    fetches the URL itself - www.odeonkino.no is Cloudflare-challenged."""
    path = urllib.parse.urlsplit(ticket_sale_url).path
    return path.rstrip('/').rsplit('/', 1)[-1]


def _get_json(url, opener):
    # cinema-api.com rejects the bare Python-urllib default User-Agent
    # string (confirmed live 2026-09-16: identical request succeeds with
    # curl's own UA, fails with none/Python's) - same as
    # filmgrail_checkout.py's get_tickets_categories_data, a normal
    # non-default UA is all that's needed, nothing evasive.
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    open_fn = opener or urllib.request.urlopen
    with open_fn(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get_show(show_id, opener=None):
    return _get_json(f"{BASE}/show/{REMOTE_SYSTEM_ALIAS}/{show_id}/no", opener)


def get_screen_layout(auditorium_layout_id, opener=None):
    return _get_json(f"{BASE}/screen/layout/no/{auditorium_layout_id}", opener)


def get_ticket_status(show_id, opener=None):
    return _get_json(f"{BASE}/show/ticketstatus/{REMOTE_SYSTEM_ALIAS}/{show_id}/", opener)


def build_seatmap(layout_seats, ticket_statuses):
    """Join the static layout's seats with the live per-seat status,
    matched by remoteEntityId, into filmgrail-checkout-shaped records
    (row/column ints, state, type, rowSymbol/columnSymbol) that
    odeon_zone_match.py can consume directly."""
    status_by_id = {s['remoteEntityId']: s['status'] for s in ticket_statuses}
    seats = []
    for seat in layout_seats:
        status = status_by_id.get(seat['remoteEntityId'])
        seats.append({
            'row': seat['row'],
            'column': seat['number'],
            'state': 'available' if status == 'Free' else 'booked',
            'type': seat.get('seatType', ''),
            'rowSymbol': str(seat['row']),
            'columnSymbol': str(seat['number']),
        })
    return seats


def check_seats(ticket_sale_url, opener=None):
    """Runs show -> screen layout -> ticket status -> join for one ODEON
    showtime. Purely read-only - see module docstring.

    Returns a dict:
      status: 'ok' or 'error'
      seats: combined seat list (see build_seatmap), only when status is 'ok'
      error: message, only when status is 'error'
    """
    show_id = extract_show_id(ticket_sale_url)
    result = {'status': None, 'seats': None, 'error': None}
    try:
        show = get_show(show_id, opener=opener)
        layout = get_screen_layout(show['auditoriumLayoutId'], opener=opener)
        ticket_statuses = get_ticket_status(show_id, opener=opener)
        result['seats'] = build_seatmap(layout['seats'], ticket_statuses)
        result['status'] = 'ok'
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Check seat availability for one ODEON showtime via the public '
                    'Cinema API (services.cinema-api.com) directly - read-only, '
                    'no transaction/hold is ever opened')
    parser.add_argument('ticket_sale_url')
    args = parser.parse_args()
    result = check_seats(args.ticket_sale_url)
    print(json.dumps(result))
    if result['status'] != 'ok':
        sys.exit(1)


if __name__ == '__main__':
    main()
