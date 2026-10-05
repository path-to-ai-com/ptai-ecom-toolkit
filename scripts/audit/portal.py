#!/usr/bin/env python3
"""Zugänge aus dem Path to AI Cockpit für einen Audit-Lauf.

Verbindet ein Kunde Shopify und Google im Cockpit, liegen seine Zugänge dort,
verschlüsselt, und nicht als Datei im Workspace. Dieses Modul holt sie je
Abruf über `/api/plugin/<brand>/<shop>` im Cockpit (Spec des Cockpits zur
Einrichtung durch den Kunden, Abschnitt 10, Nachtrag vom 03.10.2026):

* **Google:** ein Zugang, der nach etwa einer Stunde abläuft. Der
  Refresh-Token bleibt im Cockpit.
* **Shopify:** die Abfrage geht durch das Cockpit, der Offline-Token verlässt
  den Server nie. `shopify-execute` verhält sich dabei wie
  `shopify store execute --json`: Daten ohne `data`-Hülle auf stdout, bei
  Drosselung oder Fehler Exit 1 und die Meldung auf stderr.

Angemeldet wird mit zwei Werten aus `audit.env`, aus derselben Ebene gelesen:
`PTAI_PORTAL_URL` (die Adresse des Cockpits) und `PTAI_PORTAL_TOKEN` (das
Token des Plugins, 1Password "PTAI Cockpit Plugin Token"). Bewusst nicht
`SUPABASE_URL`: die gehört im Plugin zur Funnel-Datenbank.

**Kein Rückfall.** Führt das Cockpit eine Quelle als nicht verbunden, bricht
der Abruf mit `PortalError` ab, statt still das Dienstkonto zu nehmen, das ein
Kunde aus dem Cockpit gar nicht hat. Kein Wert aus dem Cockpit landet je in
`reporting/`, das im Kunden-Repo committet wird; die Config bekommt nur den
Verweis `portal:<brand>/<shop>`.

CLI:
    python3 -m audit.portal setup --brand <brand> --shop <shop> [--workspace .]
    python3 -m audit.portal status --brand <brand> --shop <shop> --status collecting [--due 2026-10-16]
    python3 -m audit.portal shopify-execute --query '<graphql>' [--variables '<json>']
    python3 -m audit.portal check --brand <brand> --shop <shop>
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from audit import env

ENV_NAMES = ("PTAI_PORTAL_URL", "PTAI_PORTAL_TOKEN")

#: Vorsilbe, mit der `PTAI_GOOGLE_CREDENTIALS` statt auf eine Datei auf das
#: Cockpit zeigt; `google_token.get_access_token` erkennt sie.
PREFIX = "portal:"

#: Scope-Schlüssel aus `google_token.py` zur Quelle im Cockpit.
SCOPE_SOURCES = {"analytics": "ga4", "webmasters": "gsc", "adwords": "google_ads"}

#: Quelle im Cockpit zum Schlüssel unter `sources` in der Config.
CONFIG_SOURCES = {"shopify": "shopify", "ga4": "ga4", "gsc": "gsc", "google_ads": "ads"}

STATUSES = ("collecting", "analyzing", "reporting", "cancelled")

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")


class PortalError(RuntimeError):
    """Das Cockpit hat einen Abruf abgelehnt oder war nicht erreichbar."""


def parse_target(value: str) -> tuple[str, str]:
    """`portal:<brand>/<shop>` zu Brand und Shop; alles andere ist ein Fehler."""
    if not value.startswith(PREFIX):
        raise PortalError(f"kein Verweis aufs Cockpit: {value!r}")
    parts = value[len(PREFIX):].split("/")
    if len(parts) != 2 or not all(_SLUG.match(p) for p in parts):
        raise PortalError(f"Verweis aufs Cockpit nicht lesbar: {value!r}, erwartet portal:<brand>/<shop>")
    return parts[0], parts[1]


def _credentials(workspace: str | os.PathLike = ".") -> tuple[str, str]:
    url, token = env.get_together(ENV_NAMES, workspace)
    if not url or not token:
        raise PortalError("PTAI_PORTAL_URL und PTAI_PORTAL_TOKEN fehlen (audit.env)")
    return url.rstrip("/"), token


def _request(method: str, brand: str, shop: str, path: str = "", body: dict | None = None,
             workspace: str | os.PathLike = ".") -> tuple[int, bytes]:
    """Ein Aufruf ans Cockpit. Gibt Status und Rohantwort zurück, nie das Token."""
    if not (_SLUG.match(brand) and _SLUG.match(shop)):
        raise PortalError(f"Brand oder Shop nicht lesbar: {brand!r}/{shop!r}")
    base, token = _credentials(workspace)
    url = f"{base}/api/plugin/{urllib.parse.quote(brand)}/{urllib.parse.quote(shop)}{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise PortalError(f"Cockpit nicht erreichbar: {exc.reason}") from exc


def _json_or_error(status: int, raw: bytes, what: str) -> dict:
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        payload = {}
    if status == 200 and isinstance(payload, dict):
        return payload
    error = payload.get("error") if isinstance(payload, dict) else None
    detail = ""
    if isinstance(payload, dict) and payload.get("source"):
        detail = f" ({payload['source']}: {payload.get('status', '?')})"
    raise PortalError(f"{what}: Cockpit antwortet {status} {error or ''}{detail}".rstrip())


def shop_settings(brand: str, shop: str, workspace: str | os.PathLike = ".") -> dict:
    """Domain, Store, Properties und verbundene Quellen; ohne Geheimnis."""
    return _json_or_error(*_request("GET", brand, shop, workspace=workspace), "Einstellungen")


def google_token(brand: str, shop: str, scope_key: str, purpose: str,
                 workspace: str | os.PathLike = ".") -> str:
    """Ein Zugang bei Google für die Quelle hinter `scope_key`, gültig etwa eine Stunde."""
    source = SCOPE_SOURCES.get(scope_key)
    if not source:
        raise PortalError(f"unbekannter Scope-Key fürs Cockpit: {scope_key!r}")
    payload = _json_or_error(*_request("POST", brand, shop, "/token",
                                       {"source": source, "purpose": purpose}, workspace),
                             f"Google-Zugang {source}")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise PortalError(f"Google-Zugang {source}: Antwort ohne Token")
    return token


def unwrap_shopify(status: int, raw: bytes) -> dict:
    """Die Antwort von Shopify wie `store execute --json`: nur `data`, sonst ein Fehler.

    Drosselung kommt als `errors` mit `THROTTLED` und HTTP 200 zurück. Genau
    wie die CLI wird daraus ein Fehler und kein leeres Ergebnis, sonst hielte
    der Aufrufer "nichts abgefragt" für "keine Daten" (pull-shopify, Schritt 4).
    """
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise PortalError(f"Shopify: Antwort {status} ist kein JSON")
    if status == 409 and isinstance(payload, dict):
        raise PortalError(f"Shopify: im Cockpit nicht verbunden ({payload.get('status', '?')})")
    if status != 200 or not isinstance(payload, dict):
        error = payload.get("error") or payload.get("errors") if isinstance(payload, dict) else None
        raise PortalError(f"Shopify: Antwort {status} {error or ''}".rstrip())
    errors = payload.get("errors")
    if errors:
        codes = {e.get("extensions", {}).get("code") for e in errors if isinstance(e, dict)}
        if "THROTTLED" in codes:
            raise PortalError("Shopify: gedrosselt (THROTTLED), später erneut versuchen")
        messages = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
        raise PortalError(f"Shopify: {messages[:500]}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PortalError("Shopify: Antwort ohne Daten")
    return data


def shopify_execute(brand: str, shop: str, query: str, variables: dict | None = None,
                    purpose: str = "pull-shopify", workspace: str | os.PathLike = ".") -> dict:
    """Eine GraphQL-Abfrage über das Cockpit; gibt die Daten ohne `data`-Hülle zurück."""
    body = {"query": query, "purpose": purpose}
    if variables:
        body["variables"] = variables
    return unwrap_shopify(*_request("POST", brand, shop, "/shopify", body, workspace))


def report_status(brand: str, shop: str, status: str, due: str | None = None,
                  run_id: str | None = None, workspace: str | os.PathLike = ".") -> dict:
    """Meldet den Stand des ersten Audits an die Karte "Erstes Audit"."""
    if status not in STATUSES:
        raise PortalError(f"Stand nicht bekannt: {status!r}, erlaubt: {', '.join(STATUSES)}")
    body: dict = {"status": status}
    if due is not None:
        body["due_date"] = due or None
    if run_id:
        body["run_id"] = run_id
    return _json_or_error(*_request("POST", brand, shop, "/status", body, workspace), "Stand")


def merge_config(config: dict, settings: dict) -> dict:
    """Trägt ein, was das Cockpit über den Shop weiß, und lässt den Rest stehen.

    Überschrieben werden nur die Felder, die dem Cockpit gehören: Domain,
    Store, Properties, Werbekonto und die Schalter der vier Quellen. Eine im
    Cockpit nicht verbundene Quelle steht danach auf `false`; ein Lauf, der sie
    trotzdem anfragt, bräche ohnehin ab.
    """
    merged = dict(config)
    merged["portal"] = {"brand": settings["brand"], "shop": settings["shop"]}
    if settings.get("domain"):
        merged["domain"] = settings["domain"]
    for key in ("shopify_store", "ga4_property_id", "gsc_site", "google_ads_customer_id"):
        if settings.get(key):
            merged[key] = settings[key]
    if settings.get("google_ads_login_customer_id"):
        merged["google_ads_login_customer_id"] = settings["google_ads_login_customer_id"]
    sources = dict(merged.get("sources") or {})
    connected = settings.get("sources") or {}
    for portal_source, config_source in CONFIG_SOURCES.items():
        sources[config_source] = connected.get(portal_source) == "connected"
    merged["sources"] = sources
    return merged


def _set_env_line(path: Path, name: str, value: str) -> None:
    """Setzt eine Zeile in der Workspace-`.env`, ohne andere anzufassen."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
    kept = [line for line in lines if not pattern.match(line)]
    kept.append(f"{name}={value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def setup(brand: str, shop: str, workspace: str | os.PathLike = ".") -> Path:
    """`setup --from-portal`: Config aus dem Cockpit, Google-Verweis in die `.env`."""
    root = Path(workspace)
    settings = shop_settings(brand, shop, workspace)
    path = root / "reporting" / "config.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    merged = merge_config(config if isinstance(config, dict) else {}, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _set_env_line(root / ".env", "PTAI_GOOGLE_CREDENTIALS", f"{PREFIX}{brand}/{shop}")
    return path


def config_target(workspace: str | os.PathLike = ".") -> tuple[str, str]:
    """Brand und Shop aus `reporting/config.json` (`portal`), für `shopify-execute`."""
    path = Path(workspace) / "reporting" / "config.json"
    try:
        portal = json.loads(path.read_text(encoding="utf-8")).get("portal") or {}
    except (OSError, ValueError) as exc:
        raise PortalError(f"{path} nicht lesbar: {exc}") from exc
    brand, shop = portal.get("brand"), portal.get("shop")
    if not (isinstance(brand, str) and isinstance(shop, str)):
        raise PortalError(f"{path} hat keinen Block `portal`; erst `audit.portal setup` laufen lassen")
    return brand, shop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audit.portal", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def target_args(p, required=True):
        p.add_argument("--brand", required=required)
        p.add_argument("--shop", required=required)
        p.add_argument("--workspace", default=".")

    target_args(sub.add_parser("setup", help="Config aus dem Cockpit schreiben"))
    status_parser = sub.add_parser("status", help="Stand des ersten Audits melden")
    target_args(status_parser)
    status_parser.add_argument("--status", required=True, choices=STATUSES)
    status_parser.add_argument("--due", help="Termin auf der Karte, YYYY-MM-DD; leer nimmt ihn heraus")
    status_parser.add_argument("--run-id")
    execute = sub.add_parser("shopify-execute", help="wie shopify store execute --json")
    target_args(execute, required=False)
    group = execute.add_mutually_exclusive_group(required=True)
    group.add_argument("--query")
    group.add_argument("--query-file")
    execute.add_argument("--variables", help="JSON")
    execute.add_argument("--purpose", default="pull-shopify")
    target_args(sub.add_parser("check", help="Verbindungen und Zugänge prüfen, ohne Werte"))

    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            path = setup(args.brand, args.shop, args.workspace)
            print(f"{path} aus dem Cockpit geschrieben, PTAI_GOOGLE_CREDENTIALS zeigt aufs Cockpit.")
        elif args.command == "status":
            result = report_status(args.brand, args.shop, args.status, args.due, args.run_id, args.workspace)
            print(f"Stand gemeldet: {result.get('status')}, Termin {result.get('due_date') or 'keiner'}.")
        elif args.command == "shopify-execute":
            brand, shop = (args.brand, args.shop) if args.brand and args.shop else config_target(args.workspace)
            query = args.query if args.query is not None else Path(args.query_file).read_text(encoding="utf-8")
            variables = json.loads(args.variables) if args.variables else None
            print(json.dumps(shopify_execute(brand, shop, query, variables, args.purpose, args.workspace),
                             ensure_ascii=False))
        elif args.command == "check":
            settings = shop_settings(args.brand, args.shop, args.workspace)
            print(f"{settings.get('name')} ({settings.get('domain') or 'ohne Domain'})")
            for source, state in sorted((settings.get("sources") or {}).items()):
                print(f"  {source:<12} {state}")
            for scope_key, source in SCOPE_SOURCES.items():
                if (settings.get("sources") or {}).get(source) == "connected":
                    google_token(args.brand, args.shop, scope_key, "audit.portal check", args.workspace)
                    print(f"  {source:<12} Zugang bei Google erhalten")
            if (settings.get("sources") or {}).get("shopify") == "connected":
                shopify_execute(args.brand, args.shop, "query { shop { name } }", None, "audit.portal check",
                                args.workspace)
                print(f"  {'shopify':<12} Abfrage über das Cockpit beantwortet")
    except PortalError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
