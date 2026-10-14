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
    python3 -m theme.run_state log --run-id <id> --kind <kind> --text <text> [--phase <phase>]
    python3 -m theme.run_state upgrade [--run-id <id>]
    python3 -m theme.run_state claim --force [--run-id <id>]
    python3 -m theme.run_state version [--run-id <id>]

Neben `state.json` liegt `journal.jsonl`: eine Zeile je Ereignis mit Zeitstempel.
`phase`, `gate` und `set` schreiben ihr Ereignis selbst, `log` hält fest, was
sonst nur im Gespräch stünde: jede Frage an das Team, jede Wartezeit auf einen
Menschen, jeden Fehler, jede Handarbeit. Der Stand sagt, wo ein Lauf steht, das
Journal, wie er dorthin kam und wo er Zeit verloren hat. Eingeführt im Oktober
2026, als sich aus Stand und Commits nicht ablesen ließ, warum ein Lauf acht
Stunden in Phase 2 stand.

Seit dem 08.10.2026 hängt der Lauf an der einen Liste offener Punkte
(`migration/open-items.json`, Modul `open_items`). `init` legt sie an. Ein Gate
hält an, es fragt nicht: `gate` verweigert G4 und G5, solange ein Punkt ihres
Gates offen ist oder eine Quelle (Prüfliste, Prüfbericht, Abnahme) Offenes
hält, das in der Liste fehlt. `phase ... --status done` verweigert Phase 2 ohne
übernommene Prüfliste, Phase 6 mit offenem `blocker` und Phase 10 mit offenem
Punkt für die Zeit nach dem Launch. Vorher lag die Arbeit verteilt auf viele
Listen, und keine davon las ein Schritt, bevor er weiterging.

Seit 0.3.11:

- Nach jedem Befehl schreibt das Modul `migration.json` in den Lauf: die neun Schritte, zwei Meilensteine, die
  offenen Fragen an das Team und die Vorgaben der Marke (Modul `steps`). Das Cockpit liest nur diese Datei.
- Das Team bereitet vor bis "Bereit für die Abnahme". Launch und Nachsorge (Phasen 9 und 10), die Gates G4 und
  G5 und `published_at` setzt nur der Betreiber (`PTAI_OPERATOR=1`). Einen Änderungsstopp gibt es nicht mehr;
  vor dem Launch wird der Stand des Live-Themes neu gezogen.
- Die Abnahme (Phase `8-test-round`) beginnt erst, wenn der Meilenstein "Bereit für die Abnahme" erfüllt ist.
- G1 und G2 verweigern, solange eine Frage ihres Gates offen ist (Modul `questions`), und ein Gate trägt den
  Namen einer Person, keinen Sammelnamen.
- Eine Sitzung je Lauf: `session.lock` mit `CLAUDE_CODE_SESSION_ID`. Eine zweite Sitzung schreibt nicht, solange
  die Sperre jünger als zwei Stunden ist; Übernahme mit `claim --force`.
- `plugin_version` steht im Stand und in jedem Journal-Eintrag. `upgrade` hebt einen älteren Lauf an.

