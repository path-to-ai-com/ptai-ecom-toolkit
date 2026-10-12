"""Bestand prüfen im Audit eines neuen Stores (Spec ptai-portal 2026-10-08, Abschnitt 8, D10)."""
import json
import os
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from audit import carry_over, measures, portal, report_build, revision

from tests import brand_support as bs

RUN = "2026-11-12-audit"
TODAY = date(2026, 11, 12)


def measure(mid, shops, statuses=None, title=None):
    """Eine Maßnahme der Marke mit einem Eintrag je Store."""
    statuses = statuses or {}
    return {
        "id": mid, "created_run_id": "2026-09-01-audit", "title": title or f"Maßnahme {mid}",
        "discipline": "cro", "type": "measure", "confidence": "plausible", "leverage": "high",
        "effort": "small", "responsible": "Path to AI", "data_source": "Shopify-Theme",
        "check_rule": "Kaufbutton ohne Scrollen sichtbar.", "approval": None,
        "shops": list(shops),
        "by_shop": {s: {"status": statuses.get(s, "open"),
                        "history": [{"status": statuses.get(s, "open"), "date": "2026-09-01",
                                     "run_id": "2026-09-01-audit"}],
                        "finding_run": "2026-09-01-audit", "finding_id": "CRO-03",
                        "evidence": "screens.json > product-mobil.png", "evidence_text": None}
                    for s in shops},
    }


def brand_doc(*items, next_id=100):
    return {"version": 2, "brand": bs.BRAND, "next_id": next_id, "measures": list(items)}


def sheet_row(mid, outcome, **extra):
    return {"id": mid, "outcome": outcome, **extra}


class TestCandidates(unittest.TestCase):
    def test_measures_of_other_stores_are_candidates_own_ones_not(self):
        doc = brand_doc(measure("M-001", ["eu"]), measure("M-002", ["eu", "uk"]))
        to_check, skipped = carry_over.candidates(doc, "uk")
        self.assertEqual([m["id"] for m in to_check], ["M-001"])
        self.assertEqual(skipped, [])

    def test_a_store_the_brand_rejected_is_not_checked(self):
        doc = brand_doc(measure("M-001", ["eu"]), measure("M-002", ["eu"]))
        to_check, skipped = carry_over.candidates(doc, "uk", {"M-002": {"uk"}})
        self.assertEqual([m["id"] for m in to_check], ["M-001"])
        self.assertEqual([s["id"] for s in skipped], ["M-002"])
        self.assertIn("verworfen", skipped[0]["reason"])

    def test_a_measure_rejected_or_obsolete_everywhere_is_not_carried(self):
        doc = brand_doc(
            measure("M-001", ["eu"], {"eu": "rejected"}),          # in der Datei verworfen
            measure("M-002", ["eu"]),                               # von der Marke gemeldet
            measure("M-003", ["eu", "ch"], {"ch": "obsolete"}),     # in EU noch offen
        )
        to_check, skipped = carry_over.candidates(doc, "uk", {"M-002": {"eu"}})
        self.assertEqual([m["id"] for m in to_check], ["M-003"])
        self.assertEqual({s["id"] for s in skipped}, {"M-001", "M-002"})

    def test_a_list_of_one_store_has_no_candidates(self):
        self.assertEqual(carry_over.candidates({"next_id": 2, "measures": []}, "uk"), ([], []))


