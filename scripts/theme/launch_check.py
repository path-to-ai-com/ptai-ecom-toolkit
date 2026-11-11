"""Launch-Check: was vor einem Livegang stimmen muss, als wiederholbarer Prüflauf.

Macht Phase 9 der Theme-Migration (`reference/theme-migration/launch-checklist.md`)
eigenständig ausführbar: mit oder ohne Migrationslauf, auch für einen Launch
ohne Theme-Wechsel (größere Theme-Änderung, neuer Shop). Je Punkt der
Checkliste ein Prüfschritt mit Status und einer Zeile Beleg:

    ok        geprüft und erfüllt
    missing   geprüft, fehlt oder verletzt eine Regel; muss vor dem Launch erledigt sein
    blocked   nicht prüfbar, weil eine Voraussetzung fehlt (Zugang, Entwurf, Mitschnitt)
    manual    braucht einen Menschen; der Punkt trägt die Frage und wer sie beantwortet
    n/a       trifft für diesen Launch nicht zu

**Schreibt nie in den Shop.** Jede Abfrage ist lesend; Mutationen gibt es hier
nicht, und `themePublish` wird nirgends aufgerufen. Die Abfragen kommen aus den
Modulen `files` und `translations` (dort gegen das Admin-Schema 2026-04
validiert) plus zwei eigenen, am 06.10.2026 mit dem Validator der Skill
`shopify-admin` gegen 2026-04 geprüft: `shopLocales(published: true)`
(Scope `read_locales`) und `shop.customerAccountsV2` (ohne eigenen Scope).
Scheitert eine Abfrage, steht der betroffene Punkt als `blocked` mit Grund;
der Lauf geht weiter.

**Die Vorschau eines Entwurfs ist nur im Browser verlässlich** (Cookie und
Weiterleitung, `seo-parity.md`). Was die Seiten des Entwurfs betrifft (Hosts,
Statuscodes, `noindex`, Canonicals), liest dieses Modul deshalb aus einem
Mitschnitt von `scripts/browser/capture_network.py`, den die Skill vorher
zieht, je Theme ein Ordner unter `<lauf>/capture/old-<consent>/` und
`<lauf>/capture/new-<consent>/`. "old" ist das Theme, das vor dem Launch live
ist, "new" der Entwurf, nach dem Launch das veröffentlichte Theme. Nach dem
Launch (`--after`) ist die Seite live, dann genügt ein HTTP-Abruf.

Die SEO-Ausgabe (strukturierte Daten, hreflang, Open Graph, Kopfdaten) vergleicht
`seo_parity` aus demselben Mitschnitt; offene Punkte aus Prüfberichten, auch
außerhalb des Workspace (`theme_migration.report_paths`), und aus der Prüfliste
der Bestandsaufnahme (`theme_migration.acceptance_checklist`) liest
`launch_findings`. Beides ist nie eine Frage: offen heißt `missing`, nicht
auffindbar `blocked`.

**Die eine Liste offener Punkte** (`migration/open-items.json`, Modul `open_items`)
ist die Quelle, sobald es sie gibt oder ein Migrationslauf besteht: jeder offene
Punkt der Gates G4 und G5 ist `missing`, eine fehlende Liste in einem
Migrationslauf `blocked`. Prüfberichte, Prüfliste, `findings.json` aus
`verify-theme` und die Abnahme sind dann nur noch Quellen für den Import; was
dort offen steht und in der Liste fehlt, ist `missing`. Ohne Liste und ohne
Migrationslauf gilt die ältere Auswertung je Bericht, Prüfliste und Abnahme.

Ein Migrationslauf (`run_state`) ist optional: ohne ihn kommen die Theme-IDs aus
`theme_migration` der Config oder aus `--live-theme-id` und `--draft-theme-id`.
Antworten auf `manual`-Punkte stehen in `reporting/launch-answers.json` und
gelten bei jedem weiteren Lauf, mit Name und Datum dessen, der geantwortet hat.

**Nach dem Launch zusätzlich** (seit 10.11.2026):

- *Testbestellung:* liest `<lauf>/test-order/walk.json` aus `scripts/browser/walk_checkout.py`
  (Kasse bis zur Zahlung, die Bestellung setzt ein Mensch ab) und prüft je Ziel, ob der Kauf
  ankommt: Bestellung in Shopify, GA4, Google Ads, Meta und die übrigen Werbe-Pixel. Lesewege
  und ihre Grenzen stehen in `theme.test_order`. Danach Storno und Erstattung als Frage an das
  Team, bestätigt aus der Bestellung selbst.
- *Tracking nach Einwilligung:* Mitschnitt mit erteilter Einwilligung je Seitentyp, neu gegen
  vorher, dazu ob die Einwilligung Shopify (`customerPrivacy`) und den Consent Mode erreicht.
  Ein Durchlauf, in dem der Dialog nicht bedient wurde (`no_dialog`, `stuck`), zählt nie als
  Durchlauf mit Einwilligung.

**Seit 11.11.2026**, aus zwei Fehlern im Launch-Ablauf selbst:

- *App-Einträge* (`app-injections`, nach dem Launch `app-injections-after`): neue Zeilen mit `render`,
  `include` oder `script` in `layout/theme.liquid` und neue oder wieder eingeschaltete App-Embeds gegen
  den hochgeladenen Stand. Referenz vor dem Launch ist das Ziel-Repo, danach die Sicherung des Entwurfs,
  die `theme.launch publish` direkt vor dem Veröffentlichen anlegt (`<lauf>/published-draft/`).
- *Vor Einwilligung* (`tracking-pre-consent`, `-after`): Werbe- und Analysedienste, die neu vor einer
  Einwilligung senden, über den Host-Katalog (Microsoft Advertising an `bat.bing.com` und `bat.bing.net`).
- *Pixel-Liste* (`web-pixels` vorher, `web-pixels-after` danach): `webPixelsConfigList` des Live-Shops
  wird vor dem Launch in `<lauf>/web-pixels-before.json` festgehalten und danach verglichen; ein
  fehlendes Pixel ist ein Befund, außer es ist bewusst entfernt und, als Custom Pixel, gesichert.
- *Custom Pixels gesichert* (`custom-pixel-backup`): jedes, das laut Entscheidung entfällt, liegt unter
  `migration/inventory/pixels/` mit Code und gelesener Notiz (`theme.web_pixels`).
- *Kauf je Messziel*: jede GA4-Property und jede Google-Ads-Kauf-Conversion, die der Shop vor dem Launch
  bediente, ist ein eigener Punkt der Testbestellung.

**Nachtrag vom Nachmittag des 11.11.2026**, aus drei weiteren Befunden:

- *Datenschicht je GA4-Property* (`funnel-ga4-<g-id>`, nach dem Launch mit `-after`): `view_item`,
  `add_to_cart` und `begin_checkout` je Property aus Durchläufen von `walk_checkout.py --headless`, altes
  gegen neues Theme unter denselben Bedingungen, Pflicht am Handy in WebKit mit langsamer Verbindung
  (`theme.funnel_events`). Ein `add_to_cart` ging verloren, weil Safari einen Abruf beim Seitenwechsel
  verwarf; am Rechner fiel das nicht auf.
- *Echtzeit je Property* (nur `--after`, `realtime-ga4-<g-id>`): GA4-Echtzeit je Property gegen die
  Property, die der Shop serverseitig beliefert (Littledata), und `purchase` gegen die Bestellungen.
- *Abgelöste Consent-App* (nur `--after`, `consent-app-after`): Skripte aus Shopify Files, die die App ins
  Layout schreibt, im Live-Theme und in den Seiten; ihre Datei darf nicht mehr abrufbar sein, und die App
  ist deinstalliert, nicht nur deaktiviert.
- *Gedrosselte Mitschnitte* (HTTP 429, Warteseite) zählen nicht und stehen als nicht prüfbar, nie als
  Fehler des Shops.

CLI:
    python3 -m theme.launch_check [--after] [--live-theme-id <id>] [--draft-theme-id <id>]
        [--launch-date YYYY-MM-DD] [--run-id <id>] [--pages <pages.json>]
        [--network-old <network.json> ...] [--network-new <network.json> ...]
        [--test-order <walk.json>] [--answers <file>] [--workspace .]

Schreibt `reporting/runs/<date>-launch-check/launch-check.json` und
`launch-check.md` (mit `--after`: `launch-check-after.*`). Exit 0 heißt Go,
1 heißt No-Go oder offen, 2 heißt Fehler.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from theme import (EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config,
                   now_utc, write_json)
from theme import (apps, funnel_events, launch_findings, open_items, run_state, seo_parity, sync, test_order,
                   tracking_ids, web_pixels)
from theme.files import fetch_by_names, list_files, list_themes
from theme.shopify import ShopifyError, numeric_id, transport_from_config
from theme.translations import read_resource

OK, MISSING, BLOCKED, MANUAL, NA = "ok", "missing", "blocked", "manual", "n/a"
STATUS_ORDER = (MISSING, BLOCKED, MANUAL, OK, NA)
STATUS_LABEL = {MISSING: "Fehlt", BLOCKED: "Nicht prüfbar", MANUAL: "Braucht einen Menschen", OK: "Erfüllt",
                NA: "Trifft nicht zu"}
RECOMMENDATION_LABEL = {"go": "Go", "no_go": "No-Go", "open": "Offen"}
OPERATOR, TEAM, BOTH = "Betreiber", "Team", "Betreiber und Team"

LOCALES_QUERY = """query LaunchCheckLocales {
  shopLocales(published: true) { locale primary published }
}"""

ACCOUNTS_QUERY = """query LaunchCheckAccounts {
  shop { customerAccountsV2 { customerAccountsVersion } }
}"""

#: Befunde aus verify-theme, die vor dem Launch erledigt sein müssen.
LAUNCH_SEVERITIES = launch_findings.LAUNCH_SEVERITIES
#: Status eines Befunds oder Testpunkts, der nichts mehr verlangt.
CLOSED = launch_findings.CLOSED
#: Status eines Testpunkts, an dem noch etwas zu tun ist (test-round).
OPEN_TEST_STATUS = ("open", "in_progress", "decision")
#: Vergleichswerte, die direkt vor dem Launch gezogen werden, mit Quelle in `sources`.
BASELINE_FILES = {"gsc.json": "gsc", "ga4.json": "ga4", "cwv.json": "cwv", "crawl.json": "crawl"}
#: So viele Wochen vor Black Friday beginnt die Saisonspitze für den Launch.
SEASON_LEAD = timedelta(days=28)
#: Entscheidungen, nach denen ein Dienst oder eine App im neuen Theme bewusst fehlt.
DROPPED_DECISIONS = ("drop", "replace")
#: Crawler, deren Gruppe in der robots.txt zählt. Shopify sperrt etwa `Nutch` ganz, das ist Standard.
ROBOTS_AGENTS = ("*", "googlebot")
#: Kategorien aus `hosts.json`, deren Anfragen als Analyse-Ereignisse zählen. Werbung zählt nicht:
#: ihre Anfragen schwanken zwischen zwei Durchläufen derselben Seite um das Dreifache.
EVENT_CATEGORIES = ("analytics",)
#: Ab diesem Faktor und dieser Differenz gelten Ereignisse je Seite als vervielfacht.
EVENT_FACTOR = 1.5
EVENT_MIN_DELTA = 3
#: Pause zwischen zwei Abrufen der Storefront in Sekunden. Sie verträgt einen Prüfer zur Zeit mit drei
#: bis fünf Sekunden Abstand; schneller folgen HTTP 429 und eine Bot-Abfrage (seo-parity.md).
FETCH_PAUSE = 4.0
#: Je Thema des SEO-Vergleichs eine Zeile: ID, Titel.
SEO_TOPICS = {
    "structured_data": ("seo-structured-data", "Strukturierte Daten (JSON-LD)"),
    "hreflang": ("seo-hreflang", "hreflang"),
    "open_graph": ("seo-open-graph", "Open Graph"),
    "head": ("seo-head", "Title, Meta-Description und Canonical vorhanden"),
}
USER_AGENT = "ptai-ecom launch-check"
#: Ein Durchlauf der Kasse gilt für diesen Launch, wenn er höchstens so alt ist.
WALK_MAX_AGE = timedelta(days=7)
#: Werte von Shopify.customerPrivacy, die eine erteilte Einwilligung heißen.
PRIVACY_GRANTED = ("yes", "true")
#: Dateien, in die sich Apps beim Veröffentlichen eintragen: eine Zeile im Layout, ein App-Embed in den Einstellungen.
INJECTION_FILES = ("layout/theme.liquid", "config/settings_data.json")
#: Ordner im Lauf, in den der geführte Launch diese Dateien des Entwurfs direkt vor dem Veröffentlichen sichert.
DRAFT_BACKUP_DIR = "published-draft"
#: Zeilen im Layout, mit denen Code eingebunden wird: Snippet, Skript, Datei aus Shopify Files oder den Assets.
INJECTED_LINE = re.compile(r"\{%-?\s*(?:render|include)\b|<script\b|\|\s*(?:script_tag|file_url|asset_url)\b"
                           r"|cdn\.shopify\.com/s/files|/cdn/shop/files/", re.I)
#: Wörter, die in fast jeder Einbindung stehen und deshalb keine App erkennen lassen.
GENERIC_WORDS = frozenset({
    "shopify", "theme", "themes", "liquid", "layout", "render", "include", "snippet", "snippets", "section",
    "sections", "script", "scripts", "async", "defer", "module", "https", "files", "assets", "asset", "content",
    "header", "footer", "block", "blocks", "embed", "embeds", "settings", "config", "static", "loader", "widget",
    "google", "consent", "cookie", "cookies", "banner", "pixel", "pixels", "tracking", "analytics", "compliance",
    "privacy", "rules", "window", "function", "javascript", "value", "unless", "endif", "endunless", "media",
    "stylesheet", "crossorigin", "anonymous"})
#: Kategorien aus `hosts.json`, deren Aufrufe vor einer Einwilligung zählen.
PRE_CONSENT_CATEGORIES = ("ads", "analytics", "session_recording")


# ---------------------------------------------------------------------------
# Kalender
# ---------------------------------------------------------------------------

def easter(year: int) -> date:
    """Ostersonntag nach der gregorianischen Osterformel (Meeus, Jones, Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def german_holidays(year: int) -> dict:
    """Bundesweite Feiertage, dazu Heiligabend und Silvester, an denen kaum jemand erreichbar ist.

    Regionale Feiertage (Fronleichnam, Allerheiligen, Reformationstag) und andere
    Länder prüft dieses Modul nicht; das steht im Beleg.
    """
    sunday = easter(year)
    return {
        date(year, 1, 1): "Neujahr", sunday - timedelta(days=2): "Karfreitag",
        sunday + timedelta(days=1): "Ostermontag", date(year, 5, 1): "Tag der Arbeit",
        sunday + timedelta(days=39): "Christi Himmelfahrt", sunday + timedelta(days=50): "Pfingstmontag",
        date(year, 10, 3): "Tag der Deutschen Einheit", date(year, 12, 24): "Heiligabend",
        date(year, 12, 25): "1. Weihnachtstag", date(year, 12, 26): "2. Weihnachtstag",
        date(year, 12, 31): "Silvester",
    }


def black_friday(year: int) -> date:
    """Der Freitag nach dem vierten Donnerstag im November."""
    first = date(year, 11, 1)
    thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    return thursday + timedelta(days=22)


def season_window(year: int) -> tuple:
    """Saisonspitze samt Vorlauf: vier Wochen vor Black Friday bis Jahresende."""
    return black_friday(year) - SEASON_LEAD, date(year, 12, 31)


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def make_check(check_id: str, group: str, title: str, status: str, evidence: str, *, action: str = "",
               owner: str = "", question: str = "", links: list | None = None) -> dict:
    return {"id": check_id, "group": group, "title": title, "status": status, "evidence": evidence,
            "action": action, "owner": owner, "question": question, "links": links or []}


def preview_url(base_url: str, path: str, theme_id) -> str:
    """Adresse einer Seite mit `preview_theme_id`; auch der Link auf das Live-Theme trägt seine ID."""
    parsed = urlparse(base_url.rstrip("/") + (path or "/"))
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "preview_theme_id"]
    if theme_id:
        query.append(("preview_theme_id", numeric_id(theme_id)))
    return urlunparse(parsed._replace(query=urlencode(query)))


def link_pair(ctx: dict, path: str = "/") -> list:
    """Entwurf und Live, beide mit ihrer ID."""
    links = []
    if ctx.get("new_id"):
        label = "Neues Theme" if ctx["after"] else "Entwurf"
        links.append({"label": label, "url": preview_url(ctx["base_url"], path, ctx["new_id"])})
    if ctx.get("old_id"):
        label = "Altes Theme" if ctx["after"] else "Live"
        links.append({"label": label, "url": preview_url(ctx["base_url"], path, ctx["old_id"])})
    return links


def safe(fn, *args, **kwargs):
    """`(ergebnis, None)` oder `(None, grund)`; ein Fehler legt nie den ganzen Lauf."""
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001  ShopifyError, TranslationError, Netz, kaputte Antwort
        return None, f"{type(exc).__name__}: {exc}"[:300]


