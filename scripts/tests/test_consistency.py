"""Abweichung zum Referenz-Store als Befund (Spec ptai-portal 2026-10-08, Abschnitt 10)."""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from audit import consistency

from tests import brand_support as bs

RUN = "2026-11-12-audit"


def shop_tech(hosts, domain):
    return {"source": "shop_tech", "storefront_script_hosts": {**{h: 3 for h in hosts}, domain: 9}}


def crawl(policies, schema_types, prefix=""):
    pages = [{"url": f"https://shop.test{prefix}/policies/{p}", "status": 200} for p in policies]
    pages.append({"url": "https://shop.test/policies/kaputt", "status": 404})
    return {"pages": pages, "findings_index": {"schema_types": {t: 1 for t in schema_types}}}


def product(handle, skus, **fields):
    base = {"handle": handle, "skus": skus, "status": "ACTIVE", "vendor": "Beispiel",
            "seo_title": True, "seo_description": True, "images": 2, "images_with_alt": 2, "variants": 1}
    return {**base, **fields}


def catalog(*products):
    return {"source": "catalogue", "summary": {}, "products_index": list(products)}


def theme(folder: Path, version="5.0.0", settings=None, sections=None, captured="2026-11-01T00:00:00Z"):
    bs.write_json(folder / "manifest.json", {"theme_role": "MAIN", "complete": True, "captured_at": captured})
    bs.write_json(folder / "config" / "settings_schema.json",
                  [{"name": "theme_info", "theme_name": "Broadcast", "theme_version": version}])
    bs.write_json(folder / "config" / "settings_data.json", {"current": settings or {}})
    (folder / "templates").mkdir(parents=True, exist_ok=True)
    (folder / "templates" / "product.json").write_text(
        "/*\n * auto-generated\n */\n" + json.dumps({"sections": sections or {}}), encoding="utf-8")


class TestActive(unittest.TestCase):
    def test_on_only_with_a_reference_store_other_than_itself(self):
        uk = {"portal": {"brand": "beispielmarke", "shop": "uk"}}
        self.assertFalse(consistency.is_active(uk))                                   # Marke ohne Referenz-Store
        self.assertTrue(consistency.is_active({**uk, "reference_shop": "eu"}))
        self.assertFalse(consistency.is_active({"portal": {"brand": "beispielmarke", "shop": "eu"},
                                                "reference_shop": "eu"}))           # der Referenz-Store selbst

    def test_without_reference_store_compare_writes_nothing(self):
        brand_ws = bs.make_brand(self)
        self.assertIsNone(consistency.run_compare(brand_ws / "uk", RUN))
        self.assertFalse((brand_ws / "uk" / "reporting" / "data" / RUN / consistency.FILE).exists())
        self.assertEqual(consistency.main(["compare", "--workspace", str(brand_ws / "uk"), "--run-id", RUN]), 0)

    def test_config_validate_checks_the_slug(self):
        from audit import config
        self.assertTrue(any("reference_shop" in e for e in config.validate({"reference_shop": "EU Store"})))
        self.assertFalse(any("reference_shop" in e for e in config.validate({"reference_shop": "eu"})))

    def test_labels(self):
        self.assertEqual(consistency.label("eu"), "EU")
        self.assertEqual(consistency.label("nord-stein"), "Nord Stein")


class TestComparisons(unittest.TestCase):
    def test_apps_ignore_the_own_domain(self):
        dev = consistency.compare_apps(shop_tech(["widget.trustpilot.com", "static.klaviyo.com"], "eu.shop.test"),
                                       shop_tech(["static.klaviyo.com", "cdn.extra.test"], "uk.shop.test"),
                                       "https://eu.shop.test", "https://uk.shop.test", "EU", "UK")
        self.assertEqual(dev["count"], 2)
        texts = json.dumps(dev["rows"])
        self.assertIn("widget.trustpilot.com", texts)
        self.assertIn("cdn.extra.test", texts)
        self.assertNotIn("uk.shop.test", texts)
        self.assertIsNone(consistency.compare_apps(shop_tech(["a.test"], "eu.shop.test"),
                                                   shop_tech(["a.test"], "uk.shop.test"),
                                                   "eu.shop.test", "uk.shop.test", "EU", "UK"))

    def test_legal_pages_without_locale_prefix_and_flagged_for_law(self):
        dev = consistency.compare_legal(crawl(["privacy-policy", "legal-notice", "refund-policy"], []),
                                        crawl(["privacy-policy", "refund-policy"], [], prefix="/en-gb"),
                                        "EU", "UK")
        self.assertEqual(dev["count"], 1)
        self.assertIn("legal-notice", dev["rows"][0]["from"])
        self.assertEqual(dev["review"], "law")

    def test_structured_data(self):
        dev = consistency.compare_structured_data(crawl([], ["Product", "Organization", "FAQPage"]),
                                                  crawl([], ["Product", "Organization"]), "EU", "UK")
        self.assertEqual(dev["count"], 1)
        self.assertIn("FAQPage", dev["rows"][0]["from"])

    def test_products_are_paired_by_sku_not_by_handle(self):
        ref = catalog(product("kinderrad", ["ER-1"]), product("helm", ["ER-2"], images_with_alt=1),
                      product("nur-eu", ["ER-9"]))
        own = catalog(product("balance-bike", ["ER-1"], seo_description=False),
                      product("helmet", ["ER-2"], images_with_alt=2),
                      product("only-uk", ["UK-1"], vendor="Anders"))
        pairs = consistency.shared_products(ref, own)
        self.assertEqual([(r["handle"], o["handle"]) for r, o in pairs],
                         [("kinderrad", "balance-bike"), ("helm", "helmet")])
        self.assertEqual(consistency.compare_seo_description(pairs, "EU", "UK")["count"], 1)
        self.assertEqual(consistency.compare_alt_text(pairs, "EU", "UK")["count"], 1)
        self.assertIsNone(consistency.compare_master_data(pairs, "EU", "UK"))

    def test_master_data_ignore_price_and_text(self):
        pairs = [(product("a", ["S"], vendor="X", variants=3, price_min=10, title="Rad"),
                  product("b", ["S"], vendor="Y", variants=3, price_min=12, title="Bike"))]
        dev = consistency.compare_master_data(pairs, "EU", "UK")
        self.assertEqual(dev["count"], 1)
        self.assertIn("vendor", dev["rows"][0]["from"])
        self.assertNotIn("price", json.dumps(dev["rows"]))

    def test_theme_settings_compare_only_language_neutral_values(self):
        ref, own = {}, {}
        for side, values in ((ref, {"sticky_cart": True, "accent": "#FF0000", "badge_text": "Neu im Shop"}),
                             (own, {"sticky_cart": False, "accent": "#FF0000", "badge_text": "New in"})):
            side.update(consistency._settings_pairs("settings_data > ", values))
        dev = consistency.compare_theme_settings(ref, own, "EU", "UK")
        self.assertEqual(dev["count"], 1)
        self.assertIn("sticky_cart", dev["rows"][0]["from"])

    def test_missing_snapshots_are_not_compared_never_equal(self):
        deviations, not_compared = consistency.compare(
            {"domain": "eu.shop.test", "shop-tech.json": None, "crawl.json": None, "catalog.json": {"summary": {}},
             "theme": None},
            {"domain": "uk.shop.test", "shop-tech.json": None, "crawl.json": None, "catalog.json": None,
             "theme": None}, "eu", "uk")
        self.assertEqual(deviations, [])
        self.assertEqual({n["key"] for n in not_compared}, set(consistency.AREA_LABELS))


