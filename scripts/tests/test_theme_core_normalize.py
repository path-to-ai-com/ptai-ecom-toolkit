"""Normalisierung: JSON-Vergleich ohne Kommentarkopf und ohne Prüfsumme von Shopify."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import normalize  # noqa: E402

SETTINGS = {"current": {"beispiel_title": "Willkommen", "blocks": {}}, "presets": {"Default": {}}}
LOCAL = json.dumps(SETTINGS, indent=2) + "\n"
#: So kommt die Datei nach dem Schreiben von Shopify zurück: Kopf davor, anders eingerückt.
FROM_SHOPIFY = "/*\n * IMPORTANT: auto-generated\n */\n" + json.dumps(SETTINGS, indent=4)


class TestJson(unittest.TestCase):
    def test_kommentarkopf_wird_entfernt_und_nur_er(self):
        self.assertEqual(json.loads(normalize.strip_json_comment(FROM_SHOPIFY)), SETTINGS)
        self.assertEqual(normalize.strip_json_comment('{"a": "/* bleibt */"}'), '{"a": "/* bleibt */"}')
        self.assertEqual(normalize.strip_json_comment("﻿/* a */ /* b */ {}"), "{}")

    def test_neu_serialisiertes_json_ist_inhaltlich_gleich_obwohl_die_md5_abweicht(self):
        self.assertNotEqual(hashlib.md5(LOCAL.encode()).hexdigest(), hashlib.md5(FROM_SHOPIFY.encode()).hexdigest())
        self.assertEqual(normalize.normalized_json(LOCAL), normalize.normalized_json(FROM_SHOPIFY))
        self.assertTrue(normalize.same_content("config/settings_data.json", LOCAL, FROM_SHOPIFY))
        a = normalize.content_hash("config/settings_data.json", LOCAL)
        b = normalize.content_hash("config/settings_data.json", FROM_SHOPIFY)
        self.assertNotEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["sha256_normalized"], b["sha256_normalized"])

    def test_ein_geaenderter_wert_bleibt_ein_unterschied(self):
        changed = FROM_SHOPIFY.replace("Willkommen", "Hallo")
        self.assertFalse(normalize.same_content("config/settings_data.json", LOCAL, changed))

    def test_leere_bloecke_und_ganze_zahlen_als_float_gelten_als_gleich(self):
        self.assertEqual(normalize.normalized_json('{"s": {"blocks": {}, "block_order": [], "n": 1.0}}'),
                         normalize.normalized_json('{"s": {"n": 1}}'))
        self.assertNotEqual(normalize.normalized_json('{"n": 1.5}'), normalize.normalized_json('{"n": 1}'))

    def test_ungueltiges_json_wird_markiert_statt_still_gezaehlt(self):
        result = normalize.content_hash("templates/index.json", "{kaputt")
        self.assertFalse(result["json_valid"])
        self.assertIsNone(result["sha256_normalized"])
        self.assertNotIn("sha256_normalized", normalize.content_hash("assets/a.css", "a{}"))

    def test_nicht_json_wird_byteweise_verglichen(self):
        self.assertFalse(normalize.same_content("snippets/a.liquid", "a  b", "a b"))


class TestCss(unittest.TestCase):
    def test_kommentare_und_leerraum_fallen_weg_gross_und_klein_bleibt(self):
        a = "/* Kopf */\n.Hero  >  a {\n  color : red ;\n}\n"
        self.assertEqual(normalize.normalized_css(a), ".Hero>a{color:red}")
        self.assertNotEqual(normalize.normalized_css(".Hero{}"), normalize.normalized_css(".hero{}"))


if __name__ == "__main__":
    unittest.main()
