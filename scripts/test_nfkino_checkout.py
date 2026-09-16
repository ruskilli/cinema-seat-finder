import json
import unittest
from nfkino_checkout import (
    check_seats,
    parse_order_uuid,
    parse_ticket_type_uuid,
    seats_from_seats_selector,
)


class FakeResponse:
    def __init__(self, body_bytes=b'', status=200):
        self._body = body_bytes
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


ORDER_PAGE_HTML = '''
<script type="application/json" data-drupal-selector="drupal-settings-json">
{"orders":{"orderUuid":"78146db6-fb72-4ce1-b8a0-892fe89c60c8","reserveSeatsUrl":"/order/78146db6-fb72-4ce1-b8a0-892fe89c60c8/reserve_seats","abandonUrl":"/order/78146db6-fb72-4ce1-b8a0-892fe89c60c8/abandon"}}
</script>
'''

TICKETS_SELECTOR_HTML = '''
<div class="ticket" data-ticket-type-uuid="c4ad3e81-ac60-4c1b-bc5d-0f9ee89e76a9">
  <div class="type">Ordinær</div>
</div>
'''


class TestParseOrderUuid(unittest.TestCase):
    def test_extracts_order_uuid_from_drupal_settings(self):
        self.assertEqual(
            parse_order_uuid(ORDER_PAGE_HTML),
            '78146db6-fb72-4ce1-b8a0-892fe89c60c8',
        )

    def test_raises_when_not_found(self):
        with self.assertRaises(RuntimeError):
            parse_order_uuid('<html></html>')


class TestParseTicketTypeUuid(unittest.TestCase):
    def test_picks_the_first_ticket_type(self):
        self.assertEqual(
            parse_ticket_type_uuid(TICKETS_SELECTOR_HTML),
            'c4ad3e81-ac60-4c1b-bc5d-0f9ee89e76a9',
        )

    def test_raises_when_no_ticket_types_found(self):
        with self.assertRaises(RuntimeError):
            parse_ticket_type_uuid('<div class="tickets-selectors"></div>')


class TestSeatsFromSeatsSelector(unittest.TestCase):
    def test_decodes_real_seats_and_skips_layout_placeholders(self):
        seats_selector = {
            'seats': {
                'rows': [{'id': 'row1', 'legend': '1', 'coordinate': 0}],
                'cols': [],
                'seats': [
                    {'id': 'aisle-1', 'symbol': '', 'kind': '1', 'rowId': 'row1',
                     'coordinateX': 0, 'coordinateY': 0, 'wheelchairSeat': False},
                    {'id': 'seat-a', 'symbol': '5', 'kind': '0', 'rowId': 'row1',
                     'coordinateX': 1, 'coordinateY': 0, 'wheelchairSeat': False},
                    {'id': 'seat-b', 'symbol': '4', 'kind': '0', 'rowId': 'row1',
                     'coordinateX': 2, 'coordinateY': 0, 'wheelchairSeat': False},
                ],
            },
            'selectedSeats': {'list': ['seat-b']},
            'bestSeats': [],
        }
        seats = seats_from_seats_selector(seats_selector)
        self.assertEqual(seats, [
            {'row': 1, 'column': 2, 'state': 'available', 'type': '', 'rowSymbol': '1', 'columnSymbol': '5'},
            {'row': 1, 'column': 3, 'state': 'booked', 'type': '', 'rowSymbol': '1', 'columnSymbol': '4'},
        ])

    def test_own_best_seats_count_as_available_even_though_theyre_in_selected_list(self):
        # selectedSeats.list is "every currently occupied seat in the room",
        # which includes this order's own just-reserved seats (bestSeats) -
        # those must still count as available, or the matcher can never see
        # the exact seats the server just proved it could give the caller
        seats_selector = {
            'seats': {
                'rows': [{'id': 'row1', 'legend': '1', 'coordinate': 0}],
                'cols': [],
                'seats': [
                    {'id': 'seat-a', 'symbol': '1', 'kind': '0', 'rowId': 'row1',
                     'coordinateX': 0, 'coordinateY': 0, 'wheelchairSeat': False},
                ],
            },
            'selectedSeats': {'list': ['seat-a']},
            'bestSeats': ['seat-a'],
        }
        seats = seats_from_seats_selector(seats_selector)
        self.assertEqual(seats[0]['state'], 'available')

    def test_wheelchair_seats_are_flagged_as_a_distinct_type(self):
        seats_selector = {
            'seats': {
                'rows': [{'id': 'row1', 'legend': '1', 'coordinate': 0}],
                'cols': [],
                'seats': [
                    {'id': 'seat-a', 'symbol': '7', 'kind': '0', 'rowId': 'row1',
                     'coordinateX': 0, 'coordinateY': 0, 'wheelchairSeat': True},
                ],
            },
            'selectedSeats': {'list': []},
            'bestSeats': [],
        }
        seats = seats_from_seats_selector(seats_selector)
        self.assertEqual(seats[0]['type'], 'wheelchair')


