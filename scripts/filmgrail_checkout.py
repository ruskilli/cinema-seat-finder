"""Direct HTTP client for the Filmgrail/Mars checkout flow used by several
Norwegian cinema chains on the same platform (confirmed working against both
Trondheim Kino and Bergen kino - see README) - no browser required.

Reverse-engineered 2026-09-16: opening a
`ticketSaleUrl` embeds the TicketsCategories block's server-rendered state as
a URL-encoded JSON blob, in a `<script>` tag shaped like
`const data = JSON.parse(decodeURIComponent("..."))`, one such blob per block
on the page (`_blockName` distinguishes them). Selecting N "Voksen" tickets
and clicking "Neste" is, underneath the Vue component, just:

  POST /api/ExecuteApiMethod?blockName=TicketsCategories&methodName=setTickets
  body: {"blockData": <the embedded TicketsCategories state>,
         "methodData": [[<Voksen ticket dict>] * N, []]}
  -> {"transactionId": "<uuid>", "nextStep": "/checkout/seatmap/<uuid>"}

  POST /checkout/seatmap/<transactionId>
  body: {"isModal": true, "modalId": 1}
  -> {"master": ..., "pageTitle": ..., "html": <same URL-encoded
      seats.seatmap array the browser flow parsed - see filmgrail_zone_match.py's
      module docstring for the seat record shape>}

  POST /api/ExecuteApiMethod?blockName=TicketsCategories&methodName=cancel
  body: {"blockData": <same state>, "methodData": [transactionId]}
  -> {"result": true}

No login, cookie, or CSRF token is required for this guest flow - the
'Token' and 'SubAppId' headers are sent empty, matching what an anonymous
browser session sends (see `window.getHeaders()` in /assets/js/mars.js).
Verified live 2026-09-16 against 7 real Trondheim Kino showtimes end to end,
including confirmed clean `cancel` on every run.

Each cinema's own site is the API host (`www.trondheimkino.no`,
`www.bergenkino.no`, ...) - `base_url()` derives it from the showtime's own
`ticketSaleUrl` rather than hardcoding one cinema. Ticket category ids/titles
are also cinema-specific (e.g. Trondheim's adult category is `VKS||`
"voksen", Bergen's is `115608` "Ordinære billetter") - `pick_standard_ticket()`
picks it by position (first enabled category) rather than by id, since that
held true on both cinemas checked. This setTickets -> seatmap -> cancel
*API* cycle itself is confirmed working live against Bergen kino too (right
host, right ticket category, clean cancel).

However, the *seat record shape* Bergen's seatmap embeds is NOT the same as
Trondheim's: every Bergen room sampled 2026-09-16 used pixel coordinates
(`coordX`/`coordY`, `row` as a string, no `column` field at all) instead of
Trondheim's integer grid (`row`/`column` as ints - see filmgrail_zone_match.py's
module docstring). `reduce_seats` below assumes the Trondheim grid shape and
raises `KeyError` on the pixel-coordinate shape - `check_seats` catches this
and reports it as a normal `status: 'error'` (transaction still cancelled
cleanly), so a Bergen showtime currently comes back as "couldn't check
seats" rather than a real zone match. Supporting Bergen's seatmap fully
would mean teaching filmgrail_zone_match.py to bucket/adjacency-match on pixel
coordinates too - not yet done.

Not every Norwegian cinema is on this platform at all - `nfkino.no`,
`aurorakino.no`, `odeonkino.no`, and `ebillett.no` are known to use
different vendors and are NOT supported by this client (calling
`get_tickets_categories_data` against one raises `RuntimeError` since no
`TicketsCategories` block will be found).
"""
import argparse
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request

API_HEADERS = {
    'Token': '',
    'SubAppId': '',
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept': 'application/json',
}


def base_url(ticket_sale_url):
    """The scheme+host a showtime's own site serves its checkout API from,
    e.g. 'https://www.bergenkino.no' for a bergenkino.no showtime URL."""
    parsed = urllib.parse.urlsplit(ticket_sale_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def pick_standard_ticket(tickets):
    """The standard/adult ticket category, cinema-agnostic: ticket ids and
    titles differ per cinema (see module docstring), but the standard
    category has been the first enabled one on every cinema checked so far."""
    for ticket in tickets:
        if not ticket.get('disabled', False):
            return ticket
    raise RuntimeError('no enabled ticket category found')


def new_session_opener():
    """A cookie-aware `opener(req, timeout=15)` callable. Use one instance
    per showtime being checked - the checkout flow doesn't strictly appear
    to need cookies (no session cookie is set beyond a generic `location`
    one, and transaction state is addressed by the transactionId in the URL
    path, not a session), but carrying them is free and matches what a real
    browser session would do."""
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)).open


def get_tickets_categories_data(ticket_sale_url, opener=urllib.request.urlopen):
    """Fetch the showtime page and pull out the embedded TicketsCategories
    block state (ticket categories/prices, showId, etc.)."""
    req = urllib.request.Request(ticket_sale_url, headers={'User-Agent': 'Mozilla/5.0'})
    with opener(req, timeout=15) as resp:
        html = resp.read().decode('utf-8')
    for encoded in re.findall(r'const data = JSON\.parse\(decodeURIComponent\("(.*?)"\)\)', html):
        data = json.loads(urllib.parse.unquote(encoded))
        if data.get('_blockName') == 'TicketsCategories':
            return data
    raise RuntimeError('TicketsCategories block state not found on showtime page')


