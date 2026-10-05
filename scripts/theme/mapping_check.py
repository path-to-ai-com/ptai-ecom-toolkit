#!/usr/bin/env python3
"""Prüft eine Mapping-Datei (Theme-Migration, Spec 8.3) gegen zwei Schema-Auszüge.

Aufruf:
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.mapping_check \\
        --mapping reference/theme-migration/mappings/broadcast-5__horizon-4.json \\
        --source-schema <quell-auszug.json> --target-schema <ziel-auszug.json> \\
        [--out <befunde.json>]

Ein Schema-Auszug ist eine JSON-Datei, die nur Namen und Typen trägt, keinen Code:

    {"theme": {"name": "Horizon", "version": "4.2.0"},
     "sections": {"<typ>": {"settings": {"<id>": {"type": "range", "min": 0, "max": 100}},
                            "blocks": {"<typ>": {"settings": {}}}}},
     "blocks": {"<typ>": {"settings": {}, "blocks": ["@theme", "text"]}},
     "settings_schema": {"<id>": {"type": "color_palette"}},
     "templates": ["product", "customers/account"],
     "section_groups": ["header-group"]}

`sections.<typ>.blocks` sind die Blöcke, die die Section annimmt (lokale Blöcke mit
eigenen Einstellungen, Theme-Blöcke nur mit Typ, dazu `@theme` und `@app`).
`blocks` sind die Theme-Blöcke aus `blocks/`, mit den Blöcken, die sie selbst
annehmen. Statt eines Objekts darf jede Einstellungs- oder Blockliste auch eine
Liste von Namen sein; dann entfallen die Typprüfungen.

Fehler (Exit-Code 1) sind Zuordnungen, die beim Erzeugen still verloren gingen oder
eine ungültige Datei ergäben: eine Quell-Section ohne Ausgang, ein Ziel, das es
nicht gibt, eine Einstellung, die das Ziel nicht kennt, eine unbekannte
Transformation. Hinweise (kein Einfluss auf den Exit-Code) sind Stellen, an denen
ein Mensch hinsehen muss: Typwechsel, Wertebereiche, die nicht passen, Werte ohne
Entsprechung, Einstellungen und Blöcke der Quelle ohne Zuordnung.

Ausgabe: die Befunde als JSON-Datei (`--out`) und eine Zusammenfassung als eine
JSON-Zeile auf stdout. Exit-Code 0 ohne Fehler, 1 mit Fehlern, 2 bei einem
Lesefehler.
"""
import argparse
import json
import re
import sys

#: Die feste Liste aus Spec 8.3. Was keine davon abbildet, wird `build`.
TRANSFORMS = ("identity", "map_values", "px_to_number", "bool_invert", "font_handle",
              "color_to_palette", "text_to_richtext", "drop")
#: Schlüssel `*` steht für "jede weitere Section bzw. jedes weitere Template" (Generator).
WILDCARD = "*"
ACTIONS = ("configure", "build", "drop")
#: Ein Schlüssel der Palette: beginnt mit einem Buchstaben, dann Buchstaben, Ziffern
#: und Unterstriche (Shopify-Doku zu `color_palette`).
PALETTE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
#: Typpaare, die `identity` ohne Umformung verträgt.
COMPATIBLE = {("text", "textarea"), ("text", "inline_richtext"), ("radio", "select"),
              ("select", "radio"), ("color", "color_background")}
SPECIAL_BLOCKS = ("@app", "@theme")


class MappingError(Exception):
    """Eine Eingabedatei ist nicht lesbar oder nicht im erwarteten Format."""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise MappingError(f"{path}: {exc}") from exc


def _settings(container):
    """Einstellungen eines Section-, Block- oder Globalauszugs als dict id -> Angaben."""
    raw = (container or {}).get("settings", {}) if isinstance(container, dict) else container
    if isinstance(raw, list):
        return {name: {} for name in raw}
    return raw or {}


def _names(raw):
    """Blockliste als Menge von Typen, egal ob dict oder Liste."""
    if isinstance(raw, dict):
        return set(raw)
    return set(raw or [])


def _global(extract):
    raw = extract.get("settings_schema", {})
    return {name: {} for name in raw} if isinstance(raw, list) else raw


