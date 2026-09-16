# cinema-seat-finder — design spec

## Purpose

Let a user ask, in natural language, "N of us want to see [film] today, ideally
seated [front/middle/back] and [left/center/right]" and get back a ranked list
of today's Trondheim Kino showtimes that actually have N contiguous available
seats in that zone — instead of manually clicking through film → date → time →
seat count → seatmap for every candidate showing.

This is a Claude Code **Skill**: a markdown instruction set that Claude follows
at invocation time, using its own Bash and browser-automation tools. It is not
a standalone script or service.

## Non-goals (v1)

- No support for cinema chains other than Trondheim Kino. Other Norwegian
  chains listed on Filmweb are not confirmed to run the same Filmgrail/Mars
  booking platform, and generalizing now means designing against flows we
  haven't verified.
- No multi-day search by default (today only; user can explicitly ask for a
  different date and the skill substitutes it into the same queries).
- The skill never completes a purchase. It stops at "here are your viable
  showtimes and their booking links" — the user does the actual checkout
  themselves.
- No persistent state, caching, or scheduling. Each invocation is a fresh,
  self-contained run.

## Background (already reverse-engineered, see project memory)

- **Discovery API**: `https://movieinfoqs.filmweb.no/graphql` is a public,
  unauthenticated, introspectable GraphQL API. `showQuery.getShows(location,
  date, movieTitle)` returns real showtimes with `movieTitle, showStart,
  screenName, theaterName, firmName, ticketSaleUrl`. No seat/capacity data.
- **Seat-map flow (Trondheim Kino / Filmgrail)**: opening a `ticketSaleUrl`,
  selecting a ticket quantity, and clicking through triggers
  `POST /api/ExecuteApiMethod?blockName=TicketsCategories&methodName=setTickets`,
  which creates a server-side transaction (UUID) and returns
  `nextStep: /checkout/seatmap/<transactionId>`. That URL returns a JSON
  envelope `{master, pageTitle, html}` where `html` is a large server-rendered
  fragment. It renders the seat grid as SVG client-side via a compiled Vue
  component, **but that same `html` string also embeds the real per-seat data
  as a URL-encoded JSON array** at JSON-path `seats.seatmap` — one object per
  seat, e.g. `{"id":"0","rowSymbol":"1","row":0,"columnSymbol":"10",
  "column":4,"state":"booked","type":"","seatCode":"1"}` (`state` is
  `"available"` or `"booked"`; `type` is `""` for standard seats or `"WC"`
  for wheelchair spots; `row`/`column` are clean 0-based grid indices). This
  is the real seat data source — see Step 2 below — and means the DOM/SVG
  rendering never actually needs to be parsed. Abandoning the flow fires
  `methodName=cancel`.

## Architecture

```
User invokes skill with: film title, party size N, zone preference
        │
        ▼
Step 1: Discovery (Bash/curl only)
  curl movieinfoqs.filmweb.no/graphql → showQuery.getShows(...)
  → list of {showStart, screenName, theaterName, ticketSaleUrl}
        │
        ▼
Step 2: Seat-check loop (claude-in-chrome), once per candidate showtime
  a. navigate to ticketSaleUrl
  b. patch window.fetch to capture the checkout/seatmap response body
     (after navigation, so the patch survives on the loaded page)
  c. select N adult tickets, click Neste (→ creates transaction, fires the
     checkout/seatmap request our patch captures)
  d. extract the seats.seatmap JSON array from the captured response body
     (URL-decode + JSON.parse a bracket-matched segment; see Step 2 below)
  e. scan requested zone (thirds of row/column index range) for N seats
     with consecutive `column` values and state "available"
  f. fire methodName=cancel to release the transaction
  g. record match / no-match (+ which row matched, if any)
  short delay before next candidate
        │
        ▼
Step 3: Report ranked list of matching showtimes to the user
```

## Step 1 — Discovery

Plain `curl` POST to `movieinfoqs.filmweb.no/graphql`:

```graphql
{
  showQuery {
    getShows(location: "Trondheim", date: "YYYY-MM-DD", movieTitle: "...") {
      showStart
      screenName
      theaterName
      ticketSaleUrl
    }
  }
}
```

