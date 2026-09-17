# cinema-seat-finder

![cinema-seat-finder](docs/assets/cinema-seat-finder.png)

A Claude Code skill that lists today's showtimes at *any* Norwegian cinema
— nationwide, or narrowed to a town you name — and, for a given film, finds
which showtimes at Trondheim Kino, Steinkjer kino, Kimen kino (Stjørdal),
Haugesund kino, Caroline kino (Kristiansund), Aurora Kino (Tromsø, Narvik,
Alta, Kirkenes, Lakselv), ODEON Kino (any city), any ebillett.no venue
(~65 mostly small independent theaters nationwide), or any NFkino venue
actually have room for a group together in their preferred part of the
room — instead of manually clicking through film → time → seat count →
seatmap for every candidate showing.

Ask something like:

> 3 of us want to see Spider-Man tonight, ideally seated in the back

and get back a ranked list of showtimes that genuinely have N contiguous
available seats in that zone, with booking links to finish checkout
yourself. The skill never completes a purchase.

Or, if you don't know what's on yet:

> what's playing tonight?
> what's on in Bergen this weekend?

and get back the lineup with showtimes — nationwide, or just that town —
no seat-checking involved. You can also ask about towns/cinemas themselves:

> is there a cinema in Ålesund?

or about a film itself, no showtimes involved:

> what's Fjord about?
> how long is Fjord, and what's the age rating?

Listing, location lookups, and movie info cover every Norwegian cinema (and
every film) Filmweb knows about; seat-finding only works for the four
platforms behind the chains named above (ten Filmgrail cinemas, any ODEON
city, any ebillett.no venue, or any NFkino venue) — see Scope below for
why, and the skill says so plainly if a film you ask about is only playing
somewhere seat-checking isn't supported.

## See it in action

A real conversation, start to finish — location lookup, listing, movie
info, then seat-finding:

<table>
<tr>
<td width="50%">

**"Are there any cinemas nearby?"**

![Location lookup](docs/assets/demo-1-location.png)

</td>
<td width="50%">

**"What's on tomorrow?"**

![Listing showtimes](docs/assets/demo-2-listing.png)

</td>
</tr>
<tr>
<td width="50%">

**"Tell me more about Harila"**

![Movie info](docs/assets/demo-3-movie-info.png)

</td>
<td width="50%">

**"Room for 4, front and center?"**

![Seat-finding](docs/assets/demo-4-seat-finding.png)

</td>
</tr>
</table>

All of Filmweb's data is in Norwegian, so the skill works natively in
Norwegian too — a full session, unprompted, in one screenshot:

<details>
<summary>Full conversation in Norwegian (click to expand)</summary>

![A complete conversation in Norwegian, covering a location lookup, listing, movie info, and seat-finding](docs/assets/demo-5-norwegian-session.png)

</details>

## How to use this skill

Open Claude Code with this repo as (or inside) the working directory, so it
can discover `.claude/skills/cinema-seat-finder/SKILL.md`. Then either:

- Just ask in natural language — Claude will invoke the skill automatically
  when your request matches, e.g. *"3 of us want to see Spider-Man tonight,
  ideally seated in the back"*.
- Invoke it explicitly with `/cinema-seat-finder <your request>`.

This skill handles four kinds of requests:

**"What's on" — just want to see the lineup, no film picked yet:**

Ask something like *"what's playing tonight"* or *"what movies are on today
in Bergen"*. Claude lists every film showing today with its showtimes and a
booking link, across every cinema Filmweb knows about — nationwide by
default, or just the town you named — including cinemas seat-checking
doesn't cover (Bygdekinoen, ODEON's non-seat-checkable siblings, and so
on): you still get the link to check/book those yourself. No
seat-checking is done for this.

**Location lookups — asking about towns/cinemas, not showtimes:**

Ask something like *"is there a cinema in Ålesund"* or *"what towns do you
cover"*. Claude resolves the town (handles typos/partial names against
Filmweb's own location index) and lists the actual cinema buildings there,
or explains the seat-finding-supported list if you're asking in general.

**Movie info — asking about a film itself, not showtimes or seats:**

