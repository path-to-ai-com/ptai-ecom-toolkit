"""Messziele und Tag Manager: Kennungen erkennen, Container auflösen, ohne Netz.

Ein Container wird nicht nach Kennungen durchsucht, sondern aufgelöst: die
Google-Ads-Kennung steht dort gern als nackte Zahl, ein Meta-Pixel in eigenem
HTML, und ein pausierter Tag oder einer ohne Auslöser sendet nie.
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import gtm, tracking_ids  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "theme" / "apps"


class TestKennungen(unittest.TestCase):
    def test_ga4_braucht_eine_ziffer(self):
        ids = [t["target_id"] for t in tracking_ids.find_targets("G-BEISPIEL01 G-STRINGS G-ABCDEF")]
        self.assertEqual(ids, ["G-BEISPIEL01"])

    def test_google_ads_mit_label_getrennt(self):
        self.assertEqual(tracking_ids.find_targets("send_to: 'AW-000000000/beispielLabel'"),
                         [{"target_id": "AW-000000000", "kind": "google_ads", "label": "beispielLabel"}])

    def test_uet_nur_im_umfeld_von_uet(self):
        self.assertEqual(tracking_ids.find_targets("var o = {ti: '12345'}"), [])
        self.assertEqual([t["target_id"] for t in tracking_ids.find_targets("window.uetq=[];o={ti:'12345'}")],
                         ["UET:12345"])

    def test_container_ist_kein_messziel(self):
        self.assertEqual(tracking_ids.find_targets("GTM-BEISP01"), [])
        self.assertEqual(tracking_ids.container_ids("x GTM-BEISP01 y GTM-BEISP01"), ["GTM-BEISP01"])

    def test_pixel_konfiguration_mit_nackter_kennung(self):
        targets = tracking_ids.config_targets({"pixel_id": "100000000000001", "pixel_type": "facebook_pixel"})
        self.assertEqual(targets, [{"target_id": "META:100000000000001", "kind": "meta"}])

    def test_events_je_ziel_aus_gtag_events(self):
        config = {"gtag_events": [{"type": "purchase", "action_label": ["G-BEISPIEL01", "AW-000000000/x1y2"]},
                                  {"type": "page_view", "action_label": ["G-BEISPIEL01"]}]}
        pairs = {event: [t["target_id"] for t in targets] for event, targets in tracking_ids.config_events(config)}
        self.assertEqual(pairs, {"purchase": ["G-BEISPIEL01", "AW-000000000"], "page_view": ["G-BEISPIEL01"]})

    def test_events_im_theme_code(self):
        code = "gtag('config', 'G-BEISPIEL01'); gtag('event', 'purchase'); fbq('track', 'AddToCart');"
        self.assertEqual(tracking_ids.code_events(code), ["AddToCart", "page_view", "purchase"])
        self.assertNotIn("page_view", tracking_ids.code_events("gtag('config', 'G-BEISPIEL01', {send_page_view: false})"))

    def test_ga4_bündelt_events_im_post(self):
        found = tracking_ids.request_targets("https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL01",
                                             "en=page_view&ep.a=1\nen=view_item&ep.b=2")
        self.assertEqual(found, [{"target_id": "G-BEISPIEL01", "kind": "ga4", "events": ["page_view", "view_item"]}])

    def test_google_ads_conversion_aus_dem_pfad(self):
        found = tracking_ids.request_targets("https://www.googleadservices.com/pagead/conversion/000000000/?label=abcd")
        self.assertEqual(found[0]["target_id"], "AW-000000000")
        self.assertEqual(found[0]["label"], "abcd")
        self.assertEqual(found[0]["events"], ["conversion"])

    def test_meta_und_uet_aus_der_adresse(self):
        meta = tracking_ids.request_targets("https://www.facebook.com/tr/?id=100000000000001&ev=PageView")
        self.assertEqual(meta, [{"target_id": "META:100000000000001", "kind": "meta", "events": ["PageView"]}])
        uet = tracking_ids.request_targets("https://bat.bing.com/action/0?ti=000000000&evt=pageLoad")
        self.assertEqual(uet[0]["target_id"], "UET:000000000")

    def test_senden_und_laden_unterscheiden(self):
        self.assertTrue(tracking_ids.sends_data("POST", "fetch", "https://x.example/c"))
        self.assertTrue(tracking_ids.sends_data("GET", "image", "https://x.example/p?id=1"))
        self.assertFalse(tracking_ids.sends_data("GET", "script", "https://x.example/s.js?id=1"))
        self.assertFalse(tracking_ids.sends_data("GET", "image", "https://x.example/logo.png"))


class TestContainer(unittest.TestCase):
    def setUp(self):
        self.result = gtm.resolve_file(str(FIXTURES / "gtm.js"))
        self.tags = {t["index"]: t for t in self.result["tags"]}

    def test_klammern_in_zeichenketten_zaehlen_nicht(self):
        text = 'x = {"a": "}{", "b": [1, {"c": "]"}]}; y'
        self.assertEqual(json.loads(gtm.extract_balanced(text, 4)), {"a": "}{", "b": [1, {"c": "]"}]})
        with self.assertRaises(ValueError):
            gtm.extract_balanced('{"offen": 1', 0)

    def test_keine_gtm_datei_ist_ein_fehler(self):
        with self.assertRaises(gtm.ContainerError):
            gtm.parse_container("console.log('kein Container');")

    def test_kennung_und_version(self):
        self.assertEqual(self.result["container_ids"], ["GTM-BEISP01"])
        self.assertEqual(self.result["version"], "7")
        self.assertEqual(self.result["summary"]["tags"], 7)

    def test_makros_werden_aufgeloest(self):
        self.assertEqual(self.tags[0]["params"]["tagId"], "G-BEISPIEL01")
        self.assertEqual(self.tags[1]["params"]["eventParameters"], [{"name": "value", "value": "dl:ecommerce.value"}])

    def test_google_ads_aus_nackter_zahl_mit_label(self):
        self.assertEqual(self.tags[2]["targets"],
                         [{"target_id": "AW-000000000", "kind": "google_ads", "label": "beispielLabel"}])
        self.assertEqual(self.tags[2]["service_id"], "google_ads")

    def test_uet_aus_tag_id(self):
        self.assertEqual(self.tags[3]["targets"], [{"target_id": "UET:000000000", "kind": "uet"}])

    def test_events_aus_den_ausloesern(self):
        self.assertEqual(self.tags[1]["events"], ["purchase"])
        self.assertEqual(self.tags[2]["events"], ["purchase"])
        self.assertIn("page_view", self.tags[0]["events"])

    def test_eigenes_html_mit_meta_pixel_und_sperre(self):
        tag = self.tags[4]
        self.assertIsNone(tag["service_id"])
        self.assertIn("connect.facebook.net", tag["hosts"])
        self.assertEqual([t["target_id"] for t in tag["targets"]], ["META:100000000000001"])
        self.assertIn("PageView", tag["events"])
        self.assertEqual(tag["consent"], ["ad_storage"])
        self.assertTrue(any("blocked_when" in trigger for trigger in tag["triggers"]))

    def test_pausiert_und_ohne_ausloeser(self):
        self.assertTrue(self.tags[5]["paused"])
        self.assertEqual(self.tags[5]["original_function"], "html")
        self.assertFalse(self.tags[6]["fires"])
        self.assertEqual(self.result["summary"]["without_trigger"], 1)

    def test_cli_schreibt_ergebnis(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gtm.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = gtm.main(["resolve", "--gtm", str(FIXTURES / "gtm.js"), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(buffer.getvalue())["tags"], 7)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["container_ids"], ["GTM-BEISP01"])
            bad = Path(tmp) / "kaputt.js"
            bad.write_text("nichts", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(gtm.main(["resolve", "--gtm", str(bad), "--out", str(out)]), 2)

    def test_aufgeloestes_json_wird_wieder_gelesen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gtm.json"
            path.write_text(json.dumps(self.result), encoding="utf-8")
            self.assertEqual(gtm.resolve_file(str(path))["summary"], self.result["summary"])


if __name__ == "__main__":
    unittest.main()
