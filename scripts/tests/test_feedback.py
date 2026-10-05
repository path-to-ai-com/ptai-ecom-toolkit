"""Tests fuer `audit.feedback`: was von aussen hereinkam und worauf es zeigt."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import feedback, measures  # noqa: E402


def entry(**kw):
    basis = {
        "id": "FB-001",
        "received": "2026-09-17",
        "source": "Aufgabenliste vom 17.09.2026, Mara Beispiel",
        "ref": "1234567890123456",
        "title": "Bewertungssterne in Kopfzeile und auf der Produktseite",
        "links": [{"measure": "M-069", "certainty": "confirmed",
                   "why": "M-069 ist die Bewertungsangabe in der Ankuendigungsleiste."}],
    }
    basis.update(kw)
    return basis


def backlog_with(*ids):
    """Ein Massnahmen-Bestand, der genau diese Kennungen enthaelt."""
    doc = measures.empty()
    for i in ids:
        doc = measures.create(doc, title=f"Massnahme {i}", discipline="seo",
                              evidence="Beleg", confidence="confirmed",
                              leverage="high", effort="small")
    return doc


class TestLaden(unittest.TestCase):
    def test_eine_fehlende_datei_ist_kein_fehler(self):
        """Der erste Lauf hat kein Feedback, und das ist der Normalfall."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(feedback.load(tmp), [])

    def test_kaputtes_json_wirft_statt_still_leer_zu_sein(self):
        """Eine unlesbare Datei als 'kein Feedback' zu behandeln hiesse, dass
        jede eingetragene Zuordnung stillschweigend verschwindet."""
        with tempfile.TemporaryDirectory() as tmp:
            p = feedback.feedback_path(tmp)
            p.parent.mkdir(parents=True)
            p.write_text("{kaputt", encoding="utf-8")
            with self.assertRaises(ValueError):
                feedback.load(tmp)

    def test_eine_blanke_liste_geht_auch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = feedback.feedback_path(tmp)
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps([entry()]), encoding="utf-8")
            self.assertEqual(len(feedback.load(tmp)), 1)


