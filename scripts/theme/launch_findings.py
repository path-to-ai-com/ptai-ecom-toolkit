"""Offene Befunde vor dem Launch: Prüfberichte und die Prüfliste aus der Bestandsaufnahme.

Am 07.10.2026 ging eine Migration live, obwohl ein Prüfbericht SEO-Lücken unter
"Vor dem Launch" führte und die Prüfliste "Muss nach dem Umbau wieder da sein"
aus Phase 2 nie abgehakt war. Der Launch-Check suchte Prüfberichte nur unter
`migration/verify/` im Workspace; der Bericht lag im Projektordner des Accounts.
Statt eines Befunds stellte er eine Frage, und eine Frage hält keinen Launch auf.

Seitdem gilt:

- Prüfberichte stehen auch außerhalb des Workspace, über
  `theme_migration.report_paths` in `reporting/config.json` (Dateien, Ordner oder
  Muster; `~` und `{drive_path}` werden aufgelöst, relative Pfade gelten ab dem
  Workspace).
- Jeder Punkt der Schwere `blocker` oder `before_launch`, und jeder Punkt in einem
  Abschnitt "Vor dem Launch" oder "Blocker" eines Markdown-Berichts, ist erledigt
  oder namentlich mit Datum verschoben. Sonst ist er offen.
- Die Prüfliste aus Phase 2 (`theme_migration.acceptance_checklist`, Zeilen der Form
  `- [ ] **P07** ...`) ist die Abnahme: jeder Punkt abgehakt, verschoben oder durch
  eine automatische Prüfung des Launch-Checks abgedeckt und bestanden.

Was als erledigt zählt, ist bewusst eng gefasst, weil ein fälschlich erledigter
Punkt niemandem auffällt, ein fälschlich offener sofort:

- Markdown-Tabelle mit Spalte `Status` oder `Stand`: die Zelle beginnt mit einem
  Wort aus `DONE_WORDS` (`erledigt`, `behoben`, `done` ...).
- Liste: `- [x]`, oder im Text `Status: erledigt`.
- JSON (`findings.json` aus `verify-theme`): `status` aus `CLOSED`.

Verschoben ist ein Punkt nur mit Person und Datum, etwa `verschoben von Beispiel
Person am 2026-10-20`, `deferred by Jane Doe on 2026-10-20` oder in einer Tabelle
eine Statuszelle `verschoben 20.10.2026` mit Namen in der Spalte `Wer`.
JSON: `deferred_by` und `deferred_at`.
"""
import glob
import json
import os
import re
from pathlib import Path

#: Befunde aus verify-theme, die vor dem Launch erledigt sein müssen.
LAUNCH_SEVERITIES = ("blocker", "before_launch")
#: Status eines Befunds, der nichts mehr verlangt.
CLOSED = ("done", "resolved", "fixed", "closed", "accepted", "wontfix")
#: So beginnt eine Statuszelle eines erledigten Punkts.
DONE_WORDS = ("erledigt", "behoben", "done", "resolved", "fixed", "closed", "geschlossen", "ok", "erfüllt")
#: Abschnitte, deren Punkte vor dem Launch erledigt sein müssen.
LAUNCH_HEADING = re.compile(r"vor dem (launch|livegang|go-live)|before[ _-]launch|pre-launch|\bblocker", re.I)
AFTER_HEADING = re.compile(r"nach dem (launch|livegang)|after[ _-]launch|post-launch", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(?:\[([ xX])\]\s+)?(.*)$")
STATUS_INLINE = re.compile(r"\b(?:status|stand)\s*:\s*(" + "|".join(DONE_WORDS) + r")\b", re.I)
DEFER_MARK = re.compile(r"\b(verschoben|zurückgestellt|deferred|postponed)\b", re.I)
DEFER_WHO = re.compile(r"\b(?:von|by|durch)\s+([A-ZÄÖÜ][\w'-]*(?:\s+[A-ZÄÖÜ][\w'-]*)*)")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b")
STATUS_COLUMNS = ("status", "stand", "erledigt")
LABEL_COLUMNS = ("punkt", "befund", "beschreibung", "title", "description", "finding")
OWNER_COLUMNS = ("wer", "verantwortlich", "owner", "zuständig", "person")
CHECKLIST_ITEM = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+\*\*([A-Za-z]+\d+)\*\*\s*(.*)$")

#: Woran ein Punkt der Prüfliste eine automatische Prüfung des Launch-Checks erkennt.
#: Eng gefasst: ein Punkt zählt nur als abgedeckt, wenn er eines dieser Merkmale nennt
#: und jede genannte Prüfung bestanden ist. Alles andere bleibt offen.
CHECK_KEYWORDS = (
    ("seo-hreflang", re.compile(r"hreflang", re.I)),
    ("seo-open-graph", re.compile(r"\bog:", re.I)),
    ("seo-structured-data", re.compile(
        r"\b(Product|ProductGroup|Organization|WebSite|SearchAction|BreadcrumbList|AggregateRating|aggregateRating)\b"
        r"|json-ld|strukturierte daten|structured data", 0)),
    ("seo-pages", re.compile(r"canonical|noindex", re.I)),
    ("seo-head", re.compile(r"meta description", re.I)),
    ("robots", re.compile(r"robots\.txt", re.I)),
)


def _deferral(text: str, owner: str = "") -> dict | None:
    """Person und Datum einer Verschiebung, None ohne beides."""
    mark = DEFER_MARK.search(text or "")
    if not mark:
        return None
    rest = text[mark.start():]
    who = DEFER_WHO.search(rest)
    when = DATE.search(rest)
    person = (who.group(1) if who else owner or "").strip()
    if not (person and when):
        return None
    return {"by": person, "at": when.group(1)}


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells: list) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells)


