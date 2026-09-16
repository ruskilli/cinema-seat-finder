# Known checkout platforms

Reference for `SKILL.md`'s Step 2 (classify candidates) and Step 3
(seat-check them) — read this file when handling a seat-finding request,
not needed for Location/Movie-info/Listing requests.

| Platform | Scripts | Candidate is in scope when... | Real hold opened? | `cancelStatus` values |
|---|---|---|---|---|
| Filmgrail/Mars | `filmgrail_checkout.py` + `filmgrail_zone_match.py` | `firmName` is one of: Trondheim Kino, Steinkjer kino, Kimen kino, Haugesund kino, Caroline kino Kristiansund, Tromsø Kino, Narvik kino, Alta kino, Kirkenes kino, Lakselv kino, Setermoen kino, Bergen kino | Yes | `cancelled` \| `failed` \| `not_created` — cancel is confirmed effective |
| ODEON (Cinema API) | `odeon_checkout.py` + `odeon_zone_match.py` | `ticketSaleUrl` starts `https://www.odeonkino.no/` (domain, not `firmName` — many `firmName`s share this backend) | No — read-only | *(no `cancelStatus` field at all)* |
| ebillett.no/DX | `ebillett_checkout.py` + `ebillett_zone_match.py` | `ticketSaleUrl` starts `https://checkout.ebillett.no/` | Yes | `attempted` \| `failed` \| `not_created` — cancel is sent but **not** confirmed to release the hold; real safety net is ~1 min auto-expiry |
| NFkino (Drupal+Vista) | `nfkino_checkout.py` + `nfkino_zone_match.py` | `ticketSaleUrl` starts `https://nfkino.no/` | Yes | `attempted` \| `failed` \| `not_created` — same caveat as ebillett.no; real safety net is ~10 min auto-expiry. General-admission screenings (`isGeneralAdmissionScreening`) have no seatmap — reported as a normal `status: "error"` |

**Never** describe an `attempted` `cancelStatus` as "cancelled" to the
user — only Filmgrail's is confirmed released.

**Out of scope, always:** Bygdekinoen (`kinologg.kino.no`) — its screenings
run in village halls with unnumbered, unreserved seating, so there's no
seatmap to check regardless of vendor. Anything not matching a row above
is also out of scope — still surface its `ticketSaleUrl` as a manual-check
link (Step 4), just don't seat-check it.

If a new candidate cinema/domain turns up that isn't in this table (e.g.
another `<town>.aurorakino.no` subdomain, or a `firmName` variant), verify
it live before trusting it — a real `check_seats()` call plus a sane zone
match — rather than adding it on pattern-matching alone. Each script's own
module docstring has the full reverse-engineering trail if you need the
underlying HTTP mechanics for any platform.
