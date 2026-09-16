---
name: cinema-seat-finder
description: "List today's showtimes at ANY Norwegian cinema (nationwide or a named town), look up/resolve a town or cinema by name, look up a movie's synopsis/genre/runtime/age rating, or find N contiguous available seats in a preferred zone (front/middle/back, left/center/right) at Trondheim Kino, Steinkjer kino, Kimen kino (Stjørdal), Haugesund kino, Caroline kino (Kristiansund), Aurora Kino (Tromsø/Narvik/Alta/Kirkenes/Lakselv), ODEON Kino (any city, e.g. Oslo/Stavanger/Sandnes/Ålesund/Skien/Moss/Lillestrøm/Sandvika/Ski/Sotra), any ebillett.no venue (~65 mostly small independent theaters nationwide), or any NFkino venue (Arendal, Farsund, Drammen, Kristiansand, Asker, Askim, Halden, Horten, Hønefoss, Tønsberg, Oslo, Sarpsborg, Verdal, Bergen/Lagunen, and more) - the only cinemas seat-checking is supported for. Use when the user asks something like 'N of us want to see [film], ideally seated in the back', 'what's playing tonight' / 'what movies are on today [in <town>]', 'is there a cinema in <town>' / 'what towns do you cover', or 'what's [film] about' / 'how long is [film]' / 'what age rating is [film]'."
---

# cinema-seat-finder

Lists today's showtimes at any Norwegian cinema — nationwide by default, or
narrowed to a town the user names — looks up towns/cinemas by name, and
looks up a movie's synopsis/genre/runtime/age rating. For a given film, it
also finds which showtimes at Trondheim Kino, Steinkjer kino, Kimen kino
(Stjørdal), Haugesund kino, Caroline kino (Kristiansund), Aurora Kino
(Tromsø, Narvik, Alta, Kirkenes, Lakselv), ODEON Kino (any city), any
ebillett.no venue (~65 mostly small independent theaters nationwide), or
any NFkino venue — the only cinemas seat-checking is supported for —
actually have room for a group together in their preferred part of the
room, instead of the user manually clicking through film → time → seat
count → seatmap for every candidate showing.

**Scope:** *Listing* what's on, and *looking up* towns/cinemas, works
nationwide — any Norwegian cinema Filmweb knows about. *Seat-finding* only
works for four checkout platforms (see "Known checkout platforms" below):
Filmgrail/Mars (ten cinemas, `filmgrail_checkout.py` +
`filmgrail_zone_match.py`), ODEON's Cinema API backend (any ODEON city,
`odeon_checkout.py` + `odeon_zone_match.py`), the ebillett.no/DX platform
(any ebillett.no venue, `ebillett_checkout.py` + `ebillett_zone_match.py`),
and NFkino's Drupal+Vista platform (any NFkino venue, `nfkino_checkout.py`
+ `nfkino_zone_match.py`) — if a film is only playing somewhere else, say
so plainly rather than silently returning nothing. Today's date only,
unless the user explicitly gives another date. Never completes a purchase
— it only reports which showtimes are viable and their booking links.

**Talking to the user:** this whole document — script names, platform
internals, JSON field names, HTTP mechanics — is orchestration detail for
you, not something to narrate. Work through Steps 1-3 quietly; don't
report each script you're about to run or each candidate you're checking
as you go (a single short "checking today's showings..." is plenty, if
you say anything at all before the final answer). The Step 4 report
should read like a person who checked seats for you, not a systems log:
plain language only — no script or field names (`cancelStatus`,
`ticketSaleUrl`, `firmName`, "matcher", "seatmap JSON", etc.), no mention
of which HTTP calls were made. Only go into the mechanics if the user
explicitly asks how this works.

## Known checkout platforms (background)

### Filmgrail/Mars cinemas

`scripts/filmgrail_checkout.py` drives the same checkout API this skill uses
for Trondheim Kino. Surveyed 2026-09-16 via `discover_shows.py --location
""` (empty string — Filmweb returns every showtime nationwide when
`location` is blank/omitted-as-empty, 893 shows across 110 cinemas that
particular day; this is how the full picture below was gathered in one
call instead of guessing town names), then a live but read-only page fetch
per unique checkout domain checking for the embedded `TicketsCategories`
block (no checkout transaction opened for that survey pass).

