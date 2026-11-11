"""Layout-Regeln: die Gestaltung einer Quell-Section in Einstellungen und CSS des Ziels übersetzen.

Das Mapping überträgt Inhalte und Einstellungen Zeile für Zeile. Breite, Ausrichtung,
Textgröße, Abstände, Deckkraft und Höhe stecken in der Quelle aber oft in Werten, die
das Ziel anders oder gar nicht als Einstellung kennt (Broadcast `wrapper` ist eine
feste Seitenbreite, `text_size` eine Größenstufe je Breakpoint). Ohne Übersetzung fällt
das Ziel auf seine Standardwerte zurück: schmale Textspalte links, Text in 14 statt
19 px, deckendes Overlay über dem Bild. So geschehen bei einem Launch im November 2026;
die Abnahme per Stichprobe hat es nicht gefunden.

Eine Section im Mapping nennt deshalb unter `layout` eine Liste von Operationen aus der
festen Liste unten. Jede liest Werte der Quell-Section oder ihrer Blöcke (fehlender
Schlüssel heißt Schema-Standard der Quelle) und schreibt Einstellungen des Ziels, geprüft
gegen dessen Schema, oder eine CSS-Regel für `custom_css` der Section. Die Tabellen
(Breakpoints, Breiten, Größenstufen) stehen einmal je Theme-Paar unter `layout` auf der
obersten Ebene des Mappings. Kann eine Operation einen Wert nicht sicher abbilden, schreibt
sie nichts; es wird nie geraten.
"""
import copy
import re

from theme import schema as schema_module

OPERATIONS = {
    "page_width": ("from",),
    "text_blocks": (),
    "text_size": ("from", "sizes", "scope"),
    "gap": ("to", "value"),
    "overlay_opacity": ("color_from", "opacity_from", "to", "toggle"),
    "set_by_value": ("from", "values"),
    "drop_empty_blocks": (),
    "copy_to_blocks": ("from", "to"),
}
SCOPES = ("section", "blocks", "child")
EMPTY_TEXT = re.compile(r"<[^>]+>|\s|&nbsp;")
HEX6 = re.compile(r"^#?([0-9a-fA-F]{6})$")
HEX3 = re.compile(r"^#?([0-9a-fA-F]{3})$")


