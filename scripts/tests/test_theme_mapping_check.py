"""Prüfung einer Mapping-Datei der Theme-Migration und die mitgelieferte Bibliothek.

Die Schema-Auszüge hier sind synthetisch: erfundene Themes `Alt` und `Neu` mit
Namen, die in keinem kommerziellen Theme vorkommen müssen. Code eines Themes
liegt nirgends im Repo, auch nicht als Fixture.
"""
import contextlib
import copy
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from theme import mapping_check

ROOT = Path(__file__).resolve().parents[2]
LIBRARY_DIR = ROOT / "reference" / "theme-migration" / "mappings"
LIBRARY = LIBRARY_DIR / "broadcast-5__horizon-4.json"

SOURCE = {
    "theme": {"name": "Alt", "version": "1.0.0"},
    "sections": {
        "banner": {
            "settings": {
                "heading": {"type": "text"},
                "height": {"type": "select", "options": ["small", "large"]},
                "padding_top": {"type": "range", "min": 0, "max": 200},
                "bg": {"type": "color"},
            },
            "blocks": {"button": {"settings": {"label": {"type": "text"}, "url": {"type": "url"}}}},
        },
        "api-cart": {"settings": {}, "blocks": {}},
    },
    "settings_schema": {"text_color": {"type": "color"}, "heading_font": {"type": "font_picker"}},
    "templates": ["index", "product"],
    "section_groups": ["group-header"],
}

TARGET = {
    "theme": {"name": "Neu", "version": "4.0.0"},
    "sections": {
        "hero": {
            "settings": {
                "section_height": {"type": "select", "options": ["", "small", "large"]},
                "padding-block-start": {"type": "range", "min": 0, "max": 100},
                "background_color": {"type": "color"},
            },
            "blocks": {"@theme": {}, "@app": {}},
        },
    },
    "blocks": {
        "text": {"settings": {"text": {"type": "richtext"}}, "blocks": []},
        "button": {"settings": {"label": {"type": "text"}, "link": {"type": "url"}}, "blocks": []},
        "_slide": {"settings": {}, "blocks": ["text"]},
    },
    "settings_schema": {"color_palette": {"type": "color_palette"},
                        "type_heading_font": {"type": "font_picker"}},
    "templates": ["index", "product"],
    "section_groups": ["header-group"],
}

MAPPING = {
    "source": {"theme": "Alt", "version": "1.x"},
    "target": {"theme": "Neu", "version": "4.x"},
    "sections": {
        "banner": {
            "action": "configure",
            "target": "hero",
            "settings": {
                "heading": {"to": "text", "transform": "identity", "block": "text"},
                "height": {"to": "section_height", "transform": "map_values",
                           "values": {"small": "small", "large": "large"}},
                "padding_top": {"to": "padding-block-start", "transform": "identity"},
                "bg": {"to": "background_color", "transform": "identity"},
            },
            "blocks": {"button": {"target": "button", "settings": {
                "label": {"to": "label", "transform": "identity"},
                "url": {"to": "link", "transform": "identity"}}}},
            "notes": "",
        },
        "api-cart": {"action": "drop", "notes": "Endpunkt, das Ziel lädt Sections selbst nach."},
    },
    "settings_data": {
        "text_color": {"to": "color_palette", "transform": "color_to_palette", "key": "foreground"},
        "heading_font": {"to": "type_heading_font", "transform": "font_handle"},
    },
    "templates": {"index": {"action": "configure"}, "product": {"action": "configure"}},
    "section_groups": {"group-header": {"action": "configure", "target": "header-group"}},
}


def run(mapping=None, source=None, target=None):
    return mapping_check.check(mapping or MAPPING, source or SOURCE, target or TARGET)


def codes(findings):
    return sorted({finding["code"] for finding in findings})


def changed(change):
    """Kopie von MAPPING, an der `change` etwas verändert."""
    mapping = copy.deepcopy(MAPPING)
    change(mapping)
    return mapping


