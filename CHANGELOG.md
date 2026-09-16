# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/). While the
major version is `0`, minor bumps mark new capability and patch bumps mark
fixes/docs/cosmetic changes — the same convention this project will keep
once it reaches `1.0.0`.

## [0.4.2] - 2026-09-16

### Added

- This changelog, documenting project history from `v0.0.1` through the
  current release in Keep a Changelog format.

## [0.4.1] - 2026-09-16

### Changed

- `SKILL.md` cut roughly in half (623 → 287 lines) by removing detail
  that duplicated each checkout script's own module docstring (exact
  HTTP payload shapes, reverse-engineering narrative, survey dates), and
  merging Step 3's four near-identical per-platform procedures into one
  shared one.
- Platform classification data (which cinemas belong to which chain,
  domain rules, `cancelStatus` vocabulary) moved out of `SKILL.md` into
  `references/platforms.md`, read only for the request types that
  actually need it instead of on every invocation.

## [0.4.0] - 2026-09-16

### Added

- NFkino as a fourth seat-finding platform (Drupal 10 + Vista
  Entertainment backend), covering 14 independent cinemas including
  Arendal, Kristiansand, Oslo (Colosseum, Gimle, Klingenberg, Ringen,
  Saga, Symra, Vika), and more. `nfkino_checkout.py` +
  `nfkino_zone_match.py`.

## [0.3.1] - 2026-09-16

### Added

- Project logo, referenced in the README header.

## [0.3.0] - 2026-09-16

### Added

- Bergen kino support. Its seatmap has no integer `column` field, only
  pixel `coordX`/`coordY` positions — `rowSymbol`/`columnSymbol` turned
  out to already carry the same clean, gapless adjacency structure the
  zone matcher needs, so `filmgrail_checkout.py` now derives a synthetic
  row/column grid from those instead of requiring the raw coordinate
  shape.
- Setermoen kino, found via a nationwide domain survey and confirmed
  live the same way as the rest.

## [0.2.3] - 2026-09-16

### Fixed

- `ebillett_checkout.py`: a reservation's own just-held seats (state
  `"2"`) were being collapsed into `"booked"`, so the zone matcher could
  never see the exact seats a successful reservation had just proven
  available. State `"2"` now counts as available.
- `discover_shows.py`: `--exclude-past` compared Filmweb's naive
  Norway-local `showStart` against naive *system*-local time, giving
  wrong results outside Norway's timezone.

## [0.2.2] - 2026-09-16

### Added

- A "See it in action" walkthrough in the README with four real
  screenshots (location lookup, listing, movie info, seat-finding).

## [0.2.1] - 2026-09-16

### Changed

- The skill no longer narrates internal mechanics (script names, JSON
  field names, `cancelStatus` values) while running or in its final
  report — reports are plain-language now.

## [0.2.0] - 2026-09-16

### Added

- ODEON seat-finding support (Cinema API backend, read-only, any ODEON
  city).
- ebillett.no/DX seat-finding support (~65 independent theaters
  nationwide, real checkout with best-effort cleanup).
- Movie info lookups (synopsis, genre, runtime, age rating).
- Top-level README.

### Changed

- Generalized the original Trondheim-Kino-only checkout client into
  `filmgrail_checkout.py`/`filmgrail_zone_match.py`, covering all ten
  confirmed Filmgrail/Mars cinemas at the time.

## [0.1.4] - 2026-09-16

### Fixed

- Untracked the design spec doc, which had been force-added, overriding
  the operator's global gitignore rule for that path.

## [0.1.3] - 2026-09-16

### Fixed

- `zone_match.py`: overlapping `<=`/`>=` thresholds in `row_zone`/
  `col_zone` emptied the middle/center band for common room sizes (e.g.
  6 rows), a silent false-negative bug.
- `discover_shows.py`: removed an unused `sys` import.

### Added

- Regression tests for the middle-band fix, `zone_col` coverage, and a
  guard against non-positive seat counts.

## [0.1.2] - 2026-09-16

### Fixed

- Strengthened `test_excludes_wheelchair_seats` to a genuine 2-vs-1
  majority case — the old 1-vs-1 fixture only passed because of
  `max()`'s tie-breaking behavior, not because the logic was correct.

## [0.1.1] - 2026-09-16

### Fixed

- `zone_match.py` now treats the room's majority seat type as
  "standard" instead of hardcoding an empty string — a real Trondheim
  Kino room used a non-empty type for its standard seats, causing
  false-negative matches.

## [0.1.0] - 2026-09-16

### Added

- First usable release: the `cinema-seat-finder` Claude Code skill,
  orchestrating showtime discovery and seat zone-matching for Trondheim
  Kino.

## [0.0.3] - 2026-09-16

### Added

- Filmweb GraphQL discovery script (`discover_shows.py`).

## [0.0.2] - 2026-09-16

### Added

- Zone/adjacency seat matching module.

## [0.0.1] - 2026-09-16

### Added

- Repo bootstrap.

[0.4.2]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/ruskilli/cinema-seat-finder/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ruskilli/cinema-seat-finder/releases/tag/v0.0.1
