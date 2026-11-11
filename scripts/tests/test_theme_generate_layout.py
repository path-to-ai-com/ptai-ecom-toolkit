"""Layout-Regeln, Pflicht-Sections und Typografie des Generators.

Hintergrund: Nach einem Launch im November 2026 waren Inhaltsseiten schmal und links,
Hero-Bilder verdeckt, die Typografie auf den Standardwerten des Ziels und die Suchseite
ohne Suchfeld. Der Generator hatte Inhalte übertragen, Breite, Ausrichtung, Textgröße,
Abstände, Overlay-Deckkraft, Höhe und die Presets aber nicht. Jeder Test hier wäre ohne
die jeweilige Regel rot. Quelle und Ziel sind erfunden und entstehen je Test im Temp-Ordner.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.theme_generate_support import entries, temp_dir, write_json  # noqa: E402
from theme import generate, layout  # noqa: E402

LIBRARY = Path(__file__).resolve().parents[2] / "reference" / "theme-migration" / "mappings" / \
    "broadcast-5__horizon-4.json"


def liquid(schema: dict, body: str = "<div>{% content_for 'blocks' %}</div>") -> str:
    return f"{body}\n{{% schema %}}\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n{{% endschema %}}\n"


def select(setting_id: str, options: list, default) -> dict:
    return {"type": "select", "id": setting_id, "label": setting_id, "default": default,
            "options": [{"value": o, "label": o} for o in options]}


def rng(setting_id: str, default, low=0, high=100, step=1) -> dict:
    return {"type": "range", "id": setting_id, "label": setting_id, "min": low, "max": high, "step": step,
            "default": default}


SOURCE_SECTION = {
    "name": "Inhalt",
    "settings": [
        select("width", ["wrapper--full", "wrapper--full-padded", "wrapper", "wrapper--narrow"], "wrapper"),
        select("align_text", ["text-left", "text-center", "text-justify"], "text-left"),
        select("height", ["image-height", "screen-height-one-half"], "image-height"),
        {"type": "color", "id": "overlay_color", "label": "x", "default": "#000"},
        rng("overlay_opacity", 0, 0, 100, 5),
        {"type": "color", "id": "color", "label": "x", "default": "#FFFFFF"},
        rng("text_size", 4, 1, 15),
    ],
    "blocks": [
        {"type": "text", "name": "Text", "settings": [{"type": "richtext", "id": "text", "label": "x"},
                                                      rng("text_size", 4, 1, 15)]},
        {"type": "heading", "name": "Titel", "settings": [{"type": "text", "id": "title", "label": "x"},
                                                          rng("heading_size", 8, 1, 15),
                                                          select("tag", ["h1", "h2", "h3"], "h2")]},
        {"type": "icon", "name": "Symbol", "settings": [{"type": "text", "id": "title", "label": "x"},
                                                        rng("heading_size", 4, 1, 15)]},
        {"type": "button", "name": "Button", "settings": [{"type": "text", "id": "label", "label": "x"},
                                                          {"type": "url", "id": "link", "label": "x"}]},
    ],
}

TARGET_SECTION = {
    "name": "Section",
    "settings": [
        select("section_width", ["page-width", "full-width"], "page-width"),
        rng("gap", 12),
        select("horizontal_alignment_flex_direction_column", ["flex-start", "center", "flex-end"], "flex-start"),
        select("section_height", ["", "small", "medium", "custom"], ""),
        rng("section_height_custom", 50),
        {"type": "checkbox", "id": "toggle_overlay", "label": "x"},
        {"type": "color", "id": "overlay_color", "label": "x", "default": "#00000026"},
    ],
    "blocks": [{"type": "@theme"}],
}

TARGET_BLOCKS = {
    "text": {"name": "Text", "settings": [
        {"type": "richtext", "id": "text", "label": "x"},
        select("width", ["fit-content", "100%"], "fit-content"),
        select("max_width", ["narrow", "normal", "none"], "normal"),
        {"type": "text_alignment", "id": "alignment", "label": "x", "default": "left"},
        {"type": "color", "id": "text_color", "label": "x"}]},
    "button": {"name": "Button", "settings": [{"type": "text", "id": "label", "label": "x"},
                                               {"type": "url", "id": "link", "label": "x"}]},
    "group": {"name": "Gruppe", "settings": [{"type": "text", "id": "title", "label": "x"}],
              "blocks": [{"type": "@theme"}]},
}

SIZES = ["10", "12", "14", "16", "18", "20", "24", "32", "40", "48", "56", "72"]
TARGET_SETTINGS = [{"name": "Typografie", "settings": [
    {"type": "font_picker", "id": "type_body_font", "label": "x", "default": "work_sans_n4"},
    {"type": "font_picker", "id": "type_subheading_font", "label": "x", "default": "work_sans_n5"},
    select("type_size_paragraph", ["10", "12", "14", "16", "18"], "14"),
    select("type_size_h1", SIZES, "72"),
    select("type_size_h6", SIZES, "16"),
    select("type_font_h6", ["heading", "subheading"], "subheading"),
]}]
SOURCE_SETTINGS = [{"name": "Typografie", "settings": [
    {"type": "font_picker", "id": "type_base_font", "label": "x", "default": "poppins_n4"},
    rng("type_body_size", 100, 50, 150, 5),
    rng("type_heading_size", 100, 50, 150, 5),
]}]

TABLES = {
    "breakpoints": [750, 990],
    "widths": {"page": {"wrapper": "calc(max(1100px, 80vw) - 20px)", "wrapper--full-padded": "100vw"},
               "content": {"wrapper": "1000px"}},
    "scale": {"body": "type_body_size", "heading": "type_heading_size"},
    "sizes": {"body": {"3": [14, 15, 16], "4": [16, 18, 19], "5": [19, 21, 23]},
              "heading": {"4": [16, 18, 19], "8": [32, 35, 38], "11": [43, 48, 56]}},
}


def base_mapping(operations: list) -> dict:
    return {
        "layout": json.loads(json.dumps(TABLES)),
        "sections": {"content": {
            "target": "section",
            "settings": {
                "width": {"to": "section_width", "transform": "map_values",
                          "values": {"wrapper--full": "full-width", "wrapper--full-padded": "page-width",
                                     "wrapper": "page-width", "wrapper--narrow": "page-width"}},
                "align_text": {"transform": "drop"}, "height": {"transform": "drop"},
                "overlay_color": {"transform": "drop"}, "overlay_opacity": {"transform": "drop"},
                "color": {"transform": "drop"}, "text_size": {"transform": "drop"},
            },
            "blocks": {
                "text": {"target": "text", "settings": {"text": {"to": "text"}, "text_size": {"transform": "drop"}}},
                "heading": {"target": "text", "settings": {"title": {"to": "text"}, "heading_size": {"transform": "drop"},
                                                           "tag": {"transform": "drop"}}},
                "icon": {"target": "group", "settings": {"title": {"to": "text", "block": "text", "block_id": "title"},
                                                         "heading_size": {"transform": "drop"}}},
                "button": {"target": "button", "settings": {"label": {"to": "label"}, "link": {"to": "link"}}},
            },
            "layout": operations,
        }},
        "templates": {"*": {"action": "configure"}},
    }


def build(case, sections: dict, settings_data: dict | None = None, target_search: dict | None = None):
    """Quelle und Ziel im Temp-Ordner. `sections` ist der Inhalt von templates/page.json der Quelle."""
    base = temp_dir(case)
    source, target = base / "source", base / "target"
    (source / "sections").mkdir(parents=True)
    (source / "sections" / "content.liquid").write_text(liquid(SOURCE_SECTION, "<div></div>"), encoding="utf-8")
    write_json(source / "templates" / "page.json", {"sections": sections, "order": list(sections)})
    write_json(source / "config" / "settings_schema.json", SOURCE_SETTINGS)
    write_json(source / "config" / "settings_data.json", {"current": settings_data or {}})
    (target / "sections").mkdir(parents=True)
    (target / "blocks").mkdir(parents=True)
    (target / "sections" / "section.liquid").write_text(liquid(TARGET_SECTION), encoding="utf-8")
    for name, schema in TARGET_BLOCKS.items():
        (target / "blocks" / f"{name}.liquid").write_text(liquid(schema), encoding="utf-8")
    write_json(target / "config" / "settings_schema.json", TARGET_SETTINGS)
    if target_search is not None:
        for section_type in ("search-header", "search-results"):
            (target / "sections" / f"{section_type}.liquid").write_text(
                liquid({"name": section_type, "settings": []}, "<div></div>"), encoding="utf-8")
        write_json(target / "templates" / "search.json", target_search)
    return source, target


def run(case, operations: list, sections: dict, **kwargs):
    mapping = kwargs.pop("mapping", None) or base_mapping(operations)
    source, target = build(case, sections, **kwargs)
    generator = generate.Generator(mapping, None, source, target)
    generator.run()
    return generator


def section(generator, section_id="a"):
    return generator.documents["templates/page.json"]["sections"][section_id]


def text(content: str, size=None) -> dict:
    settings = {"text": content}
    if size is not None:
        settings["text_size"] = size
    return {"type": "text", "settings": settings}


class PageWidth(unittest.TestCase):
    def test_wrapper_wird_seitenbreite_der_quelle(self):
        generator = run(self, [{"op": "page_width", "from": "width"}],
                        {"a": {"type": "content", "settings": {"width": "wrapper"}}})
        self.assertEqual(section(generator)["custom_css"], [".section{--page-width:calc(max(1100px, 80vw) - 20px)}"])
        self.assertEqual(section(generator)["settings"]["section_width"], "page-width")

    def test_fehlender_schluessel_ist_der_standard_der_quelle(self):
        generator = run(self, [{"op": "page_width", "from": "width"}], {"a": {"type": "content", "settings": {}}})
        self.assertIn("--page-width:calc(max(1100px, 80vw) - 20px)", section(generator)["custom_css"][0])

    def test_volle_breite_mit_rand_und_eigene_variable(self):
        generator = run(self, [{"op": "page_width", "from": "width"},
                               {"op": "page_width", "from": "width", "widths": "content",
                                "variable": "--page-content-width"}],
                        {"a": {"type": "content", "settings": {"width": "wrapper--full-padded"}},
                         "b": {"type": "content", "settings": {"width": "wrapper"}}})
        self.assertEqual(section(generator)["custom_css"], [".section{--page-width:100vw}"])
        self.assertEqual(section(generator, "b")["custom_css"][1], ".section{--page-content-width:1000px}")

    def test_wert_ohne_zeile_schreibt_nichts(self):
        generator = run(self, [{"op": "page_width", "from": "width"}],
                        {"a": {"type": "content", "settings": {"width": "wrapper--full"}}})
        self.assertNotIn("custom_css", section(generator))


class TextBlocks(unittest.TestCase):
    def test_textbloecke_ueber_die_breite_und_ausgerichtet_wie_die_quelle(self):
        generator = run(self, [{"op": "text_blocks", "alignment_from": "align_text",
                                "values": {"text-center": "center"}, "default": "left"}],
                        {"a": {"type": "content", "settings": {"align_text": "text-center"},
                               "blocks": {"t1": text("<p>Eins</p>")}, "block_order": ["t1"]}})
        settings = section(generator)["blocks"]["t1"]["settings"]
        self.assertEqual((settings["width"], settings["max_width"], settings["alignment"]), ("100%", "none", "center"))

    def test_breite_none_laesst_die_breite_aus(self):
        generator = run(self, [{"op": "text_blocks", "width": None, "max_width": "narrow"}],
                        {"a": {"type": "content", "blocks": {"t1": text("<p>Eins</p>")}, "block_order": ["t1"]}})
        settings = section(generator)["blocks"]["t1"]["settings"]
        self.assertNotIn("width", settings)
        self.assertEqual((settings["max_width"], settings["alignment"]), ("narrow", "left"))


class Gap(unittest.TestCase):
    def test_abstand_ab_zwei_bloecken(self):
        op = [{"op": "gap", "to": "gap", "value": 28, "min_blocks": 2}]
        two = run(self, op, {"a": {"type": "content", "blocks": {"t1": text("<p>a</p>"), "t2": text("<p>b</p>")},
                                   "block_order": ["t1", "t2"]}})
        one = run(self, op, {"a": {"type": "content", "blocks": {"t1": text("<p>a</p>")}, "block_order": ["t1"]}})
        self.assertEqual(section(two)["settings"]["gap"], 28)
        self.assertNotIn("gap", section(one)["settings"])


class TextSize(unittest.TestCase):
    blocks_op = {"op": "text_size", "scope": "blocks", "block_types": ["text"], "from": "text_size",
                 "sizes": "body", "baseline": 3, "suffix": ":is(p,li)"}

    def test_basisstufe_braucht_kein_css(self):
        generator = run(self, [self.blocks_op], {"a": {"type": "content", "blocks": {"t1": text("<p>a</p>", 3)},
                                                       "block_order": ["t1"]}})
        self.assertNotIn("custom_css", section(generator))

    def test_gleiche_stufe_in_allen_textbloecken_wird_eine_regel(self):
        generator = run(self, [self.blocks_op], {"a": {"type": "content",
                                                       "blocks": {"t1": text("<p>a</p>"), "t2": text("<p>b</p>", 4)},
                                                       "block_order": ["t1", "t2"]}})
        self.assertEqual(section(generator)["custom_css"], [
            ".text-block :is(p,li){font-size:16px}",
            "@media(min-width:750px){.text-block :is(p,li){font-size:18px}}",
            "@media(min-width:990px){.text-block :is(p,li){font-size:19px}}"])

    def test_einzelne_bloecke_bekommen_eigene_selektoren(self):
        generator = run(self, [self.blocks_op], {"a": {"type": "content",
                                                       "blocks": {"t1": text("<p>a</p>", 5), "t2": text("<p>b</p>", 3)},
                                                       "block_order": ["t1", "t2"]}})
        self.assertEqual(section(generator)["custom_css"][0], ".text-block[class*=__t1] :is(p,li){font-size:19px}")

    def test_groessen_folgen_dem_prozentwert_der_quelle(self):
        generator = run(self, [self.blocks_op], {"a": {"type": "content", "blocks": {"t1": text("<p>a</p>", 4)},
                                                       "block_order": ["t1"]}},
                        settings_data={"type_body_size": 120})
        self.assertEqual(section(generator)["custom_css"][0], ".text-block :is(p,li){font-size:19px}")
        self.assertIn("font-size:23px", section(generator)["custom_css"][2])

    def test_basisstufe_je_tag(self):
        op = {"op": "text_size", "scope": "blocks", "block_types": ["heading"], "from": "heading_size",
              "sizes": "heading", "baseline": 8, "baseline_from": "tag", "baselines": {"h3": 4}, "suffix": "p"}
        generator = run(self, [op], {"a": {"type": "content", "blocks": {
            "h1": {"type": "heading", "settings": {"title": "Eins", "heading_size": 8, "tag": "h3"}},
            "h2": {"type": "heading", "settings": {"title": "Zwei", "heading_size": 11, "tag": "h2"}},
            "x": text("<p>c</p>")}, "block_order": ["h1", "h2", "x"]}})
        css = section(generator)["custom_css"]
        self.assertEqual(css[0], ".text-block[class*=__h1] p{font-size:32px}")
        self.assertEqual(css[3], ".text-block[class*=__h2] p{font-size:43px}")

    def test_scope_section_und_child(self):
        generator = run(self, [
            {"op": "text_size", "scope": "section", "from": "text_size", "sizes": "body", "baseline": 3,
             "selector": ".rte p"},
            {"op": "text_size", "scope": "child", "block_types": ["icon"], "child_id": "title", "from": "heading_size",
             "sizes": "heading", "suffix": "p", "declarations": "font-weight:700"}],
            {"a": {"type": "content", "settings": {"text_size": 5},
                   "blocks": {"i1": {"type": "icon", "settings": {"title": "A", "heading_size": 8}}},
                   "block_order": ["i1"]}})
        css = section(generator)["custom_css"]
        self.assertEqual(css[0], ".rte p{font-size:19px}")
        self.assertEqual(css[3], ".text-block[class*=__title] p{font-size:32px;font-weight:700}")


class Overlay(unittest.TestCase):
    op = {"op": "overlay_opacity", "color_from": "overlay_color", "opacity_from": "overlay_opacity",
          "to": "overlay_color", "toggle": "toggle_overlay"}

    def test_deckkraft_wird_alphawert_der_farbe(self):
        generator = run(self, [self.op], {"a": {"type": "content",
                                                "settings": {"overlay_color": "#102030", "overlay_opacity": 40}}})
        settings = section(generator)["settings"]
        self.assertEqual((settings["toggle_overlay"], settings["overlay_color"]), (True, "rgba(16,32,48,0.40)"))

    def test_deckkraft_null_schaltet_das_overlay_aus(self):
        generator = run(self, [self.op], {"a": {"type": "content", "settings": {"overlay_opacity": 0}}})
        self.assertIs(section(generator)["settings"]["toggle_overlay"], False)
        self.assertNotIn("overlay_color", section(generator)["settings"])

    def test_kurze_hexfarbe_aus_dem_standard(self):
        self.assertEqual(layout.rgba("#000", 25), "rgba(0,0,0,0.25)")
        self.assertIsNone(layout.rgba("transparent", 25))


class SetByValueDropEmptyCopy(unittest.TestCase):
    def test_hoehe_setzt_mehrere_einstellungen_und_css(self):
        op = {"op": "set_by_value", "from": "height", "values": {
            "screen-height-one-half": {"set": {"section_height": "custom", "section_height_custom": 50},
                                       "css": [".x{y:z}"]}}}
        generator = run(self, [op], {"a": {"type": "content", "settings": {"height": "screen-height-one-half"}}})
        settings = section(generator)["settings"]
        self.assertEqual((settings["section_height"], settings["section_height_custom"]), ("custom", 50))
        self.assertEqual(section(generator)["custom_css"], [".x{y:z}"])

    def test_leere_platzhalter_werden_entfernt(self):
        generator = run(self, [{"op": "drop_empty_blocks"}], {"a": {"type": "content", "blocks": {
            "t1": text("<p>&nbsp;</p>"), "t2": text("<p>Da</p>"), "t3": text("{{ page.title }}"),
            "b1": {"type": "button", "settings": {"label": "Mehr"}}}, "block_order": ["t1", "t2", "t3", "b1"]}})
        node = section(generator)
        self.assertEqual(node["block_order"], ["t2", "t3"])
        self.assertEqual(sorted(node["blocks"]), ["t2", "t3"])
        self.assertEqual(entries(generator.report, "layout", op="drop_empty_blocks")[0]["result"], "t1, b1")

    def test_textfarbe_an_jeden_textblock(self):
        generator = run(self, [{"op": "copy_to_blocks", "from": "color", "block_type": "text", "to": "text_color"}],
                        {"a": {"type": "content", "blocks": {"t1": text("<p>a</p>")}, "block_order": ["t1"]}})
        self.assertEqual(section(generator)["blocks"]["t1"]["settings"]["text_color"], "#FFFFFF")


class HiddenByBlocks(unittest.TestCase):
    """Regel 11: Section an, alle Blöcke aus, im Ziel ausgeschaltet."""

    def test_section_mit_allen_bloecken_aus_wird_ausgeschaltet(self):
        generator = run(self, [], {
            "a": {"type": "content", "blocks": {"t1": {**text("<p>a</p>"), "disabled": True}}, "block_order": ["t1"]},
            "b": {"type": "content", "blocks": {"t1": {**text("<p>a</p>"), "disabled": True}, "t2": text("<p>b</p>")},
                  "block_order": ["t1", "t2"]},
            "c": {"type": "content"}})
        self.assertIs(section(generator)["disabled"], True)
        self.assertNotIn("disabled", section(generator, "b"))
        self.assertNotIn("disabled", section(generator, "c"))
        self.assertEqual([d["path"] for d in generator.report["disabled_sections"]], ["sections.a"])

    def test_hilfsfunktion(self):
        self.assertTrue(generate.hidden_by_blocks({"blocks": {"x": {"disabled": True}}}))
        self.assertFalse(generate.hidden_by_blocks({"disabled": True, "blocks": {"x": {"disabled": True}}}))
        self.assertFalse(generate.hidden_by_blocks({"blocks": {}}))


class CssBudget(unittest.TestCase):
    def test_was_nicht_passt_wird_ein_build_fall_mit_den_regeln(self):
        mapping = base_mapping([{"op": "page_width", "from": "width"},
                                {"op": "set_by_value", "from": "width", "values": {"wrapper": {"css": ["." + "b" * 300 + "{}"]}}}])
        mapping["sections"]["content"]["custom_css"] = ["." + "a" * 150 + "{}"]
        generator = run(self, [], {"a": {"type": "content", "settings": {"width": "wrapper"}}}, mapping=mapping)
        css = section(generator)["custom_css"]
        self.assertEqual(css[0], "." + "a" * 150 + "{}")
        self.assertEqual(css[1], ".section{--page-width:calc(max(1100px, 80vw) - 20px)}")
        case = entries(generator.report, "build", kind="layout_css_too_long")[0]
        self.assertEqual(case["rules"], ["." + "b" * 300 + "{}"])


class Validation(unittest.TestCase):
    def test_unbekannte_operation_und_fehlende_tabelle(self):
        mapping = base_mapping([{"op": "zaubern"}, {"op": "text_size", "from": "x", "sizes": "fehlt", "scope": "blocks"},
                                {"op": "page_width", "from": "width", "widths": "nirgends"}])
        errors = generate.validate_mapping(mapping)
        self.assertTrue(any("zaubern" not in e and "`op` muss" in e for e in errors))
        self.assertTrue(any("Größentabelle 'fehlt'" in e for e in errors))
        self.assertTrue(any("Breitentabelle 'nirgends'" in e for e in errors))

    def test_tabellen_brauchen_einen_wert_je_breakpoint(self):
        mapping = base_mapping([])
        mapping["layout"]["sizes"]["body"]["9"] = [10, 12]
        self.assertTrue(any("layout.sizes.body.9" in e for e in generate.validate_mapping(mapping)))

    def test_schluessel_der_operationen_werden_gegen_die_schemas_geprueft(self):
        mapping = base_mapping([{"op": "page_width", "from": "breite"},
                                {"op": "gap", "to": "abstand", "value": 4}])
        source, target = build(self, {"a": {"type": "content"}})
        generator = generate.Generator(mapping, None, source, target)
        generator.run()
        keys = {(f["key"], f["reason"][:10]) for f in generator.report["mapping_findings"]}
        self.assertIn(("breite", "Schlüssel "), keys)
        self.assertIn(("abstand", "Ziel-Schlü"), keys)

    def test_overrides_ersetzen_einzelne_breiten(self):
        merged = generate.merge_mapping(base_mapping([]), {"layout": {"widths": {"page": {"wrapper": "1200px"}}}})
        self.assertEqual(merged["layout"]["widths"]["page"], {"wrapper": "1200px", "wrapper--full-padded": "100vw"})
        self.assertEqual(merged["layout"]["breakpoints"], [750, 990])


class RequiredSections(unittest.TestCase):
    search = {"sections": {"search": {"type": "search-header", "settings": {}},
                           "main": {"type": "search-results", "settings": {}}}, "order": ["search", "main"]}

    def mapping(self):
        mapping = base_mapping([])
        mapping["sections"]["results"] = {"target": "search-results"}
        mapping["templates"]["search"] = {"action": "configure", "required_sections": ["search-header"]}
        return mapping

    def generate_search(self, target_search):
        source, target = build(self, {"a": {"type": "content"}}, target_search=target_search)
        (source / "sections" / "results.liquid").write_text(liquid({"name": "x", "settings": []}, "<div></div>"),
                                                            encoding="utf-8")
        write_json(source / "templates" / "search.json", {"sections": {"main": {"type": "results"}}, "order": ["main"]})
        generator = generate.Generator(self.mapping(), None, source, target)
        generator.run()
        return generator

    def test_fehlende_pflicht_section_kommt_aus_dem_ziel_an_ihre_stelle(self):
        generator = self.generate_search(self.search)
        document = generator.documents["templates/search.json"]
        self.assertEqual(document["order"], ["search", "main"])
        self.assertEqual(document["sections"]["search"]["type"], "search-header")
        self.assertEqual(generator.report["added_sections"][0]["type"], "search-header")

    def test_fehlt_sie_auch_im_ziel_ist_es_ein_build_fall(self):
        generator = self.generate_search({"sections": {"main": {"type": "search-results"}}, "order": ["main"]})
        self.assertEqual(entries(generator.report, "build", kind="required_section_missing")[0]["type"], "search-header")
        self.assertEqual(generator.documents["templates/search.json"]["order"], ["main"])

    def test_nur_templates_kennen_das_feld(self):
        mapping = base_mapping([])
        mapping["section_groups"] = {"header": {"action": "configure", "required_sections": ["x"]}}
        self.assertTrue(any("required_sections" in e for e in generate.validate_mapping(mapping)))


class Typography(unittest.TestCase):
    typography = {
        "scale": {"heading": "type_heading_size", "body": "type_body_size"},
        "roles": {"h1": {"sizes": [32, 35, 38], "scale": "heading", "preset": "type_size_h1"},
                  "h6": {"sizes": [16, 18, 19], "scale": "heading", "preset": "type_size_h6"},
                  "paragraph": {"sizes": [14, 15, 16], "scale": "body", "preset": "type_size_paragraph"}},
        "css_variable": "--font-size--{role}",
        "copy": {"type_subheading_font": "type_base_font"},
        "set": {"type_font_h6": "heading"},
    }

    def generate(self, settings_data):
        mapping = base_mapping([])
        mapping["typography"] = json.loads(json.dumps(self.typography))
        mapping["settings_data"] = {"type_base_font": {"to": "type_body_font", "transform": "font_handle",
                                                       "replace": {"alt_n4": "neu_n4"}},
                                    "type_body_size": {"transform": "drop"}, "type_heading_size": {"transform": "drop"}}
        source, target = build(self, {"a": {"type": "content"}}, settings_data=settings_data)
        generator = generate.Generator(mapping, None, source, target)
        generator.run()
        return generator, generator.documents["config/settings_data.json"]["current"]

    def test_presets_auf_die_naechste_stufe_bei_gleichstand_die_groessere(self):
        _, current = self.generate({})
        self.assertEqual((current["type_size_h1"], current["type_size_h6"], current["type_size_paragraph"]),
                         ("40", "20", "16"))

    def test_skala_der_quelle_und_schriften_je_rolle(self):
        _, current = self.generate({"type_heading_size": 150, "type_base_font": "alt_n4"})
        self.assertEqual(current["type_size_h1"], "56")
        self.assertEqual(current["type_subheading_font"], "neu_n4")
        self.assertEqual(current["type_font_h6"], "heading")

    def test_genaue_groessen_als_css_und_build_fall(self):
        generator, _ = self.generate({})
        css = generator.report["typography"]["css"].split("\n")
        self.assertEqual(css[0], ":root{--font-size--h1:32px;--font-size--h6:16px;--font-size--paragraph:14px}")
        self.assertTrue(css[2].startswith("@media screen and (min-width:990px){:root{--font-size--h1:38px"))
        self.assertEqual(len(entries(generator.report, "build", kind="type_scale_css")), 1)

    def test_aufbau_wird_geprueft(self):
        mapping = base_mapping([])
        mapping["typography"] = {"roles": {"h1": {"sizes": [32, 35], "preset": ""},
                                           "h2": {"sizes": [1, 2, 3], "preset": "type_size_h2", "scale": "x"}}}
        errors = generate.validate_mapping(mapping)
        self.assertTrue(any("preset" in e for e in errors))
        self.assertTrue(any("Skala 'x'" in e for e in errors))
        self.assertTrue(any("gleich viele" in e for e in errors))


class Library(unittest.TestCase):
    """Die mitgelieferte Bibliothek Broadcast auf Horizon trägt die Regeln aus dem Incident."""

    def setUp(self):
        self.mapping = json.loads(LIBRARY.read_text(encoding="utf-8"))

    def test_die_bibliothek_ist_gueltig(self):
        self.assertEqual(generate.validate_mapping(self.mapping), [])

    def test_inhaltsseiten_haben_breite_ausrichtung_groesse_und_abstand(self):
        ops = {op["op"] for op in self.mapping["sections"]["section-rich-text"]["layout"]}
        self.assertTrue({"page_width", "text_blocks", "text_size", "gap"} <= ops)
        hero = {op["op"] for op in self.mapping["sections"]["section-hero"]["layout"]}
        self.assertTrue({"overlay_opacity", "drop_empty_blocks"} <= hero)

    def test_suchseite_braucht_search_header_und_typografie_ist_gesetzt(self):
        self.assertEqual(self.mapping["templates"]["search"]["required_sections"], ["search-header"])
        self.assertIn("type_subheading_font", self.mapping["typography"]["copy"])
        self.assertEqual(self.mapping["typography"]["roles"]["paragraph"]["preset"], "type_size_paragraph")


if __name__ == "__main__":
    unittest.main()
