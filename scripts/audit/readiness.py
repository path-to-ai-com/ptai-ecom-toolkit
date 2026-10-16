#!/usr/bin/env python3
"""Ist eine Maßnahme der Marke umsetzbar, bevor sie als Aufgabe hochgeht?

Anlass 14. und 15.10.2026: Eine Marke ließ ihr Claude die drei wichtigsten
Aufgaben aus dem Audit umsetzen, und keine ging. Eine beruhte auf einer
einzigen Aufnahme (Befund nur `plausible`), eine nannte defekte Backlinks
nur als Zahl ohne Liste, eine hätte den Farbfilter des Themes gebrochen, weil
das Alt-Feld Steuerwerte trägt. Freigabe und Umsetzbarkeit sind zwei Dinge;
die Arbeit dazwischen ist unsere. Herleitung in der Auswertung zum Cockpit
vom 15.10.2026.

Geprüft wird jede Maßnahme der Marke (`responsible` "Customer" oder "Third
Party") mit Status `open` oder `in_progress`, in der Liste einer Marke je
Store. Unsere eigenen Maßnahmen setzen wir mit unseren Werkzeugen um; für sie
gilt die Prüfung nicht.

1. **Belegt.** Der Befund trägt `confidence: "confirmed"`. Eine Aufnahme, die
   nur plausibel ist, reicht nicht. Bis zum Beleg bleibt die Maßnahme bei Path
   to AI, als Prüfschritt.
2. **Vollständig.** Nennen Maßnahme oder Befund eine Menge von Einzelobjekten
   ("37 Backlinks", "512 Produktbilder"), liegt die Liste im Lauf-Ordner unter
   `items/` als CSV, und die Maßnahme verweist darauf (`items`). Die Zahl der
   Zeilen ist eine der genannten Zahlen: eine gekürzte Liste ist keine Liste.
   Braucht es trotz Zahl keine Liste (eine Einstellung, die für alle Seiten
   gilt), steht der Grund in `items_waiver`.
3. **Machbar.** Die Empfehlung setzt kein Werkzeug von Path to AI voraus
   ("in der Linkdatenbank exportieren", DataForSEO, unser Crawl). Und eine
   Maßnahme zu Alt-Texten sagt, wie sie mit den Steuerwerten im Alt-Feld
   umgeht, wenn der Katalog welche meldet (`images_with_alt_control`).

**Die Liste altert.** Acht Tage nach dem Audit leiteten fast vier von zehn Backlinks
schon weiter (live geprüft am 15.10.2026): erledigt auf anderem Weg. Deshalb
trägt jede Zeile das Datum ihrer Prüfung (`checked_at`) und ihren Stand
(`status`: `open` oder `done`), und `recheck` prüft die Liste einer Maßnahme
vor der Übergabe neu. Geprüft wird beim Abruf, nicht im Takt über alle
Maßnahmen; das gehört später zum Wächter. Eine Liste, deren Zeilen alle
erledigt sind, geht nicht als Aufgabe an die Marke: die Maßnahme ist erledigt.

**Es gilt der jüngere Stand** (seit 16.10.2026). Hat die Marke eine Maßnahme
für einen Store im Cockpit als in Arbeit, umgesetzt, verworfen oder überholt
gemeldet (`audit.portal.reported_statuses`), und ist die Meldung jünger als
der letzte Eintrag in der `history` dieses Stores, liegt sie dort bei der
Marke und wird nicht geprüft. So rechnet auch das Cockpit
(`lib/effective-status.ts` in `ptai-portal`): verglichen wird der Tag, am
selben Tag gilt die Datei. Ohne diese Regel hielte eine Maßnahme, die die
Marke schon umsetzt oder umgesetzt hat, das nächste publish an.

**Punkte der Marke selbst** (seit 16.10.2026). Eine Maßnahme, die aus einer
Anforderung der Marke angelegt wurde (`created_measures` in `feedback.json`,
`audit.feedback`), beruht auf ihrer Aussage, nicht auf einem Befund aus
einem Audit. Für sie gilt "Belegt" nicht. "Vollständig" und "Machbar" prüfen
nur, was wir selbst als Empfehlung hineingeschrieben haben (`intent`,
`needs`), nicht ihren Titel, den Beleg aus ihrer Quelle oder unsere
Prüfregel.

`publish` ruft `check_workspace()` vor jedem Lauf mit Befunden und vor
`--brand-only` auf und bricht bei einem Fund ab; eine Liste, die älter als
`MAX_AGE_DAYS` ist, meldet es als Hinweis. Die gemeldeten Stände holt es über
das Cockpit, wenn `reporting/config.json` einen Block `portal` hat, und nur,
wenn es etwas anzuhalten gibt: eine Meldung nimmt eine Maßnahme heraus, nie
eine hinzu. Ist das Cockpit dann nicht erreichbar, bricht es ab wie der Lauf,
statt ohne die Meldungen zu prüfen. Wochenpuls, Migration und Setup ändern
keine Maßnahme und laufen ohne diese Prüfung.

CLI:
    python3 -m audit.readiness check --workspace <store-workspace> [--run-id <lauf-id>]
    python3 -m audit.readiness items --run-dir <lauf-ordner> --name WBW-09 \\
        --source reporting/data/<lauf-id>/dfs-backlinks.json --key broken_backlinks
    python3 -m audit.readiness recheck --workspace <store-workspace> --measure M-016 [--url-column url_to]
    python3 -m audit.readiness recheck --workspace . --measure M-019 \\
        --against reporting/data/<neu>/catalog-images.json --key images --match image_url
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from audit import brand as brand_mod
from audit import measures, portal

#: Wer eine Maßnahme der Marke umsetzt. Nur sie prüft dieses Modul.
BRAND_SIDE = ("Customer", "Third Party")

#: Status, mit denen eine Maßnahme als Aufgabe ansteht.
TASK_STATUS = ("open", "in_progress")

#: Ordner der Listen im Lauf. Der Lauf geht 1:1 in den Bucket, die Listen mit.
ITEMS_DIR = "items"

#: Spalten, die jede Liste trägt, zusätzlich zu denen ihrer Quelle.
#: `checked_at` ist das Datum der Prüfung dieser Zeile (YYYY-MM-DD),
#: `status` ihr Stand, `checked_status` der HTTP-Status der letzten Prüfung
#: einer Adresse (nur nach `recheck` mit Adressen).
CHECKED_AT = "checked_at"
STATUS = "status"
CHECKED_STATUS = "checked_status"
ROW_STATUS = ("open", "done")

#: Ab diesem Alter in Tagen meldet `check` eine Liste als neu zu prüfen.
#: Dieselbe Grenze nennt das Cockpit an `next_measures` und `get_measure`.
MAX_AGE_DAYS = 7

#: Ab dieser Zahl ist eine Menge eine Liste. Zwei unbenannte Seiten sind schon
#: die Frage "welche?".
MIN_QUANTITY = 2

#: Wortstämme der Einzelobjekte, die eine Marke einzeln anfassen muss.
#: Geprüft am Nomen, das auf die Zahl folgt ("37 Backlinks", "512 von 1.204
#: Produktbildern", "120 deutschen Produktseiten").
ITEM_STEMS = ("seite", "bild", "link", "produkt", "url", "weiterleitung", "variante",
              "kollektion", "collection", "kategorie", "artikel", "handle", "sku",
              "keyword", "suchbegriff")

_NUMBER = r"\d{1,3}(?:\.\d{3})+|\d+"
#: Zahl, optional "von 1.204" oder "bis 35", bis zu zwei kleingeschriebene
#: Adjektive, dann ein großgeschriebenes Nomen. Deutsche Nomen sind groß; so
#: zählt "17 verlinken" nicht, "17 Kategorieseiten" schon.
_QUANTITY = re.compile(
    rf"(?<![\w.,])({_NUMBER})(?![,.]?\d)"
    rf"(?:\s+(?:von|bis|aus)\s+(?:{_NUMBER}))?"
    r"(?:\s+[a-zäöüß]+(?:en|e|er|es|em))?(?:\s+[a-zäöüß]+(?:en|e|er|es|em))?"
    r"\s+([A-ZÄÖÜ][\wäöüÄÖÜß-]*)")

#: Werkzeuge von Path to AI, die eine Marke nicht hat. Steht eins in der
#: Empfehlung, kann ihr Claude sie nicht ausführen: am 15.10.2026 fragte es,
#: welche 37 Backlinks gemeint sind und wo diese Linkdatenbank sei.
OPERATOR_TOOLS = (
    ("Linkdatenbank", re.compile(r"(?:Back)?[Ll]ink-?(?:[Dd]atenbank|[Ii]ndex)\w*")),
    ("DataForSEO", re.compile(r"Data\s*For\s*SEO", re.I)),
    ("unser Crawl", re.compile(r"\b(?:unser\w*|im|aus dem|laut|dem)\s+Crawl\b")),
    ("Snapshot", re.compile(r"\bSnapshots?\b")),
    ("Rohdaten", re.compile(r"\bRohdaten\b")),
    ("Datei aus dem Lauf", re.compile(r"\b[\w-]+\.json\b")),
)

#: Eine Maßnahme zu Alt-Texten, die diese Wörter trägt, hat die Steuerwerte im
#: Alt-Feld berücksichtigt.
_ALT_TOPIC = re.compile(r"Alt-?Text|alt-Attribut", re.I)
_ALT_CONTROL_HANDLED = re.compile(r"#\w|Steuerwert|Steuer-?Tag|Filter", re.I)

#: Spalten, in denen `recheck` ohne Angabe die Adresse sucht, in dieser Folge.
URL_COLUMNS = ("url_to", "url", "page_url")

#: Gemeldete Stände aus dem Cockpit, mit denen eine Maßnahme in einem Store
#: bei der Marke liegt: in Arbeit oder erledigt.
HANDLED_STATUSES = ("in_progress", "implemented", "rejected", "obsolete")


# ------------------------------------------------------------ Text lesen

def quantities(text: str) -> list[tuple[int, str]]:
    """Die Mengen von Einzelobjekten in einem Text, als (Zahl, Wortlaut).

    "37 von 640 Backlinks" gibt (37, "37 Backlinks"); die Gesamtzahl nach
    "von" ist der Nenner, nicht die Menge. Zahlen unter `MIN_QUANTITY` zählen
    nicht.
    """
    found = []
    for number, noun in _QUANTITY.findall(text or ""):
        value = int(number.replace(".", ""))
        if value >= MIN_QUANTITY and any(stem in noun.lower() for stem in ITEM_STEMS):
            found.append((value, f"{number} {noun}"))
    return found


def operator_tools(text: str) -> list[str]:
    """Die Werkzeuge von Path to AI, die ein Text voraussetzt."""
    return [name for name, pattern in OPERATOR_TOOLS if pattern.search(text or "")]


def _join(*values) -> str:
    return " ".join(str(v) for v in values if v)


# ------------------------------------------------------------ Lauf lesen

def find_finding(run_dir: Path, finding_id: str | None) -> dict | None:
    """Der Befund mit dieser Kennung im Lauf, sonst `None`.

    Eine Maßnahme zeigt auf die Kennung des Agents oder auf die des Reports
    (`report_build.finding_id()`), beide werden gesucht.
    """
    if not finding_id:
        return None
    from audit.report_build import finding_id as report_id  # spät, der Report zieht viel nach

    for path in sorted((Path(run_dir) / "findings").glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for number, finding in enumerate((doc.get("findings") if isinstance(doc, dict) else None) or [], 1):
            if not isinstance(finding, dict):
                continue
            raw = finding.get("id")
            if finding_id in (str(raw), report_id(path.stem, raw, number)):
                return finding
    return None


def read_items(path: Path) -> list[dict]:
    """Die Zeilen einer Liste unter `items/`. Ohne Kopfzeile oder Zeile: leer."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_day(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def alt_control_count(run_dir: Path) -> int:
    """Bilder mit Steuerwert im Alt-Feld laut Katalog dieses Laufs, 0 ohne Angabe.

    Der Katalog liegt unter `reporting/data/<lauf-id>/`, neben `runs/`. Ein
    Katalog von vor dem 15.10.2026 kennt das Feld nicht.
    """
    path = Path(run_dir).parent.parent / "data" / Path(run_dir).name / "catalog.json"
    try:
        summary = json.loads(path.read_text(encoding="utf-8")).get("summary") or {}
    except (OSError, ValueError, AttributeError):
        return 0
    return int(summary.get("images_with_alt_control") or 0)


