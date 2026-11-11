"""Abgleich: was hat sich im Live-Theme seit der letzten Sicherung geändert (Spec 7.9).

1. Metadaten des Live-Themes neu ziehen und je Datei gegen das Manifest der
   letzten Sicherung halten. Gezogen wird, was neu ist oder bei dem sich
   `updatedAt` oder die Prüfsumme von Shopify geändert hat; beides sind nur
   Auslöser zum Nachsehen. **Ob eine Datei geändert ist, entscheidet der
   Inhalt**, bei JSON normalisiert. Unveränderte Dateien kommen aus der alten
   Sicherung, nachdem ihre Prüfsumme gegen das alte Manifest gestimmt hat.
2. Daraus eine neue, datierte Sicherung mit Manifest.
3. `delta.json`: geändert, neu, gelöscht, angefasst ohne Inhaltsänderung,
   dazu `hidden_by_blocks`: Sections in geänderten oder neuen JSON-Dateien, die
   an sind, deren Blöcke aber alle aus sind. Broadcast blendet sie aus, Horizon
   nicht; der Generator übernimmt sie deshalb ausgeschaltet (Regel 11 in
   `theme.generate`, seit einer dunklen leeren Leiste nach einem Abgleich im November 2026).
4. Shop-Ebene: Template-Zuweisungen gegen `migration/inventory/templates.json`.

Hat das Live-Theme seit der Sicherung gewechselt, steht das als Befund im
Delta; verglichen wird dann das heutige Live-Theme gegen die alte Sicherung.

Läuft auch ohne Migration als Wachposten.

**Schlussprüfung** (`--final`, seit 10.11.2026): unmittelbar vor dem
Veröffentlichen nur `updatedAt` des Live-Themes und die Template-Zuweisungen,
jeweils gegen den jüngsten festgehaltenen Stand (Abgleich oder Sicherung).
Schreibt nichts, auch keine neue Sicherung. Jede Änderung seitdem hält den
Launch an; `theme.launch publish` ruft sie direkt vor dem Veröffentlichen auf.

CLI:
    python3 -m theme.sync --last <manifest.json> --out migration/sync/<date>
    python3 -m theme.sync --final [--live-theme-id <id>]
"""
import argparse
import json
import sys
from pathlib import Path

from theme import (EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config, now_utc,
                   today, write_json)
from theme.files import fetch_by_names, list_files, list_themes, live_theme, write_theme_files
from theme.generate import hidden_by_blocks
from theme.manifest import diff_manifests, load_manifest, write_manifest
from theme.normalize import sha256_bytes
from theme.shopify import ShopifyError, numeric_id, transport_from_config
from theme.snapshot import file_entries, free_dir
from theme import schema as schema_module
from theme import templates as template_usage


def compare_assignments(old: dict, new: dict) -> dict:
    """Template-Zuweisungen alt gegen neu: Objektzahl je Template, neue Lücken."""
    changed = []
    old_t, new_t = old.get("templates", {}), new.get("templates", {})
    for key in sorted(old_t.keys() | new_t.keys()):
        before = old_t.get(key, {}).get("objects")
        after = new_t.get(key, {}).get("objects")
        file_before, file_after = old_t.get(key, {}).get("file"), new_t.get(key, {}).get("file")
        if before != after or file_before != file_after:
            changed.append({"template": key, "objects_before": before, "objects_after": after,
                            "file_before": file_before, "file_after": file_after})
    def ident(items):
        return {(i["type"], i["suffix"]) for i in items}
    fresh = ident(new.get("assigned_without_file", [])) - ident(old.get("assigned_without_file", []))
    return {"changed": changed,
            "new_assigned_without_file": [i for i in new.get("assigned_without_file", [])
                                          if (i["type"], i["suffix"]) in fresh]}


