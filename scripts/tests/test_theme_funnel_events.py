"""Datenschicht je GA4-Property: Durchlauf alt gegen neu am Handy mit langsamer Verbindung, Echtzeit nach dem Launch.

Anlass vom 11.11.2026: `add_to_cart` fehlte nach dem Launch in einer GA4-Property, weil Safari einen
Abruf von `/cart.js` beim Seitenwechsel verwarf. Kein Test geht ins Netz: Durchläufe liegen als Dateien im
Temp-Workspace, GA4 und der Shop sind gestellt.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "browser"))

import walk_checkout  # noqa: E402
from tests import test_theme_launch_check as base  # noqa: E402
from tests import test_theme_launch_check_after as after_base  # noqa: E402
from tests import visual_compare_support as vcs  # noqa: E402
from theme import funnel_events as fe  # noqa: E402
from theme import launch_check as lc  # noqa: E402

OLD, NEW = "000000000000", "111111111111"
SECOND = "G-BEISPIEL02"


def lost_add_to_cart(theme: str) -> dict:
    """Der Fall vom 11.11.2026: add_to_cart kommt nicht an, der Abruf des Warenkorbs bricht ab."""
    return vcs.walk(theme, events=[(vcs.GA4, "view_item", "product"), (vcs.GA4, "begin_checkout", "checkout")],
                    aborted=True)


class TestAufrufeImDurchlauf(unittest.TestCase):
    def test_gebuendelte_ereignisse_und_eigene_subdomain(self):
        requests = [
            {"url": "https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL01", "status": 204,
             "post_data": "en=view_item&ep.x=1\nen=scroll", "stage": "product"},
            {"url": "https://sst.beispielshop.example/g/collect?v=2&tid=g-beispiel02&en=add_to_cart", "status": 200,
             "stage": "cart"},
            {"url": "https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL01&en=add_to_cart",
             "status": None, "failure": "cancelled", "stage": "add_to_cart"},
            {"url": "https://www.googletagmanager.com/gtag/js?id=G-BEISPIEL01", "status": 200, "stage": "product"}]
        hits = fe.ga4_events(requests)
        self.assertEqual([(h["tid"], h["en"], h["delivered"]) for h in hits],
                         [("G-BEISPIEL01", "view_item", True), ("G-BEISPIEL01", "scroll", True),
                          ("G-BEISPIEL02", "add_to_cart", True), ("G-BEISPIEL01", "add_to_cart", False)])

    def test_ereignis_zaehlt_nur_in_seinen_stufen_auch_auf_der_naechsten_seite(self):
        walk = vcs.walk(NEW, events=[(vcs.GA4, "add_to_cart", "cart"), (vcs.GA4, "view_item", "checkout"),
                                     (vcs.GA4, "begin_checkout", "checkout")])
        counts = fe.counts(walk)[vcs.GA4]
        self.assertEqual(counts["add_to_cart"]["delivered"], 1, "Meldung auf der nächsten Seite zählt")
        self.assertNotIn("view_item", counts, "view_item erst in der Kasse gehört nicht zur Produktseite")

    def test_abgebrochener_abruf_des_warenkorbs_ist_die_spur(self):
        self.assertEqual(fe.aborted_cart(lost_add_to_cart(NEW)), ["GET /cart.js (cancelled)"])


class TestAltGegenNeu(unittest.TestCase):
    def compare(self, old: dict, new: dict) -> dict:
        olds = {fe.condition(fe.profile(old)): (Path("old"), old, fe.profile(old))}
        news = {fe.condition(fe.profile(new)): (Path("new"), new, fe.profile(new))}
        return fe.compare(olds, news, OLD, NEW)

    def test_verlorenes_add_to_cart_am_handy_ist_ein_befund_mit_spur(self):
        result = self.compare(vcs.walk(OLD), lost_add_to_cart(NEW))
        self.assertTrue(result["mobile_slow"])
        status, evidence = fe.property_verdict(result["properties"][vcs.GA4], result["mobile_slow"])
        self.assertEqual(status, "missing")
        self.assertIn("add_to_cart fehlt (alt 1, neu 0)", evidence)
        self.assertIn("Handy (Safari/WebKit, langsam, 800 ms)", evidence)
        self.assertIn("GET /cart.js (cancelled)", evidence)

    def test_gleiche_ereignisse_sind_erfuellt(self):
        result = self.compare(vcs.walk(OLD), vcs.walk(NEW))
        self.assertEqual(fe.property_verdict(result["properties"][vcs.GA4], True)[0], "ok")

    def test_nur_am_rechner_reicht_nicht(self):
        result = self.compare(vcs.walk(OLD, device="desktop", latency=0), vcs.walk(NEW, device="desktop", latency=0))
        self.assertFalse(result["mobile_slow"])
        status, evidence = fe.property_verdict(result["properties"][vcs.GA4], result["mobile_slow"])
        self.assertEqual(status, "blocked")
        self.assertIn("kein gültiger Durchlauf am Handy mit langsamer Verbindung", evidence)

    def test_property_nur_aus_der_kasse_bleibt_ohne_erwartung(self):
        # Eine Property, die alt keines der drei Ereignisse bekam, wird im Durchlauf nicht erwartet.
        result = self.compare(vcs.walk(OLD), vcs.walk(NEW))
        self.assertNotIn(SECOND, result["properties"])

    def test_ungueltige_durchlaeufe_zaehlen_nicht(self):
        cases = {"Einwilligung nicht erteilt (declined)": vcs.walk(NEW, consent="declined"),
                 "gedrosselt": vcs.walk(NEW, throttle={"reason": "Seite antwortet HTTP 429"}),
                 "In den Warenkorb gescheitert": vcs.walk(NEW, add_ok=False),
                 "zeigt Theme 222222222222": vcs.walk("222222222222")}
        for reason, walk in cases.items():
            with self.subTest(reason=reason):
                result = self.compare(vcs.walk(OLD), walk)
                self.assertFalse(result["mobile_slow"])
                self.assertIn(reason, " ".join(result["blocked"]))

    def test_ohne_durchlauf_des_alten_themes_kein_vergleich(self):
        new = vcs.walk(NEW)
        result = fe.compare({}, {fe.condition(fe.profile(new)): (Path("n"), new, fe.profile(new))}, OLD, NEW)
        self.assertIn("kein Durchlauf des alten Themes", result["blocked"][0])


class TestDurchlaeufeFinden(unittest.TestCase):
    def test_juengster_je_theme_und_bedingung_alte_fallen_weg(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            now = datetime.now(timezone.utc)
            vcs.write_walk(ws, "new-a", vcs.walk(NEW, started_at=(now - timedelta(hours=2)).isoformat()))
            vcs.write_walk(ws, "new-b", lost_add_to_cart(NEW) | {"started_at": now.isoformat()}, day="2026-11-12")
            vcs.write_walk(ws, "new-old", vcs.walk(NEW, started_at=(now - timedelta(days=9)).isoformat()), day="x")
            picked = fe.pick(fe.find_walks(ws), NEW)
            self.assertEqual(list(picked), [("mobile", True)])
            self.assertEqual(picked[("mobile", True)][0].parent.name, "new-b")


class TestGateG4(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        self.config = {"theme_migration": {"live_theme_id": vcs.LIVE, "draft_theme_id": vcs.DRAFT}}

    def test_ohne_durchlauf_haelt_g4_an_und_nennt_die_aufrufe(self):
        problems = fe.gate_problems(self.ws, self.config)
        self.assertEqual(len(problems), 1)
        self.assertIn("--device mobile --latency 800", problems[0])
        self.assertIn(f"--theme {vcs.DRAFT}", problems[0])

    def test_verlorenes_ereignis_haelt_g4_an(self):
        vcs.write_walk(self.ws, "old-mobile-slow", vcs.walk(vcs.LIVE))
        vcs.write_walk(self.ws, "new-mobile-slow", lost_add_to_cart(vcs.DRAFT))
        problems = fe.gate_problems(self.ws, self.config)
        self.assertEqual(problems, [f"Datenschicht: im Entwurf fehlen Ereignisse je GA4-Property: {vcs.GA4} "
                                    "add_to_cart (Handy (Safari/WebKit, langsam, 800 ms))"])

    def test_gleiche_ereignisse_lassen_g4_durch(self):
        vcs.complete_datalayer(self.ws)
        self.assertEqual(fe.gate_problems(self.ws, self.config), [])


class TestLaunchCheckVorher(base.Base):
    def test_ohne_durchlauf_nicht_pruefbar(self):
        _, report = self.run_check()
        check = self.by_id(report)["funnel-events"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("walk_checkout.py --headless --device mobile", check["action"])

    def test_verlorenes_add_to_cart_ist_ein_befund_je_property(self):
        vcs.write_walk(self.ws, "old-mobile-slow", vcs.walk(OLD))
        vcs.write_walk(self.ws, "new-mobile-slow", lost_add_to_cart(NEW))
        _, report = self.run_check()
        check = self.by_id(report)["funnel-ga4-g-beispiel01"]
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("add_to_cart fehlt", check["evidence"])
        self.assertEqual(report["recommendation"], "no_go")


class FakeRealtime:
    def __init__(self, counts=None, error=None):
        self.counts, self.error, self.calls = counts or {}, error, []

    def realtime_events(self, names, minutes=29):
        self.calls.append(list(names))
        if self.error:
            raise RuntimeError(self.error)
        return {n: self.counts.get(n, 0) for n in names}


class TestNachDemLaunch(after_base.AfterBase):
    def set_properties(self, props: dict) -> None:
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        config["theme_migration"]["ga4_properties"] = props
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config))

    def after_with(self, readers: dict):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            lc.main(["--workspace", str(self.ws), "--run-id", after_base.RUN, "--after", "--live-theme-id", OLD],
                    transport=self.shop, fetch=self.fetch, sleep=lambda s: None, ga4=self.ga4, ga4_props=readers)
        report = json.loads((self.ws / "reporting" / "runs" / after_base.RUN / "launch-check-after.json").read_text())
        return self.by_id(report)

    def test_durchlauf_auf_dem_veroeffentlichten_theme_gegen_das_rueckfall_theme(self):
        folder = self.ws / "reporting" / "runs" / after_base.RUN / "events"
        for name, data in (("old-mobile-slow", vcs.walk(OLD)), ("new-mobile-slow", lost_add_to_cart(NEW))):
            (folder / name).mkdir(parents=True)
            (folder / name / "walk.json").write_text(json.dumps(data))
        checks, _ = self.after()
        self.assertEqual(checks["funnel-ga4-g-beispiel01-after"]["status"], lc.MISSING)

    def test_ohne_property_ids_nicht_pruefbar(self):
        checks, _ = self.after()
        self.assertEqual(checks["realtime-ga4"]["status"], lc.BLOCKED)
        self.assertIn("ga4_properties", checks["realtime-ga4"]["action"])

    def test_echtzeit_ohne_add_to_cart_gegen_littledata_ist_ein_befund(self):
        self.set_properties({"G-LITTLEDATA1": {"property_id": "100", "via": "Littledata"},
                             vcs.GA4: {"property_id": "200"}})
        now = datetime.now(timezone.utc)
        self.shop.orders = [{"id": f"gid://shopify/Order/{i}", "createdAt": now.isoformat()} for i in range(6)]
        reference = FakeRealtime({"page_view": 400, "view_item": 120, "add_to_cart": 30, "begin_checkout": 12,
                                  "purchase": 6})
        client = FakeRealtime({"page_view": 200, "view_item": 60, "add_to_cart": 0, "begin_checkout": 6,
                               "purchase": 3})
        checks = self.after_with({"100": reference, "200": client})
        own = checks["realtime-ga4-g-beispiel01"]
        self.assertEqual(own["status"], lc.MISSING, own["evidence"])
        self.assertIn("keine add_to_cart", own["evidence"])
        self.assertIn("normiert über page_view (Anteil 0.50)", own["evidence"])
        ref = checks["realtime-ga4-g-littledata1"]
        self.assertEqual(ref["status"], lc.OK, ref["evidence"])
        self.assertIn("purchase 6 (Bestellungen 6)", ref["evidence"])
        self.assertIn("Referenz", ref["title"])

    def test_property_ohne_zugang_ist_nicht_pruefbar(self):
        self.set_properties({vcs.GA4: {"property_id": "200"}})
        checks = self.after_with({})
        self.assertEqual(checks["realtime-ga4-g-beispiel01"]["status"], lc.BLOCKED)
        self.assertIn("kein Zugang zu Property 200", checks["realtime-ga4-g-beispiel01"]["evidence"])


class TestEchtzeitUrteil(unittest.TestCase):
    REF = {"page_view": 100, "view_item": 40, "add_to_cart": 12, "begin_checkout": 6, "purchase": 2}

    def test_deutlich_weniger_als_erwartet_ist_eine_frage(self):
        status, _, low = fe.realtime_verdict({"page_view": 100, "view_item": 40, "add_to_cart": 4,
                                              "begin_checkout": 6, "purchase": 2}, self.REF, None)
        self.assertEqual(status, "manual")
        self.assertEqual(low, ["add_to_cart 4 statt etwa 12"])

    def test_zu_wenig_verkehr_ist_nicht_pruefbar(self):
        status, evidence, _ = fe.realtime_verdict({"page_view": 3}, {"page_view": 4, "view_item": 2}, 1)
        self.assertEqual(status, "blocked")
        self.assertIn("zu wenig Verkehr", evidence)

    def test_ohne_referenz_nur_kauf_gegen_bestellungen(self):
        status, evidence, _ = fe.realtime_verdict({"purchase": 0}, None, 7)
        self.assertEqual(status, "missing")
        self.assertIn("keine purchase", evidence)


class TestLangsameVerbindung(unittest.TestCase):
    def test_init_skript_verzoegert_nur_die_eigene_herkunft(self):
        script = walk_checkout.latency_script(800)
        self.assertIn("const delay = 800;", script)
        self.assertIn("location.origin", script)
        self.assertIsNone(walk_checkout.latency_script(0))


if __name__ == "__main__":
    unittest.main()
