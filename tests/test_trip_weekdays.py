#!/usr/bin/env python3

from __future__ import annotations

from datetime import date
import unittest

from services import flights


class TripWeekdayTests(unittest.TestCase):
    def test_fri_to_sun_allowed_fri_sat_sun(self) -> None:
        allowed = {"fri", "sat", "sun"}
        self.assertTrue(
            flights.is_trip_within_allowed_weekdays(
                depart_date=date(2026, 3, 6),  # Fri
                return_date=date(2026, 3, 8),  # Sun
                allowed_weekdays_set=allowed,
            )
        )

    def test_sat_to_mon_not_allowed_fri_sat_sun(self) -> None:
        allowed = {"fri", "sat", "sun"}
        self.assertFalse(
            flights.is_trip_within_allowed_weekdays(
                depart_date=date(2026, 3, 7),  # Sat
                return_date=date(2026, 3, 9),  # Mon
                allowed_weekdays_set=allowed,
            )
        )

    def test_mon_to_thu_allowed_mon_to_thu(self) -> None:
        allowed = {"mon", "tue", "wed", "thu"}
        self.assertTrue(
            flights.is_trip_within_allowed_weekdays(
                depart_date=date(2026, 3, 2),  # Mon
                return_date=date(2026, 3, 5),  # Thu
                allowed_weekdays_set=allowed,
            )
        )

    def test_mon_to_fri_not_allowed_mon_to_thu(self) -> None:
        allowed = {"mon", "tue", "wed", "thu"}
        self.assertFalse(
            flights.is_trip_within_allowed_weekdays(
                depart_date=date(2026, 3, 2),  # Mon
                return_date=date(2026, 3, 6),  # Fri
                allowed_weekdays_set=allowed,
            )
        )


if __name__ == "__main__":
    unittest.main()
