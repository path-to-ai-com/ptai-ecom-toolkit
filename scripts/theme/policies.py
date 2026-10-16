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
`blocker` in der Liste offener Punkte: er muss vor der Abnahme eingebaut sein. Der Betreiber committet und
pusht; das Team zieht den Stand mit dem Repo. Eine Vorgabe öffnet nie eine Frage an das Team.

Seit 0.3.15 entscheidet die Marke eine Vorgabe ohne Regel auch selbst, im Setup des Cockpits (Karte "Vorgaben der
Marke", Fragen aus `policy_questions` im Setup des Referenz-Stores). `import` übernimmt diese Antworten aus
`get_setup` in `policies.json`: `options[0]` heißt `may_differ`, `options[1]` `same_as_reference` mit dem Ziel
"wie im Referenz-Store". Nennt die Frage eine App (`app:<handle>`), behält die angeglichene Regel sie
(`keep`), und `apply` legt in jedem Store ohne die App einen Punkt zum Einbauen an. Die Regel trägt danach
selbst `decided_by` und `decided_at`, die Datei eine neue Version.
Entscheiden dürfen alle Mitglieder der Marke; das Plugin kennt sie nicht, und das Cockpit lässt nur Mitglieder
antworten. Deshalb gilt jede Antwort aus dem Cockpit, und ihr Name steht an der Regel.

Seit 0.3.16 ist das Cockpit die einzige Quelle der Vorgaben (Vertrag V15). Der Betreiber lädt `policies.json` und
den Ordner `policy-modules/` der Marke mit `audit.publish --policies-only` hoch; das Werkzeug `get_policies` gibt
die gültige Fassung zurück, Datei plus Antworten aus dem Cockpit, je Regel die Bausteine (`modules`) mit dem
Inhalt ihrer Dateien. `sync` schreibt diese Fassung nach `migration/policies.json` im Repo des Stores und die
Bausteine nach `migration/policy-modules/<key>/`; danach greift `apply` wie bisher, mit
`--source migration/policies.json`. Das Team braucht damit weder den Ordner der Marke noch ein anderes Repo.
`import` mit `--brand-workspace` bleibt für den Betreiber.

Aufruf:
    python3 -m theme.policies apply --source <policies.json> [--workspace <ws>]
    python3 -m theme.policies check [--source <policies.json>] [--workspace <ws>]
    python3 -m theme.policies import --brand-workspace <ordner mit policies.json> --file <antworten.json | ->
        [--workspace <ws>]
    python3 -m theme.policies sync --file <ausgabe von get_policies | -> [--workspace <ws>]
    python3 -m theme.policies sheets --source <policies.json> --setup <setup.json des Referenz-Stores>
        [--setup <setup.json eines weiteren Stores> ...]
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
#: Ordner der Bausteine neben `policies.json`: im Ordner der Marke, im Bucket unter `brands/<brand>/` und im
#: Repo des Stores unter `migration/`. Der Pfad eines Bausteins (`modules[].path`) beginnt immer damit.
MODULES_DIR = "policy-modules"


class PolicyError(Exception):
    """Vorgaben, die so nicht gelten."""


def copy_path(workspace) -> Path:
    return Path(workspace) / "migration" / "policies.json"


def modules_path(workspace) -> Path:
    """Die Bausteine der Marke im Repo des Stores, geschrieben von `sync`."""
    return Path(workspace) / "migration" / MODULES_DIR


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
    if not isinstance(data.get("version"), str) or not data["version"].strip():
        errors.append("version fehlt")
    # Wer entschieden hat, steht an der Datei oder an jeder entschiedenen Regel. Ohne Datei des Betreibers
    # gibt get_policies nur Regeln aus Antworten im Cockpit zurück, jede mit ihrer Person.
    for key in ("decided_by", "decided_at"):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            errors.append(f"{key} ist leer")
    file_decided = all(isinstance(data.get(k), str) and data[k].strip() for k in ("decided_by", "decided_at"))
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
        if not file_decided and rule.get("rule") in ("same_as_reference", "may_differ") and not all(
                isinstance(rule.get(f), str) and rule[f].strip() for f in ("decided_by", "decided_at")):
            errors.append(f"{where}: decided_by und decided_at fehlen an der Regel und an der Datei")
        if "modules" in rule:
            errors += _module_errors(rule.get("modules"), key if isinstance(key, str) else "", where)
        errors += _text_errors(rule, where)
    return errors


#: Die Texte einer Regel für die Marke (seit 16.10.2026), Format in `reference/theme-migration/policies-format.md`.
TEXT_FIELDS = ("context", "reason", "recommendation", "outcomes", "needs")
DECIDED_RULES = ("same_as_reference", "may_differ")


def _text_errors(rule: dict, where: str) -> list:
    """Fehler in der Form der Texte für die Marke; ob sie da sind, prüft `explanation_problems`."""
    errors = []
    for field in ("context", "reason"):
        if field in rule and (not isinstance(rule[field], str) or not rule[field].strip()):
            errors.append(f"{where}.{field} muss ein nicht leerer Text sein")
    if "recommendation" in rule:
        if rule["recommendation"] not in DECIDED_RULES:
            errors.append(f"{where}.recommendation muss eines von {DECIDED_RULES} sein")
        elif rule.get("rule") != "open":
            errors.append(f"{where}.recommendation nur bei einer offenen Regel")
    if "outcomes" in rule:
        outcomes = rule["outcomes"]
        if not isinstance(outcomes, dict) or set(outcomes) - set(DECIDED_RULES) or not all(
                isinstance(v, str) and v.strip() for v in outcomes.values()):
            errors.append(f"{where}.outcomes muss je Option ({', '.join(DECIDED_RULES)}) einen Satz tragen")
    if "needs" in rule:
        needs = rule["needs"]
        if not isinstance(needs, dict) or set(needs) - set(DECIDED_RULES):
            errors.append(f"{where}.needs muss je Option ({', '.join(DECIDED_RULES)}) eine Liste sein")
        else:
            for option, entries in needs.items():
                if not isinstance(entries, list) or not all(
                        isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"].strip()
                        and isinstance(e.get("shops", []), list) and all(isinstance(s, str) and s for s in e.get("shops", []))
                        for e in entries):
                    errors.append(f"{where}.needs.{option} muss eine Liste von {{shops, text}} sein")
    return errors


#: Verweis auf eine Zeile einer Tabelle des Betreibers. Im Blatt einer Vorgabe versteht ihn niemand.
INTERNAL_REFERENCE = re.compile(r"\bZeile \d+\b")


def rows_of(key: str, app: str | None, entries: list) -> set:
    """Die Zeilen im Setup, die das Cockpit einer Vorgabe zuordnet, wie `rowsOf` in `lib/brand-policies.ts`.

    Gefunden wird über den Schlüssel der Regel, die App ihrer Frage und die Dienste aus `keep` und `drop`.
    """
    rows = {key}
    if app:
        rows.add(app)
    for entry in entries:
        for service in entry if isinstance(entry, list) else [entry]:
            rows.add(service if service.startswith("app:") else f"app:{service}")
    return rows


def setup_row_keys(setup: dict) -> set:
    """Die Schlüssel aller Zeilen eines Setups, über Live-Ansicht und Entwurf."""
    keys = set()
    for view in (setup.get("views") or {}).values():
        for group in (view or {}).get("groups") or []:
            for row in group.get("rows") or []:
                if isinstance(row, dict) and row.get("key"):
                    keys.add(row["key"])
    return keys


def explanation_problems(data: dict) -> list:
    """Was einer Regel fehlt, damit ihr Blatt im Cockpit ohne Path to AI verständlich ist (seit 16.10.2026).

    Jede Regel braucht `context` (worum es geht), `reason` (warum so entschieden oder empfohlen), `outcomes`
    mit der Folge beider Optionen und `needs` mit dem, was das Team je Option tun muss, leer, wenn nichts. Kein
    Text verweist auf eine Zeile einer Tabelle des Betreibers. Anlass: Am 16.10.2026 zeigte das Blatt „Google
    Tag Manager“ bei einer Marke nur „eigener Code im Theme wie <Referenz-Store>“, und niemand verstand, dass der Tag
    Manager damit ohne App lädt.
    """
    problems = []
    for rule in data.get("rules") or []:
        if not isinstance(rule, dict) or not rule.get("key"):
            continue
        key, subject = rule["key"], rule.get("subject") or rule["key"]
        missing = [f for f in ("context", "reason") if not (isinstance(rule.get(f), str) and rule[f].strip())]
        outcomes = rule.get("outcomes") if isinstance(rule.get("outcomes"), dict) else {}
        missing += [f"outcomes.{o}" for o in DECIDED_RULES if not (isinstance(outcomes.get(o), str) and outcomes[o].strip())]
        needs = rule.get("needs") if isinstance(rule.get("needs"), dict) else None
        if needs is None:
            missing.append("needs")
        else:
            missing += [f"needs.{o}" for o in DECIDED_RULES if not isinstance(needs.get(o), list)]
        if missing:
            problems.append(f"{subject} ({key}): {', '.join(missing)} fehlt. Ohne diese Texte zeigt das Blatt im Cockpit "
                            f"nur Stichworte.")
        texts = [rule.get("context"), rule.get("reason"), *outcomes.values(),
                 *(e.get("text") for entries in (needs or {}).values() if isinstance(entries, list)
                   for e in entries if isinstance(e, dict))]
        for text in texts:
            match = INTERNAL_REFERENCE.search(str(text or ""))
            if match:
                problems.append(f"{subject} ({key}) verweist auf „{match.group(0)}“ einer Tabelle des Betreibers. "
                                f"Im Cockpit versteht das niemand.")
                break
    return problems


def sheet_problems(data: dict, reference_setup: dict | None, setups: list | None = None) -> tuple[list, list]:
    """Was im Blatt einer Vorgabe im Cockpit fehlen würde, als Fehler und Hinweise.

    Das Blatt zeigt je Vorgabe eine Erklärung, die Empfehlung und die Tabelle „In den Stores“. Die Erklärung
    einer offenen Vorgabe kommt aus ihrer Frage in `policy_questions` im Setup des Referenz-Stores; fehlt die
    Frage, zeigt das Cockpit die Notiz der Regel, und die ist für den Betreiber geschrieben. Die Tabelle findet
    ihre Zeilen über `rows_of` in allen Setups der Marke; ohne Treffer fehlt sie. Anlass: Am 15.10.2026 zeigte
    das Blatt einer offenen Vorgabe nur „Zeile 21, Rückfrage.“ aus der Tabelle des Betreibers und keine Stores.

    Fehler gelten für offene Vorgaben und für Fragen, denn die entscheidet die Marke im Cockpit. Eine
    entschiedene Regel ohne Zeile ist nur ein Hinweis: ihr Blatt zeigt dann Vorgabe und Entscheidung ohne
    Tabelle, und davon gibt es heute viele. `setups` sind die Setups der übrigen Stores.
    """
    questions = {}
    for question in (reference_setup or {}).get("policy_questions") or []:
        if isinstance(question, dict) and question.get("key"):
            questions[question["key"]] = question
    rules = [rule for rule in data.get("rules") or [] if isinstance(rule, dict) and rule.get("key")]
    open_rules = [rule for rule in rules if rule.get("rule") == "open"]
    if reference_setup is None:
        if not open_rules:
            return [], []
        return [f"Setup des Referenz-Stores {data.get('reference_shop')} nicht gefunden. Ohne es lässt sich nicht "
                f"prüfen, ob das Cockpit die offenen Vorgaben erklärt: "
                f"{', '.join(rule['key'] for rule in open_rules)}."], []
    known = set()
    for setup in [reference_setup, *(setups or [])]:
        known |= setup_row_keys(setup)
    problems, hints = [], []
    unmatched_decided = []
    for rule in rules:
        key, subject = rule["key"], rule.get("subject") or rule["key"]
        question = questions.get(key)
        if rule.get("rule") == "open" and question is None:
            problems.append(f"{subject} ({key}) ist offen, aber ohne Frage in policy_questions des Referenz-Stores. "
                            f"Das Cockpit zeigte im Blatt nur die Notiz der Regel.")
        rows = rows_of(key, (question or {}).get("app"), [*(rule.get("keep") or []), *(rule.get("drop") or [])])
        if rows & known:
            continue
        if rule.get("rule") == "open":
            problems.append(f"{subject} ({key}) hat keine Zeile im Setup der Stores (gesucht: "
                            f"{', '.join(sorted(rows))}). Das Blatt zeigte keine Tabelle „In den Stores“.")
        else:
            unmatched_decided.append(key)
    rule_keys = {rule["key"] for rule in rules}
    for key, question in questions.items():
        if key not in rule_keys and not rows_of(key, question.get("app"), []) & known:
            problems.append(f"Frage {key} hat keine Zeile im Setup der Stores. Das Blatt zeigte keine Tabelle "
                            f"„In den Stores“.")
        for field in ("text", "context", "reason"):
            match = INTERNAL_REFERENCE.search(str(question.get(field) or ""))
            if match:
                problems.append(f"Frage {key}: {field} verweist auf „{match.group(0)}“ einer Tabelle des Betreibers. "
                                f"Im Cockpit versteht das niemand.")
    if unmatched_decided:
        hints.append(f"{len(unmatched_decided)} entschiedene Vorgaben ohne Zeile im Setup, ihr Blatt zeigt keine "
                     f"Tabelle „In den Stores“: {', '.join(unmatched_decided)}.")
    return problems, hints


def module_path_problem(key: str, path) -> str | None:
    """Warum `path` kein Pfad eines Bausteins der Regel `key` ist, `None`, wenn er gilt.

    Erlaubt ist nur `policy-modules/<key>/<datei>`, auch mit Unterordnern, nie mit `..`, Backslash oder
    absolutem Pfad: `sync` schreibt den Pfad unter `migration/` im Repo des Stores, und ein Pfad aus dem
    Cockpit darf dort nichts außerhalb der Bausteine dieser Regel treffen.
    """
    prefix = f"{MODULES_DIR}/{key}/"
    if not isinstance(path, str) or not path.startswith(prefix) or len(path) == len(prefix):
        return f"Pfad muss {prefix}<datei> sein, ist {path!r}"
    parts = path.split("/")
    if "\\" in path or any(part in ("", ".", "..") for part in parts):
        return f"Pfad {path!r} enthält einen leeren Teil, . oder .. oder einen Backslash"
    return None


def _module_errors(modules, key: str, where: str) -> list:
    """Fehler in `modules` einer Regel: `[{"name", "path", "description"}]`."""
    if not isinstance(modules, list):
        return [f"{where}.modules muss eine Liste sein"]
    errors, seen = [], set()
    for index, module in enumerate(modules):
        at = f"{where}.modules[{index}]"
        if not isinstance(module, dict):
            errors.append(f"{at} muss ein Objekt sein")
            continue
        if not isinstance(module.get("name"), str) or not module["name"].strip():
            errors.append(f"{at}.name fehlt")
        problem = module_path_problem(key, module.get("path"))
        if problem:
            errors.append(f"{at}: {problem}")
        elif module["path"] in seen:
            errors.append(f"{at}.path {module['path']!r} doppelt")
        seen.add(module.get("path"))
        if module.get("description") is not None and not isinstance(module["description"], str):
            errors.append(f"{at}.description muss Text sein")
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
                      "decided_by": rule.get("decided_by") or source.get("decided_by"),
                      "decided_at": rule.get("decided_at") or source.get("decided_at"),
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
                                  "und muss vor der Abnahme eingebunden sein.")
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


