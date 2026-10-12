#!/usr/bin/env python3
"""Die neun Schritte einer Theme-Migration, berechnet aus dem Lauf.

Eingeführt mit 0.3.11. Das Cockpit und die Marke sehen nicht elf Phasen und fünf Gates, sondern neun feste
Schritte mit zwei Meilensteinen. Ein
Schritt ist nur erledigt, wenn seine Phasen erledigt sind und seine Bedingung gilt. Sind die Phasen erledigt und
die Bedingung verletzt, steht er auf `rework`. Vorher konnte ein Lauf in der Testrunde stehen, obwohl erst drei von
neun Prüfern gelaufen waren und keine Vorgabe der Marke eingetragen war.

Dieses Modul liest nur. `run_state` schreibt das Ergebnis nach jedem Befehl als `migration.json` in den Lauf.
"""
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from theme import policies, questions

STEPS = (
    ("backup", "Shop gesichert"),
    ("inventory", "Abstimmung"),
    ("build", "Neubau"),
    ("upload", "Entwurf hochgeladen"),
    ("verify", "Kontrolle des Entwurfs"),
    ("test_round", "Testrunde"),
    ("sync", "Abgleich vor dem Launch"),
    ("launch", "Launch"),
    ("aftercare", "Kontrolle nach dem Launch"),
)
#: Wer einen Schritt ausführt, wenn nichts anderes ansteht.
OWNER = {"backup": "plugin", "inventory": "plugin", "build": "plugin", "upload": "plugin", "verify": "plugin",
         "test_round": "team", "sync": "plugin", "launch": "operator", "aftercare": "plugin"}

#: Die neun Prüfer von `verify-theme`, feste Ordnernamen unter `migration/verify/<date>/`.
CHECKERS = ("structure", "content", "seo", "design", "function", "apps_tracking", "languages", "performance",
            "accessibility")
#: Ordnernamen aus Läufen vor 0.3.11, die Teams selbst gewählt haben.
CHECKER_ALIASES = {
    "struktur": ("structure",), "inhalt": ("content",), "gestaltung": ("design",), "funktion": ("function",),
    "gestaltung-funktion": ("design", "function"), "design-function": ("design", "function"),
    "apps": ("apps_tracking",), "tracking": ("apps_tracking",), "apps-tracking": ("apps_tracking",),
    "apps-und-tracking": ("apps_tracking",), "sprachen": ("languages",), "barrierefreiheit": ("accessibility",),
    "a11y": ("accessibility",),
}
SYNC_MAX_AGE_DAYS = 7
DONE = ("done", "skipped")


def _questions(n: int) -> str:
    return f"{n} Frage an euch offen" if n == 1 else f"{n} Fragen an euch offen"


def checkers_run(workspace) -> list:
    """Welche Prüfer in irgendeiner Runde unter `migration/verify/` ein Ergebnis hinterlassen haben."""
    root = Path(workspace) / "migration" / "verify"
    found = set()
    if not root.is_dir():
        return []
    for round_dir in root.iterdir():
        if not round_dir.is_dir():
            continue
        for checker in round_dir.iterdir():
            if not checker.is_dir() or not any((checker / n).is_file() for n in ("findings.json", "findings.md")):
                continue
            name = checker.name.lower().replace("_", "-")
            for suffix in ("-recheck", "-nachpruefung", "-nachprüfung"):
                name = name.removesuffix(suffix)
            keys = CHECKER_ALIASES.get(name) or ((name.replace("-", "_"),) if name.replace("-", "_") in CHECKERS
                                                 else ())
            found.update(keys)
    return [c for c in CHECKERS if c in found]


