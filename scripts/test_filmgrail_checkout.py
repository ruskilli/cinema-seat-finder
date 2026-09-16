import json
import unittest
import urllib.parse
from filmgrail_checkout import (
    base_url,
    cancel,
    check_seats,
    extract_seatmap,
    get_seatmap_html,
    get_tickets_categories_data,
    pick_standard_ticket,
    set_tickets,
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


def page_html_with_blocks(*blocks):
    """Build minimal HTML embedding one `const data = ...` script per block,
    the same shape a real showtime page uses."""
    parts = []
    for block in blocks:
        encoded = urllib.parse.quote(json.dumps(block))
        parts.append(f'<script type="module">const data = JSON.parse(decodeURIComponent("{encoded}"));</script>')
    return '<html><body>' + ''.join(parts) + '</body></html>'


VOKSEN_TICKET = {'id': 'VKS||', 'title': 'voksen', 'price': 180}
SAMPLE_BLOCK_DATA = {
    '_blockName': 'TicketsCategories',
    'id': '1-112034-51438',
    'tickets': [VOKSEN_TICKET, {'id': 'BRN||', 'title': 'Barn', 'price': 155}],
}

# Bergen kino uses different ticket ids/titles than Trondheim Kino for the
# same platform - the standard/adult category still happens to be listed
# first, same as Trondheim's, which is the heuristic pick_standard_ticket relies on.
ORDINAERE_TICKET = {'id': '115608', 'title': 'Ordinære billetter', 'price': 160, 'disabled': False}
BERGEN_BLOCK_DATA = {
    '_blockName': 'TicketsCategories',
    'id': '2952647',
    'tickets': [ORDINAERE_TICKET, {'id': '115645', 'title': 'barn', 'price': 120, 'disabled': False}],
}


class TestBaseUrl(unittest.TestCase):
    def test_derives_scheme_and_host_from_the_ticket_sale_url(self):
        self.assertEqual(
            base_url('https://www.bergenkino.no/showtime/2952647'),
            'https://www.bergenkino.no',
        )

    def test_ignores_the_path(self):
        self.assertEqual(
            base_url('https://www.trondheimkino.no/showtime/1-112034-51438'),
            'https://www.trondheimkino.no',
        )


class TestPickStandardTicket(unittest.TestCase):
    def test_returns_the_first_enabled_ticket(self):
        tickets = [VOKSEN_TICKET, {'id': 'BRN||', 'title': 'Barn'}]
        self.assertEqual(pick_standard_ticket(tickets), VOKSEN_TICKET)

    def test_skips_disabled_tickets(self):
        sold_out = {'id': 'X', 'title': 'sold out category', 'disabled': True}
        tickets = [sold_out, VOKSEN_TICKET]
        self.assertEqual(pick_standard_ticket(tickets), VOKSEN_TICKET)

    def test_raises_when_no_enabled_ticket_exists(self):
        with self.assertRaises(RuntimeError):
            pick_standard_ticket([{'id': 'X', 'disabled': True}])


class TestGetTicketsCategoriesData(unittest.TestCase):
    def test_finds_the_ticketscategories_block_among_others(self):
        html = page_html_with_blocks(
            {'_blockName': 'CinemaMasterPage', 'path': '/showtime/1-112034-51438'},
            SAMPLE_BLOCK_DATA,
            {'_blockName': 'Footer1'},
        )

        def fake_opener(req, timeout=15):
            return FakeResponse(html.encode('utf-8'))

        data = get_tickets_categories_data('https://www.trondheimkino.no/showtime/1-112034-51438', opener=fake_opener)
        self.assertEqual(data['_blockName'], 'TicketsCategories')
        self.assertEqual(data['id'], '1-112034-51438')

    def test_raises_when_no_ticketscategories_block_present(self):
        html = page_html_with_blocks({'_blockName': 'Footer1'})

        def fake_opener(req, timeout=15):
            return FakeResponse(html.encode('utf-8'))

        with self.assertRaises(RuntimeError):
            get_tickets_categories_data('https://www.trondheimkino.no/showtime/x', opener=fake_opener)


class TestSetTickets(unittest.TestCase):
    def test_sends_n_copies_of_the_first_enabled_ticket_by_default(self):
        captured = {}

        def fake_opener(req, timeout=15):
            captured['url'] = req.full_url
            captured['body'] = json.loads(req.data.decode('utf-8'))
            return json_response({'transactionId': 't-1', 'nextStep': '/checkout/seatmap/t-1'})

        response = set_tickets('https://www.trondheimkino.no', SAMPLE_BLOCK_DATA, 3, fake_opener)
        self.assertEqual(response['transactionId'], 't-1')
        self.assertEqual(captured['body']['methodData'], [[VOKSEN_TICKET] * 3, []])
        self.assertEqual(captured['body']['blockData'], SAMPLE_BLOCK_DATA)
        self.assertTrue(captured['url'].startswith('https://www.trondheimkino.no/api/'))

    def test_uses_the_venues_own_standard_ticket_category(self):
        # Bergen kino's standard/adult ticket has a different id/title than
        # Trondheim's - set_tickets must not assume a fixed ticket id.
        captured = {}

        def fake_opener(req, timeout=15):
            captured['body'] = json.loads(req.data.decode('utf-8'))
            return json_response({'transactionId': 't-1', 'nextStep': '/checkout/seatmap/t-1'})

        set_tickets('https://www.bergenkino.no', BERGEN_BLOCK_DATA, 2, fake_opener)
        self.assertEqual(captured['body']['methodData'], [[ORDINAERE_TICKET] * 2, []])

    def test_raises_when_ticket_id_not_offered(self):
        def fake_opener(req, timeout=15):
            self.fail('should not make a request when the ticket id is invalid')

        with self.assertRaises(RuntimeError):
            set_tickets('https://www.trondheimkino.no', SAMPLE_BLOCK_DATA, 1, fake_opener, ticket_id='NOPE||')


class TestCancel(unittest.TestCase):
    def test_sends_the_transaction_id_as_the_sole_method_arg(self):
        captured = {}

        def fake_opener(req, timeout=15):
            captured['url'] = req.full_url
            captured['body'] = json.loads(req.data.decode('utf-8'))
            return json_response({'result': True})

        response = cancel('https://www.trondheimkino.no', SAMPLE_BLOCK_DATA, 't-1', fake_opener)
        self.assertTrue(response['result'])
        self.assertEqual(captured['body']['methodData'], ['t-1'])
        self.assertTrue(captured['url'].startswith('https://www.trondheimkino.no/api/'))


class TestGetSeatmapHtml(unittest.TestCase):
    def test_returns_the_html_field(self):
        captured = {}

        def fake_opener(req, timeout=15):
            captured['url'] = req.full_url
            return json_response({'master': 'x', 'pageTitle': 'y', 'html': '<div>seatmap</div>'})

        html = get_seatmap_html('https://www.bergenkino.no', 't-1', fake_opener)
        self.assertEqual(html, '<div>seatmap</div>')
        self.assertEqual(captured['url'], 'https://www.bergenkino.no/checkout/seatmap/t-1')


class TestExtractSeatmap(unittest.TestCase):
    def _encode_seats(self, seats):
        return urllib.parse.quote(json.dumps(seats))

    def test_extracts_a_simple_seat_array(self):
        seats = [
            {'id': '0', 'rowSymbol': '1', 'row': 0, 'columnSymbol': '1', 'column': 0,
             'state': 'available', 'type': ''},
            {'id': '1', 'rowSymbol': '1', 'row': 0, 'columnSymbol': '2', 'column': 1,
             'state': 'booked', 'type': ''},
        ]
        # surround with unrelated encoded content on both sides, like the
        # real ~130KB server-rendered fragment does
        html = 'noise%20before' + self._encode_seats(seats) + 'noise%20after'
        result = extract_seatmap(html)
        self.assertEqual(result, seats)

    def test_extracts_correctly_when_seat_objects_have_nested_braces(self):
        # a seat with an extra nested-object field shouldn't confuse the
        # brace-depth walk that finds each seat object's start
        seats = [
            {'id': '0', 'row': 0, 'column': 0, 'state': 'available', 'type': '',
             'meta': {'nested': True}},
        ]
        html = self._encode_seats(seats)
        result = extract_seatmap(html)
        self.assertEqual(result, seats)

    def test_raises_when_state_marker_absent(self):
        with self.assertRaises(RuntimeError):
            extract_seatmap('no seat data here')


class TestCheckSeats(unittest.TestCase):
    def _fake_opener_sequence(self, page_html, set_tickets_response, seatmap_response, cancel_response):
        calls = []

        def fake_opener(req, timeout=15):
            calls.append(req.full_url)
            if 'methodName=setTickets' in req.full_url:
                return json_response(set_tickets_response)
            if 'methodName=cancel' in req.full_url:
                return json_response(cancel_response)
            if '/checkout/seatmap/' in req.full_url:
                return json_response(seatmap_response)
            return FakeResponse(page_html.encode('utf-8'))

        return fake_opener, calls

    def test_happy_path_returns_seats_and_cancels(self):
        seats = [{'id': '0', 'row': 0, 'column': 0, 'state': 'available', 'type': '',
                  'rowSymbol': '1', 'columnSymbol': '1'}]
        seatmap_html = urllib.parse.quote(json.dumps(seats))
        page_html = page_html_with_blocks(SAMPLE_BLOCK_DATA)
        opener, calls = self._fake_opener_sequence(
            page_html,
            {'transactionId': 't-1', 'nextStep': '/checkout/seatmap/t-1'},
            {'html': seatmap_html},
            {'result': True},
        )

        result = check_seats('https://www.trondheimkino.no/showtime/1-112034-51438', 2, opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['cancelStatus'], 'cancelled')
        self.assertEqual(result['seats'], [
            {'row': 0, 'column': 0, 'state': 'available', 'type': '', 'rowSymbol': '1', 'columnSymbol': '1'},
        ])
        self.assertTrue(any('methodName=cancel' in c for c in calls))

    def test_cancels_even_when_seatmap_extraction_fails(self):
        page_html = page_html_with_blocks(SAMPLE_BLOCK_DATA)
        opener, calls = self._fake_opener_sequence(
            page_html,
            {'transactionId': 't-1', 'nextStep': '/checkout/seatmap/t-1'},
            {'html': 'no seat data here'},
            {'result': True},
        )

        result = check_seats('https://www.trondheimkino.no/showtime/1-112034-51438', 2, opener=opener)

        self.assertEqual(result['status'], 'error')
        self.assertIn('seatmap extraction failed', result['error'])
        self.assertEqual(result['cancelStatus'], 'cancelled')

    def test_does_not_attempt_cancel_when_no_transaction_was_created(self):
        page_html = page_html_with_blocks(SAMPLE_BLOCK_DATA)
        opener, calls = self._fake_opener_sequence(
            page_html,
            {'error': 'something went wrong, no transactionId here'},
            {'html': ''},
            {'result': True},
        )

        result = check_seats('https://www.trondheimkino.no/showtime/1-112034-51438', 2, opener=opener)

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['cancelStatus'], 'not_created')
        self.assertFalse(any('methodName=cancel' in c for c in calls))

    def test_uses_the_showtime_urls_own_domain_for_the_api_calls(self):
        # This is what lets the same client work against other towns on the
        # same platform (e.g. Bergen kino), not just Trondheim Kino.
        seats = [{'id': '0', 'row': 0, 'column': 0, 'state': 'available', 'type': '',
                  'rowSymbol': '1', 'columnSymbol': '1'}]
        seatmap_html = urllib.parse.quote(json.dumps(seats))
        page_html = page_html_with_blocks(BERGEN_BLOCK_DATA)
        opener, calls = self._fake_opener_sequence(
            page_html,
            {'transactionId': 't-1', 'nextStep': '/checkout/seatmap/t-1'},
            {'html': seatmap_html},
            {'result': True},
        )

        result = check_seats('https://www.bergenkino.no/showtime/2952647', 1, opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertTrue(any(c.startswith('https://www.bergenkino.no/api/') for c in calls))
        self.assertTrue(any(c.startswith('https://www.bergenkino.no/checkout/seatmap/') for c in calls))
        self.assertFalse(any('trondheimkino' in c for c in calls))

    def test_flags_cancel_failure_explicitly_instead_of_hiding_it(self):
        seats = [{'id': '0', 'row': 0, 'column': 0, 'state': 'available', 'type': '',
                  'rowSymbol': '1', 'columnSymbol': '1'}]
        seatmap_html = urllib.parse.quote(json.dumps(seats))
        page_html = page_html_with_blocks(SAMPLE_BLOCK_DATA)
        opener, calls = self._fake_opener_sequence(
            page_html,
            {'transactionId': 't-1', 'nextStep': '/checkout/seatmap/t-1'},
            {'html': seatmap_html},
            {'result': False},
        )

        result = check_seats('https://www.trondheimkino.no/showtime/1-112034-51438', 2, opener=opener)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['cancelStatus'], 'failed')


if __name__ == '__main__':
    unittest.main()
