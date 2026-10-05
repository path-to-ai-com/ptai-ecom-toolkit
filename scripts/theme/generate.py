"""Generator: Templates, Section-Groups und globale Einstellungen aus Mapping und Sicherung.

Aufruf:
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.generate \\
        --mapping migration/mapping/mapping.json \\
        [--overrides migration/mapping/overrides.json] \\
        --source migration/snapshots/<date>-<theme-id> \\
        --target-schemas <target-repo> \\
        --out <test-dir> --lock migration/build/sources.lock

Liest die eingefrorenen Quellen (JSON-Templates, Section-Groups und
`config/settings_data.json` der Sicherung, die Schemas beider Themes), wendet
Mapping und Overrides an und schreibt `templates/*.json`, `sections/*.json` und
`config/settings_data.json` nach `--out`, dazu `report.json` dort und
`sources.lock` mit SHA-256 jeder Eingabe. Das Format des Mappings steht in
`reference/theme-migration/mapping-format.md`.

Die Regeln, jede aus einem belegten Fehler im Feld:

1. Ein fehlender Schlüssel heißt Schema-Standard der Quelle, nie "aus".
2. Nur Einstellungen schreiben, die im Schema des Ziels stehen; jede verworfene
   steht im Report.
3. Block-IDs stabil und gültig: gültige IDs bleiben, ungültige (etwa mit `--`
   oder `__`, die Shopify ablehnt) bekommen eine aus dem Pfad abgeleitete ID,
   die bei jedem Lauf gleich ist.
4. Eigenes CSS je Section höchstens 500 Zeichen, sonst `build` (eigene Datei).
5. Limits vor dem Schreiben: 25 Sections je Template, 50 Blöcke je Section,
   1250 je Template, 8 Ebenen, 512 KB je JSON-Template; eine Datei darüber
   wird nicht geschrieben.
6. Statische Blöcke stehen mit `"static": true` im JSON und nie in `block_order`.
7. Was keine Transformation abbildet, wird ein `build`-Fall im Report, nie
   geraten.
8. Ausgabe nur in ein Testverzeichnis, nie direkt ins Ziel-Repo; der Report
   vergleicht sie mit dem Stand im Ziel-Repo, damit Editor-Änderungen nicht
   still überschrieben werden.

Exit-Code 0 ohne Befund, 1 mit Befunden (`build`, verworfene Einstellungen,
Limits, Mapping-Fehler gegen die Schemas), 2 bei Fehlern.
"""
import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from theme import schema as schema_module
from theme import transforms

LIMITS = {
    "sections_per_template": 25,
    "blocks_per_section": 50,
    "blocks_per_template": 1250,
    "nesting_depth": 8,
    "json_template_bytes": 512 * 1024,
    "settings_data_bytes": 1536 * 1024,
}
CUSTOM_CSS_MAX = 500
PALETTE_MIN, PALETTE_MAX = 2, 20

#: Laut Doku "nur alphanumerisch"; im Feld nimmt Shopify `-` und `_` an, lehnt
#: aber `--` und `__` ab. Erzeugt wird deshalb nur, was beide Lesarten trägt.
BLOCK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ACTIONS = {"configure", "build", "drop"}
POSITIONS = {"start", "end"}
TEMPLATE_KEYS = ("layout", "wrapper", "sections", "order")
#: Diese Liquid-Templates hat jedes 2.0-Theme; sie sind kein Hinweis auf Vintage.
ALWAYS_LIQUID = {"gift_card", "robots.txt"}
APP_PREFIX = "shopify://apps/"
#: Schlüssel im Mapping, unter dem die Zuordnung für App-Blöcke steht.
APP_ENTRY = "@app"
MAX_DIFF_PATHS = 20

#: Bekannte Felder je Ebene. Ein anderes Feld wird nicht beachtet und gemeldet.
TOP_FIELDS = {"source", "target", "sections", "settings_data", "templates", "section_groups"}
RULE_FIELDS = {"to", "transform", "values", "key", "replace", "variant", "block", "block_id", "note", "notes"}
SECTION_FIELDS = {"action", "target", "settings", "set", "blocks", "custom_css", "reason", "notes", "note"}
BLOCK_FIELDS = SECTION_FIELDS - {"custom_css"} | {"static", "static_id", "parent"}
NAMED_FIELDS = {"action", "target", "reason", "notes", "note"}
GROUP_FIELDS = NAMED_FIELDS | {"position"}


def valid_block_id(value: str) -> bool:
    return bool(BLOCK_ID.match(value)) and "--" not in value and "__" not in value


def stable_block_id(old_id: str, seed: str, used: set) -> str:
    """Gültige, bei jedem Lauf gleiche ID für eine ungültige: lesbarer Teil plus Prüfsumme des Pfads."""
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", old_id).strip("_")[:36].rstrip("_") or "block"
    salt = 0
    while True:
        digest = hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()[:12]
        candidate = f"{prefix}_{digest}"
        if candidate not in used and valid_block_id(candidate):
            return candidate
        salt += 1


def merge_entry(base: dict, extra: dict) -> dict:
    """Ein Override über einen Section- oder Block-Eintrag legen.

    Felder des Eintrags werden ersetzt; `settings` und `set` werden je Schlüssel
    zusammengeführt (eine Zeile ersetzt die Zeile gleichen Namens ganz), `blocks`
    je Blocktyp nach derselben Regel.
    """
    merged = {**copy.deepcopy(base),
              **{k: copy.deepcopy(v) for k, v in extra.items() if k not in ("settings", "set", "blocks")}}
    for key in ("settings", "set"):
        if key in extra:
            merged[key] = {**copy.deepcopy(base.get(key) or {}), **copy.deepcopy(extra[key] or {})}
    if "blocks" in extra:
        blocks = copy.deepcopy(base.get("blocks") or {})
        for block_type, block in (extra["blocks"] or {}).items():
            if isinstance(blocks.get(block_type), dict) and isinstance(block, dict):
                blocks[block_type] = merge_entry(blocks[block_type], block)
            else:
                blocks[block_type] = copy.deepcopy(block)
        merged["blocks"] = blocks
    return merged


def merge_mapping(base: dict, overrides: dict | None) -> dict:
    """Overrides über das Mapping legen: je Schlüssel auf Ebene Section, Block und Einstellung."""
    merged = copy.deepcopy(base)
    for key, value in (overrides or {}).items():
        if key == "instances":
            continue
        if key == "sections" and isinstance(value, dict):
            sections = merged.setdefault("sections", {})
            for section_type, entry in value.items():
                if isinstance(sections.get(section_type), dict) and isinstance(entry, dict):
                    sections[section_type] = merge_entry(sections[section_type], entry)
                else:
                    sections[section_type] = copy.deepcopy(entry)
        elif key in ("settings_data", "templates", "section_groups") and isinstance(value, dict):
            merged[key] = {**(merged.get(key) or {}), **copy.deepcopy(value)}
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def serialize(document) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def json_differences(old, new, path="", found=None) -> list[str]:
    """Pfade, an denen sich zwei JSON-Werte unterscheiden, höchstens `MAX_DIFF_PATHS`."""
    found = [] if found is None else found
    if len(found) >= MAX_DIFF_PATHS:
        return found
    if isinstance(old, dict) and isinstance(new, dict):
        for key in list(old) + [k for k in new if k not in old]:
            child = f"{path}.{key}" if path else str(key)
            if key not in old or key not in new:
                found.append(child)
            else:
                json_differences(old[key], new[key], child, found)
            if len(found) >= MAX_DIFF_PATHS:
                break
    elif old != new:
        found.append(path or "(Wurzel)")
    return found