class TestPruefen(unittest.TestCase):
    def test_ein_vollstaendiger_eintrag_ist_sauber(self):
        self.assertEqual(feedback.validate([entry()]), [])

    def test_ohne_titel_weiss_niemand_worum_es_geht(self):
        errors = feedback.validate([entry(title="  ")])
        self.assertTrue(any("title" in f for f in errors), errors)

    def test_ohne_source_ist_spaeter_nicht_nachvollziehbar_wer_das_gesagt_hat(self):
        errors = feedback.validate([entry(source="")])
        self.assertTrue(any("source" in f for f in errors), errors)

    def test_eine_doppelte_kennung_wird_gemeldet(self):
        errors = feedback.validate([entry(), entry()])
        self.assertTrue(any("doppelt" in f for f in errors), errors)

    def test_eine_verknuepfung_ohne_grund_ist_eine_behauptung(self):
        """Dieselbe Regel wie 'keine Massnahme ohne Beleg': wer die
        Gleichsetzung spaeter pruefen will, braucht ihren Grund."""
        errors = feedback.validate([entry(links=[
            {"measure": "M-069", "certainty": "confirmed", "why": " "}])])
        self.assertTrue(any("why" in f for f in errors), errors)

    def test_eine_vermutete_verknuepfung_ohne_frage_ist_nicht_entscheidbar(self):
        errors = feedback.validate([entry(links=[
            {"measure": "M-012", "certainty": "proposed", "why": "Beides ist Weiterleitung."}])])
        self.assertTrue(any("question" in f for f in errors), errors)

    def test_eine_vermutete_verknuepfung_mit_frage_ist_sauber(self):
        self.assertEqual(feedback.validate([entry(links=[
            {"measure": "M-012", "certainty": "proposed",
             "why": "Beides ist Weiterleitung.",
             "question": "Welche Kategorien sind gemeint?"}])]), [])

    def test_eine_unbekannte_sicherheit_wird_gemeldet(self):
        errors = feedback.validate([entry(links=[
            {"measure": "M-069", "certainty": "vielleicht", "why": "Grund."}])])
        self.assertTrue(any("certainty" in f for f in errors), errors)

    def test_dieselbe_massnahme_steht_nur_einmal_im_eintrag(self):
        errors = feedback.validate([entry(links=[
            {"measure": "M-069", "certainty": "confirmed", "why": "Grund."},
            {"measure": "M-069", "certainty": "proposed", "why": "Grund.",
             "question": "Frage?"}])])
        self.assertTrue(any("M-069" in f for f in errors), errors)

    def test_ausserhalb_des_projekts_und_verknuepft_schliesst_sich_aus(self):
        """Was ausserhalb liegt, hat keine Massnahme, und was eine hat, liegt
        nicht ausserhalb."""
        errors = feedback.validate([entry(out_of_scope="Andere Marke.")])
        self.assertTrue(any("out_of_scope" in f for f in errors), errors)

    def test_ausserhalb_des_projekts_ohne_verknuepfung_ist_sauber(self):
        self.assertEqual(
            feedback.validate([entry(links=[], out_of_scope="Andere Marke, Systemanbindung.")]), [])

    def test_ein_leerer_grund_fuer_ausserhalb_ist_kein_grund(self):
        errors = feedback.validate([entry(links=[], out_of_scope="   ")])
        self.assertTrue(any("out_of_scope" in f for f in errors), errors)

    def test_angaben_aus_der_quelle_sind_sauber(self):
        self.assertEqual(feedback.validate([entry(original={
            "title": "Trust slider in header", "section": "UX & CRO",
            "priority": "High", "notes": "1. Referenzen sammeln 2. Entwürfe bauen"})]), [])

    def test_ein_unbekanntes_feld_aus_der_quelle_wird_gemeldet(self):
        """Das Portal beschriftet nur Felder, die es kennt. Ein fremder
        Schlüssel stünde dort unter seinem englischen Namen."""
        errors = feedback.validate([entry(original={"assignee": "Mara Beispiel"})])
        self.assertTrue(any("assignee" in f for f in errors), errors)

    def test_ein_leeres_feld_aus_der_quelle_wird_gemeldet(self):
        errors = feedback.validate([entry(original={"notes": "  "})])
        self.assertTrue(any("notes" in f for f in errors), errors)

    def test_neu_angelegt_gibt_es_nur_bei_einer_feststehenden_zuordnung(self):
        """Wer eine Maßnahme aus dem Punkt anlegt, hat entschieden, dass sie
        dazugehört. Eine Vermutung darüber gibt es nicht."""
        errors = feedback.validate([entry(created_measures=["M-080"], links=[
            {"measure": "M-080", "certainty": "proposed", "why": "Grund.",
             "question": "Frage?"}])])
        self.assertTrue(any("created_measures" in f for f in errors), errors)

    def test_die_angelegten_massnahmen_sind_eine_liste_von_kennungen(self):
        errors = feedback.validate([entry(created_measures="M-080")])
        self.assertTrue(any("created_measures" in f for f in errors), errors)

    def test_eine_angelegte_massnahme_steht_nur_einmal_da(self):
        errors = feedback.validate([entry(created_measures=["M-080", "M-080"])])
        self.assertTrue(any("M-080" in f for f in errors), errors)

    def test_eine_klaerung_mit_frage_ist_sauber(self):
        self.assertEqual(feedback.validate([entry(
            links=[], clarification="Was soll das Quiz am Ende empfehlen?")]), [])

    def test_eine_leere_klaerung_wird_gemeldet(self):
        errors = feedback.validate([entry(links=[], clarification="  ")])
        self.assertTrue(any("clarification" in f for f in errors), errors)

    def test_klaerung_und_ausserhalb_zugleich_wird_gemeldet(self):
        """Was außerhalb des Projekts liegt, braucht keine Frage."""
        errors = feedback.validate([entry(links=[], out_of_scope="Andere Marke.",
                                          clarification="Was ist gemeint?")])
        self.assertTrue(any("clarification" in f for f in errors), errors)

    def test_angelegt_ohne_verknuepfung_ist_sauber(self):
        """Der Fall vom 24.09.2026: FB-023 liegt inzwischen außerhalb des
        Projekts, M-080 ist trotzdem aus ihm entstanden."""
        self.assertEqual(feedback.validate([entry(
            links=[], created_measures=["M-080"], out_of_scope="Visuelles Redesign.")]), [])


