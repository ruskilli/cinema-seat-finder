"""Seat-availability client for the NFkino checkout platform (Drupal 10 +
a Vista Entertainment ticketing backend), covering NFKino's independent
cinemas (Arendal, Farsund, Drammen/KinoCity, Kristiansand, Asker, Askim,
Halden, Horten, Hønefoss, Tønsberg/Kilden, Oslo, Sarpsborg, Verdal, Bergen/
Lagunen) - a separate vendor from Filmgrail, ODEON, and ebillett.no.

Reverse-engineered 2026-09-16. nfkino.no carries no bot protection at all
(confirmed: plain requests get normal 200/302/204 responses throughout,
same as any browser).

Opening a ticketSaleUrl (https://nfkino.no/screening/<cinemaUuid>/
<screeningUuid>) sets a session cookie and redirects (a normal HTTP
redirect, not ebillett.no's synchronous-form trick) to
/order/<orderUuid>/seats - the orderUuid is embedded directly in that
page's `drupalSettings` JSON (`orders.orderUuid`).

GET /order/<orderUuid>/reserve_seats returns {"seats_selector": <html>,
"tickets_selector": <html>, "basket": <html>} - full-page HTML fragments
meant for direct DOM injection. The one thing pulled from tickets_selector
here is the standard ticket type's uuid, via its `data-ticket-type-uuid`
attribute (the first one listed - same "pick the first/standard category"
reasoning used in filmgrail_checkout.py/ebillett_checkout.py).

POST /order/<orderUuid>/add_tickets with JSON body
{"types": [{"id": <ticketTypeUuid>, "quantity": <count>}]} is what
actually reserves seats - the server auto-assigns `count` contiguous
seats and returns a *differently shaped*, structured JSON response (not
HTML) at `seats_selector`:
  seats_selector.seats.rows - row legends, keyed by an internal row id
  seats_selector.seats.seats - every seat: {id, symbol, kind, rowId,
    coordinateX, coordinateY, wheelchairSeat, ...}. kind "1" means an
    empty-space layout placeholder (aisle gap), not a real seat - it has
    no `symbol` and is skipped entirely (confirmed live: exactly the
    seats rendered with the "empty-space" CSS class). kind "0" is a real,
    bookable seat, and `symbol` is its human seat number.
  seats_selector.selectedSeats.list - every currently-occupied seat uuid
    in the whole room (confirmed live: this includes the caller's own
    just-reserved seats, not just other people's - see
    seats_from_seats_selector below).
  seats_selector.bestSeats - the uuids of the `count` seats the server
    just auto-assigned to *this* order.

Availability per seat: a seat is available if its uuid is NOT in
selectedSeats.list, OR IS in bestSeats (this order's own hold) - the same
fix as ebillett_checkout.py's state-"2" handling, since selectedSeats.list
otherwise conflates "held by someone else" with "held by us just now", and
the latter is exactly the seats the caller asked to check for.

Cleanup is honest, not Filmgrail-strength: POSTing to
/order/<orderUuid>/abandon (confirmed: what the site itself fires via
sendBeacon/fetch on page unload) reliably returns 204, but live testing
(two independent sessions, including a 5s wait before re-checking) could
not fully confirm every held seat reliably shows as free again afterward.
The real, visible safety net is the order's own ~10-minute countdown
(shown on-page as "Tid som gjenstår") after which it's abandoned
automatically - so, like ebillett.no, cancelStatus here is "attempted",
never "cancelled".

General admission screenings (`isGeneralAdmissionScreening: true` -
unnumbered/unreserved seating, the same concept as Bygdekinoen) have no
seatmap at all; check_seats() reports this as an error rather than an
empty result.
"""
import argparse
import http.cookiejar
import json
import re
import urllib.request

BASE = "https://www.nfkino.no"
UA = "Mozilla/5.0"


def new_session_opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener.open


def parse_order_uuid(html):
    """Extract the orderUuid Drupal embeds in the order page's
    drupalSettings JSON blob."""
    m = re.search(r'"orderUuid":"([0-9a-f-]+)"', html)
    if not m:
        raise RuntimeError("could not find orderUuid on the order page")
    return m.group(1)


