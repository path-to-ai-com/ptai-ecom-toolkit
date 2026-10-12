"""Die eine Liste offener Punkte: drei Status, Beleg und Verschiebung Pflicht, Gates halten an."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import open_items as oi  # noqa: E402
from theme import run_state  # noqa: E402

FIXTURES = ROOT / "scripts" / "tests" / "fixtures" / "theme" / "seo"
UMBRELLA = ROOT / "scripts" / "tests" / "fixtures" / "theme" / "open-items"


def test_round(items: list) -> dict:
    return {"title": "Testrunde", "intro": "", "sections": [],
            "groups": [{"id": "g1", "title": "Schwerpunkte", "items": items}]}


class Workspace(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        (self.ws / "reporting").mkdir()
        self.config({})
        self.items, _ = oi.init(self.ws)

    def config(self, block: dict) -> None:
        (self.ws / "reporting" / "config.json").write_text(json.dumps({"theme_migration": block}), encoding="utf-8")

    def write(self, rel: str, text: str) -> Path:
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def cli(self, *args) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = oi.main([*args, "--workspace", str(self.ws)])
        return code, json.loads(out.getvalue().strip().splitlines()[-1])


class TestSchema(Workspace):
    def item(self, **values) -> dict:
        base = {"id": "X-01", "title": "Punkt", "severity": "before_launch", "gate": "G5-go-live",
                "status": "open", "source_ids": [], "links": []}
        return {**base, **values}

    def data(self, *items) -> dict:
        return {"kind": "open-items", "schema_version": 1, "items": list(items)}

    def test_eine_leere_liste_ist_gueltig(self):
        self.assertEqual(oi.validate(self.data()), [])

    def test_erledigt_ohne_beleg_ist_ungueltig(self):
        errors = oi.validate(self.data(self.item(status="done")))
        self.assertTrue(any("ohne Beleg" in e for e in errors), errors)

    def test_verschoben_nur_mit_person_und_iso_datum(self):
        errors = oi.validate(self.data(self.item(status="deferred", deferred_by="Beispiel Person",
                                                 deferred_at="20.10.2026")))
        self.assertTrue(any("ohne Datum" in e for e in errors), errors)
        self.assertEqual(oi.validate(self.data(self.item(status="deferred", deferred_by="Beispiel Person",
                                                         deferred_at="2026-10-20"))), [])

    def test_doppelte_id_unbekanntes_gate_und_fremder_status(self):
        errors = oi.validate(self.data(self.item(), self.item(gate="G9", status="in_progress")))
        self.assertTrue(any("doppelt" in e for e in errors))
        self.assertTrue(any("gate" in e for e in errors))
        self.assertTrue(any("status" in e for e in errors))

    def test_eine_ungueltige_liste_wird_nicht_geladen_und_nicht_still_ersetzt(self):
        oi.list_path(self.ws).write_text("{kaputt", encoding="utf-8")
        with self.assertRaises(oi.OpenItemsError):
            oi.load(self.ws)
        with self.assertRaises(oi.OpenItemsError):
            oi.init(self.ws)


class TestStatus(Workspace):
    def test_erledigt_braucht_einen_beleg(self):
        self.items.add(title="hreflang fehlt", ident="S-03")
        with self.assertRaises(oi.OpenItemsError):
            self.items.set_done("S-03", "  ")
        self.items.set_done("S-03", "Abruf Entwurf: hreflang je Sprache vorhanden")
        self.assertEqual(self.items.get("S-03")["status"], "done")

    def test_verschoben_braucht_person_und_datum_deutsches_datum_wird_iso(self):
        self.items.add(title="Sterne an den Kacheln", ident="P07")
        with self.assertRaises(oi.OpenItemsError):
            self.items.defer("P07", "", "2026-10-20")
        with self.assertRaises(oi.OpenItemsError):
            self.items.defer("P07", "Beispiel Person", "später")
        item = self.items.defer("P07", "Beispiel Person", "20.10.2026", "nach dem Launch")
        self.assertEqual((item["deferred_by"], item["deferred_at"]), ("Beispiel Person", "2026-10-20"))

    def test_wieder_offen_nur_mit_grund_und_ohne_alte_verschiebung(self):
        self.items.add(title="Menü", ident="B-01")
        self.items.defer("B-01", "Beispiel Person", "2026-10-20")
        with self.assertRaises(oi.OpenItemsError):
            self.items.reopen("B-01", "")
        item = self.items.reopen("B-01", "Rückmeldung aus der Testrunde")
        self.assertEqual(item["status"], "open")
        self.assertNotIn("deferred_by", item)

    def test_jeder_punkt_nennt_sein_gate_aus_der_schwere(self):
        self.assertEqual(self.items.add(title="a", severity="blocker")["gate"], "G4-acceptance")
        self.assertEqual(self.items.add(title="b")["gate"], "G5-go-live")
        self.assertEqual(self.items.add(title="c", severity="after_launch")["gate"], "after_launch")
        with self.assertRaises(oi.OpenItemsError):
            self.items.add(title="d", gate="irgendwann")

    def test_g5_liest_auch_die_punkte_von_g4(self):
        self.items.add(title="Abnahme", ident="A", gate="G4-acceptance")
        self.items.add(title="Launch", ident="B", gate="G5-go-live")
        self.items.add(title="Später", ident="C", severity="after_launch")
        self.assertEqual([i["id"] for i in self.items.blocking("G4-acceptance")], ["A"])
        self.assertEqual([i["id"] for i in self.items.blocking("G5-go-live")], ["A", "B"])
        self.assertEqual([i["id"] for i in self.items.blocking("after_launch")], ["A", "B", "C"])

    def test_speichern_schreibt_die_ansicht_neu(self):
        self.items.add(title="Pipe | im Titel", ident="S-03")
        self.items.save()
        view = oi.view_path(self.ws).read_text(encoding="utf-8")
        self.assertIn("## Go-Live (G5): 1 offen", view)
        self.assertIn("Pipe \\| im Titel", view)
        self.assertIn("nicht von Hand ändern", view)


class TestImport(Workspace):
    def test_pruefliste_ist_die_abnahme(self):
        result = self.items.merge(oi.from_checklist(FIXTURES / "checklist.md"))
        self.assertEqual(result["created"], ["P01", "P02", "P03", "P04", "P05", "P06", "P07"])
        by_id = {i["id"]: i for i in self.items.items}
        self.assertEqual(by_id["P01"]["status"], "done")
        self.assertIn("abgehakt", by_id["P01"]["evidence"])
        self.assertEqual(by_id["P07"]["status"], "deferred")
        self.assertEqual(by_id["P07"]["deferred_at"], "2026-10-20")
        self.assertEqual({i["gate"] for i in self.items.items}, {"G4-acceptance"})

    def test_bericht_kennungen_aus_der_zeile_kein_wort_ohne_ziffer(self):
        cands = oi.from_report(FIXTURES / "verify-findings.md")
        ids = [c["preferred_id"] for c in cands]
        for ident in ("B-01", "B-02", "S-03", "S-04", "S-06", "C-04"):
            self.assertIn(ident, ids)
        self.assertNotIn("H1", ids, "Zweite H1 ist Text, keine Kennung")
        self.assertNotIn("SEO", ids)
        by_id = {c["preferred_id"]: c for c in cands}
        self.assertEqual((by_id["B-02"]["severity"], by_id["B-02"]["gate"]), ("blocker", "G4-acceptance"))
        self.assertEqual((by_id["S-03"]["severity"], by_id["S-03"]["gate"]), ("before_launch", "G5-go-live"))
        self.assertEqual(by_id["S-04"]["state"], "done")
        self.assertIn("Logo als Rückfall", by_id["S-04"]["evidence"])
        self.assertEqual(by_id["S-06"]["state"], "deferred")

    def test_erneuter_import_legt_nichts_doppelt_an_und_behaelt_den_status(self):
        self.items.merge(oi.from_report(FIXTURES / "verify-findings.md"))
        count = len(self.items.items)
        self.items.set_done("S-03", "Abruf Entwurf 2026-10-08: hreflang vorhanden")
        result = self.items.merge(oi.from_report(FIXTURES / "verify-findings.md"))
        self.assertEqual((result["created"], len(self.items.items)), ([], count))
        self.assertEqual(self.items.get("S-03")["status"], "done", "die Liste ist die Quelle")
        self.assertIn({"id": "S-03", "list": "done", "source": "open",
                       "where": "verify-findings.md, Vor dem Launch"}, result["drift"])

    def test_findings_json_ohne_id_stabil_info_zaehlt_nicht(self):
        path = self.write("migration/verify/2026-10-01/findings.json", json.dumps({"findings": [
            {"checker": "seo", "page_type": "product", "severity": "before_launch", "description": "hreflang fehlt",
             "links": [{"label": "Entwurf", "url": "https://beispielshop.example/?preview_theme_id=1"}]},
            {"checker": "seo", "page_type": "home", "severity": "info", "description": "nur ein Hinweis"},
            {"checker": "design", "page_type": "home", "severity": "blocker", "description": "Menü",
             "status": "fixed"}]}))
        first = self.items.merge(oi.from_findings(path))
        second = self.items.merge(oi.from_findings(path))
        self.assertEqual(len(first["created"]), 2)
        self.assertEqual(second["created"], [])
        menu = next(i for i in self.items.items if i["title"] == "Menü")
        self.assertEqual((menu["status"], menu["evidence"]), ("done", "Status fixed in findings.json"))
        hreflang = next(i for i in self.items.items if i["title"] == "hreflang fehlt")
        self.assertEqual(hreflang["links"], ["https://beispielshop.example/?preview_theme_id=1"])

    def test_findings_json_mit_source_ids_fuehrt_quellen_zusammen(self):
        self.items.merge(oi.from_checklist(FIXTURES / "checklist.md"))
        path = self.write("liste.json", json.dumps({"findings": [
            {"id": "S-05", "source_ids": ["S-05", "P05"], "title": "WebSite fehlt", "severity": "before_launch",
             "status": "open"}]}))
        result = self.items.merge(oi.from_findings(path))
        self.assertEqual(result["created"], [], "P05 ist derselbe Punkt")
        self.assertIn("S-05", self.items.get("P05")["source_ids"])

    def test_testrunde_kennung_je_runde_entscheidung_bleibt_offen(self):
        path = self.write("reporting/runs/2026-09-24-test/test.json", json.dumps(test_round([
            {"id": "TP-01", "title": "Startseite", "text": "ansehen"},
            {"id": "TP-02", "title": "Sterne", "text": "", "status": "decision"},
            {"id": "TP-03", "title": "Menü", "text": "", "status": "done",
             "resolution": {"text": "behoben, Bildpaar im Kundenordner", "links": []}}])))
        result = self.items.merge(oi.from_test_round(path))
        self.assertEqual(result["created"], ["TP-02", "TP-03"], "ohne status zählt ein Punkt nicht")
        self.assertEqual(self.items.get("TP-02")["status"], "open")
        self.assertEqual(self.items.get("TP-02")["owner"], "Team")
        self.assertEqual(self.items.get("TP-03")["evidence"], "behoben, Bildpaar im Kundenordner")
        other = self.write("reporting/runs/2026-11-01-test/test.json", json.dumps(test_round([
            {"id": "TP-02", "title": "Neue Frage", "text": "", "status": "open"}])))
        result = self.items.merge(oi.from_test_round(other))
        self.assertEqual(result["created"], ["TP-02-2"], "TP-02 einer neuen Runde ist ein neuer Punkt")

    def test_testrunde_bekommt_den_stand_der_liste_zurueck(self):
        path = self.write("reporting/runs/2026-09-24-test/test.json", json.dumps(test_round([
            {"id": "TP-02", "title": "Sterne", "text": "", "status": "decision"},
            {"id": "TP-03", "title": "Menü", "text": "", "status": "done",
             "resolution": {"text": "behoben", "links": []}}])))
        self.items.merge(oi.from_test_round(path))
        self.items.set_done("TP-02", "entschieden im Termin: wie heute")
        self.items.reopen("TP-03", "auf dem Handy wieder kaputt")
        changed = oi.sync_test_round(self.items, path)
        self.assertEqual(changed, [{"id": "TP-02", "from": "decision", "to": "done"},
                                   {"id": "TP-03", "from": "done", "to": "open"}])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([i["status"] for i in data["groups"][0]["items"]], ["done", "open"])


class TestUmbrellaKeys(Workspace):
    """Eine Sammelkennung (LC-2.7 über sechs Testpunkte) legt nie verschiedene Punkte zusammen."""

    TESTS = ["AB-01", "AB-09", "AB-10", "AB-11", "TP-06", "TP-07"]

    def findings(self) -> list:
        return oi.from_findings(UMBRELLA / "findings-umbrella.json")

    def test_findings_mit_gemeinsamer_sammelkennung_bleiben_sechs_punkte(self):
        self.items.merge(oi.from_report(UMBRELLA / "launch-checklist.md"))
        result = self.items.merge(self.findings())
        self.assertEqual(sorted(result["created"]), self.TESTS)
        self.assertIn({"key": "LC-2.7", "shared_by": self.TESTS, "in": "import", "where": "findings-umbrella.json"},
                      result["ambiguous"])
        states = {i: self.items.get(i)["status"] for i in self.TESTS}
        self.assertEqual(states, {"TP-06": "open", "TP-07": "done", "AB-01": "open", "AB-09": "deferred",
                                  "AB-10": "open", "AB-11": "done"})
        for ident in self.TESTS:
            self.assertEqual(self.items.get(ident)["source_ids"], ["LC-2.7"], f"{ident} trägt keine fremden Punkte")
        self.assertEqual(self.items.get("LC-2.7")["source_ids"], [], "die Sammelzeile bleibt ein eigener Punkt")

    def test_erledigen_eines_testpunkts_trifft_die_anderen_nicht(self):
        self.items.merge(self.findings())
        self.items.set_done("TP-06", "Abruf Entwurf 2026-10-08: Sterne an den Kacheln")
        self.items.defer("AB-10", "Beispiel Person", "2026-10-30")
        result = self.items.merge(self.findings())
        self.assertEqual(result["created"], [])
        self.assertEqual(result["known"], 6)
        self.assertEqual({d["id"] for d in result["drift"]}, {"TP-06", "AB-10"})
        self.assertEqual(self.items.get("AB-01")["status"], "open")
        self.assertEqual(self.items.get("TP-07")["status"], "done")

    def test_sammelzeile_nach_den_findings_wird_eigener_punkt(self):
        self.items.merge(self.findings())
        result = self.items.merge(oi.from_report(UMBRELLA / "launch-checklist.md"))
        self.assertIn("LC-2.7", result["created"], "LC-2.7 kennen sechs Punkte, keiner ist LC-2.7")
        self.assertEqual([a["in"] for a in result["ambiguous"]], ["list"])
        self.assertEqual(result["ambiguous"][0]["shared_by"], ["TP-06", "TP-07", "AB-01", "AB-09", "AB-10", "AB-11"])
        again = self.items.merge(oi.from_report(UMBRELLA / "launch-checklist.md"))
        self.assertEqual(again["created"], [], "LC-2.7 als id gewinnt")
        self.assertEqual(again["ambiguous"], [])

    def test_bericht_mit_sammelkennung_vorn_in_jeder_zeile(self):
        result = self.items.merge(oi.from_report(UMBRELLA / "test-round-report.md"))
        self.assertEqual(len(result["created"]), 6)
        self.assertTrue(all(i.startswith("R-") for i in result["created"]), result["created"])
        self.assertEqual(result["ambiguous"][0]["key"], "LC-2.7")
        self.assertEqual(len(result["ambiguous"][0]["shared_by"]), 6)
        by_title = {i["title"].split(" ")[0]: i for i in self.items.items}
        self.assertEqual({k: v["status"] for k, v in by_title.items()},
                         {"TP-06": "open", "TP-07": "done", "AB-01": "open", "AB-09": "deferred",
                          "AB-10": "open", "AB-11": "done"})
        self.assertTrue(all("LC-2.7" in i["source_ids"] for i in self.items.items))
        self.items.set_done(by_title["TP-06"]["id"], "Abruf Entwurf 2026-10-08")
        again = self.items.merge(oi.from_report(UMBRELLA / "test-round-report.md"))
        self.assertEqual((again["created"], again["known"]), ([], 6))
        self.assertEqual([d["id"] for d in again["drift"]], [by_title["TP-06"]["id"]])
        self.assertEqual(by_title["AB-01"]["status"], "open")

    def test_quellen_melden_keinen_testpunkt_als_vorhanden_nur_wegen_der_sammelkennung(self):
        self.items.merge(oi.from_report(UMBRELLA / "launch-checklist.md"))
        missing = self.items.unimported(self.findings())
        self.assertEqual(sorted(c["preferred_id"] for c in missing), ["AB-01", "AB-09", "AB-10", "TP-06"])

    def test_dieselbe_kennung_in_zwei_quellen_bleibt_ein_punkt(self):
        self.items.merge(oi.from_report(FIXTURES / "verify-findings.md"))
        count = len(self.items.items)
        path = self.write("liste.json", json.dumps({"findings": [
            {"id": "S-03", "title": "hreflang fehlt", "severity": "before_launch", "status": "fixed",
             "evidence": "Abruf Entwurf 2026-10-08"},
            {"id": "S-09", "source_ids": ["B-02"], "title": "Seiten ohne Inhalt", "severity": "blocker"}]}))
        result = self.items.merge(oi.from_findings(path))
        self.assertEqual((result["created"], len(self.items.items)), ([], count))
        self.assertEqual(result["ambiguous"], [])
        self.assertIn("S-09", self.items.get("B-02")["source_ids"])
        self.assertIn({"id": "S-03", "list": "open", "source": "done", "where": "liste.json"},
                      result["drift"])

    def test_derselbe_befund_zweimal_in_einer_quelle_ist_eine_dublette(self):
        finding = {"id": "S-03", "source_ids": ["P03"], "title": "hreflang fehlt", "severity": "before_launch"}
        path = self.write("liste.json", json.dumps({"findings": [finding, finding]}))
        result = self.items.merge(oi.from_findings(path))
        self.assertEqual((result["created"], result["ambiguous"]), (["S-03"], []))
        self.assertEqual(self.items.get("S-03")["source_ids"], ["P03"])

    def test_cli_import_meldet_die_sammelkennung(self):
        code, out = self.cli("import", "--kind", "findings", "--path", str(UMBRELLA / "findings-umbrella.json"))
        self.assertEqual((code, len(out["created"])), (0, 6))
        self.assertEqual([a["key"] for a in out["ambiguous"]], ["LC-2.7"])


class TestSources(Workspace):
    def test_was_in_einem_bericht_offen_steht_und_fehlt_ist_ein_befund(self):
        drive = self.ws / "drive" / "projects" / "beispiel"
        drive.mkdir(parents=True)
        (drive / "verify-findings.md").write_text((FIXTURES / "verify-findings.md").read_text(encoding="utf-8"))
        self.write("migration/inventory/checklist.md", (FIXTURES / "checklist.md").read_text(encoding="utf-8"))
        config = {"drive_path": str(self.ws / "drive"),
                  "theme_migration": {"report_paths": ["{drive_path}/projects/beispiel", "fehlt/"],
                                      "acceptance_checklist": "migration/inventory/checklist.md"}}
        result = oi.source_gaps(self.items, self.ws, config, migration=True)
        missing = {(m["source"], m["id"]) for m in result["missing"]}
        self.assertIn(("verify-findings.md", "S-03"), missing)
        self.assertIn(("checklist.md", "P02"), missing)
        self.assertNotIn(("checklist.md", "P01"), missing, "Erledigtes fehlt nie")
        self.assertEqual(result["gaps"], ["Bericht nicht gefunden: fehlt/"])
        for kind, path in oi.configured_sources(self.ws, config)[0]:
            self.items.merge(oi.read_source(kind, path))
        self.assertEqual(oi.source_gaps(self.items, self.ws, config)["missing"], [])

    def test_im_migrationslauf_ist_eine_fehlende_pruefliste_eine_luecke(self):
        result = oi.source_gaps(self.items, self.ws, {}, migration=True)
        self.assertEqual(result["gaps"], ["theme_migration.acceptance_checklist nicht gesetzt"])
        self.assertEqual(oi.source_gaps(self.items, self.ws, {})["gaps"], [])

    def test_bestandene_pruefung_schliesst_mit_beleg(self):
        self.items.merge(oi.from_checklist(FIXTURES / "checklist.md"))
        report = {"checked_at": "2026-10-08T10:00:00Z", "checks": [
            {"id": "seo-hreflang", "status": "ok"}, {"id": "seo-open-graph", "status": "missing"},
            {"id": "seo-structured-data", "status": "ok"}, {"id": "seo-pages", "status": "ok"}]}
        closed = oi.close_covered(self.items, report, "2026-10-08-launch-check")
        self.assertEqual([c["id"] for c in closed], ["P03", "P05", "P06"])
        self.assertIn("launch-check 2026-10-08: seo-hreflang bestanden", self.items.get("P03")["evidence"])
        self.assertEqual(self.items.get("P04")["status"], "open", "og:type nicht bestanden")


class TestCli(Workspace):
    def test_import_gate_erledigen_gate(self):
        path = self.write("migration/inventory/checklist.md", (FIXTURES / "checklist.md").read_text(encoding="utf-8"))
        code, out = self.cli("import", "--kind", "checklist", "--path", str(path))
        self.assertEqual((code, len(out["created"])), (0, 7))
        code, out = self.cli("gate", "--gate", "G4-acceptance")
        self.assertEqual((code, out["open"]), (1, 5))
        for ident in ("P02", "P03", "P04", "P05", "P06"):
            self.assertEqual(self.cli("done", "--id", ident, "--evidence", "im Entwurf geprüft")[0], 0)
        code, out = self.cli("gate", "--gate", "G4-acceptance")
        self.assertEqual((code, out["open"]), (0, 0))
        self.assertTrue(oi.view_path(self.ws).is_file())

    def test_fehler_sind_exit_2_und_aendern_nichts(self):
        self.cli("add", "--title", "Menü", "--id", "B-01", "--severity", "blocker")
        before = oi.list_path(self.ws).read_text(encoding="utf-8")
        self.assertEqual(self.cli("done", "--id", "B-01")[0], 2, "ohne Beleg")
        self.assertEqual(self.cli("defer", "--id", "B-01", "--by", "Beispiel Person")[0], 2, "ohne Datum")
        self.assertEqual(self.cli("add", "--title", "x", "--id", "B-01")[0], 2, "id doppelt")
        self.assertEqual(self.cli("import", "--kind", "pdf", "--path", "x")[0], 2)
        self.assertEqual(oi.list_path(self.ws).read_text(encoding="utf-8"), before)

    def test_list_filtert_nach_status_und_gate(self):
        self.cli("add", "--title", "a", "--severity", "blocker")
        self.cli("add", "--title", "b", "--severity", "after_launch")
        code, out = self.cli("list", "--status", "open", "--gate", "G5-go-live")
        self.assertEqual((code, out["count"]), (0, 1))


class TestRunState(Workspace):
    def setUp(self):
        super().setUp()
        # G4 und G5 entscheidet seit 0.3.11 nur der Betreiber.
        patcher = mock.patch.dict(os.environ, {"PTAI_OPERATOR": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = run_state.new(self.ws, "2026-01-01-migration")
        for gate in ("G1-decisions", "G2-mapping", "G3-first-upload"):
            self.state.decide_gate(gate, "Beispielperson")

    def test_init_legt_die_liste_an_und_laesst_eine_vorhandene_stehen(self):
        self.items.add(title="schon da", ident="X-01")
        self.items.save()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_state.main(["init", "--workspace", str(self.ws), "--run-id", "2026-02-01-migration"]), 0)
        self.assertEqual([i["id"] for i in oi.load(self.ws).items], ["X-01"])
        other = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        with contextlib.redirect_stdout(io.StringIO()):
            run_state.main(["init", "--workspace", str(other)])
        self.assertTrue(oi.exists(other))

    def test_g4_haelt_an_solange_ein_punkt_offen_ist(self):
        self.write("checklist.md", "- [x] **P01** erledigt\n")
        self.config({"acceptance_checklist": "checklist.md"})
        self.items.add(title="Sterne fehlen", ident="TP-02", gate="G4-acceptance")
        self.items.save()
        with self.assertRaises(run_state.StateError) as ctx:
            self.state.decide_gate("G4-acceptance", "Beispielperson")
        self.assertIn("TP-02", str(ctx.exception))
        self.assertIsNone(self.state.data["gates"]["G4-acceptance"])
        self.items.set_done("TP-02", "behoben, im Termin bestätigt")
        self.items.save()
        self.state.decide_gate("G4-acceptance", "Beispielperson")
        self.assertTrue(self.state.data["gates"]["G4-acceptance"])

    def test_g5_haelt_an_ohne_liste_und_bei_offenem_in_einer_quelle(self):
        oi.list_path(self.ws).unlink()
        with self.assertRaises(run_state.StateError):
            self.state.decide_gate("G5-go-live", "Beispielperson")
        oi.init(self.ws)
        self.write("migration/inventory/checklist.md", (FIXTURES / "checklist.md").read_text(encoding="utf-8"))
        self.config({"acceptance_checklist": "migration/inventory/checklist.md"})
        with self.assertRaises(run_state.StateError) as ctx:
            self.state.decide_gate("G5-go-live", "Beispielperson")
        self.assertIn("nicht in der Liste", str(ctx.exception))

    def test_phase_2_erst_mit_uebernommener_pruefliste(self):
        self.state.set_phase("0-setup", "done")
        with self.assertRaises(run_state.StateError) as ctx:
            self.state.set_phase("2-inventory", "done")
        self.assertIn("acceptance_checklist", str(ctx.exception))
        path = self.write("migration/inventory/checklist.md", (FIXTURES / "checklist.md").read_text(encoding="utf-8"))
        self.config({"acceptance_checklist": "migration/inventory/checklist.md"})
        with self.assertRaises(run_state.StateError):
            self.state.set_phase("2-inventory", "done")
        self.items.merge(oi.from_checklist(path))
        self.items.save()
        self.state.set_phase("2-inventory", "done")
        self.assertEqual(self.state.data["phases"]["2-inventory"], "done")

    def test_phase_6_nicht_mit_offenem_blocker(self):
        self.items.add(title="Menü fehlt", ident="B-01", severity="blocker")
        self.items.save()
        with self.assertRaises(run_state.StateError):
            self.state.set_phase("6-verify", "done")
        self.items.set_done("B-01", "Abruf Entwurf: Menü da")
        self.items.save()
        self.state.set_phase("6-verify", "done")

    def test_nachsorge_nicht_mit_offenem_punkt_fuer_danach(self):
        self.items.add(title="Sitemap neu einreichen", severity="after_launch")
        self.items.save()
        with self.assertRaises(run_state.StateError):
            run_state.check_open_items(self.ws, phase="10-aftercare")

    def test_stand_nennt_die_offenen_punkte(self):
        self.items.add(title="a", severity="blocker")
        self.items.save()
        self.assertEqual(self.state.summary()["open_items"]["open_by_gate"]["G4-acceptance"], 1)


if __name__ == "__main__":
    unittest.main()
