import unittest
from group_showtimes import group_showtimes


def show(movie_title, show_start, **extra):
    return {'movieTitle': movie_title, 'showStart': show_start, 'screenName': 'A',
            'theaterName': 'B', 'firmName': 'C', 'ticketSaleUrl': 'D', **extra}


class TestGroupShowtimes(unittest.TestCase):
    def test_groups_by_movie_title(self):
        shows = [show('Fjord', '2026-09-17T18:00:00'), show('Harila', '2026-09-17T19:00:00')]
        result = group_showtimes(shows)
        self.assertEqual([g['movieTitle'] for g in result], ['Fjord', 'Harila'])

    def test_sorts_groups_alphabetically_by_movie_title(self):
        shows = [show('Zorro', '2026-09-17T18:00:00'), show('Alien', '2026-09-17T18:00:00')]
        result = group_showtimes(shows)
        self.assertEqual([g['movieTitle'] for g in result], ['Alien', 'Zorro'])

    def test_sorts_showtimes_within_a_group_by_start_time(self):
        shows = [
            show('Fjord', '2026-09-17T21:00:00'),
            show('Fjord', '2026-09-17T18:00:00'),
            show('Fjord', '2026-09-17T19:30:00'),
        ]
        result = group_showtimes(shows)
        starts = [s['showStart'] for s in result[0]['showtimes']]
        self.assertEqual(starts, ['2026-09-17T18:00:00', '2026-09-17T19:30:00', '2026-09-17T21:00:00'])

    def test_showtime_entries_omit_the_now_redundant_movie_title(self):
        shows = [show('Fjord', '2026-09-17T18:00:00')]
        result = group_showtimes(shows)
        self.assertNotIn('movieTitle', result[0]['showtimes'][0])
        self.assertEqual(result[0]['showtimes'][0]['screenName'], 'A')

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(group_showtimes([]), [])


if __name__ == '__main__':
    unittest.main()