#: Was an einer Regel zählt, wenn `sync` meldet, ob sie sich geändert hat. Wer entschieden hat, ändert die
#: Regel nicht; das steht in `decided_by` und `decided_at` der neuen Fassung.
#: Was keinen Neubau verlangt: wer entschieden hat und die Texte für die Marke im Cockpit (`TEXT_FIELDS`).
_UNCOUNTED = ("decided_by", "decided_at", "context", "reason", "recommendation", "outcomes", "needs")


def _rule_changes(before: list, after: list) -> list:
    """Neue, geänderte und entfallene Regeln zwischen zwei Fassungen, in der Reihenfolge der neuen."""
    old = {r.get("key"): r for r in before if isinstance(r, dict)}
    new = {r["key"]: r for r in after}
    changes = []
    for key, rule in new.items():
        previous = old.get(key)
        fields = [f for f in (*RULE_FIELDS, "modules")
                  if f not in _UNCOUNTED and (previous or {}).get(f) != rule.get(f)]
        if previous is None or fields:
            changes.append({"key": key, "subject": rule.get("subject") or key,
                            "change": "added" if previous is None else "changed",
                            "previous": previous.get("rule") if previous else None, "rule": rule["rule"],
                            "fields": [] if previous is None else fields})
    for key, rule in old.items():
        if key not in new:
            changes.append({"key": key, "subject": rule.get("subject") or key, "change": "removed",
                            "previous": rule.get("rule"), "rule": None, "fields": []})
    return changes


