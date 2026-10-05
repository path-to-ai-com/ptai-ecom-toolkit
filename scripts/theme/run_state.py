#!/usr/bin/env python3
"""Stand einer Theme-Migration: Phasen, Gates, Theme-IDs.

Eigenes Modul statt `audit.state`, weil eine Migration andere Phasen hat und
Gates, die ein Mensch entscheidet. Der Audit-Stand zählt bezahlte Quellen, der
Migrations-Stand hält fest, wer wann was freigegeben hat. Beides in eine Datei
zu zwingen, hätte das Audit-Modul für einen fremden Zweck verbogen.

Wie dort gilt: genau ein Prozess schreibt diesen Stand, der Orchestrator
`theme-migration`. Geschrieben wird atomar.

Aufruf:
    python3 -m theme.run_state show [--run-id <id>]
    python3 -m theme.run_state init --run-id <id>
    python3 -m theme.run_state phase --run-id <id> --phase <phase> --status <status>
    python3 -m theme.run_state gate --run-id <id> --gate <gate> --decided-by <name> [--note <text>]
    python3 -m theme.run_state set --run-id <id> --key <key> --value <value>
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PHASES = (
    "0-setup", "1-snapshot", "2-inventory", "3-mapping", "4-build", "5-upload",
    "6-verify", "7-sync-1", "8-acceptance", "9-launch", "10-aftercare",
)
PHASE_STATUS = ("open", "running", "done", "failed", "skipped")

# Gate und die Phase, die erst danach beginnen darf.
GATES = {
    "G1-decisions": "3-mapping",
    "G2-mapping": "4-build",
    "G3-first-upload": "5-upload",
    "G4-acceptance": "9-launch",
    "G5-go-live": "10-aftercare",
}

# Werte, die neben Phasen und Gates im Stand stehen dürfen.
KEYS = ("live_theme_id", "draft_theme_id", "snapshot", "last_sync", "freeze_from",
        "freeze_until", "published_at")


class StateError(Exception):
    """Ein Stand, der so nicht weitergehen darf."""


class MigrationState:
    def __init__(self, workspace: Path, data: dict):
        self.workspace = Path(workspace)
        self._data = data

    @property
    def run_id(self) -> str:
        return self._data["run_id"]

    @property
    def data(self) -> dict:
        return self._data

    @property
    def path(self) -> Path:
        return state_path(self.workspace, self.run_id)

    def set_phase(self, phase: str, status: str) -> None:
        """Setzt eine Phase. `running` und `done` nur, wenn das Gate davor entschieden ist."""
        if phase not in PHASES:
            raise StateError(f"unbekannte Phase: {phase!r}")
        if status not in PHASE_STATUS:
            raise StateError(f"unbekannter Status: {status!r}")
        if status in ("running", "done"):
            blocking = self.open_gate_before(phase)
            if blocking:
                raise StateError(
                    f"Phase {phase} darf erst beginnen, wenn Gate {blocking} entschieden ist."
                )
        self._data["phases"][phase] = status

    def open_gate_before(self, phase: str) -> str | None:
        """Das erste nicht entschiedene Gate, das vor dieser Phase liegt."""
        index = PHASES.index(phase)
        for gate, gated_phase in GATES.items():
            if PHASES.index(gated_phase) <= index and not self._data["gates"][gate]:
                return gate
        return None

    def decide_gate(self, gate: str, decided_by: str, note: str = "",
                    now: datetime | None = None) -> None:
        """Hält fest, wer ein Gate wann entschieden hat. Ohne Namen keine Entscheidung."""
        if gate not in GATES:
            raise StateError(f"unbekanntes Gate: {gate!r}")
        if not decided_by.strip():
            raise StateError("Ein Gate braucht den Namen der Person, die entschieden hat.")
        stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        self._data["gates"][gate] = {"decided_by": decided_by, "decided_at": stamp, "note": note}

    def set_value(self, key: str, value) -> None:
        if key not in KEYS:
            raise StateError(f"unbekannter Schlüssel: {key!r}, erlaubt sind {KEYS}")
        self._data["values"][key] = value

    def next_phase(self) -> str | None:
        """Die erste Phase, die weder fertig noch übersprungen ist."""
        for phase in PHASES:
            if self._data["phases"][phase] not in ("done", "skipped"):
                return phase
        return None

    def summary(self) -> dict:
        nxt = self.next_phase()
        return {
            "run_id": self.run_id,
            "next_phase": nxt,
            "blocked_by": self.open_gate_before(nxt) if nxt else None,
            "phases": self._data["phases"],
            "gates": {g: bool(v) for g, v in self._data["gates"].items()},
            "values": self._data["values"],
        }

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.parent / (self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path


def state_path(workspace: Path, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / "state.json"


def default_run_id(today: date | None = None) -> str:
    return f"{(today or date.today()).isoformat()}-migration"


def new(workspace: Path, run_id: str) -> MigrationState:
    return MigrationState(workspace, {
        "run_id": run_id,
        "kind": "migration",
        "phases": {p: "open" for p in PHASES},
        "gates": {g: None for g in GATES},
        "values": {},
    })


def load(workspace: Path, run_id: str) -> MigrationState:
    path = state_path(workspace, run_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise StateError(
            f"{path} ist beschädigt ({error}). Der Stand wird nicht still neu angelegt, "
            "weil sonst die festgehaltenen Freigaben verloren gingen."
        ) from error
    if data.get("kind") != "migration":
        raise StateError(f"{path} ist kein Migrations-Stand.")
    return MigrationState(workspace, data)


def latest_run_id(workspace: Path) -> str | None:
    runs = Path(workspace) / "reporting" / "runs"
    if not runs.is_dir():
        return None
    found = sorted(p.name for p in runs.iterdir() if p.name.endswith("-migration")
                   and (p / "state.json").is_file())
    return found[-1] if found else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.run_state")
    parser.add_argument("command", choices=("show", "init", "phase", "gate", "set"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--run-id")
    parser.add_argument("--phase")
    parser.add_argument("--status")
    parser.add_argument("--gate")
    parser.add_argument("--decided-by", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--key")
    parser.add_argument("--value")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    try:
        if args.command == "init":
            run_id = args.run_id or default_run_id()
            if state_path(workspace, run_id).exists():
                raise StateError(f"Stand für {run_id} existiert schon, weiter mit show.")
            state = new(workspace, run_id)
            state.save()
        else:
            run_id = args.run_id or latest_run_id(workspace)
            if not run_id:
                raise StateError("Kein Migrations-Lauf gefunden, zuerst init.")
            state = load(workspace, run_id)
            if args.command == "phase":
                state.set_phase(args.phase, args.status)
                state.save()
            elif args.command == "gate":
                state.decide_gate(args.gate, args.decided_by, args.note)
                state.save()
            elif args.command == "set":
                state.set_value(args.key, args.value)
                state.save()
    except (StateError, FileNotFoundError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(state.summary(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