Ask something like *"what's Fjord about"* or *"how long is Fjord"*. Claude
resolves the title (disambiguating if there are several plausible matches)
and answers from Filmweb's own data — synopsis, genre, runtime, age
rating, premiere date, Filmweb's own user rating. All of Filmweb's text is
Norwegian; Claude translates unless you're asking in Norwegian yourself.
No showtimes or seat-checking here — that's a separate request.

**Seat-finding — you know the film and need seats together:**

Include in your request:
- **Film title** — approximate is fine (e.g. "Spider-Man"); Claude will
  confirm the closest match if it's ambiguous.
- **Party size** — how many seats you need together.
- **Zone preference** (optional) — any of `front`/`middle`/`back` and
  `left`/`center`/`right`. Omit either or both for "anywhere".
- **Date** (optional) — defaults to today.
- **Town** (optional) — narrows the search; without one, Claude checks
  nationwide but only ever seat-checks the supported cinemas (the ten
  Filmgrail ones, any ODEON city, any ebillett.no venue, or any NFkino
  venue).

Claude will check every showtime for that film today (not just the first
one that works) and report back a ranked list of the ones with room for
your group, each with the actual seat labels and a booking link — you
complete the purchase yourself. If nothing matches your zone preference,
it'll tell you what else is playing today so you can decide whether to
relax it. If the film is also playing at cinemas outside the supported
ones, those get listed too with a booking link to check manually — as the
whole answer if that's the only place it's playing, or as a secondary note
alongside real matches otherwise.

## Using this in other agentic environments

The skill itself is just a markdown playbook
(`.claude/skills/cinema-seat-finder/SKILL.md`) that orchestrates plain
Python scripts — nothing about it is Claude-specific. See
[`docs/other-agents.md`](docs/other-agents.md) for how to run it from
GitHub Copilot, Gemini CLI, or any other coding agent.

## Scope

**Listing and location lookups are nationwide** — `discover_shows.py`
queries Filmweb directly, which aggregates every Norwegian cinema
regardless of checkout vendor, so these aren't limited to any particular
chain.

**Seat-finding is limited to four checkout platforms**, each requiring its
own reverse-engineered client since none of them share a common API:

- **Filmgrail/Mars** (`filmgrail_checkout.py` + `filmgrail_zone_match.py`)
  — ten cinemas sharing one checkout API: Trondheim Kino, Steinkjer kino,
  Kimen kino, Haugesund kino, Caroline kino Kristiansund, Aurora Kino's
  Tromsø/Narvik/Alta/Kirkenes/Lakselv locations, Setermoen kino, and
  Bergen kino (whose seatmap uses a different coordinate shape that the
  script normalizes internally — see its module docstring).
- **ODEON** (`odeon_checkout.py` + `odeon_zone_match.py`) — any ODEON
  city. ODEON's own site is behind an active Cloudflare challenge, so
  this reads from its separate, genuinely open `services.cinema-api.com`
  backend instead — purely read-only, no transaction ever opened.
- **ebillett.no/DX** (`ebillett_checkout.py` + `ebillett_zone_match.py`)
  — any of the ~65, mostly small independent theaters on that platform.
  No bot protection at all; opens a real reservation per check, with a
  best-effort (not confirmed-instant) cleanup — the real safety net is
  its own ~1-minute auto-expiry, so `cancelStatus` says `"attempted"`,
  never `"cancelled"`.
- **NFkino** (`nfkino_checkout.py` + `nfkino_zone_match.py`) — NFkino's
  independent cinemas (Arendal, Kristiansand, Oslo, Bergen/Lagunen, and
  more). Same no-bot-protection story as ebillett.no, and the same
  cleanup caveat — real safety net is its own ~10-minute order countdown.

Filmgrail and ODEON were confirmed to be dead ends for two very different
reasons: Bygdekinoen's screenings have unnumbered, unreserved seating (no
seatmap exists at all, regardless of vendor), while ebillett.no and NFkino
looked like dead ends at first (different vendor entirely) but turned out
to be their own separately supported platforms instead.

