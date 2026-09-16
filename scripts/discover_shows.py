"""Discover cinema showtimes via Filmweb's public GraphQL API, filterable by
Norwegian city (`--location`, e.g. "Trondheim" or "Bergen") and covering
whichever chains Filmweb has data for in that city - not just Trondheim
Kino, though `--location` doesn't guarantee every result belongs to a chain
this repo's checkout scripts actually support. Filmweb aggregates listings
nationwide regardless of checkout vendor, so this module stays chain
generic - unlike `filmgrail_checkout.py`/`filmgrail_zone_match.py`, which
are specific to the Filmgrail/Mars checkout platform (see that module's
docstring), and any future chain's checkout script would live alongside
them, named for that chain.

`--location ""` (empty string) returns every showtime nationwide in one
call - confirmed live 2026-09-16 (893 shows across 110 cinemas that day) -
which is more useful than it sounds when checking a specific `firmName`
that might span multiple towns, since it avoids having to enumerate towns
by name. Omitting `--location` entirely instead falls back to this script's
own CLI default of `"Trondheim"` - not the same as passing `""`.

Four more modes, each swapping out show-discovery entirely (no `--date`
needed) rather than being additive flags:

- `--search-location TEXT` resolves a partial/misspelled town name against
  Filmweb's own location index (e.g. "berg" -> ["Bergen", "Kongsberg",
  "Rødberg", "Tønsberg"]) - use this before trusting a user-given town for
  `--location`, since `getShows`'s location filter needs the *exact*
  canonical spelling with correct Norwegian diacritics (confirmed live
  2026-09-16: "Tromso" returns nothing, "Tromsø" works) - though
  `--search-location` itself still does plain substring/prefix matching on
  the correctly-spelled town, not diacritic-insensitive fuzzy matching (it
  won't turn "stjor" into "Stjørdal", only a correctly-accented prefix like
  "stjø" or "stj" will).
- `--list-cinemas` (paired with `--location`, or `--location ""` for
  nationwide) lists the cinema *buildings* Filmweb knows about in that town
  - e.g. `--location Trondheim --list-cinemas` -> `[{"name": "Nova",
  "firmId": 12}, {"name": "Prinsen", "firmId": 12}]`. This is
  theaterName-level, not firmName-level - Trondheim's two buildings share
  one firmId (one chain, "Trondheim Kino"), but that's not true everywhere.
- `--search-movie TEXT` resolves a (possibly partial) movie title to
  Filmweb's own movie ids via `movieQuery.searchForMovies` - e.g. "Fjord"
  -> `[{"title": "Fjord", "mainVersionId": "EDI20260087"}, ...]`. Feed a
  result's `mainVersionId` into `--movie-id`.
- `--movie-id ID` fetches full info for one movie via
  `movieQuery.getMovie` - title, genres, runtime, age rating, short/long
  synopsis, premiere date, production year, Filmweb's own user rating,
  languages, and production nationalities. Confirmed live 2026-09-16 for
  "Fjord" (EDI20260087): rich, real prose synopsis mentioning cast by name,
  not just a stub. All text fields are in Norwegian, same as the rest of
  Filmweb's data - not translated.

Endpoint verified working and introspectable, no auth required, as of
2026-09-16.

`--date` is date-only on the API side - `getShows(date="2026-09-16")` returns
every showtime for that whole day regardless of what time it currently is,
including ones already underway or over. Pass `--exclude-past` alongside a
`--date` of today to drop those, using the local system clock (naive
comparison against each `showStart`, which is itself a naive local
datetime string like "2026-09-16T12:30:00" - no timezone offset from the
API to compare against). Only meaningful when `--date` is today; harmless
(a no-op) for a future date, and would wrongly drop everything for a past
date, so don't pass it then.
"""
import argparse
import datetime
import json
import urllib.request
from zoneinfo import ZoneInfo