class TestZustand(unittest.TestCase):
    """Der Zustand wird abgeleitet, nie gespeichert: kein Feld, das jemand
    nachziehen muesste."""

    def test_ohne_verknuepfung_ist_der_punkt_noch_nicht_zugeordnet(self):
        self.assertEqual(feedback.state(entry(links=[])), "open")

    def test_nur_bestaetigte_verknuepfungen_heissen_zugeordnet(self):
        self.assertEqual(feedback.state(entry()), "assigned")

    def test_eine_einzige_vermutung_macht_den_punkt_entscheidungsbeduerftig(self):
        item = entry(links=[
            {"measure": "M-069", "certainty": "confirmed", "why": "Grund."},
            {"measure": "M-012", "certainty": "proposed", "why": "Grund.",
             "question": "Frage?"}])
        self.assertEqual(feedback.state(item), "to_decide")

    def test_ausserhalb_des_projekts_ist_ein_eigener_zustand(self):
        self.assertEqual(
            feedback.state(entry(links=[], out_of_scope="Andere Marke.")), "out_of_scope")

    def test_nur_neu_angelegte_massnahmen_heissen_angelegt(self):
        """Der Fall vom 24.09.2026: ein Punkt, für den eine Maßnahme neu
        entstand, stand im Portal genauso als zugeordnet da wie einer, der in
        einer bestehenden aufging."""
        item = entry(created_measures=["M-080"], links=[
            {"measure": "M-080", "certainty": "confirmed", "why": "Als M-080 aufgenommen."}])
        self.assertEqual(feedback.state(item), "created")

    def test_neu_angelegt_und_bestehend_zugleich_heisst_zugeordnet(self):
        item = entry(created_measures=["M-080"], links=[
            {"measure": "M-069", "certainty": "confirmed", "why": "Grund."},
            {"measure": "M-080", "certainty": "confirmed", "why": "Als M-080 aufgenommen."}])
        self.assertEqual(feedback.state(item), "assigned")

    def test_eine_vermutung_geht_auch_vor_einer_neu_angelegten_massnahme(self):
        item = entry(created_measures=["M-080"], links=[
            {"measure": "M-080", "certainty": "confirmed", "why": "Als M-080 aufgenommen."},
            {"measure": "M-012", "certainty": "proposed", "why": "Grund.",
             "question": "Frage?"}])
        self.assertEqual(feedback.state(item), "to_decide")

    def test_eine_frage_von_uns_macht_den_punkt_klaerungsbeduerftig(self):
        """Der Fall vom 29.09.2026: eine Anforderung, von der nur der Titel
        mitkam, und eine Frage, die keine Zuordnung voraussetzt."""
        item = entry(links=[], clarification="Was soll das Quiz am Ende empfehlen?")
        self.assertEqual(feedback.state(item), "to_clarify")

    def test_die_klaerung_geht_vor_den_verknuepfungen(self):
        item = entry(clarification="Was ist gemeint?", links=[
            {"measure": "M-012", "certainty": "proposed", "why": "Grund.",
             "question": "Frage?"}])
        self.assertEqual(feedback.state(item), "to_clarify")

    def test_ausserhalb_geht_vor_der_klaerung(self):
        item = entry(links=[], out_of_scope="Andere Marke.", clarification="Was ist gemeint?")
        self.assertEqual(feedback.state(item), "out_of_scope")

    def test_eine_leere_klaerung_aendert_den_zustand_nicht(self):
        self.assertEqual(feedback.state(entry(links=[], clarification=" ")), "open")

    def test_ausserhalb_bleibt_ausserhalb_auch_mit_angelegter_massnahme(self):
        item = entry(links=[], created_measures=["M-080"], out_of_scope="Visuelles Redesign.")
        self.assertEqual(feedback.state(item), "out_of_scope")


