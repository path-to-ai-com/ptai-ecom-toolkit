"""Umsetzbarkeit einer Maßnahme der Marke vor publish: belegt, vollständig, machbar."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from audit import measures, publish, readiness

from tests import brand_support as bs

RUN = "2026-10-07-audit"
TODAY = date(2026, 10, 15)


def measure(mid="M-016", responsible="Customer", confidence="confirmed", status="open",
            finding="WBW-09", shop="eu", run=RUN, **fields):
    """Eine Maßnahme der Marke (v2) für einen Store."""
    entry = {"status": status, "history": [{"status": status, "date": "2026-10-07"}],
             "finding_run": run if finding else None, "finding_id": finding,
             "evidence": "dfs-backlinks.json > summary.broken_backlinks",
             "evidence_text": fields.pop("evidence_text", None)}
    if "items" in fields:
        entry["items"] = fields.pop("items")
    base = {"id": mid, "title": "Backlinks auf Fehlerseiten per 301 umleiten",
            "discipline": "seo", "type": "measure", "confidence": confidence,
            "leverage": "low", "effort": "small", "responsible": responsible,
            "data_source": "Shopify-Admin, URL-Weiterleitungen",
            "check_rule": "Keine Weiterleitung fehlt.", "intent": None, "needs": None,
            "approval": None, "shops": [shop], "by_shop": {shop: entry}}
    return {**base, **fields}


def finding(fid="WBW-09", confidence="confirmed", **fields):
    return {"id": fid, "statement": "Backlinks führen auf Seiten, die nicht mehr funktionieren",
            "confidence": confidence, "fix": "Je Zielseite eine 301-Weiterleitung anlegen.", **fields}


def write_items(run_dir: Path, name: str, rows: int, *, done: int = 0, day="2026-10-07",
                columns=("url_to", "checked_at", "status")) -> str:
    path = run_dir / "items" / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for i in range(rows):
            writer.writerow({"url_to": f"https://eu.beispielmarke.test/alt-{i}", "checked_at": day,
                             "status": "done" if i < done else "open"})
    return f"items/{name}.csv"


class Brand:
    """Marke mit Store EU, einem Lauf und seinen Befunden."""

    def __init__(self, case, measures_list, findings=(), catalog=None):
        doc = {"version": 2, "brand": bs.BRAND, "next_id": 100, "measures": list(measures_list)}
        self.brand_ws = bs.make_brand(case, shops=("eu",), doc=doc)
        self.eu = self.brand_ws / "eu"
        self.run_dir = self.eu / "reporting" / "runs" / RUN
        bs.write_json(self.run_dir / "state.json", {"run_id": RUN, "cadence": "audit"})
        bs.write_json(self.run_dir / "findings" / "competition.json",
                      {"discipline": "competition", "findings": list(findings)})
        if catalog is not None:
            bs.write_json(self.eu / "reporting" / "data" / RUN / "catalog.json", catalog)

    def save(self, measures_list):
        bs.write_json(self.brand_ws / "reporting" / "measures.json",
                      {"version": 2, "brand": bs.BRAND, "next_id": 100, "measures": list(measures_list)})

    def check(self, run_id=None):
        return readiness.check(measures.peek(self.eu), readiness.runs_resolver(self.eu), run_id, TODAY)

    def reasons(self, mid="M-016"):
        return [text for e in self.check() if e["measure"] == mid for text in e["problems"]]


class TestTextRules(unittest.TestCase):
    def test_a_count_of_objects_is_a_quantity(self):
        self.assertEqual(readiness.quantities("37 von 640 Backlinks führen ins Leere"),
                         [(37, "37 Backlinks")])
        self.assertEqual(readiness.quantities("512 Produktbilder ohne Alt-Text"),
                         [(512, "512 Produktbilder")])
        self.assertEqual(readiness.quantities("auf 120 deutschen Produktseiten"),
                         [(120, "120 Produktseiten")])
        self.assertEqual(readiness.quantities("auf 3.000 Seiten"), [(3000, "3.000 Seiten")])

    def test_verbs_decimals_and_single_objects_are_no_quantity(self):
        self.assertEqual(readiness.quantities("17 verlinken darauf"), [])
        self.assertEqual(readiness.quantities("2,6 Bilder je Produkt"), [])
        self.assertEqual(readiness.quantities("1 Seite"), [])
        self.assertEqual(readiness.quantities("in 12 Monaten"), [])

    def test_operator_tools_in_a_recommendation(self):
        self.assertEqual(readiness.operator_tools("In der Linkdatenbank die Zielseiten exportieren"),
                         ["Linkdatenbank"])
        self.assertEqual(readiness.operator_tools("laut DataForSEO"), ["DataForSEO"])
        self.assertEqual(readiness.operator_tools("Seiten aus unserem Crawl"), ["unser Crawl"])
        # Das Crawl-Budget ist Googles, kein Werkzeug von uns.
        self.assertEqual(readiness.operator_tools("Das Crawl-Budget von Google schonen"), [])
        self.assertEqual(readiness.operator_tools("Im Shopify-Admin eine Weiterleitung anlegen"), [])


class TestEvidence(unittest.TestCase):
    def test_a_plausible_finding_keeps_the_task_with_us(self):
        brand = Brand(self, [measure(mid="M-027", finding="CRO-05")],
                      [finding("CRO-05", confidence="plausible")])
        reasons = brand.reasons("M-027")
        self.assertEqual(len(reasons), 1)
        self.assertIn("Befund CRO-05 ist plausible", reasons[0])
        self.assertIn("Prüfschritt", reasons[0])

    def test_the_finding_counts_over_the_measure(self):
        brand = Brand(self, [measure(confidence="confirmed")], [finding(confidence="plausible")])
        self.assertIn("plausible", brand.reasons()[0])

    def test_our_own_measures_are_not_checked(self):
        brand = Brand(self, [measure(responsible="Path to AI")], [finding(confidence="plausible")])
        self.assertEqual(brand.check(), [])

    def test_a_closed_measure_is_no_task(self):
        brand = Brand(self, [measure(status="implemented"), measure(mid="M-017", status="rejected")],
                      [finding(confidence="plausible")])
        self.assertEqual(brand.check(), [])

    def test_a_third_party_measure_is_checked_like_the_brands(self):
        brand = Brand(self, [measure(responsible="Third Party", confidence="plausible", finding=None)])
        self.assertIn("Maßnahme ist plausible", brand.reasons()[0])

    def test_without_the_run_on_this_machine_the_measure_confidence_decides(self):
        brand = Brand(self, [measure(run="2026-09-01-audit", confidence="plausible",
                                     items="items/WBW-09.csv")])
        reasons = brand.reasons()
        self.assertEqual(len(reasons), 1)  # die fehlende Datei ist hier nicht prüfbar
        self.assertIn("Maßnahme ist plausible", reasons[0])


class TestItems(unittest.TestCase):
    def setUp(self):
        self.text = {"intent": "Ihr legt für die 37 Backlinks je eine Weiterleitung an."}

    def test_a_quantity_without_a_list_stops(self):
        brand = Brand(self, [measure(**self.text)], [finding()])
        reasons = brand.reasons()
        self.assertEqual(len(reasons), 1)
        self.assertIn("nennt 37 Backlinks, aber keine Liste", reasons[0])

    def test_a_quantity_in_the_finding_counts_too(self):
        brand = Brand(self, [measure()], [finding(statement="37 Backlinks führen ins Leere")])
        self.assertIn("37 Backlinks", brand.reasons()[0])

    def test_a_complete_dated_list_passes(self):
        brand = Brand(self, [], [finding()])
        ref = write_items(brand.run_dir, "WBW-09", 37, day="2026-10-14")
        brand.save([measure(items=ref, **self.text)])
        self.assertEqual(brand.check(), [])

    def test_a_shorter_list_is_incomplete(self):
        brand = Brand(self, [], [finding()])
        ref = write_items(brand.run_dir, "WBW-09", 30)
        brand.save([measure(items=ref, **self.text)])
        self.assertIn("hat 30 Zeilen, die Maßnahme nennt 37", brand.reasons()[0])

    def test_a_missing_list_file_stops(self):
        brand = Brand(self, [measure(items="items/WBW-09.csv", **self.text)], [finding()])
        self.assertIn("die Datei fehlt", brand.reasons()[0])

    def test_a_list_outside_items_stops(self):
        brand = Brand(self, [measure(items="../measures.json", **self.text)], [finding()])
        self.assertIn("erwartet ist items/<befund>.csv", brand.reasons()[0])

    def test_every_row_carries_its_check_date_and_state(self):
        brand = Brand(self, [], [finding()])
        ref = write_items(brand.run_dir, "WBW-09", 37, columns=("url_to",))
        brand.save([measure(items=ref, **self.text)])
        self.assertIn("ohne Spalte checked_at, status", brand.reasons()[0])
        ref = write_items(brand.run_dir, "WBW-09", 37, day="")
        self.assertIn("37 Zeilen ohne gültiges checked_at", brand.reasons()[0])

    def test_a_list_with_every_row_done_is_no_task(self):
        brand = Brand(self, [], [finding()])
        ref = write_items(brand.run_dir, "WBW-09", 37, done=37)
        brand.save([measure(items=ref, **self.text)])
        self.assertIn("alle 37 Zeilen sind erledigt", brand.reasons()[0])

    def test_a_waiver_with_reason_needs_no_list(self):
        brand = Brand(self, [measure(items_waiver="Eine Einstellung im Theme, gilt für alle Seiten.",
                                     **self.text)], [finding()])
        self.assertEqual(brand.check(), [])

    def test_an_old_list_is_a_hint_not_a_stop(self):
        brand = Brand(self, [], [finding()])
        ref = write_items(brand.run_dir, "WBW-09", 37, day="2026-10-01")
        brand.save([measure(items=ref, **self.text)])
        found = brand.check()
        self.assertEqual(found[0]["problems"], [])
        self.assertIn("14 Tage alt", found[0]["hints"][0])
        self.assertIn("recheck --measure M-016", found[0]["hints"][0])


class TestFeasible(unittest.TestCase):
    def test_a_recommendation_with_our_link_database_stops(self):
        brand = Brand(self, [measure()],
                      [finding(fix="In der Linkdatenbank die Zielseiten exportieren und umleiten.")])
        reasons = brand.reasons()
        self.assertEqual(len(reasons), 1)
        self.assertIn("Werkzeug von Path to AI voraus (Linkdatenbank)", reasons[0])

    def test_alt_texts_against_control_values_in_the_alt_field(self):
        catalog = {"summary": {"images_with_alt_control": 312}}
        alt = {"title": "Alt-Texte für Produktbilder ergänzen", "items_waiver": "Liste folgt im Lauf"}
        brand = Brand(self, [measure(finding="CNT-03", **alt)], [finding("CNT-03")], catalog)
        self.assertIn("312 Bilder tragen im Alt-Feld einen Steuerwert", brand.reasons()[0])
        brand.save([measure(finding="CNT-03", intent="Bilder mit #color_-Wert bleiben, wie sie sind.", **alt)])
        self.assertEqual(brand.check(), [])


class TestStoreList(unittest.TestCase):
    """Liste eines Stores (v1): dieselben Regeln, der Lauf aus created_run_id."""

    def test_v1_measure_is_checked_in_its_run(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = Path(tmp.name)
        bs.write_json(ws / "reporting" / "config.json", {"account_slug": "beispielkunde",
                                                          "brand": "Beispielshop"})
        bs.write_json(ws / "reporting" / "runs" / RUN / "findings" / "conversion.json",
                      {"findings": [finding("CRO-05", confidence="plausible")]})
        backlog = measures.create(measures.empty(), title="Kasse auf Deutsch stellen",
                                  discipline="cro", evidence="screens.json", confidence="plausible",
                                  leverage="medium", effort="small", responsible="Customer",
                                  check_rule="Kasse auf Deutsch", finding_ref="CRO-05", run_id=RUN)
        found = readiness.check(backlog, readiness.runs_resolver(ws), today=TODAY)
        self.assertEqual(found[0]["measure"], "M-001")
        self.assertIsNone(found[0]["shop"])
        self.assertIn("Befund CRO-05 ist plausible", found[0]["problems"][0])


class TestCreate(unittest.TestCase):
    def test_items_go_to_the_store_and_the_waiver_to_the_measure(self):
        doc = measures.create(measures.empty(bs.BRAND), title="Umleiten", discipline="seo",
                              evidence="x", confidence="confirmed", leverage="low", effort="small",
                              responsible="Customer", check_rule="r", finding_ref="WBW-09",
                              shop="eu", run_id=RUN, items="items/WBW-09.csv",
                              items_waiver="  ")
        entry = doc["measures"][0]
        self.assertEqual(entry["by_shop"]["eu"]["items"], "items/WBW-09.csv")
        self.assertNotIn("items_waiver", entry)
        self.assertEqual(measures.project(doc, "eu")["measures"][0]["items"], "items/WBW-09.csv")

    def test_without_items_nothing_new_is_written(self):
        doc = measures.create(measures.empty(), title="T", discipline="seo", evidence="x",
                              confidence="confirmed", leverage="low", effort="small")
        self.assertNotIn("items", doc["measures"][0])


class TestWriteItems(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_a_snapshot_list_becomes_a_dated_csv(self):
        source = bs.write_json(self.root / "dfs-backlinks.json", {
            "pulled_at": "2026-10-07T21:12:12+00:00",
            "broken_backlinks": [{"url_from": "https://a.test/x", "url_to": "https://eu.test/alt",
                                  "dofollow": True}],
            "broken_backlinks_truncated": False})
        rows, day = readiness.items_from_snapshot(source, "broken_backlinks")
        path = readiness.write_items(self.root / "run", "WBW-09", rows, checked_at=day)
        self.assertEqual(path, self.root / "run" / "items" / "WBW-09.csv")
        row = readiness.read_items(path)[0]
        self.assertEqual(row, {"url_from": "https://a.test/x", "url_to": "https://eu.test/alt",
                               "dofollow": "ja", "checked_at": "2026-10-07", "status": "open"})

    def test_a_truncated_list_is_refused(self):
        source = bs.write_json(self.root / "s.json", {"rows": [{"a": 1}], "rows_truncated": True})
        with self.assertRaises(ValueError):
            readiness.items_from_snapshot(source, "rows")

    def test_an_empty_list_or_odd_name_is_refused(self):
        with self.assertRaises(ValueError):
            readiness.write_items(self.root, "WBW-09", [])
        with self.assertRaises(ValueError):
            readiness.write_items(self.root, "../x", [{"a": 1}])

    def test_cli_writes_the_list(self):
        source = bs.write_json(self.root / "s.json", {"rows": [{"url": "https://eu.test/a"}]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = readiness.main(["items", "--run-dir", str(self.root / "run"), "--name", "SEO-04",
                                   "--source", str(source), "--key", "rows"])
        self.assertEqual(code, 0)
        self.assertIn('items "items/SEO-04.csv"', out.getvalue())


class TestRecheck(unittest.TestCase):
    def setUp(self):
        self.brand = Brand(self, [], [finding()])
        ref = write_items(self.brand.run_dir, "WBW-09", 3)
        self.brand.save([measure(items=ref)])
        self.path = self.brand.run_dir / ref

    def test_rows_that_answer_without_error_are_done(self):
        codes = {"https://eu.beispielmarke.test/alt-0": 200,
                 "https://eu.beispielmarke.test/alt-1": 404}
        result = readiness.recheck(self.path, today=TODAY, delay=0, fetch=codes.get)
        rows = readiness.read_items(self.path)
        self.assertEqual([r["status"] for r in rows], ["done", "open", "open"])
        self.assertEqual([r["checked_at"] for r in rows], ["2026-10-15", "2026-10-15", "2026-10-07"])
        self.assertEqual(rows[1]["checked_status"], "404")
        self.assertEqual((result["done"], result["open"]), (1, 2))

    def test_against_a_fresh_snapshot(self):
        fresh = bs.write_json(self.brand.run_dir.parent / "fresh.json",
                              {"images": [{"url_to": "https://eu.beispielmarke.test/alt-2"}]})
        result = readiness.recheck(self.path, against=fresh, key="images", match="url_to", today=TODAY)
        self.assertEqual((result["done"], result["open"]), (2, 1))

    def test_cli_finds_the_list_of_a_measure_and_reports_all_done(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch("audit.readiness.fetch_status", lambda url, timeout=20: 200), \
                mock.patch("audit.readiness.time.sleep"):
            code = readiness.main(["recheck", "--workspace", str(self.brand.eu), "--measure", "M-016"])
        self.assertEqual(code, 0)
        self.assertIn("3 von 3 Zeilen erledigt", out.getvalue())
        self.assertIn("als erledigt melden", out.getvalue())
        # Danach ist die Maßnahme keine Aufgabe mehr.
        self.assertIn("alle 3 Zeilen sind erledigt", self.brand.reasons()[0])


class TestPublish(unittest.TestCase):
    """publish hält eine nicht umsetzbare Maßnahme der Marke an, nur bei Läufen mit Befunden."""

    def setUp(self):
        self.brand = Brand(self, [measure(mid="M-027", finding="CRO-05")],
                           [finding("CRO-05", confidence="plausible")])
        self.target = self.brand.brand_ws.parent / "bucket"

    def test_an_audit_with_an_unready_measure_copies_nothing(self):
        with self.assertRaises(SystemExit) as raised:
            publish.prepare(self.brand.eu, RUN, self.target)
        self.assertIn("M-027 (eu): Befund CRO-05 ist plausible", str(raised.exception))
        self.assertFalse(self.target.exists())

    def test_brand_only_stops_too(self):
        with self.assertRaises(SystemExit):
            publish.prepare_brand_only(self.brand.eu, self.target)

    def test_a_pulse_runs_without_the_check(self):
        pulse = "2026-10-12-pulse"
        bs.write_json(self.brand.eu / "reporting" / "runs" / pulse / "state.json",
                      {"run_id": pulse, "cadence": "pulse"})
        bs.write_json(self.brand.eu / "reporting" / "runs" / pulse / "pulse.json", {})
        with contextlib.redirect_stderr(io.StringIO()):
            result = publish.prepare(self.brand.eu, pulse, self.target)
        self.assertTrue(result["released"])


if __name__ == "__main__":
    unittest.main()