def lookup_key(value) -> str:
    """Schlüssel für Tabellen: Text direkt, andere Werte als JSON-Text (wie `map_values`)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def validate_tables(layout) -> list[str]:
    """Aufbau der Tabellen unter `layout` auf oberster Ebene."""
    if layout is None:
        return []
    if not isinstance(layout, dict):
        return ["layout: muss ein Objekt sein"]
    errors = []
    points = layout.get("breakpoints", [])
    if not (isinstance(points, list) and all(isinstance(p, int) and p > 0 for p in points)
            and points == sorted(set(points))):
        errors.append("layout.breakpoints: aufsteigende Liste ganzer Pixelwerte")
        points = []
    for name, table in (layout.get("widths") or {}).items():
        if not isinstance(table, dict) or not all(isinstance(v, str) and v for v in table.values()):
            errors.append(f"layout.widths.{name}: Objekt aus Wert der Quelle und CSS-Länge")
    scale = layout.get("scale") or {}
    if not isinstance(scale, dict) or not all(isinstance(v, str) and v for v in scale.values()):
        errors.append("layout.scale: Objekt aus Größentabelle und globaler Einstellung der Quelle (Prozent)")
    for name, table in (layout.get("sizes") or {}).items():
        if not isinstance(table, dict):
            errors.append(f"layout.sizes.{name}: muss ein Objekt sein")
            continue
        for step, values in table.items():
            if not (isinstance(values, list) and len(values) == len(points) + 1
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in values)):
                errors.append(f"layout.sizes.{name}.{step}: je eine Pixelgröße unter dem ersten Breakpoint "
                              f"und ab jedem Breakpoint ({len(points) + 1} Werte)")
    return errors


def validate_operations(where: str, operations, layout: dict | None) -> list[str]:
    """Aufbau einer `layout`-Liste an einer Section."""
    if operations is None:
        return []
    if not isinstance(operations, list):
        return [f"{where}.layout: Liste von Operationen"]
    errors = []
    widths = (layout or {}).get("widths") or {}
    sizes = (layout or {}).get("sizes") or {}
    for index, operation in enumerate(operations):
        at = f"{where}.layout[{index}]"
        if not isinstance(operation, dict) or operation.get("op") not in OPERATIONS:
            errors.append(f"{at}: `op` muss eine dieser Operationen sein: {', '.join(sorted(OPERATIONS))}")
            continue
        name = operation["op"]
        for field in OPERATIONS[name]:
            if field not in operation:
                errors.append(f"{at}: {name} braucht `{field}`")
        if name == "page_width" and operation.get("widths", "page") not in widths:
            errors.append(f"{at}: Breitentabelle {operation.get('widths', 'page')!r} fehlt unter layout.widths")
        if name == "text_size":
            if operation.get("sizes") not in sizes:
                errors.append(f"{at}: Größentabelle {operation.get('sizes')!r} fehlt unter layout.sizes")
            if operation.get("scope") not in SCOPES:
                errors.append(f"{at}: `scope` ist section, blocks oder child")
            if operation.get("baselines") is not None and not isinstance(operation["baselines"], dict):
                errors.append(f"{at}: `baselines` ordnet Werten von `baseline_from` eine Stufe zu")
            if operation.get("scope") == "section" and not operation.get("selector"):
                errors.append(f"{at}: scope section braucht `selector`")
            if operation.get("scope") == "child" and not operation.get("child_id"):
                errors.append(f"{at}: scope child braucht `child_id`")
        if name == "set_by_value":
            values = operation.get("values")
            if not isinstance(values, dict) or not all(
                    isinstance(v, dict) and set(v) <= {"set", "css"} for v in values.values()):
                errors.append(f"{at}: `values` ordnet jedem Wert der Quelle {{\"set\": {{…}}, \"css\": […]}} zu")
        if name == "gap" and not (isinstance(operation.get("value"), (int, float))
                                  and not isinstance(operation.get("value"), bool)):
            errors.append(f"{at}: `value` ist eine Zahl")
    return errors


def size_rules(selector: str, values: list, breakpoints: list, declarations: str = "") -> list[str]:
    """CSS je Breakpoint; eine Stufe, die sich nicht ändert, bekommt keine eigene Regel."""
    extra = f";{declarations}" if declarations else ""
    rules = [f"{selector}{{font-size:{format_px(values[0])}{extra}}}"]
    previous = values[0]
    for point, value in zip(breakpoints, values[1:]):
        if value != previous:
            rules.append(f"@media(min-width:{point}px){{{selector}{{font-size:{format_px(value)}}}}}")
        previous = value
    return rules


def format_px(value) -> str:
    return f"{int(value)}px" if float(value).is_integer() else f"{value}px"


def rgba(color, opacity) -> str | None:
    """Hex-Farbe und Deckkraft in Prozent als rgba; None, wenn die Farbe kein Hex ist."""
    text = str(color or "").strip()
    match = HEX6.match(text)
    if match is None:
        short = HEX3.match(text)
        if short is None:
            return None
        text = "".join(c * 2 for c in short.group(1))
    else:
        text = match.group(1)
    red, green, blue = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    alpha = max(0.0, min(1.0, float(opacity) / 100))
    return f"rgba({red},{green},{blue},{alpha:.2f})"


def is_empty_block(block: dict) -> bool:
    """Ein Text ohne sichtbaren Inhalt oder ein Button ohne Beschriftung oder Ziel."""
    settings = block.get("settings") or {}
    if block.get("type") == "text":
        text = settings.get("text", "")
        return isinstance(text, str) and "{{" not in text and not EMPTY_TEXT.sub("", text)
    if block.get("type") == "button":
        return not settings.get("label") or not settings.get("link")
    return False


class LayoutPass:
    """Wendet die `layout`-Liste einer Section an. Gehört zu einem Lauf des Generators.

    `generator` liefert `put` (Schema-Prüfung und Report), `report`, `file` und die
    Schemas beider Themes. Ergebnis von `apply` sind die CSS-Regeln für die Section;
    Einstellungen schreibt die Operation selbst in den Knoten.
    """

    def __init__(self, generator, tables: dict | None):
        self.generator = generator
        self.tables = tables or {}
        self.breakpoints = self.tables.get("breakpoints") or []
        self.factors: dict[str, float] = {}

    def factor(self, table: str) -> float:
        """Skalierung einer Größentabelle aus den globalen Einstellungen der Quelle (Prozent).

        Broadcast vergrößert alle Stufen über `type_body_size` und `type_heading_size`; die
        Tabellen gelten für 100 Prozent.
        """
        if table in self.factors:
            return self.factors[table]
        key = (self.tables.get("scale") or {}).get(table)
        value = None
        if key:
            path = self.generator.source_dir / "config" / "settings_data.json"
            current = {}
            if path.is_file():
                document = schema_module.read_json_file(path)
                current = document.get("current") or {}
                if isinstance(current, str):
                    current = (document.get("presets") or {}).get(current) or {}
            value = current.get(key, self.generator.source["settings_schema"]["defaults"].get(key))
        try:
            factor = float(value) / 100 if value is not None else 1.0
        except (TypeError, ValueError):
            factor = 1.0
        self.factors[table] = factor
        return factor

    def scaled(self, table: str, values: list) -> list:
        factor = self.factor(table)
        return [round(v * factor) for v in values] if factor != 1.0 else list(values)

    # Hilfen ------------------------------------------------------------------

    def source_value(self, data: dict, view: dict | None, key: str):
        """Wert der Quelle; fehlt er, gilt der Standard aus dem Schema der Quelle (Regel 1)."""
        settings = data.get("settings") or {}
        if key in settings:
            return settings[key]
        return ((view or {}).get("defaults") or {}).get(key)

    def walk(self, node: dict, view: dict | None):
        """Alle Blöcke unter einem Knoten mit ihrer Schema-Sicht, Eltern vor Kindern."""
        for block_id, child in list((node.get("blocks") or {}).items()):
            child_view = schema_module.block_definition(self.generator.target, view, child.get("type", ""))
            yield block_id, child, child_view, node
            yield from self.walk(child, child_view)

    def source_blocks(self, data: dict, source_view: dict | None, types) -> list:
        """Blöcke der Quell-Section in ihrer Reihenfolge, nur die genannten Typen."""
        blocks = data.get("blocks") or {}
        order = [b for b in data.get("block_order") or [] if b in blocks]
        order += [b for b in blocks if b not in order]
        found = []
        for block_id in order:
            block = blocks[block_id]
            if types and block.get("type") not in types:
                continue
            view = schema_module.block_definition(self.generator.source, source_view, block.get("type", ""))
            found.append((block_id, block, view))
        return found

    def target_id(self, path: str, source_id: str) -> str:
        """ID im Ziel: gleich, außer der Generator hat eine ungültige ID ersetzt."""
        for entry in self.generator.report["renamed_block_ids"]:
            inside = entry["path"] == path or entry["path"].startswith(f"{path}.")
            if entry["file"] == self.generator.file and inside and entry["old_id"] == source_id:
                return entry["new_id"]
        return source_id

    def find(self, node: dict, view: dict, block_id: str):
        for child_id, child, child_view, parent in self.walk(node, view):
            if child_id == block_id:
                return child, child_view
        return None, None

    def put(self, settings: dict, view: dict | None, key: str, value, path: str, operation: str) -> bool:
        if view is None:
            return False
        return self.generator.put(settings, view, key, copy.deepcopy(value), f"{path}.settings.{key}",
                                  f"layout:{operation}")

    def note(self, path: str, operation: str, result: str) -> None:
        self.generator.report["layout"].append({"file": self.generator.file, "path": path, "op": operation,
                                                "result": result})

    # Operationen ---------------------------------------------------------------

    def apply(self, path: str, operations: list, data: dict, source_view: dict | None, node: dict,
              target_view: dict) -> list[str]:
        css: list[str] = []
        if not isinstance(operations, list):
            return css
        for operation in operations:
            # Ungültige Einträge hat validate_operations vor dem Lauf gemeldet; hier nur überspringen.
            if not isinstance(operation, dict) or operation.get("op") not in OPERATIONS:
                continue
            handler = getattr(self, f"op_{operation['op']}")
            css.extend(handler(path, operation, data, source_view, node, target_view) or [])
        return css

    def op_page_width(self, path, operation, data, source_view, node, target_view):
        """Feste Seitenbreite der Quelle als CSS-Variable des Ziels.

        Broadcast `wrapper` ist 1100 px (ab 1400 px Fensterbreite 80 vw) mit 50 px Innenrand,
        Horizon `page-width` folgt der globalen Seitenbreite. Ohne Regel wird der Text zur
        schmalen Spalte oder läuft über die ganze Breite.
        """
        value = self.source_value(data, source_view, operation["from"])
        width = (self.tables.get("widths") or {}).get(operation.get("widths", "page"), {}).get(lookup_key(value))
        if width is None:
            return []
        variable = operation.get("variable", "--page-width")
        self.note(path, "page_width", f"{value} → {variable}:{width}")
        return [f".section{{{variable}:{width}}}"]

    def op_text_blocks(self, path, operation, data, source_view, node, target_view):
        """Textblöcke über die Inhaltsbreite, ausgerichtet wie die Quelle.

        Horizon setzt Textblöcke auf `width: fit-content` und `max_width: normal` (rund 32 em),
        links ausgerichtet. Aus einem breiten, zentrierten Fließtext der Quelle wird so eine
        schmale Spalte links.
        """
        alignment = operation.get("default", "left")
        if operation.get("alignment_from"):
            value = self.source_value(data, source_view, operation["alignment_from"])
            alignment = (operation.get("values") or {}).get(lookup_key(value), alignment)
        block_type = operation.get("block_type", "text")
        count = 0
        for block_id, block, view, _ in self.walk(node, target_view):
            if block.get("type") != block_type:
                continue
            settings = block.setdefault("settings", {})
            block_path = f"{path}.blocks.{block_id}"
            for key, value in (("width", operation.get("width", "100%")),
                               ("max_width", operation.get("max_width", "none")),
                               ("alignment", alignment)):
                if value is not None:
                    self.put(settings, view, key, value, block_path, "text_blocks")
            count += 1
        if count:
            self.note(path, "text_blocks", f"{count} Textblöcke, Ausrichtung {alignment}")
        return []

    def op_text_size(self, path, operation, data, source_view, node, target_view):
        """Größenstufe der Quelle als Schriftgröße je Breakpoint.

        Horizon kennt keine Größenstufe am Block, nur die zentralen Presets. Eine Stufe, die
        vom Standard der Quelle abweicht (etwa Fließtext Stufe 4 statt 3), wird CSS der Section.
        """
        table = (self.tables.get("sizes") or {}).get(operation["sizes"]) or {}
        key = operation["from"]
        suffix = operation.get("suffix", "")
        declarations = operation.get("declarations", "")
        scope = operation["scope"]

        def wanted(value, baseline=operation.get("baseline")):
            # `baseline` ist die Stufe, die das globale Preset schon trägt (Absatz Stufe 3, h1 Stufe 8);
            # sie braucht kein eigenes CSS.
            if value is None or (baseline is not None and lookup_key(value) == lookup_key(baseline)):
                return None
            return table.get(lookup_key(value))

        def block_baseline(block, view):
            """Stufe je Block, wenn sie vom Tag abhängt (Broadcast: h1 und h2 Stufe 8, h3 Stufe 7)."""
            if not operation.get("baseline_from"):
                return operation.get("baseline")
            tag = self.source_value(block, view, operation["baseline_from"])
            return (operation.get("baselines") or {}).get(lookup_key(tag), operation.get("baseline"))

        def selector(base: str) -> str:
            return f"{base} {suffix}".strip()

        if scope == "section":
            value = self.source_value(data, source_view, key)
            sizes = wanted(value)
            if sizes is None:
                return []
            self.note(path, "text_size", f"{key} {value}")
            return size_rules(operation["selector"], self.scaled(operation["sizes"], sizes), self.breakpoints,
                              declarations)
        types = operation.get("block_types")
        if scope == "child":
            # Kindblock mit fester ID (etwa `title` je Spalte): die Stufe kommt vom ersten Quellblock
            # der genannten Typen, ohne Typen von der Section selbst.
            value = None
            if types:
                for _, block, view in self.source_blocks(data, source_view, types):
                    value = self.source_value(block, view, key)
                    if value is not None:
                        break
            else:
                value = self.source_value(data, source_view, key)
            child = selector(f".text-block[class*=__{operation['child_id']}]")
            sizes = wanted(value)
            if sizes is None:
                # Stufe wie der Standard: nur eine eigene Auszeichnung (etwa fett) bleibt übrig.
                return [f"{child}{{{declarations}}}"] if declarations and value is not None else []
            self.note(path, "text_size", f"{operation['child_id']}: {key} {value}")
            return size_rules(child, self.scaled(operation["sizes"], sizes), self.breakpoints, declarations)
        by_size: dict[str, list] = {}
        for block_id, block, view in self.source_blocks(data, source_view, types):
            value = self.source_value(block, view, key)
            if wanted(value, block_baseline(block, view)) is None:
                continue
            new_id = self.target_id(path, block_id)
            if self.find(node, target_view, new_id)[0] is None:
                continue
            by_size.setdefault(lookup_key(value), []).append(new_id)
        if not by_size:
            return []
        text_ids = [block_id for block_id, block, _, _ in self.walk(node, target_view) if block.get("type") == "text"]
        rules = []
        for value, ids in by_size.items():
            if len(by_size) == 1 and sorted(ids) == sorted(text_ids):
                chosen = selector(".text-block")
            else:
                chosen = ",".join(selector(f".text-block[class*=__{block_id}]") for block_id in ids)
            rules += size_rules(chosen, self.scaled(operation["sizes"], table[value]), self.breakpoints, declarations)
            self.note(path, "text_size", f"{key} {value}: {', '.join(ids)}")
        return rules

    def op_gap(self, path, operation, data, source_view, node, target_view):
        """Abstand zwischen den Blöcken; Broadcast setzt 24 bis 35 px, Horizon 12 px."""
        if len(node.get("block_order") or []) < operation.get("min_blocks", 2):
            return []
        if self.put(node.setdefault("settings", {}), target_view, operation["to"], operation["value"], path, "gap"):
            self.note(path, "gap", f"{operation['to']} {operation['value']}")
        return []

    def op_overlay_opacity(self, path, operation, data, source_view, node, target_view):
        """Farbe und Deckkraft der Quelle als eine Farbe mit Alphawert.

        Broadcast hält Overlay-Farbe und Deckkraft getrennt, Horizon nur die Farbe. Wer nur die
        Farbe überträgt, legt eine deckende Fläche über das Bild.
        """
        targets = []
        if operation.get("scope", "section") == "section":
            targets.append((data, source_view, node, target_view, path))
        else:
            for block_id, block, view in self.source_blocks(data, source_view, operation.get("block_types")):
                new_id = self.target_id(path, block_id)
                found, found_view = self.find(node, target_view, new_id)
                if found is not None:
                    targets.append((block, view, found, found_view, f"{path}.blocks.{new_id}"))
        for source, view, target, out_view, at in targets:
            opacity = self.source_value(source, view, operation["opacity_from"])
            color = self.source_value(source, view, operation["color_from"]) or operation.get("default_color", "#000000")
            try:
                opacity = float(opacity)
            except (TypeError, ValueError):
                continue
            settings = target.setdefault("settings", {})
            if opacity <= 0:
                self.put(settings, out_view, operation["toggle"], False, at, "overlay_opacity")
                self.note(at, "overlay_opacity", "Deckkraft 0, Overlay aus")
                continue
            value = rgba(color, opacity)
            if value is None:
                self.generator.build_case(at, "layout_overlay", f"Overlay-Farbe {color!r} ist kein Hex-Wert",
                                          value=color)
                continue
            self.put(settings, out_view, operation["toggle"], True, at, "overlay_opacity")
            self.put(settings, out_view, operation["to"], value, at, "overlay_opacity")
            self.note(at, "overlay_opacity", value)
        return []

    def op_set_by_value(self, path, operation, data, source_view, node, target_view):
        """Ein Wert der Quelle setzt mehrere Einstellungen des Ziels und/oder CSS (Höhe, Blocksatz)."""
        value = self.source_value(data, source_view, operation["from"])
        row = (operation.get("values") or {}).get(lookup_key(value))
        if row is None:
            return []
        settings = node.setdefault("settings", {})
        for key, setting in (row.get("set") or {}).items():
            self.put(settings, target_view, key, setting, path, "set_by_value")
        self.note(path, "set_by_value", f"{operation['from']} {value}")
        return list(row.get("css") or [])

    def op_drop_empty_blocks(self, path, operation, data, source_view, node, target_view):
        """Leere Text- und Button-Blöcke entfernen.

        Platzhalter der Quelle (Überschrift ohne Text, Button ohne Ziel) werden sonst leere
        Blöcke, die im Ziel Höhe belegen und ein Bild verdecken oder zusammenklappen.
        """
        removed = []
        for block_id, block, _, parent in list(self.walk(node, target_view)):
            if block.get("static") or not is_empty_block(block):
                continue
            del parent["blocks"][block_id]
            if block_id in (parent.get("block_order") or []):
                parent["block_order"].remove(block_id)
            removed.append(block_id)
        if removed:
            self.note(path, "drop_empty_blocks", ", ".join(removed))
        return []

    def op_copy_to_blocks(self, path, operation, data, source_view, node, target_view):
        """Einstellung der Quell-Section an jeden Block eines Typs (etwa Textfarbe im Hero)."""
        value = self.source_value(data, source_view, operation["from"])
        if value in (None, ""):
            return []
        count = 0
        for block_id, block, view, _ in self.walk(node, target_view):
            if block.get("type") != operation.get("block_type", "text"):
                continue
            if self.put(block.setdefault("settings", {}), view, operation["to"], value,
                        f"{path}.blocks.{block_id}", "copy_to_blocks"):
                count += 1
        if count:
            self.note(path, "copy_to_blocks", f"{operation['to']} {value} an {count} Blöcke")
        return []
