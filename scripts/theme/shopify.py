"""Dünne Hülle um den Shopify-Zugang der Theme-Migration.

Zwei Wege, beide mit derselben Schnittstelle `execute(query, variables, *, mutation)`:

* `CliTransport`: `shopify store execute --store <s> --json` mit dem Grant von
  `shopify store auth`. Abfrage und Variablen gehen als Datei an die CLI
  (`--query-file`, `--variable-file`), nie als Argument: ein Upsert trägt bis zu
  50 Dateiinhalte, und ein Argument stünde in der Prozessliste. Mutationen
  sperrt die CLI ohne `--allow-mutations` (CLI-Referenz `store execute`,
  geprüft am 05.10.2026); das Flag setzt diese Hülle nur, wenn der Aufrufer
  `mutation=True` sagt.
* `PortalTransport`: das Cockpit (`audit.portal.shopify_execute`). Es lehnt
  Mutationen grundsätzlich ab, deshalb verweigert die Hülle sie schon vorher.

**Drosselung.** Die CLI meldet sie auf stderr und endet mit Exit 1, stdout
bleibt leer (pull-shopify, Schritt 4). Eine leere Antwort ist deshalb nie
"keine Daten", sondern ein Fehler: warten (20, dann 40 Sekunden) und erneut.
Eine Mutation wird nur wiederholt, wenn die Meldung ausdrücklich Drosselung
nennt; bei einem anderen Fehler weiß niemand, ob sie schon gewirkt hat, und
ein zweites `themeCreate` legte ein zweites Theme an.

**Windows.** npm legt die CLI dort als `shopify.cmd` ab, und `subprocess` ohne
Shell findet sie unter dem bloßen Namen nicht; `find_cli` sucht deshalb über
`shutil.which` und nimmt unter Windows auch `shopify.cmd`. Die Ausgabe wird als
UTF-8 gelesen, nicht in der Codepage der Konsole. Steht vor dem JSON eine
Fortschritts- oder Warnzeile, liest `parse_cli_json` das letzte vollständige
Objekt oder Array.

Für Tests wird `runner` (statt `run_cli`) beziehungsweise `execute_fn`
injiziert; kein Test geht ins Netz.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from theme import migration_config

THEME_GID = "gid://shopify/OnlineStoreTheme/"

#: Wartezeiten vor den Wiederholungen, wie in pull-shopify belegt.
DEFAULT_WAITS = (20, 40)

#: Unter Windows startet `subprocess` ohne Shell nur Dateien mit diesen Endungen.
IS_WINDOWS = os.name == "nt"
WINDOWS_RUNNABLE = (".exe", ".cmd", ".bat", ".com")


class ShopifyError(RuntimeError):
    """Eine Abfrage ist gescheitert, gedrosselt geblieben oder unzulässig."""


class ThrottledError(ShopifyError):
    """Gedrosselt; der Aufruf darf nach einer Pause wiederholt werden."""


class Transport:
    """Protokoll: eine GraphQL-Operation ausführen, Daten ohne `data`-Hülle zurück."""

    def execute(self, query: str, variables: dict | None = None, *, mutation: bool = False) -> dict:
        raise NotImplementedError


def theme_gid(value) -> str:
    """`000000000000` oder die GID zur GID."""
    text = str(value).strip()
    if text.startswith(THEME_GID):
        return text
    if not text.isdigit():
        raise ShopifyError(f"Theme-ID nicht lesbar: {value!r}")
    return THEME_GID + text


def numeric_id(value) -> str:
    """GID oder Zahl zur reinen Zahl, für Ordnernamen und die Config."""
    return theme_gid(value)[len(THEME_GID):]


_COMMENT = re.compile(r"#[^\n]*")


def is_mutation(query: str) -> bool:
    """Ob das Dokument eine Mutation oder Subscription ist (eine Operation je Dokument)."""
    return bool(re.match(r"\s*(mutation|subscription)\b", _COMMENT.sub("", query)))


def _is_throttle(text: str) -> bool:
    return "throttl" in (text or "").lower()


def unwrap(payload, *, source: str = "Shopify") -> dict:
    """Antwort zu Daten; `errors` wird zum Fehler, Drosselung zu `ThrottledError`."""
    if not isinstance(payload, dict):
        raise ShopifyError(f"{source}: Antwort ist kein JSON-Objekt")
    errors = payload.get("errors")
    if errors:
        codes = {e.get("extensions", {}).get("code") for e in errors if isinstance(e, dict)}
        if "THROTTLED" in codes:
            raise ThrottledError(f"{source}: gedrosselt (THROTTLED)")
        messages = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
        raise ShopifyError(f"{source}: {messages[:500]}")
    if "data" in payload and set(payload) <= {"data", "errors", "extensions"}:
        data = payload["data"]
        if not isinstance(data, dict):
            raise ShopifyError(f"{source}: Antwort ohne Daten")
        return data
    return payload


def find_cli(name: str = "shopify") -> str:
    """Voller Pfad der Shopify CLI über `shutil.which`, unter Windows auch `shopify.cmd`.

    Ein Treffer ohne ausführbare Endung ist unter Windows das Shell-Skript, das
    npm neben `shopify.cmd` ablegt; das startet `subprocess` nicht, deshalb wird
    dann weitergesucht.
    """
    candidates = [name]
    if IS_WINDOWS and not name.lower().endswith(WINDOWS_RUNNABLE):
        candidates.append(name + ".cmd")
    for candidate in candidates:
        path = shutil.which(candidate)
        if path and (not IS_WINDOWS or path.lower().endswith(WINDOWS_RUNNABLE)):
            return path
    raise ShopifyError(f"Shopify CLI nicht gefunden ({' oder '.join(candidates)} nicht im PATH); "
                       "installieren mit npm install -g @shopify/cli")


def run_cli(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` mit dem aufgelösten Pfad der CLI an erster Stelle."""
    return subprocess.run([find_cli(cmd[0]), *cmd[1:]], **kwargs)


