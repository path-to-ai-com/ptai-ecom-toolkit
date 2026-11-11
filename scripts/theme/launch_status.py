"""Der Launch einer Migration, wie das Cockpit ihn zeigt: Go-Liste, Ablauf und Rückfall.

Eingeführt am 10.11.2026. Für den ersten Launch nach dem geführten Ablauf musste er als eigene Seite
neben dem Cockpit gebaut werden: welche Go-Punkte grün sind, wer was bis wann tut, wann zurückgeschaltet
wird. Das Cockpit zeigte nur vier Bedingungen von "Bereit für den Launch". Jetzt trägt `migration.json`
(Modul `steps`) einen Block `launch` mit drei Teilen:

- **Go-Liste** (`check`, nach dem Veröffentlichen `check_after`): das jüngste Ergebnis von `launch-check`
  dieses Laufs, je Punkt `id`, `group`, `title`, `status`, eine Zeile Beleg (`evidence`), was zu tun ist
  (`todo`, Frage oder Handlung) und wer (`owner`), dazu die Summe "x von y grün". Was für diesen Launch
  nicht zutrifft, steht nur mit Titel in `not_applicable`, wie unter der Haken-Liste von `launch check`.
- **Ablauf** (`flow`): Vorbereiten, Prüfen, Go, Veröffentlichen, Prüfen danach, Beobachten, je Schritt
  Stand, Zuständige und eine Notiz, berechnet aus Stand, Gate G5 und den Launch-Checks.
- **Rückfall** (`rollback`): das alte Theme, die Kriterien, die das Team vor dem Launch festgelegt hat
  (`migration/rollback.json`, geschrieben mit `launch rollback`), wer im Ernstfall entscheidet, und was
  ein Rückfall nicht zurückdreht (`reference/theme-migration/rollback.md`).

Liest nur. Importiert bewusst weder `launch_check` noch `run_state`: `run_state` importiert `steps`, und
`steps` importiert dieses Modul. Die Statuswerte und Zuständigen von `launch_check` stehen deshalb hier
noch einmal; ein Test hält beide gleich.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: Statuswerte eines Punkts im Launch-Check, wie `launch_check.OK` usw.
OK, MISSING, BLOCKED, MANUAL, NA = "ok", "missing", "blocked", "manual", "n/a"
#: Zuständige im Launch-Check, wie `launch_check.OPERATOR`, `TEAM`, `BOTH`. "Betreiber" heißt seit 0.3.27
#: die Sitzung des Teams, also Claude.
OPERATOR, TEAM, BOTH = "Betreiber", "Team", "Betreiber und Team"
#: Zuständige im Cockpit: `claude` (die Sitzung des Teams), `team` (eine Person der Marke), `both`.
OWNER_ROLE = {OPERATOR: "claude", TEAM: "team", BOTH: "both", "": "claude"}
#: So alt darf der Launch-Check höchstens sein, auf den sich das Ja zum Veröffentlichen bezieht.
REPORT_MAX_AGE = timedelta(hours=12)
#: So lange wird nach dem Veröffentlichen eng beobachtet (`post-launch.md`, Tag 1).
OBSERVE = timedelta(hours=48)
#: Eine Zeile Beleg; längere Belege stehen vollständig in `launch-check.md`.
EVIDENCE_WIDTH = 300

#: Der Ablauf in sechs Schritten, wie ihn die Seite neben dem Cockpit am 10.11.2026 zeigte.
FLOW = (
    ("prepare", "Vorbereiten"),
    ("check", "Prüfen"),
    ("go", "Go"),
    ("live", "Veröffentlichen"),
    ("check_after", "Prüfen danach"),
    ("observe", "Beobachten"),
)

#: Was ein Rückfall nie zurückdreht, gekürzt aus `rollback.md`, Abschnitt "Was ein Rückfall nicht
#: zurückdreht". Was nur diesen Launch betrifft (etwa eine deinstallierte App), legt das Team fest.
NOT_REVERTED = (
    "Vorlagen-Zuweisungen, Menüs, URL-Weiterleitungen und Rabatte",
    "Deinstallierte Apps und entfernte Pixel",
    "Änderungen im neuen Theme nach dem Launch",
    "Bestellungen und Daten seit dem Launch",
)


def rollback_path(workspace) -> Path:
    return Path(workspace) / "migration" / "rollback.json"


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _text(value) -> str | None:
    text = " ".join(str(value).split()) if isinstance(value, str) else ""
    return text or None


def one_line(text, width: int = EVIDENCE_WIDTH) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def parse_time(value) -> datetime | None:
    """Ein Zeitstempel aus dem Lauf als `datetime` in UTC; `None`, wenn er nicht lesbar ist."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def owner_role(owner) -> str:
    """Wer einen Punkt erledigt, als Rolle des Cockpits. Unbekannte Angaben mit "Marke" oder "Team" (etwa
    "Person der Marke mit Path to AI" beim Go) gehören zum Team, alles andere zur Sitzung."""
    owner = str(owner or "").strip()
    if owner in OWNER_ROLE:
        return OWNER_ROLE[owner]
    return "team" if ("Marke" in owner or "Team" in owner) else "claude"


