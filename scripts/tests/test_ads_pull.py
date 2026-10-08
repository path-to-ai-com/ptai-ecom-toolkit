"""Abfragen und Auswertung von pull-ads. Kein Test ruft die API."""
import sys
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / "skills"
sys.path.insert(0, str(SKILLS / "pull-ads" / "scripts"))
import ads_pull  # noqa: E402


def row(date_, cost_micros, conversions=0.0, name="Brand DE", impressions="100",
        clicks="10", value=0.0, share=0.7):
    return {
        "campaign": {"id": "1", "name": name, "status": "ENABLED",
                      "advertisingChannelType": "SEARCH"},
        "metrics": {"impressions": impressions, "clicks": clicks,
                     "costMicros": str(cost_micros), "conversions": conversions,
                     "conversionsValue": value,
                     "searchImpressionShare": share,
                     "searchBudgetLostImpressionShare": 0.1,
                     "searchRankLostImpressionShare": 0.2},
        "segments": {"date": date_},
    }


class TestQueries(unittest.TestCase):
    def test_dates_are_quoted_in_the_where_clause(self):
        self.assertIn("BETWEEN '2026-01-01' AND '2026-08-31'",
                      ads_pull.query_campaigns("2026-01-01", "2026-08-31"))

    def test_campaign_query_asks_for_the_three_impression_share_metrics(self):
        query = ads_pull.query_campaigns("2026-01-01", "2026-08-31")
        for field in ("metrics.search_impression_share",
                      "metrics.search_budget_lost_impression_share",
                      "metrics.search_rank_lost_impression_share"):
            self.assertIn(field, query)

    def test_campaign_query_segments_by_date(self):
        # Ohne segments.date gibt es keine Monatsreihe, und die Baseline
        # verlangt Ausgaben je Monat.
        self.assertIn("segments.date", ads_pull.query_campaigns("a", "b"))

    def test_search_term_query_uses_the_search_term_view(self):
        self.assertIn("FROM search_term_view", ads_pull.query_search_terms("a", "b"))

    def test_history_probe_starts_far_before_any_account(self):
        # Der Historienanfang wird gemessen wie bei GSC und GA4, nicht
        # angenommen. Ein zu später Start kürzte die Baseline still.
        self.assertIn("'2010-01-01'", ads_pull.query_history())

    def test_customer_query_asks_for_the_currency(self):
        # Ein Betrag ohne Währung ist keine Zahl. Ein Euro-Betrag aus einem
        # Konto in Franken fällt niemandem auf.
        self.assertIn("customer.currency_code", ads_pull.query_customer())


class TestMonthly(unittest.TestCase):
    def test_aggregates_days_into_months(self):
        months = ads_pull.by_month([row("2026-08-01", 10_000_000),
                                     row("2026-08-30", 5_000_000),
                                     row("2026-09-02", 1_000_000)])
        self.assertEqual([m["month"] for m in months], ["2026-08", "2026-09"])
        self.assertAlmostEqual(months[0]["cost"], 15.0)

    def test_months_are_sorted_and_zero_padded(self):
        months = ads_pull.by_month([row("2026-10-01", 1), row("2026-09-01", 1)])
        self.assertEqual([m["month"] for m in months], ["2026-09", "2026-10"])

    def test_roas_is_value_over_cost(self):
        months = ads_pull.by_month([row("2026-08-01", 100_000_000,
                                         conversions=4.0, value=400.0)])
        self.assertAlmostEqual(months[0]["roas"], 4.0)

    def test_roas_without_cost_is_none_not_infinite(self):
        # Ein Monat ohne Ausgaben hat keinen ROAS. Eine 0 läse sich als
        # "nichts eingebracht", eine Division wäre ein Absturz.
        months = ads_pull.by_month([row("2026-08-01", 0, conversions=1.0, value=50.0)])
        self.assertIsNone(months[0]["roas"])

    def test_impression_share_is_impressions_over_eligible_impressions(self):
        # Ein Share ist ein Anteil an den möglichen Impressionen. 1000 bei 0,9
        # heißt rund 1111 möglich, 10 bei 0,1 heißt 100 möglich.
        rows = [row("2026-08-01", 1, impressions="1000", share=0.9),
                row("2026-08-02", 1, impressions="10", share=0.1)]
        self.assertAlmostEqual(ads_pull.by_month(rows)[0]["search_impression_share"],
                               1010 / (1000 / 0.9 + 10 / 0.1), places=4)

    def test_rows_without_a_share_do_not_dilute_it(self):
        # Am 02.10.2026 ergab ein Tag, an dem Google den Share noch nicht
        # geliefert hatte, 2 Prozent, weil alle Impressionen im Nenner standen.
        with_share = row("2026-08-01", 1, impressions="100", share=0.5)
        without = row("2026-08-01", 1, impressions="9900")
        for field in ("searchImpressionShare", "searchBudgetLostImpressionShare",
                      "searchRankLostImpressionShare"):
            del without["metrics"][field]
        month = ads_pull.by_month([with_share, without])[0]
        self.assertAlmostEqual(month["search_impression_share"], 0.5)
        self.assertAlmostEqual(month["search_impression_share_coverage"], 0.01)

    def test_lost_shares_are_weighted_by_eligible_impressions(self):
        rows = [row("2026-08-01", 1, impressions="100", share=0.5),
                row("2026-08-02", 1, impressions="100", share=1.0)]
        rows[0]["metrics"]["searchBudgetLostImpressionShare"] = 0.4
        rows[1]["metrics"]["searchBudgetLostImpressionShare"] = 0.0
        # möglich: 200 und 100, also 0,4 * 200 / 300
        self.assertAlmostEqual(
            ads_pull.by_month(rows)[0]["search_budget_lost_impression_share"],
            0.4 * 200 / 300, places=4)

    def test_month_without_impressions_has_no_share(self):
        # Keine Impressionen heisst kein Impression Share. Eine 0 stünde im
        # Report als "nie ausgeliefert", und das ist etwas anderes.
        rows = [row("2026-08-01", 0, impressions="0")]
        self.assertIsNone(ads_pull.by_month(rows)[0]["search_impression_share"])

    def test_row_without_a_date_is_skipped(self):
        broken = row("2026-08-01", 1)
        broken["segments"] = {}
        self.assertEqual(ads_pull.by_month([broken]), [])


