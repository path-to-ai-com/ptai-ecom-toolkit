"""Die feste Liste der Transformationen für Einstellungen im Mapping.

Jede Zeile im Mapping nennt eine davon, etwa
`{"to": "padding_top", "transform": "px_to_number"}`. Die Parameter einer
Transformation stehen in derselben Zeile (`values`, `replace`, `key` ...).
Was keine dieser Transformationen abbildet, wird im Mapping `build` mit
Begründung, nie stilles Raten: Eine Transformation, die einen Wert nicht
sicher umrechnen kann, wirft `TransformError`, und der Generator meldet den
Fall im Report als `build`, statt einen Wert zu erfinden.

Die Liste ist bewusst klein und jede Transformation getestet
(`scripts/tests/test_theme_generate_transforms.py`).
"""
import html
import json
import re

#: Rückgabe von `drop`: Die Einstellung wird nicht geschrieben.
DROP = object()

NUMBER_WITH_PX = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px)?\s*$")
#: Schrift-Handle der Shopify-Schriftbibliothek: Familie, Unterstrich, Stil und Gewicht.
FONT_HANDLE = re.compile(r"^[a-z0-9_]+_[nio][1-9]$")
FONT_VARIANT = re.compile(r"^[nio][1-9]$")
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
#: Schlüssel einer `color_palette`: Buchstabe am Anfang, dann Buchstaben, Ziffern, Unterstriche.
PALETTE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
#: Ein Wert, der schon als richtext gebaut ist: Wurzel ist ein Absatz, eine Liste oder eine Überschrift.
#: Überschriften stehen mit drin, weil Einpacken sie zu sichtbarem Markup machen würde.
RICHTEXT_ROOT = re.compile(r"^\s*<(p|ul|ol|h[1-6])[\s>]", re.I)
SINGLE_PARAGRAPH = re.compile(r"^\s*<p(?:\s[^>]*)?>(.*)</p>\s*$", re.S | re.I)


class TransformError(Exception):
    """Der Wert lässt sich mit dieser Transformation nicht sicher abbilden."""


def _lookup_key(value) -> str:
    """Schlüssel für `map_values`: Text bleibt Text, alles andere als JSON (`true`, `12`)."""
    return value if isinstance(value, str) else json.dumps(value)


def identity(value, rule: dict, context: dict):
    """Wert unverändert übernehmen."""
    return value


def map_values(value, rule: dict, context: dict):
    """Wert über eine Tabelle übersetzen; ein Wert ohne Zeile ist ein `build`-Fall.

    `{"transform": "map_values", "values": {"wrapper--full": "full-width"}}`.
    Nicht-Text-Werte werden als JSON nachgeschlagen (`"true"`, `"12"`).
    """
    table = rule.get("values")
    if not isinstance(table, dict) or not table:
        raise TransformError("map_values braucht eine Tabelle `values`")
    key = _lookup_key(value)
    if key not in table:
        raise TransformError(f"Wert {key!r} steht nicht in `values`")
    return table[key]


def px_to_number(value, rule: dict, context: dict):
    """`"24px"` oder `"24"` zu `24`; Zahlen bleiben. Andere Einheiten sind ein `build`-Fall."""
    if isinstance(value, bool):
        raise TransformError("Wahrheitswert ist keine Pixelangabe")
    if isinstance(value, (int, float)):
        number = value
    elif isinstance(value, str) and NUMBER_WITH_PX.match(value):
        number = float(NUMBER_WITH_PX.match(value).group(1))
    else:
        raise TransformError(f"{value!r} ist keine Pixelangabe")
    return int(number) if float(number).is_integer() else number


def bool_invert(value, rule: dict, context: dict):
    """`true` zu `false` und umgekehrt, etwa `hide_title` zu `show_title`."""
    if not isinstance(value, bool):
        raise TransformError(f"{value!r} ist kein Wahrheitswert")
    return not value


def font_handle(value, rule: dict, context: dict):
    """Schrift-Handle prüfen und bei Bedarf ersetzen.

    `replace` übersetzt ganze Handles (etwa abgekündigte Schriften auf ihren
    Ersatz, die Liste kommt aus dem Mapping, nicht aus diesem Modul);
    `variant` setzt Stil und Gewicht neu (`"n7"`). Ein Wert, der kein Handle
    ist, etwa ein CSS-Schriftstapel, ist ein `build`-Fall.
    """
    if not isinstance(value, str) or not FONT_HANDLE.match(value):
        raise TransformError(f"{value!r} ist kein Schrift-Handle")
    handle = (rule.get("replace") or {}).get(value, value)
    variant = rule.get("variant")
    if variant is not None:
        if not FONT_VARIANT.match(str(variant)):
            raise TransformError(f"`variant` {variant!r} ist kein Stil mit Gewicht wie n4")
        handle = handle.rsplit("_", 1)[0] + "_" + variant
    if not FONT_HANDLE.match(handle):
        raise TransformError(f"Ersatz {handle!r} ist kein Schrift-Handle")
    return handle


