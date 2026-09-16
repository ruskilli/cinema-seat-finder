import datetime
import json
import unittest
from discover_shows import (
    build_payload, fetch_shows, filter_past_shows, get_cinemas, get_movie, search_locations, search_movies,
)


class TestBuildPayload(unittest.TestCase):
    def test_includes_all_variables(self):
        payload = build_payload('Trondheim', '2026-09-16', 'En nasjon i sjakk')
        self.assertEqual(payload['variables'], {
            'location': 'Trondheim',
            'date': '2026-09-16',
            'movieTitle': 'En nasjon i sjakk',
        })
        self.assertIn('getShows', payload['query'])

    def test_movie_title_defaults_to_none(self):
        payload = build_payload('Trondheim', '2026-09-16')
        self.assertIsNone(payload['variables']['movieTitle'])

    def test_special_characters_in_title_survive_json_encoding(self):
        # this is exactly why we use GraphQL variables instead of string
        # interpolation into the query text: json.dumps handles escaping
        payload = build_payload('Trondheim', '2026-09-16', 'Weird "Title" with quotes')
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)
        self.assertEqual(decoded['variables']['movieTitle'], 'Weird "Title" with quotes')


class FakeResponse:
    def __init__(self, body):
        self._body = json.dumps(body).encode('utf-8')

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestFetchShows(unittest.TestCase):
    def test_parses_successful_response(self):
        canned = {'data': {'showQuery': {'getShows': [
            {'movieTitle': 'En nasjon i sjakk', 'showStart': '2026-09-16T17:40:00',
             'screenName': 'Nova 2 BOUTIQ', 'theaterName': 'Nova', 'firmName': 'Trondheim Kino',
             'ticketSaleUrl': 'https://www.trondheimkino.no/showtime/2-112245-44443'},
        ]}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        shows = fetch_shows('Trondheim', '2026-09-16', opener=fake_opener)
        self.assertEqual(shows, canned['data']['showQuery']['getShows'])

    def test_raises_on_graphql_errors(self):
        canned = {'errors': [{'message': "Cannot query field 'x'"}]}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        with self.assertRaises(RuntimeError):
            fetch_shows('Trondheim', '2026-09-16', opener=fake_opener)


class TestFilterPastShows(unittest.TestCase):
    def test_drops_shows_at_or_before_now(self):
        now = datetime.datetime(2026, 9, 16, 13, 0, 0)
        shows = [
            {'movieTitle': 'Already started', 'showStart': '2026-09-16T12:30:00'},
            {'movieTitle': 'Starts right now', 'showStart': '2026-09-16T13:00:00'},
            {'movieTitle': 'Still upcoming', 'showStart': '2026-09-16T17:30:00'},
        ]
        self.assertEqual(filter_past_shows(shows, now), [
            {'movieTitle': 'Still upcoming', 'showStart': '2026-09-16T17:30:00'},
        ])

    def test_keeps_everything_when_all_shows_are_upcoming(self):
        now = datetime.datetime(2026, 9, 16, 9, 0, 0)
        shows = [{'movieTitle': 'Later today', 'showStart': '2026-09-16T17:30:00'}]
        self.assertEqual(filter_past_shows(shows, now), shows)

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(filter_past_shows([], datetime.datetime(2026, 9, 16, 13, 0, 0)), [])


class TestSearchLocations(unittest.TestCase):
    def test_returns_list_of_matching_location_names(self):
        canned = {'data': {'cinemaQuery': {'searchForLocations': [
            {'name': 'Bergen'}, {'name': 'Kongsberg'}, {'name': 'Tønsberg'},
        ]}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        names = search_locations('berg', opener=fake_opener)
        self.assertEqual(names, ['Bergen', 'Kongsberg', 'Tønsberg'])

    def test_returns_empty_list_when_nothing_matches(self):
        canned = {'data': {'cinemaQuery': {'searchForLocations': []}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        self.assertEqual(search_locations('zzzznotatown', opener=fake_opener), [])

    def test_raises_on_graphql_errors(self):
        canned = {'errors': [{'message': 'boom'}]}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        with self.assertRaises(RuntimeError):
            search_locations('berg', opener=fake_opener)


class TestGetCinemas(unittest.TestCase):
    def test_returns_cinema_name_and_firm_id_pairs(self):
        canned = {'data': {'cinemaQuery': {'getCinemas': [
            {'name': 'Nova', 'firmId': 12}, {'name': 'Prinsen', 'firmId': 12},
        ]}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        cinemas = get_cinemas(location='Trondheim', opener=fake_opener)
        self.assertEqual(cinemas, [{'name': 'Nova', 'firmId': 12}, {'name': 'Prinsen', 'firmId': 12}])

    def test_raises_on_graphql_errors(self):
        canned = {'errors': [{'message': 'boom'}]}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        with self.assertRaises(RuntimeError):
            get_cinemas(location='Trondheim', opener=fake_opener)


class TestSearchMovies(unittest.TestCase):
    def test_returns_title_and_movie_id_pairs(self):
        canned = {'data': {'movieQuery': {'searchForMovies': [
            {'title': 'Fjord', 'mainVersionId': 'EDI20260087'},
            {'title': 'Storfjord 1829', 'mainVersionId': 'EDI20250683'},
        ]}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        results = search_movies('Fjord', opener=fake_opener)
        self.assertEqual(results, [
            {'title': 'Fjord', 'mainVersionId': 'EDI20260087'},
            {'title': 'Storfjord 1829', 'mainVersionId': 'EDI20250683'},
        ])

    def test_returns_empty_list_when_nothing_matches(self):
        canned = {'data': {'movieQuery': {'searchForMovies': []}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        self.assertEqual(search_movies('zzzznotamovie', opener=fake_opener), [])

    def test_raises_on_graphql_errors(self):
        canned = {'errors': [{'message': 'boom'}]}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        with self.assertRaises(RuntimeError):
            search_movies('Fjord', opener=fake_opener)


class TestGetMovie(unittest.TestCase):
    def test_returns_the_movie_info_fields(self):
        canned = {'data': {'movieQuery': {'getMovie': {
            'title': 'Fjord', 'titleOriginal': 'Fjord', 'genres': ['Drama'],
            'lengthInMinutes': 145, 'rating': '9 år',
            'synopsisIngress': 'Short version.', 'synopsisBodyText': 'Long version.',
            'premiere': '2026-09-04T00:00:00', 'productionYear': '2026',
            'userRatingAvg': 0, 'userRatingNum': 0,
            'languages': ['Engelsk', 'Norsk'], 'nationalities': ['Norge', 'Romania'],
        }}}}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        movie = get_movie('EDI20260087', opener=fake_opener)
        self.assertEqual(movie['title'], 'Fjord')
        self.assertEqual(movie['genres'], ['Drama'])
        self.assertEqual(movie['lengthInMinutes'], 145)

    def test_raises_on_graphql_errors(self):
        canned = {'errors': [{'message': 'boom'}]}

        def fake_opener(req, timeout=15):
            return FakeResponse(canned)

        with self.assertRaises(RuntimeError):
            get_movie('EDI20260087', opener=fake_opener)


if __name__ == '__main__':
    unittest.main()
