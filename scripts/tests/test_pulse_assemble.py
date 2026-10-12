"""Vom Abruf der Skill zum Wochenpuls: Wochen bilden, Rückfall, Lauf schreiben."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from audit import pulse

WEEK = date(2026, 10, 5)  # Montag KW 41
NOW = datetime(2026, 10, 12, 6, 0)


def daily(weeks: int = 10, **per_day):
    """Tageszeilen über `weeks` volle Wochen bis Sonntag der KW 41."""
    first = WEEK - timedelta(weeks=weeks - 1)
    return [{"date": (first + timedelta(days=n)).isoformat(), **per_day}
            for n in range(weeks * 7)]


class TestWeeks(unittest.TestCase):
    def test_zehn_montage_die_puls_woche_zuletzt(self):
        starts = pulse.week_starts(WEEK)
        self.assertEqual(len(starts), 10)
        self.assertEqual(starts[-1], WEEK)
        self.assertEqual(starts[0], date(2026, 8, 3))

    def test_mit_zehn_wochen_steht_das_band(self):
        shop = {"daily": daily(total_sales=1000, net_sales=900, orders=10, sessions=500)}
        data = pulse.assemble(week_start=WEEK, shopify=shop, ga4=None, gsc=None,
                              measures=[], now=NOW)
        self.assertEqual({r["key"]: r["state"] for r in data["kpis"]}["revenue"], "in_range")

    def test_eine_angebrochene_woche_fehlt_statt_einzubrechen(self):
        rows = daily(orders=10)[:-1]  # Sonntag der Puls-Woche fehlt
        sums = pulse.weekly_sums(rows, "orders", pulse.week_starts(WEEK))
        self.assertEqual(sums[-2], 70)
        self.assertIsNone(sums[-1])


class TestAssemble(unittest.TestCase):
    def test_shopify_liefert_umsatz_bestellwert_und_conversion(self):
        shop = {"daily": daily(total_sales=1000, net_sales=900, orders=10, sessions=500)}
        data = pulse.assemble(week_start=WEEK, shopify=shop, ga4=None, gsc=None,
                              measures=[], now=NOW)
        rows = {r["key"]: r for r in data["kpis"]}
        self.assertEqual(rows["revenue"]["value"], 7000)
        self.assertEqual(rows["aov"]["value"], 100)
        self.assertEqual(rows["conversion_rate"]["value"], 2.0)
        self.assertEqual(rows["revenue"]["label"], "Umsatz")
        self.assertEqual(data["sources"]["shopify"]["ok"], True)

    def test_ohne_shopify_sitzungen_kommen_sie_aus_ga4(self):
        shop = {"daily": daily(total_sales=1000, net_sales=900, orders=10)}
        ga4 = {"by_week": [{"week": pulse.week_key(s), "sessions": 3500, "purchases": 70,
                            "purchase_revenue": 6000} for s in pulse.week_starts(WEEK)]}
        data = pulse.assemble(week_start=WEEK, shopify=shop, ga4=ga4, gsc=None,
                              measures=[], now=NOW)
        rows = {r["key"]: r for r in data["kpis"]}
        self.assertEqual(rows["sessions"]["source"], "Google Analytics")
        self.assertEqual(rows["conversion_rate"]["value"], 2.0)

    def test_fehlender_abruf_wird_zur_meldung(self):
        data = pulse.assemble(week_start=WEEK, shopify={"error": "ACCESS_DENIED"}, ga4=None,
                              gsc=None, measures=[], now=NOW)
        kinds = [(a["kind"], a["source"]) for a in data["alerts"]]
        self.assertIn(("connection", "shopify"), kinds)

    def test_luecke_in_ga4_wird_gemeldet(self):
        shop = {"daily": daily(total_sales=1000, net_sales=1000, orders=10, sessions=500)}
        weeks = pulse.week_starts(WEEK)
        ga4 = {"by_week": [{"week": pulse.week_key(s), "sessions": 3500, "purchases": 70,
                            "purchase_revenue": 6650 if s != WEEK else 5000} for s in weeks]}
        data = pulse.assemble(week_start=WEEK, shopify=shop, ga4=ga4, gsc=None,
                              measures=[], now=NOW)
        [cov] = [a for a in data["alerts"] if a["kind"] == "coverage"]
        self.assertEqual(cov["share"], 71.4)

    def test_andere_waehrung_in_ga4_keine_messabdeckung(self):
        shop = {"currency": "EUR", "daily": daily(total_sales=1000, net_sales=1000, orders=10, sessions=500)}
        ga4 = {"currency": "GBP", "by_week": [{"week": pulse.week_key(s), "sessions": 3500, "purchases": 70,
                                                "purchase_revenue": 3000} for s in pulse.week_starts(WEEK)]}
        data = pulse.assemble(week_start=WEEK, shopify=shop, ga4=ga4, gsc=None,
                              measures=[], now=NOW)
        self.assertFalse([a for a in data["alerts"] if a["kind"] == "coverage"])


class TestWriteRun(unittest.TestCase):
    def test_lauf_mit_kadenz_week_und_titel(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = pulse.assemble(week_start=WEEK, shopify=None, ga4=None, gsc=None,
                                  measures=[], now=NOW)
            run_dir = pulse.write_run(tmp, data, NOW)
            self.assertEqual(run_dir.name, "2026-10-12-week")
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["cadence"], "week")
            self.assertEqual(state["title"], "Wochenpuls KW 41")
            self.assertTrue((Path(run_dir) / "pulse.json").exists())


if __name__ == "__main__":
    unittest.main()
