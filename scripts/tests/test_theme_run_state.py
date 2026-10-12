"""Tests für den Stand einer Theme-Migration."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from theme import open_items, run_state


class RunStateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)

    def test_eine_phase_hinter_einem_offenen_gate_darf_nicht_beginnen(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        with self.assertRaises(run_state.StateError):
            state.set_phase("3-mapping", "running")

    def test_nach_entschiedenem_gate_darf_die_phase_beginnen(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        state.decide_gate("G1-decisions", "Beispielperson")
        state.set_phase("3-mapping", "running")
        self.assertEqual(state.data["phases"]["3-mapping"], "running")

    def test_ein_gate_ohne_namen_ist_keine_entscheidung(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        with self.assertRaises(run_state.StateError):
            state.decide_gate("G1-decisions", "  ")

    @mock.patch.dict(os.environ, {"PTAI_OPERATOR": "1"})
    def test_die_entscheidung_haelt_person_und_zeitpunkt_fest(self):
        # G5 liest die Liste offener Punkte und die Prüfliste; beide ohne offenen Punkt halten nicht an.
        (self.ws / "reporting").mkdir()
        (self.ws / "checklist.md").write_text("- [x] **P01** erledigt\n", encoding="utf-8")
        config = {"theme_migration": {"acceptance_checklist": "checklist.md"}}
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config), encoding="utf-8")
        open_items.init(self.ws)
        state = run_state.new(self.ws, "2026-01-01-migration")
        now = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
        state.decide_gate("G5-go-live", "Beispielperson", "Launch freigegeben", now=now)
        entry = state.data["gates"]["G5-go-live"]
        self.assertEqual(entry["decided_by"], "Beispielperson")
        self.assertEqual(entry["decided_at"], "2026-01-02T09:00:00+00:00")

    def test_launch_ist_ohne_abnahme_gesperrt(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        for gate in ("G1-decisions", "G2-mapping", "G3-first-upload"):
            state.decide_gate(gate, "Beispielperson")
        self.assertEqual(state.open_gate_before("9-launch"), "G4-acceptance")

    def test_speichern_und_laden_ergibt_denselben_stand(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        state.set_value("live_theme_id", "000000000000")
        state.save()
        loaded = run_state.load(self.ws, "2026-01-01-migration")
        self.assertEqual(loaded.data, state.data)

    def test_ein_beschaedigter_stand_wird_nicht_still_neu_angelegt(self):
        path = run_state.state_path(self.ws, "2026-01-01-migration")
        path.parent.mkdir(parents=True)
        path.write_text("{kaputt", encoding="utf-8")
        with self.assertRaises(run_state.StateError):
            run_state.load(self.ws, "2026-01-01-migration")

    def test_unbekannte_schluessel_werden_abgelehnt(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        with self.assertRaises(run_state.StateError):
            state.set_value("irgendwas", "1")

    def test_naechste_phase_ueberspringt_fertige_und_uebersprungene(self):
        state = run_state.new(self.ws, "2026-01-01-migration")
        state.set_phase("0-setup", "done")
        state.set_phase("1-snapshot", "skipped")
        self.assertEqual(state.next_phase(), "2-inventory")

    def test_cli_findet_den_neuesten_lauf(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for run_id in ("2026-01-01-migration", "2026-02-01-migration"):
                self.assertEqual(run_state.main(["init", "--workspace", str(self.ws),
                                                 "--run-id", run_id]), 0)
        self.assertEqual(run_state.latest_run_id(self.ws), "2026-02-01-migration")
        data = json.loads(run_state.state_path(self.ws, "2026-02-01-migration").read_text())
        self.assertEqual(data["kind"], "migration")



class VersionTest(unittest.TestCase):
    """Zu Beginn jeder Sitzung: stammt der Lauf aus einem neueren Plugin als dem installierten?"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)

    def run_version(self, version) -> tuple[int, dict]:
        state = run_state.new(self.ws, "2026-01-01-migration")
        state.save()
        state.data["plugin_version"] = version
        run_state.state_path(self.ws, state.run_id).write_text(json.dumps(state.data), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(run_state, "plugin_version", return_value="0.3.9"):
            code = run_state.main(["version", "--workspace", str(self.ws)])
        return code, json.loads(out.getvalue())

    def test_neuerer_lauf_haelt_an(self):
        # 0.3.13 ist neuer als 0.3.9, auch wenn der Text kleiner sortiert.
        code, result = self.run_version("0.3.13")
        self.assertEqual(code, 1)
        self.assertTrue(result["plugin_outdated"])
        self.assertIn("aktualisieren", result["hint"])

    def test_gleicher_oder_aelterer_lauf_geht_weiter(self):
        for version in ("0.3.9", "0.3.8", "unbekannt", None):
            with self.subTest(version=version):
                code, result = self.run_version(version)
                self.assertEqual(code, 0)
                self.assertFalse(result["plugin_outdated"])

    def test_version_schreibt_nichts(self):
        self.run_version("0.3.13")
        run_dir = self.ws / "reporting" / "runs" / "2026-01-01-migration"
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()), ["state.json"])

    def test_ohne_lauf_gibt_es_nichts_zu_vergleichen(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_state.main(["version", "--workspace", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out.getvalue())["run_id"])

if __name__ == "__main__":
    unittest.main()


class JournalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = str(Path(tmp.name))

    def run_cli(self, *args) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return run_state.main([*args, "--workspace", self.ws])

    def journal(self) -> list[dict]:
        path = run_state.journal_path(Path(self.ws), "2026-01-01-migration")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_phase_gate_und_set_schreiben_ihr_ereignis_selbst(self):
        self.run_cli("init", "--run-id", "2026-01-01-migration")
        self.run_cli("phase", "--phase", "0-setup", "--status", "running")
        self.run_cli("gate", "--gate", "G1-decisions", "--decided-by", "Beispielperson", "--note", "alles so")
        self.run_cli("set", "--key", "live_theme_id", "--value", "000000000000")
        kinds = [entry["kind"] for entry in self.journal()]
        self.assertEqual(kinds, ["phase", "phase", "gate", "set"])
        self.assertEqual(self.journal()[2]["decided_by"], "Beispielperson")

    def test_log_haengt_an_und_nimmt_die_laufende_phase(self):
        self.run_cli("init", "--run-id", "2026-01-01-migration")
        self.run_cli("phase", "--phase", "0-setup", "--status", "running")
        self.assertEqual(self.run_cli("log", "--kind", "question", "--text", "Wie lautet die Shop-Adresse?"), 0)
        entry = self.journal()[-1]
        self.assertEqual((entry["kind"], entry["phase"]), ("question", "0-setup"))

    def test_log_ohne_text_oder_mit_fremder_art_ist_ein_fehler(self):
        self.run_cli("init", "--run-id", "2026-01-01-migration")
        self.assertEqual(self.run_cli("log", "--kind", "question"), 2)
        self.assertEqual(self.run_cli("log", "--kind", "phase", "--text", "x"), 2)

