"""Der Wochenpuls: Band, Meldungen und pulse.json."""
import unittest
from datetime import date, datetime

from audit import pulse

STEADY = [100, 103, 99, 102, 98, 101, 104, 100, 102]  # neun Wochen, acht Veränderungen


class TestBand(unittest.TestCase):
    def test_vor_der_achten_woche_gibt_es_kein_band(self):
        self.assertIsNone(pulse.band([100, 101, 102]))

    def test_das_band_ist_die_spanne_der_letzten_acht_veraenderungen(self):
        lo, hi = pulse.band(STEADY)
        self.assertAlmostEqual(lo, -3.92, places=2)
        self.assertAlmostEqual(hi, 3.06, places=2)

    def test_eine_woche_ohne_wert_verengt_das_band_nicht(self):
        self.assertEqual(pulse.week_changes([100, None, 110]), [])


class TestClassify(unittest.TestCase):
    def test_im_rahmen(self):
        row = pulse.classify_kpi("revenue", 104, 102, STEADY)
        self.assertEqual(row["state"], "in_range")

    def test_auffaellig_ausserhalb_der_spanne(self):
        row = pulse.classify_kpi("gsc_clicks", 120, 102, STEADY)
        self.assertEqual(row["state"], "outside")
        self.assertEqual(row["change"], 17.6)

    def test_ohne_band_keine_einordnung(self):
        self.assertEqual(pulse.classify_kpi("orders", 120, 100, [90, 100])["state"], "no_band")

    def test_vorwoche_null_ist_nicht_berechenbar(self):
        self.assertEqual(pulse.classify_kpi("orders", 5, 0, STEADY)["state"], "not_computable")


class TestConnection(unittest.TestCase):
    NOW = datetime(2026, 10, 12, 6, 0)

    def test_eine_liefernde_quelle_meldet_nichts(self):
        self.assertEqual(pulse.connection_alerts(
            {"gsc": {"ok": True, "pulled_at": "2026-10-12T05:50"}}, self.NOW), [])

    def test_gescheiterte_quelle_meldet_mit_namen(self):
        [a] = pulse.connection_alerts(
            {"google_ads": {"ok": False, "pulled_at": None, "reason": "Token widerrufen."}}, self.NOW)
        self.assertEqual(a["title"], "Google Ads-Verbindung unterbrochen")
        self.assertIn("Token widerrufen.", a["text"])

    def test_aelter_als_36_stunden_gilt_als_unterbrochen(self):
        [a] = pulse.connection_alerts(
            {"ga4": {"ok": True, "pulled_at": "2026-10-10T12:00"}}, self.NOW)
        self.assertIn("10.10.2026", a["text"])


class TestCoverage(unittest.TestCase):
    HISTORY = [93, 95, 94, 96, 92, 95, 94, 93]

    def test_im_ueblichen_anteil_keine_meldung(self):
        self.assertIsNone(pulse.coverage_alert(94, 100, self.HISTORY))

    def test_luecke_wird_gemeldet(self):
        a = pulse.coverage_alert(71, 100, self.HISTORY)
        self.assertEqual(a["title"], "Google Analytics erfasst 71 % des Umsatzes")
        self.assertIn("92 bis 96 %", a["text"])

    def test_doppelte_erfassung_wird_gemeldet(self):
        self.assertIn("doppelt", pulse.coverage_alert(140, 100, self.HISTORY)["text"])

    def test_ohne_band_nur_unter_der_haelfte(self):
        self.assertIsNone(pulse.coverage_alert(80, 100, []))
        self.assertIsNotNone(pulse.coverage_alert(40, 100, []))


class TestRelated(unittest.TestCase):
    MEASURES = [
        {"id": "M-011", "title": "Kategorietexte Wanderschuhe", "target_metric": "gsc_clicks",
         "history": [{"status": "open", "date": "2026-09-01"},
                     {"status": "implemented", "date": "2026-09-29"}]},
        {"id": "M-012", "title": "Alt", "target_metric": "gsc_clicks",
         "history": [{"status": "implemented", "date": "2026-07-01"}]},
        {"id": "M-013", "title": "Andere Kennzahl", "target_metric": "revenue",
         "by_shop": {"eu": {"history": [{"status": "implemented", "date": "2026-10-08"}]}}},
    ]

    def test_nur_zeitnah_umgesetzte_mit_gleicher_kennzahl(self):
        found = pulse.related_measures("gsc_clicks", self.MEASURES, date(2026, 10, 11))
        self.assertEqual([m["id"] for m in found], ["M-011"])

    def test_format_v2_liest_den_verlauf_je_store(self):
        found = pulse.related_measures("revenue", self.MEASURES, date(2026, 10, 11))
        self.assertEqual([m["id"] for m in found], ["M-013"])


class TestBuild(unittest.TestCase):
    def test_pulse_json(self):
        data = pulse.build(
            week_start=date(2026, 10, 5),
            kpis={"revenue": {"value": 104, "previous": 102, "history": STEADY, "source": "Shopify"},
                  "gsc_clicks": {"value": 120, "previous": 102, "history": STEADY,
                                 "source": "Search Console"}},
            sources={"google_ads": {"ok": False, "pulled_at": None, "reason": None}},
            measures=TestRelated.MEASURES, now=datetime(2026, 10, 12, 6, 0),
            labels={"gsc_clicks": "Klicks aus Google"})
        self.assertEqual(data["week"], "2026-W41")
        self.assertEqual(data["period"], {"start": "2026-10-05", "end": "2026-10-11"})
        self.assertEqual([a["kind"] for a in data["alerts"]], ["connection", "kpi"])
        kpi = data["alerts"][1]
        self.assertEqual(kpi["title"], "Klicks aus Google +18 % zur Vorwoche")
        self.assertEqual(kpi["related"][0]["id"], "M-011")

    def test_ohne_meldung_ist_die_liste_leer(self):
        data = pulse.build(week_start=date(2026, 10, 5),
                           kpis={"revenue": {"value": 104, "previous": 102, "history": STEADY}},
                           sources={}, measures=[], now=datetime(2026, 10, 12, 6, 0))
        self.assertEqual(data["alerts"], [])


if __name__ == "__main__":
    unittest.main()
