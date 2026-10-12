#!/usr/bin/env python3
"""Hebt die Maßnahmen eines Stores in den Ordner seiner Marke (Umzug, Phase A3).

Spec `ptai-portal` 2026-10-08 "eine Marke, mehrere Stores",
Abschnitt 11, Zeile "Umzug". Aus

    <marke>/<store>/reporting/measures.json   (v1, Liste eines Stores)
    <marke>/<store>/reporting/feedback.json   (falls es sie gibt)

wird

    <marke>/reporting/measures.json           (v2, Liste der Marke)
    <marke>/reporting/feedback.json           (v2, jede Anforderung mit shops)

und die Config des Stores bekommt `brand_workspace`, den absoluten Pfad zur
Marke. Was der Store je Maßnahme hatte (Status, Verlauf, Beleg, Befund), steht
danach unter `by_shop.<store>`; die Maßnahme gilt für `shops: [<store>]`.

**Was erhalten bleibt.** Die IDs bleiben, `next_id` läuft weiter. Die alten
Dateien bleiben als `*.migrated` neben der Config liegen, gelöscht wird nichts.

**Was nicht erfunden wird.** Eine Maßnahme aus der Zeit vor dem Umzug hat keine
`created_run_id`, und ihre Verlaufseinträge haben keine `run_id`. Beides bleibt
leer: eine nachgetragene Lauf-ID wäre die Behauptung, ein Lauf habe den Stand
gemessen (Spec 5.1, Regel 7).

**Der Befund wird aufgeteilt** (D12). `finding_ref` wird zu `finding_id` und
`finding_run`. Den Lauf sucht das Skript als neuesten Lauf des Stores, dessen
`findings/*.json` diese Kennung tragen; erst wenn keiner sie trägt, auch in den
Fassungen unter `revisions/`. Was sich nicht zuordnen lässt, behält seine
`finding_id` ohne `finding_run` und steht in der Ausgabe. `publish` lehnt eine
solche Liste ab, bis jemand den Lauf eingetragen hat.

**Mehrfach ausführbar.** Eine Maßnahme, die schon mit diesem Store in der Liste
der Marke steht, wird übersprungen; ein zweiter Lauf ändert nichts. Bricht der
Umzug mittendrin ab, setzt der nächste Aufruf dort fort.

CLI:
    python3 -m audit.brand_migrate --brand-workspace <ordner-der-marke> --shop eu
    python3 -m audit.brand_migrate --brand-workspace <ordner-der-marke> --shop eu --dry-run
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from audit import brand as brand_mod
from audit import measures

#: Endung der Dateien, die der Umzug im Store liegen lässt.
MIGRATED_SUFFIX = ".migrated"

#: Reihenfolge der Felder an einer Maßnahme der Marke, wie in Spec 5.1.
#: Unbekannte Felder aus v1 bleiben erhalten und stehen dahinter.
MEASURE_ORDER = ("id", "created_run_id", "title", "discipline", "type",
                 "confidence", "leverage", "effort", "responsible", "data_source",
                 "check_rule", "intent", "effect", "needs", "approval")

#: Felder aus v1, die unter `by_shop.<store>` wandern oder ersetzt werden.
MOVED = ("status", "history", "evidence", "evidence_text", "finding_ref")


class MigrationError(SystemExit):
    """Abbruch mit Ansage, bevor etwas geschrieben ist."""


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MigrationError(f"{path} ist kein gültiges JSON ({exc}). Nichts geändert.")


def _write_json(path: Path, data) -> None:
    """Atomar: erst daneben, dann umbenennen."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_index(runs_dir: Path) -> list[tuple[str, set, set]]:
    """Die Läufe eines Stores, neuester zuerst, je mit ihren Befund-Kennungen.

    Je Lauf zwei Mengen: die Kennungen der aktuellen Fassung und die aus
    `revisions/`. Die Lauf-ID beginnt mit dem Datum, die Sortierung nach Namen
    ist deshalb die nach Zeit.
    """
    if not runs_dir.is_dir():
        return []
    out = []
    for run_dir in sorted((d for d in runs_dir.iterdir() if d.is_dir()),
                          key=lambda d: d.name, reverse=True):
        current = brand_mod.finding_ids(run_dir, include_revisions=False)
        everything = brand_mod.finding_ids(run_dir, include_revisions=True)
        out.append((run_dir.name, current, everything - current))
    return out


def resolve_finding(finding: str, index: list[tuple[str, set, set]]) -> str | None:
    """Der neueste Lauf, der diesen Befund trägt; erst aktuelle Fassungen, dann
    frühere. `None`, wenn keiner ihn kennt."""
    for run_id, current, _earlier in index:
        if finding in current:
            return run_id
    for run_id, _current, earlier in index:
        if finding in earlier:
            return run_id
    return None