def _cockpit_brand(workspace) -> str | None:
    """Die Marke des Stores im Cockpit (`portal.brand`, sonst `account_slug`), `None` ohne Config."""
    try:
        config = load_config(workspace)
    except ConfigError:
        return None
    portal = config.get("portal") if isinstance(config.get("portal"), dict) else {}
    brand = portal.get("brand") or config.get("account_slug")
    return brand if isinstance(brand, str) and brand.strip() else None


#: Die Felder von `policies.json`, an der Datei, je Regel und je Baustein. `sync` schreibt nur sie: Was
#: `get_policies` sonst mitgibt (`brand`, `file_version`, `reference_shop_name`, `open_rules`,
#: `cockpit_questions`, Felder der Datei, die das Format nicht kennt), wechselt mit jedem Abruf oder gehört
#: in die Sitzung, nicht ins Repo. `null` heißt "fehlt".
SOURCE_FIELDS = ("version", "reference_shop", "decided_by", "decided_at")
RULE_FIELDS = ("key", "subject", "rule", "target", "keep", "drop", "note", "decided_by", "decided_at",
               *("context", "reason", "recommendation", "outcomes", "needs"))
MODULE_FIELDS = ("name", "path", "description")


def _pick(data: dict, fields: tuple) -> dict:
    return {f: data[f] for f in fields if data.get(f) is not None}


