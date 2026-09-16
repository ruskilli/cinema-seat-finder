---
name: cinema-seat-finder
description: "List today's showtimes at ANY Norwegian cinema (nationwide or a named town), look up/resolve a town or cinema by name, look up a movie's synopsis/genre/runtime/age rating, or find N contiguous available seats in a preferred zone (front/middle/back, left/center/right) at Trondheim Kino, Steinkjer kino, Kimen kino (Stjørdal), Haugesund kino, Caroline kino (Kristiansund), Aurora Kino (Tromsø/Narvik/Alta/Kirkenes/Lakselv), ODEON Kino (any city, e.g. Oslo/Stavanger/Sandnes/Ålesund/Skien/Moss/Lillestrøm/Sandvika/Ski/Sotra), any ebillett.no venue (~65 mostly small independent theaters nationwide), or any NFkino venue (Arendal, Farsund, Drammen, Kristiansand, Asker, Askim, Halden, Horten, Hønefoss, Tønsberg, Oslo, Sarpsborg, Verdal, Bergen/Lagunen, and more) - the only cinemas seat-checking is supported for. Use when the user asks something like 'N of us want to see [film], ideally seated in the back', 'what's playing tonight' / 'what movies are on today [in <town>]', 'is there a cinema in <town>' / 'what towns do you cover', or 'what's [film] about' / 'how long is [film]' / 'what age rating is [film]'."
---

# cinema-seat-finder

*Listing* what's on, and *looking up* towns/cinemas/movies, works nationwide
via Filmweb's public API. *Seat-finding* (checking real seat availability
for a named film) only works for four checkout platforms — Filmgrail/Mars,
ODEON, ebillett.no, and NFkino; see `references/platforms.md` for exactly
which cinemas and how each is classified — say so plainly if a film is
only playing somewhere else, rather than silently returning nothing.
Today's date only, unless the user gives another date. Never completes a
purchase — only reports viable showtimes and their booking links.

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
with correct Norwegian diacritics (confirmed live: "Tromso" returns
nothing, "Tromsø" works):

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

For a general "what towns/cinemas do you cover" question, read
`references/platforms.md` and answer from its table — Filmgrail is a fixed
cinema list, ODEON/ebillett.no/NFkino each cover any city/venue on their
platform, not a fixed list — and make clear that's narrower than
*listing*, which covers every cinema nationwide.

For a specific town (e.g. "is there a cinema in Ålesund"), resolve it per
**Resolving a location** above, then run:

```bash
python3 scripts/discover_shows.py --location "<resolved town>" --list-cinemas
```

This lists the cinema *buildings* Filmweb knows about there (e.g.
`[{"name": "Nova", "firmId": 12}, {"name": "Prinsen", "firmId": 12}]` for
Trondheim). Report the building names plainly, and note whether that town
is seat-finding-supported per `references/platforms.md`. An empty array
means no cinema found for that resolved town — say so.

### Movie info query

Resolve the title to a Filmweb movie id first:

```bash
python3 scripts/discover_shows.py --search-movie "<film title as the user typed it>"
```

- Exactly one plausible result → use its `mainVersionId`.
- Several results → titles are frequently reused/similar (e.g. searching
  "Fjord" also returns "Storfjord 1829", "Deilig er fjorden", etc.) — pick
  the one whose `title` matches what the user asked for; if more than one
  is plausible, confirm with the user before proceeding, the same as Step
  2's fuzzy-title handling for seat-finding.
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
Filmweb returns, any chain, since this is purely informational. The same
error handling as Step 2 applies: a non-zero exit, or stdout that isn't
valid JSON, means discovery itself failed — report that rather than
"nothing playing today."

Group the results by `movieTitle` and present each film with its showtimes
(time, `screenName`, `theaterName`, and — since results may now span many
towns/chains — `firmName` too whenever it isn't already obvious from
`theaterName`), sorted by start time. Include each showtime's
`ticketSaleUrl` as a booking link whenever it's non-empty — this applies
to *every* cinema listed, not just the seat-finding-supported ones: the
user can always follow the link and check/book manually, so don't
withhold it just because this skill can't check it itself. Stop here — do
not seat-check anything unless the user follows up naming a film and
party size. (If they do, and that film turns out to only be playing at
out-of-scope cinemas, Step 2/4 below handles saying so plainly rather than
reporting no matches.)

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