# ---------------------------------------------------------------------------
# Go-Liste
# ---------------------------------------------------------------------------

def latest_report(workspace, mode: str, run_id: str | None = None) -> dict | None:
    """Der jüngste Launch-Check dieses Modus (`before`, `after`) im Workspace.

    Gesucht wird in jedem Lauf unter `reporting/runs/`, nicht nur in `<heute>-launch-check`, weil `--run-id`
    einen anderen Ordner wählen kann. Ein Bericht eines anderen Migrationslaufs zählt nicht; einer ohne
    Migrationslauf schon, das ist ein Launch-Check, der vor `run_state init` lief.
    """
    name = "launch-check-after.json" if mode == "after" else "launch-check.json"
    runs = Path(workspace) / "reporting" / "runs"
    found = []
    for path in runs.glob(f"*/{name}") if runs.is_dir() else ():
        report = _read(path)
        if not isinstance(report, dict) or report.get("kind") != "launch-check" or report.get("mode") != mode:
            continue
        if run_id and report.get("migration_run") not in (None, run_id):
            continue
        if parse_time(report.get("checked_at")) is None or not isinstance(report.get("checks"), list):
            continue
        found.append(report)
    return max(found, key=lambda r: parse_time(r["checked_at"])) if found else None


def go_list(report: dict | None) -> dict | None:
    """Ein Launch-Check als Go-Liste für das Cockpit: je Punkt eine Zeile, die Summe, was entfällt."""
    if not report:
        return None
    items, skipped = [], []
    for check in report["checks"]:
        if not isinstance(check, dict) or not _text(check.get("title")):
            continue
        status = check.get("status")
        if status == NA:
            skipped.append(_text(check["title"]))
            continue
        if status not in (OK, MISSING, BLOCKED, MANUAL):
            continue
        todo = None if status == OK else _text(check.get("question")) or _text(check.get("action"))
        items.append({
            "id": _text(check.get("id")) or _text(check["title"]),
            "group": _text(check.get("group")),
            "title": _text(check["title"]),
            "status": status,
            "evidence": one_line(check.get("evidence")) or None,
            "todo": one_line(todo) if todo else None,
            "owner": None if status == OK else owner_role(check.get("owner")),
        })
    return {
        "mode": report.get("mode"),
        "checked_at": report.get("checked_at"),
        "recommendation": report.get("recommendation"),
        "green": sum(1 for i in items if i["status"] == OK),
        "total": len(items),
        "new_theme_id": _text(report.get("new_theme_id")),
        "old_theme_id": _text(report.get("old_theme_id")),
        "launch_date": _text(report.get("launch_date")),
        "items": items,
        "not_applicable": skipped,
    }


def is_green(report: dict | None) -> bool:
    return bool(report) and report.get("recommendation") == "go"


# ---------------------------------------------------------------------------
# Rückfall
# ---------------------------------------------------------------------------

def load_rollback(workspace) -> dict:
    """Die Rückfallkriterien des Teams aus `migration/rollback.json`; leer, wenn es sie nicht gibt."""
    data = _read(rollback_path(workspace))
    return data if isinstance(data, dict) else {}


def rollback_view(workspace, values: dict, before: dict | None) -> dict:
    """Altes Theme, Kriterien, wer entscheidet und was ein Rückfall nicht zurückdreht."""
    plan = load_rollback(workspace)
    criteria = []
    for c in plan.get("criteria") or []:
        when = _text(c.get("when")) if isinstance(c, dict) else None
        if when:
            criteria.append({"when": when, "deadline": _text(c.get("deadline"))})
    own = [t for t in (_text(k) for k in plan.get("not_reverted") or []) if t]
    # Vor dem Launch ist das Rückfall-Theme das Theme, das gerade live ist; danach steht es im Stand.
    theme = values.get("rollback_theme_id") or (before or {}).get("old_theme_id") or values.get("live_theme_id")
    return {
        "theme_id": _text(str(theme)) if theme else None,
        "decider": _text(plan.get("decider")),
        "agreed_with": _text(plan.get("agreed_with")),
        "set_at": _text(plan.get("set_at")),
        "criteria": criteria,
        "not_reverted": [{"text": t, "source": "team"} for t in own]
                        + [{"text": t, "source": "rule"} for t in NOT_REVERTED],
    }


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

def _count(report: dict) -> str:
    view = go_list(report)
    return f"{view['green']} von {view['total']} grün"


