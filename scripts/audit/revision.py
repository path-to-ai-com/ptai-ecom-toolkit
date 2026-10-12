#!/usr/bin/env python3
"""Eine Fassung eines Laufs beiseitelegen, bevor eine neue darüber entsteht.

**Wofür.** Die Rohdaten eines Laufs sind gut, aber die Auswertung darüber hat
sich geändert: eine Analyse ist dazugekommen, eine Regel wurde gefixt. Dann
läuft Phase 2 bis 4 erneut auf denselben Snapshots. Was dabei entsteht,
überschreibt die vorige Fassung, und die war ein Kundendokument oder hätte
eines werden können.

**Warum nicht einfach überschreiben.** Ein Report trägt Zahlen, über die
gesprochen wurde. Wer eine Fassung ersetzt, ohne die alte zu behalten, kann
später nicht mehr sagen, warum eine Zahl heute anders lautet als im Termin.
Das Archiv beantwortet genau diese Frage und kostet ein paar Kilobyte.

**Was nicht mitgeht.** `report-text.json` bleibt liegen. Darin stehen die
Sätze, die ein Mensch geschrieben hat (Cover-Headline, Kernaussagen je
Kapitel); sie gelten für den Lauf, nicht für die Fassung, und wer sie
mitarchiviert, lässt den Betreiber sie ein zweites Mal schreiben.

CLI:
    python3 -m audit.revision --workspace . --run-id 2026-10-01-audit
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from audit import brand as brand_mod
from audit import measures

#: Was eine Fassung ausmacht: die Befunde je Disziplin, ihre Belegbilder und
#: was daraus gerendert wurde. Verzeichnisse wandern als Ganzes, Dateien
#: einzeln. `proof/` gehört dazu, weil die Befunde einer Fassung auf genau
#: diese Bilder zeigen; eine neue Fassung nimmt ihre eigenen auf.
BEWEGT_ORDNER = ("findings", "proof")
#: `carry-over.json` (Bestand prüfen, `audit.carry_over`) gehört zur Fassung:
#: `reset_measures()` nimmt die übertragenen Stores dieses Laufs zurück, und
#: eine neue Analyse prüft den Bestand neu.
BEWEGT_DATEIEN = ("audit.pdf", "audit.html", "audit-web.html", "carry-over.json")

#: Der Backlog liegt eine Ebene höher als der Lauf, weil er über alle Läufe
#: gilt, und bei einer Marke mit mehreren Stores im Ordner der Marke
#: (`audit.brand`). Er wird kopiert, nicht verschoben: die Maßnahmen, die ein
#: Mensch schon angefasst hat, bleiben im Original stehen.
BACKLOG = ("measures.json", "measures.md")


def revisions_dir(workspace, run_id: str) -> Path:
    return Path(workspace) / "reporting" / "runs" / run_id / "revisions"


def next_number(workspace, run_id: str) -> str:
    """Die nächste freie Fassungsnummer, zweistellig."""
    base = revisions_dir(workspace, run_id)
    if not base.is_dir():
        return "01"
    genutzt = [int(d.name) for d in base.iterdir()
               if d.is_dir() and d.name.isdigit()]
    return f"{max(genutzt, default=0) + 1:02d}"


def archive(workspace, run_id: str, copy: bool = False) -> Path | None:
    """Legt die aktuelle Fassung nach `revisions/NN/` und gibt den Pfad zurück.

    `copy=True` kopiert statt zu verschieben. Das braucht der Nachlauf einer
    einzelnen Disziplin (`audit.rerun`): er ersetzt nur deren Befund-Datei,
    die übrigen Befunde und `report-text.json` müssen im Lauf stehen bleiben,
    sonst hat der neu gebaute Gesamtreport nur noch eine Disziplin.

    `None` heisst: es gab nichts zu archivieren, der Lauf hat noch keine
    Befunde und keinen Report. Das ist kein Fehler, sondern der Normalfall beim
    allerersten Durchgang.
    """
    workspace = Path(workspace)
    run = workspace / "reporting" / "runs" / run_id
    quellen = [run / name for name in (*BEWEGT_ORDNER, *BEWEGT_DATEIEN)]
    # Ein leerer `findings/`-Ordner ist keine Fassung. Er entsteht schon beim
    # Anlegen des Laufs, und wer ihn archiviert, legt beim ersten Durchgang
    # eine leere Fassung 01 an, gegen die später niemand vergleichen kann.
    if not any(any(q.iterdir()) if q.is_dir() else q.exists() for q in quellen):
        return None

    ziel = revisions_dir(workspace, run_id) / next_number(workspace, run_id)
    ziel.mkdir(parents=True)
    for quelle in quellen:
        if not quelle.exists():
            continue
        if not copy:
            shutil.move(str(quelle), str(ziel / quelle.name))
        elif quelle.is_dir():
            shutil.copytree(quelle, ziel / quelle.name)
        else:
            shutil.copy2(quelle, ziel / quelle.name)
    backlog_dir = measures.file_path(workspace).parent
    for name in BACKLOG:
        datei = backlog_dir / name
        if datei.exists():
            shutil.copy2(datei, ziel / name)
    return ziel


def keep(measure: dict) -> bool:
    """Bleibt diese Maßnahme beim Zurücksetzen stehen?

    Ja, sobald ein Mensch sie angefasst hat: ein Status jenseits von `open`
    oder mehr als der eine Eintrag, den `create()` selbst schreibt. Diese
    Arbeit darf eine neue Analyse nicht wegwerfen, auch wenn sie denselben
    Befund noch einmal stellt. Der Preis ist eine mögliche Dublette, und die
    ist billiger als eine verlorene Entscheidung.
    """
    if measure.get("status") != "open":
        return True
    return len(measure.get("history") or []) > 1


def reset_measures(backlog: dict, shop: str | None = None,
                   run_id: str | None = None) -> tuple[dict, int, int]:
    """Nimmt zurück, was die vorige Auswertung dieses Laufs angelegt hat.

    Gibt den neuen Backlog zurück, dazu die Zahl der entfernten und der
    behaltenen Maßnahmen. **`next_id` sinkt nie** (Spec 5.1, Regel 6): eine
    entfernte Kennung bleibt verbraucht. Bis zum 09.10.2026 zählte `next_id`
    hinter den behaltenen weiter; in der Liste einer Marke hätte eine neue
    Analyse in UK damit Kennungen neu vergeben, die EU schon trägt.

    **v1 (Liste eines Stores):** unberührte Maßnahmen gehen, angefasste
    bleiben (`keep()`).

    **v2 (Liste einer Marke, D12):** nur, was dieser Store in diesem Lauf
    geschrieben hat. Eine Maßnahme mit `created_run_id == run_id`, die nur
    Einträge dieses Laufs trägt und nur für diesen Store gilt, geht. Bei jeder
    anderen gehen nur die Verlaufseinträge unter `by_shop.<shop>` mit dieser
    `run_id`; bleibt dort keiner, ist der Store in diesem Lauf dazugekommen und
    fällt aus `shops`. Maßnahmen anderer Stores bleiben unangetastet.
    """
    alle = backlog.get("measures") or []
    if not measures.is_v2(backlog):
        behalten = [m for m in alle if keep(m)]
        return ({**backlog, "next_id": backlog.get("next_id", 1), "measures": behalten},
                len(alle) - len(behalten), len(behalten))
    if not shop or not run_id:
        raise ValueError("Die Liste einer Marke setzt nur zurück, was ein Store in "
                         "einem Lauf geschrieben hat: shop und run_id angeben.")

    behalten = []
    for m in alle:
        by_shop = m.get("by_shop") or {}
        own = by_shop.get(shop)
        if m.get("created_run_id") == run_id:
            others = [s for s in m.get("shops") or [] if s != shop]
            own_history = (own or {}).get("history") or []
            if not others and all(h.get("run_id") == run_id for h in own_history):
                continue
            # Angefasst: von Hand gemeldet oder schon in einem anderen Store.
            # Bleibt ganz, wie bisher eine angefasste Maßnahme in v1.
            behalten.append(m)
            continue
        if own is None:
            behalten.append(m)
            continue
        history = own.get("history") or []
        rest = [h for h in history if h.get("run_id") != run_id]
        if len(rest) == len(history):
            behalten.append(m)
        elif rest:
            behalten.append({**m, "by_shop": {
                **by_shop, shop: {**own, "history": rest, "status": rest[-1]["status"]}}})
        else:
            shops = [s for s in m.get("shops") or [] if s != shop]
            behalten.append({**m, "shops": shops,
                             "by_shop": {k: v for k, v in by_shop.items() if k != shop}})
    return ({**backlog, "measures": behalten},
            len(alle) - len(behalten), len(behalten))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--keep-measures", action="store_true",
                        help="den Backlog nicht anfassen")
    parser.add_argument("--copy", action="store_true",
                        help="Fassung kopieren statt verschieben, für den Nachlauf "
                             "einer Disziplin; lässt den Backlog immer stehen")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace)
    ziel = archive(workspace, args.run_id, copy=args.copy)
    if ziel is None:
        print("Nichts zu archivieren: dieser Lauf hat noch keine Fassung.")
    else:
        print(f"Fassung liegt in {ziel.relative_to(workspace)}")

    # Der Nachlauf einer Disziplin setzt nie den Backlog zurück: die Maßnahmen
    # der anderen Disziplinen gelten weiter, auch die unberührten.
    if args.keep_measures or args.copy:
        return 0
    if not measures.file_path(workspace).exists():
        return 0
    shop = brand_mod.shop_slug(brand_mod.read_config(workspace))
    # Lesen, Sieben und Schreiben am Stück unter der Sperre der Marke: ein Lauf
    # in einem anderen Store darf dazwischen nicht schreiben (D4). Geschrieben
    # wird über save(), das next_id und fremde Änderungen prüft.
    with measures.locked(workspace):
        neu, entfernt, behalten = reset_measures(
            measures.load(workspace), shop=shop, run_id=args.run_id)
        measures.save(workspace, neu)
    print(f"Backlog: {entfernt} Maßnahmen dieser Auswertung entfernt, "
          f"{behalten} behalten. next_id bleibt {neu.get('next_id')}.")
    if behalten:
        print("  Die behaltenen tragen einen Status oder eine Historie. Eine "
              "neue Analyse kann denselben Befund noch einmal stellen; das "
              "gibt eine Dublette und ist billiger als eine verlorene "
              "Entscheidung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
