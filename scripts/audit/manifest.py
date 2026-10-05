#!/usr/bin/env python3
"""Das Verzeichnis der Läufe einer Brand im Bucket.

**Ein Verzeichnis, kein Schema** (Spec Abschnitt 4). Es listet, welche Läufe es
gibt und wo ihre Dateien liegen. Es enthält **keine Kennzahl**: sobald Zahlen
darin stünden, wäre es ein normalisiertes Schema und damit die Datenbank durch
die Hintertür, die Abschnitt 9 ausdrücklich vertagt.

Es löst zwei praktische Probleme. Die App muss den Bucket nicht durchsuchen,
und die beiden gewachsenen Ablage-Layouts lassen sich nebeneinander bedienen:
ein Kunde liegt noch unter `reporting/reports/`, ein anderer schon unter
`reporting/runs/`. Der Manifest zeigt auf beides, ohne dass im Workspace etwas
umzieht.

**Der Freigabestatus lebt hier.** `publish` lädt hoch und setzt ihn nie,
`release` setzt ihn. Ein hochgeladener Lauf ist für den Kunden unsichtbar, bis
ein Mensch ihn gelesen hat.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

#: Version des Manifest-Formats. Steht drin, damit die App eine aeltere Fassung
#: erkennt, statt an einem fehlenden Feld zu scheitern.
VERSION = 1

#: Die Lauf-Arten, die es gibt. `light` ist der Verkaufs-Audit fuer einen kalten
#: Lead, `audit` der Vollaudit, `report` der wiederkehrende Bericht.
#: `inventory` ist die Bestandsaufnahme vor einem Theme-Wechsel und die einzige
#: Art, die Auswahl-Antworten des Kunden traegt. `tracking` dokumentiert eine
#: konkrete Tracking-Architektur und nimmt chronologische Kommentare auf.
#: `test` ist die Testrunde vor einem Launch (`test.json`): je Punkt ein Stand
#: aus festen Optionen und Rueckmeldungen des Teams, seit dem 24.09.2026.
KINDS = ("audit", "report", "light", "inventory", "tracking", "test")

#: Dateien, die nie in den Bucket gehen. **Ausschlussliste, keine Auswahlliste**
#: (Spec Abschnitt 5): alles andere geht hoch, denn es sind die Daten des
#: Kunden. Wer eine Auswahlliste pflegt, vergisst die Datei, die der Kunde
#: gerade sucht.
EXCLUDED = ("dfs-ledger.jsonl",)


def path_for(brand: str, shop: str, run_id: str = "", revision: int = 1) -> str:
    """Der Bucket-Pfad. Login-Ebene ist die Brand, Ablage-Ebene der Shop.

    **Die erste Fassung liegt flach.** Sie behaelt den Pfad, den sie immer
    hatte, damit kein Lauf umziehen muss, der heute schon im Bucket liegt.
    Erst eine Korrektur bekommt mit `v02` einen eigenen Platz. Der Upload
    schickt jede Datei mit `x-upsert`, also ueberschreibt eine zweite Fassung
    unter demselben Namen die erste Byte fuer Byte; unter einem eigenen Pfad
    kann das nicht passieren.

    **Zwei Dinge heissen Fassung, und sie sind nicht dasselbe.** `revisions/`
    im Workspace sind Werkstatt-Staende, die nie jemand freigegeben hat, und
    `collect_files` schliesst sie aus. `revision` hier ist die Zaehlung der
    Staende, die veroeffentlicht wurden, also derer, die ein Kunde sehen
    konnte. Wer die beiden verwechselt, laedt die Werkstatt hoch.
    """
    base = f"brands/{brand}/shops/{shop}"
    if not run_id:
        return base
    run = f"{base}/runs/{run_id}"
    return run if revision <= 1 else f"{run}/v{revision:02d}"


def next_revision(manifest_data: dict, shop: str, run_id: str, *,
                  replace: bool = False) -> int:
    """Welche Fassung ein publish dieses Laufs schreiben wuerde.

    `replace` ist die Hintertuer fuer die Korrektur, die niemand gesehen hat:
    sie behaelt die laufende Nummer und ueberschreibt damit wie frueher.
    """
    for run in manifest_data.get("runs") or []:
        if (run["shop"], run["run_id"]) == (shop, run_id):
            current = run.get("revision", 1)
            return current if replace else current + 1
    return 1


def empty(brand: str, name: str, shops: dict | None = None) -> dict:
    """Ein leeres Verzeichnis fuer eine Brand."""
    return {"version": VERSION, "brand": brand, "name": name,
            "shops": shops or {}, "runs": []}


def add_run(manifest_data: dict, *, shop: str, run_id: str, kind: str,
            cadence: str | None, period: str | None, run_date: str,
            files: dict, revision: int = 1, note: str | None = None,
            title: str | None = None, today: date | None = None) -> dict:
    """Traegt einen Lauf ein und gibt ein neues Manifest zurueck.

    Ein Lauf, den es schon gibt, wird ersetzt und behaelt dabei seinen
    Freigabestatus: ein erneutes `publish` derselben Lauf-ID ist eine
    Korrektur, keine Ruecknahme der Freigabe. Wer eine Freigabe zuruecknehmen
    will, tut das ausdruecklich.

    **`path` und `files` zeigen immer auf die aktuelle Fassung**, damit jede
    bestehende Ansicht unveraendert weiterlaeuft. `revisions` haelt daneben
    jede Fassung mit ihrem eigenen Pfad und ihrer eigenen Dateiliste; erst
    dadurch kann das Portal eine aeltere oeffnen. `note` ist der Satz, was an
    dieser Fassung korrigiert wurde, und steht im Verlauf beim Kunden.

    `title` ist der eigene Titel des Laufs ohne Shop, etwa "Abstimmung vor dem
    Theme-Wechsel", und kommt aus der `state.json`. Fehlt er, nennt das Portal
    die Art ("Beispielshop: Abstimmung"). Bis zum 28.09.2026 stand der Titel
    einer Abstimmung fest im Portal und hätte jede andere Brand mitbetroffen.
    """
    if kind not in KINDS:
        raise ValueError(f"unbekannte Lauf-Art: {kind!r}")
    if not shop:
        raise ValueError("ein Lauf gehoert zu einem Shop")
    by_key = {(r["shop"], r["run_id"]): r for r in manifest_data.get("runs") or []}
    previous = by_key.get((shop, run_id))
    stamp = (today or date.today()).isoformat()
    path = path_for(manifest_data["brand"], shop, run_id, revision)

    # Ein Lauf aus der Zeit vor den Fassungen hat keine Liste. Seine Fassung 1
    # wird aus dem nachgetragen, was der Eintrag ohnehin schon sagt.
    history = list((previous or {}).get("revisions") or [])
    if previous and not history:
        history = [{"no": previous.get("revision", 1),
                    "published_at": previous.get("published_at"),
                    "note": None,
                    "path": previous["path"],
                    "files": previous["files"]}]
    history = [r for r in history if r["no"] != revision]
    history.append({"no": revision, "published_at": stamp, "note": note,
                    "path": path, "files": files})
    history.sort(key=lambda r: r["no"])

    entry = {
        "shop": shop,
        "run_id": run_id,
        "kind": kind,
        "cadence": cadence,
        "period": period,
        "title": (title or "").strip() or None,
        "run_date": run_date,
        "published_at": stamp,
        # **Freigabe ist nie eine Nebenwirkung des Hochladens.**
        "released": bool(previous and previous.get("released")),
        "released_at": (previous or {}).get("released_at"),
        "revision": revision,
        "revisions": history,
        "path": path,
        "files": files,
    }
    by_key[(shop, run_id)] = entry
    runs = sorted(by_key.values(),
                  key=lambda r: (r["shop"], r["run_date"], r["run_id"]),
                  reverse=True)
    return {**manifest_data, "runs": runs}


def release(manifest_data: dict, shop: str, run_id: str,
            today: date | None = None) -> dict:
    """Gibt einen Lauf frei. Erst danach sieht der Kunde ihn."""
    runs, found = [], False
    for r in manifest_data.get("runs") or []:
        if (r["shop"], r["run_id"]) == (shop, run_id):
            r = {**r, "released": True,
                 "released_at": (today or date.today()).isoformat()}
            found = True
        runs.append(r)
    if not found:
        raise KeyError(f"kein Lauf {run_id!r} fuer Shop {shop!r} im Manifest")
    return {**manifest_data, "runs": runs}


def released(manifest_data: dict, shop: str | None = None) -> list[dict]:
    """Was der Kunde sehen darf, neueste zuerst."""
    return [r for r in manifest_data.get("runs") or []
            if r.get("released") and (shop is None or r["shop"] == shop)]


def collect_files(run_dir: Path) -> dict:
    """Die Dateien eines Lauf-Ordners, relativ zu ihm, ohne die Ausschlussliste.

    Die Zuordnung ist bewusst flach: der Manifest nennt Pfade, keine Typen.
    Was `report.html` ist und was `findings/` sind, weiss die App.
    """
    out = {}
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name in EXCLUDED:
            continue
        rel = path.relative_to(run_dir).as_posix()
        # Fassungen sind Archiv und gehoeren nicht in die Kundenansicht: sie
        # zeigen Zwischenstaende, die nie jemand freigegeben hat.
        if rel.startswith("revisions/"):
            continue
        out[rel] = path.stat().st_size
    return out


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: Path, manifest_data: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path
