"""Discover Trondheim Kino showtimes via Filmweb's public GraphQL API.

Endpoint verified working and introspectable, no auth required, as of
2026-09-16 (see docs/superpowers/specs/2026-09-16-cinema-seat-finder-design.md).
"""
import argparse
import json
import sys
import urllib.request

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


def build_payload(location, date, movie_title=None):
    return {
        "query": QUERY,
        "variables": {
            "location": location,
            "date": date,
            "movieTitle": movie_title,
        },
    }


def fetch_shows(location, date, movie_title=None, endpoint=GRAPHQL_ENDPOINT, opener=None):
    payload = build_payload(location, date, movie_title)
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
    return body['data']['showQuery']['getShows']


def main():
    parser = argparse.ArgumentParser(description="Discover Trondheim Kino showtimes via Filmweb's public GraphQL API")
    parser.add_argument('--location', default='Trondheim')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--movie-title', default=None)
    args = parser.parse_args()
    shows = fetch_shows(args.location, args.date, args.movie_title)
    print(json.dumps(shows))


if __name__ == '__main__':
    main()