Every checkout script's own module docstring has the full
reverse-engineering trail (exact HTTP payloads, what was tried and
confirmed live) for its platform; `.claude/skills/cinema-seat-finder/SKILL.md`
and its `references/platforms.md` have the classification rules actually
used at runtime. Today's date only, unless another date is given
explicitly.

## Public APIs only

Every script here only ever talks to endpoints that answer a plain,
unauthenticated HTTP request the same way they would for anyone opening
that URL in a browser — no login, no session, no defeating a security
control. Concretely:

- **`www.odeonkino.no` is never contacted.** It returns an active
  Cloudflare bot-challenge (`cf-mitigated: challenge`) to every plain
  request, on every page, not just checkout — a clear "no scripted access"
  signal this project respects. `odeon_checkout.py` gets everything it
  needs from `services.cinema-api.com` instead, a separate backend that
  genuinely has no such protection.
- **`checkout.ebillett.no` and `nfkino.no` have no bot protection to
  respect or bypass, either.** Confirmed by extensive live testing during
  development — the only real obstacle for either was learning the
  correct payload shape, not any defensive control.
- **A non-default User-Agent header is not evasion.** `filmgrail_checkout.py`
  and `odeon_checkout.py` send `User-Agent: Mozilla/5.0` because some of
  these APIs reject the bare default string a scripting library sends
  (`Python-urllib/3.x`) — the same treatment they'd give any unrecognized
  client, confirmed live by comparing identical requests with and without
  it. That's ordinary HTTP courtesy, not spoofing a browser to get past
  something designed to keep scripts out.

Each checkout script's cleanup story (guaranteed vs. best-effort) is
covered per platform in Scope above.

If a future chain's data isn't reachable this way — genuine auth required,
or an active challenge on the data itself rather than just the storefront
— it doesn't get a script here.

## How it works

1. **Discovery** — `scripts/discover_shows.py` queries Filmweb's public
   GraphQL API for today's showtimes matching the requested film (or every
   film, for a listing request), nationwide or in a named town. The same
   script also resolves/searches town names (`--search-location`) and lists
   cinema buildings in a town (`--list-cinemas`), and resolves/fetches movie
   info — synopsis, genre, runtime, age rating, premiere date, user rating
   (`--search-movie` then `--movie-id`) — all against the same live API. A
   nationwide result can run into the hundreds of shows, so
   `scripts/group_showtimes.py` (for listing requests) and
   `scripts/classify_candidates.py` (for seat-finding requests) do the
   grouping/sorting/platform-classification in code rather than leaving
   Claude to do it by hand over a large result.
2. **Seat-check** — for a Filmgrail candidate, `scripts/filmgrail_checkout.py`
   drives the Filmgrail/Mars checkout flow directly over HTTP (select N
   tickets → open a transaction → read the seatmap → cancel the
   transaction), with no browser involved. For an ODEON candidate,
   `scripts/odeon_checkout.py` reads the seatmap straight from ODEON's
   Cinema API backend instead — no transaction or hold, purely read-only.
   For an ebillett.no candidate, `scripts/ebillett_checkout.py` drives that
   platform's own setup → POST → `302` redirect → seatmap flow, opening a
   real reservation and sending a best-effort (not confirmed-effective)
   cancel. For an NFkino candidate, `scripts/nfkino_checkout.py` drives
   that platform's order-creation → add_tickets → structured-seatmap flow,
   with the same kind of best-effort cleanup — see Scope above for both.
   `SKILL.md` classifies each candidate (`firmName` for Filmgrail,
   `ticketSaleUrl` domain for ODEON, ebillett.no, and NFkino) and calls the
   matching script — see Scope above for why each platform needs different
   logic.
