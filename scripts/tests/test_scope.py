"""Der Scope-Check: enthalten GA4, Google Ads und Search Console genau diesen Shop?

Geprüft werden die reinen Funktionen. Die Fälle stammen aus zwei echten
Konten vom 07.10.2026, mit erfundenen Namen: eine Marke mit mehreren Stores
in einer Property und einem Werbekonto, und ein Store, der in viele Länder
verkauft und dessen Käufe in einer Connector-Property ohne Hostnamen stehen.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import scope  # noqa: E402

SHOP = ["eu.beispielshop.test"]


def lpv(campaign_id, name, url, clicks, cost_micros):
    return {"campaign": {"id": campaign_id, "name": name},
            "landingPageView": {"unexpandedFinalUrl": url},
            "metrics": {"clicks": str(clicks), "costMicros": str(cost_micros),
                        "conversions": 1, "conversionsValue": 10}}


def ga4_row(stream, host, sessions, purchases):
    return {"stream_id": stream, "stream_name": "x", "measurement_id": None,
            "host_name": host, "sessions": sessions, "purchases": purchases,
            "purchase_revenue": 0, "included": True}


class TestHosts(unittest.TestCase):
    def test_www_is_the_same_shop_a_subdomain_is_not(self):
        self.assertTrue(scope.is_shop_host("www.beispielshop.test", ["beispielshop.test"]))
        self.assertFalse(scope.is_shop_host("eu.beispielshop.test", ["beispielshop.test"]))

    def test_with_www_adds_both_variants(self):
        self.assertEqual(scope.with_www(["www.beispielshop.test"]),
                         ["beispielshop.test", "www.beispielshop.test"])


class TestShopify(unittest.TestCase):
    def test_domains_and_countries_come_from_the_markets(self):
        data = {"shop": {"primaryDomain": {"host": "eu.beispielshop.test"}, "currencyCode": "EUR"},
                "markets": {"nodes": [
                    {"enabled": True, "regions": {"nodes": [{"code": "DE"}]},
                     "webPresences": {"nodes": [{"domain": None, "subfolderSuffix": "de"}]}},
                    {"enabled": True, "regions": {"nodes": [{"code": "AT"}]},
                     "webPresences": {"nodes": [{"domain": {"host": "beispielshop.at"}}]}},
                    {"enabled": False, "regions": {"nodes": [{"code": "MC"}]},
                     "webPresences": {"nodes": [{"domain": {"host": "beispielshop.mc"}}]}}]}}
        shop = scope.parse_shopify(data)
        self.assertEqual(shop["hosts"], ["eu.beispielshop.test", "beispielshop.at"])
        self.assertEqual(shop["countries"], ["AT", "DE"])
        self.assertEqual(shop["subfolders"], ["de"])


class TestCampaigns(unittest.TestCase):
    """Das Merkmal ist die Ziel-Domain, nicht das Land der Kampagne."""

    def test_campaigns_are_assigned_by_landing_host(self):
        rows = [lpv("1", "DE Shopping", "https://eu.beispielshop.test/p/a", 100, 50_000_000),
                lpv("2", "UK PMax", "https://beispielshop.test/p/a", 95, 40_000_000),
                lpv("2", "UK PMax", "https://eu.beispielshop.test/p/a", 5, 2_000_000),
                lpv("3", "Mixed", "https://eu.beispielshop.test/", 50, 10_000_000),
                lpv("3", "Mixed", "https://us.beispielshop.test/", 50, 10_000_000)]
        result = {c["campaign_id"]: c for c in scope.classify_campaigns(rows, SHOP)}
        self.assertEqual(result["1"]["assignment"], "own")
        self.assertEqual(result["2"]["assignment"], "foreign")
        self.assertEqual(result["3"]["assignment"], "mixed")
        self.assertEqual(result["2"]["cost"], 42.0)
        self.assertEqual(list(result["2"]["hosts"]), ["beispielshop.test", "eu.beispielshop.test"])

    def test_a_campaign_without_clicks_counts_by_cost(self):
        rows = [lpv("1", "Neu", "https://eu.beispielshop.test/", 0, 3_000_000)]
        self.assertEqual(scope.classify_campaigns(rows, SHOP)[0]["assignment"], "own")


class TestHistory(unittest.TestCase):
    def test_first_and_last_month_per_host(self):
        rows = [(["202301", "alt.beispielshop.test"], {"sessions": 10, "ecommercePurchases": 2}),
                (["202310", "alt.beispielshop.test"], {"sessions": 5, "ecommercePurchases": 1}),
                (["202610", "eu.beispielshop.test"], {"sessions": 50, "ecommercePurchases": 3})]
        hosts = {h["host_name"]: h for h in scope.host_history(rows)}
        self.assertEqual((hosts["alt.beispielshop.test"]["first_month"],
                          hosts["alt.beispielshop.test"]["last_month"]), ("2023-01", "2023-10"))
        self.assertEqual(hosts["alt.beispielshop.test"]["purchases"], 3)


class TestProposal(unittest.TestCase):
    def report(self, **sections):
        base = {"shopify": {"hosts": SHOP, "currency": "EUR"}, "config_hosts": SHOP}
        base.update(sections)
        return base

    def test_one_store_in_many_countries_needs_no_filter(self):
        """Kampagnen für mehrere Länder, alle auf dem Store: kein Filter."""
        rows = [lpv("1", "DE", "https://eu.beispielshop.test/", 100, 10_000_000),
                lpv("2", "AT", "https://eu.beispielshop.test/", 50, 5_000_000)]
        result = scope.propose(self.report(
            ga4={"rows": [ga4_row("1", "eu.beispielshop.test", 1000, 20)]},
            ads={"campaigns": scope.classify_campaigns(rows, SHOP)}))
        self.assertFalse(result["needed"])
        self.assertEqual(result["config"], {"shop_hostnames": [], "ga4_stream_ids": []})

    def test_a_shared_property_and_account_need_the_shop_filter(self):
        rows = [lpv("1", "DE", "https://eu.beispielshop.test/", 100, 10_000_000),
                lpv("2", "US", "https://us.beispielshop.test/", 300, 30_000_000)]
        result = scope.propose(self.report(
            ga4={"rows": [ga4_row("1", "eu.beispielshop.test", 1000, 20),
                          ga4_row("1", "us.beispielshop.test", 900, 30),
                          ga4_row("1", "www.eu.beispielshop.test", 3, 0)]},
            ads={"campaigns": scope.classify_campaigns(rows, SHOP)}))
        self.assertTrue(result["needed"])
        self.assertEqual(result["config"]["shop_hostnames"],
                         ["eu.beispielshop.test", "www.eu.beispielshop.test"])
        self.assertEqual(len(result["reasons"]), 2)

    def test_purchases_in_two_streams_propose_the_complete_stream(self):
        tx = {"in_multiple_streams": 30, "by_stream": [
            {"stream_id": "111", "purchases": 100, "transactions": 100, "id_formats": [],
             "multiple_id_formats": False},
            {"stream_id": "222", "purchases": 30, "transactions": 30, "id_formats": [],
             "multiple_id_formats": False}]}
        result = scope.propose(self.report(ga4={"rows": [], "transactions": tx}))
        self.assertEqual(result["config"]["ga4_stream_ids"], ["111"])

    def test_purchases_without_hostname_are_a_warning_and_join_the_filter(self):
        """Ein Connector schreibt Käufe ohne Hostnamen; ein Filter löschte sie."""
        result = scope.propose(self.report(
            ga4={"property_id": "1", "rows": [ga4_row("1", "eu.beispielshop.test", 1000, 5),
                                              ga4_row("1", "(not set)", 50, 80),
                                              ga4_row("1", "us.beispielshop.test", 900, 30)]}))
        self.assertIn("(not set)", result["config"]["shop_hostnames"])
        self.assertTrue(any("ohne Hostnamen" in w for w in result["warnings"]))

    def test_a_silent_old_host_with_weight_is_a_warning(self):
        history = [{"host_name": "alt.beispielshop.test", "first_month": "2022-01",
                    "last_month": "2023-10", "sessions": 9000, "purchases": 500},
                   {"host_name": "andere.test", "first_month": "2022-01",
                    "last_month": "2023-10", "sessions": 200, "purchases": 1},
                   {"host_name": "eu.beispielshop.test", "first_month": "2023-11",
                    "last_month": "2026-10", "sessions": 9000, "purchases": 500}]
        result = scope.propose(self.report(ga4={"rows": [], "history": history}))
        old = [w for w in result["warnings"] if "seitdem still" in w]
        self.assertEqual(len(old), 1)
        self.assertIn("alt.beispielshop.test", old[0])

    def test_an_uncovering_search_console_property_is_no_filter_reason(self):
        result = scope.propose(self.report(gsc={"site": "https://beispielshop.test/",
                                                "covered": False,
                                                "hosts": [{"host_name": "beispielshop.test",
                                                           "clicks": 100}]}))
        self.assertFalse(result["needed"])
        self.assertTrue(any("deckt die Shop-Domains nicht ab" in w for w in result["warnings"]))

    def test_different_currencies_are_named(self):
        result = scope.propose(self.report(ga4={"rows": [], "currency": "GBP"},
                                           ads={"campaigns": [], "currency": "GBP"}))
        self.assertTrue(any("Währungen verschieden" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