def sections_hidden_by_blocks(bodies: dict, names) -> list:
    """Sections, die an sind, deren Blöcke aber alle aus sind, je Template und Section-Group."""
    found = []
    for name in sorted(names):
        if not (name.endswith(".json") and (name.startswith("templates/") or name.startswith("sections/"))):
            continue
        try:
            document = schema_module.read_json_text(bodies[name].decode("utf-8"))
        except (KeyError, UnicodeDecodeError, ValueError):
            continue
        for section_id, data in ((document or {}).get("sections") or {}).items():
            if isinstance(data, dict) and hidden_by_blocks(data):
                found.append({"file": name, "section_id": section_id, "type": data.get("type"),
                              "blocks": len(data.get("blocks") or {}),
                              "note": "an, alle Blöcke aus: im Entwurf ausgeschaltet übernehmen"})
    return found


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def latest_reference(workspace, theme_id=None) -> dict | None:
    """Jüngster festgehaltener Stand des Live-Themes: Abgleich (`delta.json`) oder Sicherung (`manifest.json`).

    Gleich alt gewinnt der Abgleich, weil er die Zuweisungen dieses Moments trägt. Mit `theme_id` zählen nur
    Stände dieses Themes. `snapshot` ist der Ordner der Sicherung, aus dem die Template-Dateien kommen;
    `assignments` sind die Abweichungen der Zuweisungen von der Bestandsaufnahme zu diesem Zeitpunkt (eine
    Sicherung ohne Abgleich hat keine).
    """
    workspace = Path(workspace)
    candidates = []
    for path in (workspace / "migration" / "sync").glob("*/delta.json"):
        data = _read(path)
        if data.get("theme_updated_at_after"):
            snapshot = Path(data["snapshot"]) if data.get("snapshot") else None
            if snapshot and not snapshot.is_absolute():
                snapshot = workspace / snapshot
            candidates.append({"captured_at": data.get("captured_at") or "", "updated_at": data["theme_updated_at_after"],
                               "theme_id": str(data.get("live_theme_id") or ""), "source": path, "kind": "sync",
                               "snapshot": snapshot, "assignments": data.get("assignments")})
    for path in (workspace / "migration" / "snapshots").glob("*/manifest.json"):
        data = _read(path)
        if data.get("theme_updated_at"):
            candidates.append({"captured_at": data.get("captured_at") or "", "updated_at": data["theme_updated_at"],
                               "theme_id": str(data.get("theme_id") or ""), "source": path, "kind": "snapshot",
                               "snapshot": path.parent, "assignments": None})
    if theme_id:
        candidates = [c for c in candidates if c["theme_id"] == numeric_id(theme_id)]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c["captured_at"], c["kind"] == "sync"))


def _assignment_view(data: dict | None) -> dict:
    """Abweichungen der Zuweisungen in vergleichbarer Form: sortierte JSON-Zeilen je Art."""
    data = data or {}
    return {key: sorted(json.dumps(item, sort_keys=True) for item in data.get(key) or [])
            for key in ("changed", "new_assigned_without_file")}


