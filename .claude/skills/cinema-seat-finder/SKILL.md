---
name: cinema-seat-finder
description: "Find Trondheim Kino showtimes today with N contiguous available seats in a preferred zone (front/middle/back, left/center/right). Use when the user asks something like 'N of us want to see [film], ideally seated in the back' instead of manually checking each showtime's seatmap."
---

# cinema-seat-finder

Finds which of today's Trondheim Kino showtimes for a given film actually
have room for a group together in their preferred part of the room —
instead of the user manually clicking through film → time → seat count →
seatmap for every candidate showing.

**Scope:** Trondheim Kino only. Today's date only, unless the user
explicitly gives another date. Never completes a purchase — it only reports
which showtimes are viable and their booking links.

## Step 1 — Parse the request

Extract from the user's message:
- **Film title** (may be approximate/partial — disambiguate in Step 2).
- **Party size N** (integer).
- **Zone preference**: any combination of a row preference (`front`,
  `middle`, `back`) and a side preference (`left`, `center`, `right`). Either
  or both may be omitted (treat omitted as "any").
- **Date**: defaults to today (system date) unless the user specifies one —
  pass it as `YYYY-MM-DD` to the scripts below.

## Step 2 — Discover candidate showtimes

Run, from the project root:

```bash
python3 scripts/discover_shows.py --date <YYYY-MM-DD> --movie-title "<film title>"
```

- If the script exits with a non-zero status, or its stdout is not valid JSON
  (as opposed to a valid empty array `[]`), the discovery step itself failed
  — report that to the user (e.g. the API may be down or unreachable) rather
  than treating it the same as "no showings today."
- If this returns an empty array, retry **without** `--movie-title` for that
  date, and check whether any returned `movieTitle` looks like a fuzzy match
  for what the user asked for (titles are in Norwegian and may not match the
  user's exact wording). If you find a plausible match, confirm it with the
  user before proceeding. If nothing plausible exists, tell the user there
  are no showings of that film today and stop.
- Otherwise, you now have the full candidate list: each entry has
  `showStart`, `screenName`, `theaterName`, `firmName`, `ticketSaleUrl`.
- Before seat-checking any candidate, **skip** (do not seat-check) any
  candidate whose `firmName` is not exactly `"Trondheim Kino"`. This skill is
  scoped to that specific chain, and the discovery API's `location`-based
  query alone doesn't guarantee every result belongs to it — other venues
  could theoretically appear under the same city.

## Step 3 — Seat-check every candidate

For **each** candidate showtime (all of them — this is deliberately
thorough, not just a top-N subset), do the following using the
`claude-in-chrome` tools. Load them first if not already loaded:
`ToolSearch("select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__tabs_close_mcp,mcp__claude-in-chrome__read_page")`.

Get a tab via `tabs_context_mcp` (create one if needed), then for each
candidate:

1. **Navigate** to the candidate's `ticketSaleUrl`.
2. **Patch `window.fetch`** via `javascript_tool` to capture the seatmap
   response body before it's needed (this must run on the fresh page,
   before the click in step 4 below fires the request):

   ```js
   window.__seatmapCapture = null;
   const __origFetch = window.fetch;
   window.fetch = async function(...args) {
     const res = await __origFetch.apply(this, args);
     const url = typeof args[0] === 'string' ? args[0] : args[0].url;
     if (url.includes('checkout/seatmap')) {
       window.__seatmapCapture = await res.clone().text();
     }
     return res;
   };
   'patched';
   ```

3. **Select N adult ("Voksen") tickets**: the ticket-category "+" buttons
   have no accessible labels, but "Voksen" is consistently the first
   category listed on this page. Call `read_page` with
   `filter: "interactive"` — the first plain `button [ref_N]` that appears
   immediately after the `button "Søke"` entry is the "Voksen" row's `+`
   control. Click that same ref N times (once per ticket), taking a
   screenshot after each click to confirm the counter actually incremented.
   Ref-based clicking on this control has been observed to work only about
   half the time — if a click doesn't visibly move the counter, don't retry
   the ref blindly; fall back to a direct coordinate click on the visible
   "+" button instead. Do not trust raw screenshot pixel coordinates for
   that fallback click without first checking `window.innerWidth` /
   `window.innerHeight` via `javascript_tool`: the screenshot frame and the
   real viewport can use different pixel scales, which shifts where a
   coordinate click actually lands.
4. **Click "Neste"**. Wait ~2 seconds. This creates a checkout transaction
   and fires the `checkout/seatmap` request the patch above captures (the
   modal also renders visually — that's fine, just not what we're reading).