def normalize_hex(value: str) -> str:
    """`#abc` zu `#AABBCC`; `#rrggbbff` verliert das volle Alpha, anderes Alpha bleibt Fehler."""
    if not isinstance(value, str) or not HEX_COLOR.match(value):
        raise TransformError(f"{value!r} ist keine Hex-Farbe")
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    if len(digits) == 8:
        if digits[6:].lower() != "ff":
            raise TransformError(f"{value!r} hat Transparenz, eine Palette kennt keine")
        digits = digits[:6]
    return "#" + digits.upper()


def color_to_palette(value, rule: dict, context: dict):
    """Eine Farbe der Quelle als Farbe in der `color_palette` des Ziels.

    Horizon ab 4.0 hat keine Farbschemata mehr, sondern eine Palette mit 2 bis
    20 Farben; ein Mapping auf `color_scheme` ist dort falsch. Die Zeile nennt
    die Palette als `to` und den Schlüssel als `key`:
    `{"to": "colors", "transform": "color_to_palette", "key": "primary"}`.
    Nur in `settings_data` erlaubt; Ergebnis ist `{"key": ..., "color": "#RRGGBB"}`,
    das der Generator in das Palettenobjekt einträgt.
    """
    if context.get("scope") != "settings_data":
        raise TransformError("color_to_palette gilt nur in settings_data")
    key = rule.get("key")
    if not isinstance(key, str) or not PALETTE_KEY.match(key):
        raise TransformError(f"Palettenschlüssel {key!r} ist ungültig")
    return {"key": key, "color": normalize_hex(value)}


def wrap_paragraphs(text: str, escape: bool = True) -> str | None:
    """Text in Absätze fassen: jede nicht leere Zeile ein `<p>`; leerer Text ergibt `None`."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return "".join(f"<p>{html.escape(line, quote=False) if escape else line}</p>" for line in lines)


def is_richtext(value) -> bool:
    return isinstance(value, str) and bool(RICHTEXT_ROOT.match(value))


def unwrap_paragraph(value: str) -> str | None:
    """Die Absatz-Hülle eines einzelnen Absatzes entfernen (für `inline_richtext`); sonst `None`."""
    match = SINGLE_PARAGRAPH.match(value)
    if not match or "<p" in match.group(1).lower():
        return None
    return match.group(1)


def text_to_richtext(value, rule: dict, context: dict):
    """Klartext für ein `richtext`-Feld: HTML maskiert, jede Zeile ein Absatz.

    Ein `richtext`-Wert braucht ein Wurzelelement (Absatz oder Liste), Klartext
    aus einem `text`- oder `textarea`-Feld hat keins. Ein Wert, der schon mit
    `<p>`, `<ul>`, `<ol>` oder einer Überschrift beginnt, bleibt unverändert.
    """
    if not isinstance(value, str):
        raise TransformError(f"{value!r} ist kein Text")
    if is_richtext(value):
        return value
    return wrap_paragraphs(value)


def drop(value, rule: dict, context: dict):
    """Einstellung bewusst nicht übernehmen; der Report führt sie als gewollt."""
    return DROP


TRANSFORMS = {
    "identity": identity,
    "map_values": map_values,
    "px_to_number": px_to_number,
    "bool_invert": bool_invert,
    "font_handle": font_handle,
    "color_to_palette": color_to_palette,
    "text_to_richtext": text_to_richtext,
    "drop": drop,
}


def apply(rule: dict, value, context: dict | None = None):
    """Die Transformation einer Mapping-Zeile auf einen Wert anwenden.

    Ohne `transform` gilt `identity`. Ein unbekannter Name ist ein Fehler im
    Mapping und wirft ebenfalls `TransformError`.
    """
    name = rule.get("transform", "identity")
    function = TRANSFORMS.get(name)
    if function is None:
        raise TransformError(f"Transformation {name!r} gibt es nicht")
    if isinstance(value, str) and "{{" in value and name not in ("identity", "drop"):
        # Dynamische Quellen (`{{ product.metafields... }}`) lassen sich nicht umrechnen.
        raise TransformError("dynamische Quelle lässt sich nicht umrechnen")
    return function(value, rule, context or {})
