#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services import users


class ReferralTests(unittest.TestCase):
    def test_referral_increment_and_bonus_cap(self) -> None:
        with TemporaryDirectory() as tmpdir:
            original_path = users.USERS_PATH
            try:
                users.USERS_PATH = Path(tmpdir) / "users.json"

                referrer, _ = users.ensure_user("referrer@example.com")

                for idx in range(4):
                    referred_email = f"friend{idx}@example.com"
                    _, created = users.ensure_user(referred_email)
                    self.assertTrue(created)
                    applied = users.apply_referral_for_new_user(
                        referred_email,
                        referrer["referral_code"],
                    )
                    self.assertTrue(applied)

                updated_referrer = users.find_user_by_email("referrer@example.com")
                self.assertIsNotNone(updated_referrer)
                self.assertEqual(updated_referrer["referral_count"], 4)
                self.assertEqual(updated_referrer["bonus_destination_slots"], 3)
                self.assertEqual(
                    users.allowed_destinations_for_email("referrer@example.com"),
                    4,
                )
            finally:
                users.USERS_PATH = original_path

    def test_base_destination_limit_env_with_total_cap(self) -> None:
        with TemporaryDirectory() as tmpdir:
            original_path = users.USERS_PATH
            original_env = os.environ.get("BASE_DESTINATION_LIMIT")
            try:
                users.USERS_PATH = Path(tmpdir) / "users.json"
                os.environ["BASE_DESTINATION_LIMIT"] = "3"

                referrer, _ = users.ensure_user("referrer@example.com")
                self.assertEqual(users.allowed_destinations_for_email("referrer@example.com"), 3)

                _, _ = users.ensure_user("friend@example.com")
                applied = users.apply_referral_for_new_user("friend@example.com", referrer["referral_code"])
                self.assertTrue(applied)

                # Base 3 + bonus 1, capped at total 4.
                self.assertEqual(users.allowed_destinations_for_email("referrer@example.com"), 4)
            finally:
                users.USERS_PATH = original_path
                if original_env is None:
                    os.environ.pop("BASE_DESTINATION_LIMIT", None)
                else:
                    os.environ["BASE_DESTINATION_LIMIT"] = original_env


if __name__ == "__main__":
    unittest.main()
