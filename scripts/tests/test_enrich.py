"""Einen fertigen Lauf ergänzen, ohne dass sich an Aussage, Kennung oder Zahl etwas bewegt."""
import json
import tempfile
import unittest
from pathlib import Path

from audit import enrich

FINDING = {"id": "CRO-01", "statement": "Der Kaufbutton liegt unter der Erstansicht",
           "metrics": [{"label": "Warenkorb-Rate", "value": "9,1 %", "context": "Produktansichten"}],
           "severity": "hoch"}


class TestMerge(unittest.TestCase):
    def test_the_four_fields_are_added_and_nothing_else_moves(self):
        doc = {"discipline": "cro", "findings": [FINDING]}
        extra = {"findings": [{"id": "CRO-01", "url": "https://beispielshop.test/p",
                               "facts": [{"kind": "effect", "text": "Wer nicht scrollt, sieht keinen Kaufbutton."}],
                               "evidence_text": "9,1 Prozent der Produktansichten führen zu einer Warenkorb-Zugabe.",
                               "proof": {"columns": [{"blocks": [{"type": "metric", "ref": 0}]}]}}]}
        merged, problems, count = enrich.merge(doc, extra, "conversion.json")
        self.assertEqual(problems, [])
        self.assertEqual(count, 4)
        finding = merged["findings"][0]
        for key in ("statement", "metrics", "severity", "id"):
            self.assertEqual(finding[key], FINDING[key])
        self.assertEqual(finding["url"], "https://beispielshop.test/p")
        self.assertNotIn("url", FINDING, "die Eingabe bleibt unverändert")

    def test_an_unknown_id_is_refused(self):
        _, problems, _ = enrich.merge({"findings": [FINDING]}, {"findings": [{"id": "CRO-09", "url": "https://x.test"}]},
                                      "conversion.json")
        self.assertIn("CRO-09", problems[0])

    def test_an_existing_value_is_never_overwritten(self):
        doc = {"findings": [dict(FINDING, url="https://beispielshop.test/a")]}
        _, problems, _ = enrich.merge(doc, {"findings": [{"id": "CRO-01", "url": "https://beispielshop.test/b"}]},
                                      "conversion.json")
        self.assertTrue(any("url ist schon gesetzt" in p for p in problems))

    def test_the_same_value_twice_is_no_conflict(self):
        doc = {"findings": [dict(FINDING, url="https://beispielshop.test/a")]}
        _, problems, count = enrich.merge(doc, {"findings": [{"id": "CRO-01", "url": "https://beispielshop.test/a"}]},
                                          "conversion.json")
        self.assertEqual((problems, count), ([], 0))

    def test_a_statement_or_a_decision_is_refused(self):
        extra = {"findings": [{"id": "CRO-01", "statement": "anders", "decision": {"options": []}}]}
        _, problems, _ = enrich.merge({"findings": [FINDING]}, extra, "conversion.json")
        self.assertIn("decision, statement", problems[0])


class TestEnrich(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name) / "ws"
        self.findings = self.ws / "reporting" / "runs" / "2026-09-08-audit" / "findings"
        self.findings.mkdir(parents=True)
        for name, finding_id in (("conversion.json", "CRO-01"), ("trust.json", "TRS-01")):
            (self.findings / name).write_text(json.dumps({"findings": [dict(FINDING, id=finding_id)]}),
                                              encoding="utf-8")
        self.source = Path(self.tmp.name) / "enrichment"
        self.source.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _extra(self, name, entry):
        (self.source / name).write_text(json.dumps({"findings": [entry]}), encoding="utf-8")

    def _read(self, name):
        return json.loads((self.findings / name).read_text(encoding="utf-8"))["findings"][0]

    def test_one_bad_file_stops_every_file(self):
        self._extra("conversion.json", {"id": "CRO-01", "url": "https://beispielshop.test/p"})
        self._extra("trust.json", {"id": "TRS-09", "url": "https://beispielshop.test/q"})
        result = enrich.enrich(self.ws, "2026-09-08-audit", self.source)
        self.assertTrue(result["problems"])
        self.assertNotIn("url", self._read("conversion.json"), "auch die gute Datei bleibt unberührt")

    def test_a_clean_set_is_written(self):
        self._extra("conversion.json", {"id": "CRO-01", "url": "https://beispielshop.test/p"})
        result = enrich.enrich(self.ws, "2026-09-08-audit", self.source)
        self.assertEqual(result, {"files": {"conversion.json": 1}, "problems": []})
        self.assertEqual(self._read("conversion.json")["url"], "https://beispielshop.test/p")
        self.assertEqual(sorted(p.name for p in self.findings.iterdir()), ["conversion.json", "trust.json"])

    def test_a_dry_run_writes_nothing(self):
        self._extra("conversion.json", {"id": "CRO-01", "url": "https://beispielshop.test/p"})
        enrich.enrich(self.ws, "2026-09-08-audit", self.source, dry_run=True)
        self.assertNotIn("url", self._read("conversion.json"))

    def test_an_enrichment_without_its_findings_file_is_refused(self):
        self._extra("geo.json", {"id": "GEO-01", "url": "https://beispielshop.test/"})
        result = enrich.enrich(self.ws, "2026-09-08-audit", self.source)
        self.assertIn("geo.json", result["problems"][0])


if __name__ == "__main__":
    unittest.main()
