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


if __name__ == "__main__":
    unittest.main()