def _post_api_method(base, method_name, block_data, method_data, opener):
    url = f"{base}/api/ExecuteApiMethod?blockName=TicketsCategories&methodName={method_name}"
    body = json.dumps({"blockData": block_data, "methodData": method_data}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=API_HEADERS, method='POST')
    with opener(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def set_tickets(base, block_data, count, opener, ticket_id=None):
    """Selects `count` tickets of `ticket_id`, or the venue's standard/adult
    category (see pick_standard_ticket) when `ticket_id` is omitted. Returns
    the parsed response, which on success has a `transactionId`."""
    if ticket_id is None:
        ticket = pick_standard_ticket(block_data['tickets'])
    else:
        ticket = next((t for t in block_data['tickets'] if t['id'] == ticket_id), None)
        if ticket is None:
            raise RuntimeError(f"ticket category {ticket_id!r} not offered for this showtime")
    return _post_api_method(base, 'setTickets', block_data, [[ticket] * count, []], opener)


def cancel(base, block_data, transaction_id, opener):
    """Abandons the transaction, releasing whatever hold it placed. Always
    call this once a transaction has been created, even after an error -
    never leave one dangling on a real checkout system."""
    return _post_api_method(base, 'cancel', block_data, [transaction_id], opener)


def get_seatmap_html(base, transaction_id, opener):
    url = f"{base}/checkout/seatmap/{transaction_id}"
    body = json.dumps({"isModal": True, "modalId": 1}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=API_HEADERS, method='POST')
    with opener(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))['html']


def extract_seatmap(html):
    """Pull the seats.seatmap URL-encoded JSON array out of the seatmap
    response's `html` field. See filmgrail_zone_match.py's module docstring for the
    seat record shape this returns."""
    anchor = html.find('%22state%22')
    if anchor == -1:
        raise RuntimeError('seat state marker not found in seatmap response')
    i, depth = anchor, 0
    while i > 0:
        if html[i:i + 3] == '%7D':
            depth += 1
        elif html[i:i + 3] == '%7B':
            if depth == 0:
                break
            depth -= 1
        i -= 1
    arr_start = i
    while arr_start > 0 and html[arr_start - 3:arr_start] != '%5B':
        arr_start -= 1
    arr_start -= 3
    j, bracket_depth = arr_start, 0
    while j < len(html):
        if html[j:j + 3] == '%5B':
            bracket_depth += 1
        elif html[j:j + 3] == '%5D':
            bracket_depth -= 1
            if bracket_depth == 0:
                j += 3
                break
        j += 1
    return json.loads(urllib.parse.unquote(html[arr_start:j]))


def reduce_seats(seats):
    """Drop fields filmgrail_zone_match.py doesn't use, keeping the payload small."""
    return [{'row': s['row'], 'column': s['column'], 'state': s['state'],
              'type': s['type'], 'rowSymbol': s['rowSymbol'], 'columnSymbol': s['columnSymbol']}
            for s in seats]


def check_seats(ticket_sale_url, count, opener=None):
    """Runs the full setTickets -> seatmap -> cancel cycle for one showtime.
    Always attempts cancel if a transaction was created, even on error -
    never leaves a transaction dangling.

    Returns a dict:
      status: 'ok' or 'error'
      seats: reduced seat list (see reduce_seats), only when status is 'ok'
      error: message, only when status is 'error'
      cancelStatus: 'cancelled' | 'failed' | 'not_created'
        ('not_created' means no transaction was ever opened, e.g. because
        setTickets itself failed - so there was nothing to cancel.)
    """
    opener = opener or new_session_opener()
    base = base_url(ticket_sale_url)
    result = {'status': None, 'seats': None, 'error': None, 'cancelStatus': 'not_created'}
    try:
        block_data = get_tickets_categories_data(ticket_sale_url, opener)
        st_response = set_tickets(base, block_data, count, opener)
    except Exception as e:
        result['status'] = 'error'
        result['error'] = f'setTickets failed: {e}'
        return result

    transaction_id = st_response.get('transactionId')
    if not transaction_id:
        result['status'] = 'error'
        result['error'] = f'no transactionId in setTickets response: {st_response}'
        return result

    try:
        html = get_seatmap_html(base, transaction_id, opener)
        result['seats'] = reduce_seats(extract_seatmap(html))
        result['status'] = 'ok'
    except Exception as e:
        result['status'] = 'error'
        result['error'] = f'seatmap extraction failed: {e}'
    finally:
        try:
            cancel_response = cancel(base, block_data, transaction_id, opener)
            result['cancelStatus'] = 'cancelled' if cancel_response.get('result') else 'failed'
        except Exception as e:
            result['cancelStatus'] = 'failed'
            note = f'cancel failed: {e}'
            result['error'] = f'{result["error"]}; {note}' if result['error'] else note

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Check seat availability for one showtime via its cinema\'s '
                    'checkout API directly (no browser required)')
    parser.add_argument('ticket_sale_url')
    parser.add_argument('--count', type=int, required=True)
    args = parser.parse_args()
    result = check_seats(args.ticket_sale_url, args.count)
    print(json.dumps(result))
    if result['status'] != 'ok' or result['cancelStatus'] == 'failed':
        sys.exit(1)


if __name__ == '__main__':
    main()
