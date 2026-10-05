"""App-Inventar eines Shopify-Themes: jede Einbindung jedes Dienstes, je Messziel alle Absender.

Aufruf:

  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.apps scan \
    --snapshot migration/snapshots/<date>-<theme-id> \
    [--html <capture>/html] [--network <capture>/network.json ...] [--gtm <gtm.js> ...] \
    [--templates migration/inventory/templates.json] [--app-names <file>] \
    [--metafields <file>] [--admin-apps <file>] [--own-host <host> ...] \
    --out migration/inventory/apps.json

Schreibt `apps.json` (eine Zeile je Einbindung, gruppiert nach `service_id`) und
daneben `tracking.json` (je Messziel alle Absender und doppelte Events). Auf
stdout steht eine Zusammenfassung als eine JSON-Zeile. Exit 0 heißt fertig ohne
Befund, 1 Befunde (unbekannte Hosts, doppelte Events, Skript-Tags mit Frist,
Reste, kaputte Einbindungen), 2 Fehler.

**Keine Quelle reicht allein.** Die Admin-API zeigt nur, was der eigenen App
gehört. Getragen wird das Inventar von:

- dem ausgelieferten HTML (`webPixelsConfigList` für die verbundenen Web Pixels,
  `asyncLoad` für die Skript-Tags),
- dem Theme-Code samt `config/settings_data.json` (App-Embeds) und den
  JSON-Templates und Section-Groups (App-Blöcke),
- dem aufgelösten Tag-Manager-Container,
- dem Browser-Mitschnitt aus `scripts/browser/capture_network.py`.

Was nur über die Admin-API oder vom Team kommt (App-Namen zu `apiClientId`,
Shop-Metafeld-Namensräume, Liste der installierten Apps), liest die Skill über
die Shopify-Skills und übergibt es als Datei. Fehlt eine Quelle, steht sie im
Abdeckungsblock als `not_readable` mit Grund und nie als 0.

`survives_theme_switch` folgt allein aus `integration_type`, nie von Hand: ein
App-Block, ein App-Embed und Theme-Code gehen beim Wechsel verloren, ein
Skript-Tag, ein Web Pixel, eine Function und ein App-Proxy bleiben. Ein
Skript-Tag bekommt die Fristen aus `deprecation`.

Nur Standardbibliothek.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from theme import gtm, tracking_ids  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOSTS = PLUGIN_ROOT / "reference" / "theme-migration" / "hosts.json"

#: Ob eine Einbindung den Theme-Wechsel übersteht, je Art. `None` heißt: hängt am
#: Weg, und der ist nicht bekannt.
SURVIVES_THEME_SWITCH = {
    "app_block": False,
    "app_embed": False,
    "theme_code": False,
    "tag_manager": False,
    "script_tag": True,
    "web_pixel_app": True,
    "web_pixel_custom": True,
    "checkout_extension": True,
    "function": True,
    "app_proxy": True,
    "server_side": True,
    "metafield_only": True,
    "sales_channel": True,
    "network_only": None,
}
INTEGRATION_TYPES = tuple(SURVIVES_THEME_SWITCH)

#: Skript-Tags im Storefront: seit dem 01.10.2026 nicht mehr anlegbar oder
#: änderbar, ab dem 01.03.2027 lädt Shopify sie nicht mehr.
SCRIPT_TAG_DEPRECATION = {
    "kind": "script_tag",
    "frozen_since": "2026-10-01",
    "stops_loading_on": "2027-03-01",
    "note": ("Skript-Tags lassen sich seit dem 01.10.2026 nicht mehr anlegen oder ändern und laden ab dem "
             "01.03.2027 nicht mehr. Nachfolger einplanen, meist ein App-Embed; bei Streichen die App "
             "deinstallieren, sonst lädt sie bis zur Frist weiter."),
}

#: Die Quellen des Inventars, in der Reihenfolge der Methode, mit Namen für Menschen.
SOURCES = [
    ("browser_capture", "Browser-Mitschnitt"),
    ("web_pixels", "Web Pixels aus webPixelsConfigList"),
    ("app_names", "App-Namen über app(id:)"),
    ("script_tags", "Skript-Tags aus asyncLoad"),
    ("app_embeds", "App-Embeds aus settings_data.json"),
    ("app_blocks", "App-Blöcke aus JSON-Templates und Section-Groups"),
    ("theme_code", "Fest eingebauter Code und Reste"),
    ("tag_manager", "Tag Manager aufgelöst"),
    ("shop_metafields", "Shop-Metafeld-Namensräume"),
    ("checkout_backend", "Checkout und Backend"),
    ("app_proxy", "App-Proxies"),
    ("consent", "Consent-Verhalten"),
    ("admin_app_list", "Liste der installierten Apps aus dem Admin"),
]

CODE_DIRS = ("layout", "sections", "snippets", "blocks", "templates", "assets", "config")
CODE_SUFFIXES = (".liquid", ".js", ".css", ".json", ".html", ".mjs")
APP_TYPE = re.compile(r"shopify://apps/([^/\s\"']+)/blocks/([^/\s\"']+)/([0-9a-fA-F-]+)")
#: Ein Element mit fremder Adresse in Liquid oder HTML.
TAG_URL = re.compile(r"<(script|iframe|img|link|source|embed|object)\b[^>]*?\b(?:src|href|data)\s*=\s*"
                     r"[\"']((?:https?:)?//[^\"'\s>]+)", re.I)
#: Eine Adresse im Code: mit Schema überall, protokollrelativ nur in einem String
#: oder Attribut. Sonst träfe `// window.location` in einem Kommentar.
CODE_URL = re.compile(r"(?:https?:|(?<=[\"'(=]))//([a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
                      r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,24})(?![\w-])", re.I)
PROXY_PATH = re.compile(r"^/(apps|a|community|tools)/([\w.-]+)")
PROXY_LINK = re.compile(r"""["'](/(?:apps|a|community|tools)/[\w.-]+)""")
PIXEL_IN_URL = re.compile(r"web-pixel-(\d+)")
EXTENSION_IN_URL = re.compile(r"/extensions/([0-9a-fA-F-]{36})/")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def strip_comment_header(text: str) -> str:
    """Entfernt den Kommentarkopf, den Shopify beim Speichern vor `settings_data.json` setzt.

    Dieselbe Aufgabe hat `theme.normalize.strip_json_comment`; hier eigenständig,
    damit das Inventar auch ohne dieses Modul läuft.
    """
    stripped = text.lstrip("﻿ \t\r\n")
    while stripped.startswith("/*"):
        end = stripped.find("*/")
        if end < 0:
            return stripped
        stripped = stripped[end + 2:].lstrip()
    return stripped


# ---------------------------------------------------------------------------
# Host-Katalog
# ---------------------------------------------------------------------------

