import unittest
from datetime import date

from src.dates import (
    easter_sunday,
    italian_public_holidays,
    working_days_inclusive,
    working_days_in_month,
)


class WorkingDayTests(unittest.TestCase):
    def test_easter_and_easter_monday_are_calculated_dynamically(self):
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertIn(date(2026, 4, 6), italian_public_holidays(2026))

    def test_weekday_national_holiday_is_excluded(self):
        self.assertEqual(
            working_days_inclusive(date(2026, 6, 1), date(2026, 6, 3)),
            2,
        )
        self.assertEqual(working_days_in_month(date(2026, 6, 1)), 21)

    def test_august_2026_period_matches_current_sheet(self):
        self.assertEqual(working_days_in_month(date(2026, 8, 1)), 21)
        self.assertEqual(
            working_days_inclusive(date(2026, 8, 1), date(2026, 8, 6)),
            4,
        )


if __name__ == "__main__":
    unittest.main()
