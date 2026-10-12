#!/usr/bin/env python3
"""Die eine Liste offener Punkte einer Migration: `migration/open-items.json`.

Am 07.10.2026 ging eine Migration live, obwohl ihre SEO-Lücken seit Wochen
aufgeschrieben waren, in der Prüfliste der Bestandsaufnahme und im Prüfbericht
unter "Vor dem Launch". Offene Punkte lagen am Ende in neun Listen, jede mit
eigener Nummerierung und eigenem Statuswort, und keine hatte einen Schritt, der
sie vor dem nächsten Schritt liest. Seitdem gelten vier Regeln:

1. Eine Liste offener Punkte je Projekt, mit genau drei Status: `open`, `done`
   mit Beleg, `deferred` mit Person und Datum. Prüfberichte, Prüflisten,
   Testrunden und Portal sind Ansichten darauf oder schreiben hinein, sie führen
   keinen eigenen Stand.
2. Keine Liste ohne Verbraucher: jeder Punkt nennt das Gate, das ihn liest
   (`gate`).
3. Ein Gate hält an, es fragt nicht. `run_state` verweigert G4 und G5, solange
   ein Punkt ihres Gates offen ist; `launch-check` meldet `missing`.
4. Jede Migration läuft als Migrationslauf; `run_state init` legt diese Liste an.

Die Liste liegt fest unter `migration/open-items.json`, unabhängig von der
Lauf-ID, weil sie das ganze Projekt überdauert und jede Skill sie ohne Lauf
findet. Daneben `migration/open-items.md`, nach jedem Schreiben neu erzeugt, nie
von Hand geändert. Nicht unter `migration/verify/`: dort sucht `launch-check`
den jüngsten Prüfbericht, und ein späterer Lauf von `verify-theme` hätte die
Liste verdeckt.

Andere Listen kommen über `import` hinein. Gleich ist ein Punkt, wenn eine seiner
Kennungen (`id` oder `source_ids`) passt; ein bekannter Punkt behält seinen
Status, auch wenn die Quelle etwas anderes sagt. Die Abweichung steht als
`drift` in der Ausgabe, damit jemand sie bewusst in der Liste nachzieht. Ein
fälschlich erledigter Punkt fällt niemandem auf, ein fälschlich offener sofort.

Eine Kennung zählt nur, wenn sie genau einen Punkt bezeichnet. Am 08.10.2026
trug in einem Pilot jeder Befund eines `findings.json` die Sammelkennung LC-2.7
einer Prüflistenzeile ("Testrunde, offene Punkte") in `source_ids`; der Import
legte daraufhin sechs Testpunkte zu einem zusammen, und Erledigen oder
Verschieben des einen traf still die anderen. Seitdem gilt: eine Kennung, die im
selben Import mehrere verschiedene Punkte tragen, ist mehrdeutig und wird nicht
zum Zuordnen benutzt; ebenso eine, die in der Liste mehrere Punkte kennen, ohne
dass einer sie als `id` führt. Beides steht als `ambiguous` in der Ausgabe. Die
Kennung bleibt als Herkunft in `source_ids`. Trägt ein Punkt nur mehrdeutige
Kennungen, bekommt er eine eigene aus Quelle und Titel.

Aufruf (aus dem Workspace):
    python3 -m theme.open_items init [--project <name>]
    python3 -m theme.open_items add --title <text> [--id <id>] [--description <text>]
        [--severity blocker|before_launch|after_launch] [--gate <gate>] [--owner <name>]
        [--source <text>] [--source-id <id> ...] [--link <url> ...]
    python3 -m theme.open_items done --id <id> --evidence <text>
    python3 -m theme.open_items defer --id <id> --by <name> --at <YYYY-MM-DD> [--reason <text>]
    python3 -m theme.open_items reopen --id <id> --reason <text>
    python3 -m theme.open_items import --kind checklist|report|findings|test-round --path <file> [--gate <gate>]
    python3 -m theme.open_items list [--status <status>] [--severity <severity>] [--gate <gate>]
    python3 -m theme.open_items gate --gate G4-acceptance|G5-go-live|after_launch
    python3 -m theme.open_items sources
    python3 -m theme.open_items close-covered --launch-check <launch-check.json>
    python3 -m theme.open_items sync-test-round --path <test.json>
    python3 -m theme.open_items render
    python3 -m theme.open_items validate

Ausgabe je Aufruf eine JSON-Zeile. Exit 0 heißt fertig ohne Befund, 1 heißt
offene Punkte (`gate`, `sources`), 2 heißt Fehler.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config
from theme import launch_findings

SCHEMA_VERSION = 1
KIND = "open-items"
LIST_PATH = Path("migration") / "open-items.json"
VIEW_PATH = Path("migration") / "open-items.md"

STATUSES = ("open", "done", "deferred")
SEVERITIES = ("blocker", "before_launch", "after_launch")
#: Wer einen Punkt liest: die beiden Gates der Migration und die Nachsorge (Abschluss von Phase 10).
GATES = ("G4-acceptance", "G5-go-live", "after_launch")
DEFAULT_GATE = {"blocker": "G4-acceptance", "before_launch": "G5-go-live", "after_launch": "after_launch"}
#: Welche Punkte ein Gate anhalten. Kumulativ: ein Punkt für G4, der nach G4 wieder aufgeht, hält auch G5.
GATE_READS = {
    "G4-acceptance": ("G4-acceptance",),
    "G5-go-live": ("G4-acceptance", "G5-go-live"),
    "after_launch": GATES,
}
GATE_LABEL = {"G4-acceptance": "Abnahme (G4)", "G5-go-live": "Go-Live (G5)", "after_launch": "Nach dem Launch"}
STATUS_LABEL = {"open": "offen", "done": "erledigt", "deferred": "verschoben"}
SOURCE_KINDS = ("checklist", "report", "findings", "test-round")
#: Status eines Testpunkts, die als offene Arbeit zählen (test-round); ohne Status zählt ein Punkt nicht.
TEST_OPEN = ("open", "in_progress", "decision")

#: Eine Kennung in einem Bericht: B-01, S-03, P07, LC-1.7, TP-06, V1-06. Ein Wort ohne Ziffer (SEO) ist
#: keine, eine einzelne Ziffer ohne Bindestrich auch nicht: "Zweite H1" oder "GA4" sind Text, keine Kennung.
LOCAL_ID = re.compile(r"(?<![\w-])([A-Z][A-Z0-9]{0,5}(?:-\d+(?:\.\d+)?|\d{2,}))(?![\w-])")
GERMAN_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")


class OpenItemsError(Exception):
    """Eine Liste oder ein Aufruf, der so nicht weitergehen darf."""


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def list_path(workspace) -> Path:
    return Path(workspace) / LIST_PATH


def view_path(workspace) -> Path:
    return Path(workspace) / VIEW_PATH


def exists(workspace) -> bool:
    return list_path(workspace).is_file()


def iso_date(text) -> str | None:
    """`JJJJ-MM-TT` oder `TT.MM.JJJJ` als ISO-Datum, sonst None."""
    raw = str(text or "").strip()[:10]
    match = GERMAN_DATE.match(str(text or "").strip())
    if match:
        raw = f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def short_hash(*parts) -> str:
    text = "|".join(re.sub(r"\s+", " ", str(p or "")).strip().lower() for p in parts)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def link_urls(links) -> list:
    """Links als Liste von URLs; `{label, url}` wie in Befunden und Testpunkten wird zur URL."""
    out = []
    for link in links or []:
        url = link.get("url") if isinstance(link, dict) else link
        if isinstance(url, str) and url.strip() and url not in out:
            out.append(url.strip())
    return out


def clip(text, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "").replace("**", "")).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def validate(data) -> list:
    """Fehler der Liste als Sätze; leer heißt gültig."""
    if not isinstance(data, dict):
        return ["die Liste ist kein JSON-Objekt"]
    errors = []
    if data.get("kind") != KIND:
        errors.append(f"kind ist {data.get('kind')!r}, erwartet {KIND!r}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version ist {data.get('schema_version')!r}, erwartet {SCHEMA_VERSION}")
    items = data.get("items")
    if not isinstance(items, list):
        return errors + ["items fehlt oder ist keine Liste"]
    seen = set()
    for index, item in enumerate(items):
        where = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} ist kein Objekt")
            continue
        ident = item.get("id")
        if not isinstance(ident, str) or not ident.strip():
            errors.append(f"{where}: id fehlt")
        elif ident in seen:
            errors.append(f"{where}: id {ident} doppelt")
        else:
            seen.add(ident)
            where = f"{ident}"
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            errors.append(f"{where}: title fehlt")
        if item.get("status") not in STATUSES:
            errors.append(f"{where}: status {item.get('status')!r} nicht in {STATUSES}")
        if item.get("severity") not in SEVERITIES:
            errors.append(f"{where}: severity {item.get('severity')!r} nicht in {SEVERITIES}")
        if item.get("gate") not in GATES:
            errors.append(f"{where}: gate {item.get('gate')!r} nicht in {GATES}")
        for key in ("source_ids", "links"):
            value = item.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"{where}: {key} ist keine Liste von Texten")
        for key in ("description", "owner", "source", "evidence", "deferred_by"):
            if key in item and not isinstance(item[key], str):
                errors.append(f"{where}: {key} ist kein Text")
        if item.get("status") == "done" and not str(item.get("evidence") or "").strip():
            errors.append(f"{where}: erledigt ohne Beleg (evidence)")
        if item.get("status") == "deferred":
            if not str(item.get("deferred_by") or "").strip():
                errors.append(f"{where}: verschoben ohne Person (deferred_by)")
            if iso_date(item.get("deferred_at")) != str(item.get("deferred_at") or ""):
                errors.append(f"{where}: verschoben ohne Datum JJJJ-MM-TT (deferred_at)")
    return errors


# ---------------------------------------------------------------------------
# Die Liste
# ---------------------------------------------------------------------------

class OpenItems:
    def __init__(self, workspace, data: dict):
        self.workspace = Path(workspace)
        self.data = data

    @property
    def items(self) -> list:
        return self.data["items"]

    def get(self, ident: str) -> dict:
        for item in self.items:
            if item["id"] == ident:
                return item
        raise OpenItemsError(f"kein Punkt mit id {ident!r}")

    @staticmethod
    def _knows(item: dict, key: str) -> bool:
        return key == item["id"] or key in (item.get("source_ids") or [])

    def match(self, keys: list, alias: str = "", context: str = "", conflicts: list | None = None) -> dict | None:
        """Der Punkt, den eine der Kennungen schon trägt, in der Reihenfolge der Kennungen.

        Eine Kennung zählt, wenn ein Punkt sie als `id` führt oder genau ein Punkt sie kennt. Kennen
        sie mehrere nur aus `source_ids`, ist sie eine Sammelkennung und zählt nicht; sie landet in
        `conflicts` als `(kennung, [ids])`.

        `alias` mit `context`: eine Kennung, die allein mehrdeutig ist (TP-06 gibt es in jeder
        Testrunde), zählt nur, wenn `source` des Punkts den Kontext nennt, etwa die Lauf-ID.
        """
        for key in keys:
            if not key:
                continue
            owners = [i for i in self.items if self._knows(i, key)]
            primary = [i for i in owners if i["id"] == key]
            if primary:
                return primary[0]
            if len(owners) == 1:
                return owners[0]
            if owners and conflicts is not None:
                conflicts.append((key, [i["id"] for i in owners]))
        if alias and context:
            for item in self.items:
                if self._knows(item, alias) and context in str(item.get("source") or ""):
                    return item
        return None

    def free_id(self, preferred: str) -> str:
        taken = {i["id"] for i in self.items}
        if preferred not in taken:
            return preferred
        n = 2
        while f"{preferred}-{n}" in taken:
            n += 1
        return f"{preferred}-{n}"

    def add(self, *, title: str, ident: str = "", description: str = "", severity: str = "before_launch",
            gate: str = "", owner: str = "", source: str = "", source_ids: list | None = None,
            links: list | None = None, status: str = "open", evidence: str = "", deferred_by: str = "",
            deferred_at: str = "", today: str | None = None) -> dict:
        """Legt einen Punkt an; `ident` muss frei sein, sonst Fehler (zum Ändern gibt es done, defer, reopen)."""
        if not str(title).strip():
            raise OpenItemsError("ein Punkt braucht einen Titel")
        if severity not in SEVERITIES:
            raise OpenItemsError(f"severity muss eines von {SEVERITIES} sein")
        gate = gate or DEFAULT_GATE[severity]
        if gate not in GATES:
            raise OpenItemsError(f"gate muss eines von {GATES} sein")
        source_ids = [s for s in (source_ids or []) if s]
        if ident:
            if any(i["id"] == ident for i in self.items):
                raise OpenItemsError(f"id {ident} gibt es schon")
        else:
            ident = self.free_id(f"OI-{len(self.items) + 1:03d}")
        today = today or date.today().isoformat()
        item = {"id": ident, "title": str(title).strip(), "description": description or "", "severity": severity,
                "gate": gate, "status": "open", "owner": owner or "", "evidence": "", "source": source or "",
                "source_ids": source_ids, "links": link_urls(links), "created_at": today, "updated_at": today}
        if status == "done":
            self._close(item, evidence, today)
        elif status == "deferred":
            self._defer(item, deferred_by, deferred_at, evidence, today)
        self.items.append(item)
        return item

    @staticmethod
    def _close(item: dict, evidence: str, today: str) -> None:
        if not str(evidence or "").strip():
            raise OpenItemsError(f"{item['id']}: erledigt nur mit Beleg (--evidence)")
        item.update(status="done", evidence=str(evidence).strip(), updated_at=today)
        item.pop("deferred_by", None)
        item.pop("deferred_at", None)

    @staticmethod
    def _defer(item: dict, by: str, at: str, reason: str, today: str) -> None:
        when = iso_date(at)
        if not str(by or "").strip() or not when:
            raise OpenItemsError(f"{item['id']}: verschoben nur mit Person (--by) und Datum JJJJ-MM-TT (--at)")
        item.update(status="deferred", deferred_by=str(by).strip(), deferred_at=when, updated_at=today)
        if reason:
            item["evidence"] = str(reason).strip()

    def set_done(self, ident: str, evidence: str, today: str | None = None) -> dict:
        item = self.get(ident)
        self._close(item, evidence, today or date.today().isoformat())
        return item

    def defer(self, ident: str, by: str, at: str, reason: str = "", today: str | None = None) -> dict:
        item = self.get(ident)
        self._defer(item, by, at, reason, today or date.today().isoformat())
        return item

    def reopen(self, ident: str, reason: str, today: str | None = None) -> dict:
        if not str(reason or "").strip():
            raise OpenItemsError("wieder offen nur mit Grund (--reason)")
        item = self.get(ident)
        item.update(status="open", evidence=f"wieder offen: {reason.strip()}",
                    updated_at=today or date.today().isoformat())
        item.pop("deferred_by", None)
        item.pop("deferred_at", None)
        return item

    def blocking(self, gate: str) -> list:
        """Offene Punkte, die dieses Gate anhalten."""
        if gate not in GATE_READS:
            raise OpenItemsError(f"unbekanntes Gate: {gate!r}, erlaubt sind {GATES}")
        return [i for i in self.items if i["status"] == "open" and i["gate"] in GATE_READS[gate]]

    def counts(self) -> dict:
        out = {s: sum(1 for i in self.items if i["status"] == s) for s in STATUSES}
        out["open_by_gate"] = {g: sum(1 for i in self.items if i["status"] == "open" and i["gate"] == g)
                               for g in GATES}
        return out

    def merge(self, candidates: list, today: str | None = None, gate: str = "") -> dict:
        """Kandidaten aus einer Quelle übernehmen. Neue Punkte anlegen, bekannte nur um Kennungen ergänzen."""
        today = today or date.today().isoformat()
        created, known, drift = [], [], []
        candidates, ambiguous = resolve_keys(candidates)
        for cand in candidates:
            conflicts = []
            item = self.match(cand["keys"], cand.get("alias", ""), cand.get("context", ""), conflicts)
            ambiguous += [{"key": key, "shared_by": ids, "in": "list", "where": cand["source"]}
                          for key, ids in conflicts if not any(a["key"] == key for a in ambiguous)]
            if item:
                known.append(item["id"])
                for key in cand["keys"] + cand["shared_keys"]:
                    if key and key != item["id"] and key not in item.setdefault("source_ids", []):
                        item["source_ids"].append(key)
                for url in cand.get("links") or []:
                    if url not in item.setdefault("links", []):
                        item["links"].append(url)
                if cand["state"] != item["status"]:
                    drift.append({"id": item["id"], "list": item["status"], "source": cand["state"],
                                  "where": cand["source"]})
                continue
            item = self.add(
                title=cand["title"], ident=self.free_id(cand["preferred_id"]), description=cand.get("description", ""),
                severity=cand["severity"], gate=gate or cand.get("gate") or "", owner=cand.get("owner", ""),
                source=cand["source"],
                source_ids=[k for k in cand["keys"] + cand["shared_keys"] if k != cand["preferred_id"]],
                links=cand.get("links"), status=cand["state"], evidence=cand.get("evidence", ""),
                deferred_by=cand.get("deferred_by", ""), deferred_at=cand.get("deferred_at", ""), today=today)
            if cand["preferred_id"] != item["id"] and cand["preferred_id"] not in item["source_ids"]:
                item["source_ids"].insert(0, cand["preferred_id"])
            created.append(item["id"])
        return {"created": created, "known": len(known), "drift": drift, "ambiguous": ambiguous}

    def unimported(self, candidates: list) -> list:
        """Kandidaten, die in der Quelle nicht erledigt sind und in der Liste fehlen."""
        candidates, _ = resolve_keys(candidates)
        return [c for c in candidates if c["state"] != "done"
                and not self.match(c["keys"], c.get("alias", ""), c.get("context", ""))]

    def save(self, today: str | None = None) -> Path:
        errors = validate(self.data)
        if errors:
            raise OpenItemsError("Liste ungültig, nichts geschrieben: " + "; ".join(errors[:5]))
        self.data["updated_at"] = today or date.today().isoformat()
        path = list_path(self.workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        view = view_path(self.workspace)
        tmp = view.parent / (view.name + ".tmp")
        tmp.write_text(render(self.data), encoding="utf-8")
        os.replace(tmp, view)
        return path


def new(workspace, project: str = "") -> OpenItems:
    return OpenItems(workspace, {"kind": KIND, "schema_version": SCHEMA_VERSION, "project": project,
                                 "updated_at": date.today().isoformat(), "items": []})


def load(workspace) -> OpenItems:
    path = list_path(workspace)
    if not path.is_file():
        raise OpenItemsError(f"{LIST_PATH} fehlt; anlegen mit open_items init (theme-migration, Phase 0)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OpenItemsError(f"{path} ist nicht lesbar ({exc}); nicht neu anlegen, reparieren") from exc
    errors = validate(data)
    if errors:
        raise OpenItemsError(f"{path} ist ungültig: " + "; ".join(errors[:5]))
    return OpenItems(workspace, data)


def init(workspace, project: str = "") -> tuple:
    """Legt die Liste an, wenn sie fehlt: `(liste, angelegt)`. Eine vorhandene bleibt unberührt."""
    if exists(workspace):
        return load(workspace), False
    items = new(workspace, project)
    items.save()
    return items, True


# ---------------------------------------------------------------------------
# Quellen: Prüfliste, Prüfbericht, findings.json, Testrunde
# ---------------------------------------------------------------------------

def candidate(*, preferred_id: str, keys: list, title: str, source: str, state: str, severity: str,
              gate: str = "", description: str = "", owner: str = "", evidence: str = "",
              deferral: dict | None = None, links: list | None = None, alias: str = "", context: str = "",
              fallback_key: str = "", fallback_id: str = "") -> dict:
    """Ein Punkt aus einer Quelle, noch nicht in der Liste.

    `fallback_key` und `fallback_id` sind die Identität, falls jede Kennung in `keys` im selben
    Import auch andere Punkte bezeichnet (`resolve_keys`). Ohne Angabe: Quelle und Titel.
    """
    digest = short_hash(source, preferred_id, title)
    out = {"preferred_id": preferred_id, "keys": keys, "title": clip(title, 140) or preferred_id,
           "description": description, "source": source, "state": state, "severity": severity,
           "gate": gate or DEFAULT_GATE[severity], "owner": owner, "evidence": evidence,
           "links": link_urls(links), "alias": alias, "context": context,
           "fallback_key": fallback_key or f"{source}#{digest}", "fallback_id": fallback_id or f"X-{digest[:6]}"}
    if state == "deferred":
        out["deferred_by"] = (deferral or {}).get("by", "")
        out["deferred_at"] = iso_date((deferral or {}).get("at")) or ""
        if not (out["deferred_by"] and out["deferred_at"]):
            out["state"] = "open"
    if out["state"] == "done" and not out["evidence"]:
        out["evidence"] = f"erledigt laut {source}"
    return out


def resolve_keys(candidates: list) -> tuple:
    """Kennungen, die im selben Import mehrere verschiedene Punkte tragen, aus dem Zuordnen nehmen.

    Gibt `(kandidaten, mehrdeutig)` zurück. Jeder Kandidat ist eine Kopie mit `keys` ohne die
    mehrdeutigen Kennungen und `shared_keys` mit ihnen; sie bleiben als Herkunft in `source_ids`,
    entscheiden aber nicht mehr, welcher Punkt gemeint ist. Bleibt keine Kennung übrig, gilt
    `fallback_key` und `fallback_id`. Verschieden heißt: andere Kennung oder anderer Titel. Derselbe
    Punkt zweimal in einer Quelle ist eine Dublette und bleibt ein Punkt.
    """
    carriers = {}
    for cand in candidates:
        for key in {k for k in cand["keys"] if k}:
            carriers.setdefault(key, {})[(cand["preferred_id"], cand["title"])] = cand["source"]
    shared = {key: owners for key, owners in carriers.items() if len(owners) > 1}
    out = []
    for cand in candidates:
        cand = dict(cand)
        own = [k for k in cand["keys"] if k and k not in shared]
        cand["shared_keys"] = [k for k in cand["keys"] if k in shared]
        if own:
            cand["keys"] = own
            if cand["preferred_id"] in shared:
                cand["preferred_id"] = own[0]
        elif cand["shared_keys"]:
            cand["keys"] = [cand["fallback_key"], cand["fallback_id"]]
            cand["preferred_id"] = cand["fallback_id"]
        out.append(cand)
    ambiguous = []
    for key, owners in sorted(shared.items()):
        ids = sorted({pid for pid, _ in owners})
        if len(ids) < len(owners):
            ids = sorted(f"{pid}: {clip(title, 60)}" for pid, title in owners)
        ambiguous.append({"key": key, "shared_by": ids, "in": "import", "where": sorted(set(owners.values()))[0]})
    return out, ambiguous


def from_checklist(path: Path) -> list:
    """Prüfliste aus Phase 2: `- [ ] **P07** ...`. Sie ist die Abnahme, also Gate G4."""
    path = Path(path)
    out = []
    for entry in launch_findings.parse_checklist(path.read_text(encoding="utf-8")):
        deferral = None if entry["done"] else launch_findings._deferral(entry["text"])
        state = "done" if entry["done"] else ("deferred" if deferral else "open")
        out.append(candidate(preferred_id=entry["id"], keys=[entry["id"]], title=entry["text"].split(". ")[0],
                             description=clip(entry["text"], 600), source=path.name, state=state,
                             severity="before_launch", gate="G4-acceptance",
                             evidence=f"abgehakt in {path.name}" if entry["done"] else "", deferral=deferral))
    return out


def from_report(path: Path) -> list:
    """Abschnitte "Vor dem Launch" und "Blocker" eines Markdown-Berichts."""
    path = Path(path)
    out = []
    for entry in launch_findings.parse_markdown_report(path.read_text(encoding="utf-8"), path.name):
        severity = "blocker" if re.search(r"blocker", entry["section"] or "", re.I) else "before_launch"
        found = LOCAL_ID.search(entry.get("raw") or "")
        local = found.group(1) if found else ""
        key = local or f"{path.name}#{short_hash(entry['label'])}"
        label = entry["label"]
        if local and label.startswith(local):
            label = label[len(local):].lstrip(": ")
        evidence = f"{path.name}: {entry.get('status_text')}" if entry["state"] == "done" and entry.get("status_text") \
            else ""
        # Die angezeigte Kennung (R-...) zählt auch als Schlüssel, sonst lässt sich ein gemeldeter
        # Punkt nicht über `--source-id` einem vorhandenen Punkt zuordnen.
        preferred = local or f"R-{short_hash(entry['label'])[:6]}"
        # Trägt jede Zeile dieselbe Sammelkennung (LC-2.7), gilt dieselbe Identität wie ohne Kennung.
        out.append(candidate(preferred_id=preferred, keys=[key] if local else [key, preferred], title=label,
                             description=clip(entry.get("raw"), 600), source=f"{path.name}, {entry['section']}",
                             state=entry["state"], severity=severity, owner=entry.get("owner", ""),
                             evidence=evidence, deferral=entry.get("deferral"),
                             fallback_key=f"{path.name}#{short_hash(entry['label'])}",
                             fallback_id=f"R-{short_hash(entry['label'])[:6]}"))
    return out


def from_findings(path: Path) -> list:
    """`findings.json` aus `verify-theme` oder eine Liste im selben Format; `info` zählt nicht."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items") if data.get("kind") == KIND else data.get("findings")
    out = []
    for finding in data if isinstance(data, list) else []:
        if not isinstance(finding, dict) or finding.get("severity") not in SEVERITIES:
            continue
        local = str(finding.get("id") or "").strip()
        given = [str(s) for s in finding.get("source_ids") or [] if str(s).strip()]
        fallback = f"verify#{short_hash(finding.get('checker'), finding.get('page_type'), finding.get('description'))}"
        keys = [local] + [s for s in given if s != local] if local else (given or [fallback])
        status = str(finding.get("status") or "").lower()
        if status in launch_findings.CLOSED:
            state = "done"
        elif finding.get("deferred_by") and finding.get("deferred_at"):
            state = "deferred"
        else:
            state = "open"
        gate = finding.get("gate") if finding.get("gate") in GATES else ""
        evidence = str(finding.get("evidence") or "")
        if state == "done" and not evidence:
            evidence = f"Status {status} in {path.name}"
        out.append(candidate(
            preferred_id=local or keys[0].replace("verify#", "V-")[:8], keys=keys,
            title=finding.get("title") or finding.get("description") or local,
            description=str(finding.get("description") or ""), source=str(finding.get("source") or path.name),
            state=state, severity=finding["severity"], gate=gate, owner=str(finding.get("owner") or ""),
            evidence=evidence, links=finding.get("links"),
            deferral={"by": str(finding.get("deferred_by") or ""), "at": str(finding.get("deferred_at") or "")},
            fallback_key=fallback, fallback_id=fallback.replace("verify#", "V-")[:8]))
    return out


