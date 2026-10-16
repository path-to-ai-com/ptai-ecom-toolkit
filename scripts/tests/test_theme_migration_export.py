"""Tests für `migration.json` seit 0.3.14: Fragen mit Antwort, ohne Frage Entschiedenes, Übergabe, Repo."""
import contextlib
import io
import json
import subprocess
import unittest
from datetime import datetime, timezone

from theme import handover, questions, ruled, run_state, steps
from tests.test_theme_steps import CLEAN_GIT, RUN, Workspace, write

LIVE = "https://beispielshop.test/?preview_theme_id=000000000000"
DRAFT = "https://beispielshop.test/?preview_theme_id=000000000002"


class ExportWorkspace(Workspace):
    def setUp(self):
        super().setUp()
        write(self.ws / "reporting" / "config.json",
              {"portal": {"brand": "beispielmarke", "shop": "beispielshop"},
               "theme_migration": {"people": ["Erika Muster", "Max Beispiel"]}})

    def export(self, state=None) -> dict:
        return steps.export(self.ws, (state or run_state.new(self.ws, RUN)).data, "0.0.0", git_status=CLEAN_GIT)


class QuestionsInExportTest(ExportWorkspace):
    def test_offene_frage_traegt_alle_felder_und_keine_antwort(self):
        self.ask("Gestaltung vor oder nach der Abnahme angleichen?", gate="G2-mapping",
                 options=["Vor der Abnahme", "Nach der Abnahme"], recommendation="Vor der Abnahme",
                 compare=[("Startseite", LIVE, DRAFT)], decider=["Erika Muster"])
        question = self.export()["questions"][0]
        self.assertEqual(question["step"], 3)
        self.assertEqual(question["context"], "Das Formular hat heute drei Zusatzfelder.")
        self.assertEqual(question["compare"], [{"label": "Startseite", "live_url": LIVE, "draft_url": DRAFT}])
        self.assertEqual(question["recommendation"], "Vor der Abnahme")
        self.assertEqual(question["reason"], "So bleibt es wie heute.")
        self.assertEqual(question["decider"], ["Erika Muster"])
        self.assertIsNone(question["other"])
        self.assertIsNone(question["answer"])

    def test_ohne_entscheider_entscheiden_alle_aus_people(self):
        self.ask()
        self.assertEqual(self.export()["questions"][0]["decider"], ["Erika Muster", "Max Beispiel"])

    def test_beantwortete_frage_steht_mit_antwort_und_herkunft(self):
        first, second = self.ask(), self.ask("Zweite Frage?")
        questions.import_answers(self.ws, [{"id": first["id"], "value": "wie heute", "by": "Erika Muster",
                                            "at": "2026-01-13T09:12:00+00:00"}])
        questions.answer(self.ws, second["id"], "Max Beispiel", "ohne Zusatzfelder",
                         now=datetime(2026, 1, 14, 8, 0, tzinfo=timezone.utc))
        answers = [q["answer"] for q in self.export()["questions"]]
        self.assertEqual(answers, [
            {"value": "wie heute", "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00", "via": "cockpit"},
            {"value": "ohne Zusatzfelder", "by": "Max Beispiel", "at": "2026-01-14T08:00:00+00:00", "via": "session"},
        ])

    def test_zurueckgezogene_frage_erscheint_nicht_ihr_ergebnis_in_ruled(self):
        first, second = self.ask(), self.ask("Zweite Frage?")
        questions.withdraw(self.ws, first["id"], "as_today", "Kontaktformular wie heute")
        data = self.export()
        self.assertEqual([q["id"] for q in data["questions"]], [second["id"]])
        self.assertEqual(data["ruled"], [{"id": "R-001", "text": "Kontaktformular wie heute", "source": "as_today"}])

    def test_antwort_von_path_to_ai_traegt_ihre_rolle(self):
        entry = self.ask()
        questions.import_answers(self.ws, [{"id": entry["id"], "value": "wie heute", "by": "Pat Betreiber",
                                            "at": "2026-01-13T09:12:00+00:00", "role": "operator"}])
        self.assertEqual(self.export()["questions"][0]["answer"],
                         {"value": "wie heute", "by": "Pat Betreiber", "at": "2026-01-13T09:12:00+00:00",
                          "via": "cockpit", "role": "operator"})

    def test_alte_frage_ohne_neue_felder_wird_exportiert(self):
        write(questions.path(self.ws), {"questions": [
            {"id": "Q-001", "gate": "G1-decisions", "text": "Alte Frage?", "options": ["ja", "nein"],
             "recommendation": "", "status": "answered", "answer": "ja", "answered_by": "Erika Muster",
             "answered_at": "2026-01-02T10:00:00+00:00", "asked_at": "2026-01-01T08:00:00+00:00"}]})
        question = self.export()["questions"][0]
        self.assertIsNone(question["context"])
        self.assertIsNone(question["reason"])
        self.assertIsNone(question["recommendation"])
        self.assertEqual(question["compare"], [])
        self.assertEqual(question["answer"]["via"], "session")

    def test_show_zaehlt_nur_offene_fragen(self):
        first = self.ask()
        self.ask("Zweite Frage?")
        questions.answer(self.ws, first["id"], "Erika Muster", "wie heute")
        with contextlib.redirect_stdout(io.StringIO()):
            run_state.main(["init", "--workspace", str(self.ws), "--run-id", RUN])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run_state.main(["show", "--workspace", str(self.ws)])
        self.assertEqual(json.loads(out.getvalue())["open_questions"], 1)
        data = json.loads((self.ws / "reporting" / "runs" / RUN / "migration.json").read_text())
        self.assertEqual(len(data["questions"]), 2)