def http_fetch(url: str, timeout: int = 30) -> tuple:
    """Status, Header (klein geschrieben) und Text einer Adresse; Fehlerseiten liefern ihren Status."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, \
                response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, ""


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def newest(paths) -> Path | None:
    paths = [p for p in paths if p.is_file()]
    return max(paths, key=lambda p: (p.parent.name, p.stat().st_mtime)) if paths else None


def short_list(items: list, limit: int = 6) -> str:
    items = [str(i) for i in items]
    rest = len(items) - limit
    return ", ".join(items[:limit]) + (f" und {rest} weitere" if rest > 0 else "")


# ---------------------------------------------------------------------------
# HTML aus dem Mitschnitt
# ---------------------------------------------------------------------------

_TAG = re.compile(r"<(meta|link)\b([^>]*)>", re.I)
_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def head_tags(html: str) -> dict:
    """Meta-Robots und Canonical aus dem HTML; ohne Parser, nur die zwei Tags."""
    robots, canonical = [], None
    for match in _TAG.finditer(html or ""):
        attrs = {m.group(1).lower(): (m.group(2) or m.group(3) or m.group(4) or "")
                 for m in _ATTR.finditer(match.group(2))}
        if match.group(1).lower() == "meta" and attrs.get("name", "").lower() in ("robots", "googlebot"):
            robots.append(attrs.get("content", "").lower())
        if match.group(1).lower() == "link" and "canonical" in attrs.get("rel", "").lower().split():
            canonical = canonical or attrs.get("href")
    return {"noindex": any("noindex" in r for r in robots), "nofollow": any("nofollow" in r for r in robots),
            "canonical": canonical}


def canonical_path(url: str | None) -> str | None:
    """Pfad eines Canonicals ohne Vorschau-Parameter und ohne Schrägstrich am Ende."""
    if not url:
        return None
    parsed = urlparse(url)
    return (parsed.path.rstrip("/") or "/")


def robots_groups(body: str) -> dict:
    """Regeln je User-Agent aus einer robots.txt: `{agent: [(directive, value)]}`.

    Aufeinanderfolgende `User-agent`-Zeilen bilden eine Gruppe, die Regeln danach
    gelten für jede davon (RFC 9309). Ein `Disallow: /` gilt also nur für seine
    Gruppe; Shopify sperrt so etwa `Nutch`, ohne dass Google betroffen ist.
    """
    groups, agents, in_rules = {}, [], False
    for raw in (body or "").splitlines():
        key, sep, value = raw.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
            groups.setdefault(value.lower(), [])
        elif key in ("allow", "disallow") and agents:
            in_rules = True
            for agent in agents:
                groups[agent].append((key, value))
    return groups


def blocks_everything(rules: list) -> bool:
    """Sperrt eine Gruppe die ganze Seite: `Disallow: /` ohne `Allow: /` daneben."""
    roots = ("/", "/*")
    return any(k == "disallow" and v in roots for k, v in rules) and not any(k == "allow" and v in roots
                                                                          for k, v in rules)


def blocked_agents(body: str) -> tuple:
    """Maßgebliche und übrige Crawler, für die alles gesperrt ist.

    Googlebot folgt seiner eigenen Gruppe und ohne sie der Gruppe `*`.
    """
    groups = robots_groups(body)
    relevant = [a for a in ROBOTS_AGENTS if blocks_everything(groups.get(a, groups.get("*", [])))]
    others = sorted(a for a, rules in groups.items() if a not in ROBOTS_AGENTS and blocks_everything(rules))
    return relevant, others


def load_captures(paths: list) -> dict:
    """Mitschnitte je Seite: `{page_id: {"runs": [...], "path", "template"}}`, dazu Basis-URL und Modi."""
    pages, modes, problems = {}, set(), []
    for path in paths:
        data = read_json(path)
        if not isinstance(data, dict):
            problems.append(f"{path} nicht lesbar")
            continue
        mode = data.get("consent_mode") or "declined"
        modes.add(mode)
        for run in data.get("runs") or []:
            run = dict(run, consent=run.get("consent") or mode, _dir=str(Path(path).parent),
                       _base=data.get("base_url"), _captured_at=data.get("captured_at"))
            entry = pages.setdefault(run.get("page_id"), {"runs": [], "path": run.get("path"),
                                                          "template": run.get("template")})
            entry["runs"].append(run)
    return {"pages": pages, "modes": modes, "problems": problems, "files": [str(p) for p in paths]}


def primary_run(entry: dict) -> dict | None:
    """Der gültige erste Durchlauf, Desktop bevorzugt; der trägt das HTML."""
    runs = [r for r in entry["runs"] if r.get("state") == "ok"]
    runs.sort(key=lambda r: (r.get("run") != 1, r.get("device") != "desktop", r.get("consent") != "declined"))
    return runs[0] if runs else None


def run_html(run: dict) -> str | None:
    if not run.get("html_file"):
        return None
    try:
        return (Path(run["_dir"]) / run["html_file"]).read_text(encoding="utf-8")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Tracking: Hosts je Seite, alt gegen neu
# ---------------------------------------------------------------------------

def registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "ac", "gv"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def request_key(url: str, own_hosts: set, catalog, host_map: dict | None = None) -> str | None:
    """Dienst oder Domain einer Anfrage; None für die eigene Domain, Shopify und Ignoriertes.

    Nur die Shop-Domain selbst ist eigen. Eine Subdomain davon gehört oft einem
    Dienst, der sie per CNAME oder A-Eintrag als eigenen Endpunkt nutzt
    (Attribution, Server-Side-Tagging). Sie zählt über `host_map` aus der
    Bestandsaufnahme als dieser Dienst, sonst als eigener Host. Weggefiltert
    erschiene der Ausweich-Endpunkt desselben Dienstes fälschlich als neu.
    Unbekannte fremde Hosts zählen über ihre Domain, damit wechselnde
    Subdomains (Werbe-Auktionen, Lastverteiler) keine Scheinlücke erzeugen.
    """
    host = (urlparse(url or "").hostname or "").lower()
    if not host or host in own_hosts or catalog.ignored(host):
        return None
    sid = (host_map or {}).get(host) or catalog.service_for_url(url)
    if catalog.is_platform(sid):
        return None
    if sid:
        return sid
    return host if any(host.endswith("." + h) for h in own_hosts) else registrable(host)


def consent_result(run: dict) -> str | None:
    """Was der Cookie-Dialog im Durchlauf ergab: accepted, declined, no_dialog, stuck; None ohne Angabe."""
    return (run.get("consent_result") or {}).get("result")


def consent_counts(run: dict) -> bool:
    """Zählt ein Durchlauf im Vergleich seines Consent-Zustands?

    Ein Mitschnitt "mit Einwilligung", in dem der Dialog nicht erkannt oder nicht
    bedient wurde (`no_dialog`, `stuck`), misst den Zustand ohne Einwilligung. Am
    15.10.2026 so geschehen: der Pandectes-Dialog wurde nicht erkannt, und ein
    Vergleich hätte das als Tracking mit Einwilligung gezählt. Ohne Angabe (alte
    Mitschnitte) zählt er wie bisher.
    """
    return run.get("consent") != "accepted" or consent_result(run) in (None, "accepted")


def third_party_keys(runs: list, own_hosts: set, catalog, host_map: dict | None = None) -> set:
    """Dienste oder Domains, die eine Seite lädt, ohne eigene Domain und ohne Shopify selbst."""
    keys = {request_key(r.get("url") or "", own_hosts, catalog, host_map)
            for run in runs for r in run.get("requests") or []}
    return keys - {None}


def throttled_runs(capture: dict, side: str) -> list:
    """Durchläufe, die Shopify gedrosselt hat (HTTP 429, Warteseite): `home (mobile, neu)`.

    Sie zählen in keinem Vergleich (nur `state: ok` zählt) und stehen als nicht prüfbar im Beleg. Am
    11.11.2026 scheiterte im Test gegen den Live-Shop Horizons Nachladen an 429, und das sah aus wie ein
    Fehler des Shops.
    """
    return sorted({f"{r.get('page_id')} ({r.get('device')}, {side})" for e in capture["pages"].values()
                   for r in e["runs"] if r.get("state") == "throttled"})


def compare_tracking(old: dict, new: dict, own_hosts: set, catalog, host_map: dict | None = None) -> dict:
    """Je Seite und Consent-Zustand: was alt lädt und neu fehlt, was neu dazukommt."""
    result = {"missing": [], "added": [], "pages": 0, "wrong_theme": [], "unmatched": [], "unconfirmed": [],
              "throttled": throttled_runs(old, "alt") + throttled_runs(new, "neu")}
    for page_id, old_entry in sorted(old["pages"].items(), key=lambda kv: str(kv[0])):
        new_entry = new["pages"].get(page_id)
        if not new_entry:
            result["unmatched"].append(page_id)
            continue
        result["wrong_theme"] += [f"{page_id} ({r.get('device')})" for r in new_entry["runs"]
                                  if r.get("state") == "wrong_theme"]
        for mode in sorted({r.get("consent") for r in old_entry["runs"]} & {r.get("consent") for r in new_entry["runs"]}):
            old_runs = [r for r in old_entry["runs"] if r.get("consent") == mode and r.get("state") == "ok"]
            new_runs = [r for r in new_entry["runs"] if r.get("consent") == mode and r.get("state") == "ok"]
            if not (old_runs and new_runs):
                # Kein gültiger Durchlauf auf einer Seite (gedrosselt, falsches Theme, Fehler): ohne ihn fehlte im
                # Vergleich jeder Dienst. Der Grund steht unter throttled oder wrong_theme.
                continue
            # Ohne erteilte Einwilligung auf einer Seite fiele jeder Dienst nach der Einwilligung als fehlend auf.
            if any(r for r in old_runs + new_runs if not consent_counts(r)) and not (
                    any(consent_counts(r) for r in old_runs) and any(consent_counts(r) for r in new_runs)):
                result["unconfirmed"].append(f"{page_id} ({mode})")
                continue
            before = third_party_keys([r for r in old_runs if consent_counts(r)], own_hosts, catalog, host_map)
            after = third_party_keys([r for r in new_runs if consent_counts(r)], own_hosts, catalog, host_map)
            result["pages"] += 1
            for key in sorted(before - after):
                result["missing"].append({"page_id": page_id, "path": old_entry.get("path"), "consent": mode,
                                          "service": key, "name": catalog.describe(key)["service_name"]})
            for key in sorted(after - before):
                result["added"].append({"page_id": page_id, "consent": mode, "service": key})
    return result


def page_number(url: str | None) -> int:
    """Wert von `page` in einer Adresse, 1 ohne den Parameter."""
    for key, value in parse_qsl(urlparse(url or "").query):
        if key == "page" and value.isdigit():
            return int(value)
    return 1


def event_counts(run: dict, own_hosts: set, catalog, host_map: dict | None = None) -> dict:
    """Anfragen je Analysedienst in einem Durchlauf.

    Eine nicht zugeordnete eigene Subdomain zählt mit: meist ist sie der
    Sammelendpunkt eines Attributions- oder Server-Side-Dienstes.
    """
    counts = {}
    for request in run.get("requests") or []:
        key = request_key(request.get("url") or "", own_hosts, catalog, host_map)
        if not key:
            continue
        own_subdomain = any(key.endswith("." + h) for h in own_hosts)
        if own_subdomain or catalog.describe(key)["category"] in EVENT_CATEGORIES:
            counts[key] = counts.get(key, 0) + 1
    return counts


def compare_pagination(old: dict, new: dict, own_hosts: set, catalog, host_map: dict | None = None) -> list:
    """Je Seite und Gerät: schreibt das neue Theme beim Scrollen Seiten in die Adresse, sendet es mehr Ereignisse?

    Der Mitschnitt scrollt jede Seite bis zum Ende. Lädt ein Theme dabei nach und
    schreibt `page=N` in die Adresse, steht das in `final_url`; jede so
    geschriebene Seite kann in GA4 und anderen Werkzeugen als eigener
    Seitenaufruf oder eigene Suche zählen. Verglichen wird vorsichtig: das
    Minimum der neuen Durchläufe gegen das Maximum der alten, damit Schwankung
    zwischen zwei Durchläufen (Werbe-Auktionen, Ladezeit) keinen Befund erzeugt.
    """
    rows = []
    for page_id, old_entry in sorted(old["pages"].items(), key=lambda kv: str(kv[0])):
        new_entry = new["pages"].get(page_id)
        if not new_entry:
            continue
        start = page_number(old_entry.get("path"))
        for device in sorted({r.get("device") for r in old_entry["runs"]} | {r.get("device") for r in new_entry["runs"]},
                             key=str):
            old_runs = [r for r in old_entry["runs"] if r.get("device") == device and r.get("state") == "ok"]
            new_runs = [r for r in new_entry["runs"] if r.get("device") == device and r.get("state") == "ok"]
            if not (old_runs and new_runs):
                continue
            old_page = max(page_number(r.get("final_url")) for r in old_runs)
            new_page = max(page_number(r.get("final_url")) for r in new_runs)
            old_counts = [event_counts(r, own_hosts, catalog, host_map) for r in old_runs]
            new_counts = [event_counts(r, own_hosts, catalog, host_map) for r in new_runs]
            inflated = []
            for key in sorted({k for c in old_counts for k in c}):
                before = max(c.get(key, 0) for c in old_counts)
                after = min(c.get(key, 0) for c in new_counts)
                if after >= before * EVENT_FACTOR and after - before >= EVENT_MIN_DELTA:
                    inflated.append({"service": key, "name": catalog.describe(key)["service_name"],
                                     "old": before, "new": after})
            rows.append({"page_id": page_id, "template": old_entry.get("template") or page_id,
                         "path": old_entry.get("path"), "device": device, "start_page": start,
                         "old_page": old_page, "new_page": new_page, "inflated": inflated})
    return rows


# ---------------------------------------------------------------------------
# Entscheidungen aus der Bestandsaufnahme
# ---------------------------------------------------------------------------

def subject_keys(subject: str, catalog) -> set:
    """Schlüssel, unter denen ein Eintrag der Entscheidungsliste einen Dienst trifft.

    Ein Gegenstand kann Dienst-ID, Name, App-Handle oder Host sein; jeder wird
    über den Host-Katalog auf die Dienst-ID geführt, mit der Tracking und Embeds
    rechnen.
    """
    text = str(subject or "").strip()
    lowered = text.lower()
    if not lowered:
        return set()
    keys = {lowered}
    looks_like_host = "." in lowered and " " not in lowered and "/" not in lowered
    sid = lowered if lowered in catalog.services else None
    if looks_like_host:
        sid = sid or catalog.service_for(lowered)
        # Die Domain nur für unbekannte Hosts: ajax.googleapis.com darf nicht alles unter googleapis.com streichen.
        if not sid:
            keys.add(registrable(lowered))
    sid = sid or catalog.service_for_name(text) or catalog.service_for_handle(lowered)
    if sid:
        keys.add(sid)
    return keys


def load_decisions(workspace: Path, catalog) -> tuple:
    """Bewusst entfallene Dienste und die Zuordnung eigener Subdomains, aus der Bestandsaufnahme.

    Quellen: `migration/inventory/apps.json` (Zeilen mit `decision`) und
    `migration/mapping/decisions.json` (Einträge der Art `app`, angehängt, der
    jüngste gilt). Liefert `({schlüssel: beleg}, {host: dienst})`; der Beleg
    nennt Gegenstand, Entscheidung, Person und Grund.
    """
    dropped, host_map = {}, {}
    data = read_json(workspace / "migration" / "inventory" / "apps.json") or {}
    rows = data.get("integrations") if isinstance(data, dict) else data
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("service_id") or "")
        hosts = [str(h).lower() for h in row.get("hosts") or []]
        if sid and not sid.startswith("unknown:"):
            for host in hosts:
                host_map[host] = sid
        if row.get("decision") not in DROPPED_DECISIONS:
            continue
        label = (f"{row.get('service_name') or row.get('app_handle') or sid}: {row['decision']} laut apps.json"
                 + (f", {row['decided_by']}" if row.get("decided_by") else ""))
        keys = {k for k in (sid, str(row.get("app_handle") or "").lower()) if k} | set(hosts)
        keys |= {registrable(h) for h in hosts if not catalog.service_for(h)}
        for key in keys:
            dropped[key] = label
    data = read_json(workspace / "migration" / "mapping" / "decisions.json")
    entries = data.get("decisions") if isinstance(data, dict) else data
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("kind") not in (None, "", "app"):
            continue
        keys = subject_keys(entry.get("subject"), catalog)
        if entry.get("decision") not in DROPPED_DECISIONS:
            for key in keys:
                dropped.pop(key, None)
            continue
        label = (f"{entry.get('subject')}: {entry['decision']} laut decisions.json"
                 + (f", {entry['decided_by']}" if entry.get("decided_by") else "")
                 + (f" am {str(entry['decided_at'])[:10]}" if entry.get("decided_at") else "")
                 + (f" ({entry['reason']})" if entry.get("reason") else ""))
        for key in keys:
            dropped[key] = label
    return dropped, host_map


def dropped_reason(ctx: dict, *keys) -> str | None:
    """Beleg der Entscheidung, wenn einer der Schlüssel als bewusst entfallen gilt."""
    for key in keys:
        if key and str(key).lower() in ctx["dropped"]:
            return ctx["dropped"][str(key).lower()]
    return None


# ---------------------------------------------------------------------------
# Kontext
# ---------------------------------------------------------------------------

def build_context(args, config: dict, workspace: Path, *, transport=None) -> dict:
    block = migration_config(config)
    state, state_error = None, None
    run_id = run_state.latest_run_id(workspace)
    if run_id:
        try:
            state = run_state.load(workspace, run_id).data
        except run_state.StateError as exc:
            state_error = str(exc)
    values = (state or {}).get("values") or {}
    live_id = args.live_theme_id or values.get("live_theme_id") or block.get("live_theme_id")
    draft_id = args.draft_theme_id or values.get("draft_theme_id") or block.get("draft_theme_id")
    if args.after and not args.live_theme_id and values.get("rollback_theme_id"):
        # Nach dem geführten Launch (`theme.launch publish`) zeigt live_theme_id auf das neue Theme, und das
        # alte steht als rollback_theme_id im Stand. Bis dahin musste die alte ID von Hand übergeben werden.
        live_id = values["rollback_theme_id"]
        draft_id = args.draft_theme_id or values.get("live_theme_id") or draft_id
    # Seit 0.3.11 kein Änderungsstopp mehr: den Termin nennt der Betreiber beim Aufruf.
    launch = args.launch_date
    launch_date = None
    if launch:
        try:
            launch_date = date.fromisoformat(str(launch)[:10])
        except ValueError:
            raise ConfigError(f"Launch-Datum nicht lesbar: {launch!r}, erwartet JJJJ-MM-TT")
    domain = config.get("domain") or (f"https://{config['shopify_store']}" if config.get("shopify_store") else "")
    if domain and "://" not in domain:
        domain = "https://" + domain
    transport_error = None
    if transport is None:
        try:
            transport = transport_from_config(config, workspace=workspace)
        except ShopifyError as exc:
            transport_error = str(exc)
    suffix = "-after" if args.after else ""
    run_dir = workspace / "reporting" / "runs" / (args.run_id or f"{date.today().isoformat()}-launch-check")
    capture = run_dir / "capture"
    # Nach dem Launch ist "neu" der Mitschnitt des veröffentlichten Themes (capture/after-*), nicht der Entwurf.
    new_glob = "after-*/network.json" if args.after else "new-*/network.json"
    network_old = [Path(p) for p in args.network_old] or sorted(capture.glob("old-*/network.json"))
    network_new = [Path(p) for p in args.network_new] or sorted(capture.glob(new_glob))
    pages_file = next((p for p in [Path(args.pages) if args.pages else None, run_dir / "pages.json",
                                   workspace / "migration" / "inventory" / "pages.json"] if p and p.is_file()), None)
    answers_file = Path(args.answers) if args.answers else workspace / "reporting" / "launch-answers.json"
    answers = (read_json(answers_file) or {}).get("answers") or {} if answers_file.is_file() else {}
    catalog = apps.HostCatalog.load()
    dropped, host_map = load_decisions(workspace, catalog)
    # Vor dem Launch ist das alte Theme das Live-Theme und das neue der Entwurf; danach dieselben zwei.
    return {
        "workspace": workspace, "config": config, "after": args.after, "base_url": domain.rstrip("/"),
        "store": config.get("shopify_store", ""), "old_id": live_id and numeric_id(live_id),
        "new_id": draft_id and numeric_id(draft_id), "launch_date": launch_date, "today": date.today(),
        "state": state, "state_run_id": run_id, "state_error": state_error, "transport": transport,
        "transport_error": transport_error, "run_dir": run_dir, "suffix": suffix,
        "old": load_captures(network_old), "new": load_captures(network_new),
        "pages_file": pages_file, "answers": answers, "answers_file": str(answers_file),
        "catalog": catalog, "dropped": dropped, "host_map": host_map, "cache": {},
        "report_paths": [str(p) for p in block.get("report_paths") or [] if str(p).strip()],
        "checklist": block.get("acceptance_checklist") or None,
        "open_items": open_items.exists(workspace),
        "test_order_arg": getattr(args, "test_order", None),
        # Erst bei Bedarf gelesen (nur --after mit Testbestellung); hier nur der Zugang, kein Abruf.
        "ga4": (None, "nur nach dem Launch gelesen") if not args.after else test_order.ga4_from_config(config, workspace),
    }


def shop(ctx: dict, key: str, fn, *args):
    """Eine Shopify-Abfrage je Lauf, gecacht; ohne Zugang der Grund statt des Werts."""
    if key not in ctx["cache"]:
        if ctx["transport"] is None:
            ctx["cache"][key] = (None, f"kein Shopify-Zugang: {ctx['transport_error']}")
        else:
            ctx["cache"][key] = safe(fn, ctx["transport"], *args)
    return ctx["cache"][key]


def themes_by_id(ctx: dict) -> tuple:
    themes, error = shop(ctx, "themes", list_themes)
    return ({numeric_id(t["id"]): t for t in themes} if themes else None), error


def file_names(ctx: dict, theme_id) -> tuple:
    files, error = shop(ctx, f"files-{theme_id}", list_files, theme_id)
    return ({f["filename"] for f in files} if files is not None else None), error


def file_body(ctx: dict, theme_id, name: str) -> tuple:
    bodies, error = shop(ctx, f"body-{theme_id}-{name}", fetch_by_names, theme_id, [name])
    return (None if bodies is None else bodies.get(name)), error


def own_hosts(ctx: dict) -> set:
    hosts = {(urlparse(ctx["base_url"]).hostname or "").lower(), ctx["store"].lower()}
    for capture in (ctx["old"], ctx["new"]):
        for entry in capture["pages"].values():
            for run in entry["runs"]:
                hosts.add((urlparse(run.get("_base") or "").hostname or "").lower())
    hosts |= {"www." + h for h in hosts if h and not h.startswith("www.")}
    return {h for h in hosts if h}


def page_list(ctx: dict) -> list:
    """Seiten für Abrufe und Links: pages.json, sonst die Seiten des Mitschnitts, sonst die Startseite."""
    data = read_json(ctx["pages_file"]) if ctx["pages_file"] else None
    if isinstance(data, dict) and data.get("pages"):
        return [{"id": p.get("id"), "path": p.get("path") or "/", "template": p.get("template")}
                for p in data["pages"] if isinstance(p, dict)]
    captured = ctx["old"]["pages"] or ctx["new"]["pages"]
    if captured:
        return [{"id": k, "path": v.get("path") or "/", "template": v.get("template")} for k, v in captured.items()]
    return [{"id": "home", "path": "/", "template": "index"}]


# ---------------------------------------------------------------------------
# Prüfungen vor dem Launch
# ---------------------------------------------------------------------------

def check_timing(ctx: dict) -> list:
    group = "Zeitpunkt"
    out = []
    day = ctx["launch_date"]
    if not day:
        out.append(make_check("timing-date", group, "Launch-Termin", MANUAL,
                              "kein Termin bekannt (--launch-date)",
                              question="An welchem Tag und zu welcher Uhrzeit wird veröffentlicht?", owner=BOTH))
    else:
        names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        weekday = names[day.weekday()]
        out.append(make_check(
            "timing-weekday", group, "Wochentag", OK if day.weekday() <= 3 else MISSING,
            f"{day.strftime('%d.%m.%Y')} ist ein {weekday}",
            action="" if day.weekday() <= 3 else "auf Montag bis Donnerstag legen, bei wenig Traffic",
            owner="" if day.weekday() <= 3 else BOTH))
        holidays = {**german_holidays(day.year), **german_holidays(day.year + 1)}
        hits = [f"{holidays[d]} am {d.strftime('%d.%m.')}" for d in (day, day + timedelta(days=1)) if d in holidays]
        out.append(make_check(
            "timing-holiday", group, "Feiertag", MISSING if hits else OK,
            ("; ".join(hits) if hits else "kein bundesweiter Feiertag am Tag und am Folgetag")
            + "; regionale Feiertage und andere Länder nicht geprüft",
            action="nicht am Tag vor einem Feiertag veröffentlichen" if hits else "", owner=BOTH if hits else ""))
        start, end = season_window(day.year)
        in_season = start <= day <= end
        out.append(make_check(
            "timing-season", group, "Saisonspitze", MISSING if in_season else OK,
            f"Saisonfenster {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')} "
            f"(vier Wochen vor Black Friday am {black_friday(day.year).strftime('%d.%m.')})"
            + (", der Termin liegt darin" if in_season else ", der Termin liegt davor oder danach"),
            action="nach der Saison veröffentlichen oder ausdrücklich mit dem Team entscheiden" if in_season else "",
            owner=BOTH if in_season else ""))
    out.append(make_check("timing-campaigns", group, "Kampagnen", MANUAL,
                          "nicht automatisch prüfbar",
                          question="Laufen um den Termin große Kampagnen, ein Sale oder ein Newsletter mit viel Traffic?",
                          owner=TEAM))
    tests = sorted({ctx["catalog"].describe(k)["service_name"]
                    for entry in ctx["old"]["pages"].values()
                    for k in third_party_keys(entry["runs"], own_hosts(ctx), ctx["catalog"], ctx["host_map"])
                    if ctx["catalog"].describe(k)["category"] == "ab_testing"})
    out.append(make_check("timing-tests", group, "Preis- und A/B-Tests", MANUAL,
                          ("im Mitschnitt des Live-Themes geladen: " + ", ".join(tests)) if tests
                          else ("im Mitschnitt kein Testwerkzeug gesehen" if ctx["old"]["pages"]
                                else "kein Mitschnitt des Live-Themes") + "; laufende Tests zeigt nur das Werkzeug selbst",
                          question="Läuft am Termin ein Preis- oder A/B-Test? Dann vorher beenden oder pausieren.",
                          owner=TEAM))
    out.append(make_check("timing-contacts", group, "Ansprechpartner", MANUAL, "nicht automatisch prüfbar",
                          question="Sind am Launch-Tag auf beiden Seiten Ansprechpartner erreichbar, die entscheiden dürfen?",
                          owner=BOTH))
    return out


def latest_verify_findings(workspace: Path):
    path = newest((workspace / "migration" / "verify").glob("*/findings.json"))
    data = read_json(path) if path else None
    if isinstance(data, dict):
        data = data.get("findings")
    return path, data if isinstance(data, list) else None


def check_findings(ctx: dict) -> dict:
    """Offene Punkte aus allen Prüfberichten: im Workspace und unter `theme_migration.report_paths`.

    Nie eine Frage: ein offener Punkt ist `missing`, kein auffindbarer Bericht
    `blocked`. Am 07.10.2026 stand hier die Frage, ob alles erledigt sei, und der
    Bericht mit den offenen Punkten lag außerhalb des Workspace.
    """
    group, title = "Abnahme und offene Befunde", "Befunde aus der Prüfung"
    workspace = ctx["workspace"]
    sources, unreadable = [], []
    path, _ = latest_verify_findings(workspace)
    if path:
        sources.append(path)
    files, unresolved = launch_findings.report_files(ctx["report_paths"], workspace, ctx["config"])
    sources += [f for f in files if f not in sources]
    items, reports = [], []
    for source in sources:
        found = launch_findings.read_report(source)
        if found is None:
            unreadable.append(source.name)
        elif launch_findings.is_report(source, found):
            reports.append(source.name)
            items += found
    gaps = ([f"nicht gefunden: {', '.join(unresolved)}"] if unresolved else []) \
        + ([f"nicht lesbar: {', '.join(unreadable)}"] if unreadable else [])
    if not reports:
        where = "nichts unter migration/verify/*/findings.json"
        where += (", theme_migration.report_paths: " + ", ".join(ctx["report_paths"]) if ctx["report_paths"]
                  else ", theme_migration.report_paths nicht gesetzt")
        if files:
            where += f"; {len(files)} Dateien gelesen, keine mit einem Abschnitt Vor dem Launch oder Blocker"
        return make_check("acceptance-findings", group, title, BLOCKED,
                          "kein Prüfbericht gefunden: " + where + ("; " + "; ".join(gaps) if gaps else ""),
                          action="verify-theme laufen lassen oder theme_migration.report_paths auf den Ordner des "
                                 "Prüfberichts setzen (etwa {drive_path}/projects/<projekt>)", owner=OPERATOR)
    open_items = [i for i in items if i["state"] == "open"]
    deferred = [i for i in items if i["state"] == "deferred"]
    done = [i for i in items if i["state"] == "done"]
    evidence = f"{len(reports)} Berichte ({short_list(reports, 4)}), {len(items)} Punkte vor dem Launch"
    if open_items:
        evidence += f"; {len(open_items)} offen: " + short_list([f"{i['source']}, {i['section']}: {i['label']}"
                                                                 for i in open_items], 8)
    evidence += f"; {len(done)} erledigt"
    if deferred:
        evidence += "; verschoben: " + short_list([f"{i['label'][:60]} (von {i['deferral']['by']} am "
                                                   f"{i['deferral']['at']})" for i in deferred], 6)
    if gaps:
        evidence += "; " + "; ".join(gaps)
    status = MISSING if open_items else (BLOCKED if gaps else OK)
    action = ("jeden Punkt beheben und im Bericht als erledigt markieren oder mit Person und Datum verschieben "
              "(verschoben von <Name> am <JJJJ-MM-TT>)" if open_items
              else "Pfad prüfen, ob der Ordner eingebunden ist" if gaps else "")
    check = make_check("acceptance-findings", group, title, status, evidence, action=action,
                       owner=OPERATOR if status != OK else "")
    check["details"] = {"open": open_items, "deferred": deferred, "reports": reports}
    return check


def check_checklist(ctx: dict, statuses: dict) -> dict:
    """Die Prüfliste "Muss nach dem Umbau wieder da sein" aus Phase 2 als Abnahme.

    Jeder Punkt ist abgehakt, mit Person und Datum verschoben oder durch eine
    bestandene automatische Prüfung dieses Laufs abgedeckt; sonst `missing`.
    """
    group, title = "Abnahme und offene Befunde", "Prüfliste aus der Bestandsaufnahme"
    raw = ctx["checklist"]
    if not raw:
        if ctx["state"]:
            return make_check("acceptance-checklist", group, title, BLOCKED,
                              "keine Prüfliste konfiguriert (theme_migration.acceptance_checklist), obwohl ein "
                              "Migrationslauf besteht",
                              action="Pfad der Prüfliste aus Phase 2 (Zeilen - [ ] **P01** ...) eintragen",
                              owner=OPERATOR)
        return make_check("acceptance-checklist", group, title, NA,
                          "ohne Migrationslauf und ohne theme_migration.acceptance_checklist")
    path = Path(launch_findings.resolve_path(raw, ctx["workspace"], ctx["config"]))
    try:
        items = launch_findings.parse_checklist(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return make_check("acceptance-checklist", group, title, BLOCKED, f"{raw} nicht lesbar ({type(exc).__name__})",
                          action="Pfad prüfen, ob der Ordner eingebunden ist", owner=OPERATOR)
    if not items:
        return make_check("acceptance-checklist", group, title, BLOCKED,
                          f"{path.name}: keine Punkte der Form - [ ] **P01** gefunden", owner=OPERATOR)
    result = launch_findings.evaluate_checklist(items, statuses)
    evidence = (f"{path.name}: {len(items)} Punkte, {len(result['done'])} abgehakt, "
                f"{len(result['covered'])} automatisch abgedeckt, {len(result['deferred'])} verschoben, "
                f"{len(result['open'])} offen")
    if result["open"]:
        evidence += "; offen: " + short_list(
            [i["id"] + (f" ({', '.join(i['failing'])} nicht bestanden)" if i["failing"] else "")
             for i in result["open"]], 12)
    if result["covered"]:
        evidence += "; abgedeckt: " + short_list([f"{i['id']} ({', '.join(i['checks'])})" for i in result["covered"]], 8)
    if result["deferred"]:
        evidence += "; verschoben: " + short_list([f"{i['id']} (von {i['deferral']['by']} am {i['deferral']['at']})"
                                                   for i in result["deferred"]], 6)
    status = MISSING if result["open"] else OK
    check = make_check("acceptance-checklist", group, title, status, evidence,
                       action="jeden offenen Punkt prüfen und abhaken oder mit Person und Datum verschieben"
                       if result["open"] else "", owner=OPERATOR if result["open"] else "")
    check["details"] = result
    return check


def latest_test_round(workspace: Path):
    path = newest((workspace / "reporting" / "runs").glob("*-test/test.json"))
    return path, read_json(path) if path else None


def check_open_items(ctx: dict, statuses: dict) -> dict:
    """Die eine Liste offener Punkte: jeder offene Punkt der Gates G4 und G5 ist `missing`.

    Eine Prüfung dieses Laufs schließt keinen Punkt still: deckt sie ihn ab, steht das im Beleg,
    und `open_items close-covered` schreibt es mit Beleg in die Liste. Sonst führte der Launch-Check
    einen zweiten Stand neben der Liste.
    """
    group, title = "Abnahme und offene Befunde", "Offene Punkte (migration/open-items.json)"
    if not ctx["open_items"]:
        return make_check("acceptance-open-items", group, title, BLOCKED,
                          "keine Liste offener Punkte, obwohl ein Migrationslauf besteht",
                          action="python3 -m theme.open_items init, dann jede Quelle importieren "
                                 "(open_items import, theme-migration Phase 2)", owner=OPERATOR)
    try:
        items = open_items.load(ctx["workspace"])
    except open_items.OpenItemsError as exc:
        return make_check("acceptance-open-items", group, title, BLOCKED, str(exc)[:300],
                          action="Liste reparieren, nicht neu anlegen", owner=OPERATOR)
    blocking = items.blocking("G5-go-live")
    deferred = [i for i in items.items if i["status"] == "deferred" and i["gate"] != "after_launch"]
    counts = items.counts()
    evidence = (f"{len(items.items)} Punkte, {counts['open']} offen ({len(blocking)} vor dem Launch), "
                f"{counts['done']} erledigt, {counts['deferred']} verschoben")
    if blocking:
        evidence += "; offen: " + short_list([f"{i['id']} {i['title'][:60]} ({i['gate']})" for i in blocking], 10)
        covered = [f"{i['id']} ({', '.join(c)})" for i in blocking
                   for c in [launch_findings.checks_for(f"{i['title']} {i.get('description', '')}")]
                   if c and all(statuses.get(x) == OK for x in c)]
        if covered:
            evidence += ("; durch bestandene Prüfungen dieses Laufs abgedeckt, in der Liste noch offen: "
                         + short_list(covered, 8))
    if deferred:
        evidence += "; verschoben: " + short_list([f"{i['id']} (von {i['deferred_by']} am {i['deferred_at']})"
                                                   for i in deferred], 6)
    action = ("jeden Punkt beheben und mit Beleg erledigen (open_items done --id <id> --evidence <text>) oder mit "
              "Person und Datum verschieben (open_items defer); abgedeckte Punkte: open_items close-covered "
              "--launch-check <launch-check.json>") if blocking else ""
    check = make_check("acceptance-open-items", group, title, MISSING if blocking else OK, evidence,
                       action=action, owner=OPERATOR if blocking else "")
    check["details"] = {"open": [open_items.brief(i) for i in blocking],
                        "deferred": [open_items.brief(i) for i in deferred]}
    return check


def check_open_item_sources(ctx: dict) -> dict:
    """Was in einem Prüfbericht, der Prüfliste, `findings.json` oder der Abnahme offen steht und in
    der Liste fehlt. So geht nichts still verloren, das jemand an anderer Stelle festgehalten hat.
    """
    group, title = "Abnahme und offene Befunde", "Quellen in der Liste übernommen"
    items = None
    if ctx["open_items"]:
        try:
            items = open_items.load(ctx["workspace"])
        except open_items.OpenItemsError:
            items = None
    result = open_items.source_gaps(items, ctx["workspace"], ctx["config"], migration=bool(ctx["state"]))
    missing, gaps = result["missing"], result["gaps"]
    evidence = (f"{len(result['sources'])} Quellen gelesen ({short_list(result['sources'], 5)})"
                if result["sources"] else "keine Quelle gefunden")
    if missing:
        evidence += f"; {len(missing)} offen und nicht in der Liste: " + short_list(
            [f"{m['source']}: {m['id']} {m['title'][:50]}" for m in missing], 8)
    if gaps:
        evidence += "; " + "; ".join(gaps)
    status = MISSING if missing else (BLOCKED if gaps else OK)
    action = ("jede Quelle übernehmen: open_items import --kind <checklist|report|findings|test-round> --path "
              "<datei>" if missing else "Pfad prüfen oder in theme_migration der Config eintragen" if gaps else "")
    check = make_check("acceptance-sources", group, title, status, evidence, action=action,
                       owner=OPERATOR if status != OK else "")
    check["details"] = result
    return check


def ledger_mode(ctx: dict) -> bool:
    """Die Liste ist die Quelle, sobald es sie gibt oder ein Migrationslauf besteht."""
    return bool(ctx["open_items"] or ctx["state"])


def check_acceptance(ctx: dict, statuses: dict | None = None) -> list:
    group = "Abnahme und offene Befunde"
    out = []
    state = ctx["state"]
    if state:
        gate = (state.get("gates") or {}).get("G4-acceptance")
        out.append(make_check(
            "acceptance-decision", group, "Abnahme (G4)", OK if gate else MISSING,
            f"entschieden von {gate['decided_by']} am {gate['decided_at'][:10]}" if gate
            else f"Gate G4 im Migrationslauf {ctx['state_run_id']} offen",
            action="" if gate else "Abnahme abschließen und G4 mit dem Team entscheiden", owner="" if gate else TEAM))
    else:
        out.append(make_check("acceptance-decision", group, "Abnahme", MANUAL,
                              "kein Migrationslauf im Workspace" + (f" ({ctx['state_error']})" if ctx["state_error"] else ""),
                              question="Hat das Team den Entwurf abgenommen? Wer, an welchem Tag?", owner=TEAM))
    if ledger_mode(ctx):
        return out + [check_open_items(ctx, statuses or {}), check_open_item_sources(ctx)]
    out.append(check_findings(ctx))
    path, test = latest_test_round(ctx["workspace"])
    if not isinstance(test, dict):
        out.append(make_check("acceptance-test-round", group, "Testpunkte der Abnahme", NA,
                              "keine Abnahme unter reporting/runs/*-test/"))
    else:
        items = [i for g in test.get("groups") or [] for i in g.get("items") or [] if isinstance(i, dict)]
        open_items = [i for i in items if i.get("status") in OPEN_TEST_STATUS]
        decisions = [i for i in open_items if i.get("status") == "decision"]
        owner = BOTH if decisions and len(decisions) < len(open_items) else (TEAM if decisions else OPERATOR)
        out.append(make_check(
            "acceptance-test-round", group, "Testpunkte der Abnahme", MISSING if open_items else OK,
            (f"{len(open_items)} von {len(items)} Punkten offen in {path.parent.name}: "
             + short_list([f"{i.get('id')} {i.get('title')} ({i.get('status')})" for i in open_items], 8))
            if open_items else f"alle Punkte mit Status erledigt in {path.parent.name}",
            action="Entscheidungen im nächsten Termin einholen, offene Punkte umsetzen" if open_items else "",
            owner=owner if open_items else "",
            links=[test["preview"]] if isinstance(test.get("preview"), dict) else []))
    return out


def last_sync_reference(ctx: dict) -> dict | None:
    """Jüngster festgehaltener Stand des Live-Themes: Abgleich oder Sicherung (dieselbe Quelle wie die
    Schlussprüfung in `theme.sync`)."""
    return sync.latest_reference(ctx["workspace"], ctx["old_id"])


def check_sync(ctx: dict) -> list:
    group = "Abgleich mit dem Live-Stand"
    out = []
    themes, error = themes_by_id(ctx)
    if themes is None:
        out.append(make_check("live-sync", group, "Live-Theme seit dem letzten Abgleich", BLOCKED,
                              f"Theme-Liste nicht lesbar: {error}", owner=OPERATOR))
    else:
        main = next((t for t in themes.values() if t.get("role") == "MAIN"), None)
        main_id = numeric_id(main["id"]) if main else None
        reference = last_sync_reference(ctx)
        if ctx["old_id"] and main_id != ctx["old_id"]:
            status, evidence = MISSING, f"live ist {main_id} ({main and main.get('name')}), erwartet {ctx['old_id']}"
            action = "klären, wer das Live-Theme gewechselt hat; IDs neu setzen"
        elif not reference:
            status = MISSING
            evidence = (f"Live-Theme {main_id} zuletzt geändert {main and main.get('updatedAt')}; "
                        "kein Abgleich und keine Sicherung unter migration/ im Workspace")
            action = "sync-live-theme laufen lassen (Abgleich II), bei Bedarf vorher snapshot-theme"
        elif reference["updated_at"] != main.get("updatedAt"):
            status = MISSING
            evidence = (f"Live-Theme geändert am {main.get('updatedAt')}, letzter Stand {reference['updated_at']} "
                        f"aus {reference['source'].relative_to(ctx['workspace']).as_posix()}")
            action = "sync-live-theme laufen lassen und jede Änderung entscheiden"
        else:
            status, action = OK, ""
            evidence = (f"Live-Theme unverändert seit {reference['captured_at']} "
                        f"({reference['source'].relative_to(ctx['workspace']).as_posix()})")
        last = ((ctx["state"] or {}).get("values") or {}).get("last_sync")
        if last:
            evidence += f"; letzter Abgleich laut Migrationslauf {last}"
        out.append(make_check("live-sync", group, "Live-Theme seit dem letzten Abgleich", status, evidence,
                              action=action, owner=OPERATOR if status != OK else "", links=link_pair(ctx)))
    # Seit 0.3.11 gibt es keinen Änderungsstopp: das Team arbeitet am Live-Theme weiter, und direkt vor dem
    # Launch wird der Stand neu gezogen. Geprüft wird deshalb, wie frisch der letzte Abgleich ist.
    values = (ctx["state"] or {}).get("values") or {}
    last = values.get("last_sync")
    try:
        age = (date.today() - date.fromisoformat(str(last)[:10])).days if last else None
    except ValueError:
        age = None
    if age is None:
        out.append(make_check("sync-fresh", group, "Abgleich vor dem Launch", MISSING,
                              "kein Abgleich im Migrationslauf festgehalten",
                              action="sync-live-theme direkt vor dem Launch laufen lassen", owner=OPERATOR))
    else:
        out.append(make_check("sync-fresh", group, "Abgleich vor dem Launch", OK if age <= 7 else MISSING,
                              f"letzter Abgleich {last}, vor {age} Tagen",
                              action="" if age <= 7 else "sync-live-theme direkt vor dem Launch erneut laufen lassen",
                              owner="" if age <= 7 else OPERATOR))
    return out


def check_draft(ctx: dict) -> list:
    group = "Entwurf und Rückfall"
    themes, error = themes_by_id(ctx)
    out = []
    if not ctx["new_id"]:
        out.append(make_check("draft-theme", group, "Entwurf", BLOCKED, "keine Entwurfs-ID bekannt",
                              action="--draft-theme-id setzen oder draft_theme_id in der Config", owner=OPERATOR))
    elif themes is None:
        out.append(make_check("draft-theme", group, "Entwurf", BLOCKED, f"Theme-Liste nicht lesbar: {error}"))
    else:
        theme = themes.get(ctx["new_id"])
        problems = []
        if not theme:
            problems.append(f"Theme {ctx['new_id']} gibt es im Store nicht")
        else:
            if theme.get("role") != "UNPUBLISHED":
                problems.append(f"Rolle {theme.get('role')}, erwartet UNPUBLISHED")
            if theme.get("processing") or theme.get("processingFailed"):
                problems.append("Shopify verarbeitet das Theme noch oder die Verarbeitung ist gescheitert")
        out.append(make_check(
            "draft-theme", group, "Entwurf", MISSING if problems else OK,
            "; ".join(problems) if problems else
            f"{ctx['new_id']} \"{theme.get('name')}\", Rolle UNPUBLISHED, zuletzt geändert {theme.get('updatedAt')}",
            action="Entwurfs-ID prüfen" if problems else "", owner=OPERATOR if problems else "",
            links=link_pair(ctx)))
    out.append(rollback_check(ctx, themes, error, group))
    return out


def rollback_check(ctx: dict, themes, error, group: str) -> dict:
    title = "Rückfall-Theme"
    if not ctx["old_id"]:
        return make_check("rollback-theme", group, title, BLOCKED, "keine Live-Theme-ID bekannt",
                          action="--live-theme-id setzen oder live_theme_id in der Config", owner=OPERATOR)
    if themes is None:
        return make_check("rollback-theme", group, title, BLOCKED, f"Theme-Liste nicht lesbar: {error}")
    if ctx["after"] and ctx["old_id"] == ctx["new_id"]:
        # Nach dem Launch zeigt live_theme_id im Migrationslauf schon auf das neue Theme.
        return make_check("rollback-theme", group, title, BLOCKED,
                          "die Live-Theme-ID zeigt schon auf das neue Theme; die alte ist nicht bekannt",
                          action="--live-theme-id mit der ID des alten Themes setzen (Notiz zu G5)", owner=OPERATOR)
    theme = themes.get(ctx["old_id"])
    expected = "UNPUBLISHED" if ctx["after"] else "MAIN"
    if not theme or theme.get("role") != expected:
        found = f"Rolle {theme.get('role')}" if theme else "nicht im Store"
        return make_check("rollback-theme", group, title, MISSING, f"Theme {ctx['old_id']}: {found}, erwartet {expected}",
                          action="klären, wo das alte Theme ist; nie löschen", owner=OPERATOR)
    return make_check("rollback-theme", group, title, OK,
                      f"Rückfall-Theme {ctx['old_id']} \"{theme.get('name')}\", Rolle {expected}; bleibt in der "
                      "Theme-Bibliothek und wird erst nach der Stabilisierung mit Freigabe gelöscht",
                      links=link_pair(ctx))


def embeds_of(ctx: dict, theme_id) -> tuple:
    body, error = file_body(ctx, theme_id, "config/settings_data.json")
    if body is None:
        return None, error or "config/settings_data.json fehlt"
    try:
        settings = json.loads(apps.strip_comment_header(body.decode("utf-8")))
    except ValueError as exc:
        return None, f"settings_data.json kein JSON: {exc}"
    return {(e["app_handle"], e["block"]): e for e in apps.app_embeds(settings)}, None


def check_embeds(ctx: dict) -> list:
    group = "Apps und Embeds"
    title = "App-Embeds im neuen Theme"
    if not (ctx["old_id"] and ctx["new_id"]):
        return [make_check("app-embeds", group, title, BLOCKED, "Live- und Entwurfs-ID nötig")]
    old, error_old = embeds_of(ctx, ctx["old_id"])
    new, error_new = embeds_of(ctx, ctx["new_id"])
    if old is None or new is None:
        return [make_check("app-embeds", group, title, BLOCKED, f"nicht lesbar: {error_old or error_new}")]
    active_old = {k for k, e in old.items() if not e["disabled"]}
    active_new = {k for k, e in new.items() if not e["disabled"]}
    reasons = {k: dropped_reason(ctx, k[0], ctx["catalog"].service_for_handle(k[0])) for k in active_old - active_new}
    gaps = sorted(k for k, reason in reasons.items() if not reason)
    intended = sorted({reason for reason in reasons.values() if reason})
    extra = sorted(active_new - active_old)
    evidence = f"{len(active_old)} aktiv im alten, {len(active_new)} aktiv im neuen Theme"
    if gaps:
        evidence += "; fehlt oder aus: " + short_list([f"{h}/{b}" for h, b in gaps], 10)
    if extra:
        evidence += "; nur im neuen: " + short_list([f"{h}/{b}" for h, b in extra], 6)
    if intended:
        evidence += "; bewusst entfallen: " + "; ".join(intended)
    return [make_check("app-embeds", group, title, MISSING if gaps else OK, evidence,
                       action="im Theme-Editor des Entwurfs einschalten oder bewusst streichen" if gaps else "",
                       owner=OPERATOR if gaps else "", links=link_pair(ctx))]


# ---------------------------------------------------------------------------
# App-Einträge gegen den hochgeladenen Stand
# ---------------------------------------------------------------------------

def target_repo_dir(ctx: dict) -> Path | None:
    """Das Ziel-Repo, aus dem hochgeladen wurde (`theme_migration.target_repo`); None, wenn nicht gesetzt."""
    raw = migration_config(ctx["config"]).get("target_repo")
    if not raw:
        return None
    path = Path(os.path.expanduser(str(raw)))
    return path if path.is_absolute() else ctx["workspace"] / path


def read_injection_files(folder: Path) -> dict:
    """Layout und Einstellungen aus einem Ordner mit Theme-Struktur, soweit vorhanden."""
    files = {}
    for name in INJECTION_FILES:
        try:
            files[name] = (folder / name).read_bytes()
        except OSError:
            continue
    return files


def launch_records(ctx: dict) -> list:
    """Jedes `launch.json` eines bestätigten Launches des neuen Themes, das jüngste zuerst."""
    found = []
    for path in (ctx["workspace"] / "reporting" / "runs").glob("*/launch.json"):
        record = read_json(path)
        if isinstance(record, dict) and record.get("published") and \
                str(record.get("new_theme_id")) == str(ctx["new_id"]):
            found.append((str(record.get("published_at") or ""), path, record))
    return [(path, record) for _, path, record in sorted(found, key=lambda item: item[0], reverse=True)]


def launch_time(ctx: dict) -> datetime | None:
    """Zeitpunkt des Veröffentlichens: aus dem Migrationslauf, sonst aus `launch.json`."""
    values = (ctx["state"] or {}).get("values") or {}
    stamp = test_order.parse_time(values.get("published_at"))
    if stamp:
        return stamp
    for _, record in launch_records(ctx):
        stamp = test_order.parse_time(record.get("published_at"))
        if stamp:
            return stamp
    return None


def backup_draft(transport, theme_id, run_dir: Path) -> dict:
    """Sichert Layout und Einstellungen des Entwurfs direkt vor dem Veröffentlichen nach `<lauf>/published-draft/`.

    Referenz für `app-injections-after`: was danach im Live-Theme steht und hier fehlt, hat sich beim
    Veröffentlichen eingetragen. Liest nur. Scheitert der Abruf, steht der Grund im Ergebnis, und die
    Prüfung danach vergleicht mit dem Ziel-Repo.
    """
    record = {"dir": DRAFT_BACKUP_DIR, "theme_id": str(numeric_id(theme_id)), "captured_at": now_utc()}
    try:
        bodies = fetch_by_names(transport, theme_id, list(INJECTION_FILES))
    except Exception as exc:  # noqa: BLE001  ShopifyError, Netz, kaputte Antwort
        return {**record, "files": [], "error": f"{type(exc).__name__}: {exc}"[:300]}
    for name, data in bodies.items():
        target = run_dir / DRAFT_BACKUP_DIR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {**record, "files": sorted(bodies), "missing": sorted(set(INJECTION_FILES) - set(bodies))}


def injection_reference(ctx: dict) -> tuple:
    """Der hochgeladene Stand von Layout und Einstellungen: `(dateien, herkunft)` oder `(None, grund)`.

    Nach dem Launch zuerst die Sicherung, die der geführte Launch direkt vor dem Veröffentlichen anlegt:
    sie zeigt genau, was veröffentlicht wurde, auch eine Änderung im Theme-Editor nach dem Hochladen.
    Sonst, und vor dem Launch immer, das Ziel-Repo, aus dem hochgeladen wurde.
    """
    if ctx["after"]:
        for path, record in launch_records(ctx):
            folder = path.parent / str((record.get("draft_backup") or {}).get("dir") or DRAFT_BACKUP_DIR)
            files = read_injection_files(folder)
            if files:
                rel = folder.relative_to(ctx["workspace"]).as_posix()
                return files, f"Sicherung des Entwurfs vor dem Veröffentlichen ({rel})"
    folder = target_repo_dir(ctx)
    if folder is None:
        return None, "theme_migration.target_repo nicht gesetzt" + (
            ", und keine Sicherung des Entwurfs aus dem geführten Launch" if ctx["after"] else "")
    files = read_injection_files(folder)
    if not files:
        return None, f"{folder} hat weder layout/theme.liquid noch config/settings_data.json"
    return files, f"Ziel-Repo ({migration_config(ctx['config']).get('target_repo')})"


def layout_lines(data: bytes | None) -> list:
    """Zeilen des Layouts, die etwas einbinden, mit vereinheitlichtem Leerraum."""
    out = []
    for line in (data or b"").decode("utf-8", "replace").splitlines():
        norm = " ".join(line.split())
        if norm and INJECTED_LINE.search(norm) and norm not in out:
            out.append(norm)
    return out


def settings_embeds(data: bytes | None) -> dict | None:
    """App-Embeds aus `settings_data.json` je `(app_handle, block)`; None, wenn die Datei kein JSON ist."""
    if data is None:
        return None
    try:
        settings = json.loads(apps.strip_comment_header(data.decode("utf-8", "replace")))
    except ValueError:
        return None
    return {(e["app_handle"], e["block"]): e for e in apps.app_embeds(settings)} if isinstance(settings, dict) else None


def distinctive_words(text) -> set:
    """Wörter eines Namens oder einer Zeile, die eine App erkennen lassen: ab fünf Zeichen, nicht allgemein."""
    return {w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(w) >= 5 and not w.isdigit() and w not in GENERIC_WORDS}


def line_keys(line: str, catalog, own: set) -> set:
    """Schlüssel, unter denen eine eingebundene Zeile eine App treffen kann: Snippet, Datei, Host, Dienst."""
    keys = {m.group(1).lower() for m in re.finditer(r"\{%-?\s*(?:render|include)\s+['\"]([^'\"]+)['\"]", line)}
    keys |= {m.group(1).lower().rsplit(".", 1)[0]
             for m in re.finditer(r"['\"]([\w.-]+)['\"]\s*\|\s*(?:file_url|asset_url)", line)}
    for match in re.finditer(r"(?:https?:)?//([a-z0-9.-]+\.[a-z]{2,})(/[^\s'\"<>]*)?", line, re.I):
        host, path = match.group(1).lower(), match.group(2) or ""
        sid = catalog.service_for(host, path)
        if host in own or catalog.is_platform(sid):
            # Shopify Files oder die eigene Domain: der Dateiname trägt den Namen der App.
            name = path.rsplit("/", 1)[-1].split("?")[0]
            if name:
                keys.add(name.lower().rsplit(".", 1)[0])
            continue
        keys |= {k for k in (sid, host, registrable(host)) if k}
    keys |= {sid for sid, _, _ in catalog.code_hits(line)}
    keys |= {catalog.service_for_handle(k) for k in list(keys)} - {None}
    return keys


def injection_reason(ctx: dict, keys: set, text: str) -> str | None:
    """Beleg, wenn ein Eintrag zu einer App gehört, die laut Entscheidung entfällt (`drop` oder `replace`).

    Erst genau über Dienst, Handle oder Host, dann über ein kennzeichnendes Wort: eine Zeile
    `{% render 'beispiel-consent-rules' %}` gehört zur gestrichenen App `beispiel-consent`.
    """
    reason = dropped_reason(ctx, *keys)
    if reason:
        return reason
    words = distinctive_words(text) | {w for k in keys for w in distinctive_words(k)}
    return next((label for key, label in ctx["dropped"].items() if words & distinctive_words(key)), None)


def check_injections(ctx: dict) -> dict:
    """Hat sich eine App in Layout oder Einstellungen eingetragen, die im hochgeladenen Stand nicht stand?

    Vor dem Launch: der Entwurf gegen das Ziel-Repo. Nach dem Launch: das Live-Theme gegen die Sicherung
    des Entwurfs vom Veröffentlichen, sonst gegen das Ziel-Repo. Gemeldet werden neue Zeilen in
    `layout/theme.liquid` mit `render`, `include` oder `script` (auch aus Shopify Files) und App-Embeds in
    `current.blocks`, die neu sind oder wieder eingeschaltet. Gehört der Eintrag zu einer App, die laut
    Entscheidung entfällt, ist das ein Befund; sonst eine Frage.

    Seit 11.11.2026: eine Consent-App trug sich beim Veröffentlichen wieder ins Live-Theme ein, mit einer
    Zeile im Layout und einem App-Embed, und lud ein Werbe-Tag ohne Einwilligung. Abschalten in der App
    entfernte die Zeile nicht.
    """
    after = ctx["after"]
    group = "Apps und Embeds"
    cid = "app-injections-after" if after else "app-injections"
    title = ("App-Einträge im Live-Theme seit dem Veröffentlichen" if after
             else "App-Einträge im Entwurf gegen den hochgeladenen Stand")
    which = "Live-Theme" if after else "Entwurf"
    if not ctx["new_id"]:
        return make_check(cid, group, title, BLOCKED, "keine ID des neuen Themes")
    reference, origin = injection_reference(ctx)
    if reference is None:
        if after or ctx["state"]:
            return make_check(cid, group, title, BLOCKED, f"kein hochgeladener Stand zum Vergleich: {origin}",
                              action="theme_migration.target_repo setzen; der geführte Launch sichert den Entwurf "
                                     "künftig selbst", owner=OPERATOR)
        return make_check(cid, group, title, NA, f"ohne Migrationslauf und ohne hochgeladenen Stand ({origin})")
    subject = {}
    for name in INJECTION_FILES:
        body, error = file_body(ctx, ctx["new_id"], name)
        if error:
            return make_check(cid, group, title, BLOCKED, f"{name} im {which} nicht lesbar: {error}")
        subject[name] = body
    layout, settings = INJECTION_FILES
    items, compared, gaps = [], [], []
    if reference.get(layout) is not None and subject.get(layout) is not None:
        compared.append("theme.liquid")
        before = set(layout_lines(reference[layout]))
        own = own_hosts(ctx)
        for line in layout_lines(subject[layout]):
            if line not in before:
                items.append((f"theme.liquid: {line[:120]}",
                              injection_reason(ctx, line_keys(line, ctx["catalog"], own), line)))
    if reference.get(settings) is not None and subject.get(settings) is not None:
        old_embeds, new_embeds = settings_embeds(reference[settings]), settings_embeds(subject[settings])
        if old_embeds is None or new_embeds is None:
            gaps.append("settings_data.json kein JSON (" + ("Referenz" if old_embeds is None else which) + ")")
        else:
            compared.append("App-Embeds")
            for key, embed in sorted(new_embeds.items()):
                previous = old_embeds.get(key)
                if embed["disabled"] or (previous is not None and not previous["disabled"]):
                    continue
                handle = key[0]
                state = "wieder eingeschaltet" if previous is not None else "neu"
                keys = {handle, ctx["catalog"].service_for_handle(handle)} - {None}
                items.append((f"App-Embed {handle}/{key[1]} ({state})", injection_reason(ctx, keys, handle)))
    if not compared:
        return make_check(cid, group, title, BLOCKED,
                          f"weder theme.liquid noch App-Embeds in beiden Ständen lesbar ({origin})"
                          + ("; " + "; ".join(gaps) if gaps else ""), owner=OPERATOR)
    dropped = [(text, reason) for text, reason in items if reason]
    unknown = [text for text, reason in items if not reason]
    evidence = f"{' und '.join(compared)} im {which} gegen {origin}"
    if dropped:
        evidence += "; laut Entscheidung gestrichen und trotzdem eingetragen: " + short_list(
            [f"{text} ({reason})" for text, reason in dropped], 6)
    if unknown:
        evidence += "; nicht im hochgeladenen Stand: " + short_list(unknown, 6)
    if not items:
        evidence += ": keine neue Zeile mit render, include oder script, kein neues oder wieder eingeschaltetes App-Embed"
    if gaps:
        evidence += "; " + "; ".join(gaps)
    status = MISSING if dropped else MANUAL if unknown else (BLOCKED if gaps else OK)
    check = make_check(
        cid, group, title, status, evidence,
        action=(f"Zeile aus layout/theme.liquid entfernen und das Embed ausschalten, im {which}; die App selbst "
                "abschalten oder deinstallieren, sonst trägt sie sich beim nächsten Veröffentlichen wieder ein. "
                "Abschalten in der App entfernt eine eingetragene Zeile nicht. Danach neu prüfen")
        if status == MISSING else "",
        question=(f"Diese Einträge standen nicht im hochgeladenen Stand: {short_list(unknown, 3)}. Gehören sie ins "
                  f"{which}? Wenn nicht: entfernen und die App prüfen, die sie eingetragen hat.")
        if status == MANUAL else "",
        owner=OPERATOR if status in (MISSING, BLOCKED) else BOTH if status == MANUAL else "", links=link_pair(ctx))
    check["details"] = {"reference": origin, "dropped": [{"entry": t, "decision": r} for t, r in dropped],
                        "unknown": unknown}
    return check


def check_translations(ctx: dict) -> list:
    group = "Übersetzungen"
    title = "Theme-Übersetzungen"
    locales, error = shop(ctx, "locales", lambda t: t.execute(LOCALES_QUERY).get("shopLocales") or [])
    if locales is None:
        return [make_check("theme-translations", group, title, BLOCKED, f"Sprachen nicht lesbar: {error}",
                           action="Grant um read_locales erweitern", owner=OPERATOR)]
    others = sorted(l["locale"] for l in locales if l.get("published") and not l.get("primary"))
    if not others:
        return [make_check("theme-translations", group, title, NA, "nur die Primärsprache ist veröffentlicht")]
    if not (ctx["old_id"] and ctx["new_id"]):
        return [make_check("theme-translations", group, title, BLOCKED, "Live- und Entwurfs-ID nötig")]
    status, parts, gap = OK, [], False
    for locale in others:
        counts = {}
        for side, theme_id in (("new", ctx["new_id"]), ("old", ctx["old_id"])):
            resource, error = shop(ctx, f"tr-{theme_id}-{locale}", read_resource, theme_id, locale)
            if resource is None:
                return [make_check("theme-translations", group, title, BLOCKED,
                                   f"{locale}: Übersetzungen nicht lesbar ({error})")]
            done = [t for t in resource.get("translations") or [] if t.get("value")]
            counts[side] = {"total": len(resource.get("translatableContent") or []), "done": len(done),
                            "outdated": sum(1 for t in done if t.get("outdated"))}
        new, old = counts["new"], counts["old"]
        if new["outdated"] or (old["done"] and not new["done"]):
            status = MISSING
        share = lambda c: (c["done"] / c["total"] * 100) if c["total"] else 0.0  # noqa: E731
        if share(old) - share(new) > 10:
            gap = True
        parts.append(f"{locale}: neu {new['done']} von {new['total']} übersetzt, {new['outdated']} veraltet; "
                     f"alt {old['done']} von {old['total']}")
    if status == OK and gap:
        status = MANUAL
    return [make_check(
        "theme-translations", group, title, status, "; ".join(parts),
        action="auf dem Entwurf neu registrieren (theme.translations register)" if status == MISSING else "",
        question="Der Anteil übersetzter Texte ist im neuen Theme deutlich kleiner. Ist das gewollt?"
        if status == MANUAL else "", owner=OPERATOR if status != OK else "", links=link_pair(ctx))]


def check_customer_accounts(ctx: dict) -> list:
    group = "Plattform-Fristen"
    title = "Kundenkonten"
    data, error = shop(ctx, "accounts", lambda t: t.execute(ACCOUNTS_QUERY))
    if data is None:
        return [make_check("customer-accounts", group, title, BLOCKED, f"nicht lesbar: {error}")]
    version = (((data.get("shop") or {}).get("customerAccountsV2")) or {}).get("customerAccountsVersion")
    if version != "CLASSIC":
        return [make_check("customer-accounts", group, title, OK, f"Kundenkonten {version}, unabhängig vom Theme")]
    names, error = file_names(ctx, ctx["new_id"]) if ctx["new_id"] else (None, "keine Entwurfs-ID")
    if names is None:
        return [make_check("customer-accounts", group, title, BLOCKED, f"klassische Konten; Dateien nicht lesbar: {error}")]
    has = any(n.startswith("templates/customers/") for n in names)
    return [make_check(
        "customer-accounts", group, title, OK if has else MISSING,
        "klassische Kundenkonten (abgekündigt); "
        + ("das neue Theme hat templates/customers/" if has else "dem neuen Theme fehlen templates/customers/"),
        action="" if has else "Templates für klassische Konten ergänzen oder vor dem Launch auf neue Konten umstellen",
        owner="" if has else BOTH, links=link_pair(ctx, "/account/login"))]


def check_script_tags(ctx: dict) -> list:
    group = "Plattform-Fristen"
    title = "Skript-Tags"
    htmls = [run_html(r) for e in ctx["old"]["pages"].values() for r in e["runs"] if r.get("html_file")]
    htmls = [h for h in htmls if h]
    if not htmls:
        return [make_check("script-tags", group, title, BLOCKED, "kein HTML des Live-Themes im Mitschnitt",
                           action="Mitschnitt des Live-Themes ziehen (capture/old-declined)", owner=OPERATOR)]
    urls = sorted({u for h in htmls for u in apps.parse_async_load(h) or []})
    if not urls:
        return [make_check("script-tags", group, title, OK, "keine Skript-Tags in asyncLoad")]
    return [make_check("script-tags", group, title, MANUAL,
                       f"{len(urls)} Skript-Tags laufen weiter, Shopify lädt sie ab 01.03.2027 nicht mehr: "
                       + short_list([urlparse(u).hostname or u for u in urls]),
                       question="Ist für jeden Skript-Tag ein Nachfolger (meist ein App-Embed) geplant?",
                       owner=OPERATOR)]


def check_seo_robots(ctx: dict, group: str) -> dict:
    title = "robots.txt"
    name = "templates/robots.txt.liquid"
    if not (ctx["old_id"] and ctx["new_id"]):
        return make_check("robots", group, title, BLOCKED, "Live- und Entwurfs-ID nötig")
    old_names, error_old = file_names(ctx, ctx["old_id"])
    new_names, error_new = file_names(ctx, ctx["new_id"])
    if old_names is None or new_names is None:
        return make_check("robots", group, title, BLOCKED, f"Dateilisten nicht lesbar: {error_old or error_new}")
    live = f"{ctx['base_url']}/robots.txt"
    fetched, fetch_error = safe(ctx["fetch"], live)
    note = ""
    if fetched:
        note = f"; {live} antwortet {fetched[0]}"
        if fetched[0] == 200:
            write_text(ctx["run_dir"] / "robots-live.txt", fetched[2])
    elif fetch_error:
        note = f"; {live} nicht abrufbar ({fetch_error})"
    if name in old_names and name not in new_names:
        return make_check("robots", group, title, MISSING, "eigene robots.txt.liquid im Live-Theme, im Entwurf nicht" + note,
                          action="robots.txt.liquid übernehmen oder bewusst streichen", owner=OPERATOR)
    if name in old_names and name in new_names:
        old_body, _ = file_body(ctx, ctx["old_id"], name)
        new_body, _ = file_body(ctx, ctx["new_id"], name)
        same = old_body is not None and old_body.strip() == (new_body or b"").strip()
        return make_check("robots", group, title, OK if same else MISSING,
                          ("robots.txt.liquid in beiden Themes gleich" if same
                           else "robots.txt.liquid unterscheidet sich zwischen den Themes") + note,
                          action="" if same else "Unterschied ansehen und entscheiden", owner="" if same else OPERATOR)
    if name in new_names:
        return make_check("robots", group, title, MANUAL, "nur der Entwurf hat eine eigene robots.txt.liquid" + note,
                          question="Ist die neue robots.txt gewollt und geprüft?", owner=OPERATOR)
    return make_check("robots", group, title, OK, "beide Themes ohne eigene robots.txt.liquid, Ausgabe von Shopify" + note)


def check_seo_pages(ctx: dict, group: str) -> dict:
    title = "Statuscodes, noindex und Canonicals im Entwurf"
    if not ctx["new"]["pages"]:
        return make_check("seo-pages", group, title, BLOCKED, "kein Mitschnitt des Entwurfs",
                          action="capture_network.py mit --theme <Entwurf> nach capture/new-declined", owner=OPERATOR)
    problems, checked, blocked = [], 0, []
    for page_id, new_entry in sorted(ctx["new"]["pages"].items(), key=lambda kv: str(kv[0])):
        new_run = primary_run(new_entry)
        if not new_run:
            blocked.append(str(page_id))
            continue
        old_entry = ctx["old"]["pages"].get(page_id)
        old_run = primary_run(old_entry) if old_entry else None
        new_tags = head_tags(run_html(new_run) or "")
        old_tags = head_tags(run_html(old_run) or "") if old_run else {}
        checked += 1
        path = new_entry.get("path") or "/"
        status_new, status_old = new_run.get("status"), (old_run or {}).get("status")
        if status_new and (status_new >= 400 or (status_old and status_new != status_old)):
            problems.append((path, f"{path}: Status {status_new}" + (f", live {status_old}" if status_old else "")))
        if new_tags.get("noindex") and not old_tags.get("noindex"):
            problems.append((path, f"{path}: noindex im Entwurf"))
        if old_run and canonical_path(new_tags.get("canonical")) != canonical_path(old_tags.get("canonical")):
            problems.append((path, f"{path}: Canonical {canonical_path(new_tags.get('canonical'))}, "
                                   f"live {canonical_path(old_tags.get('canonical'))}"))
    if not checked:
        return make_check("seo-pages", group, title, BLOCKED, "kein gültiger Durchlauf im Mitschnitt des Entwurfs "
                          f"(falsches Theme oder Fehler: {short_list(blocked)})", owner=OPERATOR)
    evidence = f"{checked} Seiten aus dem Mitschnitt verglichen"
    if blocked:
        evidence += f"; ohne gültigen Durchlauf: {short_list(blocked)}"
    if problems:
        evidence += "; " + short_list([p[1] for p in problems], 6)
    links = [l for path in sorted({p[0] for p in problems})[:4] for l in link_pair(ctx, path)]
    return make_check("seo-pages", group, title, MISSING if problems else OK, evidence,
                      action="Ursache im Entwurf beheben (Mapping oder Generator-Regel)" if problems else "",
                      owner=OPERATOR if problems else "", links=links)


def published_locales(ctx: dict) -> tuple:
    """Primär-Subtags der veröffentlichten Sprachen und die Primärsprache; `(None, None, grund)` ohne Zugang."""
    locales, error = shop(ctx, "locales", lambda t: t.execute(LOCALES_QUERY).get("shopLocales") or [])
    if locales is None:
        return None, None, error
    published = {seo_parity.primary_subtag(l["locale"]) for l in locales if l.get("published")}
    primary = next((seo_parity.primary_subtag(l["locale"]) for l in locales if l.get("primary")), None)
    return published, primary, None


def seo_pairs(ctx: dict) -> tuple:
    """Seitenpaare aus den Mitschnitten: HTML des neuen Themes und, falls vorhanden, des alten."""
    pairs, blocked = [], []
    for page_id, entry in sorted(ctx["new"]["pages"].items(), key=lambda kv: str(kv[0])):
        run = primary_run(entry)
        html = run_html(run) if run else None
        if html is None:
            blocked.append(str(page_id))
            continue
        old_entry = ctx["old"]["pages"].get(page_id)
        old_run = primary_run(old_entry) if old_entry else None
        pairs.append({"id": page_id, "path": entry.get("path") or "/", "template": entry.get("template"),
                      "new_html": html, "old_html": run_html(old_run) if old_run else None})
    return pairs, blocked


def check_seo_output(ctx: dict, *, after: bool = False) -> list:
    """Strukturierte Daten, hreflang, Open Graph und Kopfdaten je Seite, neu gegen alt (seo_parity).

    Was live da ist und im neuen Theme fehlt, ist `missing`; eine ProductGroup mit
    Varianten ohne description ist es immer. Fehlt im Mitschnitt ein Pflicht-Seitentyp
    oder eine veröffentlichte Sprache, ist der Vergleich unvollständig und `blocked`,
    nie `ok`.
    """
    group = "SEO am Launch-Tag" if after else "SEO"
    suffix = "-after" if after else ""
    titles = {topic: (check_id + suffix, title) for topic, (check_id, title) in SEO_TOPICS.items()}
    if not ctx["new"]["pages"]:
        which = "des veröffentlichten Themes (capture/after-declined)" if after else "des Entwurfs (capture/new-declined)"
        return [make_check(cid, group, title, BLOCKED, f"kein Mitschnitt {which}",
                           action="capture_network.py mit derselben pages.json mitschneiden", owner=OPERATOR)
                for cid, title in titles.values()]
    pairs, without_html = seo_pairs(ctx)
    if not pairs:
        return [make_check(cid, group, title, BLOCKED, "kein HTML im Mitschnitt des neuen Themes "
                           f"(falsches Theme oder Fehler: {short_list(without_html)})", owner=OPERATOR)
                for cid, title in titles.values()]
    published, primary, locale_error = published_locales(ctx)
    result = seo_parity.compare_pages(pairs, published, primary)
    gaps = []
    if result["missing_templates"]:
        gaps.append("Seitentyp nicht im Mitschnitt: " + ", ".join(result["missing_templates"]))
    if result["missing_languages"]:
        gaps.append("Sprache nicht im Mitschnitt: " + ", ".join(result["missing_languages"])
                    + " (seo_parity pages ergänzt die Seitenliste)")
    if len(result["without_live"]) == len(pairs):
        gaps.append("kein HTML des alten Themes im Mitschnitt, nur absolute Regeln geprüft")
    if locale_error:
        gaps.append(f"Sprachen nicht lesbar ({locale_error[:80]}), Abdeckung je Sprache nicht geprüft")
    base = (f"{len(pairs)} Seiten verglichen, Seitentypen {', '.join(result['templates'])}"
            + (f", Sprachen {', '.join(result['languages'])}" if result["languages"] else ""))
    out = []
    for topic, (cid, title) in titles.items():
        found = result["topics"][topic]
        by_text = {}
        for problem in found["problems"]:
            by_text.setdefault(problem["text"], []).append(problem["path"] or "/")
        evidence = base
        if by_text:
            evidence += "; " + short_list([f"{text} ({short_list(paths, 3)})" for text, paths in by_text.items()], 6)
        if found["notes"]:
            evidence += "; Hinweis: " + short_list(sorted({n["text"] for n in found["notes"]}), 3)
        if without_html:
            evidence += f"; ohne HTML: {short_list(without_html, 4)}"
        if gaps:
            evidence += "; " + "; ".join(gaps)
        status = MISSING if by_text else (BLOCKED if gaps else OK)
        paths = sorted({p["path"] or "/" for p in found["problems"]})[:4]
        check = make_check(cid, group, title, status, evidence,
                           action="im Theme nachbauen, Horizon-Grundpaket (seo-parity.md) prüfen, neu mitschneiden"
                           if status == MISSING else ("Mitschnitt vervollständigen" if status == BLOCKED else ""),
                           owner=OPERATOR if status != OK else "", links=[l for p in paths for l in link_pair(ctx, p)])
        check["details"] = {"problems": found["problems"], "notes": found["notes"],
                            "missing_templates": result["missing_templates"],
                            "missing_languages": result["missing_languages"]}
        out.append(check)
    return out


def check_tracking(ctx: dict, *, after: bool = False) -> list:
    group = "Tracking"
    title = "Fremde Hosts je Seite, neu gegen alt" if not after else "Apps und Tracking auf dem veröffentlichten Theme"
    check_id = "tracking-hosts" if not after else "tracking-after"
    if not ctx["old"]["pages"] or not ctx["new"]["pages"]:
        which = "alt" if not ctx["old"]["pages"] else "neu"
        return [make_check(check_id, group, title, BLOCKED, f"Mitschnitt fehlt ({which})",
                           action="beide Themes mit capture_network.py mitschneiden, höchstens zwei Browser gleichzeitig",
                           owner=OPERATOR)]
    result = compare_tracking(ctx["old"], ctx["new"], own_hosts(ctx), ctx["catalog"], ctx["host_map"])
    # Was laut Entscheidungsliste bewusst entfällt, ist erfüllt, mit der Entscheidung als Beleg.
    intended = [m for m in result["missing"] if dropped_reason(ctx, m["service"])]
    result["missing"] = [m for m in result["missing"] if m not in intended]
    status = MISSING if result["missing"] else OK
    evidence = f"{result['pages']} Seiten und Consent-Zustände verglichen"
    if result["missing"]:
        by_service = {}
        for m in result["missing"]:
            by_service.setdefault(m["name"], set()).add(m["page_id"])
        evidence += "; fehlt im neuen Theme: " + short_list(
            [f"{name} ({len(pages)} {'Seite' if len(pages) == 1 else 'Seiten'})"
             for name, pages in sorted(by_service.items(), key=lambda kv: (-len(kv[1]), kv[0]))], 12)
    if intended:
        evidence += "; bewusst entfallen: " + "; ".join(sorted({dropped_reason(ctx, m["service"]) for m in intended}))
    if result["added"]:
        evidence += "; nur im neuen: " + short_list(sorted({a["service"] for a in result["added"]}), 6)
    if result["wrong_theme"]:
        status = BLOCKED if status == OK else status
        evidence += "; Durchläufe mit falschem Theme: " + short_list(result["wrong_theme"])
    if result["throttled"]:
        status = BLOCKED if status == OK else status
        evidence += ("; von Shopify gedrosselt (HTTP 429), kein Fehler des Shops, nicht verglichen: "
                     + short_list(result["throttled"]))
    if result["unmatched"]:
        evidence += "; ohne Gegenstück: " + short_list(result["unmatched"])
    if result["unconfirmed"]:
        evidence += ("; nicht verglichen, weil die Einwilligung im Mitschnitt nicht erteilt wurde: "
                     + short_list(result["unconfirmed"]))
    paths = sorted({m["path"] for m in result["missing"] if m.get("path")})[:4]
    out = [make_check(check_id, group, title, status, evidence,
                      action="Einbindung im neuen Theme herstellen oder bewusst streichen (apps-and-tracking.md)"
                      if result["missing"] else "gedrosselte Seiten mit capture_network.py --parallel 1 --pace 10 "
                      "nachholen (--only <ids>)" if result["throttled"] else "",
                      owner=OPERATOR if status != OK else "",
                      links=[l for p in paths for l in link_pair(ctx, p)])]
    out[0]["details"] = {"missing": result["missing"], "added": result["added"], "dropped": intended}
    if not after:
        out.append(check_consent_capture(ctx))
    return out


def accepted_runs(capture: dict) -> tuple:
    """Durchläufe mit Einwilligung: belegt (Dialog zugestimmt) und unbelegt, mit Grund."""
    runs = [r for e in capture["pages"].values() for r in e["runs"]
            if r.get("consent") == "accepted" and r.get("state") == "ok"]
    confirmed = [r for r in runs if consent_result(r) == "accepted"]
    unconfirmed = sorted({f"{r.get('page_id')} ({consent_result(r) or 'ohne Ergebnis des Dialogs'})"
                          for r in runs if consent_result(r) != "accepted"})
    return confirmed, unconfirmed


def consent_ways(runs: list) -> str:
    return ", ".join(sorted({str((r.get("consent_result") or {}).get("how")) for r in runs})) or "unbekannt"


def check_consent_capture(ctx: dict) -> dict:
    """Vor dem Launch: liegt auf beiden Themes ein Mitschnitt mit erteilter Einwilligung vor?

    Bis 10.11.2026 genügte ein Ordner `*-accepted`, auch wenn der Dialog darin nie
    bedient wurde. Jetzt zählt nur ein Durchlauf, in dem der Dialog zugestimmt hat.
    """
    group, title = "Tracking", "Mitschnitt mit Einwilligung"
    if not ({"accepted"} & ctx["old"]["modes"] and {"accepted"} & ctx["new"]["modes"]):
        return make_check("tracking-consent", group, title, MANUAL,
                          "nur ohne Einwilligung mitgeschnitten; App-Pixel in Consent-Regionen laden erst danach",
                          question="Darf ich auf beiden Themes mit Einwilligung mitschneiden?", owner=TEAM)
    old_ok, old_bad = accepted_runs(ctx["old"])
    new_ok, new_bad = accepted_runs(ctx["new"])
    if old_ok and new_ok and not (old_bad or new_bad):
        return make_check("tracking-consent", group, title, OK,
                          f"beide Themes mit und ohne Einwilligung mitgeschnitten; zugestimmt über {consent_ways(old_ok + new_ok)}")
    gaps = [f"{side}: {short_list(bad)}" for side, bad in (("alt", old_bad), ("neu", new_bad)) if bad]
    gaps += [f"{side}: kein Durchlauf mit erteilter Einwilligung" for side, ok in (("alt", old_ok), ("neu", new_ok))
             if not ok and not dict(alt=old_bad, neu=new_bad)[side]]
    return make_check("tracking-consent", group, title, BLOCKED,
                      "Einwilligung im Mitschnitt nicht erteilt; " + "; ".join(gaps),
                      action="Cookie-Dialog im Browser ansehen; kennt consent.py das Tool nicht, Knopf ergänzen, "
                             "dann mit --consent accepted neu mitschneiden", owner=OPERATOR)


def privacy_problems(run: dict) -> list:
    """Erreicht die Einwilligung Shopify und den Consent Mode? Leer, wenn ja oder nicht lesbar.

    `Shopify.customerPrivacy` entscheidet, ob App- und Kassen-Pixel senden; ein
    Banner, der nur sich selbst merkt, lässt sie stumm. Im Consent Mode zählt das
    Update nach der Zustimmung (`update`), nicht der Ausgangswert.
    """
    privacy = run.get("privacy") or {}
    problems = []
    customer = privacy.get("customer_privacy")
    if isinstance(customer, dict):
        denied = [f"{k}={customer.get(k)!r}" for k in ("analytics", "marketing")
                  if str(customer.get(k)).lower() not in PRIVACY_GRANTED]
        if denied:
            problems.append("Shopify customerPrivacy " + ", ".join(denied))
    google = privacy.get("google_consent")
    if isinstance(google, dict):
        denied = [k for k in ("analytics_storage", "ad_storage")
                  if isinstance(google.get(k), dict) and google[k].get("update") is False]
        if denied:
            problems.append("Consent Mode ohne Zustimmung für " + ", ".join(denied))
    return problems


def check_consent_after(ctx: dict) -> dict:
    """Nach dem Launch: Tracking mit erteilter Einwilligung je Seitentyp, neu gegen den Mitschnitt vorher.

    Nie `ok` ohne Durchläufe mit erteilter Einwilligung auf beiden Seiten. Das alte
    Theme lässt sich nach dem Launch weiter als Vorschau mitschneiden.
    """
    group, title = "Tracking", "Tracking nach Einwilligung je Seitentyp"
    check_id = "tracking-consent-after"
    old_ok, old_bad = accepted_runs(ctx["old"])
    new_ok, new_bad = accepted_runs(ctx["new"])
    capture_hint = "capture_network.py --consent accepted mit derselben pages.json"
    if not ({"accepted"} & ctx["new"]["modes"]):
        return make_check(check_id, group, title, BLOCKED,
                          "kein Mitschnitt des veröffentlichten Themes mit Einwilligung (capture/after-accepted)",
                          action=f"nach Freigabe des Teams {capture_hint} nach capture/after-accepted",
                          owner=OPERATOR)
    if not ({"accepted"} & ctx["old"]["modes"]):
        return make_check(check_id, group, title, BLOCKED,
                          "kein Mitschnitt des alten Themes mit Einwilligung zum Vergleich",
                          action=f"{capture_hint} und --theme {ctx['old_id'] or '<altes Theme>'} (Vorschau) nach "
                                 "capture/old-accepted, oder den Mitschnitt vom Tag vor dem Launch über --network-old",
                          owner=OPERATOR)
    hosts, catalog, host_map = own_hosts(ctx), ctx["catalog"], ctx["host_map"]
    compared, blocked, missing, added, gated = [], [], [], set(), set()
    for page_id, old_entry in sorted(ctx["old"]["pages"].items(), key=lambda kv: str(kv[0])):
        before_runs = [r for r in old_entry["runs"] if r in old_ok]
        new_entry = ctx["new"]["pages"].get(page_id) or {"runs": []}
        after_runs = [r for r in new_entry["runs"] if r in new_ok]
        if not any(r.get("consent") == "accepted" for r in old_entry["runs"] + new_entry["runs"]):
            continue
        if not (before_runs and after_runs):
            blocked.append(f"{old_entry.get('template') or page_id} ({'alt' if not before_runs else 'neu'})")
            continue
        template = old_entry.get("template") or page_id
        compared.append(str(template))
        before = third_party_keys(before_runs, hosts, catalog, host_map)
        after = third_party_keys(after_runs, hosts, catalog, host_map)
        for key in sorted(before - after):
            if not dropped_reason(ctx, key):
                missing.append((template, catalog.describe(key)["service_name"], old_entry.get("path")))
        added |= after - before
        declined_runs = [r for r in new_entry["runs"] if r.get("consent") == "declined" and r.get("state") == "ok"]
        if declined_runs:
            declined = third_party_keys(declined_runs, hosts, catalog, host_map)
            gated |= {catalog.describe(k)["service_name"] for k in after - declined}
    new_privacy = sorted({p for r in new_ok for p in privacy_problems(r)})
    old_privacy = sorted({p for r in old_ok for p in privacy_problems(r)})
    gaps = []
    if new_bad:
        gaps.append("neu ohne erteilte Einwilligung: " + short_list(new_bad))
    if old_bad:
        gaps.append("alt ohne erteilte Einwilligung: " + short_list(old_bad))
    if blocked:
        gaps.append("ohne Gegenstück mit Einwilligung: " + short_list(blocked))
    evidence = (f"{len(compared)} Seitentypen mit erteilter Einwilligung verglichen ({short_list(compared)})"
                if compared else "kein Seitentyp mit erteilter Einwilligung auf beiden Seiten")
    if new_ok:
        evidence += f"; zugestimmt über {consent_ways(new_ok)}"
    if missing:
        by_service = {}
        for template, name, _ in missing:
            by_service.setdefault(name, set()).add(str(template))
        evidence += "; fehlt nach Einwilligung im neuen Theme: " + short_list(
            [f"{name} ({', '.join(sorted(t))})" for name, t in sorted(by_service.items())], 10)
    if new_privacy:
        evidence += "; Einwilligung erreicht nicht alles: " + "; ".join(new_privacy) + (
            " (im alten Theme ebenso)" if set(new_privacy) <= set(old_privacy) and old_privacy else "")
    elif new_ok:
        evidence += "; Shopify customerPrivacy und Consent Mode nach Zustimmung erteilt"
    if gated:
        evidence += "; lädt erst nach Einwilligung: " + short_list(sorted(gated), 8)
    if added:
        evidence += "; nur im neuen: " + short_list(sorted(added), 6)
    if gaps:
        evidence += "; " + "; ".join(gaps)
    status = MISSING if (missing or new_privacy) else (BLOCKED if (gaps or not compared) else OK)
    action = {MISSING: "Einbindung nach Einwilligung herstellen (Pixel, Consent-Anbindung an Shopify Customer Privacy "
                       "und Consent Mode), dann neu mitschneiden",
              BLOCKED: "Cookie-Dialog ansehen; kennt consent.py das Tool nicht, Knopf ergänzen; fehlende Seiten mit "
                       "--consent accepted mitschneiden"}.get(status, "")
    paths = sorted({p for _, _, p in missing if p})[:4]
    check = make_check(check_id, group, title, status, evidence, action=action,
                       owner=OPERATOR if status != OK else "", links=[l for p in paths for l in link_pair(ctx, p)])
    check["details"] = {"compared": compared, "missing": [{"template": t, "service": n} for t, n, _ in missing],
                        "privacy": new_privacy, "unconfirmed": {"old": old_bad, "new": new_bad}, "blocked": blocked}
    return check


def pre_consent_senders(capture: dict, own: set, catalog, host_map: dict | None = None) -> tuple:
    """Dienste für Werbung, Analyse und Sitzungsaufzeichnung, die vor einer Einwilligung senden oder laden.

    Vor der Einwilligung heißt: jeder Durchlauf ohne Einwilligung und in einem Durchlauf mit Einwilligung
    jede Anfrage bis zum Klick (`consent_phase: pre`). Ein Dienst zählt über den Host-Katalog, nie über
    einen einzelnen Hostnamen: Microsoft Advertising sendet an `bat.bing.com` und an `bat.bing.net`, beide
    stehen in `hosts.json` beim selben Dienst. Bis 11.11.2026 prüfte eine Consent-Messung nur
    `bat.bing.com` und übersah so Aufrufe ohne Einwilligung.

    Gibt `({dienst: {"sends": seiten, "loads": seiten, "hosts": hosts}}, zahl der durchläufe)` zurück.
    """
    found, runs = {}, 0
    for page_id, entry in capture["pages"].items():
        for run in entry["runs"]:
            if run.get("state") != "ok":
                continue
            declined = run.get("consent") != "accepted"
            requests = [r for r in run.get("requests") or [] if declined or r.get("consent_phase") == "pre"]
            if declined or requests:
                runs += 1
            for request in requests:
                url = request.get("url") or ""
                key = request_key(url, own, catalog, host_map)
                if not key or catalog.describe(key)["category"] not in PRE_CONSENT_CATEGORIES:
                    continue
                slot = found.setdefault(key, {"sends": set(), "loads": set(), "hosts": set()})
                sends = tracking_ids.sends_data(request.get("method"), request.get("resource_type"), url)
                slot["sends" if sends else "loads"].add(str(entry.get("template") or page_id))
                slot["hosts"].add((urlparse(url).hostname or "").lower())
    return found, runs


def check_pre_consent(ctx: dict) -> dict:
    """Sendet das neue Theme vor einer Einwilligung an einen Werbe- oder Analysedienst, an den das alte nicht sendete?

    Verglichen wird neu gegen alt, nicht absolut: ein Consent Mode im erweiterten Modus sendet auch vor
    der Einwilligung Pings ohne Cookies, und das war vorher schon so. Neu ist ein Befund; ein Dienst, der
    neu nur lädt, ohne zu senden, steht als Hinweis.
    """
    after = ctx["after"]
    group, cid = "Tracking", "tracking-pre-consent-after" if after else "tracking-pre-consent"
    title = "Werbung und Analyse vor Einwilligung, neu gegen alt"
    which = "veröffentlichten Themes (capture/after-declined)" if after else "Entwurfs (capture/new-declined)"
    if not ctx["old"]["pages"] or not ctx["new"]["pages"]:
        return make_check(cid, group, title, BLOCKED,
                          f"Mitschnitt fehlt ({'alt' if not ctx['old']['pages'] else 'neu'})",
                          action=f"beide Themes ohne Einwilligung mitschneiden, das neue als Mitschnitt des {which}",
                          owner=OPERATOR)
    own, catalog, host_map = own_hosts(ctx), ctx["catalog"], ctx["host_map"]
    before, old_runs = pre_consent_senders(ctx["old"], own, catalog, host_map)
    now, new_runs = pre_consent_senders(ctx["new"], own, catalog, host_map)
    if not (old_runs and new_runs):
        return make_check(cid, group, title, BLOCKED,
                          f"kein Durchlauf ohne Einwilligung im Mitschnitt ({'alt' if not old_runs else 'neu'})",
                          action="ohne --consent accepted mitschneiden (Standard)", owner=OPERATOR)

    def describe(key: str, pages: set) -> str:
        hosts = ", ".join(sorted(now[key]["hosts"]))
        return f"{catalog.describe(key)['service_name']} an {hosts} ({short_list(sorted(pages), 4)})"

    senders = sorted(k for k in now if now[k]["sends"] and not (before.get(k) or {}).get("sends"))
    loaders = sorted(k for k in now if now[k]["loads"] and not now[k]["sends"] and k not in before)
    same = sorted(k for k in now if now[k]["sends"] and (before.get(k) or {}).get("sends"))
    evidence = f"{new_runs} Durchläufe ohne Einwilligung im neuen, {old_runs} im alten Theme"
    if senders:
        evidence += "; sendet neu vor der Einwilligung: " + short_list([describe(k, now[k]["sends"]) for k in senders], 6)
    if loaders:
        evidence += "; lädt neu vor der Einwilligung, ohne zu senden: " + short_list(
            [describe(k, now[k]["loads"]) for k in loaders], 4)
    if same:
        evidence += "; sendet vor der Einwilligung wie im alten Theme: " + short_list(
            [catalog.describe(k)["service_name"] for k in same], 6)
    if not (senders or loaders or same):
        evidence += "; kein Werbe- oder Analysedienst sendet vor der Einwilligung"
    status = MISSING if senders else OK
    check = make_check(cid, group, title, status, evidence,
                       action="Auslöser im Browser suchen (Initiator der Anfrage, meist eine App oder ein Tag), "
                              "abschalten oder an die Einwilligung binden, dann neu mitschneiden" if senders else "",
                       owner=OPERATOR if senders else "", links=link_pair(ctx) if senders else [])
    check["details"] = {"sends": {k: sorted(now[k]["sends"]) for k in senders},
                        "loads": {k: sorted(now[k]["loads"]) for k in loaders}, "as_before": same}
    return check


# ---------------------------------------------------------------------------
# Web Pixels: Liste vorher gegen nachher, Sicherung der Custom Pixels
# ---------------------------------------------------------------------------

def inventory_rows(ctx: dict) -> list | None:
    """Zeilen aus `migration/inventory/apps.json`; None ohne Datei."""
    data = read_json(ctx["workspace"] / "migration" / "inventory" / "apps.json")
    if data is None:
        return None
    rows = data.get("integrations") if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def capture_htmls(capture: dict, until: datetime | None = None) -> list:
    """HTML aller Durchläufe eines Mitschnitts; mit `until` nur aus Mitschnitten, die davor entstanden.

    Ein Mitschnitt ohne Zeitstempel zählt mit, ältere Mitschnitte tragen keinen.
    """
    out = []
    for entry in capture["pages"].values():
        for run in entry["runs"]:
            captured = test_order.parse_time(run.get("_captured_at"))
            if until and captured and captured > until:
                continue
            html = run_html(run)
            if html:
                out.append(html)
    return out


def live_pixels(ctx: dict) -> tuple:
    """Die Pixel-Liste des Live-Shops jetzt: `(pixel, herkunft)` oder `(None, grund)`.

    Aus dem HTML des Mitschnitts des Themes, das gerade live ist (vor dem Launch das alte, danach das neue),
    sonst aus einem Abruf der Startseite. Die Liste gilt für den ganzen Shop; ein Abruf ohne Browser
    genügt, weil keine Vorschau im Spiel ist.
    """
    if "pixels-live" not in ctx["cache"]:
        capture = ctx["new"] if ctx["after"] else ctx["old"]
        htmls = capture_htmls(capture)
        pixels = web_pixels.merge(web_pixels.from_html(h) for h in htmls)
        if pixels is not None:
            result = (pixels, f"HTML des Mitschnitts ({len(htmls)} Seiten)")
        else:
            url = ctx["base_url"] + "/"
            fetched, error = safe(ctx["fetch"], url)
            pixels = web_pixels.from_html(fetched[2]) if fetched and fetched[0] == 200 else None
            if pixels is not None:
                result = (pixels, f"Abruf von {url}")
            else:
                result = (None, f"webPixelsConfigList weder im HTML des Mitschnitts ({len(htmls)} Seiten) noch in {url} ("
                          + (f"Status {fetched[0]}" if fetched else f"nicht abrufbar: {error}") + ")")
        ctx["cache"]["pixels-live"] = result
    return ctx["cache"]["pixels-live"]


def pixels_before(ctx: dict) -> tuple:
    """Die Pixel-Liste von vor dem Launch: `(pixel, herkunft)` oder `(None, grund)`.

    In dieser Reihenfolge: `web-pixels-before.json` aus dem Launch-Check vor dem Launch, das HTML eines
    Mitschnitts des alten Themes, der vor dem Launch entstand, das HTML der Bestandsaufnahme. Ein
    Mitschnitt des alten Themes nach dem Launch zeigt schon die Liste danach und zählt nicht.
    """
    published = launch_time(ctx)
    candidates = []
    for path in (ctx["workspace"] / "reporting" / "runs").glob(f"*/{web_pixels.BEFORE_FILE}"):
        data = web_pixels.load_before(path)
        captured = test_order.parse_time((data or {}).get("captured_at"))
        if data and not (published and captured and captured > published):
            candidates.append((captured or datetime.min.replace(tzinfo=timezone.utc), path, data))
    if candidates:
        _, path, data = max(candidates, key=lambda c: c[0])
        return data["pixels"], (f"{path.relative_to(ctx['workspace']).as_posix()} vom "
                                f"{str(data.get('captured_at'))[:10]}")
    htmls = capture_htmls(ctx["old"], published)
    pixels = web_pixels.merge(web_pixels.from_html(h) for h in htmls)
    if pixels is not None:
        return pixels, "HTML des Mitschnitts des alten Themes" + (
            "" if published else "; Zeitpunkt des Launches unbekannt, gilt nur für einen Mitschnitt von vorher")
    texts = []
    for path in sorted((ctx["workspace"] / "migration" / "inventory" / "network").glob("*/html/*.html")):
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    pixels = web_pixels.merge(web_pixels.from_html(t) for t in texts)
    if pixels is not None:
        return pixels, "HTML der Bestandsaufnahme (migration/inventory/network)"
    return None, ("keine Pixel-Liste von vor dem Launch: kein web-pixels-before.json aus dem Launch-Check vorher, "
                  "kein HTML im Mitschnitt des alten Themes und keins in der Bestandsaufnahme")


def custom_pixels(ctx: dict, pixels: list | None) -> dict:
    """Custom Pixels aus Pixel-Liste und Bestandsaufnahme: `{id: {"id", "name"}}`."""
    found = {}
    for pixel in pixels or []:
        if web_pixels.is_custom(pixel):
            found[str(pixel["id"])] = {"id": str(pixel["id"]), "name": pixel.get("name")}
    for row in inventory_rows(ctx) or []:
        sid = str(row.get("service_id") or "")
        if row.get("integration_type") != "web_pixel_custom" and not sid.startswith("custom_pixel:"):
            continue
        location = row.get("location") or {}
        pid = str(location.get("pixel_id") or sid.partition(":")[2] or "")
        if pid:
            entry = found.setdefault(pid, {"id": pid, "name": None})
            entry["name"] = entry["name"] or location.get("pixel_name")
    return found


def custom_pixel_decision(ctx: dict, pixel: dict) -> str | None:
    """Beleg, wenn ein Custom Pixel laut Entscheidung entfernt oder ersetzt wird."""
    pid = pixel["id"]
    return dropped_reason(ctx, f"custom_pixel:{pid}", f"web_pixel:{pid}", f"custom pixel {pid}", pixel.get("name"))


def app_pixel_decision(ctx: dict, pixel: dict) -> str | None:
    """Beleg, wenn die App eines App-Pixels laut Entscheidung entfällt: über die Zeile der Bestandsaufnahme."""
    pid = str(pixel.get("id"))
    row = next((r for r in inventory_rows(ctx) or [] if r.get("integration_id") == f"web_pixel:{pid}"), None)
    keys = {f"web_pixel:{pid}"}
    if row:
        keys |= {str(row.get("service_id") or ""), str(row.get("app_handle") or "")}
    else:
        keys |= {tracking_ids.KIND_SERVICE.get(t["kind"]) or ""
                 for t in tracking_ids.config_targets(pixel.get("configuration"))}
    return dropped_reason(ctx, *(k for k in keys if k))


def check_web_pixels(ctx: dict) -> list:
    """Vor dem Launch: die Pixel-Liste des Live-Shops festhalten und die Sicherung der Custom Pixels prüfen."""
    group, title = "Tracking", "Pixel-Liste des Live-Shops festgehalten"
    pixels, origin = live_pixels(ctx)
    if pixels is None:
        out = [make_check("web-pixels", group, title, BLOCKED, origin,
                          action="Mitschnitt des Live-Themes mit HTML ziehen (capture/old-declined); ohne die Liste "
                                 "fällt nach dem Launch kein entferntes Pixel auf", owner=OPERATOR)]
    else:
        path = ctx["run_dir"] / web_pixels.BEFORE_FILE
        web_pixels.save_before(path, pixels, origin, now_utc())
        custom = [p for p in pixels if web_pixels.is_custom(p)]
        evidence = (f"{len(pixels)} Pixel aus {origin}, davon {len(custom)} Custom"
                    + (": " + short_list([web_pixels.label(p) for p in custom], 6) if custom else "")
                    + f"; festgehalten in {path.relative_to(ctx['workspace']).as_posix()} für den Vergleich nach "
                      "dem Launch")
        out = [make_check("web-pixels", group, title, OK, evidence)]
    return out + [check_pixel_backup(ctx, pixels)]


def check_pixel_backup(ctx: dict, pixels: list | None) -> dict:
    """Jedes Custom Pixel, das laut Entscheidung entfernt oder ersetzt wird, liegt gesichert und gelesen vor.

    Gesichert und gelesen heißt: Code unter `migration/inventory/pixels/<name>.js` und eine Notiz
    `<name>.md` mit Sendet, Wo und An (`theme.web_pixels`). Sonst ist das ein Befund und blockiert den Go:
    ein Pixel, das nur in der Kasse sendet, sieht kein Mitschnitt, und nach dem Löschen ist sein Code weg.
    """
    group, cid, title = "Tracking", "custom-pixel-backup", "Custom Pixels vor dem Entfernen gesichert"
    rows = inventory_rows(ctx)
    if pixels is None and rows is None:
        return make_check(cid, group, title, BLOCKED,
                          "weder Pixel-Liste noch Bestandsaufnahme (migration/inventory/apps.json)",
                          action="Mitschnitt des Live-Themes mit HTML ziehen oder inventory-apps laufen lassen",
                          owner=OPERATOR)
    custom = custom_pixels(ctx, pixels)
    if not custom:
        return make_check(cid, group, title, NA, "kein Custom Pixel in "
                          + " und ".join(s for s, has in (("Pixel-Liste", pixels is not None),
                                                         ("Bestandsaufnahme", rows is not None)) if has))
    backups = web_pixels.load_backups(ctx["workspace"])
    missing, saved, kept = [], [], []
    for pixel in sorted(custom.values(), key=lambda p: p["id"]):
        name = web_pixels.label({"type": "CUSTOM", **pixel})
        reason = custom_pixel_decision(ctx, pixel)
        ok, state = web_pixels.backup_state(web_pixels.find_backup(backups, pixel["id"], pixel.get("name")))
        if not reason:
            if not ok:
                kept.append(name)
            continue
        (saved if ok else missing).append(f"{name}: {reason}; {state}")
    evidence = f"{len(custom)} Custom Pixels"
    if missing:
        evidence += "; entfernt oder ersetzt ohne gesicherte, gelesene Datei: " + short_list(missing, 4)
    if saved:
        evidence += "; entfernt oder ersetzt und gesichert: " + short_list(saved, 4)
    if not (missing or saved):
        evidence += ", keines soll laut Entscheidung entfernt oder ersetzt werden"
    if kept:
        evidence += "; bleiben, noch ohne Sicherung: " + short_list(kept, 4)
    check = make_check(cid, group, title, MISSING if missing else OK, evidence,
                       action=(f"Code jedes Pixels aus dem Admin (Einstellungen, Kundenereignisse) nach "
                               f"{web_pixels.BACKUP_DIR.as_posix()}/<name>.js, daneben <name>.md mit Pixel-ID, "
                               "Sendet, Wo und An; erst dann entfernen") if missing else "",
                       owner=OPERATOR if missing else "")
    check["details"] = {"missing": missing, "saved": saved, "kept_without_backup": kept}
    return check


def check_web_pixels_after(ctx: dict) -> dict:
    """Nach dem Launch: die Pixel-Liste des Live-Shops gegen die von vor dem Launch.

    Pixel überleben einen Theme-Wechsel; fehlt eines danach, hat es jemand entfernt. Ein Befund, außer es
    ist bewusst entfernt und, als Custom Pixel, gesichert. Hat ein Pixel ein Messziel verloren, ist das eine
    Frage.
    """
    group, cid, title = "Tracking", "web-pixels-after", "Pixel-Liste vorher gegen nachher"
    before, origin_before = pixels_before(ctx)
    if before is None:
        return make_check(cid, group, title, BLOCKED, origin_before,
                          action="Mitschnitt des alten Themes vom Tag vor dem Launch über --network-old übergeben; "
                                 "künftig hält der Launch-Check vor dem Launch die Liste fest", owner=OPERATOR)
    after, origin_after = live_pixels(ctx)
    if after is None:
        return make_check(cid, group, title, BLOCKED, origin_after,
                          action="Mitschnitt des veröffentlichten Themes mit HTML (capture/after-declined)",
                          owner=OPERATOR)
    old = {str(p.get("id")): p for p in before}
    new = {str(p.get("id")): p for p in after}
    backups = web_pixels.load_backups(ctx["workspace"])
    gone_ok, gone_bad, lost, gained = [], [], [], []
    for pid in sorted(set(old) - set(new)):
        pixel = old[pid]
        name = web_pixels.label(pixel)
        sends = web_pixels.targets(pixel)
        impact = f", Ziele {short_list(sends, 4)}" if sends else ""
        if web_pixels.is_custom(pixel):
            reason = custom_pixel_decision(ctx, {"id": pid, "name": pixel.get("name")})
            ok, state = web_pixels.backup_state(web_pixels.find_backup(backups, pid, pixel.get("name")))
            if reason and ok:
                gone_ok.append(f"{name}: {reason}; {state}")
            elif reason:
                gone_bad.append(f"{name}: entfernt laut {reason}, aber nicht gesichert ({state})")
            else:
                gone_bad.append(f"{name}: ohne Entscheidung entfernt" + (f"; {state}" if ok else f" ({state})"))
        else:
            reason = app_pixel_decision(ctx, pixel)
            (gone_ok if reason else gone_bad).append(
                f"{name}{impact}: " + (reason if reason else "ohne Entscheidung entfernt"))
    for pid in sorted(set(old) & set(new)):
        before_targets, after_targets = set(web_pixels.targets(old[pid])), set(web_pixels.targets(new[pid]))
        if before_targets - after_targets:
            lost.append(f"{web_pixels.label(new[pid])} sendet nicht mehr an "
                        f"{short_list(sorted(before_targets - after_targets), 4)}")
        if after_targets - before_targets:
            gained.append(f"{web_pixels.label(new[pid])} neu an {short_list(sorted(after_targets - before_targets), 4)}")
    added = [web_pixels.label(new[pid]) for pid in sorted(set(new) - set(old))]
    evidence = f"{len(old)} Pixel vorher ({origin_before}), {len(new)} jetzt ({origin_after})"
    if gone_bad:
        evidence += "; fehlt: " + short_list(gone_bad, 4)
    if lost:
        evidence += "; Messziel verloren: " + short_list(lost, 4)
    if gone_ok:
        evidence += "; bewusst entfernt: " + short_list(gone_ok, 4)
    if added:
        evidence += "; neu: " + short_list(added, 4)
    if gained:
        evidence += "; " + short_list(gained, 4)
    if not (gone_bad or gone_ok or lost):
        evidence += "; kein Pixel entfernt"
    status = MISSING if gone_bad else MANUAL if lost else OK
    check = make_check(
        cid, group, title, status, evidence,
        action=("Pixel wiederherstellen (Custom Pixel aus der Sicherung oder dem Admin-Verlauf, App-Pixel über die "
                "App verbinden); entfällt es bewusst: Entscheidung mit Person und Grund in decisions.json, ein Custom "
                f"Pixel vorher nach {web_pixels.BACKUP_DIR.as_posix()}/ sichern") if gone_bad else "",
        question=("Ein Pixel sendet nach dem Launch an weniger Ziele als vorher. Ist das gewollt? Sonst die "
                  "Verbindung in der App neu einrichten.") if status == MANUAL else "",
        owner=OPERATOR if gone_bad else BOTH if status == MANUAL else "")
    check["details"] = {"missing": gone_bad, "removed_on_purpose": gone_ok, "lost_targets": lost, "added": added}
    return check


def property_slug(g_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", g_id.lower()).strip("-")


def check_funnel_events(ctx: dict) -> list:
    """Datenschicht je GA4-Property: altes gegen neues Theme, Pflicht am Handy (Safari) mit langsamer Verbindung.

    Liest Durchläufe von `walk_checkout.py --headless` (`theme.funnel_events`): unter diesem Lauf `events/`,
    sonst `migration/verify/*/events/` und andere Läufe der letzten sieben Tage. Vor dem Launch ist "neu"
    der Entwurf, danach das veröffentlichte Theme und "alt" das Rückfall-Theme. Was alt unter denselben
    Bedingungen an eine Property ging und neu fehlt, ist ein Befund.
    """
    group = "Tracking"
    suffix = "-after" if ctx["after"] else ""
    title = "Datenschicht je GA4-Property (Handy, Safari, langsame Verbindung)"
    walks = funnel_events.find_walks(ctx["workspace"], [ctx["run_dir"] / "events"])
    old_walks = funnel_events.pick(walks, ctx["old_id"])
    new_walks = funnel_events.pick(walks, ctx["new_id"])
    which = "veröffentlichten Themes" if ctx["after"] else "Entwurfs"
    base = f"reporting/runs/{ctx['run_dir'].name}/events" if ctx["after"] else "migration/verify/<date>/events"
    action = ("Durchläufe ohne Bestellung, nach Freigabe des Mitschnitts mit Einwilligung: "
              + funnel_events.walk_commands(ctx["old_id"], ctx["new_id"], base))
    if not new_walks:
        return [make_check("funnel-events" + suffix, group, title, BLOCKED,
                           f"kein Durchlauf des {which} (events/*/walk.json); ein verlorenes add_to_cart zeigt sich "
                           "oft nur am Handy mit Safari und langsamer Verbindung", action=action, owner=OPERATOR)]
    result = funnel_events.compare(old_walks, new_walks, ctx["old_id"], ctx["new_id"])
    blocked = ("; nicht verglichen: " + short_list(result["blocked"], 3)) if result["blocked"] else ""
    if not result["properties"]:
        if result["mobile_slow"] and not result["blocked"]:
            return [make_check("funnel-events" + suffix, group, title, NA,
                               "keine GA4-Ereignisse des Kaufwegs im Browser, weder alt noch neu; eine serverseitige "
                               "Property prüft nach dem Launch die Echtzeit (realtime-ga4-*)")]
        return [make_check("funnel-events" + suffix, group, title, BLOCKED,
                           "kein vergleichbarer Durchlauf am Handy mit langsamer Verbindung" + blocked,
                           action=action, owner=OPERATOR)]
    out = []
    for tid, entries in sorted(result["properties"].items()):
        status, evidence = funnel_events.property_verdict(entries, result["mobile_slow"])
        out.append(make_check(
            f"funnel-ga4-{property_slug(tid)}{suffix}", group, f"Datenschicht: GA4-Property {tid}", status,
            evidence + blocked,
            action=("Ereignis im neuen Theme wieder senden: die Datenschicht darf beim Seitenwechsel nach dem "
                    "Hinzufügen nichts verlieren (etwa die Meldung auf der nächsten Seite nachholen), dann beide "
                    "Durchläufe wiederholen") if status == MISSING else action if status == BLOCKED else "",
            owner=OPERATOR if status != OK else "", links=link_pair(ctx, "/cart")))
        out[-1]["details"] = {"entries": entries, "conditions": result["conditions"]}
    return out


def check_funnel_realtime(ctx: dict) -> list:
    """Nach dem Launch: GA4-Echtzeit je Property gegen die serverseitige Property und gegen die Bestellungen.

    Die Property-IDs stehen in `theme_migration.ga4_properties`; die mit `via` (etwa Littledata) ist die
    Referenz. Gelesen wird nur, Abgleich und Grenzen in `theme.funnel_events.realtime_verdict`.
    """
    group = "Tracking"
    title = "Echtzeit je GA4-Property gegen Littledata und Bestellungen"
    props = funnel_events.configured_properties(ctx["config"])
    if not props:
        known = sorted(purchase_targets(ctx)["ga4"])
        return [make_check("realtime-ga4", group, title, BLOCKED,
                           "theme_migration.ga4_properties fehlt; die Echtzeit braucht je Messkennung die Property-ID"
                           + (f"; Properties von vor dem Launch: {short_list(known, 6)}" if known else ""),
                           action='in reporting/config.json eintragen: "ga4_properties": {"G-…": {"property_id": '
                                  '"…", "via": "Littledata"}, "G-…": {"property_id": "…"}}', owner=OPERATOR)]
    factory = ctx.get("ga4_for") or test_order.ga4_reader_factory(ctx["workspace"])
    numbers = {}
    for g_id, spec in props.items():
        reader, error = factory(spec["property_id"])
        if reader is None:
            numbers[g_id] = (None, error)
            continue
        numbers[g_id] = test_order.safe_call(reader.realtime_events, list(funnel_events.REALTIME_EVENTS))
    since = datetime.now(timezone.utc) - timedelta(minutes=funnel_events.REALTIME_MINUTES)
    counted, order_error = shop(ctx, "orders-realtime", test_order.orders_since, since)
    orders = counted[0] if counted else None
    reference_id = next((g for g, spec in props.items() if spec.get("via")), None)
    reference = (numbers.get(reference_id) or (None, None))[0] if reference_id else None
    notes = []
    if not reference_id:
        notes.append("keine Property mit via (serverseitig) in ga4_properties; nur purchase gegen die Bestellungen")
    elif reference is None:
        notes.append(f"Referenz {reference_id} nicht lesbar ({numbers[reference_id][1]})")
    if orders is None:
        notes.append(f"Bestellungen nicht lesbar ({order_error})")
    elif counted[1]:
        notes.append("mindestens 20 Bestellungen im Fenster")
    out = []
    for g_id, (values, error) in sorted(numbers.items()):
        spec = props[g_id]
        cid = "realtime-ga4-" + property_slug(g_id)
        label = f"Echtzeit: GA4-Property {g_id}" + (f" (über {spec['via']}, Referenz)" if g_id == reference_id else "")
        if values is None:
            out.append(make_check(cid, group, label, BLOCKED, f"Property {spec['property_id']} nicht lesbar: {error}",
                                  action="Zugang des Dienstkontos zur Property prüfen", owner=OPERATOR))
            continue
        status, evidence, low = funnel_events.realtime_verdict(values, None if g_id == reference_id else reference,
                                                               orders)
        evidence += ("; " + "; ".join(notes)) if notes else ""
        out.append(make_check(
            cid, group, label, status, evidence,
            action=("Einbindung dieser Property prüfen (Datenschicht, Tag Manager, Kassen-Pixel), dann erneut "
                    "abgleichen") if status == MISSING else (
                "später erneut prüfen, sobald Verkehr da ist" if status == BLOCKED else ""),
            question=(f"{g_id} zählt deutlich weniger als erwartet ({', '.join(low)}). Erklärt das die "
                      "Einwilligungsrate, oder fehlt ein Ereignis?") if status == MANUAL else "",
            owner=OPERATOR if status in (MISSING, BLOCKED) else BOTH if status == MANUAL else ""))
    return out


#: Skripte aus Shopify Files (Inhalte > Dateien), nicht aus den Theme-Assets.
FILES_URL = re.compile(r"(?:cdn\.shopify\.com/s/files/1/(?:\d+/)+files/|/cdn/shop/files/)[^\s'\"<>?]+", re.I)
SCRIPT_SRC = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.I)


def files_name(url: str) -> str | None:
    """Dateiname eines Skripts aus Shopify Files, None für alles andere."""
    match = FILES_URL.search(url or "")
    return match.group(0).rsplit("/", 1)[-1].lower() if match and match.group(0).lower().endswith(".js") else None


def capture_files_scripts(capture: dict) -> dict:
    """Skripte aus Shopify Files in einem Mitschnitt: `{dateiname: adresse}`, aus Anfragen und HTML."""
    found = {}
    for entry in capture["pages"].values():
        for run in entry["runs"]:
            urls = [r.get("url") or "" for r in run.get("requests") or []]
            urls += SCRIPT_SRC.findall(run_html(run) or "")
            for url in urls:
                name = files_name(url)
                if name:
                    full = url if "://" in url else ("https:" + url if url.startswith("//") else run_base(run) + url)
                    found.setdefault(name, full)
    return found


def run_base(run: dict) -> str:
    return str(run.get("_base") or "").rstrip("/")


def consent_apps(ctx: dict) -> dict:
    """Abgelöste Consent-Apps: `{name: (schlüssel, beleg)}` aus der Bestandsaufnahme und der Entscheidungsliste."""
    out = {}
    for row in inventory_rows(ctx) or []:
        if row.get("category") != "consent" or row.get("decision") not in DROPPED_DECISIONS:
            continue
        keys = {k.lower() for k in (str(row.get("service_id") or ""), str(row.get("app_handle") or "")) if k}
        name = str(row.get("service_name") or row.get("app_handle") or row.get("service_id"))
        out[name] = (keys, dropped_reason(ctx, *keys) or f"{name}: {row['decision']} laut apps.json")
    for key, label in ctx["dropped"].items():
        if ctx["catalog"].describe(key)["category"] == "consent":
            name = ctx["catalog"].describe(key)["service_name"]
            keys, _ = out.get(name, (set(), label))
            out[name] = (keys | {key}, label)
    return out


def check_consent_app_after(ctx: dict) -> dict:
    """Nach dem Launch: ist eine abgelöste Consent-App wirklich weg?

    Am 11.11.2026 trug sich eine abgelöste Consent-App beim Veröffentlichen wieder ein: eine Zeile in
    `layout/theme.liquid`, die ein Skript aus Shopify Files lädt, und ein App-Embed. Das Skript lud ein
    Werbe-Tag ohne Einwilligung. Deaktivieren in der App wirkt nicht auf die Zeile und nicht auf die Datei.
    Geprüft wird deshalb: keine Zeile im Live-Layout und kein geladenes Skript aus Shopify Files, das zu der
    App gehört; jede Datei, die sie vor dem Launch aus Files lud, antwortet nicht mehr; und die Frage an das
    Team, ob die App deinstalliert ist.
    """
    group, cid = "Apps und Embeds", "consent-app-after"
    title = "Abgelöste Consent-App deinstalliert, ihre Datei gelöscht"
    apps_ = consent_apps(ctx)
    if not apps_:
        return make_check(cid, group, title, NA, "kein Consent-Tool laut Entscheidung abgelöst (apps.json, "
                                                 "decisions.json)")
    words = {name: {w for k in keys for w in distinctive_words(k)} | distinctive_words(name)
             for name, (keys, _) in apps_.items()}

    def owner_of(text: str) -> str | None:
        found = distinctive_words(text)
        return next((name for name, w in words.items() if w & found), None)

    problems, unknown, unreachable, checked = [], [], [], []
    layout, error = file_body(ctx, ctx["new_id"], "layout/theme.liquid")
    if layout is not None:
        checked.append("theme.liquid")
        for line in layout_lines(layout):
            if ("file_url" in line or FILES_URL.search(line)) and owner_of(line):
                problems.append(f"Zeile im Live-Layout: {line[:100]} ({owner_of(line)})")
    after_scripts = capture_files_scripts(ctx["new"])
    before_scripts = capture_files_scripts(ctx["old"])
    if ctx["new"]["pages"]:
        checked.append("Mitschnitt nach dem Launch")
        for name, url in sorted(after_scripts.items()):
            if owner_of(name):
                problems.append(f"lädt noch aus Shopify Files: {name} ({owner_of(name)})")
            elif name not in before_scripts:
                unknown.append(name)
    for index, (name, url) in enumerate(sorted((n, u) for n, u in before_scripts.items() if owner_of(n))):
        if index:
            ctx["sleep"](FETCH_PAUSE)
        fetched, fetch_error = safe(ctx["fetch"], url)
        checked.append(f"Datei {name}")
        if fetched and fetched[0] == 200:
            problems.append(f"Datei {name} liegt noch unter Inhalte > Dateien (antwortet 200)")
        elif not fetched:
            unreachable.append(f"{name} ({fetch_error})")
    names = ", ".join(sorted(apps_))
    evidence = f"abgelöst: {'; '.join(sorted({label for _, label in apps_.values()}))}"
    evidence += f"; geprüft: {', '.join(checked) or 'nichts (kein Layout, kein Mitschnitt)'}"
    if error and layout is None:
        evidence += f"; theme.liquid nicht lesbar ({error})"
    if problems:
        evidence += "; " + short_list(problems, 6)
    if unknown:
        evidence += "; Skripte aus Shopify Files ohne Zuordnung, neu seit dem Launch: " + short_list(unknown, 4)
    if unreachable:
        evidence += "; Abruf gescheitert: " + short_list(unreachable, 3)
    if problems:
        return make_check(cid, group, title, MISSING, evidence,
                          action=f"{names} im Admin deinstallieren (nicht nur deaktivieren), die Zeile aus "
                                 "layout/theme.liquid und das Embed entfernen, die Datei unter Inhalte > Dateien "
                                 "löschen; dann neu mitschneiden und prüfen", owner=BOTH, links=link_pair(ctx))
    if not checked:
        return make_check(cid, group, title, BLOCKED, evidence, action="Mitschnitt nach dem Launch ziehen",
                          owner=OPERATOR)
    return make_check(cid, group, title, MANUAL, evidence + "; keine Zeile, kein Skript, keine Datei mehr",
                      question=f"Ist {names} im Admin unter Apps deinstalliert, nicht nur deaktiviert? Sonst trägt "
                               "sie sich beim nächsten Veröffentlichen wieder ein.", owner=TEAM)


def check_pagination(ctx: dict) -> list:
    """Nachladen je Seitentyp und Zahl der Analyse-Ereignisse, neu gegen alt.

    Am 07.10.2026 übersehen: eine Suchseite lud im neuen Theme beim Scrollen endlos
    nach und schrieb jede Seite in die Adresse; das vervielfachte die
    Suchereignisse in Analyse und Attribution. Die Host-Prüfung sieht das nicht,
    weil dieselben Dienste laden, nur öfter.
    """
    group = "Tracking"
    title = "Pagination und Analyse-Ereignisse je Seitentyp"
    if not ctx["old"]["pages"] or not ctx["new"]["pages"]:
        return [make_check("pagination", group, title, BLOCKED,
                           f"Mitschnitt fehlt ({'alt' if not ctx['old']['pages'] else 'neu'})", owner=OPERATOR)]
    rows = compare_pagination(ctx["old"], ctx["new"], own_hosts(ctx), ctx["catalog"], ctx["host_map"])
    if not rows:
        return [make_check("pagination", group, title, BLOCKED, "keine Seite mit gültigem Durchlauf in beiden "
                           "Mitschnitten", owner=OPERATOR)]
    paging, inflated = [], []
    for row in rows:
        where = f"{row['template']} ({row['device']})"
        if row["new_page"] > row["start_page"] and row["old_page"] <= row["start_page"]:
            paging.append((row, f"{where}: lädt beim Scrollen nach bis page={row['new_page']} in der Adresse, "
                                "das alte Theme nicht"))
        elif row["old_page"] > row["start_page"] and row["new_page"] <= row["start_page"]:
            paging.append((row, f"{where}: schreibt keine Seite mehr in die Adresse, das alte Theme bis "
                                f"page={row['old_page']}"))
        if row["inflated"]:
            inflated.append((row, f"{where}: " + ", ".join(f"{i['name']} {i['new']} statt {i['old']} Anfragen"
                                                          for i in row["inflated"])))
    templates = sorted({str(r["template"]) for r in rows})
    evidence = f"{len(templates)} Seitentypen mitgeschnitten bis zum Seitenende, alt gegen neu"
    if paging:
        evidence += "; " + short_list([text for _, text in paging], 6)
    if inflated:
        evidence += "; mehr Analyse-Ereignisse je Seite: " + short_list([text for _, text in inflated], 6)
    status = MISSING if inflated else (MANUAL if paging else OK)
    paths = sorted({r["path"] or "/" for r, _ in paging + inflated})[:4]
    check = make_check(
        "pagination", group, title, status, evidence,
        action="Nachladen so bauen wie im alten Theme oder ohne Adresswechsel; danach neu mitschneiden"
        if inflated else "",
        question="Die Pagination verhält sich anders als im alten Theme. Ist das gewollt, und zählt jede "
                 "nachgeladene Seite in GA4 und Attribution nicht als eigener Aufruf?" if status == MANUAL else "",
        owner=OPERATOR if status != OK else "", links=[l for p in paths for l in link_pair(ctx, p)])
    check["details"] = {"pages": rows}
    return [check]


def check_baseline(ctx: dict) -> list:
    group = "Vergleichswerte vorher"
    sources = ctx["config"].get("sources") or {}
    reference = ctx["launch_date"] or ctx["today"]
    found, stale, absent = [], [], []
    for filename, key in BASELINE_FILES.items():
        if sources.get(key) is False:
            continue
        path = newest((ctx["workspace"] / "reporting" / "data").glob(f"*/{filename}"))
        if not path:
            absent.append(filename)
            continue
        day = datetime.fromtimestamp(path.stat().st_mtime).date()
        entry = f"{filename} vom {day.strftime('%d.%m.%Y')}"
        (found if 0 <= (reference - day).days <= 1 else stale).append(entry)
    status = OK if not (stale or absent) else MISSING
    evidence = f"Bezug {reference.strftime('%d.%m.%Y')}"
    if found:
        evidence += "; frisch: " + ", ".join(found)
    if stale:
        evidence += "; zu alt: " + ", ".join(stale)
    if absent:
        evidence += "; fehlt: " + ", ".join(absent)
    return [make_check("baseline-values", group, "GSC, GA4, Core Web Vitals und Crawl von heute oder gestern", status,
                       evidence, action="pull-gsc, pull-ga4, pull-cwv und crawl-site direkt vor dem Launch"
                       if status != OK else "", owner=OPERATOR if status != OK else "")]


def check_go_decision(ctx: dict) -> list:
    """Gate G5 als Go-Punkt, nur in einem Migrationslauf.

    Seit 10.11.2026 veröffentlicht der geführte Launch (`theme.launch`) selbst und fragt nur, wenn alles grün
    ist. G5 gehört deshalb in die Liste: solange es offen ist, ist der Lauf nicht grün, und niemand wird
    gefragt, ob jetzt veröffentlicht werden soll.
    """
    if not ctx["state"]:
        return []
    group = "Go/No-Go und Kommunikation"
    gate = (ctx["state"].get("gates") or {}).get("G5-go-live")
    if gate:
        note = f": {gate['note']}" if gate.get("note") else ""
        return [make_check("go-decision", group, "Go/No-Go entschieden (G5)", OK,
                           f"Go von {gate.get('decided_by')} am {str(gate.get('decided_at'))[:10]}{note}")]
    when = f" am {ctx['launch_date'].strftime('%d.%m.%Y')}" if ctx["launch_date"] else ""
    return [make_check("go-decision", group, "Go/No-Go entschieden (G5)", MANUAL,
                       "G5 ist im Migrationslauf nicht eingetragen",
                       question=f"Go für den Launch{when}? Die Person der Marke entscheidet nach Abstimmung mit "
                                "Path to AI und trägt G5 mit ihrem Namen ein.",
                       owner="Person der Marke mit Path to AI")]


def check_criteria(ctx: dict) -> list:
    group = "Go/No-Go und Kommunikation"
    return [
        make_check("go-criteria", group, "Go/No-Go- und Rückfallkriterien schriftlich", MANUAL,
                   "launch-checklist.md und rollback.md geben die Form vor, die Schwellen legt das Team fest",
                   question="Stehen Go/No-Go- und Rückfallkriterien schriftlich, mit der Person, die im Ernstfall "
                            "entscheidet?", owner=BOTH),
        make_check("rollback-limits", group, "Was ein Rückfall nicht zurückdreht", MANUAL,
                   "Liste in rollback.md: Zuweisungen, Admin-Daten, App-Deinstallationen, Embeds je Theme, Skript-Tags",
                   question="Hat das Team die Liste gesehen?", owner=OPERATOR),
        make_check("communication", group, "Kommunikation", MANUAL, "nicht automatisch prüfbar",
                   question="Sind Termin und Rückfallkriterien an alle Beteiligten raus, auch an "
                            "Agenturen und Apps mit Schreibrecht ins Theme?", owner=OPERATOR),
    ]


# ---------------------------------------------------------------------------
# Prüfungen nach dem Launch
# ---------------------------------------------------------------------------

def check_published(ctx: dict) -> list:
    group = "Veröffentlichtes Theme"
    themes, error = themes_by_id(ctx)
    out = []
    if themes is None or not ctx["new_id"]:
        out.append(make_check("published-theme", group, "Erwartetes Theme ist live", BLOCKED,
                              f"Theme-Liste nicht lesbar: {error}" if themes is None else "keine ID des neuen Themes"))
    else:
        main = next((t for t in themes.values() if t.get("role") == "MAIN"), None)
        main_id = numeric_id(main["id"]) if main else None
        ok = main_id == ctx["new_id"]
        out.append(make_check("published-theme", group, "Erwartetes Theme ist live", OK if ok else MISSING,
                              f"live ist {main_id} \"{main and main.get('name')}\"" + ("" if ok else f", erwartet {ctx['new_id']}"),
                              action="" if ok else "im Admin prüfen, was veröffentlicht wurde", owner="" if ok else OPERATOR,
                              links=link_pair(ctx)))
    out.append(rollback_check(ctx, themes, error, group))
    return out


def previous_robots(ctx: dict) -> Path | None:
    runs = ctx["workspace"] / "reporting" / "runs"
    return newest(p for p in runs.glob("*-launch-check/robots-live.txt"))


def old_noindex(ctx: dict, page: dict) -> bool | None:
    """Stand `noindex` im HTML des alten Themes auf dieser Seite? None ohne Mitschnitt davon."""
    entry = ctx["old"]["pages"].get(page.get("id")) or next(
        (e for e in ctx["old"]["pages"].values() if e.get("path") == page.get("path")), None)
    run = primary_run(entry) if entry else None
    html = run_html(run) if run else None
    return head_tags(html)["noindex"] if html is not None else None


def check_after_seo(ctx: dict) -> list:
    group = "SEO am Launch-Tag"
    out = []
    url = f"{ctx['base_url']}/robots.txt"
    fetched, error = safe(ctx["fetch"], url)
    if not fetched:
        out.append(make_check("robots-after", group, "robots.txt", BLOCKED, f"{url} nicht abrufbar ({error})"))
    else:
        status, _, body = fetched
        before_path = previous_robots(ctx)
        relevant, others = blocked_agents(body) if status == 200 else ([], [])
        note = f"; Disallow: / nur für {', '.join(others)}" if others else ""
        if status != 200 or relevant:
            agents = " und ".join("alle Crawler (*)" if a == "*" else "Googlebot" for a in relevant)
            out.append(make_check("robots-after", group, "robots.txt", MISSING,
                                  f"{url} antwortet {status}" + (f", sperrt alles für {agents} (Disallow: /)"
                                                                 if relevant else ""),
                                  action="robots.txt sofort korrigieren", owner=OPERATOR))
        elif before_path is None:
            out.append(make_check("robots-after", group, "robots.txt", MANUAL,
                                  f"{url} antwortet 200, {len(body.splitlines())} Zeilen; kein Stand von vorher im "
                                  "Workspace" + note,
                                  question="Ist die robots.txt wie vor dem Launch?", owner=OPERATOR))
        else:
            same = before_path.read_text(encoding="utf-8").strip() == body.strip()
            rel = before_path.relative_to(ctx["workspace"]).as_posix()
            out.append(make_check("robots-after", group, "robots.txt", OK if same else MISSING,
                                  f"{'gleich wie' if same else 'anders als'} {rel}" + note,
                                  action="" if same else "Unterschied ansehen und entscheiden",
                                  owner="" if same else OPERATOR))
    problems, notes, checked, errors = [], [], 0, []
    for index, page in enumerate(page_list(ctx)):
        if index:
            ctx["sleep"](FETCH_PAUSE)
        page_url = ctx["base_url"] + page["path"]
        fetched, error = safe(ctx["fetch"], page_url)
        if not fetched:
            errors.append(f"{page['path']} ({error})")
            continue
        checked += 1
        status, headers, html = fetched
        tags = head_tags(html)
        if status >= 400:
            problems.append(f"{page['path']}: Status {status}")
        if tags["noindex"]:
            before = old_noindex(ctx, page)
            if before:
                notes.append(f"{page['path']}: noindex wie im alten Theme")
            else:
                problems.append(f"{page['path']}: noindex" + (", ohne Mitschnitt des alten Themes zum Vergleich"
                                                              if before is None else ", im alten Theme nicht"))
        elif "noindex" in headers.get("x-robots-tag", "").lower():
            # Ein Theme setzt keine Antwort-Header; X-Robots-Tag kommt von Shopify (etwa auf /search).
            notes.append(f"{page['path']}: noindex als Header X-Robots-Tag von Shopify, unabhängig vom Theme")
        if tags["canonical"] and canonical_path(tags["canonical"]) != canonical_path(page_url):
            problems.append(f"{page['path']}: Canonical {canonical_path(tags['canonical'])}")
    evidence = f"{checked} Seiten live abgerufen"
    if problems:
        evidence += "; " + short_list(problems, 8)
    if notes:
        evidence += "; Hinweis: " + short_list(notes, 4)
    if errors:
        evidence += "; nicht abrufbar: " + short_list(errors, 4)
    status = MISSING if problems else (BLOCKED if not checked else OK)
    out.append(make_check("pages-after", group, "Statuscodes, noindex und Canonicals live", status, evidence,
                          action="sofort beheben oder Rückfall nach den Kriterien" if problems else "",
                          owner=OPERATOR if problems else ""))
    return out


def check_after_languages(ctx: dict) -> list:
    group = "Sprachen"
    locales, error = shop(ctx, "locales", lambda t: t.execute(LOCALES_QUERY).get("shopLocales") or [])
    if locales is None:
        return [make_check("languages-after", group, "Jede Sprache einmal", BLOCKED, f"Sprachen nicht lesbar: {error}")]
    paths = ["/"] + [f"/{l['locale'].lower()}" for l in locales if l.get("published") and not l.get("primary")]
    problems, checked = [], []
    for index, path in enumerate(paths):
        if index:
            ctx["sleep"](FETCH_PAUSE)
        fetched, error = safe(ctx["fetch"], ctx["base_url"] + path)
        if not fetched:
            problems.append(f"{path} nicht abrufbar ({error})")
            continue
        checked.append(path)
        if fetched[0] >= 400:
            problems.append(f"{path}: Status {fetched[0]}")
        if "translation missing" in fetched[2].lower():
            problems.append(f"{path}: \"Translation missing\" im Quelltext")
    return [make_check("languages-after", group, "Jede Sprache einmal", MISSING if problems else OK,
                       f"geprüft: {', '.join(checked) or 'keine'}" + ("; " + short_list(problems) if problems else "")
                       + "; Markt-Pfade, die nicht dem Muster /<sprache> folgen, sind nicht geprüft",
                       action="Übersetzungen auf dem neuen Theme registrieren" if problems else "",
                       owner=OPERATOR if problems else "")]


# ---------------------------------------------------------------------------
# Testbestellung nach dem Launch
# ---------------------------------------------------------------------------

TEST_ORDER_GROUP = "Testbestellung"


def find_walk(ctx: dict) -> tuple:
    """Der Durchlauf der Kasse: `--test-order`, sonst dieser Lauf, sonst der jüngste der letzten sieben Tage.

    Der GA4-Bericht braucht bis zu 48 Stunden; der Lauf am Folgetag hat einen
    neuen Ordner und muss den Durchlauf vom Launch-Tag finden.
    """
    if ctx["test_order_arg"]:
        path = Path(ctx["test_order_arg"])
        return path, test_order.load_walk(path)
    own = ctx["run_dir"] / "test-order" / "walk.json"
    if own.is_file():
        return own, test_order.load_walk(own)
    found = []
    for path in (ctx["workspace"] / "reporting" / "runs").glob("*/test-order/walk.json"):
        walk = test_order.load_walk(path)
        started = test_order.parse_time((walk or {}).get("started_at"))
        if started and datetime.now(timezone.utc) - started <= WALK_MAX_AGE:
            found.append((started, path, walk))
    if not found:
        return None, None
    _, path, walk = max(found, key=lambda item: item[0])
    return path, walk


def run_relative(ctx: dict, walk_path: Path, name: str | None) -> str | None:
    if not name:
        return None
    return Path(os.path.relpath(walk_path.parent / name, ctx["run_dir"])).as_posix()


def purchase_targets(ctx: dict) -> dict:
    """GA4-Properties und Google-Ads-Kauf-Conversions, die der Shop vor dem Launch bediente, je mit Herkunft.

    Quellen: `tracking.json` der Bestandsaufnahme, die Anfragen im Mitschnitt des alten Themes, die
    Pixel-Liste von vor dem Launch (Konfiguration je Pixel, für Google Ads nur Ziele des Ereignisses
    `purchase`) und jedes gesicherte Custom Pixel. Eine Property oder Conversion, die nur ein Pixel in der
    Kasse bediente, steht allein in der Pixel-Konfiguration oder in der Sicherung; ein Mitschnitt der
    Seiten sieht sie nie. Bewusst Gestrichenes (`decisions.json` mit der Kennung als Gegenstand) fehlt.

    Gibt `{"ga4": {"G-…": [herkunft]}, "google_ads": {("AW-…", label): [herkunft]}}` zurück.
    """
    ga4, ads = {}, {}

    def add(table: dict, key, source: str) -> None:
        sources = table.setdefault(key, [])
        if source not in sources:
            sources.append(source)

    tracking = read_json(ctx["workspace"] / "migration" / "inventory" / "tracking.json")
    # Nur Kennungen mit einem lebenden Absender: ein Rest in totem Theme-Code bekommt keinen Kauf und wäre
    # sonst ein Befund ohne Grund.
    states = {r.get("integration_id"): r.get("state") for r in inventory_rows(ctx) or []}
    for target in (tracking.get("targets") or []) if isinstance(tracking, dict) else []:
        if not (isinstance(target, dict) and target.get("kind") == "ga4" and target.get("target_id")):
            continue
        live = [s for s in target.get("senders") or [] if isinstance(s, dict) and (
            s.get("basis") == "network" or states.get(s.get("integration_id")) not in ("disabled", "leftover"))]
        if live or not target.get("senders"):
            add(ga4, str(target["target_id"]).upper(), "Bestandsaufnahme (tracking.json)")
    for entry in ctx["old"]["pages"].values():
        for run in entry["runs"]:
            for request in run.get("requests") or []:
                for target in tracking_ids.request_targets(request.get("url") or "", request.get("post_data")):
                    if target["kind"] == "ga4":
                        add(ga4, target["target_id"].upper(), "Mitschnitt des alten Themes")
    pixels, _ = pixels_before(ctx) if ctx["after"] else live_pixels(ctx)
    for pixel in pixels or []:
        source = f"Pixel-Konfiguration ({web_pixels.label(pixel)})"
        for target in tracking_ids.config_targets(pixel.get("configuration")):
            if target["kind"] == "ga4":
                add(ga4, target["target_id"].upper(), source)
        for target in web_pixels.purchase_targets(pixel):
            if target["kind"] == "google_ads" and target.get("label"):
                add(ads, (target["target_id"], target["label"]), source)
    for target, path in web_pixels.backup_targets(web_pixels.load_backups(ctx["workspace"])):
        if target["kind"] == "ga4":
            add(ga4, target["target_id"].upper(), f"gesichertes Custom Pixel ({path})")
        elif target["kind"] == "google_ads" and target.get("label"):
            add(ads, (target["target_id"], target["label"]), f"gesichertes Custom Pixel ({path})")
    return {"ga4": {k: v for k, v in ga4.items() if not dropped_reason(ctx, k)},
            "google_ads": {k: v for k, v in ads.items() if not dropped_reason(ctx, k[0], f"{k[0]}/{k[1]}")}}


def purchase_destinations(ctx: dict, targets: dict | None = None) -> tuple:
    """Ziele des Kaufs: Config, sonst Bestandsaufnahme, Mitschnitt des alten Themes und Messziele von vorher,
    ohne Gestrichenes."""
    configured = test_order.configured_destinations(migration_config(ctx["config"]).get("purchase_destinations"))
    used, senders = {}, {}
    for row in inventory_rows(ctx) or []:
        sid = str(row.get("service_id") or "")
        if sid in test_order.PURCHASE_SERVICES:
            used.setdefault(sid, "Bestandsaufnahme (apps.json)")
        if sid in test_order.SERVER_SENDERS and not dropped_reason(ctx, sid):
            senders[sid] = test_order.SERVER_SENDERS[sid]
    for entry in ctx["old"]["pages"].values():
        for key in third_party_keys(entry["runs"], own_hosts(ctx), ctx["catalog"], ctx["host_map"]):
            if key in test_order.PURCHASE_SERVICES:
                used.setdefault(key, "Mitschnitt des alten Themes")
            if key in test_order.SERVER_SENDERS and not dropped_reason(ctx, key):
                senders.setdefault(key, test_order.SERVER_SENDERS[key])
    # Eine Property oder Conversion, die nur ein Pixel in der Kasse bediente, macht ihren Dienst zum Ziel.
    for sid, key in (("google_analytics", "ga4"), ("google_ads", "google_ads")):
        if (targets or {}).get(key):
            used.setdefault(sid, "Messziele vor dem Launch (" + short_list(
                sorted({s for sources in targets[key].values() for s in sources}), 2) + ")")
    dropped = {sid: dropped_reason(ctx, sid) for sid in test_order.PURCHASE_SERVICES if dropped_reason(ctx, sid)}
    return test_order.derive_destinations(configured, used, dropped, senders), dropped


def destination_id(sid: str) -> str:
    return "purchase-" + sid.replace("_", "-")


def property_id(g_id: str) -> str:
    return "purchase-ga4-" + re.sub(r"[^a-z0-9]+", "-", g_id.lower()).strip("-")


def conversion_id(key: tuple) -> str:
    aw_id, label = key
    return "purchase-google-ads-" + re.sub(r"[^a-z0-9]+", "-", f"{aw_id[3:]}-{label}".lower()).strip("-")


def configured_properties(ctx: dict, targets: dict) -> dict:
    """GA4-Properties der Testbestellung: `ids` in `purchase_destinations.google_analytics`, sonst die von vorher."""
    configured = test_order.configured_destinations(migration_config(ctx["config"]).get("purchase_destinations"))
    ids = ((configured or {}).get("google_analytics") or {}).get("ids")
    if isinstance(ids, list):
        return {str(g).upper(): ["Config (theme_migration.purchase_destinations)"] for g in ids if str(g).strip()}
    return targets["ga4"]


def target_checks(ctx: dict, destinations: list, targets: dict) -> dict:
    """Je Dienst die Punkte der einzelnen Messziele: `{dienst: [(id, titel, kennung, herkunft)]}`.

    Jede GA4-Property, die der Shop vor dem Launch bediente, ist ein eigenes Ziel, ebenso jede
    Google-Ads-Kauf-Conversion mit Label. Bis 11.11.2026 genügte ein Kauf an irgendeine Property; eine
    zweite, die nur ein Pixel in der Kasse beliefert hatte, fiel so nicht auf.
    """
    ids = {d["id"] for d in destinations}
    out = {}
    if "google_analytics" in ids:
        out["google_analytics"] = [(property_id(g), f"Kauf kommt an: GA4-Property {g}", g, sources)
                                   for g, sources in sorted(configured_properties(ctx, targets).items())]
    if "google_ads" in ids:
        out["google_ads"] = [(conversion_id(k), f"Kauf kommt an: Google-Ads-Conversion {k[0]}/{k[1]}", k, sources)
                             for k, sources in sorted(targets["google_ads"].items())]
    return out


def target_purchase_check(ctx: dict, dest: dict, walk: dict, hits: list, spec: tuple) -> dict:
    """Ein einzelnes Messziel: ein Kauf-Aufruf von der Dankeseite an genau diese Property oder Conversion."""
    cid, title, key, sources = spec
    sid = dest["id"]
    if sid == "google_analytics":
        mine = [h for h in hits if str(h.get("id") or "").upper() == key]
        name, tool = key, f"GA4-Property {key} (Echtzeitbericht oder Bericht mit der Transaktions-ID)"
    else:
        aw_id, label = key
        mine = [h for h in hits if str(h.get("id")) == aw_id[3:] and h.get("label") == label]
        name, tool = f"{aw_id}/{label}", f"Google Ads (Conversion-Aktion mit dem Label {label})"
    origin = f"; vor dem Launch bedient laut {short_list(sources, 3)}"
    delivered = [h for h in mine if h["delivered"]]
    if delivered:
        doubled = test_order.repeated(delivered)
        note = (f"; {', '.join(f'{c}-mal' for _, c in doubled)} für dieselbe Kennung" if doubled else "")
        return make_check(cid, TEST_ORDER_GROUP, title, OK,
                          f"Kauf-Aufruf an {name}: {short_list([test_order.describe_hit(h) for h in delivered], 2)}"
                          + note + origin)
    if mine:
        return make_check(cid, TEST_ORDER_GROUP, title, MISSING,
                          f"Kauf-Aufruf an {name} gescheitert: "
                          f"{short_list([test_order.describe_hit(h) for h in mine], 2)}" + origin,
                          action="Einbindung prüfen, dann erneut testen", owner=OPERATOR)
    if dest.get("via"):
        return make_check(cid, TEST_ORDER_GROUP, title, MANUAL,
                          f"kein Kauf-Aufruf an {name} im Browser; der Kauf geht serverseitig über {dest['via']}" + origin,
                          question=f"Zeigt {tool} den Kauf der Testbestellung ({walk.get('token')})?", owner=BOTH)
    if not test_order.consent_given(walk):
        result = (walk.get("consent_result") or {}).get("result") or "ohne Ergebnis"
        return make_check(cid, TEST_ORDER_GROUP, title, BLOCKED,
                          f"Einwilligung im Testlauf nicht erteilt ({result}); ohne sie senden Pixel in "
                          "Consent-Regionen nicht" + origin,
                          action="walk_checkout mit --consent accepted", owner=OPERATOR)
    return make_check(cid, TEST_ORDER_GROUP, title, MISSING,
                      f"kein Kauf-Aufruf an {name} von der Dankeseite" + origin,
                      action="Absender für dieses Ziel wiederherstellen (gesichertes Custom Pixel, App oder Tag "
                             "Manager), dann erneut testen; entfällt es bewusst, mit Person und Grund in "
                             "decisions.json (Gegenstand: die Kennung)", owner=OPERATOR)


def test_order_approval(ctx: dict, walk: dict | None, destinations: list, dropped: dict,
                        per_target: dict | None = None) -> dict:
    title = "Testbestellung freigegeben"
    targets = ("; Ziele: " + ", ".join(test_order.LABELS[d["id"]] + (f" (über {d['via']})" if d.get("via") else "")
                                      for d in destinations)) if destinations else (
        "; keine Werbe- oder Analyseziele erkannt (theme_migration.purchase_destinations setzen)")
    for sid, label in (("google_analytics", "GA4-Properties"), ("google_ads", "Google-Ads-Kauf-Conversions")):
        specs = (per_target or {}).get(sid) or []
        if specs:
            targets += f"; {label}: " + short_list([s[1].rsplit(" ", 1)[-1] for s in specs], 6)
    if dropped:
        targets += "; bewusst entfallen: " + "; ".join(sorted(set(dropped.values())))
    if walk:
        return make_check("test-order", TEST_ORDER_GROUP, title, OK,
                          f"freigegeben von {walk.get('approved_by')}, Kasse durchlaufen ab "
                          f"{str(walk.get('started_at'))[:16]}" + (", Probelauf ohne Bestellung" if walk.get("headless")
                                                                   else "") + targets)
    return make_check("test-order", TEST_ORDER_GROUP, title, MANUAL,
                      "keine Testbestellung im Workspace (test-order/walk.json); Kasse, Dankeseite und Kauf-Ereignisse "
                      "zeigt nur eine Bestellung" + targets,
                      question="Gebt ihr eine Testbestellung frei? Ich gehe die Kasse bis zur Zahlung durch, ihr setzt "
                               "die Bestellung ab; danach wird sie storniert und erstattet.", owner=TEAM)


def test_order_declined(ctx: dict) -> str | None:
    """Beleg, wenn das Team die Testbestellung ausdrücklich abgelehnt hat (Antwort n/a mit Namen)."""
    answer = ctx["answers"].get("test-order")
    if isinstance(answer, dict) and answer.get("status") == NA and str(answer.get("by", "")).strip():
        return f"Testbestellung abgelehnt von {answer['by']}" + (f" am {answer['at']}" if answer.get("at") else "")
    return None


def checkout_walk_check(ctx: dict, walk: dict, walk_path: Path, completed: bool) -> dict:
    """Kasse bis zur Zahlung: Warenkorb, Steuer- und Versandhinweis, Versandarten, Zahlung."""
    title = "Kasse bis zur Zahlung"
    stages = {s.get("stage"): s for s in walk.get("stages") or []}
    problems, unverified, notes = [], [], []
    for name, label in (("product", "Produktseite"), ("add_to_cart", "In den Warenkorb"), ("cart", "Warenkorb"),
                        ("checkout", "Kasse")):
        entry = stages.get(name)
        if not entry:
            unverified.append(f"{label} nicht erreicht")
        elif entry.get("state") == "failed":
            problems.append(f"{label}: {entry.get('evidence')}")
        elif name in ("add_to_cart", "cart"):
            notes.append(f"{label}: {entry.get('evidence')}")
    for name, label in (("cart", "Warenkorb"), ("checkout", "Kasse")):
        entry = stages.get(name) or {}
        if entry.get("state") != "ok":
            continue
        notices = entry.get("notices") or {}
        for kind, text in (("tax", "Steuerhinweis"), ("shipping", "Versandhinweis")):
            if notices.get(kind):
                notes.append(f"{label}, {text}: „{notices[kind][:80]}“")
            else:
                problems.append(f"{label} ohne {text}")
    for name, label in (("shipping", "Versandarten"), ("payment", "Zahlung")):
        entry = stages.get(name) or {}
        if entry.get("state") == "ok":
            notes.append(f"{label}: {str(entry.get('evidence'))[:120]}")
        elif completed:
            notes.append(f"{label}: durch die abgesetzte Bestellung belegt")
        elif entry.get("state") == "failed":
            problems.append(f"{label}: {entry.get('evidence')}")
        else:
            unverified.append(f"{label} nicht geprüft ({entry.get('evidence') or 'Stufe nicht erreicht'})")
    status = MISSING if problems else (BLOCKED if unverified else OK)
    evidence = "; ".join(problems + unverified + notes)
    links = [{"label": f"Bild {s.get('stage')}", "url": run_relative(ctx, walk_path, s.get("screenshot"))}
             for s in walk.get("stages") or [] if s.get("screenshot")
             and s.get("stage") in ("cart", "checkout", "shipping", "payment", "thank_you")][:5]
    return make_check("checkout-walk", TEST_ORDER_GROUP, title, status, evidence,
                      action={MISSING: "Ursache im Theme oder in den Kasseneinstellungen beheben, dann walk_checkout "
                                       "erneut", BLOCKED: "walk_checkout mit --contact (Testadresse des Teams) oder die "
                                                          "Testbestellung absetzen"}.get(status, ""),
                      owner=OPERATOR if status != OK else "", links=links)


def shopify_order_check(ctx: dict, walk: dict, order, error) -> dict:
    title = f"Kauf kommt an: {test_order.LABELS['shopify']}"
    marked = (test_order.stage(walk, "mark").get("state") == "ok")
    if error:
        return make_check("purchase-shopify", TEST_ORDER_GROUP, title, BLOCKED, f"Bestellungen nicht lesbar: {error}",
                          action="Grant um read_orders erweitern", owner=OPERATOR)
    if order:
        amount, currency = test_order.order_amount(order)
        url = test_order.admin_order_url(ctx["store"], order)
        return make_check("purchase-shopify", TEST_ORDER_GROUP, title, OK,
                          f"Bestellung {order.get('name')} vom {str(order.get('createdAt'))[:16]}, {amount} {currency}, "
                          f"Zahlungsstatus {order.get('displayFinancialStatus')}"
                          + (", Testmodus der Zahlung" if order.get("test") else "")
                          + f"; gefunden über das Warenkorb-Attribut {test_order.TOKEN_KEY}={walk.get('token')}",
                          links=[{"label": "Bestellung im Admin", "url": url}] if url else [])
    if walk.get("headless"):
        return make_check("purchase-shopify", TEST_ORDER_GROUP, title, BLOCKED, "Probelauf ohne Bestellung (--headless)",
                          action="walk_checkout ohne --headless, die Bestellung setzt ein Mensch ab", owner=TEAM)
    if not marked:
        return make_check("purchase-shopify", TEST_ORDER_GROUP, title, BLOCKED,
                          "Kennung im Warenkorb nicht gesetzt, die Bestellung lässt sich nicht zuordnen; "
                          + str(test_order.stage(walk, "mark").get("evidence") or "Stufe nicht erreicht"),
                          action="die Bestellung im Admin von Hand suchen oder walk_checkout erneut", owner=OPERATOR)
    if (walk.get("thank_you") or {}).get("reached"):
        return make_check("purchase-shopify", TEST_ORDER_GROUP, title, MISSING,
                          f"Dankeseite erreicht ({(walk['thank_you'].get('order_text') or walk['thank_you'].get('url'))}), "
                          f"aber keine Bestellung mit {test_order.TOKEN_KEY}={walk.get('token')} seit "
                          f"{str(walk.get('started_at'))[:16]}",
                          action="im Admin nach der Bestellung sehen; fehlt sie, die Kasse sofort prüfen", owner=OPERATOR)
    return make_check("purchase-shopify", TEST_ORDER_GROUP, title, BLOCKED,
                      "keine Dankeseite und keine Bestellung mit der Kennung; die Bestellung wurde nicht abgesetzt",
                      action="walk_checkout erneut, die Bestellung im geöffneten Fenster absetzen", owner=TEAM)


def ga4_purchase_check(ctx: dict, dest: dict, walk: dict, hits: list, order) -> dict:
    """GA4: Bericht je Transaktions-ID, wenn es einen Zugang gibt; sonst der Aufruf im Browser."""
    cid, title = destination_id("google_analytics"), "Kauf kommt an: GA4"
    via = dest.get("via")
    delivered = [h for h in hits if h["delivered"]]
    browser = (f"im Browser: {short_list([test_order.describe_hit(h) for h in hits], 3)}" if hits
               else "im Browser kein purchase an GA4")
    reader, reason = ctx["ga4"]

    def made(status, evidence, action="", question=""):
        return make_check(cid, TEST_ORDER_GROUP, title, status, f"{evidence}; Ziel laut {dest['source']}",
                          action=action, question=question, owner=OPERATOR if status != OK else "")

    access = "ga4_property_id in reporting/config.json und PTAI_GOOGLE_CREDENTIALS setzen, dann erneut prüfen"
    if reader is None:
        if via:
            return made(BLOCKED, f"Kauf geht serverseitig über {via} an GA4; ohne Lesezugang nicht prüfbar ({reason}); "
                                 f"{browser}", action=access)
        if delivered:
            doubled = test_order.repeated(delivered)
            if doubled:
                return made(MISSING, f"purchase mehrfach gesendet ({', '.join(f'{c}-mal' for _, c in doubled)}); "
                                     f"{browser}", action="doppelten Absender abschalten")
            return made(OK, f"purchase an GA4 gesendet; {browser}; Bericht nicht geprüft ({reason})")
        if hits:
            return made(MISSING, f"purchase an GA4 gescheitert; {browser}", action="Einbindung prüfen")
        if not test_order.consent_given(walk):
            return made(BLOCKED, f"Einwilligung im Testlauf nicht erteilt; {browser}; Bericht nicht geprüft ({reason})",
                        action=access)
        return made(MISSING, f"kein purchase an GA4 von der Dankeseite; Bericht nicht geprüft ({reason})",
                    action="GA4-Einbindung der Kasse prüfen (Custom Pixel, App oder Connector)")
    candidates = test_order.order_candidates(order, hits)
    if not candidates:
        return made(BLOCKED, f"ohne Bestellnummer nicht im Bericht suchbar; {browser}",
                    action="Bestellung im Admin suchen und als --test-order nachtragen")
    placed = test_order.parse_time((order or {}).get("createdAt")) or test_order.parse_time(
        (walk.get("thank_you") or {}).get("at")) or test_order.parse_time(walk.get("started_at"))
    start = ((placed or datetime.now(timezone.utc)) - timedelta(days=1)).date().isoformat()
    data, error = test_order.safe_call(reader.transactions, candidates, start)
    if error:
        return made(BLOCKED, f"GA4-Bericht nicht lesbar ({error}); {browser}", action=access)
    rows = [r for r in data["rows"] if r["purchases"]]
    if rows:
        total = sum(r["purchases"] for r in rows)
        found = short_list([f"{r['transaction']}: {r['purchases']}-mal, Umsatz {r['revenue']} {data.get('currency') or ''}"
                            .strip() for r in rows])
        if total > 1:
            return made(MISSING, f"Bestellung im GA4-Bericht {total}-mal als Kauf gezählt ({found}), Property "
                                 f"{reader.prop}; {browser}",
                        action="einen Absender abschalten (Browser-Pixel oder " + (via or "Connector") + ")")
        return made(OK, f"im GA4-Bericht: {found}, Property {reader.prop}; {browser}")
    age = datetime.now(timezone.utc) - placed if placed else None
    hours = int(age.total_seconds() // 3600) if age else None
    if age and age >= timedelta(hours=test_order.GA4_REPORT_DELAY_HOURS):
        return made(MISSING, f"nach {hours} Stunden kein Kauf mit Transaktions-ID {short_list(candidates, 4)} im Bericht "
                             f"der Property {reader.prop}; {browser}",
                    action="Absender prüfen" + (f" ({via})" if via else "") + "; Kasse erneut testen")
    realtime = ""
    minutes = int(age.total_seconds() // 60) + 1 if age else None
    if minutes is not None and minutes <= test_order.GA4_REALTIME_MINUTES:
        count, rt_error = test_order.safe_call(reader.realtime_purchases, minutes)
        realtime = (f"; Echtzeit: {count} purchase in den letzten {minutes} Minuten, ohne Transaktions-ID nicht "
                    "zuordenbar" if rt_error is None else f"; Echtzeit nicht lesbar ({rt_error})")
    retry = ((placed or datetime.now(timezone.utc)) + timedelta(hours=24)).strftime("%d.%m.%Y")
    return made(BLOCKED, f"noch nicht im GA4-Bericht (Verarbeitung bis {test_order.GA4_REPORT_DELAY_HOURS} Stunden, "
                         f"Bestellung vor {hours if hours is not None else '?'} Stunden){realtime}; {browser}",
                action=f"launch-check --after ab {retry} erneut laufen lassen; der Durchlauf wird wiedergefunden")


def pixel_purchase_check(ctx: dict, dest: dict, walk: dict, hits: list) -> dict:
    """Werbe-Pixel ohne Leseweg: der Kauf-Aufruf von der Dankeseite ist der Beleg."""
    sid = dest["id"]
    label = test_order.LABELS[sid]
    cid, title = destination_id(sid), f"Kauf kommt an: {label}"
    via = dest.get("via")
    delivered = [h for h in hits if h["delivered"]]
    source = f"; Ziel laut {dest['source']}"
    ads_note = ("; im Konto erscheint eine Testbestellung ohne Anzeigenklick nie, geprüft ist der Aufruf"
                if sid == "google_ads" else "")
    if delivered:
        doubled = test_order.repeated(delivered)
        note = (f"; {', '.join(f'{c}-mal' for _, c in doubled)} für dieselbe Kennung, im Werkzeug auf doppelte "
                "Zählung prüfen") if doubled else ""
        return make_check(cid, TEST_ORDER_GROUP, title, OK,
                          f"Kauf-Aufruf von der Dankeseite: {short_list([test_order.describe_hit(h) for h in delivered], 3)}"
                          + note + ads_note + source)
    if hits:
        return make_check(cid, TEST_ORDER_GROUP, title, MISSING,
                          f"Kauf-Aufruf gescheitert: {short_list([test_order.describe_hit(h) for h in hits], 3)}" + source,
                          action="Einbindung prüfen, dann erneut testen", owner=OPERATOR)
    if via:
        return make_check(cid, TEST_ORDER_GROUP, title, MANUAL,
                          f"Kauf geht serverseitig über {via} an {label}; dafür gibt es keinen Lesezugang" + source,
                          question=f"Zeigt {test_order.TOOLS.get(sid, label)} den Kauf der Testbestellung "
                                   f"({walk.get('token')})?", owner=BOTH)
    if not test_order.consent_given(walk):
        result = (walk.get("consent_result") or {}).get("result") or "ohne Ergebnis"
        return make_check(cid, TEST_ORDER_GROUP, title, BLOCKED,
                          f"Einwilligung im Testlauf nicht erteilt ({result}); ohne sie senden Werbe-Pixel in "
                          "Consent-Regionen nicht" + source,
                          action="walk_checkout mit --consent accepted; erkennt consent.py den Dialog nicht, Knopf "
                                 "ergänzen", owner=OPERATOR)
    count = sum(1 for r in walk.get("requests") or [] if r.get("stage") in test_order.PURCHASE_STAGES)
    return make_check(cid, TEST_ORDER_GROUP, title, MISSING,
                      f"kein Kauf-Aufruf an {label} von der Dankeseite ({count} Anfragen ab der Übergabe mitgeschnitten)"
                      + ads_note + source,
                      action="Pixel oder App-Einbindung der Kasse prüfen; läuft der Kauf serverseitig, in "
                             "theme_migration.purchase_destinations mit via eintragen", owner=OPERATOR)


def refund_check(ctx: dict, order, error, reason: str | None) -> dict:
    title = "Testbestellung storniert und erstattet"
    if reason:
        return make_check("test-order-refund", TEST_ORDER_GROUP, title, BLOCKED, reason)
    if error:
        return make_check("test-order-refund", TEST_ORDER_GROUP, title, BLOCKED, f"Bestellungen nicht lesbar: {error}",
                          action="Grant um read_orders erweitern", owner=OPERATOR)
    if not order:
        return make_check("test-order-refund", TEST_ORDER_GROUP, title, BLOCKED, "keine Testbestellung gefunden")
    amount, currency = test_order.order_amount(order)
    cancelled = order.get("cancelledAt")
    financial = order.get("displayFinancialStatus")
    url = test_order.admin_order_url(ctx["store"], order)
    links = [{"label": "Bestellung im Admin", "url": url}] if url else []
    if cancelled and (financial in ("REFUNDED", "VOIDED") or amount == 0):
        return make_check("test-order-refund", TEST_ORDER_GROUP, title, OK,
                          f"{order.get('name')} storniert am {str(cancelled)[:10]}, Zahlungsstatus {financial}", links=links)
    return make_check("test-order-refund", TEST_ORDER_GROUP, title, MANUAL,
                      f"{order.get('name')}: storniert {str(cancelled)[:10] if cancelled else 'nein'}, Zahlungsstatus "
                      f"{financial}",
                      question=f"Storniert und erstattet ihr die Testbestellung {order.get('name')} ({amount} {currency}) "
                               "im Admin, sobald alle Ziele geprüft sind? Der nächste Lauf liest den Stand aus der "
                               "Bestellung.", owner=TEAM, links=links)


def check_test_order(ctx: dict) -> list:
    """Testbestellung: Freigabe, Kasse bis zur Zahlung, Kauf je Ziel, Storno und Erstattung.

    Schreibt nie in den Shop: die Bestellung setzt ein Mensch ab, Storno und
    Erstattung macht das Team; gelesen wird die Bestellung über das
    Warenkorb-Attribut aus dem Durchlauf.
    """
    walk_path, walk = find_walk(ctx)
    targets = purchase_targets(ctx)
    destinations, dropped = purchase_destinations(ctx, targets)
    per_target = target_checks(ctx, destinations, targets)
    out = [test_order_approval(ctx, walk, destinations, dropped, per_target)]
    checks = [("checkout-walk", "Kasse bis zur Zahlung"), ("purchase-shopify", "Kauf kommt an: Shopify-Bestellung")]
    for d in destinations:
        checks.append((destination_id(d["id"]), f"Kauf kommt an: {test_order.LABELS[d['id']]}"))
        checks += [(spec[0], spec[1]) for spec in per_target.get(d["id"]) or []]
    checks += [("test-order-refund", "Testbestellung storniert und erstattet")]
    if walk is None:
        declined = test_order_declined(ctx)
        status = NA if declined else BLOCKED
        evidence = declined or "keine Testbestellung (test-order/walk.json fehlt)"
        action = "" if declined else ("nach Freigabe walk_checkout.py --approved-by <Name>; die Bestellung setzt ein "
                                      "Mensch im geöffneten Fenster ab")
        return out + [make_check(cid, TEST_ORDER_GROUP, title, status, evidence, action=action,
                                 owner=OPERATOR if action else "") for cid, title in checks]
    since = test_order.parse_time(walk.get("started_at"))
    since = since - timedelta(minutes=10) if since else None
    order, error = (None, None)
    if not walk.get("headless") and walk.get("token"):
        order, error = shop(ctx, "test-order", test_order.find_order, walk["token"], since)
    completed = bool(order) or bool((walk.get("thank_you") or {}).get("reached"))
    out.append(checkout_walk_check(ctx, walk, walk_path, completed))
    out.append(shopify_order_check(ctx, walk, order, error))
    hits = test_order.purchase_hits(walk.get("requests"))
    pending = ("Probelauf ohne Bestellung (--headless)" if walk.get("headless") else
               None if completed else "Bestellung nicht abgeschlossen: keine Dankeseite und keine Bestellung mit der "
                                      "Kennung")
    for dest in destinations:
        specs = per_target.get(dest["id"]) or []
        if pending:
            out += [make_check(cid, TEST_ORDER_GROUP, title, BLOCKED, pending,
                               action="Testbestellung absetzen, dann erneut prüfen", owner=TEAM)
                    for cid, title in [(destination_id(dest["id"]), f"Kauf kommt an: {test_order.LABELS[dest['id']]}")]
                    + [(s[0], s[1]) for s in specs]]
            continue
        mine = [h for h in hits if h["service"] == dest["id"]]
        out.append(ga4_purchase_check(ctx, dest, walk, mine, order) if dest["id"] == "google_analytics"
                   else pixel_purchase_check(ctx, dest, walk, mine))
        out += [target_purchase_check(ctx, dest, walk, mine, spec) for spec in specs]
    out.append(refund_check(ctx, order, error, pending))
    return out


def check_after_rest(ctx: dict) -> list:
    group = "Abschluss"
    out = []
    url = f"{ctx['base_url']}/sitemap.xml"
    fetched, error = safe(ctx["fetch"], url)
    if not fetched or fetched[0] != 200:
        out.append(make_check("sitemap-after", group, "Sitemap", MISSING,
                              f"{url} " + (f"antwortet {fetched[0]}" if fetched else f"nicht abrufbar ({error})"),
                              action="Ursache klären", owner=OPERATOR))
    else:
        out.append(make_check("sitemap-after", group, "Sitemap", MANUAL, f"{url} antwortet 200",
                              question="Ist die Sitemap in der Search Console neu eingereicht?", owner=OPERATOR))
    state = ctx["state"]
    if state:
        values = state.get("values") or {}
        done = values.get("published_at") and str(values.get("live_theme_id")) == ctx["new_id"] \
            and values.get("rollback_theme_id")
        evidence = (f"published_at {values.get('published_at') or 'fehlt'}, live_theme_id "
                    f"{values.get('live_theme_id') or 'fehlt'}, Rückfall-Theme {values.get('rollback_theme_id') or 'fehlt'}")
        if values.get("launch_approved_by"):
            evidence += f", veröffentlicht nach Ja von {values['launch_approved_by']}"
        out.append(make_check("record-after", group, "Stand festgehalten", OK if done else MISSING, evidence,
                              action="" if done else "run_state set für published_at, live_theme_id und "
                                                     "rollback_theme_id, Config nachziehen",
                              owner="" if done else OPERATOR))
    else:
        out.append(make_check("record-after", group, "Stand festgehalten", MANUAL, "kein Migrationslauf im Workspace",
                              question="Sind Zeitpunkt, neue Live-Theme-ID und Rückfall-Theme-ID festgehalten?",
                              owner=OPERATOR))
    return out


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def apply_answers(checks: list, answers: dict) -> None:
    """Antworten gelten nur für Punkte, die einen Menschen brauchen; nie über einen Befund hinweg."""
    for check in checks:
        answer = answers.get(check["id"])
        if check["status"] != MANUAL or not isinstance(answer, dict):
            continue
        if answer.get("status") not in (OK, MISSING, NA) or not str(answer.get("by", "")).strip():
            continue
        check["status"] = answer["status"]
        check["evidence"] += f"; Antwort von {answer['by']}" + (f" am {answer['at']}" if answer.get("at") else "") \
            + (f": {answer['note']}" if answer.get("note") else "")
        if answer["status"] != MISSING:
            check["question"] = ""


def recommend(checks: list) -> str:
    statuses = {c["status"] for c in checks}
    if MISSING in statuses:
        return "no_go"
    if statuses & {BLOCKED, MANUAL}:
        return "open"
    return "go"


def collect(ctx: dict) -> list:
    if ctx["after"]:
        checks = check_published(ctx) + [check_injections(ctx), check_consent_app_after(ctx)] + check_after_seo(ctx) \
            + check_seo_output(ctx, after=True) + check_tracking(ctx, after=True) + [check_consent_after(ctx)] \
            + [check_pre_consent(ctx), check_web_pixels_after(ctx)] + check_funnel_events(ctx) \
            + check_funnel_realtime(ctx) + check_pagination(ctx) \
            + check_test_order(ctx) + check_after_languages(ctx) + check_after_rest(ctx)
    else:
        seo = [check_seo_robots(ctx, "SEO"), check_seo_pages(ctx, "SEO")] + check_seo_output(ctx)
        statuses = {c["id"]: c["status"] for c in seo}
        # Ohne Liste zählt die Prüfliste einen Punkt als abgedeckt, wenn die SEO-Prüfung dazu bestanden ist.
        # Mit Liste stehen ihre Punkte dort, und check_open_items prüft sie.
        checklist = [] if ledger_mode(ctx) else [check_checklist(ctx, statuses)]
        checks = (check_timing(ctx) + check_acceptance(ctx, statuses) + checklist + check_sync(ctx) + check_draft(ctx)
                  + check_embeds(ctx) + [check_injections(ctx)] + check_translations(ctx) + check_tracking(ctx)
                  + [check_pre_consent(ctx)] + check_web_pixels(ctx) + check_funnel_events(ctx) + check_pagination(ctx)
                  + seo + check_baseline(ctx) + check_criteria(ctx) + check_go_decision(ctx)
                  + check_customer_accounts(ctx)
                  + check_script_tags(ctx))
    apply_answers(checks, ctx["answers"])
    return checks


def build_report(ctx: dict, checks: list) -> dict:
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in STATUS_ORDER}
    return {
        "kind": "launch-check", "mode": "after" if ctx["after"] else "before", "checked_at": now_utc(),
        "store": ctx["store"], "domain": ctx["base_url"], "old_theme_id": ctx["old_id"], "new_theme_id": ctx["new_id"],
        "launch_date": ctx["launch_date"].isoformat() if ctx["launch_date"] else None,
        "migration_run": ctx["state_run_id"], "answers_file": ctx["answers_file"],
        "captures": {"old": ctx["old"]["files"], "new": ctx["new"]["files"]},
        "recommendation": recommend(checks), "counts": counts, "checks": checks,
    }


def render_markdown(report: dict) -> str:
    after = report["mode"] == "after"
    recommendation = RECOMMENDATION_LABEL[report["recommendation"]]
    lines = [f"# Launch-Check {'nach dem Veröffentlichen' if after else 'vor dem Launch'}", ""]
    lines.append(f"**Empfehlung: {recommendation}.** "
                 + {"go": "Alle Punkte sind erfüllt oder treffen nicht zu.",
                    "no_go": "Mindestens ein Punkt fehlt; erst beheben, dann neu prüfen.",
                    "open": "Nichts fehlt, aber Punkte sind nicht prüfbar oder brauchen eine Antwort."}[report["recommendation"]]
                 + " Die Entscheidung trifft ein Mensch.")
    lines.append("")
    counts = report["counts"]
    lines.append(" · ".join(f"{STATUS_LABEL[s]} {counts[s]}" for s in STATUS_ORDER))
    lines.append("")
    base = report["domain"]
    old_label, new_label = ("Altes Theme", "Neues Theme") if after else ("Live", "Entwurf")
    if report["new_theme_id"]:
        lines.append(f"- {new_label}: [{report['new_theme_id']}]({preview_url(base, '/', report['new_theme_id'])})")
    if report["old_theme_id"]:
        lines.append(f"- {old_label}: [{report['old_theme_id']}]({preview_url(base, '/', report['old_theme_id'])})")
    if report["launch_date"]:
        lines.append(f"- Launch-Termin: {date.fromisoformat(report['launch_date']).strftime('%d.%m.%Y')}")
    lines.append(f"- Geprüft: {report['checked_at']}"
                 + (f", Migrationslauf {report['migration_run']}" if report["migration_run"] else ", ohne Migrationslauf"))
    lines.append("")
    for status in STATUS_ORDER:
        items = [c for c in report["checks"] if c["status"] == status]
        if not items:
            continue
        lines += [f"## {STATUS_LABEL[status]} ({len(items)})", ""]
        for c in items:
            lines.append(f"- **{c['title']}** ({c['group']}): {c['evidence']}")
            if c["question"]:
                lines.append(f"  - Frage an {c['owner'] or 'Betreiber'}: {c['question']}")
            elif c["action"]:
                lines.append(f"  - Zu tun ({c['owner'] or 'Betreiber'}): {c['action']}")
            if c["links"]:
                lines.append("  - " + " · ".join(f"[{l['label']}]({l['url']})" for l in c["links"]))
        lines.append("")
    if after:
        lines += ["Ab jetzt laufen Umsatz, Conversion Rate, Fehlerseiten und Kaufabbrüche unter Beobachtung, die "
                  "ersten 48 Stunden eng (post-launch.md).", ""]
    return "\n".join(lines)


def run(ctx: dict) -> tuple:
    checks = collect(ctx)
    report = build_report(ctx, checks)
    name = "launch-check" + ctx["suffix"]
    write_json(ctx["run_dir"] / f"{name}.json", report)
    write_text(ctx["run_dir"] / f"{name}.md", render_markdown(report))
    return report, EXIT_OK if report["recommendation"] == "go" else EXIT_FINDINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="theme.launch_check", description=__doc__.split("\n\n")[0])
    parser.add_argument("--after", action="store_true", help="Prüfungen direkt nach dem Veröffentlichen")
    parser.add_argument("--live-theme-id", help="Theme, das vor dem Launch live ist (Rückfall-Theme)")
    parser.add_argument("--draft-theme-id", help="Entwurf, der veröffentlicht wird")
    parser.add_argument("--launch-date", help="geplanter Tag des Veröffentlichens, JJJJ-MM-TT")
    parser.add_argument("--run-id", help="Standard <heute>-launch-check")
    parser.add_argument("--pages", help="pages.json für Links und Abrufe")
    parser.add_argument("--network-old", action="append", default=[], help="network.json des alten Themes")
    parser.add_argument("--network-new", action="append", default=[], help="network.json des neuen Themes")
    parser.add_argument("--test-order", help="walk.json der Testbestellung; Standard <lauf>/test-order/walk.json, "
                                             "sonst der jüngste Durchlauf der letzten sieben Tage")
    parser.add_argument("--answers", help="Antworten auf manuelle Punkte, Standard reporting/launch-answers.json")
    parser.add_argument("--workspace", default=".")
    return parser


def execute(args, *, transport=None, fetch=None, sleep=None, ga4=None, ga4_props=None) -> tuple:
    """Ein Prüflauf aus fertigen Argumenten: `(report, exit_code, ctx)`. Wirft `ConfigError`, `OSError` oder
    `ValueError`; `main` und `theme.launch` fangen sie."""
    workspace = Path(args.workspace)
    config = load_config(workspace)
    ctx = build_context(args, config, workspace, transport=transport)
    if ga4 is not None:
        ctx["ga4"] = (ga4, None)
    if ga4_props is not None:
        # Für Tests: je Property-ID ein Leser; eine fehlende Property ist nicht lesbar.
        ctx["ga4_for"] = lambda prop: ((ga4_props[prop], None) if prop in ga4_props
                                       else (None, f"kein Zugang zu Property {prop}"))
    ctx["fetch"] = fetch or http_fetch
    ctx["sleep"] = sleep or time.sleep
    report, code = run(ctx)
    return report, code, ctx


def main(argv: list[str] | None = None, *, transport=None, fetch=None, sleep=None, ga4=None, ga4_props=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report, code, ctx = execute(args, transport=transport, fetch=fetch, sleep=sleep, ga4=ga4, ga4_props=ga4_props)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    name = "launch-check" + ctx["suffix"]
    emit({"ok": True, "mode": report["mode"], "recommendation": report["recommendation"], "counts": report["counts"],
          "out": str(ctx["run_dir"] / f"{name}.md")})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
