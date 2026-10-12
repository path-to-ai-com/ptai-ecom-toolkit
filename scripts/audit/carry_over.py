#!/usr/bin/env python3
"""Bestand prüfen: die Maßnahmen der Marke im Audit eines neuen Stores.

Spec `ptai-portal` 2026-10-08 "eine Marke, mehrere Stores", Abschnitt 8. Kommt
ein Store zu einer Marke dazu, bekommt er ein Audit, und dieses Audit geht die
Maßnahmenliste der Marke durch. Verworfen wurden "erst übertragen, später
auditieren" (ohne Baseline lässt sich die Wirkung nie zeigen) und "erst eigenes
Audit, dann abgleichen" (erzeugt Dubletten, die jemand von Hand zusammenführt).

Jede Maßnahme der Marke, die nicht für diesen Store gilt und die nicht
verworfen oder überholt ist, weder in der Datei noch von der Marke im Cockpit
gemeldet, bekommt eines von drei Ergebnissen:

=================  =========================================================
``applies``        trifft zu: der Store kommt in `shops`, Status `open`, mit
                   Beleg und Befund aus diesem Lauf
``fulfilled``      schon erfüllt: der Store kommt in `shops`, Status
                   `implemented`, gemessen in diesem Lauf. So ist sichtbar,
                   dass der Store geprüft wurde.
``not_applicable`` passt nicht: der Store kommt nicht dazu, der Bericht nennt
                   die Maßnahme mit Grund unter "Nicht übertragen"
=================  =========================================================

Ausgenommen ist eine Maßnahme, deren sämtliche Stores verworfen oder überholt
sind (in der Datei oder gemeldet): die Marke hat sie aufgegeben. Ebenso eine,
die die Marke für diesen Store schon verworfen gemeldet hat.

**Ablauf in drei Schritten, damit das Urteil bei der Sitzung bleibt.** Ob eine
Maßnahme zu einem Store passt, entscheidet kein Skript, sondern wer die
Snapshots und Befunde dieses Laufs liest. Das Skript sorgt für den Rest:

1. `prepare` holt die Meldungen aus dem Cockpit (Abbruch, wenn es nicht
   erreichbar ist), wählt die Kandidaten und legt
   `reporting/runs/<run-id>/carry-over.json` an.
2. Die Sitzung trägt je Kandidat `outcome` ein, dazu `evidence` (und
   `finding_id`, `evidence_text`, wo vorhanden) oder bei `not_applicable` den
   `reason`.
3. `apply` holt die Meldungen erneut, schreibt unter der Sperre der Marke und
   hält das Ergebnis in derselben Datei fest. Danach entstehen neue Maßnahmen
   nur für Befunde, die keine übertragene Maßnahme abdeckt
   (`covered_findings()`).

CLI:
    python3 -m audit.carry_over prepare --workspace . --run-id <run-id>
    python3 -m audit.carry_over apply --workspace . --run-id <run-id>
    python3 -m audit.carry_over covered --workspace . --run-id <run-id>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from audit import brand as brand_mod
from audit import measures
from audit import portal

#: Die Datei im Lauf-Ordner. Sie ist Arbeitsblatt der Sitzung und Beleg für den
#: Bericht zugleich ("Nicht übertragen").
FILE = "carry-over.json"

#: Die drei Ergebnisse aus Spec Abschnitt 8, Punkt 3.
OUTCOMES = ("applies", "fulfilled", "not_applicable")

#: Status, den ein Ergebnis in `by_shop.<shop>` setzt.
STATUS_BY_OUTCOME = {"applies": "open", "fulfilled": "implemented"}


class CarryOverError(ValueError):
    """Das Arbeitsblatt passt nicht: fehlendes Ergebnis, fehlender Beleg, falscher Lauf."""


def path_for(workspace, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / FILE


def _dead_everywhere(measure: dict, exclusions: dict) -> bool:
    """Sind alle Stores der Maßnahme verworfen oder überholt, in Datei oder Meldung?"""
    shops = measure.get("shops") or []
    by_shop = measure.get("by_shop") or {}
    if not shops:
        return False
    return all((by_shop.get(s) or {}).get("status") in measures.EXCLUDING_STATUS
               or measures.is_excluded(exclusions, measure.get("id"), s)
               for s in shops)


def candidates(backlog: dict, shop: str, exclusions: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Welche Maßnahmen der Marke gegen `shop` geprüft werden, und welche nicht.

    Gibt `(to_check, skipped)` zurück. `to_check` sind die Maßnahmen selbst,
    `skipped` je ausgenommene Maßnahme `id`, `title` und `reason`. Maßnahmen,
    die schon für `shop` gelten, kommen in keiner der beiden Listen vor: sie
    prüft der Lauf über ihre Prüfregel wie jeder Folgelauf.
    """
    if not measures.is_v2(backlog):
        return [], []
    exclusions = exclusions or {}
    to_check, skipped = [], []
    for measure in backlog.get("measures") or []:
        if shop in (measure.get("shops") or []):
            continue
        if measures.is_excluded(exclusions, measure.get("id"), shop):
            skipped.append({"id": measure["id"], "title": measure.get("title"),
                            "reason": f"von der Marke für {shop} verworfen gemeldet"})
            continue
        if _dead_everywhere(measure, exclusions):
            skipped.append({"id": measure["id"], "title": measure.get("title"),
                            "reason": "in allen Stores verworfen oder überholt"})
            continue
        to_check.append(measure)
    return to_check, skipped


