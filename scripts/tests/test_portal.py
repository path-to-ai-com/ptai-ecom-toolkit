"""Zugänge aus dem Cockpit: Verweis, Antworten von Shopify, Config und Google-Weiche."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit import env, portal  # noqa: E402
import google_token  # noqa: E402

SETTINGS = {
    "brand": "beispielmarke", "shop": "eu", "name": "Beispielshop EU", "domain": "beispielshop.test",
    "shopify_store": "beispielshop.myshopify.com", "ga4_property_id": "123456", "gsc_site": "sc-domain:beispielshop.test",
    "google_ads_customer_id": None, "google_ads_login_customer_id": None,
    "sources": {"shopify": "connected", "ga4": "connected", "gsc": "connected"},
    "audit_request": {"status": "requested"},
}


def answer(status, payload):
    return status, json.dumps(payload).encode()


class TestVerweis(unittest.TestCase):
    def test_brand_und_shop_aus_dem_verweis(self):
        self.assertEqual(portal.parse_target("portal:beispielmarke/eu"), ("beispielmarke", "eu"))

    def test_ein_kaputter_verweis_ist_ein_fehler(self):
        for value in ("portal:beispielmarke", "portal:../x/eu", "secrets/google-sa.json", "portal:A/eu"):
            with self.subTest(value=value), self.assertRaises(portal.PortalError):
                portal.parse_target(value)


class TestShopifyAntwort(unittest.TestCase):
    def test_daten_kommen_ohne_huelle_zurueck_wie_bei_der_cli(self):
        data = portal.unwrap_shopify(*answer(200, {"data": {"shop": {"name": "Beispielshop"}}}))
        self.assertEqual(data, {"shop": {"name": "Beispielshop"}})

    def test_drosselung_ist_ein_fehler_und_kein_leeres_ergebnis(self):
        payload = {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
        with self.assertRaisesRegex(portal.PortalError, "gedrosselt"):
            portal.unwrap_shopify(*answer(200, payload))

    def test_nicht_verbunden_bricht_ab(self):
        with self.assertRaisesRegex(portal.PortalError, "nicht verbunden"):
            portal.unwrap_shopify(*answer(409, {"error": "not_connected", "source": "shopify", "status": "missing"}))

    def test_antwort_ohne_daten_oder_ohne_json_ist_ein_fehler(self):
        with self.assertRaises(portal.PortalError):
            portal.unwrap_shopify(*answer(200, {"data": None}))
        with self.assertRaises(portal.PortalError):
            portal.unwrap_shopify(502, b"<html>")


class TestConfig(unittest.TestCase):
    def test_das_cockpit_traegt_seine_felder_ein_und_laesst_den_rest_stehen(self):
        before = {"brand": "Beispielmarke", "market": "DE", "cwv_urls": ["https://x.test/"], "sources": {"geo": False}}
        merged = portal.merge_config(before, SETTINGS)
        self.assertEqual(merged["market"], "DE")
        self.assertEqual(merged["cwv_urls"], ["https://x.test/"])
        self.assertEqual(merged["portal"], {"brand": "beispielmarke", "shop": "eu"})
        self.assertEqual(merged["shopify_store"], "beispielshop.myshopify.com")
        self.assertEqual(merged["ga4_property_id"], "123456")
        self.assertEqual(merged["sources"], {"geo": False, "shopify": True, "ga4": True, "gsc": True, "ads": False})

    def test_setup_schreibt_config_und_verweis_ohne_geheimnis(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / ".env").write_text("PTAI_GOOGLE_CREDENTIALS=secrets/google-sa.json\nANDERES=1\n", encoding="utf-8")
            with mock.patch.object(portal, "shop_settings", return_value=SETTINGS):
                path = portal.setup("beispielmarke", "eu", ws)
            config = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(config["portal"]["shop"], "eu")
            lines = (ws / ".env").read_text(encoding="utf-8").splitlines()
            self.assertIn("ANDERES=1", lines)
            self.assertIn("PTAI_GOOGLE_CREDENTIALS=portal:beispielmarke/eu", lines)
            self.assertEqual(sum(line.startswith("PTAI_GOOGLE_CREDENTIALS") for line in lines), 1)
            self.assertEqual(portal.config_target(ws), ("beispielmarke", "eu"))

    def test_ohne_portal_block_weiss_shopify_execute_nicht_wohin(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "reporting").mkdir()
            (Path(tmp) / "reporting" / "config.json").write_text('{"brand": "x"}', encoding="utf-8")
            with self.assertRaisesRegex(portal.PortalError, "portal"):
                portal.config_target(tmp)


class TestGoogleWeiche(unittest.TestCase):
    def test_ein_verweis_holt_den_zugang_beim_cockpit_fuer_die_richtige_quelle(self):
        calls = []

        def fake(method, brand, shop, path="", body=None, workspace="."):
            calls.append((method, brand, shop, path, body["source"]))
            return answer(200, {"access_token": "ya29.kurzlebig", "expires_in": 3599})

        with mock.patch.object(portal, "_request", side_effect=fake):
            token = google_token.get_access_token("portal:beispielmarke/eu", "webmasters")
        self.assertEqual(token, "ya29.kurzlebig")
        self.assertEqual(calls, [("POST", "beispielmarke", "eu", "/token", "gsc")])

    def test_lehnt_das_cockpit_ab_gibt_es_keinen_rueckfall(self):
        refusal = answer(409, {"error": "not_connected", "source": "ga4", "status": "broken"})
        with mock.patch.object(portal, "_request", return_value=refusal), \
                self.assertRaisesRegex(portal.PortalError, "not_connected"):
            google_token.get_access_token("portal:beispielmarke/eu", "analytics")


class TestAnmeldung(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._central = env.CENTRAL
        env.CENTRAL = Path(self.tmp.name) / "zentral.env"
        self.addCleanup(lambda: setattr(env, "CENTRAL", self._central))
        for name in portal.ENV_NAMES:
            self.addCleanup(os.environ.pop, name, None)
            os.environ.pop(name, None)

    def test_ohne_adresse_und_token_bricht_der_abruf_ab(self):
        with self.assertRaisesRegex(portal.PortalError, "PTAI_PORTAL_URL"):
            portal.shop_settings("beispielmarke", "eu", self.tmp.name)

    def test_ein_unbekannter_stand_wird_nicht_gesendet(self):
        with mock.patch.object(portal, "_request") as request, self.assertRaises(portal.PortalError):
            portal.report_status("beispielmarke", "eu", "veroeffentlicht")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
