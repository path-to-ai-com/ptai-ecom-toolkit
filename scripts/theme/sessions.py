#!/usr/bin/env python3
"""Transkripte der Claude-Sessions eines Migrationslaufs bereinigt im Workspace ablegen.

Claude Code speichert jede Session als JSONL unter `~/.claude/projects/<ordner>/`,
Subagents darunter in `<session-id>/subagents/`. Das liegt nur auf dem Rechner der
Person, die gearbeitet hat. Für die Auswertung (welche Fragen kamen, wo stand ein
Lauf, was haben Subagents gebracht) braucht es den Verlauf an einer Stelle, im
Repo der Marke neben `state.json` und `journal.jsonl`.

Abgelegt wird nach `reporting/runs/<run-id>/sessions/`:

- `<session-id>.jsonl.gz` je Session und `<session-id>/subagents/<agent>.jsonl.gz`
- `index.json` mit Beginn, Ende, Zahl der Eingaben, Subagents und Schwärzungen,
  ein Eintrag je `session_id`, mit dem bisherigen Stand zusammengeführt

Zugeordnet wird über das `cwd` der Zeilen einer Session, nicht über Freitext: bis
zum 12.10.2026 reichte es, den Workspace-Pfad irgendwo zu nennen. Dadurch landeten
Scratch-Sitzungen (auch private) im Archiv, während echte Sitzungen unter Windows
fehlten, weil der Pfad dort JSON-escaped, in anderer Schreibweise, mit
Laufwerksbuchstabe oder als UNC-Pfad steht. Ein Lauf ohne Treffer hatte zudem einen
gefüllten Index geleert.

Vor dem Schreiben werden bekannte Geheimnis-Formate geschwärzt (Shopify-, GitHub-,
Google- und Anthropic-Token, private Schlüssel, Felder wie `access_token`). Das
Repo ist privat, trotzdem gehört kein Zugangswert hinein. gzip ohne Zeitstempel,
damit ein erneuter Lauf über unveränderte Sessions keinen Diff erzeugt.

Aufruf:
    python3 -m theme.sessions archive [--workspace .] [--run-id <id>] [--days 30]
        [--projects ~/.claude/projects]
"""
import argparse
import functools
import gzip
import json
import os
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


# Präfixe von Windows-Gerätepfaden: `\\?\C:\` und `\\.\C:\` meinen `C:\`,
# `\\?\UNC\server\share` meint `\\server\share`. Nach dem Tausch von `\` gegen `/`.
DEVICE_PREFIX = re.compile(r"^//[?.]/(unc/)?", re.I)
DRIVE = re.compile(r"^([a-z]):(?=/|$)")


def normalize_path(path: str) -> str:
    """Schreibweise eines Pfads für den Vergleich, ohne das Dateisystem zu fragen.

    Groß- und Kleinschreibung egal, `/` und `\\` gleich, doppelte Trenner (auch aus
    nicht entschlüsseltem JSON) zusammengefasst, Gerätepräfix weg, kein Trenner am Ende.
    Ein UNC-Pfad behält seine zwei führenden Trenner, damit er nicht wie ein
    Unix-Pfad aussieht.
    """
    text = path.strip().replace("\\", "/")
    unc = text.startswith("//")
    match = DEVICE_PREFIX.match(text)
    if match:
        unc = bool(match.group(1))
        text = text[match.end():]
    parts = [part for part in text.split("/") if part and part != "."]
    lead = "//" if unc else ("/" if text.startswith("/") else "")
    return (lead + "/".join(parts)).lower()


@functools.lru_cache(maxsize=None)
def drive_target(letter: str) -> str | None:
    """Wohin ein Laufwerksbuchstabe zeigt (Netzlaufwerk, subst), nur unter Windows.

    Ein Workspace auf `Y:` und dieselbe Freigabe als `\\\\server\\share` sind ein Ort.
    Claude Code legt Sessions aus beiden Schreibweisen getrennt ab, je nachdem, wie
    die Sitzung gestartet wurde. Gefragt wird nur der Laufwerksstamm, nie der
    Workspace selbst.
    """
    if os.name != "nt":
        return None
    try:
        target = normalize_path(os.path.realpath(f"{letter}:\\"))
    except (OSError, ValueError):
        return None
    return target if target and target != f"{letter}:" else None


def path_forms(path: str) -> set[str]:
    """Normalisierte Schreibweisen eines Pfads, bei Laufwerksbuchstaben auch das Ziel."""
    form = normalize_path(path)
    forms = {form}
    match = DRIVE.match(form)
    if match:
        target = drive_target(match.group(1))
        if target:
            forms.add(target.rstrip("/") + form[2:])
    return forms


def is_within(path: str, root: str) -> bool:
    """Ob ein normalisierter Pfad der Wurzel gleich ist oder darunter liegt."""
    return path == root or path.startswith(root.rstrip("/") + "/")


def project_dir_name(form: str) -> str:
    """Ordnername unter `~/.claude/projects/`, wie Claude Code ihn aus einem Pfad bildet."""
    return re.sub(r"[^a-z0-9]", "-", form)


def workspace_roots(workspace: Path) -> set[str]:
    """Workspace und Ziel-Repo daneben (`<name>-horizon`) in allen Schreibweisen.

    Verglichen wird ohne `resolve()`, weil das unter Windows ein Netzlaufwerk in
    einen UNC-Pfad verwandelt und die Sessions mit Laufwerksbuchstaben dann nicht
    mehr passen. Die aufgelöste Form kommt nur als zusätzliche Schreibweise dazu,
    etwa für `/var` und `/private/var` unter macOS.
    """
    absolute = Path(os.path.abspath(workspace))
    bases = {absolute}
    try:
        bases.add(absolute.resolve())
    except (OSError, RuntimeError):
        pass
    roots: set[str] = set()
    for base in bases:
        for path in (base, base.parent / f"{base.name}-horizon"):
            roots |= path_forms(str(path))
    return roots