# --- Mapping prüfen -----------------------------------------------------------

def validate_mapping(mapping) -> list[str]:
    """Aufbau des Mappings laut Format; Fehler hier brechen den Lauf ab (Exit 2)."""
    errors = []
    if not isinstance(mapping, dict):
        return ["Mapping ist kein JSON-Objekt"]

    def rules(where: str, value, scope: str):
        if value is None:
            return
        if not isinstance(value, dict):
            errors.append(f"{where}: `settings` muss ein Objekt sein")
            return
        for key, rule in value.items():
            if not isinstance(rule, dict):
                errors.append(f"{where}.{key}: Zeile muss ein Objekt sein")
                continue
            name = rule.get("transform", "identity")
            if name not in transforms.TRANSFORMS:
                errors.append(f"{where}.{key}: Transformation {name!r} gibt es nicht")
            if name == "map_values" and not isinstance(rule.get("values"), dict):
                errors.append(f"{where}.{key}: map_values braucht `values`")
            if name == "color_to_palette" and scope != "settings_data":
                errors.append(f"{where}.{key}: color_to_palette gilt nur in settings_data")
            if "to" in rule and rule["to"] is None and name != "drop":
                errors.append(f"{where}.{key}: `to` ist leer, aber die Transformation ist nicht drop")
            for field in ("block", "block_id"):
                if field in rule and not (isinstance(rule[field], str) and rule[field]):
                    errors.append(f"{where}.{key}: `{field}` muss ein Name sein")
            if "block_id" in rule and "block" not in rule:
                errors.append(f"{where}.{key}: `block_id` braucht `block`")
            if scope == "settings_data" and "block" in rule:
                errors.append(f"{where}.{key}: `block` gibt es in settings_data nicht")

    def entry(where: str, value, is_block: bool):
        if not isinstance(value, dict):
            errors.append(f"{where}: Eintrag muss ein Objekt sein")
            return
        if value.get("action", "configure") not in ACTIONS:
            errors.append(f"{where}: `action` muss configure, build oder drop sein")
        if value.get("action") == "build" and not value.get("reason") and not value.get("notes"):
            errors.append(f"{where}: `build` braucht eine Begründung in `reason` oder `notes`")
        rules(where, value.get("settings"), "section")
        if "set" in value and not isinstance(value["set"], dict):
            errors.append(f"{where}: `set` muss ein Objekt sein")
        css = value.get("custom_css")
        if css is not None and css != "source" and not (isinstance(css, list) and all(isinstance(r, str) for r in css)):
            errors.append(f"{where}: `custom_css` ist eine Liste von Regeln oder \"source\"")
        if is_block:
            if "static" in value and not isinstance(value["static"], bool):
                errors.append(f"{where}: `static` ist true oder false")
            if "parent" in value and not (isinstance(value["parent"], str) and value["parent"]):
                errors.append(f"{where}: `parent` muss ein Blocktyp sein")
        for block_type, block in (value.get("blocks") or {}).items():
            entry(f"{where}.blocks.{block_type}", block, True)

    for section_type, value in (mapping.get("sections") or {}).items():
        entry(f"sections.{section_type}", value, False)
    rules("settings_data", mapping.get("settings_data"), "settings_data")
    for kind in ("templates", "section_groups"):
        for name, value in (mapping.get(kind) or {}).items():
            if not isinstance(value, dict) or value.get("action", "configure") not in ACTIONS:
                errors.append(f"{kind}.{name}: `action` muss configure, build oder drop sein")
            elif value.get("position", "end") not in POSITIONS:
                errors.append(f"{kind}.{name}: `position` ist start oder end")
    return errors


def unknown_fields(mapping: dict) -> list[dict]:
    """Felder, die das Format nicht kennt. Sie werden nicht beachtet; der Report nennt jedes."""
    found = []

    def note(where, keys, known):
        for key in keys:
            if key not in known:
                found.append({"where": where, "key": key, "reason": "unbekanntes Feld, nicht beachtet"})

    def entry(where, value, known):
        if not isinstance(value, dict):
            return
        note(where, value, known)
        for key, rule in (value.get("settings") or {}).items():
            if isinstance(rule, dict):
                note(f"{where}.settings.{key}", rule, RULE_FIELDS)
        for block_type, block in (value.get("blocks") or {}).items():
            entry(f"{where}.blocks.{block_type}", block, BLOCK_FIELDS)

    note("", mapping, TOP_FIELDS)
    for section_type, value in (mapping.get("sections") or {}).items():
        entry(f"sections.{section_type}", value, SECTION_FIELDS)
    for key, rule in (mapping.get("settings_data") or {}).items():
        if isinstance(rule, dict):
            note(f"settings_data.{key}", rule, RULE_FIELDS)
    for kind, known in (("templates", NAMED_FIELDS), ("section_groups", GROUP_FIELDS)):
        for name, value in (mapping.get(kind) or {}).items():
            if isinstance(value, dict):
                note(f"{kind}.{name}", value, known)
    return found


