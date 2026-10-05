"""Der Host-Katalog `reference/theme-migration/hosts.json` ist gültig und allgemein.

Ein Muster, das zwei Diensten gehört, entscheidet nach Reihenfolge statt nach
Sinn; ein Muster mit dem Namen eines Shops macht aus der Referenz eine Liste über
einen Kunden.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "reference" / "theme-migration" / "hosts.json"


class TestHostKatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.services = cls.data["services"]

    def test_kennungen_eindeutig_und_kategorien_bekannt(self):
        ids = [s["id"] for s in self.services]
        self.assertEqual(len(ids), len(set(ids)))
        for service in self.services:
            with self.subTest(service=service["id"]):
                self.assertRegex(service["id"], r"^[a-z][a-z0-9_]*$")
                self.assertIn(service["category"], self.data["categories"])
                self.assertTrue(service["name"])
                self.assertTrue(service["hosts"])

    def test_jedes_muster_gehoert_genau_einem_dienst(self):
        seen = {}
        for service in self.services:
            for pattern in service["hosts"]:
                with self.subTest(pattern=pattern):
                    self.assertEqual(pattern, pattern.lower())
                    self.assertNotIn(pattern, seen, f"auch bei {seen.get(pattern)}")
                    self.assertRegex(pattern, r"^[a-z0-9.-]+\.[a-z]{2,}(/[\w./-]*)?$")
                    seen[pattern] = service["id"]

    def test_ausdruecke_lassen_sich_uebersetzen(self):
        for service in self.services:
            for key in ("code", "cookies", "globals"):
                for pattern in service.get(key) or []:
                    with self.subTest(service=service["id"], pattern=pattern):
                        re.compile(pattern)

    def test_kein_bezug_zu_einem_shop(self):
        text = CATALOG.read_text(encoding="utf-8").lower()
        for word in ("beispiel", "myshopify.com/", ".myshopify.com\""):
            self.assertNotIn(word, text)
        for service in self.services:
            for pattern in service["hosts"]:
                self.assertFalse(pattern.endswith((".example", ".test", ".local")), pattern)

    def test_geteilte_hosts_gehoeren_keinem_dienst(self):
        patterns = {p for s in self.services for p in s["hosts"]}
        for shared in ("cloudfront.net", "amazonaws.com", "b-cdn.net", "herokuapp.com", "vercel.app", "netlify.app"):
            self.assertNotIn(shared, patterns)

    def test_nur_shopify_ist_plattform(self):
        self.assertEqual([s["id"] for s in self.services if s.get("platform")], ["shopify"])


if __name__ == "__main__":
    unittest.main()
