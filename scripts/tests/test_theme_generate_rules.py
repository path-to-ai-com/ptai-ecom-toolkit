"""Die Regeln des Generators, jede mit einem Test, der ohne die Regel rot wäre.

Jede Regel stammt aus einem Fehler, der in einem echten Umbau aufgefallen ist:
fehlende Schlüssel als "aus" gelesen, Einstellungen, die Shopify still
verwirft, Block-IDs, die Shopify ablehnt, eigenes CSS über der Grenze, Limits
erst beim Upload bemerkt, statische Blöcke in `block_order`, geratene Werte und
Editor-Änderungen, die ein neuer Lauf still überschreibt.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.theme_generate_support import (  # noqa: E402
    SOURCE, TARGET, copy_themes, entries, fixture_mapping, run_generator, temp_dir, write_json)
from theme import generate  # noqa: E402


def banner(generator):
    return generator.documents["templates/index.json"]["sections"]["banner_1"]


class MissingKeyIsSchemaDefault(unittest.TestCase):
    """Regel 1: ein fehlender Schlüssel heißt Schema-Standard der Quelle, nie "aus"."""

    def setUp(self):
        self.generator = run_generator()
        self.settings = banner(self.generator)["settings"]

    def test_missing_checkbox_with_default_true_stays_on(self):
        # Im Template fehlt show_heading; der Standard der Quelle ist true.
        self.assertIs(self.settings["show_title"], True)

    def test_missing_checkbox_without_default_counts_as_false(self):
        # hide_divider hat keinen Standard, Shopify liest das als false; umgekehrt also true.
        self.assertIs(self.settings["show_divider"], True)

    def test_missing_range_takes_the_default_value(self):
        self.assertEqual(self.settings["padding-block-start"], 40)

    def test_used_defaults_are_listed_in_the_report(self):
        keys = {e["key"] for e in entries(self.generator.report, "defaults_applied", file="templates/index.json")}
        self.assertTrue({"show_heading", "hide_divider", "padding_top"} <= keys)

    def test_global_settings_fall_back_to_the_source_default_as_well(self):
        palette = self.generator.documents["config/settings_data.json"]["current"]["colors"]
        self.assertEqual(palette["accent"], "#C0392B")


class OnlyTargetSchemaSettings(unittest.TestCase):
    """Regel 2: nur Einstellungen schreiben, die im Ziel-Schema stehen; jede verworfene melden."""

    def setUp(self):
        self.generator = run_generator()

    def test_a_key_outside_the_target_schema_is_not_written(self):
        # Das Ziel hat keine Farbschemata mehr (color_palette statt color_scheme).
        self.assertNotIn("color_scheme", banner(self.generator)["settings"])

    def test_and_it_is_reported(self):
        dropped = entries(self.generator.report, "dropped", key="color_scheme", intended=False)
        self.assertEqual(dropped[0]["reason"], "nicht im Schema des Ziels")
        self.assertEqual(dropped[0]["value"], "scheme_2")

    def test_the_mapping_check_names_the_line_before_the_run(self):
        findings = self.generator.report["mapping_findings"]
        self.assertIn({"where": "sections.banner", "key": "color_scheme", "to": "color_scheme",
                       "reason": "Ziel-Schlüssel steht nicht im Schema des Ziels"}, findings)

    def test_a_value_outside_the_options_is_dropped_and_reported(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["settings"]["layout_width"] = {"to": "section_width"}
        generator = run_generator(mapping)
        self.assertNotIn("section_width", banner(generator)["settings"])
        self.assertEqual(entries(generator.report, "dropped", key="layout_width")[0]["reason"],
                         "Wert steht nicht unter den Optionen des Ziels")

    def test_set_values_are_checked_against_the_schema_too(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["set"] = {"show_title": False, "erfunden": 1}
        generator = run_generator(mapping)
        settings = banner(generator)["settings"]
        self.assertIs(settings["show_title"], False)
        self.assertNotIn("erfunden", settings)

    def test_an_explicit_source_value_without_mapping_line_is_reported(self):
        mapping = fixture_mapping()
        del mapping["sections"]["banner"]["settings"]["heading"]
        generator = run_generator(mapping)
        self.assertEqual(entries(generator.report, "dropped", key="heading")[0]["reason"], "nicht im Mapping")

    def test_a_range_value_is_clamped_to_the_target_and_reported(self):
        group = run_generator().documents["sections/header-group.json"]
        self.assertEqual(group["sections"]["header"]["settings"]["logo_width"], 240)

    def test_a_block_setting_outside_the_block_schema_is_dropped(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["blocks"]["button"]["settings"]["label"] = {"to": "text_color"}
        generator = run_generator(mapping)
        blocks = banner(generator)["blocks"]
        button = next(b for b in blocks.values() if b["type"] == "button")
        self.assertNotIn("text_color", button["settings"])


class StableValidBlockIds(unittest.TestCase):
    """Regel 3: Block-IDs stabil und gültig."""

    def test_an_invalid_id_is_replaced_by_a_valid_one(self):
        blocks = banner(run_generator())["blocks"]
        self.assertNotIn("btn--1", blocks)
        for block_id in blocks:
            self.assertTrue(generate.valid_block_id(block_id), block_id)

    def test_the_replacement_is_the_same_on_every_run(self):
        first = banner(run_generator())["block_order"]
        second = banner(run_generator())["block_order"]
        self.assertEqual(first, second)

    def test_valid_ids_stay_and_renames_are_reported(self):
        generator = run_generator()
        product = generator.documents["templates/product.json"]["sections"]["main"]
        self.assertIn("price", product["blocks"])
        renamed = generator.report["renamed_block_ids"]
        self.assertEqual([(r["old_id"], r["new_id"].startswith("btn_1_")) for r in renamed], [("btn--1", True)])

    def test_a_dynamic_block_never_takes_the_id_of_a_static_one(self):
        source, target = copy_themes(self)
        index = generate.schema_module.read_json_file(source / "templates/index.json")
        index["sections"]["banner_1"]["blocks"]["heading"] = {"type": "button", "settings": {"label": "Zweiter"}}
        index["sections"]["banner_1"]["block_order"].append("heading")
        write_json(source / "templates/index.json", index)
        section = banner(run_generator(source=source, target=target))
        self.assertTrue(section["blocks"]["heading"]["static"])
        self.assertEqual(section["blocks"]["heading"]["type"], "text")
        self.assertNotIn("heading", section["block_order"])
        self.assertEqual(len(section["block_order"]), 2)

    def test_id_rules(self):
        for value in ("text_1", "a-b", "Ab9"):
            self.assertTrue(generate.valid_block_id(value), value)
        for value in ("a--b", "a__b", "_a", "", "a b", "x" * 65):
            self.assertFalse(generate.valid_block_id(value), value)


class CustomCssLimit(unittest.TestCase):
    """Regel 4: eigenes CSS je Section höchstens 500 Zeichen."""

    def product(self, css):
        mapping = fixture_mapping()
        mapping["sections"]["main-product"]["custom_css"] = css
        generator = run_generator(mapping)
        return generator, generator.documents["templates/product.json"]["sections"]["main"]

    def test_css_up_to_500_characters_is_written(self):
        rule = "." + "a" * 495 + "{}"
        self.assertEqual(len(rule), 498)
        _, section = self.product([rule])
        self.assertEqual(section["custom_css"], [rule])

    def test_longer_css_is_not_written_but_a_build_case(self):
        generator, section = self.product([".x { color: red; }", "." + "a" * 490 + "{}"])
        self.assertNotIn("custom_css", section)
        self.assertEqual(entries(generator.report, "build", kind="custom_css_too_long")[0]["characters"], 512)

    def test_source_css_without_decision_is_reported_not_copied(self):
        mapping = fixture_mapping()
        del mapping["sections"]["main-product"]["custom_css"]
        generator = run_generator(mapping)
        self.assertNotIn("custom_css", generator.documents["templates/product.json"]["sections"]["main"])
        self.assertEqual(len(entries(generator.report, "build", kind="custom_css_not_carried")), 1)


class Limits(unittest.TestCase):
    """Regel 5: Limits vor dem Schreiben prüfen."""

    target = generate.schema_module.extract(TARGET)

    @staticmethod
    def blocks(count, static=False):
        return {f"b{i}": {"type": "text", "settings": {}, **({"static": True} if static else {})} for i in range(count)}

    def limits(self, document, size=100):
        return {v["limit"] for v in generate.check_limits(document, "templates/x.json", self.target, size)}

    def test_25_sections_pass_26_do_not(self):
        doc = {"sections": {f"s{i}": {"type": "hero", "settings": {}} for i in range(25)}}
        self.assertEqual(self.limits(doc), set())
        doc["sections"]["s25"] = {"type": "hero", "settings": {}}
        self.assertEqual(self.limits(doc), {"sections_per_template"})

    def test_50_blocks_per_section_and_static_blocks_do_not_count(self):
        doc = {"sections": {"a": {"type": "hero", "blocks": {**self.blocks(50), "fest": {"type": "text", "static": True}}}}}
        self.assertEqual(self.limits(doc), set())
        doc["sections"]["a"]["blocks"]["b50"] = {"type": "text"}
        self.assertEqual(self.limits(doc), {"blocks_per_section"})

    def test_max_blocks_lowers_the_section_limit(self):
        doc = {"sections": {"h": {"type": "header", "blocks": self.blocks(4)}}}
        violations = generate.check_limits(doc, "sections/header-group.json", self.target, 10)
        self.assertEqual([(v["limit"], v["max"]) for v in violations], [("blocks_per_section", 3)])

    def test_1250_blocks_per_template(self):
        doc = {"sections": {f"s{i}": {"type": "hero", "blocks": self.blocks(50)} for i in range(26)}}
        self.assertIn("blocks_per_template", self.limits(doc))

    def test_eight_levels_pass_nine_do_not(self):
        def nested(levels):
            node = {"type": "group", "settings": {}}
            for _ in range(levels - 1):
                node = {"type": "group", "blocks": {"g": node}}
            return {"sections": {"s": {"type": "hero", "blocks": {"g": node}}}}
        self.assertEqual(self.limits(nested(8)), set())
        self.assertEqual(self.limits(nested(9)), {"nesting_depth"})

    def test_512_kb_per_json_template(self):
        self.assertEqual(self.limits({"sections": {}}, 512 * 1024), set())
        self.assertEqual(self.limits({"sections": {}}, 512 * 1024 + 1), {"json_template_bytes"})

    def test_a_template_over_a_limit_is_not_written(self):
        source, target = copy_themes(self)
        sections = {f"s{i}": {"type": "header", "settings": {}} for i in range(26)}
        write_json(source / "templates/index.json", {"sections": sections, "order": list(sections)})
        generator = run_generator(source=source, target=target)
        out = temp_dir(self)
        generator.write(out)
        self.assertFalse((out / "templates/index.json").exists())
        self.assertTrue((out / "templates/product.json").exists())
        self.assertEqual(entries(generator.report, "limit_violations", file="templates/index.json")[0]["limit"],
                         "sections_per_template")


class StaticBlocks(unittest.TestCase):
    """Regel 6: statische Blöcke mit `static: true` und nie in `block_order`."""

    def setUp(self):
        self.generator = run_generator()

    def test_static_block_is_flagged_and_left_out_of_block_order(self):
        product = self.generator.documents["templates/product.json"]["sections"]["main"]
        self.assertIs(product["blocks"]["title"]["static"], True)
        self.assertNotIn("title", product["block_order"])
        self.assertEqual(product["block_order"], ["price", "reviews"])

    def test_block_order_holds_exactly_the_dynamic_blocks(self):
        for rel, document in self.generator.documents.items():
            if rel.endswith("settings_data.json"):
                continue
            for section in document["sections"].values():
                dynamic = [k for k, b in (section.get("blocks") or {}).items() if not b.get("static")]
                self.assertEqual(sorted(section.get("block_order", [])), sorted(dynamic), rel)

    def test_a_static_target_that_the_liquid_does_not_render_is_a_build_case(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["blocks"]["text"]["static_id"] = "subheading"
        generator = run_generator(mapping)
        self.assertEqual(len(entries(generator.report, "build", kind="static_block_unknown")), 1)

    def test_a_block_type_the_target_does_not_allow_is_a_build_case(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["blocks"]["button"]["target"] = "_slide"
        generator = run_generator(mapping)
        self.assertEqual(entries(generator.report, "build", kind="block_not_allowed")[0]["path"],
                         "sections.banner_1.blocks.btn--1")


class BuildInsteadOfGuessing(unittest.TestCase):
    """Regel 7: was keine Transformation abbildet, wird ein `build`-Fall."""

    def test_a_value_without_mapping_row_is_not_written(self):
        source, target = copy_themes(self)
        index = generate.schema_module.read_json_file(source / "templates/index.json")
        index["sections"]["banner_1"]["settings"]["layout_width"] = "wrapper--split"
        write_json(source / "templates/index.json", index)
        generator = run_generator(source=source, target=target)
        self.assertNotIn("section_width", banner(generator)["settings"])
        case = entries(generator.report, "build", kind="transform")[0]
        self.assertEqual(case["path"], "sections.banner_1.settings.layout_width")
        self.assertEqual(case["value"], "wrapper--split")

    def test_an_unmapped_section_and_a_build_section_are_build_cases(self):
        generator = run_generator()
        kinds = {(e["path"], e["kind"]) for e in entries(generator.report, "build", file="templates/index.json")}
        self.assertEqual(kinds, {("sections.promo", "unmapped_section"), ("sections.slider_1", "mapping_build")})
        self.assertEqual(generator.documents["templates/index.json"]["order"], ["banner_1"])

    def test_an_unmapped_block_is_a_build_case(self):
        mapping = fixture_mapping()
        del mapping["sections"]["banner"]["blocks"]["button"]
        generator = run_generator(mapping)
        self.assertEqual(entries(generator.report, "build", kind="unmapped_block")[0]["type"], "button")

    def test_app_blocks_are_carried_only_where_the_target_takes_app(self):
        generator = run_generator()
        product = generator.documents["templates/product.json"]["sections"]["main"]
        self.assertIn("reviews", product["blocks"])
        mapping = fixture_mapping()
        mapping["sections"]["main-product"]["target"] = "header"
        mapping["sections"]["main-product"]["settings"] = {}
        generator = run_generator(mapping)
        self.assertEqual(len(entries(generator.report, "build", kind="app_block_not_accepted")), 1)

    def test_an_unmapped_template_is_a_build_case_and_a_wildcard_covers_all(self):
        mapping = fixture_mapping()
        del mapping["templates"]["product"]
        generator = run_generator(mapping)
        self.assertNotIn("templates/product.json", generator.documents)
        self.assertEqual(len(entries(generator.report, "build", kind="unmapped_template")), 1)
        mapping["templates"] = {"*": {"action": "configure"}}
        self.assertIn("templates/page.alt.json", run_generator(mapping).documents)

    def test_a_liquid_template_other_than_gift_card_is_a_build_case(self):
        source, target = copy_themes(self)
        (source / "templates/page.contact.liquid").write_text("{{ page.content }}\n", encoding="utf-8")
        generator = run_generator(source=source, target=target)
        files = [e["file"] for e in entries(generator.report, "build", kind="liquid_template")]
        self.assertEqual(files, ["templates/page.contact.liquid"])

    def test_a_missing_layout_is_a_build_case(self):
        source, target = copy_themes(self)
        product = generate.schema_module.read_json_file(source / "templates/product.json")
        write_json(source / "templates/product.json", {"layout": "alternativ", **product})
        generator = run_generator(source=source, target=target)
        self.assertNotIn("layout", generator.documents["templates/product.json"])
        self.assertEqual(len(entries(generator.report, "build", kind="missing_layout")), 1)

    def test_color_to_palette_in_a_section_is_refused_by_the_mapping_check(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["settings"]["heading"] = {"transform": "color_to_palette", "key": "x"}
        self.assertTrue(any("color_to_palette" in e for e in generate.validate_mapping(mapping)))


class SettingsData(unittest.TestCase):
    def setUp(self):
        self.generator = run_generator()
        self.data = self.generator.documents["config/settings_data.json"]

    def test_colors_go_into_the_palette_starting_from_its_default(self):
        self.assertEqual(self.data["current"]["colors"],
                         {"primary": "#112233", "secondary": "#FFFFFF", "accent": "#C0392B"})

    def test_fonts_and_numbers_are_transformed(self):
        self.assertEqual(self.data["current"]["type_font_heading"], "inter_n7")
        self.assertEqual(self.data["current"]["page_width"], 1400)

    def test_presets_come_from_the_target(self):
        self.assertEqual(list(self.data["presets"]), ["Zielthema"])

    def test_app_embeds_are_carried_with_their_state(self):
        # In einer echten Migration hat Shopify die per Upload gesetzten Embeds angenommen.
        block = self.data["current"]["blocks"]["1234567890"]
        self.assertEqual(block["type"], "shopify://apps/beispiel-app/blocks/embed/00000000-0000-0000-0000-000000000000")
        self.assertIs(block["disabled"], False)
        self.assertTrue(self.generator.report["app_embeds"][0]["carried"])

    def test_an_embed_decided_drop_in_g1_stays_out(self):
        apps = {"services": [{"service_id": "app:beispiel-app", "decision": "drop"}],
                "integrations": [{"service_id": "app:beispiel-app", "integration_type": "app_embed",
                                  "location": {"block_ids": ["1234567890"]}}]}
        generator = generate.Generator(fixture_mapping(), None, SOURCE, TARGET, apps)
        generator.run()
        self.assertNotIn("blocks", generator.documents["config/settings_data.json"]["current"])
        self.assertEqual(generator.report["app_embeds"][0]["decision"], "drop")
        self.assertFalse(generator.report["app_embeds"][0]["carried"])

    def test_an_embed_decided_keep_is_carried(self):
        apps = {"services": [{"service_id": "app:beispiel-app", "decision": "keep"}],
                "integrations": [{"service_id": "app:beispiel-app",
                                  "location": {"type": "shopify://apps/beispiel-app/blocks/embed/"
                                                       "00000000-0000-0000-0000-000000000000"}}]}
        generator = generate.Generator(fixture_mapping(), None, SOURCE, TARGET, apps)
        generator.run()
        self.assertIn("1234567890", generator.documents["config/settings_data.json"]["current"]["blocks"])

    def test_current_as_preset_name_is_resolved(self):
        source, target = copy_themes(self)
        write_json(source / "config/settings_data.json",
                   {"current": "Hell", "presets": {"Hell": {"color_primary": "#010203"}}})
        data = run_generator(source=source, target=target).documents["config/settings_data.json"]
        self.assertEqual(data["current"]["colors"]["primary"], "#010203")

    def test_a_palette_target_that_is_no_palette_is_dropped(self):
        mapping = fixture_mapping()
        mapping["settings_data"]["color_primary"]["to"] = "color_sale"
        generator = run_generator(mapping)
        self.assertEqual(entries(generator.report, "dropped", key="color_primary")[0]["reason"],
                         "Ziel ist keine Einstellung vom Typ color_palette")


class Overrides(unittest.TestCase):
    def test_overrides_are_merged_over_the_mapping(self):
        overrides = {"sections": {"banner": {"settings": {"heading": {"to": "show_title", "transform": "map_values",
                                                                      "values": {"Neue Kollektion": False}}}}}}
        self.assertIs(banner(run_generator(overrides=overrides))["settings"]["show_title"], False)

    def test_an_instance_can_be_dropped_or_given_values(self):
        overrides = {"instances": {"templates/index.json": {"banner_1": {"set": {"show_divider": False}}},
                                   "templates/product.json": {"main": {"action": "drop"}}}}
        generator = run_generator(overrides=overrides)
        self.assertIs(banner(generator)["settings"]["show_divider"], False)
        self.assertEqual(generator.documents["templates/product.json"]["sections"], {})


class OutputGoesToATestDirectory(unittest.TestCase):
    """Regel 8: erst ins Testverzeichnis, mit Diff gegen das Ziel-Repo."""

    def test_writing_into_the_target_repo_is_refused(self):
        problem = generate.prepare_out_dir(TARGET / "templates", SOURCE, TARGET)
        self.assertIn("Testverzeichnis", problem)
        self.assertIsNotNone(generate.prepare_out_dir(TARGET, SOURCE, TARGET))

    def test_a_foreign_non_empty_directory_is_refused(self):
        out = temp_dir(self)
        (out / "notiz.txt").write_text("x", encoding="utf-8")
        self.assertIn("report.json", generate.prepare_out_dir(out, SOURCE, TARGET))

    def test_a_previous_run_is_cleared(self):
        out = temp_dir(self)
        write_json(out / "report.json", {})
        write_json(out / "templates/alt.json", {})
        self.assertIsNone(generate.prepare_out_dir(out, SOURCE, TARGET))
        self.assertFalse((out / "templates").exists())

    def test_the_diff_names_changed_new_and_untouched_files(self):
        generator = run_generator()
        generator.write(temp_dir(self))
        diff = generator.diff_against_target()
        self.assertEqual(diff["new"], ["templates/product.json"])
        changed = {c["path"]: c["differences"] for c in diff["changed"]}
        self.assertIn("sections.banner_1.settings.section_width", changed["templates/index.json"])
        self.assertEqual(diff["not_generated"], ["templates/collection.json"])

    def test_an_identical_file_counts_as_unchanged(self):
        source, target = copy_themes(self)
        generator = run_generator(source=source, target=target)
        write_json(target / "templates/product.json", generator.documents["templates/product.json"])
        generator.write(temp_dir(self))
        self.assertIn("templates/product.json", generator.diff_against_target()["unchanged"])


if __name__ == "__main__":
    unittest.main()
