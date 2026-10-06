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

Ein Migrationslauf (`run_state`) ist optional: ohne ihn kommen die Theme-IDs aus
`theme_migration` der Config oder aus `--live-theme-id` und `--draft-theme-id`.
Antworten auf `manual`-Punkte stehen in `reporting/launch-answers.json` und
gelten bei jedem weiteren Lauf, mit Name und Datum dessen, der geantwortet hat.

CLI:
    python3 -m theme.launch_check [--after] [--live-theme-id <id>] [--draft-theme-id <id>]
        [--launch-date YYYY-MM-DD] [--run-id <id>] [--pages <pages.json>]
        [--network-old <network.json> ...] [--network-new <network.json> ...]
        [--answers <file>] [--workspace .]

Schreibt `reporting/runs/<date>-launch-check/launch-check.json` und
`launch-check.md` (mit `--after`: `launch-check-after.*`). Exit 0 heißt Go,
1 heißt No-Go oder offen, 2 heißt Fehler.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from theme import (EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config,
                   now_utc, write_json)
from theme import apps, run_state
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
LAUNCH_SEVERITIES = ("blocker", "before_launch")
#: Status eines Befunds oder Testpunkts, der nichts mehr verlangt.
CLOSED = ("done", "resolved", "fixed", "closed", "accepted", "wontfix")
#: Status eines Testpunkts, an dem noch etwas zu tun ist (test-round).
OPEN_TEST_STATUS = ("open", "in_progress", "decision")
#: Vergleichswerte, die direkt vor dem Launch gezogen werden, mit Quelle in `sources`.
BASELINE_FILES = {"gsc.json": "gsc", "ga4.json": "ga4", "cwv.json": "cwv", "crawl.json": "crawl"}
#: So viele Wochen vor Black Friday beginnt die Saisonspitze für den Launch.
SEASON_LEAD = timedelta(days=28)
#: Pause zwischen zwei Abrufen der Storefront; sie verträgt keine Parallelität.
FETCH_PAUSE = 2.0
USER_AGENT = "ptai-ecom launch-check"


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
                       _base=data.get("base_url"))
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


def third_party_keys(runs: list, own_hosts: set, catalog) -> set:
    """Dienste oder Domains, die eine Seite lädt, ohne eigene Domain und ohne Shopify selbst.

    Unbekannte Hosts zählen über ihre Domain, damit wechselnde Subdomains
    (Werbe-Auktionen, Lastverteiler) keine Scheinlücke erzeugen.
    """
    keys = set()
    for run in runs:
        for request in run.get("requests") or []:
            host = (urlparse(request.get("url") or "").hostname or "").lower()
            if not host or host in own_hosts or any(host.endswith("." + h) for h in own_hosts):
                continue
            if catalog.ignored(host):
                continue
            sid = catalog.service_for_url(request["url"])
            if catalog.is_platform(sid):
                continue
            keys.add(sid or registrable(host))
    return keys


