#!/usr/bin/env python3
"""Die Befunde eines fertigen Laufs um die Felder des Befund-Vertrags ergänzen.

**Wofür.** Ein Lauf, der vor dem Vertrag `reference/finding-format.md`
entstanden ist, zeigt seine Befunde im Portal als Text. Ihn neu prüfen hieße
neue Kennungen, neue Zahlen und neue Maßnahmen, und die Freigaben und
Rückfragen des Kunden zeigten danach ins Leere. Stattdessen schreibt ein Agent
je Disziplin eine Ergänzungsdatei, und dieses Modul mischt sie ein. Entstanden
für den Piloten vom 02.10.2026 (Portal-Spec `2026-10-02-finding-cards-design.md`,
Abschnitt 22).

**Was es nie tut.** Es ändert keine Aussage, keine Kennzahl, keinen Text,
keine Schwere und keine Kennung. Es nimmt nur die vier Felder `url`, `facts`,
`proof` und `evidence_text` an, und nur dort, wo der Befund sie noch nicht hat
oder denselben Wert trägt. `decision` gehört nicht dazu: im fertigen Lauf
gibt es die Maßnahme schon, und eine nachgereichte Entscheidung zwischen zwei
Wegen ließe den Kunden etwas anderes lesen, als er freigegeben hat.

**Alles oder nichts.** Eine unbekannte Kennung, ein fremdes Feld oder ein
Wert, der einen vorhandenen überschriebe, hält alle Dateien auf, bevor eine
geschrieben ist. Vorher `audit.revision --copy` laufen lassen.

Format einer Ergänzungsdatei, Name wie die Befund-Datei (`conversion.json`):

    {"findings": [{"id": "CRO-01", "facts": [...], "evidence_text": "...",
                   "url": "https://...", "proof": {...}}]}

CLI:
    python3 -m audit.enrich --workspace . --run-id 2026-09-08-audit \\
        --from <ordner mit den ergänzungsdateien> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

#: Die Felder, die eine Ergänzung tragen darf.
FIELDS = ("url", "facts", "proof", "evidence_text")


def merge(findings_doc: dict, enrichment_doc: dict, name: str) -> tuple[dict, list[str], int]:
    """Mischt eine Ergänzung in eine Befund-Datei.

    Rückgabe: das neue Dokument, die Probleme und die Zahl der gesetzten
    Felder. Mit Problemen ist das Dokument unbrauchbar; `main` schreibt dann
    nichts.
    """
    problems = []
    by_id = {f.get("id"): f for f in findings_doc.get("findings") or [] if isinstance(f, dict)}
    additions: dict[str, dict] = {}
    for entry in enrichment_doc.get("findings") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            problems.append(f"{name}: Eintrag ohne id")
            continue
        finding_id = entry["id"]
        if finding_id not in by_id:
            problems.append(f"{name} {finding_id}: keine solche Kennung in der Befund-Datei")
            continue
        if finding_id in additions:
            problems.append(f"{name} {finding_id}: steht zweimal in der Ergänzung")
            continue
        foreign = sorted(k for k in entry if k != "id" and k not in FIELDS)
        if foreign:
            problems.append(f"{name} {finding_id}: Felder, die eine Ergänzung nicht setzen darf: "
                            + ", ".join(foreign))
        fields = {}
        for key in FIELDS:
            if key not in entry:
                continue
            present = by_id[finding_id].get(key)
            if present not in (None, "", []) and present != entry[key]:
                problems.append(f"{name} {finding_id}: {key} ist schon gesetzt und bliebe nicht erhalten")
                continue
            if present != entry[key]:
                fields[key] = entry[key]
        additions[finding_id] = fields

    findings = []
    count = 0
    for finding in findings_doc.get("findings") or []:
        fields = additions.get(finding.get("id")) if isinstance(finding, dict) else None
        if fields:
            finding = {**finding, **fields}
            count += len(fields)
        findings.append(finding)
    return {**findings_doc, "findings": findings}, problems, count


def write_json_atomic(path: Path, data: dict) -> None:
    """Schreibt ganz oder gar nicht, damit ein Abbruch keine halbe Datei hinterlässt."""
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def enrich(workspace, run_id: str, source, dry_run: bool = False) -> dict:
    """Mischt alle Ergänzungsdateien aus `source` in die Befunde des Laufs.

    Rückgabe `{"files": {name: gesetzte Felder}, "problems": [...]}`. Gibt es
    Probleme, ist nichts geschrieben.
    """
    findings_dir = Path(workspace) / "reporting" / "runs" / run_id / "findings"
    if not findings_dir.is_dir():
        raise SystemExit(f"Kein Befund-Ordner unter {findings_dir}")
    results, problems, counts = {}, [], {}
    for path in sorted(Path(source).glob("*.json")):
        target = findings_dir / path.name
        if not target.exists():
            problems.append(f"{path.name}: keine Befund-Datei dieses Namens im Lauf")
            continue
        try:
            enrichment = json.loads(path.read_text(encoding="utf-8"))
            findings_doc = json.loads(target.read_text(encoding="utf-8"))
        except ValueError as exc:
            problems.append(f"{path.name}: kein gültiges JSON ({exc})")
            continue
        doc, file_problems, count = merge(findings_doc, enrichment, path.name)
        problems += file_problems
        results[target] = doc
        counts[path.name] = count
    if not problems and not dry_run:
        for target, doc in results.items():
            write_json_atomic(target, doc)
    return {"files": counts, "problems": problems}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--from", dest="source", required=True, help="Ordner mit den Ergänzungsdateien")
    parser.add_argument("--dry-run", action="store_true", help="nur prüfen, nichts schreiben")
    args = parser.parse_args(argv)

    result = enrich(args.workspace, args.run_id, args.source, dry_run=args.dry_run)
    for name, count in result["files"].items():
        print(f"{name}: {count} Felder")
    if result["problems"]:
        print("Nichts geschrieben:", file=sys.stderr)
        for problem in result["problems"]:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("Nur geprüft, nichts geschrieben." if args.dry_run else "Eingemischt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