class TestAnlegen(unittest.TestCase):
    def test_der_erste_eintrag_bekommt_die_erste_kennung(self):
        with tempfile.TemporaryDirectory() as tmp:
            neu = feedback.add(tmp, title="Suche funktioniert schlecht",
                               source="Aufgabenliste vom 17.09.2026, Mara Beispiel",
                               today=date(2026, 9, 17))
            self.assertEqual(neu["id"], "FB-001")
            self.assertEqual(neu["received"], "2026-09-17")
            self.assertEqual(neu["links"], [])

    def test_die_kennung_zaehlt_hoch_und_wird_nie_wiederverwendet(self):
        with tempfile.TemporaryDirectory() as tmp:
            feedback.add(tmp, title="Eins", source="Termin 17.09.2026, Tom Beispiel")
            zweiter = feedback.add(tmp, title="Zwei", source="Termin 17.09.2026, Tom Beispiel")
            self.assertEqual(zweiter["id"], "FB-002")

    def test_ein_eintrag_ohne_titel_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                feedback.add(tmp, title="  ", source="Termin 17.09.2026, Tom Beispiel")

    def test_ein_eintrag_ohne_quelle_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                feedback.add(tmp, title="Suche", source="")

    def test_angehaengt_wird_nie_ersetzt(self):
        with tempfile.TemporaryDirectory() as tmp:
            feedback.add(tmp, title="Eins", source="Termin 17.09.2026, Tom Beispiel")
            feedback.add(tmp, title="Zwei", source="Termin 17.09.2026, Tom Beispiel")
            self.assertEqual([e["title"] for e in feedback.load(tmp)], ["Eins", "Zwei"])


class TestQuelle(unittest.TestCase):
    """Die Angaben aus der Quelle stehen getrennt von unserer Einordnung.

    Bis zum 24.09.2026 kam von einer Zeile der Aufgabenliste nur unser
    übersetzter Titel mit; Bereich, Priorität, Notizen und Ziel fehlten, und
    das Portal hatte nichts, was es zeigen konnte.
    """

    def test_die_angaben_aus_der_quelle_kommen_mit(self):
        with tempfile.TemporaryDirectory() as tmp:
            neu = feedback.add(tmp, title="Suche funktioniert schlecht",
                               source="Aufgabenliste vom 17.09.2026, Mara Beispiel",
                               original={"title": "Search is not working",
                                         "section": "Product data", "priority": "High"})
            self.assertEqual(neu["original"], {"title": "Search is not working",
                                               "section": "Product data",
                                               "priority": "High"})
            self.assertEqual(feedback.load(tmp)[0]["original"], neu["original"])

    def test_leere_felder_der_quelle_fallen_weg(self):
        """Eine leere Spalte im Export ist keine Angabe. Stünde sie drin, zeigte
        das Portal eine Beschriftung ohne Wert."""
        with tempfile.TemporaryDirectory() as tmp:
            neu = feedback.add(tmp, title="Suche", source="Aufgabenliste, Mara Beispiel",
                               original={"title": "Search", "notes": "", "goal": "  "})
            self.assertEqual(neu["original"], {"title": "Search"})

    def test_ohne_angaben_aus_der_quelle_steht_kein_leeres_feld_da(self):
        with tempfile.TemporaryDirectory() as tmp:
            neu = feedback.add(tmp, title="Suche", source="Termin, Tom Beispiel",
                               original={"notes": ""})
            self.assertNotIn("original", neu)

    def test_ein_unbekanntes_feld_der_quelle_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as fehler:
                feedback.add(tmp, title="Suche", source="Aufgabenliste, Mara Beispiel",
                             original={"assignee": "Mara Beispiel"})
            self.assertIn("assignee", str(fehler.exception))

    def test_die_angaben_lassen_sich_nachtragen(self):
        """Der Weg für Punkte, die vor dem 24.09.2026 angelegt wurden."""
        with tempfile.TemporaryDirectory() as tmp:
            feedback.add(tmp, title="Suche", source="Aufgabenliste, Mara Beispiel")
            item = feedback.set_original(tmp, "FB-001", {"title": "Search", "shop": "All"})
            self.assertEqual(item["original"], {"title": "Search", "shop": "All"})
            self.assertEqual(feedback.load(tmp)[0]["original"], {"title": "Search", "shop": "All"})

    def test_nachtragen_ohne_angaben_entfernt_das_feld(self):
        with tempfile.TemporaryDirectory() as tmp:
            feedback.add(tmp, title="Suche", source="Aufgabenliste, Mara Beispiel",
                         original={"title": "Search"})
            item = feedback.set_original(tmp, "FB-001", {"title": " "})
            self.assertNotIn("original", item)

    def test_nachtragen_bei_einem_unbekannten_punkt_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                feedback.set_original(tmp, "FB-099", {"title": "Search"})