def _split_modules(data: dict) -> tuple[dict, dict, list]:
    """Die Fassung im Format von `policies.json`, die Inhalte der Bausteine je Pfad und die ohne Inhalt.

    `get_policies` liefert je Baustein `content` mit dem Text der Datei, `null`, wenn die Datei im Cockpit
    fehlt. In `policies.json` steht nur der Verweis (`name`, `path`, `description`), der Inhalt liegt als
    Datei daneben.
    """
    data = json.loads(json.dumps(data))
    source = _pick(data, SOURCE_FIELDS)
    source["rules"] = data["rules"] if not isinstance(data.get("rules"), list) else []
    contents, missing = {}, []
    for rule in data.get("rules") if isinstance(data.get("rules"), list) else []:
        if not isinstance(rule, dict):
            source["rules"].append(rule)  # validate meldet es
            continue
        picked = _pick(rule, RULE_FIELDS)
        modules = rule.get("modules")
        if isinstance(modules, list) and modules:
            picked["modules"] = []
            for module in modules:
                if not isinstance(module, dict):
                    picked["modules"].append(module)
                    continue
                picked["modules"].append(_pick(module, MODULE_FIELDS))
                if isinstance(module.get("content"), str):
                    contents[module.get("path")] = module["content"]
                else:
                    missing.append({"key": rule.get("key"), "name": module.get("name"), "path": module.get("path")})
        elif modules is not None and not isinstance(modules, list):
            picked["modules"] = modules
        source["rules"].append(picked)
    return source, contents, missing


