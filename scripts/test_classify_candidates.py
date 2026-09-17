import unittest
from classify_candidates import classify


def show(firm_name='', ticket_url='', **extra):
    return {'movieTitle': 'X', 'showStart': '2026-09-17T20:00:00', 'screenName': 'A',
            'theaterName': 'B', 'firmName': firm_name, 'ticketSaleUrl': ticket_url, **extra}


class TestClassify(unittest.TestCase):
    def test_classifies_filmgrail_by_firm_name(self):
        shows = [show(firm_name='Trondheim Kino'), show(firm_name='Bergen kino')]
        result = classify(shows)
        self.assertEqual(result['filmgrail'], shows)

    def test_classifies_odeon_by_domain_not_firm_name(self):
        s = show(firm_name='Stavanger Kino', ticket_url='https://www.odeonkino.no/booking/kjop/abc')
        result = classify([s])
        self.assertEqual(result['odeon'], [s])

    def test_classifies_ebillett_by_domain(self):
        s = show(ticket_url='https://checkout.ebillett.no/246/events/77439/purchase?kanal=dxf')
        result = classify([s])
        self.assertEqual(result['ebillett'], [s])

    def test_classifies_nfkino_by_domain(self):
        s = show(ticket_url='https://nfkino.no/screening/abc/def')
        result = classify([s])
        self.assertEqual(result['nfkino'], [s])

    def test_out_of_scope_for_unmatched(self):
        s = show(firm_name='Bygdekinoen', ticket_url='')
        result = classify([s])
        self.assertEqual(result['out_of_scope'], [s])

    def test_missing_ticket_sale_url_is_out_of_scope(self):
        s = show(firm_name='Some Cinema', ticket_url='')
        result = classify([s])
        self.assertEqual(result['out_of_scope'], [s])

    def test_empty_input_returns_all_empty_groups(self):
        result = classify([])
        self.assertEqual(result, {
            'filmgrail': [], 'odeon': [], 'ebillett': [], 'nfkino': [], 'out_of_scope': [],
        })

    def test_preserves_order_within_each_group(self):
        a = show(firm_name='Trondheim Kino', screenName='first')
        b = show(firm_name='Trondheim Kino', screenName='second')
        result = classify([a, b])
        self.assertEqual(result['filmgrail'], [a, b])


if __name__ == '__main__':
    unittest.main()
