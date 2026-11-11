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
  Ganzseiten-Bild in der verlangten Breite

`shoot_pair.py` schreibt dafür neben die Bilder im Kundenordner einen Eintrag in
den Workspace, `migration/verify/<date>/pairs.json`. Gelesen werden alle diese
Einträge; je Seite und Breite zählt die jüngste Aufnahme. So reicht nach einer
Korrektur das Nachholen der betroffenen Seiten, und eine fehlgeschlagene neue
Aufnahme verdeckt nie still eine alte gelungene: dann zählt die Seite nicht.

Aufruf (aus dem Workspace):
    python3 -m theme.visual_compare check

Ausgabe eine JSON-Zeile. Exit 0 vollständig, 1 unvollständig, 2 Fehler.
"""
import argparse
import json
import sys
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


def reference_status(theme_a, shots_a: list, config_live=None) -> dict:
    """Ob die linke Seite das veröffentlichte Theme ist.

    Beleg ist die Rolle im Theme-Nachweis der Seiten (`main`). Sie gilt vor der Config, weil eine
    veraltete `live_theme_id` genau den Fehler vom 11.11.2026 erlaubt: ein älteres Theme als Vorlage.
    Fehlt die Rolle, muss die ID der Config entsprechen. Eine abweichende Config bei belegter Rolle ist
    eine Warnung, kein Fehler: dann ist die Config veraltet, nicht der Vergleich.
    """
    roles = sorted({(s.get("theme_check") or {}).get("found_role") for s in shots_a
                    if isinstance(s, dict) and s.get("state") == "ok"} - {None, ""})
    matches = same_id(theme_a, config_live) if config_live else None
    problems, warnings = [], []
    if roles and roles != [PUBLISHED_ROLE]:
        problems.append(f"links steht Theme {theme_a} mit Rolle {', '.join(roles)}, nicht das veröffentlichte "
                        "Theme; Referenz ist immer das Live-Theme mit seiner ID")
    elif not roles:
        if matches is None:
            problems.append(f"Rolle von Theme {theme_a} nicht belegt und keine live_theme_id in der Config")
        elif not matches:
            problems.append(f"links steht Theme {theme_a}, live_theme_id der Config ist {config_live}, und die "
                            "Seiten belegen keine Rolle")
    if roles == [PUBLISHED_ROLE] and matches is False:
        warnings.append(f"live_theme_id {config_live} der Config ist veraltet: veröffentlicht ist {theme_a}")
    return {"theme_id": str(theme_a or ""), "roles": roles, "published": roles == [PUBLISHED_ROLE],
            "config_live_theme_id": str(config_live) if config_live else None, "matches_config": matches,
            "ok": not problems, "problems": problems, "warnings": warnings}


def coverage(page_ids: list, slots: dict, themes_of=None) -> dict:
    """Abdeckung je Seite, Breite und Seite des Paars.

    `slots` ordnet `(page_id, device)` ein Paar zu (`{"a": shot, "b": shot}`). `themes_of(pair)` liefert
    die erwarteten Theme-IDs des Paars; ohne Angabe stehen sie im Paar unter `themes`.
    """
    missing = []
    for page_id in page_ids:
        for device in DEVICES:
            pair = slots.get((page_id, device))
            themes = (themes_of(pair) if themes_of else (pair or {}).get("themes")) or {}
            for side in SIDES:
                problem = shot_problem((pair or {}).get(side), device, themes.get(side))
                if problem:
                    missing.append({"page_id": page_id, "device": device, "side": side, "reason": problem})
    expected = len(page_ids) * len(DEVICES) * len(SIDES)
    return {"pages": len(page_ids), "devices": list(DEVICES), "widths": dict(WIDTHS), "expected": expected,
            "valid": expected - len(missing), "missing": missing, "complete": bool(page_ids) and not missing}


def record_summary(page_ids: list, pairs: list, themes: dict, config_live=None) -> dict:
    """Referenz und Abdeckung eines Laufs von `shoot_pair.py`, wie sie in `pairs.json` stehen."""
    slots = {(p.get("page_id"), p.get("device")): p for p in pairs if isinstance(p, dict)}
    reference = reference_status(themes.get("a"), [p.get("a") for p in pairs if isinstance(p, dict)], config_live)
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


def _label(entry: dict) -> str:
    return f"{entry['page_id']} {DEVICE_LABEL.get(entry['device'], entry['device'])} {entry['side'].upper()}"


def evaluate(workspace, config: dict, values: dict | None = None) -> dict:
    """Ob der Bildvergleich für G4 vollständig ist, mit Gründen. Liest nur.

    Ohne `values` gelten die Werte des jüngsten Migrationslaufs (`run_values`).
    """
    live, draft = current_ids(config, run_values(workspace) if values is None else values)
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
        reference = reference_status(themes.get("a"), [p.get("a") for p in data["pairs"] if isinstance(p, dict)],
                                     live)
        if not reference["ok"]:
            rejected.append(f"{where}: " + "; ".join(reference["problems"]))
            continue
        qualified.append(record)
    if not readable:
        problems.append("kein Bildvergleich unter migration/verify/<date>/pairs.json")
    elif not qualified:
        problems.append("kein Bildvergleich mit dem veröffentlichten Theme links und dem Entwurf rechts: "
                        + " | ".join(rejected[-3:]))
    slots, themes_by_slot = {}, {}
    if qualified:
        reference_id = (qualified[-1]["data"].get("themes") or {}).get("a")
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
            "draft_theme_id": draft, "records": [str(r["path"].parent.name) for r in qualified],
            "rejected": rejected, "coverage": cover}


def gate_problems(workspace, config: dict, values: dict | None = None) -> list:
    """Sätze für `run_state gate --gate G4-acceptance`; leer heißt: der Bildvergleich hält nicht an."""
    result = evaluate(workspace, config, values)
    if result["ok"]:
        return []
    live = result.get("live_theme_id") or "<live-theme-id>"
    draft = result.get("draft_theme_id") or "<draft-theme-id>"
    hint = (f"aufnehmen mit compare-themes --compare (shoot_pair.py --a {live} --b {draft}), alle Beispielseiten, "
            "Rechner 1440 und Handy 390")
    return ["Bildvergleich unvollständig: " + "; ".join(result["problems"]) + f"; {hint}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.visual_compare", description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.workspace)
    except ConfigError as exc:
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    result = evaluate(args.workspace, config)
    emit(result)
    return EXIT_OK if result["ok"] else EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