def parse_ticket_type_uuid(tickets_selector_html):
    """Pick the first (standard/adult) ticket type's uuid - same
    "pick the first category" reasoning as filmgrail_checkout.py and
    ebillett_checkout.py."""
    m = re.search(r'data-ticket-type-uuid="([0-9a-f-]+)"', tickets_selector_html)
    if not m:
        raise RuntimeError("no ticket types found on order page")
    return m.group(1)


def seats_from_seats_selector(seats_selector):
    """Decode an add_tickets response's structured `seats_selector` into
    filmgrail-checkout-shaped records (row/column ints, state, type,
    rowSymbol/columnSymbol). Skips kind "1" layout placeholders (aisle
    gaps, not real seats). A seat counts as available if it's not in
    selectedSeats.list, or if it is but is also in bestSeats (this order's
    own hold - see module docstring)."""
    seats_data = seats_selector["seats"]
    row_legend = {row["id"]: row["legend"] for row in seats_data["rows"]}
    taken = set(seats_selector["selectedSeats"]["list"])
    ours = set(seats_selector["bestSeats"])

    seats = []
    for seat in seats_data["seats"]:
        if seat["kind"] == "1":
            continue
        available = seat["id"] not in taken or seat["id"] in ours
        seats.append({
            "row": seat["coordinateY"] + 1,
            "column": seat["coordinateX"] + 1,
            "state": "available" if available else "booked",
            "type": "wheelchair" if seat["wheelchairSeat"] else "",
            "rowSymbol": row_legend.get(seat["rowId"], ""),
            "columnSymbol": seat["symbol"],
        })
    return seats


def check_seats(ticket_sale_url, count, opener=None):
    """Runs discover-order -> select ticket type -> reserve `count` seats
    -> best-effort cleanup for one NFkino screening. See module docstring
    for why `cancelStatus` here is weaker than Filmgrail's.

    Returns a dict:
      status: 'ok' or 'error'
      seats: combined seat list (see seats_from_seats_selector), only when status is 'ok'
      error: message, only when status is 'error'
      cancelStatus: 'attempted' | 'failed' | 'not_created'
        ('not_created' means no order was ever made, e.g. the initial page
        request itself failed - so there was nothing to clean up.)
    """
    opener = opener or new_session_opener()
    result = {"status": None, "seats": None, "error": None, "cancelStatus": "not_created"}
    order_uuid = None

    try:
        req = urllib.request.Request(ticket_sale_url, headers={"User-Agent": UA})
        with opener(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
        order_uuid = parse_order_uuid(html)

        req = urllib.request.Request(f"{BASE}/order/{order_uuid}/reserve_seats", headers={"User-Agent": UA})
        with opener(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ticket_type_uuid = parse_ticket_type_uuid(data["tickets_selector"])

        body = json.dumps({"types": [{"id": ticket_type_uuid, "quantity": count}]}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE}/order/{order_uuid}/add_tickets", data=body,
            headers={
                "User-Agent": UA, "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            method="POST",
        )
        with opener(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if "error" in data:
            raise RuntimeError(f"add_tickets failed: {data['error']}")
        seats_selector = data["seats_selector"]
        if seats_selector.get("isGeneralAdmissionScreening"):
            raise RuntimeError("general admission screening - no seatmap to check")

        result["seats"] = seats_from_seats_selector(seats_selector)
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"seat check failed: {e}"
    finally:
        if order_uuid:
            try:
                req = urllib.request.Request(
                    f"{BASE}/order/{order_uuid}/abandon", data=b"",
                    headers={"User-Agent": UA}, method="POST",
                )
                with opener(req, timeout=15):
                    pass
                result["cancelStatus"] = "attempted"
            except Exception:
                result["cancelStatus"] = "failed"

    return result


def main():
    parser = argparse.ArgumentParser(description="Check NFkino seat availability for one screening")
    parser.add_argument("ticket_sale_url")
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()

    result = check_seats(args.ticket_sale_url, args.count)
    print(json.dumps(result))
    if result["status"] != "ok" or result["cancelStatus"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