Same `--exclude-past` rule as **Listing request** above.

- If the script exits with a non-zero status, or its stdout is not valid JSON
  (as opposed to a valid empty array `[]`), the discovery step itself failed
  — report that to the user rather than treating it the same as "no
  showings today."
- If this returns an empty array, retry **without** `--movie-title` (same
  location and date), and check whether any returned `movieTitle` looks
  like a fuzzy match for what the user asked for (titles are in Norwegian
  and may not match the user's exact wording). If you find a plausible
  match, confirm it with the user before proceeding. If nothing plausible
  exists, tell the user there are no showings of that film today (in that
  town, if one was given) and stop.
- Otherwise, classify each candidate against `references/platforms.md`'s
  table (`firmName` for Filmgrail, `ticketSaleUrl` domain for the other
  three) — everything else is out-of-scope. Only seat-check in-scope
  candidates in Step 3.
- Keep the out-of-scope list around (don't discard it) — Step 4 always
  mentions these, with their `ticketSaleUrl` as a manual-check link,
  whether or not any in-scope candidate matched. Only skip Step 3 entirely
  (no seat-checking at all) when there are **no in-scope candidates at
  all**, i.e. the film is only playing at out-of-scope cinemas.

## Step 3 — Seat-check every candidate

For **each** in-scope candidate (all of them — this is deliberately
thorough, not just a top-N subset), run that platform's checkout script:

```bash
python3 scripts/filmgrail_checkout.py "<ticketSaleUrl>" --count <N>
python3 scripts/odeon_checkout.py "<ticketSaleUrl>"                 # no --count - read-only
python3 scripts/ebillett_checkout.py "<ticketSaleUrl>" --count <N>
python3 scripts/nfkino_checkout.py "<ticketSaleUrl>" --count <N>
```

Each prints one JSON object to stdout:
`{"status": "ok"|"error", "seats": [...]|null, "error": "..."|null[, "cancelStatus": "..."]}`
(the `cancelStatus` field and its possible values are per-platform — see
`references/platforms.md`; ODEON never has it at all).

1. Parse the JSON.
2. `status: "error"` is a genuine failure (network issue, page shape
   changed, ticket category unavailable), **not** "sold out" — a fully
   booked room just returns zero available seats at the matcher step
   below, which naturally reports no match. Skip this candidate but note
   the error for Step 4.
3. Where `cancelStatus` is present and `"failed"`, flag it for Step 4 too
   — a genuine failure to even *send* the cleanup request is worth
   surfacing, even though `"attempted"` itself isn't a strong guarantee
   either. `"not_created"` is fine and expected whenever `status` is
   `"error"` before a hold ever existed.
4. If `status` is `"ok"`, pipe `seats` into that platform's own matcher
   (identical CLI shape across all four — swap the script name to match
   the candidate's platform):

```bash
python3 scripts/filmgrail_zone_match.py --count <N> \
  [--zone-row front|middle|back] [--zone-col left|center|right] \
  <<< '<seats JSON array>'
```

Record whether `matched` is `true` for this showtime. Then **pause a few
seconds** before moving to the next candidate — Filmgrail, ebillett.no,
and NFkino all open real holds on production checkout systems, so never
fire candidates back-to-back; ODEON's read-only check doesn't strictly
need the same pause for correctness, but keep it anyway as a default
courtesy to someone else's production API.

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
(cleanup confirmed fine) or an ODEON one (nothing was ever held there).

If Step 2 found any out-of-scope candidates for this film, always mention
them too, each with its `ticketSaleUrl` as a manual-check link, so the
user knows those options exist even though this skill can't check their
seats:
- If there were **no** in-scope matches at all, lead with this — it's the
  whole answer, not a footnote, and matters more than a bare "no matches."
- If there **were** in-scope matches, add it after the ranked list as a
  secondary "also playing at (not seat-checkable)" note rather than the
  headline.

**Never** proceed to actually purchasing tickets or entering payment
details — this skill's job ends at reporting viable showtimes.
