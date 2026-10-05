"""Abgleich: was hat sich im Live-Theme seit der letzten Sicherung geändert (Spec 7.9).

1. Metadaten des Live-Themes neu ziehen und je Datei gegen das Manifest der
   letzten Sicherung halten. Gezogen wird, was neu ist oder bei dem sich
   `updatedAt` oder die Prüfsumme von Shopify geändert hat; beides sind nur
   Auslöser zum Nachsehen. **Ob eine Datei geändert ist, entscheidet der
   Inhalt**, bei JSON normalisiert. Unveränderte Dateien kommen aus der alten
   Sicherung, nachdem ihre Prüfsumme gegen das alte Manifest gestimmt hat.
2. Daraus eine neue, datierte Sicherung mit Manifest.
3. `delta.json`: geändert, neu, gelöscht, angefasst ohne Inhaltsänderung.
4. Shop-Ebene: Template-Zuweisungen gegen `migration/inventory/templates.json`.

Hat das Live-Theme seit der Sicherung gewechselt, steht das als Befund im
Delta; verglichen wird dann das heutige Live-Theme gegen die alte Sicherung.

Läuft auch ohne Migration als Wachposten.

CLI:
    python3 -m theme.sync --last <manifest.json> --out migration/sync/<date>
"""
import argparse
import json
import sys
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, now_utc, today, write_json
from theme.files import fetch_by_names, list_files, list_themes, live_theme, write_theme_files
from theme.manifest import diff_manifests, load_manifest, write_manifest
from theme.normalize import sha256_bytes
from theme.shopify import ShopifyError, numeric_id, transport_from_config
from theme.snapshot import file_entries, free_dir
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
    parser.add_argument("--last", required=True, help="manifest.json der letzten Sicherung")
    parser.add_argument("--out", required=True, help="Ordner für delta.json")
    parser.add_argument("--snapshots", help="Ordner für die neue Sicherung; Standard neben der letzten")
    parser.add_argument("--templates", default="migration/inventory/templates.json")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.workspace)
        if transport is None:
            transport = transport_from_config(config, workspace=args.workspace)
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
