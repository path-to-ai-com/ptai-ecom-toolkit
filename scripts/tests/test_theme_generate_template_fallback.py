"""Alternative Templates folgen ihrem Grundtyp; nur zugewiesene Templates mit --living."""
import json
import tempfile
import unittest
from pathlib import Path

from theme import generate


class TemplateFallbackTest(unittest.TestCase):
    def test_grundtyp_eines_alternativen_templates(self):
        self.assertEqual(generate.template_base("collection.sommer"), "collection")
        self.assertEqual(generate.template_base("product.beispiel.context.de"), "product")
        self.assertEqual(generate.template_base("customers/account"), "customers/account")

    def test_ein_alternatives_template_nutzt_den_eintrag_des_grundtyps(self):
        gen = generate.Generator.__new__(generate.Generator)
        gen.mapping = {"templates": {"collection": {"action": "configure"}, "*": {"action": "drop"}}}
        self.assertEqual(gen.lookup("templates", "collection.sommer"), {"action": "configure"})
        self.assertEqual(gen.lookup("templates", "blog.alt"), {"action": "drop"})

    def test_ein_exakter_eintrag_geht_vor_dem_grundtyp(self):
        gen = generate.Generator.__new__(generate.Generator)
        gen.mapping = {"templates": {"page": {"action": "configure"}, "page.contact": {"action": "build"}}}
        self.assertEqual(gen.lookup("templates", "page.contact"), {"action": "build"})

    def test_living_nimmt_zugewiesene_und_typen_ohne_zuweisung(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "templates.json"
            path.write_text(json.dumps({"templates": {
                "collection.sommer": {"objects": 3},
                "collection.alt": {"objects": 0},
                "404": {"objects": None},
            }}), encoding="utf-8")
            self.assertEqual(generate.living_templates(path), {"collection.sommer", "404"})


if __name__ == "__main__":
    unittest.main()