def convert_measure(measure: dict, shop: str, index) -> tuple[dict, str | None]:
    """Eine Maßnahme aus v1 im Zuschnitt der Marke, dazu der nicht zuordenbare
    Befund, falls einer übrig bleibt."""
    finding = measure.get("finding_ref") or None
    finding_run = resolve_finding(finding, index) if finding else None
    entry = {
        "status": measure.get("status", "open"),
        "history": list(measure.get("history") or []),
        "finding_run": finding_run,
        "finding_id": finding,
        "evidence": measure.get("evidence"),
        "evidence_text": measure.get("evidence_text"),
    }
    out = {key: measure[key] for key in MEASURE_ORDER if key in measure}
    for key, value in measure.items():
        if key not in out and key not in MOVED:
            out[key] = value
    out["shops"] = [shop]
    out["by_shop"] = {shop: entry}
    return out, (finding if finding and not finding_run else None)


def merge_measures(brand_doc: dict | None, store_doc: dict, shop: str,
                   brand: str, index) -> tuple[dict, dict]:
    """Die Liste der Marke nach dem Umzug, dazu ein Bericht.

    Steht eine ID schon mit diesem Store in der Liste der Marke, ist sie
    umgezogen und bleibt, wie sie ist. Steht sie dort für einen anderen Store,
    haben zwei Stores eigene Zählungen geführt, und dieselbe ID meint zwei
    Maßnahmen. Das löst kein Skript: Abbruch.
    """
    if brand_doc is None:
        brand_doc = measures.empty(brand)
    elif not measures.is_v2(brand_doc):
        raise MigrationError("Die Datei der Marke ist keine Liste im Format v2. "
                             "Nichts geändert.")
    elif brand_doc.get("brand") != brand:
        raise MigrationError(
            f"Die Datei der Marke gehört zu {brand_doc.get('brand')!r}, der Store "
            f"zu {brand!r}. Nichts geändert.")
    if measures.is_v2(store_doc):
        raise MigrationError("Die Datei des Stores ist schon im Format v2. Nichts geändert.")

    known = {m["id"]: m for m in brand_doc.get("measures") or []}
    report = {"moved": [], "skipped": [], "unresolved": [], "without_finding": []}
    added = []
    for measure in store_doc.get("measures") or []:
        mid = measure.get("id")
        if mid in known:
            if shop in (known[mid].get("shops") or []):
                report["skipped"].append(mid)
                continue
            raise MigrationError(
                f"{mid} steht in der Liste der Marke schon für "
                f"{known[mid].get('shops')}, nicht für {shop}. Zwei Stores haben "
                "eigene Zählungen geführt; das löst kein Skript. Nichts geändert.")
        converted, unresolved = convert_measure(measure, shop, index)
        added.append(converted)
        report["moved"].append(mid)
        if unresolved:
            report["unresolved"].append((mid, unresolved))
        if not measure.get("finding_ref"):
            report["without_finding"].append(mid)
    next_id = max(int(brand_doc.get("next_id") or 1), int(store_doc.get("next_id") or 1))
    merged = {**brand_doc, "next_id": next_id,
              "measures": [*(brand_doc.get("measures") or []), *added]}
    return merged, report


def merge_feedback(brand_entries: list[dict], store_entries: list[dict],
                   shop: str) -> tuple[list[dict], list[str], list[str]]:
    """Die Anforderungen nach dem Umzug: jede mit `shops`, keine doppelt.

    Gibt die neue Liste zurück, dazu die übernommenen und die übersprungenen
    Kennungen. Eine Kennung, die bei der Marke schon für einen anderen Store
    steht, ist dieselbe Kollision wie bei den Maßnahmen: Abbruch.
    """
    known = {e.get("id"): e for e in brand_entries}
    moved, skipped, added = [], [], []
    for entry in store_entries:
        fid = entry.get("id")
        if fid in known:
            if shop in (known[fid].get("shops") or []):
                skipped.append(fid)
                continue
            raise MigrationError(
                f"Anforderung {fid} steht bei der Marke schon für "
                f"{known[fid].get('shops')}. Nichts geändert.")
        added.append({**entry, "shops": list(entry.get("shops") or [shop])})
        moved.append(fid)
    return [*brand_entries, *added], moved, skipped


