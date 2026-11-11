"""Der vollständige Bildvergleich vor Gate G4: Referenz, Abdeckung, jüngste Aufnahme je Seite und Breite."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import visual_compare_support as vcs
from theme import open_items, run_state, visual_compare as vc


class TestAufnahme(unittest.TestCase):
    def test_gueltige_aufnahme_zaehlt(self):
        self.assertIsNone(vc.shot_problem(vcs.shot("2", "mobile"), "mobile", "2"))

    def test_gruende_warum_eine_aufnahme_nicht_zaehlt(self):
        cases = {
            "keine Aufnahme": None,
            "error: Zeitlimit": vcs.shot("2", "desktop", state="error", error="Zeitlimit"),
            "incomplete": vcs.shot("2", "desktop", state="incomplete"),
            "Seite zeigt Theme 3": vcs.shot("2", "desktop", theme_check={"found": "3", "ok": True}),
            "Theme-Nachweis fehlt": vcs.shot("2", "desktop", theme_check={"found": None}),
            "kein Ganzseiten-Bild": vcs.shot("2", "desktop", file=None),
            "Breite 1280 statt 1440": vcs.shot("2", "desktop", viewport={"width": 1280, "height": 800}),
        }
        for expected, shot in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, vc.shot_problem(shot, "desktop", "2"))

    def test_handy_braucht_390_und_rechner_1440(self):
        self.assertIn("Breite 1440 statt 390", vc.shot_problem(vcs.shot("2", "desktop"), "mobile", "2"))

    def test_theme_id_als_zahl_und_als_text_ist_dieselbe(self):
        self.assertTrue(vc.same_id(2, "000000000002"))
        self.assertFalse(vc.same_id(None, ""))


class TestReferenz(unittest.TestCase):
    def shots(self, role):
        return [vcs.shot("1", d, role) for d in vc.DEVICES]

    def test_rolle_main_belegt_das_veroeffentlichte_theme(self):
        status = vc.reference_status("1", self.shots("main"), "1")
        self.assertTrue(status["ok"] and status["published"])

    def test_ein_aelteres_theme_links_ist_keine_referenz(self):
        # Am 11.11.2026 lag zeitweise ein älteres Theme statt des veröffentlichten als Vorlage auf dem Tisch.
        status = vc.reference_status("7", self.shots("unpublished"), "7")
        self.assertFalse(status["ok"])
        self.assertIn("nicht das veröffentlichte Theme", status["problems"][0])

    def test_ohne_rolle_entscheidet_die_config(self):
        self.assertTrue(vc.reference_status("1", self.shots(None), "1")["ok"])
        self.assertFalse(vc.reference_status("1", self.shots(None), "9")["ok"])
        self.assertFalse(vc.reference_status("1", self.shots(None), None)["ok"])

    def test_veraltete_config_bei_belegter_rolle_ist_ein_hinweis(self):
        status = vc.reference_status("5", self.shots("main"), "1")
        self.assertTrue(status["ok"])
        self.assertIn("veraltet", status["warnings"][0])


class TestEintrag(unittest.TestCase):
    def test_abdeckung_nennt_jede_fehlende_aufnahme(self):
        data = vcs.record(["home"], devices=("desktop",))
        summary = vc.record_summary(["home", "product"], data["pairs"], data["themes"], vcs.LIVE)
        cover = summary["coverage"]
        self.assertEqual((cover["expected"], cover["valid"], cover["complete"]), (8, 2, False))
        self.assertIn({"page_id": "home", "device": "mobile", "side": "a", "reason": "keine Aufnahme"},
                      cover["missing"])
        self.assertTrue(summary["reference"]["ok"])

    def test_zweiter_lauf_am_selben_tag_ergaenzt_je_seite_und_breite(self):
        old = vcs.record(["home", "product"], captured_at="2026-11-11T08:00:00+00:00")
        new = vcs.record(["home"], devices=("mobile",), captured_at="2026-11-11T10:00:00+00:00")
        merged = vc.merge_record(old, new)
        self.assertEqual(len(merged["pairs"]), 4)
        home_mobile = [p for p in merged["pairs"] if (p["page_id"], p["device"]) == ("home", "mobile")]
        self.assertEqual(home_mobile[0]["captured_at"], "2026-11-11T10:00:00+00:00")

    def test_anderes_theme_am_selben_tag_ersetzt_den_eintrag(self):
        old = vcs.record(["home"])
        new = vcs.record(["home"], draft="000000000009")
        self.assertIs(vc.merge_record(old, new), new)


class GateWorkspace(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        vcs.write_pages(self.ws)
        self.config = {"theme_migration": {"live_theme_id": vcs.LIVE, "draft_theme_id": vcs.DRAFT}}

    def evaluate(self, values=None):
        return vc.evaluate(self.ws, self.config, values)


class TestGate(GateWorkspace):
    def test_ohne_vergleich_haelt_g4_an(self):
        result = self.evaluate()
        self.assertFalse(result["ok"])
        self.assertIn("kein Bildvergleich", result["problems"][0])
        self.assertIn("shoot_pair.py --a 000000000004 --b 000000000002",
                      vc.gate_problems(self.ws, self.config)[0])

    def test_ohne_beispielseiten_haelt_g4_an(self):
        (self.ws / vc.PAGES_PATH).unlink()
        self.assertIn("pages.json fehlt", self.evaluate()["problems"][0])

    def test_vollstaendiger_vergleich_laesst_g4_durch(self):
        vcs.write_record(self.ws, vcs.record())
        result = self.evaluate()
        self.assertTrue(result["ok"], result["problems"])
        self.assertEqual(vc.gate_problems(self.ws, self.config), [])

    def test_fehlt_das_handy_fuer_eine_seite_haelt_g4_an(self):
        data = vcs.record()
        data["pairs"] = [p for p in data["pairs"] if (p["page_id"], p["device"]) != ("product", "mobile")]
        vcs.write_record(self.ws, data)
        result = self.evaluate()
        self.assertFalse(result["ok"])
        self.assertIn("2 von 8 Aufnahmen", result["problems"][0])
        self.assertIn("product Handy A", result["problems"][0])

    def test_falsches_theme_rechts_zaehlt_nicht(self):
        data = vcs.record()
        data["pairs"][0]["b"] = vcs.shot(vcs.DRAFT, "desktop", state="wrong_theme",
                                         theme_check={"found": vcs.LIVE, "reason": "Seite zeigt Theme 1"})
        vcs.write_record(self.ws, data)
        self.assertIn("home Rechner B (wrong_theme", self.evaluate()["problems"][0])

    def test_referenz_nicht_veroeffentlicht_zaehlt_nicht(self):
        vcs.write_record(self.ws, vcs.record(live="000000000007", live_role="unpublished"))
        result = self.evaluate()
        self.assertFalse(result["ok"])
        self.assertIn("Rolle unpublished", result["problems"][0])

    def test_vergleich_mit_altem_entwurf_zaehlt_nicht(self):
        vcs.write_record(self.ws, vcs.record(draft="000000000009"))
        self.assertIn("Entwurf ist 000000000002", self.evaluate()["problems"][0])

    def test_entwurf_aus_dem_lauf_wenn_die_config_ihn_nicht_hat(self):
        self.config = {"theme_migration": {}}
        vcs.write_record(self.ws, vcs.record())
        self.assertFalse(self.evaluate()["ok"])
        self.assertTrue(self.evaluate({"draft_theme_id": vcs.DRAFT})["ok"])

    def test_ohne_angabe_gelten_die_werte_des_juengsten_laufs(self):
        self.config = {"theme_migration": {}}
        vcs.write_record(self.ws, vcs.record())
        state = self.ws / "reporting" / "runs" / "2026-11-01-migration" / "state.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"kind": "migration", "values": {"draft_theme_id": vcs.DRAFT}}), encoding="utf-8")
        self.assertTrue(vc.evaluate(self.ws, self.config)["ok"])

    def test_nachgeholte_seite_ergaenzt_einen_frueheren_vergleich(self):
        old = vcs.record(captured_at="2026-11-10T09:00:00+00:00")
        old["pairs"][0]["a"] = vcs.shot(vcs.LIVE, "desktop", "main", state="error", error="Zeitlimit")
        vcs.write_record(self.ws, old, day="2026-11-10")
        self.assertFalse(self.evaluate()["ok"])
        vcs.write_record(self.ws, vcs.record(["home"], devices=("desktop",)), day="2026-11-11")
        self.assertTrue(self.evaluate()["ok"])

    def test_die_juengste_aufnahme_zaehlt_auch_wenn_sie_scheitert(self):
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-10T09:00:00+00:00"), day="2026-11-10")
        newer = vcs.record(["home"], devices=("desktop",))
        newer["pairs"][0]["b"] = vcs.shot(vcs.DRAFT, "desktop", state="error", error="Zeitlimit")
        vcs.write_record(self.ws, newer, day="2026-11-11")
        self.assertIn("home Rechner B (error", self.evaluate()["problems"][0])

    def test_nach_einem_neuen_live_theme_zaehlen_alte_vergleiche_nicht(self):
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-10T09:00:00+00:00"), day="2026-11-10")
        vcs.write_record(self.ws, vcs.record(["home"], live="000000000005"), day="2026-11-11")
        result = self.evaluate()
        self.assertFalse(result["ok"])
        self.assertIn("product", result["problems"][0])

    def test_unlesbarer_eintrag_haelt_an(self):
        vcs.write_record(self.ws, vcs.record())
        broken = vc.record_path(self.ws, "2026-11-12")
        broken.parent.mkdir(parents=True)
        broken.write_text("{kaputt", encoding="utf-8")
        self.assertIn("nicht lesbar", " ".join(self.evaluate()["problems"]))

    def test_cli_exit_1_unvollstaendig_0_vollstaendig(self):
        (self.ws / "reporting").mkdir()
        (self.ws / "reporting" / "config.json").write_text(json.dumps(self.config), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vc.main(["check", "--workspace", str(self.ws)]), 1)
            vcs.write_record(self.ws, vcs.record())
            self.assertEqual(vc.main(["check", "--workspace", str(self.ws)]), 0)


class TestRunStateG4(GateWorkspace):
    """`run_state gate --gate G4-acceptance` hält an, es fragt nicht."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("PTAI_OPERATOR", None)
        (self.ws / "reporting").mkdir()
        (self.ws / "checklist.md").write_text("- [x] **P01** erledigt\n", encoding="utf-8")
        self.config["theme_migration"]["acceptance_checklist"] = "checklist.md"
        (self.ws / "reporting" / "config.json").write_text(json.dumps(self.config), encoding="utf-8")
        self.items, _ = open_items.init(self.ws)
        self.state = run_state.new(self.ws, "2026-01-01-migration")

    def test_g4_verweigert_ohne_vollstaendigen_bildvergleich(self):
        with self.assertRaises(run_state.StateError) as ctx:
            self.state.decide_gate("G4-acceptance", "Beispielperson")
        self.assertIn("Bildvergleich unvollständig", str(ctx.exception))
        self.assertIsNone(self.state.data["gates"]["G4-acceptance"])

    def test_g4_erlaubt_mit_vollstaendigem_bildvergleich(self):
        vcs.write_record(self.ws, vcs.record())
        vcs.complete_datalayer(self.ws)
        self.state.decide_gate("G4-acceptance", "Beispielperson")
        self.assertEqual(self.state.data["gates"]["G4-acceptance"]["decided_by"], "Beispielperson")

    def test_g4_verweigert_bei_testpunkt_ohne_bilder(self):
        vcs.write_record(self.ws, vcs.record())
        # Ein Testpunkt, der vor dem 11.11.2026 oder von Hand ohne Bilder erledigt wurde.
        self.items.items.append({"id": "TP-03", "title": "Menü", "severity": "before_launch", "gate": "G4-acceptance",
                                 "status": "done", "evidence": "behoben",
                                 "source": "Abnahme 2026-11-01-test (test.json)",
                                 "source_ids": ["2026-11-01-test:TP-03"], "links": []})
        self.items.save()
        with self.assertRaises(run_state.StateError) as ctx:
            self.state.decide_gate("G4-acceptance", "Beispielperson")
        self.assertIn("Testpunkte erledigt ohne Bilder vom Entwurf: TP-03", str(ctx.exception))

    def test_g5_verlangt_keinen_bildvergleich(self):
        self.state.decide_gate("G5-go-live", "Beispielperson")
        self.assertTrue(self.state.data["gates"]["G5-go-live"])


if __name__ == "__main__":
    unittest.main()
