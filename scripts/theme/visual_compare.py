#!/usr/bin/env python3
"""Der vollständige Bildvergleich alt gegen neu, Voraussetzung für Gate G4.

Am 11.11.2026 ging ein Shop auf Horizon live, und danach fielen Layoutfehler auf,
die jeder auf einem Bild gesehen hätte: Inhaltsseiten schmal und links,
Typografie falsch, Suchseite ohne Suchfeld, Mega-Menü, Newsletter zu hoch. Die
Abnahme hatte Testpunkte einzeln und als Stichprobe geprüft. Einen Bildvergleich
über alle Beispielseiten am Rechner und am Handy gab es vor G4 nicht, und als
Vorlage lag zeitweise ein älteres Theme statt des veröffentlichten auf dem Tisch.

Seitdem gilt: G4 hält an, bis für jede Beispielseite aus
`migration/inventory/pages.json` am Rechner (1440 px, Chromium) und am Handy
(390 px, WebKit) ein gültiges Bildpaar vorliegt. Gültig heißt:

- links das veröffentlichte Theme: der Theme-Nachweis der Seite trägt die Rolle
  `main`; fehlt die Rolle im Nachweis, muss die ID `live_theme_id` der Config sein
- rechts der aktuelle Entwurf (`draft_theme_id` der Config, sonst des Laufs)
- beide Aufnahmen mit Theme-Nachweis der erwarteten ID, ohne Fehler, mit
  Ganzseiten-Bild in der verlangten Breite; eine von Shopify gedrosselte Aufnahme
  (`throttled`, HTTP 429) zählt nicht und ist kein Befund am Shop
- am Handy rechts auch der Zustand "Menü offen", ohne fremde Elemente über der
  Menü-Schublade (seit 11.11.2026, Nachtrag)

**Nachtrag vom Nachmittag des 11.11.2026.** Am Handy lagen ein E-Mail-Teaser und
eine Countdown-Leiste über Horizons Menü-Schublade (z-index 90000 gegen 18). Die
geschlossene Seite zeigte nichts davon. `shoot_pair.py` öffnet deshalb am Handy
das Menü, nimmt es auf und prüft per `elementFromPoint` über der Schublade, was
oben liegt (`menu`). Ein fremdes Element über der Schublade im Entwurf hält G4
an, außer es liegt im veröffentlichten Theme genauso darüber; dann ist es ein
Hinweis.

Am selben Nachmittag wurden Schriften gegen ein älteres Theme verglichen statt
gegen das veröffentlichte. Jede Referenz steht deshalb mit ID und Name im
Ergebnis (`reference.name`), und nach dem Launch ist sie das alte Theme, das bis
zum Launch veröffentlicht war (`rollback_theme_id` des Laufs), nie ein drittes.
`visual_compare reference` nennt sie vor jedem Vergleich und jeder Abnahme.

`shoot_pair.py` schreibt dafür neben die Bilder im Kundenordner einen Eintrag in
den Workspace, `migration/verify/<date>/pairs.json`. Gelesen werden alle diese
Einträge; je Seite und Breite zählt die jüngste Aufnahme. So reicht nach einer
Korrektur das Nachholen der betroffenen Seiten, und eine fehlgeschlagene neue
Aufnahme verdeckt nie still eine alte gelungene: dann zählt die Seite nicht.

Aufruf (aus dem Workspace):
    python3 -m theme.visual_compare check
    python3 -m theme.visual_compare reference

Ausgabe eine JSON-Zeile. `check`: Exit 0 vollständig, 1 unvollständig, 2 Fehler.
`reference`: Exit 0 Referenz belegt, 1 widersprüchlich, 2 Fehler.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from theme import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config

#: Die beiden Breiten des Vergleichs in CSS-Pixeln: Rechner in Chromium, Handy in WebKit (iPhone).
WIDTHS = {"desktop": 1440, "mobile": 390}
DEVICES = tuple(WIDTHS)
SIDES = ("a", "b")
DEVICE_LABEL = {"desktop": "Rechner", "mobile": "Handy"}
#: Rolle des veröffentlichten Themes im Theme-Nachweis (`Shopify.theme.role`).
PUBLISHED_ROLE = "main"
#: Status einer Aufnahme, die Shopify gedrosselt hat (`scripts/browser/common.py`).
THROTTLED = "throttled"
#: Zustände der Aufnahme "Menü offen" am Handy (`shoot_pair.py`, Feld `menu.state`).
MENU_OK, MENU_OVERLAP = "ok", "overlap"
MENU_REASON = {"no_toggle": "kein Menüknopf im Kopfbereich gefunden",
               "no_drawer": "nach dem Klick keine Menü-Schublade gefunden", "error": "Fehler beim Öffnen"}
RECORD_NAME = "pairs.json"
PAGES_PATH = Path("migration") / "inventory" / "pages.json"


class CompareError(Exception):
    """Ein Eintrag oder eine Seitenliste, die sich nicht lesen lässt."""


def same_id(a, b) -> bool:
    """Zwei Theme-IDs gleich, auch wenn eine als Zahl und eine als Text kommt."""
    a, b = str(a or "").strip(), str(b or "").strip()
    if not a or not b:
        return False
    if a.isdigit() and b.isdigit():
        return int(a) == int(b)
    return a == b


def record_path(workspace, day: str | None = None) -> Path:
    return Path(workspace) / "migration" / "verify" / (day or date.today().isoformat()) / RECORD_NAME


# ---------------------------------------------------------------------------
# Eine Aufnahme, ein Bildvergleich
# ---------------------------------------------------------------------------

def shot_problem(shot: dict | None, device: str, expected_theme) -> str | None:
    """Warum eine Aufnahme nicht zählt, sonst None."""
    if not isinstance(shot, dict):
        return "keine Aufnahme"
    check = shot.get("theme_check") or {}
    if shot.get("state") == THROTTLED:
        return ("von Shopify gedrosselt (HTTP 429), kein Fehler des Shops; mit --parallel 1 und größerem --pace "
                "nachholen")
    if shot.get("state") != "ok":
        reason = check.get("reason") or shot.get("error") or ""
        return f"{shot.get('state') or 'ohne Status'}" + (f": {reason}" if reason else "")
    if not same_id(check.get("found"), expected_theme):
        return "Theme-Nachweis fehlt" if not check.get("found") else f"Seite zeigt Theme {check.get('found')}"
    if not shot.get("file"):
        return "kein Ganzseiten-Bild"
    width = (shot.get("viewport") or {}).get("width")
    if width != WIDTHS.get(device):
        return f"Breite {width} statt {WIDTHS.get(device)}"
    return None


def theme_name(shots: list) -> str | None:
    """Der Name des Themes aus den Theme-Nachweisen der Aufnahmen, der häufigste; None ohne Nachweis."""
    names = Counter((s.get("theme_check") or {}).get("found_name") for s in shots
                    if isinstance(s, dict) and s.get("state") == "ok")
    names.pop(None, None)
    names.pop("", None)
    return names.most_common(1)[0][0] if names else None


def theme_label(theme_id, name: str | None = None) -> str:
    """`Theme 000000000000 „Beispiel Theme“`, ohne Namen nur mit ID."""
    return f"Theme {theme_id}" + (f" „{name}“" if name else "")


def reference_status(theme_a, shots_a: list, config_live=None, rollback=None) -> dict:
    """Ob die linke Seite die Referenz ist, mit ID und Name.

    Vor dem Launch ist die Referenz das veröffentlichte Theme. Beleg ist die Rolle im Theme-Nachweis der
    Seiten (`main`). Sie gilt vor der Config, weil eine veraltete `live_theme_id` genau den Fehler vom
    11.11.2026 erlaubt: ein älteres Theme als Vorlage. Fehlt die Rolle, muss die ID der Config entsprechen.
    Eine abweichende Config bei belegter Rolle ist eine Warnung, kein Fehler: dann ist die Config veraltet,
    nicht der Vergleich.

    Nach dem Launch (`rollback` gesetzt) ist die Referenz das alte Theme, das bis zum Launch veröffentlicht
    war; es trägt dann die Rolle `unpublished`. Gültig ist links nur genau diese ID. Am Nachmittag des
    11.11.2026 lag stattdessen ein drittes, älteres Theme als Vorlage auf dem Tisch.
    """
    name = theme_name(shots_a)
    label = theme_label(theme_a, name)
    roles = sorted({(s.get("theme_check") or {}).get("found_role") for s in shots_a
                    if isinstance(s, dict) and s.get("state") == "ok"} - {None, ""})
    problems, warnings = [], []
    if rollback:
        matches = same_id(theme_a, rollback)
        if not matches:
            problems.append(f"links steht {label}; nach dem Launch ist die Referenz das alte Theme {rollback} "
                            "(Rückfall-Theme, bis zum Launch veröffentlicht), nie ein anderes")
        return {"theme_id": str(theme_a or ""), "name": name, "kind": "rollback", "roles": roles,
                "published": False, "rollback_theme_id": str(rollback), "config_live_theme_id": None,
                "matches_config": matches, "ok": not problems, "problems": problems, "warnings": warnings}
    matches = same_id(theme_a, config_live) if config_live else None
    if roles and roles != [PUBLISHED_ROLE]:
        problems.append(f"links steht {label} mit Rolle {', '.join(roles)}, nicht das veröffentlichte "
                        "Theme; Referenz ist immer das Live-Theme mit seiner ID")
    elif not roles:
        if matches is None:
            problems.append(f"Rolle von {label} nicht belegt und keine live_theme_id in der Config")
        elif not matches:
            problems.append(f"links steht {label}, live_theme_id der Config ist {config_live}, und die "
                            "Seiten belegen keine Rolle")
    if roles == [PUBLISHED_ROLE] and matches is False:
        warnings.append(f"live_theme_id {config_live} der Config ist veraltet: veröffentlicht ist {label}")
    return {"theme_id": str(theme_a or ""), "name": name, "kind": "published", "roles": roles,
            "published": roles == [PUBLISHED_ROLE], "rollback_theme_id": None,
            "config_live_theme_id": str(config_live) if config_live else None, "matches_config": matches,
            "ok": not problems, "problems": problems, "warnings": warnings}


def menu_labels(shot: dict | None) -> set:
    """Kennzeichen der fremden Elemente über der Menü-Schublade einer Aufnahme."""
    menu = (shot or {}).get("menu") or {}
    return {str(f.get("label")) for f in menu.get("foreign") or [] if isinstance(f, dict) and f.get("label")}


def describe_foreign(item: dict, drawer: dict | None) -> str:
    """`div#klaviyo-teaser (z-index 90000 über Schublade z-index 18, 12 % der Fläche)`."""
    parts = []
    if item.get("z_index") not in (None, "", "auto"):
        parts.append(f"z-index {item['z_index']}"
                     + (f" über Schublade z-index {drawer['z_index']}"
                        if (drawer or {}).get("z_index") not in (None, "", "auto") else ""))
    if item.get("share") is not None:
        parts.append(f"{round(float(item['share']) * 100)} % der Fläche")
    if item.get("text"):
        parts.append(f"„{str(item['text'])[:40]}“")
    return str(item.get("label")) + (f" ({', '.join(parts)})" if parts else "")


def menu_problem(pair: dict | None) -> tuple:
    """`(problem, hinweis)` für den Zustand "Menü offen" am Handy, rechts im Paar; je None, wenn nichts ist.

    Ein Problem hält G4 an: Aufnahme fehlt, Menü ließ sich nicht öffnen, oder ein fremdes Element liegt über
    der Schublade. Liegt dasselbe Element (gleiches Kennzeichen) links genauso darüber, ist es schon im
    veröffentlichten Theme so und nur ein Hinweis.
    """
    shot_b = (pair or {}).get("b") or {}
    menu = shot_b.get("menu")
    if not isinstance(menu, dict):
        return ("Menü offen nicht aufgenommen; shoot_pair.py ab 0.3.30 nimmt es am Handy mit auf", None)
    state = menu.get("state")
    if state not in (MENU_OK, MENU_OVERLAP):
        reason = MENU_REASON.get(state, state or "ohne Status")
        detail = f": {menu['error']}" if menu.get("error") else ""
        return (f"Menü offen: {reason}{detail}; mit --menu-toggle '<Selektor des Menüknopfs>' nachholen", None)
    foreign = [f for f in menu.get("foreign") or [] if isinstance(f, dict)]
    if not foreign:
        return None, None
    before = menu_labels((pair or {}).get("a"))
    new = [f for f in foreign if str(f.get("label")) not in before]
    known = [f for f in foreign if str(f.get("label")) in before]
    problem = ("Menü offen: fremde Elemente über der Menü-Schublade: "
               + "; ".join(describe_foreign(f, menu.get("drawer")) for f in new[:3])) if new else None
    note = ("Menü offen: liegt im veröffentlichten Theme genauso über dem Menü: "
            + "; ".join(str(f.get("label")) for f in known[:3])) if known else None
    return problem, note


def coverage(page_ids: list, slots: dict, themes_of=None) -> dict:
    """Abdeckung je Seite, Breite und Seite des Paars.

    `slots` ordnet `(page_id, device)` ein Paar zu (`{"a": shot, "b": shot}`). `themes_of(pair)` liefert
    die erwarteten Theme-IDs des Paars; ohne Angabe stehen sie im Paar unter `themes`. Am Handy zählt rechts
    zusätzlich der Zustand "Menü offen" (`menu_problem`); er steht, wenn das Bild selbst gültig ist, als
    Grund derselben Aufnahme in `missing`, damit jede Aufnahme höchstens einmal fehlt.
    """
    missing, notes = [], []
    for page_id in page_ids:
        for device in DEVICES:
            pair = slots.get((page_id, device))
            themes = (themes_of(pair) if themes_of else (pair or {}).get("themes")) or {}
            for side in SIDES:
                problem = shot_problem((pair or {}).get(side), device, themes.get(side))
                if not problem and device == "mobile" and side == "b":
                    problem, note = menu_problem(pair)
                    if note:
                        notes.append({"page_id": page_id, "device": device, "side": side, "note": note})
                if problem:
                    missing.append({"page_id": page_id, "device": device, "side": side, "reason": problem})
    expected = len(page_ids) * len(DEVICES) * len(SIDES)
    return {"pages": len(page_ids), "devices": list(DEVICES), "widths": dict(WIDTHS), "expected": expected,
            "valid": expected - len(missing), "missing": missing, "notes": notes,
            "complete": bool(page_ids) and not missing}


def record_summary(page_ids: list, pairs: list, themes: dict, config_live=None, rollback=None) -> dict:
    """Referenz und Abdeckung eines Laufs von `shoot_pair.py`, wie sie in `pairs.json` stehen."""
    slots = {(p.get("page_id"), p.get("device")): p for p in pairs if isinstance(p, dict)}
    guessed = None if rollback else inferred_rollback(themes.get("a"), [p.get("b") for p in pairs if isinstance(p, dict)],
                                                      config_live)
    reference = reference_status(themes.get("a"), [p.get("a") for p in pairs if isinstance(p, dict)], config_live,
                                 rollback or guessed)
    if guessed:
        reference["warnings"].append(UNRECORDED)
    return {"reference": reference, "coverage": coverage(page_ids, slots, lambda _pair: themes)}


def merge_record(old: dict | None, new: dict) -> dict:
    """Ein neuer Lauf am selben Tag ergänzt den Eintrag, wenn beide Themes gleich sind; sonst ersetzt er ihn.

    Je Seite und Breite gilt die neue Aufnahme. Ohne das würde das Nachholen einer einzelnen Seite den
    vollständigen Vergleich vom Morgen überschreiben.
    """
    if not isinstance(old, dict) or not all(same_id((old.get("themes") or {}).get(s), (new.get("themes") or {}).get(s))
                                            for s in SIDES):
        return new
    fresh = {(p.get("page_id"), p.get("device")) for p in new.get("pairs") or []}
    kept = [p for p in old.get("pairs") or [] if (p.get("page_id"), p.get("device")) not in fresh]
    for pair in kept:
        pair.setdefault("captured_at", old.get("captured_at"))
    for pair in new.get("pairs") or []:
        pair.setdefault("captured_at", new.get("captured_at"))
    return {**new, "pairs": kept + list(new.get("pairs") or [])}


# ---------------------------------------------------------------------------
# Gate G4: alle Einträge des Workspace
# ---------------------------------------------------------------------------

def load_page_ids(workspace) -> list:
    path = Path(workspace) / PAGES_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CompareError(f"{PAGES_PATH} fehlt; die Beispielseiten legt inventory-theme an") from exc
    except (OSError, ValueError) as exc:
        raise CompareError(f"{PAGES_PATH} nicht lesbar: {exc}") from exc
    ids = [str(p["id"]) for p in (data.get("pages") or []) if isinstance(p, dict) and p.get("id")]
    if not ids:
        raise CompareError(f"{PAGES_PATH} nennt keine Seite")
    return ids


def load_records(workspace) -> list:
    """Alle Einträge unter `migration/verify/*/pairs.json`, ältester zuerst; unlesbare als Fehler."""
    out = []
    for path in sorted((Path(workspace) / "migration" / "verify").glob(f"*/{RECORD_NAME}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out.append({"path": path, "error": f"{path.parent.name}/{RECORD_NAME} nicht lesbar: {exc}"})
            continue
        if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
            out.append({"path": path, "error": f"{path.parent.name}/{RECORD_NAME} ohne pairs"})
            continue
        out.append({"path": path, "data": data})
    return sorted(out, key=lambda r: (str((r.get("data") or {}).get("captured_at") or ""), str(r["path"])))


def run_values(workspace) -> dict:
    """`values` aus dem jüngsten Migrationslauf (`reporting/runs/*-migration/state.json`), leer ohne Lauf.

    Liest nur, ohne `run_state` zu importieren (das importiert dieses Modul). So urteilen `run_state gate`,
    `open_items gate` und `visual_compare check` über dieselben Theme-IDs.
    """
    runs = sorted((Path(workspace) / "reporting" / "runs").glob("*-migration/state.json"))
    try:
        data = json.loads(runs[-1].read_text(encoding="utf-8")) if runs else {}
    except (OSError, ValueError):
        return {}
    values = data.get("values") if isinstance(data, dict) else None
    return values if isinstance(values, dict) else {}


def current_ids(config: dict, values: dict | None = None) -> tuple:
    """`(live, draft)` aus der Config, sonst aus dem Stand des Laufs."""
    block = migration_config(config)
    values = values or {}
    live = block.get("live_theme_id") or values.get("live_theme_id")
    draft = block.get("draft_theme_id") or values.get("draft_theme_id")
    return (str(live) if live else None), (str(draft) if draft else None)


def rollback_id(values: dict | None) -> str | None:
    """Nach dem Launch das alte Theme, das bis dahin veröffentlicht war; vor dem Launch None.

    Gilt nur mit `published_at` im Stand des Laufs: `rollback_theme_id` allein kann vor dem Launch als Plan
    eingetragen sein (Rückfall-Theme), dann ist die Referenz noch das Live-Theme.
    """
    values = values or {}
    rollback = values.get("rollback_theme_id")
    return str(rollback) if rollback and values.get("published_at") else None


def inferred_rollback(theme_a, shots_b: list, config_live=None) -> str | None:
    """Rückfall-Theme, wenn von Hand veröffentlicht wurde und der Lauf es nicht kennt; sonst None.

    Rechts zeigt der Theme-Nachweis die Rolle `main` (der Entwurf ist veröffentlicht), und links steht das
    Theme, das laut Config bis dahin live war. Dann ist links das Rückfall-Theme. So am 11.11.2026: im
    Admin veröffentlicht, im Lauf weder `published_at` noch `rollback_theme_id`.
    """
    roles = {(s.get("theme_check") or {}).get("found_role") for s in shots_b
             if isinstance(s, dict) and s.get("state") == "ok"} - {None, ""}
    return str(theme_a) if roles == {PUBLISHED_ROLE} and config_live and same_id(theme_a, config_live) else None


UNRECORDED = ("im Lauf fehlen published_at und rollback_theme_id, obwohl der Entwurf veröffentlicht ist; "
              "nachziehen mit run_state set (published_at, live_theme_id, rollback_theme_id)")


def _domain(config: dict) -> str:
    domain = str(config.get("domain") or "").strip().rstrip("/")
    if not domain and config.get("shopify_store"):
        domain = str(config["shopify_store"])
    return domain if not domain or "://" in domain else "https://" + domain


def recorded_name(workspace, theme_id) -> str | None:
    """Name eines Themes aus den Theme-Nachweisen früherer Bildvergleiche, jüngster zuerst."""
    for record in reversed(load_records(workspace)):
        data = record.get("data") or {}
        for side in SIDES:
            if same_id((data.get("themes") or {}).get(side), theme_id):
                name = theme_name([p.get(side) for p in data.get("pairs") or [] if isinstance(p, dict)])
                if name:
                    return name
    return None


def resolve_reference(workspace, config: dict, values: dict | None = None, themes: list | None = None,
                      themes_error: str | None = None) -> dict:
    """Das Referenz-Theme jedes Vergleichs und jeder Abnahme, mit ID, Name, Rolle und einer Zeile zum Nennen.

    Vor dem Launch das veröffentlichte Theme (Rolle `MAIN` in der Theme-Liste des Shops), nach dem Launch das
    alte Theme, das bis dahin veröffentlicht war (`rollback_theme_id`). `themes` ist die Theme-Liste aus
    Shopify (`theme.files.list_themes`); ohne sie kommen ID aus Config und Lauf und der Name aus früheren
    Bildvergleichen. Weicht `live_theme_id` vor dem Launch vom veröffentlichten Theme ab, gilt das
    veröffentlichte, und die Config ist veraltet.
    """
    values = run_values(workspace) if values is None else values
    rollback = rollback_id(values)
    live, _ = current_ids(config, values)
    kind = "rollback" if rollback else "published"
    theme_id = rollback or live
    problems, warnings = [], []
    by_id = {str(t.get("id") or "").rsplit("/", 1)[-1]: t for t in themes or [] if isinstance(t, dict)}
    main = [t for t in by_id.values() if t.get("role") == "MAIN"]
    source = "Theme-Liste des Shops" if themes is not None else "Config und Migrationslauf"
    _, draft = current_ids(config, values)
    if themes is not None and not rollback and len(main) == 1 and theme_id and draft \
            and same_id(str(main[0].get("id")).rsplit("/", 1)[-1], draft) and not same_id(theme_id, draft) \
            and any(same_id(k, theme_id) for k in by_id):
        # Von Hand veröffentlicht: der Entwurf ist live, das bisherige Live-Theme ist das Rückfall-Theme.
        rollback, kind = str(theme_id), "rollback"
        warnings.append(UNRECORDED)
    if themes is not None and not rollback:
        if len(main) == 1 and not same_id(str(main[0].get("id")).rsplit("/", 1)[-1], theme_id):
            published = str(main[0]["id"]).rsplit("/", 1)[-1]
            if theme_id:
                warnings.append(f"live_theme_id {theme_id} der Config ist nicht das veröffentlichte Theme; "
                                f"veröffentlicht ist {theme_label(published, main[0].get('name'))}. Config nachziehen")
            theme_id = published
        elif not main:
            problems.append("kein Theme mit Rolle MAIN in der Theme-Liste")
    if not theme_id:
        problems.append("keine Referenz: live_theme_id fehlt in Config und Lauf")
        return {"theme_id": None, "name": None, "role": None, "kind": kind, "source": source,
                "line": "Referenz: unbekannt", "preview_url": None, "ok": False, "problems": problems,
                "warnings": warnings}
    found = next((t for k, t in by_id.items() if same_id(k, theme_id)), None)
    if themes is not None and found is None:
        problems.append(f"Theme {theme_id} gibt es im Shop nicht (mehr)")
    name = (found or {}).get("name") or recorded_name(workspace, theme_id)
    role = (found or {}).get("role")
    if themes is None and themes_error:
        warnings.append(f"Theme-Liste nicht lesbar ({themes_error}); ID aus Config und Lauf"
                        + ("" if name else ", Name unbekannt"))
    if rollback and role == "MAIN":
        warnings.append(f"Rückfall-Theme {rollback} ist wieder veröffentlicht; Stand im Lauf prüfen")
    when = str(values.get("published_at") or "")[:10]
    when = f" am {when[8:10]}.{when[5:7]}.{when[:4]}" if len(when) == 10 else ""
    line = f"Referenz: {theme_label(theme_id, name)}, " + (
        f"bis zum Launch{when} veröffentlicht, jetzt Rückfall-Theme" if rollback else "veröffentlicht")
    domain = _domain(config)
    preview = f"{domain}/?preview_theme_id={theme_id}" if domain else None
    return {"theme_id": str(theme_id), "name": name, "role": role, "kind": kind, "source": source,
            "line": line, "preview_url": preview, "ok": not problems, "problems": problems, "warnings": warnings}


def _label(entry: dict) -> str:
    return f"{entry['page_id']} {DEVICE_LABEL.get(entry['device'], entry['device'])} {entry['side'].upper()}"


def evaluate(workspace, config: dict, values: dict | None = None) -> dict:
    """Ob der Bildvergleich für G4 vollständig ist, mit Gründen. Liest nur.

    Ohne `values` gelten die Werte des jüngsten Migrationslaufs (`run_values`).
    """
    values = run_values(workspace) if values is None else values
    live, draft = current_ids(config, values)
    rollback = rollback_id(values)
    problems = []
    try:
        page_ids = load_page_ids(workspace)
    except CompareError as exc:
        return {"ok": False, "problems": [str(exc)], "live_theme_id": live, "draft_theme_id": draft}
    if not draft:
        problems.append("draft_theme_id fehlt in der Config; ohne Entwurf kein Vergleich")
    records = load_records(workspace)
    problems += [r["error"] for r in records if "error" in r]
    readable = [r for r in records if "data" in r]
    qualified, rejected = [], []
    for record in readable:
        data = record["data"]
        themes = data.get("themes") or {}
        where = record["path"].parent.name
        if draft and not same_id(themes.get("b"), draft):
            rejected.append(f"{where}: rechts Theme {themes.get('b')}, Entwurf ist {draft}")
            continue
        guessed = None if rollback else inferred_rollback(
            themes.get("a"), [p.get("b") for p in data["pairs"] if isinstance(p, dict)], live)
        reference = reference_status(themes.get("a"), [p.get("a") for p in data["pairs"] if isinstance(p, dict)],
                                     live, rollback or guessed)
        if not reference["ok"]:
            rejected.append(f"{where}: " + "; ".join(reference["problems"]))
            continue
        qualified.append(record)
    if not readable:
        problems.append("kein Bildvergleich unter migration/verify/<date>/pairs.json")
    elif not qualified:
        problems.append(("kein Bildvergleich mit dem alten Theme links (Rückfall-Theme) und dem Entwurf rechts: "
                         if rollback else "kein Bildvergleich mit dem veröffentlichten Theme links und dem Entwurf "
                                          "rechts: ") + " | ".join(rejected[-3:]))
    slots, themes_by_slot = {}, {}
    reference_id, reference_name = None, None
    if qualified:
        reference_id = (qualified[-1]["data"].get("themes") or {}).get("a")
        reference_name = recorded_name(workspace, reference_id)
        for record in qualified:
            data = record["data"]
            themes = data.get("themes") or {}
            if not same_id(themes.get("a"), reference_id):
                continue  # inzwischen ist ein anderes Theme veröffentlicht
            for pair in data["pairs"]:
                if not isinstance(pair, dict):
                    continue
                key = (str(pair.get("page_id")), pair.get("device"))
                stamp = str(pair.get("captured_at") or data.get("captured_at") or "")
                if key not in slots or stamp >= slots[key][0]:
                    slots[key] = (stamp, pair)
                    themes_by_slot[id(pair)] = themes
    cover = coverage(page_ids, {k: v[1] for k, v in slots.items()}, lambda pair: themes_by_slot.get(id(pair), {}))
    if qualified and cover["missing"]:
        shown = ", ".join(f"{_label(m)} ({m['reason']})" for m in cover["missing"][:6])
        more = f" und {len(cover['missing']) - 6} weitere" if len(cover["missing"]) > 6 else ""
        problems.append(f"{len(cover['missing'])} von {cover['expected']} Aufnahmen fehlen oder zählen nicht: "
                        f"{shown}{more}")
    return {"ok": not problems and cover["complete"], "problems": problems, "live_theme_id": live,
            "draft_theme_id": draft, "rollback_theme_id": rollback,
            "reference": ({"theme_id": str(reference_id), "name": reference_name,
                           "label": theme_label(reference_id, reference_name)} if reference_id else None),
            "records": [str(r["path"].parent.name) for r in qualified], "rejected": rejected, "coverage": cover}


def gate_problems(workspace, config: dict, values: dict | None = None) -> list:
    """Sätze für `run_state gate --gate G4-acceptance`; leer heißt: der Bildvergleich hält nicht an."""
    result = evaluate(workspace, config, values)
    if result["ok"]:
        return []
    live = result.get("rollback_theme_id") or result.get("live_theme_id") or "<live-theme-id>"
    draft = result.get("draft_theme_id") or "<draft-theme-id>"
    hint = (f"aufnehmen mit compare-themes --compare (shoot_pair.py --a {live} --b {draft}), alle Beispielseiten, "
            "Rechner 1440 und Handy 390 mit Menü offen")
    return ["Bildvergleich unvollständig: " + "; ".join(result["problems"]) + f"; {hint}"]


def shop_themes(config: dict, workspace, transport=None) -> tuple:
    """`(themes, None)` aus Shopify oder `(None, grund)`; nur lesend."""
    from theme.files import list_themes  # erst hier: check läuft ohne Shopify-Zugang
    from theme.shopify import ShopifyError, transport_from_config
    try:
        transport = transport or transport_from_config(config, workspace=workspace)
        return list_themes(transport), None
    except (ShopifyError, OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"[:200]


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.visual_compare", description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("check", "reference"))
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.workspace)
    except ConfigError as exc:
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    if args.command == "reference":
        themes, error = shop_themes(config, args.workspace, transport)
        result = resolve_reference(args.workspace, config, themes=themes, themes_error=error)
        print(result["line"], file=sys.stderr, flush=True)
        emit(result)
        return EXIT_OK if result["ok"] else EXIT_FINDINGS
    result = evaluate(args.workspace, config)
    emit(result)
    return EXIT_OK if result["ok"] else EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