**In scope, fully working** — each confirmed live end to end (real
transaction, real seatmap, real `filmgrail_zone_match.py` match, clean
cancel):

| Cinema | Town(s) | Domain |
|---|---|---|
| Trondheim Kino | Trondheim | `www.trondheimkino.no` |
| Steinkjer kino | Steinkjer | `www.trondheimkino.no` |
| Kimen kino | Stjørdal | `www.trondheimkino.no` |
| Haugesund kino | Haugesund | `www.edda-kino.no` |
| Caroline kino Kristiansund | Kristiansund | `www.carolinekino.no` |
| Tromsø Kino | Tromsø | `fokus.aurorakino.no` |
| Narvik kino | Narvik | `narvik.aurorakino.no` |
| Alta kino | Alta | `alta.aurorakino.no` |
| Kirkenes kino | Kirkenes | `kirkenes.aurorakino.no` |
| Lakselv kino | Lakselv | `lakselv.aurorakino.no` |
| Setermoen kino | Setermoen | `www.setermoenkino.no` |
| Bergen kino | Bergen | `www.bergenkino.no` |

These twelve `firmName` values are exactly what the allow-list in Step
1/Step 2 below checks against. (Setermoen kino added 2026-09-17: found via
a nationwide domain survey, not yet listed anywhere, and confirmed live
the same way as the rest.)

Most of these rooms share the same integer `row`/`column` seatmap grid.
**Bergen kino is the one exception** (added 2026-09-17): its seatmap has
no integer `column` field at all, only pixel `coordX`/`coordY` plus
`rowSymbol`/`columnSymbol`. It turned out `rowSymbol`/`columnSymbol` alone
already carry the same clean, gapless adjacency structure the matcher
needs (confirmed live against two different Bergen kino rooms, 2026-09-17)
— so `filmgrail_checkout.py`'s `reduce_seats` derives a synthetic
`row`/`column` from those symbols for any room shaped like this, and
everything downstream (`filmgrail_zone_match.py` included) works
unchanged. See that function's docstring for exactly how.

Two chains found this way at first looked like dead ends (different
checkout vendor entirely) but turned out to be their own separately
supported platforms rather than "not on this platform" — **ebillett.no**
and **NFkino** — see their own sections below.

Bygdekinoen (the mobile-cinema circuit, `kinologg.kino.no`) is excluded for
a stronger reason than "different vendor": its screenings run in village
halls and other venues with unnumbered, unreserved seating, so there is no
seatmap to seat-check at all, regardless of platform. Never attempt
seat-checking against a Bygdekinoen showtime even if the vendor question
were somehow moot.

If a new candidate cinema turns up later (another `<town>.aurorakino.no`
subdomain not yet checked, say), verify it the same way before adding it to
the allow-list: a real `check_seats()` call, confirm `status: 'ok'` and a
sane `filmgrail_zone_match.py` match — don't add a cinema on
domain-pattern-matching alone. A seatmap shape different from Trondheim's
integer grid isn't automatically a dead end any more (Bergen proved that,
see above) — but it still needs a live check per new *shape* encountered,
not just per cinema, since a future shape might not be `rowSymbol`/
`columnSymbol`-friendly the way Bergen's was.

### ODEON (Cinema API)

