"""Felder der Mapping-Bibliothek: Kindblöcke aus Einstellungen, Behälterblöcke,
statische Blöcke, feste Werte, zusammengeführte Section-Groups, Overrides je Ebene,
richtext und unbekannte Felder.

Quelle und Ziel sind ein kleiner erfundener Ausschnitt, im Test erzeugt. Er
bildet den Aufbau nach, den eine Bibliothek wie die von einem älteren 2.0-Theme
auf ein Theme mit Theme-Blöcken braucht: Inhalte, die in der Quelle Einstellungen
der Section sind, werden im Ziel Blöcke.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.theme_generate_support import entries, temp_dir, write_json  # noqa: E402
from theme import generate  # noqa: E402


def liquid(root: Path, rel: str, body: str, schema: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{body}\n{{% schema %}}\n{json.dumps(schema, ensure_ascii=False)}\n{{% endschema %}}\n",
                    encoding="utf-8")


def text(setting_id, setting_type="text", **extra):
    return {"type": setting_type, "id": setting_id, "label": setting_id, **extra}


APP = "shopify://apps/beispiel-app/blocks/sterne/00000000-0000-0000-0000-000000000000"


def build_themes(base: Path) -> tuple[Path, Path]:
    source, target = base / "quelle", base / "ziel"
    liquid(source, "sections/rich-text.liquid", "<div></div>", {
        "name": "Text", "settings": [text("title", default="Über uns"), text("subheading"),
                                     text("width", "select", default="narrow",
                                          options=[{"value": "narrow", "label": "s"}, {"value": "full", "label": "v"}])],
        "blocks": [{"type": "text", "name": "Text", "settings": [text("text", "richtext")]},
                   {"type": "image", "name": "Bild", "settings": [text("image", "image_picker"), text("caption")]}]})
    liquid(source, "sections/product-main.liquid", "<div></div>", {
        "name": "Produkt", "settings": [text("gap", default="12px")],
        "blocks": [{"type": "@app"},
                   {"type": "price", "name": "Preis", "settings": [text("show_compare", "checkbox", default=True)]},
                   {"type": "recommend", "name": "Empfehlung", "settings": [text("heading", default="Passt dazu")]}]})
    liquid(source, "sections/footer-links.liquid", "<div></div>", {"name": "Links", "settings": [text("heading")]})
    liquid(source, "sections/newsletter.liquid", "<div></div>", {"name": "Newsletter", "settings": [text("title")]})
    write_json(source / "templates/page.json", {"sections": {"main": {
        "type": "rich-text", "settings": {"title": "Wir über uns & mehr", "width": "full"},
        "blocks": {"t1": {"type": "text", "settings": {"text": "<p>Absatz</p>"}},
                   "img1": {"type": "image", "settings": {"image": "shopify://shop_images/a.jpg", "caption": "Bildtext"}}},
        "block_order": ["t1", "img1"]}}, "order": ["main"]})
    write_json(source / "templates/product.json", {"sections": {"main": {
        "type": "product-main", "settings": {},
        "blocks": {"price": {"type": "price", "settings": {"show_compare": False}},
                   "recommend": {"type": "recommend", "settings": {}},
                   "reviews": {"type": APP, "settings": {}}},
        "block_order": ["price", "recommend", "reviews"]}}, "order": ["main"]})
    write_json(source / "sections/group-footer.json", {"type": "footer", "name": "Fußzeile",
                                                      "sections": {"links": {"type": "footer-links", "settings": {"heading": "Hilfe"}}},
                                                      "order": ["links"]})
    write_json(source / "sections/group-pre-footer.json", {"type": "footer", "name": "Vor der Fußzeile",
                                                          "sections": {"links": {"type": "newsletter", "settings": {"title": "Bleib dran"}}},
                                                          "order": ["links"]})

    liquid(target, "sections/section.liquid", "{% content_for 'blocks' %}", {
        "name": "Section", "settings": [text("section_width", "select", default="page-width",
                                             options=[{"value": "page-width", "label": "s"},
                                                      {"value": "full-width", "label": "v"}])],
        "blocks": [{"type": "@theme"}, {"type": "@app"}]})
    liquid(target, "sections/product-information.liquid",
           "{% content_for 'block', type: '_product-details', id: 'details' %}",
           {"name": "Produktinformation", "settings": [], "blocks": [{"type": "@app"}]})
    liquid(target, "sections/footer.liquid", "{% content_for 'blocks' %}",
           {"name": "Fußzeile", "settings": [], "blocks": [{"type": "@theme"}]})
    liquid(target, "blocks/text.liquid", "<div></div>", {"name": "Text", "settings": [text("text", "richtext")]})
    liquid(target, "blocks/image.liquid", "<div></div>", {"name": "Bild", "settings": [text("image", "image_picker")]})
    liquid(target, "blocks/group.liquid", "{% content_for 'blocks' %}",
           {"name": "Gruppe", "settings": [], "blocks": [{"type": "@theme"}]})
    liquid(target, "blocks/_product-details.liquid", "{% content_for 'blocks' %}", {
        "name": "Details", "settings": [text("gap", "range", min=0, max=40, step=2, default=8)],
        "blocks": [{"type": "@theme"}, {"type": "@app"}]})
    liquid(target, "blocks/price.liquid", "<div></div>",
           {"name": "Preis", "settings": [text("show_compare_price", "checkbox", default=True)]})
    liquid(target, "blocks/product-recommendations.liquid", "<div></div>", {
        "name": "Empfehlungen", "settings": [text("heading", "inline_richtext"),
                                             text("recommendation_type", "select", default="related",
                                                  options=[{"value": "related", "label": "r"},
                                                           {"value": "complementary", "label": "c"}])]})
    write_json(target / "sections/footer-group.json", {"type": "footer", "name": "t:names.footer",
                                                      "sections": {}, "order": []})
    return source, target


MAPPING = {
    "source": {"theme": "Quellthema B", "version": "1.x"},
    "target": {"theme": "Zielthema B", "version": "4.x"},
    "sections": {
        "rich-text": {
            "action": "configure", "target": "section",
            "settings": {
                "title": {"to": "text", "transform": "identity", "block": "text", "block_id": "title",
                          "note": "Klartext in ein richtext-Feld"},
                "subheading": {"to": "text", "transform": "text_to_richtext", "block": "text", "block_id": "subheading"},
                "width": {"to": "section_width", "transform": "map_values",
                          "values": {"narrow": "page-width", "full": "full-width"}}},
            "blocks": {
                "text": {"target": "text", "settings": {"text": {"to": "text", "transform": "identity"}}},
                "image": {"target": "group", "settings": {
                    "image": {"to": "image", "transform": "identity", "block": "image"},
                    "caption": {"to": "text", "transform": "identity", "block": "text"}}}}},
        "product-main": {
            "action": "configure", "target": "product-information",
            "settings": {"gap": {"to": "gap", "transform": "px_to_number", "block": "_product-details"}},
            "blocks": {
                "price": {"target": "price", "parent": "_product-details",
                          "settings": {"show_compare": {"to": "show_compare_price", "transform": "identity"}}},
                "recommend": {"target": "product-recommendations", "parent": "_product-details",
                              "settings": {"heading": {"to": "heading", "transform": "identity"}},
                              "set": {"recommendation_type": "complementary"}},
                "@app": {"target": "@app", "parent": "_product-details"}}},
        "footer-links": {"action": "configure", "target": "footer", "settings": {
            "heading": {"to": "text", "transform": "text_to_richtext", "block": "text", "block_id": "heading"}}},
        "newsletter": {"action": "configure", "target": "section", "settings": {
            "title": {"to": "text", "transform": "identity", "block": "text"}}},
    },
    "templates": {"page": {"action": "configure"}, "product": {"action": "configure"}},
    "section_groups": {"group-footer": {"action": "configure", "target": "footer-group"},
                       "group-pre-footer": {"action": "configure", "target": "footer-group", "position": "start"}},
}


class LibraryFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = __import__("tempfile").TemporaryDirectory()
        cls.source, cls.target = build_themes(Path(cls.tmp.name))
        cls.generator = generate.Generator(MAPPING, None, cls.source, cls.target)
        cls.generator.run()
        cls.page = cls.generator.documents["templates/page.json"]["sections"]["main"]
        cls.product = cls.generator.documents["templates/product.json"]["sections"]["main"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_mapping_is_valid_and_has_no_findings(self):
        self.assertEqual(generate.validate_mapping(MAPPING), [])
        self.assertEqual(self.generator.report["mapping_findings"], [])
        self.assertEqual(self.generator.report["build"], [])

    def test_setting_with_block_creates_a_child_block_under_its_block_id(self):
        title = self.page["blocks"]["title"]
        self.assertEqual(title["type"], "text")
        self.assertEqual(self.page["block_order"], ["title", "t1", "img1"])

    def test_plain_text_into_richtext_is_wrapped_and_reported(self):
        self.assertEqual(self.page["blocks"]["title"]["settings"]["text"], "<p>Wir über uns &amp; mehr</p>")
        adjusted = entries(self.generator.report, "adjusted", path="sections.main.settings.title")
        self.assertEqual(adjusted[0]["reason"], "Klartext in Absätze gefasst (richtext)")
        self.assertEqual(self.page["blocks"]["t1"]["settings"]["text"], "<p>Absatz</p>")

    def test_a_setting_without_value_creates_no_empty_block(self):
        self.assertNotIn("subheading", self.page["blocks"])

    def test_settings_of_a_source_block_spread_over_nested_children(self):
        group = self.page["blocks"]["img1"]
        self.assertEqual(group["type"], "group")
        self.assertEqual(group["block_order"], ["image", "text"])
        self.assertEqual(group["blocks"]["image"]["settings"]["image"], "shopify://shop_images/a.jpg")
        self.assertEqual(group["blocks"]["text"]["settings"]["text"], "<p>Bildtext</p>")

    def test_block_path_to_a_static_block_uses_its_liquid_id(self):
        details = self.product["blocks"]["details"]
        self.assertIs(details["static"], True)
        self.assertEqual(details["settings"]["gap"], 12)
        self.assertNotIn("details", self.product["block_order"])

    def test_parent_puts_blocks_into_the_container(self):
        details = self.product["blocks"]["details"]
        self.assertEqual(details["block_order"], ["price", "recommend", "reviews"])
        self.assertIs(details["blocks"]["price"]["settings"]["show_compare_price"], False)
        self.assertEqual(details["blocks"]["reviews"]["type"], APP)

    def test_set_writes_fixed_values_and_inline_richtext_takes_plain_text(self):
        recommend = self.product["blocks"]["details"]["blocks"]["recommend"]["settings"]
        self.assertEqual(recommend, {"heading": "Passt dazu", "recommendation_type": "complementary"})

    def test_section_groups_are_merged_into_one_target_group(self):
        group = self.generator.documents["sections/footer-group.json"]
        self.assertEqual(group["name"], "t:names.footer")
        self.assertEqual(group["order"], ["links", "group_footer_links"])
        self.assertEqual(group["sections"]["links"]["type"], "section")
        self.assertEqual(group["sections"]["group_footer_links"]["blocks"]["heading"]["settings"]["text"], "<p>Hilfe</p>")
        self.assertEqual(self.generator.report["merged_groups"],
                         [{"file": "sections/footer-group.json", "sources": ["group-pre-footer", "group-footer"]}])
        self.assertEqual(len(self.generator.report["renamed_section_ids"]), 1)


class OverridesPerLevel(unittest.TestCase):
    def test_a_setting_line_is_replaced_whole_other_lines_stay(self):
        merged = generate.merge_mapping(MAPPING, {"sections": {"rich-text": {"settings": {
            "width": {"to": None, "transform": "drop", "note": "Shop will immer volle Breite"}}}}})
        settings = merged["sections"]["rich-text"]["settings"]
        self.assertEqual(settings["width"], {"to": None, "transform": "drop", "note": "Shop will immer volle Breite"})
        self.assertIn("title", settings)
        self.assertEqual(merged["sections"]["rich-text"]["target"], "section")

    def test_block_entries_are_merged_per_block_and_setting(self):
        merged = generate.merge_mapping(MAPPING, {"sections": {"product-main": {"blocks": {
            "recommend": {"set": {"recommendation_type": "related"}}}}}})
        recommend = merged["sections"]["product-main"]["blocks"]["recommend"]
        self.assertEqual(recommend["set"], {"recommendation_type": "related"})
        self.assertEqual(recommend["parent"], "_product-details")
        self.assertIn("price", merged["sections"]["product-main"]["blocks"])

    def test_a_section_entry_can_be_replaced_by_another_action(self):
        merged = generate.merge_mapping(MAPPING, {"sections": {"newsletter": {"action": "drop", "notes": "kein Newsletter"}}})
        self.assertEqual(merged["sections"]["newsletter"]["action"], "drop")
        self.assertIsNot(merged["sections"], MAPPING["sections"])
        self.assertEqual(MAPPING["sections"]["newsletter"]["action"], "configure")


class UnknownFields(unittest.TestCase):
    def test_unknown_fields_are_ignored_and_reported(self):
        mapping = json.loads(json.dumps(MAPPING))
        mapping["sections"]["rich-text"]["settings"]["width"]["frobnicate"] = True
        mapping["sections"]["rich-text"]["layout"] = "x"
        source, target = build_themes(temp_dir(self))
        generator = generate.Generator(mapping, None, source, target)
        generator.run()
        found = {(f["where"], f["key"]) for f in generator.report["mapping_findings"]}
        self.assertEqual(found, {("sections.rich-text.settings.width", "frobnicate"), ("sections.rich-text", "layout")})
        page = generator.documents["templates/page.json"]["sections"]["main"]
        self.assertEqual(page["settings"]["section_width"], "full-width")


class BlockPathFailures(unittest.TestCase):
    def setUp(self):
        self.source, self.target = build_themes(temp_dir(self))

    def run_with(self, mapping):
        generator = generate.Generator(mapping, None, self.source, self.target)
        generator.run()
        return generator

    def test_a_block_type_the_target_does_not_allow_is_a_build_case(self):
        mapping = json.loads(json.dumps(MAPPING))
        mapping["sections"]["product-main"]["settings"]["gap"]["block"] = "price"
        generator = self.run_with(mapping)
        self.assertEqual(entries(generator.report, "build", kind="block_not_allowed")[0]["path"],
                         "sections.main.settings.gap")

    def test_a_key_outside_the_child_schema_is_dropped_and_leaves_no_empty_block(self):
        mapping = json.loads(json.dumps(MAPPING))
        mapping["sections"]["rich-text"]["settings"]["title"]["to"] = "heading"
        generator = self.run_with(mapping)
        page = generator.documents["templates/page.json"]["sections"]["main"]
        self.assertNotIn("title", page["blocks"])
        self.assertEqual(entries(generator.report, "dropped", key="title")[0]["reason"], "nicht im Schema des Ziels")


if __name__ == "__main__":
    unittest.main()
