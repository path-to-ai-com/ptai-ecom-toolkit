"""Schemas aus Sections, Theme-Blöcken und `settings_schema.json` lesen."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.theme_generate_support import SOURCE, TARGET, temp_dir  # noqa: E402
from theme import schema  # noqa: E402


class Extract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = schema.extract(SOURCE)
        cls.target = schema.extract(TARGET)

    def test_sections_and_blocks_including_private_ones_are_read(self):
        self.assertIn("hero", self.target["sections"])
        self.assertEqual(set(self.target["blocks"]),
                         {"text", "button", "price", "group", "_product-title", "_slide"})
        self.assertTrue(self.target["blocks"]["_product-title"]["private"])
        self.assertFalse(self.target["blocks"]["text"]["private"])

    def test_defaults_come_from_the_schema_and_a_checkbox_without_default_is_false(self):
        banner = self.source["sections"]["banner"]
        self.assertEqual(banner["defaults"]["show_heading"], True)
        self.assertEqual(banner["defaults"]["padding_top"], 40)
        self.assertIs(banner["defaults"]["hide_divider"], False)
        self.assertNotIn("link", self.source["sections"]["banner"]["inline_blocks"]["button"]["defaults"])

    def test_sidebar_settings_without_value_are_not_settings(self):
        self.assertNotIn("header", [s.get("type") for s in self.source["sections"]["banner"]["settings"].values()])

    def test_allowed_blocks_know_theme_app_and_inline_blocks(self):
        hero = self.target["sections"]["hero"]
        self.assertTrue(hero["accepts_theme_blocks"])
        self.assertTrue(hero["accepts_app_blocks"])
        banner = self.source["sections"]["banner"]
        self.assertFalse(banner["accepts_theme_blocks"])
        self.assertEqual(set(banner["inline_blocks"]), {"button", "text"})
        self.assertEqual(banner["inline_blocks"]["text"]["defaults"]["text"], "<p>Text</p>")

    def test_static_blocks_come_from_content_for_in_the_liquid(self):
        self.assertEqual(self.target["sections"]["hero"]["static_blocks"], [{"type": "text", "id": "heading"}])
        self.assertEqual(self.target["sections"]["product-information"]["static_blocks"],
                         [{"type": "_product-title", "id": "title"}])

    def test_global_settings_with_theme_info_and_color_palette(self):
        settings = self.target["settings_schema"]
        self.assertEqual(settings["theme_info"]["theme_version"], "4.0.0")
        self.assertEqual(settings["settings"]["colors"]["type"], "color_palette")
        self.assertEqual(settings["defaults"]["colors"], {"primary": "#000000", "secondary": "#FFFFFF"})

    def test_max_blocks_is_kept(self):
        self.assertEqual(self.target["sections"]["header"]["max_blocks"], 3)


class BlockRules(unittest.TestCase):
    def setUp(self):
        self.target = schema.extract(TARGET)
        self.hero = self.target["sections"]["hero"]

    def test_a_private_block_is_not_covered_by_theme(self):
        self.assertTrue(schema.block_allowed(self.target, self.hero, "text"))
        self.assertFalse(schema.block_allowed(self.target, self.hero, "_slide"))

    def test_an_explicitly_listed_private_block_is_allowed(self):
        parent = dict(self.hero, allowed_blocks=["_slide"], accepts_theme_blocks=False)
        self.assertTrue(schema.block_allowed(self.target, parent, "_slide"))
        self.assertFalse(schema.block_allowed(self.target, parent, "text"))

    def test_app_blocks_need_app_in_the_schema(self):
        app = "shopify://apps/beispiel/blocks/x/00000000-0000-0000-0000-000000000000"
        self.assertTrue(schema.block_allowed(self.target, self.hero, app))
        header = self.target["sections"]["header"]
        self.assertFalse(schema.block_allowed(self.target, header, app))

    def test_inline_definition_wins_over_blocks_folder(self):
        source = schema.extract(SOURCE)
        banner = source["sections"]["banner"]
        self.assertIn("label", schema.block_definition(source, banner, "button")["settings"])
        self.assertIsNone(schema.block_definition(source, banner, "unbekannt"))


class Export(unittest.TestCase):
    """Der Auszug im Format von `theme.mapping_check` (Kopf jenes Moduls)."""

    def setUp(self):
        self.target = schema.export(TARGET)
        self.source = schema.export(SOURCE)

    def test_top_level_fields(self):
        self.assertEqual(self.target["theme"], {"name": "Zielthema", "version": "4.0.0"})
        self.assertEqual(self.target["templates"], ["collection", "index"])
        self.assertEqual(self.target["section_groups"], ["header-group"])
        self.assertIn("gift_card", self.source["templates"])

    def test_settings_carry_type_range_and_option_values(self):
        hero = self.target["sections"]["hero"]["settings"]
        self.assertEqual(hero["padding-block-start"], {"type": "range", "min": 0, "max": 60, "step": 2, "default": 0})
        self.assertEqual(hero["section_width"]["options"], ["page-width", "full-width"])
        self.assertEqual(self.target["settings_schema"]["colors"]["type"], "color_palette")

    def test_section_blocks_hold_inline_settings_and_names(self):
        self.assertEqual(self.target["sections"]["hero"]["blocks"], {"@theme": {}, "@app": {}})
        banner = self.source["sections"]["banner"]["blocks"]
        self.assertEqual(banner["button"]["settings"]["label"]["type"], "text")

    def test_theme_blocks_list_what_they_accept(self):
        self.assertEqual(self.target["blocks"]["group"]["blocks"], ["@theme"])
        self.assertIn("show_vendor", self.target["blocks"]["_product-title"]["settings"])

    def test_cli_export(self):
        out = temp_dir(self) / "auszug.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = schema.main(["export", "--theme-dir", str(TARGET), "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["theme"]["name"], "Zielthema")


class Reading(unittest.TestCase):
    def test_comment_head_is_stripped_before_parsing(self):
        self.assertEqual(schema.read_json_text("/*\n * Kopf\n */\n{\"a\": 1}"), {"a": 1})

    def test_unreadable_schema_is_reported_not_skipped(self):
        theme = temp_dir(self)
        (theme / "sections").mkdir()
        (theme / "sections" / "kaputt.liquid").write_text("{% schema %}{ nein {% endschema %}", encoding="utf-8")
        result = schema.extract(theme)
        self.assertEqual([e["file"] for e in result["errors"]], ["sections/kaputt.liquid"])

    def test_cli_writes_the_file_and_one_summary_line(self):
        out = temp_dir(self) / "schemas.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = schema.main(["extract", "--theme-dir", str(TARGET), "--out", str(out)])
        self.assertEqual(len(stdout.getvalue().strip().splitlines()), 1)
        self.assertEqual(code, 0)
        self.assertIn("hero", json.loads(out.read_text(encoding="utf-8"))["sections"])


if __name__ == "__main__":
    unittest.main()
