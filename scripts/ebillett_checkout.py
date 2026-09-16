"""Seat-availability client for the ebillett.no (eBillett/DX) checkout platform,
used by ~65 mostly small independent Norwegian theaters - a completely
different vendor from Filmgrail and ODEON's Cinema API.

Reverse-engineered 2026-09-16. checkout.ebillett.no itself carries no bot
protection at all (confirmed: plain curl gets normal 200/302 responses
throughout, same as any browser) - the flow just took real effort to map
because the actual mechanism doesn't match what the static HTML implies at
first glance. Two things in particular are easy to get wrong:

1. The `<select class="qtySelect" id="qty_N">` ticket-quantity dropdowns
   have NO `name` attribute, even after the page's own JS renders them - so
   they are never part of the visible form's literal field set. The real
   submission uses a completely different, parallel-array shape, confirmed
   directly from a live browser's Request Payload:
     categories[0]=<ticketCategoryId>&antall[0]=<count>&events[0]=<arrnr>
   ("antall" is Norwegian for "quantity"). Guessing at qty_N/qty[N]-style
   names (the natural first guess from the DOM) will silently fail - the
   server returns a plain 200 with the same "choose quantity" page instead
   of creating a reservation, which looks superficially like success if you
   don't check the status code.

2. The POST to `.../purchase/setup` is a genuine synchronous, full-page
   form submission (not an XHR/fetch, and not interceptable by patching
   window.fetch/XMLHttpRequest/HTMLFormElement.prototype.submit after page
   load - confirmed by four separate JS-instrumentation attempts, none of
   which observed it, because whatever performs it captured its network
   reference before any post-load script could patch it). On success it
   returns a 302 whose Location header is
     /{p_id}/events/{arrnr}/purchase/{PHPSESSID}/{reservationId}/seating
   - the first path segment there is literally the request's own PHPSESSID
   cookie value (confirmed directly), and {reservationId} is assigned by
   the server on this exact call - it is not derivable in advance or
   client-generated, contrary to what its steadily-increasing-over-time
   values might suggest at a glance.

Getting the real seatmap then needs the *exact* reservation id from that
Location header (a wrong one 404s) but tolerates almost anything else - a
plain GET to `.../seatmap` (no query) returns no seat data at all
(`{}`/`[]`), and only `.../seatmap?a=select&e=<anything>&c=0` returns the
real `seatplan`, confirmed live even when `e` doesn't match the real id.

Seat data shape (the `seats` string per `seatplan[i]` entry) is a
colon-separated list of `state,x,y,z` seats, one per seat in that row, in
left-to-right seat-number order (position in this list, 1-indexed, is the
seat number - confirmed directly against a real reservation's
"RAD 7, SETE 16-19" confirmation text, which matched positions 16-19
exactly). `state` is a numeric code: "1" is free; every other value
(confirmed: "2" for a seat this reservation currently holds, others for
sold seats and special categories like sofa/companion sections) is treated
uniformly as not available for a *new* booking here - deliberately
conservative rather than trying to fully reverse-engineer every code.

Cleanup is honest, not Filmgrail-strength: resubmitting the same setup form
with `action=cancel` instead of `action=continue` is what the site's own
close ("X") button does (found in app.js's doCancel()), and this module
always attempts it - but confirmed live that doing so does NOT immediately
release the held seats (rechecking the seatmap right after, and again
after a few seconds, still showed them held). The real, repeatedly-
confirmed safety net is that ebillett.no reservations self-expire after
about a minute of inactivity regardless ("Det er gått mer enn ett minutt
uten aktivitet og dine valgte plasser er derfor blitt frigitt"). So
`cancelStatus` here means "the cancel request was sent/failed", not
"the hold is confirmed released" - callers should not treat 'attempted'
as equivalent to Filmgrail's 'cancelled'.
"""
import argparse
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://checkout.ebillett.no"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

