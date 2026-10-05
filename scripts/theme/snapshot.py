"""Ein Theme vollständig und unverändert sichern, mit Manifest (Spec 7.1).

1. Theme-Liste lesen: Rolle, Name, `updatedAt`, freie Plätze. Bei vollen
   Plätzen (20, auf Plus 100) steht eine Warnung im Ergebnis, bevor ein
   Duplikat oder Upload nötig wird.
2. Metadaten aller Dateien seitenweise: die Referenzliste.
3. Inhalte ziehen, fehlende gezielt über `filenames` nachfordern,
   Binärdateien über ihre URL. **Erst wenn die Inhalte die Referenzliste
   decken, gilt die Sicherung als vollständig**; sonst Exit 1 und die Liste
   der fehlenden Dateien im Manifest.
4. Dateien Byte für Byte schreiben, nie formatieren, dazu `manifest.json`.
5. `updatedAt` des Themes nach dem Ziehen noch einmal lesen. Hat es sich
   geändert, hat jemand während der Sicherung am Theme gearbeitet, und die
   Sicherung ist kein einheitlicher Stand.

Mit `--original-zip` wird zusätzlich das unveränderte Quell-Theme aus einem ZIP
als Vergleichsbasis abgelegt (`<out>/original-<name>/`).

Der Commit im Workspace ist Sache der Skill, nicht dieses Moduls.

CLI:
    python3 -m theme.snapshot --theme <id|live> --out migration/snapshots [--original-zip <zip>]
"""
import argparse
import sys
import zipfile
from pathlib import Path, PurePosixPath

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, now_utc, today
from theme.files import RUNTIME_DIRS, fetch_bodies, get_theme, is_plus, list_files, list_themes, live_theme, \
    write_theme_files
from theme.limits import theme_capacity
from theme.manifest import write_manifest
from theme.normalize import content_hash
from theme.shopify import ShopifyError, numeric_id, theme_gid, transport_from_config


def free_dir(root: Path, name: str) -> Path:
    """Ein noch nicht belegter Ordner; eine Sicherung wird nie überschrieben."""
    candidate, counter = root / name, 2
    while candidate.exists():
        candidate = root / f"{name}-{counter}"
        counter += 1
    return candidate


def resolve_theme(transport, themes: list[dict], wanted: str) -> dict:
    if wanted == "live":
        return live_theme(themes)
    gid = theme_gid(wanted)
    for theme in themes:
        if theme.get("id") == gid:
            return theme
    theme = get_theme(transport, gid)
    if not theme:
        raise ShopifyError(f"Theme {numeric_id(gid)} gibt es im Store nicht")
    return theme


def file_entries(meta: list[dict], bodies: dict[str, bytes]) -> dict:
    """Manifest-Einträge: Metadaten von Shopify plus Prüfsummen des gezogenen Inhalts."""
    by_name = {node["filename"]: node for node in meta}
    files = {}
    for name, data in bodies.items():
        node = by_name.get(name, {})
        entry = {"size": len(data), "updated_at": node.get("updatedAt", ""),
                 "checksum_md5": node.get("checksumMd5")}
        entry.update(content_hash(name, data))
        files[name] = entry
    return files


