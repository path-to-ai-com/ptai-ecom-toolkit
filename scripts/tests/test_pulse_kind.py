"""Der Wochenpuls als Lauf-Art, die sich selbst veröffentlicht."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from audit import measures, publish
from tests.test_publish import make_workspace


class PulseKind(unittest.TestCase):
    def test_die_kadenz_week_ist_der_wochenpuls(self):
        self.assertEqual(publish.run_kind("2026-10-13-week", {"cadence": "week"}),
                         ("pulse", "week"))

    def test_der_wochenpuls_ist_sofort_veroeffentlicht(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "2026-10-13-week"
            ws = make_workspace(Path(tmp), run_id)
            state = ws / "reporting" / "runs" / run_id / "state.json"
            state.write_text(json.dumps({"run_id": run_id, "cadence": "week"}), encoding="utf-8")
            out = publish.prepare(ws, run_id, Path(tmp) / "bucket", today=date(2026, 10, 13))
            self.assertTrue(out["released"])

    def test_ein_zweiter_puls_am_selben_tag_braucht_kein_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "2026-10-13-week"
            ws = make_workspace(Path(tmp), run_id)
            state = ws / "reporting" / "runs" / run_id / "state.json"
            state.write_text(json.dumps({"run_id": run_id, "cadence": "week"}), encoding="utf-8")
            bucket = Path(tmp) / "bucket"
            publish.prepare(ws, run_id, bucket, today=date(2026, 10, 13))
            out = publish.prepare(ws, run_id, bucket, today=date(2026, 10, 13))
            self.assertTrue(out["released"])

    def test_ein_audit_bleibt_unveroeffentlicht(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp), "2026-09-08-audit")
            out = publish.prepare(ws, "2026-09-08-audit", Path(tmp) / "bucket")
            self.assertFalse(out["released"])


class TargetMetric(unittest.TestCase):
    def test_die_zielkennzahl_steht_an_der_massnahme(self):
        backlog = measures.create(
            {"next_id": 1, "measures": []}, title="Kategorietexte", discipline="SEO",
            evidence="data/gsc.json", confidence="confirmed", leverage="high",
            effort="medium", target_metric="gsc_clicks", today=date(2026, 10, 11))
        self.assertEqual(backlog["measures"][0]["target_metric"], "gsc_clicks")

    def test_ohne_zielkennzahl_bleibt_das_feld_leer(self):
        backlog = measures.create(
            {"next_id": 1, "measures": []}, title="Impressum", discipline="Vertrauen",
            evidence="data/crawl.json", confidence="confirmed", leverage="low",
            effort="small", today=date(2026, 10, 11))
        self.assertIsNone(backlog["measures"][0]["target_metric"])


if __name__ == "__main__":
    unittest.main()
