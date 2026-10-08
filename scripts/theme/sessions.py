#!/usr/bin/env python3
"""Transkripte der Claude-Sessions eines Migrationslaufs bereinigt im Workspace ablegen.

Claude Code speichert jede Session als JSONL unter `~/.claude/projects/<ordner>/`,
Subagents darunter in `<session-id>/subagents/`. Das liegt nur auf dem Rechner der
Person, die gearbeitet hat. Für die Auswertung (welche Fragen kamen, wo stand ein
Lauf, was haben Subagents gebracht) braucht es den Verlauf an einer Stelle, im
Repo der Marke neben `state.json` und `journal.jsonl`.

Abgelegt wird nach `reporting/runs/<run-id>/sessions/`:

- `<session-id>.jsonl.gz` je Session und `<session-id>/subagents/<agent>.jsonl.gz`
- `index.json` mit Beginn, Ende, Zahl der Eingaben, Subagents und Schwärzungen

Vor dem Schreiben werden bekannte Geheimnis-Formate geschwärzt (Shopify-, GitHub-,
Google- und Anthropic-Token, private Schlüssel, Felder wie `access_token`). Das
Repo ist privat, trotzdem gehört kein Zugangswert hinein. gzip ohne Zeitstempel,
damit ein erneuter Lauf über unveränderte Sessions keinen Diff erzeugt.

Aufruf:
    python3 -m theme.sessions archive [--workspace .] [--run-id <id>] [--days 30]
        [--projects ~/.claude/projects]
"""
import argparse
import gzip
import json
import re
import sys
import time
from pathlib import Path

from theme import run_state

# Jedes Muster mit einem Beispiel aus der Praxis: Shopify-Admin-Token aus `store auth`,
# GitHub-Token aus `gh auth`, Google-OAuth aus den Pulls, Anthropic-Schlüssel.
SECRET_PATTERNS = [
    re.compile(r"shp(?:at|ca|ss|pa|ua)_[A-Fa-f0-9]{32}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}"),
    re.compile(r"\b1//0[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
]
# Werte hinter typischen Feldnamen, auch JSON-escaped innerhalb eines Strings.
SECRET_FIELDS = re.compile(
    r'(?i)((?:\\?")?(?:access_token|refresh_token|client_secret|api_key|apikey|password|secret|token)'
    r'(?:\\?")?\s*[:=]\s*(?:\\?"))([^"\\\s]{12,})')
MASK = "[REDACTED]"


def redact(text: str) -> tuple[str, int]:
    """Schwärzt bekannte Geheimnisse, gibt Text und Zahl der Treffer zurück."""
    count = 0
    for pattern in SECRET_PATTERNS:
        text, n = pattern.subn(MASK, text)
        count += n
    text, n = SECRET_FIELDS.subn(lambda m: m.group(1) + MASK, text)
    return text, count + n


def belongs_to(transcript: Path, roots: list[Path]) -> bool:
    """Eine Session gehört zum Lauf, wenn sie in einem der Ordner lief oder ihn nennt.

    Das Nennen fängt Sessions, die im übergeordneten Ordner gestartet wurden und das
    Repo der Marke erst in Phase 0 geklont haben.
    """
    names = [str(root) for root in roots]
    try:
        with transcript.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if any(name in line for name in names):
                    return True
    except OSError:
        return False
    return False


def summarize(lines: list[str]) -> dict:
    """Beginn, Ende und Zahl der Eingaben einer Person, aus den Zeilen einer Session."""
    stamps, prompts = [], 0
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("timestamp"):
            stamps.append(record["timestamp"])
        message = record.get("message") or {}
        if (record.get("type") == "user" and not record.get("isMeta") and not record.get("isSidechain")
                and isinstance(message.get("content"), str)):
            prompts += 1
    return {"started": min(stamps) if stamps else None, "ended": max(stamps) if stamps else None,
            "user_prompts": prompts}


def write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as handle:
        handle.write(text.encode("utf-8"))


def archive(workspace: Path, run_id: str, projects: Path, days: int, now: float | None = None) -> dict:
    workspace = workspace.resolve()
    roots = [workspace, workspace.parent / f"{workspace.name}-horizon"]
    out = workspace / "reporting" / "runs" / run_id / "sessions"
    cutoff = (now or time.time()) - days * 86400
    index = []
    for transcript in sorted(projects.glob("*/*.jsonl")):
        if transcript.stat().st_mtime < cutoff or not belongs_to(transcript, roots):
            continue
        session_id = transcript.stem
        text, hits = redact(transcript.read_text(encoding="utf-8", errors="replace"))
        write_gz(out / f"{session_id}.jsonl.gz", text)
        entry = {"session_id": session_id, "project_dir": transcript.parent.name, **summarize(text.splitlines()),
                 "subagents": 0, "redactions": hits, "bytes": len(text)}
        for agent in sorted((transcript.parent / session_id / "subagents").glob("*.jsonl")):
            agent_text, agent_hits = redact(agent.read_text(encoding="utf-8", errors="replace"))
            write_gz(out / session_id / "subagents" / f"{agent.stem}.jsonl.gz", agent_text)
            entry["subagents"] += 1
            entry["redactions"] += agent_hits
        index.append(entry)
    index.sort(key=lambda e: e["started"] or "")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"out": str(out), "sessions": len(index), "subagents": sum(e["subagents"] for e in index),
            "redactions": sum(e["redactions"] for e in index)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.sessions")
    parser.add_argument("command", choices=("archive",))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--run-id")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--projects", default=str(Path.home() / ".claude" / "projects"))
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    run_id = args.run_id or run_state.latest_run_id(workspace)
    if not run_id:
        print(json.dumps({"error": "Kein Migrations-Lauf gefunden, zuerst run_state init."}, ensure_ascii=False))
        return 2
    projects = Path(args.projects).expanduser()
    if not projects.is_dir():
        print(json.dumps({"error": f"Kein Ordner mit Transkripten: {projects}"}, ensure_ascii=False))
        return 2
    print(json.dumps(archive(workspace, run_id, projects, args.days), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