class TermsSince0316Test(ExportWorkspace):
    """Vertrag V15: Schritt 6 heißt "Abnahme". Ein bestehender Lauf zeigt das beim nächsten Export."""

    def test_schritt_sechs_heisst_abnahme(self):
        step = self.export()["steps"][5]
        self.assertEqual((step["key"], step["name"]), ("test_round", "Abnahme"))

    def test_alte_saetze_im_lauf_zeigen_das_neue_wort(self):
        write(questions.path(self.ws), {"questions": [
            {"id": "Q-001", "gate": "G2-mapping", "text": "Gestaltung vor oder nach der Testrunde angleichen?",
             "context": "Offen ist nur, ob schon vor der Testrunde.",
             "options": ["Vor der Testrunde", "Nach der Testrunde"], "recommendation": "Vor der Testrunde",
             "reason": "Sonst meldet ihr in der Testrunde dieselben Abweichungen.",
             "status": "answered", "answer": "Vor der Testrunde", "answered_by": "Erika Muster",
             "answered_at": "2026-01-02T10:00:00+00:00", "asked_at": "2026-01-01T08:00:00+00:00"}]})
        ruled.add(self.ws, "Zwei Testrunden statt einer", "operator")
        handover.write(self.ws, "Testrunde", "Danach ist der Entwurf bereit für die Testrunde.",
                       ["Testrunde ins Cockpit stellen"], step=1)
        data = self.export()
        question = data["questions"][0]
        self.assertEqual(question["text"], "Gestaltung vor oder nach der Abnahme angleichen?")
        self.assertEqual(question["context"], "Offen ist nur, ob schon vor der Abnahme.")
        self.assertEqual(question["options"], ["Vor der Abnahme", "Nach der Abnahme"])
        self.assertEqual(question["recommendation"], "Vor der Abnahme")
        self.assertEqual(question["reason"], "Sonst meldet ihr in der Abnahme dieselben Abweichungen.")
        self.assertEqual(question["answer"]["value"], "Vor der Abnahme")
        self.assertEqual(data["ruled"][0]["text"], "Zwei Abnahmen statt einer")
        self.assertEqual((data["now"], data["after"], data["operator_tasks"]),
                         ("Abnahme", "Danach ist der Entwurf bereit für die Abnahme.",
                          ["Abnahme ins Cockpit stellen"]))
        # Die Dateien des Laufs bleiben, wie die Sitzung sie geschrieben hat.
        self.assertEqual(questions.load(self.ws)[0]["answer"], "Vor der Testrunde")

    def test_nur_das_ganze_wort_wird_ersetzt(self):
        self.assertEqual(steps.current_terms("Testrundenbericht und Testrunde."), "Testrundenbericht und Abnahme.")
        self.assertEqual(steps.current_terms(["Testrunden", None]), ["Abnahmen", None])
        self.assertIsNone(steps.current_terms(None))

class RuledInExportTest(ExportWorkspace):
    def test_ohne_datei_ist_ruled_leer(self):
        self.assertEqual(self.export()["ruled"], [])

    def test_zurueckgenommene_punkte_fehlen(self):
        kept = ruled.add(self.ws, "Tag Manager als eigener Code", "policy")
        dropped = ruled.add(self.ws, "Zuletzt angesehen entfällt", "check")
        ruled.revoke(self.ws, dropped["id"], "Einwand des Teams")
        self.assertEqual([r["id"] for r in self.export()["ruled"]], [kept["id"]])


