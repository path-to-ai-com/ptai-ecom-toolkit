"""Template-Nutzung aus den Zuweisungen im Shop, abgeglichen mit den Template-Dateien.

**Wie viele Templates leben, ergibt sich aus den Zuweisungen, nie aus der
Dateiliste.** Eine Template-Datei beweist nur, dass ein Layout existiert. Die
Zuweisung (`templateSuffix`) hängt am Objekt und bleibt beim Theme-Wechsel;
fehlt im neuen Theme die gleichnamige Datei, rendert das Objekt sehr
wahrscheinlich das Standard-Template.

Gelesen werden Produkte, Kollektionen, Seiten, Blogs und Artikel, je mit
`templateSuffix`; `null` oder leer heißt Standard-Template. Markt-Varianten
(`<typ>.<suffix>.context.<markt>.json`) zählen zum Template, zu dem sie
gehören, und stehen dort unter `markets`.

Abfragen gegen das Admin-Schema 2026-04 validiert (05.10.2026). Scopes:
`read_products` für Produkte und Kollektionen, `read_content` beziehungsweise
`read_online_store_pages` für Seiten, Blogs und Artikel.

CLI:
    python3 -m theme.templates usage --snapshot <dir> --out migration/inventory/templates.json
"""
import argparse
import sys
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, write_json
from theme.shopify import ShopifyError, transport_from_config

_SUFFIX_QUERY = """query %(name)s($after: String) {
  %(field)s(first: 250, after: $after) {
    nodes { templateSuffix }
    pageInfo { hasNextPage endCursor }
  }
}"""

#: Objekttyp im Template-Namen zum Feld der Admin-API.
SUFFIX_QUERIES = {
    "product": ("products", _SUFFIX_QUERY % {"name": "ProductTemplates", "field": "products"}),
    "collection": ("collections", _SUFFIX_QUERY % {"name": "CollectionTemplates", "field": "collections"}),
    "page": ("pages", _SUFFIX_QUERY % {"name": "PageTemplates", "field": "pages"}),
    "blog": ("blogs", _SUFFIX_QUERY % {"name": "BlogTemplates", "field": "blogs"}),
    "article": ("articles", _SUFFIX_QUERY % {"name": "ArticleTemplates", "field": "articles"}),
}
ASSIGNABLE = tuple(SUFFIX_QUERIES)


def collect_suffixes(transport) -> dict[str, dict[str, int]]:
    """Je Objekttyp die Zahl der Objekte je Suffix; `""` ist das Standard-Template."""
    result = {}
    for kind, (field, query) in SUFFIX_QUERIES.items():
        counts: dict[str, int] = {}
        after, cursors = None, set()
        while True:
            connection = transport.execute(query, {"after": after}).get(field) or {}
            for node in connection.get("nodes") or []:
                suffix = node.get("templateSuffix") or ""
                counts[suffix] = counts.get(suffix, 0) + 1
            page = connection.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
            if not after or after in cursors:
                raise ShopifyError(f"Seitenzeiger bei {field} fehlt oder wiederholt sich")
            cursors.add(after)
        result[kind] = counts
    return result


def parse_template_name(path: str) -> dict | None:
    """`templates/product.beispiel.context.eu.json` zu Typ, Suffix und Markt."""
    if not path.startswith("templates/"):
        return None
    name = path[len("templates/"):]
    for extension in (".json", ".liquid"):
        if name.endswith(extension):
            name = name[: -len(extension)]
            break
    else:
        return None
    kind, _, rest = name.partition(".")
    parts = rest.split(".") if rest else []
    market = None
    if "context" in parts:
        index = parts.index("context")
        market = ".".join(parts[index + 1:]) or None
        parts = parts[:index]
    suffix = ".".join(parts)
    return {"type": kind, "suffix": suffix, "market": market,
            "key": kind + ("." + suffix if suffix else "")}


def template_files(snapshot_dir) -> list[str]:
    root = Path(snapshot_dir)
    base = root / "templates"
    if not base.is_dir():
        raise FileNotFoundError(f"{base} fehlt; ist das eine Theme-Sicherung?")
    return sorted(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())


def build_usage(names: list[str], suffixes: dict[str, dict[str, int]]) -> dict:
    templates: dict[str, dict] = {}
    for path in sorted(names, key=lambda n: (n.endswith(".liquid"), n)):
        parsed = parse_template_name(path)
        if not parsed:
            continue
        entry = templates.setdefault(parsed["key"], {"type": parsed["type"], "file": None, "objects": 0,
                                                     "markets": []})
        if parsed["market"]:
            entry["markets"].append(parsed["market"])
        elif entry["file"] is None:
            entry["file"] = path
    for key, entry in templates.items():
        parsed = parse_template_name(f"templates/{key}.json")
        if entry["type"] in ASSIGNABLE:
            entry["objects"] = suffixes.get(entry["type"], {}).get(parsed["suffix"], 0)
        else:
            entry["objects"] = None
        entry["markets"].sort()
    assigned_without_file = []
    for kind in ASSIGNABLE:
        for suffix, count in sorted(suffixes.get(kind, {}).items()):
            key = kind + ("." + suffix if suffix else "")
            if count and (key not in templates or templates[key]["file"] is None):
                assigned_without_file.append({"type": kind, "suffix": suffix, "objects": count})
    files_without_objects = sorted(
        entry["file"] for key, entry in templates.items()
        if entry["file"] and entry["type"] in ASSIGNABLE and "." in key and entry["objects"] == 0)
    return {"templates": dict(sorted(templates.items())), "assigned_without_file": assigned_without_file,
            "files_without_objects": files_without_objects}


def usage(transport, snapshot_dir) -> dict:
    return build_usage(template_files(snapshot_dir), collect_suffixes(transport))


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.templates", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    use = sub.add_parser("usage", help="Template-Nutzung aus den Zuweisungen")
    use.add_argument("--snapshot", required=True)
    use.add_argument("--out", default="migration/inventory/templates.json")
    use.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    try:
        if transport is None:
            transport = transport_from_config(load_config(args.workspace), workspace=args.workspace)
        result = usage(transport, args.snapshot)
    except (ConfigError, ShopifyError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    write_json(args.out, result)
    living = sum(1 for e in result["templates"].values() if e["objects"])
    emit({"ok": True, "out": args.out, "templates": len(result["templates"]), "living": living,
          "assigned_without_file": len(result["assigned_without_file"]),
          "files_without_objects": len(result["files_without_objects"])})
    return EXIT_FINDINGS if result["assigned_without_file"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