def check_mapping_against_schemas(mapping: dict, source: dict, target: dict) -> list[dict]:
    """Zeilen, die auf Schlüssel zeigen, die es in den Schemas nicht gibt (Tippfehler, falsche Version)."""
    findings = []

    def resolve(start_view, path, where):
        view = start_view
        for part in path.split("/"):
            view = schema_module.block_definition(target, view, part)
            if view is None:
                findings.append({"where": where, "key": None, "reason": f"Kindblock {part!r} hat im Ziel kein Schema"})
                return None
        return view

    def check_rules(where, rules, src_view, tgt_view):
        for key, rule in (rules or {}).items():
            if src_view is not None and key not in src_view["settings"]:
                findings.append({"where": where, "key": key, "reason": "Schlüssel steht nicht im Schema der Quelle"})
            name = rule.get("transform", "identity")
            if name == "drop" or tgt_view is None:
                continue
            view = tgt_view
            if rule.get("block"):
                view = resolve(tgt_view, rule["block"], f"{where}.{key}")
                if view is None:
                    continue
            target_key = rule.get("to", key)
            setting = view["settings"].get(target_key)
            if setting is None:
                findings.append({"where": where, "key": key, "to": target_key,
                                 "reason": "Ziel-Schlüssel steht nicht im Schema des Ziels"})
            elif name == "color_to_palette" and setting.get("type") != "color_palette":
                findings.append({"where": where, "key": key, "to": target_key,
                                 "reason": "color_to_palette braucht eine Einstellung vom Typ color_palette"})

    def check_entry(where, entry, src_view, tgt_view):
        if entry.get("action", "configure") != "configure":
            return
        check_rules(where, entry.get("settings"), src_view, tgt_view)
        for key in (entry.get("set") or {}):
            if tgt_view is not None and key not in tgt_view["settings"]:
                findings.append({"where": where, "key": key, "reason": "`set` nennt einen Schlüssel außerhalb des Ziel-Schemas"})
        for block_type, block in (entry.get("blocks") or {}).items():
            if not isinstance(block, dict):
                continue
            block_where = f"{where}.blocks.{block_type}"
            container = tgt_view
            if tgt_view is not None and block.get("parent"):
                container = resolve(tgt_view, block["parent"], block_where)
            target_type = block.get("target", block_type)
            if block_type.startswith(APP_PREFIX) or block_type == APP_ENTRY or target_type == APP_ENTRY:
                continue
            src_block = schema_module.block_definition(source, src_view, block_type) if src_view else None
            tgt_block = schema_module.block_definition(target, container, target_type) if container else None
            if block.get("action", "configure") == "configure" and container is not None and tgt_block is None:
                findings.append({"where": block_where, "key": None,
                                 "reason": f"Blocktyp {target_type!r} hat im Ziel kein Schema"})
            check_entry(block_where, block, src_block, tgt_block)

    for section_type, entry in (mapping.get("sections") or {}).items():
        if not isinstance(entry, dict):
            continue
        src_view = source["sections"].get(section_type)
        target_type = entry.get("target", section_type)
        tgt_view = target["sections"].get(target_type)
        if entry.get("action", "configure") == "configure":
            if src_view is None:
                findings.append({"where": f"sections.{section_type}", "key": None,
                                 "reason": "Section-Typ hat in der Quelle kein Schema"})
            if tgt_view is None:
                findings.append({"where": f"sections.{section_type}", "key": None,
                                 "reason": f"Ziel-Section {target_type!r} hat kein Schema"})
        check_entry(f"sections.{section_type}", entry, src_view, tgt_view)
    if mapping.get("settings_data"):
        check_rules("settings_data", mapping["settings_data"], source["settings_schema"], target["settings_schema"])
    return findings + unknown_fields(mapping)


# --- Limits ------------------------------------------------------------------

def check_limits(document: dict, file: str, target: dict, size: int) -> list[dict]:
    """Shopify-Limits eines JSON-Templates oder einer Section-Group.

    Statische Blöcke zählen laut Doku nicht zu den Blockzahlen, wohl aber zur
    Tiefe. Je Section zählen alle dynamischen Blöcke darunter, auch
    verschachtelte; das ist die strengere Lesart. `max_blocks` im Schema
    senkt die Grenze der Section.
    """
    violations = []
    sections = document.get("sections") or {}
    if len(sections) > LIMITS["sections_per_template"]:
        violations.append({"file": file, "limit": "sections_per_template", "value": len(sections),
                           "max": LIMITS["sections_per_template"]})
    total = 0

    def walk(node: dict, depth: int, path: str) -> int:
        count = 0
        for block_id, block in (node.get("blocks") or {}).items():
            child_path = f"{path}.blocks.{block_id}"
            if depth + 1 > LIMITS["nesting_depth"]:
                violations.append({"file": file, "limit": "nesting_depth", "value": depth + 1,
                                   "max": LIMITS["nesting_depth"], "path": child_path})
            if not block.get("static"):
                count += 1
            count += walk(block, depth + 1, child_path)
        return count

    for section_id, section in sections.items():
        path = f"sections.{section_id}"
        count = walk(section, 0, path)
        total += count
        maximum = LIMITS["blocks_per_section"]
        view = target["sections"].get(section.get("type", ""))
        if view and isinstance(view.get("max_blocks"), int):
            maximum = min(maximum, view["max_blocks"])
        if count > maximum:
            violations.append({"file": file, "limit": "blocks_per_section", "value": count, "max": maximum,
                               "path": path})
    if total > LIMITS["blocks_per_template"]:
        violations.append({"file": file, "limit": "blocks_per_template", "value": total,
                           "max": LIMITS["blocks_per_template"]})
    if size > LIMITS["json_template_bytes"]:
        violations.append({"file": file, "limit": "json_template_bytes", "value": size,
                           "max": LIMITS["json_template_bytes"]})
    return violations


def custom_css_length(rules: list[str]) -> int:
    """Zeichen des eigenen CSS einer Section, alle Regeln samt Trennzeichen."""
    return len("\n".join(rules))


# --- Generator ---------------------------------------------------------------