class TestMappingCheck(unittest.TestCase):
    def test_gueltiges_mapping_ohne_fehler(self):
        result = run()
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["coverage"], {"configure": 1, "build": 0, "drop": 1})

    def test_quell_section_ohne_ausgang_ist_ein_fehler(self):
        result = run(changed(lambda m: m["sections"].pop("api-cart")))
        self.assertIn("missing_source_section", codes(result["errors"]))

    def test_section_die_es_in_der_quelle_nicht_gibt(self):
        result = run(changed(lambda m: m["sections"].update(
            {"veraltet": {"action": "drop", "notes": "gibt es nicht mehr"}})))
        self.assertIn("unknown_source_section", codes(result["errors"]))

    def test_unbekannte_ziel_section(self):
        result = run(changed(lambda m: m["sections"]["banner"].update({"target": "gibt-es-nicht"})))
        self.assertEqual(codes(result["errors"]), ["unknown_target_section"])

    def test_ziel_einstellung_die_es_nicht_gibt(self):
        def change(m):
            m["sections"]["banner"]["settings"]["bg"]["to"] = "color_scheme"
        self.assertEqual(codes(run(changed(change))["errors"]), ["unknown_target_setting"])

    def test_ziel_einstellung_im_kindblock_wird_gegen_den_block_geprueft(self):
        def change(m):
            m["sections"]["banner"]["settings"]["heading"]["to"] = "heading"
        self.assertEqual(codes(run(changed(change))["errors"]), ["unknown_target_setting"])

    def test_unbekannter_kindblock(self):
        def change(m):
            m["sections"]["banner"]["settings"]["heading"]["block"] = "_heading"
        self.assertEqual(codes(run(changed(change))["errors"]), ["unknown_target_block"])

    def test_unbekannte_transformation(self):
        def change(m):
            m["sections"]["banner"]["settings"]["bg"]["transform"] = "guess"
        self.assertEqual(codes(run(changed(change))["errors"]), ["unknown_transform"])

    def test_quell_einstellung_die_es_nicht_gibt(self):
        def change(m):
            m["sections"]["banner"]["settings"]["subheading"] = {"to": "background_color",
                                                                 "transform": "identity"}
        self.assertEqual(codes(run(changed(change))["errors"]), ["unknown_source_setting"])

    def test_privater_block_wird_ueber_theme_nicht_angenommen(self):
        def change(m):
            m["sections"]["banner"]["blocks"]["button"] = {"target": "_slide", "settings": {}}
        self.assertEqual(codes(run(changed(change))["errors"]), ["block_not_accepted"])

    def test_block_im_eltern_block_wird_gegen_dessen_liste_geprueft(self):
        def change(m):
            m["sections"]["banner"]["blocks"]["button"]["parent"] = "_slide"
        self.assertEqual(codes(run(changed(change))["errors"]), ["block_not_accepted"])

    def test_build_ohne_begruendung_ist_ein_fehler(self):
        result = run(changed(lambda m: m["sections"].update({"api-cart": {"action": "build"}})))
        self.assertEqual(codes(result["errors"]), ["missing_reason"])

    def test_unbekannter_ausgang(self):
        result = run(changed(lambda m: m["sections"]["api-cart"].update({"action": "maybe"})))
        self.assertEqual(codes(result["errors"]), ["unknown_action"])

    def test_map_values_mit_zielwert_ausserhalb_der_optionen(self):
        def change(m):
            m["sections"]["banner"]["settings"]["height"]["values"]["large"] = "huge"
        self.assertEqual(codes(run(changed(change))["errors"]), ["invalid_target_value"])

    def test_map_values_ohne_werte(self):
        def change(m):
            del m["sections"]["banner"]["settings"]["height"]["values"]
        self.assertEqual(codes(run(changed(change))["errors"]), ["missing_values"])

    def test_ungueltiger_paletten_schluessel(self):
        def change(m):
            m["settings_data"]["text_color"]["key"] = "1-text"
        self.assertEqual(codes(run(changed(change))["errors"]), ["palette_key"])

    def test_unbekanntes_ziel_template_und_gruppe(self):
        def change(m):
            m["templates"]["customers/account"] = {"action": "configure"}
            m["section_groups"]["group-header"]["target"] = "overlay-group"
        self.assertEqual(codes(run(changed(change))["errors"]),
                         ["unknown_target_section_group", "unknown_target_template"])

    def test_pflichtfeld_fehlt(self):
        result = run(changed(lambda m: m.pop("sections")))
        self.assertEqual(codes(result["errors"]), ["invalid_format"])

    def test_wertebereich_und_typwechsel_sind_hinweise_keine_fehler(self):
        """Die Quelle erlaubt 200 px Abstand, das Ziel 100; Klartext landet in richtext."""
        result = run()
        self.assertEqual(result["errors"], [])
        self.assertIn("range_exceeds", codes(result["warnings"]))
        self.assertIn("type_mismatch", codes(result["warnings"]))

    def test_nicht_zugeordnete_quell_einstellung_ist_ein_hinweis(self):
        def change(m):
            del m["sections"]["banner"]["settings"]["bg"]
        result = run(changed(change))
        self.assertEqual(result["errors"], [])
        self.assertIn("unmapped_source_setting", codes(result["warnings"]))

    def test_einstellungslisten_als_namen_ohne_typpruefung(self):
        source = copy.deepcopy(SOURCE)
        source["sections"]["banner"]["settings"] = list(source["sections"]["banner"]["settings"])
        result = run(source=source)
        self.assertEqual(result["errors"], [])
        self.assertNotIn("range_exceeds", codes(result["warnings"]))