HIDDEN_FIELD_NAMES = [
    "action", "frs_id", "arrnr", "p_id", "movie_id", "cinema_id",
    "return_url", "sb_receipt_id", "campaign_id",
]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class _PassThrough3xx(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        if 300 <= response.status < 400:
            return response
        return super().http_response(request, response)

    https_response = http_response


def new_session_opener():
    """A cookie-aware `opener(req, timeout=15)` callable that never
    auto-follows redirects and returns 3xx responses normally (not as
    exceptions) - every call in this module needs to read a Location
    header or rely on a redirect's Set-Cookie without being redirected."""
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj), _NoRedirect(), _PassThrough3xx(),
    ).open


def extract_ids(ticket_sale_url):
    """Pull (p_id, arrnr) out of an ebillett.no ticketSaleUrl, e.g.
    'https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf'
    -> ('246', '77439')."""
    path = urllib.parse.urlsplit(ticket_sale_url).path
    m = re.match(r"^/(\d+)/events/(\d+)/purchase", path)
    if not m:
        raise RuntimeError(f"unexpected ticketSaleUrl shape: {ticket_sale_url!r}")
    return m.group(1), m.group(2)


def parse_hidden_fields(html):
    """Extract the setup form's static hidden <input> fields (action,
    frs_id, arrnr, p_id, movie_id, cinema_id, return_url, sb_receipt_id,
    campaign_id)."""
    fields = {}
    for name in HIDDEN_FIELD_NAMES:
        m = re.search(rf'name="{name}"\s+value="([^"]*)"', html)
        if not m:
            raise RuntimeError(f"hidden field {name!r} not found on setup page")
        fields[name] = m.group(1)
    return fields


def parse_group_codes(html):
    """Extract `group_code<N>` hidden field names, if any - these vary per
    venue/event and must be included (empty) in the setup POST alongside
    the fixed hidden fields, e.g. ['group_code11']."""
    return [f"group_code{n}" for n in re.findall(r'name="group_code(\d+)"', html)]


def pick_first_category_id(html):
    """The standard/adult ticket category, picked by position (first
    listed via `this.categories.set(<id>, {...})`) - the same
    first-enabled-category heuristic used elsewhere in this repo, since
    ebillett.no's category ids/labels are venue-specific (no fixed "adult"
    id or empty-string type to rely on)."""
    m = re.search(r"categories\.set\((\d+),", html)
    if not m:
        raise RuntimeError("no ticket categories found on setup page")
    return m.group(1)


def parse_seating_location(location):
    """Parse a successful setup POST's Location header into
    (token, reservationId), e.g.
    '/246/events/77439/purchase/uvg1adidnlqp5eljef73vr8s5i/73497231/seating'
    -> ('uvg1adidnlqp5eljef73vr8s5i', '73497231'). `token` is the same
    value as the PHPSESSID cookie (confirmed live) - not re-derived here,
    just read directly from the URL the server gave us."""
    m = re.match(r"^/\d+/events/\d+/purchase/([^/]+)/(\d+)/seating$", location)
    if not m:
        raise RuntimeError(f"unexpected setup redirect location: {location!r}")
    return m.group(1), m.group(2)


def seats_from_seatmap(data):
    """Decode a seatmap response's compact `seatplan` encoding into
    filmgrail-checkout-shaped records (row/column ints, state, type,
    rowSymbol/columnSymbol). Each seatplan row's `seats` field is a
    colon-separated list of `state,x,y,z` seats in left-to-right seat-order
    (list position, 1-indexed, is the seat/column number - confirmed
    directly against a real reservation's on-screen "RAD n, SETE a-b"
    confirmation text). Only state "1" (free) counts as available; every
    other code - this reservation's own held seats, sold seats, and
    special categories like sofa/companion sections - is conservatively
    treated as booked (see module docstring)."""
    seats = []
    for row_entry in data.get("seatplan", []):
        row = row_entry.get("row")
        if row is None:
            continue
        raw_seats = [s for s in row_entry.get("seats", "").split(":") if s]
        for column, raw_seat in enumerate(raw_seats, start=1):
            state_code = raw_seat.split(",")[0]
            seats.append({
                "row": row,
                "column": column,
                "state": "available" if state_code == "1" else "booked",
                "type": "",
                "rowSymbol": str(row),
                "columnSymbol": str(column),
            })
    return seats


