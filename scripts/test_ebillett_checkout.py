import json
import unittest
from ebillett_checkout import (
    check_seats,
    extract_ids,
    parse_group_codes,
    parse_hidden_fields,
    parse_seating_location,
    pick_first_category_id,
    seats_from_seatmap,
)


class FakeResponse:
    def __init__(self, body_bytes=b'', status=200, headers=None):
        self._body = body_bytes
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


SETUP_HTML = '''
<form method="POST" action="/246/events/77439/purchase/setup" id="eb_input_form_id">
<input type="hidden" name="action" value="continue">
<input type="hidden" name="frs_id" value="8352971">
<input type="hidden" name="arrnr" value="77439">
<input type="hidden" name="p_id" value="246">
<input type="hidden" name="movie_id" value="EDI20251106">
<input type="hidden" name="cinema_id" value="139">
<input type="hidden" name="return_url" value="">
<input type="hidden" name="sb_receipt_id" value="">
<input type="hidden" name="campaign_id" value="">
<input type="hidden" name="group_code11"/>
<select class="qtySelect" id="qty_1"></select>
</form>
<script>
this.categories.set(1, {id: 1, navn: "Voksen", pris: "145", prepaid: false});
this.categories.set(2, {id: 2, navn: "Barn u15", pris: "115", prepaid: false});
</script>
'''


class TestExtractIds(unittest.TestCase):
    def test_pulls_p_id_and_arrnr_from_the_ticket_sale_url(self):
        url = 'https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf'
        self.assertEqual(extract_ids(url), ('246', '77439'))


class TestParseHiddenFields(unittest.TestCase):
    def test_extracts_all_known_hidden_fields(self):
        fields = parse_hidden_fields(SETUP_HTML)
        self.assertEqual(fields, {
            'action': 'continue', 'frs_id': '8352971', 'arrnr': '77439', 'p_id': '246',
            'movie_id': 'EDI20251106', 'cinema_id': '139', 'return_url': '',
            'sb_receipt_id': '', 'campaign_id': '',
        })


class TestParseGroupCodes(unittest.TestCase):
    def test_finds_group_code_field_names(self):
        self.assertEqual(parse_group_codes(SETUP_HTML), ['group_code11'])

    def test_returns_empty_list_when_none_present(self):
        self.assertEqual(parse_group_codes('<form></form>'), [])


class TestPickFirstCategoryId(unittest.TestCase):
    def test_picks_the_first_listed_category_id(self):
        self.assertEqual(pick_first_category_id(SETUP_HTML), '1')

    def test_raises_when_no_categories_found(self):
        with self.assertRaises(RuntimeError):
            pick_first_category_id('<script></script>')


class TestParseSeatingLocation(unittest.TestCase):
    def test_extracts_token_and_reservation_id(self):
        location = '/246/events/77439/purchase/uvg1adidnlqp5eljef73vr8s5i/73497231/seating'
        self.assertEqual(
            parse_seating_location(location),
            ('uvg1adidnlqp5eljef73vr8s5i', '73497231'),
        )

    def test_raises_on_unexpected_location_shape(self):
        with self.assertRaises(RuntimeError):
            parse_seating_location('/246/purchase/error')


class TestSeatsFromSeatmap(unittest.TestCase):
    def test_decodes_row_column_state_from_compact_string(self):
        data = {
            'seatplan': [
                {'row': 1, 'seats': '1,105,15,0:1,95,15,0:4,85,15,0'},
                {'row': None, 'seats': ''},
            ]
        }
        seats = seats_from_seatmap(data)
        self.assertEqual(seats, [
            {'row': 1, 'column': 1, 'state': 'available', 'type': '', 'rowSymbol': '1', 'columnSymbol': '1'},
            {'row': 1, 'column': 2, 'state': 'available', 'type': '', 'rowSymbol': '1', 'columnSymbol': '2'},
            {'row': 1, 'column': 3, 'state': 'booked', 'type': '', 'rowSymbol': '1', 'columnSymbol': '3'},
        ])

    def test_state_2_counts_as_available_too(self):
        # "2" means "held by this reservation" - i.e. exactly the seats
        # check_seats() just reserved for the user, so they must count as
        # available or the matcher can never see the seats it just proved
        # exist
        data = {'seatplan': [{'row': 1, 'seats': '2,0,0,0:1,0,0,0'}]}
        seats = seats_from_seatmap(data)
        self.assertEqual([s['state'] for s in seats], ['available', 'available'])

    def test_other_codes_count_as_booked(self):
        # any other non-"1"/"2" code (sold, special seat types, ...) is
        # conservatively treated as not available for a new booking
        data = {'seatplan': [{'row': 1, 'seats': '4,0,0,0:10,0,0,0:1,0,0,0'}]}
        seats = seats_from_seatmap(data)
        self.assertEqual([s['state'] for s in seats], ['booked', 'booked', 'available'])


