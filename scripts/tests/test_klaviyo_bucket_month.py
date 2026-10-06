"""Monats-Buckets von Klaviyo werden dem richtigen Monat zugeordnet.

Klaviyo liefert den Monatsbeginn in der Zeitzone des Accounts als UTC-Zeitstempel.
Östlich von UTC liegt er am letzten Tag des Vormonats.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "klaviyo_pull", ROOT / "skills" / "pull-klaviyo" / "scripts" / "klaviyo_pull.py")
klaviyo_pull = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(klaviyo_pull)


class TestBucketMonth(unittest.TestCase):
    def test_berlin_bucket_belongs_to_the_next_month(self):
        self.assertEqual(klaviyo_pull.bucket_month("2025-08-31T22:00:00+00:00"), "2025-09")

    def test_december_rolls_into_the_next_year(self):
        self.assertEqual(klaviyo_pull.bucket_month("2025-12-31T23:00:00+00:00"), "2026-01")

    def test_bucket_west_of_utc_stays(self):
        self.assertEqual(klaviyo_pull.bucket_month("2025-09-01T04:00:00+00:00"), "2025-09")

    def test_plain_date(self):
        self.assertEqual(klaviyo_pull.bucket_month("2025-09-01"), "2025-09")


if __name__ == "__main__":
    unittest.main()