`date` defaults to today (system date) unless the user specifies otherwise.
`movieTitle` match should be treated loosely (the skill should confirm the
closest matching title against the returned list if the user's phrasing
doesn't match exactly — e.g. list distinct movie titles for the day first if
there's ambiguity, rather than silently guessing).

## Step 2 — Seat-check per candidate

This is the expensive half and runs once per candidate showtime returned by
Step 1. Per the user's explicit choice, **every** matching showtime is
checked (not just a top-N subset) — the skill should proceed through the full
candidate list.

### Driving the flow

Use claude-in-chrome tools exactly as manually verified:
1. `navigate` to the candidate's `ticketSaleUrl`.
2. Patch `window.fetch` (via `javascript_tool`) to capture the response body
   of any request whose URL includes `checkout/seatmap`. This must happen
   *after* navigation — patching first would have the patch wiped out by
   the navigation, since it replaces the page (and its JS globals) entirely.
3. Select N "Voksen" (adult) tickets via the ticket-category `+` control.
4. Click "Neste" → this fires `setTickets`, creates the transaction, and
   triggers the `checkout/seatmap/<transactionId>` request our patch
   captures (the modal also renders visually, but we don't need to parse
   what it renders).
5. Extract the seat array from the captured response body (see below).
6. Regardless of match outcome, close the modal / trigger the abandon
   confirmation so `methodName=cancel` fires — **never leave a transaction
   dangling**. This must happen even if extraction throws an error (wrap in
   try/finally logic at the instruction level: always attempt cleanup).
7. Add a short pause (a few seconds) before moving to the next candidate —
   this is a real cinema's checkout backend, not a read-only API; don't
   hammer it with back-to-back transaction creation.

### Extraction (parse the embedded JSON, not the DOM)

**Confirmed 2026-09-16 against a live Trondheim Kino seatmap** (Spider-Man:
Brand New Day, Nova 5): the `checkout/seatmap/<transactionId>` response body
is `{master, pageTitle, html}` where `html` — a large server-rendered
fragment, ~130KB — embeds the real seat data as **URL-encoded JSON**, one
object per seat, at JSON-path `seats.seatmap`:

```json
{"id":"0","width":20,"height":20,"coordX":106,"coordY":0,"rowSymbol":"1","row":0,"columnSymbol":"10","column":4,"state":"booked","type":"","seatCode":"1"}
```

`state` is the literal string `"available"` or `"booked"`. `type` is `""`
for standard seats or `"WC"` for wheelchair spots (a different ticket
category than the plain "Voksen" seats being searched for — exclude these).
`row`/`column` are clean 0-based grid indices; `rowSymbol`/`columnSymbol` are
the human-readable labels shown on screen. Verified live: decoding and
`JSON.parse`-ing the array produced a valid 90-element array whose `state`
counts (83 available / 7 booked) matched what was visible in the rendered
seatmap screenshot.

Extraction JS, run against the captured response text:

```js
function extractSeatmap(responseText) {
  const body = JSON.parse(responseText);
  const html = body.html;
  const anchor = html.indexOf('%22state%22');
  if (anchor === -1) throw new Error('seat state marker not found in seatmap response');
  let i = anchor;
  let depth = 0;
  while (i > 0) {
    if (html.slice(i, i + 3) === '%7D') depth++;
    if (html.slice(i, i + 3) === '%7B') { if (depth === 0) break; depth--; }
    i--;
  }
  // walk further back to the enclosing array's opening %5B
  let arrStart = i;
  while (arrStart > 0 && html.slice(arrStart - 3, arrStart) !== '%5B') arrStart--;
  arrStart -= 3;
  let j = arrStart, bracketDepth = 0;
  while (j < html.length) {
    if (html.slice(j, j + 3) === '%5B') bracketDepth++;
    if (html.slice(j, j + 3) === '%5D') { bracketDepth--; if (bracketDepth === 0) { j += 3; break; } }
    j++;
  }
  return JSON.parse(decodeURIComponent(html.slice(arrStart, j)));
}
```

This exact function (verbatim) was run live against three different rooms —
Nova 5 (90 seats, Spider-Man: Brand New Day), Prinsen 6 EPIQ (211 seats,
The Odyssey), and Prinsen 1 D-BOX — and correctly parsed all three. The
larger EPIQ room surfaced two more `type` values not seen in the smaller
one: `sofa_left`/`sofa_right` (paired recliner seats, 26 of each). Prinsen 1
D-BOX, however, showed that a hardcoded `type === ''` check for "standard
seat" is not reliable: that room's *standard* seats use `type: "test4"`
instead of `""`, so an empty-string filter would have produced a false
negative for every seat in the room. The shipped implementation
(`standard_seats` in `zone_match.py`) instead uses a **majority-vote rule**:
whichever `type` value is most common among a room's seats is treated as
the standard category, and everything else (wheelchair spots, paired
recliners, footstools, or whatever a room-specific code turns out to be) is
excluded as a minority special category. This keeps the same reasoning —
special categories are always a minority within a room — while working
correctly regardless of what string a given room happens to use for its
plain seats.

### Zone bucketing and adjacency (integer grid math, no heuristics)

Because `row`/`column` are already clean integer indices, no coordinate
clustering or gap-tolerance guessing is needed:
- Filter to standard seats (the room's majority `type` value — see
  Extraction above) before computing anything — wheelchair spots
  (`type === 'WC'`), paired recliners, and other minority categories are a
  different ticket category.
- Compute `minRow`/`maxRow` and `minColumn`/`maxColumn` across the standard
  seats; split each range into thirds → front/middle/back and
  left/center/right. This self-calibrates per room (Nova vs Prinsen, small
  vs large) with no per-room configuration.
- Within a row, sort seats by `column`. A run of N seats is contiguous if
  their `column` values are consecutive integers (difference of exactly 1)
  — no pitch/gap tolerance needed, since column numbering already reflects
  actual seat slots including any gaps (removed seats, aisles).
- A showtime "matches" if any row within the requested zone contains such a
  run of N seats all with `state === 'available'`.

## Step 3 — Output

A ranked list (ranked by start time, ascending) of showtimes that matched,
each showing: time, room name, cinema (Nova/Prinsen), and the `ticketSaleUrl`
for the user to complete booking themselves. Showtimes checked but not
matching should be omitted from the main list; optionally mention the count
checked vs matched for context (e.g. "6 showings today, 2 have room for 3 in
the back").

## Error handling

- If a candidate's ticket-category page doesn't have enough seats available
  in total (e.g. sold out before reaching the seatmap), skip it and note it
  as sold out rather than treating it as a tool failure.
- If the transaction/cancel step fails for any reason, surface that clearly
  rather than silently continuing — a dangling transaction on a real
  checkout system is worth flagging, not hiding.
- If Filmweb's `movieTitle` filter returns zero shows for the day, report
  that plainly (no showings today) rather than erroring.

## Testing / validation approach

Since this depends entirely on two live third-party systems (Filmweb GraphQL,
Filmgrail checkout), there's no meaningful offline unit-test story for v1.
Validation is: run the skill end-to-end against a real film/day with known
showtimes (as already done manually in this project's research), and confirm
its reported matches align with what's visible when checking the same
showtime's seatmap by hand in a browser.
