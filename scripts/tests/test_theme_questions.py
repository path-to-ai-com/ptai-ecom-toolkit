"""Tests für die Fragen an das Team seit 0.3.14: Erklärung, Vergleich, Empfehlung mit Grund."""
import contextlib
import io
import json
import unittest
from unittest import mock

from theme import questions, ruled, run_state
from tests.test_theme_steps import Workspace, write

LIVE = "https://beispielshop.test/products/ring?preview_theme_id=000000000000"
DRAFT = "https://beispielshop.test/products/ring?preview_theme_id=000000000002"


def run(argv: list, module=questions) -> tuple[int, object]:
    """Ruft die CLI auf und gibt Exit-Code und die gelesene JSON-Zeile zurück."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(argv)
    return code, json.loads(out.getvalue())


class PeopleWorkspace(Workspace):
    """Ein Workspace mit zwei Personen, die entscheiden dürfen."""

    def setUp(self):
        super().setUp()
        write(self.ws / "reporting" / "config.json",
              {"theme_migration": {"people": ["Erika Muster", "Max Beispiel"]}})


class AskTest(PeopleWorkspace):

    def test_frage_ohne_erklaerung_wird_verweigert(self):
        with self.assertRaises(questions.QuestionError) as caught:
            self.ask(context="  ")
        self.assertIn("context", str(caught.exception))

    def test_frage_ohne_grund_wird_verweigert(self):
        with self.assertRaises(questions.QuestionError) as caught:
            self.ask(reason="")
        self.assertIn("reason", str(caught.exception))

    def test_empfehlung_muss_eine_der_optionen_sein(self):
        with self.assertRaises(questions.QuestionError):
            self.ask(recommendation="lieber wie heute, weil es funktioniert")

    def test_keine_empfehlung_ist_ausdruecklich_none_mit_grund(self):
        entry = self.ask(recommendation=None, reason="Keine Empfehlung, das klärt ihr im Team.")
        self.assertIsNone(entry["recommendation"])
        stored = questions.load(self.ws)[0]
        self.assertIsNone(stored["recommendation"])
        self.assertEqual(stored["reason"], "Keine Empfehlung, das klärt ihr im Team.")

    def test_eine_option_ohne_freitext_ist_keine_frage(self):
        with self.assertRaises(questions.QuestionError):
            self.ask(options=["wie heute"])

    def test_option_mit_freitext_zaehlt_als_zweite_antwort(self):
        entry = self.ask("Wer testet?", gate="G4-acceptance", options=["Max Beispiel"], other="Eine andere Person",
                         recommendation=None, reason="Keine Empfehlung, das klärt ihr im Team.")
        self.assertEqual(entry["other"], "Eine andere Person")
        self.assertEqual(entry["options"], ["Max Beispiel"])

    def test_vergleich_braucht_preview_theme_id(self):
        with self.assertRaises(questions.QuestionError) as caught:
            self.ask(compare=[("Produktseite", "https://beispielshop.test/products/ring", DRAFT)])
        self.assertIn("preview_theme_id", str(caught.exception))

    def test_vergleich_mit_derselben_seite_wird_verweigert(self):
        with self.assertRaises(questions.QuestionError):
            self.ask(compare=[("Produktseite", LIVE, LIVE)])

    def test_vergleich_wird_als_paar_gespeichert(self):
        entry = self.ask(compare=[("Produktseite", LIVE, DRAFT)])
        self.assertEqual(entry["compare"], [{"label": "Produktseite", "live_url": LIVE, "draft_url": DRAFT}])

    def test_entscheider_muss_in_people_stehen(self):
        with self.assertRaises(questions.QuestionError):
            self.ask(decider=["Beispiel Team"])
        entry = self.ask(decider=["Erika Muster", "Erika Muster"])
        self.assertEqual(entry["decider"], ["Erika Muster"])

    def test_alte_frage_ohne_neue_felder_bleibt_lesbar(self):
        write(questions.path(self.ws), {"questions": [
            {"id": "Q-001", "gate": "G1-decisions", "text": "Alte Frage?", "options": [], "recommendation": "",
             "status": "open", "asked_at": "2026-01-01T08:00:00+00:00"}]})
        self.assertEqual(len(questions.open_for(self.ws)), 1)
        self.assertEqual(self.ask()["id"], "Q-002")


class AskCliTest(PeopleWorkspace):
    BASE = ["ask", "--gate", "G2-mapping", "--text", "Gestaltung vor oder nach der Abnahme angleichen?",
            "--context", "Der Entwurf weicht an 12 Stellen sichtbar vom heutigen Shop ab.",
            "--option", "Vor der Abnahme", "--option", "Nach der Abnahme",
            "--reason", "Sonst meldet ihr in der Abnahme dieselben Abweichungen noch einmal."]

    def test_ohne_empfehlung_und_ohne_ausdruecklich_keine_wird_verweigert(self):
        code, result = run([*self.BASE, "--workspace", str(self.ws)])
        self.assertEqual(code, 2)
        self.assertIn("--no-recommendation", result["error"])

    def test_empfehlung_und_ausdruecklich_keine_zugleich_wird_verweigert(self):
        code, _ = run([*self.BASE, "--workspace", str(self.ws), "--recommendation", "Vor der Abnahme",
                       "--no-recommendation"])
        self.assertEqual(code, 2)

    def test_ask_mit_allen_optionen(self):
        code, result = run([*self.BASE, "--workspace", str(self.ws), "--recommendation", "Vor der Abnahme",
                            "--compare", "Produktseite", LIVE, DRAFT, "--decider", "Erika Muster",
                            "--other", "Anders, und zwar"])
        self.assertEqual(code, 0, result)
        self.assertEqual(result["recommendation"], "Vor der Abnahme")
        self.assertEqual(result["compare"][0]["draft_url"], DRAFT)
        self.assertEqual(result["decider"], ["Erika Muster"])
        self.assertEqual(result["other"], "Anders, und zwar")
        self.assertEqual(result["status"], "open")



class WithdrawTest(PeopleWorkspace):
    def test_zurueckgezogene_frage_steht_als_punkt_ohne_frage(self):
        entry = self.ask()
        result = questions.withdraw(self.ws, entry["id"], "as_today", "Kontaktformular mit drei Zusatzfeldern")
        self.assertEqual(result["ruled"]["id"], "R-001")
        self.assertEqual(questions.load(self.ws)[0]["status"], "withdrawn")
        self.assertEqual(questions.load(self.ws)[0]["ruled_id"], "R-001")
        self.assertEqual(ruled.visible(self.ws), [{"id": "R-001", "text": "Kontaktformular mit drei Zusatzfeldern",
                                                   "source": "as_today"}])
        self.assertEqual(ruled.load(self.ws)[0]["question_id"], entry["id"])

    def test_zurueckgezogene_frage_haelt_g1_nicht_an(self):
        entry = self.ask()
        questions.withdraw(self.ws, entry["id"], "policy", "Wie die Vorgabe der Marke")
        state = run_state.new(self.ws, "2026-01-01-migration")
        state.decide_gate("G1-decisions", "Erika Muster")
        self.assertEqual(questions.open_for(self.ws), [])

    def test_unbekannte_herkunft_aendert_nichts(self):
        entry = self.ask()
        with self.assertRaises(questions.QuestionError):
            questions.withdraw(self.ws, entry["id"], "gefuehl", "irgendwas")
        self.assertEqual(questions.load(self.ws)[0]["status"], "open")
        self.assertFalse(ruled.path(self.ws).exists())

    def test_beantwortete_frage_wird_nicht_zurueckgezogen(self):
        entry = self.ask()
        questions.answer(self.ws, entry["id"], "Erika Muster", "wie heute")
        with self.assertRaises(questions.QuestionError):
            questions.withdraw(self.ws, entry["id"], "as_today", "wie heute")

    def test_antwort_auf_zurueckgezogene_frage_nennt_den_punkt(self):
        entry = self.ask()
        questions.withdraw(self.ws, entry["id"], "as_today", "wie heute")
        with self.assertRaises(questions.QuestionError) as caught:
            questions.answer(self.ws, entry["id"], "Erika Muster", "wie heute")
        self.assertIn("R-001", str(caught.exception))

    def test_cli_withdraw(self):
        entry = self.ask()
        code, result = run(["withdraw", "--workspace", str(self.ws), "--id", entry["id"], "--source",
                            "as_reference", "--text", "Warenkorb als eigene Seite wie im Referenz-Store"])
        self.assertEqual(code, 0, result)
        self.assertEqual(result["ruled"]["source"], "as_reference")
        code, listed = run(["list", "--workspace", str(self.ws), "--status", "withdrawn"])
        self.assertEqual([q["id"] for q in listed], [entry["id"]])


class ImportTest(PeopleWorkspace):
    AT = "2026-01-13T09:12:00Z"

    def test_antwort_aus_dem_cockpit_wird_eingetragen(self):
        entry = self.ask()
        result = questions.import_answers(self.ws, [{"id": entry["id"], "value": "wie heute", "by": "Erika Muster",
                                                     "at": self.AT}])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["imported"][0]["id"], entry["id"])
        stored = questions.load(self.ws)[0]
        self.assertEqual((stored["status"], stored["answer"], stored["answered_by"], stored["answered_via"]),
                         ("answered", "wie heute", "Erika Muster", "cockpit"))
        self.assertEqual(stored["answered_at"], "2026-01-13T09:12:00+00:00")

    def test_antwort_von_path_to_ai_gilt_auch_ausserhalb_von_people(self):
        # Das Cockpit entscheidet, wer antworten darf; am 15.10.2026 blieb sonst eine Antwort von Path to AI offen.
        entry = self.ask()
        result = questions.import_answers(self.ws, [{"id": entry["id"], "value": "Vor der Abnahme",
                                                     "by": "Pat Betreiber", "at": self.AT}])
        self.assertEqual(result["skipped"], [])
        stored = questions.load(self.ws)[0]
        self.assertEqual((stored["status"], stored["answered_by"], stored["answered_via"]),
                         ("answered", "Pat Betreiber", "cockpit"))
        self.assertNotIn("answered_role", stored)

    def test_rolle_operator_bleibt_an_der_antwort(self):
        entry = self.ask()
        result = questions.import_answers(self.ws, [{"id": entry["id"], "value": "Vor der Abnahme",
                                                     "by": "Pat Betreiber", "at": self.AT, "role": "operator"}])
        self.assertEqual(result["imported"][0]["role"], "operator")
        self.assertEqual(questions.load(self.ws)[0]["answered_role"], "operator")

    def test_ohne_people_wird_die_antwort_aus_dem_cockpit_uebernommen(self):
        entry = self.ask()
        write(self.ws / "reporting" / "config.json", {"theme_migration": {}})
        result = questions.import_answers(self.ws, [{"id": entry["id"], "value": "wie heute", "by": "Erika Muster"}])
        self.assertEqual([i["id"] for i in result["imported"]], [entry["id"]])

    def test_sammelname_oder_ohne_namen_bleibt_offen_mit_grund(self):
        entry = self.ask()
        result = questions.import_answers(self.ws, [{"id": entry["id"], "value": "wie heute", "by": "Team Nord"},
                                                    {"id": entry["id"], "value": "wie heute", "by": ""}])
        self.assertEqual(result["imported"], [])
        self.assertIn("Sammelname", result["skipped"][0]["reason"])
        self.assertIn("keinen Namen", result["skipped"][1]["reason"])
        self.assertEqual(questions.load(self.ws)[0]["status"], "open")

    def test_im_repo_beantwortete_frage_behaelt_ihre_antwort(self):
        entry = self.ask()
        questions.answer(self.ws, entry["id"], "Max Beispiel", "ohne Zusatzfelder")
        result = questions.import_answers(self.ws, [{"id": entry["id"], "value": "wie heute", "by": "Erika Muster"}])
        self.assertEqual(result["imported"], [])
        self.assertIn("gilt", result["skipped"][0]["reason"])
        stored = questions.load(self.ws)[0]
        self.assertEqual((stored["answer"], stored["answered_via"]), ("ohne Zusatzfelder", "session"))

    def test_unbekannte_zurueckgezogene_und_unentschiedene_bleiben_offen(self):
        first, second, third = self.ask(), self.ask("Zweite Frage?"), self.ask("Dritte Frage?")
        questions.withdraw(self.ws, second["id"], "as_today", "wie heute")
        result = questions.import_answers(self.ws, [
            {"id": "Q-099", "value": "wie heute", "by": "Erika Muster"},
            {"id": second["id"], "value": "wie heute", "by": "Erika Muster"},
            {"id": third["id"], "value": "später", "by": "Erika Muster"},
            {"id": first["id"], "value": "wie heute", "by": "Erika Muster"},
            {"id": first["id"], "value": "ohne Zusatzfelder", "by": "Max Beispiel"},
        ])
        self.assertEqual([i["id"] for i in result["imported"]], [first["id"]])
        self.assertEqual([s["id"] for s in result["skipped"]], ["Q-099", second["id"], third["id"], first["id"]])
        self.assertEqual(questions.load(self.ws)[0]["answer"], "wie heute")
        self.assertEqual(questions.load(self.ws)[2]["status"], "open")

    def test_keine_liste_ist_ein_fehler(self):
        with self.assertRaises(questions.QuestionError):
            questions.import_answers(self.ws, {"id": "Q-001"})

    def test_cli_import_aus_datei_und_stdin(self):
        first, second = self.ask(), self.ask("Zweite Frage?")
        answers = self.ws / "answers.json"
        write(answers, [{"id": first["id"], "value": "wie heute", "by": "Erika Muster", "at": self.AT}])
        code, result = run(["import", "--workspace", str(self.ws), "--file", str(answers)])
        self.assertEqual(code, 0, result)
        self.assertEqual(result["imported"][0]["by"], "Erika Muster")
        stdin = io.StringIO(json.dumps([{"id": second["id"], "value": "wie heute", "by": "Team"}]))
        with mock.patch("sys.stdin", stdin):
            code, result = run(["import", "--workspace", str(self.ws), "--file", "-"])
        self.assertEqual(code, 1)
        self.assertEqual(result["skipped"][0]["id"], second["id"])

    def test_cli_import_ohne_datei_oder_mit_kaputtem_json(self):
        code, result = run(["import", "--workspace", str(self.ws)])
        self.assertEqual(code, 2)
        broken = self.ws / "answers.json"
        broken.write_text("[{", encoding="utf-8")
        code, result = run(["import", "--workspace", str(self.ws), "--file", str(broken)])
        self.assertEqual(code, 2)
        self.assertIn("kein JSON", result["error"])

    def test_antwort_in_der_sitzung_traegt_session(self):
        entry = self.ask()
        questions.answer(self.ws, entry["id"], "Erika Muster", "wie heute")
        self.assertEqual(questions.load(self.ws)[0]["answered_via"], "session")


class RuledTest(PeopleWorkspace):
    def test_add_vergibt_fortlaufende_ids(self):
        first = ruled.add(self.ws, "Tag Manager als eigener Code", "policy")
        second = ruled.add(self.ws, "Warenkorb als eigene Seite", "as_reference")
        self.assertEqual((first["id"], second["id"]), ("R-001", "R-002"))

    def test_derselbe_punkt_entsteht_nur_einmal(self):
        ruled.add(self.ws, "Warenkorb als eigene Seite", "as_today")
        again = ruled.add(self.ws, "Warenkorb als eigene Seite", "as_today")
        self.assertEqual(again["id"], "R-001")
        self.assertEqual(len(ruled.load(self.ws)), 1)

    def test_text_und_herkunft_sind_pflicht(self):
        with self.assertRaises(ruled.RuledError):
            ruled.add(self.ws, " ", "as_today")
        with self.assertRaises(ruled.RuledError):
            ruled.add(self.ws, "wie heute", "today")

    def test_zurueckgenommener_punkt_erscheint_nicht_mehr(self):
        entry = ruled.add(self.ws, "Zuletzt angesehen entfällt", "check")
        with self.assertRaises(ruled.RuledError):
            ruled.revoke(self.ws, entry["id"], "")
        ruled.revoke(self.ws, entry["id"], "Einwand von Erika Muster: wird genutzt")
        self.assertEqual(ruled.visible(self.ws), [])
        self.assertEqual(ruled.load(self.ws)[0]["revoke_reason"], "Einwand von Erika Muster: wird genutzt")
        self.assertEqual(ruled.add(self.ws, "Zuletzt angesehen bleibt", "operator")["id"], "R-002")

    def test_beschaedigte_datei_wird_nicht_still_ueberschrieben(self):
        ruled.path(self.ws).parent.mkdir(parents=True, exist_ok=True)
        ruled.path(self.ws).write_text("{kaputt", encoding="utf-8")
        with self.assertRaises(ruled.RuledError):
            ruled.add(self.ws, "wie heute", "as_today")
        self.assertEqual(ruled.path(self.ws).read_text(encoding="utf-8"), "{kaputt")

    def test_cli_add_revoke_list(self):
        code, entry = run(["add", "--workspace", str(self.ws), "--source", "operator", "--text",
                           "Für diesen Store entscheidet Erika Muster"], module=ruled)
        self.assertEqual(code, 0, entry)
        code, revoked = run(["revoke", "--workspace", str(self.ws), "--id", entry["id"], "--reason",
                             "Person gewechselt"], module=ruled)
        self.assertEqual(code, 0, revoked)
        code, listed = run(["list", "--workspace", str(self.ws)], module=ruled)
        self.assertEqual(listed[0]["revoke_reason"], "Person gewechselt")
        code, error = run(["add", "--workspace", str(self.ws), "--source", "x", "--text", "y"], module=ruled)
        self.assertEqual(code, 2)
        self.assertIn("error", error)


if __name__ == "__main__":
    unittest.main()