class HandoverTest(ExportWorkspace):
    def test_ohne_uebergabe_gilt_der_aktuelle_schritt(self):
        data = self.export()
        self.assertEqual((data["now"], data["after"], data["operator_tasks"]), ("Shop gesichert", "", []))

    def test_uebergabe_aus_demselben_schritt_gilt(self):
        handover.write(self.ws, "Abstimmung", "Danach baut Claude den Entwurf um.",
                       ["Wir lesen die App-Liste im Shopify-Admin."], step=1)
        data = self.export()
        self.assertEqual(data["now"], "Abstimmung")
        self.assertEqual(data["after"], "Danach baut Claude den Entwurf um.")
        self.assertEqual(data["operator_tasks"], ["Wir lesen die App-Liste im Shopify-Admin."])

    def test_aufgabe_des_betreibers_macht_ihn_zustaendig(self):
        handover.write(self.ws, "Abstimmung", "Danach baut Claude den Entwurf um.",
                       ["Wir lesen die App-Liste im Shopify-Admin."], step=1)
        self.assertEqual(self.export()["owner"], "operator")

    def test_uebergabe_aus_einem_anderen_schritt_gilt_nicht_mehr(self):
        handover.write(self.ws, "Abstimmung", "Danach baut Claude den Entwurf um.", ["Aufgabe"], step=2)
        data = self.export()
        self.assertEqual((data["now"], data["after"], data["operator_tasks"]), ("Shop gesichert", "", []))

    def test_uebergabe_ohne_schritt_gilt(self):
        write(handover.path(self.ws), {"now": "Abstimmung", "after": "Danach weiter.", "operator_tasks": []})
        self.assertEqual(self.export()["now"], "Abstimmung")

    def test_now_ist_pflicht(self):
        with self.assertRaises(handover.HandoverError):
            handover.write(self.ws, " ", "Danach weiter.")

    def test_beschaedigte_uebergabe_haelt_den_export_an(self):
        handover.path(self.ws).parent.mkdir(parents=True, exist_ok=True)
        handover.path(self.ws).write_text("{kaputt", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            run_state.main(["init", "--workspace", str(self.ws), "--run-id", RUN])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_state.main(["show", "--workspace", str(self.ws)])
        self.assertEqual(code, 2)
        self.assertIn("next.json", out.getvalue())

    def test_cli_write_traegt_den_aktuellen_schritt_ein(self):
        with contextlib.redirect_stdout(io.StringIO()):
            run_state.main(["init", "--workspace", str(self.ws), "--run-id", RUN])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = handover.main(["write", "--workspace", str(self.ws), "--now", "Shop sichern",
                                  "--after", "Danach nimmt Claude euren Shop auf.",
                                  "--operator-task", "Wir legen die Vorgaben der Marke ins Repo."])
        self.assertEqual(code, 0, out.getvalue())
        written = json.loads(handover.path(self.ws).read_text())
        self.assertEqual(written["step"], 1)
        self.assertEqual(written["operator_tasks"], ["Wir legen die Vorgaben der Marke ins Repo."])
        with contextlib.redirect_stdout(io.StringIO()):
            run_state.main(["show", "--workspace", str(self.ws)])
        data = json.loads((self.ws / "reporting" / "runs" / RUN / "migration.json").read_text())
        self.assertEqual(data["now"], "Shop sichern")
        self.assertEqual(data["after"], "Danach nimmt Claude euren Shop auf.")


class RepoNameTest(ExportWorkspace):
    def git(self, *args):
        subprocess.run(["git", "-C", str(self.ws), *args], check=True, capture_output=True)

    def test_ohne_git_gilt_der_ordnername(self):
        self.assertEqual(self.export()["repo"], self.ws.resolve().name)

    def test_name_aus_dem_remote_origin(self):
        self.git("init", "-q")
        for url, name in (("git@github.com:beispiel-org/beispielshop-workspace.git", "beispielshop-workspace"),
                          ("https://github.com/beispiel-org/beispielshop-zwei", "beispielshop-zwei"),
                          ("https://github.com/beispiel-org/beispielshop-drei.git/", "beispielshop-drei")):
            with self.subTest(url=url):
                self.git("remote", "add", "origin", url)
                self.assertEqual(steps.repo_name(self.ws), name)
                self.git("remote", "remove", "origin")


if __name__ == "__main__":
    unittest.main()
