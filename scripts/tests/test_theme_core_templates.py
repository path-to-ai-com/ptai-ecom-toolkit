"""Template-Nutzung: lebende Templates aus den Zuweisungen, nie aus der Dateiliste."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import templates  # noqa: E402


def shop_with_assignments() -> fake.FakeShop:
    shop = fake.shop_with_live()
    shop.suffixes = {
        "products": [None] * 300 + ["beispiel"] * 4 + ["verschwunden"] * 2,
        "collections": [""] * 3,
        "pages": [None, "kontakt"],
        "blogs": [],
        "articles": [None],
    }
    return shop


class TestNamen(unittest.TestCase):
    def test_typ_suffix_und_markt_aus_dem_dateinamen(self):
        self.assertEqual(templates.parse_template_name("templates/product.beispiel.context.eu.json"),
                         {"type": "product", "suffix": "beispiel", "market": "eu", "key": "product.beispiel"})
        self.assertEqual(templates.parse_template_name("templates/index.json")["key"], "index")
        self.assertEqual(templates.parse_template_name("templates/customers/account.liquid")["type"], "customers/account")
        self.assertIsNone(templates.parse_template_name("sections/hero.liquid"))


class TestNutzung(unittest.TestCase):
    def setUp(self):
        self.result = templates.usage(shop_with_assignments(), fake.FIXTURE)

    def test_objekte_je_template_aus_den_zuweisungen(self):
        t = self.result["templates"]
        self.assertEqual(t["product"]["objects"], 300)
        self.assertEqual(t["product.beispiel"]["objects"], 4)
        self.assertEqual(t["collection"]["objects"], 3)
        self.assertIsNone(t["index"]["objects"], "index kann keinem Objekt zugewiesen werden")

    def test_markt_variante_gehoert_zum_template_und_ist_kein_eigenes(self):
        t = self.result["templates"]
        self.assertEqual(t["product.beispiel"]["markets"], ["eu"])
        self.assertEqual(t["product.beispiel"]["file"], "templates/product.beispiel.json")
        self.assertNotIn("product.beispiel.context.eu", t)

    def test_zuweisung_ohne_datei_wird_gemeldet(self):
        self.assertEqual(self.result["assigned_without_file"], [
            {"type": "product", "suffix": "verschwunden", "objects": 2},
            {"type": "page", "suffix": "kontakt", "objects": 1},
            {"type": "article", "suffix": "", "objects": 1},
        ])

    def test_datei_ohne_objekt_ist_kein_lebendes_template(self):
        self.assertEqual(self.result["files_without_objects"], ["templates/page.alt.json"])

    def test_paginierung_ueber_alle_objekte(self):
        shop = shop_with_assignments()
        templates.collect_suffixes(shop)
        self.assertEqual(len(shop.ops("ProductTemplates")), 2)

    def test_cli_exit_eins_bei_zuweisung_ohne_datei(self):
        ws = fake.temp_workspace(self)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = templates.main(["usage", "--snapshot", str(fake.FIXTURE), "--out",
                                   str(ws / "migration/inventory/templates.json")], transport=shop_with_assignments())
        self.assertEqual(code, 1)
        summary = json.loads(out.getvalue())
        self.assertEqual(summary["assigned_without_file"], 3)
        saved = json.loads((ws / "migration/inventory/templates.json").read_text())
        self.assertIn("product.beispiel", saved["templates"])


if __name__ == "__main__":
    unittest.main()