class HostCatalog:
    """`reference/theme-migration/hosts.json` als Nachschlagewerk."""

    def __init__(self, data: dict):
        self.categories = data.get("categories") or {}
        self.ignore = [h.lower() for h in data.get("ignore_hosts") or []]
        self.services: dict[str, dict] = {}
        self.patterns: list[tuple[str, str, str]] = []
        self.code: list[tuple[re.Pattern, str]] = []
        self.cookies: list[tuple[re.Pattern, str]] = []
        self.globals: list[tuple[re.Pattern, str]] = []
        self.handles: list[tuple[str, str]] = []
        for service in data.get("services") or []:
            sid = service["id"]
            self.services[sid] = service
            for pattern in service.get("hosts") or []:
                host, _, path = pattern.lower().partition("/")
                self.patterns.append((host, "/" + path if path else "", sid))
            self.code += [(re.compile(p), sid) for p in service.get("code") or []]
            self.cookies += [(re.compile(p), sid) for p in service.get("cookies") or []]
            self.globals += [(re.compile(p), sid) for p in service.get("globals") or []]
            self.handles += [(h.lower(), sid) for h in service.get("app_handles") or []]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_HOSTS) -> "HostCatalog":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def service_for(self, host: str, path: str = "") -> str | None:
        """Der Dienst zu Host und Pfad; das längste passende Muster gewinnt."""
        host = (host or "").lower().rstrip(".")
        best, best_len = None, -1
        for pattern_host, pattern_path, sid in self.patterns:
            if host != pattern_host and not host.endswith("." + pattern_host):
                continue
            if pattern_path and not (path or "").startswith(pattern_path):
                continue
            length = len(pattern_host) + len(pattern_path)
            if length > best_len:
                best, best_len = sid, length
        return best

    def service_for_url(self, url: str) -> str | None:
        parsed = urlparse(url if "//" in url else "//" + url)
        return self.service_for(parsed.hostname or "", parsed.path)

    def ignored(self, host: str) -> bool:
        host = (host or "").lower()
        return any(host == h or host.endswith("." + h) for h in self.ignore)

    def is_platform(self, sid: str | None) -> bool:
        return bool(sid and self.services.get(sid, {}).get("platform"))

    def code_hits(self, text: str) -> list[tuple[str, int, str]]:
        """Je Treffer eines Code-Kennworts: Dienst, Position, getroffener Text."""
        hits = []
        for pattern, sid in self.code:
            for match in pattern.finditer(text):
                hits.append((sid, match.start(), match.group(0)))
        return hits

    @staticmethod
    def _first(table, name: str) -> str | None:
        for pattern, sid in table:
            if pattern.search(name):
                return sid
        return None

    def service_for_cookie(self, name: str) -> str | None:
        return self._first(self.cookies, name)

    def service_for_global(self, name: str) -> str | None:
        return self._first(self.globals, name)

    def service_for_handle(self, handle: str) -> str | None:
        handle = (handle or "").lower()
        for token, sid in self.handles:
            if token in handle:
                return sid
        return None

    def service_for_name(self, name: str) -> str | None:
        """Ein App-Titel aus der Admin-Liste oder aus `app(id:)` zu einem Dienst."""
        key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
        if not key:
            return None
        for sid, service in self.services.items():
            names = {re.sub(r"[^a-z0-9]", "", service["name"].lower()), sid.replace("_", "")}
            names |= {re.sub(r"[^a-z0-9]", "", h) for h in service.get("app_handles") or []}
            if any(n == key or key.startswith(n) for n in names if len(n) >= 4):
                return sid
        return None

    def describe(self, sid: str) -> dict:
        """Name, Anbieter und Kategorie eines Dienstes, auch für die abgeleiteten Kennungen."""
        if sid in self.services:
            service = self.services[sid]
            return {"service_name": service["name"], "vendor": service.get("vendor"),
                    "category": service["category"], "known": True}
        kind, _, rest = sid.partition(":")
        names = {
            "unknown": (rest, None, "unknown"),
            "app": (rest, None, "app"),
            "pixel": (f"Web Pixel der App {rest}", None, "app"),
            "custom_pixel": (f"Custom Pixel {rest}", None, "custom_pixel"),
            "proxy": (f"App-Proxy {rest}", None, "app"),
            "metafield": (f"Metafeld-Namensraum {rest}", None, "app"),
            "gtm_custom": (f"Eigener Tag im Tag Manager ({rest})", None, "unknown"),
        }
        name, vendor, category = names.get(kind, (sid, None, "unknown"))
        return {"service_name": name, "vendor": vendor, "category": category, "known": False}


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def looks_like_shopify(html: str) -> bool:
    return any(marker in html for marker in ("Shopify.shop", "ShopifyAnalytics", "cdn.shopify.com", "shopify-features"))


def parse_web_pixels(html: str) -> list[dict] | None:
    """Die verbundenen Web Pixels aus `webPixelsConfigList`; `None`, wenn die Liste fehlt.

    Shopify rät davon ab, `content_for_header` zu parsen, weil sich das Format
    ändern kann. Ohne diesen Weg ist die Liste der fremden Pixel aber nicht zu
    haben; fehlt die Liste, meldet die Abdeckung das, statt "keine Pixel" zu sagen.
    """
    match = re.search(r"webPixelsConfigList\s*[:=]\s*\[", html)
    if not match:
        return None
    try:
        raw = json.loads(gtm.extract_balanced(html, match.end() - 1))
    except ValueError:
        return None
    pixels = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        config = item.get("configuration")
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except ValueError:
                pass
        pixels.append({
            "id": str(item.get("id") or ""),
            "type": str(item.get("type") or ""),
            "api_client_id": str(item.get("apiClientId") or "") or None,
            "runtime_context": item.get("runtimeContext"),
            "privacy_purposes": item.get("privacyPurposes") or [],
            "configuration": config,
            "data_sharing_state": item.get("dataSharingState"),
        })
    return pixels


def parse_async_load(html: str) -> list[str] | None:
    """Die Skript-Tags aus `asyncLoad` (`var urls = [...]`); `None`, wenn keine Liste da ist."""
    anchor = html.find("asyncLoad")
    match = re.search(r"var\s+urls\s*=\s*\[", html[anchor:] if anchor >= 0 else html)
    if not match:
        return None
    offset = (anchor if anchor >= 0 else 0) + match.end() - 1
    try:
        urls = json.loads(gtm.extract_balanced(html, offset))
    except ValueError:
        return None
    return [u for u in urls if isinstance(u, str)]


def shop_domain(html: str) -> str | None:
    match = re.search(r"Shopify\.shop\s*=\s*[\"']([a-z0-9.-]+)[\"']", html)
    return match.group(1).lower() if match else None


# ---------------------------------------------------------------------------
# Theme-Dateien
# ---------------------------------------------------------------------------

def load_settings_data(theme_dir: Path) -> tuple[dict | None, str | None]:
    """`config/settings_data.json` geparst, oder `None` und ein Grund."""
    path = theme_dir / "config" / "settings_data.json"
    if not path.is_file():
        return None, "config/settings_data.json fehlt in der Sicherung"
    try:
        return json.loads(strip_comment_header(path.read_text(encoding="utf-8"))), None
    except ValueError as exc:
        return None, f"config/settings_data.json ist kein gültiges JSON: {exc}"


def app_embeds(settings: dict) -> list[dict]:
    """App-Embeds aus `current.blocks`, auch wenn `current` auf ein Preset zeigt."""
    current = settings.get("current")
    if isinstance(current, str):
        current = (settings.get("presets") or {}).get(current) or {}
    blocks = (current or {}).get("blocks") or {}
    out = []
    for block_id, block in blocks.items() if isinstance(blocks, dict) else []:
        if not isinstance(block, dict):
            continue
        match = APP_TYPE.match(str(block.get("type") or ""))
        if not match:
            continue
        out.append({
            "block_id": block_id,
            "type": block["type"],
            "app_handle": match.group(1),
            "block": match.group(2),
            "extension_uuid": match.group(3),
            "disabled": bool(block.get("disabled")),
            "settings": block.get("settings") or {},
        })
    return out


def app_blocks_in(data, file: str) -> list[dict]:
    """Alle App-Blöcke einer JSON-Vorlage oder Section-Group, mit geerbtem `disabled`."""
    found = []

    def walk(node, disabled=False):
        if isinstance(node, dict):
            here = disabled or bool(node.get("disabled"))
            match = APP_TYPE.match(str(node.get("type") or ""))
            if match:
                found.append({"file": file, "app_handle": match.group(1), "block": match.group(2),
                              "extension_uuid": match.group(3), "disabled": here,
                              "settings": node.get("settings") or {}})
            for value in node.values():
                walk(value, here)
        elif isinstance(node, list):
            for value in node:
                walk(value, disabled)

    walk(data)
    return found


def theme_files(theme_dir: Path) -> list[Path]:
    files = []
    for folder in CODE_DIRS:
        base = theme_dir / folder
        if base.is_dir():
            files += [p for p in sorted(base.rglob("*")) if p.is_file() and p.name.endswith(CODE_SUFFIXES)]
    return files


