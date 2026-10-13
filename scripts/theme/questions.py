#!/usr/bin/env python3
"""Fragen an das Team einer Theme-Migration, eine Datei je Lauf.

Eingeführt mit 0.3.11. Vorher legte Gate G1 einem
Team 171 bis 529 Zeilen vor. Das konnte niemand beantworten: Claude entschied selbst und trug einen Sammelnamen
ein, oder die Entscheidung blieb "vorläufig", oder der Lauf stand still. Deshalb:

- Eine Frage gehört zu genau einem Gate: G1 (Abstimmung), G2 (Zuordnung) oder G4 (Testrunde).
- Höchstens zehn offene Fragen je Gate. Was vorentschieden ist (Vorgaben der Marke, feste Regeln), wird nicht
  gefragt.
- Beantworten kann nur eine Person aus `theme_migration.people`. Ein Sammelname wie "Team" ist keine Person,
  "vorläufig" oder "später" ist keine Antwort; die Frage bleibt dann offen und das Gate auch.
- `run_state gate` verweigert G1 und G2, solange eine Frage ihres Gates offen ist.

Seit 0.3.14 beantwortet das Team die Fragen im Cockpit, nicht mehr in der Sitzung. Dort steht keine Sitzung
daneben, die erklärt, worum es geht. Deshalb trägt jede Frage, was die Person zum Entscheiden braucht:

- `context`: worum es geht und was schon feststeht, in der Sprache des Kunden.
- `compare`: Seitenpaare heute und Entwurf, je mit `preview_theme_id`, damit die Person den Unterschied sieht.
- `options` und `other`: die Antworten zum Anklicken, `other` beschriftet eine Antwort mit Freitext.
- `recommendation` und `reason`: die Empfehlung mit Grund, oder ausdrücklich keine (`None`) und warum nicht.
- `decider`: wer entscheidet; leer heißt jede Person aus `theme_migration.people`.

Ältere Fragen ohne diese Felder bleiben lesbar; ihnen fehlen Erklärung und Grund.

Entscheidet eine Regel eine gestellte Frage doch ("wie heute", "wie im Referenz-Store", Vorgabe der Marke),
zieht `withdraw` sie zurück: Status `withdrawn`, und ihr Ergebnis steht als Punkt in `migration/ruled.json`
(Modul `ruled`), im Cockpit unter "Entscheidungen" bei "Entschieden". Eine zurückgezogene Frage hält kein
Gate an.

Die Antworten aus dem Cockpit holt die Skill beim Start über das Werkzeug `get_migration` des Cockpits und trägt
sie mit `import` ein: nur, wenn die Person in `theme_migration.people` steht und die Frage im Repo noch offen ist.
Eine im Repo eingetragene Antwort gilt; eine spätere im Cockpit ändert sie nicht. Was nicht übernommen wird,
bleibt offen und steht mit Grund in der Ausgabe. Jede Antwort trägt, woher sie kam (`answered_via`: `session`
oder `cockpit`).

Aufruf:
    python3 -m theme.questions ask --gate <gate> --text <frage> --context <text> --reason <text>
        (--recommendation <option> | --no-recommendation) --option <text> [--option <text> ...] [--other <text>]
        [--compare <label> <live-url> <draft-url> ...] [--decider <name> ...]
    python3 -m theme.questions answer --id <id> --by <name> --text <antwort>
    python3 -m theme.questions import --file <antworten.json | ->
    python3 -m theme.questions withdraw --id <id> --source <source> --text <was gilt>
    python3 -m theme.questions list [--status open|answered|withdrawn] [--gate <gate>]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from theme import ConfigError, load_config, migration_config, ruled

GATES = ("G1-decisions", "G2-mapping", "G4-acceptance")
MAX_OPEN_PER_GATE = 10

#: Antworten, die nichts entscheiden.
NON_ANSWERS = re.compile(r"\b(vorläufig|vorlaeufig|später|spaeter|tbd|unklar|provisional|later)\b",
                         re.IGNORECASE)
#: Namen, die keine Person sind.
GROUP_NAMES = re.compile(r"\b(team|alle|everyone|all|gruppe|group)\b", re.IGNORECASE)


class QuestionError(Exception):
    """Eine Frage oder Antwort, die so nicht gilt."""


def path(workspace) -> Path:
    return Path(workspace) / "migration" / "questions.json"


def load(workspace) -> list:
    """Alle Fragen des Laufs, leer, wenn es die Datei noch nicht gibt."""
    target = path(workspace)
    if not target.is_file():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise QuestionError(f"{target} ist beschädigt ({error}); nicht still neu anlegen.") from error
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list):
        raise QuestionError(f"{target} hat keine Liste questions.")
    return questions


def save(workspace, questions: list) -> Path:
    target = path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / (target.name + ".tmp")
    tmp.write_text(json.dumps({"questions": questions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def open_for(workspace, gate: str | None = None) -> list:
    """Offene Fragen, auf Wunsch nur die eines Gates."""
    return [q for q in load(workspace) if q["status"] == "open" and (gate is None or q["gate"] == gate)]


def people(workspace) -> list:
    """Die Personen, die entscheiden dürfen, aus `theme_migration.people`."""
    try:
        block = migration_config(load_config(workspace))
    except ConfigError:
        return []
    names = block.get("people")
    return [n.strip() for n in names if isinstance(n, str) and n.strip()] if isinstance(names, list) else []


def check_person(workspace, name: str) -> str:
    """Gibt den Namen zurück, wenn er eine Person ist, die entscheiden darf. Sonst Fehler mit Grund."""
    name = (name or "").strip()
    if not name:
        raise QuestionError("Eine Entscheidung braucht den Namen der Person.")
    allowed = people(workspace)
    if allowed:
        if name not in allowed:
            raise QuestionError(f"{name!r} steht nicht in theme_migration.people ({', '.join(allowed)}). "
                                "Den Namen der Person eintragen, die entscheidet, keinen Sammelnamen.")
        return name
    if GROUP_NAMES.search(name):
        raise QuestionError(f"{name!r} ist ein Sammelname. Eine Entscheidung trägt den Namen einer Person; "
                            "die Personen in theme_migration.people eintragen.")
    return name


def _text(value, what: str) -> str:
    """Ein Pflichttext ohne Leerraum am Rand; leer ist ein Fehler mit Grund."""
    value = str(value or "").strip()
    if not value:
        raise QuestionError(f"{what} fehlt.")
    return value


def _url(value, what: str) -> str:
    """Ein Link auf den Shop mit `preview_theme_id`, sonst zeigt der Browser das zuletzt besuchte Theme."""
    value = str(value or "").strip()
    if not value.startswith(("https://", "http://")):
        raise QuestionError(f"{what} ist kein Link: {value!r}")
    if "preview_theme_id=" not in value:
        raise QuestionError(f"{what} braucht ?preview_theme_id=<id>, sonst zeigt Shopify das Theme aus dem "
                            f"Cookie statt des gemeinten: {value}")
    return value


def _compare(entries) -> list:
    """Seitenpaare heute und Entwurf, als `{label, live_url, draft_url}`."""
    result = []
    for entry in entries or []:
        if isinstance(entry, dict):
            label, live, draft = entry.get("label"), entry.get("live_url"), entry.get("draft_url")
        elif isinstance(entry, (list, tuple)) and len(entry) == 3:
            label, live, draft = entry
        else:
            raise QuestionError(f"Ein Vergleich braucht Bezeichnung, Link heute und Link Entwurf: {entry!r}")
        pair = {"label": _text(label, "Die Bezeichnung des Vergleichs"),
                "live_url": _url(live, "Der Link auf heute"), "draft_url": _url(draft, "Der Link auf den Entwurf")}
        if pair["live_url"] == pair["draft_url"]:
            raise QuestionError(f"Heute und Entwurf zeigen auf dieselbe Seite ({pair['live_url']}).")
        result.append(pair)
    return result


def ask(workspace, gate: str, text: str, *, context: str, reason: str, recommendation: str | None,
        options: list | None = None, other: str | None = None, compare: list | None = None,
        decider: list | None = None, now: datetime | None = None) -> dict:
    """Legt eine Frage an. `recommendation=None` heißt ausdrücklich keine Empfehlung; `reason` sagt dann, worauf es bei der Entscheidung ankommt."""
    if gate not in GATES:
        raise QuestionError(f"unbekanntes Gate {gate!r}, erlaubt sind {GATES}")
    text = _text(text, "Die Frage")
    context = _text(context, "Die Erklärung (context)")
    reason = _text(reason, "Der Grund (reason)")
    options = [o.strip() for o in (options or []) if isinstance(o, str) and o.strip()]
    other = other.strip() if isinstance(other, str) and other.strip() else None
    if len(options) + (1 if other else 0) < 2:
        raise QuestionError("Eine Frage braucht mindestens zwei Antworten zur Auswahl, Optionen oder eine Option "
                            "mit Freitext (other). Gibt es nur eine, ist es keine Frage.")
    if recommendation is not None:
        recommendation = _text(recommendation, "Die Empfehlung")
        if recommendation not in options:
            raise QuestionError(f"Die Empfehlung {recommendation!r} ist keine der Optionen ({', '.join(options)}). "
                                "Das Cockpit markiert die empfohlene Option; ohne Empfehlung --no-recommendation.")
    deciders = []
    for name in decider or []:
        name = check_person(workspace, name)
        if name not in deciders:
            deciders.append(name)
    pairs = _compare(compare)
    questions = load(workspace)
    still_open = [q for q in questions if q["status"] == "open" and q["gate"] == gate]
    if len(still_open) >= MAX_OPEN_PER_GATE:
        raise QuestionError(f"Für {gate} sind schon {MAX_OPEN_PER_GATE} Fragen offen. Erst beantworten lassen; "
                            "was die Vorgaben oder feste Regeln entscheiden, wird nicht gefragt.")
    number = max([int(q["id"].split("-")[1]) for q in questions] or [0]) + 1
    entry = {"id": f"Q-{number:03d}", "gate": gate, "text": text, "context": context, "compare": pairs,
             "options": options, "other": other, "recommendation": recommendation, "reason": reason,
             "decider": deciders, "status": "open",
             "asked_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    questions.append(entry)
    save(workspace, questions)
    return entry


def _not_open(found: dict) -> str:
    """Warum eine Frage nicht mehr offen ist, in einem Satz."""
    if found["status"] == "withdrawn":
        return (f"Frage {found['id']} ist zurückgezogen und steht im Cockpit unter Entschieden "
                f"({found.get('ruled_id')}).")
    return f"Frage {found['id']} ist schon beantwortet ({found.get('answered_by')}); die Antwort im Repo gilt."


def _find_open(questions: list, question_id: str) -> dict:
    found = next((q for q in questions if q["id"] == question_id), None)
    if found is None:
        raise QuestionError(f"Frage {question_id} gibt es nicht.")
    if found["status"] != "open":
        raise QuestionError(_not_open(found))
    return found


def _decision(text) -> str:
    """Die Antwort, wenn sie etwas entscheidet; sonst Fehler mit Grund."""
    text = str(text or "").strip()
    if not text:
        raise QuestionError("Die Antwort fehlt.")
    if NON_ANSWERS.search(text):
        raise QuestionError("Das ist keine Entscheidung. Die Frage bleibt offen, bis eine Person sie entscheidet.")
    return text


def _stamp(value, now: datetime | None) -> str:
    """Zeitpunkt der Antwort; aus dem Cockpit übernommen, wenn lesbar, sonst jetzt."""
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).isoformat(timespec="seconds")
        except ValueError:
            pass
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def answer(workspace, question_id: str, by: str, text: str, now: datetime | None = None) -> dict:
    """Trägt eine Antwort aus der Sitzung ein."""
    questions = load(workspace)
    found = _find_open(questions, question_id)
    text = _decision(text)
    found.update({"status": "answered", "answer": text, "answered_by": check_person(workspace, by),
                  "answered_at": _stamp(None, now), "answered_via": "session"})
    save(workspace, questions)
    return found


def import_answers(workspace, entries, now: datetime | None = None) -> dict:
    """Trägt Antworten aus dem Cockpit ein, `[{"id", "value", "by", "at"}]` aus `get_migration`.

    Übernommen wird nur, was eine Person aus `theme_migration.people` zu einer im Repo offenen Frage
    entschieden hat. Alles andere bleibt, wie es ist, und steht mit Grund unter `skipped`.
    """
    if not isinstance(entries, list):
        raise QuestionError('Erwartet eine Liste [{"id", "value", "by", "at"}] aus get_migration.')
    allowed = people(workspace)
    questions = load(workspace)
    by_id = {q["id"]: q for q in questions}
    imported, skipped = [], []
    for entry in entries:
        entry = entry if isinstance(entry, dict) else {}
        question_id = str(entry.get("id") or "").strip()
        by = str(entry.get("by") or "").strip()
        found = by_id.get(question_id)
        try:
            if found is None:
                raise QuestionError(f"Frage {question_id or '(ohne id)'} gibt es im Repo nicht.")
            if found["status"] != "open":
                raise QuestionError(_not_open(found))
            value = _decision(entry.get("value"))
            if not allowed:
                raise QuestionError("theme_migration.people ist leer; ohne die Personen, die entscheiden, wird "
                                    "keine Antwort aus dem Cockpit übernommen.")
            if by not in allowed:
                raise QuestionError(f"{by or '(ohne Namen)'} steht nicht in theme_migration.people "
                                    f"({', '.join(allowed)}).")
        except QuestionError as error:
            skipped.append({"id": question_id or None, "by": by or None, "reason": str(error)})
            continue
        found.update({"status": "answered", "answer": value, "answered_by": by,
                      "answered_at": _stamp(entry.get("at"), now), "answered_via": "cockpit"})
        imported.append({"id": question_id, "value": value, "by": by, "at": found["answered_at"]})
    if imported:
        save(workspace, questions)
    return {"imported": imported, "skipped": skipped}


def withdraw(workspace, question_id: str, source: str, text: str, now: datetime | None = None) -> dict:
    """Zieht eine offene Frage zurück und hält ihr Ergebnis als Punkt ohne Frage fest."""
    questions = load(workspace)
    found = _find_open(questions, question_id)
    try:
        entry = ruled.add(workspace, text, source, question_id=question_id, now=now)
    except ruled.RuledError as error:
        raise QuestionError(str(error)) from error
    found.update({"status": "withdrawn", "ruled_id": entry["id"],
                  "withdrawn_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")})
    save(workspace, questions)
    return {"question": found, "ruled": entry}


def _read_answers(source: str | None):
    """Die Antworten aus einer Datei oder, bei `-`, von stdin."""
    if not source:
        raise QuestionError("--file fehlt (Datei mit den Antworten aus get_migration oder - für stdin).")
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        return json.loads(text)
    except OSError as error:
        raise QuestionError(f"{source} nicht lesbar: {error}") from error
    except json.JSONDecodeError as error:
        raise QuestionError(f"{source} ist kein JSON: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.questions")
    parser.add_argument("command", choices=("ask", "answer", "import", "withdraw", "list"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--gate")
    parser.add_argument("--text", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--option", action="append", default=[])
    parser.add_argument("--other")
    parser.add_argument("--recommendation")
    parser.add_argument("--no-recommendation", action="store_true")
    parser.add_argument("--compare", nargs=3, action="append", default=[],
                        metavar=("LABEL", "LIVE_URL", "DRAFT_URL"))
    parser.add_argument("--decider", action="append", default=[])
    parser.add_argument("--id")
    parser.add_argument("--by", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--file")
    parser.add_argument("--status", choices=("open", "answered", "withdrawn"))
    args = parser.parse_args(argv)
    try:
        if args.command == "ask":
            if (args.recommendation is None) == (not args.no_recommendation):
                raise QuestionError("Entweder --recommendation <Option> oder ausdrücklich --no-recommendation; "
                                    "der Grund steht in beiden Fällen in --reason.")
            result = ask(args.workspace, args.gate, args.text, context=args.context, reason=args.reason,
                         recommendation=None if args.no_recommendation else args.recommendation,
                         options=args.option, other=args.other, compare=args.compare, decider=args.decider)
        elif args.command == "answer":
            result = answer(args.workspace, args.id, args.by, args.text)
        elif args.command == "withdraw":
            result = withdraw(args.workspace, args.id, args.source, args.text)
        elif args.command == "import":
            result = import_answers(args.workspace, _read_answers(args.file))
            print(json.dumps(result, ensure_ascii=False))
            # 1 heißt Befund: mindestens eine Antwort blieb offen, der Grund steht unter skipped.
            return 1 if result["skipped"] else 0
        else:
            result = [q for q in load(args.workspace)
                      if (args.status is None or q["status"] == args.status)
                      and (args.gate is None or q["gate"] == args.gate)]
    except QuestionError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