def final_check(transport, workspace, live_theme_id=None, *,
                templates_json="migration/inventory/templates.json") -> dict:
    """Schlussprüfung unmittelbar vor dem Veröffentlichen. Liest nur, schreibt nichts.

    Hält an (`ok: False` mit `problems`), wenn das Live-Theme gewechselt hat, wenn sein `updatedAt` vom
    jüngsten festgehaltenen Stand abweicht oder wenn sich eine Template-Zuweisung seit diesem Stand geändert
    hat. Was sich nicht prüfen lässt (kein Stand, keine Bestandsaufnahme der Zuweisungen), hält ebenfalls an:
    nie mit bekannter Lücke veröffentlichen.
    """
    workspace = Path(workspace)
    problems = []
    live = live_theme(list_themes(transport))
    current = {"theme_id": numeric_id(live["id"]), "name": live.get("name", ""), "updated_at": live.get("updatedAt")}
    if live_theme_id and current["theme_id"] != numeric_id(live_theme_id):
        problems.append(f"Live ist {current['theme_id']} \"{current['name']}\", erwartet {numeric_id(live_theme_id)}")
    reference = latest_reference(workspace, live_theme_id or current["theme_id"])
    if not reference:
        problems.append("kein Abgleich und keine Sicherung des Live-Themes unter migration/")
    elif reference["updated_at"] != current["updated_at"]:
        problems.append(f"Live-Theme geändert am {current['updated_at']}, der Abgleich vor dem Launch hielt "
                        f"{reference['updated_at']}")
    assignments = {"checked": False}
    templates = workspace / templates_json
    if reference and not problems:
        if not templates.is_file():
            problems.append(f"{templates_json} fehlt; Template-Zuweisungen nicht prüfbar")
        elif reference["kind"] == "sync" and reference["assignments"] is None:
            problems.append("Template-Zuweisungen beim Abgleich vor dem Launch nicht erhoben "
                            f"({reference['source'].relative_to(workspace).as_posix()})")
        elif not (reference["snapshot"] and Path(reference["snapshot"]).is_dir()):
            problems.append(f"Sicherung {reference['snapshot']} fehlt; Template-Dateien nicht lesbar")
        else:
            before = json.loads(templates.read_text(encoding="utf-8"))
            now = compare_assignments(before, template_usage.usage(transport, reference["snapshot"]))
            expected = _assignment_view(reference["assignments"])
            found = _assignment_view(now)
            assignments = {"checked": True, "unchanged": expected == found}
            if expected != found:
                fresh = [json.loads(line) for line in found["changed"] if line not in expected["changed"]]
                gone = [json.loads(line) for line in expected["changed"] if line not in found["changed"]]
                templates_changed = sorted({c["template"] for c in fresh + gone})
                missing_files = [f"{i['type']}.{i['suffix']}" for i in now["new_assigned_without_file"]]
                detail = ", ".join(templates_changed + [f"{m} ohne Datei" for m in missing_files
                                                        if m not in templates_changed]) or "Abweichung"
                problems.append(f"Template-Zuweisungen seit dem Abgleich vor dem Launch geändert: {detail}")
    return {"ok": not problems, "checked_at": now_utc(), "live": current, "problems": problems,
            "assignments": assignments,
            "reference": None if not reference else {
                "kind": reference["kind"], "captured_at": reference["captured_at"],
                "updated_at": reference["updated_at"], "source": reference["source"].relative_to(workspace).as_posix()}}