def compare_tracking(old: dict, new: dict, own_hosts: set, catalog) -> dict:
    """Je Seite und Consent-Zustand: was alt lädt und neu fehlt, was neu dazukommt."""
    result = {"missing": [], "added": [], "pages": 0, "wrong_theme": [], "unmatched": []}
    for page_id, old_entry in sorted(old["pages"].items(), key=lambda kv: str(kv[0])):
        new_entry = new["pages"].get(page_id)
        if not new_entry:
            result["unmatched"].append(page_id)
            continue
        result["wrong_theme"] += [f"{page_id} ({r.get('device')})" for r in new_entry["runs"]
                                  if r.get("state") == "wrong_theme"]
        for mode in sorted({r.get("consent") for r in old_entry["runs"]} & {r.get("consent") for r in new_entry["runs"]}):
            before = third_party_keys([r for r in old_entry["runs"] if r.get("consent") == mode
                                       and r.get("state") == "ok"], own_hosts, catalog)
            after = third_party_keys([r for r in new_entry["runs"] if r.get("consent") == mode
                                      and r.get("state") == "ok"], own_hosts, catalog)
            result["pages"] += 1
            for key in sorted(before - after):
                result["missing"].append({"page_id": page_id, "path": old_entry.get("path"), "consent": mode,
                                          "service": key, "name": catalog.describe(key)["service_name"]})
            for key in sorted(after - before):
                result["added"].append({"page_id": page_id, "consent": mode, "service": key})
    return result


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
    freeze = block.get("freeze") or {}
    launch = args.launch_date or values.get("freeze_until") or freeze.get("until")
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
    # Vor dem Launch ist das alte Theme das Live-Theme und das neue der Entwurf; danach dieselben zwei.
    return {
        "workspace": workspace, "config": config, "after": args.after, "base_url": domain.rstrip("/"),
        "store": config.get("shopify_store", ""), "old_id": live_id and numeric_id(live_id),
        "new_id": draft_id and numeric_id(draft_id), "launch_date": launch_date, "today": date.today(),
        "state": state, "state_run_id": run_id, "state_error": state_error, "transport": transport,
        "transport_error": transport_error, "run_dir": run_dir, "suffix": suffix,
        "old": load_captures(network_old), "new": load_captures(network_new),
        "pages_file": pages_file, "answers": answers, "answers_file": str(answers_file),
        "catalog": apps.HostCatalog.load(), "cache": {},
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
                              "kein Termin bekannt (--launch-date, freeze_until im Migrationslauf oder in der Config)",
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
                    for k in third_party_keys(entry["runs"], own_hosts(ctx), ctx["catalog"])
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


def latest_test_round(workspace: Path):
    path = newest((workspace / "reporting" / "runs").glob("*-test/test.json"))
    return path, read_json(path) if path else None


def check_acceptance(ctx: dict) -> list:
    group = "Abnahme und offene Befunde"
    out = []
    state = ctx["state"]
    if state:
        gate = (state.get("gates") or {}).get("G4-acceptance")
        out.append(make_check(
            "acceptance-decision", group, "Abnahme (G4)", OK if gate else MISSING,
            f"entschieden von {gate['decided_by']} am {gate['decided_at'][:10]}" if gate
            else f"Gate G4 im Migrationslauf {ctx['state_run_id']} offen",
            action="" if gate else "Testrunde abschließen und die Abnahme beim Team einholen", owner="" if gate else TEAM))
    else:
        out.append(make_check("acceptance-decision", group, "Abnahme", MANUAL,
                              "kein Migrationslauf im Workspace" + (f" ({ctx['state_error']})" if ctx["state_error"] else ""),
                              question="Hat das Team den Entwurf abgenommen? Wer, an welchem Tag?", owner=TEAM))
    path, findings = latest_verify_findings(ctx["workspace"])
    if findings is None:
        out.append(make_check("acceptance-findings", group, "Befunde aus der Prüfung", MANUAL,
                              "kein Prüfbericht unter migration/verify/",
                              question="Sind alle Befunde der Schwere blocker und before_launch erledigt?",
                              action="verify-theme laufen lassen, wenn es keinen Prüfbericht gibt", owner=OPERATOR))
    else:
        open_items = [f for f in findings if isinstance(f, dict) and f.get("severity") in LAUNCH_SEVERITIES
                      and str(f.get("status", "")).lower() not in CLOSED]
        rel = path.relative_to(ctx["workspace"]).as_posix()
        out.append(make_check(
            "acceptance-findings", group, "Befunde aus der Prüfung", MISSING if open_items else OK,
            (f"{len(open_items)} offen in {rel}: "
             + short_list([f"{f.get('severity')}: {str(f.get('description') or f.get('title') or '')[:80]}"
                           for f in open_items], 4)) if open_items
            else f"keine offenen Befunde blocker oder before_launch in {rel}",
            action="an der Ursache beheben, hochladen, betroffene Prüfer erneut" if open_items else "",
            owner=OPERATOR if open_items else ""))
    path, test = latest_test_round(ctx["workspace"])
    if not isinstance(test, dict):
        out.append(make_check("acceptance-test-round", group, "Testrunde", NA,
                              "keine Testrunde unter reporting/runs/*-test/"))
    else:
        items = [i for g in test.get("groups") or [] for i in g.get("items") or [] if isinstance(i, dict)]
        open_items = [i for i in items if i.get("status") in OPEN_TEST_STATUS]
        decisions = [i for i in open_items if i.get("status") == "decision"]
        owner = BOTH if decisions and len(decisions) < len(open_items) else (TEAM if decisions else OPERATOR)
        out.append(make_check(
            "acceptance-test-round", group, "Testrunde", MISSING if open_items else OK,
            (f"{len(open_items)} von {len(items)} Punkten offen in {path.parent.name}: "
             + short_list([f"{i.get('id')} {i.get('title')} ({i.get('status')})" for i in open_items], 8))
            if open_items else f"alle Punkte mit Status erledigt in {path.parent.name}",
            action="Entscheidungen im nächsten Termin einholen, offene Punkte umsetzen" if open_items else "",
            owner=owner if open_items else "",
            links=[test["preview"]] if isinstance(test.get("preview"), dict) else []))
    return out


def last_sync_reference(ctx: dict) -> dict | None:
    """Jüngster festgehaltener Stand des Live-Themes: Abgleich oder Sicherung."""
    candidates = []
    for path in (ctx["workspace"] / "migration" / "sync").glob("*/delta.json"):
        data = read_json(path) or {}
        if data.get("theme_updated_at_after"):
            candidates.append({"captured_at": data.get("captured_at") or "", "updated_at": data["theme_updated_at_after"],
                               "theme_id": data.get("live_theme_id"), "source": path})
    for path in (ctx["workspace"] / "migration" / "snapshots").glob("*/manifest.json"):
        data = read_json(path) or {}
        if data.get("theme_updated_at"):
            candidates.append({"captured_at": data.get("captured_at") or "", "updated_at": data["theme_updated_at"],
                               "theme_id": data.get("theme_id"), "source": path})
    candidates = [c for c in candidates if not ctx["old_id"] or str(c["theme_id"]) == ctx["old_id"]]
    return max(candidates, key=lambda c: c["captured_at"]) if candidates else None


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
    values = (ctx["state"] or {}).get("values") or {}
    freeze = migration_config(ctx["config"]).get("freeze") or {}
    start = values.get("freeze_from") or freeze.get("from")
    until = values.get("freeze_until") or freeze.get("until")
    if not start:
        out.append(make_check("change-freeze", group, "Änderungsstopp", MISSING,
                              "kein Änderungsstopp festgehalten (freeze_from im Migrationslauf oder theme_migration.freeze)",
                              action="Umfang und Zeitraum nach change-freeze.md vorschlagen, Text an das Team schicken",
                              owner=OPERATOR))
    else:
        ends_early = bool(until and ctx["launch_date"] and str(until)[:10] < ctx["launch_date"].isoformat())
        out.append(make_check("change-freeze", group, "Änderungsstopp", MISSING if ends_early else OK,
                              f"von {start} bis {until or 'offen'}" + (", endet vor dem Launch" if ends_early else ""),
                              action="freeze_until auf den Launch-Termin ziehen und dem Team sagen" if ends_early else "",
                              owner=OPERATOR if ends_early else ""))
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


def dropped_handles(workspace: Path) -> set:
    """App-Handles, die in der Entscheidungsliste gestrichen sind; ihr Fehlen ist gewollt."""
    data = read_json(workspace / "migration" / "inventory" / "apps.json") or {}
    rows = data.get("integrations") if isinstance(data, dict) else data
    return {str(r.get("app_handle")).lower() for r in rows or []
            if isinstance(r, dict) and r.get("decision") == "drop" and r.get("app_handle")}


def check_embeds(ctx: dict) -> list:
    group = "Apps und Embeds"
    title = "App-Embeds im neuen Theme"
    if not (ctx["old_id"] and ctx["new_id"]):
        return [make_check("app-embeds", group, title, BLOCKED, "Live- und Entwurfs-ID nötig")]
    old, error_old = embeds_of(ctx, ctx["old_id"])
    new, error_new = embeds_of(ctx, ctx["new_id"])
    if old is None or new is None:
        return [make_check("app-embeds", group, title, BLOCKED, f"nicht lesbar: {error_old or error_new}")]
    dropped = dropped_handles(ctx["workspace"])
    active_old = {k for k, e in old.items() if not e["disabled"]}
    active_new = {k for k, e in new.items() if not e["disabled"]}
    gaps = sorted(k for k in active_old - active_new if k[0].lower() not in dropped)
    extra = sorted(active_new - active_old)
    evidence = f"{len(active_old)} aktiv im alten, {len(active_new)} aktiv im neuen Theme"
    if gaps:
        evidence += "; fehlt oder aus: " + short_list([f"{h}/{b}" for h, b in gaps], 10)
    if extra:
        evidence += "; nur im neuen: " + short_list([f"{h}/{b}" for h, b in extra], 6)
    if dropped:
        evidence += f"; gestrichen laut apps.json: {short_list(sorted(dropped))}"
    return [make_check("app-embeds", group, title, MISSING if gaps else OK, evidence,
                       action="im Theme-Editor des Entwurfs einschalten oder bewusst streichen" if gaps else "",
                       owner=OPERATOR if gaps else "", links=link_pair(ctx))]


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


def check_tracking(ctx: dict, *, after: bool = False) -> list:
    group = "Tracking"
    title = "Fremde Hosts je Seite, neu gegen alt" if not after else "Apps und Tracking auf dem veröffentlichten Theme"
    check_id = "tracking-hosts" if not after else "tracking-after"
    if not ctx["old"]["pages"] or not ctx["new"]["pages"]:
        which = "alt" if not ctx["old"]["pages"] else "neu"
        return [make_check(check_id, group, title, BLOCKED, f"Mitschnitt fehlt ({which})",
                           action="beide Themes mit capture_network.py mitschneiden, höchstens zwei Browser gleichzeitig",
                           owner=OPERATOR)]
    result = compare_tracking(ctx["old"], ctx["new"], own_hosts(ctx), ctx["catalog"])
    status = MISSING if result["missing"] else OK
    evidence = f"{result['pages']} Seiten und Consent-Zustände verglichen"
    if result["missing"]:
        by_service = {}
        for m in result["missing"]:
            by_service.setdefault(m["name"], set()).add(m["page_id"])
        evidence += "; fehlt im neuen Theme: " + short_list(
            [f"{name} ({len(pages)} {'Seite' if len(pages) == 1 else 'Seiten'})"
             for name, pages in sorted(by_service.items(), key=lambda kv: (-len(kv[1]), kv[0]))], 12)
    if result["added"]:
        evidence += "; nur im neuen: " + short_list(sorted({a["service"] for a in result["added"]}), 6)
    if result["wrong_theme"]:
        status = BLOCKED if status == OK else status
        evidence += "; Durchläufe mit falschem Theme: " + short_list(result["wrong_theme"])
    if result["unmatched"]:
        evidence += "; ohne Gegenstück: " + short_list(result["unmatched"])
    paths = sorted({m["path"] for m in result["missing"] if m.get("path")})[:4]
    out = [make_check(check_id, group, title, status, evidence,
                      action="Einbindung im neuen Theme herstellen oder bewusst streichen (apps-and-tracking.md)"
                      if result["missing"] else "", owner=OPERATOR if status != OK else "",
                      links=[l for p in paths for l in link_pair(ctx, p)])]
    out[0]["details"] = {"missing": result["missing"], "added": result["added"]}
    if not after:
        both = ctx["old"]["modes"] & ctx["new"]["modes"]
        if "accepted" in both:
            out.append(make_check("tracking-consent", group, "Mitschnitt mit Einwilligung", OK,
                                  "beide Themes mit und ohne Einwilligung mitgeschnitten"))
        else:
            out.append(make_check("tracking-consent", group, "Mitschnitt mit Einwilligung", MANUAL,
                                  "nur ohne Einwilligung mitgeschnitten; App-Pixel in Consent-Regionen laden erst danach",
                                  question="Darf ich auf beiden Themes mit Einwilligung mitschneiden?", owner=TEAM))
    return out


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
                   question="Sind Termin, Änderungsstopp und Rückfallkriterien an alle Beteiligten raus, auch an "
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
        blocks_all = bool(re.search(r"(?im)^disallow:\s*/\s*$", body))
        if status != 200 or blocks_all:
            out.append(make_check("robots-after", group, "robots.txt", MISSING,
                                  f"{url} antwortet {status}" + (", sperrt alles (Disallow: /)" if blocks_all else ""),
                                  action="robots.txt sofort korrigieren", owner=OPERATOR))
        elif before_path is None:
            out.append(make_check("robots-after", group, "robots.txt", MANUAL,
                                  f"{url} antwortet 200, {len(body.splitlines())} Zeilen; kein Stand von vorher im Workspace",
                                  question="Ist die robots.txt wie vor dem Launch?", owner=OPERATOR))
        else:
            same = before_path.read_text(encoding="utf-8").strip() == body.strip()
            rel = before_path.relative_to(ctx["workspace"]).as_posix()
            out.append(make_check("robots-after", group, "robots.txt", OK if same else MISSING,
                                  f"{'gleich wie' if same else 'anders als'} {rel}",
                                  action="" if same else "Unterschied ansehen und entscheiden",
                                  owner="" if same else OPERATOR))
    problems, checked, errors = [], 0, []
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
        if tags["noindex"] or "noindex" in headers.get("x-robots-tag", "").lower():
            problems.append(f"{page['path']}: noindex")
        if tags["canonical"] and canonical_path(tags["canonical"]) != canonical_path(page_url):
            problems.append(f"{page['path']}: Canonical {canonical_path(tags['canonical'])}")
    evidence = f"{checked} Seiten live abgerufen"
    if problems:
        evidence += "; " + short_list(problems, 8)
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


def check_after_rest(ctx: dict) -> list:
    group = "Abschluss"
    out = [make_check("test-order", group, "Testbestellung", MANUAL,
                      "Pixel, Checkout, Dankeseite und Events in GA4 und Werbekonten zeigt nur eine Bestellung",
                      question="Gebt ihr eine Testbestellung frei? Danach wird sie storniert und erstattet.", owner=TEAM)]
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
        done = values.get("published_at") and str(values.get("live_theme_id")) == ctx["new_id"]
        out.append(make_check("record-after", group, "Stand festgehalten", OK if done else MISSING,
                              f"published_at {values.get('published_at') or 'fehlt'}, live_theme_id "
                              f"{values.get('live_theme_id') or 'fehlt'}",
                              action="" if done else "run_state set für published_at und live_theme_id, Config nachziehen",
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
        checks = check_published(ctx) + check_after_seo(ctx) + check_tracking(ctx, after=True) \
            + check_after_languages(ctx) + check_after_rest(ctx)
    else:
        checks = (check_timing(ctx) + check_acceptance(ctx) + check_sync(ctx) + check_draft(ctx)
                  + check_embeds(ctx) + check_translations(ctx) + check_tracking(ctx)
                  + [check_seo_robots(ctx, "SEO"), check_seo_pages(ctx, "SEO")]
                  + check_baseline(ctx) + check_criteria(ctx) + check_customer_accounts(ctx)
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


def main(argv: list[str] | None = None, *, transport=None, fetch=None, sleep=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.launch_check", description=__doc__.split("\n\n")[0])
    parser.add_argument("--after", action="store_true", help="Prüfungen direkt nach dem Veröffentlichen")
    parser.add_argument("--live-theme-id", help="Theme, das vor dem Launch live ist (Rückfall-Theme)")
    parser.add_argument("--draft-theme-id", help="Entwurf, der veröffentlicht wird")
    parser.add_argument("--launch-date", help="geplanter Tag des Veröffentlichens, JJJJ-MM-TT")
    parser.add_argument("--run-id", help="Standard <heute>-launch-check")
    parser.add_argument("--pages", help="pages.json für Links und Abrufe")
    parser.add_argument("--network-old", action="append", default=[], help="network.json des alten Themes")
    parser.add_argument("--network-new", action="append", default=[], help="network.json des neuen Themes")
    parser.add_argument("--answers", help="Antworten auf manuelle Punkte, Standard reporting/launch-answers.json")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    try:
        config = load_config(workspace)
        ctx = build_context(args, config, workspace, transport=transport)
        ctx["fetch"] = fetch or http_fetch
        ctx["sleep"] = sleep or time.sleep
        report, code = run(ctx)
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