class TestApplyOutcomes(unittest.TestCase):
    def setUp(self):
        self.doc = brand_doc(measure("M-025", ["eu"]), measure("M-040", ["eu"]),
                             measure("M-050", ["eu"], title="Grundpreis nach deutschem Recht"))

    def apply(self, rows, exclusions=None, known=None):
        return carry_over.apply_outcomes(self.doc, "uk", RUN, rows, exclusions, TODAY, known)

    def test_three_outcomes(self):
        rows = [
            sheet_row("M-025", "applies", finding_id="CRO-02", evidence="screens.json > product-mobil.png",
                      evidence_text="Der Kaufbutton beginnt bei 1.400 Pixeln."),
            sheet_row("M-040", "fulfilled", evidence="crawl.json > findings_index.descriptions"),
            sheet_row("M-050", "not_applicable", reason="Die Grundpreisangabe gilt in UK nicht."),
        ]
        new, summary = self.apply(rows, known={"CRO-02"})
        by_id = {m["id"]: m for m in new["measures"]}

        applies = by_id["M-025"]
        self.assertEqual(applies["shops"], ["eu", "uk"])
        uk = applies["by_shop"]["uk"]
        self.assertEqual(uk["status"], "open")
        self.assertEqual(uk["history"], [{"status": "open", "date": "2026-11-12", "run_id": RUN}])
        self.assertEqual((uk["finding_run"], uk["finding_id"]), (RUN, "CRO-02"))
        self.assertEqual(uk["evidence_text"], "Der Kaufbutton beginnt bei 1.400 Pixeln.")

        fulfilled = by_id["M-040"]["by_shop"]["uk"]
        self.assertEqual(fulfilled["status"], "implemented")
        self.assertEqual(fulfilled["history"][0]["run_id"], RUN)
        self.assertIsNone(fulfilled["finding_id"])

        self.assertEqual(by_id["M-050"]["shops"], ["eu"])
        self.assertNotIn("uk", by_id["M-050"]["by_shop"])
        self.assertEqual([r["id"] for r in summary["not_transferred"]], ["M-050"])
        self.assertIn("gilt in UK nicht", summary["not_transferred"][0]["reason"])
        self.assertEqual(measures.consistency_problems(new), [])
        self.assertEqual(new["next_id"], self.doc["next_id"])

    def test_the_eu_entry_is_untouched(self):
        new, _ = self.apply([sheet_row("M-025", "applies", evidence="x.json > y")])
        self.assertEqual(new["measures"][0]["by_shop"]["eu"], self.doc["measures"][0]["by_shop"]["eu"])

    def test_missing_outcome_reason_or_evidence_writes_nothing(self):
        for rows, needle in (
                ([sheet_row("M-025", None)], "outcome"),
                ([sheet_row("M-050", "not_applicable")], "reason"),
                ([sheet_row("M-040", "fulfilled")], "evidence"),
                ([sheet_row("M-025", "applies", evidence="x", finding_id="CRO-99")], "CRO-99"),
                ([sheet_row("M-999", "applies", evidence="x")], "M-999")):
            with self.subTest(needle=needle), self.assertRaises(carry_over.CarryOverError) as raised:
                self.apply(rows, known={"CRO-02"})
            self.assertIn(needle, str(raised.exception))

    def test_a_rejection_reported_after_prepare_is_skipped(self):
        new, summary = self.apply([sheet_row("M-025", "applies", evidence="x.json > y")],
                                  exclusions={"M-025": {"uk"}})
        self.assertEqual(new["measures"][0]["shops"], ["eu"])
        self.assertEqual([s["id"] for s in summary["skipped"]], ["M-025"])

    def test_twice_is_an_error(self):
        new, _ = self.apply([sheet_row("M-025", "applies", evidence="x.json > y")])
        with self.assertRaises(carry_over.CarryOverError):
            carry_over.apply_outcomes(new, "uk", RUN, [sheet_row("M-025", "applies", evidence="x")],
                                      today=TODAY)

    def test_reanalyze_takes_the_carried_store_back_out(self):
        new, _ = self.apply([sheet_row("M-025", "applies", evidence="x.json > y")])
        reset, removed, _kept = revision.reset_measures(new, shop="uk", run_id=RUN)
        self.assertEqual(removed, 0)
        self.assertEqual(reset["measures"][0]["shops"], ["eu"])
        self.assertNotIn("uk", reset["measures"][0]["by_shop"])


class TestRejectedStoreIsNotChecked(unittest.TestCase):
    """D10 im Folgelauf: ein verworfener Store wird nicht geprüft und nicht wieder geöffnet."""

    def test_reported_rejection_keeps_the_check_unchecked(self):
        m = measure("M-025", ["eu", "uk"])
        self.assertEqual(measures.check(m, {"M-025": False}, shop="uk"), "open")
        self.assertEqual(measures.check(m, {"M-025": False}, shop="uk",
                                        exclusions={"M-025": {"uk"}}), "unchecked")
        # Die Meldung für UK lässt EU unberührt.
        self.assertEqual(measures.check(m, {"M-025": False}, shop="eu",
                                        exclusions={"M-025": {"uk"}}), "open")

    def test_rejected_or_obsolete_in_the_file_keeps_the_check_unchecked(self):
        for status in ("rejected", "obsolete"):
            m = measure("M-025", ["uk"], {"uk": status})
            with self.subTest(status=status):
                self.assertEqual(measures.check(m, {"M-025": False}, shop="uk"), "unchecked")

    def test_portal_exclusions_count_only_rejected_and_obsolete(self):
        reports = [{"shop": "uk", "measure_id": "M-001", "status": "rejected"},
                   {"shop": "eu", "measure_id": "M-001", "status": "in_progress"},
                   {"shop": "ch", "measure_id": "M-002", "status": "obsolete"}]
        self.assertEqual(portal.exclusions(reports), {"M-001": {"uk"}, "M-002": {"ch"}})