def _post(event_path, hidden_fields, extra_fields, opener):
    """`event_path` is the full '/{p_id}/events/{arrnr}' prefix - not just
    '/{p_id}' - since the setup endpoint lives at
    '/{p_id}/events/{arrnr}/purchase/setup'."""
    fields = dict(hidden_fields)
    fields.update(extra_fields)
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{event_path}/purchase/setup", data=data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with opener(req, timeout=15) as resp:
        return resp


def check_seats(ticket_sale_url, count, opener=None):
    """Runs discover-hidden-fields -> create reservation -> read seatmap
    -> best-effort cancel for one ebillett.no showtime. See module
    docstring for why `cancelStatus` here is weaker than Filmgrail's.

    Returns a dict:
      status: 'ok' or 'error'
      seats: combined seat list (see seats_from_seatmap), only when status is 'ok'
      error: message, only when status is 'error'
      cancelStatus: 'attempted' | 'failed' | 'not_created'
        ('not_created' means no reservation was ever made, e.g. the setup
        POST didn't redirect - so there was nothing to cancel.)
    """
    opener = opener or new_session_opener()
    p_id, arrnr = extract_ids(ticket_sale_url)
    event_path = f"/{p_id}/events/{arrnr}"
    result = {"status": None, "seats": None, "error": None, "cancelStatus": "not_created"}

    hidden_fields = None
    try:
        req = urllib.request.Request(ticket_sale_url, headers={"User-Agent": UA})
        with opener(req, timeout=15) as resp:
            resp.read()

        req = urllib.request.Request(f"{BASE}{event_path}/purchase/setup", headers={"User-Agent": UA})
        with opener(req, timeout=15) as resp:
            setup_html = resp.read().decode("utf-8")

        hidden_fields = parse_hidden_fields(setup_html)
        group_codes = parse_group_codes(setup_html)
        category_id = pick_first_category_id(setup_html)

        extra = {name: "" for name in group_codes}
        extra.update({"categories[0]": category_id, "antall[0]": str(count), "events[0]": arrnr})
        resp = _post(event_path, hidden_fields, extra, opener)
        if resp.status != 302 or "Location" not in resp.headers:
            raise RuntimeError(f"setup POST did not redirect (status {resp.status}) - reservation not created")
        token, reservation_id = parse_seating_location(resp.headers["Location"])
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"reservation failed: {e}"
        return result

    try:
        seatmap_url = (
            f"{BASE}{event_path}/purchase/{token}/{reservation_id}"
            f"/seatmap?a=select&e={reservation_id}&c=0"
        )
        req = urllib.request.Request(seatmap_url, headers={
            "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })
        with opener(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result["seats"] = seats_from_seatmap(data)
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"seatmap extraction failed: {e}"
    finally:
        try:
            _post(event_path, hidden_fields, {"action": "cancel"}, opener)
            result["cancelStatus"] = "attempted"
        except Exception as e:
            result["cancelStatus"] = "failed"
            note = f"cancel failed: {e}"
            result["error"] = f'{result["error"]}; {note}' if result["error"] else note

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Check seat availability for one ebillett.no showtime by driving the "
                    "real checkout flow directly over HTTP (no browser needed)")
    parser.add_argument("ticket_sale_url")
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()
    result = check_seats(args.ticket_sale_url, args.count)
    print(json.dumps(result))
    if result["status"] != "ok" or result["cancelStatus"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