def _line(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def scan_code(text: str) -> dict:
    """Fremde Adressen, Messziele, Events, Container und Proxy-Links in einem Stück Code."""
    urls = []
    seen = set()
    for match in TAG_URL.finditer(text):
        url = match.group(2)
        host = (urlparse(url if url.startswith("http") else "https:" + url).hostname or "").lower()
        if host:
            urls.append({"host": host, "path": urlparse("https:" + url.split(":", 1)[-1]).path,
                         "element": match.group(1).lower(), "line": _line(text, match.start()), "url": url[:200]})
            seen.add((host, _line(text, match.start())))
    for match in CODE_URL.finditer(text):
        host = match.group(1).lower()
        line = _line(text, match.start())
        if (host, line) in seen:
            continue
        seen.add((host, line))
        tail = text[match.end():match.end() + 120]
        path = re.match(r"[^\s\"'<>)]*", tail).group(0)
        urls.append({"host": host, "path": path.split("?")[0], "element": "url", "line": line,
                     "url": text[match.start():match.end()] + path[:120]})
    return {
        "urls": urls,
        "targets": tracking_ids.find_targets(text),
        "events": tracking_ids.code_events(text),
        "containers": tracking_ids.container_ids(text),
        "proxy_links": sorted(set(PROXY_LINK.findall(text))),
    }


# ---------------------------------------------------------------------------
# Inventar
# ---------------------------------------------------------------------------

class Inventory:
    """Sammelt Einbindungen, Spuren und Messziel-Absender aus allen Quellen."""

    def __init__(self, catalog: HostCatalog, own_hosts: set[str]):
        self.catalog = catalog
        self.own_hosts = {h.lower() for h in own_hosts if h}
        self.integrations: dict[str, dict] = {}
        self.unknown: dict[str, dict] = {}
        self.unknown_traces = {"cookies": set(), "storage_keys": set(), "globals": set()}
        self.service_traces = defaultdict(lambda: {"cookies": set(), "storage_keys": set(), "globals": set(),
                                                   "hosts": set(), "pages": set()})
        self.senders: list[dict] = []
        self.network_hits: list[dict] = []
        self.containers_seen: dict[str, set] = defaultdict(set)
        self.coverage: dict[str, dict] = {}
        self.notes: list[str] = []

    # -- Hosts --------------------------------------------------------------
    def own_base(self) -> set[str]:
        return {h[4:] if h.startswith("www.") else h for h in self.own_hosts if not h.endswith(".myshopify.com")}

    def classify(self, host: str, path: str = "") -> tuple[str, str | None]:
        """Art eines Hosts: own, own_subdomain, platform, ignored, service oder unknown."""
        host = (host or "").lower()
        if not host:
            return "ignored", None
        if host in self.own_hosts or any(host == "www." + b for b in self.own_base()):
            return "own", None
        sid = self.catalog.service_for(host, path)
        if sid and self.catalog.is_platform(sid):
            return "platform", sid
        if sid:
            return "service", sid
        if self.catalog.ignored(host):
            return "ignored", None
        if any(host.endswith("." + b) for b in self.own_base()):
            return "own_subdomain", f"unknown:{host}"
        return "unknown", f"unknown:{host}"

    def note_unknown(self, host: str, source: str, where: str, reason: str | None = None) -> None:
        entry = self.unknown.setdefault(host, {"host": host, "sources": set(), "where": set(), "reason": reason,
                                               "requests": 0, "sends": False, "pages": set()})
        entry["sources"].add(source)
        if where:
            entry["where"].add(where)
        if reason and not entry["reason"]:
            entry["reason"] = reason

    # -- Einbindungen ------------------------------------------------------
    def add(self, integration_id: str, service_id: str, integration_type: str, location: dict,
            state: str, state_basis: str, evidence: dict) -> dict:
        if integration_id in self.integrations:
            row = self.integrations[integration_id]
            row["evidence"].append(evidence)
            return row
        info = self.catalog.describe(service_id)
        row = {
            "integration_id": integration_id,
            "service_id": service_id,
            "service_name": info["service_name"],
            "vendor": info["vendor"],
            "category": info["category"],
            "app_id": None,
            "api_client_id": None,
            "app_handle": None,
            "installed": "unknown",
            "integration_type": integration_type,
            "location": location,
            "state": state,
            "state_basis": state_basis,
            "page_types": set(),
            "function": self.catalog.categories.get(info["category"]),
            "visible_frontend": None,
            "hosts": set(),
            "cookies": set(),
            "storage_keys": set(),
            "globals": set(),
            "sends_data": None,
            "before_consent": "not_measured",
            "before_consent_basis": None,
            "privacy_purposes": [],
            "survives_theme_switch": SURVIVES_THEME_SWITCH[integration_type],
            "deprecation": dict(SCRIPT_TAG_DEPRECATION) if integration_type == "script_tag" else None,
            "targets": [],
            "evidence": [evidence],
            "decision": "open",
            "decided_by": None,
            "decided_on": None,
            "target_integration": None,
            "verified_draft": None,
            "verified_live": None,
            "_net": {},
        }
        self.integrations[integration_id] = row
        return row

    def add_sender(self, target: dict, integration_id: str | None, service_id: str | None, path: str,
                   events: list[str], basis: str, **extra) -> None:
        self.senders.append({"target_id": target["target_id"], "kind": target["kind"],
                             "label": target.get("label"), "integration_id": integration_id,
                             "service_id": service_id, "path": path, "events": sorted(set(events or [])),
                             "basis": basis, **extra})

    def by_service(self, sid: str) -> list[dict]:
        return [row for row in self.integrations.values() if row["service_id"] == sid]


def _service_for_handle(inv: Inventory, handle: str) -> str:
    return inv.catalog.service_for_handle(handle) or f"app:{handle}"


# -- Quelle: HTML ------------------------------------------------------------

def read_html(inv: Inventory, html_dir: Path | None, app_names: dict) -> None:
    pixels_cov = {"status": "not_readable", "reason": "kein gespeichertes HTML übergeben (--html)", "count": None}
    tags_cov = {"status": "not_readable", "reason": "kein gespeichertes HTML übergeben (--html)", "count": None}
    if html_dir is None:
        inv.coverage["web_pixels"], inv.coverage["script_tags"] = pixels_cov, tags_cov
        return
    files = sorted(p for p in html_dir.rglob("*.html") if p.is_file()) if html_dir.is_dir() else []
    if not files:
        reason = f"keine HTML-Datei unter {html_dir}"
        inv.coverage["web_pixels"] = {**pixels_cov, "reason": reason}
        inv.coverage["script_tags"] = {**tags_cov, "reason": reason}
        return

    pixels: dict[str, dict] = {}
    script_urls: dict[str, set] = defaultdict(set)
    pixel_pages = shopify_pages = async_pages = 0
    for path in files:
        html = path.read_text(encoding="utf-8", errors="replace")
        if not looks_like_shopify(html):
            continue
        shopify_pages += 1
        domain = shop_domain(html)
        if domain:
            inv.own_hosts.add(domain)
        for container in tracking_ids.container_ids(html):
            inv.containers_seen[container].add(f"html:{path.name}")
        found = parse_web_pixels(html)
        if found is not None:
            pixel_pages += 1
            for pixel in found:
                pixels.setdefault(pixel["id"], pixel)
        urls = parse_async_load(html)
        if urls is not None:
            async_pages += 1
            for url in urls:
                script_urls[url].add(path.name)

    for pixel_id, pixel in sorted(pixels.items()):
        custom = pixel["type"].upper() == "CUSTOM"
        targets = tracking_ids.config_targets(pixel["configuration"])
        client = pixel["api_client_id"]
        resolved = app_names.get(client or "") or {}
        kinds = {tracking_ids.KIND_SERVICE.get(t["kind"]) for t in targets} - {None}
        if custom:
            sid = f"custom_pixel:{pixel_id}"
        elif resolved.get("title") and inv.catalog.service_for_name(resolved["title"]):
            sid = inv.catalog.service_for_name(resolved["title"])
        elif len(kinds) == 1:
            sid = kinds.pop()
        elif resolved.get("title"):
            sid = f"app:{_slug(resolved['title'])}"
        else:
            sid = f"pixel:{client or pixel_id}"
        row = inv.add(f"web_pixel:{pixel_id}", sid, "web_pixel_custom" if custom else "web_pixel_app",
                      {"pixel_id": pixel_id, "pixel_type": pixel["type"], "runtime_context": pixel["runtime_context"]},
                      "active", "html", {"source": "web_pixels", "detail": "webPixelsConfigList, verbunden"})
        row["api_client_id"] = client
        row["app_id"] = f"gid://shopify/App/{client}" if client and not custom else None
        row["privacy_purposes"] = list(pixel["privacy_purposes"])
        row["targets"] = targets
        if resolved:
            row["installed"] = resolved.get("installed") or row["installed"]
            row["app_handle"] = resolved.get("handle")
            if resolved.get("title") and not inv.catalog.describe(sid)["known"]:
                row["service_name"] = resolved["title"]
        per_event = tracking_ids.config_events(pixel["configuration"])
        covered = set()
        for event, event_targets in per_event:
            for target in event_targets:
                inv.add_sender(target, row["integration_id"], sid, "web_pixel", [event], "config")
                covered.add(target["target_id"])
        for target in targets:
            if target["target_id"] not in covered:
                inv.add_sender(target, row["integration_id"], sid, "web_pixel", [], "config")

    for url, pages in sorted(script_urls.items()):
        parsed = urlparse(url if "//" in url else "https:" + url)
        host = (parsed.hostname or "").lower()
        kind, sid = inv.classify(host, parsed.path)
        if kind in ("own", "platform", "ignored") or sid is None:
            # Ein Skript-Tag auf einem Shopify-Host gehört trotzdem einer App; der
            # Anbieter steht im Dateinamen und wird von Hand bestimmt.
            sid = f"unknown:{host}{parsed.path}"[:120]
            inv.note_unknown(f"{host}{parsed.path}"[:120], "script_tags", url,
                             "Skript-Tag auf Shopify- oder Shop-Host, Anbieter aus Dateiname bestimmen")
        elif kind in ("unknown", "own_subdomain"):
            inv.note_unknown(host, "script_tags", url)
        key = url.split("?")[0]
        row = inv.add(f"script_tag:{key}", sid, "script_tag", {"url": url, "pages": sorted(pages)},
                      "active", "html", {"source": "script_tags", "detail": "asyncLoad im Seitenkopf"})
        row["hosts"].add(host)
        for target in tracking_ids.find_targets(url):
            row["targets"].append(target)
            inv.add_sender(target, row["integration_id"], sid, "script_tag", [], "config")

    if shopify_pages == 0:
        reason = "keine der HTML-Dateien ist eine Shopify-Seite"
        inv.coverage["web_pixels"] = {"status": "not_readable", "reason": reason, "count": None}
        inv.coverage["script_tags"] = {"status": "not_readable", "reason": reason, "count": None}
        return
    if pixel_pages:
        inv.coverage["web_pixels"] = {
            "status": "partial", "count": len(pixels),
            "reason": ("webPixelsConfigList zeigt nur verbundene Pixel; getrennte stehen nur im Admin unter "
                       "Kundenereignisse"),
        }
    else:
        inv.coverage["web_pixels"] = {"status": "not_readable", "count": None,
                                      "reason": f"webPixelsConfigList in keiner von {shopify_pages} Seiten gefunden"}
    # Eine Shopify-Seite ohne asyncLoad hat keine Skript-Tags; das ist eine Aussage, keine Lücke.
    inv.coverage["script_tags"] = {"status": "complete", "count": len(script_urls),
                                   "reason": None if async_pages else "kein asyncLoad im Seitenkopf: keine Skript-Tags"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "ohne-name"


# -- Quelle: Theme ----------------------------------------------------------

def _live_files(templates: dict | None) -> tuple[set[str] | None, set[str]]:
    """Template-Dateien mit und ohne Objekte aus `templates.json` (Paket A)."""
    if not templates:
        return None, set()
    dead = set(templates.get("files_without_objects") or [])
    live = set()
    for info in (templates.get("templates") or {}).values():
        file = info.get("file")
        if file and file not in dead:
            live.add(file)
    return live, dead


def _without_embeds(settings: dict) -> dict:
    copy = json.loads(json.dumps(settings))
    current = copy.get("current")
    if isinstance(current, dict):
        current.pop("blocks", None)
    for preset in (copy.get("presets") or {}).values():
        if isinstance(preset, dict):
            preset.pop("blocks", None)
    return copy


def read_theme(inv: Inventory, theme_dir: Path | None, templates: dict | None) -> None:
    missing = {"status": "not_readable", "reason": "keine Theme-Sicherung übergeben (--snapshot)", "count": None}
    if theme_dir is None or not theme_dir.is_dir():
        reason = missing["reason"] if theme_dir is None else f"{theme_dir} ist kein Verzeichnis"
        for source in ("app_embeds", "app_blocks", "theme_code"):
            inv.coverage[source] = {**missing, "reason": reason}
        return

    # App-Embeds
    settings, problem = load_settings_data(theme_dir)
    if settings is None:
        inv.coverage["app_embeds"] = {"status": "not_readable", "reason": problem, "count": None}
    else:
        embeds = app_embeds(settings)
        for embed in embeds:
            sid = _service_for_handle(inv, embed["app_handle"])
            key = f"app_embed:{embed['app_handle']}/{embed['block']}"
            row = inv.add(key, sid, "app_embed",
                          {"file": "config/settings_data.json", "block_ids": [], "type": embed["type"],
                           "extension_uuid": embed["extension_uuid"]},
                          "disabled" if embed["disabled"] else "active", "config",
                          {"source": "app_embeds", "detail": "config/settings_data.json current.blocks"})
            row["location"]["block_ids"].append(embed["block_id"])
            if not embed["disabled"]:
                row["state"] = "active"
            row["app_handle"] = embed["app_handle"]
            for target in tracking_ids.config_targets(embed["settings"]):
                row["targets"].append(target)
                inv.add_sender(target, key, sid, "app_embed", [], "config")
        inv.coverage["app_embeds"] = {"status": "complete", "count": len(embeds), "reason": None}

    # App-Blöcke
    live, dead = _live_files(templates)
    json_files = sorted(p for p in (theme_dir / "templates").rglob("*.json")) if (theme_dir / "templates").is_dir() else []
    json_files += sorted((theme_dir / "sections").glob("*.json")) if (theme_dir / "sections").is_dir() else []
    broken_json = []
    blocks = defaultdict(list)
    for path in json_files:
        rel = path.relative_to(theme_dir).as_posix()
        try:
            data = json.loads(strip_comment_header(path.read_text(encoding="utf-8")))
        except ValueError:
            broken_json.append(rel)
            continue
        for block in app_blocks_in(data, rel):
            blocks[(block["app_handle"], block["block"])].append(block)
    for (handle, name), found in sorted(blocks.items()):
        sid = _service_for_handle(inv, handle)
        files = defaultdict(lambda: {"active": 0, "disabled": 0})
        for block in found:
            files[block["file"]]["disabled" if block["disabled"] else "active"] += 1
        on_live = on_dead = None
        if live is not None:
            template_files = [f for f in files if f.startswith("templates/")]
            on_live = sum(1 for f in template_files if f in live)
            on_dead = sum(1 for f in template_files if f in dead or f not in live)
        location = {"block": f"{handle}/{name}", "extension_uuid": found[0]["extension_uuid"],
                    "files": {f: dict(v) for f, v in sorted(files.items())},
                    "section_groups": sorted(f for f in files if f.startswith("sections/")),
                    "templates_live": on_live, "templates_without_objects": on_dead}
        any_active = any(not b["disabled"] for b in found)
        row = inv.add(f"app_block:{handle}/{name}", sid, "app_block", location,
                      "active" if any_active else "disabled", "config",
                      {"source": "app_blocks", "detail": f"{len(found)} Fundstelle(n) in {len(files)} Datei(en)"})
        row["app_handle"] = handle
        for block in found:
            for target in tracking_ids.config_targets(block["settings"]):
                if target not in row["targets"]:
                    row["targets"].append(target)
                    inv.add_sender(target, row["integration_id"], sid, "app_block", [], "config")
    if broken_json:
        inv.coverage["app_blocks"] = {"status": "partial", "count": len(blocks),
                                      "reason": "nicht lesbar: " + ", ".join(broken_json[:10])}
    elif live is None:
        inv.coverage["app_blocks"] = {"status": "partial", "count": len(blocks),
                                      "reason": ("ohne templates.json (--templates) ist offen, welche Fundstellen "
                                                 "auf Templates mit Objekten liegen")}
    else:
        inv.coverage["app_blocks"] = {"status": "complete", "count": len(blocks), "reason": None}

    # Fest eingebauter Code
    files = theme_files(theme_dir)
    rows = 0
    per_service_file: dict[tuple[str, str], dict] = {}
    proxy_links = defaultdict(set)
    for path in files:
        rel = path.relative_to(theme_dir).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if rel == "config/settings_data.json" and settings is not None:
            # Die App-Embeds sind oben schon Zeilen; gesucht wird nur im Rest der
            # Theme-Einstellungen (etwa eingefügter Code in einem Textfeld).
            text = json.dumps(_without_embeds(settings), ensure_ascii=False, indent=1)
        found = scan_code(text)
        for container in found["containers"]:
            inv.containers_seen[container].add(f"theme:{rel}")
        for link in found["proxy_links"]:
            proxy_links[link].add(rel)
        hits: dict[str, dict] = {}
        for url in found["urls"]:
            kind, sid = inv.classify(url["host"], url["path"])
            if kind in ("own", "platform", "ignored"):
                continue
            if kind in ("unknown", "own_subdomain"):
                reason = "Subdomain des Shops, oft ein eigener Mess-Endpunkt" if kind == "own_subdomain" else None
                inv.note_unknown(url["host"], "theme_code", f"{rel}:{url['line']}", reason)
            hit = hits.setdefault(sid, {"lines": set(), "hosts": set(), "elements": set(), "keywords": set()})
            hit["lines"].add(url["line"])
            hit["hosts"].add(url["host"])
            hit["elements"].add(url["element"])
        for sid, position, keyword in inv.catalog.code_hits(text):
            if inv.catalog.is_platform(sid):
                continue
            hit = hits.setdefault(sid, {"lines": set(), "hosts": set(), "elements": set(), "keywords": set()})
            hit["lines"].add(_line(text, position))
            hit["keywords"].add(keyword.strip())
        for sid, hit in hits.items():
            key = f"theme_code:{sid}:{rel}"
            location = {"file": rel, "lines": sorted(hit["lines"])[:50], "elements": sorted(hit["elements"]),
                        "keywords": sorted(hit["keywords"])[:20]}
            row = inv.add(key, sid, "theme_code", location, "active", "code_only",
                          {"source": "theme_code", "detail": f"{rel}, {len(hit['lines'])} Zeile(n)"})
            row["hosts"] |= hit["hosts"]
            per_service_file[(sid, rel)] = row
            rows += 1
        # Messziele im Code: Absender ist die Code-Zeile des passenden Dienstes,
        # sonst eine eigene Zeile für die Datei.
        for target in found["targets"]:
            sid = tracking_ids.KIND_SERVICE.get(target["kind"])
            row = per_service_file.get((sid, rel))
            if row is None:
                # gtag.js trägt GA4 und Ads; ohne eigenen Treffer zählt die Datei als Google-Tag.
                for candidate in ("google_tag", "google_tag_manager"):
                    row = per_service_file.get((candidate, rel)) or row
            if row is None:
                row = inv.add(f"theme_code:{sid}:{rel}", sid or "unknown:code", "theme_code",
                              {"file": rel, "lines": [], "elements": [], "keywords": []}, "active", "code_only",
                              {"source": "theme_code", "detail": f"{rel}, Kennung im Code"})
                per_service_file[(sid, rel)] = row
            if target not in row["targets"]:
                row["targets"].append(target)
            inv.add_sender(target, row["integration_id"], row["service_id"], "theme_code", found["events"], "config",
                           file=rel)
    for link, where in sorted(proxy_links.items()):
        match = PROXY_PATH.match(link)
        prefix = f"/{match.group(1)}/{match.group(2)}" if match else link
        row = inv.add(f"app_proxy:{prefix}", f"proxy:{prefix}", "app_proxy", {"path": prefix, "files": sorted(where)},
                      "active", "code_only", {"source": "app_proxy", "detail": "Link im Theme-Code"})
    inv.coverage["theme_code"] = {"status": "complete" if files else "not_readable",
                                  "count": rows if files else None,
                                  "reason": None if files else "keine Code-Dateien in der Sicherung"}


# -- Quelle: Tag Manager -----------------------------------------------------

def _tag_service(inv: Inventory, tag: dict) -> str:
    if tag.get("service_id"):
        return tag["service_id"]
    unknown = None
    for host in tag.get("hosts") or []:
        kind, sid = inv.classify(host)
        if kind == "service":
            return sid
        if kind in ("unknown", "own_subdomain") and unknown is None:
            unknown = sid
    if unknown:
        return unknown
    text = json.dumps(tag.get("params") or {}, ensure_ascii=False)
    for sid, _, _ in inv.catalog.code_hits(text):
        if not inv.catalog.is_platform(sid):
            return sid
    for target in tag.get("targets") or []:
        sid = tracking_ids.KIND_SERVICE.get(target["kind"])
        if sid:
            return sid
    return f"gtm_custom:{tag.get('function')}"


def read_gtm(inv: Inventory, gtm_files: list[Path]) -> None:
    resolved_ids = set()
    problems = []
    for path in gtm_files:
        try:
            result = gtm.resolve_file(str(path))
        except (OSError, gtm.ContainerError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        ids = result.get("container_ids") or [f"GTM-unbekannt-{path.stem}"]
        container = ids[0]
        resolved_ids.update(ids)
        inv.add(f"tag_manager:{container}", "google_tag_manager", "tag_manager",
                {"container_id": container, "version": result.get("version"), "tags": len(result["tags"]),
                 "file": path.name}, "active", "config",
                {"source": "tag_manager", "detail": f"Container aufgelöst, {len(result['tags'])} Tags"})
        for tag in result["tags"]:
            sid = _tag_service(inv, tag)
            state = "disabled" if tag["paused"] or not tag["fires"] else "active"
            location = {"container_id": container, "tag_index": tag["index"], "tag_id": tag.get("tag_id"),
                        "function": tag["function"], "purpose": tag.get("purpose"), "events": tag["events"],
                        "fires_when": [c for t in tag["triggers"] for c in t.get("fires_when", [])][:12],
                        "consent": tag.get("consent")}
            row = inv.add(f"tag_manager:{container}:tag-{tag['index']}", sid, "tag_manager", location, state, "config",
                          {"source": "tag_manager", "detail": f"Tag {tag['index']} ({tag['function']})"})
            row["hosts"] |= {h.lower() for h in tag.get("hosts") or []}
            row["targets"] = list(tag["targets"])
            for host in tag.get("hosts") or []:
                kind, hsid = inv.classify(host)
                if kind in ("unknown", "own_subdomain"):
                    inv.note_unknown(host.lower(), "tag_manager", f"{container} Tag {tag['index']}")
            if state == "active":
                for target in tag["targets"]:
                    inv.add_sender(target, row["integration_id"], sid, "tag_manager", tag["events"], "config")
    seen_not_resolved = sorted(set(inv.containers_seen) - resolved_ids)
    for container in seen_not_resolved:
        inv.add(f"tag_manager:{container}", "google_tag_manager", "tag_manager",
                {"container_id": container, "seen_in": sorted(inv.containers_seen[container])[:10]},
                "active", "code_only", {"source": "tag_manager", "detail": "Container-Kennung gefunden, nicht aufgelöst"})
    if problems:
        inv.coverage["tag_manager"] = {"status": "partial" if resolved_ids else "not_readable", "count": None,
                                       "reason": "; ".join(problems)}
    elif seen_not_resolved:
        inv.coverage["tag_manager"] = {
            "status": "partial" if resolved_ids else "not_readable", "count": len(resolved_ids) or None,
            "reason": "Container gefunden, aber nicht aufgelöst (--gtm fehlt): " + ", ".join(seen_not_resolved)}
    elif resolved_ids:
        inv.coverage["tag_manager"] = {"status": "complete", "count": len(resolved_ids), "reason": None}
    else:
        inv.coverage["tag_manager"] = {"status": "complete", "count": 0,
                                       "reason": "kein Container in HTML, Theme-Code oder Mitschnitt"}


# -- Quelle: Netzwerk-Mitschnitt --------------------------------------------

def load_network(paths: list[Path]) -> tuple[list[dict], list[str], dict]:
    runs, problems, baselines = [], [], {}
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        base = data.get("base_url")
        for run in data.get("runs") or []:
            run.setdefault("consent", data.get("consent_mode"))
            run.setdefault("base_url", base)
            runs.append(run)
        for browser, names in (data.get("baseline_globals") or {}).items():
            baselines.setdefault(browser, set()).update(names)
    return runs, problems, baselines


def read_network(inv: Inventory, network_files: list[Path]) -> dict:
    """Ordnet jede Anfrage, jeden Cookie, Speicher-Schlüssel und jedes Global einem Dienst zu."""
    result = {"valid_runs": 0, "runs": 0, "consent_modes": set(), "wrong_theme": 0, "errors": 0,
              "requests": 0, "consent_states": []}
    if not network_files:
        inv.coverage["browser_capture"] = {"status": "not_readable", "count": None,
                                           "reason": "kein Mitschnitt übergeben (--network)"}
        return result
    runs, problems, baselines = load_network(network_files)
    for run in runs:
        if run.get("base_url"):
            host = (urlparse(run["base_url"]).hostname or "").lower()
            if host:
                inv.own_hosts.add(host)
    pixel_rows = {row["location"].get("pixel_id"): row for row in inv.integrations.values()
                  if row["integration_type"].startswith("web_pixel")}
    script_rows = {row["location"]["url"].split("?")[0]: row for row in inv.integrations.values()
                   if row["integration_type"] == "script_tag"}
    extension_rows = defaultdict(list)
    for row in inv.integrations.values():
        if row["integration_type"] in ("app_embed", "app_block") and row["location"].get("extension_uuid"):
            extension_rows[row["location"]["extension_uuid"].lower()].append(row)
    devices = defaultdict(set)
    for run in runs:
        result["runs"] += 1
        state = run.get("state") or "ok"
        if state == "wrong_theme":
            result["wrong_theme"] += 1
            continue
        if state != "ok":
            result["errors"] += 1
            continue
        result["valid_runs"] += 1
        consent = run.get("consent") or "declined"
        result["consent_modes"].add(consent)
        page = run.get("template") or run.get("page_id") or "?"
        devices[run.get("page_id")].add(run.get("device"))
        if run.get("privacy"):
            result["consent_states"].append({"page_id": run.get("page_id"), "device": run.get("device"),
                                             "consent": consent, "privacy": run["privacy"]})
        for request in run.get("requests") or []:
            url = request.get("url") or ""
            if not url.startswith("http"):
                continue
            result["requests"] += 1
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            frame = request.get("frame_url") or ""
            pixel_match = PIXEL_IN_URL.search(frame) or PIXEL_IN_URL.search(url)
            pixel_row = pixel_rows.get(pixel_match.group(1)) if pixel_match else None
            kind, sid = inv.classify(host, parsed.path)
            # Ein Skript-Tag oder eine App-Erweiterung auf einem Shopify- oder
            # Shop-Host gehört trotzdem zu seiner Einbindung.
            if kind in ("own", "platform"):
                if url.split("?")[0] in script_rows:
                    _attach(script_rows[url.split("?")[0]], request, run, consent, page, exact=True)
                extension = EXTENSION_IN_URL.search(parsed.path)
                for row in extension_rows.get(extension.group(1).lower(), []) if extension else []:
                    _attach(row, request, run, consent, page, exact=True)
            if kind == "own":
                for container in tracking_ids.container_ids(url):
                    inv.containers_seen[container].add("network")
                proxy = PROXY_PATH.match(parsed.path)
                if proxy:
                    prefix = f"/{proxy.group(1)}/{proxy.group(2)}"
                    row = inv.add(f"app_proxy:{prefix}", f"proxy:{prefix}", "app_proxy", {"path": prefix, "files": []},
                                  "active", "network", {"source": "app_proxy", "detail": "Anfrage im Mitschnitt"})
                    _attach(row, request, run, consent, page, exact=True)
                continue
            if kind == "platform":
                for container in tracking_ids.container_ids(url):
                    inv.containers_seen[container].add("network")
                continue
            if kind == "ignored":
                continue
            for container in tracking_ids.container_ids(url):
                inv.containers_seen[container].add("network")
            sends = tracking_ids.sends_data(request.get("method"), request.get("resource_type"), url)
            pre = request.get("consent_phase") == "pre" or consent == "declined"
            if kind in ("unknown", "own_subdomain"):
                reason = "Subdomain des Shops, oft ein eigener Mess-Endpunkt" if kind == "own_subdomain" else None
                inv.note_unknown(host, "browser_capture", "", reason)
                entry = inv.unknown[host]
                entry["requests"] += 1
                entry["sends"] = entry["sends"] or sends
                entry["pages"].add(page)
                entry.setdefault("example", url[:200])
            traces = inv.service_traces[sid]
            traces["hosts"].add(host)
            traces["pages"].add(page)
            inv.network_hits.append({"service_id": sid, "host": host, "page": page, "consent": consent,
                                     "pre": pre, "sends": sends, "status": request.get("status"),
                                     "failed": bool(request.get("failure"))})
            # Zuordnung zur Einbindung: erst der Pixel-Rahmen, dann der exakte Host.
            targets = []
            if pixel_row is not None:
                _attach(pixel_row, request, run, consent, page, exact=True)
                pixel_row["hosts"].add(host)
                attached = [pixel_row]
            else:
                rows = inv.by_service(sid)
                if not rows:
                    rows = [inv.add(f"network:{sid}", sid, "network_only", {}, "active", "network",
                                    {"source": "browser_capture", "detail": "nur im Mitschnitt gesehen, Weg offen"})]
                exact = [row for row in rows if host in row["hosts"]]
                if not exact:
                    exact = [row for row in rows if row["integration_type"] == "network_only"]
                    for row in exact:
                        row["hosts"].add(host)
                for row in rows:
                    _attach(row, request, run, consent, page, exact=row in exact)
            targets = tracking_ids.request_targets(url, request.get("post_data")) if sends else []
            for target in targets:
                context = f"pixel:{pixel_match.group(1)}" if pixel_match else "page"
                inv.add_sender(target, pixel_row["integration_id"] if pixel_row else None, sid,
                               "web_pixel" if pixel_row else "page", target.get("events") or [], "network",
                               context=context, run_key=_run_key(run), page=page, consent=consent, pre=pre)
        # Spuren: Cookies, Speicher, Globals
        for cookie in run.get("cookies") or []:
            _trace(inv, "cookies", cookie.get("name") or "", f"{cookie.get('name')} @ {cookie.get('domain')}",
                   inv.catalog.service_for_cookie)
        for kind_key, store in (("local_storage", "localStorage"), ("session_storage", "sessionStorage")):
            for origin, keys in (run.get(kind_key) or {}).items():
                for key in keys or []:
                    _trace(inv, "storage_keys", key, f"{store}:{key} @ {origin}", inv.catalog.service_for_cookie)
        baseline = baselines.get(run.get("browser") or "", set())
        for name in run.get("new_globals") or []:
            if name in baseline or name.isdigit():
                continue
            _trace(inv, "globals", name, name, inv.catalog.service_for_global)

    pages = len(devices)
    complete_pages = sum(1 for d in devices.values() if {"desktop", "mobile"} <= d)
    reasons = list(problems)
    if result["wrong_theme"]:
        reasons.append(f"{result['wrong_theme']} Aufruf(e) zeigten ein anderes Theme (wrong_theme) und zählen nicht")
    if result["errors"]:
        reasons.append(f"{result['errors']} Aufruf(e) mit Fehler")
    if pages and complete_pages < pages:
        reasons.append(f"nur {complete_pages} von {pages} Seiten auf Desktop und Mobil")
    if result["valid_runs"] == 0:
        inv.coverage["browser_capture"] = {"status": "not_readable", "count": None,
                                           "reason": "; ".join(reasons) or "kein gültiger Aufruf im Mitschnitt"}
    else:
        inv.coverage["browser_capture"] = {"status": "partial" if reasons else "complete",
                                           "count": result["valid_runs"], "reason": "; ".join(reasons) or None}
    return result


def _run_key(run: dict) -> str:
    return f"{run.get('page_id')}|{run.get('device')}|{run.get('run')}|{run.get('consent')}"


def _attach(row: dict, request: dict, run: dict, consent: str, page: str, exact: bool) -> None:
    net = row["_net"]
    url = request.get("url") or ""
    sends = tracking_ids.sends_data(request.get("method"), request.get("resource_type"), url)
    status = request.get("status")
    failed = bool(request.get("failure")) or (isinstance(status, int) and status >= 400)
    key = "exact" if exact else "service"
    bucket = net.setdefault(key, {"requests": 0, "ok": 0, "failed": 0, "sends": False, "pre_sends": False,
                                  "pre_loads": False, "pages": set()})
    bucket["requests"] += 1
    bucket["failed" if failed else "ok"] += 1
    bucket["sends"] = bucket["sends"] or sends
    pre = request.get("consent_phase") == "pre" or consent == "declined"
    if pre:
        bucket["pre_sends"] = bucket["pre_sends"] or sends
        bucket["pre_loads"] = True
    bucket["pages"].add(page)
    if exact:
        row["page_types"].add(page)


def _trace(inv: Inventory, field: str, name: str, label: str, lookup) -> None:
    sid = lookup(name)
    if sid is None:
        inv.unknown_traces[field].add(label)
        return
    inv.service_traces[sid][field].add(label)


# -- Optionale Dateien der Skill --------------------------------------------

def _read_json(path: Path | None):
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_app_names(inv: Inventory, data) -> None:
    clients = sorted({row["api_client_id"] for row in inv.integrations.values()
                      if row["integration_type"] == "web_pixel_app" and row["api_client_id"]})
    if data is None and not clients and inv.coverage.get("web_pixels", {}).get("status") != "not_readable":
        inv.coverage["app_names"] = {"status": "complete", "count": 0, "reason": "keine App-Pixel aufzulösen"}
        return
    if data is None:
        inv.coverage["app_names"] = {
            "status": "not_readable", "count": None,
            "reason": ("App-Namen kommen über app(id:) aus der Admin-API; die Skill übergibt sie mit --app-names"
                       + (f" ({len(clients)} Kennung(en) offen)" if clients else ""))}
        return
    resolved = [c for c in clients if (data.get(c) or {}).get("title")]
    open_ids = sorted(set(clients) - set(resolved))
    inv.coverage["app_names"] = {"status": "complete" if not open_ids else "partial", "count": len(resolved),
                                 "reason": ("offen: " + ", ".join(open_ids)) if open_ids else None}


def read_metafields(inv: Inventory, data) -> list[str]:
    if data is None:
        inv.coverage["shop_metafields"] = {"status": "not_readable", "count": None,
                                           "reason": "Admin-Abfrage, die Skill übergibt sie mit --metafields"}
        return []
    namespaces = sorted({str(item.get("namespace")) for item in data if isinstance(item, dict) and item.get("namespace")})
    unmatched = []
    for namespace in namespaces:
        client = re.match(r"app--(\d+)", namespace)
        sid = None
        if client:
            for row in inv.integrations.values():
                if row.get("api_client_id") == client.group(1):
                    sid = row["service_id"]
                    break
            sid = sid or f"pixel:{client.group(1)}"
        else:
            sid = inv.catalog.service_for_name(namespace)
        if sid is None:
            unmatched.append(namespace)
            continue
        if any(row["service_id"] == sid and row["integration_type"] != "metafield_only"
               for row in inv.integrations.values()):
            for row in inv.by_service(sid):
                row["evidence"].append({"source": "shop_metafields", "detail": f"Namensraum {namespace}"})
            continue
        inv.add(f"metafield:{namespace}", sid, "metafield_only", {"namespace": namespace}, "active", "config",
                {"source": "shop_metafields", "detail": "nur Shop-Metafelder, keine Einbindung gefunden"})
    inv.coverage["shop_metafields"] = {"status": "complete", "count": len(namespaces),
                                       "reason": None if not unmatched else
                                       "ohne Zuordnung, von Hand prüfen: " + ", ".join(unmatched[:20])}
    return unmatched


def read_admin_apps(inv: Inventory, data) -> None:
    if data is None:
        inv.coverage["admin_app_list"] = {"status": "not_readable", "count": None,
                                          "reason": "nur im Admin lesbar, die Liste liefert das Team (--admin-apps)"}
        return
    titles = [str(item.get("title") if isinstance(item, dict) else item) for item in data]
    for title in titles:
        sid = inv.catalog.service_for_name(title)
        matched = [row for row in inv.integrations.values()
                   if (sid and row["service_id"] == sid) or row["service_name"].lower() == title.lower()]
        for row in matched:
            row["installed"] = "yes"
        if not matched:
            row = inv.add(f"admin_app:{_slug(title)}", sid or f"app:{_slug(title)}", "server_side",
                          {"admin_title": title}, "active", "admin",
                          {"source": "admin_app_list", "detail": "nur in der Admin-Liste, keine Spur im Frontend"})
            row["installed"] = "yes"
            if not sid:
                row["service_name"] = title
    inv.coverage["admin_app_list"] = {"status": "complete", "count": len(titles), "reason": None}


# ---------------------------------------------------------------------------
# Ableitungen
# ---------------------------------------------------------------------------

def derive_states(inv: Inventory, capture: dict) -> None:
    """Zustand und Consent-Verhalten aus dem Mitschnitt, nur wo er etwas belegt."""
    capture_ok = capture["valid_runs"] > 0 and inv.coverage["browser_capture"]["status"] in ("complete", "partial")
    declined = "declined" in capture["consent_modes"]
    seen_services = {hit["service_id"] for hit in inv.network_hits}
    service_pre = defaultdict(lambda: {"sends": False, "loads": False})
    service_sends = defaultdict(bool)
    for hit in inv.network_hits:
        service_sends[hit["service_id"]] = service_sends[hit["service_id"]] or hit["sends"]
        if hit["pre"]:
            service_pre[hit["service_id"]]["loads"] = True
            service_pre[hit["service_id"]]["sends"] = service_pre[hit["service_id"]]["sends"] or hit["sends"]

    for row in inv.integrations.values():
        net = row["_net"]
        exact = net.get("exact")
        if capture_ok and row["integration_type"].startswith("web_pixel") and not exact:
            # Ein Pixel sendet aus seinem eigenen Rahmen; was der Dienst sonst
            # schickt, kommt über einen anderen Weg und gehört nicht ihm.
            if declined:
                row["before_consent"], row["before_consent_basis"] = "silent", "integration"
            continue
        if capture_ok:
            if exact:
                row["sends_data"] = "sends" if exact["sends"] else "loads_only"
                if exact["failed"] and not exact["ok"]:
                    row["state"], row["state_basis"] = "broken", "network"
                elif row["state"] == "active":
                    row["state_basis"] = "network"
            elif row["integration_type"] == "theme_code" and row["state"] == "active" and (
                    row["hosts"] or row["service_id"] not in seen_services):
                # Code im Theme, dessen Adressen in keinem Aufruf auftauchen: ein Rest
                # einer deinstallierten App oder ein Snippet, das nirgends gerendert wird.
                # Ohne eigene Adresse (nur ein Kennwort) zählt, ob der Dienst überhaupt lädt.
                row["state"], row["state_basis"] = "leftover", "network"
            elif row["service_id"] in seen_services:
                row["sends_data"] = "sends" if service_sends[row["service_id"]] else "loads_only"
            if declined:
                if exact:
                    row["before_consent"] = "sends" if exact["pre_sends"] else "loads" if exact["pre_loads"] else "silent"
                    row["before_consent_basis"] = "integration"
                elif row["service_id"] in seen_services:
                    pre = service_pre[row["service_id"]]
                    row["before_consent"] = "sends" if pre["sends"] else "loads" if pre["loads"] else "silent"
                    row["before_consent_basis"] = "service"
                else:
                    row["before_consent"] = "silent"
                    row["before_consent_basis"] = "service"
        traces = inv.service_traces.get(row["service_id"])
        if traces:
            row["cookies"] |= traces["cookies"]
            row["storage_keys"] |= traces["storage_keys"]
            row["globals"] |= traces["globals"]
            if not exact:
                row["page_types"] |= traces["pages"]


def build_tracking(inv: Inventory) -> dict:
    """Je Messziel alle Absender und jedes Event mit mehr als einem Absender."""
    targets: dict[str, dict] = {}
    for sender in inv.senders:
        entry = targets.setdefault(sender["target_id"], {
            "target_id": sender["target_id"], "kind": sender["kind"],
            "service_id": tracking_ids.KIND_SERVICE.get(sender["kind"]), "labels": set(),
            "senders": {}, "network": defaultdict(lambda: defaultdict(lambda: defaultdict(int))),
        })
        if sender.get("label"):
            entry["labels"].add(sender["label"])
        if sender["basis"] == "network":
            for event in sender["events"] or ["(ohne Event)"]:
                entry["network"][(sender["run_key"], sender["page"])][event][sender["context"]] += 1
            key = (sender["integration_id"] or f"page:{sender['service_id']}", "network")
        else:
            key = (sender["integration_id"], "config")
        record = entry["senders"].setdefault(key, {
            "integration_id": sender["integration_id"], "service_id": sender["service_id"], "path": sender["path"],
            "basis": sender["basis"], "events": set(), "events_known": False, "pages": set(),
            "before_consent": None})
        record["events"] |= set(sender["events"])
        record["events_known"] = record["events_known"] or bool(sender["events"])
        if sender["basis"] == "network":
            record["pages"].add(sender["page"])
            if sender.get("pre"):
                record["before_consent"] = "sends"

    out = []
    for target_id, entry in sorted(targets.items()):
        senders = list(entry["senders"].values())
        duplicates = []
        config_events = defaultdict(set)
        spellings = defaultdict(set)
        for record in senders:
            if record["basis"] == "config" and record["integration_id"]:
                row = inv.integrations.get(record["integration_id"])
                if row and row["state"] in ("disabled", "leftover"):
                    continue
                for event in record["events"]:
                    config_events[_norm_event(event)].add(record["integration_id"])
                    spellings[_norm_event(event)].add(event)
        for event, ids in sorted(config_events.items()):
            if len(ids) > 1:
                duplicates.append({"event": event, "spellings": sorted(spellings[event]), "senders": sorted(ids),
                                   "basis": "config"})
        net_dups = defaultdict(lambda: {"contexts": set(), "pages": set(), "repeated": False})
        for (run_key, page), events in entry["network"].items():
            for event, contexts in events.items():
                if event == "(ohne Event)":
                    continue
                norm = _norm_event(event)
                if len(contexts) > 1:
                    net_dups[norm]["contexts"] |= set(contexts)
                    net_dups[norm]["pages"].add(page)
                elif norm in ("page_view", "pageview") and sum(contexts.values()) > 1:
                    net_dups[norm]["contexts"] |= set(contexts)
                    net_dups[norm]["pages"].add(page)
                    net_dups[norm]["repeated"] = True
        for event, info in sorted(net_dups.items()):
            duplicates.append({"event": event, "senders": sorted(info["contexts"]), "basis": "network",
                               "pages": sorted(info["pages"]),
                               "kind": "repeated" if info["repeated"] and len(info["contexts"]) == 1 else "two_senders"})
        out.append({
            "target_id": target_id,
            "kind": entry["kind"],
            "service_id": entry["service_id"],
            "labels": sorted(entry["labels"]),
            "senders": [{**r, "events": sorted(r["events"]), "pages": sorted(r["pages"])}
                        for r in sorted(senders, key=lambda r: (r["basis"], r["integration_id"] or ""))],
            "duplicate_events": duplicates,
            "target_after_migration": None,
        })
    return {"targets": out}


def _norm_event(event: str) -> str:
    """`PageView` und `page_view` sind dasselbe Event in zwei Schreibweisen."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower().replace("__", "_") if event else event


def finalize(inv: Inventory, capture: dict) -> dict:
    rows = []
    for row in sorted(inv.integrations.values(), key=lambda r: (r["service_id"], r["integration_type"],
                                                                r["integration_id"])):
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        for key in ("page_types", "hosts", "cookies", "storage_keys", "globals"):
            clean[key] = sorted(clean[key])
        rows.append(clean)
    services = {}
    for row in rows:
        entry = services.setdefault(row["service_id"], {
            "service_id": row["service_id"], "service_name": row["service_name"], "vendor": row["vendor"],
            "category": row["category"], "known": inv.catalog.describe(row["service_id"])["known"],
            "integration_ids": [], "integration_types": set(), "hosts": set(), "survives_theme_switch": set()})
        entry["integration_ids"].append(row["integration_id"])
        entry["integration_types"].add(row["integration_type"])
        entry["hosts"] |= set(row["hosts"])
        entry["survives_theme_switch"].add(row["survives_theme_switch"])
    for sid, traces in inv.service_traces.items():
        if sid in services:
            services[sid]["hosts"] |= traces["hosts"]
    service_list = []
    for entry in services.values():
        survives = entry.pop("survives_theme_switch")
        entry["survives_theme_switch"] = (True if survives == {True} else False if survives == {False}
                                          else "mixed" if True in survives and False in survives else None)
        entry["integration_types"] = sorted(entry["integration_types"])
        entry["hosts"] = sorted(entry["hosts"])
        service_list.append(entry)
    unknown = []
    for host, entry in sorted(inv.unknown.items()):
        unknown.append({"host": host, "sources": sorted(entry["sources"]), "where": sorted(entry["where"])[:10],
                        "reason": entry["reason"], "requests": entry["requests"], "sends": entry["sends"],
                        "pages": sorted(entry["pages"]), "example": entry.get("example"),
                        "service_id": None, "resolved_by": None})
    coverage = {}
    for key, label in SOURCES:
        entry = inv.coverage.get(key) or {"status": "not_readable", "count": None,
                                          "reason": "nicht Teil dieses Scans"}
        coverage[key] = {"label": label, **entry}
    return {"integrations": rows, "services": sorted(service_list, key=lambda s: s["service_id"]),
            "unknown_hosts": unknown,
            "unknown_traces": {k: sorted(v)[:200] for k, v in inv.unknown_traces.items()},
            "consent_states": capture.get("consent_states", [])[:200],
            "coverage": coverage}


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def scan(snapshot: Path | None, html: Path | None = None, network: list[Path] | None = None,
         gtm_files: list[Path] | None = None, templates: dict | None = None, app_names: dict | None = None,
         metafields=None, admin_apps=None, own_hosts: list[str] | None = None,
         catalog: HostCatalog | None = None) -> tuple[dict, dict]:
    """Das Inventar aus allen übergebenen Quellen: `(apps, tracking)`."""
    catalog = catalog or HostCatalog.load()
    inv = Inventory(catalog, set(own_hosts or []))
    # Eigene Hosts zuerst aus dem Mitschnitt, damit die Theme-Suche sie schon kennt.
    for path in network or []:
        try:
            base = json.loads(path.read_text(encoding="utf-8")).get("base_url")
        except (OSError, ValueError):
            base = None
        if base:
            inv.own_hosts.add((urlparse(base).hostname or "").lower())
    read_html(inv, html, app_names or {})
    read_theme(inv, snapshot, templates)
    read_gtm(inv, gtm_files or [])
    capture = read_network(inv, network or [])
    # Ein Container, den erst der Mitschnitt zeigt, bekommt noch eine Zeile.
    for container in sorted(inv.containers_seen):
        if f"tag_manager:{container}" not in inv.integrations:
            read_gtm_seen_only(inv, container)
    read_app_names(inv, app_names)
    read_metafields(inv, metafields)
    read_admin_apps(inv, admin_apps)
    inv.coverage["checkout_backend"] = {
        "status": "not_readable", "count": None,
        "reason": ("Functions, Rabatte, Versand und Bestellquellen kommen aus der Admin-API; sie überleben den "
                   "Wechsel und werden in der Skill aufgenommen")}
    proxy_rows = [r for r in inv.integrations.values() if r["integration_type"] == "app_proxy"]
    inv.coverage["app_proxy"] = {
        "status": "complete" if capture["valid_runs"] and snapshot else "partial", "count": len(proxy_rows),
        "reason": None if capture["valid_runs"] and snapshot else "nur aus einer Quelle (Theme-Code oder Mitschnitt)"}
    if capture["valid_runs"] == 0:
        inv.coverage["consent"] = {"status": "not_readable", "count": None, "reason": "kein Mitschnitt"}
    elif {"declined", "accepted"} <= capture["consent_modes"]:
        inv.coverage["consent"] = {"status": "complete", "count": len(capture["consent_states"]), "reason": None}
    else:
        inv.coverage["consent"] = {
            "status": "partial", "count": len(capture["consent_states"]),
            "reason": ("nur " + ", ".join(sorted(capture["consent_modes"])) +
                       "; mit Einwilligung nur nach Freigabe des Teams (--consent accepted)")}
    derive_states(inv, capture)
    tracking = build_tracking(inv)
    apps = finalize(inv, capture)
    generated = _now()
    apps = {"generated_at": generated, "sources": {
        "snapshot": str(snapshot) if snapshot else None, "html": str(html) if html else None,
        "network": [str(p) for p in network or []], "gtm": [str(p) for p in gtm_files or []]},
        "own_hosts": sorted(inv.own_hosts), **apps}
    tracking = {"generated_at": generated, **tracking, "coverage": {
        key: apps["coverage"][key] for key in ("browser_capture", "web_pixels", "tag_manager", "theme_code",
                                                "consent")}}
    return apps, tracking


def read_gtm_seen_only(inv: Inventory, container: str) -> None:
    inv.add(f"tag_manager:{container}", "google_tag_manager", "tag_manager",
            {"container_id": container, "seen_in": sorted(inv.containers_seen[container])[:10]},
            "active", "network", {"source": "tag_manager", "detail": "Container im Mitschnitt, nicht aufgelöst"})
    cov = inv.coverage.get("tag_manager") or {}
    if cov.get("status") == "complete":
        inv.coverage["tag_manager"] = {"status": "not_readable" if not cov.get("count") else "partial",
                                       "count": cov.get("count") or None,
                                       "reason": f"Container {container} im Mitschnitt, nicht aufgelöst (--gtm fehlt)"}


def findings(apps: dict, tracking: dict) -> dict:
    rows = apps["integrations"]
    return {
        "unknown_hosts": len(apps["unknown_hosts"]),
        "duplicate_events": sum(len(t["duplicate_events"]) for t in tracking["targets"]),
        "script_tags": sum(1 for r in rows if r["integration_type"] == "script_tag"),
        "leftover": sum(1 for r in rows if r["state"] == "leftover"),
        "broken": sum(1 for r in rows if r["state"] == "broken"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="App-Inventar eines Shopify-Themes")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("scan", help="Inventar aus Sicherung, HTML, Mitschnitt und Tag Manager")
    run.add_argument("--snapshot", required=True, help="Theme-Sicherung (Verzeichnis mit layout/, config/, …)")
    run.add_argument("--html", help="Ordner mit gespeichertem HTML (capture_network.py, Unterordner html/)")
    run.add_argument("--network", action="append", default=[], help="network.json aus capture_network.py, wiederholbar")
    run.add_argument("--gtm", action="append", default=[], help="gespeicherte gtm.js oder aufgelöstes JSON, wiederholbar")
    run.add_argument("--templates", help="templates.json aus theme.templates (Template-Nutzung)")
    run.add_argument("--app-names", help='JSON {"<apiClientId>": {"title", "handle", "installed"}} aus app(id:)')
    run.add_argument("--metafields", help='JSON [{"namespace", "key", "type"}] der Shop-Metafelder')
    run.add_argument("--admin-apps", help='JSON ["App-Titel", ...] oder [{"title"}] aus dem Admin')
    run.add_argument("--own-host", action="append", default=[], help="eigene Domain des Shops, wiederholbar")
    run.add_argument("--hosts", default=str(DEFAULT_HOSTS), help="Host-Katalog")
    run.add_argument("--out", required=True, help="Ziel apps.json; tracking.json landet daneben")
    run.add_argument("--tracking-out", help="Ziel tracking.json, Standard neben --out")
    args = parser.parse_args(argv)

    try:
        catalog = HostCatalog.load(args.hosts)
        apps, tracking = scan(
            Path(args.snapshot), Path(args.html) if args.html else None, [Path(p) for p in args.network],
            [Path(p) for p in args.gtm], _read_json(Path(args.templates) if args.templates else None),
            _read_json(Path(args.app_names) if args.app_names else None),
            _read_json(Path(args.metafields) if args.metafields else None),
            _read_json(Path(args.admin_apps) if args.admin_apps else None), args.own_host, catalog)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    out = Path(args.out)
    tracking_out = Path(args.tracking_out) if args.tracking_out else out.with_name("tracking.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    tracking_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(apps, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tracking_out.write_text(json.dumps(tracking, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    found = findings(apps, tracking)
    print(json.dumps({"out": str(out), "tracking": str(tracking_out), "integrations": len(apps["integrations"]),
                      "services": len(apps["services"]), "targets": len(tracking["targets"]), **found,
                      "not_readable": sorted(k for k, v in apps["coverage"].items() if v["status"] == "not_readable")},
                     ensure_ascii=False))
    return 1 if any(found.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