def migrate(brand_workspace, shop: str, dry_run: bool = False) -> dict:
    """Der Umzug eines Stores. Gibt zurück, was geschah oder geschähe."""
    brand_ws = Path(brand_workspace).expanduser()
    if not brand_ws.is_absolute():
        brand_ws = brand_ws.resolve()
    store_ws = brand_ws / shop
    store_reporting = store_ws / "reporting"
    config_path = store_reporting / "config.json"
    if not config_path.is_file():
        raise MigrationError(f"Kein Store-Workspace: {config_path} fehlt.")
    config = _read_json(config_path)
    brand = brand_mod.brand_slug(config)
    if not brand:
        raise MigrationError(f"{config_path} nennt keine Marke (portal.brand oder "
                             "account_slug). Nichts geändert.")
    config_shop = brand_mod.shop_slug(config)
    if config_shop != shop:
        raise MigrationError(f"{config_path} gehört zum Store {config_shop!r}, nicht "
                             f"zu {shop!r}. Nichts geändert.")
    configured = config.get("brand_workspace")
    if configured and Path(configured).expanduser().resolve() != brand_ws.resolve():
        raise MigrationError(f"{config_path} zeigt schon auf {configured}, nicht auf "
                             f"{brand_ws}. Nichts geändert.")

    brand_reporting = brand_ws / "reporting"
    brand_measures = brand_reporting / "measures.json"
    brand_feedback = brand_reporting / "feedback.json"
    store_measures = store_reporting / "measures.json"
    store_feedback = store_reporting / "feedback.json"
    index = run_index(store_reporting / "runs")

    # Ein Probelauf legt nichts an, auch nicht den Ordner für die Sperre.
    lock_ctx = (brand_mod.lock(path=brand_reporting / brand_mod.LOCK_NAME)
                if not dry_run else contextlib.nullcontext())
    with lock_ctx:
        brand_doc = _read_json(brand_measures) if brand_measures.exists() else None
        if store_measures.exists():
            store_doc = _read_json(store_measures)
            merged, report = merge_measures(brand_doc, store_doc, shop, brand, index)
        elif brand_doc is not None:
            merged, report = brand_doc, {"moved": [], "skipped": [], "unresolved": [],
                                         "without_finding": []}
        else:
            raise MigrationError(f"Weder {store_measures} noch {brand_measures} gibt "
                                 "es. Nichts umzuziehen.")
        problems = measures.consistency_problems(merged)
        if problems:
            raise MigrationError("Die Liste der Marke passte nach dem Umzug nicht, "
                                 "nichts geändert:\n- " + "\n- ".join(problems))

        feedback_moved, feedback_skipped = [], []
        feedback_entries = None
        if store_feedback.exists():
            store_entries = _entries(_read_json(store_feedback))
            brand_entries = (_entries(_read_json(brand_feedback))
                             if brand_feedback.exists() else [])
            feedback_entries, feedback_moved, feedback_skipped = merge_feedback(
                brand_entries, store_entries, shop)

        result = {"brand": brand, "shop": shop, "brand_file": str(brand_measures),
                  "next_id": merged["next_id"], "measures": len(merged["measures"]),
                  **report, "feedback_moved": feedback_moved,
                  "feedback_skipped": feedback_skipped,
                  "config": str(config_path), "dry_run": dry_run,
                  "config_changed": configured is None or configured == ""}
        if dry_run:
            return result

        # Reihenfolge mit Absicht: erst die Datei der Marke, dann die Config,
        # zuletzt die alten Dateien beiseite. Bricht es dazwischen ab, findet
        # der nächste Aufruf die Maßnahmen schon bei der Marke und überspringt
        # sie, und keine Sitzung kann in der Zwischenzeit eine zweite Liste
        # anlegen (`audit.brand.guard_second_counter`).
        _write_json(brand_measures, merged)
        if feedback_entries is not None:
            _write_json(brand_feedback, {"version": 2, "entries": feedback_entries})
        if not configured:
            _write_json(config_path, {**config, "brand_workspace": str(brand_ws.resolve())})
        for old in (store_measures, store_reporting / "measures.md", store_feedback):
            if old.exists():
                target = old.with_name(old.name + MIGRATED_SUFFIX)
                if target.exists():
                    raise MigrationError(
                        f"{target} gibt es schon; {old} bleibt liegen. Von Hand "
                        "prüfen, welche Fassung gilt.")
                os.replace(old, target)
        measures.render(store_ws)
    return result


def _entries(document) -> list[dict]:
    entries = document.get("entries") if isinstance(document, dict) else document
    return list(entries or [])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brand-workspace", required=True,
                        help="Ordner der Marke, darunter je Store ein Workspace")
    parser.add_argument("--shop", required=True, help="der Store, etwa eu")
    parser.add_argument("--dry-run", action="store_true",
                        help="nur zeigen, was geschähe, nichts schreiben")
    args = parser.parse_args(argv)

    result = migrate(args.brand_workspace, args.shop, dry_run=args.dry_run)
    head = "Probelauf, nichts geschrieben" if result["dry_run"] else "Umgezogen"
    print(f"{head}: {result['shop']} nach {result['brand_file']}")
    print(f"  Maßnahmen übernommen: {len(result['moved'])}, schon da: "
          f"{len(result['skipped'])}, in der Liste der Marke: {result['measures']}, "
          f"next_id {result['next_id']}")
    print(f"  ohne Befund (Lücke in der Datenlage): {len(result['without_finding'])}")
    if result["unresolved"]:
        print("  Befund keinem Lauf zuzuordnen, finding_run bleibt leer:")
        for mid, finding in result["unresolved"]:
            print(f"    {mid}  {finding}")
    else:
        print("  Jeder Befund ist einem Lauf zugeordnet.")
    print(f"  Anforderungen übernommen: {len(result['feedback_moved'])}, schon da: "
          f"{len(result['feedback_skipped'])}")
    if result["config_changed"]:
        print(f"  brand_workspace {'käme' if result['dry_run'] else 'steht'} in {result['config']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