def belongs_to(transcript: Path, roots: set[str]) -> bool:
    """Eine Session gehört zum Lauf, wenn sie im Workspace oder im Ziel-Repo gearbeitet hat.

    Entscheidend ist das `cwd` der Zeilen, nie Freitext. Es folgt jedem `cd`, deshalb
    zählt nicht jedes `cwd`, sondern der Start der Session:

    - startet sie im Workspace, einem Unterordner (auch Worktree) oder im Ziel-Repo,
      gehört sie dazu;
    - startet sie im übergeordneten Ordner oder in dem Projektordner, den Claude Code
      für den Workspace anlegt, gehört sie dazu, sobald ein `cwd` hineinwechselt.
      Das ist der Fall, in dem das Repo der Marke erst in Phase 0 geklont wird;
    - startet sie anderswo (Scratch-Ordner, anderes Repo, Drive), gehört sie nicht
      dazu, auch wenn sie kurz hineinwechselt. Geprüft am 12.10.2026: ein Wechsel
      allein hätte über ein Viertel der Sessions eines Workspaces aus fremden Repos,
      dem Drive und Scratch-Ordnern zugeordnet.

    Der Projektordner allein entscheidet nur, wenn keine Zeile ein `cwd` trägt. Seine
    Kodierung ist verlustbehaftet (`a-b` und `a/b` ergeben denselben Namen) und
    reicht deshalb nie ohne ein passendes `cwd`, sobald es eines gibt.
    """
    name = transcript.parent.name.lower()
    in_project_dir = any(name == project_dir_name(root) for root in roots)
    parents = {root.rsplit("/", 1)[0] for root in roots if "/" in root.strip("/")}
    seen: set[str] = set()
    try:
        with transcript.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"cwd"' not in line:
                    continue
                try:
                    cwd = json.loads(line).get("cwd")
                except (json.JSONDecodeError, AttributeError):
                    continue
                if not isinstance(cwd, str) or cwd in seen:
                    continue
                forms = path_forms(cwd)
                if any(is_within(form, root) for form in forms for root in roots):
                    return True
                if not seen and not (forms & parents or in_project_dir):
                    return False
                seen.add(cwd)
    except OSError:
        return False
    return not seen and in_project_dir


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


def load_index(path: Path) -> list[dict]:
    """Bestehender Index; ein unlesbarer bricht ab, statt beim Schreiben verloren zu gehen."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} ist nicht lesbar ({exc}), Index bleibt unangetastet.") from exc
    if not isinstance(data, list):
        raise ValueError(f"{path} ist keine Liste, Index bleibt unangetastet.")
    return [entry for entry in data if isinstance(entry, dict) and entry.get("session_id")]


def merge_index(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Ein Eintrag je `session_id`: der neue Lauf ersetzt seine Sessions, alle anderen bleiben.

    Ältere Läufe haben dieselbe Session doppelt eingetragen, wenn sie in zwei
    Projektordnern lag. Von solchen Dubletten bleibt die vollständigere (späteres
    Ende, dann mehr Bytes).
    """
    merged: dict[str, dict] = {}
    for entry in existing:
        known = merged.get(entry["session_id"])
        if known is None or completeness(entry) > completeness(known):
            merged[entry["session_id"]] = entry
    for entry in fresh:
        merged[entry["session_id"]] = entry
    return sorted(merged.values(), key=lambda e: (e.get("started") or "", e["session_id"]))


def completeness(entry: dict) -> tuple:
    return entry.get("ended") or "", entry.get("bytes") or 0


def pick_transcripts(projects: Path, roots: set[str], cutoff: float) -> list[Path]:
    """Je Session ein Transkript.

    Dieselbe `session_id` kann in zwei Projektordnern liegen, etwa im Repo und in
    einem Worktree oder unter Laufwerksbuchstabe und UNC-Pfad. Abgelegt wird die
    zuletzt geschriebene Fassung, bei Gleichstand die größere.
    """
    chosen: dict[str, tuple[float, int, Path]] = {}
    for transcript in sorted(projects.glob("*/*.jsonl")):
        stat = transcript.stat()
        if stat.st_mtime < cutoff or not belongs_to(transcript, roots):
            continue
        rank = (stat.st_mtime, stat.st_size, transcript)
        known = chosen.get(transcript.stem)
        if known is None or rank[:2] > known[:2]:
            chosen[transcript.stem] = rank
    return [rank[2] for _, rank in sorted(chosen.items())]


def archive(workspace: Path, run_id: str, projects: Path, days: int, now: float | None = None) -> dict:
    roots = workspace_roots(workspace)
    out = Path(os.path.abspath(workspace)) / "reporting" / "runs" / run_id / "sessions"
    index_path = out / "index.json"
    existing = load_index(index_path)
    cutoff = (now or time.time()) - days * 86400
    index = []
    for transcript in pick_transcripts(projects, roots, cutoff):
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
    merged = merge_index(existing, index)
    # Ein Lauf ohne Treffer (falscher Workspace, Transkripte zu alt, anderer Rechner)
    # schreibt nichts: ein gefüllter Index darf nie durch einen leeren ersetzt werden.
    written = bool(index) or not index_path.exists()
    if written:
        out.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"out": str(out), "sessions": len(index), "subagents": sum(e["subagents"] for e in index),
            "redactions": sum(e["redactions"] for e in index), "indexed": len(merged),
            "index_written": written}


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
    try:
        result = archive(workspace, run_id, projects, args.days)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