class TestWithFiles(unittest.TestCase):
    def setUp(self):
        self.brand_ws = bs.make_brand(self, shops=("eu", "uk"), doc=brand_doc(
            measure("M-025", ["eu"]), measure("M-040", ["eu"]), measure("M-050", ["eu"])))
        self.uk = self.brand_ws / "uk"
        findings = self.uk / "reporting" / "runs" / RUN / "findings"
        bs.write_json(findings / "conversion.json", {
            "discipline": "cro", "run_id": RUN,
            "findings": [{"id": "CRO-02", "statement": "Kaufbutton unter der Erstansicht",
                          "evidence": "screens.json > product-mobil.png"}]})

    def fill(self):
        path = carry_over.path_for(self.uk, RUN)
        sheet = json.loads(path.read_text(encoding="utf-8"))
        outcomes = {"M-025": {"outcome": "applies", "finding_id": "CRO-02",
                              "evidence": "screens.json > product-mobil.png"},
                    "M-040": {"outcome": "fulfilled", "evidence": "crawl.json > findings_index.descriptions"},
                    "M-050": {"outcome": "not_applicable", "reason": "Gilt in UK nicht."}}
        for row in sheet["candidates"]:
            row.update(outcomes.get(row["id"], {}))
        path.write_text(json.dumps(sheet), encoding="utf-8")

    def test_prepare_apply_and_covered_findings(self):
        carry_over.prepare(self.uk, RUN, exclusions={"M-040": {"uk"}})
        sheet = bs.read(carry_over.path_for(self.uk, RUN))
        self.assertEqual([c["id"] for c in sheet["candidates"]], ["M-025", "M-050"])
        self.assertEqual([s["id"] for s in sheet["skipped"]], ["M-040"])
        self.assertEqual(sheet["shop"], "uk")
        self.fill()
        summary = carry_over.apply(self.uk, RUN, exclusions={"M-040": {"uk"}}, today=TODAY)
        self.assertEqual([r["id"] for r in summary["applied"]], ["M-025"])
        doc = bs.read(self.brand_ws / "reporting" / "measures.json")
        self.assertEqual(doc["measures"][0]["shops"], ["eu", "uk"])
        self.assertEqual(doc["measures"][2]["shops"], ["eu"])
        self.assertEqual(carry_over.covered_findings(self.uk, RUN), {"CRO-02"})
        self.assertTrue(bs.read(carry_over.path_for(self.uk, RUN))["applied_at"])

    def test_prepare_keeps_a_filled_sheet(self):
        carry_over.prepare(self.uk, RUN, exclusions={})
        self.fill()
        with self.assertRaises(carry_over.CarryOverError):
            carry_over.prepare(self.uk, RUN, exclusions={})

    def test_cockpit_unreachable_aborts_before_anything_is_written(self):
        with mock.patch.dict(os.environ, {"PTAI_PORTAL_URL": "http://127.0.0.1:9",
                                          "PTAI_PORTAL_TOKEN": "x"}):
            with mock.patch("urllib.request.urlopen",
                            side_effect=portal.urllib.error.URLError("connection refused")):
                with self.assertRaises(portal.PortalError):
                    carry_over.prepare(self.uk, RUN)
                self.assertEqual(carry_over.main(["prepare", "--workspace", str(self.uk),
                                                  "--run-id", RUN]), 1)
        self.assertFalse(carry_over.path_for(self.uk, RUN).exists())

    def test_cockpit_unreachable_at_apply_writes_nothing(self):
        carry_over.prepare(self.uk, RUN, exclusions={})
        self.fill()
        before = (self.brand_ws / "reporting" / "measures.json").read_bytes()
        with mock.patch.object(portal, "reported_statuses",
                               side_effect=portal.PortalError("Cockpit nicht erreichbar")):
            with self.assertRaises(portal.PortalError):
                carry_over.apply(self.uk, RUN, today=TODAY)
        self.assertEqual((self.brand_ws / "reporting" / "measures.json").read_bytes(), before)

    def test_prepare_asks_the_cockpit_for_the_brand_and_store(self):
        with mock.patch.object(portal, "reported_statuses", return_value=[
                {"shop": "uk", "measure_id": "M-025", "status": "rejected"}]) as asked:
            carry_over.prepare(self.uk, RUN)
        self.assertEqual(asked.call_args.args[:2], (bs.BRAND, "uk"))
        sheet = bs.read(carry_over.path_for(self.uk, RUN))
        self.assertEqual(sheet["excluded"], {"M-025": ["uk"]})

    def test_the_report_lists_what_was_not_transferred(self):
        carry_over.prepare(self.uk, RUN, exclusions={})
        self.fill()
        carry_over.apply(self.uk, RUN, exclusions={}, today=TODAY)
        run = SimpleNamespace(findings={}, run=self.uk / "reporting" / "runs" / RUN)
        html_text = report_build.brand_list_blocks(run, "Beispielmarke UK")
        self.assertIn("Nicht übertragen", html_text)
        self.assertIn("M-050", html_text)
        self.assertIn("Gilt in UK nicht.", html_text)


if __name__ == "__main__":
    unittest.main()