ODEON's own site (`www.odeonkino.no`) is behind an active Cloudflare
bot-challenge on every page (`cf-mitigated: challenge` to any plain
request) and is never contacted by this skill. Its booking pages instead
call a separate, genuinely open backend — `services.cinema-api.com` — which
answers plain unauthenticated GETs directly (see `odeon_checkout.py`'s
module docstring for exactly which endpoints, and the README's "Public
APIs only" section for why this distinction matters). `odeon_checkout.py`
+ `odeon_zone_match.py` handle this platform; unlike Filmgrail, checking
seats is purely read-only — no transaction or hold is ever opened.

ODEON showtimes are identified by **domain, not `firmName`** — unlike the
Filmgrail cinemas above, ODEON's chain spans many different `firmName`
strings for the same underlying platform (some branded "ODEON \<city\>",
others independently, e.g. "Stavanger Kino"), all sharing the checkout
domain `www.odeonkino.no`. A candidate is in scope for this platform when
its `ticketSaleUrl` has that domain, regardless of `firmName`.

Confirmed live 2026-09-16, real seatmap + real `odeon_zone_match.py` match,
for two different cities sharing this backend (Oslo and Stavanger) — both
returned the same clean integer `row`/`column` grid shape, so this is
treated as one platform rather than requiring a per-city check the way
Filmgrail's Bergen/Trondheim split did. `firmName` values seen under
`www.odeonkino.no` so far: ODEON Oslo, ODEON Ålesund, ODEON Skien, ODEON
Moss, ODEON Lillestrøm, ODEON Sandvika, ODEON Ski, ODEON Sotra, Stavanger
Kino, Sandnes Kino — this list is illustrative, not the matching rule; the
domain is.

### ebillett.no (eBillett/DX)

`checkout.ebillett.no` carries no bot protection at all — every call in
`ebillett_checkout.py` is a plain HTTP request (no browser). What made this
platform take real effort wasn't detection, it was that its actual
mechanism doesn't match what the static setup-page HTML implies:

- The ticket-quantity `<select>` dropdowns have no `name` attribute even
  after the page renders, so the obvious guesses (`qty_1`, `qty[1]`, ...)
  silently fail — the server just re-shows the same quantity page with
  `200`. The real submission is a parallel-array shape, confirmed directly
  from a live browser's Request Payload: `categories[0]=<categoryId>
  &antall[0]=<count>&events[0]=<arrnr>` ("antall" = Norwegian for
  "quantity"), alongside the visible hidden fields and any venue-specific
  `group_code<N>` fields (submitted empty).
- A successful submission is a `302` whose `Location` header is
  `/{p_id}/events/{arrnr}/purchase/{PHPSESSID}/{reservationId}/seating` —
  the token segment is literally that request's own `PHPSESSID` cookie
  value (confirmed directly), and `{reservationId}` is assigned by the
  server on that call, not derivable in advance.
- The real seatmap needs `.../seatmap?a=select&e=<reservationId>&c=0` — a
  plain GET with no query returns no seat data at all.

`ebillett_checkout.py` + `ebillett_zone_match.py` handle this platform.
ebillett.no showtimes are identified by **domain**, same reasoning as
ODEON: `ticketSaleUrl` starts with `https://checkout.ebillett.no/`,
regardless of `firmName` — one shared backend serves ~65 different
theaters, each with its own `firmName`.

**Cleanup is honest, not Filmgrail-strength.** The site's own close ("X")
button resubmits the same form with `action=cancel` instead of
`action=continue`, and `ebillett_checkout.py` always attempts this — but
confirmed live that it does **not** visibly release the held seats
immediately (rechecking the seatmap right after, and again a few seconds
later, still showed them held). The real, repeatedly-confirmed safety net
is that ebillett.no reservations self-expire after about a minute of
inactivity regardless. So `check_seats()`'s `cancelStatus: "attempted"`
here means "the cancel request was sent", not "the hold is confirmed
released" — never treat it as equivalent to Filmgrail's `"cancelled"`.

Confirmed live 2026-09-16, real reservation + real seatmap + real
`ebillett_zone_match.py` match, for two different venues (Rana kino and
Stryn kino) sharing this backend, both returning the same seat shape
`ebillett_checkout.py` expects.

### NFkino (Drupal + Vista)

`nfkino.no` carries no bot protection either — every call in
`nfkino_checkout.py` is a plain HTTP request. The site is Drupal 10 with a
Vista Entertainment ticketing backend bolted on:

- Opening a `ticketSaleUrl`
  (`https://nfkino.no/screening/<cinemaUuid>/<screeningUuid>`) sets a
  session cookie and redirects (a normal HTTP redirect, unlike ebillett.no's
  synchronous-form trick) to `/order/<orderUuid>/seats` — the `orderUuid`
  is embedded directly in that page's `drupalSettings` JSON.
- `GET /order/<orderUuid>/reserve_seats` returns full-page HTML fragments
  meant for direct DOM injection; the only thing pulled from it here is the
  standard ticket type's uuid (`data-ticket-type-uuid`, first one listed —
  same "pick the first category" reasoning as Filmgrail/ebillett.no).
