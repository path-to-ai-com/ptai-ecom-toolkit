"""Tests für die neun Schritte, die Fragen an das Team, die Vorgaben der Marke und den Lauf seit 0.3.11."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from theme import open_items, policies, questions, run_state, steps

RUN = "2026-01-01-migration"
CLEAN_GIT = {"met": True, "note": "alles gepusht"}


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class Workspace(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        write(self.ws / "reporting" / "config.json",
              {"theme_migration": {"people": ["Beispielperson"]}})
        open_items.init(self.ws)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PTAI_OPERATOR", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

    def state_until_verify(self) -> run_state.MigrationState:
        """Ein Lauf mit erledigten Phasen 0 bis 6 und entschiedenen Gates G1 bis G3."""
        state = run_state.new(self.ws, RUN)
        for gate in ("G1-decisions", "G2-mapping", "G3-first-upload"):
            state.decide_gate(gate, "Beispielperson")
        for phase in ("0-setup", "1-snapshot", "2-inventory", "3-mapping", "4-build", "5-upload", "6-verify"):
            state.data["phases"][phase] = "done"
        state.data["values"]["draft_theme_id"] = "000000000000"
        return state

    def all_checkers(self, names=steps.CHECKERS) -> None:
        for name in names:
            write(self.ws / "migration" / "verify" / "2026-01-02" / name / "findings.json", [])

    def one_language(self) -> None:
        write(self.ws / "migration" / "inventory" / "translations.json",
              {"locales": [{"locale": "de", "primary": True, "published": True}]})


class StepsTest(Workspace):
    def test_ein_neuer_lauf_steht_bei_schritt_eins(self):
        result = steps.compute(self.ws, run_state.new(self.ws, RUN).data, git_status=CLEAN_GIT)
        self.assertEqual(result["current_step"], 1)
        self.assertEqual([s["status"] for s in result["steps"]], ["open"] * 9)

    def test_drei_von_neun_pruefern_heisst_nacharbeiten(self):
        state = self.state_until_verify()
        self.all_checkers(("structure", "content", "seo"))
        self.one_language()
        result = steps.compute(self.ws, state.data, git_status=CLEAN_GIT)
        verify = result["steps"][4]
        self.assertEqual(verify["status"], "rework")
        self.assertIn("3 von 9", verify["note"])
        self.assertFalse(result["ready_for_test_round"]["met"])

    def test_aeltere_ordnernamen_der_pruefer_werden_gezaehlt(self):
        for name in ("struktur", "inhalt", "seo-recheck", "gestaltung-funktion"):
            write(self.ws / "migration" / "verify" / "2026-01-02" / name / "findings.md", "x")
        self.assertEqual(steps.checkers_run(self.ws), ["structure", "content", "seo", "design", "function"])

    def test_alles_erledigt_ergibt_bereit_fuer_die_testrunde(self):
        state = self.state_until_verify()
        self.all_checkers()
        self.one_language()
        result = steps.compute(self.ws, state.data, git_status=CLEAN_GIT)
        self.assertTrue(result["ready_for_test_round"]["met"], result["ready_for_test_round"])
        self.assertEqual(result["current_step"], 6)
        self.assertEqual(result["owner"], "team")

    def test_offener_blocker_haelt_den_meilenstein(self):
        state = self.state_until_verify()
        self.all_checkers()
        self.one_language()
        items = open_items.load(self.ws)
        items.add(title="Menü fehlt", severity="blocker")
        items.save()
        result = steps.compute(self.ws, state.data, git_status=CLEAN_GIT)
        self.assertFalse(result["ready_for_test_round"]["met"])
        self.assertEqual(result["steps"][4]["status"], "rework")

    def test_nebensprache_ohne_registrierung_haelt_den_meilenstein(self):
        state = self.state_until_verify()
        self.all_checkers()
        write(self.ws / "migration" / "inventory" / "translations.json",
              {"locales": [{"locale": "de", "primary": True, "published": True},
                           {"locale": "en", "primary": False, "published": True}]})
        result = steps.compute(self.ws, state.data, git_status=CLEAN_GIT)
        condition = next(c for c in result["ready_for_test_round"]["conditions"]
                         if c["key"] == "translations_registered")
        self.assertFalse(condition["met"])
        self.assertIn("en", condition["note"])

    def test_marke_ohne_eingetragene_vorgaben_heisst_neubau_nacharbeiten(self):
        write(self.ws / "reporting" / "config.json",
              {"portal": {"brand": "beispielmarke"}, "theme_migration": {"people": ["Beispielperson"]}})
        state = self.state_until_verify()
        result = steps.compute(self.ws, state.data, git_status=CLEAN_GIT)
        self.assertEqual(result["steps"][2]["status"], "rework")
        self.assertEqual(result["steps"][2]["note"], "Vorgaben der Marke nicht eingetragen")
        self.assertEqual(result["owner"], "operator")

    def test_vorgaben_ohne_belegten_neubau_danach_heisst_nacharbeiten(self):
        state = self.state_until_verify()
        write(self.ws / "migration" / "policies.json", {"version": "2026-01-05.1", "rules": [],
                                                         "applied_at": "2026-01-05T10:00:00+00:00"})
        result = steps.compute(self.ws, state.data, git_status=CLEAN_GIT)
        self.assertEqual(result["steps"][2]["status"], "rework")
        self.assertIn("Neubau danach steht aus", result["steps"][2]["note"])

    def test_abgleich_vor_dem_launch_ist_hoechstens_sieben_tage_alt(self):
        state = self.state_until_verify()
        state.data["values"]["last_sync"] = "2026-01-01"
        result = steps.compute(self.ws, state.data, today=date(2026, 1, 20), git_status=CLEAN_GIT)
        sync = next(c for c in result["ready_for_launch"]["conditions"] if c["key"] == "sync_fresh")
        self.assertFalse(sync["met"])


class QuestionsTest(Workspace):
    def test_elfte_offene_frage_wird_verweigert(self):
        for n in range(questions.MAX_OPEN_PER_GATE):
            questions.ask(self.ws, "G1-decisions", f"Frage {n}")
        with self.assertRaises(questions.QuestionError):
            questions.ask(self.ws, "G1-decisions", "eine zu viel")

    def test_sammelname_ist_keine_antwort(self):
        entry = questions.ask(self.ws, "G1-decisions", "Kontaktformular übernehmen?")
        with self.assertRaises(questions.QuestionError):
            questions.answer(self.ws, entry["id"], "Beispiel Team", "ja")

    def test_vorlaeufig_ist_keine_antwort(self):
        entry = questions.ask(self.ws, "G1-decisions", "Kontaktformular übernehmen?")
        with self.assertRaises(questions.QuestionError):
            questions.answer(self.ws, entry["id"], "Beispielperson", "vorläufig wie heute")
        self.assertEqual(len(questions.open_for(self.ws)), 1)

    def test_g1_haelt_an_solange_eine_frage_offen_ist(self):
        questions.ask(self.ws, "G1-decisions", "Kontaktformular übernehmen?")
        state = run_state.new(self.ws, RUN)
        with self.assertRaises(run_state.StateError):
            state.decide_gate("G1-decisions", "Beispielperson")

    def test_beantwortete_frage_gibt_g1_frei(self):
        entry = questions.ask(self.ws, "G1-decisions", "Kontaktformular übernehmen?")
        questions.answer(self.ws, entry["id"], "Beispielperson", "ja, wie heute")
        state = run_state.new(self.ws, RUN)
        state.decide_gate("G1-decisions", "Beispielperson")
        self.assertEqual(state.data["gates"]["G1-decisions"]["decided_by"], "Beispielperson")


class PoliciesTest(Workspace):
    SOURCE = {
        "version": "2026-01-05.1", "decided_by": "Betreiber", "decided_at": "2026-01-05",
        "rules": [
            {"key": "cookie_banner", "subject": "Cookie-Banner", "rule": "same_as_reference", "target": "Banner A",
             "keep": ["app:banner-a"], "drop": ["app:banner-b"]},
            {"key": "translation", "subject": "Übersetzung", "rule": "open", "note": "noch klären"},
            {"key": "languages", "subject": "Sprachen", "rule": "may_differ"},
        ],
    }

    def setUp(self):
        super().setUp()
        write(self.ws / "migration" / "inventory" / "apps.json",
              {"services": [{"service_id": "app:banner-b", "decision": "keep"}]})
        write(self.ws / "migration" / "mapping" / "decisions.json",
              {"decisions": [{"id": "G1-001", "service_id": "app:banner-b", "decision": "keep",
                              "decided_by": "Beispielperson", "source": "G1"}]})

    def test_apply_ersetzt_alte_entscheidung_mit_verweis(self):
        result = policies.apply(self.ws, self.SOURCE)
        decisions = json.loads((self.ws / "migration" / "mapping" / "decisions.json").read_text())["decisions"]
        dropped = next(d for d in decisions if d["service_id"] == "app:banner-b" and d["source"] == "policy")
        self.assertEqual(dropped["decision"], "drop")
        self.assertEqual(dropped["replaces"], ["G1-001"])
        apps = json.loads((self.ws / "migration" / "inventory" / "apps.json").read_text())
        self.assertEqual(apps["services"][0]["decision"], "drop")
        self.assertEqual(result["open_rules"], ["translation"])

    def test_fehlender_dienst_wird_ein_blocker_zum_einbauen(self):
        result = policies.apply(self.ws, self.SOURCE)
        self.assertEqual(len(result["open_items_added"]), 1)
        item = open_items.load(self.ws).get(result["open_items_added"][0])
        self.assertEqual(item["severity"], "blocker")

    def test_dieselbe_version_zweimal_aendert_nichts(self):
        policies.apply(self.ws, self.SOURCE)
        again = policies.apply(self.ws, self.SOURCE)
        self.assertEqual(again["decisions_added"], [])
        self.assertEqual(again["open_items_added"], [])

    def test_check_meldet_veraltete_vorgaben(self):
        policies.apply(self.ws, self.SOURCE)
        newer = {**self.SOURCE, "version": "2026-01-09.1"}
        self.assertFalse(policies.check(self.ws, newer)["current"])
        self.assertTrue(policies.check(self.ws, self.SOURCE)["current"])

    def test_schreibweisen_desselben_dienstes_ergeben_keinen_falschen_blocker(self):
        write(self.ws / "migration" / "inventory" / "apps.json",
              {"services": [{"service_id": "banner-a", "decision": "keep"},
                            {"service_id": "app:banner-b-alt", "decision": "keep"}]})
        source = {**self.SOURCE, "rules": [
            {"key": "cookie_banner", "rule": "same_as_reference", "target": "Banner A",
             "keep": [["app:banner-a", "banner-a"]], "drop": [["app:banner-b", "app:banner-b-alt"]]}]}
        result = policies.apply(self.ws, source)
        self.assertEqual(result["open_items_added"], [])
        apps = {s["service_id"]: s["decision"] for s in
                json.loads((self.ws / "migration" / "inventory" / "apps.json").read_text())["services"]}
        self.assertEqual(apps, {"banner-a": "keep", "app:banner-b-alt": "drop"})

    def test_keep_bei_offener_regel_ist_ungueltig(self):
        broken = {**self.SOURCE, "rules": [{"key": "x", "rule": "open", "keep": ["app:a"]}]}
        self.assertTrue(policies.validate(broken))


class RunStateSince0311Test(Workspace):
    def test_launch_ohne_betreiber_wird_verweigert(self):
        state = run_state.new(self.ws, RUN)
        with self.assertRaises(run_state.StateError):
            state.set_phase("9-launch", "running")

    def test_freeze_werte_werden_verweigert(self):
        state = run_state.new(self.ws, RUN)
        with self.assertRaises(run_state.StateError):
            state.set_value("freeze_until", "2026-02-01")

    def test_testrunde_vor_dem_meilenstein_wird_verweigert(self):
        state = self.state_until_verify()
        self.all_checkers(("structure",))
        with self.assertRaises(run_state.StateError) as caught:
            state.set_phase("8-test-round", "running")
        self.assertIn("all_checkers", str(caught.exception))

    def test_upgrade_benennt_phasen_um_und_entfernt_den_stopp(self):
        write(self.ws / "reporting" / "config.json",
              {"theme_migration": {"people": ["Beispielperson"], "freeze": {"from": None, "until": None}}})
        old = run_state.new(self.ws, RUN)
        old.data["phases"] = {("7-sync-1" if p == "7-sync" else "8-acceptance" if p == "8-test-round" else p): "open"
                              for p in run_state.PHASES}
        old.data["phases"]["7-sync-1"] = "done"
        old.data["values"]["freeze_until"] = "2026-02-01"
        old.save()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_state.main(["upgrade", "--workspace", str(self.ws)]), 0)
        state = run_state.load(self.ws, RUN)
        self.assertEqual(state.data["phases"]["7-sync"], "done")
        self.assertNotIn("8-acceptance", state.data["phases"])
        self.assertNotIn("freeze_until", state.data["values"])
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        self.assertNotIn("freeze", config["theme_migration"])

    def test_alter_lauf_verlangt_upgrade_vor_dem_schreiben(self):
        old = run_state.new(self.ws, RUN)
        old.data["phases"]["7-sync-1"] = old.data["phases"].pop("7-sync")
        old.save()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_state.main(["set", "--workspace", str(self.ws), "--key", "last_sync", "--value", "2026-01-02"])
        self.assertEqual(code, 2)
        self.assertIn("upgrade", out.getvalue())

    def test_nach_jedem_befehl_steht_migration_json_im_lauf(self):
        with contextlib.redirect_stdout(io.StringIO()):
            run_state.main(["init", "--workspace", str(self.ws), "--run-id", RUN])
        data = json.loads((self.ws / "reporting" / "runs" / RUN / "migration.json").read_text())
        self.assertEqual(data["current_step"], 1)
        self.assertEqual(len(data["steps"]), 9)
        self.assertIn("plugin_version", data)

    def test_zweite_sitzung_wird_abgewiesen(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-a"}):
            with contextlib.redirect_stdout(io.StringIO()):
                run_state.main(["init", "--workspace", str(self.ws), "--run-id", RUN])
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-b"}):
            with contextlib.redirect_stdout(out):
                code = run_state.main(["log", "--workspace", str(self.ws), "--kind", "note", "--text", "x"])
        self.assertEqual(code, 2)
        self.assertIn("andere Claude-Sitzung", out.getvalue())

    def test_uebernahme_mit_force_wird_im_journal_festgehalten(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-a"}):
            with contextlib.redirect_stdout(io.StringIO()):
                run_state.main(["init", "--workspace", str(self.ws), "--run-id", RUN])
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-b"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_state.main(["claim", "--workspace", str(self.ws), "--force"]), 0)
        journal = (self.ws / "reporting" / "runs" / RUN / "journal.jsonl").read_text()
        self.assertIn("sitzung-a", journal)

    def test_alte_sperre_haelt_nicht_mehr(self):
        old = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-a"}):
            run_state.claim(self.ws, RUN, now=old)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-b"}):
            run_state.claim(self.ws, RUN, now=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc))
        held = json.loads(run_state.lock_path(self.ws, RUN).read_text())
        self.assertEqual(held["session_id"], "sitzung-b")

    def test_sperre_steht_in_gitignore(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sitzung-a"}):
            run_state.claim(self.ws, RUN)
            run_state.claim(self.ws, RUN)
        lines = (self.ws / ".gitignore").read_text().splitlines()
        self.assertEqual(lines.count("reporting/runs/*/session.lock"), 1)


if __name__ == "__main__":
    unittest.main()