class TestVerknuepfen(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ws = self.dir.name
        measures.save(Path(self.ws), backlog_with("M-001", "M-002"))
        feedback.add(self.ws, title="Trust slider", source="Aufgabenliste, Mara Beispiel")

    def tearDown(self):
        self.dir.cleanup()

    def test_eine_bestaetigte_verknuepfung_landet_im_eintrag(self):
        item = feedback.link(self.ws, "FB-001", "M-001", "confirmed",
                             why="Dieselbe Sache.")
        self.assertEqual(item["links"], [
            {"measure": "M-001", "certainty": "confirmed", "why": "Dieselbe Sache."}])

    def test_eine_vermutete_verknuepfung_traegt_ihre_frage(self):
        item = feedback.link(self.ws, "FB-001", "M-002", "proposed",
                             why="Ueberschneidet sich.", question="Welche Kategorien?")
        self.assertEqual(item["links"][0]["question"], "Welche Kategorien?")

    def test_eine_vermutung_ohne_frage_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            feedback.link(self.ws, "FB-001", "M-002", "proposed", why="Grund.")

    def test_eine_verknuepfung_ohne_grund_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="  ")

    def test_ein_punkt_kann_auf_mehrere_massnahmen_fallen(self):
        """Der Fall aus der Praxis: eine Kundenaufgabe trifft M-069 und M-067."""
        feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Header.")
        item = feedback.link(self.ws, "FB-001", "M-002", "confirmed", why="Produktseite.")
        self.assertEqual([l["measure"] for l in item["links"]], ["M-001", "M-002"])

    def test_dieselbe_massnahme_zweimal_ersetzt_statt_zu_doppeln(self):
        """Eine entschiedene Vermutung wird bestaetigt, nicht danebengelegt."""
        feedback.link(self.ws, "FB-001", "M-001", "proposed", why="Grund.", question="Frage?")
        item = feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Entschieden am 20.09.")
        self.assertEqual(len(item["links"]), 1)
        self.assertEqual(item["links"][0]["certainty"], "confirmed")
        self.assertNotIn("question", item["links"][0])

    def test_eine_unbekannte_massnahme_wird_abgelehnt(self):
        """Der Grund fuer die Kreuzpruefung: eine Verknuepfung auf eine
        Kennung, die es nicht gibt, ist im Portal ein toter Verweis."""
        with self.assertRaises(ValueError) as fehler:
            feedback.link(self.ws, "FB-001", "M-999", "confirmed", why="Grund.")
        self.assertIn("M-999", str(fehler.exception))

    def test_ein_unbekannter_punkt_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            feedback.link(self.ws, "FB-099", "M-001", "confirmed", why="Grund.")

    def test_was_ausserhalb_liegt_wird_nicht_verknuepft(self):
        feedback.mark_out_of_scope(self.ws, "FB-001", "Andere Marke, nicht dieser Shop.")
        with self.assertRaises(ValueError):
            feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Grund.")

    def test_eine_verknuepfung_laesst_sich_wieder_loesen(self):
        feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Grund.")
        item = feedback.unlink(self.ws, "FB-001", "M-001")
        self.assertEqual(item["links"], [])

    def test_der_geschriebene_stand_ist_der_gelesene(self):
        feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Grund.")
        self.assertEqual(feedback.load(self.ws)[0]["links"][0]["measure"], "M-001")

    def test_eine_aus_dem_punkt_angelegte_massnahme_steht_am_punkt(self):
        item = feedback.link(self.ws, "FB-001", "M-002", "confirmed",
                             why="Als M-002 aufgenommen.", created=True)
        self.assertEqual(item["created_measures"], ["M-002"])
        self.assertEqual(item["links"], [
            {"measure": "M-002", "certainty": "confirmed", "why": "Als M-002 aufgenommen."}])
        self.assertEqual(feedback.state(item), "created")

    def test_eine_bestehende_massnahme_steht_nicht_unter_den_angelegten(self):
        item = feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Grund.")
        self.assertNotIn("created_measures", item)

    def test_neu_angelegt_und_vermutet_zugleich_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            feedback.link(self.ws, "FB-001", "M-002", "proposed", why="Grund.",
                          question="Frage?", created=True)

    def test_ein_neuer_grund_behaelt_die_herkunft_der_massnahme(self):
        """Dass eine Maßnahme aus diesem Punkt entstand, ist eine Tatsache
        über ihre Herkunft. Wer nur den Grund nachschärft, darf sie nicht
        nebenbei verlieren."""
        feedback.link(self.ws, "FB-001", "M-002", "confirmed", why="Alt.", created=True)
        item = feedback.link(self.ws, "FB-001", "M-002", "confirmed", why="Neu.")
        self.assertEqual(item["created_measures"], ["M-002"])
        self.assertEqual(item["links"][0]["why"], "Neu.")

    def test_die_herkunft_laesst_sich_ausdruecklich_zuruecknehmen(self):
        feedback.link(self.ws, "FB-001", "M-002", "confirmed", why="Grund.", created=True)
        item = feedback.link(self.ws, "FB-001", "M-002", "confirmed", why="Grund.",
                             created=False)
        self.assertNotIn("created_measures", item)

    def test_die_herkunft_uebersteht_das_loesen_der_verknuepfung(self):
        """Der Fall vom 24.09.2026: FB-023 wurde aus dem Projekt genommen, die
        Verknüpfung auf M-080 gelöst. Hinge die Herkunft am Link, stünde M-080
        danach als gemessene Maßnahme aus dem Audit da."""
        feedback.link(self.ws, "FB-001", "M-002", "confirmed", why="Grund.", created=True)
        feedback.unlink(self.ws, "FB-001", "M-002")
        item = feedback.mark_out_of_scope(self.ws, "FB-001", "Visuelles Redesign.")
        self.assertEqual(item["created_measures"], ["M-002"])
        self.assertEqual(feedback.state(item), "out_of_scope")

    def test_die_herkunft_laesst_sich_ohne_verknuepfung_festhalten(self):
        feedback.mark_out_of_scope(self.ws, "FB-001", "Visuelles Redesign.")
        item = feedback.record_created(self.ws, "FB-001", "M-002")
        self.assertEqual(item["created_measures"], ["M-002"])
        again = feedback.record_created(self.ws, "FB-001", "M-002")
        self.assertEqual(again["created_measures"], ["M-002"])

    def test_die_herkunft_braucht_eine_bekannte_massnahme(self):
        with self.assertRaises(ValueError):
            feedback.record_created(self.ws, "FB-001", "M-999")


