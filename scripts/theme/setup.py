#!/usr/bin/env python3
"""Das Setup eines Stores als `setup.json` für das Cockpit.

Format: `reference/setup-format.md`. Das Cockpit zeigt je Store Theme, Tracking
und Einwilligung, Sprachen und Märkte und die Apps im Theme nebeneinander und
gegen den Referenz-Store der Marke. Es rechnet nichts selbst, deshalb trägt die
Datei fertige Zeilen, und dieses Modul prüft sie, bevor sie in einen Lauf geht.

Ein Lauf `reporting/runs/<datum>-setup/` hält `state.json` (`cadence: "setup"`)
und `setup.json`. `audit.publish` lädt nur `setup.json` hoch und gibt sie sofort
frei (entschieden am 12.10.2026). Ein zweiter Lauf am selben Tag überschreibt
den ersten.

Seit 0.3.15 trägt das Setup des Referenz-Stores optional `policy_questions`: Vorgaben der Marke, die noch
keine Regel haben. Das Cockpit zeigt sie im Setup auf der Karte "Vorgaben der Marke"; die Antworten holt die
Skill `theme-migration` beim Start über `get_setup` und trägt sie mit `theme.policies import` ein.

`from_shop_tech` baut die Live-Ansicht aus `shop-tech.json` (Skill
`pull-shopify-tech`): Theme, Tracking aus den inline gefundenen Kennungen,
Sprachen und Märkte, Apps aus den Hosts der Fremdskripte. Ohne Crawl im
Technik-Abzug sind Tracking und Apps nicht gemessen; dann entsteht kein Setup,
weil das Cockpit jede fehlende App als "nicht eingebunden" zeigen würde.

CLI:
    python3 -m theme.setup validate --path <setup.json>
    python3 -m theme.setup from-shop-tech --path <shop-tech.json> --shop <slug>
        [--reference-shop <slug>] [--source <text>] [--workspace <ws>]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, write_json
from theme.apps import DEFAULT_HOSTS, HostCatalog
from theme.limits import MAX_THEMES

SCHEMA = 1
FILE_NAME = "setup.json"
VIEWS = ("live", "draft")
#: Feste Gruppenschlüssel, in der Reihenfolge, in der das Cockpit sie zeigt.
GROUPS = ("theme", "tracking", "languages", "apps", "features")
POLICY_KINDS = ("gap", "decide", "allowed")
#: Die zwei Antworten einer Vorgabe im Cockpit, in dieser Reihenfolge: `options[0]` heißt in `policies.json`
#: `may_differ`, `options[1]` heißt `same_as_reference` (Vertrag V14).
POLICY_OPTIONS = 2
DEFAULT_SOURCE = "aus dem Technik-Abzug des Shops"

#: Kennungen, die `crawl-site` inline im Quelltext findet, je Zeile der Gruppe Tracking.
TRACKERS = (
    ("ga4", "Google Analytics 4", "G-"),
    ("google_ads", "Google Ads", "AW-"),
    ("tag_manager", "Google Tag Manager", "GTM-"),
)
#: Kategorien aus `hosts.json`, die keine App sind: die Plattform selbst, Schriften und Bibliotheken.
NOT_APP_CATEGORIES = ("shopify", "fonts", "cdn_library")


class SetupError(ValueError):
    """Ein Setup, das so nicht ins Cockpit darf."""


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso(value) -> bool:
    if not _text(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_row(row, where: str, group_key: str, view: str, seen: set) -> list[str]:
    if not isinstance(row, dict):
        return [f"{where}: kein Objekt"]
    errors = []
    for field in ("key", "label"):
        if not _text(row.get(field)):
            errors.append(f"{where}: {field} fehlt")
    if not isinstance(row.get("value"), str):
        errors.append(f"{where}: value fehlt oder ist kein Text")
    for field in ("note", "hint"):
        if row.get(field) is not None and not isinstance(row[field], str):
            errors.append(f"{where}: {field} ist kein Text")
    if "compare" in row and not isinstance(row["compare"], bool):
        errors.append(f"{where}: compare ist nicht true oder false")
    if "present" in row:
        if not isinstance(row["present"], bool):
            errors.append(f"{where}: present ist nicht true oder false")
        if group_key != "apps":
            errors.append(f"{where}: present gibt es nur bei Apps")
    key = row.get("key")
    if _text(key):
        if group_key == "apps" and not key.startswith("app:"):
            errors.append(f"{where}: eine App heißt app:<handle>, nicht {key!r}")
        if key in seen:
            errors.append(f"{where}: Schlüssel {key!r} steht zweimal in der Ansicht {view}")
        seen.add(key)
    policy = row.get("policy")
    if policy is not None:
        if view != "draft":
            errors.append(f"{where}: policy gibt es nur im Entwurf")
        if not isinstance(policy, dict):
            errors.append(f"{where}: policy ist kein Objekt")
        else:
            if policy.get("kind") not in POLICY_KINDS:
                errors.append(f"{where}: policy.kind ist {policy.get('kind')!r}, erlaubt sind {', '.join(POLICY_KINDS)}")
            if not _text(policy.get("text")):
                errors.append(f"{where}: policy.text fehlt")
    return errors


def _validate_view(view_data, view: str) -> list[str]:
    where = f"views.{view}"
    if not isinstance(view_data, dict):
        return [f"{where}: kein Objekt"]
    errors = []
    theme = view_data.get("theme")
    if not isinstance(theme, dict) or not _text(theme.get("name")):
        errors.append(f"{where}.theme: name fehlt")
    else:
        for field in ("version", "id"):
            if theme.get(field) is not None and not isinstance(theme[field], str):
                errors.append(f"{where}.theme: {field} ist kein Text")
    groups = view_data.get("groups")
    if not isinstance(groups, list):
        return errors + [f"{where}.groups: fehlt oder ist keine Liste"]
    seen_groups, seen_rows = set(), set()
    for g, group in enumerate(groups):
        gwhere = f"{where}.groups[{g}]"
        if not isinstance(group, dict):
            errors.append(f"{gwhere}: kein Objekt")
            continue
        key = group.get("key")
        if key not in GROUPS:
            errors.append(f"{gwhere}: key ist {key!r}, erlaubt sind {', '.join(GROUPS)}")
        elif key in seen_groups:
            errors.append(f"{gwhere}: Gruppe {key!r} steht zweimal in der Ansicht {view}")
        seen_groups.add(key)
        if not _text(group.get("label")):
            errors.append(f"{gwhere}: label fehlt")
        rows = group.get("rows")
        if not isinstance(rows, list):
            errors.append(f"{gwhere}.rows: fehlt oder ist keine Liste")
            continue
        for r, row in enumerate(rows):
            errors += _validate_row(row, f"{gwhere}.rows[{r}]", key, view, seen_rows)
    return errors


def _validate_policy_question(question, where: str, seen: set) -> list[str]:
    if not isinstance(question, dict):
        return [f"{where}: kein Objekt"]
    errors = []
    for field in ("key", "text", "context", "reason"):
        if not _text(question.get(field)):
            errors.append(f"{where}: {field} fehlt")
    key = question.get("key")
    if _text(key):
        if key in seen:
            errors.append(f"{where}: Schlüssel {key!r} steht zweimal")
        seen.add(key)
    if question.get("subject") is not None and not _text(question["subject"]):
        errors.append(f"{where}: subject ist kein Text")
    options = question.get("options")
    options_ok = (isinstance(options, list) and len(options) == POLICY_OPTIONS and all(_text(o) for o in options)
                  and options[0].strip() != options[1].strip())
    if not options_ok:
        # Die Reihenfolge trägt die Bedeutung, deshalb genau zwei und nie gleich.
        errors.append(f"{where}: options braucht genau zwei verschiedene Antworten, zuerst die Abweichung "
                      "(may_differ), dann die Angleichung an den Referenz-Store (same_as_reference)")
    if "recommendation" not in question:
        errors.append(f"{where}: recommendation fehlt (null heißt ausdrücklich keine Empfehlung)")
    elif question["recommendation"] is not None and (not options_ok or question["recommendation"] not in options):
        errors.append(f"{where}: recommendation {question['recommendation']!r} ist keine der options")
    app = question.get("app")
    if app is not None and not (_text(app) and app.startswith("app:") and len(app.strip()) > len("app:")):
        errors.append(f"{where}: app heißt app:<handle> wie die Zeile im Setup, nicht {app!r}")
    return errors


def _validate_policy_questions(data: dict) -> list[str]:
    questions = data["policy_questions"]
    if not isinstance(questions, list):
        return ["policy_questions ist keine Liste"]
    errors = []
    # Die Vorgaben gelten für alle Stores der Marke; das Cockpit liest sie aus dem Setup des Referenz-Stores.
    if not _text(data.get("reference_shop")) or data.get("reference_shop") != data.get("shop"):
        errors.append("policy_questions gibt es nur im Setup des Referenz-Stores (shop gleich reference_shop)")
    seen: set = set()
    for index, question in enumerate(questions):
        errors += _validate_policy_question(question, f"policy_questions[{index}]", seen)
    return errors


def validate(data) -> list[str]:
    """Die Fehler eines Setups gegen `reference/setup-format.md`, leer, wenn es passt."""
    if not isinstance(data, dict):
        return ["setup.json ist kein JSON-Objekt"]
    errors = []
    if data.get("schema") != SCHEMA:
        errors.append(f"schema ist {data.get('schema')!r}, erwartet {SCHEMA}")
    for field in ("shop", "source"):
        if not _text(data.get(field)):
            errors.append(f"{field} fehlt")
    if not _iso(data.get("collected_at")):
        errors.append("collected_at fehlt oder ist kein Zeitpunkt nach ISO 8601")
    if data.get("reference_shop") is not None and not isinstance(data["reference_shop"], str):
        errors.append("reference_shop ist kein Text")
    if "automatic" in data and not isinstance(data["automatic"], bool):
        errors.append("automatic ist nicht true oder false")
    if data.get("policy_questions") is not None:
        errors += _validate_policy_questions(data)
    views = data.get("views")
    if not isinstance(views, dict):
        return errors + ["views fehlt"]
    if "live" not in views:
        errors.append("views.live fehlt: das Setup des Live-Themes ist immer da")
    for name in views:
        if name not in VIEWS:
            errors.append(f"views.{name}: unbekannte Ansicht, erlaubt sind {', '.join(VIEWS)}")
            continue
        errors += _validate_view(views[name], name)
    return errors


def run_id_for(today: date | None = None) -> str:
    return f"{(today or date.today()).isoformat()}-setup"


def write_run(workspace, data: dict, run_id: str | None = None, today: date | None = None) -> Path:
    """Legt den Lauf `reporting/runs/<datum>-setup/` an und gibt seinen Ordner zurück.

    Geprüft wird vorher: ein ungültiges Setup landet nie in einem Lauf. Derselbe
    Tag überschreibt den Lauf, denn im Cockpit gibt es je Store eine lebende Fassung.
    """
    errors = validate(data)
    if errors:
        raise SetupError("setup.json passt nicht zum Format:\n  " + "\n  ".join(errors))
    run_id = run_id or run_id_for(today)
    run_dir = Path(workspace) / "reporting" / "runs" / run_id
    write_json(run_dir / "state.json", {"run_id": run_id, "cadence": "setup", "title": "Setup"})
    write_json(run_dir / FILE_NAME, data)
    return run_dir


def _unread(shop_tech: dict, block: str) -> bool:
    """Ob `shop_tech_build` einen Block als nicht gelesen vermerkt hat (fehlend ist nicht leer)."""
    return any(f"Block {block!r}" in str(note) for note in shop_tech.get("notes") or [])


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _theme_group(shop_tech: dict) -> tuple[dict, dict]:
    live = shop_tech.get("theme") or {}
    if not _text(live.get("name")):
        raise SetupError("shop-tech.json nennt kein Live-Theme (Block themes nicht gelesen?). "
                         "Ohne Live-Theme kein Setup.")
    updated = live.get("updated_at")
    slots = len(shop_tech.get("themes") or [])
    rows = [
        {"key": "theme", "label": "Theme", "value": live["name"],
         "note": f"zuletzt geändert {str(updated)[:10]}" if updated else None},
        {"key": "theme_slots", "label": "Theme-Plätze", "value": f"{slots} von {MAX_THEMES} belegt",
         "compare": False},
    ]
    return ({"name": live["name"], "version": None, "id": None},
            {"key": "theme", "label": "Theme", "rows": [_clean(r) for r in rows]})


def _tracking_group(shop_tech: dict) -> dict:
    tag_ids = shop_tech.get("storefront_inline_tag_ids") or {}
    pages = (shop_tech.get("summary") or {}).get("crawl_pages_scanned")
    rows = []
    for key, label, prefix in TRACKERS:
        found = sorted(((tid, n) for tid, n in tag_ids.items() if tid.startswith(prefix)),
                       key=lambda kv: (-kv[1], kv[0]))
        if not found:
            # Gesucht wird nur inline im Quelltext. Über den Tag Manager oder ein externes Skript
            # geladen findet der Crawl die Kennung nicht, deshalb kein "nicht eingebunden".
            value = "keine Kennung im Quelltext"
            note = "über den Tag Manager oder ein externes Skript geladen ist möglich"
        else:
            value = "eingebunden" if len(found) == 1 else f"{len(found)} Kennungen"
            note = "; ".join(f"{tid} auf {n} von {pages} Seiten" if pages else f"{tid} auf {n} Seiten"
                             for tid, n in found)
        rows.append({"key": key, "label": label, "value": value, "note": note})
    return {"key": "tracking", "label": "Tracking und Einwilligung", "rows": rows}


def _languages_group(shop_tech: dict) -> dict:
    rows = []
    if _unread(shop_tech, "shopLocales"):
        rows.append({"key": "languages", "label": "Sprachen", "value": "nicht gelesen", "compare": False,
                     "note": "Sprachen in shop-tech.json nicht gelesen"})
    else:
        locales = [l for l in shop_tech.get("locales") or [] if isinstance(l, dict) and l.get("locale")]
        published = sorted((l for l in locales if l.get("published")),
                           key=lambda l: (not l.get("primary"), l["locale"]))
        hidden = len(locales) - len(published)
        rows.append({"key": "languages", "label": "Sprachen",
                     "value": ", ".join(l["locale"] for l in published) or "keine veröffentlicht",
                     "note": f"{_count(hidden, 'Sprache', 'Sprachen')} nicht veröffentlicht" if hidden else None})
    if _unread(shop_tech, "markets"):
        rows.append({"key": "markets", "label": "Märkte", "value": "nicht gelesen", "compare": False,
                     "note": "Märkte in shop-tech.json nicht gelesen"})
    else:
        markets = [m for m in shop_tech.get("markets") or [] if isinstance(m, dict)]
        # `enabled` fehlt in neueren API-Fassungen; ohne Angabe zählt ein Markt als aktiv.
        active = [m for m in markets if m.get("enabled") is not False]
        inactive = len(markets) - len(active)
        rows.append({"key": "markets", "label": "Märkte", "value": str(len(active)), "compare": False,
                     "note": f"{inactive} weitere angelegt, nicht aktiv" if inactive else None})
    return {"key": "languages", "label": "Sprachen und Märkte", "rows": [_clean(r) for r in rows]}


def _apps_group(shop_tech: dict, hosts) -> dict:
    if isinstance(hosts, dict):
        catalog = HostCatalog(hosts)
    else:
        catalog = HostCatalog.load(hosts or DEFAULT_HOSTS)
    by_service: dict[str, list[str]] = {}
    for host in shop_tech.get("storefront_script_hosts") or {}:
        if catalog.ignored(host):
            continue
        sid = catalog.service_for(host)
        if not sid or catalog.is_platform(sid):
            continue
        if catalog.services[sid].get("category") in NOT_APP_CATEGORIES:
            continue
        by_service.setdefault(sid, []).append(host)
    rows = []
    for sid, found in by_service.items():
        service = catalog.services[sid]
        rows.append({"key": f"app:{sid}", "label": service["name"],
                     "hint": catalog.categories.get(service.get("category")) or None,
                     "value": "eingebunden", "present": True,
                     "note": "Skript von " + ", ".join(sorted(found))})
    rows.sort(key=lambda r: r["label"].lower())
    return {"key": "apps", "label": "Apps im Theme", "rows": [_clean(r) for r in rows]}


def _clean(row: dict) -> dict:
    """Ohne leere Felder: `note: null` sagt dem Cockpit nichts."""
    return {k: v for k, v in row.items() if v is not None}


def from_shop_tech(shop_tech: dict, *, shop: str, reference_shop: str | None = None,
                   source: str = DEFAULT_SOURCE, collected_at: str, hosts=None) -> dict:
    """Ein Setup mit der Live-Ansicht aus `shop-tech.json`.

    `hosts` ist `hosts.json` als Pfad oder schon gelesen, Standard der Katalog im
    Plugin. Ein Host ohne Treffer im Katalog bleibt weg: er ist keine benennbare
    App. Hat `pull-shopify-tech` mehr als 100 Hosts gekappt, fehlen die seltensten.
    """
    if not isinstance(shop_tech, dict):
        raise SetupError("shop-tech.json ist kein JSON-Objekt")
    # Ohne gecrawlte Seite ist "nicht gefunden" keine Messung, sondern eine Lücke.
    if not (shop_tech.get("summary") or {}).get("crawl_pages_scanned"):
        raise SetupError("shop-tech.json ohne Crawl: Tracking und Apps sind nicht gemessen. "
                         "pull-shopify-tech mit --crawl laufen lassen.")
    theme, theme_group = _theme_group(shop_tech)
    return {
        "schema": SCHEMA,
        "shop": shop,
        "reference_shop": reference_shop or None,
        "collected_at": collected_at,
        "source": source,
        "automatic": False,
        "views": {"live": {"theme": theme, "groups": [
            theme_group, _tracking_group(shop_tech), _languages_group(shop_tech), _apps_group(shop_tech, hosts),
        ]}},
    }


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SetupError(f"{path} fehlt") from exc
    except ValueError as exc:
        raise SetupError(f"{path} ist kein gültiges JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.setup", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="setup.json gegen das Format prüfen")
    check.add_argument("--path", required=True)
    build = sub.add_parser("from-shop-tech", help="Setup aus shop-tech.json als Lauf schreiben")
    build.add_argument("--path", required=True, help="shop-tech.json aus pull-shopify-tech")
    build.add_argument("--shop", required=True, help="Slug des Stores wie im Cockpit")
    build.add_argument("--reference-shop", help="Referenz-Store der Marke; Standard reference_shop der Config")
    build.add_argument("--source", default=DEFAULT_SOURCE, help="woraus erhoben, in Worten")
    build.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            errors = validate(_read_json(args.path))
            emit({"path": args.path, "valid": not errors, "errors": errors})
            return EXIT_FINDINGS if errors else EXIT_OK
        path = Path(args.path)
        reference = args.reference_shop
        if reference is None:
            try:
                reference = load_config(args.workspace).get("reference_shop")
            except ConfigError:
                reference = None
        # Erhoben wurde, als der Technik-Abzug entstand, nicht jetzt.
        collected = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) if path.is_file() else None
        data = from_shop_tech(_read_json(path), shop=args.shop, reference_shop=reference, source=args.source,
                              collected_at=(collected or datetime.now(timezone.utc)).isoformat(timespec="seconds"))
        run_dir = write_run(args.workspace, data)
    except SetupError as error:
        emit({"error": str(error)})
        return EXIT_ERROR
    rows = sum(len(g["rows"]) for g in data["views"]["live"]["groups"])
    emit({"run_id": run_dir.name, "path": str(run_dir / FILE_NAME), "rows": rows})
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