# ------------------------------------------------------------ prüfen

def tasks(backlog: dict):
    """Jede Maßnahme der Marke, die ansteht, als (Store, flache Sicht).

    In der Liste einer Marke einmal je Store mit Status `open` oder
    `in_progress`, mit den Feldern aus `by_shop.<store>`; in der Liste eines
    Stores die Maßnahme selbst, Store `None`.
    """
    for measure in backlog.get("measures") or []:
        if measure.get("responsible") not in BRAND_SIDE:
            continue
        if measures.is_v2(backlog):
            for shop, entry in (measure.get("by_shop") or {}).items():
                if isinstance(entry, dict) and entry.get("status") in TASK_STATUS:
                    yield shop, _flat(measure, entry)
        elif measure.get("status") in TASK_STATUS:
            yield None, _flat(measure, None)


def _flat(measure: dict, entry: dict | None) -> dict:
    """Die Maßnahme mit den Feldern ihres Stores; in v1 mit dem Lauf als `finding_run`."""
    flat = {k: v for k, v in measure.items() if k != "by_shop"}
    if entry is not None:
        flat.update(entry)
    else:
        flat.setdefault("finding_run", measure.get("created_run_id"))
    return flat


def latest_reports(reported) -> dict[tuple[str, str], dict]:
    """Je Store und Maßnahme die jüngste Meldung aus dem Cockpit."""
    latest: dict[tuple[str, str], dict] = {}
    for row in reported or []:
        key = (row.get("shop"), row.get("measure_id"))
        if key not in latest or str(row.get("set_at") or "") > str(latest[key].get("set_at") or ""):
            latest[key] = row
    return latest


