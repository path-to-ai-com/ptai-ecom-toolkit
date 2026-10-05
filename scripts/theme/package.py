"""Theme-Ordner zu einem ZIP mit Manifest packen, für die Erstanlage eines Entwurfs.

Ins ZIP kommen nur die Theme-Verzeichnisse (`files.RUNTIME_DIRS`), sortiert und
ohne Symlink. Daneben liegt `<zip-name>.manifest.json` mit SHA-256 des Archivs
und jeder Datei; `upload create` lädt nur ein Archiv hoch, das dazu passt.

Gepackt wird nicht, wenn

* eine JSON-Datei ungültig ist: ein ZIP-Import lässt sie still weg und meldet
  trotzdem Erfolg (im Feld belegt),
* ein Limit aus `theme.limits` überschritten ist,
* ein Zugangsschlüssel von Shopify im Inhalt steht (`shpat_` und Verwandte).

CLI:
    python3 -m theme.package --theme-dir <dir> --out <zip>
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, emit, now_utc, write_json
from theme.files import read_theme_dir
from theme.limits import MAX_ZIP_BYTES, check_files
from theme.normalize import sha256_bytes

_SECRET = re.compile(rb"\bshp(?:at|ca|ss|ua|pa)_[A-Za-z0-9]{16,}")

#: Fester Zeitstempel im ZIP, damit dasselbe Theme dasselbe Archiv ergibt.
_ZIP_TIME = (2000, 1, 1, 0, 0, 0)


class PackageError(RuntimeError):
    """Befunde, die ein Packen oder Hochladen verhindern."""

    def __init__(self, findings: list[dict]):
        super().__init__(f"{len(findings)} Befunde verhindern das Packen")
        self.findings = findings


def manifest_path(zip_path) -> Path:
    zip_path = Path(zip_path)
    return zip_path.with_name(zip_path.name + ".manifest.json")


def preflight(files: dict[str, bytes]) -> list[dict]:
    """Befunde, die ein Packen verhindern."""
    findings = check_files(files)
    for name, data in sorted(files.items()):
        if _SECRET.search(data):
            findings.append({"rule": "secret", "file": name, "value": None, "limit": None,
                             "message": "Zugangsschlüssel von Shopify im Inhalt"})
    return findings


def build_package(theme_dir, out_zip) -> dict:
    """Packt, liest zurück und prüft jede Datei; gibt das Manifest zurück.

    Wirft `PackageError` mit den Befunden, wenn nicht gepackt werden darf.
    """
    files = read_theme_dir(theme_dir)
    if not files:
        raise PackageError([{"rule": "empty", "file": None, "value": 0, "limit": None,
                             "message": "keine Theme-Dateien im Ordner"}])
    findings = preflight(files)
    if findings:
        raise PackageError(findings)
    out = Path(out_zip)
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = [{"path": name, "size": len(files[name]), "sha256": sha256_bytes(files[name])} for name in sorted(files)]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for entry in entries:
            info = zipfile.ZipInfo(entry["path"], date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, files[entry["path"]])
    with zipfile.ZipFile(out) as bundle:
        if bundle.testzip() is not None or bundle.namelist() != [e["path"] for e in entries]:
            raise PackageError([{"rule": "readback", "file": str(out), "value": None, "limit": None,
                                 "message": "Archiv stimmt beim Zurücklesen nicht"}])
        for entry in entries:
            if sha256_bytes(bundle.read(entry["path"])) != entry["sha256"]:
                raise PackageError([{"rule": "readback", "file": entry["path"], "value": None, "limit": None,
                                     "message": "Datei im Archiv weicht ab"}])
    archive = out.read_bytes()
    if len(archive) > MAX_ZIP_BYTES:
        out.unlink()
        raise PackageError([{"rule": "zip_size", "file": str(out), "value": len(archive), "limit": MAX_ZIP_BYTES,
                             "message": f"Archiv hat {len(archive)} Byte"}])
    manifest = {"built_at": now_utc(), "archive": out.name, "archive_sha256": sha256_bytes(archive),
                "archive_bytes": len(archive), "file_count": len(entries), "files": entries}
    write_json(manifest_path(out), manifest)
    return manifest


def verify_package(zip_path) -> dict[str, bytes]:
    """Archiv gegen sein Manifest; gibt die Dateien zurück oder wirft `PackageError`."""
    zip_path = Path(zip_path)
    manifest = json.loads(manifest_path(zip_path).read_text(encoding="utf-8"))
    archive = zip_path.read_bytes()
    problems = []
    if sha256_bytes(archive) != manifest.get("archive_sha256"):
        problems.append({"rule": "archive_sha256", "file": zip_path.name, "value": None, "limit": None,
                         "message": "Archiv weicht vom geprüften Paket ab"})
        raise PackageError(problems)
    files = {}
    with zipfile.ZipFile(zip_path) as bundle:
        for entry in manifest.get("files", []):
            data = bundle.read(entry["path"])
            if sha256_bytes(data) != entry["sha256"]:
                problems.append({"rule": "file_sha256", "file": entry["path"], "value": None, "limit": None,
                                 "message": "Datei weicht vom Manifest ab"})
            files[entry["path"]] = data
        if sorted(bundle.namelist()) != sorted(files):
            problems.append({"rule": "file_list", "file": zip_path.name, "value": None, "limit": None,
                             "message": "Dateiliste des Archivs weicht vom Manifest ab"})
    if problems:
        raise PackageError(problems)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.package", description=__doc__.split("\n\n")[0])
    parser.add_argument("--theme-dir", required=True)
    parser.add_argument("--out", required=True, help="Pfad des ZIP")
    args = parser.parse_args(argv)
    try:
        manifest = build_package(args.theme_dir, args.out)
    except PackageError as exc:
        write_json(manifest_path(args.out).with_name(Path(args.out).name + ".findings.json"),
                   {"findings": exc.findings})
        emit({"ok": False, "findings": len(exc.findings), "rules": sorted({f["rule"] for f in exc.findings})})
        return EXIT_FINDINGS
    except (OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    emit({"ok": True, "archive": args.out, "manifest": str(manifest_path(args.out)), "files": manifest["file_count"],
          "bytes": manifest["archive_bytes"], "sha256": manifest["archive_sha256"]})
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
