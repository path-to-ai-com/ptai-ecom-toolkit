"""Der Umzug der Maßnahmen eines Stores in den Ordner der Marke (Spec 2026-10-08, Abschnitt 11)."""
import contextlib
import io
import unittest

from audit import brand_migrate, measures

from tests import brand_support as bs

V1 = {"next_id": 9, "measures": [
    {"id": "M-001", "title": "Kaufleiste einblenden", "discipline": "cro",
     "evidence": "screens.json > product.png", "confidence": "plausible",
     "leverage": "high", "effort": "small", "responsible": "Path to AI",
     "data_source": "Theme", "check_rule": "Kaufbutton sichtbar.",
     "finding_ref": "CRO-03", "approval": "recommended", "intent": "i",
     "effect": "e", "needs": None, "evidence_text": "Beleg EU.", "type": "measure",
     "status": "in_progress",
     "history": [{"status": "open", "date": "2026-09-01"},
                 {"status": "in_progress", "date": "2026-09-20"}]},
    {"id": "M-004", "title": "Alt-Texte", "discipline": "content", "evidence": "x",
     "confidence": "confirmed", "leverage": "low", "effort": "small",
     "responsible": "Path to AI", "data_source": "Katalog", "check_rule": "r",
     "finding_ref": "SEA-01", "approval": None, "type": "measure",
     "status": "implemented",
     "history": [{"status": "open", "date": "2026-09-01"},
                 {"status": "implemented", "date": "2026-10-02", "run_id": "2026-10-02-audit"}]},
    {"id": "M-007", "title": "Zugang einrichten", "discipline": "data_quality",
     "evidence": "state.json", "confidence": "confirmed", "leverage": "low",
     "effort": "small", "responsible": "Customer", "data_source": "GA4",
     "check_rule": "r", "finding_ref": None, "approval": None, "type": "measure",
     "status": "open", "history": [{"status": "open", "date": "2026-09-01"}]},
    {"id": "M-008", "title": "Verwaist", "discipline": "seo", "evidence": "x",
     "confidence": "confirmed", "leverage": "low", "effort": "small",
     "responsible": "Path to AI", "data_source": "x", "check_rule": "r",
     "finding_ref": "SEO-99", "approval": None, "type": "measure",
     "status": "open", "history": [{"status": "open", "date": "2026-09-01"}]},
]}