- `POST /order/<orderUuid>/add_tickets` with JSON body
  `{"types": [{"id": <ticketTypeUuid>, "quantity": <count>}]}` is what
  actually reserves seats — the server auto-assigns `count` contiguous
  seats and, unlike the GET above, returns a *structured* JSON seatmap:
  every seat's row/column position, plus `selectedSeats.list` (every
  currently-occupied seat in the whole room) and `bestSeats` (the seats
  just assigned to *this* order).
- **Availability requires the same fix as ebillett.no's state-"2" seats**:
  `selectedSeats.list` includes this order's own just-reserved seats, not
  just other people's — a seat only counts as booked if it's in that list
  *and not* in `bestSeats`. See `nfkino_checkout.py`'s module docstring.
- Wheelchair seats are flagged explicitly (`wheelchairSeat: true`), unlike
  ebillett.no which has no such signal — `nfkino_zone_match.py` excludes
  them via the same majority-type logic as `filmgrail_zone_match.py`,
  rather than ebillett's pass-through.

**Cleanup is honest here too.** `POST /order/<orderUuid>/abandon` (what the
site itself fires via `sendBeacon` on page unload) reliably returns `204`,
but live testing (two independent sessions, including a 5s wait before
re-checking) could not fully confirm every held seat reliably shows as
free again afterward. The real, visible safety net is the order's own
~10-minute countdown ("Tid som gjenstår" on-page) after which it's
abandoned automatically — so, like ebillett.no, `cancelStatus: "attempted"`
here is never "cancelled".

General admission screenings (`isGeneralAdmissionScreening: true` —
unnumbered/unreserved seating, the same concept as Bygdekinoen) have no
seatmap at all; `nfkino_checkout.py` reports this as a normal `status:
"error"` rather than an empty result.

NFkino showtimes are identified by **domain**, same reasoning as ODEON and
ebillett.no: `ticketSaleUrl` starts with `https://nfkino.no/`, regardless
of `firmName`.