def handled_by(flat: dict, shop: str | None, latest: dict) -> dict | None:
    """Die Meldung, mit der die Maßnahme in diesem Store bei der Marke liegt, sonst `None`.

    Bei der Marke heißt in Arbeit, umgesetzt, verworfen oder überholt gemeldet
    (`HANDLED_STATUSES`), an einem späteren Tag als der letzte Eintrag in der
    `history`; am selben Tag gilt die Datei, wie im Cockpit. Ohne Store
    (Liste eines Stores, v1) zählt jede Meldung zur Maßnahme, wie in
    `measures.is_excluded()`.
    """
    mid = flat.get("id")
    if shop is None:
        report = max((row for (_shop, m), row in latest.items() if m == mid),
                     key=lambda row: str(row.get("set_at") or ""), default=None)
    else:
        report = latest.get((shop, mid))
    if not report or report.get("status") not in HANDLED_STATUSES:
        return None
    set_day = str(report.get("set_at") or "")[:10]
    history = [h for h in flat.get("history") or [] if isinstance(h, dict)]
    last_day = str(history[-1].get("date") or "")[:10] if history else ""
    return report if set_day > last_day else None


def measure_problems(flat: dict, run_dir: Path | None, from_request: bool = False) -> list[str]:
    """Was eine Maßnahme der Marke noch nicht umsetzbar macht, als Sätze.

    `run_dir` ist der Lauf ihres Befunds, `None` oder ein fehlender Ordner,
    wenn er nicht auf diesem Rechner liegt: dann zählen Sicherheit und Text
    der Maßnahme allein, und ob die Liste daliegt, ist nicht prüfbar.

    `from_request`: aus einer Anforderung der Marke angelegt. Dann gilt
    "Belegt" nicht, und von der Maßnahme zählt nur unsere Empfehlung
    (`intent`, `needs`); Titel, Beleg und Prüfregel geben ihren Punkt wieder.
    """
    local = run_dir is not None and Path(run_dir).is_dir()
    fid = measures.finding_of(flat)
    finding = find_finding(run_dir, fid) if local else None
    problems = []

    # 1. Belegt: die Sicherheit des Befunds, ohne ihn die der Maßnahme.
    confidence = (finding or {}).get("confidence") or flat.get("confidence")
    if confidence != "confirmed" and not from_request:
        source = f"Befund {fid}" if finding and finding.get("confidence") else "Maßnahme"
        problems.append(
            f"{source} ist {confidence or 'ohne Sicherheit'}, nicht confirmed. Eine Aufgabe der Marke "
            "braucht einen belegten Befund; bis dahin bei Path to AI als Prüfschritt führen "
            "(responsible \"Path to AI\", Titel als Prüfung).")

    # 2. Vollständig: Menge heißt Liste, und die Liste ist ganz.
    if from_request:
        text = _join(flat.get("intent"), flat.get("needs"))
    else:
        text = _join(flat.get("title"), flat.get("intent"), flat.get("needs"), flat.get("check_rule"),
                     flat.get("evidence_text"))
    if finding:
        text = _join(text, finding.get("statement"), finding.get("fix"), finding.get("evidence_text"))
    counts = quantities(text)
    ref = flat.get("items")
    if counts and not ref and not flat.get("items_waiver"):
        named = ", ".join(dict.fromkeys(words for _n, words in counts))
        if finding and finding.get("items"):
            problems.append(f"nennt {named}; der Befund verweist auf {finding['items']}, "
                            "die Maßnahme nicht. Den Verweis in items übernehmen.")
        else:
            problems.append(
                f"nennt {named}, aber keine Liste. Die Liste gehört als CSV nach "
                f"{ITEMS_DIR}/<befund>.csv in den Lauf und in die Maßnahme als items; "
                "braucht es keine, steht der Grund in items_waiver.")
    if ref:
        problems += _items_problems(ref, run_dir if local else None, counts)

    # 3. Machbar: kein Werkzeug von uns, und das Alt-Feld so, wie das Theme es nutzt.
    advice = _join(flat.get("intent"), flat.get("needs"),
                   None if from_request else flat.get("data_source"),
                   (finding or {}).get("fix"),
                   *[(option or {}).get("text") for option in
                     (((finding or {}).get("decision") or {}).get("options") or [])
                     if isinstance(option, dict)])
    tools = operator_tools(advice)
    if tools:
        problems.append(
            f"die Empfehlung setzt ein Werkzeug von Path to AI voraus ({', '.join(tools)}). "
            "Die Marke hat es nicht: das Ergebnis als Liste beilegen und die Empfehlung "
            "ohne das Werkzeug schreiben.")
    topic = (flat.get("intent") or "") if from_request else _join(flat.get("title"), flat.get("intent"))
    if local and _ALT_TOPIC.search(topic):
        controlled = alt_control_count(run_dir)
        if controlled and not _ALT_CONTROL_HANDLED.search(_join(topic, flat.get("needs"),
                                                                  (finding or {}).get("fix"))):
            problems.append(
                f"{controlled} Bilder tragen im Alt-Feld einen Steuerwert des Themes (beginnt "
                "mit #). Die Empfehlung muss sagen, wie sie damit umgeht, sonst bricht das "
                "Befüllen die Funktion im Theme, die den Wert liest.")
    return problems