class TestCheckSeats(unittest.TestCase):
    def _fake_opener_sequence(self, setup_html, post_setup_status, location_header, seatmap_body, cancel_status=200):
        calls = []

        setup_url = 'https://checkout.ebillett.no/246/events/77439/purchase/setup'

        def fake_opener(req, timeout=15):
            calls.append((req.get_method(), req.full_url))
            if req.get_method() == 'GET' and req.full_url.endswith('/purchase?kanal=dxf'):
                return FakeResponse(status=302, headers={'Location': '/246/events/77439/purchase/setup'})
            if req.get_method() == 'GET' and req.full_url == setup_url:
                return FakeResponse(setup_html.encode('utf-8'), status=200)
            if req.get_method() == 'POST' and req.full_url == setup_url:
                body = req.data.decode('utf-8')
                if 'action=cancel' in body:
                    return FakeResponse(b'<HTML><TITLE>Avbryter...</TITLE></HTML>', status=cancel_status)
                return FakeResponse(status=post_setup_status, headers={'Location': location_header} if location_header else {})
            if req.get_method() == 'GET' and '/seatmap' in req.full_url:
                return FakeResponse(json.dumps(seatmap_body).encode('utf-8'), status=200)
            raise AssertionError(f'unexpected request: {req.get_method()} {req.full_url}')

        return fake_opener, calls

    def test_happy_path_returns_seats_and_attempts_cancel(self):
        opener, calls = self._fake_opener_sequence(
            SETUP_HTML,
            post_setup_status=302,
            location_header='/246/events/77439/purchase/uvg1adidnlqp5eljef73vr8s5i/73497231/seating',
            seatmap_body={'seatplan': [{'row': 1, 'seats': '1,0,0,0'}]},
        )

        result = check_seats('https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf', 2, opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['seats'], [
            {'row': 1, 'column': 1, 'state': 'available', 'type': '', 'rowSymbol': '1', 'columnSymbol': '1'},
        ])
        self.assertEqual(result['cancelStatus'], 'attempted')

    def test_status_error_when_setup_post_does_not_redirect(self):
        # a 200 instead of 302 means the reservation was never actually
        # created (e.g. malformed category/quantity data)
        opener, calls = self._fake_opener_sequence(
            SETUP_HTML, post_setup_status=200, location_header=None, seatmap_body={},
        )

        result = check_seats('https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf', 2, opener=opener)

        self.assertEqual(result['status'], 'error')
        self.assertIn('reservation', result['error'])
        self.assertEqual(result['cancelStatus'], 'not_created')

    def test_cancel_failure_is_flagged_not_hidden(self):
        setup_url = 'https://checkout.ebillett.no/246/events/77439/purchase/setup'

        def fake_opener(req, timeout=15):
            if req.get_method() == 'GET' and req.full_url.endswith('/purchase?kanal=dxf'):
                return FakeResponse(status=302, headers={'Location': '/246/events/77439/purchase/setup'})
            if req.get_method() == 'GET' and req.full_url == setup_url:
                return FakeResponse(SETUP_HTML.encode('utf-8'), status=200)
            if req.get_method() == 'POST' and req.full_url == setup_url:
                body = req.data.decode('utf-8')
                if 'action=cancel' in body:
                    raise RuntimeError('network blip')
                return FakeResponse(status=302, headers={
                    'Location': '/246/events/77439/purchase/uvg1adidnlqp5eljef73vr8s5i/73497231/seating'})
            if req.get_method() == 'GET' and '/seatmap' in req.full_url:
                return FakeResponse(json.dumps({'seatplan': []}).encode('utf-8'), status=200)
            raise AssertionError(f'unexpected request: {req.get_method()} {req.full_url}')

        result = check_seats('https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf', 2, opener=fake_opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['cancelStatus'], 'failed')
        self.assertIn('cancel failed', result['error'])


if __name__ == '__main__':
    unittest.main()
