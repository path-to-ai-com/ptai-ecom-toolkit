"""Horizon-Grundpaket: Snippets mit Projektpräfix ins Ziel-Repo, Eingriffe danach geprüft."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import horizon_base as hb  # noqa: E402

EXPECTED = {"beispiel-product-structured-data.liquid", "beispiel-hreflang.liquid",
            "beispiel-og-image-fallback.liquid", "beispiel-website-structured-data.liquid"}


class TestPackage(unittest.TestCase):
    def test_vier_snippets_mit_doku_ohne_gedankenstriche(self):
        files = hb.snippets()
        self.assertEqual(set(files), EXPECTED)
        for name, text in files.items():
            self.assertTrue(text.lstrip().startswith("{%- doc -%}"), name)
            self.assertNotRegex(text, r"[–—]", name)

    def test_produkt_snippet_traegt_beschreibung_je_variante_und_bewertung(self):
        text = hb.snippets()["beispiel-product-structured-data.liquid"]
        variants = text.split('"hasVariant"', 1)[1]
        self.assertIn('"description"', variants)
        self.assertIn("reviews.rating", text)
        self.assertIn("reviews.rating_count", text)
        self.assertIn('"aggregateRating"', text)


class TestInstallAndCheck(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        for folder in ("sections", "snippets", "layout"):
            (self.repo / folder).mkdir()
        (self.repo / "sections" / "product-information.liquid").write_text(
            '<script type="application/ld+json">\n  {{ closest.product | structured_data }}\n</script>\n')
        (self.repo / "snippets" / "meta-tags.liquid").write_text("{%- liquid\n  assign og_type = 'website'\n-%}\n")
        (self.repo / "layout" / "theme.liquid").write_text("<head>{%- render 'meta-tags' -%}</head>\n")

    def test_installiert_mit_praefix_und_ueberschreibt_nichts_ohne_force(self):
        result = hb.install(self.repo, "shop")
        self.assertEqual(len(result["written"]), 4)
        text = (self.repo / "snippets" / "shop-hreflang.liquid").read_text()
        self.assertIn("render 'shop-hreflang'", text)
        self.assertNotRegex(text, r"\bbeispiel-")
        self.assertEqual(hb.install(self.repo, "shop")["unchanged"], sorted(result["written"]))
        (self.repo / "snippets" / "shop-hreflang.liquid").write_text("eigene Fassung")
        self.assertEqual(hb.install(self.repo, "shop")["kept"], ["shop-hreflang.liquid"])
        self.assertEqual((self.repo / "snippets" / "shop-hreflang.liquid").read_text(), "eigene Fassung")
        self.assertIn("shop-hreflang.liquid", hb.install(self.repo, "shop", force=True)["written"])

    def test_check_meldet_fehlende_eingriffe_und_verbliebenes_structured_data(self):
        hb.install(self.repo, "shop")
        findings = hb.check(self.repo, "shop")
        self.assertEqual(len([f for f in findings if "Eingriff fehlt" in f]), 5)
        self.assertTrue(any("structured_data steht noch" in f for f in findings))
        (self.repo / "sections" / "product-information.liquid").write_text(
            "{%- comment -%} shop: eigenes JSON-LD {%- endcomment -%}\n"
            "{% render 'shop-product-structured-data', product: closest.product %}\n")
        (self.repo / "snippets" / "meta-tags.liquid").write_text(
            "{%- liquid\n  elsif request.page_type == 'collection'\n    assign og_type = 'product.group'\n-%}\n"
            "{%- else -%}{%- render 'shop-og-image-fallback' -%}\n")
        (self.repo / "layout" / "theme.liquid").write_text(
            "<head>{%- render 'meta-tags' -%}{%- render 'shop-website-structured-data' -%}</head>\n")
        self.assertEqual(hb.check(self.repo, "shop", with_hreflang=False), [])
        self.assertEqual(hb.check(self.repo, "shop"),
                         ["layout/theme.liquid: Eingriff fehlt (hreflang aus den veröffentlichten Sprachen)"])

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = hb.main(["install", "--target-repo", str(self.repo), "--prefix", "shop"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out.getvalue())["written"]), 4)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hb.main(["check", "--target-repo", str(self.repo), "--prefix", "Shop_"]), 2)
            self.assertEqual(hb.main(["check", "--target-repo", str(self.repo), "--prefix", "shop"]), 1)


if __name__ == "__main__":
    unittest.main()
