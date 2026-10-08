"""Deckt die Search-Console-Property die Shop-Domain ab? Kein Test ruft eine API.

Neben der reinen Regel die drei Stellen, die sie anwenden: die Sperre in
`config.validate()`, `audit.portal setup` und `check` sowie `gsc_pull.py`.
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from audit import config, gsc_scope, portal  # noqa: E402

GSC_PULL = SCRIPTS.parent / "skills" / "pull-gsc" / "scripts" / "gsc_pull.py"

#: Ein Shop auf einer Subdomain, dem das Cockpit die Property der Hauptdomain gibt.
SUBDOMAIN_SETTINGS = {
    "brand": "beispielmarke", "shop": "eu", "name": "Beispielshop EU", "domain": "eu.beispielshop.test",
    "shopify_store": "beispielshop-eu.myshopify.com", "ga4_property_id": "123456",
    "gsc_site": "https://beispielshop.test/",
    "google_ads_customer_id": None, "google_ads_login_customer_id": None,
    "sources": {"shopify": "connected", "ga4": "connected", "gsc": "connected"},
}

VALID_CONFIG = {
    "brand": "Beispielshop", "domain": "https://eu.beispielshop.test",
    "shopify_store": "beispielshop-eu.myshopify.com", "ga4_property_id": "1",
    "gsc_site": "sc-domain:beispielshop.test", "cwv_urls": [],
    "sources": {}, "account_slug": "beispielshop",
    "drive_path": "/pfad/zum/kundenordner/beispielshop",
    "market": {"location_code": 2276, "language_code": "de"},
}


class TestCovers(unittest.TestCase):
    def test_url_praefix_mit_genau_dem_host_passt(self):
        self.assertTrue(gsc_scope.covers("https://eu.beispielshop.test/", "eu.beispielshop.test"))

    def test_url_praefix_der_hauptdomain_deckt_die_subdomain_nicht_ab(self):
        # Der Fall vom 07.10.2026: lesbar, aber die Zahlen gehören zum Store der Hauptdomain.
        self.assertFalse(gsc_scope.covers("https://beispielshop.test/", "eu.beispielshop.test"))

    def test_url_praefix_einer_subdomain_deckt_die_hauptdomain_nicht_ab(self):
        self.assertFalse(gsc_scope.covers("https://eu.beispielshop.test/", "beispielshop.test"))

    def test_www_gilt_als_derselbe_host(self):
        self.assertTrue(gsc_scope.covers("https://www.beispielshop.test/", "beispielshop.test"))
        self.assertTrue(gsc_scope.covers("https://beispielshop.test/", "www.beispielshop.test"))

    def test_www_vor_einer_anderen_subdomain_hilft_nicht(self):
        self.assertFalse(gsc_scope.covers("https://www.beispielshop.test/", "eu.beispielshop.test"))

    def test_domain_property_deckt_host_und_subdomains_ab(self):
        self.assertTrue(gsc_scope.covers("sc-domain:beispielshop.test", "beispielshop.test"))
        self.assertTrue(gsc_scope.covers("sc-domain:beispielshop.test", "eu.beispielshop.test"))
        self.assertTrue(gsc_scope.covers("sc-domain:beispielshop.test", "www.beispielshop.test"))

    def test_domain_property_einer_subdomain_deckt_die_hauptdomain_nicht_ab(self):
        self.assertFalse(gsc_scope.covers("sc-domain:eu.beispielshop.test", "beispielshop.test"))

    def test_gleiche_endung_ist_keine_uebergeordnete_domain(self):
        self.assertFalse(gsc_scope.covers("sc-domain:shop.test", "beispielshop.test"))

    def test_fremde_domain_passt_nicht(self):
        self.assertFalse(gsc_scope.covers("sc-domain:anderer-shop.test", "beispielshop.test"))
        self.assertFalse(gsc_scope.covers("https://anderer-shop.test/", "beispielshop.test"))

    def test_domain_mit_schema_pfad_port_und_grossschreibung(self):
        self.assertTrue(gsc_scope.covers("https://eu.beispielshop.test/",
                                         "HTTPS://EU.Beispielshop.test:443/de/"))
        self.assertTrue(gsc_scope.covers("SC-DOMAIN:Beispielshop.test", "https://beispielshop.test"))

    def test_http_oder_pfad_sieht_nur_einen_teil_des_shops(self):
        # Wie im Cockpit (gscCoversDomain): der Shop läuft unter https und ganz.
        self.assertFalse(gsc_scope.covers("http://beispielshop.test/", "beispielshop.test"))
        self.assertFalse(gsc_scope.covers("https://beispielshop.test/de/", "beispielshop.test"))
        self.assertTrue(gsc_scope.covers("https://beispielshop.test", "beispielshop.test"))

    def test_nicht_lesbares_deckt_nichts_ab(self):
        for site, domain in (("beispielshop.test", "beispielshop.test"),
                             ("sc-domain:", "beispielshop.test"),
                             ("ftp://beispielshop.test/", "beispielshop.test"),
                             (None, "beispielshop.test"),
                             ("sc-domain:beispielshop.test", ""),
                             ("sc-domain:beispielshop.test", None)):
            with self.subTest(site=site, domain=domain):
                self.assertFalse(gsc_scope.covers(site, domain))


class TestMismatch(unittest.TestCase):
    def test_passende_property_ergibt_keinen_satz(self):
        self.assertIsNone(gsc_scope.mismatch("sc-domain:beispielshop.test", "eu.beispielshop.test"))

    def test_unpassende_property_nennt_property_host_und_was_passen_wuerde(self):
        message = gsc_scope.mismatch("https://beispielshop.test/", "https://eu.beispielshop.test")
        self.assertIn("https://beispielshop.test/", message)
        self.assertIn("eu.beispielshop.test", message)
        self.assertIn("https://eu.beispielshop.test/", message)

    def test_fehlende_werte_meldet_die_pflichtfeldpruefung_nicht_diese(self):
        self.assertIsNone(gsc_scope.mismatch("", "beispielshop.test"))
        self.assertIsNone(gsc_scope.mismatch(None, "beispielshop.test"))
        self.assertIsNone(gsc_scope.mismatch("sc-domain:beispielshop.test", ""))



class TestValidateGate(unittest.TestCase):
    def test_passende_property_besteht(self):
        self.assertEqual(config.validate(VALID_CONFIG), [])

    def test_unpassende_property_haelt_den_lauf_vor_jedem_pull_an(self):
        errors = config.validate(dict(VALID_CONFIG, gsc_site="https://beispielshop.test/"))
        self.assertEqual(len(errors), 1)
        self.assertIn("deckt den Shop eu.beispielshop.test nicht ab", errors[0])

    def test_abgeschaltete_search_console_wird_nicht_geprueft(self):
        broken = dict(VALID_CONFIG, gsc_site="https://beispielshop.test/", sources={"gsc": False})
        self.assertEqual(config.validate(broken), [])


class TestPortalSetup(unittest.TestCase):
    def test_unpassende_property_schaltet_search_console_mit_grund_ab(self):
        merged = portal.merge_config({}, SUBDOMAIN_SETTINGS)
        self.assertIs(merged["sources"]["gsc"], False)
        self.assertIn("https://beispielshop.test/", merged["source_off_reasons"]["gsc"])
        # Die Property bleibt stehen, damit sichtbar ist, was das Cockpit geliefert hat.
        self.assertEqual(merged["gsc_site"], "https://beispielshop.test/")

    def test_nach_der_korrektur_im_cockpit_ist_sie_wieder_an_und_der_grund_weg(self):
        before = portal.merge_config({}, SUBDOMAIN_SETTINGS)
        fixed = dict(SUBDOMAIN_SETTINGS, gsc_site="sc-domain:beispielshop.test")
        merged = portal.merge_config(before, fixed)
        self.assertIs(merged["sources"]["gsc"], True)
        self.assertNotIn("source_off_reasons", merged)

    def test_andere_gruende_bleiben_stehen(self):
        before = {"source_off_reasons": {"ads": "eigener Grund"}}
        merged = portal.merge_config(before, dict(SUBDOMAIN_SETTINGS, gsc_site="sc-domain:beispielshop.test"))
        self.assertEqual(merged["source_off_reasons"], {"ads": "eigener Grund"})

    def test_der_stand_domain_mismatch_aus_dem_cockpit_bringt_den_grund_mit(self):
        settings = dict(SUBDOMAIN_SETTINGS, sources={"shopify": "connected", "gsc": "domain_mismatch"})
        merged = portal.merge_config({}, settings)
        self.assertIs(merged["sources"]["gsc"], False)
        self.assertIn("deckt den Shop eu.beispielshop.test nicht ab", merged["source_off_reasons"]["gsc"])

    def test_domain_mismatch_ohne_property_hat_trotzdem_einen_grund(self):
        settings = dict(SUBDOMAIN_SETTINGS, gsc_site=None,
                        sources={"shopify": "connected", "gsc": "domain_mismatch"})
        self.assertIn("domain_mismatch", portal.merge_config({}, settings)["source_off_reasons"]["gsc"])

    def test_nicht_verbunden_ist_kein_unpassend(self):
        settings = dict(SUBDOMAIN_SETTINGS, sources={"shopify": "connected", "gsc": "not_connected"})
        self.assertNotIn("source_off_reasons", portal.merge_config({}, settings))

    def test_setup_schreibt_die_config_und_warnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(portal, "shop_settings", return_value=SUBDOMAIN_SETTINGS), \
                    redirect_stdout(out), redirect_stderr(err):
                code = portal.main(["setup", "--brand", "beispielmarke", "--shop", "eu", "--workspace", tmp])
            written = json.loads((Path(tmp) / "reporting" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertIs(written["sources"]["gsc"], False)
        self.assertIn("Warnung", err.getvalue())
        self.assertIn("eu.beispielshop.test", err.getvalue())


class TestPortalCheck(unittest.TestCase):
    def run_check(self, settings):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(portal, "shop_settings", return_value=settings), \
                mock.patch.object(portal, "google_token", return_value="ya29.kurzlebig"), \
                mock.patch.object(portal, "shopify_execute", return_value={"shop": {"name": "x"}}), \
                redirect_stdout(out), redirect_stderr(err):
            code = portal.main(["check", "--brand", "beispielmarke", "--shop", "eu"])
        return code, out.getvalue(), err.getvalue()

    def test_unpassende_property_endet_mit_exit_1_nach_allen_pruefungen(self):
        code, out, err = self.run_check(SUBDOMAIN_SETTINGS)
        self.assertEqual(code, 1)
        self.assertIn("Abfrage über das Cockpit beantwortet", out)
        self.assertIn("deckt den Shop eu.beispielshop.test nicht ab", err)

    def test_domain_mismatch_aus_dem_cockpit_endet_mit_exit_1(self):
        settings = dict(SUBDOMAIN_SETTINGS, sources={"shopify": "connected", "gsc": "domain_mismatch"})
        code, out, err = self.run_check(settings)
        self.assertEqual(code, 1)
        self.assertIn("domain_mismatch", out)
        self.assertIn("deckt den Shop eu.beispielshop.test nicht ab", err)

    def test_passende_property_endet_mit_exit_0(self):
        code, _, err = self.run_check(dict(SUBDOMAIN_SETTINGS, gsc_site="https://eu.beispielshop.test/"))
        self.assertEqual((code, err), (0, ""))


class TestGscPull(unittest.TestCase):
    def run_pull(self, *extra):
        # Ohne gültigen Zugang: die Prüfung muss vor dem Token greifen, sonst
        # endete der Aufruf mit einem Fehler beim Token statt mit dem echten Grund.
        return subprocess.run([sys.executable, str(GSC_PULL), "--site", "https://beispielshop.test/",
                               "--creds", "/gibt/es/nicht.json", "--start", "2026-01-01",
                               "--end", "2026-01-31", "--out", "unbenutzt", *extra],
                              capture_output=True, text=True)

    def test_mit_domain_wird_nichts_gezogen(self):
        result = self.run_pull("--domain", "eu.beispielshop.test")
        self.assertEqual(result.returncode, 1)
        self.assertIn("deckt den Shop eu.beispielshop.test nicht ab", result.stderr)

    def test_die_domain_kommt_auch_aus_der_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"domain": "eu.beispielshop.test"}), encoding="utf-8")
            result = self.run_pull("--config", str(path))
        self.assertIn("deckt den Shop eu.beispielshop.test nicht ab", result.stderr)

    def test_ohne_domain_bleibt_es_beim_bisherigen_verhalten(self):
        result = self.run_pull()
        self.assertNotIn("deckt den Shop", result.stderr)


if __name__ == "__main__":
    unittest.main()
