"""Der Nachlauf einer Disziplin: Kennungen und verwaiste Maßnahmen."""
import unittest

from audit import rerun


def doc(*findings):
    return {"discipline": "sea", "findings": [
        {"id": fid, "statement": text} for fid, text in findings]}


PREVIOUS = doc(("SEA-01", "Kein Zugang zum Werbekonto"),
               ("SEA-02", "Ein eigenes Shopping-Angebot bei 1 von 4 Begriffen"))


class TestKennungen(unittest.TestCase):
    def test_ein_gebliebener_befund_behaelt_kennung_und_aussage(self):
        rerun.check_ids(PREVIOUS, doc(
            ("SEA-02", "Ein eigenes Shopping-Angebot bei 1 von 4 Begriffen"),
            ("SEA-03", "Der Rang begrenzt stärker als das Budget")))

    def test_neu_nummeriert_ab_01_scheitert(self):
        # Genau der Fall vom 02.10.2026: die neue Analyse zählte wieder ab 01,
        # und die Maßnahme zum fehlenden Zugang hätte auf einen fremden
        # Befund gezeigt.
        with self.assertRaises(ValueError) as caught:
            rerun.check_ids(PREVIOUS, doc(
                ("SEA-01", "Alle Käufe stammen aus einer Conversion-Aktion")))
        self.assertIn("SEA-01", str(caught.exception))

    def test_neue_kennung_vor_der_hoechsten_scheitert(self):
        with self.assertRaises(ValueError):
            rerun.check_ids(doc(("SEA-01", "a"), ("SEA-05", "b")),
                            doc(("SEA-03", "neu")))

    def test_doppelte_kennung_scheitert(self):
        with self.assertRaises(ValueError):
            rerun.check_ids(PREVIOUS, doc(("SEA-03", "a"), ("SEA-03", "b")))

    def test_ohne_vorige_fassung_ist_jede_kennung_neu(self):
        rerun.check_ids({}, doc(("SEA-01", "a")))


class TestAbgleich(unittest.TestCase):
    CURRENT = doc(("SEA-02", "Ein eigenes Shopping-Angebot bei 1 von 4 Begriffen"),
                  ("SEA-03", "Der Rang begrenzt stärker als das Budget"))

    def test_nur_neue_befunde_gehen_durch_create(self):
        self.assertEqual([f["id"] for f in rerun.new_findings(PREVIOUS, self.CURRENT)],
                         ["SEA-03"])

    def test_weggefallener_befund_meldet_seine_offene_massnahme(self):
        backlog = {"measures": [
            {"id": "M-041", "finding_ref": "SEA-01", "status": "open"},
            {"id": "M-042", "finding_ref": "SEA-02", "status": "open"}]}
        self.assertEqual(
            [m["id"] for m in rerun.orphaned_measures(backlog, PREVIOUS, self.CURRENT)],
            ["M-041"])

    def test_abgeschlossene_massnahme_verwaist_nicht(self):
        backlog = {"measures": [
            {"id": "M-041", "finding_ref": "SEA-01", "status": "implemented"}]}
        self.assertEqual(rerun.orphaned_measures(backlog, PREVIOUS, self.CURRENT), [])


class TestVerwaistJeStore(unittest.TestCase):
    """Spec 2026-10-08, Abschnitt 11: nur Befunde desselben Stores und Laufs."""

    def setUp(self):
        from tests import brand_support as bs
        self.backlog = bs.fixture()

    def test_der_nachlauf_in_uk_meldet_keine_massnahme_aus_eu(self):
        # CRO-03 fällt weg. In EU trägt M-001 denselben Kurznamen, aber aus
        # einem anderen Lauf; das ist ein anderer Befund.
        previous = doc(("CRO-02", "a"), ("CRO-03", "b"))
        orphans = rerun.orphaned_measures(self.backlog, previous, doc(("CRO-02", "a")),
                                          shop="uk", run_id="2026-11-12-audit")
        self.assertEqual(orphans, [])

    def test_der_nachlauf_in_uk_meldet_die_eigene(self):
        previous = doc(("CRO-02", "a"), ("TRU-04", "b"))
        orphans = rerun.orphaned_measures(self.backlog, previous, doc(),
                                          shop="uk", run_id="2026-11-12-audit")
        self.assertEqual([(m["id"], m["shop"]) for m in orphans],
                         [("M-001", "uk"), ("M-004", "uk")])

    def test_nur_der_lauf_des_befunds_zaehlt(self):
        previous = doc(("CNT-04", "a"))
        self.assertEqual(rerun.orphaned_measures(self.backlog, previous, doc(),
                                                 shop="eu", run_id="2026-10-15-report"), [])
        self.assertEqual([m["id"] for m in rerun.orphaned_measures(
            self.backlog, previous, doc(), shop="eu", run_id="2026-09-01-audit")], ["M-002"])

    def test_ohne_store_bricht_es_ab(self):
        with self.assertRaises(ValueError):
            rerun.orphaned_measures(self.backlog, doc(), doc())


if __name__ == "__main__":
    unittest.main()