class TestAusserhalb(unittest.TestCase):
    def test_ein_punkt_ausserhalb_traegt_seinen_grund(self):
        with tempfile.TemporaryDirectory() as tmp:
            feedback.add(tmp, title="Zweitmarke an das Warenwirtschaftssystem anbinden",
                         source="Aufgabenliste, Mara Beispiel")
            item = feedback.mark_out_of_scope(tmp, "FB-001", "Andere Marke, Systemanbindung.")
            self.assertEqual(feedback.state(item), "out_of_scope")

    def test_ohne_grund_wird_der_punkt_nicht_ausgeschlossen(self):
        with tempfile.TemporaryDirectory() as tmp:
            feedback.add(tmp, title="Zweitmarke", source="Aufgabenliste, Mara Beispiel")
            with self.assertRaises(ValueError):
                feedback.mark_out_of_scope(tmp, "FB-001", "   ")

    def test_ein_verknuepfter_punkt_wird_nicht_ausgeschlossen(self):
        with tempfile.TemporaryDirectory() as tmp:
            measures.save(Path(tmp), backlog_with("M-001"))
            feedback.add(tmp, title="Trust slider", source="Aufgabenliste, Mara Beispiel")
            feedback.link(tmp, "FB-001", "M-001", "confirmed", why="Grund.")
            with self.assertRaises(ValueError):
                feedback.mark_out_of_scope(tmp, "FB-001", "Andere Marke.")


