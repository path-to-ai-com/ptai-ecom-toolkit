"""App-Inventar: die einzelnen Quellen ohne Netz und ohne Browser.

Geprüft wird, was aus dem ausgelieferten HTML (`webPixelsConfigList`,
`asyncLoad`), aus `settings_data.json` samt Kommentarkopf, aus den JSON-Vorlagen
und aus dem Theme-Code gelesen wird, und wie der Host-Katalog zuordnet.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import apps  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "theme" / "apps"
HTML = (FIXTURES / "html" / "home-desktop-1.html").read_text(encoding="utf-8")


class TestHtml(unittest.TestCase):
    def test_web_pixels_mit_konfiguration_und_kennung_als_text(self):
        pixels = apps.parse_web_pixels(HTML)
        self.assertEqual([p["id"] for p in pixels], ["1", "2", "3"])
        self.assertEqual(pixels[0]["api_client_id"], "1000001")
        self.assertEqual(pixels[0]["configuration"], {"pixel_id": "100000000000001", "pixel_type": "facebook_pixel"})
        self.assertEqual(pixels[2]["type"], "CUSTOM")
        self.assertIsNone(pixels[2]["api_client_id"])

    def test_fehlende_pixelliste_ist_none_und_nicht_leer(self):
        self.assertIsNone(apps.parse_web_pixels("<html><script>var Shopify = {};</script></html>"))
        self.assertEqual(apps.parse_web_pixels("x webPixelsConfigList: [], y"), [])

    def test_skript_tags_aus_async_load_mit_entschluesselten_zeichen(self):
        urls = apps.parse_async_load(HTML)
        self.assertEqual(urls, [
            "https://static.klaviyo.com/onsite/js/klaviyo.js?company_id=BSP123&shop=beispiel.myshopify.com",
            "https://scripts.unbekannt-app.example/loader.js?shop=beispiel.myshopify.com",
        ])
        self.assertIsNone(apps.parse_async_load("<html></html>"))

    def test_shop_domain_und_shopify_erkennung(self):
        self.assertEqual(apps.shop_domain(HTML), "beispiel.myshopify.com")
        self.assertTrue(apps.looks_like_shopify(HTML))
        self.assertFalse(apps.looks_like_shopify("<html><body>Fehlerseite</body></html>"))


class TestThemeDateien(unittest.TestCase):
    def test_kommentarkopf_vor_settings_data_wird_entfernt(self):
        text = "/*\n * IMPORTANT\n */\n{\"current\": {}}"
        self.assertEqual(json.loads(apps.strip_comment_header(text)), {"current": {}})
        self.assertEqual(apps.strip_comment_header('{"a": 1}'), '{"a": 1}')

    def test_embeds_mit_zustand_aus_der_sicherung(self):
        settings, problem = apps.load_settings_data(FIXTURES / "theme")
        self.assertIsNone(problem)
        embeds = {e["app_handle"]: e for e in apps.app_embeds(settings)}
        self.assertFalse(embeds["judge-me-reviews"]["disabled"])
        self.assertTrue(embeds["klaviyo-email-marketing-sms"]["disabled"])
        self.assertEqual(embeds["beispiel-upsell"]["settings"], {"tracking_id": "G-BEISPIEL02"})

    def test_current_als_name_eines_presets(self):
        settings = {"current": "Hell", "presets": {"Hell": {"blocks": {"1": {
            "type": "shopify://apps/beispiel/blocks/embed/00000000-0000-0000-0000-000000000009"}}}}}
        self.assertEqual([e["block"] for e in apps.app_embeds(settings)], ["embed"])

    def test_fehlende_settings_data_hat_einen_grund(self):
        settings, problem = apps.load_settings_data(FIXTURES / "html")
        self.assertIsNone(settings)
        self.assertIn("fehlt", problem)

    def test_app_block_erbt_deaktivierung_der_section(self):
        data = json.loads((FIXTURES / "theme" / "templates" / "page.alt.json").read_text(encoding="utf-8"))
        found = {b["block"]: b["disabled"] for b in apps.app_blocks_in(data, "templates/page.alt.json")}
        self.assertEqual(found, {"review_widget": True, "offer": True})

    def test_code_findet_fremde_adressen_aber_keine_kommentare(self):
        text = (FIXTURES / "theme" / "layout" / "theme.liquid").read_text(encoding="utf-8")
        found = apps.scan_code(text)
        hosts = {u["host"] for u in found["urls"]}
        self.assertIn("tracker.unbekannt.example", hosts)
        self.assertIn("www.googletagmanager.com", hosts)
        self.assertNotIn("window.location", hosts)
        self.assertEqual(found["containers"], ["GTM-BEISP01"])
        script = next(u for u in found["urls"] if u["host"] == "tracker.unbekannt.example")
        self.assertEqual((script["element"], script["line"]), ("script", 12))

    def test_protokollrelative_adresse_nur_in_einem_string(self):
        found = apps.scan_code("// cdn.kommentar.example\nvar a = '//cdn.beispiel-cdn.example/x.js';")
        self.assertEqual([u["host"] for u in found["urls"]], ["cdn.beispiel-cdn.example"])

    def test_proxy_link_im_theme_code(self):
        text = (FIXTURES / "theme" / "assets" / "theme.js").read_text(encoding="utf-8")
        self.assertEqual(apps.scan_code(text)["proxy_links"], ["/apps/beispiel-proxy"])


class TestHostKatalog(unittest.TestCase):
    catalog = apps.HostCatalog.load()

    def test_laengstes_muster_gewinnt(self):
        self.assertEqual(self.catalog.service_for("www.googletagmanager.com", "/gtag/js"), "google_tag")
        self.assertEqual(self.catalog.service_for("www.googletagmanager.com", "/gtm.js"), "google_tag_manager")
        self.assertEqual(self.catalog.service_for("www.google.com", "/pagead/1p-conversion/1/"), "google_ads")
        self.assertIsNone(self.catalog.service_for("www.google.com", "/search"))

    def test_unterdomain_trifft_aber_kein_namensvetter(self):
        self.assertEqual(self.catalog.service_for("static.klaviyo.com"), "klaviyo")
        self.assertIsNone(self.catalog.service_for("notklaviyo.com"))

    def test_unbekannter_host_bleibt_ohne_dienst(self):
        self.assertIsNone(self.catalog.service_for("tracker.unbekannt.example"))
        self.assertEqual(self.catalog.describe("unknown:tracker.unbekannt.example")["category"], "unknown")

    def test_shopify_ist_plattform_und_dokumentation_wird_ignoriert(self):
        self.assertTrue(self.catalog.is_platform(self.catalog.service_for("cdn.shopify.com")))
        self.assertTrue(self.catalog.ignored("schema.org"))

    def test_cookies_globals_und_app_handles(self):
        self.assertEqual(self.catalog.service_for_cookie("_ga_ABC"), "google_analytics")
        self.assertEqual(self.catalog.service_for_cookie("_gcl_au"), "google_ads")
        self.assertEqual(self.catalog.service_for_global("fbq"), "meta")
        self.assertEqual(self.catalog.service_for_handle("judge-me-reviews"), "judgeme")
        self.assertIsNone(self.catalog.service_for_cookie("beispiel_rest"))

    def test_app_titel_trifft_nur_am_anfang(self):
        self.assertEqual(self.catalog.service_for_name("Judge.me Product Reviews"), "judgeme")
        self.assertEqual(self.catalog.service_for_name("Klaviyo: Email Marketing & SMS"), "klaviyo")
        self.assertIsNone(self.catalog.service_for_name("Beispiel ERP Connector"))


if __name__ == "__main__":
    unittest.main()
