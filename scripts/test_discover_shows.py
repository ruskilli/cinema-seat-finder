import json
import unittest
from discover_shows import build_payload, fetch_shows


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


if __name__ == '__main__':
    unittest.main()
