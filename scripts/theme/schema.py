"""Schemas eines Themes lesen: Sections, Theme-Blöcke und globale Einstellungen.

Aufruf:
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.schema extract \\
        --theme-dir <dir> --out <schemas.json>
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.schema export \\
        --theme-dir <dir> --out <auszug.json>

`extract` schreibt die volle Sicht, die der Generator nutzt. `export` schreibt
den Schema-Auszug, den `theme.mapping_check` liest: nur Namen, Typen,
Wertebereiche und Optionen, kein Code. Er bleibt lokal, weil er aus fremdem
Code abgeleitet ist.

Grundlage für den Generator (`theme.generate`): Er schreibt nur Einstellungen,
die im Schema des Ziels stehen, und liest für jeden fehlenden Schlüssel den
Standardwert aus dem Schema der Quelle. Ein fehlender Schlüssel in einem
JSON-Template heißt Schema-Standard, nie "aus"; bei einer Checkbox ohne
`default` ist der Standard laut Shopify `false`.

Gelesen wird je Datei der eine `{% schema %}`-Block:

- `sections/*.liquid`: Sections. Erlaubte Blöcke stehen in `blocks`, entweder
  als Typ (`@theme`, `@app`, ein Dateiname aus `blocks/`, auch privat mit `_`)
  oder als Block mit eigenen Einstellungen direkt im Schema (inline).
- `blocks/*.liquid`: Theme-Blöcke. Ein Name mit `_` am Anfang ist privat und
  zählt nicht unter `@theme`, er muss ausdrücklich angefordert werden.
- `config/settings_schema.json`: globale Einstellungen samt `theme_info`.

Statische Blöcke stehen nicht im Schema, sondern im Liquid-Code als
`{% content_for 'block', type: '...', id: '...' %}`; sie werden mitgelesen,
weil sie im JSON mit `"static": true` und ohne Eintrag in `block_order`
stehen müssen.

Exit-Code 0 ohne Befund, 1 wenn ein Schema nicht lesbar ist, 2 bei Fehlern.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_TAG = re.compile(r"{%-?\s*schema\s*-?%}(.*?){%-?\s*endschema\s*-?%}", re.S)
CONTENT_FOR_BLOCK = re.compile(r"{%-?\s*content_for\s+['\"]block['\"]\s*,(.*?)-?%}", re.S)
NAMED_ARGUMENT = re.compile(r"(\w+)\s*:\s*['\"]([^'\"]*)['\"]")
#: Ein Kommentarkopf, den Shopify beim Schreiben vor `settings_data.json` setzt.
JSON_COMMENT_HEAD = re.compile(r"^\s*/\*.*?\*/\s*", re.S)

#: Einstellungstypen ohne Wert (nur Überschrift oder Hinweis im Editor).
SIDEBAR_TYPES = {"header", "paragraph"}


def read_json_text(text: str):
    """JSON lesen, auch mit dem Kommentarkopf, den Shopify vor Dateien setzt."""
    return json.loads(JSON_COMMENT_HEAD.sub("", text, count=1))


def read_json_file(path) -> object:
    return read_json_text(Path(path).read_text(encoding="utf-8"))


def schema_of(liquid: str):
    """Der geparste Inhalt des `{% schema %}`-Blocks oder `None` ohne Block."""
    match = SCHEMA_TAG.search(liquid)
    if not match:
        return None
    return json.loads(match.group(1))


def static_blocks_of(liquid: str) -> list[dict]:
    """Statische Blöcke aus `content_for 'block'`, je mit `type` und `id`."""
    found = []
    for match in CONTENT_FOR_BLOCK.finditer(liquid):
        arguments = dict(NAMED_ARGUMENT.findall(match.group(1)))
        if "type" in arguments and "id" in arguments:
            entry = {"type": arguments["type"], "id": arguments["id"]}
            if entry not in found:
                found.append(entry)
    return found


def effective_default(setting: dict):
    """Standardwert einer Einstellung; Checkbox ohne `default` ist `false`.

    Gibt `(True, wert)` zurück, wenn es einen Standard gibt, sonst `(False, None)`.
    """
    if "default" in setting:
        return True, setting["default"]
    if setting.get("type") == "checkbox":
        return True, False
    return False, None


def settings_index(settings: list | None) -> tuple[dict, dict]:
    """Einstellungen nach `id` und die Standardwerte daraus."""
    by_id, defaults = {}, {}
    for setting in settings or []:
        if not isinstance(setting, dict) or "id" not in setting or setting.get("type") in SIDEBAR_TYPES:
            continue
        by_id[setting["id"]] = setting
        has_default, value = effective_default(setting)
        if has_default:
            defaults[setting["id"]] = value
    return by_id, defaults


def describe(schema: dict, liquid: str, file: str) -> dict:
    """Die für Mapping und Generator nötige Sicht auf ein Section- oder Block-Schema."""
    settings, defaults = settings_index(schema.get("settings"))
    allowed, inline = [], {}
    for entry in schema.get("blocks") or []:
        if not isinstance(entry, dict) or "type" not in entry:
            continue
        allowed.append(entry["type"])
        # Ein Block mit Namen oder Einstellungen im Schema ist ein Section-Block
        # (inline); seine Einstellungen stehen hier, nicht in blocks/.
        if "settings" in entry or "name" in entry:
            block_settings, block_defaults = settings_index(entry.get("settings"))
            inline[entry["type"]] = {"settings": block_settings, "defaults": block_defaults,
                                     "limit": entry.get("limit")}
    return {
        "file": file,
        "name": schema.get("name"),
        "settings": settings,
        "defaults": defaults,
        "allowed_blocks": allowed,
        "accepts_theme_blocks": "@theme" in allowed,
        "accepts_app_blocks": "@app" in allowed,
        "inline_blocks": inline,
        "static_blocks": static_blocks_of(liquid),
        "max_blocks": schema.get("max_blocks"),
        "presets": schema.get("presets") or [],
    }


def extract(theme_dir) -> dict:
    """Je Section und Block das Schema, dazu die globalen Einstellungen.

    Ergebnis: `{"sections": {typ: sicht}, "blocks": {typ: sicht}, "settings_schema":
    {"settings", "defaults", "theme_info"}, "errors": [...]}`. Eine Datei ohne
    Schema steht mit leerer Sicht drin, eine mit ungültigem JSON unter `errors`.
    """
    root = Path(theme_dir)
    result = {"sections": {}, "blocks": {}, "settings_schema": {"settings": {}, "defaults": {}, "theme_info": {}},
              "errors": []}
    for kind in ("sections", "blocks"):
        for path in sorted((root / kind).glob("*.liquid")):
            rel = path.relative_to(root).as_posix()
            liquid = path.read_text(encoding="utf-8")
            try:
                schema = schema_of(liquid) or {}
            except json.JSONDecodeError as exc:
                result["errors"].append({"file": rel, "error": f"Schema ist kein gültiges JSON: {exc}"})
                continue
            view = describe(schema, liquid, rel)
            view["has_schema"] = bool(SCHEMA_TAG.search(liquid))
            if kind == "blocks":
                view["private"] = path.stem.startswith("_")
            result[kind][path.stem] = view
    settings_path = root / "config" / "settings_schema.json"
    if settings_path.is_file():
        try:
            groups = read_json_file(settings_path)
        except json.JSONDecodeError as exc:
            result["errors"].append({"file": "config/settings_schema.json", "error": str(exc)})
            groups = []
        flat = []
        for group in groups if isinstance(groups, list) else []:
            if group.get("name") == "theme_info":
                result["settings_schema"]["theme_info"] = {k: v for k, v in group.items() if k != "name"}
            flat.extend(group.get("settings") or [])
        settings, defaults = settings_index(flat)
        result["settings_schema"]["settings"] = settings
        result["settings_schema"]["defaults"] = defaults
    return result


def block_definition(schemas: dict, parent: dict | None, block_type: str) -> dict | None:
    """Einstellungen eines Blocktyps: inline im Eltern-Schema oder aus blocks/."""
    if parent and block_type in parent.get("inline_blocks", {}):
        return parent["inline_blocks"][block_type]
    return schemas["blocks"].get(block_type)


def block_allowed(schemas: dict, parent: dict, block_type: str) -> bool:
    """Darf der Elternteil diesen Blocktyp als dynamischen Block aufnehmen?"""
    if block_type.startswith("shopify://apps/"):
        return parent.get("accepts_app_blocks", False)
    if block_type in parent.get("allowed_blocks", []):
        return True
    block = schemas["blocks"].get(block_type)
    return bool(parent.get("accepts_theme_blocks") and block and not block.get("private"))


EXPORT_FIELDS = ("type", "min", "max", "step", "default")


def export_settings(settings: dict) -> dict:
    """Einstellungen für den Auszug: Typ, Wertebereich, Standard und die Werte der Optionen."""
    result = {}
    for setting_id, setting in settings.items():
        entry = {field: setting[field] for field in EXPORT_FIELDS if field in setting}
        if "options" in setting:
            entry["options"] = [option.get("value") for option in setting["options"] if isinstance(option, dict)]
        result[setting_id] = entry
    return result


def export(theme_dir) -> dict:
    """Schema-Auszug im Format von `theme.mapping_check`.

    `sections.<typ>.blocks` sind die Blöcke, die die Section annimmt: Blöcke mit
    eigenen Einstellungen im Schema mit `settings`, Theme-Blöcke, `@theme` und
    `@app` nur mit Namen. `blocks` sind die Theme-Blöcke aus `blocks/` mit den
    Blöcken, die sie selbst annehmen. `static_blocks` ergänzt, was das Liquid
    statisch rendert.
    """
    root = Path(theme_dir)
    data = extract(root)
    info = data["settings_schema"]["theme_info"]

    def section_blocks(view):
        blocks = {}
        for block_type in view["allowed_blocks"]:
            inline = view["inline_blocks"].get(block_type)
            blocks[block_type] = {"settings": export_settings(inline["settings"])} if inline else {}
        return blocks

    sections = {name: {"settings": export_settings(view["settings"]), "blocks": section_blocks(view),
                       "static_blocks": view["static_blocks"]}
                for name, view in data["sections"].items()}
    blocks = {name: {"settings": export_settings(view["settings"]), "blocks": list(view["allowed_blocks"]),
                     "static_blocks": view["static_blocks"]}
              for name, view in data["blocks"].items()}
    templates = sorted({path.relative_to(root / "templates").as_posix().rsplit(".", 1)[0]
                        for path in (root / "templates").rglob("*") if path.suffix in (".json", ".liquid")}
                       if (root / "templates").is_dir() else [])
    groups = sorted(path.stem for path in (root / "sections").glob("*.json")) if (root / "sections").is_dir() else []
    return {"theme": {"name": info.get("theme_name", ""), "version": info.get("theme_version", "")},
            "sections": sections, "blocks": blocks,
            "settings_schema": export_settings(data["settings_schema"]["settings"]),
            "templates": templates, "section_groups": groups, "errors": data["errors"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Schemas eines Themes lesen")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("extract", "volle Sicht für den Generator"), ("export", "Schema-Auszug für mapping_check")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--theme-dir", required=True)
        command.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not Path(args.theme_dir).is_dir():
        print(json.dumps({"error": f"Verzeichnis fehlt: {args.theme_dir}"}, ensure_ascii=False))
        return 2
    result = extract(args.theme_dir) if args.command == "extract" else export(args.theme_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"command": args.command, "out": str(out), "sections": len(result["sections"]),
                      "blocks": len(result["blocks"]), "errors": len(result["errors"])}, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
