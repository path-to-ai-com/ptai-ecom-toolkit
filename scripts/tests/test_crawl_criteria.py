"""Die Crawl-Blöcke der Kriterienliste vom 27.09.2026.

Zwei Läufe desselben Moduls auf demselben Shop hatten nur einen Teil ihrer
Befunde gemeinsam, obwohl die Daten für die übrigen in beiden Snapshots
standen. Die Zählregel steht deshalb im Crawl-Index statt in einer Abfrage,
die der Agent pro Lauf neu schreibt. Diese Tests halten die Zählregeln fest,
vor allem die Grundgesamtheit: kanonische, indexierbare Seiten, jede Adresse
einmal.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "skills" / "crawl-site" / "scripts"))
import crawl  # noqa: E402
import render_check  # noqa: E402


def page(url, **kw):
    """Eine erfolgreich geparste Seite. `indexable` markiert sie als solche."""
    base = {"url": url, "status": 200, "indexable": True, "click_depth": 1,
            "title": "", "description": "", "canonical": url, "canonical_count": 1,
            "h1": ["Titel"], "hreflang": {}, "schema_types": [], "internal_links": [],
            "markup": {}}
    base.update(kw)
    return base


def ldjson(*blocks):
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(b)}</script>'
                      for b in blocks)
    return f"<html><head>{scripts}</head><body><h1>x</h1></body></html>"


class TestProductMarkup(unittest.TestCase):
    def test_reads_the_merchant_listing_fields(self):
        markup = crawl.parse_page(ldjson({
            "@type": "Product", "name": "Ring", "image": "https://s.de/r.jpg",
            "brand": {"@type": "Brand", "name": "Beispielshop"}, "sku": "R-1",
            "offers": {"@type": "Offer", "price": "49.90", "priceCurrency": "EUR",
                       "availability": "https://schema.org/InStock"},
        }), "https://s.de/products/ring")["markup"]["product"]
        self.assertTrue(markup["has_name"] and markup["has_image"] and markup["has_brand"])
        self.assertTrue(markup["has_identifier"] and markup["has_offers"])
        self.assertEqual((markup["price"], markup["currency"], markup["availability"]),
                         ("49.90", "EUR", "InStock"))
        self.assertFalse(markup["has_shipping_details"])
        self.assertFalse(markup["has_return_policy"])

    def test_takes_the_offer_from_the_first_variant_of_a_product_group(self):
        markup = crawl.parse_page(ldjson({
            "@type": "ProductGroup", "name": "Ring",
            "hasVariant": [{"@type": "Product", "gtin13": "4000000000000",
                            "offers": {"price": 20, "priceCurrency": "EUR"}}],
        }), "https://s.de/products/ring")["markup"]["product"]
        self.assertTrue(markup["has_offers"])
        self.assertTrue(markup["has_identifier"])
        self.assertTrue(markup["has_variants"])
        self.assertEqual(markup["price"], "20")

    def test_reads_price_from_price_specification(self):
        markup = crawl.parse_page(ldjson({
            "@type": "Product", "name": "Ring",
            "offers": {"priceSpecification": {"price": "9.00", "priceCurrency": "EUR"}},
        }), "https://s.de/p")["markup"]["product"]
        self.assertEqual((markup["price"], markup["currency"]), ("9.00", "EUR"))

    def test_products_nested_in_an_item_list_are_not_the_page_product(self):
        # Eine Kategorieseite listet ihre Produkte als ItemList. Das ist keine
        # Produktauszeichnung der Seite; sonst trüge jede Kategorie scheinbar
        # ein Produkt-Schema.
        result = crawl.parse_page(ldjson({
            "@type": "ItemList",
            "itemListElement": [{"@type": "ListItem", "item": {"@type": "Product", "name": "A"}}],
        }), "https://s.de/collections/ringe")
        self.assertNotIn("product", result["markup"])

    def test_two_product_nodes_merge_and_are_counted(self):
        markup = crawl.parse_page(ldjson(
            {"@type": "Product", "name": "Ring"},
            {"@type": "Product", "offers": {"price": "5", "priceCurrency": "EUR"},
             "aggregateRating": {"ratingValue": 4.8}},
        ), "https://s.de/p")["markup"]["product"]
        self.assertEqual(markup["count"], 2)
        self.assertTrue(markup["has_name"] and markup["has_offers"] and markup["has_aggregate_rating"])

    def test_broken_json_ld_is_ignored_not_raised(self):
        html = '<html><head><script type="application/ld+json">{"@type": "Product",</script></head></html>'
        self.assertEqual(crawl.parse_page(html, "https://s.de/")["markup"], {})

    def test_organization_with_global_policies_and_same_as(self):
        org = crawl.parse_page(ldjson({"@graph": [{
            "@type": "Organization", "logo": "https://s.de/l.png",
            "sameAs": ["https://instagram.com/x", "https://facebook.com/x"],
            "hasMerchantReturnPolicy": {"@type": "MerchantReturnPolicy"},
            "hasShippingService": {"@type": "ShippingService"},
        }]}), "https://s.de/")["markup"]["organization"]
        self.assertEqual(org, {"has_logo": True, "same_as": 2,
                               "has_shipping_service": True, "has_return_policy": True})

    def test_json_ld_inside_a_template_does_not_count(self):
        html = ('<html><body><template><script type="application/ld+json">'
                '{"@type": "Product", "name": "x"}</script></template></body></html>')
        self.assertEqual(crawl.parse_page(html, "https://s.de/")["markup"], {})


class TestCanonicalPopulation(unittest.TestCase):
    def test_collection_scoped_product_urls_are_not_counted_twice(self):
        pages = [
            page("https://s.de/products/ring", description="Gleich"),
            page("https://s.de/collections/ringe/products/ring", description="Gleich",
                 canonical="https://s.de/products/ring"),
        ]
        idx = crawl.build_findings_index(pages)
        self.assertEqual(idx["canonical_pages"], 1)
        self.assertEqual(idx["descriptions"]["duplicate_groups"]["count"], 0)

    def test_a_redirect_and_its_target_are_one_page(self):
        pages = [
            page("https://s.de/products/alt", end_url="https://s.de/products/neu",
                 canonical="https://s.de/products/neu", description="Gleich"),
            page("https://s.de/products/neu", description="Gleich"),
        ]
        idx = crawl.build_findings_index(pages)
        self.assertEqual(idx["canonical_pages"], 1)
        self.assertEqual(idx["descriptions"]["duplicate_groups"]["pages"], 0)

    def test_home_with_and_without_slash_counts_once(self):
        pages = [page("https://s.de", canonical="https://s.de/", click_depth=0),
                 page("https://s.de/", click_depth=0)]
        self.assertEqual(crawl.build_findings_index(pages)["canonical_pages"], 1)

    def test_following_pages_of_a_list_count_once(self):
        # Seite 2 und 3 tragen dieselbe H1 und Description wie Seite 1. Eine
        # fehlende Description der Kategorie ist ein Mangel, nicht drei.
        pages = [page("https://s.de/collections/ketten", description="")]
        pages += [page(f"https://s.de/collections/ketten?page={n}", description="",
                       canonical=f"https://s.de/collections/ketten?page={n}")
                  for n in (2, 3)]
        idx = crawl.build_findings_index(pages)
        self.assertEqual(idx["canonical_pages"], 1)
        self.assertEqual(idx["descriptions"]["missing"]["count"], 1)
        self.assertEqual(idx["pagination"]["count"], 2)
        self.assertEqual(idx["pagination"]["canonical_to_first_page"]["count"], 0)

    def test_non_indexable_pages_are_outside_the_population(self):
        idx = crawl.build_findings_index([page("https://s.de/a", indexable=False, h1=[])])
        self.assertEqual(idx["canonical_pages"], 0)
        self.assertEqual(idx["h1"]["missing"]["count"], 0)


class TestContentBlocks(unittest.TestCase):
    def test_h1_multiple_and_missing(self):
        idx = crawl.build_findings_index([
            page("https://s.de/a", h1=["x", "y"]),
            page("https://s.de/b", h1=[]),
            page("https://s.de/c"),
        ])
        self.assertEqual(idx["h1"]["multiple"]["count"], 1)
        self.assertEqual(idx["h1"]["missing"]["examples"], ["https://s.de/b"])

    def test_title_length_uses_the_stated_maximum(self):
        idx = crawl.build_findings_index([
            page("https://s.de/a", title="x" * 61),
            page("https://s.de/b", title="x" * 60),
        ])
        self.assertEqual(idx["titles"]["too_long"]["count"], 1)
        self.assertEqual(idx["titles"]["too_long"]["max_chars"], 60)

    def test_duplicate_descriptions_report_group_size_and_page_total(self):
        idx = crawl.build_findings_index([
            page(f"https://s.de/{i}", description="Startseitentext") for i in range(3)
        ] + [page("https://s.de/x", description="Eigen")])
        groups = idx["descriptions"]["duplicate_groups"]
        self.assertEqual((groups["count"], groups["pages"]), (1, 3))
        self.assertEqual(groups["groups"][0]["count"], 3)

    def test_missing_description_counts_whitespace_as_missing(self):
        idx = crawl.build_findings_index([page("https://s.de/a", description="   ")])
        self.assertEqual(idx["descriptions"]["missing"]["count"], 1)


class TestNonCanonicalLinks(unittest.TestCase):
    def test_counts_linked_pages_that_canonicalise_elsewhere(self):
        idx = crawl.build_findings_index([
            page("https://s.de/products/ring"),
            page("https://s.de/collections/ringe/products/ring",
                 canonical="https://s.de/products/ring"),
            page("https://s.de/sitemap-only", canonical="https://s.de/x", click_depth=None),
        ])
        block = idx["non_canonical_linked"]
        self.assertEqual(block["count"], 1)
        self.assertEqual(block["collection_product_urls"], 1)
        self.assertEqual(block["share_of_crawl"], round(1 / 3, 4))


class TestPagination(unittest.TestCase):
    def test_canonical_to_the_first_page_is_counted(self):
        idx = crawl.build_findings_index([
            page("https://s.de/collections/ringe?page=2", canonical="https://s.de/collections/ringe"),
            page("https://s.de/collections/ketten?page=2"),
        ])
        self.assertEqual(idx["pagination"]["count"], 2)
        self.assertEqual(idx["pagination"]["canonical_to_first_page"]["count"], 1)

    def test_no_pagination_yields_zeros(self):
        self.assertEqual(crawl.build_findings_index([page("https://s.de/")])["pagination"]["count"], 0)


class TestHreflang(unittest.TestCase):
    def test_self_reference_ignores_the_trailing_slash_of_the_home(self):
        idx = crawl.build_findings_index([
            page("https://s.de/", hreflang={"de": "https://s.de", "x-default": "https://s.de"}),
        ])
        self.assertEqual(idx["hreflang"]["missing_self_reference"]["count"], 0)
        self.assertEqual(idx["hreflang"]["missing_x_default"]["count"], 0)

    def test_missing_x_default_and_self_reference(self):
        idx = crawl.build_findings_index([
            page("https://s.de/a", hreflang={"en": "https://s.de/en/a"}),
        ])
        self.assertEqual(idx["hreflang"]["missing_x_default"]["count"], 1)
        self.assertEqual(idx["hreflang"]["missing_self_reference"]["count"], 1)

    def test_a_target_never_reached_is_reported_once(self):
        tags = {"de": "https://s.de/a", "en": "https://s.de/en/a"}
        idx = crawl.build_findings_index([
            page("https://s.de/a", hreflang=tags),
            page("https://s.de/b", hreflang={"de": "https://s.de/b", "en": "https://s.de/en/a"}),
        ])
        self.assertEqual(idx["hreflang"]["targets_not_crawled"]["count"], 1)
        self.assertEqual(idx["hreflang"]["targets_not_crawled"]["examples"], ["https://s.de/en/a"])

    def test_a_target_without_return_tag_is_not_reciprocal(self):
        idx = crawl.build_findings_index([
            page("https://s.de/a", hreflang={"de": "https://s.de/a", "en": "https://s.de/en/a"}),
            page("https://s.de/en/a", hreflang={"en": "https://s.de/en/a", "de": "https://s.de/x"}),
        ])
        self.assertEqual(idx["hreflang"]["not_reciprocal"]["count"], 1)

    def test_a_target_that_is_a_404_is_not_indexable(self):
        idx = crawl.build_findings_index([
            page("https://s.de/a", hreflang={"de": "https://s.de/a", "en": "https://s.de/en/a"}),
            {"url": "https://s.de/en/a", "status": 404},
        ])
        self.assertEqual(idx["hreflang"]["targets_not_indexable"]["count"], 1)
        self.assertEqual(idx["hreflang"]["targets_not_crawled"]["count"], 0)


class TestMarkupIndex(unittest.TestCase):
    def test_missing_fields_are_counted_per_field(self):
        full = {"has_name": True, "has_image": True, "has_brand": True, "has_identifier": True,
                "has_offers": True, "price": "1", "currency": "EUR", "availability": "InStock",
                "has_shipping_details": False, "has_return_policy": False, "count": 1}
        idx = crawl.build_findings_index([
            page("https://s.de/products/a", markup={"product": full}),
            page("https://s.de/products/b", markup={"product": {**full, "has_brand": False,
                                                              "price": None, "count": 2}}),
        ])
        block = idx["product_markup"]
        self.assertEqual(block["pages"], 2)
        self.assertEqual(block["missing"]["has_brand"]["count"], 1)
        self.assertEqual(block["missing"]["price"]["count"], 1)
        self.assertEqual(block["missing"]["has_shipping_details"]["count"], 2)
        self.assertEqual(block["multiple_nodes"]["count"], 1)
        self.assertEqual(block["availability"], {"InStock": 2})

    def test_organization_block_names_the_home(self):
        org = {"has_logo": True, "same_as": 3, "has_shipping_service": False,
               "has_return_policy": True}
        idx = crawl.build_findings_index([
            page("https://s.de/", click_depth=0, markup={"organization": org}),
            page("https://s.de/a"),
        ])
        block = idx["organization_markup"]
        self.assertEqual(block["home_url"], "https://s.de/")
        self.assertEqual(block["home"], org)
        self.assertEqual((block["with_return_policy"], block["with_shipping_service"]), (1, 0))

    def test_an_old_snapshot_without_markup_yields_zero_pages(self):
        pages = [page("https://s.de/")]
        del pages[0]["markup"]
        self.assertEqual(crawl.build_findings_index(pages)["product_markup"]["pages"], 0)


class TestRenderCheck(unittest.TestCase):
    """Die Vergleichslogik der gerenderten Gegenprobe, ohne Browser."""

    def test_json_ld_added_by_javascript_is_only_rendered(self):
        static = page("https://s.de/products/a", schema_types=["Product"],
                      markup={"product": {"has_name": True, "has_aggregate_rating": False, "count": 1}})
        rendered = ldjson({"@type": "Product", "name": "A",
                           "aggregateRating": {"ratingValue": 4.9}})
        row = render_check.compare("https://s.de/products/a", static, rendered)
        self.assertEqual(row["verdict"], "only_rendered")

    def test_same_markup_is_same(self):
        html = ldjson({"@type": "Product", "name": "A"})
        static = crawl.parse_page(html, "https://s.de/p")
        self.assertEqual(render_check.compare("https://s.de/p", static, html)["verdict"], "same")

    def test_no_dom_means_nothing_was_checked(self):
        self.assertEqual(render_check.compare("https://s.de/p", {}, None)["verdict"], "render_failed")


if __name__ == "__main__":
    unittest.main()