5. **Extract seat data** from the captured response by running this exact
   JavaScript via `javascript_tool` (see the design spec's "Extraction"
   section for how this was derived and verified against a real seatmap):

   ```js
   function extractSeatmap(responseText) {
     const body = JSON.parse(responseText);
     const html = body.html;
     const anchor = html.indexOf('%22state%22');
     if (anchor === -1) throw new Error('seat state marker not found in seatmap response');
     let i = anchor, depth = 0;
     while (i > 0) {
       if (html.slice(i, i + 3) === '%7D') depth++;
       if (html.slice(i, i + 3) === '%7B') { if (depth === 0) break; depth--; }
       i--;
     }
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
   window.__seats = extractSeatmap(window.__seatmapCapture).map(s => (
     {row: s.row, column: s.column, state: s.state, type: s.type, rowSymbol: s.rowSymbol, columnSymbol: s.columnSymbol}
   ));
   JSON.stringify({count: window.__seats.length, length: JSON.stringify(window.__seats).length});
   ```

   This drops fields `zone_match.py` doesn't use (`id`, `width`, `height`,
   `coordX`, `coordY`, `seatCode`) to keep the payload as small as possible,
   but keeps `columnSymbol` (one extra field per seat, cheap) alongside
   `rowSymbol` so Step 4 can report human-readable matched seat labels,
   and reports the reduced array's length in characters rather than dumping
   it — **do not** try to print the full JSON in one shot. The
   `javascript_tool`'s text result is truncated (observed consistently
   around 900–1000 characters, with a literal `[TRUNCATED]` marker appended)
   and every real seatmap tried during this skill's validation (29 and 59
   seats) exceeded that, silently losing data if fetched whole. Instead,
   pull it out in safe chunks and concatenate:

   ```js
   JSON.stringify(window.__seats).slice(<start>, <start + 800>)
   ```

   Starting at `0` and incrementing `<start>` by `800` each call until you
   reach `length` from the previous step (the last chunk will be shorter).
   Concatenate the chunks in order with the `Write` tool as you save to
   `<scratchpad>/seats-<showtime-id>.json`, then verify the file is valid
   JSON with the expected element `count` before running the matcher — a
   parse error or a mismatched count means a chunk boundary was fumbled;
   redo the affected chunk rather than guessing at seat data. If
   `window.__seatmapCapture` was still `null` when this step ran, the patch
   in step 2 didn't catch the request (e.g. it fired before the patch was
   installed) — re-run this candidate from step 1, but **first perform the
   cleanup step** (step 7 below: close the modal, confirm abandonment by
   clicking "Ja") exactly as you would for a normal completed check, since
   the "Neste" click in step 4 already created a server-side transaction
   even though extraction failed. Jumping straight back to step 1 would
   abandon that transaction without ever cancelling it.

6. **Run the matcher**:

   ```bash
   python3 scripts/zone_match.py --count <N> \
     [--zone-row front|middle|back] [--zone-col left|center|right] \
     < <scratchpad>/seats-<showtime-id>.json
   ```

   Record whether `matched` is `true` for this showtime.

7. **Always clean up**, regardless of whether it matched or step 5/6 errored:
   take a screenshot of the current tab (you need one anyway to sanity-check
   the seatmap), locate the small "X" close icon at the top-right corner of
   the modal box itself (not the browser viewport corner — the modal is
   centered and its top-right moves with its size), and click it at that
   observed position. A confirmation dialog titled "Avslutt kjøpet?" then
   appears asking "Er du sikker på at du vil avslutte kjøpet?" with two
   buttons, "Ja" and "Avbryt" — take another screenshot and click "Ja" to
   confirm abandoning the transaction (this is what releases it
   server-side; "Avbryt" would cancel the *close*, i.e. keep the
   transaction open — do not click it here). Do not skip this step on
   error — if extraction or matching failed, still perform this cleanup
   before moving to the next candidate. If this cleanup sequence itself
   fails, or you cannot confirm the transaction was actually released (e.g.
   the modal doesn't close, "Ja" has no visible effect, or a fresh reload of
   the ticketSaleUrl still shows lingering "Dine seter" state), **do not**
   silently move on — report this explicitly to the user as a flagged issue
   for that specific showtime (time, room, and what was observed) alongside
   the final results.
8. **Pause a few seconds** before moving to the next candidate showtime —
   this is a real production checkout system, not a read-only API.

If a candidate's ticket-category page shows the room is already sold out
before you can even reach the seatmap (e.g. the "+" control for Voksen is
disabled or an error appears), record it as sold out and move on rather
than treating it as a failure.

## Step 4 — Report results

Present a ranked list (by `showStart`, ascending) of every showtime that
matched, each with: time, room (`screenName`), cinema (`theaterName`),
`ticketSaleUrl` for the user to complete booking themselves, and the actual
matched seat labels — build these from `zone_match.py`'s `matches[].row`
entry's `rowSymbol` plus each matched seat's `columnSymbol` (e.g. "Row 5,
seats 10-12"). Mention the total checked vs. matched count for context (e.g.
"6 showings today, 2 have room for 3 in the back"). If none matched, say so
plainly and mention which showtimes exist today regardless, in case the user
wants to relax their zone preference. Also surface any flagged
cleanup-failure issues from Step 3 alongside the results.

**Never** proceed to actually purchasing tickets or entering payment
details — this skill's job ends at reporting viable showtimes.
