"""SEO-Ausgabe im Vergleich: was live da ist und im Entwurf fehlt, ist ein Befund."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import seo_parity as sp  # noqa: E402

FIXTURES = ROOT / "scripts" / "tests" / "fixtures" / "theme" / "seo"
PUBLISHED = {"de", "en"}


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def problems(result: dict, topic: str) -> list:
    return result[topic]["problems"]


class TestParsePage(unittest.TestCase):
    def test_meta_tags_ueber_mehrere_zeilen(self):
        page = sp.parse_page(html("draft-product.html"))
        self.assertEqual(page["lang"], "de")
        self.assertEqual(page["og"]["og:type"], ["product"])
        self.assertEqual(page["og"]["og:image"], ["http://beispielshop.example/cdn/ring.jpg"])
        self.assertEqual(page["canonical"], "https://beispielshop.example/products/beispielring")
        self.assertEqual(page["description"], "Ein erfundener Ring aus Silber.")
        self.assertEqual(page["title"], "Beispielring Silber")

    def test_jsonld_mit_graph_und_kaputtem_block(self):
        text = ('<script type="application/ld+json">{"@graph": [{"@type": "WebSite"}, {"@type": "Organization"}]}'
                '</script><script type="application/ld+json">{kaputt</script>')
        page = sp.parse_page(text)
        self.assertEqual(sp.type_set(page["jsonld"]), {"WebSite", "Organization"})
        self.assertEqual(page["jsonld_errors"], 1)

    def test_hreflang_aus_link_alternate(self):
        page = sp.parse_page(html("live-product.html"))
        self.assertEqual([v for v, _ in page["hreflang"]], ["x-default", "de", "en"])

    def test_produktgruppe_und_produkt_zaehlen_gleich(self):
        live = sp.product_summary(sp.products(sp.parse_page(html("live-product.html"))["jsonld"])[0])
        draft = sp.product_summary(sp.products(sp.parse_page(html("draft-product.html"))["jsonld"])[0])
        self.assertTrue(live["offers"] and live["identifier"] and live["aggregateRating"])
        self.assertFalse(live["is_group"])
        self.assertTrue(draft["is_group"] and draft["offers"] and draft["identifier"])
        self.assertEqual((draft["variants"], draft["variants_without_description"]), (2, 2))
        self.assertFalse(draft["aggregateRating"])


class TestComparePage(unittest.TestCase):
    def test_horizon_entwurf_gegen_altes_theme_auf_der_produktseite(self):
        result = sp.compare_page(html("live-product.html"), html("draft-product.html"), PUBLISHED)
        data = " | ".join(problems(result, "structured_data"))
        self.assertIn("ProductGroup: 2 von 2 Varianten ohne description", data)
        self.assertIn("Produkt ohne aggregateRating (live vorhanden)", data)
        self.assertNotIn("Produkt ohne offers", data)
        self.assertIn("hreflang fehlt ganz", " ".join(problems(result, "hreflang")))
        self.assertEqual(problems(result, "open_graph"), [])
        self.assertEqual(problems(result, "head"), [])
        self.assertIn("Produkt als ProductGroup, live als Product", result["structured_data"]["notes"])

    def test_varianten_ohne_beschreibung_auch_ohne_live_stand(self):
        result = sp.compare_page(None, html("draft-product.html"), PUBLISHED)
        self.assertEqual(problems(result, "structured_data"), ["ProductGroup: 2 von 2 Varianten ohne description"])
        self.assertEqual(problems(result, "hreflang"), [])

    def test_mit_grundpaket_ohne_befund(self):
        result = sp.compare_page(html("live-product.html"), html("fixed-product.html"), PUBLISHED)
        for topic in sp.TOPICS:
            self.assertEqual(problems(result, topic), [], topic)

    def test_kategorie_og_type_und_og_image(self):
        result = sp.compare_page(html("live-collection.html"), html("draft-collection.html"), PUBLISHED)
        og = " | ".join(problems(result, "open_graph"))
        self.assertIn("og:type website, live product.group", og)
        self.assertIn("og:image", og)
        self.assertIn("og:image:secure_url", og)

    def test_startseite_ohne_website(self):
        result = sp.compare_page(html("live-home.html"), html("draft-home.html"), PUBLISHED)
        self.assertIn("WebSite fehlt (live vorhanden)", problems(result, "structured_data"))
        self.assertIn("og:image fehlt (live vorhanden)", problems(result, "open_graph"))

    def test_website_ohne_suchaktion(self):
        draft = html("live-home.html").replace('"potentialAction"', '"unused"')
        result = sp.compare_page(html("live-home.html"), draft, PUBLISHED)
        self.assertIn("WebSite ohne potentialAction (live vorhanden)", problems(result, "structured_data"))

    def test_hreflang_doppelt_unveroeffentlicht_und_gegen_canonical(self):
        live = html("live-product.html")
        draft = live.replace(
            '<link rel="alternate" hreflang="en"',
            '<link rel="alternate" hreflang="fr" href="https://beispielshop.example/fr/products/beispielring">'
            '<link rel="alternate" hreflang="de" href="https://beispielshop.example/products/anders">'
            '<link rel="alternate" hreflang="en"')
        found = " | ".join(problems(sp.compare_page(live, draft, PUBLISHED), "hreflang"))
        self.assertIn("hreflang doppelt: de", found)
        self.assertIn("hreflang auf unveröffentlichte Sprache: fr", found)
        self.assertIn("hreflang de zeigt auf /products/anders", found)

    def test_widerspruch_wie_live_ist_ein_hinweis(self):
        broken = html("live-product.html").replace(
            'hreflang="de" href="https://beispielshop.example/products/beispielring"',
            'hreflang="de" href="https://beispielshop.example/"')
        result = sp.compare_page(broken, broken, PUBLISHED)
        self.assertEqual(problems(result, "hreflang"), [])
        self.assertTrue(any("wie live" in n for n in result["hreflang"]["notes"]))

    def test_canonical_mit_seite_zwei_und_vorschauparametern(self):
        self.assertEqual(sp.url_key("https://b.example/collections/ringe/?page=2&preview_theme_id=1"),
                         "/collections/ringe?page=2")

    def test_doppeltes_produkt_json_ld(self):
        live = html("live-product.html")
        block = live.split('<script type="application/ld+json">')[1].split("</script>")[0]
        draft = live.replace("</head>", f'<script type="application/ld+json">{block}</script></head>')
        self.assertIn("Produkt-JSON-LD 2-mal statt einmal",
                      problems(sp.compare_page(live, draft, PUBLISHED), "structured_data"))

    def test_fehlender_title_und_description(self):
        draft = html("live-home.html").replace("<title>Beispielshop</title>", "").replace(
            '<meta name="description" content="Erfundener Schmuck.">', "")
        self.assertEqual(problems(sp.compare_page(html("live-home.html"), draft, PUBLISHED), "head"),
                         ["title fehlt (live vorhanden)", "meta description fehlt (live vorhanden)"])


class TestComparePages(unittest.TestCase):
    def pairs(self, side="draft"):
        return [{"id": name, "path": path, "template": name, "old_html": html(f"live-{name if name != 'index' else 'home'}.html"),
                 "new_html": html(f"{side}-{name if name != 'index' else 'home'}.html")}
                for name, path in (("index", "/"), ("collection", "/collections/ringe"),
                                   ("product", "/products/beispielring"))]

    def test_abdeckung_je_seitentyp_und_sprache(self):
        result = sp.compare_pages(self.pairs(), PUBLISHED, "de")
        self.assertEqual(result["missing_templates"], [])
        self.assertEqual(result["missing_languages"], ["en"])
        pairs = self.pairs() + [{"id": "product-en", "path": "/en/products/beispielring", "template": "product",
                                 "old_html": None, "new_html": html("fixed-product.html")}]
        result = sp.compare_pages(pairs, PUBLISHED, "de")
        self.assertEqual(result["missing_languages"], [])
        self.assertEqual(result["without_live"], ["/en/products/beispielring"])

    def test_fehlender_seitentyp(self):
        result = sp.compare_pages(self.pairs()[:1], PUBLISHED, "de")
        self.assertEqual(result["missing_templates"], ["collection", "product"])

    def test_seitenliste_um_sprachen_ergaenzen(self):
        pages = {"base_url": "https://beispielshop.example", "pages": [
            {"id": "home", "path": "/", "template": "index", "locale": "de"},
            {"id": "product", "path": "/products/beispielring", "template": "product"},
            {"id": "product-en", "path": "/en/products/beispielring", "template": "product", "locale": "en"}]}
        out = sp.expand_pages(pages, ["de", "en", "fr"])
        paths = {p["id"]: p["path"] for p in out["pages"]}
        self.assertEqual(paths["home-en"], "/en")
        self.assertEqual(paths["home-fr"], "/fr")
        self.assertEqual(paths["product-fr"], "/fr/products/beispielring")
        self.assertEqual(len(out["pages"]), 3 + 3, "product-en gibt es schon, keine Dublette")


class TestCli(unittest.TestCase):
    def test_compare_aus_zwei_mitschnitten(self):
        with tempfile.TemporaryDirectory() as tmp:
            for side, name in (("old", "live-product.html"), ("new", "draft-product.html")):
                folder = Path(tmp) / side
                (folder / "html").mkdir(parents=True)
                (folder / "html" / "product-desktop-1.html").write_text(html(name), encoding="utf-8")
                (folder / "network.json").write_text(json.dumps({"runs": [
                    {"page_id": "product", "path": "/products/beispielring", "template": "product",
                     "device": "desktop", "run": 1, "state": "ok", "html_file": "html/product-desktop-1.html"}]}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = sp.main(["compare", "--old", f"{tmp}/old/network.json", "--new", f"{tmp}/new/network.json",
                                "--locales", "de,en"])
        self.assertEqual(code, 1)
        result = json.loads(out.getvalue())
        self.assertTrue(result["topics"]["structured_data"]["problems"])


if __name__ == "__main__":
    unittest.main()
