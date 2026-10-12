#!/usr/bin/env python3
"""Ohne Frage entschieden: was eine Regel statt einer Person entscheidet, eine Datei je Lauf.

Seit 0.3.14. Die Regel für Fragen an das Team lautet: Standard ist "wie heute", "wie im Referenz-Store" oder
die Vorgabe der Marke. Gefragt wird nur bei einem echten Zielkonflikt. Was eine Regel entscheidet, verschwindet
aber nicht still: es steht im Cockpit unter "Ohne Frage entschieden", mit seiner Herkunft, und das Team kann
einen Einwand schreiben. Ohne diese Liste sähe das Team nicht, was Claude für es entschieden hat.

Ein Punkt entsteht auf zwei Wegen: `questions withdraw` zieht eine gestellte Frage zurück und schreibt ihr
Ergebnis hierher, `ruled add` hält einen Punkt fest, der nie gefragt wurde. Führt ein Einwand doch zu einer
Frage, nimmt `revoke` den Punkt mit Grund zurück; er bleibt in der Datei und erscheint nicht mehr im Cockpit.

Herkunft (`source`):
- `policy`: Vorgabe der Marke
- `as_today`: wie heute
- `as_reference`: wie im Referenz-Store
- `operator`: vom Betreiber eingetragen
- `check`: Prüfung im Shop

Aufruf:
    python3 -m theme.ruled add --source <source> --text <text>
    python3 -m theme.ruled revoke --id <R-001> --reason <text>
    python3 -m theme.ruled list
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCES = ("policy", "as_today", "as_reference", "operator", "check")


class RuledError(Exception):
    """Ein Punkt, der so nicht gilt, oder eine beschädigte Datei."""


def path(workspace) -> Path:
    return Path(workspace) / "migration" / "ruled.json"


def load(workspace) -> list:
    """Alle Punkte, auch zurückgenommene; leer, wenn es die Datei noch nicht gibt."""
    target = path(workspace)
    if not target.is_file():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuledError(f"{target} ist beschädigt ({error}); nicht still neu anlegen.") from error
    entries = data.get("ruled") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise RuledError(f"{target} hat keine Liste ruled.")
    return entries


def save(workspace, entries: list) -> Path:
    target = path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / (target.name + ".tmp")
    tmp.write_text(json.dumps({"ruled": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def check(text: str, source: str) -> tuple[str, str]:
    """Prüft Text und Herkunft, bevor irgendetwas geschrieben wird."""
    if source not in SOURCES:
        raise RuledError(f"unbekannte Herkunft {source!r}, erlaubt sind {SOURCES}")
    text = str(text or "").strip()
    if not text:
        raise RuledError("Der Text fehlt: was ist entschieden, in einem Satz für das Team.")
    return text, source


def add(workspace, text: str, source: str, question_id: str | None = None, now: datetime | None = None) -> dict:
    """Hält einen Punkt fest. Derselbe Text mit derselben Herkunft entsteht nur einmal."""
    text, source = check(text, source)
    entries = load(workspace)
    same = next((e for e in entries if e["text"] == text and e["source"] == source and not e.get("revoked_at")),
                None)
    if same is not None:
        return same
    number = max([int(e["id"].split("-")[1]) for e in entries] or [0]) + 1
    entry = {"id": f"R-{number:03d}", "text": text, "source": source,
             "at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    if question_id:
        entry["question_id"] = question_id
    entries.append(entry)
    save(workspace, entries)
    return entry


def revoke(workspace, ruled_id: str, reason: str, now: datetime | None = None) -> dict:
    """Nimmt einen Punkt zurück, etwa wenn ein Einwand des Teams doch eine Frage nötig macht."""
    reason = str(reason or "").strip()
    if not reason:
        raise RuledError("Ein Punkt wird nur mit Grund zurückgenommen, etwa dem Einwand des Teams.")
    entries = load(workspace)
    found = next((e for e in entries if e["id"] == ruled_id), None)
    if found is None:
        raise RuledError(f"Punkt {ruled_id} gibt es nicht.")
    if found.get("revoked_at"):
        raise RuledError(f"Punkt {ruled_id} ist schon zurückgenommen ({found.get('revoke_reason')}).")
    found.update({"revoked_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                  "revoke_reason": reason})
    save(workspace, entries)
    return found


def visible(workspace) -> list:
    """Die Punkte für `migration.json`: nur die geltenden, nur `id`, `text` und `source`."""
    return [{"id": e["id"], "text": e["text"], "source": e["source"]}
            for e in load(workspace) if not e.get("revoked_at")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.ruled")
    parser.add_argument("command", choices=("add", "revoke", "list"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--id")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "add":
            result = add(args.workspace, args.text, args.source)
        elif args.command == "revoke":
            result = revoke(args.workspace, args.id, args.reason)
        else:
            result = load(args.workspace)
    except RuledError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