Seit 0.3.14 prüft `version` zu Beginn jeder Sitzung, ob der Lauf aus einer neueren Version des Plugins stammt
als der installierten, etwa weil eine andere Person mit einem neueren Plugin weitergearbeitet hat. Dann hält
die Sitzung an, bis das Plugin aktualisiert ist; sonst schriebe die ältere Fassung den Lauf mit älteren Regeln
weiter. `version` liest nur: kein `migration.json`, keine Sperre, damit der Arbeitsbaum vor dem `git pull`
sauber bleibt.
"""
import argparse
import json
import os
import platform
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from theme import ConfigError, load_config
from theme import handover, open_items, questions, ruled, steps

PHASES = (
    "0-setup", "1-snapshot", "2-inventory", "3-mapping", "4-build", "5-upload",
    "6-verify", "7-sync", "8-test-round", "9-launch", "10-aftercare",
)
#: Namen vor 0.3.11; `upgrade` benennt sie um.
RENAMED_PHASES = {"7-sync-1": "7-sync", "8-acceptance": "8-test-round"}
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
KEYS = ("live_theme_id", "draft_theme_id", "snapshot", "last_sync", "published_at", "policies_version",
        "policies_applied_at")
#: Werte vor 0.3.11, die `upgrade` entfernt: es gibt keinen Änderungsstopp mehr.
DROPPED_KEYS = ("freeze_from", "freeze_until")

#: Was nur der Betreiber setzt. Das Team bereitet vor bis "Bereit für die Abnahme".
OPERATOR_PHASES = ("9-launch", "10-aftercare")
OPERATOR_GATES = ("G4-acceptance", "G5-go-live")
OPERATOR_KEYS = ("published_at",)
#: Gates, die offene Fragen an das Team anhalten.
QUESTION_GATES = ("G1-decisions", "G2-mapping")
LOCK_MAX_AGE_SECONDS = 2 * 60 * 60

# Arten eines Journal-Eintrags über `log`.
LOG_KINDS = ("question", "answer", "wait", "manual", "error", "note")


class StateError(Exception):
    """Ein Stand, der so nicht weitergehen darf."""


def is_operator() -> bool:
    """Betreiber-Modus: nur für Launch, Nachsorge und die Gates G4 und G5."""
    return os.environ.get("PTAI_OPERATOR") == "1"


def plugin_version() -> str:
    """Die installierte Version aus `.claude-plugin/plugin.json`."""
    try:
        manifest = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
        return json.loads(manifest.read_text(encoding="utf-8")).get("version") or "unbekannt"
    except (OSError, json.JSONDecodeError):
        return "unbekannt"


def _operator_only(what: str) -> StateError:
    return StateError(f"{what} macht der Betreiber, nicht das Team. Die Vorbereitung endet bei "
                      "\"Bereit für die Abnahme\"; Termin, Launch und Nachsorge übernimmt der Betreiber.")


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
        if phase in RENAMED_PHASES:
            raise StateError(f"Phase {phase} heißt seit 0.3.11 {RENAMED_PHASES[phase]}; zuerst run_state upgrade.")
        if phase not in PHASES:
            raise StateError(f"unbekannte Phase: {phase!r}")
        if status not in PHASE_STATUS:
            raise StateError(f"unbekannter Status: {status!r}")
        if phase in OPERATOR_PHASES and status in ("running", "done") and not is_operator():
            raise _operator_only(f"Phase {phase}")
        if phase == "8-test-round" and status in ("running", "done"):
            ready = steps.compute(self.workspace, self._data)["ready_for_test_round"]
            if not ready["met"]:
                missing = [f"{c['key']} ({c['note']})" if c.get("note") else c["key"]
                           for c in ready["conditions"] if not c["met"]]
                raise StateError("Die Abnahme beginnt erst, wenn der Entwurf bereit für die Abnahme ist. "
                                 "Es fehlt: " + "; ".join(missing or ["Schritte 1 bis 5 erledigt"]))
        if status in ("running", "done"):
            blocking = self.open_gate_before(phase)
            if blocking:
                raise StateError(
                    f"Phase {phase} darf erst beginnen, wenn Gate {blocking} entschieden ist."
                )
        if status == "done" and phase in PHASE_GUARDS:
            check_open_items(self.workspace, phase=phase)
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
        if gate in OPERATOR_GATES and not is_operator():
            raise _operator_only(f"Gate {gate}")
        try:
            decided_by = questions.check_person(self.workspace, decided_by)
        except questions.QuestionError as error:
            raise StateError(str(error)) from error
        if gate in QUESTION_GATES:
            pending = questions.open_for(self.workspace, gate)
            if pending:
                raise StateError(f"Gate {gate} hält an: {len(pending)} Fragen an das Team offen "
                                 f"({_short([q['id'] for q in pending])}). Antworten aus dem Cockpit mit "
                                 "questions import übernehmen oder in der Sitzung mit questions answer eintragen.")
        if gate in open_items.GATE_READS:
            check_open_items(self.workspace, gate=gate)
        stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        self._data["gates"][gate] = {"decided_by": decided_by, "decided_at": stamp, "note": note}

    def set_value(self, key: str, value) -> None:
        if key in DROPPED_KEYS:
            raise StateError(f"{key} gibt es seit 0.3.11 nicht mehr: kein Änderungsstopp, vor dem Launch wird "
                             "der Stand des Live-Themes neu gezogen.")
        if key not in KEYS:
            raise StateError(f"unbekannter Schlüssel: {key!r}, erlaubt sind {KEYS}")
        if key in OPERATOR_KEYS and not is_operator():
            raise _operator_only(f"Der Wert {key}")
        self._data["values"][key] = value

    def upgrade(self) -> list:
        """Hebt einen Lauf aus einer älteren Version an. Gibt zurück, was sich geändert hat."""
        changes = []
        for old, new_name in RENAMED_PHASES.items():
            if old in self._data["phases"]:
                self._data["phases"][new_name] = self._data["phases"].pop(old)
                changes.append(f"Phase {old} heißt jetzt {new_name}")
        self._data["phases"] = {p: self._data["phases"].get(p, "open") for p in PHASES}
        for key in DROPPED_KEYS:
            if key in self._data["values"]:
                changes.append(f"{key}={self._data['values'].pop(key)} entfernt (kein Änderungsstopp)")
        if self._data.get("plugin_version") != plugin_version():
            changes.append(f"Plugin-Version {self._data.get('plugin_version') or 'unbekannt'} -> {plugin_version()}")
        return changes

    def next_phase(self) -> str | None:
        """Die erste Phase, die weder fertig noch übersprungen ist."""
        for phase in PHASES:
            if self._data["phases"][phase] not in ("done", "skipped"):
                return phase
        return None

    def summary(self) -> dict:
        nxt = self.next_phase()
        try:
            items = open_items.load(self.workspace).counts()
        except open_items.OpenItemsError as error:
            items = {"error": str(error)}
        try:
            computed = steps.compute(self.workspace, self._data)
            step_view = {"current_step": computed["current_step"],
                         "steps": {s["key"]: s["status"] for s in computed["steps"]},
                         "ready_for_test_round": computed["ready_for_test_round"]["met"],
                         "ready_for_launch": computed["ready_for_launch"]["met"],
                         "open_questions": sum(1 for q in computed["questions"] if q["answer"] is None)}
        except (questions.QuestionError, open_items.OpenItemsError) as error:
            step_view = {"error": str(error)}
        return {
            "run_id": self.run_id,
            "plugin_version": self._data.get("plugin_version"),
            "operator": is_operator(),
            **step_view,
            "next_phase": nxt,
            "blocked_by": self.open_gate_before(nxt) if nxt else None,
            "phases": self._data["phases"],
            "gates": {g: bool(v) for g, v in self._data["gates"].items()},
            "values": self._data["values"],
            "open_items": items,
        }

    def log(self, kind: str, text: str, phase: str | None = None, now: datetime | None = None,
            **extra) -> dict:
        """Hängt ein Ereignis an `journal.jsonl` an. Nie umschreiben, nur anhängen."""
        if kind not in LOG_KINDS + ("phase", "gate", "set"):
            raise StateError(f"unbekannte Art: {kind!r}, erlaubt sind {LOG_KINDS}")
        if phase is not None and phase not in PHASES:
            raise StateError(f"unbekannte Phase: {phase!r}")
        entry = {"at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), "kind": kind,
                 "phase": phase or self.current_phase(), "text": text, "plugin_version": plugin_version(),
                 **extra}
        path = journal_path(self.workspace, self.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def current_phase(self) -> str | None:
        """Die laufende Phase, sonst die nächste offene."""
        for phase in PHASES:
            if self._data["phases"][phase] == "running":
                return phase
        return self.next_phase()

    def save(self) -> Path:
        self._data["plugin_version"] = plugin_version()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.parent / (self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path


#: Phasen, die erst mit der Liste offener Punkte als erledigt gelten, und was ihr Abschluss verlangt.
PHASE_GUARDS = {
    "2-inventory": "Prüfliste aus Phase 2 in der Liste",
    "6-verify": "kein offener blocker, jüngster Prüfbericht in der Liste",
    "10-aftercare": "kein offener Punkt für die Zeit nach dem Launch",
}


def _short(items: list, limit: int = 8) -> str:
    text = ", ".join(items[:limit])
    return text + (f" und {len(items) - limit} weitere" if len(items) > limit else "")


def check_open_items(workspace: Path, *, phase: str | None = None, gate: str | None = None) -> None:
    """Hält eine Phase oder ein Gate an, solange die Liste offener Punkte es verlangt. Fragt nie."""
    try:
        items = open_items.load(workspace)
    except open_items.OpenItemsError as error:
        raise StateError(f"{error}. Ohne die Liste geht kein Gate und kein Abschluss weiter.") from error
    try:
        config = load_config(workspace)
    except ConfigError as error:
        raise StateError(str(error)) from error
    hint = "erledigen mit open_items done --id <id> --evidence <text> oder verschieben mit open_items defer"
    if phase == "2-inventory":
        result = open_items.source_gaps(items, workspace, config, migration=True, kinds=("checklist",))
        if not any(s.endswith("(checklist)") for s in result["sources"]):
            raise StateError("Phase 2 ist erst fertig mit der Prüfliste aus der Bestandsaufnahme: "
                             + ("; ".join(result["gaps"]) or "keine Punkte - [ ] **P01** gefunden")
                             + ". Pfad in theme_migration.acceptance_checklist eintragen.")
        if result["missing"]:
            raise StateError("Prüfliste nicht in der Liste offener Punkte: "
                             + _short([m["id"] for m in result["missing"]])
                             + ". Übernehmen mit open_items import --kind checklist --path <prüfliste>.")
        return
    if phase == "6-verify":
        blockers = [i["id"] for i in items.items if i["status"] == "open" and i["severity"] == "blocker"]
        result = open_items.source_gaps(items, workspace, config, kinds=("findings",))
        if blockers:
            raise StateError(f"Phase 6 ist erst fertig ohne offenen blocker: {_short(blockers)}; {hint}.")
        if result["missing"]:
            raise StateError("Befunde aus verify-theme nicht in der Liste: "
                             + _short([f"{m['source']}: {m['id']}" for m in result["missing"]])
                             + ". Übernehmen mit open_items import --kind findings --path <findings.json>.")
        return
    if phase == "10-aftercare":
        pending = [i["id"] for i in items.blocking("after_launch")]
        if pending:
            raise StateError(f"Nachsorge ist erst fertig ohne offenen Punkt: {_short(pending)}; {hint}.")
        return
    if gate:
        blocking = [f"{i['id']} {i['title'][:50]}" for i in items.blocking(gate)]
        result = open_items.source_gaps(items, workspace, config, migration=True)
        problems = []
        if blocking:
            problems.append(f"{len(blocking)} offen: {_short(blocking)}; {hint}")
        if result["missing"]:
            problems.append("offen in einer Quelle, nicht in der Liste: "
                            + _short([f"{m['source']}: {m['id']}" for m in result["missing"]])
                            + "; übernehmen mit open_items import")
        if result["gaps"]:
            problems.append("Quelle fehlt oder ist nicht lesbar: " + "; ".join(result["gaps"]))
        if problems:
            raise StateError(f"Gate {gate} hält an. " + " | ".join(problems))


def lock_path(workspace: Path, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / "session.lock"


def claim(workspace: Path, run_id: str, *, force: bool = False, now: datetime | None = None) -> dict | None:
    """Hält den Lauf für diese Claude-Sitzung. Verweigert, solange eine andere Sitzung ihn hält.

    Ohne `CLAUDE_CODE_SESSION_ID` (Aufruf von Hand, nicht aus Claude Code) gibt es keine Sperre.
    Zurück kommt die Sperre einer anderen Sitzung, die mit `force` übernommen wurde, sonst `None`.
    """
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session:
        return None
    moment = now or datetime.now(timezone.utc)
    path = lock_path(workspace, run_id)
    other = None
    if path.is_file():
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            held = {}
        last = held.get("last_seen")
        try:
            age = (moment - datetime.fromisoformat(last)).total_seconds() if last else None
        except ValueError:
            age = None
        if held.get("session_id") and held["session_id"] != session and age is not None \
                and age < LOCK_MAX_AGE_SECONDS:
            if not force:
                raise StateError(
                    f"Eine andere Claude-Sitzung arbeitet an diesem Lauf (zuletzt {last} auf "
                    f"{held.get('host') or 'einem anderen Rechner'}). Nur eine Sitzung je Lauf: die andere "
                    "Sitzung schließen oder diese mit run_state claim --force übernehmen.")
            other = held
        started = held.get("started_at") if held.get("session_id") == session else None
    else:
        started = None
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = moment.isoformat(timespec="seconds")
    path.write_text(json.dumps({"session_id": session, "host": platform.node(), "started_at": started or stamp,
                                "last_seen": stamp}, ensure_ascii=False) + "\n", encoding="utf-8")
    _ignore_lock(workspace)
    return other


def _ignore_lock(workspace: Path) -> None:
    """Die Sperre gehört nicht ins Repo."""
    line = "reporting/runs/*/session.lock"
    path = Path(workspace) / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if line not in text.splitlines():
        path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + line + "\n", encoding="utf-8")


def migration_path(workspace: Path, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / "migration.json"


def export(workspace: Path, state: "MigrationState") -> Path:
    """Schreibt `migration.json`: Schritte, Meilensteine, Fragen und Vorgaben für Cockpit und Claude."""
    data = steps.export(workspace, state.data, plugin_version())
    path = migration_path(workspace, state.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _drop_freeze_from_config(workspace: Path) -> bool:
    """Entfernt `theme_migration.freeze` aus der Config, falls vorhanden."""
    path = Path(workspace) / "reporting" / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    block = config.get("theme_migration")
    if not isinstance(block, dict) or "freeze" not in block:
        return False
    del block["freeze"]
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return True


def state_path(workspace: Path, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / "state.json"


def journal_path(workspace: Path, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / "journal.jsonl"


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


def needs_upgrade(state: MigrationState) -> bool:
    return any(old in state.data["phases"] for old in RENAMED_PHASES) or \
        any(key in state.data.get("values", {}) for key in DROPPED_KEYS)


def latest_run_id(workspace: Path) -> str | None:
    runs = Path(workspace) / "reporting" / "runs"
    if not runs.is_dir():
        return None
    found = sorted(p.name for p in runs.iterdir() if p.name.endswith("-migration")
                   and (p / "state.json").is_file())
    return found[-1] if found else None


def _version_key(value) -> tuple | None:
    """`0.3.14` als `(0, 3, 14)`; `None`, wenn die Version nicht lesbar ist."""
    parts = str(value or "").strip().split(".")
    return tuple(int(p) for p in parts) if parts and all(p.isdigit() for p in parts) else None


def version_status(workspace: Path, run_id: str | None = None) -> dict:
    """Ob der Lauf aus einer neueren Version des Plugins stammt als der installierten. Liest nur."""
    run_id = run_id or latest_run_id(workspace)
    run_version = load(workspace, run_id).data.get("plugin_version") if run_id else None
    installed = plugin_version()
    ran, have = _version_key(run_version), _version_key(installed)
    outdated = bool(ran and have and ran > have)
    return {"run_id": run_id, "run_version": run_version, "installed_version": installed,
            "plugin_outdated": outdated,
            "hint": (f"Der Lauf stammt aus ptai-ecom {run_version}, installiert ist {installed}. Erst das Plugin "
                     "aktualisieren, dann weiterarbeiten.") if outdated else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.run_state")
    parser.add_argument("command", choices=("show", "init", "phase", "gate", "set", "log", "upgrade", "claim",
                                            "version"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--run-id")
    parser.add_argument("--phase")
    parser.add_argument("--status")
    parser.add_argument("--gate")
    parser.add_argument("--decided-by", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--key")
    parser.add_argument("--value")
    parser.add_argument("--kind")
    parser.add_argument("--text", default="")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    if args.command == "version":
        try:
            status = version_status(workspace, args.run_id)
        except (StateError, FileNotFoundError) as error:
            print(json.dumps({"error": str(error)}, ensure_ascii=False))
            return 2
        print(json.dumps(status, ensure_ascii=False))
        # 1 heißt Befund: das Plugin ist älter als der Lauf.
        return 1 if status["plugin_outdated"] else 0
    try:
        if args.command == "init":
            run_id = args.run_id or default_run_id()
            if state_path(workspace, run_id).exists():
                raise StateError(f"Stand für {run_id} existiert schon, weiter mit show.")
            state = new(workspace, run_id)
            claim(workspace, run_id)
            state.save()
            state.log("phase", "init")
            # Regel 4: jede Migration läuft als Lauf, und ab dem ersten Schritt gibt es die eine Liste.
            open_items.init(workspace)
        else:
            run_id = args.run_id or latest_run_id(workspace)
            if not run_id:
                raise StateError("Kein Migrations-Lauf gefunden, zuerst init.")
            state = load(workspace, run_id)
            if args.command == "upgrade":
                changes = state.upgrade()
                if _drop_freeze_from_config(workspace):
                    changes.append("theme_migration.freeze aus der Config entfernt")
                claim(workspace, run_id)
                state.save()
                state.log("note", "upgrade: " + ("; ".join(changes) or "nichts zu tun"))
            elif needs_upgrade(state) and args.command != "show":
                raise StateError("Dieser Lauf stammt aus einer Version vor 0.3.11; zuerst run_state upgrade.")
            elif args.command == "claim":
                if not args.force:
                    raise StateError("claim übernimmt einen Lauf von einer anderen Sitzung nur mit --force.")
                other = claim(workspace, run_id, force=True)
                if other:
                    state.log("note", f"Lauf übernommen von Sitzung {other.get('session_id')} "
                                      f"auf {other.get('host')}")
            elif args.command != "show":
                claim(workspace, run_id)
            if args.command == "phase":
                state.set_phase(args.phase, args.status)
                state.save()
                state.log("phase", args.status, phase=args.phase)
            elif args.command == "gate":
                state.decide_gate(args.gate, args.decided_by, args.note)
                state.save()
                state.log("gate", args.note, gate=args.gate, decided_by=args.decided_by)
            elif args.command == "set":
                state.set_value(args.key, args.value)
                state.save()
                state.log("set", f"{args.key}={args.value}")
            elif args.command == "log":
                if args.kind not in LOG_KINDS:
                    raise StateError(f"--kind muss eines von {LOG_KINDS} sein")
                if not args.text.strip():
                    raise StateError("--text fehlt")
                state.log(args.kind, args.text, phase=args.phase)
    except (StateError, open_items.OpenItemsError, questions.QuestionError, FileNotFoundError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    if needs_upgrade(state):
        print(json.dumps({**state.summary(), "upgrade_needed": True,
                          "hint": "Lauf aus einer Version vor 0.3.11: run_state upgrade"}, ensure_ascii=False))
        return 0
    try:
        export(workspace, state)
    except (questions.QuestionError, open_items.OpenItemsError, ruled.RuledError, handover.HandoverError) as error:
        print(json.dumps({"error": f"migration.json nicht geschrieben: {error}"}, ensure_ascii=False))
        return 2
    print(json.dumps(state.summary(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
