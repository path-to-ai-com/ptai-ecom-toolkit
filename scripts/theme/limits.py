"""Shopify-Limits für Themes prüfen, bevor geschrieben wird (Spec Abschnitt 2).

Quelle der Zahlen: shopify.dev, "Theme architecture: limits", und die
Help-Seite zum Hinzufügen von Themes, beide abgerufen am 05.10.2026. Größen
sind dezimal gerechnet (512 KB = 512.000 Byte): bei einer Grenze, die Shopify
in KB nennt, ist die kleinere Lesart die sichere.

Statische Blöcke (`"static": true`) zählen laut Doku nicht zu den Blockzahlen.

CLI:
    python3 -m theme.limits check --theme-dir <dir> [--out <file>]
"""
import argparse
import sys

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, emit, write_json
from theme.files import UPSERT_LIMIT, read_theme_dir
from theme.normalize import parse_json

MAX_THEMES = 20
MAX_THEMES_PLUS = 100
MAX_JSON_TEMPLATES = 1000
MAX_SECTIONS_PER_TEMPLATE = 25
MAX_BLOCKS_PER_SECTION = 50
MAX_BLOCKS_PER_TEMPLATE = 1250
MAX_NESTING = 8
MAX_BLOCK_FILES = 300
MAX_JSON_TEMPLATE_BYTES = 512_000
MAX_SETTINGS_DATA_BYTES = 1_500_000
MAX_LOCALE_BYTES = 1_500_000
MAX_LIQUID_BYTES = 256_000
MAX_LOCALE_KEYS = 3400
MAX_UPSERT_FILES = UPSERT_LIMIT
MAX_ZIP_BYTES = 50_000_000


def theme_capacity(themes: list[dict], plus: bool | None) -> dict:
    """Belegte und freie Theme-Plätze; `full` heißt: kein Duplikat und kein Upload mehr möglich."""
    limit = MAX_THEMES_PLUS if plus else MAX_THEMES
    count = len(themes)
    result = {"count": count, "limit": limit, "free": max(limit - count, 0), "full": count >= limit,
              "plus": plus}
    if plus is None:
        result["note"] = "Plan nicht lesbar, 20 Plätze angenommen (Plus: 100)"
    return result


def _finding(rule: str, file: str | None, value, limit, message: str) -> dict:
    return {"rule": rule, "file": file, "value": value, "limit": limit, "message": message}


def _walk_blocks(blocks, depth: int, stats: dict) -> None:
    if not isinstance(blocks, dict):
        return
    for block in blocks.values():
        if not isinstance(block, dict):
            continue
        if block.get("static") is not True:
            stats["total"] += 1
        stats["depth"] = max(stats["depth"], depth)
        _walk_blocks(block.get("blocks"), depth + 1, stats)


def check_structure(name: str, document) -> list[dict]:
    """Sections je Template, Blöcke je Section und je Template, Verschachtelung."""
    findings = []
    sections = document.get("sections") if isinstance(document, dict) else None
    if not isinstance(sections, dict):
        return findings
    if len(sections) > MAX_SECTIONS_PER_TEMPLATE:
        findings.append(_finding("sections_per_template", name, len(sections), MAX_SECTIONS_PER_TEMPLATE,
                                 f"{len(sections)} Sections, erlaubt sind {MAX_SECTIONS_PER_TEMPLATE}"))
    stats = {"total": 0, "depth": 0}
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks") if isinstance(section.get("blocks"), dict) else {}
        direct = sum(1 for b in blocks.values() if isinstance(b, dict) and b.get("static") is not True)
        if direct > MAX_BLOCKS_PER_SECTION:
            findings.append(_finding("blocks_per_section", f"{name}#{section_id}", direct, MAX_BLOCKS_PER_SECTION,
                                     f"Section {section_id} hat {direct} Blöcke"))
        _walk_blocks(blocks, 1, stats)
    if stats["total"] > MAX_BLOCKS_PER_TEMPLATE:
        findings.append(_finding("blocks_per_template", name, stats["total"], MAX_BLOCKS_PER_TEMPLATE,
                                 f"{stats['total']} Blöcke im Template"))
    if stats["depth"] > MAX_NESTING:
        findings.append(_finding("nesting_depth", name, stats["depth"], MAX_NESTING,
                                 f"Blöcke {stats['depth']} Ebenen tief verschachtelt"))
    return findings


def _leaf_count(value) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(child) for child in value.values())
    return 1


def _size_limit(name: str) -> tuple[str, int] | None:
    if name == "config/settings_data.json":
        return "settings_data_size", MAX_SETTINGS_DATA_BYTES
    if name.startswith("locales/") and name.endswith(".json"):
        return "locale_size", MAX_LOCALE_BYTES
    if name.endswith(".json") and (name.startswith("templates/") or name.startswith("sections/")
                                   or name == "config/settings_schema.json"):
        return "json_template_size", MAX_JSON_TEMPLATE_BYTES
    if name.endswith(".liquid"):
        return "liquid_size", MAX_LIQUID_BYTES
    return None


def check_files(files: dict[str, bytes]) -> list[dict]:
    """Alle Limits über einen Satz Theme-Dateien."""
    findings = []
    json_templates = [n for n in files if n.startswith("templates/") and n.endswith(".json")]
    if len(json_templates) > MAX_JSON_TEMPLATES:
        findings.append(_finding("json_templates", None, len(json_templates), MAX_JSON_TEMPLATES,
                                 f"{len(json_templates)} JSON-Templates"))
    block_files = [n for n in files if n.startswith("blocks/")]
    if len(block_files) > MAX_BLOCK_FILES:
        findings.append(_finding("block_files", None, len(block_files), MAX_BLOCK_FILES,
                                 f"{len(block_files)} Dateien in blocks/"))
    for name in sorted(files):
        data = files[name]
        limit = _size_limit(name)
        if limit and len(data) > limit[1]:
            findings.append(_finding(limit[0], name, len(data), limit[1], f"{len(data)} Byte"))
        if not name.endswith(".json"):
            continue
        try:
            document = parse_json(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            findings.append(_finding("invalid_json", name, None, None,
                                     f"kein gültiges JSON ({exc}); ein ZIP-Import ließe die Datei still weg"))
            continue
        if name.startswith("templates/") or (name.startswith("sections/") and name.endswith(".json")):
            findings += check_structure(name, document)
        if name.startswith("locales/"):
            keys = _leaf_count(document)
            if keys > MAX_LOCALE_KEYS:
                findings.append(_finding("locale_keys", name, keys, MAX_LOCALE_KEYS, f"{keys} Übersetzungen"))
    return findings


def check_theme_dir(theme_dir) -> list[dict]:
    return check_files(read_theme_dir(theme_dir))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.limits", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Limits eines Theme-Ordners prüfen")
    check.add_argument("--theme-dir", required=True)
    check.add_argument("--out", default="migration/build/limits.json")
    args = parser.parse_args(argv)
    try:
        findings = check_theme_dir(args.theme_dir)
    except (OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    write_json(args.out, {"theme_dir": args.theme_dir, "findings": findings})
    emit({"ok": True, "out": args.out, "findings": len(findings),
          "rules": sorted({f["rule"] for f in findings})})
    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