def _label(cells: list, header: list, skip: set) -> str:
    """Kurzer Text eines Tabellenpunkts: Kennung, wenn es eine gibt, und die Spalte mit dem Punkt.

    Ohne Spalte namens Punkt oder Befund der längste Text, aber nie Status oder Person.
    """
    ident = cells[0] if cells and len(cells[0]) <= 12 and cells[0] else ""
    named = next((i for i, h in enumerate(header) if h in LABEL_COLUMNS and i < len(cells)), None)
    rest = [c for i, c in enumerate(cells) if i not in skip]
    text = cells[named] if named is not None else (max(rest, key=len) if rest else "")
    text = re.sub(r"\s+", " ", text.replace("**", ""))[:100]
    return f"{ident}: {text}" if ident and ident != text else text


def _first_word(cell: str) -> str:
    return re.split(r"[\s:,.;(]", (cell or "").strip().lower(), maxsplit=1)[0]


def parse_markdown_report(text: str, source: str) -> list:
    """Punkte aus den Abschnitten "Vor dem Launch" und "Blocker" eines Markdown-Berichts.

    Je Punkt `{"source", "section", "label", "state", "deferral"}`, `state` ist
    `done`, `deferred` oder `open`.
    """
    items = []
    level, section = None, None
    header = None
    current = None

    def flush():
        nonlocal current
        if current:
            items.append(current)
            current = None

    for line in (text or "").splitlines():
        heading = HEADING.match(line)
        if heading:
            flush()
            header = None
            depth, title = len(heading.group(1)), heading.group(2)
            if section is not None and depth <= level:
                section = None
            if section is None and LAUNCH_HEADING.search(title) and not AFTER_HEADING.search(title):
                level, section = depth, title
            continue
        if section is None:
            continue
        if line.lstrip().startswith("|"):
            flush()
            cells = _cells(line)
            if header is None:
                header = [c.lower() for c in cells]
                continue
            if _is_separator(cells):
                continue
            status_col = next((i for i, h in enumerate(header) if h in STATUS_COLUMNS), None)
            owner_col = next((i for i, h in enumerate(header) if h in OWNER_COLUMNS), None)
            status = cells[status_col] if status_col is not None and status_col < len(cells) else ""
            owner = cells[owner_col] if owner_col is not None and owner_col < len(cells) else ""
            row_text = " | ".join(cells)
            state, deferral = "open", None
            if status and _first_word(status) in DONE_WORDS:
                state = "done"
            else:
                deferral = _deferral(status or row_text, owner)
                state = "deferred" if deferral else "open"
            items.append({"source": source, "section": section, "label": _label(cells, header, {status_col, owner_col}),
                          "state": state, "deferral": deferral})
            continue
        header = None
        item = LIST_ITEM.match(line)
        if item and len(item.group(1)) < 2:
            flush()
            box, body = item.group(2), item.group(3)
            current = {"source": source, "section": section, "box": box, "text": body}
        elif current and line.startswith((" ", "\t")) and line.strip():
            current["text"] += " " + line.strip()
        else:
            flush()
    flush()
    out = []
    for entry in items:
        if "text" not in entry:
            out.append(entry)
            continue
        text = entry["text"]
        deferral = None
        if entry["box"] in ("x", "X") or STATUS_INLINE.search(text):
            state = "done"
        else:
            deferral = _deferral(text)
            state = "deferred" if deferral else "open"
        out.append({"source": entry["source"], "section": entry["section"],
                    "label": re.sub(r"\s+", " ", text.replace("**", ""))[:100], "state": state,
                    "deferral": deferral})
    return out