GRAPHQL_ENDPOINT = "https://movieinfoqs.filmweb.no/graphql"

QUERY = """
query GetShows($location: String, $date: String, $movieTitle: String) {
  showQuery {
    getShows(location: $location, date: $date, movieTitle: $movieTitle) {
      movieTitle
      showStart
      screenName
      theaterName
      firmName
      ticketSaleUrl
    }
  }
}
"""

SEARCH_LOCATIONS_QUERY = """
query SearchLocations($searchText: String) {
  cinemaQuery {
    searchForLocations(searchText: $searchText) {
      name
    }
  }
}
"""

GET_CINEMAS_QUERY = """
query GetCinemas($location: String) {
  cinemaQuery {
    getCinemas(location: $location) {
      name
      firmId
    }
  }
}
"""

SEARCH_MOVIES_QUERY = """
query SearchMovies($searchText: String, $maxNumItems: Int) {
  movieQuery {
    searchForMovies(searchText: $searchText, maxNumItems: $maxNumItems) {
      title
      mainVersionId
    }
  }
}
"""

GET_MOVIE_QUERY = """
query GetMovie($movieId: String) {
  movieQuery {
    getMovie(movieId: $movieId) {
      title
      titleOriginal
      genres
      lengthInMinutes
      rating
      synopsisIngress
      synopsisBodyText
      premiere
      productionYear
      userRatingAvg
      userRatingNum
      languages
      nationalities
    }
  }
}
"""


def build_payload(location, date, movie_title=None):
    return {
        "query": QUERY,
        "variables": {
            "location": location,
            "date": date,
            "movieTitle": movie_title,
        },
    }


def _post_graphql(query, variables, endpoint, opener):
    payload = {"query": query, "variables": variables}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        endpoint, data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(req, timeout=15) as resp:
        body = json.loads(resp.read().decode('utf-8'))
    if 'errors' in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body['data']


def fetch_shows(location, date, movie_title=None, endpoint=GRAPHQL_ENDPOINT, opener=None):
    data = _post_graphql(QUERY, {"location": location, "date": date, "movieTitle": movie_title}, endpoint, opener)
    return data['showQuery']['getShows']


def filter_past_shows(shows, now):
    """Drop shows whose showStart is not after `now` (a naive local
    datetime). `getShows`'s `date` filter is date-only, so a full day's
    results include showtimes already underway or finished by the time this
    runs - relevant whenever the caller is asking about "today"."""
    return [s for s in shows if datetime.datetime.fromisoformat(s['showStart']) > now]


def oslo_now(utc_now=None):
    """Current wall-clock time in Europe/Oslo, as a naive datetime -
    directly comparable against Filmweb's showStart strings, which are
    themselves naive Norway-local wall-clock times with no offset. Using
    plain `datetime.datetime.now()` here would instead be the *host's own*
    system timezone, which is wrong (and silently so) on anything not
    itself running in Europe/Oslo - a UTC container/CI runner, say."""
    utc_now = utc_now or datetime.datetime.now(datetime.timezone.utc)
    return utc_now.astimezone(ZoneInfo("Europe/Oslo")).replace(tzinfo=None)


def search_locations(search_text, endpoint=GRAPHQL_ENDPOINT, opener=None):
    """Resolve a (possibly partial or misspelled) Norwegian town name against
    Filmweb's own location index - e.g. "berg" -> ["Bergen", "Kongsberg",
    "Tønsberg"]. Use this before passing a user-given town straight to
    `--location`, since `getShows`'s location filter needs the exact
    canonical spelling (confirmed live 2026-09-16: "Tromso" returns nothing,
    "Tromsø" works)."""
    data = _post_graphql(SEARCH_LOCATIONS_QUERY, {"searchText": search_text}, endpoint, opener)
    return [loc['name'] for loc in data['cinemaQuery']['searchForLocations']]