#: Ein Kandidat beginnt am Anfang einer Zeile, ohne Einrückung. Eingerückte
#: Klammern gehören zum Inneren eines Objekts, und ein Teilobjekt einer
#: abgeschnittenen Antwort darf nie als ganze Antwort gelten.
_JSON_START = re.compile(r"(?:^|(?<=[\r\n]))[\[{]")


def parse_cli_json(text: str):
    """JSON aus der Ausgabe der CLI, auch mit Fortschritts- oder Warnzeilen davor.

    Erst die ganze Ausgabe; scheitert das, das letzte vollständige Objekt oder
    Array, das am Zeilenanfang beginnt. Beginnt danach noch ein Objekt, das
    nicht vollständig ist, ist die Antwort abgeschnitten, und das ist ein
    Fehler statt eines älteren Treffers. `ValueError`, wenn nichts passt.
    """
    try:
        return json.loads(text)
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    found, pos = None, 0
    while (match := _JSON_START.search(text, pos)) is not None:
        start = match.start()
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            if found is not None and text[start] == "{":
                raise ValueError("Antwort nach dem letzten vollständigen JSON abgeschnitten")
            pos = start + 1
            continue
        found, pos = (value,), end
    if found is None:
        raise ValueError("kein JSON-Objekt in der Ausgabe")
    return found[0]


class CliTransport(Transport):
    """`shopify store execute --store <s> --json`, mit Drosselung und Wartezeit."""

    def __init__(self, store: str, *, version: str | None = None, runner=None, sleep=time.sleep,
                 waits=DEFAULT_WAITS, binary: str = "shopify"):
        if not store or not str(store).endswith(".myshopify.com"):
            raise ShopifyError(f"Store muss die myshopify.com-Domain sein, nicht {store!r}")
        self.store = store
        self.version = version
        self.runner = runner or run_cli
        self.sleep = sleep
        self.waits = tuple(waits)
        self.binary = binary

    def command(self, query_file: str, variable_file: str | None, mutation: bool) -> list[str]:
        cmd = [self.binary, "store", "execute", "--store", self.store, "--query-file", query_file, "--json"]
        if variable_file:
            cmd += ["--variable-file", variable_file]
        if mutation:
            cmd.append("--allow-mutations")
        if self.version:
            cmd += ["--version", self.version]
        return cmd

    def execute(self, query: str, variables: dict | None = None, *, mutation: bool = False) -> dict:
        if is_mutation(query) and not mutation:
            raise ShopifyError("Mutation ohne mutation=True abgelehnt")
        env = dict(os.environ, SHOPIFY_CLI_NO_ANALYTICS="1", SHOPIFY_CLI_NO_UPDATE_NOTIFIER="1")
        last = ""
        with tempfile.TemporaryDirectory(prefix="ptai-theme-") as tmp:
            query_file = Path(tmp) / "operation.graphql"
            query_file.write_text(query, encoding="utf-8")
            variable_file = None
            if variables:
                variable_file = Path(tmp) / "variables.json"
                variable_file.write_text(json.dumps(variables, ensure_ascii=False), encoding="utf-8")
                os.chmod(variable_file, 0o600)
            cmd = self.command(str(query_file), str(variable_file) if variable_file else None, mutation)
            for attempt in range(len(self.waits) + 1):
                if attempt:
                    self.sleep(self.waits[attempt - 1])
                proc = self.runner(cmd, capture_output=True, encoding="utf-8", errors="replace", env=env)
                if proc.returncode != 0:
                    last = (proc.stderr or proc.stdout or "").strip()[:400]
                    if mutation and not _is_throttle(last):
                        raise ShopifyError(f"Mutation gescheitert, nicht wiederholt: {last}")
                    continue
                if not (proc.stdout or "").strip():
                    last = "leere Antwort trotz Exit 0"
                    if mutation:
                        raise ShopifyError(f"Mutation ohne Antwort, nicht wiederholt: {last}")
                    continue
                try:
                    payload = parse_cli_json(proc.stdout)
                except ValueError as exc:
                    raise ShopifyError(f"Antwort der CLI ist kein JSON ({exc}): {proc.stdout[:200]}")
                try:
                    return unwrap(payload, source="Shopify CLI")
                except ThrottledError as exc:
                    last = str(exc)
                    continue
        raise ShopifyError(f"Abfrage nach {len(self.waits) + 1} Versuchen gescheitert: {last}")


