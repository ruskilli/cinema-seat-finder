import json
import unittest
from odeon_checkout import (
    build_seatmap,
    check_seats,
    extract_show_id,
    get_screen_layout,
    get_show,
    get_ticket_status,
)


class FakeResponse:
    def __init__(self, body_bytes):
        self._body = body_bytes

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def json_response(obj):
    return FakeResponse(json.dumps(obj).encode('utf-8'))


class TestExtractShowId(unittest.TestCase):
    def test_pulls_the_uuid_from_the_ticket_sale_url(self):
        url = 'https://www.odeonkino.no/booking/kjop/02167291-18d5-4b4a-a498-20af2b9cd8ed'
        self.assertEqual(extract_show_id(url), '02167291-18d5-4b4a-a498-20af2b9cd8ed')

    def test_tolerates_a_trailing_slash(self):
        url = 'https://www.odeonkino.no/booking/kjop/02167291-18d5-4b4a-a498-20af2b9cd8ed/'
        self.assertEqual(extract_show_id(url), '02167291-18d5-4b4a-a498-20af2b9cd8ed')


class TestGetShow(unittest.TestCase):
    def test_requests_the_show_endpoint_and_returns_parsed_json(self):
        captured = {}

        def fake_opener(req, timeout=15):
            captured['url'] = req.full_url
            return json_response({'auditoriumLayoutId': '1508'})

        show = get_show('abc123', opener=fake_opener)
        self.assertEqual(show['auditoriumLayoutId'], '1508')
        self.assertEqual(captured['url'], 'https://services.cinema-api.com/show/Sys99-NO/abc123/no')


class TestGetScreenLayout(unittest.TestCase):
    def test_requests_the_layout_endpoint_and_returns_parsed_json(self):
        captured = {}

        def fake_opener(req, timeout=15):
            captured['url'] = req.full_url
            return json_response({'seats': []})

        layout = get_screen_layout('1508', opener=fake_opener)
        self.assertEqual(layout['seats'], [])
        self.assertEqual(captured['url'], 'https://services.cinema-api.com/screen/layout/no/1508')


class TestGetTicketStatus(unittest.TestCase):
    def test_requests_the_ticketstatus_endpoint_and_returns_parsed_json(self):
        captured = {}

        def fake_opener(req, timeout=15):
            captured['url'] = req.full_url
            return json_response([{'remoteEntityId': '1', 'status': 'Free'}])

        statuses = get_ticket_status('abc123', opener=fake_opener)
        self.assertEqual(statuses, [{'remoteEntityId': '1', 'status': 'Free'}])
        self.assertEqual(
            captured['url'],
            'https://services.cinema-api.com/show/ticketstatus/Sys99-NO/abc123/',
        )


class TestBuildSeatmap(unittest.TestCase):
    def test_joins_layout_and_status_by_remote_entity_id(self):
        layout_seats = [
            {'remoteEntityId': '1', 'row': 1, 'number': 1, 'seatType': 'REGULAR'},
            {'remoteEntityId': '2', 'row': 1, 'number': 2, 'seatType': 'REGULAR'},
        ]
        statuses = [
            {'remoteEntityId': '1', 'status': 'Free'},
            {'remoteEntityId': '2', 'status': 'Sold'},
        ]
        seats = build_seatmap(layout_seats, statuses)
        self.assertEqual(seats, [
            {'row': 1, 'column': 1, 'state': 'available', 'type': 'REGULAR', 'rowSymbol': '1', 'columnSymbol': '1'},
            {'row': 1, 'column': 2, 'state': 'booked', 'type': 'REGULAR', 'rowSymbol': '1', 'columnSymbol': '2'},
        ])

    def test_treats_locked_seats_as_booked_not_available(self):
        # "Locked" means someone else has it mid-checkout - not bookable now
        layout_seats = [{'remoteEntityId': '1', 'row': 1, 'number': 1, 'seatType': 'REGULAR'}]
        statuses = [{'remoteEntityId': '1', 'status': 'Locked'}]
        seats = build_seatmap(layout_seats, statuses)
        self.assertEqual(seats[0]['state'], 'booked')

    def test_treats_a_seat_missing_from_ticket_status_as_booked(self):
        # conservative default: only an explicit "Free" status counts as
        # available, never silently assume availability
        layout_seats = [{'remoteEntityId': '1', 'row': 1, 'number': 1, 'seatType': 'REGULAR'}]
        seats = build_seatmap(layout_seats, [])
        self.assertEqual(seats[0]['state'], 'booked')


class TestCheckSeats(unittest.TestCase):
    def _fake_opener_sequence(self, show_response, layout_response, ticketstatus_response):
        calls = []

        def fake_opener(req, timeout=15):
            calls.append(req.full_url)
            if '/screen/layout/' in req.full_url:
                return json_response(layout_response)
            if '/show/ticketstatus/' in req.full_url:
                return json_response(ticketstatus_response)
            return json_response(show_response)

        return fake_opener, calls

    def test_happy_path_returns_joined_seats(self):
        opener, calls = self._fake_opener_sequence(
            {'auditoriumLayoutId': '1508'},
            {'seats': [{'remoteEntityId': '1', 'row': 1, 'number': 1, 'seatType': 'REGULAR'}]},
            [{'remoteEntityId': '1', 'status': 'Free'}],
        )

        result = check_seats('https://www.odeonkino.no/booking/kjop/abc123', opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['seats'], [
            {'row': 1, 'column': 1, 'state': 'available', 'type': 'REGULAR', 'rowSymbol': '1', 'columnSymbol': '1'},
        ])
        self.assertEqual(len(calls), 3)

    def test_never_sends_a_request_body(self):
        # unlike filmgrail_checkout.py's check_seats (which POSTs to select
        # tickets and to cancel), this is pure read-only GETs - no request
        # body is ever sent, confirming no transaction/hold is ever opened
        bodies = []

        def fake_opener(req, timeout=15):
            bodies.append(req.data)
            if '/screen/layout/' in req.full_url:
                return json_response({'seats': []})
            if '/show/ticketstatus/' in req.full_url:
                return json_response([])
            return json_response({'auditoriumLayoutId': '1508'})

        check_seats('https://www.odeonkino.no/booking/kjop/abc123', opener=fake_opener)

        self.assertEqual(len(bodies), 3)
        self.assertTrue(all(b is None for b in bodies))

    def test_status_error_when_a_request_fails(self):
        def fake_opener(req, timeout=15):
            raise RuntimeError('boom')

        result = check_seats('https://www.odeonkino.no/booking/kjop/abc123', opener=fake_opener)
        self.assertEqual(result['status'], 'error')
        self.assertIn('boom', result['error'])
        self.assertIsNone(result['seats'])


if __name__ == '__main__':
    unittest.main()
