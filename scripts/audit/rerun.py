#!/usr/bin/env python3
"""Eine Disziplin nachlaufen lassen, ohne den Lauf drumherum zu verlieren.

**Wofür.** Ein Audit besteht aus Einzelanalysen, und der Gesamtreport steht
auf allen zusammen. Fehlte einer Analyse ein Zugang, steht sie als "fehlt" im
Report, und aus ihrer Lücke ist meist eine Maßnahme geworden ("Zugang
einrichten"). Kommt der Zugang später, läuft nur diese eine Analyse neu, und
ihr Ergebnis muss in denselben Lauf zurück: in die Befunde, in den Backlog und
in den Gesamtreport. Ein Ordner daneben reicht nicht, den liest niemand mit.

**Die Kennungen sind die Naht.** Eine Maßnahme zeigt über `finding_ref` (v1)
oder `finding_run` und `finding_id` (Liste einer Marke) auf einen Befund. Nummeriert die neue Analyse wieder ab 01, zeigt die alte
Maßnahme auf einen fremden Befund, und im Portal stünde unter "Lesezugang
einrichten" plötzlich die Analyse der Conversion-Aktionen. Im ersten Nachlauf
überhaupt, am 02.10.2026, hatte die Analyse genau so wieder ab 01 gezählt;
aufgefallen ist es vor dem Hochladen. Deshalb gilt:

- Ein Befund, der weiter gilt, behält seine Kennung und seine Aussage.
- Ein neuer Befund bekommt eine Kennung hinter der höchsten bisherigen.
- Ein Befund, der wegfällt, nimmt seine Maßnahmen nicht stillschweigend mit:
  sie werden als verwaist gemeldet, und die Sitzung entscheidet je Maßnahme,
  ob sie erledigt ist (der Nachlauf hat die Lücke geschlossen) oder hinfällig.

`check_ids()` erzwingt die ersten beiden Regeln, `orphaned_measures()` liefert
die dritte als Liste. Was daraus folgt, entscheidet die Skill, nicht dieses
Modul: ob eine Maßnahme erledigt ist, ist ein Urteil über den Shop.

CLI:
    python3 -m audit.rerun --workspace . --run-id 2026-09-08-audit \\
        --discipline sea --previous reporting/runs/<run-id>/revisions/05/findings/sea.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from audit import brand as brand_mod
from audit import measures

#: Maßnahmen in diesen Zuständen hat noch niemand abgeschlossen. Nur sie können
#: verwaisen; eine erledigte oder verworfene Maßnahme bleibt, wie sie ist.
OPEN_STATUS = ("open", "in_progress")

_ID = re.compile(r"^([A-Z]+)-(\d+)$")


def _number(finding_id: str) -> int | None:
    match = _ID.match(finding_id or "")
    return int(match.group(2)) if match else None


def _findings(document: dict | None) -> list[dict]:
    return list((document or {}).get("findings") or [])


def check_ids(previous: dict, current: dict) -> None:
    """Wirft, wenn eine Kennung der neuen Fassung einen anderen Befund meint.

    Erlaubt ist eine Kennung aus der vorigen Fassung nur mit derselben
    Aussage (`statement`), denn dann ist es derselbe Befund. Jede andere
    Kennung muss hinter der höchsten bisherigen liegen. Doppelte Kennungen
    innerhalb der neuen Fassung sind immer ein Fehler.
    """
    before = {f["id"]: f for f in _findings(previous)}
    highest = max((n for n in map(_number, before) if n is not None), default=0)
    seen = set()
    problems = []
    for finding in _findings(current):
        fid = finding.get("id")
        if fid in seen:
            problems.append(f"{fid} steht zweimal in der neuen Fassung")
            continue
        seen.add(fid)
        if fid in before:
            if before[fid].get("statement") != finding.get("statement"):
                problems.append(
                    f"{fid} hieß vorher \"{before[fid].get('statement')}\" und jetzt "
                    f"\"{finding.get('statement')}\". Ein geänderter Befund bekommt "
                    f"eine neue Kennung ab {highest + 1:02d}")
        elif (_number(fid) or 0) <= highest:
            problems.append(
                f"{fid} ist neu, liegt aber nicht hinter der höchsten bisherigen "
                f"Kennung ({highest:02d})")
    if problems:
        raise ValueError("Kennungen der neuen Fassung passen nicht zur vorigen:\n- "
                         + "\n- ".join(problems))


def new_findings(previous: dict, current: dict) -> list[dict]:
    """Die Befunde, die es in der vorigen Fassung nicht gab. Nur sie gehen
    durch `measures.create()`, sonst entsteht jede Maßnahme ein zweites Mal."""
    before = {f["id"] for f in _findings(previous)}
    return [f for f in _findings(current) if f.get("id") not in before]


def dropped_findings(previous: dict, current: dict) -> list[dict]:
    """Die Befunde der vorigen Fassung, die in der neuen fehlen."""
    now = {f.get("id") for f in _findings(current)}
    return [f for f in _findings(previous) if f["id"] not in now]


def orphaned_measures(backlog: dict, previous: dict, current: dict,
                      shop: str | None = None,
                      run_id: str | None = None) -> list[dict]:
    """Offene Maßnahmen, deren Befund in der neuen Fassung fehlt.

    Jede davon braucht ein Urteil: erledigt, weil der Nachlauf die Lücke
    geschlossen hat, oder hinfällig, weil die Analyse den Befund nicht mehr
    trägt. Beides geht über `measures.set_status()` mit `run_id` und `note`,
    damit im Portal steht, woran es gemessen wurde.

    **In der Liste einer Marke** sind Befund-IDs nur innerhalb eines Laufs
    eindeutig: CRO-03 in EU ist ein anderer Befund als CRO-03 in UK. Verwaist
    ist deshalb nur eine Maßnahme dieses Stores (`shop`), deren Befund aus
    genau diesem Lauf stammt (`finding_run == run_id`, `finding_id`), und
    zurück kommt ihre Sicht auf diesen Store (`measures.project()`).
    """
    gone = {f["id"] for f in dropped_findings(previous, current)}
    backlog = backlog or {}
    if measures.is_v2(backlog):
        if not shop or not run_id:
            raise ValueError("In der Liste einer Marke braucht orphaned_measures() "
                             "den Store und den Lauf (shop, run_id).")
        return [m for m in measures.project(backlog, shop)["measures"]
                if m.get("finding_run") == run_id
                and m.get("finding_id") in gone
                and m.get("status") in OPEN_STATUS]
    return [m for m in backlog.get("measures") or []
            if m.get("finding_ref") in gone and m.get("status") in OPEN_STATUS]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Prüft den Nachlauf einer Disziplin gegen die vorige Fassung.")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--discipline", required=True,
                        help="Dateiname der Befunde ohne .json, etwa sea")
    parser.add_argument("--previous", required=True,
                        help="die Befund-Datei der vorigen Fassung")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace)
    current_path = (workspace / "reporting" / "runs" / args.run_id / "findings"
                    / f"{args.discipline}.json")
    previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    current = json.loads(current_path.read_text(encoding="utf-8"))
    backlog = measures.peek(workspace)
    shop = brand_mod.shop_slug(brand_mod.read_config(workspace))

    try:
        check_ids(previous, current)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    print("Neue Befunde, je ein Aufruf von measures.create():")
    for finding in new_findings(previous, current):
        print(f"  {finding['id']}  {finding.get('statement')}")
    print("Weggefallene Befunde:")
    for finding in dropped_findings(previous, current):
        print(f"  {finding['id']}  {finding.get('statement')}")
    print("Verwaiste Maßnahmen, je ein Urteil nötig (implemented oder obsolete):")
    for measure in orphaned_measures(backlog, previous, current,
                                     shop=shop, run_id=args.run_id):
        print(f"  {measure['id']}  {measures.finding_of(measure)}  {measure.get('title')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
