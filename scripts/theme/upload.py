"""Entwurf anlegen, aktualisieren und gegen den lokalen Stand prüfen (Admin-Weg, Spec 7.7).

Geschrieben wird nur in ein Theme mit Rolle `UNPUBLISHED`, und nur, wenn
`theme_migration.access.write` auf `admin-api` steht. Mit einem Konto lädt die
Skill stattdessen über `shopify theme push --unpublished` beziehungsweise
`shopify theme push --theme <id> --only <datei>` hoch und lässt danach
`verify` laufen.

* `create`: Paket prüfen, freie Theme-Plätze prüfen, `stagedUploadsCreate`
  (Ressource `FILE`, `application/zip`; ein eigener Typ für Themes existiert
  im Enum nicht), ZIP hochladen, `themeCreate` mit fester Rolle `UNPUBLISHED`,
  Verarbeitung abwarten, zurücklesen. Die neue ID steht danach als
  `draft_theme_id` in der Config.
* `update`: nur geänderte Dateien, Code vor Templates, höchstens 50 je
  `themeFilesUpsert`, vor jedem Paket der Schutz aus `theme.guard`, bei
  `userErrors` Halt. Danach jede geschriebene Datei zurücklesen.
* `verify`: nur lesend, der ganze lokale Stand gegen das Theme.

`processingFailed: false` beweist nichts: ein ZIP-Import ließ im Feld ungültiges
JSON still weg. Deshalb endet jeder Weg mit einem inhaltlichen Vergleich, JSON
normalisiert, und dem Ergebnis "n von n gleich".

Nie `themePublish`, nie `theme publish`: Veröffentlichen ist ein Mensch.

CLI:
    python3 -m theme.upload create --zip <zip> --name <name>
    python3 -m theme.upload update --theme <draft-id> --dir <dir> [--files a,b]
    python3 -m theme.upload verify --theme <id> --dir <dir>
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from theme import (EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config,
                   today, write_json)
from theme.files import (UpsertError, batches, compare_remote, get_theme, is_plus, list_themes, read_theme_dir,
                         upsert_batch)
from theme.guard import GuardError, assert_live_unchanged, check_write_target, live_fingerprint
from theme.limits import theme_capacity
from theme.package import PackageError, verify_package
from theme.shopify import ShopifyError, numeric_id, transport_from_config

STAGED_UPLOAD_MUTATION = """mutation StageThemeArchive($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}"""

THEME_CREATE_MUTATION = """mutation CreateUnpublishedTheme($source: URL!, $name: String!) {
  themeCreate(source: $source, name: $name, role: UNPUBLISHED) {
    theme { id name role processing processingFailed }
    userErrors { code field message }
  }
}"""

MAX_THEME_NAME = 50


class UploadError(RuntimeError):
    """Ein Schritt des Uploads ist gescheitert; der Lauf hält an."""


def multipart(fields: list[tuple[str, str]], filename: str, data: bytes, mime: str) -> tuple[bytes, str]:
    """Formular für den Staged Upload: alle Parameter in Reihenfolge, die Datei zuletzt."""
    boundary = "ptai-" + uuid.uuid4().hex
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def http_post(url: str, body: bytes, content_type: str) -> int:
    """POST an das Upload-Ziel; gibt den HTTP-Status zurück. Die Parameter werden nie protokolliert."""
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def stage_archive(transport, filename: str, size: int) -> dict:
    data = transport.execute(STAGED_UPLOAD_MUTATION, {"input": [{
        "resource": "FILE", "filename": filename, "mimeType": "application/zip",
        "httpMethod": "POST", "fileSize": str(size)}]}, mutation=True)
    result = data.get("stagedUploadsCreate") or {}
    if result.get("userErrors"):
        raise UploadError(f"stagedUploadsCreate: {result['userErrors']}")
    targets = result.get("stagedTargets") or []
    if len(targets) != 1:
        raise UploadError(f"stagedUploadsCreate lieferte {len(targets)} Ziele statt einem")
    target = targets[0]
    for key in ("url", "resourceUrl"):
        if not str(target.get(key) or "").startswith("https://"):
            raise UploadError(f"stagedUploadsCreate: {key} ist kein HTTPS-Ziel")
    return target


def create_theme(transport, source: str, name: str) -> dict:
    data = transport.execute(THEME_CREATE_MUTATION, {"source": source, "name": name}, mutation=True)
    result = data.get("themeCreate") or {}
    if result.get("userErrors"):
        raise UploadError(f"themeCreate: {result['userErrors']}; vor einem neuen Versuch die Theme-Liste prüfen")
    theme = result.get("theme") or {}
    if not theme.get("id"):
        raise UploadError("themeCreate ohne Theme in der Antwort; vor einem neuen Versuch die Theme-Liste prüfen")
    if theme.get("role") != "UNPUBLISHED":
        raise UploadError(f"themeCreate lieferte Rolle {theme.get('role')} statt UNPUBLISHED")
    return theme


def wait_processing(transport, theme_id, *, sleep=time.sleep, interval: float = 5, timeout: float = 600) -> dict:
    waited = 0.0
    while True:
        theme = get_theme(transport, theme_id) or {}
        if theme.get("processing") is False:
            return theme
        if waited >= timeout:
            raise UploadError(f"Theme {numeric_id(theme_id)} nach {timeout:.0f} Sekunden noch in Verarbeitung")
        sleep(interval)
        waited += interval


def _set_draft_id(workspace, theme_id: str) -> None:
    """Trägt die neue Entwurfs-ID in `reporting/config.json` ein und lässt alles andere stehen."""
    path = Path(workspace) / "reporting" / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    block = config.setdefault("theme_migration", {})
    block["draft_theme_id"] = numeric_id(theme_id)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _findings_of(comparison: dict) -> int:
    return len(comparison["missing"]) + len(comparison["different"]) + len(comparison.get("extra", []))


def create(config: dict, zip_path, name: str, *, transport, post=http_post, sleep=time.sleep,
           workspace=".") -> tuple[dict, int]:
    tm = migration_config(config)
    if tm.get("draft_theme_id"):
        raise UploadError(f"Es gibt schon den Entwurf {tm['draft_theme_id']}; aktualisieren mit "
                          "upload update statt einen weiteren anzulegen")
    if not name or len(name) > MAX_THEME_NAME:
        raise UploadError(f"Theme-Name braucht 1 bis {MAX_THEME_NAME} Zeichen")
    report = {"command": "create", "archive": str(zip_path), "name": name}
    try:
        files = verify_package(zip_path)
    except PackageError as exc:
        report["findings"] = exc.findings
        return report, EXIT_FINDINGS
    capacity = theme_capacity(list_themes(transport), is_plus(transport))
    report["theme_capacity"] = capacity
    if capacity["full"]:
        report["findings"] = [{"rule": "theme_capacity", "message":
                               f"{capacity['count']} von {capacity['limit']} Theme-Plätzen belegt"}]
        return report, EXIT_FINDINGS
    before = live_fingerprint(transport)
    archive = Path(zip_path).read_bytes()
    target = stage_archive(transport, Path(zip_path).name, len(archive))
    body, content_type = multipart([(p["name"], p["value"]) for p in target.get("parameters") or []],
                                   Path(zip_path).name, archive, "application/zip")
    status = post(target["url"], body, content_type)
    if not 200 <= status < 300:
        raise UploadError(f"Upload des Archivs scheiterte mit HTTP {status}")
    theme = create_theme(transport, target["resourceUrl"], name)
    theme_id = theme["id"]
    report["theme_id"] = numeric_id(theme_id)
    _set_draft_id(workspace, theme_id)
    state = wait_processing(transport, theme_id, sleep=sleep)
    report["theme_state"] = state
    comparison = compare_remote(transport, theme_id, files)
    report["comparison"] = comparison
    findings = []
    if state.get("processingFailed"):
        findings.append({"rule": "processing_failed", "message": "Shopify meldet processingFailed"})
    if _findings_of(comparison):
        findings.append({"rule": "readback", "message": f"{len(comparison['equal'])} von "
                                                        f"{comparison['checked']} Dateien gleich"})
    after = live_fingerprint(transport)
    report["live_before"], report["live_after"] = before, after
    try:
        assert_live_unchanged(before, after)
    except GuardError as exc:
        findings.append({"rule": "live_changed", "message": str(exc)})
    report["findings"] = findings
    return report, EXIT_FINDINGS if findings else EXIT_OK


def update(config: dict, theme_id, theme_dir, names=None, *, transport, sleep=time.sleep) -> tuple[dict, int]:
    draft = migration_config(config).get("draft_theme_id")
    check_write_target(transport, theme_id, draft)
    local = read_theme_dir(theme_dir)
    report = {"command": "update", "theme_id": numeric_id(theme_id), "dir": str(theme_dir)}
    if names:
        unknown = sorted(set(names) - local.keys())
        if unknown:
            raise UploadError(f"nicht im Theme-Ordner: {', '.join(unknown)}")
        targets = sorted(set(names))
    else:
        before_cmp = compare_remote(transport, theme_id, local)
        targets = sorted(before_cmp["different"] + before_cmp["missing"])
        report["remote_only"] = before_cmp["extra"]
    report["planned"] = targets
    written, findings, protocol = [], [], []
    for batch in batches(targets):
        try:
            live_before = live_fingerprint(transport)
            check_write_target(transport, theme_id, draft)
            written += upsert_batch(transport, theme_id, {name: local[name] for name in batch}, sleep=sleep)
            live_after = live_fingerprint(transport)
            protocol.append({"files": len(batch), "live_before": live_before, "live_after": live_after})
            assert_live_unchanged(live_before, live_after)
        except UpsertError as exc:
            written += exc.written
            findings.append({"rule": "user_errors", "message": str(exc), "errors": exc.errors})
            break
        except GuardError as exc:
            findings.append({"rule": "guard", "message": str(exc)})
            break
    report["written"] = sorted(set(written))
    report["batches"] = protocol
    if report["written"]:
        readback = compare_remote(transport, theme_id, local, names=report["written"])
        report["readback"] = readback
        if readback["different"] or readback["missing"]:
            findings.append({"rule": "readback", "message": f"{len(readback['equal'])} von "
                                                            f"{readback['checked']} Dateien gleich"})
    if len(set(written)) < len(targets) and not findings:
        findings.append({"rule": "incomplete", "message": f"{len(set(written))} von {len(targets)} geschrieben"})
    report["findings"] = findings
    return report, EXIT_FINDINGS if findings else EXIT_OK


def verify(theme_id, theme_dir, *, transport) -> tuple[dict, int]:
    local = read_theme_dir(theme_dir)
    state = get_theme(transport, theme_id)
    if not state:
        raise UploadError(f"Theme {numeric_id(theme_id)} gibt es im Store nicht")
    comparison = compare_remote(transport, theme_id, local)
    report = {"command": "verify", "theme_id": numeric_id(theme_id), "dir": str(theme_dir), "theme_state": state,
              "live": live_fingerprint(transport), "comparison": comparison}
    findings = []
    if state.get("processing") or state.get("processingFailed"):
        findings.append({"rule": "processing", "message": "Theme in Verarbeitung oder Verarbeitung gescheitert"})
    if _findings_of(comparison):
        findings.append({"rule": "comparison", "message": f"{len(comparison['equal'])} von "
                                                          f"{comparison['checked']} Dateien gleich"})
    report["findings"] = findings
    return report, EXIT_FINDINGS if findings else EXIT_OK


def main(argv: list[str] | None = None, *, transport=None, post=http_post, sleep=time.sleep) -> int:
    parser = argparse.ArgumentParser(prog="theme.upload", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create", help="Entwurf aus einem Paket anlegen")
    p_create.add_argument("--zip", required=True)
    p_create.add_argument("--name", required=True)
    p_update = sub.add_parser("update", help="geänderte Dateien in den Entwurf schreiben")
    p_update.add_argument("--theme", required=True)
    p_update.add_argument("--dir", required=True)
    p_update.add_argument("--files", help="kommagetrennt; ohne: alle geänderten Dateien")
    p_verify = sub.add_parser("verify", help="lokalen Stand gegen ein Theme prüfen, nur lesend")
    p_verify.add_argument("--theme", required=True)
    p_verify.add_argument("--dir", required=True)
    for p in (p_create, p_update, p_verify):
        p.add_argument("--workspace", default=".")
        p.add_argument("--out", help="Ergebnisdatei; Standard migration/upload/<datum>-<befehl>.json")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(args.workspace) / "migration" / "upload" / f"{today()}-{args.command}.json"
    try:
        config = load_config(args.workspace)
        if transport is None:
            transport = transport_from_config(config, write=args.command != "verify", workspace=args.workspace)
        if args.command == "create":
            report, code = create(config, args.zip, args.name, transport=transport, post=post, sleep=sleep,
                                  workspace=args.workspace)
        elif args.command == "update":
            names = [n.strip() for n in args.files.split(",") if n.strip()] if args.files else None
            report, code = update(config, args.theme, args.dir, names, transport=transport, sleep=sleep)
        else:
            report, code = verify(args.theme, args.dir, transport=transport)
    except (ConfigError, ShopifyError, GuardError, UploadError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "command": args.command, "error": str(exc)})
        return EXIT_ERROR
    write_json(out, report)
    summary = {"ok": code == EXIT_OK, "command": args.command, "out": str(out), "theme_id": report.get("theme_id"),
               "findings": len(report.get("findings", []))}
    for key in ("comparison", "readback"):
        if key in report:
            summary["equal"] = len(report[key]["equal"])
            summary["checked"] = report[key]["checked"]
    if "written" in report:
        summary["written"] = len(report["written"])
    emit(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