def get_cinemas(location=None, endpoint=GRAPHQL_ENDPOINT, opener=None):
    """List the cinema buildings Filmweb knows about in a town (or
    nationwide if `location` is None/empty) - e.g. location="Trondheim" ->
    [{"name": "Nova", "firmId": 12}, {"name": "Prinsen", "firmId": 12}].
    Note this is theaterName-level (the building), not firmName-level (the
    chain) - both share Trondheim Kino's firmId here."""
    data = _post_graphql(GET_CINEMAS_QUERY, {"location": location}, endpoint, opener)
    return data['cinemaQuery']['getCinemas']


def search_movies(search_text, max_num_items=10, endpoint=GRAPHQL_ENDPOINT, opener=None):
    """Resolve a (possibly partial) movie title to Filmweb's own movie ids -
    e.g. "Fjord" -> [{"title": "Fjord", "mainVersionId": "EDI20260087"},
    {"title": "Storfjord 1829", "mainVersionId": "EDI20250683"}, ...]. Feed
    a result's `mainVersionId` into get_movie() as `movie_id`."""
    data = _post_graphql(
        SEARCH_MOVIES_QUERY, {"searchText": search_text, "maxNumItems": max_num_items}, endpoint, opener)
    return data['movieQuery']['searchForMovies']


def get_movie(movie_id, endpoint=GRAPHQL_ENDPOINT, opener=None):
    """Full info for one movie by Filmweb movie id (see search_movies) -
    title, genres, runtime, age rating, synopsis (short + long), premiere
    date, production year, Filmweb user rating, languages, and production
    nationalities. All text fields are in Norwegian, same as the rest of
    Filmweb's data - not translated."""
    data = _post_graphql(GET_MOVIE_QUERY, {"movieId": movie_id}, endpoint, opener)
    return data['movieQuery']['getMovie']


def main():
    parser = argparse.ArgumentParser(description="Discover cinema showtimes via Filmweb's public GraphQL API")
    parser.add_argument('--location', default='Trondheim')
    parser.add_argument('--date', help='YYYY-MM-DD (required unless --search-location, --list-cinemas, --search-movie, or --movie-id is given)')
    parser.add_argument('--movie-title', default=None)
    parser.add_argument('--exclude-past', action='store_true',
                         help='Drop showtimes at or before the current local time - use when '
                              '--date is today so already-started/finished shows are not listed '
                              'as available')
    parser.add_argument('--search-location', metavar='TEXT', default=None,
                         help="Resolve a partial/misspelled town name against Filmweb's location index "
                              "(e.g. \"berg\" -> Bergen, Kongsberg, ...) instead of discovering shows")
    parser.add_argument('--list-cinemas', action='store_true',
                         help='List cinema buildings in --location (or nationwide with --location "") '
                              'instead of discovering shows')
    parser.add_argument('--search-movie', metavar='TEXT', default=None,
                         help='Resolve a movie title to Filmweb movie ids instead of discovering shows')
    parser.add_argument('--movie-id', metavar='ID', default=None,
                         help='Fetch full info (synopsis, genre, runtime, rating, ...) for one movie id '
                              '(from --search-movie) instead of discovering shows')
    args = parser.parse_args()

    if args.search_location is not None:
        print(json.dumps(search_locations(args.search_location)))
        return
    if args.list_cinemas:
        print(json.dumps(get_cinemas(args.location)))
        return
    if args.search_movie is not None:
        print(json.dumps(search_movies(args.search_movie)))
        return
    if args.movie_id is not None:
        print(json.dumps(get_movie(args.movie_id)))
        return
    if args.date is None:
        parser.error('--date is required unless --search-location, --list-cinemas, --search-movie, or --movie-id is given')
    shows = fetch_shows(args.location, args.date, args.movie_title)
    if args.exclude_past:
        shows = filter_past_shows(shows, oslo_now())
    print(json.dumps(shows))


if __name__ == '__main__':
    main()
