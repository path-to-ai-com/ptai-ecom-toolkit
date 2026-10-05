"""Theme-Übersetzungen am Entwurf registrieren (Spec 7.7).

Theme-Übersetzungen hängen an der Theme-ID, nicht am Shop. Ein neues Theme
startet ohne sie, und ändert sich ein Ausgangswert, liefert Shopify weiter die
alte Übersetzung aus, bis neu registriert wird (im Feld belegt). Deshalb:

* Schlüssel und `digest` werden **frisch vom Entwurf** gelesen, unmittelbar
  vor dem Registrieren, nie aus einer Datei oder einem anderen Theme
  übernommen. `translationsRegister` verlangt den aktuellen
  `translatableContentDigest` je Wert.
* Ein Eintrag wird nur registriert, wenn genau ein Schlüssel des Servers
  passt: gleicher Pfad (Section, alle übergeordneten Block-IDs, Einstellung)
  und gleicher Ausgangswert. Gleicher Text allein reicht nicht. Bleibt ein
  Eintrag offen, wird gar nichts registriert.
* Nur die Ressource des Entwurfs (`resourceId` = Theme-GID) wird angefasst.
  Store-Übersetzungen (Produkte, Seiten, Menüs) nie.

Schlüsselaufbau im Feld beobachtet, nicht dokumentiert:
`section.<template>.<section-id>.<eltern-id>__<kind-id>.<einstellung>:<hash>`.
Für Einstellungen außerhalb von `templates/` (Section-Groups, Locale-Inhalte)
ist der Aufbau nicht belegt; solche Einträge brauchen einen geprüften `key`.

Quelldatei (`--source`):

    {"locale": "en", "entries": [
      {"file": "templates/index.json", "pointer": "/sections/hero/settings/title",
       "source_value": "Willkommen", "value": "Welcome"}]}

Ein Eintrag darf `key` tragen, einen exakt beobachteten Schlüssel ohne oder mit
Hash-Endung; dann zählt nur dieser.

Abfragen gegen das Admin-Schema 2026-04 validiert (05.10.2026). Scopes:
`read_translations`, `write_translations`, dazu `read_themes` für den Schutz.

CLI:
    python3 -m theme.translations register --theme <draft-id> --source <file> [--dir <theme-dir>] [--dry-run]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from theme import (EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config,
                   today, write_json)
from theme.guard import GuardError, assert_live_unchanged, check_write_target, live_fingerprint
from theme.normalize import parse_json
from theme.shopify import ShopifyError, numeric_id, theme_gid, transport_from_config

TRANSLATIONS_QUERY = """query ThemeTranslations($resourceId: ID!, $locale: String!) {
  translatableResource(resourceId: $resourceId) {
    resourceId
    translatableContent { key value digest locale }
    translations(locale: $locale) { key value locale outdated }
  }
}"""

REGISTER_MUTATION = """mutation RegisterThemeTranslations($resourceId: ID!, $translations: [TranslationInput!]!) {
  translationsRegister(resourceId: $resourceId, translations: $translations) {
    translations { key value locale }
    userErrors { code field message }
  }
}"""

#: Je Aufruf; mit 100 lief der Import im Feld ohne Fehler, eine Obergrenze nennt die Doku nicht.
BATCH = 100


class TranslationError(RuntimeError):
    pass


def read_resource(transport, theme_id, locale: str) -> dict:
    """Schlüssel, Werte, Digests und bestehende Übersetzungen des Themes, frisch gelesen."""
    gid = theme_gid(theme_id)
    resource = transport.execute(TRANSLATIONS_QUERY, {"resourceId": gid, "locale": locale}).get(
        "translatableResource")
    if not resource or resource.get("resourceId") != gid:
        raise TranslationError("Shopify liefert keine übersetzbare Ressource für dieses Theme")
    return resource


def pointer_parts(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise TranslationError(f"JSON-Pointer muss mit / beginnen: {pointer!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def resolve(document, parts: list[str]):
    for part in parts:
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def server_stem(filename: str, parts: list[str]) -> str | None:
    """Schlüssel ohne Hash-Endung für eine Einstellung in einem JSON-Template.

    Jede übergeordnete Block-ID bleibt erhalten; nie nur die Blatt-ID, weil
    dieselbe Block-ID in mehreren Sections vorkommen kann.
    """
    if not filename.startswith("templates/") or len(parts) < 4 or parts[0] != "sections":
        return None
    identifiers, position = [parts[1]], 2
    while position + 1 < len(parts) and parts[position] == "blocks":
        identifiers.append(parts[position + 1])
        position += 2
    if parts[position:] != ["settings", parts[-1]]:
        return None
    chain = ["__".join(identifiers[1:])] if len(identifiers) > 1 else []
    return ".".join(["section", filename[len("templates/"):], identifiers[0], *chain, parts[-1]])


def build_plan(entries: list[dict], resource: dict, locale: str, theme_dir=None) -> dict:
    """Ordnet jedem Eintrag genau einen Serverschlüssel zu, oder lässt ihn offen."""
    by_key, by_stem = {}, defaultdict(list)
    for content in resource.get("translatableContent") or []:
        if content["key"] in by_key:
            raise TranslationError(f"Schlüssel doppelt in der Antwort: {content['key']}")
        by_key[content["key"]] = content
        by_stem[content["key"].rsplit(":", 1)[0]].append(content)
    registered = {item["key"]: item for item in resource.get("translations") or []}
    cache: dict[str, object] = {}
    matched, existing, unresolved, used = [], [], [], set()
    for entry in entries:
        filename, pointer = entry["file"], entry["pointer"]
        identity = f"{filename}#{pointer}"
        parts = pointer_parts(pointer)
        if theme_dir is not None:
            if filename not in cache:
                cache[filename] = parse_json((Path(theme_dir) / filename).read_text(encoding="utf-8"))
            try:
                local = resolve(cache[filename], parts)
            except (KeyError, IndexError, ValueError):
                local = None
            if local != entry["source_value"]:
                unresolved.append({"target": identity, "reason": "source_value_differs_from_theme_dir"})
                continue
        if entry.get("key"):
            wanted = entry["key"]
            candidates = [by_key[wanted]] if wanted in by_key else list(by_stem.get(wanted, []))
            strategy = "reviewed_key"
        elif server_stem(filename, parts):
            candidates = list(by_stem.get(server_stem(filename, parts), []))
            strategy = "section_and_block_path"
        elif filename == "config/settings_data.json" and len(parts) == 2 and parts[0] == "current":
            field = parts[1]
            candidates = [c for stem, items in by_stem.items() if stem == field or stem.endswith("." + field)
                          for c in items]
            strategy = "theme_setting_id"
        else:
            candidates, strategy = [], "unsupported_pointer"
        candidates = [c for c in candidates if c.get("value") == entry["source_value"] and c.get("digest")
                      and c.get("locale") != locale]
        if len(candidates) != 1:
            unresolved.append({"target": identity, "reason": "no_unique_match", "strategy": strategy,
                               "candidates": len(candidates)})
            continue
        content = candidates[0]
        if content["key"] in used:
            raise TranslationError(f"mehrere Einträge zeigen auf denselben Schlüssel: {content['key']}")
        used.add(content["key"])
        item = {"target": identity, "key": content["key"], "value": entry["value"], "locale": locale,
                "translatableContentDigest": content["digest"], "strategy": strategy}
        current = registered.get(content["key"])
        if current and current.get("value") == entry["value"] and not current.get("outdated"):
            existing.append(item)
        else:
            matched.append(item)
    return {"status": "ready" if not unresolved else "needs_key_review", "matched": matched,
            "already_registered": existing, "unresolved": unresolved}


def register(transport, theme_id, items: list[dict], locale: str, draft_id) -> dict:
    """Registriert in Paketen, jedes unter dem Schutz; bei `userErrors` Halt."""
    gid = theme_gid(theme_id)
    done, errors = [], []
    for start in range(0, len(items), BATCH):
        batch = items[start:start + BATCH]
        before = live_fingerprint(transport)
        check_write_target(transport, theme_id, draft_id)
        payload = [{k: item[k] for k in ("key", "value", "locale", "translatableContentDigest")} for item in batch]
        data = transport.execute(REGISTER_MUTATION, {"resourceId": gid, "translations": payload}, mutation=True)
        result = data.get("translationsRegister") or {}
        if result.get("userErrors"):
            errors = result["userErrors"]
            break
        done += [item["key"] for item in batch]
        assert_live_unchanged(before, live_fingerprint(transport))
    return {"registered": done, "user_errors": errors}


def readback(transport, theme_id, items: list[dict], locale: str) -> dict:
    """Frisch lesen: jeder Schlüssel trägt den erwarteten Wert und ist nicht veraltet."""
    current = {t["key"]: t for t in read_resource(transport, theme_id, locale).get("translations") or []}
    ok, wrong = [], []
    for item in items:
        found = current.get(item["key"])
        if found and found.get("value") == item["value"] and not found.get("outdated"):
            ok.append(item["key"])
        else:
            wrong.append(item["key"])
    return {"equal": ok, "different": wrong, "checked": len(items)}


def run(config: dict, theme_id, source: dict, *, transport, theme_dir=None, dry_run: bool = False) -> tuple[dict, int]:
    draft = migration_config(config).get("draft_theme_id")
    check_write_target(transport, theme_id, draft)
    locale = source.get("locale")
    entries = source.get("entries")
    if not locale or not isinstance(entries, list):
        raise TranslationError("Quelldatei braucht locale und entries")
    resource = read_resource(transport, theme_id, locale)
    plan = build_plan(entries, resource, locale, theme_dir)
    report = {"command": "register", "theme_id": numeric_id(theme_id), "locale": locale, "entries": len(entries),
              "plan": plan}
    findings = []
    if plan["unresolved"]:
        findings.append({"rule": "unresolved", "message": f"{len(plan['unresolved'])} Einträge ohne eindeutigen "
                                                          "Schlüssel; nichts registriert"})
    elif plan["matched"] and not dry_run:
        result = register(transport, theme_id, plan["matched"], locale, draft)
        report["register"] = result
        if result["user_errors"]:
            findings.append({"rule": "user_errors", "message": "translationsRegister meldet Fehler",
                             "errors": result["user_errors"]})
        check = readback(transport, theme_id, plan["matched"] + plan["already_registered"], locale)
        report["readback"] = check
        if check["different"]:
            findings.append({"rule": "readback", "message": f"{len(check['equal'])} von {check['checked']} "
                                                            "Übersetzungen aktuell"})
    report["findings"] = findings
    return report, EXIT_FINDINGS if findings else EXIT_OK


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.translations", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="Theme-Übersetzungen am Entwurf registrieren")
    reg.add_argument("--theme", required=True)
    reg.add_argument("--source", required=True)
    reg.add_argument("--dir", help="Theme-Ordner; prüft, dass jeder Ausgangswert dort so steht")
    reg.add_argument("--dry-run", action="store_true", help="nur zuordnen, nichts registrieren")
    reg.add_argument("--workspace", default=".")
    reg.add_argument("--out")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(args.workspace) / "migration" / "upload" / f"{today()}-translations.json"
    try:
        config = load_config(args.workspace)
        source = json.loads(Path(args.source).read_text(encoding="utf-8"))
        if transport is None:
            transport = transport_from_config(config, write=True, workspace=args.workspace)
        report, code = run(config, args.theme, source, transport=transport, theme_dir=args.dir,
                           dry_run=args.dry_run)
    except (ConfigError, ShopifyError, GuardError, TranslationError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "command": args.command, "error": str(exc)})
        return EXIT_ERROR
    write_json(out, report)
    plan = report["plan"]
    emit({"ok": code == EXIT_OK, "command": "register", "out": str(out), "status": plan["status"],
          "matched": len(plan["matched"]), "existing": len(plan["already_registered"]),
          "unresolved": len(plan["unresolved"]), "registered": len(report.get("register", {}).get("registered", [])),
          "findings": len(report["findings"])})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
