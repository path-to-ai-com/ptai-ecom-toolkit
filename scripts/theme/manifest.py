"""Manifest einer Theme-Sicherung schreiben, lesen und vergleichen.

Das Manifest ist die Grundlage für Sicherung und Abgleich: je Datei Größe,
`updated_at` und `checksum_md5` aus den Metadaten von Shopify, dazu SHA-256
des gezogenen Inhalts und für JSON SHA-256 der normalisierten Fassung.

Verglichen wird nie über `checksum_md5`, sondern über den Inhalt: bei JSON
über `sha256_normalized`, sonst über `sha256` (siehe `normalize`).

CLI:
    python3 -m theme.manifest diff <old> <new> --out <file>
"""
import argparse
import json
import os
import sys
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, emit, write_json

META_KEYS = ("store", "theme_id", "theme_name", "theme_role", "theme_updated_at", "captured_at")


def write_manifest(snapshot_dir: str | os.PathLike, meta: dict, files: dict) -> str:
    """Schreibt `<snapshot_dir>/manifest.json` und gibt den Pfad zurück."""
    manifest = {key: meta.get(key, "") for key in META_KEYS}
    for key, value in meta.items():
        if key not in manifest:
            manifest[key] = value
    manifest["files"] = {name: files[name] for name in sorted(files)}
    path = write_json(Path(snapshot_dir) / "manifest.json", manifest)
    return str(path)


def load_manifest(path: str | os.PathLike) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError(f"{path} ist kein Manifest einer Theme-Sicherung")
    return manifest


def content_key(entry: dict) -> str | None:
    """Der Wert, an dem Gleichheit hängt: normalisiert bei JSON, sonst roh."""
    return entry.get("sha256_normalized") or entry.get("sha256")


def diff_manifests(old: dict, new: dict) -> dict:
    """Geänderte, neue und gelöschte Dateien; eine Datei ohne Prüfsumme zählt als geändert."""
    old_files, new_files = old.get("files", {}), new.get("files", {})
    changed, unchanged = [], 0
    for name in sorted(old_files.keys() & new_files.keys()):
        before, after = content_key(old_files[name]), content_key(new_files[name])
        if before is None or after is None or before != after:
            changed.append(name)
        else:
            unchanged += 1
    return {
        "changed": changed,
        "added": sorted(new_files.keys() - old_files.keys()),
        "removed": sorted(old_files.keys() - new_files.keys()),
        "unchanged": unchanged,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.manifest", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    diff = sub.add_parser("diff", help="zwei Manifeste vergleichen")
    diff.add_argument("old")
    diff.add_argument("new")
    diff.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = diff_manifests(load_manifest(args.old), load_manifest(args.new))
    except (OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    write_json(args.out, result)
    differences = len(result["changed"]) + len(result["added"]) + len(result["removed"])
    emit({"ok": True, "out": args.out, "changed": len(result["changed"]), "added": len(result["added"]),
          "removed": len(result["removed"]), "unchanged": result["unchanged"]})
    return EXIT_FINDINGS if differences else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