class TestWaste(unittest.TestCase):
    def term(self, text, cost_micros, conversions=0.0, clicks="5"):
        return {"searchTermView": {"searchTerm": text}, "campaign": {"name": "Generisch"},
                "metrics": {"costMicros": str(cost_micros), "conversions": conversions,
                             "clicks": clicks, "impressions": "50"}}

    def test_sums_cost_of_terms_without_conversions(self):
        shaped = ads_pull.shape_search_terms([
            self.term("gratis muster", 30_000_000),
            self.term("brand kaufen", 10_000_000, conversions=3.0)])
        self.assertAlmostEqual(shaped["summary_search_terms"]["cost_without_conversion"], 30.0)
        self.assertEqual(shaped["summary_search_terms"]["terms_without_conversion"], 1)

    def test_terms_are_sorted_by_wasted_cost(self):
        shaped = ads_pull.shape_search_terms([self.term("klein", 1_000_000),
                                               self.term("gross", 50_000_000)])
        self.assertEqual(shaped["search_terms_without_conversion"][0]["term"], "gross")

    def test_list_is_capped_but_the_sum_is_complete(self):
        terms = [self.term(f"t{i}", 1_000_000) for i in range(ads_pull.MAX_TERMS + 50)]
        shaped = ads_pull.shape_search_terms(terms)
        self.assertEqual(len(shaped["search_terms_without_conversion"]), ads_pull.MAX_TERMS)
        self.assertTrue(shaped["search_terms_truncated"])
        self.assertAlmostEqual(shaped["summary_search_terms"]["cost_without_conversion"],
                               (ads_pull.MAX_TERMS + 50) * 1.0)

    def test_cost_total_covers_all_terms(self):
        # Die Bezugsgröße für den Anteil ohne Conversion. Gegen die
        # Gesamtausgaben gerechnet, Performance Max eingeschlossen, sähe die
        # Verschwendung kleiner aus, als sie ist.
        shaped = ads_pull.shape_search_terms([
            self.term("ohne", 30_000_000),
            self.term("mit", 70_000_000, conversions=2.0)])
        self.assertAlmostEqual(shaped["summary_search_terms"]["cost_total"], 100.0)

    def test_fractional_conversions_count_as_converted(self):
        # Google zählt Conversions als Bruchteile. 0,5 ist eine Conversion,
        # keine Verschwendung.
        shaped = ads_pull.shape_search_terms([self.term("halb", 10_000_000, conversions=0.5)])
        self.assertEqual(shaped["summary_search_terms"]["terms_without_conversion"], 0)


class TestHistory(unittest.TestCase):
    def test_detail_period_is_the_last_twelve_full_months(self):
        from datetime import date
        self.assertEqual(ads_pull.detail_period(date(2026, 10, 2)),
                         ("2025-10-01", "2026-09-30"))
        self.assertEqual(ads_pull.detail_period(date(2026, 1, 15)),
                         ("2025-01-01", "2025-12-31"))

    def test_history_start_is_the_earliest_day_with_data(self):
        self.assertEqual(ads_pull.history_start([row("2024-03-11", 1), row("2023-11-02", 1)]),
                         "2023-11-02")

    def test_no_rows_means_no_history(self):
        self.assertIsNone(ads_pull.history_start([]))