def parse_findings_json(data, source: str) -> list:
    """Befunde aus `findings.json` (verify-theme), nur die Schweren vor dem Launch."""
    if isinstance(data, dict):
        data = data.get("findings")
    out = []
    for finding in data if isinstance(data, list) else []:
        if not isinstance(finding, dict) or finding.get("severity") not in LAUNCH_SEVERITIES:
            continue
        label = f"{finding.get('severity')}: " + str(finding.get("description") or finding.get("title") or "")[:90]
        deferral = None
        if str(finding.get("status", "")).lower() in CLOSED:
            state = "done"
        elif finding.get("deferred_by") and finding.get("deferred_at"):
            state, deferral = "deferred", {"by": str(finding["deferred_by"]), "at": str(finding["deferred_at"])[:10]}
        else:
            state = "open"
        out.append({"source": source, "section": finding.get("severity"), "label": label, "state": state,
                    "deferral": deferral})
    return out


def resolve_path(raw: str, workspace: Path, config: dict) -> str:
    """`~`, `{drive_path}` und relative Pfade ab dem Workspace auflösen."""
    text = str(raw).replace("{drive_path}", str(config.get("drive_path") or ""))
    text = os.path.expanduser(text)
    return text if os.path.isabs(text) else str(Path(workspace) / text)


def report_files(entries: list, workspace: Path, config: dict) -> tuple:
    """Berichtsdateien aus `report_paths`: `(dateien, nicht gefundene Einträge)`.

    Ein Ordner liefert seine `*.md` und `findings.json`, nicht rekursiv; ein
    Muster wird per glob aufgelöst.
    """
    files, unresolved = [], []
    for entry in entries or []:
        path = resolve_path(entry, workspace, config)
        matches = sorted(glob.glob(path)) if any(ch in path for ch in "*?[") else [path]
        found = []
        for match in matches:
            candidate = Path(match).resolve()
            if candidate.is_dir():
                found += sorted(p for p in candidate.iterdir()
                                if p.is_file() and (p.suffix == ".md" or p.name == "findings.json"))
            elif candidate.is_file():
                found.append(candidate)
        if not found:
            unresolved.append(str(entry))
        files += [f for f in found if f not in files]
    return files, unresolved


def read_report(path: Path) -> list | None:
    """Punkte einer Berichtsdatei; None, wenn sie nicht lesbar ist."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if Path(path).suffix == ".json":
        try:
            return parse_findings_json(json.loads(text), Path(path).name)
        except ValueError:
            return None
    return parse_markdown_report(text, Path(path).name)


def is_report(path: Path, items: list | None) -> bool:
    """Ein Markdown ohne Abschnitt "Vor dem Launch" oder "Blocker" ist kein Prüfbericht für den Launch."""
    return items is not None and (Path(path).suffix == ".json" or bool(items))


# ---------------------------------------------------------------------------
# Prüfliste aus der Bestandsaufnahme
# ---------------------------------------------------------------------------

def parse_checklist(text: str) -> list:
    """Punkte der Form `- [ ] **P07** Text`, Folgezeilen eingerückt; je Punkt Kennung, Text, abgehakt."""
    items, current = [], None
    for line in (text or "").splitlines():
        match = CHECKLIST_ITEM.match(line)
        if match:
            current = {"id": match.group(2), "done": match.group(1) in ("x", "X"), "text": match.group(3).strip()}
            items.append(current)
        elif current and line.startswith((" ", "\t")) and line.strip():
            current["text"] += " " + line.strip()
        else:
            current = None
    return items


def checks_for(text: str) -> list:
    """Prüfungen des Launch-Checks, die ein Punkt der Prüfliste nennt."""
    return [check_id for check_id, pattern in CHECK_KEYWORDS if pattern.search(text or "")]


def evaluate_checklist(items: list, statuses: dict) -> dict:
    """Je Punkt `done`, `deferred`, `covered` oder `open`.

    `statuses`: Status der Prüfungen dieses Laufs nach ID. Ein offener Punkt gilt
    als abgedeckt, wenn er mindestens eine Prüfung nennt und jede genannte `ok` ist.
    """
    out = {"done": [], "deferred": [], "covered": [], "open": []}
    for item in items:
        if item["done"]:
            out["done"].append(item)
            continue
        deferral = _deferral(item["text"])
        if deferral:
            out["deferred"].append({**item, "deferral": deferral})
            continue
        checks = checks_for(item["text"])
        if checks and all(statuses.get(c) == "ok" for c in checks):
            out["covered"].append({**item, "checks": checks})
        else:
            out["open"].append({**item, "checks": checks,
                                "failing": [c for c in checks if statuses.get(c) != "ok"]})
    return out