def _write_text(path: Path, text: str) -> bool:
    """Schreibt `text`, wenn er sich von der Datei unterscheidet. Gibt zurück, ob geschrieben wurde."""
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _remove_stale_modules(workspace, keep: set) -> list:
    """Löscht Dateien unter `migration/policy-modules/`, die die neue Fassung nicht mehr nennt.

    Der Ordner ist ein Abbild der Bausteine der Marke und gehört `sync`; ein Baustein, den die Marke
    gestrichen hat, darf im Repo des Stores nicht als gültig liegen bleiben.
    """
    root = modules_path(workspace)
    if not root.is_dir():
        return []
    removed = []
    for path in sorted(root.rglob("*"), reverse=True):
        rel = path.relative_to(Path(workspace) / "migration").as_posix()
        if path.is_file() and rel not in keep:
            path.unlink()
            removed.append(f"migration/{rel}")
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()
    return sorted(removed)


def sync(workspace, data) -> dict:
    """Schreibt die Fassung aus `get_policies` in das Repo des Stores, `migration/policies.json` und Bausteine.

    `data` ist die Ausgabe von `get_policies`: Felder von `policies.json`, je Regel `modules` mit `content`;
    alles andere zählt nicht (`SOURCE_FIELDS`). Ein Baustein ohne Inhalt steht unter `modules_missing`, seine
    Datei fehlt dann auch im Repo des Stores. Hat sich nichts geändert, bleibt `applied_at` der Kopie stehen,
    und `apply` danach ändert nichts. Hat sich die Version, eine Regel oder ein Baustein geändert, fällt
    `applied_at` weg: `apply` trägt die Fassung ein, und Schritt 3 verlangt danach einen Neubau, der auch
    geänderte Bausteine einbaut.
    Führt die Marke keine Vorgaben (`rules` fehlt oder ist leer), wird nichts geschrieben (`available: false`).
    """
    if not isinstance(data, dict):
        raise PolicyError("Erwartet die Ausgabe von get_policies als JSON-Objekt mit rules.")
    previous = _read(copy_path(workspace), default=None)
    previous_version = previous.get("version") if isinstance(previous, dict) else None
    if not data.get("rules"):
        return {"available": False, "path": "migration/policies.json", "version": previous_version,
                "previous_version": previous_version, "changed": False, "apply_needed": False,
                "rules_changed": [], "modules_written": [], "modules_removed": [], "modules_missing": [],
                "still_open": []}
    own, theirs = _cockpit_brand(workspace), data.get("brand")
    if own and isinstance(theirs, str) and theirs and theirs != own:
        raise PolicyError(f"get_policies nennt die Marke {theirs!r}, dieser Store gehört im Cockpit zu {own!r} "
                          "(portal.brand, sonst account_slug). Nichts geschrieben.")
    source, contents, missing = _split_modules(data)
    errors = validate(source)
    if errors:
        raise PolicyError("Die Vorgaben aus get_policies gelten so nicht: " + "; ".join(errors)
                          + ". Nichts geschrieben.")
    modules = {m["path"]: (rule["key"], m.get("name"))
               for rule in source["rules"] for m in rule.get("modules") or []}
    written = []
    for module_path, content in contents.items():
        if _write_text(Path(workspace) / "migration" / module_path, content):
            key, name = modules[module_path]
            written.append({"key": key, "name": name, "path": f"migration/{module_path}"})
    removed = _remove_stale_modules(workspace, set(contents))
    missing = [{**m, "path": f"migration/{m['path']}"} for m in missing]
    changes = _rule_changes(previous.get("rules") or [] if isinstance(previous, dict) else [], source["rules"])
    # Eine neue Version, die nur Texte für die Marke ändert (`_UNCOUNTED`), verlangt keinen Neubau: Der
    # Zeitpunkt der Anwendung bleibt, und Schritt 3 springt nicht auf nacharbeiten (seit 16.10.2026).
    keep_stamp = (isinstance(previous, dict)
                  and isinstance(previous.get("applied_at"), str) and previous["applied_at"].strip()
                  and not changes and not written and not removed)
    copy = {**source, "applied_at": previous["applied_at"]} if keep_stamp else source
    target = copy_path(workspace)
    before = target.read_text(encoding="utf-8") if target.is_file() else None
    text = json.dumps(copy, ensure_ascii=False, indent=2) + "\n"
    if text != before:
        _write(target, copy)
    return {"available": True, "path": "migration/policies.json", "version": source["version"],
            "previous_version": previous_version, "changed": text != before or bool(written or removed),
            "apply_needed": not keep_stamp, "rules_changed": changes, "modules_written": written,
            "modules_removed": removed, "modules_missing": missing,
            "still_open": [{"key": r["key"], "subject": r.get("subject") or r["key"]}
                           for r in source["rules"] if r["rule"] == "open"]}