def _sheet_entry(measure: dict) -> dict:
    """Ein Kandidat im Arbeitsblatt: was die Sitzung zum Prüfen braucht, und die
    leeren Felder für ihr Ergebnis."""
    by_shop = measure.get("by_shop") or {}
    return {
        "id": measure["id"],
        "title": measure.get("title"),
        "discipline": measure.get("discipline"),
        "check_rule": measure.get("check_rule"),
        "data_source": measure.get("data_source"),
        "shops": list(measure.get("shops") or []),
        "evidence_text_by_shop": {s: (by_shop.get(s) or {}).get("evidence_text")
                                  for s in measure.get("shops") or []},
        "outcome": None,
        "reason": None,
        "finding_id": None,
        "evidence": None,
        "evidence_text": None,
    }


def add_shop(measure: dict, shop: str, outcome: str, *, run_id: str, today: date,
             evidence: str, evidence_text: str | None = None,
             finding_id: str | None = None, note: str | None = None) -> dict:
    """Nimmt `shop` in eine Maßnahme auf, mit Status aus `outcome`, gemessen in `run_id`.

    Gibt eine neue Maßnahme zurück. Der erste Verlaufseintrag trägt `run_id`;
    `revision.reset_measures()` nimmt den Store bei einer neuen Analyse
    darüber wieder heraus.
    """
    if outcome not in STATUS_BY_OUTCOME:
        raise CarryOverError(f"{measure.get('id')}: {outcome!r} nimmt keinen Store auf")
    if shop in (measure.get("shops") or []):
        raise CarryOverError(f"{measure.get('id')} gilt schon für {shop}")
    if not (evidence or "").strip():
        raise CarryOverError(f"{measure.get('id')}: kein Beleg. Keine Maßnahme ohne Beleg, "
                             "auch nicht für einen weiteren Store.")
    entry = {"status": STATUS_BY_OUTCOME[outcome], "date": today.isoformat(), "run_id": run_id}
    if note:
        entry["note"] = note
    return {**measure,
            "shops": [*(measure.get("shops") or []), shop],
            "by_shop": {**(measure.get("by_shop") or {}), shop: {
                "status": entry["status"],
                "history": [entry],
                "finding_run": run_id if finding_id else None,
                "finding_id": finding_id or None,
                "evidence": evidence.strip(),
                "evidence_text": (evidence_text or "").strip() or None,
            }}}