class TestRunAndFindings(unittest.TestCase):
    def setUp(self):
        self.brand_ws = bs.make_brand(self)
        self.uk = self.brand_ws / "uk"
        config = bs.read(self.uk / "reporting" / "config.json")
        bs.write_json(self.uk / "reporting" / "config.json", {**config, "reference_shop": "eu"})
        eu_data = self.brand_ws / "eu" / "reporting" / "data"
        # Ein älterer EU-Lauf und ein neuerer: verglichen wird mit dem neuesten.
        bs.write_json(eu_data / "2026-09-01-audit" / "shop-tech.json", shop_tech(["alt.test"], "eu.beispielmarke.test"))
        bs.write_json(eu_data / "2026-10-01" / "shop-tech.json",
                      shop_tech(["widget.trustpilot.com"], "eu.beispielmarke.test"))
        bs.write_json(eu_data / "2026-10-01" / "crawl.json", crawl(["legal-notice", "privacy-policy"], ["Product"]))
        bs.write_json(eu_data / "2026-10-01" / "catalog.json", catalog(product("rad", ["S-1"])))
        theme(self.brand_ws / "eu" / "migration" / "snapshots" / "2026-11-01-1",
              settings={"sticky_cart": True},
              sections={"main": {"type": "main-product", "settings": {"show_badge": True}}})
        uk_data = self.uk / "reporting" / "data" / RUN
        bs.write_json(uk_data / "shop-tech.json", shop_tech([], "uk.beispielmarke.test"))
        bs.write_json(uk_data / "crawl.json", crawl(["privacy-policy"], ["Product"]))
        bs.write_json(uk_data / "catalog.json", catalog(product("bike", ["S-1"], seo_description=False)))
        theme(self.uk / "migration" / "snapshots" / "2026-11-10-2",
              settings={"sticky_cart": False},
              sections={"main": {"type": "main-product", "settings": {"show_badge": True}}})

    def test_compare_and_findings(self):
        target = consistency.run_compare(self.uk, RUN)
        doc = bs.read(target)
        keys = {d["key"] for d in doc["deviations"]}
        self.assertEqual(keys, {"theme_settings", "apps", "legal", "seo_description"})
        self.assertIn("2026-10-01", doc["reference_snapshots"]["shop-tech.json"])
        apps = next(d for d in doc["deviations"] if d["key"] == "apps")
        self.assertNotIn("alt.test", json.dumps(apps))

        with self.assertRaisesRegex(consistency.ConsistencyError, "Recht"):
            consistency.run_findings(self.uk, RUN, {})
        out = consistency.run_findings(self.uk, RUN, {"legal": "Ein Impressum verlangt UK nicht."})
        findings = bs.read(out)
        self.assertEqual(findings["discipline"], "consistency")
        statements = [f["statement"] for f in findings["findings"]]
        self.assertTrue(all(s.startswith("Abweichung zu EU: ") for s in statements))
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(len(s) <= 90 for s in statements))
        self.assertEqual([f["id"] for f in findings["findings"]], ["ABW-01", "ABW-02", "ABW-03"])
        self.assertEqual(bs.read(target)["dropped"], {"legal": "Ein Impressum verlangt UK nicht."})

    def test_a_drop_needs_a_reason(self):
        consistency.run_compare(self.uk, RUN)
        with self.assertRaisesRegex(consistency.ConsistencyError, "ohne Grund"):
            consistency.run_findings(self.uk, RUN, {"legal": " "})

    def test_keep_law_keeps_the_legal_finding(self):
        consistency.run_compare(self.uk, RUN)
        findings = bs.read(consistency.run_findings(self.uk, RUN, {}, keep_law=True))
        self.assertEqual(len(findings["findings"]), 4)

    def test_measures_accept_the_discipline(self):
        from audit import measures
        self.assertIn(consistency.DISCIPLINE, measures.LABELS["discipline"])


if __name__ == "__main__":
    unittest.main()