def capture(transport, wanted: str, out_root, *, store: str = "", fetch_url=None) -> tuple[Path, dict, dict]:
    """Zieht ein Theme und schreibt die Sicherung; gibt Ordner, Manifest und Bericht zurück."""
    themes = list_themes(transport)
    capacity = theme_capacity(themes, is_plus(transport))
    theme = resolve_theme(transport, themes, wanted)
    gid = theme["id"]
    meta = list_files(transport, gid)
    expected = [node["filename"] for node in meta]
    bodies, missing = fetch_bodies(transport, gid, expected, fetch_url=fetch_url)
    # Was nicht in der Referenzliste steht, kam erst während des Ziehens dazu.
    late = sorted(bodies.keys() - set(expected))
    after = get_theme(transport, gid) or {}
    target = free_dir(Path(out_root), f"{today()}-{numeric_id(gid)}")
    target.mkdir(parents=True)
    write_theme_files(target, bodies)
    findings, warnings = [], []
    if missing:
        findings.append({"rule": "incomplete", "message": f"{len(missing)} von {len(expected)} Dateien ohne Inhalt",
                         "files": missing})
    if after.get("updatedAt") != theme.get("updatedAt") or late:
        findings.append({"rule": "theme_changed_during_snapshot",
                         "message": f"updatedAt {theme.get('updatedAt')} zu {after.get('updatedAt')}",
                         "files": late})
    if capacity["full"]:
        warnings.append(f"{capacity['count']} von {capacity['limit']} Theme-Plätzen belegt; vor einem Duplikat "
                        "oder Upload einen Platz freimachen")
    manifest_meta = {
        "store": store, "theme_id": numeric_id(gid), "theme_name": theme.get("name", ""),
        "theme_role": theme.get("role", ""), "theme_updated_at": theme.get("updatedAt", ""),
        "captured_at": now_utc(), "theme_store_id": theme.get("themeStoreId"),
        "expected_files": len(expected), "captured_files": len(bodies), "complete": not missing,
        "missing": missing,
    }
    files = file_entries(meta, bodies)
    path = write_manifest(target, manifest_meta, files)
    report = {"snapshot": str(target), "manifest": path, "theme_capacity": capacity, "findings": findings,
              "warnings": warnings}
    return target, {**manifest_meta, "files": files}, report


def _strip_prefix(names: list[str]) -> str:
    """Gemeinsamer Oberordner eines ZIP, wenn das Theme darin eine Ebene tiefer liegt."""
    firsts = {PurePosixPath(n).parts[0] for n in names if PurePosixPath(n).parts}
    if len(firsts) == 1:
        first = next(iter(firsts))
        if first not in RUNTIME_DIRS:
            return first + "/"
    return ""


def extract_original(zip_path, out_root) -> tuple[Path, str]:
    """Legt das unveränderte Quell-Theme aus einem ZIP ab, mit eigenem Manifest."""
    with zipfile.ZipFile(zip_path) as bundle:
        names = [n for n in bundle.namelist() if not n.endswith("/")]
        prefix = _strip_prefix(names)
        files = {}
        for name in names:
            relative = name[len(prefix):] if name.startswith(prefix) else name
            parts = PurePosixPath(relative).parts
            if not parts or parts[0] not in RUNTIME_DIRS or ".." in parts or any(p.startswith(".") for p in parts):
                continue
            files[relative] = bundle.read(name)
    target = free_dir(Path(out_root), f"original-{Path(zip_path).stem}")
    target.mkdir(parents=True)
    write_theme_files(target, files)
    entries = {name: {"size": len(data), "updated_at": "", **content_hash(name, data)}
               for name, data in files.items()}
    path = write_manifest(target, {"theme_id": "", "theme_name": Path(zip_path).stem, "theme_role": "ORIGINAL",
                                   "captured_at": now_utc(), "source": "zip", "complete": True,
                                   "captured_files": len(files)}, entries)
    return target, path


def main(argv: list[str] | None = None, *, transport=None, fetch_url=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.snapshot", description=__doc__.split("\n\n")[0])
    parser.add_argument("--theme", required=True, help="Theme-ID oder live")
    parser.add_argument("--out", default="migration/snapshots")
    parser.add_argument("--original-zip")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.workspace)
        if transport is None:
            transport = transport_from_config(config, workspace=args.workspace)
        target, manifest, report = capture(transport, args.theme, args.out, store=config.get("shopify_store", ""),
                                           fetch_url=fetch_url)
        if args.original_zip:
            original, _ = extract_original(args.original_zip, args.out)
            report["original"] = str(original)
    except (ConfigError, ShopifyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    summary = {"ok": not report["findings"], "snapshot": str(target), "theme_id": manifest["theme_id"],
               "role": manifest["theme_role"], "expected": manifest["expected_files"],
               "captured": manifest["captured_files"], "complete": manifest["complete"],
               "findings": len(report["findings"]), "warnings": report["warnings"],
               "free_theme_slots": report["theme_capacity"]["free"]}
    if "original" in report:
        summary["original"] = report["original"]
    emit(summary)
    return EXIT_FINDINGS if report["findings"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
