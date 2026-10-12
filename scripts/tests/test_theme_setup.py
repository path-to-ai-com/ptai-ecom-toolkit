"""Tests für das Setup eines Stores (`theme.setup`, Format `reference/setup-format.md`)."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from audit import publish
from theme import setup

COLLECTED = "2026-10-12T11:00:00+00:00"

#: Ein kleiner Host-Katalog im Format von `hosts.json`, erfunden.
HOSTS = {
    "categories": {"shopify": "Shopify (Plattform)", "email_sms": "E-Mail und SMS", "fonts": "Schriften",
                   "reviews": "Bewertungen"},
    "ignore_hosts": ["example.com"],
    "services": [
        {"id": "shopify", "name": "Shopify", "category": "shopify", "hosts": ["shopify.com"], "platform": True},
        {"id": "beispielmail", "name": "Beispielmail", "category": "email_sms", "hosts": ["beispielmail.test"]},
        {"id": "beispielschrift", "name": "Beispielschrift", "category": "fonts", "hosts": ["schrift.test"]},
        {"id": "sterne", "name": "Sterne", "category": "reviews", "hosts": ["sterne.test"]},
    ],
}


def valid() -> dict:
    """Ein Setup wie im Beispiel der Format-Beschreibung."""
    return {
        "schema": 1, "shop": "beispielshop", "reference_shop": "beispielshop", "collected_at": COLLECTED,
        "source": "aus dem Repo der Migration", "automatic": False,
        "views": {
            "live": {"theme": {"name": "Broadcast", "version": "5.0.0", "id": "000000000000"}, "groups": [
                {"key": "theme", "label": "Theme", "rows": [
                    {"key": "theme", "label": "Theme", "value": "Broadcast 5.0.0", "note": "angepasst"},
                    {"key": "base_changes", "label": "Änderungen am Basis-Theme", "value": "12 Anpassungen",
                     "compare": False, "hint": "je weniger, desto leichter das nächste Update"}]},
                {"key": "apps", "label": "Apps im Theme", "rows": [
                    {"key": "app:beispielmail", "label": "Beispielmail", "hint": "Marketing",
                     "value": "eingebunden", "present": True}]}]},
            "draft": {"theme": {"name": "Horizon", "version": "4.2.0", "id": "000000000002"}, "groups": [
                {"key": "tracking", "label": "Tracking und Einwilligung", "rows": [
                    {"key": "cookie_banner", "label": "Cookie-Banner", "value": "Beispielbanner",
                     "policy": {"kind": "gap", "text": "bis zum Launch angleichen"}}]}]},
        },
    }


def shop_tech() -> dict:
    """Ein erfundener Technik-Abzug im Format von `shop_tech_build`."""
    return {
        "source": "shop_tech",
        "summary": {"themes_total": 3, "crawl_pages_scanned": 40},
        "theme": {"name": "Beispiel Live", "role": "MAIN", "updated_at": "2026-10-01T08:00:00Z"},
        "themes": [{"name": "Beispiel Live", "role": "MAIN"}, {"name": "Entwurf", "role": "UNPUBLISHED"},
                   {"name": "Alt", "role": "UNPUBLISHED"}],
        "locales": [{"locale": "en", "primary": False, "published": True},
                    {"locale": "de", "primary": True, "published": True},
                    {"locale": "fr", "primary": False, "published": False}],
        "markets": [{"name": "A", "enabled": True, "primary": True}, {"name": "B", "enabled": True},
                    {"name": "C", "enabled": False}],
        "storefront_script_hosts": {"cdn.shopify.com": 40, "static.beispielmail.test": 40, "api.beispielmail.test": 5,
                                    "schrift.test": 40, "sterne.test": 12, "unbekannt.test": 3, "example.com": 1},
        "storefront_inline_tag_ids": {"G-AAAA1111": 40, "G-BBBB2222": 2, "GTM-CCCC33": 40},
        "notes": [],
    }


def build(data=None, **kwargs) -> dict:
    return setup.from_shop_tech(data or shop_tech(), shop="beispielshop", collected_at=COLLECTED, hosts=HOSTS,
                                **kwargs)


def rows(data: dict, group: str) -> dict:
    found = next(g for g in data["views"]["live"]["groups"] if g["key"] == group)
    return {r["key"]: r for r in found["rows"]}


class Validate(unittest.TestCase):
    def test_das_beispiel_aus_der_formatbeschreibung_ist_gueltig(self):
        self.assertEqual(setup.validate(valid()), [])

    def test_ohne_live_ansicht_ist_es_ungueltig(self):
        data = valid()
        del data["views"]["live"]
        self.assertTrue(any("views.live fehlt" in e for e in setup.validate(data)))

    def test_falsches_schema_und_fehlende_pflichtfelder_werden_genannt(self):
        data = valid()
        data["schema"] = 2
        del data["shop"]
        data["collected_at"] = "gestern"
        errors = " | ".join(setup.validate(data))
        self.assertIn("schema", errors)
        self.assertIn("shop fehlt", errors)
        self.assertIn("collected_at", errors)

    def test_unbekannter_gruppenschluessel_wird_abgewiesen(self):
        data = valid()
        data["views"]["live"]["groups"][0]["key"] = "sonstiges"
        self.assertTrue(any("sonstiges" in e for e in setup.validate(data)))

    def test_eine_zeile_braucht_key_label_und_value(self):
        data = valid()
        data["views"]["live"]["groups"][0]["rows"][0] = {"key": "theme"}
        errors = " | ".join(setup.validate(data))
        self.assertIn("label fehlt", errors)
        self.assertIn("value fehlt", errors)

    def test_ein_zeilenschluessel_darf_je_ansicht_nur_einmal_stehen(self):
        data = valid()
        data["views"]["live"]["groups"][0]["rows"].append({"key": "theme", "label": "Theme", "value": "x"})
        self.assertTrue(any("zweimal" in e for e in setup.validate(data)))

    def test_derselbe_schluessel_in_zwei_ansichten_ist_erlaubt(self):
        data = valid()
        data["views"]["draft"]["groups"].append(copy.deepcopy(data["views"]["live"]["groups"][0]))
        self.assertEqual(setup.validate(data), [])

    def test_unbekannte_einordnung_wird_abgewiesen(self):
        data = valid()
        data["views"]["draft"]["groups"][0]["rows"][0]["policy"]["kind"] = "egal"
        self.assertTrue(any("policy.kind" in e for e in setup.validate(data)))

    def test_eine_einordnung_gibt_es_nur_im_entwurf(self):
        data = valid()
        data["views"]["live"]["groups"][0]["rows"][0]["policy"] = {"kind": "allowed", "text": "darf abweichen"}
        self.assertTrue(any("nur im Entwurf" in e for e in setup.validate(data)))

    def test_eine_app_heisst_app_doppelpunkt_handle(self):
        data = valid()
        data["views"]["live"]["groups"][1]["rows"][0]["key"] = "beispielmail"
        self.assertTrue(any("app:<handle>" in e for e in setup.validate(data)))


class WriteRun(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)

    def test_der_lauf_traegt_state_und_setup(self):
        run_dir = setup.write_run(self.ws, valid(), today=date(2026, 10, 12))
        self.assertEqual(run_dir.name, "2026-10-12-setup")
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual((state["cadence"], state["title"]), ("setup", "Setup"))
        self.assertEqual(json.loads((run_dir / "setup.json").read_text(encoding="utf-8"))["shop"], "beispielshop")

    def test_ein_ungueltiges_setup_landet_nie_im_lauf(self):
        data = valid()
        del data["views"]
        with self.assertRaises(setup.SetupError):
            setup.write_run(self.ws, data, today=date(2026, 10, 12))
        self.assertFalse((self.ws / "reporting" / "runs").exists())

    def test_derselbe_tag_ueberschreibt_den_lauf(self):
        setup.write_run(self.ws, valid(), today=date(2026, 10, 12))
        second = valid()
        second["source"] = "zweite Erhebung"
        run_dir = setup.write_run(self.ws, second, today=date(2026, 10, 12))
        self.assertEqual(len(list((self.ws / "reporting" / "runs").iterdir())), 1)
        self.assertEqual(json.loads((run_dir / "setup.json").read_text(encoding="utf-8"))["source"],
                         "zweite Erhebung")

    def test_publish_laedt_den_lauf_als_setup_hoch_und_gibt_ihn_frei(self):
        (self.ws / "reporting").mkdir(parents=True, exist_ok=True)
        (self.ws / "reporting" / "config.json").write_text(json.dumps(
            {"account_slug": "beispielkunde", "brand": "Beispielshop"}), encoding="utf-8")
        run_dir = setup.write_run(self.ws, build(), today=date(2026, 10, 12))
        out = publish.prepare(self.ws, run_dir.name, self.ws / "bucket", today=date(2026, 10, 12))
        self.assertTrue(out["released"])
        self.assertEqual(out["files"], 1)


class FromShopTech(unittest.TestCase):
    def test_das_ergebnis_ist_ein_gueltiges_setup_nur_mit_live_ansicht(self):
        data = build()
        self.assertEqual(setup.validate(data), [])
        self.assertEqual(list(data["views"]), ["live"])
        self.assertEqual(data["views"]["live"]["theme"]["name"], "Beispiel Live")

    def test_theme_plaetze_als_belegt_von_zwanzig_ohne_vergleich(self):
        slots = rows(build(), "theme")["theme_slots"]
        self.assertEqual(slots["value"], "3 von 20 belegt")
        self.assertFalse(slots["compare"])

    def test_zwei_ga4_kennungen_stehen_im_wert_die_kennungen_in_der_notiz(self):
        ga4 = rows(build(), "tracking")["ga4"]
        self.assertEqual(ga4["value"], "2 Kennungen")
        self.assertIn("G-AAAA1111", ga4["note"])
        self.assertIn("G-BBBB2222", ga4["note"])

    def test_eine_kennung_heisst_eingebunden(self):
        self.assertEqual(rows(build(), "tracking")["tag_manager"]["value"], "eingebunden")

    def test_fehlende_kennung_heisst_nicht_nicht_eingebunden(self):
        # Über den Tag Manager geladen findet der Crawl keine Kennung im Quelltext.
        ads = rows(build(), "tracking")["google_ads"]
        self.assertEqual(ads["value"], "keine Kennung im Quelltext")

    def test_veroeffentlichte_sprachen_mit_der_hauptsprache_zuerst(self):
        languages = rows(build(), "languages")["languages"]
        self.assertEqual(languages["value"], "de, en")
        self.assertEqual(languages["note"], "1 Sprache nicht veröffentlicht")

    def test_maerkte_als_zahl_der_aktiven_ohne_vergleich(self):
        markets = rows(build(), "languages")["markets"]
        self.assertEqual(markets["value"], "2")
        self.assertFalse(markets["compare"])

    def test_nicht_gelesene_sprachen_sind_keine_leere_liste(self):
        data = shop_tech()
        data["locales"] = []
        data["notes"] = ["Block 'shopLocales' nicht gelesen (fehlender Scope oder Feldname)."]
        languages = rows(build(data), "languages")["languages"]
        self.assertEqual(languages["value"], "nicht gelesen")
        self.assertFalse(languages["compare"])

    def test_je_anbieter_eine_app_zeile_ohne_plattform_schrift_und_unbekannte_hosts(self):
        apps = rows(build(), "apps")
        self.assertEqual(sorted(apps), ["app:beispielmail", "app:sterne"])
        mail = apps["app:beispielmail"]
        self.assertTrue(mail["present"])
        self.assertEqual(mail["hint"], "E-Mail und SMS")
        self.assertIn("api.beispielmail.test", mail["note"])

    def test_ohne_crawl_entsteht_kein_setup(self):
        data = shop_tech()
        data["summary"]["crawl_pages_scanned"] = None
        with self.assertRaises(setup.SetupError) as caught:
            build(data)
        self.assertIn("ohne Crawl", str(caught.exception))

    def test_ohne_live_theme_entsteht_kein_setup(self):
        data = shop_tech()
        data["theme"] = None
        with self.assertRaises(setup.SetupError):
            build(data)

    def test_referenz_store_wird_uebernommen(self):
        self.assertEqual(build(reference_shop="referenzshop")["reference_shop"], "referenzshop")
        self.assertIsNone(build()["reference_shop"])

    def test_der_echte_host_katalog_ist_lesbar(self):
        data = setup.from_shop_tech(shop_tech(), shop="beispielshop", collected_at=COLLECTED)
        self.assertEqual(setup.validate(data), [])


class Cli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def run_cli(self, *args) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = setup.main(list(args))
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_validate_meldet_fehler_mit_exit_eins(self):
        path = self.root / "setup.json"
        data = valid()
        del data["views"]["live"]
        path.write_text(json.dumps(data), encoding="utf-8")
        code, summary = self.run_cli("validate", "--path", str(path))
        self.assertEqual(code, 1)
        self.assertFalse(summary["valid"])

    def test_validate_ohne_befund_mit_exit_null(self):
        path = self.root / "setup.json"
        path.write_text(json.dumps(valid()), encoding="utf-8")
        self.assertEqual(self.run_cli("validate", "--path", str(path))[0], 0)

    def test_from_shop_tech_schreibt_den_lauf_mit_referenz_aus_der_config(self):
        ws = self.root / "ws"
        (ws / "reporting").mkdir(parents=True)
        (ws / "reporting" / "config.json").write_text(json.dumps({"reference_shop": "referenzshop"}),
                                                      encoding="utf-8")
        source = self.root / "shop-tech.json"
        source.write_text(json.dumps(shop_tech()), encoding="utf-8")
        code, summary = self.run_cli("from-shop-tech", "--path", str(source), "--shop", "beispielshop",
                                     "--workspace", str(ws))
        self.assertEqual(code, 0, summary)
        written = json.loads(Path(summary["path"]).read_text(encoding="utf-8"))
        self.assertEqual(written["reference_shop"], "referenzshop")
        self.assertTrue(summary["run_id"].endswith("-setup"))

    def test_from_shop_tech_ohne_crawl_bricht_mit_exit_zwei_ab(self):
        data = shop_tech()
        data["summary"]["crawl_pages_scanned"] = None
        source = self.root / "shop-tech.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        code, summary = self.run_cli("from-shop-tech", "--path", str(source), "--shop", "beispielshop",
                                     "--workspace", str(self.root / "ws"))
        self.assertEqual(code, 2)
        self.assertIn("ohne Crawl", summary["error"])


if __name__ == "__main__":
    unittest.main()