class TestCampaigns(unittest.TestCase):
    def test_campaigns_are_aggregated_over_the_period(self):
        rows = [row("2026-08-01", 10_000_000, name="Brand DE"),
                row("2026-09-01", 5_000_000, name="Brand DE"),
                row("2026-08-01", 2_000_000, name="Generisch DE")]
        campaigns = ads_pull.shape_campaigns(rows)["campaigns"]
        by_name = {c["name"]: c for c in campaigns}
        self.assertAlmostEqual(by_name["Brand DE"]["cost"], 15.0)
        self.assertAlmostEqual(by_name["Generisch DE"]["cost"], 2.0)

    def test_campaigns_are_sorted_by_cost(self):
        rows = [row("2026-08-01", 1_000_000, name="klein"),
                row("2026-08-01", 90_000_000, name="gross")]
        self.assertEqual(ads_pull.shape_campaigns(rows)["campaigns"][0]["name"], "gross")


def landing(campaign_id, name, url, clicks, cost_micros, month="2026-01-01"):
    return {"campaign": {"id": campaign_id, "name": name}, "segments": {"month": month},
            "landingPageView": {"unexpandedFinalUrl": url},
            "metrics": {"clicks": str(clicks), "costMicros": str(cost_micros),
                        "conversions": 0, "conversionsValue": 0}}


class TestShopFilter(unittest.TestCase):
    """Ein Werbekonto für mehrere Stores: nur die Kampagnen dieses Shops.

    Das Merkmal ist die Ziel-Domain, nicht das Land. Am 07.10.2026 an einem
    echten Konto: die Kampagnen für ein Land landeten auf einem anderen Store.
    """

    SHOP = ["eu.beispielshop.test"]

    def test_without_filter_the_queries_are_unchanged(self):
        self.assertNotIn("campaign.id IN", ads_pull.query_campaigns("2026-01-01", "2026-01-31"))
        self.assertEqual(ads_pull.campaign_condition(None), "")

    def test_every_query_carries_the_campaign_filter(self):
        for query in (ads_pull.query_campaigns("2026-01-01", "2026-01-31", ["11", "12"]),
                      ads_pull.query_ad_groups("2026-01-01", "2026-01-31", ["11", "12"]),
                      ads_pull.query_search_terms("2026-01-01", "2026-01-31", ["11", "12"])):
            with self.subTest(query=query[:40]):
                self.assertTrue(query.endswith(" AND campaign.id IN (11, 12)"))

    def test_campaign_ids_must_be_numbers(self):
        with self.assertRaises(ValueError):
            ads_pull.campaign_condition(["11) OR (1=1"])

    def test_campaigns_count_with_the_share_that_lands_on_the_shop(self):
        rows = [landing("11", "DE Shopping", "https://eu.beispielshop.test/p", 100, 50_000_000),
                landing("12", "UK PMax", "https://beispielshop.test/p", 95, 40_000_000),
                landing("12", "UK PMax", "https://eu.beispielshop.test/p", 5, 2_000_000),
                landing("13", "Brand DE", "https://eu.beispielshop.test/", 80, 8_000_000),
                landing("13", "Brand DE", "https://beispielshop.test/all", 20, 2_000_000)]
        scope = ads_pull.assign_campaigns(rows, self.SHOP)
        self.assertEqual(set(scope["shares"]), {"11", "13"})
        self.assertEqual(scope["shares"]["13"]["months"], {"2026-01": 0.8})
        self.assertEqual(scope["cost_on_shop"], 58.0)
        self.assertEqual(scope["cost_to_other_stores"], 2.0)
        self.assertEqual(scope["foreign_cost"], 42.0)
        self.assertEqual({c["campaign_id"]: c["assignment"] for c in scope["campaigns"]},
                         {"11": "own", "12": "foreign", "13": "mixed"})

    def test_shares_cut_the_daily_rows_per_month(self):
        shares = {"1": {"overall": 0.5, "months": {"2026-01": 0.8}}}
        rows = [row("2026-01-15", 10_000_000, conversions=2.0, value=100.0),
                row("2026-02-15", 10_000_000, conversions=2.0, value=100.0)]
        cut = ads_pull.apply_shares(rows, shares)
        self.assertEqual([r["metrics"]["costMicros"] for r in cut], [8_000_000, 5_000_000])
        self.assertEqual(cut[0]["metrics"]["conversionsValue"], 80.0)
        self.assertEqual(cut[0]["metrics"]["searchImpressionShare"], 0.7)
        months = ads_pull.by_month(cut)
        self.assertEqual([m["cost"] for m in months], [8.0, 5.0])
        self.assertEqual(ads_pull.apply_shares(rows, {}), [])

    def test_www_belongs_to_the_shop(self):
        rows = [landing("11", "Brand", "https://www.beispielshop.test/", 10, 1_000_000)]
        self.assertEqual(list(ads_pull.assign_campaigns(rows, ["beispielshop.test"])["shares"]),
                         ["11"])


if __name__ == "__main__":
    unittest.main()
