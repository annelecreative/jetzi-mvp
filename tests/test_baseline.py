#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from services import price_observations


class BaselineCalculationTests(unittest.TestCase):
    def test_baseline_with_enough_observations_returns_average(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        observations = [
            {
                "observed_at": now_iso,
                "origin_airport_code": "SFO",
                "destination_airport_code": "LAX",
                "trip_type": "round_trip",
                "depart_window": "mon,tue",
                "return_window": "min_days:3",
                "price": value,
            }
            for value in [100, 120, 140, 160, 180]
        ]

        baseline = price_observations.calculate_baseline_price(
            observations=observations,
            origin_airport_code="SFO",
            destination_airport_code="LAX",
            trip_type="round_trip",
            depart_window="mon,tue",
            return_window="min_days:3",
            lookback_days=30,
            min_observations=5,
        )

        self.assertEqual(baseline, 140.0)

    def test_baseline_with_insufficient_observations_returns_none(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        observations = [
            {
                "observed_at": now_iso,
                "origin_airport_code": "SFO",
                "destination_airport_code": "LAX",
                "trip_type": "round_trip",
                "depart_window": "mon,tue",
                "return_window": "min_days:3",
                "price": value,
            }
            for value in [100, 120, 140, 160]
        ]

        baseline = price_observations.calculate_baseline_price(
            observations=observations,
            origin_airport_code="SFO",
            destination_airport_code="LAX",
            trip_type="round_trip",
            depart_window="mon,tue",
            return_window="min_days:3",
            lookback_days=30,
            min_observations=5,
        )

        self.assertIsNone(baseline)


if __name__ == "__main__":
    unittest.main()