def translations_status(workspace) -> dict:
    """Ob jede veröffentlichte Nebensprache am Entwurf registriert ist, ohne Befund."""
    inventory = Path(workspace) / "migration" / "inventory" / "translations.json"
    try:
        locales = json.loads(inventory.read_text(encoding="utf-8")).get("locales") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return {"met": False, "note": "Bestandsaufnahme der Sprachen fehlt"}
    needed = sorted(l["locale"] for l in locales
                    if isinstance(l, dict) and l.get("published") and not l.get("primary") and l.get("locale"))
    if not needed:
        return {"met": True, "note": "eine Sprache, nichts zu registrieren"}
    newest = {}
    for path in sorted((Path(workspace) / "migration" / "upload").glob("*translations*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(report, dict) and report.get("locale"):
            newest[report["locale"]] = report
    missing = [l for l in needed if l not in newest]
    failing = [l for l in needed if l in newest and (newest[l].get("findings") or
                                                     (newest[l].get("readback") or {}).get("different"))]
    if missing or failing:
        parts = ([f"nicht registriert: {', '.join(missing)}"] if missing else []) + \
                ([f"mit Befund: {', '.join(failing)}"] if failing else [])
        return {"met": False, "note": "; ".join(parts)}
    return {"met": True, "note": f"registriert: {', '.join(needed)}"}


def pushed(workspace) -> dict:
    """Ob im Workspace nichts uncommittet und nichts ungepusht ist."""
    def git(*args):
        return subprocess.run(["git", "-C", str(workspace), *args], capture_output=True, text=True, timeout=20)
    try:
        dirty = git("status", "--porcelain")
        ahead = git("rev-list", "--count", "@{u}..HEAD")
    except (OSError, subprocess.SubprocessError):
        return {"met": False, "note": "Git nicht lesbar"}
    if dirty.returncode != 0:
        return {"met": False, "note": "kein Git-Repo"}
    if dirty.stdout.strip():
        return {"met": False, "note": "uncommittete Änderungen"}
    if ahead.returncode != 0:
        return {"met": False, "note": "kein Remote eingerichtet"}
    if ahead.stdout.strip() not in ("", "0"):
        return {"met": False, "note": f"{ahead.stdout.strip()} Commits nicht gepusht"}
    return {"met": True, "note": "alles gepusht"}


def _journal_time(workspace, run_id: str, phase: str, status: str) -> str | None:
    """Zeitpunkt, zu dem eine Phase zuletzt diesen Status bekam."""
    path = Path(workspace) / "reporting" / "runs" / run_id / "journal.jsonl"
    found = None
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("kind") == "phase" and entry.get("phase") == phase and entry.get("text") == status:
                found = entry.get("at")
    return found


def _age_days(value, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(value)[:10])).days
    except ValueError:
        return None


def compute(workspace, data: dict, *, today: date | None = None, items=None, git_status: dict | None = None) -> dict:
    """Schritte und Meilensteine eines Laufs. `data` ist der Inhalt von `state.json`."""
    today = today or date.today()
    phases, gates, values = data["phases"], data["gates"], data.get("values") or {}

    def state_of(*names):
        if all(phases.get(n) in DONE for n in names):
            return "done"
        if any(phases.get(n) in ("running", "failed") for n in names) or any(phases.get(n) in DONE for n in names):
            return "running"
        return "open"

    open_q = questions.open_for(workspace) if questions.path(workspace).is_file() else []
    q_by_gate = {g: [q for q in open_q if q["gate"] == g] for g in questions.GATES}
    policy = policies.status(workspace)
    if items is None:
        from theme import open_items
        items = open_items.load(workspace) if open_items.exists(workspace) else None
    blockers = [i for i in (items.items if items else []) if i["status"] == "open" and i["severity"] == "blocker"]
    steps = []

    # 1 Shop gesichert
    steps.append((state_of("0-setup", "1-snapshot"), ""))
    # 2 Abstimmung
    status = state_of("2-inventory")
    note = ""
    if status == "done" and not gates.get("G1-decisions"):
        status = "running"
        note = (_questions(len(q_by_gate['G1-decisions'])) if q_by_gate["G1-decisions"]
                else "wartet auf Gate G1")
    elif status == "done" and q_by_gate["G1-decisions"]:
        status, note = "rework", _questions(len(q_by_gate['G1-decisions']))
    steps.append((status, note))
    # 3 Neubau
    status = state_of("3-mapping", "4-build")
    note = ""
    if status == "done" and not gates.get("G2-mapping"):
        status, note = "running", "wartet auf Gate G2"
    elif status == "done":
        built = _journal_time(workspace, data["run_id"], "4-build", "done") or ""
        if policy["required"] and not policy["applied"]:
            status, note = "rework", "Vorgaben der Marke nicht eingetragen"
        elif policy["applied"] and (not built or built < (policy["applied_at"] or "")):
            # Ohne Zeitpunkt des Neubaus im Journal ist nicht belegt, dass er die Vorgaben schon gelesen hat.
            status, note = "rework", f"Vorgaben {policy['version']} eingetragen, Neubau danach steht aus"
        elif q_by_gate["G2-mapping"]:
            status, note = "rework", _questions(len(q_by_gate['G2-mapping']))
        elif policy["applied"]:
            note = f"nach Vorgaben {policy['version']}"
    steps.append((status, note))
    # 4 Entwurf hochgeladen
    status = state_of("5-upload")
    if status == "done" and not values.get("draft_theme_id"):
        status = "rework"
    steps.append((status, f"Entwurf {values['draft_theme_id']}" if values.get("draft_theme_id") else ""))
    # 5 Kontrolle des Entwurfs
    ran = checkers_run(workspace)
    missing = [c for c in CHECKERS if c not in ran]
    status = state_of("6-verify")
    note = f"{len(ran)} von {len(CHECKERS)} Prüfern gelaufen" + (f"; offen: {', '.join(missing)}" if missing else "")
    if blockers:
        note += f"; {len(blockers)} Blocker offen"
    if status == "done" and (missing or blockers):
        status = "rework"
    elif status == "open" and ran:
        status = "running"
    steps.append((status, note))
    # 6 Testrunde
    status = state_of("8-test-round")
    if status == "done" and not gates.get("G4-acceptance"):
        status = "running"
    note = (_questions(len(q_by_gate['G4-acceptance'])) + " zur Testrunde"
            if q_by_gate["G4-acceptance"] else "")
    early = status != "open" and not all(s == "done" for s, _ in steps[:5])
    if early:
        note = "begonnen, bevor der Entwurf bereit für die Testrunde war" + (f"; {note}" if note else "")
    steps.append((status, note))
    # 7 Abgleich vor dem Launch
    age = _age_days(values.get("last_sync"), today) if values.get("last_sync") else None
    tested = _journal_time(workspace, data["run_id"], "8-test-round", "done")
    launched = phases.get("9-launch") in DONE and values.get("published_at")
    if launched:
        status = "done"
    elif age is not None and age <= SYNC_MAX_AGE_DAYS and tested and str(values["last_sync"]) >= tested[:10]:
        status = "done"
    elif phases.get("7-sync") in ("running",):
        status = "running"
    else:
        status = "open"
    steps.append((status, f"zuletzt abgeglichen {values['last_sync']}" if values.get("last_sync") else ""))
    # 8 Launch
    status = state_of("9-launch")
    if status == "done" and not values.get("published_at"):
        status = "rework"
    steps.append((status, f"veröffentlicht {values['published_at']}" if values.get("published_at") else ""))
    # 9 Kontrolle nach dem Launch
    steps.append((state_of("10-aftercare"), ""))

    out_steps = [{"step": n + 1, "key": STEPS[n][0], "name": STEPS[n][1], "status": s, "note": note or None}
                 for n, (s, note) in enumerate(steps)]
    current = next((s for s in out_steps if s["status"] != "done"), out_steps[-1])

    transl = translations_status(workspace)
    ready_test = [
        {"key": "build_per_policies", "met": out_steps[2]["status"] == "done",
         "note": out_steps[2]["note"] or "Neubau nach den Vorgaben"},
        {"key": "draft_uploaded", "met": out_steps[3]["status"] == "done", "note": out_steps[3]["note"]},
        {"key": "all_checkers", "met": not missing, "note": f"{len(ran)} von {len(CHECKERS)} Prüfern"},
        {"key": "no_blocker", "met": not blockers, "note": f"{len(blockers)} Blocker offen" if blockers else None},
        {"key": "translations_registered", "met": transl["met"], "note": transl["note"]},
    ]
    ready_test_met = all(c["met"] for c in ready_test) and all(s["status"] == "done" for s in out_steps[:5])
    owned = []
    if items:
        owned = items.blocking("G5-go-live")
    git_info = git_status if git_status is not None else pushed(workspace)
    ready_launch = [
        {"key": "test_round_done", "met": out_steps[5]["status"] == "done", "note": None},
        {"key": "open_items_owned", "met": not owned,
         "note": f"{len(owned)} Punkte ohne Person und Datum" if owned else None},
        {"key": "sync_fresh", "met": age is not None and age <= SYNC_MAX_AGE_DAYS,
         "note": f"Abgleich vor {age} Tagen" if age is not None else "kein Abgleich"},
        {"key": "pushed", "met": git_info["met"], "note": git_info["note"]},
    ]
    ready_launch_met = ready_test_met and all(c["met"] for c in ready_launch) and out_steps[6]["status"] == "done"

    owner = OWNER[current["key"]]
    if current["key"] in ("inventory", "build", "test_round") and open_q:
        owner = "team"
    if current["key"] == "build" and current["status"] == "rework" and "Vorgaben" in (current["note"] or "") \
            and not policy["applied"]:
        owner = "operator"
    return {
        "current_step": current["step"],
        "steps": out_steps,
        "ready_for_test_round": {"met": ready_test_met, "conditions": ready_test},
        "ready_for_launch": {"met": ready_launch_met, "conditions": ready_launch},
        "owner": owner,
        "questions": [{"id": q["id"], "gate": q["gate"], "step": {"G1-decisions": 2, "G2-mapping": 3,
                                                                  "G4-acceptance": 6}[q["gate"]],
                       "text": q["text"], "options": q.get("options") or [],
                       "recommendation": q.get("recommendation") or None} for q in open_q],
        "policies": {"version": policy["version"], "applied_at": policy["applied_at"],
                     "open_rules": policy["open_rules"]},
    }


def export(workspace, data: dict, plugin_version: str, **kwargs) -> dict:
    """Der Inhalt von `migration.json`, wie ihn das Cockpit liest."""
    result = compute(workspace, data, **kwargs)
    values = data.get("values") or {}
    return {
        "schema": 1,
        "run_id": data["run_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plugin_version": plugin_version,
        "live_theme_id": values.get("live_theme_id"),
        "draft_theme_id": values.get("draft_theme_id"),
        "last_sync": values.get("last_sync"),
        **result,
    }