class Generator:
    """Ein Lauf: Mapping plus Overrides auf eine Sicherung gegen die Schemas des Ziels."""

    def __init__(self, mapping: dict, overrides: dict | None, source_dir, target_dir):
        self.instances = (overrides or {}).get("instances") or {}
        self.mapping = merge_mapping(mapping, overrides)
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.source = schema_module.extract(self.source_dir)
        self.target = schema_module.extract(self.target_dir)
        self.report = {
            "build": [], "dropped": [], "defaults_applied": [], "adjusted": [], "renamed_block_ids": [],
            "renamed_section_ids": [], "merged_groups": [], "skipped": [], "app_items": [], "app_embeds": [],
            "limit_violations": [], "mapping_findings": [],
            "schema_errors": self.source["errors"] + self.target["errors"], "files": [],
        }
        self.documents: dict[str, object] = {}
        self.file = ""

    # Report ------------------------------------------------------------------

    def build_case(self, path: str, kind: str, reason: str, **extra):
        self.report["build"].append({"file": self.file, "path": path, "kind": kind, "reason": reason, **extra})

    def dropped(self, path: str, key: str, reason: str, intended: bool = False, **extra):
        self.report["dropped"].append({"file": self.file, "path": path, "key": key, "reason": reason,
                                       "intended": intended, **extra})

    def adjusted(self, path: str, key: str, old, new, reason: str):
        self.report["adjusted"].append({"file": self.file, "path": path, "key": key, "from": old, "to": new,
                                        "reason": reason})

    # Einstellungen -----------------------------------------------------------

    def put(self, out: dict, target_view: dict, key: str, value, path: str, source_key: str,
            source_type: str | None = None) -> bool:
        """Einen Wert schreiben, wenn das Ziel-Schema ihn kennt und annimmt. Gibt zurück, ob er steht."""
        if value is None:
            return False
        setting = target_view["settings"].get(key)
        if setting is None:
            self.dropped(path, source_key, "nicht im Schema des Ziels", to=key, value=value)
            return False
        kind = setting.get("type")
        if isinstance(value, str) and "{{" in value:
            out[key] = value
            return True
        if kind in ("select", "radio"):
            options = [option.get("value") for option in setting.get("options", [])]
            if value not in options:
                self.dropped(path, source_key, "Wert steht nicht unter den Optionen des Ziels", to=key, value=value)
                return False
        elif kind == "checkbox" and not isinstance(value, bool):
            self.dropped(path, source_key, "Checkbox braucht einen Wahrheitswert", to=key, value=value)
            return False
        elif kind in ("range", "number"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                self.dropped(path, source_key, f"{kind} braucht eine Zahl", to=key, value=value)
                return False
            if kind == "range":
                value = self.fit_range(setting, value, path, key)
        elif kind == "richtext" and isinstance(value, str) and not transforms.is_richtext(value):
            # Ein richtext-Wert braucht ein Wurzelelement; Klartext wird maskiert,
            # inline_richtext ist schon HTML und wird nur eingefasst.
            wrapped = transforms.wrap_paragraphs(value, escape=source_type != "inline_richtext")
            self.adjusted(path, key, value, wrapped, "Klartext in Absätze gefasst (richtext)")
            if wrapped is None:
                return False
            value = wrapped
        elif kind == "inline_richtext" and isinstance(value, str) and transforms.is_richtext(value):
            inner = transforms.unwrap_paragraph(value)
            if inner is None:
                self.dropped(path, source_key, "mehrere Absätze passen nicht in inline_richtext", to=key, value=value)
                return False
            self.adjusted(path, key, value, inner, "Absatz-Hülle entfernt (inline_richtext)")
            value = inner
        out[key] = value
        return True

    def fit_range(self, setting: dict, value, path: str, key: str):
        low, high, step = setting.get("min"), setting.get("max"), setting.get("step", 1)
        adjusted = value
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            adjusted = max(low, min(high, adjusted))
            adjusted = round(low + round((adjusted - low) / step) * step, 6)
            if float(adjusted).is_integer():
                adjusted = int(adjusted)
        if adjusted != value:
            self.adjusted(path, key, value, adjusted, "außerhalb von min/max oder nicht auf der Schrittweite")
        return adjusted

    def map_settings(self, path: str, source_view: dict | None, data_settings: dict | None, entry: dict,
                     target_view: dict, scope: str = "section") -> tuple[dict, list]:
        """Einstellungen eines Knotens übertragen.

        Regel 1: Für jeden Schlüssel des Mappings gilt der Wert aus den Daten
        oder, wenn er dort fehlt, der Standard aus dem Schema der Quelle.
        Zeilen mit `block` gehören an einen Kindblock; sie kommen als zweite
        Liste zurück und werden von `place_child_values` eingesetzt.
        """
        explicit = data_settings or {}
        defaults = source_view["defaults"] if source_view else {}
        source_settings = source_view["settings"] if source_view else {}
        rules = entry.get("settings") or {}
        out: dict = {}
        children: list = []
        palettes: dict = {}
        for source_key, rule in rules.items():
            if source_key in explicit:
                value = explicit[source_key]
            elif source_key in defaults:
                value = defaults[source_key]
                self.report["defaults_applied"].append({"file": self.file, "path": path, "key": source_key,
                                                        "value": value})
            else:
                continue
            setting_path = f"{path}.settings.{source_key}"
            try:
                result = transforms.apply(rule, value, {"scope": scope})
            except transforms.TransformError as exc:
                self.build_case(setting_path, "transform", str(exc), value=value,
                                transform=rule.get("transform", "identity"))
                continue
            if result is transforms.DROP:
                self.dropped(setting_path, source_key, "Mapping: drop", intended=True)
                continue
            target_key = rule.get("to") or source_key
            source_type = (source_settings.get(source_key) or {}).get("type")
            if rule.get("transform") == "color_to_palette":
                palettes.setdefault(target_key, []).append((result, setting_path, source_key))
            elif rule.get("block"):
                children.append({"block": rule["block"], "block_id": rule.get("block_id"), "key": target_key,
                                 "value": result, "path": setting_path, "source_key": source_key,
                                 "source_type": source_type})
            else:
                self.put(out, target_view, target_key, result, setting_path, source_key, source_type)
        for target_key, entries in palettes.items():
            self.put_palette(out, target_view, target_key, entries)
        for source_key in explicit:
            if source_key not in rules:
                self.dropped(f"{path}.settings.{source_key}", source_key, "nicht im Mapping",
                             value=explicit[source_key])
        for key, value in (entry.get("set") or {}).items():
            self.put(out, target_view, key, copy.deepcopy(value), f"{path}.settings.{key}", key)
        return out, children

    def put_palette(self, out: dict, target_view: dict, target_key: str, entries: list) -> None:
        """Farben in die `color_palette` des Ziels, ausgehend von deren Standard."""
        setting = target_view["settings"].get(target_key)
        if setting is None or setting.get("type") != "color_palette":
            for _, setting_path, source_key in entries:
                self.dropped(setting_path, source_key, "Ziel ist keine Einstellung vom Typ color_palette",
                             to=target_key)
            return
        palette = dict(setting.get("default") or {})
        for result, _, _ in entries:
            palette[result["key"]] = result["color"]
        if not PALETTE_MIN <= len(palette) <= PALETTE_MAX:
            self.build_case(f"settings.{target_key}", "palette_size",
                            f"Palette hätte {len(palette)} Farben, erlaubt sind {PALETTE_MIN} bis {PALETTE_MAX}")
            return
        out[target_key] = palette

    # Blöcke ------------------------------------------------------------------

    def free_id(self, node: dict, view: dict, wanted: str, seed: str) -> str:
        """Regel 3: eine gültige, freie ID; statische IDs des Elternteils sind reserviert."""
        used = set(node.get("blocks") or {}) | {s["id"] for s in view.get("static_blocks", [])}
        if valid_block_id(wanted) and wanted not in used:
            return wanted
        return stable_block_id(wanted, seed, used)

    def insert_dynamic(self, node: dict, view: dict, wanted: str, child: dict, path: str,
                       report_rename: bool) -> str:
        new_id = self.free_id(node, view, wanted, f"{self.file}:{path}.blocks.{wanted}")
        if report_rename and new_id != wanted:
            self.report["renamed_block_ids"].append({"file": self.file, "path": path, "old_id": wanted,
                                                     "new_id": new_id})
        node.setdefault("blocks", {})[new_id] = child
        node.setdefault("block_order", []).append(new_id)
        return new_id

    def static_slot(self, view: dict, block_type: str, block_id: str | None, path: str) -> str | None:
        """Regel 6: die ID eines statischen Blocks, wie das Liquid des Elternteils ihn rendert."""
        slots = [s["id"] for s in view.get("static_blocks", []) if s["type"] == block_type]
        if block_id is not None:
            slots = [s for s in slots if s == block_id]
        if len(slots) == 1:
            return slots[0]
        if len(slots) > 1:
            self.build_case(path, "static_block_ambiguous",
                            f"mehrere statische Blöcke {block_type!r}; `static_id` oder `block_id` nennen")
        return None

    def ensure_child(self, path: str, node: dict, view: dict, block_type: str, block_id: str | None,
                     created: list) -> tuple[dict, dict] | None:
        """Kindblock eines Typs finden oder anlegen: statisch, wenn das Liquid ihn so rendert, sonst dynamisch."""
        for child_id, child in (node.get("blocks") or {}).items():
            if child.get("type") == block_type and (block_id is None or child_id == block_id):
                return child, schema_module.block_definition(self.target, view, block_type)
        child_view = schema_module.block_definition(self.target, view, block_type)
        if child_view is None:
            self.build_case(path, "missing_target_schema", f"Blocktyp {block_type!r} hat im Ziel kein Schema")
            return None
        declared = [s for s in view.get("static_blocks", []) if s["type"] == block_type]
        if declared:
            slot = self.static_slot(view, block_type, block_id, path)
            if slot is None or slot in (node.get("blocks") or {}):
                if slot is not None:
                    self.build_case(path, "static_block_taken", f"statischer Block {slot!r} ist schon belegt")
                elif block_id is not None:
                    self.build_case(path, "static_block_unknown",
                                    f"statischer Block {block_type!r} mit ID {block_id!r} steht nicht im Liquid des Ziels")
                return None
            child = {"type": block_type, "settings": {}, "static": True}
            node.setdefault("blocks", {})[slot] = child
            node.setdefault("block_order", [])
            created.append((node, slot))
            return child, child_view
        if not schema_module.block_allowed(self.target, view, block_type):
            self.build_case(path, "block_not_allowed", f"Blocktyp {block_type!r} ist im Ziel an dieser Stelle nicht erlaubt")
            return None
        wanted = block_id or re.sub(r"[^A-Za-z0-9]+", "_", block_type).strip("_") or "block"
        child = {"type": block_type, "settings": {}}
        new_id = self.insert_dynamic(node, view, wanted, child, path, report_rename=False)
        created.append((node, new_id))
        return child, child_view

    @staticmethod
    def remove_empty(created: list) -> None:
        for parent, child_id in reversed(created):
            child = parent["blocks"].get(child_id)
            if child is not None and not child.get("settings") and not child.get("blocks"):
                del parent["blocks"][child_id]
                if child_id in parent.get("block_order", []):
                    parent["block_order"].remove(child_id)

    def place_child_values(self, path: str, node: dict, view: dict, children: list) -> None:
        """Werte mit `block` an ihren Kindblock setzen, Pfade wie `a/b` Ebene für Ebene."""
        for item in children:
            created: list = []
            current = (node, view)
            parts = item["block"].split("/")
            for index, part in enumerate(parts):
                last = index == len(parts) - 1
                current = self.ensure_child(item["path"], current[0], current[1], part,
                                            item["block_id"] if last else None, created)
                if current is None:
                    break
            if current is None or not self.put(current[0]["settings"], current[1], item["key"], item["value"],
                                               item["path"], item["source_key"], item["source_type"]):
                self.remove_empty(created)

    def build_node(self, path: str, node_type: str, source_view: dict | None, data: dict, entry: dict,
                   target_view: dict) -> dict:
        """Ein Section- oder Block-Knoten des Ziels samt Einstellungen und Blöcken."""
        node = {"type": node_type}
        if "name" in data:
            node["name"] = data["name"]
        if data.get("disabled"):
            node["disabled"] = True
        settings, children = self.map_settings(path, source_view, data.get("settings"), entry, target_view)
        node["settings"] = settings
        node["blocks"], node["block_order"] = {}, []
        # Kindblöcke aus Einstellungen zuerst: Überschrift und Titel stehen vor dem übertragenen Inhalt.
        self.place_child_values(path, node, target_view, children)
        self.fill_blocks(path, source_view, data, entry, node, target_view)
        if not node["blocks"] and "blocks" not in data and not entry.get("blocks"):
            del node["blocks"], node["block_order"]
        return node

    def fill_blocks(self, path: str, source_parent: dict | None, source_node: dict, entry: dict,
                    out_node: dict, target_parent: dict) -> None:
        """Blöcke der Quelle in den Knoten des Ziels übertragen."""
        source_blocks = source_node.get("blocks") or {}
        order = [block_id for block_id in source_node.get("block_order") or [] if block_id in source_blocks]
        order += [block_id for block_id in source_blocks if block_id not in order]
        mapped = entry.get("blocks") or {}
        for block_id in order:
            block = source_blocks[block_id]
            block_type = block.get("type", "")
            block_path = f"{path}.blocks.{block_id}"
            is_app = block_type.startswith(APP_PREFIX)
            block_entry = mapped.get(block_type) or (mapped.get(APP_ENTRY) if is_app else None)
            if is_app and block_entry is None:
                block_entry = {"target": APP_ENTRY}
            if block_entry is None:
                self.build_case(block_path, "unmapped_block", f"Blocktyp {block_type!r} steht nicht im Mapping",
                                type=block_type)
                continue
            action = block_entry.get("action", "configure")
            if action == "drop":
                self.report["skipped"].append({"file": self.file, "path": block_path, "type": block_type,
                                               "reason": block_entry.get("reason") or block_entry.get("notes")
                                               or "Mapping: drop"})
                continue
            if action == "build":
                self.build_case(block_path, "mapping_build", block_entry.get("reason") or block_entry.get("notes", ""),
                                type=block_type)
                continue
            dest_node, dest_view = out_node, target_parent
            if block_entry.get("parent"):
                created: list = []
                found = None
                current = (out_node, target_parent)
                for part in block_entry["parent"].split("/"):
                    found = current = self.ensure_child(block_path, current[0], current[1], part, None, created)
                    if found is None:
                        break
                if found is None:
                    self.remove_empty(created)
                    continue
                dest_node, dest_view = found
            if is_app:
                if schema_module.block_allowed(self.target, dest_view, block_type):
                    self.insert_dynamic(dest_node, dest_view, block_id, copy.deepcopy(block), path, True)
                    self.report["app_items"].append({"file": self.file, "path": block_path, "type": block_type})
                else:
                    self.build_case(block_path, "app_block_not_accepted",
                                    "App-Block, aber das Ziel nimmt hier kein @app auf", type=block_type)
                continue
            target_type = block_entry.get("target", block_type)
            slot = None
            if "static_id" in block_entry or block_entry.get("static"):
                slot = self.static_slot(dest_view, target_type, block_entry.get("static_id"), block_path)
                if slot is None:
                    if not entries_have(self.report["build"], block_path):
                        self.build_case(block_path, "static_block_unknown",
                                        f"statischer Block {target_type!r} steht nicht im Liquid des Ziels")
                    continue
                if slot in (dest_node.get("blocks") or {}):
                    self.build_case(block_path, "static_block_taken", f"statischer Block {slot!r} ist schon belegt")
                    continue
            elif not schema_module.block_allowed(self.target, dest_view, target_type):
                self.build_case(block_path, "block_not_allowed",
                                f"Blocktyp {target_type!r} ist im Ziel an dieser Stelle nicht erlaubt")
                continue
            target_view = schema_module.block_definition(self.target, dest_view, target_type)
            if target_view is None:
                self.build_case(block_path, "missing_target_schema", f"Blocktyp {target_type!r} hat im Ziel kein Schema")
                continue
            source_view = schema_module.block_definition(self.source, source_parent, block_type)
            if source_view is None:
                self.build_case(block_path, "missing_source_schema",
                                f"Blocktyp {block_type!r} hat in der Quelle kein Schema, Standardwerte unbekannt")
            node = self.build_node(block_path, target_type, source_view, block, block_entry, target_view)
            if slot is not None:
                node["static"] = True
                dest_node.setdefault("blocks", {})[slot] = node
                dest_node.setdefault("block_order", [])
            else:
                self.insert_dynamic(dest_node, dest_view, block_id, node, path, True)

    # Sections ----------------------------------------------------------------

    def map_section(self, section_id: str, data: dict) -> dict | None:
        path = f"sections.{section_id}"
        section_type = data.get("type", "")
        instance = (self.instances.get(self.file) or {}).get(section_id) or {}
        if instance.get("action") == "drop":
            self.report["skipped"].append({"file": self.file, "path": path, "type": section_type,
                                           "reason": instance.get("reason") or "Override: drop"})
            return None
        if not valid_block_id(section_id):
            self.build_case(path, "invalid_section_id",
                            "Section-ID ist ungültig; Section-IDs werden nicht umbenannt (Übersetzungen hängen daran)")
            return None
        if section_type.startswith(APP_PREFIX):
            self.report["app_items"].append({"file": self.file, "path": path, "type": section_type})
            return copy.deepcopy(data)
        entry = (self.mapping.get("sections") or {}).get(section_type)
        if entry is None:
            self.build_case(path, "unmapped_section", f"Section-Typ {section_type!r} steht nicht im Mapping",
                            type=section_type)
            return None
        action = entry.get("action", "configure")
        if action == "drop":
            self.report["skipped"].append({"file": self.file, "path": path, "type": section_type,
                                           "reason": entry.get("reason") or entry.get("notes") or "Mapping: drop"})
            return None
        if action == "build":
            self.build_case(path, "mapping_build", entry.get("reason") or entry.get("notes", ""), type=section_type)
            return None
        target_type = entry.get("target", section_type)
        target_view = self.target["sections"].get(target_type)
        if target_view is None:
            self.build_case(path, "missing_target_schema", f"Ziel-Section {target_type!r} hat kein Schema")
            return None
        source_view = self.source["sections"].get(section_type)
        if source_view is None:
            self.build_case(path, "missing_source_schema",
                            f"Section {section_type!r} hat in der Quelle kein Schema, Standardwerte unbekannt")
        node = self.build_node(path, target_type, source_view, data, entry, target_view)
        for key, value in (instance.get("set") or {}).items():
            self.put(node["settings"], target_view, key, copy.deepcopy(value), f"{path}.settings.{key}", key)
        css = self.custom_css(path, entry, data)
        if css:
            node["custom_css"] = css
        return node

    def custom_css(self, path: str, entry: dict, data: dict) -> list | None:
        """Regel 4: eigenes CSS je Section höchstens 500 Zeichen."""
        wanted = entry.get("custom_css")
        source_css = data.get("custom_css") or []
        if wanted is None:
            if source_css:
                self.build_case(path, "custom_css_not_carried",
                                "eigenes CSS der Quelle nicht übernommen, die Selektoren gehören zum alten Theme",
                                characters=custom_css_length(source_css))
            return None
        rules = list(source_css) if wanted == "source" else list(wanted)
        if not rules:
            return None
        length = custom_css_length(rules)
        if length > CUSTOM_CSS_MAX:
            self.build_case(path, "custom_css_too_long",
                            f"{length} Zeichen eigenes CSS, erlaubt sind {CUSTOM_CSS_MAX}; in eine eigene Datei legen",
                            characters=length)
            return None
        return rules

    def map_sections_document(self, source_doc: dict) -> tuple[dict, list]:
        sections, emitted = {}, []
        for section_id, data in (source_doc.get("sections") or {}).items():
            node = self.map_section(section_id, data)
            if node is not None:
                sections[section_id] = node
                emitted.append(section_id)
        order = [section_id for section_id in source_doc.get("order") or [] if section_id in sections]
        order += [section_id for section_id in emitted if section_id not in order]
        return sections, order

    # Dateien -----------------------------------------------------------------

    def lookup(self, kind: str, name: str) -> dict | None:
        """Eintrag im Mapping: exakt, bei Templates dann der Grundtyp, zuletzt `*`.

        Ein alternatives Template wie `collection.sommer` oder eine Markt-Variante
        `product.beispiel.context.de` steht selten einzeln im Mapping, folgt aber
        derselben Zuordnung wie sein Grundtyp `collection` bzw. `product`. Ohne
        diesen Rückfall wäre jedes alternative Template ein `build`-Fall; im ersten
        Probelauf an einer echten Sicherung waren das fast alle Templates.
        """
        table = self.mapping.get(kind) or {}
        if name in table:
            return table[name]
        if kind == "templates":
            base = template_base(name)
            if base != name and base in table:
                return table[base]
        return table.get("*")

    def generate_template(self, rel: str) -> None:
        self.file = rel
        name = rel[len("templates/"):-len(".json")]
        entry = self.lookup("templates", name)
        if entry is None:
            self.build_case("", "unmapped_template", f"Template {name!r} steht nicht im Mapping")
            return
        action = entry.get("action", "configure")
        if action == "drop":
            self.report["skipped"].append({"file": rel, "path": "", "type": "template",
                                           "reason": entry.get("reason") or entry.get("notes") or "Mapping: drop"})
            return
        if action == "build":
            self.build_case("", "mapping_build", entry.get("reason") or entry.get("notes", ""))
            return
        source_doc = schema_module.read_json_file(self.source_dir / rel)
        document = {}
        for key, value in source_doc.items():
            if key == "layout":
                if value is False or (isinstance(value, str) and (self.target_dir / "layout" / f"{value}.liquid").is_file()):
                    document["layout"] = value
                else:
                    self.build_case("layout", "missing_layout", f"Layout {value!r} gibt es im Ziel nicht")
            elif key == "wrapper":
                document["wrapper"] = value
            elif key == "sections":
                document["sections"], document["order"] = self.map_sections_document(source_doc)
            elif key not in TEMPLATE_KEYS:
                self.dropped(key, key, "unbekanntes Attribut im Template")
        document.setdefault("sections", {})
        document.setdefault("order", [])
        self.documents[rel] = document

    def generate_groups(self) -> None:
        """Section-Groups der Quelle auf Gruppen des Ziels, mehrere Quellen auch in eine Gruppe.

        `position: start` stellt die Sections einer Quelle an den Anfang der Ziel-Gruppe,
        sonst kommen sie in der Reihenfolge des Mappings dahinter. Gleiche Section-IDs
        aus zwei Quellen bekommen den Namen der Quell-Gruppe vorangestellt.
        """
        directory = self.source_dir / "sections"
        table = self.mapping.get("section_groups") or {}
        names = list(table)
        parts: dict[str, list] = {}
        for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
            rel = path.relative_to(self.source_dir).as_posix()
            self.file = rel
            name = path.stem
            entry = self.lookup("section_groups", name)
            if entry is None:
                self.build_case("", "unmapped_group", f"Section-Group {name!r} steht nicht im Mapping")
                continue
            action = entry.get("action", "configure")
            if action == "drop":
                self.report["skipped"].append({"file": rel, "path": "", "type": "group",
                                               "reason": entry.get("reason") or entry.get("notes") or "Mapping: drop"})
                continue
            if action == "build":
                self.build_case("", "mapping_build", entry.get("reason") or entry.get("notes", ""))
                continue
            source_doc = schema_module.read_json_file(path)
            sections, order = self.map_sections_document(source_doc)
            rank = (0 if entry.get("position") == "start" else 1, names.index(name) if name in names else len(names), name)
            parts.setdefault(entry.get("target", name), []).append((rank, name, source_doc, sections, order))
        for target, group_parts in parts.items():
            group_parts.sort(key=lambda part: part[0])
            rel = f"sections/{target}.json"
            self.file = rel
            existing_path = self.target_dir / rel
            existing = schema_module.read_json_file(existing_path) if existing_path.is_file() else {}
            first = group_parts[0][2]
            document = {"type": existing.get("type", first.get("type")), "name": existing.get("name", first.get("name")),
                        "sections": {}, "order": []}
            for _, name, _, sections, order in group_parts:
                for section_id in order:
                    new_id = section_id
                    if new_id in document["sections"]:
                        base = re.sub(r"[^A-Za-z0-9]+", "_", f"{name}_{section_id}").strip("_")
                        new_id, counter = base, 2
                        while new_id in document["sections"]:
                            new_id, counter = f"{base}_{counter}", counter + 1
                        self.report["renamed_section_ids"].append({"file": rel, "from_group": name,
                                                                   "old_id": section_id, "new_id": new_id})
                    document["sections"][new_id] = sections[section_id]
                    document["order"].append(new_id)
            if len(group_parts) > 1:
                self.report["merged_groups"].append({"file": rel, "sources": [part[1] for part in group_parts]})
            self.documents[rel] = document

    def generate_settings_data(self) -> None:
        rel = "config/settings_data.json"
        self.file = rel
        rules = self.mapping.get("settings_data")
        source_path = self.source_dir / rel
        if rules is None or not source_path.is_file():
            if rules is not None:
                self.build_case("", "missing_source", "settings_data.json fehlt in der Sicherung")
            return
        source_doc = schema_module.read_json_file(source_path)
        current = source_doc.get("current") or {}
        if isinstance(current, str):
            # Ältere Themes speichern in `current` nur den Namen eines Presets.
            current = (source_doc.get("presets") or {}).get(current) or {}
        for block_id, block in (current.get("blocks") or {}).items():
            self.report["app_embeds"].append({"file": rel, "path": f"current.blocks.{block_id}",
                                              "type": block.get("type"), "disabled": bool(block.get("disabled"))})
        for key in ("sections", "content_for_index"):
            if current.get(key):
                self.build_case(f"current.{key}", "vintage_static_sections",
                                "statische Sections eines Vintage-Themes, Inhalt muss eigens übertragen werden")
        if (source_doc.get("platform_customizations") or {}).get("custom_css"):
            self.build_case("platform_customizations.custom_css", "custom_css_not_carried",
                            "eigenes CSS auf Theme-Ebene nicht übernommen, die Selektoren gehören zum alten Theme")
        source_settings = {key: value for key, value in current.items()
                           if key not in ("blocks", "sections", "content_for_index")}
        mapped, _ = self.map_settings("current", self.source["settings_schema"], source_settings,
                                      {"settings": rules}, self.target["settings_schema"], scope="settings_data")
        existing_path = self.target_dir / rel
        presets = {}
        if existing_path.is_file():
            presets = schema_module.read_json_file(existing_path).get("presets") or {}
        self.documents[rel] = {"current": mapped, "presets": presets}

    def run(self, living: set[str] | None = None) -> None:
        """Erzeugt alle Templates oder, mit `living`, nur die zugewiesenen und die Grundtypen."""
        self.report["mapping_findings"] = check_mapping_against_schemas(self.mapping, self.source, self.target)
        templates = self.source_dir / "templates"
        for path in sorted(templates.rglob("*.liquid")) if templates.is_dir() else []:
            rel = path.relative_to(self.source_dir).as_posix()
            name = rel[len("templates/"):-len(".liquid")]
            if name not in ALWAYS_LIQUID:
                self.file = rel
                self.build_case("", "liquid_template", "Liquid-Template, der Inhalt steckt im Code (Vintage)")
        for path in sorted(templates.rglob("*.json")) if templates.is_dir() else []:
            rel = path.relative_to(self.source_dir).as_posix()
            name = rel[len("templates/"):-len(".json")]
            key = name.split(".context.", 1)[0]
            if living is not None and key not in living and template_base(name) != name:
                self.report["skipped"].append({"file": rel, "path": "", "type": "template",
                                               "reason": "keinem Objekt zugewiesen (templates.json)"})
                continue
            self.generate_template(rel)
        self.generate_groups()
        self.generate_settings_data()

    # Ausgabe -----------------------------------------------------------------

    def write(self, out_dir: Path) -> None:
        """Regel 5: Limits vor dem Schreiben; eine Datei darüber wird nicht geschrieben."""
        for rel, document in self.documents.items():
            text = serialize(document)
            size = len(text.encode("utf-8"))
            if rel == "config/settings_data.json":
                violations = []
                if size > LIMITS["settings_data_bytes"]:
                    violations.append({"file": rel, "limit": "settings_data_bytes", "value": size,
                                       "max": LIMITS["settings_data_bytes"]})
            else:
                violations = check_limits(document, rel, self.target, size)
            self.report["limit_violations"].extend(violations)
            if violations:
                self.report["files"].append({"path": rel, "written": False, "reason": "Limit überschritten"})
                continue
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            self.report["files"].append({"path": rel, "written": True, "bytes": size})

    def diff_against_target(self) -> dict:
        """Regel 8: Was der Lauf im Ziel-Repo ändern würde, je Datei mit den betroffenen Pfaden."""
        result = {"compared_with": "target", "new": [], "changed": [], "unchanged": [], "not_generated": []}
        for entry in self.report["files"]:
            if not entry["written"]:
                continue
            rel = entry["path"]
            existing = self.target_dir / rel
            if not existing.is_file():
                result["new"].append(rel)
                continue
            try:
                old = schema_module.read_json_file(existing)
            except json.JSONDecodeError:
                result["changed"].append({"path": rel, "differences": ["(Ziel-Datei ist kein gültiges JSON)"]})
                continue
            differences = json_differences(old, self.documents[rel])
            if differences:
                result["changed"].append({"path": rel, "differences": differences})
            else:
                result["unchanged"].append(rel)
        generated = set(self.documents)
        for pattern in ("templates/**/*.json", "sections/*.json"):
            for path in sorted(self.target_dir.glob(pattern)):
                rel = path.relative_to(self.target_dir).as_posix()
                if rel not in generated:
                    result["not_generated"].append(rel)
        return result

    def findings(self) -> int:
        return (len(self.report["build"]) + len([d for d in self.report["dropped"] if not d["intended"]])
                + len(self.report["limit_violations"]) + len(self.report["mapping_findings"])
                + len(self.report["schema_errors"]))


def entries_have(items: list, path: str) -> bool:
    return any(item.get("path") == path for item in items)


def lock_inputs(mapping_arg: str, overrides_arg: str | None, source_arg: str, target_arg: str) -> dict:
    """`sources.lock`: jede Eingabe mit SHA-256, Pfade relativ zum jeweiligen Verzeichnis."""

    def theme_files(root: Path, patterns) -> dict:
        files = {}
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                if path.is_file():
                    files[path.relative_to(root).as_posix()] = sha256_file(path)
        return dict(sorted(files.items()))

    source_root, target_root = Path(source_arg), Path(target_arg)
    return {
        "mapping": {"path": mapping_arg, "sha256": sha256_file(Path(mapping_arg))},
        "overrides": {"path": overrides_arg, "sha256": sha256_file(Path(overrides_arg))} if overrides_arg else None,
        "source": {"dir": source_arg, "files": theme_files(source_root, (
            "templates/**/*.json", "templates/**/*.liquid", "sections/*.json", "sections/*.liquid",
            "blocks/*.liquid", "config/settings_data.json", "config/settings_schema.json"))},
        "target": {"dir": target_arg, "files": theme_files(target_root, (
            "sections/*.liquid", "sections/*.json", "blocks/*.liquid", "templates/**/*.json",
            "config/settings_schema.json", "config/settings_data.json", "layout/*.liquid"))},
    }


def prepare_out_dir(out: Path, source: Path, target: Path) -> str | None:
    """Das Testverzeichnis prüfen und von einem früheren Lauf leeren. Gibt einen Fehler zurück oder `None`."""
    resolved = out.resolve()
    for name, other in (("Ziel-Repo", target), ("Sicherung", source)):
        other = other.resolve()
        if resolved == other or resolved.is_relative_to(other):
            return (f"--out liegt im {name}. Erst in ein Testverzeichnis erzeugen, "
                    "dann gegen das Ziel-Repo vergleichen und übernehmen.")
    if out.exists() and any(out.iterdir()):
        if not (out / "report.json").is_file():
            return "--out ist nicht leer und stammt nicht aus einem früheren Lauf (report.json fehlt)."
        for name in ("templates", "sections", "config"):
            if (out / name).is_dir():
                shutil.rmtree(out / name)
        (out / "report.json").unlink()
    out.mkdir(parents=True, exist_ok=True)
    return None


def template_base(name: str) -> str:
    """Grundtyp eines Templates: `collection.sommer` -> `collection`, `customers/account` bleibt."""
    return name.split(".", 1)[0]


def living_templates(path) -> set[str]:
    """Namen der zugewiesenen Templates aus `migration/inventory/templates.json` (theme.templates)."""
    data = schema_module.read_json_file(path)
    names = set()
    for name, entry in (data.get("templates") or {}).items():
        objects = (entry or {}).get("objects", 0)
        # None heißt: Typ ohne Zuweisung (etwa 404), das Template lebt immer.
        if objects is None or objects > 0:
            names.add(name)
    return names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Templates und Einstellungen des Ziel-Themes erzeugen")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--overrides")
    parser.add_argument("--source", required=True, help="Sicherung des Quell-Themes")
    parser.add_argument("--target-schemas", required=True, help="Ziel-Repo, aus dem die Schemas kommen")
    parser.add_argument("--out", required=True, help="Testverzeichnis für die Ausgabe")
    parser.add_argument("--lock", required=True, help="Pfad für sources.lock")
    parser.add_argument("--living", help="templates.json aus theme.templates: nur zugewiesene Templates erzeugen")
    args = parser.parse_args(argv)

    def fail(message: str) -> int:
        print(json.dumps({"error": message}, ensure_ascii=False))
        return 2

    for flag, value in (("--source", args.source), ("--target-schemas", args.target_schemas)):
        if not Path(value).is_dir():
            return fail(f"{flag}: Verzeichnis fehlt: {value}")
    try:
        mapping = schema_module.read_json_file(args.mapping)
        overrides = schema_module.read_json_file(args.overrides) if args.overrides else None
    except (OSError, json.JSONDecodeError) as exc:
        return fail(f"Mapping oder Overrides nicht lesbar: {exc}")
    errors = validate_mapping(mapping)
    if overrides is not None and not isinstance(overrides, dict):
        errors.append("Overrides sind kein JSON-Objekt")
    if not errors and overrides:
        errors = validate_mapping(merge_mapping(mapping, overrides))
    if errors:
        print(json.dumps({"error": "Mapping ungültig", "details": errors}, ensure_ascii=False))
        return 2
    out = Path(args.out)
    problem = prepare_out_dir(out, Path(args.source), Path(args.target_schemas))
    if problem:
        return fail(problem)

    generator = Generator(mapping, overrides, args.source, args.target_schemas)
    try:
        living = living_templates(args.living) if args.living else None
    except (OSError, json.JSONDecodeError) as exc:
        return fail(f"--living nicht lesbar: {exc}")
    try:
        generator.run(living)
    except json.JSONDecodeError as exc:
        return fail(f"{generator.file}: kein gültiges JSON ({exc})")
    generator.write(out)
    report = generator.report
    report["diff"] = generator.diff_against_target()
    report["diff"]["compared_with"] = args.target_schemas
    summary = {
        "out": str(out),
        "files_written": sum(1 for f in report["files"] if f["written"]),
        "files_not_written": sum(1 for f in report["files"] if not f["written"]),
        "build": len(report["build"]),
        "dropped": len([d for d in report["dropped"] if not d["intended"]]),
        "dropped_intended": len([d for d in report["dropped"] if d["intended"]]),
        "defaults_applied": len(report["defaults_applied"]),
        "limit_violations": len(report["limit_violations"]),
        "mapping_findings": len(report["mapping_findings"]),
        "diff_changed": len(report["diff"]["changed"]),
        "diff_new": len(report["diff"]["new"]),
        "findings": generator.findings(),
    }
    report["summary"] = summary
    (out / "report.json").write_text(serialize(report), encoding="utf-8")
    lock = Path(args.lock)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(serialize(lock_inputs(args.mapping, args.overrides, args.source, args.target_schemas)),
                    encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