3. **Zone matching** — `scripts/filmgrail_zone_match.py`,
   `scripts/odeon_zone_match.py`, `scripts/ebillett_zone_match.py`, or
   `scripts/nfkino_zone_match.py` (matched to the candidate's platform)
   scans the extracted seatmap for N contiguous available seats in the
   requested front/middle/back and left/center/right zone.

All of this is orchestrated by
`.claude/skills/cinema-seat-finder/SKILL.md`, which Claude follows when the
skill is invoked — this repo has no standalone entry point or service.

## Scripts

Run these from the project root.

```bash
# Discover today's showtimes for a film (nationwide - --location "" is
# explicit nationwide; omitting --location defaults to "Trondheim" only)
python3 scripts/discover_shows.py --date 2026-09-16 --location "" --movie-title "Spider-Man"

# Resolve/search a town name against Filmweb's own location index
python3 scripts/discover_shows.py --search-location "berg"
# -> ["Bergen", "Kongsberg", "Rødberg", "Tønsberg"]

# List the cinema buildings in a town
python3 scripts/discover_shows.py --location "Trondheim" --list-cinemas
# -> [{"name": "Nova", "firmId": 12}, {"name": "Prinsen", "firmId": 12}]

# Resolve a movie title to Filmweb movie ids
python3 scripts/discover_shows.py --search-movie "Fjord"
# -> [{"title": "Fjord", "mainVersionId": "EDI20260087"}, ...]

# Fetch full movie info (synopsis, genre, runtime, age rating, ...)
python3 scripts/discover_shows.py --movie-id "EDI20260087"

# Group a nationwide listing by film instead of a flat list of shows
python3 scripts/discover_shows.py --date 2026-09-16 --location "" | python3 scripts/group_showtimes.py

# Classify a film's candidate showtimes by seat-finding platform instead
# of checking each one by hand
python3 scripts/discover_shows.py --date 2026-09-16 --location "" --movie-title "Spider-Man" | python3 scripts/classify_candidates.py

# Check seat availability for one showtime (opens and cleanly
# cancels a real checkout transaction - safe, no purchase is made)
python3 scripts/filmgrail_checkout.py "https://www.trondheimkino.no/showtime/1-112034-51438" --count 3

# Find N contiguous available seats in a zone, from filmgrail_checkout.py's
# `seats` field piped in on stdin
python3 scripts/filmgrail_zone_match.py --count 3 --zone-row back --zone-col center < seats.json

# Check seat availability for one ODEON showtime (read-only - no
# transaction/hold is ever opened, unlike filmgrail_checkout.py)
python3 scripts/odeon_checkout.py "https://www.odeonkino.no/booking/kjop/02167291-18d5-4b4a-a498-20af2b9cd8ed"

# Find N contiguous available seats in a zone, from odeon_checkout.py's
# `seats` field piped in on stdin
python3 scripts/odeon_zone_match.py --count 3 --zone-row back --zone-col center < seats.json

# Check seat availability for one ebillett.no showtime (opens a real
# reservation and sends a best-effort cancel - see Scope above for why
# that cancel isn't guaranteed, unlike filmgrail_checkout.py's)
python3 scripts/ebillett_checkout.py "https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf" --count 3

# Find N contiguous available seats in a zone, from ebillett_checkout.py's
# `seats` field piped in on stdin
python3 scripts/ebillett_zone_match.py --count 3 --zone-row back --zone-col center < seats.json

# Check seat availability for one NFkino showtime (opens a real order and
# sends a best-effort cleanup - see Scope above for why that isn't
# guaranteed, same caveat as ebillett_checkout.py's)
python3 scripts/nfkino_checkout.py "https://nfkino.no/screening/53126442-33d8-4b30-a736-b80d35b4049a/6c3775a8-39c2-488b-8fcd-c1d2d6f1ba25" --count 3

# Find N contiguous available seats in a zone, from nfkino_checkout.py's
# `seats` field piped in on stdin
python3 scripts/nfkino_zone_match.py --count 3 --zone-row back --zone-col center < seats.json
```

## Tests

```bash
cd scripts
python3 -m unittest test_discover_shows test_filmgrail_zone_match test_filmgrail_checkout test_odeon_zone_match test_odeon_checkout test_ebillett_checkout test_ebillett_zone_match test_nfkino_checkout test_nfkino_zone_match test_classify_candidates test_group_showtimes
```

All eleven test modules run entirely offline against fake/canned
responses — no network access or real checkout transactions/API calls
are involved.
