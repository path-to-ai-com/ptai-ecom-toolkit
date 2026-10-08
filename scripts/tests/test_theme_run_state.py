"""Tests für den Stand einer Theme-Migration."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from theme import run_state


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

    def test_die_entscheidung_haelt_person_und_zeitpunkt_fest(self):
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

