"""App-Inventar als Ganzes: `theme.apps scan` über alle synthetischen Quellen.

Die Regeln, die hier festgehalten sind, kommen aus Feldfehlern: ein Skript-Tag,
das nur im Seitenkopf steht, ein Rest einer deinstallierten App im Snippet, eine
Seitenansicht, die Seite und Pixel doppelt senden, ein Mitschnitt, der still das
falsche Theme zeigt, und eine Quelle, die nicht lesbar war und trotzdem als 0
im Inventar stand.
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

from theme import apps  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "theme" / "apps"

#: Die Felder des Datenmodells je Einbindung.
FIELDS = {
    "integration_id", "service_id", "service_name", "vendor", "category", "app_id", "api_client_id", "app_handle",
    "installed", "integration_type", "location", "state", "page_types", "function", "visible_frontend", "hosts",
    "cookies", "storage_keys", "globals", "sends_data", "before_consent", "privacy_purposes",
    "survives_theme_switch", "deprecation", "evidence", "decision", "decided_by", "decided_on",
    "target_integration", "verified_draft", "verified_live",
}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def full_scan():
    return apps.scan(FIXTURES / "theme", FIXTURES / "html", [FIXTURES / "network.json"], [FIXTURES / "gtm.js"],
                     load("templates.json"), load("app-names.json"), load("metafields.json"), load("admin-apps.json"))


class TestVollerScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.apps, cls.tracking = full_scan()
        cls.rows = {row["integration_id"]: row for row in cls.apps["integrations"]}
        cls.targets = {t["target_id"]: t for t in cls.tracking["targets"]}

    def test_jede_zeile_traegt_das_datenmodell_und_ist_offen(self):
        for row in self.apps["integrations"]:
            with self.subTest(row=row["integration_id"]):
                self.assertLessEqual(FIELDS, set(row))
                self.assertEqual(row["decision"], "open")
                self.assertIn(row["integration_type"], apps.INTEGRATION_TYPES)

    def test_ueberleben_folgt_allein_aus_der_art(self):
        for row in self.apps["integrations"]:
            with self.subTest(row=row["integration_id"]):
                self.assertEqual(row["survives_theme_switch"], apps.SURVIVES_THEME_SWITCH[row["integration_type"]])
        self.assertFalse(self.rows["app_embed:judge-me-reviews/judgeme_core"]["survives_theme_switch"])
        self.assertTrue(self.rows["web_pixel:1"]["survives_theme_switch"])

    def test_skript_tags_mit_beiden_fristen(self):
        tags = [r for r in self.apps["integrations"] if r["integration_type"] == "script_tag"]
        self.assertEqual(len(tags), 2)
        for row in tags:
            self.assertEqual(row["deprecation"]["frozen_since"], "2026-10-01")
            self.assertEqual(row["deprecation"]["stops_loading_on"], "2027-03-01")
        self.assertIsNone(self.rows["web_pixel:1"]["deprecation"])

    def test_skript_tag_mit_404_ist_kaputt(self):
        row = self.rows["script_tag:https://scripts.unbekannt-app.example/loader.js"]
        self.assertEqual((row["state"], row["state_basis"]), ("broken", "network"))

    def test_rest_einer_alten_app_trotz_aufruf_mit_falschem_theme(self):
        row = self.rows["theme_code:unknown:widget.altanbieter.example:snippets/old-widget.liquid"]
        self.assertEqual(row["state"], "leftover")
        self.assertEqual(row["location"]["lines"], [3])

    def test_embeds_aktiv_und_deaktiviert(self):
        self.assertEqual(self.rows["app_embed:judge-me-reviews/judgeme_core"]["state"], "active")
        self.assertEqual(self.rows["app_embed:klaviyo-email-marketing-sms/klaviyo-onsite-embed"]["state"], "disabled")
        self.assertEqual(self.rows["app_embed:beispiel-upsell/app-embed"]["service_id"], "app:beispiel-upsell")

    def test_app_erweiterung_auf_shopify_cdn_gehoert_zum_embed(self):
        embed = self.rows["app_embed:judge-me-reviews/judgeme_core"]
        self.assertEqual((embed["state_basis"], embed["page_types"]), ("network", ["index"]))
        self.assertEqual(embed["sends_data"], "loads_only")
        other = self.rows["app_embed:klaviyo-email-marketing-sms/klaviyo-onsite-embed"]
        self.assertEqual((other["state_basis"], other["page_types"]), ("config", ["index"]))

    def test_app_bloecke_gegen_templates_mit_objekten(self):
        widget = self.rows["app_block:judge-me-reviews/review_widget"]["location"]
        self.assertEqual(widget["files"], {"templates/page.alt.json": {"active": 0, "disabled": 1},
                                           "templates/product.json": {"active": 1, "disabled": 0}})
        self.assertEqual((widget["templates_live"], widget["templates_without_objects"]), (1, 1))
        self.assertEqual(self.rows["app_block:beispiel-upsell/offer"]["state"], "disabled")
        group = self.rows["app_block:klaviyo-email-marketing-sms/form-embed-block"]["location"]
        self.assertEqual(group["section_groups"], ["sections/header-group.json"])

    def test_code_in_einer_custom_liquid_section_zaehlt_als_theme_code(self):
        self.assertIn("theme_code:jsdelivr:templates/index.json", self.rows)

    def test_embed_kennung_nicht_doppelt_als_theme_code(self):
        self.assertFalse(any(key.endswith("config/settings_data.json") for key in self.rows))

    def test_pixel_sendet_nur_aus_seinem_rahmen(self):
        self.assertEqual(self.rows["web_pixel:1"]["before_consent"], "silent")
        self.assertEqual(self.rows["web_pixel:1"]["service_id"], "meta")
        custom = self.rows["web_pixel:3"]
        self.assertEqual(custom["hosts"], ["collector.unbekannt.example"])
        self.assertEqual((custom["before_consent"], custom["sends_data"]), ("sends", "sends"))

    def test_tag_manager_je_tag_eine_zeile(self):
        self.assertEqual(self.rows["tag_manager:GTM-BEISP01"]["location"]["tags"], 7)
        self.assertEqual(self.rows["tag_manager:GTM-BEISP01:tag-4"]["service_id"], "meta")
        self.assertEqual(self.rows["tag_manager:GTM-BEISP01:tag-5"]["state"], "disabled")
        self.assertEqual(self.rows["tag_manager:GTM-BEISP01:tag-6"]["service_id"],
                         "unknown:widget.gtm-unbekannt.example")

    def test_unbekannte_hosts_bleiben_mit_fundstelle(self):
        hosts = {u["host"]: u for u in self.apps["unknown_hosts"]}
        self.assertEqual(set(hosts), {"collector.unbekannt.example", "scripts.unbekannt-app.example",
                                      "t.beispielshop.example", "tracker.unbekannt.example",
                                      "widget.altanbieter.example", "widget.gtm-unbekannt.example"})
        self.assertIn("Subdomain", hosts["t.beispielshop.example"]["reason"])
        self.assertTrue(hosts["t.beispielshop.example"]["sends"])
        self.assertEqual(self.rows["network:unknown:t.beispielshop.example"]["integration_type"], "network_only")

    def test_spuren_ohne_zuordnung(self):
        self.assertEqual(self.apps["unknown_traces"]["cookies"], ["beispiel_rest @ beispielshop.example"])
        self.assertEqual(self.apps["unknown_traces"]["globals"], ["unbekanntesGlobal"])
        self.assertIn("_ga @ .beispielshop.example", self.rows["tag_manager:GTM-BEISP01:tag-1"]["cookies"])

    def test_app_proxy_aus_code_und_mitschnitt(self):
        row = self.rows["app_proxy:/apps/beispiel-proxy"]
        self.assertEqual(row["location"]["files"], ["assets/theme.js"])
        self.assertTrue(row["survives_theme_switch"])

    def test_admin_liste_und_app_namen(self):
        self.assertEqual(self.rows["app_embed:judge-me-reviews/judgeme_core"]["installed"], "yes")
        self.assertEqual(self.rows["admin_app:beispiel-erp-connector"]["integration_type"], "server_side")
        self.assertEqual(self.rows["web_pixel:1"]["installed"], "yes")
        self.assertEqual(self.apps["coverage"]["app_names"]["status"], "partial")
        self.assertIn("1000002", self.apps["coverage"]["app_names"]["reason"])

    def test_metafelder_ohne_zuordnung_werden_genannt(self):
        reason = self.apps["coverage"]["shop_metafields"]["reason"]
        self.assertIn("beispiel_altapp", reason)
        self.assertIn("custom", reason)
        evidence = [e["source"] for e in self.rows["web_pixel:2"]["evidence"]]
        self.assertIn("shop_metafields", evidence)

    def test_falsches_theme_macht_den_mitschnitt_unvollstaendig(self):
        capture = self.apps["coverage"]["browser_capture"]
        self.assertEqual(capture["status"], "partial")
        self.assertIn("wrong_theme", capture["reason"])
        self.assertEqual(capture["count"], 2)

    def test_doppelte_events_aus_konfiguration_und_mitschnitt(self):
        ga4 = {(d["event"], d["basis"]): d for d in self.targets["G-BEISPIEL01"]["duplicate_events"]}
        self.assertEqual(ga4[("purchase", "config")]["senders"],
                         ["tag_manager:GTM-BEISP01:tag-1", "theme_code:google_tag:snippets/ga4.liquid", "web_pixel:2"])
        self.assertEqual(ga4[("page_view", "network")]["senders"], ["page", "pixel:2"])
        self.assertEqual(ga4[("page_view", "network")]["kind"], "two_senders")
        meta = self.targets["META:100000000000001"]["duplicate_events"]
        self.assertEqual([(d["event"], d["spellings"]) for d in meta], [("page_view", ["PageView"])])
        ads = self.targets["AW-000000000"]
        self.assertEqual(ads["labels"], ["beispielLabel"])

    def test_deaktivierte_absender_zaehlen_nicht_als_doppel(self):
        for target in self.tracking["targets"]:
            for duplicate in target["duplicate_events"]:
                for sender in duplicate["senders"]:
                    if sender in self.rows:
                        self.assertNotIn(self.rows[sender]["state"], ("disabled", "leftover"))


class TestAbdeckung(unittest.TestCase):
    def test_jede_quelle_steht_da_und_nicht_lesbar_ist_nie_null(self):
        result, _ = full_scan()
        self.assertEqual(list(result["coverage"]), [key for key, _ in apps.SOURCES])
        for key, entry in result["coverage"].items():
            with self.subTest(source=key):
                self.assertIn(entry["status"], ("complete", "partial", "not_readable"))
                if entry["status"] == "not_readable":
                    self.assertIsNone(entry["count"])
                    self.assertTrue(entry["reason"])

    def test_nur_die_sicherung(self):
        result, tracking = apps.scan(FIXTURES / "theme")
        coverage = result["coverage"]
        for key in ("browser_capture", "web_pixels", "script_tags", "admin_app_list", "consent"):
            with self.subTest(source=key):
                self.assertEqual(coverage[key]["status"], "not_readable")
                self.assertIsNone(coverage[key]["count"])
        self.assertEqual(coverage["tag_manager"]["status"], "not_readable")
        self.assertIn("GTM-BEISP01", coverage["tag_manager"]["reason"])
        self.assertEqual(coverage["app_blocks"]["status"], "partial")
        old = [r for r in result["integrations"] if r["integration_id"].endswith("old-widget.liquid")][0]
        self.assertEqual((old["state"], old["before_consent"]), ("active", "not_measured"))

    def test_html_ohne_shopify(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "seite.html").write_text("<html><body>Fehlerseite</body></html>", encoding="utf-8")
            result, _ = apps.scan(FIXTURES / "theme", html=Path(tmp))
        self.assertEqual(result["coverage"]["web_pixels"]["status"], "not_readable")
        self.assertIn("Shopify", result["coverage"]["web_pixels"]["reason"])


class TestCli(unittest.TestCase):
    def test_schreibt_beide_dateien_und_meldet_befunde(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "inventory" / "apps.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = apps.main(["scan", "--snapshot", str(FIXTURES / "theme"), "--html", str(FIXTURES / "html"),
                                  "--network", str(FIXTURES / "network.json"), "--gtm", str(FIXTURES / "gtm.js"),
                                  "--templates", str(FIXTURES / "templates.json"), "--out", str(out)])
            summary = json.loads(buffer.getvalue())
            self.assertEqual(code, 1)
            self.assertTrue(out.is_file())
            self.assertTrue((out.parent / "tracking.json").is_file())
            self.assertEqual(summary["script_tags"], 2)
            self.assertEqual(summary["leftover"], 1)
            self.assertIn("admin_app_list", summary["not_readable"])

    def test_fehlender_katalog_ist_ein_fehler(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            code = apps.main(["scan", "--snapshot", str(FIXTURES / "theme"), "--hosts", str(Path(tmp) / "fehlt.json"),
                              "--out", str(Path(tmp) / "apps.json")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