def from_test_round(path: Path) -> list:
    """Testpunkte mit `status` aus `test.json`; die Testrunde ist die Abnahme, also Gate G4."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    run_id = path.parent.name
    out = []
    for group in data.get("groups") or [] if isinstance(data, dict) else []:
        for item in group.get("items") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            status = item.get("status")
            if status not in TEST_OPEN + ("done",):
                continue
            resolution = item.get("resolution") if isinstance(item.get("resolution"), dict) else {}
            local = str(item["id"])
            out.append(candidate(
                preferred_id=local, keys=[f"{run_id}:{local}"], alias=local, context=run_id,
                title=item.get("title") or local, description=clip(item.get("text"), 600),
                source=f"Testrunde {run_id} (test.json)", state="done" if status == "done" else "open",
                severity="before_launch", gate="G4-acceptance",
                owner="Team" if status == "decision" else "",
                evidence=clip(resolution.get("text"), 300) if status == "done" else "",
                links=resolution.get("links")))
    return out


READERS = {"checklist": from_checklist, "report": from_report, "findings": from_findings,
           "test-round": from_test_round}


def read_source(kind: str, path) -> list:
    if kind not in READERS:
        raise OpenItemsError(f"--kind muss eines von {SOURCE_KINDS} sein")
    try:
        return READERS[kind](Path(path))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise OpenItemsError(f"{path} nicht lesbar: {type(exc).__name__}: {exc}") from exc


def newest(paths) -> Path | None:
    paths = [p for p in paths if p.is_file()]
    return max(paths, key=lambda p: (p.parent.name, p.stat().st_mtime)) if paths else None


def configured_sources(workspace, config: dict, *, migration: bool = False) -> tuple:
    """Jede Quelle, die Punkte vor dem Launch halten kann: `([(kind, path)], [lücken])`.

    Prüfliste und `report_paths` aus der Config, dazu der jüngste Prüfbericht unter
    `migration/verify/` und die jüngste Testrunde. `migration`: in einem Migrationslauf ist eine
    fehlende Prüfliste eine Lücke, kein Normalfall.
    """
    workspace = Path(workspace)
    block = migration_config(config)
    sources, gaps = [], []
    own = list_path(workspace).resolve()
    checklist = block.get("acceptance_checklist")
    if checklist:
        path = Path(launch_findings.resolve_path(checklist, workspace, config))
        if path.is_file():
            sources.append(("checklist", path))
        else:
            gaps.append(f"Prüfliste nicht gefunden: {checklist}")
    elif migration:
        gaps.append("theme_migration.acceptance_checklist nicht gesetzt")
    entries = [str(p) for p in block.get("report_paths") or [] if str(p).strip()]
    files, unresolved = launch_findings.report_files(entries, workspace, config)
    gaps += [f"Bericht nicht gefunden: {u}" for u in unresolved]
    verify = newest((workspace / "migration" / "verify").glob("*/findings.json"))
    for path in ([verify] if verify else []) + files:
        path = Path(path).resolve()
        if path == own or any(p == path for _, p in sources):
            continue
        sources.append(("findings" if path.suffix == ".json" else "report", path))
    test = newest((workspace / "reporting" / "runs").glob("*-test/test.json"))
    if test:
        sources.append(("test-round", test.resolve()))
    return sources, gaps


def source_gaps(items: OpenItems | None, workspace, config: dict, *, migration: bool = False,
                kinds: tuple = SOURCE_KINDS) -> dict:
    """Was in einer Quelle steht und in der Liste fehlt, dazu Quellen, die sich nicht lesen lassen.

    Erledigtes in einer Quelle fehlt nie: es verlangt nichts mehr. Ohne Liste (`items` None) zählt
    jeder nicht erledigte Punkt einer Quelle als fehlend.
    """
    sources, gaps = configured_sources(workspace, config, migration=migration)
    missing, read = [], []
    for kind, path in sources:
        if kind not in kinds:
            continue
        try:
            cands = read_source(kind, path)
        except OpenItemsError as exc:
            gaps.append(str(exc))
            continue
        if kind == "report" and not cands:
            continue  # ein Markdown ohne Abschnitt "Vor dem Launch" oder "Blocker" ist kein Bericht
        read.append(f"{path.name} ({kind})")
        pending = [c for c in cands if c["state"] != "done"] if items is None else items.unimported(cands)
        missing += [{"source": path.name, "kind": kind, "id": c["preferred_id"], "title": c["title"],
                     "state": c["state"]} for c in pending]
    return {"sources": read, "missing": missing, "gaps": gaps}


# ---------------------------------------------------------------------------
# Abgedeckt durch den Launch-Check, Rückschreiben in die Testrunde
# ---------------------------------------------------------------------------

def close_covered(items: OpenItems, report: dict, where: str, today: str | None = None) -> list:
    """Offene Punkte, deren genannte Prüfungen im Launch-Check alle `ok` sind, als erledigt mit Beleg."""
    statuses = {c.get("id"): c.get("status") for c in report.get("checks") or [] if isinstance(c, dict)}
    stamp = str(report.get("checked_at") or "")[:10]
    closed = []
    for item in items.items:
        if item["status"] != "open":
            continue
        checks = launch_findings.checks_for(f"{item['title']} {item.get('description', '')}")
        if checks and all(statuses.get(c) == "ok" for c in checks):
            items.set_done(item["id"], f"launch-check {stamp}: {', '.join(checks)} bestanden ({where})", today)
            closed.append({"id": item["id"], "checks": checks})
    return closed


def sync_test_round(items: OpenItems, path: Path) -> list:
    """Schreibt den Status der Liste in `test.json` zurück, damit das Portal denselben Stand zeigt.

    Die Liste ist die Quelle: erledigt wird `done`; ein Testpunkt, der dort `done` sagt, in der Liste
    aber offen ist, wird `open`. Verschoben kennt das Portal nicht, der Punkt bleibt, wie er ist.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    run_id = Path(path).parent.name
    changed = []
    for group in data.get("groups") or []:
        for test_item in group.get("items") or []:
            if not isinstance(test_item, dict) or test_item.get("status") not in TEST_OPEN + ("done",):
                continue
            item = items.match([f"{run_id}:{test_item['id']}"], str(test_item["id"]), run_id)
            if not item:
                continue
            target = test_item["status"]
            if item["status"] == "done":
                target = "done"
            elif item["status"] == "open" and test_item["status"] == "done":
                target = "open"
            if target != test_item["status"]:
                changed.append({"id": test_item["id"], "from": test_item["status"], "to": target})
                test_item["status"] = target
    if changed:
        tmp = Path(path).parent / (Path(path).name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return changed


# ---------------------------------------------------------------------------
# Ansicht
# ---------------------------------------------------------------------------

def _cell(text) -> str:
    return clip(text, 200).replace("|", "\\|")


def render(data: dict) -> str:
    """Markdown-Ansicht der Liste, je Gate eine Tabelle, offene Punkte zuerst."""
    items = data.get("items") or []
    counts = {s: sum(1 for i in items if i.get("status") == s) for s in STATUSES}
    lines = ["# Offene Punkte", "",
             f"Erzeugt aus `{LIST_PATH.as_posix()}` am {data.get('updated_at')}, nicht von Hand ändern. "
             "Ändern über `python3 -m theme.open_items done|defer|reopen`.", "",
             f"{len(items)} Punkte: {counts['open']} offen, {counts['done']} erledigt, "
             f"{counts['deferred']} verschoben.", ""]
    order = {"open": 0, "deferred": 1, "done": 2}
    for gate in GATES:
        rows = sorted((i for i in items if i.get("gate") == gate), key=lambda i: (order.get(i.get("status"), 3), i["id"]))
        if not rows:
            continue
        opened = sum(1 for i in rows if i.get("status") == "open")
        lines += [f"## {GATE_LABEL[gate]}: {opened} offen", "",
                  "| ID | Punkt | Schwere | Wer | Stand |", "|---|---|---|---|---|"]
        for item in rows:
            status = item.get("status")
            if status == "done":
                state = f"erledigt: {item.get('evidence', '')}"
            elif status == "deferred":
                state = f"verschoben von {item.get('deferred_by')} am {item.get('deferred_at')}"
                state += f": {item['evidence']}" if item.get("evidence") else ""
            else:
                state = "offen"
            title = item.get("title", "")
            if item.get("links"):
                title += f" ([Link]({item['links'][0]}))"
            lines.append(f"| {_cell(item['id'])} | {_cell(title)} | {item.get('severity')} | "
                         f"{_cell(item.get('owner'))} | {_cell(state)} |")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def brief(item: dict) -> dict:
    return {k: item.get(k) for k in ("id", "title", "severity", "gate", "status", "owner")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.open_items", description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("init", "add", "done", "defer", "reopen", "import", "list", "gate",
                                            "sources", "close-covered", "sync-test-round", "render", "validate"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--project", default="")
    parser.add_argument("--id", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--severity", default="")
    parser.add_argument("--gate", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--link", action="append", default=[])
    parser.add_argument("--evidence", default="")
    parser.add_argument("--by", default="")
    parser.add_argument("--at", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--kind", default="")
    parser.add_argument("--path", default="")
    parser.add_argument("--status", default="")
    parser.add_argument("--launch-check", default="")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    code = EXIT_OK
    try:
        if args.command == "init":
            items, created = init(workspace, args.project)
            emit({"ok": True, "created": created, "path": str(list_path(workspace)), "counts": items.counts()})
            return EXIT_OK
        if args.command == "validate":
            path = list_path(workspace)
            errors = validate(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() \
                else [f"{LIST_PATH} fehlt"]
            emit({"ok": not errors, "errors": errors})
            return EXIT_OK if not errors else EXIT_FINDINGS
        items = load(workspace)
        if args.command == "add":
            severity = args.severity or "before_launch"
            item = items.add(title=args.title, ident=args.id, description=args.description, severity=severity,
                             gate=args.gate, owner=args.owner, source=args.source, source_ids=args.source_id,
                             links=args.link)
            items.save()
            result = {"ok": True, "item": brief(item)}
        elif args.command == "done":
            item = items.set_done(args.id, args.evidence)
            items.save()
            result = {"ok": True, "item": brief(item)}
        elif args.command == "defer":
            item = items.defer(args.id, args.by, args.at, args.reason)
            items.save()
            result = {"ok": True, "item": brief(item)}
        elif args.command == "reopen":
            item = items.reopen(args.id, args.reason)
            items.save()
            result = {"ok": True, "item": brief(item)}
        elif args.command == "import":
            if not args.path:
                raise OpenItemsError("--path fehlt")
            if args.gate and args.gate not in GATES:
                raise OpenItemsError(f"--gate muss eines von {GATES} sein")
            summary = items.merge(read_source(args.kind, args.path), gate=args.gate)
            items.save()
            result = {"ok": True, "kind": args.kind, "path": args.path, **summary, "counts": items.counts()}
        elif args.command == "list":
            rows = [i for i in items.items
                    if (not args.status or i["status"] == args.status)
                    and (not args.severity or i["severity"] == args.severity)
                    and (not args.gate or i["gate"] in GATE_READS.get(args.gate, (args.gate,)))]
            result = {"ok": True, "count": len(rows), "items": [brief(i) for i in rows]}
        elif args.command == "gate":
            blocking = items.blocking(args.gate)
            result = {"ok": True, "gate": args.gate, "open": len(blocking), "items": [brief(i) for i in blocking]}
            code = EXIT_FINDINGS if blocking else EXIT_OK
        elif args.command == "sources":
            config = load_config(workspace)
            gaps = source_gaps(items, workspace, config, migration=True)
            result = {"ok": True, **gaps}
            code = EXIT_FINDINGS if gaps["missing"] or gaps["gaps"] else EXIT_OK
        elif args.command == "close-covered":
            if not args.launch_check:
                raise OpenItemsError("--launch-check fehlt")
            report = json.loads(Path(args.launch_check).read_text(encoding="utf-8"))
            closed = close_covered(items, report, Path(args.launch_check).parent.name)
            items.save()
            result = {"ok": True, "closed": closed, "counts": items.counts()}
        elif args.command == "sync-test-round":
            if not args.path:
                raise OpenItemsError("--path fehlt")
            result = {"ok": True, "changed": sync_test_round(items, Path(args.path))}
        else:  # render
            items.save(items.data.get("updated_at"))
            result = {"ok": True, "path": str(view_path(workspace))}
    except (OpenItemsError, ConfigError, OSError, ValueError) as exc:
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    emit(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