def apply_outcomes(backlog: dict, shop: str, run_id: str, sheet: list[dict],
                   exclusions: dict | None = None, today: date | None = None,
                   known_findings: set[str] | None = None) -> tuple[dict, dict]:
    """Schreibt die Ergebnisse des Arbeitsblatts in die Liste der Marke.

    Prüft zuerst alles, dann schreibt es: ein Fehler in Zeile 40 soll nicht
    39 Stores halb aufgenommen hinterlassen. Ist eine Maßnahme seit `prepare`
    ausgenommen worden (neue Meldung der Marke), wird sie übersprungen und
    gezählt, nie aufgenommen. `known_findings` sind die Befund-Kennungen
    dieses Laufs; eine `finding_id`, die dort fehlt, ist ein Fehler.

    Gibt `(backlog, summary)` zurück, `summary` mit den Listen `applied`,
    `fulfilled`, `not_transferred` und `skipped`.
    """
    if not measures.is_v2(backlog):
        raise CarryOverError("Bestand prüfen gibt es nur für die Liste einer Marke (Format v2)")
    today = today or date.today()
    exclusions = exclusions or {}
    by_id = {m["id"]: m for m in backlog.get("measures") or []}
    problems = []
    for row in sheet:
        mid, outcome = row.get("id"), row.get("outcome")
        if mid not in by_id:
            problems.append(f"{mid}: steht nicht in der Liste der Marke")
            continue
        if outcome not in OUTCOMES:
            problems.append(f"{mid}: outcome fehlt oder ist unbekannt ({outcome!r}), "
                            f"erlaubt: {', '.join(OUTCOMES)}")
            continue
        if outcome == "not_applicable" and not (row.get("reason") or "").strip():
            problems.append(f"{mid}: passt nicht, aber ohne reason. Der Bericht nennt "
                            "den Grund unter \"Nicht übertragen\".")
        if outcome in STATUS_BY_OUTCOME and not (row.get("evidence") or "").strip():
            problems.append(f"{mid}: {outcome} ohne evidence")
        fid = row.get("finding_id")
        if fid and known_findings is not None and fid not in known_findings:
            problems.append(f"{mid}: Befund {fid} gibt es in diesem Lauf nicht")
        if shop in (by_id[mid].get("shops") or []):
            problems.append(f"{mid} gilt schon für {shop}; zweimal übertragen geht nicht")
    if problems:
        raise CarryOverError("Arbeitsblatt unvollständig, nichts geschrieben:\n- " + "\n- ".join(problems))

    summary = {"applied": [], "fulfilled": [], "not_transferred": [], "skipped": []}
    for row in sheet:
        mid, outcome = row["id"], row["outcome"]
        measure = by_id[mid]
        if measures.is_excluded(exclusions, mid, shop) or _dead_everywhere(measure, exclusions):
            summary["skipped"].append({"id": mid, "title": measure.get("title"),
                                       "reason": "seit der Vorbereitung von der Marke verworfen gemeldet"})
            continue
        if outcome == "not_applicable":
            summary["not_transferred"].append({"id": mid, "title": measure.get("title"),
                                               "reason": row["reason"].strip()})
            continue
        by_id[mid] = add_shop(measure, shop, outcome, run_id=run_id, today=today,
                              evidence=row["evidence"], evidence_text=row.get("evidence_text"),
                              finding_id=row.get("finding_id"), note=row.get("note"))
        summary["applied" if outcome == "applies" else "fulfilled"].append(
            {"id": mid, "title": measure.get("title"), "finding_id": row.get("finding_id")})
    new = {**backlog, "measures": [by_id[m["id"]] for m in backlog.get("measures") or []]}
    return new, summary


# ------------------------------------------------------------- mit Dateien

def _cockpit_target(workspace) -> tuple[str, str]:
    """Marke und Store im Cockpit, wie `publish` sie bildet."""
    return portal.cockpit_target(workspace)