def _read_json(path: str | None, what: str):
    """JSON aus einer Datei oder, bei `-`, von stdin. `what` sagt in der Meldung, was erwartet wird."""
    if not path:
        raise PolicyError(f"--file fehlt (Datei mit {what} oder - für stdin).")
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except OSError as error:
        raise PolicyError(f"{path} nicht lesbar: {error}") from error
    except json.JSONDecodeError as error:
        raise PolicyError(f"{path} ist kein JSON: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.policies")
    parser.add_argument("command", choices=("apply", "check", "import", "sync", "sheets"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source")
    parser.add_argument("--brand-workspace", help="Ordner mit policies.json der Marke (import)")
    parser.add_argument("--file", help="Antworten aus get_setup (import) oder Ausgabe von get_policies (sync) "
                                       "als JSON-Datei, - für stdin")
    parser.add_argument("--setup", action="append", default=[],
                        help="setup.json eines Stores (sheets), zuerst der Referenz-Store")
    args = parser.parse_args(argv)
    try:
        if args.command == "sheets":
            if not args.source or not args.setup:
                raise PolicyError("sheets braucht --source und mindestens ein --setup (zuerst der Referenz-Store).")
            setups = [_read_json(path, "einem Setup") for path in args.setup]
            problems, hints = sheet_problems(load_source(args.source), setups[0], setups[1:])
            print(json.dumps({"problems": problems, "hints": hints}, ensure_ascii=False))
            # 1 heißt Befund: das Cockpit könnte mindestens eine offene Vorgabe nicht erklären.
            return 1 if problems else 0
        if args.command == "import":
            if not args.brand_workspace:
                raise PolicyError("--brand-workspace fehlt (Ordner mit policies.json der Marke).")
            result = import_answers(args.brand_workspace, _read_json(args.file, "den Antworten aus get_setup"),
                                    workspace=args.workspace)
            print(json.dumps(result, ensure_ascii=False))
            # 1 heißt Befund: mindestens eine Antwort wurde nicht übernommen, der Grund steht unter skipped.
            return 1 if result["skipped"] else 0
        if args.command == "sync":
            result = sync(args.workspace, _read_json(args.file, "der Ausgabe von get_policies"))
            print(json.dumps(result, ensure_ascii=False))
            # 1 heißt Befund: ein Baustein kam ohne Inhalt; die übrige Fassung ist geschrieben.
            return 1 if result["modules_missing"] else 0
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
