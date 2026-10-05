"""Die feste Liste der Transformationen: jede mit dem Fall, den sie abbildet, und dem, den sie verweigert.

Verweigern heißt `TransformError`; der Generator macht daraus einen `build`-Fall
im Report, statt einen Wert zu raten.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from theme import transforms  # noqa: E402
from theme.transforms import TransformError, apply  # noqa: E402


class Identity(unittest.TestCase):
    def test_value_is_unchanged(self):
        self.assertEqual(apply({"transform": "identity"}, "<p>Text</p>"), "<p>Text</p>")

    def test_without_transform_identity_applies(self):
        self.assertEqual(apply({"to": "x"}, 12), 12)

    def test_dynamic_sources_pass_identity(self):
        self.assertEqual(apply({}, "{{ product.title }}"), "{{ product.title }}")


class MapValues(unittest.TestCase):
    rule = {"transform": "map_values", "values": {"wrapper--full": "full-width", "true": "always", "4": "four"}}

    def test_text_values_are_translated(self):
        self.assertEqual(apply(self.rule, "wrapper--full"), "full-width")

    def test_non_text_values_are_looked_up_as_json(self):
        self.assertEqual(apply(self.rule, True), "always")
        self.assertEqual(apply(self.rule, 4), "four")

    def test_a_value_without_row_is_not_guessed(self):
        with self.assertRaises(TransformError):
            apply(self.rule, "wrapper--narrow")

    def test_a_table_is_required(self):
        with self.assertRaises(TransformError):
            apply({"transform": "map_values"}, "x")


class PxToNumber(unittest.TestCase):
    def test_px_text_and_numbers(self):
        rule = {"transform": "px_to_number"}
        self.assertEqual(apply(rule, "24px"), 24)
        self.assertEqual(apply(rule, " 24 "), 24)
        self.assertEqual(apply(rule, "1.5px"), 1.5)
        self.assertEqual(apply(rule, 30), 30)

    def test_other_units_and_booleans_are_refused(self):
        for value in ("2rem", "50%", True, None):
            with self.subTest(value=value), self.assertRaises(TransformError):
                apply({"transform": "px_to_number"}, value)


class BoolInvert(unittest.TestCase):
    def test_inverts(self):
        self.assertIs(apply({"transform": "bool_invert"}, True), False)
        self.assertIs(apply({"transform": "bool_invert"}, False), True)

    def test_non_booleans_are_refused(self):
        with self.assertRaises(TransformError):
            apply({"transform": "bool_invert"}, "true")


class FontHandle(unittest.TestCase):
    def test_a_valid_handle_passes(self):
        self.assertEqual(apply({"transform": "font_handle"}, "assistant_n4"), "assistant_n4")

    def test_replace_and_variant(self):
        rule = {"transform": "font_handle", "replace": {"alt_n4": "neu_n4"}, "variant": "n7"}
        self.assertEqual(apply(rule, "alt_n4"), "neu_n7")

    def test_a_css_font_stack_is_not_a_handle(self):
        with self.assertRaises(TransformError):
            apply({"transform": "font_handle"}, "Didot, serif")

    def test_a_bad_variant_is_refused(self):
        with self.assertRaises(TransformError):
            apply({"transform": "font_handle", "variant": "bold"}, "assistant_n4")


class ColorToPalette(unittest.TestCase):
    rule = {"to": "colors", "transform": "color_to_palette", "key": "primary"}

    def test_color_goes_to_the_palette_key(self):
        result = apply(self.rule, "#abc", {"scope": "settings_data"})
        self.assertEqual(result, {"key": "primary", "color": "#AABBCC"})

    def test_full_alpha_is_dropped_partial_alpha_is_refused(self):
        self.assertEqual(apply(self.rule, "#112233ff", {"scope": "settings_data"})["color"], "#112233")
        with self.assertRaises(TransformError):
            apply(self.rule, "#11223380", {"scope": "settings_data"})

    def test_only_in_settings_data(self):
        with self.assertRaises(TransformError):
            apply(self.rule, "#112233", {"scope": "section"})

    def test_invalid_key_and_non_colors_are_refused(self):
        with self.assertRaises(TransformError):
            apply(dict(self.rule, key="1st"), "#112233", {"scope": "settings_data"})
        with self.assertRaises(TransformError):
            apply(self.rule, "rgb(0,0,0)", {"scope": "settings_data"})


class TextToRichtext(unittest.TestCase):
    rule = {"transform": "text_to_richtext"}

    def test_plain_text_becomes_an_escaped_paragraph(self):
        self.assertEqual(apply(self.rule, "Kaffee & Kuchen <neu>"), "<p>Kaffee &amp; Kuchen &lt;neu&gt;</p>")

    def test_each_line_becomes_a_paragraph(self):
        self.assertEqual(apply(self.rule, "Erste Zeile\n\nZweite Zeile\n"), "<p>Erste Zeile</p><p>Zweite Zeile</p>")

    def test_existing_richtext_stays(self):
        for value in ("<p>Text</p>", "<ul><li>a</li></ul>", "<h2>Titel</h2>"):
            self.assertEqual(apply(self.rule, value), value)

    def test_empty_text_gives_no_value_and_non_text_is_refused(self):
        self.assertIsNone(apply(self.rule, "  \n "))
        with self.assertRaises(TransformError):
            apply(self.rule, 12)

    def test_unwrap_for_inline_richtext(self):
        self.assertEqual(transforms.unwrap_paragraph("<p>Ein <b>Satz</b></p>"), "Ein <b>Satz</b>")
        self.assertIsNone(transforms.unwrap_paragraph("<p>a</p><p>b</p>"))


class Drop(unittest.TestCase):
    def test_drop_returns_the_marker(self):
        self.assertIs(apply({"transform": "drop"}, "egal"), transforms.DROP)


class Apply(unittest.TestCase):
    def test_the_list_is_fixed(self):
        self.assertEqual(set(transforms.TRANSFORMS),
                         {"identity", "map_values", "px_to_number", "bool_invert", "font_handle",
                          "color_to_palette", "text_to_richtext", "drop"})

    def test_unknown_transform_is_refused(self):
        with self.assertRaises(TransformError):
            apply({"transform": "guess"}, 1)

    def test_dynamic_sources_cannot_be_converted(self):
        with self.assertRaises(TransformError):
            apply({"transform": "px_to_number"}, "{{ section.settings.x }}")


if __name__ == "__main__":
    unittest.main()