def load_exclusions(workspace) -> dict[str, set[str]]:
    """Holt die Meldungen der Marke über das Cockpit. Kein Rückfall: ist es
    nicht erreichbar, steigt `portal.PortalError` auf, und der Lauf bricht ab."""
    brand, shop = _cockpit_target(workspace)
    return portal.exclusions(portal.reported_statuses(brand, shop, workspace))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def prepare(workspace, run_id: str, exclusions: dict | None = None) -> Path:
    """Legt das Arbeitsblatt an. Ohne `exclusions` fragt es das Cockpit.

    Ein vorhandenes Arbeitsblatt mit eingetragenen Ergebnissen bleibt stehen:
    das wären Urteile einer Sitzung, und ein zweiter Aufruf soll sie nicht
    wegwerfen.
    """
    workspace = Path(workspace)
    target = path_for(workspace, run_id)
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing.get("applied_at") or any(c.get("outcome") for c in existing.get("candidates") or []):
            raise CarryOverError(f"{target} enthält schon Ergebnisse. Nicht überschrieben; "
                                 "zum Neuanfang die Datei beiseitelegen.")
    config = brand_mod.read_config(workspace)
    shop = brand_mod.shop_slug(config)
    if exclusions is None:
        exclusions = load_exclusions(workspace)
    backlog = measures.peek(workspace)
    to_check, skipped = candidates(backlog, shop, exclusions)
    sheet = {
        "run_id": run_id,
        "shop": shop,
        "brand": brand_mod.brand_slug(config),
        "prepared_at": _now(),
        "excluded": {mid: sorted(shops) for mid, shops in sorted(exclusions.items())},
        "candidates": [_sheet_entry(m) for m in to_check],
        "skipped": skipped,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def apply(workspace, run_id: str, exclusions: dict | None = None,
          today: date | None = None) -> dict:
    """Schreibt die Ergebnisse unter der Sperre der Marke und hält sie im Arbeitsblatt fest."""
    workspace = Path(workspace)
    target = path_for(workspace, run_id)
    sheet = json.loads(target.read_text(encoding="utf-8"))
    if sheet.get("applied_at"):
        raise CarryOverError(f"{target} ist schon angewendet ({sheet['applied_at']}).")
    if sheet.get("run_id") != run_id:
        raise CarryOverError(f"{target} gehört zu Lauf {sheet.get('run_id')!r}, nicht {run_id!r}")
    shop = sheet["shop"]
    if shop != brand_mod.shop_slug(brand_mod.read_config(workspace)):
        raise CarryOverError(f"{target} gilt für den Store {shop!r}, dieser Workspace ist ein anderer")
    if exclusions is None:
        exclusions = load_exclusions(workspace)
    known = brand_mod.finding_ids(workspace / "reporting" / "runs" / run_id, include_revisions=False)
    with measures.locked(workspace):
        backlog = measures.load_or_empty(workspace)
        backlog, summary = apply_outcomes(backlog, shop, run_id, sheet.get("candidates") or [],
                                          exclusions, today, known)
        measures.save(workspace, backlog)
    sheet.update({"applied_at": _now(), "result": summary,
                  "skipped": [*(sheet.get("skipped") or []), *summary["skipped"]]})
    target.write_text(json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def covered_findings(workspace, run_id: str) -> set[str]:
    """Befunde dieses Laufs, die eine übertragene Maßnahme abdeckt (Spec 8, Punkt 4).

    Für sie ruft Phase 3 kein `measures.create()` auf: der Befund ist der Fall
    "trifft zu" einer bestehenden Maßnahme, keine neue.
    """
    target = path_for(workspace, run_id)
    if not target.is_file():
        return set()
    sheet = json.loads(target.read_text(encoding="utf-8"))
    return {row["finding_id"] for row in sheet.get("candidates") or []
            if row.get("outcome") in STATUS_BY_OUTCOME and row.get("finding_id")}


def read(run_dir) -> dict | None:
    """Das Arbeitsblatt eines Lauf-Ordners, für den Bericht; `None`, wenn es keins gibt."""
    try:
        return json.loads((Path(run_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="audit.carry_over", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "apply", "covered"):
        p = sub.add_parser(name)
        p.add_argument("--workspace", default=".")
        p.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            target = prepare(args.workspace, args.run_id)
            sheet = json.loads(target.read_text(encoding="utf-8"))
            print(f"{target}: {len(sheet['candidates'])} Maßnahmen zu prüfen, "
                  f"{len(sheet['skipped'])} ausgenommen.")
        elif args.command == "apply":
            summary = apply(args.workspace, args.run_id)
            print(f"Übertragen: {len(summary['applied'])} trifft zu, "
                  f"{len(summary['fulfilled'])} schon erfüllt, "
                  f"{len(summary['not_transferred'])} nicht übertragen, "
                  f"{len(summary['skipped'])} übersprungen.")
        else:
            print(json.dumps(sorted(covered_findings(args.workspace, args.run_id))))
    except portal.PortalError as exc:
        print(f"Abbruch: {exc}. Ohne die Meldungen der Marke wird nichts geprüft.", file=sys.stderr)
        return 1
    except CarryOverError as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
