#!/usr/bin/env python3
"""Vorgaben einer Marke für alle ihre Stores: einmal entschieden, in jedem Lauf gleich angewendet.

Eingeführt mit 0.3.11. Vorher kamen Entscheidungen, die alle Stores einer Marke betreffen (Cookie-Banner, Tracking,
Apps), nur als eingefügter Prompt in einzelne Sitzungen. Ein Entwurf nach dem anderen trug danach etwas anderes
ein, und niemand sah, welcher Stand wo galt.

Die Datei `policies.json` liegt nicht im Plugin, sondern beim Betreiber im Workspace der Marke. Format in
`reference/theme-migration/policies-format.md`. Je Merkmal eine Regel:

- `same_as_reference`: wie im Referenz-Store der Marke; mit `keep` und `drop` (Dienst-IDs aus `apps.json`)
- `open`: noch nicht entschieden; hält die Vorbereitung nicht an, steht im Cockpit als Entscheidung beim Betreiber
- `may_differ`: darf je Store abweichen

`apply` schreibt eine Kopie nach `migration/policies.json` im Repo des Stores, die Entscheidungen nach
`migration/mapping/decisions.json` (`source: policy`, ersetzt ältere) und nach `apps.json`, damit der Generator
sie beim nächsten Neubau liest. Ein Dienst, der beibehalten werden soll, aber im Inventar fehlt, wird ein Punkt
`blocker` in der Liste offener Punkte: er muss vor der Testrunde eingebaut sein. Der Betreiber committet und
pusht; das Team zieht den Stand mit dem Repo. Eine Vorgabe öffnet nie eine Frage an das Team.

Aufruf:
    python3 -m theme.policies apply --source <policies.json> [--workspace <ws>]
    python3 -m theme.policies check [--source <policies.json>] [--workspace <ws>]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from theme import ConfigError, load_config

RULES = ("same_as_reference", "open", "may_differ")


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
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                errors.append(f"{where}.{field} muss eine Liste von Dienst-IDs sein")
        if rule.get("rule") != "same_as_reference" and (rule.get("keep") or rule.get("drop")):
            errors.append(f"{where}: keep und drop nur bei same_as_reference")
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


def apply(workspace, source: dict, now: datetime | None = None) -> dict:
    """Wendet die Vorgaben auf den Lauf eines Stores an. Gleiche Version zweimal ändert nichts."""
    from theme import open_items  # erst hier, damit der Import der Schritte leicht bleibt

    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    version = source["version"]
    decisions, wrap = _decisions(workspace)
    apps = _read(apps_path(workspace), default=None)
    services = {s.get("service_id"): s for s in (apps or {}).get("services") or [] if isinstance(s, dict)}
    added, replaced, missing = [], [], []
    for rule in source["rules"]:
        if rule["rule"] != "same_as_reference":
            continue
        for decision, ids in (("keep", rule.get("keep", [])), ("drop", rule.get("drop", []))):
            for service_id in ids:
                ident = f"policy-{version}-{rule['key']}-{service_id}"
                if any(d.get("id") == ident for d in decisions):
                    continue
                earlier = [d["id"] for d in decisions
                           if d.get("service_id") == service_id and d.get("id")
                           and not any(d["id"] in (e.get("replaces") or []) for e in decisions)]
                entry = {"id": ident, "subject": rule.get("subject") or rule["key"],
                         "kind": "app" if service_id.startswith("app:") else "service", "decision": decision,
                         "reason": f"Vorgabe der Marke, Version {version}: {rule.get('target') or rule.get('note') or decision}",
                         "decided_by": source["decided_by"], "decided_at": source["decided_at"],
                         "source": "policy", "service_id": service_id, "replaces": earlier}
                decisions.append(entry)
                added.append(ident)
                replaced += earlier
                if service_id in services:
                    services[service_id].update({"decision": decision, "decision_source": "policy",
                                                 "policy_version": version})
                elif decision == "keep":
                    missing.append((rule, service_id))
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
    return {"version": version, "applied_at": stamp, "decisions_added": added, "decisions_replaced": replaced,
            "open_items_added": items_added,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.policies")
    parser.add_argument("command", choices=("apply", "check"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source")
    args = parser.parse_args(argv)
    try:
        source = load_source(args.source) if args.source else None
        if args.command == "apply":
            if source is None:
                raise PolicyError("--source fehlt")
            result = apply(args.workspace, source)
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