class TestKlaerung(unittest.TestCase):
    """Unsere offene Frage an den Kunden, was ein Punkt meint."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ws = self.dir.name
        measures.save(Path(self.ws), backlog_with("M-001"))
        feedback.add(self.ws, title="Interessen-Quiz", source="Aufgabenliste, Mara Beispiel")

    def tearDown(self):
        self.dir.cleanup()

    def test_die_frage_landet_am_punkt(self):
        item = feedback.set_clarification(self.ws, "FB-001", " Was soll das Quiz empfehlen? ")
        self.assertEqual(item["clarification"], "Was soll das Quiz empfehlen?")
        self.assertEqual(feedback.load(self.ws)[0]["clarification"],
                         "Was soll das Quiz empfehlen?")
        self.assertEqual(feedback.state(item), "to_clarify")

    def test_eine_neue_frage_ersetzt_die_alte(self):
        feedback.set_clarification(self.ws, "FB-001", "Alt?")
        item = feedback.set_clarification(self.ws, "FB-001", "Neu?")
        self.assertEqual(item["clarification"], "Neu?")

    def test_ohne_frage_wird_nichts_gesetzt(self):
        with self.assertRaises(ValueError):
            feedback.set_clarification(self.ws, "FB-001", "   ")
        self.assertNotIn("clarification", feedback.load(self.ws)[0])

    def test_ein_unbekannter_punkt_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            feedback.set_clarification(self.ws, "FB-099", "Frage?")

    def test_was_ausserhalb_liegt_bekommt_keine_frage(self):
        feedback.mark_out_of_scope(self.ws, "FB-001", "Andere Marke.")
        with self.assertRaises(ValueError):
            feedback.set_clarification(self.ws, "FB-001", "Frage?")

    def test_die_frage_laesst_sich_zuruecknehmen(self):
        feedback.link(self.ws, "FB-001", "M-001", "confirmed", why="Grund.")
        feedback.set_clarification(self.ws, "FB-001", "Frage?")
        item = feedback.clear_clarification(self.ws, "FB-001")
        self.assertNotIn("clarification", item)
        self.assertEqual(feedback.state(item), "assigned")
        self.assertNotIn("clarification", feedback.load(self.ws)[0])

    def test_ausschliessen_nimmt_die_frage_mit(self):
        feedback.set_clarification(self.ws, "FB-001", "Frage?")
        item = feedback.mark_out_of_scope(self.ws, "FB-001", "Andere Marke.")
        self.assertNotIn("clarification", item)
        self.assertEqual(feedback.validate(feedback.load(self.ws)), [])


class TestRueckweg(unittest.TestCase):
    def test_zu_einer_massnahme_finden_sich_alle_punkte(self):
        items = [
            entry(id="FB-001", links=[{"measure": "M-069", "certainty": "confirmed",
                                       "why": "Grund."}]),
            entry(id="FB-002", links=[{"measure": "M-069", "certainty": "proposed",
                                       "why": "Grund.", "question": "Frage?"}]),
            entry(id="FB-003", links=[{"measure": "M-012", "certainty": "confirmed",
                                       "why": "Grund."}]),
        ]
        treffer = feedback.for_measure(items, "M-069")
        self.assertEqual([e["id"] for e in treffer], ["FB-001", "FB-002"])

    def test_eine_massnahme_ohne_punkte_liefert_nichts(self):
        self.assertEqual(feedback.for_measure([entry()], "M-999"), [])


if __name__ == "__main__":
    unittest.main()