class TestCheckSeats(unittest.TestCase):
    def _fake_opener_sequence(self, add_tickets_body, abandon_status=204, abandon_raises=False):
        calls = []
        order_url = 'https://www.nfkino.no/order/78146db6-fb72-4ce1-b8a0-892fe89c60c8'

        def fake_opener(req, timeout=15):
            calls.append((req.get_method(), req.full_url))
            if req.full_url == 'https://nfkino.no/screening/cinema-1/screening-1':
                return FakeResponse(ORDER_PAGE_HTML.encode('utf-8'))
            if req.full_url == f'{order_url}/reserve_seats':
                return FakeResponse(json.dumps({'tickets_selector': TICKETS_SELECTOR_HTML}).encode('utf-8'))
            if req.full_url == f'{order_url}/add_tickets':
                return FakeResponse(json.dumps(add_tickets_body).encode('utf-8'))
            if req.full_url == f'{order_url}/abandon':
                if abandon_raises:
                    raise RuntimeError('network blip')
                return FakeResponse(status=abandon_status)
            raise AssertionError(f'unexpected request: {req.get_method()} {req.full_url}')

        return fake_opener, calls

    def test_happy_path_returns_seats_and_attempts_cleanup(self):
        seats_selector = {
            'isGeneralAdmissionScreening': False,
            'seats': {
                'rows': [{'id': 'row1', 'legend': '1', 'coordinate': 0}],
                'cols': [],
                'seats': [
                    {'id': 'seat-a', 'symbol': '1', 'kind': '0', 'rowId': 'row1',
                     'coordinateX': 0, 'coordinateY': 0, 'wheelchairSeat': False},
                ],
            },
            'selectedSeats': {'list': ['seat-a']},
            'bestSeats': ['seat-a'],
        }
        opener, calls = self._fake_opener_sequence({'seats_selector': seats_selector})

        result = check_seats('https://nfkino.no/screening/cinema-1/screening-1', 1, opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['seats'], [
            {'row': 1, 'column': 1, 'state': 'available', 'type': '', 'rowSymbol': '1', 'columnSymbol': '1'},
        ])
        self.assertEqual(result['cancelStatus'], 'attempted')
        self.assertIn(('POST', 'https://www.nfkino.no/order/78146db6-fb72-4ce1-b8a0-892fe89c60c8/abandon'), calls)

    def test_status_error_when_add_tickets_returns_an_error(self):
        opener, calls = self._fake_opener_sequence({'error': 'sold out'})

        result = check_seats('https://nfkino.no/screening/cinema-1/screening-1', 1, opener=opener)

        self.assertEqual(result['status'], 'error')
        self.assertIn('sold out', result['error'])
        # an order was still created, so cleanup must still be attempted
        self.assertEqual(result['cancelStatus'], 'attempted')

    def test_status_error_for_general_admission_screenings(self):
        seats_selector = {'isGeneralAdmissionScreening': True, 'seats': {'rows': [], 'cols': [], 'seats': []},
                           'selectedSeats': {'list': []}, 'bestSeats': []}
        opener, calls = self._fake_opener_sequence({'seats_selector': seats_selector})

        result = check_seats('https://nfkino.no/screening/cinema-1/screening-1', 1, opener=opener)

        self.assertEqual(result['status'], 'error')
        self.assertIn('general admission', result['error'])

    def test_cleanup_failure_is_flagged_not_hidden(self):
        seats_selector = {
            'isGeneralAdmissionScreening': False,
            'seats': {'rows': [], 'cols': [], 'seats': []},
            'selectedSeats': {'list': []},
            'bestSeats': [],
        }
        opener, calls = self._fake_opener_sequence({'seats_selector': seats_selector}, abandon_raises=True)

        result = check_seats('https://nfkino.no/screening/cinema-1/screening-1', 1, opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['cancelStatus'], 'failed')

    def test_not_created_when_the_order_page_itself_fails(self):
        def fake_opener(req, timeout=15):
            raise RuntimeError('connection refused')

        result = check_seats('https://nfkino.no/screening/cinema-1/screening-1', 1, opener=fake_opener)

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['cancelStatus'], 'not_created')


if __name__ == '__main__':
    unittest.main()