class PortalTransport(Transport):
    """Abfrage über das Cockpit (`audit.portal`); verweigert jede Mutation."""

    def __init__(self, brand: str, shop: str, *, workspace: str | os.PathLike = ".", execute_fn=None,
                 sleep=time.sleep, waits=DEFAULT_WAITS):
        self.brand = brand
        self.shop = shop
        self.workspace = workspace
        self.execute_fn = execute_fn
        self.sleep = sleep
        self.waits = tuple(waits)

    def _call(self, query: str, variables: dict | None) -> dict:
        if self.execute_fn is not None:
            return self.execute_fn(self.brand, self.shop, query, variables)
        from audit import portal
        return portal.shopify_execute(self.brand, self.shop, query, variables, "theme-migration", self.workspace)

    def execute(self, query: str, variables: dict | None = None, *, mutation: bool = False) -> dict:
        if mutation or is_mutation(query):
            raise ShopifyError("Der Cockpit-Zugang ist nur lesend; Schreiben geht nur über die CLI")
        last = ""
        for attempt in range(len(self.waits) + 1):
            if attempt:
                self.sleep(self.waits[attempt - 1])
            try:
                return self._call(query, variables)
            except Exception as exc:  # PortalError und Fehler des injizierten Aufrufs
                last = str(exc)
                if "gedrosselt" in last or _is_throttle(last):
                    continue
                raise ShopifyError(f"Cockpit: {last}") from exc
        raise ShopifyError(f"Cockpit: nach {len(self.waits) + 1} Versuchen weiter gedrosselt ({last})")


def transport_from_config(config: dict, *, write: bool = False, workspace: str | os.PathLike = ".",
                          **kwargs) -> Transport:
    """Der Zugang laut `theme_migration.access`.

    Lesen: `cli-grant` (Standard) oder `portal` (Standard, wenn die Config einen
    Block `portal` hat). `staff` heißt `shopify theme pull` mit einem Konto; das
    führt die Skill selbst aus, nicht dieses Modul.

    Schreiben geht hier nur über `admin-api` (`store execute` mit
    `--allow-mutations`). Steht `access.write` auf `cli-theme`, dem Standard
    laut Spec, lädt die Skill mit `shopify theme push --unpublished` hoch.
    """
    access = migration_config(config).get("access") or {}
    store = config.get("shopify_store")
    if write:
        mode = access.get("write") or "cli-theme"
        if mode != "admin-api":
            raise ShopifyError(f"theme_migration.access.write ist {mode!r}; der Admin-Weg braucht 'admin-api'. "
                               "Mit Konto lädt die Skill über shopify theme push --unpublished hoch.")
        return CliTransport(store, **kwargs)
    mode = access.get("read") or ("portal" if config.get("portal") else "cli-grant")
    if mode == "portal":
        portal = config.get("portal") or {}
        if not (portal.get("brand") and portal.get("shop")):
            raise ShopifyError("access.read ist 'portal', aber der Block portal fehlt; erst setup --from-portal")
        return PortalTransport(portal["brand"], portal["shop"], workspace=workspace, **kwargs)
    if mode == "staff":
        raise ShopifyError("access.read 'staff' heißt shopify theme pull mit Konto; das führt die Skill aus")
    if mode != "cli-grant":
        raise ShopifyError(f"theme_migration.access.read unbekannt: {mode!r}")
    return CliTransport(store, **kwargs)