def _items_problems(ref, run_dir: Path | None, counts: list) -> list[str]:
    """Verweis, Ort, Form und Vollständigkeit der Liste einer Maßnahme."""
    ref = str(ref)
    if not (ref.startswith(f"{ITEMS_DIR}/") and ref.endswith(".csv")) or ".." in ref:
        return [f"items zeigt auf {ref}; erwartet ist {ITEMS_DIR}/<befund>.csv im Lauf."]
    if run_dir is None:
        return []
    path = Path(run_dir) / ref
    if not path.is_file():
        return [f"items zeigt auf {ref}, die Datei fehlt im Lauf {Path(run_dir).name}."]
    try:
        rows = read_items(path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [f"{ref} ist keine lesbare CSV ({exc})."]
    if not rows:
        return [f"{ref} hat keine Zeile."]
    missing = [col for col in (CHECKED_AT, STATUS) if col not in rows[0]]
    if missing:
        return [f"{ref} ohne Spalte {', '.join(missing)}: jede Zeile trägt das Datum ihrer "
                "Prüfung und ihren Stand (open, done)."]
    undated = sum(1 for row in rows if _parse_day(row.get(CHECKED_AT)) is None)
    unknown = sum(1 for row in rows if row.get(STATUS) not in ROW_STATUS)
    problems = []
    if undated:
        problems.append(f"{ref}: {undated} Zeilen ohne gültiges {CHECKED_AT} (YYYY-MM-DD).")
    if unknown:
        problems.append(f"{ref}: {unknown} Zeilen mit status außerhalb von {', '.join(ROW_STATUS)}.")
    if all(row.get(STATUS) == "done" for row in rows):
        problems.append(f"{ref}: alle {len(rows)} Zeilen sind erledigt. Die Maßnahme ist keine "
                        "Aufgabe mehr, sondern als erledigt zu melden.")
    numbers = {n for n, _words in counts}
    if numbers and len(rows) not in numbers:
        stated = ", ".join(str(n) for n in sorted(numbers))
        problems.append(f"{ref} hat {len(rows)} Zeilen, die Maßnahme nennt {stated}. "
                        "Die Liste ist nicht vollständig oder die Zahl stimmt nicht.")
    return problems


def list_age(path: Path, today: date | None = None) -> int | None:
    """Alter der ältesten Prüfung einer Liste in Tagen, `None` ohne Datum."""
    days = [_parse_day(row.get(CHECKED_AT)) for row in read_items(path)]
    days = [d for d in days if d]
    return ((today or date.today()) - min(days)).days if days else None


def runs_resolver(workspace, config: dict | None = None):
    """Der Ordner `runs/` je Store, so wie die Ablage ihn vorsieht.

    In der Liste einer Marke über `brand.store_runs_dir()`, sonst der eigene.
    """
    workspace = Path(workspace)
    config = brand_mod.read_config(workspace) if config is None else config
    brand_reporting = brand_mod.brand_reporting_dir(workspace, config)
    own = workspace / "reporting" / "runs"
    if brand_reporting is None:
        return lambda shop: own
    own_shop = brand_mod.shop_slug(config)
    return lambda shop: brand_mod.store_runs_dir(brand_reporting, shop, workspace, own_shop)


def check(backlog: dict, runs_dir_of, run_id: str | None = None,
          today: date | None = None, reported: list[dict] | None = None,
          requested: set[str] | None = None) -> list[dict]:
    """Jede Maßnahme der Marke mit Gründen gegen die Übergabe oder einem Hinweis.

    `runs_dir_of(shop)` gibt den Ordner `runs/` eines Stores. Mit `run_id` nur
    die Maßnahmen, deren Befund aus diesem Lauf stammt. `reported` sind die
    gemeldeten Stände aus dem Cockpit (`audit.portal.reported_statuses`); was
    die Marke dort später als in Arbeit oder erledigt gemeldet hat, wird nicht
    geprüft (`handled_by()`). `requested` sind die Kennungen der Maßnahmen, die
    aus einer Anforderung der Marke angelegt wurden (`requested_measures()`).
    `problems` hält die Übergabe an, `hints` nicht: eine Liste älter als
    `MAX_AGE_DAYS`.
    """
    latest = latest_reports(reported)
    out = []
    for shop, flat in tasks(backlog):
        frun = flat.get("finding_run") or flat.get("created_run_id")
        if run_id and frun != run_id:
            continue
        if latest and handled_by(flat, shop, latest):
            continue
        run_dir = Path(runs_dir_of(shop)) / frun if frun else None
        found = measure_problems(flat, run_dir, flat.get("id") in (requested or ()))
        hints = []
        ref = flat.get("items")
        path = run_dir / str(ref) if ref and run_dir is not None else None
        if path is not None and path.is_file() and not found:
            age = list_age(path, today)
            if age is not None and age > MAX_AGE_DAYS:
                hints.append(f"{ref} ist {age} Tage alt; vor der Übergabe neu prüfen "
                             f"(python3 -m audit.readiness recheck --measure {flat.get('id')}).")
        if found or hints:
            out.append({"measure": flat.get("id"), "shop": shop, "title": flat.get("title"),
                        "problems": found, "hints": hints})
    return out


def _where(entry: dict) -> str:
    return f"{entry['measure']} ({entry['shop']})" if entry["shop"] else entry["measure"]


def lines(found: list[dict]) -> tuple[list[str], list[str]]:
    """Das Ergebnis von `check()` als Zeilen für `publish`: (Gründe, Hinweise)."""
    reasons, hints = [], []
    for entry in found:
        reasons += [f"{_where(entry)}: {text}" for text in entry["problems"]]
        hints += [f"{_where(entry)}: {text}" for text in entry["hints"]]
    return reasons, hints


def problems(backlog: dict, runs_dir_of, run_id: str | None = None,
             today: date | None = None, reported: list[dict] | None = None,
             requested: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Wie `check()`, als Zeilen für `publish`: (Gründe, Hinweise)."""
    return lines(check(backlog, runs_dir_of, run_id, today, reported, requested))


def requested_measures(workspace) -> set[str]:
    """Die Maßnahmen, die aus einer Anforderung der Marke angelegt wurden.

    Aus `created_measures` in `feedback.json` (`audit.feedback`), der Datei der
    Marke oder des Stores. Dieselbe Angabe liest das Cockpit, um eine solche
    Maßnahme als "noch nicht gemessen" zu zeigen.
    """
    from audit import feedback  # spät: feedback zieht die Ablage der Marke nach

    return {mid for entry in feedback.load(str(workspace)) if isinstance(entry, dict)
            for mid in entry.get("created_measures") or []}


def cockpit_reports(workspace, config: dict | None = None) -> list[dict] | None:
    """Die gemeldeten Stände der Marke aus dem Cockpit, `None` ohne Block `portal`.

    Marke und Store kommen aus `portal` in `reporting/config.json`. Kein
    Rückfall: ist das Cockpit nicht erreichbar, steigt `portal.PortalError` auf.
    """
    config = brand_mod.read_config(workspace) if config is None else config
    target = config.get("portal")
    if not isinstance(target, dict):
        return None
    brand, shop = target.get("brand"), target.get("shop")
    if not (isinstance(brand, str) and isinstance(shop, str)):
        raise portal.PortalError(f"Block portal in {Path(workspace) / 'reporting' / 'config.json'} "
                                 "ohne brand oder shop")
    return portal.reported_statuses(brand, shop, workspace)


def check_workspace(workspace, config: dict | None = None, run_id: str | None = None,
                    today: date | None = None) -> list[dict]:
    """`check()` für einen Store-Workspace, mit den Anforderungen der Marke aus
    `feedback.json` und ihren Meldungen aus dem Cockpit.

    Das Cockpit wird nur gefragt, wenn ohne Meldungen etwas ansteht: eine
    Meldung nimmt eine Maßnahme heraus, nie eine hinzu. Ist es dann nicht
    erreichbar, steigt `portal.PortalError` auf, statt ohne die Meldungen
    weiterzuprüfen.
    """
    workspace = Path(workspace)
    config = brand_mod.read_config(workspace) if config is None else config
    backlog, runs_dir_of = measures.peek(workspace), runs_resolver(workspace, config)
    requested = requested_measures(workspace)
    found = check(backlog, runs_dir_of, run_id, today, requested=requested)
    if found:
        reported = cockpit_reports(workspace, config)
        if reported is not None:
            found = check(backlog, runs_dir_of, run_id, today, reported, requested)
    return found


# ------------------------------------------------------------ Liste schreiben

def _pick(data, key: str):
    """Ein Wert aus verschachteltem JSON über einen Punktpfad ("summary.rows")."""
    for part in key.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def write_items(run_dir: Path, name: str, rows: list[dict], columns: list[str] | None = None,
                checked_at: date | None = None) -> Path:
    """Schreibt `items/<name>.csv` in den Lauf, UTF-8 mit BOM für Excel.

    Spalten in der Reihenfolge der ersten Zeile, ergänzt um Schlüssel späterer
    Zeilen; mit `columns` genau diese. Dahinter `checked_at` und `status`:
    eine Zeile ohne eigenes Datum bekommt `checked_at` (Vorgabe heute), ohne
    eigenen Stand `open`.
    """
    if not re.fullmatch(r"[A-Za-z0-9][\w-]*", name or ""):
        raise ValueError(f"{name!r} taugt nicht als Dateiname, erwartet etwa WBW-09")
    if not rows:
        raise ValueError("keine Zeile: eine leere Liste ist kein Beleg")
    if columns is None:
        columns = []
        for row in rows:
            columns += [key for key in row if key not in columns]
    columns = [c for c in columns if c not in (CHECKED_AT, STATUS)] + [CHECKED_AT, STATUS]
    day = (checked_at or date.today()).isoformat()
    full = [{**row, CHECKED_AT: row.get(CHECKED_AT) or day, STATUS: row.get(STATUS) or "open"}
            for row in rows]
    return _write_csv(Path(run_dir) / ITEMS_DIR / f"{name}.csv", full, columns)


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row.get(k)) for k in columns})
    tmp.replace(path)
    return path


def _cell(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "ja"
    if value is False:
        return "nein"
    return "" if value is None else value


def items_from_snapshot(source: Path, key: str) -> tuple[list[dict], date | None]:
    """Die Zeilen einer Liste aus einem Snapshot und der Tag, an dem er entstand.

    Gekürzt heißt `<key>_truncated: true` neben der Liste; eine Liste, die
    nicht alles trägt, ist für die Marke dieselbe Frage wie gar keine, also
    bricht das ab. Der Tag kommt aus `pulled_at` des Snapshots.
    """
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    rows = _pick(data, key)
    if not isinstance(rows, list):
        raise ValueError(f"{source} hat unter {key} keine Liste")
    if _pick(data, f"{key}_truncated"):
        raise ValueError(f"{key} in {source} ist gekürzt; für die Marke zählt nur die ganze Liste")
    return rows, _parse_day(data.get("pulled_at") if isinstance(data, dict) else None)


# ------------------------------------------------------------ neu prüfen

def fetch_status(url: str, timeout: float = 20) -> int | None:
    """HTTP-Status einer Adresse nach allen Weiterleitungen, `None` ohne Antwort.

    GET statt HEAD: Shopify beantwortet HEAD nicht überall wie GET, und eine
    Weiterleitung auf HEAD folgt nicht jede Python-Version.
    """
    import urllib.error
    import urllib.request

    from audit.account import USER_AGENT

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


def recheck_urls(rows: list[dict], column: str, today: date, fetch=None,
                 delay: float = 0.3) -> list[dict]:
    """Jede Zeile mit ihrer Adresse neu geprüft: erledigt, wenn sie ohne Fehler antwortet.

    Erledigt heißt Status unter 400 nach allen Weiterleitungen, also die
    Weiterleitung, die die Maßnahme verlangt, oder die Seite gibt es wieder.
    Keine Antwort lässt die Zeile, wie sie ist, mit altem Datum: ein Ausfall
    ist keine Prüfung.
    """
    fetch = fetch or fetch_status
    out = []
    for i, row in enumerate(rows):
        if i and delay:
            time.sleep(delay)
        code = fetch(row.get(column) or "")
        if code is None:
            out.append(dict(row))
            continue
        out.append({**row, CHECKED_STATUS: code, CHECKED_AT: today.isoformat(),
                    STATUS: "done" if code < 400 else "open"})
    return out


def recheck_against(rows: list[dict], fresh: list[dict], match: str, today: date) -> list[dict]:
    """Jede Zeile gegen einen frischen Snapshot: erledigt, wenn sie dort fehlt.

    Für Listen aus dem Katalog: steht ein Bild nicht mehr in der frischen
    Liste der Bilder ohne Alt-Text, hat es inzwischen einen.
    """
    present = {str(item.get(match)) for item in fresh if isinstance(item, dict)}
    if not any(row.get(match) for row in rows):
        raise ValueError(f"Spalte {match} fehlt in der Liste oder ist überall leer")
    return [{**row, CHECKED_AT: today.isoformat(),
             STATUS: "open" if str(row.get(match)) in present else "done"} for row in rows]


def items_path(workspace, measure_id: str, shop: str | None = None) -> tuple[Path, dict]:
    """Die Liste einer Maßnahme auf diesem Rechner und die flache Sicht der Maßnahme."""
    workspace = Path(workspace)
    config = brand_mod.read_config(workspace)
    backlog = measures.peek(workspace)
    shop = shop or (brand_mod.shop_slug(config) if measures.is_v2(backlog) else None)
    measure = next((m for m in backlog.get("measures") or [] if m.get("id") == measure_id), None)
    if measure is None:
        raise ValueError(f"{measure_id} steht nicht in der Liste")
    if measures.is_v2(backlog):
        entry = (measure.get("by_shop") or {}).get(shop)
        if not isinstance(entry, dict):
            raise ValueError(f"{measure_id} gilt nicht für {shop}")
        flat = _flat(measure, entry)
    else:
        flat = _flat(measure, None)
    ref, frun = flat.get("items"), flat.get("finding_run") or flat.get("created_run_id")
    if not ref or not frun:
        raise ValueError(f"{measure_id} verweist auf keine Liste (items) oder keinen Lauf")
    path = Path(runs_resolver(workspace, config)(shop)) / frun / str(ref)
    if not path.is_file():
        raise ValueError(f"{path} fehlt auf diesem Rechner")
    return path, flat


def recheck(path: Path, *, url_column: str | None = None, against: Path | None = None,
            key: str | None = None, match: str | None = None, today: date | None = None,
            fetch=None, delay: float = 0.3) -> dict:
    """Prüft eine Liste neu und schreibt sie zurück. Gibt die Zählung zurück.

    Mit `against` gegen einen frischen Snapshot (`key`, `match`), sonst über
    die Adresse jeder Zeile (`url_column`, ohne Angabe die erste aus
    `URL_COLUMNS`, die die Liste hat).
    """
    today = today or date.today()
    rows = read_items(path)
    if not rows:
        raise ValueError(f"{path} hat keine Zeile")
    columns = list(rows[0].keys())
    if against is not None:
        if not key or not match:
            raise ValueError("--against braucht --key und --match")
        fresh, _day = items_from_snapshot(against, key)
        rows = recheck_against(rows, fresh, match, today)
    else:
        column = url_column or next((c for c in URL_COLUMNS if c in columns), None)
        if not column or column not in columns:
            raise ValueError(f"keine Spalte mit Adressen in {path.name}; --url-column oder --against angeben")
        rows = recheck_urls(rows, column, today, fetch, delay)
        if CHECKED_STATUS not in columns:
            columns.append(CHECKED_STATUS)
    columns = [c for c in columns if c not in (CHECKED_AT, STATUS)] + [CHECKED_AT, STATUS]
    _write_csv(path, rows, columns)
    done = sum(1 for row in rows if row.get(STATUS) == "done")
    return {"path": str(path), "rows": len(rows), "done": done, "open": len(rows) - done,
            "checked_at": today.isoformat()}


# ------------------------------------------------------------ CLI

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Umsetzbarkeit der Maßnahmen der Marke.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("check", help="Maßnahmen der Marke prüfen; Exit-Code: Zahl der nicht umsetzbaren")
    run.add_argument("--workspace", default=".", help="Workspace des Stores")
    run.add_argument("--run-id", help="nur Maßnahmen aus diesem Lauf")
    items = sub.add_parser("items", help="Liste aus einem Snapshot als items/<name>.csv schreiben")
    items.add_argument("--run-dir", required=True, help="reporting/runs/<lauf-id>")
    items.add_argument("--name", required=True, help="Dateiname ohne Endung, die Kennung des Befunds")
    items.add_argument("--source", required=True, help="Snapshot mit der Liste")
    items.add_argument("--key", required=True, help="Pfad zur Liste im Snapshot, etwa broken_backlinks")
    items.add_argument("--columns", help="Spalten, kommagetrennt; Vorgabe: alle")
    again = sub.add_parser("recheck", help="Liste einer Maßnahme vor der Übergabe neu prüfen")
    again.add_argument("--workspace", default=".", help="Workspace des Stores")
    again.add_argument("--measure", required=True, help="Kennung, etwa M-016")
    again.add_argument("--shop", help="Store in der Liste einer Marke; Vorgabe: dieser")
    again.add_argument("--url-column", help="Spalte mit der Adresse; Vorgabe: url_to, url, page_url")
    again.add_argument("--against", help="frischer Snapshot statt Abruf der Adressen")
    again.add_argument("--key", help="Liste im frischen Snapshot, mit --against")
    again.add_argument("--match", help="Spalte, über die Zeile und Snapshot zusammenpassen, mit --against")
    args = parser.parse_args(argv)

    try:
        if args.command == "items":
            rows, day = items_from_snapshot(Path(args.source), args.key)
            columns = [c.strip() for c in args.columns.split(",")] if args.columns else None
            path = write_items(Path(args.run_dir), args.name, rows, columns, checked_at=day)
            print(f"Geschrieben: {path} ({len(rows)} Zeilen, geprüft am "
                  f"{(day or date.today()).isoformat()}). In die Maßnahme: "
                  f"items \"{ITEMS_DIR}/{path.name}\"")
            return 0
        if args.command == "recheck":
            path, flat = items_path(args.workspace, args.measure, args.shop)
            result = recheck(path, url_column=args.url_column,
                             against=Path(args.against) if args.against else None,
                             key=args.key, match=args.match)
            print(f"{args.measure}: {result['done']} von {result['rows']} Zeilen erledigt, "
                  f"{result['open']} offen, geprüft am {result['checked_at']} ({path}).")
            if not result["open"]:
                print(f"Alles erledigt: {args.measure} nicht übergeben, sondern als erledigt melden.")
            elif result["done"]:
                print("Die Liste im Bucket ist erst nach erneutem publish dieses Laufs neu "
                      "(mit --visible, wenn er veröffentlicht ist).")
            return 0
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    try:
        found = check_workspace(Path(args.workspace), run_id=args.run_id)
    except portal.PortalError as exc:
        print(f"Fehler: {exc}. Ohne die gemeldeten Stände aus dem Cockpit nicht geprüft.",
              file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    blocked = [e for e in found if e["problems"]]
    for entry in found:
        print(f"{_where(entry)} {entry['title']}")
        for reason in entry["problems"]:
            print(f"  - {reason}")
        for hint in entry["hints"]:
            print(f"  Hinweis: {hint}")
    print(f"{len(blocked)} Maßnahmen der Marke nicht umsetzbar." if blocked
          else "Jede anstehende Maßnahme der Marke ist umsetzbar.")
    return min(len(blocked), 125)


if __name__ == "__main__":
    sys.exit(main())
