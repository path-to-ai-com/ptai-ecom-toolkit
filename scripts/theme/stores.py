#!/usr/bin/env python3
"""Stand der Migration aller Stores einer Marke, gelesen aus GitHub.

Seit 0.3.27. Path to AI hat keinen Shop-Zugang und arbeitet nicht in den Store-Repos; das Team führt die
Migration bis zum Launch selbst, Path to AI begleitet. Dafür muss Path to AI den Stand jedes Stores kennen,
ohne ihn aus Chat, Cockpit und alten lokalen Kopien zusammenzusuchen. Jede Sitzung des Teams pusht
`migration.json` nach `main`; dieser Befehl liest genau das, für alle Repos auf einmal, ohne zu klonen.

Je Store eine Zeile: Schritt, wer dran ist, offene Fragen, was Path to AI tun soll, letzter Push.

Aufruf:
    python3 -m theme.stores status --repo <owner/name> [--repo <owner/name> ...] [--json]

Braucht `gh`, angemeldet mit Lesezugriff auf die Repos. Exit 0, auch wenn ein Repo nicht lesbar ist; die
Zeile nennt dann den Grund. Exit 2 bei falschem Aufruf oder ohne `gh`.
"""
import argparse
import base64
import json
import re
import shutil
import subprocess
import sys

RUN_PATH = re.compile(r"^reporting/runs/(\d{4}-\d{2}-\d{2}[^/]*-migration)/migration\.json$")

OWNER_LABEL = {"operator": "Path to AI", "team": "Team", "plugin": "Team mit Claude"}


class StoresError(Exception):
    """Ein Repo, dessen Stand sich nicht lesen lässt."""


def gh_json(endpoint: str):
    """Ein Aufruf von `gh api`, Ergebnis als JSON."""
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
    if result.returncode != 0:
        raise StoresError((result.stderr or result.stdout).strip().splitlines()[-1] if
                          (result.stderr or result.stdout).strip() else "gh api fehlgeschlagen")
    return json.loads(result.stdout)


def latest_run_path(paths: list) -> str | None:
    """Der jüngste Migrationslauf unter `reporting/runs/`, nach Lauf-ID."""
    runs = sorted((m.group(1), p) for p in paths if (m := RUN_PATH.match(p)))
    return runs[-1][1] if runs else None


def summarize(repo: str, migration: dict, pushed_at: str | None) -> dict:
    """Die Zeile eines Stores aus seiner `migration.json`."""
    step = migration.get("current_step")
    steps = migration.get("steps") or []
    current = steps[step - 1] if isinstance(step, int) and 0 < step <= len(steps) else {}
    open_questions = [q for q in migration.get("questions") or [] if q.get("status") == "open"]
    return {
        "repo": repo,
        "step": step,
        "step_name": current.get("name"),
        "step_status": current.get("status"),
        "now": migration.get("now"),
        "owner": migration.get("owner"),
        "open_questions": [q.get("id") for q in open_questions],
        "operator_tasks": migration.get("operator_tasks") or [],
        "ready_for_launch": (migration.get("ready_for_launch") or {}).get("met"),
        "pushed_at": pushed_at,
    }


def read_store(repo: str) -> dict:
    """Liest den Stand eines Repos von `main`. Bei einem Fehler eine Zeile mit `error`."""
    try:
        branch = gh_json(f"repos/{repo}").get("default_branch") or "main"
        head = gh_json(f"repos/{repo}/commits/{branch}")
        pushed_at = ((head.get("commit") or {}).get("committer") or {}).get("date")
        tree = gh_json(f"repos/{repo}/git/trees/{branch}?recursive=1")
        run_path = latest_run_path([e["path"] for e in tree.get("tree") or []])
        if not run_path:
            return {"repo": repo, "error": "kein Migrationslauf auf " + branch, "pushed_at": pushed_at}
        blob = gh_json(f"repos/{repo}/contents/{run_path}?ref={branch}")
        migration = json.loads(base64.b64decode(blob["content"]).decode("utf-8"))
        return summarize(repo, migration, pushed_at)
    except (StoresError, KeyError, ValueError) as error:
        return {"repo": repo, "error": str(error)}


def line(row: dict) -> str:
    """Eine lesbare Zeile je Store."""
    if row.get("error"):
        return f"{row['repo']}: nicht gelesen ({row['error']})"
    parts = [f"Schritt {row['step']} von 9: {row.get('now') or row.get('step_name')}"]
    if row.get("step_status") == "rework":
        parts[0] += ", nacharbeiten"
    parts.append("Zuständig: " + OWNER_LABEL.get(row.get("owner"), row.get("owner") or "unbekannt"))
    if row["open_questions"]:
        parts.append(f"{len(row['open_questions'])} Fragen offen ({', '.join(row['open_questions'])})")
    if row["operator_tasks"]:
        parts.append("Path to AI: " + "; ".join(row["operator_tasks"]))
    if row.get("ready_for_launch"):
        parts.append("bereit für den Launch")
    parts.append("letzter Push " + (row.get("pushed_at") or "unbekannt")[:10])
    return f"{row['repo']}: " + " · ".join(parts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.stores")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Stand aller Stores aus GitHub")
    status.add_argument("--repo", action="append", required=True, help="owner/name, mehrfach")
    status.add_argument("--json", action="store_true", help="eine JSON-Zeile je Store")
    args = parser.parse_args(argv)
    if not shutil.which("gh"):
        print(json.dumps({"error": "gh fehlt"}, ensure_ascii=False))
        return 2
    for repo in args.repo:
        row = read_store(repo)
        print(json.dumps(row, ensure_ascii=False) if args.json else line(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