class TestBrandMigrate(unittest.TestCase):
    def setUp(self):
        self.brand_ws = bs.make_brand(self, shops=("eu",), doc=False, linked=False)
        self.eu = self.brand_ws / "eu"
        reporting = self.eu / "reporting"
        bs.write_json(reporting / "measures.json", V1)
        (reporting / "measures.md").write_text("# Maßnahmen\n", encoding="utf-8")
        # CRO-03 steht im ersten Audit und im späteren Report; der neueste gilt.
        bs.write_json(reporting / "runs" / "2026-09-01-audit" / "findings" / "conversion.json",
                      {"findings": [{"id": "CRO-03"}]})
        bs.write_json(reporting / "runs" / "2026-10-02-audit" / "findings" / "conversion.json",
                      {"findings": [{"id": "CRO-03"}]})
        # SEA-01 liegt nur noch in einer früheren Fassung (Nachlauf).
        bs.write_json(reporting / "runs" / "2026-10-02-audit" / "revisions" / "01"
                      / "findings" / "sea.json", {"findings": [{"id": "SEA-01"}]})
        bs.write_json(reporting / "runs" / "2026-10-02-audit" / "findings" / "sea.json",
                      {"findings": [{"id": "SEA-02"}]})

    def _migrate(self, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()):
            brand_migrate.main(["--brand-workspace", str(self.brand_ws), "--shop", "eu",
                                *(["--dry-run"] if dry_run else [])])
        return brand_migrate.migrate(self.brand_ws, "eu", dry_run=True)

    def _brand_doc(self):
        return bs.read(self.brand_ws / "reporting" / "measures.json")

    def test_the_eu_list_is_moved_completely(self):
        self._migrate()
        doc = self._brand_doc()
        self.assertEqual((doc["version"], doc["brand"], doc["next_id"]), (2, bs.BRAND, 9))
        self.assertEqual([m["id"] for m in doc["measures"]], ["M-001", "M-004", "M-007", "M-008"])
        first = doc["measures"][0]
        self.assertEqual(first["shops"], ["eu"])
        self.assertEqual(first["by_shop"]["eu"], {
            "status": "in_progress", "history": V1["measures"][0]["history"],
            "finding_run": "2026-10-02-audit", "finding_id": "CRO-03",
            "evidence": "screens.json > product.png", "evidence_text": "Beleg EU."})
        for field in ("status", "history", "evidence", "evidence_text", "finding_ref"):
            self.assertNotIn(field, first)
        for field in ("title", "intent", "approval", "check_rule", "leverage"):
            self.assertEqual(first[field], V1["measures"][0][field])
        self.assertEqual(measures.consistency_problems(doc), [])

    def test_no_run_id_is_invented(self):
        self._migrate()
        for measure in self._brand_doc()["measures"]:
            self.assertNotIn("created_run_id", measure)
        history = self._brand_doc()["measures"][0]["by_shop"]["eu"]["history"]
        self.assertTrue(all("run_id" not in h for h in history))
        # Was schon eine run_id trug, behält sie.
        self.assertEqual(self._brand_doc()["measures"][1]["by_shop"]["eu"]["history"][-1]
                         ["run_id"], "2026-10-02-audit")

    def test_findings_are_resolved_and_the_rest_listed(self):
        report = brand_migrate.migrate(self.brand_ws, "eu")
        by_id = {m["id"]: m["by_shop"]["eu"] for m in self._brand_doc()["measures"]}
        self.assertEqual(by_id["M-004"]["finding_run"], "2026-10-02-audit")
        self.assertEqual((by_id["M-007"]["finding_run"], by_id["M-007"]["finding_id"]),
                         (None, None))
        self.assertEqual((by_id["M-008"]["finding_run"], by_id["M-008"]["finding_id"]),
                         (None, "SEO-99"))
        self.assertEqual(report["unresolved"], [("M-008", "SEO-99")])
        self.assertEqual(report["without_finding"], ["M-007"])

    def test_config_and_old_files(self):
        self._migrate()
        reporting = self.eu / "reporting"
        self.assertEqual(bs.read(reporting / "config.json")["brand_workspace"],
                         str(self.brand_ws))
        self.assertFalse((reporting / "measures.json").exists())
        self.assertEqual(bs.read(reporting / "measures.json.migrated"), V1)
        self.assertTrue((reporting / "measures.md.migrated").exists())
        self.assertTrue((self.brand_ws / "reporting" / "measures.md").exists())
        # Der Store liest danach die Liste der Marke.
        self.assertEqual(measures.load(self.eu)["version"], 2)

    def test_twice_is_once(self):
        self._migrate()
        first = (self.brand_ws / "reporting" / "measures.json").read_bytes()
        config = (self.eu / "reporting" / "config.json").read_bytes()
        report = brand_migrate.migrate(self.brand_ws, "eu")
        self.assertEqual(report["moved"], [])
        self.assertEqual((self.brand_ws / "reporting" / "measures.json").read_bytes(), first)
        self.assertEqual((self.eu / "reporting" / "config.json").read_bytes(), config)

    def test_an_interrupted_move_finishes_on_the_next_call(self):
        # Abbruch nach dem Schreiben der Marke, vor dem Umbenennen.
        self._migrate()
        (self.eu / "reporting" / "measures.json.migrated").rename(
            self.eu / "reporting" / "measures.json")
        report = brand_migrate.migrate(self.brand_ws, "eu")
        self.assertEqual(len(report["skipped"]), 4)
        self.assertFalse((self.eu / "reporting" / "measures.json").exists())

    def test_dry_run_writes_nothing(self):
        report = self._migrate(dry_run=True)
        self.assertEqual(len(report["moved"]), 4)
        self.assertFalse((self.brand_ws / "reporting").exists())
        self.assertNotIn("brand_workspace", bs.read(self.eu / "reporting" / "config.json"))

    def test_feedback_moves_with_shops(self):
        bs.write_json(self.eu / "reporting" / "feedback.json",
                      {"entries": [{"id": "FB-001", "title": "x", "source": "y", "links": []}]})
        self._migrate()
        doc = bs.read(self.brand_ws / "reporting" / "feedback.json")
        self.assertEqual(doc, {"version": 2, "entries": [
            {"id": "FB-001", "title": "x", "source": "y", "links": [], "shops": ["eu"]}]})
        self.assertTrue((self.eu / "reporting" / "feedback.json.migrated").exists())

    def test_no_feedback_is_fine(self):
        self._migrate()
        self.assertFalse((self.brand_ws / "reporting" / "feedback.json").exists())

    def test_an_id_of_another_store_stops_everything(self):
        doc = bs.fixture()
        doc["brand"] = bs.BRAND
        bs.write_json(self.brand_ws / "reporting" / "measures.json", doc)
        with self.assertRaises(SystemExit) as raised:
            brand_migrate.migrate(self.brand_ws, "eu")
        self.assertIn("eigene Zählungen", str(raised.exception))
        self.assertTrue((self.eu / "reporting" / "measures.json").exists())

    def test_a_wrong_shop_is_refused(self):
        bs.write_json(self.brand_ws / "uk" / "reporting" / "config.json",
                      bs.store_config("eu", None))
        with self.assertRaises(SystemExit):
            brand_migrate.migrate(self.brand_ws, "uk")


if __name__ == "__main__":
    unittest.main()