Confirmed live 2026-09-16, real reservation + real seatmap + real
`nfkino_zone_match.py` match, for Horten kino. The domain-based
classification is expected to generalize to NFkino's other independent
cinemas (Arendal, Farsund, Drammen, Kristiansand, Asker, Askim, Halden,
Hønefoss, Tønsberg, Oslo, Sarpsborg, Verdal, Bergen/Lagunen, and more)
since they all run the identical Drupal+Vista integration — but only
Horten has actually been verified end-to-end so far; treat the rest the
same way the Filmgrail/ODEON allow-lists are treated (verify a new one
live before fully trusting it, don't just assume from architecture alone).

## Step 1 — Parse the request

First, figure out which of four things the user is asking for:

- **Location query** — asking about towns/cinemas themselves, not
  showtimes (e.g. "is there a cinema in Bergen", "what towns do you
  cover", "what cinemas are in Trondheim"). Handle this per **Location
  query** below and stop there.
- **Movie info query** — asking about a film itself, not showtimes or
  seats (e.g. "what's Fjord about", "how long is Fjord", "what age rating
  is Fjord"). Handle this per **Movie info query** below and stop there.
- **Listing request** — no specific film named (e.g. "what's playing
  tonight", "what movies are on today [in <town>]"). Handle this per
  **Listing request** below and stop there — do not proceed to
  seat-checking.
- **Seat-finding request** — names a film and (usually) a party size, e.g.
  "3 of us want to see Spider-Man tonight [in <town>]". Parse the fields
  below and continue through the rest of this skill.

### Resolving a location (shared by Listing and Seat-finding)

If the user names a town, resolve it before using it as `--location` —
`discover_shows.py`'s show-discovery needs the *exact* canonical spelling
with correct Norwegian diacritics (confirmed live 2026-09-16: "Tromso"
returns nothing, "Tromsø" works):

```bash
python3 scripts/discover_shows.py --search-location "<town as the user typed it>"
```

- Exactly one name back → use it as `--location`.
- Several back (e.g. "berg" → `["Bergen", "Kongsberg", "Rødberg",
  "Tønsberg"]`) → ask the user which one they meant before proceeding.
- Empty array → this search does plain substring/prefix matching on
  correctly-accented text, not diacritic-insensitive fuzzy matching (see
  `discover_shows.py`'s module docstring) — try a shorter, more likely
  prefix of the user's spelling before giving up; if still nothing, tell
  the user you couldn't find that town and ask them to confirm the
  spelling.
- Non-zero exit or invalid JSON stdout → the search itself failed — report
  that rather than treating it as "no such town."

If the user names no town at all, skip this — use `--location ""`
(nationwide) in the steps below.

### Location query

For a general "what towns/cinemas do you cover" question, answer from
"Known checkout platforms" above for *seat-finding* coverage (the Filmgrail
table, plus ODEON, ebillett.no, and NFkino — mention all three of those
cover any city/venue on their platform, not a fixed list), and make clear
that's narrower than *listing*, which covers every cinema nationwide.

For a specific town (e.g. "is there a cinema in Ålesund"), resolve it per
**Resolving a location** above, then run:

```bash
python3 scripts/discover_shows.py --location "<resolved town>" --list-cinemas
```

This lists the cinema *buildings* Filmweb knows about there (e.g.
`[{"name": "Nova", "firmId": 12}, {"name": "Prinsen", "firmId": 12}]` for
Trondheim). Report the building names plainly, and note whether that town
is seat-finding-supported — one of the twelve Filmgrail cinemas (cross-check
against the table above), any ODEON city, any ebillett.no venue, any
NFkino venue, or listing-only. An empty array means no cinema found for
that resolved town — say so.

### Movie info query

Resolve the title to a Filmweb movie id first:

```bash
python3 scripts/discover_shows.py --search-movie "<film title as the user typed it>"
```

- Exactly one plausible result → use its `mainVersionId`.
- Several results → titles are frequently reused/similar (e.g. searching
  "Fjord" also returns "Storfjord 1829", "Deilig er fjorden", etc. —
  confirmed live 2026-09-16) — pick the one whose `title` matches what the
  user asked for; if more than one is plausible, confirm with the user
  before proceeding, the same as Step 2's fuzzy-title handling for
  seat-finding.
- Empty array → tell the user you couldn't find that film and ask them to
  confirm the title, rather than guessing.
- Non-zero exit or invalid JSON stdout → the search itself failed — report
  that rather than "no such film."

Then fetch the full info:

```bash
python3 scripts/discover_shows.py --movie-id "<mainVersionId from above>"
```

This returns `title`, `titleOriginal`, `genres`, `lengthInMinutes`,
`rating` (age rating), `synopsisIngress` (short), `synopsisBodyText`
(long), `premiere`, `productionYear`, `userRatingAvg`/`userRatingNum`
(Filmweb's own user rating), `languages`, and `nationalities`. Answer only
what the user actually asked (runtime, age rating, synopsis, genre,
etc.) — don't dump every field back at them unprompted; a genuinely
open-ended "tell me about X" is the one case where presenting most of it
(title, genre, runtime, rating, synopsis) makes sense. **All text fields
are in Norwegian** (same as the rest of Filmweb's data) — translate for
the user unless they're clearly asking in Norwegian themselves. Never
seat-check or list showtimes as part of this — that's a separate request
type, only proceed there if the user follows up asking for showtimes or
seats.

### Listing request

Resolve any town the user named per **Resolving a location** above; use
`--location ""` if none was named. Then run, from the project root:

```bash
python3 scripts/discover_shows.py --date <YYYY-MM-DD> --location "<resolved town, or "" for nationwide>" [--exclude-past]
```

Add `--exclude-past` whenever `<YYYY-MM-DD>` is today (the default) — the
API's `--date` filter is date-only, so without it a showtime that already
started or finished earlier today would be listed as if it were still on.
Omit it for an explicitly future (or past) date the user asked for.

(no `--movie-title` — this returns every showtime for the day.) This is
**not** restricted to the seat-finding-supported cinemas — list everything
Filmweb returns, any chain, since this is purely informational and
Filmweb's discovery already covers every Norwegian cinema regardless of
checkout platform. The same error handling as Step 2 applies: a non-zero
exit, or stdout that isn't valid JSON, means discovery itself failed —
report that rather than "nothing playing today."

Group the results by `movieTitle` and present each film with its showtimes
(time, `screenName`, `theaterName`, and — since results may now span many
towns/chains — `firmName` too whenever it isn't already obvious from
`theaterName`), sorted by start time. Include each showtime's
`ticketSaleUrl` as a booking link whenever it's non-empty — this applies to
*every* cinema listed, not just the seat-finding-supported ones (see "Known
checkout platforms" above): a showtime at, say, a Bygdekinoen screening has
no seat-checking available, but the user can still follow the link and
check/book manually, so don't withhold it just because this skill can't
check it itself. Stop here — do not seat-check anything unless the user
follows up naming a film and party size. (If they do, and that film turns
out to only be playing at cinemas outside all four seat-finding platforms,
Step 2/4 below handles saying so plainly rather than reporting no
matches.)

### Seat-finding request

Extract from the user's message:
- **Film title** (may be approximate/partial — disambiguate in Step 2).
- **Party size N** (integer).
- **Zone preference**: any combination of a row preference (`front`,
  `middle`, `back`) and a side preference (`left`, `center`, `right`). Either
  or both may be omitted (treat omitted as "any").
- **Date**: defaults to today (system date) unless the user specifies one —
  pass it as `YYYY-MM-DD` to the scripts below.
- **Location** (optional): a town the user named, e.g. "in Bergen" or "at
  Kimen kino" — resolve it per **Resolving a location** above before Step
  2. If none was named, use `--location ""` (nationwide) in Step 2.

## Step 2 — Discover candidate showtimes

Run, from the project root, using the location resolved in Step 1
(`--location ""` if the user named no town):

```bash
python3 scripts/discover_shows.py --date <YYYY-MM-DD> --location "<resolved town, or "" for nationwide>" --movie-title "<film title>" [--exclude-past]
```

Same `--exclude-past` rule as **Listing request** above: include it when
`<YYYY-MM-DD>` is today, omit it for an explicitly different date — a
seat-finding candidate that already started or finished isn't one worth
seat-checking in Step 3.

- If the script exits with a non-zero status, or its stdout is not valid JSON
  (as opposed to a valid empty array `[]`), the discovery step itself failed
  — report that to the user (e.g. the API may be down or unreachable) rather
  than treating it the same as "no showings today."
- If this returns an empty array, retry **without** `--movie-title` (same
  location and date), and check whether any returned `movieTitle` looks
  like a fuzzy match for what the user asked for (titles are in Norwegian
  and may not match the user's exact wording). If you find a plausible
  match, confirm it with the user before proceeding. If nothing plausible
  exists, tell the user there are no showings of that film today (in that
  town, if one was given) and stop.
- Otherwise, you now have the full candidate list: each entry has
  `showStart`, `screenName`, `theaterName`, `firmName`, `ticketSaleUrl`.
- Classify each candidate into exactly one of five groups:
  - **Filmgrail** — `firmName` exactly one of the twelve values listed under
    "Filmgrail/Mars cinemas" above (`"Trondheim Kino"`, `"Steinkjer kino"`,
    `"Kimen kino"`, `"Haugesund kino"`, `"Caroline kino Kristiansund"`,
    `"Tromsø Kino"`, `"Narvik kino"`, `"Alta kino"`, `"Kirkenes kino"`,
    `"Lakselv kino"`, `"Setermoen kino"`, `"Bergen kino"`).
  - **ODEON** — `ticketSaleUrl` starts with `https://www.odeonkino.no/`
    (domain-based, not `firmName`-based — see "ODEON (Cinema API)" above
    for why).
  - **ebillett.no** — `ticketSaleUrl` starts with
    `https://checkout.ebillett.no/` (domain-based, same reasoning as
    ODEON — see "ebillett.no (eBillett/DX)" above).
  - **NFkino** — `ticketSaleUrl` starts with `https://nfkino.no/`
    (domain-based, same reasoning — see "NFkino (Drupal + Vista)" above).
  - **Out-of-scope** — everything else.
  Only seat-check the Filmgrail, ODEON, ebillett.no, and NFkino groups in
  Step 3, each with its own script pair; this classification is what keeps
  any checkout script from ever being pointed at an unsupported cinema.
- Keep the out-of-scope list around (don't discard it) — Step 4 always
  mentions these, with their `ticketSaleUrl` as a manual-check link,
  whether or not any in-scope candidate matched. That applies to every
  out-of-scope cinema equally, including Bygdekinoen showings, which never
  even reach Step 3 (see "Known checkout platforms" above for why) — the
  user can still follow the link and check/book manually. Only skip Step 3
  entirely (no seat-checking at all) when there are **no in-scope
  candidates at all**, i.e. the film is only playing at out-of-scope
  cinemas.

## Step 3 — Seat-check every candidate

For **each** Filmgrail, ODEON, ebillett.no, or NFkino candidate (all of
them — this is deliberately thorough, not just a top-N subset), run the
script pair for that candidate's platform.

**Filmgrail candidates:**

```bash
python3 scripts/filmgrail_checkout.py "<ticketSaleUrl>" --count <N>
```

This drives the checkout API directly over HTTP (no browser needed — see
`scripts/filmgrail_checkout.py`'s module docstring and the design spec's
"Seat-map flow" section for how this was reverse-engineered and verified
live). It prints one JSON object to stdout and always attempts to cancel
the transaction it opens, even on error — never leaves one dangling:

```json
{"status": "ok"|"error", "seats": [...] | null, "error": "..."|null,
 "cancelStatus": "cancelled"|"failed"|"not_created"}
```

1. Run the command above and parse its stdout JSON.
2. If `status` is `"error"`: this is a genuine failure (network issue,
   page shape changed, ticket category unavailable), not "sold out" — the
   API doesn't reject `setTickets` for a fully-booked room, it just returns
   zero available seats at the seatmap step, which the matcher below
   naturally reports as no match. Skip this candidate but don't silently
   swallow the error — note it for the final report.
3. If `cancelStatus` is `"failed"`, **do not** silently move on — flag this
   explicitly for the final report (time, room, and the `error` field),
   the same as a dangling transaction would warrant. `"not_created"` is
   fine and expected whenever `status` is `"error"` at the `setTickets`
   stage (no transaction ever opened, so there was nothing to cancel).
4. Continue with the shared matcher step below.

**ODEON candidates:**

```bash
python3 scripts/odeon_checkout.py "<ticketSaleUrl>"
```

This reads the seatmap directly from ODEON's Cinema API backend (no
`--count` — see "ODEON (Cinema API)" above). Purely read-only: no
transaction or hold is ever opened, so there is no cancel step and no
`cancelStatus` field at all:

```json
{"status": "ok"|"error", "seats": [...] | null, "error": "..."|null}
```

1. Run the command above and parse its stdout JSON.
2. If `status` is `"error"`, note it for the final report and skip this
   candidate — no cleanup is needed (nothing was ever opened).
3. Continue with the shared matcher step below.

**ebillett.no candidates:**

```bash
python3 scripts/ebillett_checkout.py "<ticketSaleUrl>" --count <N>
```

This drives the real ebillett.no checkout flow directly over HTTP (no
browser — see "ebillett.no (eBillett/DX)" above and
`scripts/ebillett_checkout.py`'s module docstring for exactly how). It
always attempts a cancel, but unlike Filmgrail's, that cancel is **not**
confirmed to actually release the hold immediately (see above) — the real
safety net is ebillett.no's own ~1-minute auto-expiry:

```json
{"status": "ok"|"error", "seats": [...] | null, "error": "..."|null,
 "cancelStatus": "attempted"|"failed"|"not_created"}
```

1. Run the command above and parse its stdout JSON.
2. If `status` is `"error"`, note it for the final report and skip this
   candidate.
3. If `cancelStatus` is `"failed"`, flag it for the final report same as
   Filmgrail's — a genuine failure to even *send* the cancel request is
   worth surfacing, even though `"attempted"` itself isn't a strong
   guarantee either. `"not_created"` is fine and expected whenever
   `status` is `"error"` before a reservation existed.
4. Continue with the shared matcher step below.

**NFkino candidates:**

```bash
python3 scripts/nfkino_checkout.py "<ticketSaleUrl>" --count <N>
```

This drives the real NFkino checkout flow directly over HTTP (no browser —
see "NFkino (Drupal + Vista)" above and `scripts/nfkino_checkout.py`'s
module docstring for exactly how). It always attempts cleanup, but like
ebillett.no's, that cleanup is **not** confirmed to actually release the
hold immediately — the real safety net is NFkino's own ~10-minute
order countdown:

```json
{"status": "ok"|"error", "seats": [...] | null, "error": "..."|null,
 "cancelStatus": "attempted"|"failed"|"not_created"}
```

1. Run the command above and parse its stdout JSON.
2. If `status` is `"error"`, note it for the final report and skip this
   candidate — this also covers general admission screenings (no seatmap
   to check at all), which report the same way.
3. If `cancelStatus` is `"failed"`, flag it for the final report same as
   ebillett.no's. `"not_created"` is fine and expected whenever `status`
   is `"error"` before an order existed.
4. Continue with the shared matcher step below.

**Shared final step, any platform:** if `status` is `"ok"`, pipe `seats`
into that platform's own matcher — `filmgrail_zone_match.py` for Filmgrail
candidates, `odeon_zone_match.py` for ODEON candidates,
`ebillett_zone_match.py` for ebillett.no candidates, `nfkino_zone_match.py`
for NFkino candidates (identical CLI shape across all four):

```bash
python3 scripts/filmgrail_zone_match.py --count <N> \
  [--zone-row front|middle|back] [--zone-col left|center|right] \
  <<< '<seats JSON array>'
```

Record whether `matched` is `true` for this showtime. Then **pause a few
seconds** before moving to the next candidate — Filmgrail's, ebillett.no's,
and NFkino's are all real production checkout systems (not read-only), so
never fire candidates back-to-back; ODEON's read-only check doesn't
strictly need the same pause for correctness, but keep it anyway as a
default courtesy to someone else's production API.

## Step 4 — Report results

Present a ranked list (by `showStart`, ascending) of every showtime that
matched, each with: time, room (`screenName`), cinema (`theaterName`),
`ticketSaleUrl` for the user to complete booking themselves, and the actual
matched seat labels — build these from the matcher's `matches[].row`
entry's `rowSymbol` plus each matched seat's `columnSymbol` (e.g. "Row 5,
seats 10-12"). Mention the total checked vs. matched count for context (e.g.
"6 showings today, 2 have room for 3 in the back"). If none matched, say so
plainly and mention which showtimes exist today regardless, in case the user
wants to relax their zone preference. If Step 3 flagged a genuine
cleanup-failure for a matched showtime, mention it as a plain, brief
caveat next to that showtime — e.g. "heads up, the hold I placed to check
this one may not have released instantly, but it expires on its own
shortly" — never as a raw status value, and never for a Filmgrail showtime
where cleanup is confirmed fine or an ODEON one (nothing was ever held
there). The same caveat applies to ebillett.no and NFkino alike — neither
platform's `cancelStatus: "attempted"` means "cancelled".

If Step 2 found any out-of-scope candidates for this film (any cinema
seat-checking doesn't cover, Bygdekinoen included), always mention them
too, each with its `ticketSaleUrl` as a manual-check link, so the user
knows those options exist even though this skill can't check their seats:
- If there were **no** in-scope matches at all, lead with this — it's the
  whole answer, not a footnote, and matters more than a bare "no matches."
- If there **were** in-scope matches, add it after the ranked list as a
  secondary "also playing at (not seat-checkable)" note rather than the
  headline.

**Never** proceed to actually purchasing tickets or entering payment
details — this skill's job ends at reporting viable showtimes.