class TestMappingCheckCli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def call(self, mapping):
        args = ["--mapping", mapping, "--source-schema", self.write("source.json", SOURCE),
                "--target-schema", self.write("target.json", TARGET),
                "--out", str(self.dir / "out.json")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mapping_check.main(args)
        return code, json.loads(out.getvalue())

    def test_exit_code_null_ohne_fehler(self):
        code, summary = self.call(self.write("mapping.json", MAPPING))
        self.assertEqual(code, 0)
        self.assertTrue(summary["ok"])
        self.assertTrue((self.dir / "out.json").exists())

    def test_exit_code_eins_mit_fehlern(self):
        broken = changed(lambda m: m["sections"].pop("api-cart"))
        code, summary = self.call(self.write("mapping.json", broken))
        self.assertEqual((code, summary["errors"]), (1, 1))

    def test_exit_code_zwei_bei_unlesbarer_datei(self):
        path = self.dir / "kaputt.json"
        path.write_text("{", encoding="utf-8")
        code, summary = self.call(str(path))
        self.assertEqual(code, 2)
        self.assertFalse(summary["ok"])


def entries_with_transform(node, where="$"):
    """Alle Zuordnungen mit einem Feld `transform`, rekursiv."""
    if isinstance(node, dict):
        if "transform" in node:
            yield where, node
        for key, value in node.items():
            yield from entries_with_transform(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from entries_with_transform(value, f"{where}[{index}]")


class TestLibrary(unittest.TestCase):
    """Die mitgelieferte Bibliothek Broadcast 5 auf Horizon 4."""

    @classmethod
    def setUpClass(cls):
        cls.mapping = json.loads(LIBRARY.read_text(encoding="utf-8"))

    def test_format_nach_spec(self):
        for key in ("source", "target", "sections", "settings_data", "templates"):
            self.assertIsInstance(self.mapping.get(key), dict, key)
        self.assertEqual(self.mapping["source"]["theme"], "Broadcast")
        self.assertEqual(self.mapping["target"]["theme"], "Horizon")
        self.assertTrue(self.mapping["target"]["version"].startswith("4."))

    def test_jeder_ausgang_ist_vollstaendig(self):
        for name, entry in self.mapping["sections"].items():
            with self.subTest(section=name):
                self.assertIn(entry["action"], mapping_check.ACTIONS)
                if entry["action"] == "configure":
                    self.assertTrue(entry.get("target"))
                else:
                    self.assertTrue(entry.get("notes", "").strip())
                for block, spec in (entry.get("blocks") or {}).items():
                    action = spec.get("action", "configure")
                    self.assertIn(action, mapping_check.ACTIONS, block)
                    if action == "configure":
                        self.assertTrue(spec.get("target"), block)
                    else:
                        self.assertTrue(spec.get("notes", "").strip(), block)

    def test_nur_erlaubte_transformationen(self):
        found = list(entries_with_transform(self.mapping))
        self.assertTrue(found)
        for where, entry in found:
            with self.subTest(where=where):
                self.assertIn(entry["transform"], mapping_check.TRANSFORMS)
                if entry["transform"] == "map_values":
                    self.assertTrue(entry.get("values"))
                if entry["transform"] == "color_to_palette":
                    self.assertRegex(entry.get("key", ""), mapping_check.PALETTE_KEY)
                if entry["transform"] == "drop":
                    self.assertTrue(entry.get("note"), "drop ohne Begründung")
                else:
                    self.assertTrue(entry.get("to"))

    def test_kein_farbschema_im_ziel(self):
        """Horizon hat ab 4.0.0 eine color_palette statt Farbschemata."""
        targets = {entry.get("to") for _, entry in entries_with_transform(self.mapping)}
        self.assertFalse({t for t in targets if t and "color_scheme" in t})

    def test_readme_nennt_die_abdeckung_der_bibliothek(self):
        readme = (LIBRARY_DIR / "README.md").read_text(encoding="utf-8")
        coverage = mapping_check.coverage(self.mapping)
        for action, count in coverage.items():
            with self.subTest(action=action):
                self.assertRegex(readme, rf"\|\s*`{action}`\s*\|\s*{count}\s*\|")
        self.assertRegex(readme, rf"\|\s*Summe\s*\|\s*{sum(coverage.values())}\s*\|")

    def test_keine_absoluten_pfade(self):
        for path in (LIBRARY, LIBRARY_DIR / "README.md"):
            with self.subTest(path=path.name):
                self.assertIsNone(re.search(r"/(Users|home)/", path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()


class GeneratorAlignmentTest(unittest.TestCase):
    """Die Prüfung kennt, was der Generator kennt (Integration 05.10.2026)."""

    def test_text_to_richtext_ist_eine_erlaubte_transformation(self):
        self.assertIn("text_to_richtext", mapping_check.TRANSFORMS)

    def test_die_listen_von_pruefung_und_generator_stimmen_ueberein(self):
        from theme import transforms
        self.assertEqual(set(mapping_check.TRANSFORMS), set(transforms.TRANSFORMS))