def flow(data: dict, *, sync_done: bool, before: dict | None, after: dict | None, rollback: dict,
         people: list, now: datetime | None = None) -> list:
    """Die sechs Schritte des Launches mit Stand (`done`, `running`, `open`), Zuständigen und Notiz.

    `sync_done` ist Schritt 7 von `steps.compute` ("Abgleich vor dem Launch"). Zuständige sind Rollen
    (`team`, `claude`, `operator`); `person` nennt die Person der Marke, wo eine zuständig ist.
    """
    now = now or datetime.now(timezone.utc)
    values = data.get("values") or {}
    phases = data.get("phases") or {}
    g5 = (data.get("gates") or {}).get("G5-go-live") or {}
    published = parse_time(values.get("published_at")) if values.get("published_at") else None
    approved_by = values.get("launch_approved_by")
    person = approved_by or g5.get("decided_by") or rollback.get("decider") or (people[0] if people else None)
    launching = phases.get("9-launch") in ("running", "done") or published is not None
    steps = []

    def add(key: str, status: str, note: str | None, owners: list) -> None:
        name = dict(FLOW)[key]
        steps.append({"key": key, "name": name, "status": status, "note": note or None, "owners": owners,
                      "person": person if "team" in owners else None})

    # Vorbereiten: Abgleich vor dem Launch und Rückfallkriterien schriftlich (Phase 9, Vorbereitung).
    missing = [label for label, met in (("Abgleich vor dem Launch", sync_done or published is not None),
                                        ("Rückfallkriterien", bool(rollback["criteria"]))) if not met]
    status = "done" if not missing else "running" if launching or len(missing) == 1 else "open"
    add("prepare", status, f"Ausstehend: {', '.join(missing)}" if missing else None, ["team", "claude"])

    # Prüfen: der Launch-Check vor dem Launch. Grün zählt nur, solange er frisch genug für das Ja ist.
    checked = parse_time(before["checked_at"]) if before else None
    if published:
        status, note = "done", _count(before) if before else None
    elif not before:
        status, note = "open", None
    elif is_green(before) and now - checked <= REPORT_MAX_AGE:
        status, note = "done", _count(before)
    elif is_green(before):
        hours = int(REPORT_MAX_AGE.total_seconds() // 3600)
        status, note = "running", f"{_count(before)}, älter als {hours} Stunden"
    else:
        status, note = "running", _count(before)
    add("check", status, note, ["claude"])

    # Go: G5 und das Ja auf "Jetzt Launch durchführen?"; gefragt wird erst, wenn alles grün ist.
    if approved_by or published:
        status, note = "done", f"Ja von {approved_by}" if approved_by else None
    elif steps[-1]["status"] == "done":
        status, note = "running", "Bestätigung ausstehend"
    elif g5.get("decided_by"):
        # G5 ist entschieden, gefragt wird aber erst bei allem grün: der Schritt läuft noch nicht.
        status, note = "open", f"G5 entschieden von {g5['decided_by']}"
    else:
        status, note = "open", None
    add("go", status, note, ["team"])

    # Veröffentlichen: nur nach dem Ja, durch die Sitzung, zurückgelesen als MAIN.
    add("live", "done" if published else "open", values.get("published_at") if published else None,
        ["claude"])

    # Prüfen danach: der Launch-Check nach dem Veröffentlichen, mit Testbestellung des Teams.
    if not published:
        status, note = "open", None
    elif not after or (parse_time(after["checked_at"]) or now) < published:
        status, note = "running", "Launch-Check ausstehend"
    else:
        status, note = ("done" if is_green(after) else "running"), _count(after)
    add("check_after", status, note, ["claude", "team"])

    # Beobachten: die ersten 48 Stunden nach dem Veröffentlichen eng (post-launch.md).
    if not published:
        status, note = "open", None
    else:
        until = published + OBSERVE
        status = "done" if now >= until or phases.get("10-aftercare") == "done" else "running"
        note = until.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    add("observe", status, note, ["operator", "claude"])
    return steps


# ---------------------------------------------------------------------------
# Block für migration.json
# ---------------------------------------------------------------------------

def build(workspace, data: dict, *, sync_done: bool, people: list, now: datetime | None = None) -> dict:
    """Der Block `launch` für `migration.json`. `data` ist der Inhalt von `state.json`."""
    run_id = data.get("run_id")
    values = data.get("values") or {}
    before = latest_report(workspace, "before", run_id)
    after = latest_report(workspace, "after", run_id)
    published = parse_time(values.get("published_at")) if values.get("published_at") else None
    # Ein Launch-Check nach dem Launch, der vor dem Veröffentlichen lief, gehört zu einem früheren Versuch.
    if after and published and parse_time(after["checked_at"]) < published:
        after = None
    rollback = rollback_view(workspace, values, before)
    g5 = (data.get("gates") or {}).get("G5-go-live") or {}
    return {
        "published_at": values.get("published_at") if published else None,
        "approved_by": _text(values.get("launch_approved_by")),
        "go_by": _text(g5.get("decided_by")),
        "new_theme_id": _text(str(values.get("live_theme_id"))) if published and values.get("live_theme_id")
        else (before or {}).get("new_theme_id") or _text(str(values.get("draft_theme_id") or "")),
        "check": go_list(before),
        "check_after": go_list(after),
        "flow": flow(data, sync_done=sync_done, before=before, after=after, rollback=rollback, people=people,
                     now=now),
        "rollback": rollback,
    }
