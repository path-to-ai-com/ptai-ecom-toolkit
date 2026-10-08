"""Offene Befunde vor dem Launch: Prüfberichte und Prüfliste, erledigt nur mit klarem Vermerk."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import launch_findings as lf  # noqa: E402

FIXTURES = ROOT / "scripts" / "tests" / "fixtures" / "theme" / "seo"


class TestMarkdownReport(unittest.TestCase):
    def setUp(self):
        self.items = lf.parse_markdown_report((FIXTURES / "verify-findings.md").read_text(encoding="utf-8"),
                                              "verify-findings.md")
        self.by_state = {s: [i["label"] for i in self.items if i["state"] == s] for s in ("open", "done", "deferred")}

    def test_nur_abschnitte_vor_dem_launch_und_blocker(self):
        self.assertEqual(len(self.items), 10)
        self.assertFalse(any("Sitemap" in i["label"] for i in self.items), "Nach dem Launch zählt nicht")
        self.assertFalse(any("Zwei Blocker" in i["label"] for i in self.items), "Zusammenfassung zählt nicht")

    def test_offen_ist_alles_ohne_klaren_vermerk(self):
        opened = " | ".join(self.by_state["open"])
        self.assertIn("B-02", opened, "Im Entwurf heißt nicht erledigt")
        self.assertIn("hreflang fehlt", opened)
        self.assertIn("Tag Manager", opened, "nach Launch ohne Person und Datum ist offen")
        self.assertIn("WebSite-Auszeichnung", opened)
        self.assertEqual(len(self.by_state["open"]), 4)

    def test_erledigt_ueber_statusspalte_haken_und_status_im_text(self):
        done = " | ".join(self.by_state["done"])
        for text in ("B-01", "og:image", "robots.txt", "Blog-Übersicht"):
            self.assertIn(text, done)

    def test_verschoben_nur_mit_person_und_datum(self):
        deferred = [i for i in self.items if i["state"] == "deferred"]
        self.assertEqual(sorted(d["deferral"]["by"] for d in deferred), ["Beispiel Person", "Beispiel Person"])
        self.assertEqual(sorted(d["deferral"]["at"] for d in deferred), ["20.10.2026", "2026-10-20"])
        self.assertIsNone(lf._deferral("verschoben auf später"))
        self.assertIsNone(lf._deferral("verschoben von Beispiel Person"))

    def test_findings_json_mit_verschiebung(self):
        data = {"findings": [
            {"severity": "before_launch", "description": "hreflang", "status": "open"},
            {"severity": "blocker", "description": "Menü", "status": "fixed"},
            {"severity": "before_launch", "description": "Sterne", "deferred_by": "Beispiel Person",
             "deferred_at": "2026-10-20"},
            {"severity": "after_launch", "description": "später"}]}
        items = lf.parse_findings_json(data, "findings.json")
        self.assertEqual([i["state"] for i in items], ["open", "done", "deferred"])


class TestReportPaths(unittest.TestCase):
    def test_ordner_muster_drive_pfad_und_fehlendes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "drive" / "projects" / "beispiel"
            project.mkdir(parents=True)
            (project / "verify-findings.md").write_text("x", encoding="utf-8")
            (project / "notes.txt").write_text("x", encoding="utf-8")
            (root / "ws").mkdir()
            files, unresolved = lf.report_files(["{drive_path}/projects/beispiel", "fehlt/*.md", "../drive/projects/*/*.md"],
                                                root / "ws", {"drive_path": str(root / "drive")})
            self.assertEqual([f.name for f in files], ["verify-findings.md"])
            self.assertEqual(unresolved, ["fehlt/*.md"])

    def test_markdown_ohne_launch_abschnitt_ist_kein_bericht(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.md"
            path.write_text("# Journal\n\n- Eintrag\n", encoding="utf-8")
            self.assertFalse(lf.is_report(path, lf.read_report(path)))
            findings = Path(tmp) / "findings.json"
            findings.write_text(json.dumps({"findings": []}))
            self.assertTrue(lf.is_report(findings, lf.read_report(findings)), "leere findings.json ist ein Bericht")


class TestChecklist(unittest.TestCase):
    def test_abgehakt_verschoben_abgedeckt_offen(self):
        items = lf.parse_checklist((FIXTURES / "checklist.md").read_text(encoding="utf-8"))
        self.assertEqual([i["id"] for i in items], ["P01", "P02", "P03", "P04", "P05", "P06", "P07"])
        self.assertIn("x-default", items[2]["text"], "Folgezeile gehört zum Punkt")
        statuses = {"seo-hreflang": "ok", "seo-open-graph": "missing", "seo-structured-data": "ok",
                    "seo-pages": "ok"}
        result = lf.evaluate_checklist(items, statuses)
        self.assertEqual([i["id"] for i in result["done"]], ["P01"])
        self.assertEqual([i["id"] for i in result["deferred"]], ["P07"])
        self.assertEqual([i["id"] for i in result["covered"]], ["P03", "P05", "P06"])
        self.assertEqual([i["id"] for i in result["open"]], ["P02", "P04"])
        self.assertEqual(result["open"][1]["failing"], ["seo-open-graph"])

    def test_pfad_mit_products_ist_keine_produktauszeichnung(self):
        self.assertEqual(lf.checks_for("PRODC zeigt auf `/products/beispielring`"), [])
        self.assertEqual(lf.checks_for("`aggregateRating` auf PRODR"), ["seo-structured-data"])


if __name__ == "__main__":
    unittest.main()