class Checker:
    """Sammelt Fehler und Hinweise einer Mapping-Datei."""

    def __init__(self, mapping, source, target):
        self.mapping = mapping
        self.source = source
        self.target = target
        self.errors = []
        self.warnings = []

    def error(self, code, where, message):
        self.errors.append({"code": code, "where": where, "message": message})

    def warn(self, code, where, message):
        self.warnings.append({"code": code, "where": where, "message": message})

    # -- Ziel-Blöcke ------------------------------------------------------------

    def target_block_settings(self, block_type, section_type=None):
        """Einstellungen eines Ziel-Blocks: Theme-Block oder lokaler Block der Section."""
        blocks = self.target.get("blocks", {})
        if block_type in blocks:
            return _settings(blocks[block_type])
        if section_type:
            local = self.target.get("sections", {}).get(section_type, {}).get("blocks", {})
            if isinstance(local, dict) and block_type in local:
                return _settings(local[block_type])
        return None

    def accepts(self, container_blocks, block_type):
        """Nimmt ein Behälter mit dieser Blockliste den Typ an?"""
        names = _names(container_blocks)
        if block_type in names:
            return True
        theme_blocks = self.target.get("blocks", {})
        return ("@theme" in names and block_type in theme_blocks
                and not block_type.startswith("_"))

    def container_blocks(self, section_type, parent):
        if parent:
            return self.target.get("blocks", {}).get(parent, {}).get("blocks", [])
        return self.target.get("sections", {}).get(section_type, {}).get("blocks", {})

    # -- Einstellungen ------------------------------------------------------------

    def check_setting(self, where, source_key, entry, source_settings, target_settings,
                      section_type=None):
        """Prüft eine Zuordnung `<quell-key>: {to, transform, ...}`."""
        if not isinstance(entry, dict):
            self.error("invalid_entry", where, "Zuordnung ist kein Objekt")
            return
        if source_settings is not None and source_key not in source_settings:
            self.error("unknown_source_setting", where,
                       f"Quell-Einstellung {source_key!r} gibt es nicht")
        # Ohne Angabe nimmt der Generator `identity`; die Prüfung tut dasselbe.
        transform = entry.get("transform", "identity")
        if transform not in TRANSFORMS:
            self.error("unknown_transform", where, f"Transformation {transform!r} ist nicht erlaubt")
            return
        if transform == "drop":
            if not entry.get("note"):
                self.warn("drop_without_note", where, "drop ohne Begründung (note)")
            return
        to = entry.get("to")
        if not to:
            self.error("missing_target_setting", where, "Feld 'to' fehlt")
            return
        settings = target_settings
        child = entry.get("block")
        if child:
            settings = self.resolve_block_path(where, child, section_type)
            if settings is None:
                return
        if settings is not None and to not in settings:
            self.error("unknown_target_setting", where, f"Ziel-Einstellung {to!r} gibt es nicht")
            return
        source_spec = (source_settings or {}).get(source_key, {})
        target_spec = (settings or {}).get(to, {})
        self.check_types(where, transform, entry, source_spec, target_spec)

    def resolve_block_path(self, where, path, section_type):
        """Kindblock-Pfad `a/b/c` auflösen; gibt die Einstellungen des letzten Blocks."""
        settings = None
        for part in path.split("/"):
            settings = self.target_block_settings(part, section_type)
            if settings is None:
                self.error("unknown_target_block", where, f"Ziel-Block {part!r} gibt es nicht")
                return None
        return settings

    def check_types(self, where, transform, entry, source_spec, target_spec):
        s_type, t_type = source_spec.get("type"), target_spec.get("type")
        if transform == "map_values":
            values = entry.get("values")
            if not isinstance(values, dict) or not values:
                self.error("missing_values", where, "map_values ohne 'values'")
                return
            options = target_spec.get("options")
            if options is not None:
                wrong = [v for v in values.values() if v not in options and str(v) not in map(str, options)]
                if wrong:
                    self.error("invalid_target_value", where,
                               f"Zielwerte ohne Option im Ziel: {sorted(map(str, wrong))}")
            if source_spec.get("options") is not None:
                missing = [o for o in source_spec["options"] if str(o) not in values]
                if missing:
                    self.warn("unmapped_values", where, f"Quellwerte ohne Zuordnung: {missing}")
            return
        if transform == "color_to_palette":
            if t_type and t_type != "color_palette":
                self.error("palette_target", where, "color_to_palette braucht ein Ziel vom Typ color_palette")
            key = entry.get("key", "")
            if not PALETTE_KEY.match(key):
                self.error("palette_key", where, f"Paletten-Schlüssel {key!r} ist ungültig")
            return
        if transform == "text_to_richtext":
            if t_type and t_type not in ("richtext", "inline_richtext"):
                self.warn("type_mismatch", where, f"text_to_richtext in ein Ziel vom Typ {t_type}")
            return
        if not s_type or not t_type:
            return
        expected = {"bool_invert": ("checkbox", "checkbox"),
                    "font_handle": ("font_picker", "font_picker")}.get(transform)
        if expected and (s_type, t_type) != expected:
            self.warn("type_mismatch", where, f"{transform} erwartet {expected}, hat ({s_type}, {t_type})")
            return
        if transform == "px_to_number":
            if t_type not in ("range", "number"):
                self.warn("type_mismatch", where, f"px_to_number in ein Ziel vom Typ {t_type}")
            return
        if transform != "identity":
            return
        if s_type != t_type and (s_type, t_type) not in COMPATIBLE:
            self.warn("type_mismatch", where, f"identity von {s_type} nach {t_type}")
            return
        if s_type == "range" and t_type == "range":
            s_min, s_max = source_spec.get("min"), source_spec.get("max")
            t_min, t_max = target_spec.get("min"), target_spec.get("max")
            if None not in (s_min, s_max, t_min, t_max) and (s_min < t_min or s_max > t_max):
                self.warn("range_exceeds", where,
                          f"Quelle {s_min} bis {s_max}, Ziel {t_min} bis {t_max}")
        if source_spec.get("options") is not None and target_spec.get("options") is not None:
            missing = [o for o in source_spec["options"]
                       if str(o) not in map(str, target_spec["options"])]
            if missing:
                self.warn("unmapped_values", where, f"Quellwerte ohne Option im Ziel: {missing}")

    def check_set(self, where, values, settings):
        for key in (values or {}):
            if settings is not None and key not in settings:
                self.error("unknown_target_setting", f"{where}.set.{key}",
                           f"Ziel-Einstellung {key!r} gibt es nicht")

    # -- Sections -----------------------------------------------------------------

    def check_reason(self, where, entry):
        if not (entry.get("notes") or "").strip():
            self.error("missing_reason", where, f"{entry.get('action')} ohne Begründung (notes)")

    def check_sections(self):
        sections = self.mapping.get("sections", {})
        source_sections = self.source.get("sections", {})
        for name in source_sections:
            if name not in sections and WILDCARD not in sections:
                self.error("missing_source_section", f"sections.{name}",
                           "Quell-Section ohne Ausgang")
        for name, entry in sections.items():
            where = f"sections.{name}"
            if name not in source_sections and name != WILDCARD:
                self.error("unknown_source_section", where, "Section gibt es im Quell-Theme nicht")
            action = entry.get("action")
            if action not in ACTIONS:
                self.error("unknown_action", where, f"Ausgang {action!r} ist nicht erlaubt")
                continue
            if action != "configure":
                self.check_reason(where, entry)
                continue
            target = entry.get("target")
            target_section = self.target.get("sections", {}).get(target)
            if target_section is None:
                self.error("unknown_target_section", where, f"Ziel-Section {target!r} gibt es nicht")
                continue
            source_section = source_sections.get(name, {})
            source_settings = _settings(source_section) if name in source_sections else None
            target_settings = _settings(target_section)
            for key, setting in (entry.get("settings") or {}).items():
                self.check_setting(f"{where}.settings.{key}", key, setting, source_settings,
                                   target_settings, target)
            self.check_set(where, entry.get("set"), target_settings)
            if source_settings is not None:
                for key in source_settings:
                    if key not in (entry.get("settings") or {}):
                        self.warn("unmapped_source_setting", f"{where}.settings.{key}",
                                  "Quell-Einstellung ohne Zuordnung")
            self.check_blocks(where, entry, source_section, target)

    def check_blocks(self, where, entry, source_section, target):
        source_blocks = source_section.get("blocks", {}) if isinstance(source_section, dict) else {}
        mapped = entry.get("blocks") or {}
        for block_type in _names(source_blocks):
            if block_type not in mapped:
                self.warn("unmapped_source_block", f"{where}.blocks.{block_type}",
                          "Quell-Block ohne Zuordnung")
        for block_type, block in mapped.items():
            b_where = f"{where}.blocks.{block_type}"
            if source_blocks and block_type not in _names(source_blocks):
                self.error("unknown_source_block", b_where, "Block gibt es in der Quell-Section nicht")
            action = block.get("action", "configure")
            if action not in ACTIONS:
                self.error("unknown_action", b_where, f"Ausgang {action!r} ist nicht erlaubt")
                continue
            if action != "configure":
                self.check_reason(b_where, block)
                continue
            target_block = block.get("target")
            parent = block.get("parent")
            if parent and self.target_block_settings(parent, target) is None:
                self.error("unknown_target_block", b_where, f"Eltern-Block {parent!r} gibt es nicht")
                continue
            if target_block in SPECIAL_BLOCKS:
                if not self.accepts(self.container_blocks(target, parent), target_block):
                    self.error("block_not_accepted", b_where, f"{target_block} wird dort nicht angenommen")
                continue
            settings = self.target_block_settings(target_block, target)
            if settings is None:
                self.error("unknown_target_block", b_where, f"Ziel-Block {target_block!r} gibt es nicht")
                continue
            if not block.get("static") and not self.accepts(self.container_blocks(target, parent),
                                                             target_block):
                self.error("block_not_accepted", b_where,
                           f"{target_block!r} wird von {parent or target!r} nicht angenommen")
            source_settings = None
            if isinstance(source_blocks, dict) and block_type in source_blocks:
                source_settings = _settings(source_blocks[block_type])
            for key, setting in (block.get("settings") or {}).items():
                self.check_setting(f"{b_where}.settings.{key}", key, setting, source_settings,
                                   settings, target)
            self.check_set(b_where, block.get("set"), settings)
            for key in (source_settings or {}):
                if key not in (block.get("settings") or {}):
                    self.warn("unmapped_source_setting", f"{b_where}.settings.{key}",
                              "Quell-Einstellung ohne Zuordnung")

    # -- Globale Einstellungen, Templates, Gruppen ----------------------------------

    def check_settings_data(self):
        mapped = self.mapping.get("settings_data", {})
        source_settings, target_settings = _global(self.source), _global(self.target)
        for key, entry in mapped.items():
            self.check_setting(f"settings_data.{key}", key, entry, source_settings, target_settings)
        for key in source_settings:
            if key not in mapped:
                self.warn("unmapped_source_setting", f"settings_data.{key}",
                          "globale Quell-Einstellung ohne Zuordnung")

    def check_named(self, section, known):
        """Templates und Section-Gruppen: Ausgang je Name, Ziel muss existieren."""
        for name, entry in (self.mapping.get(section) or {}).items():
            where = f"{section}.{name}"
            action = entry.get("action")
            if action not in ACTIONS:
                self.error("unknown_action", where, f"Ausgang {action!r} ist nicht erlaubt")
                continue
            if action != "configure":
                self.check_reason(where, entry)
                continue
            target = entry.get("target", name)
            if known is not None and target not in known:
                self.error(f"unknown_target_{section.rstrip('s')}", where,
                           f"Ziel {target!r} gibt es im Ziel-Theme nicht")

    def check_format(self):
        for key in ("source", "target", "sections"):
            if not isinstance(self.mapping.get(key), dict):
                self.error("invalid_format", key, f"Pflichtfeld {key!r} fehlt oder ist kein Objekt")
        for key in ("settings_data", "templates", "section_groups"):
            if key in self.mapping and not isinstance(self.mapping[key], dict):
                self.error("invalid_format", key, f"{key!r} ist kein Objekt")
        return not self.errors

    def run(self):
        if not self.check_format():
            return self.result()
        self.check_sections()
        self.check_settings_data()
        templates = self.target.get("templates")
        self.check_named("templates", set(templates) if templates is not None else None)
        groups = self.target.get("section_groups")
        self.check_named("section_groups", set(groups) if groups is not None else None)
        return self.result()

    def result(self):
        return {"errors": self.errors, "warnings": self.warnings,
                "coverage": coverage(self.mapping)}


def coverage(mapping):
    """Zahl der Sections je Ausgang."""
    counts = {action: 0 for action in ACTIONS}
    for entry in (mapping.get("sections") or {}).values():
        if isinstance(entry, dict) and entry.get("action") in counts:
            counts[entry["action"]] += 1
    return counts


def check(mapping, source, target):
    """Prüft ein geladenes Mapping gegen zwei geladene Schema-Auszüge."""
    return Checker(mapping, source, target).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mapping-Datei gegen zwei Schema-Auszüge prüfen")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--source-schema", required=True)
    parser.add_argument("--target-schema", required=True)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        result = check(load_json(args.mapping), load_json(args.source_schema),
                       load_json(args.target_schema))
    except MappingError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps({"ok": not result["errors"], "errors": len(result["errors"]),
                      "warnings": len(result["warnings"]), "coverage": result["coverage"],
                      "out": args.out}, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
