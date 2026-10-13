#!/usr/bin/env python3
"""Vorgaben einer Marke für alle ihre Stores: einmal entschieden, in jedem Lauf gleich angewendet.

Eingeführt mit 0.3.11. Vorher kamen Entscheidungen, die alle Stores einer Marke betreffen (Cookie-Banner, Tracking,
Apps), nur als eingefügter Prompt in einzelne Sitzungen. Ein Entwurf nach dem anderen trug danach etwas anderes
ein, und niemand sah, welcher Stand wo galt.

Die Datei `policies.json` liegt nicht im Plugin, sondern beim Betreiber im Workspace der Marke. Format in
`reference/theme-migration/policies-format.md`. Je Merkmal eine Regel:

- `same_as_reference`: wie im Referenz-Store der Marke; mit `keep` und `drop` (Dienst-IDs aus `apps.json`).
  Ein Eintrag ist eine ID oder eine Liste von Schreibweisen desselben Dienstes, weil die Inventare der Stores
  einer Marke denselben Dienst verschieden benennen (`cookiefirst`, `app:cookiefirst-cookie-consent`).
- `open`: noch nicht entschieden; hält die Vorbereitung nicht an, steht im Cockpit als Entscheidung beim Betreiber
- `may_differ`: darf je Store abweichen

`apply` schreibt eine Kopie nach `migration/policies.json` im Repo des Stores, die Entscheidungen nach
`migration/mapping/decisions.json` (`source: policy`, ersetzt ältere) und nach `apps.json`, damit der Generator
sie beim nächsten Neubau liest. Ein Dienst, der beibehalten werden soll, aber im Inventar fehlt, wird ein Punkt
`blocker` in der Liste offener Punkte: er muss vor der Testrunde eingebaut sein. Der Betreiber committet und
pusht; das Team zieht den Stand mit dem Repo. Eine Vorgabe öffnet nie eine Frage an das Team.

Seit 0.3.15 entscheidet die Marke eine Vorgabe ohne Regel auch selbst, im Setup des Cockpits (Karte "Vorgaben der
Marke", Fragen aus `policy_questions` im Setup des Referenz-Stores). `import` übernimmt diese Antworten aus
`get_setup` in `policies.json`: `options[0]` heißt `may_differ`, `options[1]` `same_as_reference` mit dem Ziel
"wie im Referenz-Store". Nennt die Frage eine App (`app:<handle>`), behält die angeglichene Regel sie
(`keep`), und `apply` legt in jedem Store ohne die App einen Punkt zum Einbauen an. Die Regel trägt danach
selbst `decided_by` und `decided_at`, die Datei eine neue Version.
Entscheiden dürfen alle Mitglieder der Marke; das Plugin kennt sie nicht, und das Cockpit lässt nur Mitglieder
antworten. Deshalb gilt jede Antwort aus dem Cockpit, und ihr Name steht an der Regel.

Aufruf:
    python3 -m theme.policies apply --source <policies.json> [--workspace <ws>]
    python3 -m theme.policies check [--source <policies.json>] [--workspace <ws>]
    python3 -m theme.policies import --brand-workspace <ordner mit policies.json> --file <antworten.json | ->
        [--workspace <ws>]
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from theme import ConfigError, load_config

RULES = ("same_as_reference", "open", "may_differ")
#: Die Regel je Antwort einer Vorgabe im Cockpit, in der Reihenfolge von `options` (Vertrag V14).
OPTION_RULES = ("may_differ", "same_as_reference")
#: Das Ziel einer Regel, die das Team im Cockpit an den Referenz-Store angleicht.
REFERENCE_TARGET = "wie im Referenz-Store"
#: Die Knöpfe im Cockpit, falls eine Antwort ihre `options` nicht mitbringt.
MAY_DIFFER_LABEL = "Abweichung erlauben"
ALIGN_LABEL = re.compile(r"^An .+ angleichen$")
#: Version einer Fassung: Datum und laufende Nummer am Tag, etwa `2026-01-05.1`.
VERSION = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(\d+)$")


class PolicyError(Exception):
    """Vorgaben, die so nicht gelten."""


def copy_path(workspace) -> Path:
    return Path(workspace) / "migration" / "policies.json"


def decisions_path(workspace) -> Path:
    return Path(workspace) / "migration" / "mapping" / "decisions.json"


def apps_path(workspace) -> Path:
    return Path(workspace) / "migration" / "inventory" / "apps.json"


def _read(path: Path, default=None):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PolicyError(f"{path} ist kein gültiges JSON ({error}).") from error


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def validate(data) -> list:
    """Fehler im Format, leer, wenn alles gilt."""
    if not isinstance(data, dict):
        return ["policies.json muss ein JSON-Objekt sein"]
    errors = []
    for key in ("version", "decided_by", "decided_at"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            errors.append(f"{key} fehlt")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        return errors + ["rules muss eine nicht leere Liste sein"]
    seen = set()
    for index, rule in enumerate(rules):
        where = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{where} muss ein Objekt sein")
            continue
        key = rule.get("key")
        if not isinstance(key, str) or not key.strip():
            errors.append(f"{where}.key fehlt")
        elif key in seen:
            errors.append(f"{where}.key {key!r} doppelt")
        seen.add(key)
        if rule.get("rule") not in RULES:
            errors.append(f"{where}.rule muss eines von {RULES} sein")
        for field in ("keep", "drop"):
            value = rule.get(field, [])
            if not isinstance(value, list) or not all(
                    (isinstance(v, str) and v) or (isinstance(v, list) and v and all(isinstance(a, str) and a for a in v))
                    for v in value):
                errors.append(f"{where}.{field} muss eine Liste von Dienst-IDs oder Listen von Schreibweisen sein")
        if rule.get("rule") != "same_as_reference" and (rule.get("keep") or rule.get("drop")):
            errors.append(f"{where}: keep und drop nur bei same_as_reference")
        for field in ("decided_by", "decided_at"):
            if field in rule and (not isinstance(rule[field], str) or not rule[field].strip()):
                errors.append(f"{where}.{field} ist leer")
    return errors


def load_source(path) -> dict:
    data = _read(Path(path))
    if data is None:
        raise PolicyError(f"{path} fehlt.")
    errors = validate(data)
    if errors:
        raise PolicyError("policies.json gilt so nicht: " + "; ".join(errors))
    return data


def _decisions(workspace) -> tuple:
    """Entscheidungen als Liste und eine Funktion, die sie in der ursprünglichen Form zurückschreibt."""
    data = _read(decisions_path(workspace), default={"decisions": []})
    if isinstance(data, list):
        return data, lambda items: items
    if isinstance(data, dict) and isinstance(data.get("decisions"), list):
        return data["decisions"], lambda items: {**data, "decisions": items}
    raise PolicyError(f"{decisions_path(workspace)} hat eine unbekannte Form.")


def _decide(decisions: list, rule: dict, decision: str, service_id: str, version: str, source: dict) -> str | None:
    """Hängt eine Entscheidung aus der Vorgabe an. Gibt ihre ID zurück, `None`, wenn es sie schon gibt."""
    ident = f"policy-{version}-{rule['key']}-{service_id}"
    if any(d.get("id") == ident for d in decisions):
        return None
    earlier = [d["id"] for d in decisions
               if d.get("service_id") == service_id and d.get("id")
               and not any(d["id"] in (e.get("replaces") or []) for e in decisions)]
    decisions.append({"id": ident, "subject": rule.get("subject") or rule["key"],
                      "kind": "app" if service_id.startswith("app:") else "service", "decision": decision,
                      "reason": f"Vorgabe der Marke, Version {version}: {rule.get('target') or rule.get('note') or decision}",
                      # Eine im Cockpit entschiedene Regel trägt ihre Person selbst, sonst gilt die der Datei.
                      "decided_by": rule.get("decided_by") or source["decided_by"],
                      "decided_at": rule.get("decided_at") or source["decided_at"],
                      "source": "policy", "service_id": service_id, "replaces": earlier})
    return ident


def apply(workspace, source: dict, now: datetime | None = None) -> dict:
    """Wendet die Vorgaben auf den Lauf eines Stores an. Gleiche Version zweimal ändert nichts.

    Auch `applied_at` bleibt dann stehen: Schritt 3 verlangt einen Neubau nach `applied_at`, und der Start jeder
    Sitzung wendet die Vorgaben an. Mit neuem Zeitpunkt stünde der Neubau nach jedem Start auf nacharbeiten.
    """
    from theme import open_items  # erst hier, damit der Import der Schritte leicht bleibt

    version = source["version"]
    previous = _read(copy_path(workspace), default=None)
    unchanged = (isinstance(previous, dict) and previous.get("version") == version
                 and isinstance(previous.get("applied_at"), str) and bool(previous["applied_at"]))
    stamp = previous["applied_at"] if unchanged else (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    decisions, wrap = _decisions(workspace)
    apps = _read(apps_path(workspace), default=None)
    services = {s.get("service_id"): s for s in (apps or {}).get("services") or [] if isinstance(s, dict)}
    added, replaced, missing = [], [], []
    for rule in source["rules"]:
        if rule["rule"] != "same_as_reference":
            continue
        for decision, entries in (("keep", rule.get("keep", [])), ("drop", rule.get("drop", []))):
            for entry_ids in entries:
                aliases = [entry_ids] if isinstance(entry_ids, str) else list(entry_ids)
                present = [a for a in aliases if a in services]
                # Ein Dienst, den der Store nicht hat: beim Streichen nichts zu tun, beim Behalten ein Punkt zum
                # Einbauen, und die Entscheidung gilt für die erste Schreibweise.
                if not present and decision == "drop":
                    continue
                for service_id in present or aliases[:1]:
                    added_id = _decide(decisions, rule, decision, service_id, version, source)
                    if added_id:
                        added.append(added_id)
                        replaced += next(d for d in decisions if d["id"] == added_id)["replaces"]
                    if service_id in services:
                        services[service_id].update({"decision": decision, "decision_source": "policy",
                                                     "policy_version": version})
                if not present and decision == "keep":
                    missing.append((rule, aliases[0]))
    _write(decisions_path(workspace), wrap(decisions))
    if apps is not None:
        _write(apps_path(workspace), apps)
    items_added = []
    if missing:
        items = open_items.load(workspace) if open_items.exists(workspace) else open_items.new(workspace)
        for rule, service_id in missing:
            ident = f"POLICY-{rule['key']}-{service_id.split(':')[-1]}"[:60]
            if any(i["id"] == ident for i in items.items):
                continue
            items.add(title=f"Vorgabe {rule.get('subject') or rule['key']}: {rule.get('target') or service_id} einbauen",
                      ident=ident, severity="blocker", source="policy",
                      description=f"Vorgabe der Marke, Version {version}. {service_id} fehlt im Inventar dieses Stores "
                                  "und muss vor der Testrunde eingebunden sein.")
            items_added.append(ident)
        items.save()
    copy = {**source, "applied_at": stamp}
    _write(copy_path(workspace), copy)
    return {"version": version, "applied_at": stamp, "unchanged": unchanged, "decisions_added": added,
            "decisions_replaced": replaced, "open_items_added": items_added,
            "open_rules": [r["key"] for r in source["rules"] if r["rule"] == "open"]}


def status(workspace) -> dict:
    """Was die Schritte über die Vorgaben wissen müssen."""
    copy = _read(copy_path(workspace), default=None)
    try:
        config = load_config(workspace)
    except ConfigError:
        config = {}
    portal = config.get("portal") if isinstance(config.get("portal"), dict) else {}
    required = bool(copy) or bool(portal.get("brand"))
    if not copy:
        return {"required": required, "applied": False, "version": None, "applied_at": None, "open_rules": []}
    return {"required": True, "applied": True, "version": copy.get("version"), "applied_at": copy.get("applied_at"),
            "open_rules": [{"key": r["key"], "subject": r.get("subject") or r["key"], "note": r.get("note", "")}
                           for r in copy.get("rules") or [] if r.get("rule") == "open"]}


def check(workspace, source: dict | None = None) -> dict:
    current = status(workspace)
    result = {**current, "current": current["applied"]}
    if source is not None:
        result["source_version"] = source["version"]
        result["current"] = current["applied"] and current["version"] == source["version"]
    return result


def source_path(brand_workspace) -> Path:
    """`policies.json` im Ordner der Marke, der sie führt."""
    return Path(brand_workspace) / "policies.json"


def next_version(current, today: date) -> str:
    """Die Version nach `current`: heute mit der nächsten Nummer, an einem neuen Tag `.1`.

    Nie kleiner als die bestehende: liegt ihr Datum nach heute (andere Zeitzone), zählt dort weiter.
    """
    match = VERSION.match(current or "")
    day = today.isoformat()
    if match and match.group(1) >= day:
        return f"{match.group(1)}.{int(match.group(2)) + 1}"
    return f"{day}.1"


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _stamp(value, now: datetime) -> str:
    """Zeitpunkt der Antwort aus dem Cockpit, wenn lesbar, sonst jetzt."""
    if isinstance(value, str) and value.strip():
        try:
            return _instant(value).isoformat(timespec="seconds")
        except ValueError:
            pass
    return now.isoformat(timespec="seconds")


def _later(at: str, decided) -> bool:
    """Ob eine Antwort nach der Entscheidung im Repo liegt. Ein Datum ohne Uhrzeit gilt für den ganzen Tag."""
    if not isinstance(decided, str) or not decided.strip():
        return True
    decided = decided.strip()
    if len(decided) == len("2026-01-05"):
        return at[:10] > decided
    try:
        return _instant(at) > _instant(decided)
    except ValueError:
        return True


def _rule_for(entry: dict, value: str) -> str:
    """Die Regel zu einer Antwort: nach ihrer Stelle in `options`, ohne `options` nach den Knöpfen des Cockpits."""
    options = entry.get("options")
    if options is not None:
        labels = [o.strip() for o in options if isinstance(o, str) and o.strip()] if isinstance(options, list) else []
        if len(labels) != len(OPTION_RULES) or labels[0] == labels[1]:
            raise PolicyError(f"options braucht genau zwei verschiedene Antworten wie in policy_questions: {options!r}")
        if value not in labels:
            raise PolicyError(f"{value!r} ist keine der Antworten ({', '.join(labels)}).")
        return OPTION_RULES[labels.index(value)]
    if value == MAY_DIFFER_LABEL:
        return "may_differ"
    if ALIGN_LABEL.match(value):
        return "same_as_reference"
    raise PolicyError(f"{value!r} ist weder {MAY_DIFFER_LABEL!r} noch \"An <Referenz-Store> angleichen\"; "
                      "options aus get_setup mitgeben.")


def _app_of(entry: dict) -> str | None:
    """Die App der Frage als Zeilenschlüssel `app:<handle>`, `None` ohne App."""
    app = entry.get("app")
    if app is None or (isinstance(app, str) and not app.strip()):
        return None
    if not isinstance(app, str) or not app.strip().startswith("app:") or len(app.strip()) <= len("app:"):
        raise PolicyError(f"app heißt app:<handle> wie die Zeile im Setup, nicht {app!r}.")
    return app.strip()


def _set_rule(rule: dict, new_rule: str, by: str, at: str, app: str | None = None) -> None:
    """Setzt die Regel und wer sie wann entschieden hat; räumt auf, was zur neuen Regel nicht passt.

    Eine angeglichene Regel mit App behält die App unter beiden Schreibweisen, die Inventare der Stores
    kennen (`app:<handle>` und `<handle>`). Fehlt sie im Inventar eines Stores, macht `apply` daraus einen
    Punkt `blocker` zum Einbauen.
    """
    rule["rule"] = new_rule
    if new_rule == "same_as_reference":
        rule.setdefault("target", REFERENCE_TARGET)
        if app:
            spellings = [app, app[len("app:"):]]
            keep = rule.setdefault("keep", [])
            known = {a for e in keep for a in ([e] if isinstance(e, str) else e)}
            if not known.intersection(spellings):
                keep.append(spellings)
    else:
        # Ziel, keep und drop gibt es nur bei same_as_reference; das Cockpit zeigte sonst "bis zum Launch: …".
        for field in ("target", "keep", "drop"):
            rule.pop(field, None)
    rule["decided_by"], rule["decided_at"] = by, at


def import_answers(brand_workspace, entries, workspace=None, now: datetime | None = None) -> dict:
    """Trägt Antworten aus dem Cockpit in `policies.json` ein, `[{"key", "value", "by", "at"}]` aus `get_setup`.

    Je Antwort: Regel anlegen oder ändern, mit `decided_by` und `decided_at` an der Regel. Die neueste Antwort im
    Cockpit gilt, auch gegen eine frühere aus dem Cockpit; gegen eine Regel, die im Repo später entschieden wurde,
    nicht. Eine Antwort, die schon so gilt, steht unter `unchanged`. Hat sich etwas geändert, bekommt die Datei eine
    neue Version. `apply_needed` nennt die Stores, deren Kopie nicht auf dieser Version steht.
    """
    target = source_path(brand_workspace)
    source = load_source(target)
    if not isinstance(entries, list):
        raise PolicyError('Erwartet eine Liste [{"key", "value", "by", "at"}] aus get_setup.')
    now = now or datetime.now(timezone.utc)
    rules = {r["key"]: r for r in source["rules"]}
    imported, unchanged, skipped = [], [], []
    for entry in entries:
        entry = entry if isinstance(entry, dict) else {}
        key = str(entry.get("key") or "").strip()
        by = str(entry.get("by") or "").strip()
        value = str(entry.get("value") or "").strip()
        try:
            if not key:
                raise PolicyError("Antwort ohne key.")
            if not value:
                raise PolicyError(f"Antwort zu {key} ohne value.")
            if not by:
                raise PolicyError(f"Antwort zu {key} ohne Namen (by); eine Vorgabe trägt die Person, die entschied.")
            new_rule = _rule_for(entry, value)
            app = _app_of(entry)
            at = _stamp(entry.get("at"), now)
            rule = rules.get(key)
            if rule is not None and rule["rule"] == new_rule:
                unchanged.append({"key": key, "rule": new_rule, "value": value, "by": by})
                continue
            if rule is not None and rule["rule"] != "open" and not _later(
                    at, rule.get("decided_at") or source.get("decided_at")):
                raise PolicyError(f"Vorgabe {key} ist im Repo später entschieden ({rule['rule']}, "
                                  f"{rule.get('decided_by') or source.get('decided_by')}); die Regel dort gilt.")
        except PolicyError as error:
            skipped.append({"key": key or None, "by": by or None, "reason": str(error)})
            continue
        previous = rule["rule"] if rule is not None else None
        if rule is None:
            subject = str(entry.get("subject") or "").strip() or key
            rule = {"key": key, "subject": subject}
            source["rules"].append(rule)
            rules[key] = rule
        _set_rule(rule, new_rule, by, at, app)
        imported.append({"key": key, "rule": new_rule, "previous": previous, "value": value, "by": by, "at": at,
                         "app": app})
    previous_version = source["version"]
    if imported:
        source["version"] = next_version(previous_version, now.date())
        errors = validate(source)
        if errors:
            raise PolicyError("policies.json gälte danach so nicht: " + "; ".join(errors))
        _write(target, source)
    return {"path": str(target), "version": source["version"], "previous_version": previous_version,
            "imported": imported, "unchanged": unchanged, "skipped": skipped,
            "still_open": [{"key": r["key"], "subject": r.get("subject") or r["key"]}
                           for r in source["rules"] if r["rule"] == "open"],
            "apply_needed": stores_needing_apply(brand_workspace, source, workspace)}


def _shop_of(workspace: Path) -> str:
    """Der Store im Cockpit (`portal.shop`), sonst der Name des Ordners."""
    try:
        portal = load_config(workspace).get("portal")
    except ConfigError:
        portal = None
    shop = portal.get("shop") if isinstance(portal, dict) else None
    return shop if isinstance(shop, str) and shop else workspace.name


def stores_needing_apply(brand_workspace, source: dict, workspace=None) -> list:
    """Die Stores, deren Kopie `migration/policies.json` nicht auf der Version von `source` steht.

    Das Plugin führt keine Liste der Stores einer Marke. Gesucht wird deshalb dort, wo die Ablage sie vorsieht:
    in den Ordnern im Ordner von `policies.json` und daneben, je mit einer Kopie derselben Marke (gleicher
    `reference_shop`). Der eigene Workspace zählt auch ohne Kopie, sobald er einen Ordner `migration/` hat.
    """
    folder = Path(brand_workspace).resolve()
    own = Path(workspace).resolve() if workspace is not None else None
    candidates = [own] if own is not None else []
    for base in (folder, folder.parent):
        try:
            candidates += sorted(child for child in base.iterdir() if child.is_dir())
        except OSError:
            continue
    result, seen = [], set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        is_own = candidate == own
        try:
            copy = _read(copy_path(candidate), default=None)
        except PolicyError:
            if is_own:
                raise
            continue
        if copy is None:
            if not (is_own and (candidate / "migration").is_dir()):
                continue
        elif not isinstance(copy, dict) or (not is_own and copy.get("reference_shop") != source.get("reference_shop")):
            continue
        applied = copy.get("version") if isinstance(copy, dict) else None
        if applied == source["version"]:
            continue
        result.append({"shop": _shop_of(candidate), "workspace": str(candidate), "applied_version": applied,
                       "own": is_own})
    return result


def _read_answers(path: str | None):
    """Die Antworten aus einer Datei oder, bei `-`, von stdin."""
    if not path:
        raise PolicyError("--file fehlt (Datei mit den Antworten aus get_setup oder - für stdin).")
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except OSError as error:
        raise PolicyError(f"{path} nicht lesbar: {error}") from error
    except json.JSONDecodeError as error:
        raise PolicyError(f"{path} ist kein JSON: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.policies")
    parser.add_argument("command", choices=("apply", "check", "import"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source")
    parser.add_argument("--brand-workspace", help="Ordner mit policies.json der Marke (import)")
    parser.add_argument("--file", help="Antworten aus get_setup als JSON-Datei, - für stdin (import)")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            if not args.brand_workspace:
                raise PolicyError("--brand-workspace fehlt (Ordner mit policies.json der Marke).")
            result = import_answers(args.brand_workspace, _read_answers(args.file), workspace=args.workspace)
            print(json.dumps(result, ensure_ascii=False))
            # 1 heißt Befund: mindestens eine Antwort wurde nicht übernommen, der Grund steht unter skipped.
            return 1 if result["skipped"] else 0
        source = load_source(args.source) if args.source else None
        if args.command == "apply":
            if source is None:
                raise PolicyError("--source fehlt")
            result = apply(args.workspace, source)
            if not result["unchanged"]:
                _note_in_run(args.workspace, result)
        else:
            result = check(args.workspace, source)
    except PolicyError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if args.command == "apply" or result.get("current") else 1


def _note_in_run(workspace, result: dict) -> None:
    """Hält Version und Zeitpunkt im Migrationslauf fest, falls es einen gibt."""
    from theme import run_state
    run_id = run_state.latest_run_id(workspace)
    if not run_id:
        return
    state = run_state.load(workspace, run_id)
    state.set_value("policies_version", result["version"])
    state.set_value("policies_applied_at", result["applied_at"])
    state.save()
    state.log("set", f"Vorgaben {result['version']} angewendet: {len(result['decisions_added'])} Entscheidungen, "
                     f"{len(result['open_items_added'])} Punkte zum Einbauen")
    run_state.export(workspace, state)


if __name__ == "__main__":
    sys.exit(main())
