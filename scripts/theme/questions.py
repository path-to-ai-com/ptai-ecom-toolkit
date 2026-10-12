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

Die offenen Fragen stehen in `migration.json` und erscheinen im Cockpit als Offene Aufgaben.

Aufruf:
    python3 -m theme.questions ask --gate <gate> --text <frage> [--option <text> ...] [--recommendation <text>]
    python3 -m theme.questions answer --id <id> --by <name> --text <antwort>
    python3 -m theme.questions list [--status open|answered] [--gate <gate>]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from theme import ConfigError, load_config, migration_config

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


def ask(workspace, gate: str, text: str, options: list | None = None, recommendation: str = "",
        now: datetime | None = None) -> dict:
    if gate not in GATES:
        raise QuestionError(f"unbekanntes Gate {gate!r}, erlaubt sind {GATES}")
    if not (text or "").strip():
        raise QuestionError("Die Frage fehlt.")
    questions = load(workspace)
    still_open = [q for q in questions if q["status"] == "open" and q["gate"] == gate]
    if len(still_open) >= MAX_OPEN_PER_GATE:
        raise QuestionError(f"Für {gate} sind schon {MAX_OPEN_PER_GATE} Fragen offen. Erst beantworten lassen; "
                            "was die Vorgaben oder feste Regeln entscheiden, wird nicht gefragt.")
    number = max([int(q["id"].split("-")[1]) for q in questions] or [0]) + 1
    entry = {"id": f"Q-{number:03d}", "gate": gate, "text": text.strip(), "options": options or [],
             "recommendation": recommendation.strip(), "status": "open",
             "asked_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    questions.append(entry)
    save(workspace, questions)
    return entry


def answer(workspace, question_id: str, by: str, text: str, now: datetime | None = None) -> dict:
    questions = load(workspace)
    found = next((q for q in questions if q["id"] == question_id), None)
    if found is None:
        raise QuestionError(f"Frage {question_id} gibt es nicht.")
    if found["status"] != "open":
        raise QuestionError(f"Frage {question_id} ist schon beantwortet ({found.get('answered_by')}).")
    if not (text or "").strip():
        raise QuestionError("Die Antwort fehlt.")
    if NON_ANSWERS.search(text):
        raise QuestionError("Das ist keine Entscheidung. Die Frage bleibt offen, bis eine Person sie entscheidet.")
    found.update({"status": "answered", "answer": text.strip(), "answered_by": check_person(workspace, by),
                  "answered_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")})
    save(workspace, questions)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.questions")
    parser.add_argument("command", choices=("ask", "answer", "list"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--gate")
    parser.add_argument("--text", default="")
    parser.add_argument("--option", action="append", default=[])
    parser.add_argument("--recommendation", default="")
    parser.add_argument("--id")
    parser.add_argument("--by", default="")
    parser.add_argument("--status", choices=("open", "answered"))
    args = parser.parse_args(argv)
    try:
        if args.command == "ask":
            result = ask(args.workspace, args.gate, args.text, args.option, args.recommendation)
        elif args.command == "answer":
            result = answer(args.workspace, args.id, args.by, args.text)
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
