"""Prüfläufe gegen den Live-Shop drosseln, und eine abgelöste Consent-App nach dem Launch wirklich entfernen.

Nachtrag vom 11.11.2026: Shopify antwortete im Test mit HTTP 429, Horizons Nachladen scheiterte, und das
sah aus wie ein Fehler des Shops. Eine abgelöste Consent-App trug sich beim Veröffentlichen wieder ein und
lud ein Skript aus Shopify Files; deaktiviert war sie, deinstalliert nicht. Kein Test geht ins Netz.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "browser"))

import common  # noqa: E402
import compose  # noqa: E402
from tests import test_theme_launch_check as base  # noqa: E402
from tests import test_theme_launch_check_after as after_base  # noqa: E402
from tests import test_theme_launch_check_guards as guards  # noqa: E402
from tests import theme_fake_shop as fake  # noqa: E402
from tests import visual_compare_support as vcs  # noqa: E402
from theme import launch_check as lc  # noqa: E402
from theme import visual_compare as vc  # noqa: E402

BASE = "https://beispielshop.example"
FILES_JS = f"{BASE}/cdn/shop/files/beispielconsent-rules.js?v=1700000000"


class TestDrosselungErkennen(unittest.TestCase):
    def test_drei_zeichen_je_fuer_sich(self):
        self.assertIn("Seite antwortet HTTP 429", common.throttle_signal(429, "Beispielshop", 0)["reason"])
        self.assertIn("Warteseite „Nur einen Moment…“", common.throttle_signal(200, "Nur einen Moment…", 0)["reason"])
        signal = common.throttle_signal(200, "Beispielshop", 3)
        self.assertEqual(signal["requests_429"], 3)
        self.assertIn("kein Fehler des Shops", signal["reason"])
        self.assertIsNone(common.throttle_signal(200, "Beispielshop", 0))

    def test_nur_anfragen_an_den_shop_zaehlen(self):
        requests = [{"url": f"{BASE}/?section_id=header", "status": 429},
                    {"url": "https://www.beispielshop.example/cart.js", "status": 429},
                    {"url": "https://beispiel.myshopify.com/x", "status": 429},
                    {"url": "https://fremd.example/pixel", "status": 429},
                    {"url": f"{BASE}/", "status": 200}]
        self.assertEqual(common.count_429(requests, BASE), 3)

    def test_gedrosselt_geht_vor_falschem_theme(self):
        result = common.mark_throttled({"state": "wrong_theme"}, common.throttle_signal(429, None, 0))
        self.assertEqual(result["state"], common.THROTTLED)
        self.assertEqual(common.mark_throttled({"state": "ok"}, None)["state"], "ok")


class FakeClock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 2))
        self.now += seconds


class TestTempo(unittest.TestCase):
    def test_abstand_zwischen_seitenaufrufen_und_pause_nach_drosselung(self):
        clock = FakeClock()
        pacer = common.Pacer(pace=3, cooldown=60, clock=clock.clock, sleep=clock.sleep)
        pacer.wait()
        pacer.wait()
        self.assertEqual(clock.slept, [3.0])
        pacer.throttled()
        pacer.wait()
        self.assertEqual(clock.slept[-1], 60.0)
        self.assertEqual(pacer.pace, 6.0)
        for _ in range(5):
            pacer.throttled()
        self.assertEqual(pacer.pace, common.MAX_PACE_SECONDS)

    def test_zusammenfassung_nennt_die_drosselung(self):
        self.assertIsNone(common.throttled_summary([{"state": "ok"}]))
        self.assertIn("kein Fehler des Shops", common.throttled_summary([{"state": "throttled"}]))


class TestDrosselungImErgebnis(unittest.TestCase):
    def test_bildvergleich_zaehlt_die_aufnahme_nicht_und_nennt_den_grund(self):
        shot = vcs.shot("2", "desktop", state="throttled", throttle={"reason": "Seite antwortet HTTP 429"})
        self.assertIn("von Shopify gedrosselt (HTTP 429), kein Fehler des Shops", vc.shot_problem(shot, "desktop", "2"))

    def test_vergleichsseite_markiert_gedrosselt(self):
        shot = vcs.shot("2", "desktop", state="throttled", throttle={"reason": "Seite antwortet HTTP 429"})
        html = compose.figure("b", shot, "2", Path("."), Path("."))
        self.assertIn("Gedrosselt (HTTP 429), kein Fehler des Shops", html)
        self.assertIn("Seite antwortet HTTP 429", html)


class TestDrosselungImLaunchCheck(base.Base):
    def test_gedrosselter_mitschnitt_ist_nicht_pruefbar_statt_fehlend(self):
        ga4 = "https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL01&en=page_view"
        old = guards.run("home", [guards.request(ga4)])
        new = guards.run("home", [])
        new.update(state="throttled", throttle={"reason": "Seite antwortet HTTP 429"})
        guards.write_capture(self.ws, "old", [old])
        guards.write_capture(self.ws, "new", [new])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-hosts"]
        self.assertEqual(check["status"], lc.BLOCKED, check["evidence"])
        self.assertIn("von Shopify gedrosselt (HTTP 429), kein Fehler des Shops", check["evidence"])
        self.assertIn("--parallel 1 --pace 10", check["action"])


class TestConsentAppNachDemLaunch(after_base.AfterBase):
    def setUp(self):
        super().setUp()
        self.write_apps([{"service_id": "google_analytics", "service_name": "Google Analytics 4"},
                         {"service_id": "beispielconsent", "service_name": "Beispielconsent CMP",
                          "category": "consent", "decision": "replace", "decided_by": "Beispiel Person"},
                         {"service_id": "cookiefirst", "service_name": "CookieFirst", "category": "consent",
                          "decision": "keep"}])
        self.files_status = 404

    def fetch(self, url):
        if "/cdn/shop/files/" in url:
            self.fetched.append(url)
            return self.files_status, {}, ""
        return super().fetch(url)

    def captures(self, *, after_loads: bool):
        guards.write_capture(self.ws, "old", [guards.run("home", [guards.request(FILES_JS, kind="script")])])
        guards.write_capture(self.ws, "after", [guards.run("home", [guards.request(FILES_JS, kind="script")]
                                                             if after_loads else [])])

    def test_skript_aus_shopify_files_laedt_noch_und_datei_liegt_noch(self):
        self.captures(after_loads=True)
        self.files_status = 200
        checks, _ = self.after()
        check = checks["consent-app-after"]
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("lädt noch aus Shopify Files: beispielconsent-rules.js", check["evidence"])
        self.assertIn("Datei beispielconsent-rules.js liegt noch unter Inhalte > Dateien", check["evidence"])
        self.assertIn("deinstallieren (nicht nur deaktivieren)", check["action"])

    def test_zeile_im_live_layout_ist_ein_befund(self):
        self.captures(after_loads=False)
        line = "<script src=\"{{ 'beispielconsent-rules.js' | file_url }}\" defer></script>"
        self.shop.touch(fake.DRAFT_ID, "layout/theme.liquid", guards.LAYOUT.replace("</head>", f"{line}\n</head>").encode())
        checks, _ = self.after()
        self.assertEqual(checks["consent-app-after"]["status"], lc.MISSING)
        self.assertIn("Zeile im Live-Layout", checks["consent-app-after"]["evidence"])

    def test_alles_weg_bleibt_die_frage_nach_dem_deinstallieren(self):
        self.captures(after_loads=False)
        checks, _ = self.after()
        check = checks["consent-app-after"]
        self.assertEqual(check["status"], lc.MANUAL, check["evidence"])
        self.assertIn("Beispielconsent CMP im Admin unter Apps deinstalliert", check["question"])
        self.assertIn(FILES_JS, self.fetched)
        answers = self.ws / "reporting" / "launch-answers.json"
        answers.write_text(json.dumps({"answers": {"consent-app-after": {"status": "ok", "by": "Beispiel Team"}}}))
        checks, _ = self.after()
        self.assertEqual(checks["consent-app-after"]["status"], lc.OK)

    def test_ohne_abgeloeste_consent_app_trifft_es_nicht_zu(self):
        self.write_apps([{"service_id": "cookiefirst", "service_name": "CookieFirst", "category": "consent"}])
        checks, _ = self.after()
        self.assertEqual(checks["consent-app-after"]["status"], lc.NA)

    def test_files_skripte_von_theme_assets_unterscheiden(self):
        self.assertEqual(lc.files_name("https://cdn.shopify.com/s/files/1/0001/0002/files/beispiel.js?v=1"),
                         "beispiel.js")
        self.assertEqual(lc.files_name("https://beispielshop.example/cdn/shop/files/beispiel.js"), "beispiel.js")
        self.assertIsNone(lc.files_name("https://beispielshop.example/cdn/shop/t/12/assets/beispiel.js"))
        self.assertIsNone(lc.files_name("https://beispielshop.example/cdn/shop/files/bild.png"))


if __name__ == "__main__":
    unittest.main()
