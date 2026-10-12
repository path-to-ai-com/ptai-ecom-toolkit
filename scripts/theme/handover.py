#!/usr/bin/env python3
"""Übergabe einer Sitzung: was jetzt ansteht, was danach passiert, was der Betreiber vorher tun muss.

Seit 0.3.14. Das Cockpit zeigt je Store eine Zeile "Jetzt", einen Absatz "Danach" und, wenn der Betreiber
etwas tun muss, bevor es weitergeht, seine Aufgaben. Diese Sätze kann nur die Sitzung schreiben, die weiß,
was sie getan hat und was als Nächstes kommt; aus dem Stand lassen sie sich nicht berechnen. Deshalb schreibt
die Skill am Ende jeder Sitzung `migration/next.json` neu, in der Sprache des Kunden (ihr, euch), und
`steps.export` übernimmt die Datei in `migration.json`.

Jeder Eintrag trägt den Schritt, in dem er geschrieben wurde. Steht der Lauf inzwischen in einem anderen
Schritt, etwa weil eine Sitzung abbrach, bevor sie die Übergabe schrieb, gilt sie nicht mehr: dann steht
"Jetzt" auf dem Namen des aktuellen Schritts, "Danach" ist leer, Aufgaben gibt es keine. Lieber nichts als
ein Satz aus einem früheren Schritt.

Aufruf:
    python3 -m theme.handover write --now <text> --after <text> [--operator-task <text> ...]
    python3 -m theme.handover show
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


class HandoverError(Exception):
    """Eine Übergabe, die so nicht gilt, oder eine beschädigte Datei."""


def path(workspace) -> Path:
    return Path(workspace) / "migration" / "next.json"


def load(workspace) -> dict | None:
    """Die Übergabe der letzten Sitzung, `None`, wenn es keine gibt."""
    target = path(workspace)
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise HandoverError(f"{target} ist beschädigt ({error}); mit handover write neu schreiben.") from error
    if not isinstance(data, dict) or not isinstance(data.get("now"), str) \
            or not isinstance(data.get("after", ""), str) or not isinstance(data.get("operator_tasks", []), list):
        raise HandoverError(f"{target} hat nicht die Form {{now, after, operator_tasks}}; mit handover write "
                            "neu schreiben.")
    return data


def write(workspace, now: str, after: str = "", operator_tasks: list | None = None, step: int | None = None,
          at: datetime | None = None) -> dict:
    """Schreibt die Übergabe neu. `step` ist der aktuelle Schritt des Laufs, 1 bis 9."""
    now = str(now or "").strip()
    if not now:
        raise HandoverError("--now fehlt: der Name des Schritts, an dem die Migration jetzt steht.")
    tasks = [str(t).strip() for t in (operator_tasks or []) if str(t or "").strip()]
    data = {"now": now, "after": str(after or "").strip(), "operator_tasks": tasks, "step": step,
            "written_at": (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    target = path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / (target.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return data


def resolve(workspace, current_step: int, step_name: str) -> dict:
    """`now`, `after` und `operator_tasks` für `migration.json`, mit Rückfall auf den aktuellen Schritt."""
    data = load(workspace)
    if data is None or (isinstance(data.get("step"), int) and data["step"] != current_step):
        return {"now": step_name, "after": "", "operator_tasks": []}
    return {"now": data["now"].strip() or step_name, "after": (data.get("after") or "").strip(),
            "operator_tasks": [t.strip() for t in data.get("operator_tasks") or [] if isinstance(t, str) and t.strip()]}


def current_step(workspace) -> int | None:
    """Der aktuelle Schritt des jüngsten Migrationslaufs, `None` ohne Lauf."""
    # Spät importiert: run_state liest über steps dieses Modul.
    from theme import run_state, steps
    run_id = run_state.latest_run_id(Path(workspace))
    if not run_id:
        return None
    try:
        data = run_state.load(Path(workspace), run_id).data
        return steps.compute(workspace, data, git_status={"met": True, "note": ""})["current_step"]
    except Exception:  # noqa: BLE001 - ohne lesbaren Lauf gilt die Übergabe ohne Schritt
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.handover")
    parser.add_argument("command", choices=("write", "show"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--now", default="")
    parser.add_argument("--after", default="")
    parser.add_argument("--operator-task", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "write":
            result = write(args.workspace, args.now, args.after, args.operator_task,
                           step=current_step(args.workspace))
        else:
            result = load(args.workspace)
    except HandoverError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