def sync(transport, last_manifest, out_dir, *, snapshots_root=None, templates_json=None, store: str = "",
         fetch_url=None) -> tuple[dict, int]:
    last_manifest = Path(last_manifest)
    old = load_manifest(last_manifest)
    old_dir = last_manifest.parent
    live = live_theme(list_themes(transport))
    live_id = live["id"]
    delta = {"captured_at": now_utc(), "last_manifest": str(last_manifest), "last_theme_id": old.get("theme_id"),
             "live_theme_id": numeric_id(live_id), "live_theme_switched": numeric_id(live_id) != old.get("theme_id"),
             "theme_updated_at_before": old.get("theme_updated_at"), "theme_updated_at_after": live.get("updatedAt")}
    meta = list_files(transport, live_id)
    old_files = old["files"]
    bodies, to_fetch = {}, []
    for node in meta:
        name = node["filename"]
        before = old_files.get(name)
        if not before or node.get("updatedAt") != before.get("updated_at") \
                or node.get("checksumMd5") != before.get("checksum_md5"):
            to_fetch.append(name)
            continue
        local = old_dir / name
        data = local.read_bytes() if local.is_file() else None
        if data is None or sha256_bytes(data) != before.get("sha256"):
            to_fetch.append(name)  # alte Sicherung lokal verändert oder unvollständig
        else:
            bodies[name] = data
    fetched = fetch_by_names(transport, live_id, to_fetch, fetch_url=fetch_url) if to_fetch else {}
    bodies.update(fetched)
    missing = sorted(set(to_fetch) - fetched.keys())
    root = Path(snapshots_root) if snapshots_root else old_dir.parent
    target = free_dir(root, f"{today()}-{numeric_id(live_id)}")
    target.mkdir(parents=True)
    write_theme_files(target, bodies)
    new_meta = {"store": store or old.get("store", ""), "theme_id": numeric_id(live_id),
                "theme_name": live.get("name", ""), "theme_role": live.get("role", ""),
                "theme_updated_at": live.get("updatedAt", ""), "captured_at": delta["captured_at"],
                "expected_files": len(meta), "captured_files": len(bodies), "complete": not missing,
                "missing": missing, "previous_manifest": str(last_manifest)}
    files = file_entries(meta, bodies)
    write_manifest(target, new_meta, files)
    diff = diff_manifests(old, {"files": files})
    # Fehlt ein Inhalt, ist die Datei nicht gelöscht, sondern nicht gelesen.
    diff["removed"] = [n for n in diff["removed"] if n not in missing]
    delta.update(diff)
    delta["touched_without_change"] = sorted(n for n in fetched if n in old_files and n not in diff["changed"])
    delta["missing"] = missing
    delta["hidden_by_blocks"] = sections_hidden_by_blocks(bodies, diff["changed"] + diff["added"])
    delta["snapshot"] = str(target)
    if templates_json and Path(templates_json).is_file():
        before = json.loads(Path(templates_json).read_text(encoding="utf-8"))
        after = template_usage.usage(transport, target)
        delta["assignments"] = compare_assignments(before, after)
        delta["assignments"]["assigned_without_file"] = after["assigned_without_file"]
    write_json(Path(out_dir) / "delta.json", delta)
    changes = (len(diff["changed"]) + len(diff["added"]) + len(diff["removed"]) + len(missing)
               + int(delta["live_theme_switched"]))
    if "assignments" in delta:
        changes += len(delta["assignments"]["changed"]) + len(delta["assignments"]["new_assigned_without_file"])
    return delta, EXIT_FINDINGS if changes else EXIT_OK


def main(argv: list[str] | None = None, *, transport=None, fetch_url=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.sync", description=__doc__.split("\n\n")[0])
    parser.add_argument("--last", help="manifest.json der letzten Sicherung")
    parser.add_argument("--out", help="Ordner für delta.json")
    parser.add_argument("--snapshots", help="Ordner für die neue Sicherung; Standard neben der letzten")
    parser.add_argument("--templates", default="migration/inventory/templates.json")
    parser.add_argument("--final", action="store_true",
                        help="Schlussprüfung vor dem Veröffentlichen: nur updatedAt und Template-Zuweisungen")
    parser.add_argument("--live-theme-id", help="erwartetes Live-Theme für --final; Standard aus der Config")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    if not args.final and not (args.last and args.out):
        parser.error("--last und --out sind nötig, außer mit --final")
    try:
        config = load_config(args.workspace)
        if transport is None:
            transport = transport_from_config(config, workspace=args.workspace)
        if args.final:
            live_id = args.live_theme_id or migration_config(config).get("live_theme_id")
            result = final_check(transport, args.workspace, live_id, templates_json=args.templates)
            emit({"ok": result["ok"], "final": True, "problems": result["problems"], "live": result["live"],
                  "reference": result["reference"]})
            return EXIT_OK if result["ok"] else EXIT_FINDINGS
        delta, code = sync(transport, args.last, args.out, snapshots_root=args.snapshots,
                           templates_json=args.templates, store=config.get("shopify_store", ""), fetch_url=fetch_url)
    except (ConfigError, ShopifyError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    summary = {"ok": True, "out": str(Path(args.out) / "delta.json"), "snapshot": delta["snapshot"],
               "changed": len(delta["changed"]), "added": len(delta["added"]), "removed": len(delta["removed"]),
               "missing": len(delta["missing"]), "live_theme_switched": delta["live_theme_switched"]}
    if "assignments" in delta:
        summary["assignments_changed"] = len(delta["assignments"]["changed"])
    emit(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
