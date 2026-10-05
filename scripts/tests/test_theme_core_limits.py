"""Shopify-Limits laut Spec Abschnitt 2, je Grenze ein Fall knapp darüber."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import files as theme_files  # noqa: E402
from theme import limits  # noqa: E402


def template(sections: dict) -> bytes:
    return json.dumps({"sections": sections, "order": list(sections)}).encode()


def blocks(count: int, static: int = 0) -> dict:
    result = {f"b{i}": {"type": "text"} for i in range(count)}
    result.update({f"s{i}": {"type": "text", "static": True} for i in range(static)})
    return result


def rules(files: dict) -> set:
    return {f["rule"] for f in limits.check_files(files)}


class TestStruktur(unittest.TestCase):
    def test_das_beispiel_theme_haelt_alle_limits(self):
        self.assertEqual(limits.check_files(fake.fixture_files()), [])

    def test_mehr_als_25_sections_je_template(self):
        self.assertIn("sections_per_template", rules({"templates/a.json": template(
            {f"s{i}": {"type": "hero"} for i in range(26)})}))
        self.assertNotIn("sections_per_template", rules({"templates/a.json": template(
            {f"s{i}": {"type": "hero"} for i in range(25)})}))

    def test_mehr_als_50_bloecke_je_section_statische_zaehlen_nicht(self):
        self.assertIn("blocks_per_section", rules({"templates/a.json": template(
            {"s": {"type": "hero", "blocks": blocks(51)}})}))
        self.assertEqual(rules({"templates/a.json": template({"s": {"type": "hero", "blocks": blocks(50, 10)}})}),
                         set())

    def test_mehr_als_1250_bloecke_je_template_auch_in_section_groups(self):
        sections = {f"s{i}": {"type": "hero", "blocks": {f"b{j}": {"type": "group", "blocks": blocks(49)}
                                                         for j in range(2)}} for i in range(13)}
        # 13 Sections x 2 x (1 + 49) = 1300 Blöcke
        self.assertIn("blocks_per_template", rules({"sections/footer-group.json": template(sections)}))

    def test_mehr_als_acht_ebenen(self):
        nested = {"type": "text"}
        for _ in range(8):
            nested = {"type": "group", "blocks": {"x": nested}}
        self.assertIn("nesting_depth", rules({"templates/a.json": template({"s": {"type": "hero",
                                                                                     "blocks": {"top": nested}}})}))

    def test_mehr_als_1000_json_templates_und_300_block_dateien(self):
        files = {f"templates/page.p{i}.json": b'{"sections": {}, "order": []}' for i in range(1001)}
        files.update({f"blocks/b{i}.liquid": b"x" for i in range(301)})
        self.assertTrue({"json_templates", "block_files"} <= rules(files))

    def test_ungueltiges_json_ist_ein_befund(self):
        self.assertIn("invalid_json", rules({"templates/a.json": b"{kaputt"}))


class TestGroessen(unittest.TestCase):
    def test_dateigroessen(self):
        cases = {
            "templates/a.json": (limits.MAX_JSON_TEMPLATE_BYTES, "json_template_size"),
            "config/settings_data.json": (limits.MAX_SETTINGS_DATA_BYTES, "settings_data_size"),
            "locales/de.json": (limits.MAX_LOCALE_BYTES, "locale_size"),
            "sections/a.liquid": (limits.MAX_LIQUID_BYTES, "liquid_size"),
        }
        for name, (size, rule) in cases.items():
            with self.subTest(name=name):
                padding = b" " * (size + 1 - 2)
                self.assertIn(rule, rules({name: b"{" + padding + b"}"}))
                self.assertNotIn(rule, rules({name: b"{" + b" " * (size - 2) + b"}"}))

    def test_mehr_als_3400_schluessel_je_locale(self):
        locale = {"g": {f"k{i}": "x" for i in range(3401)}}
        self.assertIn("locale_keys", rules({"locales/de.json": json.dumps(locale).encode()}))


class TestPlaetzeUndUpsert(unittest.TestCase):
    def test_zwanzig_themes_sind_voll_auf_plus_hundert(self):
        themes = [{"id": str(i)} for i in range(20)]
        self.assertTrue(limits.theme_capacity(themes, False)["full"])
        self.assertTrue(limits.theme_capacity(themes, None)["full"])
        self.assertFalse(limits.theme_capacity(themes, True)["full"])
        self.assertEqual(limits.theme_capacity(themes, True)["free"], 80)

    def test_ein_upsert_nimmt_hoechstens_50_dateien(self):
        self.assertEqual(limits.MAX_UPSERT_FILES, 50)
        with self.assertRaises(ValueError):
            theme_files.upsert_batch(fake.FakeShop(), "111111111111", {f"assets/{i}": b"x" for i in range(51)})
        self.assertTrue(all(len(b) <= 50 for b in theme_files.batches([f"assets/{i}" for i in range(120)], 80)))


class TestCli(unittest.TestCase):
    def test_exit_eins_bei_befund(self):
        with tempfile.TemporaryDirectory() as tmp:
            theme = Path(tmp, "theme")
            (theme / "templates").mkdir(parents=True)
            (theme / "templates/a.json").write_text("{kaputt")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = limits.main(["check", "--theme-dir", str(theme), "--out", str(Path(tmp, "limits.json"))])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.getvalue())["rules"], ["invalid_json"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(limits.main(["check", "--theme-dir", str(fake.FIXTURE), "--out",
                                              str(Path(tmp, "ok.json"))]), 0)


if __name__ == "__main__":
    unittest.main()
