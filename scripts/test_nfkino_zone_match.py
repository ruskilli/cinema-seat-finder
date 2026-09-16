import unittest
from nfkino_zone_match import zone_bounds, row_zone, col_zone, find_contiguous_run, find_match, standard_seats


def seat(row, column, state='available', seat_type=''):
    return {'row': row, 'column': column, 'state': state, 'type': seat_type, 'rowSymbol': str(row)}


class TestStandardSeats(unittest.TestCase):
    def test_excludes_wheelchair_seats(self):
        seats = [seat(0, 0), seat(0, 1), seat(0, 2, seat_type='wheelchair')]
        result = standard_seats(seats)
        self.assertEqual(len(result), 2)
        self.assertEqual({s['column'] for s in result}, {0, 1})

    def test_majority_type_is_treated_as_standard_even_when_nonempty(self):
        seats = [seat(0, c, seat_type='test4') for c in range(3)] + [seat(0, 10, seat_type='wheelchair')]
        result = standard_seats(seats)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(s['type'] == 'test4' for s in result))


class TestZoneBounds(unittest.TestCase):
    def test_computes_thirds_from_min_max_row_and_column(self):
        seats = [seat(r, c) for r in (0, 3, 6) for c in (0, 3, 6)]
        bounds = zone_bounds(seats)
        self.assertEqual(bounds['min_row'], 0)
        self.assertEqual(bounds['max_row'], 6)
        self.assertAlmostEqual(bounds['row_third'], 7 / 3)

    def test_row_zone_front_middle_back(self):
        bounds = zone_bounds([seat(0, 0), seat(9, 0)])
        self.assertEqual(row_zone(0, bounds), 'front')
        self.assertEqual(row_zone(5, bounds), 'middle')
        self.assertEqual(row_zone(9, bounds), 'back')

    def test_col_zone_left_center_right(self):
        bounds = zone_bounds([seat(0, 0), seat(0, 9)])
        self.assertEqual(col_zone(0, bounds), 'left')
        self.assertEqual(col_zone(5, bounds), 'center')
        self.assertEqual(col_zone(9, bounds), 'right')


class TestFindContiguousRun(unittest.TestCase):
    def test_finds_simple_run(self):
        row = [seat(0, 0), seat(0, 1), seat(0, 2)]
        run = find_contiguous_run(row, 3)
        self.assertIsNotNone(run)
        self.assertEqual([s['column'] for s in run], [0, 1, 2])

    def test_booked_seat_breaks_the_run(self):
        row = [seat(0, 0), seat(0, 1, state='booked'), seat(0, 2), seat(0, 3)]
        run = find_contiguous_run(row, 2)
        self.assertEqual([s['column'] for s in run], [2, 3])

    def test_column_gap_breaks_the_run_even_if_available(self):
        row = [seat(0, 0), seat(0, 1), seat(0, 8), seat(0, 9)]
        self.assertIsNone(find_contiguous_run(row, 3))

    def test_non_positive_count_never_matches(self):
        row = [seat(0, 0), seat(0, 1)]
        self.assertIsNone(find_contiguous_run(row, 0))


class TestFindMatch(unittest.TestCase):
    def test_end_to_end_match_in_requested_zone(self):
        front_row = [seat(0, c) for c in range(4)]
        back_row = [seat(9, 0), seat(9, 1, state='booked'), seat(9, 2), seat(9, 3)]
        result = find_match(front_row + back_row, n=3, zone_row='back')
        self.assertFalse(result['matched'])
        result_front = find_match(front_row + back_row, n=3, zone_row='front')
        self.assertTrue(result_front['matched'])

    def test_find_match_respects_zone_col(self):
        row = [seat(0, c) for c in range(3)] + [seat(0, c, state='booked') for c in range(3, 9)]
        result_left = find_match(row, n=3, zone_col='left')
        self.assertTrue(result_left['matched'])
        result_right = find_match(row, n=3, zone_col='right')
        self.assertFalse(result_right['matched'])


if __name__ == '__main__':
    unittest.main()
