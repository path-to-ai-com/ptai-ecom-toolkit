#!/usr/bin/env python3
"""Der Maßnahmen-Backlog als Zustand über alle Läufe (Spec Abschnitt 9).

Der Backlog ist keine Liste, die ein Audit einmal erzeugt, sondern Zustand:
jeder Folgelauf liest ihn, prüft offene Maßnahmen gegen ihre Prüfregel und
trägt neue Befunde nach. Deshalb, genau wie bei der Baseline, zwei Dateien:
**`measures.json` ist der Zustand**, `measures.md` (Task 12) die daraus
gerenderte lesbare Fassung. Von Hand geändert wird nur die JSON, oder besser:
über den Lauf.

Drei Regeln tragen dieses Modul:

1. **Eine ID wird nie wiederverwendet.** `M-001` bezeichnet eine Maßnahme für
   die Lebensdauer des Accounts. Die nächste ID kommt aus `next_id`, einem
   Zähler im Dokument selbst, nie aus der Länge der Liste: eine gelöschte
   Maßnahme darf ihre ID nie an eine neue vergeben, sonst bezeichnet `M-007`
   in einem späteren Report etwas anderes als sechs Monate zuvor.
2. **Keine Maßnahme ohne Beleg.** Der Audit kennt keinen Befund ohne Quellfeld
   oder URL, das gilt für die daraus entstehende Maßnahme genauso. Ein leerer
   `evidence` fliegt mit `ValueError`.
3. **Eine Hypothese wird nie priorisiert.** Sie wird als Test ausgewiesen und
   nimmt an der Rangfolge aus Sicherheit, Hebel und Aufwand nicht teil.

`create()` und `set_status()` mutieren das übergebene Dokument nicht,
sondern geben ein neues zurück: ein Aufrufer, der versehentlich das alte
Dokument weiterreicht, bekommt sichtbar den alten Stand, keine stille
Verwechslung zweier Objekte, die dieselbe Liste teilen.

**Zwei Formate.** v1 ist die Liste eines Stores (`{"next_id", "measures"}`,
Status und Verlauf an der Maßnahme). v2 ist die Liste einer Marke mit mehreren
Stores (Spec `ptai-portal` 2026-10-08, Abschnitt
5.1): `version: 2`, `brand`, und je Maßnahme `shops` plus `by_shop.<shop>` mit
Status, Verlauf, Befund (`finding_run`, `finding_id`) und Beleg. Was für alle
Stores gleich ist, steht an der Maßnahme. Wo die Datei liegt, entscheidet
`audit.brand`: mit `brand_workspace` in der Config im Ordner der Marke, sonst
im Store. Ein Store, der noch nicht umgezogen ist, liest und schreibt weiter
v1. `create()`, `set_status()` und `check()` nehmen in v2 den Store und
schreiben nur `by_shop.<shop>`; `project()` macht aus v2 die Sicht eines
Stores im Zuschnitt von v1, damit Report, QA und Score nur dessen Maßnahmen
sehen.

**Jedes Lesen, Ändern und Schreiben läuft unter der Sperre der Marke**
(`locked()`, `update()`), und `save()` verweigert zwei stille Verluste: einen
`next_id`, der unter den auf der Platte fällt, und eine Datei, die seit dem
letzten `load()` dieses Prozesses ein anderer geschrieben hat.
"""
import contextlib
import hashlib
import json
import os
from datetime import date
from pathlib import Path

from audit import brand as brand_mod
from audit import env

#: Das Format der Liste einer Marke. Eine Datei ohne `version` ist v1.
VERSION = 2

#: Was je Store unter `by_shop.<shop>` steht. Alles andere gilt für die Maßnahme.
SHOP_FIELDS = ("status", "history", "finding_run", "finding_id",
               "evidence", "evidence_text")

#: Sicherheit einer Maßnahme, geordnet nach fallender Verlässlichkeit.
#: "hypothesis" entscheidet allein über `type`, siehe `create()`.
CONFIDENCE = ("confirmed", "plausible", "hypothesis")

#: Hebel-Band, geordnet nach fallendem Hebel (aus den Baseline-Zahlen
#: abgeleitet, Spec Abschnitt 9, nicht geschätzt).
LEVERAGE = ("high", "medium", "low")

#: Aufwand-Band, geordnet nach steigendem Aufwand.
EFFORT = ("small", "medium", "large")

#: Wer eine Maßnahme umsetzt (Spec Abschnitt 9). `"Path to AI"` meint den
#: Betreiber, der den Lauf fährt, nicht die Firma. Der Wert bleibt so, weil ein
#: neuer eine Migration in `create()`, `load()`, `report_build.py` und im Portal
#: bräuchte, das den Rohwert zeigt (Spec 2026-09-11, D7). Angezeigt wird er nur
#: über `responsible_label()`.
RESPONSIBLE = ("Path to AI", "Customer", "Third Party")

#: Status einer Maßnahme (Spec Abschnitt 9). Eine neue Maßnahme startet immer
#: bei "open", siehe `create()`.
STATUS = ("open", "in_progress", "implemented", "rejected", "obsolete")

#: Status, mit denen eine Maßnahme in einem Store nicht mehr geprüft und nicht
#: wieder geöffnet wird: verworfen und überholt, in der Datei oder von der
#: Marke im Cockpit gemeldet (Spec `ptai-portal` 2026-10-08, 5.5, D10).
EXCLUDING_STATUS = ("rejected", "obsolete")

#: Unsere Empfehlung zu dieser Maßnahme. Ein Urteil über die Maßnahme, kein
#: gemessener Zustand, und **keine Aussage darüber, wer entscheiden darf**:
#: jede Maßnahme ist ein Vorschlag, und über jede entscheidet der Kunde.
#:
#: "recommended"  wir empfehlen die Umsetzung, ein Ja genügt
#: "decision"     wir können sie nicht für ihn treffen: Geschmack, mehrere
#:                Wege, Kosten oder Arbeit bei ihm
#:
#: Bis zum 17.09.2026 gab es eine dritte Stufe "not_required" für Maßnahmen,
#: die im Shop unsichtbar bleiben. Sie ist raus, weil sie im Portal als "ihr
#: habt hier nichts zu entscheiden" gelesen wurde, und das stimmt nicht.
#:
#: **Ohne Angabe bleibt das Feld leer**, siehe `create()`. Ein Ersatzwert wäre
#: die Behauptung, jemand habe die Maßnahme eingeordnet.
APPROVAL = ("recommended", "decision")

#: Ergebnis von `check()` für einen einzelnen Lauf. Nur "implemented" und
#: "open" sind zugleich gültige Werte für `set_status()`, "unchecked" nie:
#: der Aufrufer darf einen ungeprüften Stand nicht als Statuswechsel
#: schreiben, siehe `check()`.
CHECK_RESULTS = ("implemented", "open", "unchecked")

#: Disziplin, deren Befunde unabhängig von Sicherheit, Hebel und Aufwand oben
#: stehen (Spec Abschnitt 9, Priorisierung).
PRIORITY_DISCIPLINE = "data_quality"

_CONFIDENCE_RANK = {value: i for i, value in enumerate(CONFIDENCE)}
_LEVERAGE_RANK = {value: i for i, value in enumerate(LEVERAGE)}
_EFFORT_RANK = {value: i for i, value in enumerate(EFFORT)}


def empty(brand: str | None = None) -> dict:
    """Das leere Dokument: kein Vorlauf, Zähler startet bei 1.

    Mit `brand` das leere Dokument einer Marke (v2), sonst das eines Stores (v1).
    """
    if brand:
        return {"version": VERSION, "brand": brand, "next_id": 1, "measures": []}
    return {"next_id": 1, "measures": []}


def is_v2(backlog) -> bool:
    """Ist das die Liste einer Marke (Format v2)?"""
    return isinstance(backlog, dict) and backlog.get("version") == VERSION


def finding_of(measure: dict) -> str | None:
    """Die Kennung des Befunds hinter einer Maßnahme, in v1 wie in der
    Projektion von v2. v1 heißt das Feld `finding_ref`, v2 `finding_id` (D12)."""
    return measure.get("finding_id") or measure.get("finding_ref") or None


def _require_shop(shop: str | None, what: str) -> str:
    if not shop or not isinstance(shop, str):
        raise ValueError(
            f"{what} in der Liste einer Marke braucht den Store (shop=...). "
            "Der Store steht in reporting/config.json unter portal.shop.")
    return shop


def create(backlog: dict, *, title: str, discipline: str, evidence: str,
           confidence: str, leverage: str, effort: str,
           responsible: str | None = None, data_source: str | None = None,
           check_rule: str | None = None, finding_ref: str | None = None,
           approval: str | None = None, intent: str | None = None,
           effect: str | None = None, needs: str | None = None,
           evidence_text: str | None = None, today: date | None = None,
           shop: str | None = None, run_id: str | None = None,
           finding_id: str | None = None,
           finding_run: str | None = None,
           target_metric: str | None = None) -> dict:
    """Legt eine neue Maßnahme an und gibt ein neues Dokument zurück.

    Validiert vollständig, bevor eine ID vergeben wird: eine abgelehnte
    Erstellung (leerer Beleg, unbekannte Sicherheit, ...) darf `next_id`
    nicht weiterzählen, sonst entstünde eine Lücke in der ID-Reihe, die beim
    nächsten Blick auf den Backlog wie eine verlorene Maßnahme aussieht.

    `confidence` entscheidet allein über `type`: "hypothesis" wird nie zur
    Maßnahme, sondern zum Test, siehe Spec Abschnitt 9 ("Eine Hypothese wird
    nie priorisiert, sie wird als Test formuliert").

    `finding_ref` ist die Kennung des Befunds, aus dem die Maßnahme folgt
    (etwa "MES-01"). Sie ist der Grund, warum der Report eine Maßnahme
    beauftragbar zeigen kann: ohne sie steht im Backlog eine Handlung ohne
    Herkunft, und der Leser kann nicht prüfen, worauf sie sich stützt. Sie
    bleibt optional, weil eine Maßnahme auch aus einer Lücke in der Datenlage
    folgen kann, für die es keinen Befund am Shop gibt.

    **Vier Felder erklären die Maßnahme dem Kunden** (seit 17.09.2026, Anlass
    in `SKILL.md`, Abschnitt Maßnahmen): `intent` sagt, was wir vorhaben,
    `effect`, was es bringt oder was es kostet, wenn es so bleibt, `needs`,
    was wir dafür vom Kundenteam brauchen, und `evidence_text` trägt den Beleg
    als Satz mit Zahlen. Bis dahin stand im Portal nur `evidence`, also ein
    Pfad in eine Rohdatei, und ein Kunde konnte einer Maßnahme außer ihrem
    Titel nichts entnehmen.

    Alle vier sind freiwillig, damit ein Folgelauf über einen alten Backlog
    nicht bricht; `qa.py` zählt, wie viele Maßnahmen ohne sie entstehen.
    Leerzeichen-Werte werden zu `None`, sonst stünde im Portal eine leere
    Überschrift.

    **In der Liste einer Marke (v2)** ist `shop` Pflicht: die Maßnahme gilt
    zunächst nur für diesen Store (`shops: [shop]`), Status, Verlauf, Befund
    und Beleg stehen unter `by_shop.<shop>`. `run_id` ist der Lauf, der sie
    anlegt; er steht als `created_run_id` an der Maßnahme und im ersten
    Verlaufseintrag (Spec 5.1, Regel 7). Ohne `run_id` entsteht sie wie eine
    Maßnahme aus einer Anforderung: nicht gemessen. Der Befund heißt in v2
    `finding_id` (`finding_ref` wird als derselbe Wert angenommen) und
    `finding_run` ist sein Lauf, Vorgabe `run_id`. In v1 stehen `run_id` und
    `created_run_id` nur, wenn ein Lauf übergeben wurde.

    `target_metric` ist die Kennzahl, auf die die Maßnahme zielt, ein Schlüssel
    aus `METRICS` in `lib/baseline.ts` des Cockpits (etwa `conversion_rate`,
    `gsc_clicks`). Der Wochenpuls nennt damit Maßnahmen als zeitlichen Bezug,
    später rechnet das Cockpit daraus die Wirkung. Ohne messbares Ziel bleibt es
    leer (Spec Wächter und Wirkung im Repo `ptai-portal`, Abschnitt 3.1).
    """
    if not title:
        raise ValueError("titel darf nicht leer sein")
    if not discipline:
        raise ValueError("disziplin darf nicht leer sein")
    if not evidence:
        # Die Kernregel des Audits: kein Befund ohne Beleg, das gilt für die
        # daraus entstehende Maßnahme genauso.
        raise ValueError(
            f"Maßnahme {title!r} hat keinen Beleg. Kein Befund ohne Beleg, "
            "keine Maßnahme ohne Beleg."
        )
    if confidence not in CONFIDENCE:
        raise ValueError(f"unbekannte Sicherheit: {confidence!r}, erlaubt sind {CONFIDENCE}")
    if leverage not in LEVERAGE:
        raise ValueError(f"unbekannter Hebel: {leverage!r}, erlaubt sind {LEVERAGE}")
    if effort not in EFFORT:
        raise ValueError(f"unbekannter Aufwand: {effort!r}, erlaubt sind {EFFORT}")
    if approval is not None and approval not in APPROVAL:
        raise ValueError(
            f"unbekannte Empfehlungsstufe: {approval!r}, erlaubt sind {APPROVAL}")
    if responsible is not None and responsible not in RESPONSIBLE:
        raise ValueError(
            f"unbekannt, wer verantwortlich ist: {responsible!r}, "
            f"erlaubt sind {RESPONSIBLE}"
        )
    v2 = is_v2(backlog)
    if v2:
        _require_shop(shop, "create()")
    if finding_id and finding_ref and finding_id != finding_ref:
        raise ValueError(f"finding_id {finding_id!r} und finding_ref {finding_ref!r} "
                         "widersprechen sich, es ist dasselbe Feld")

    # Ein Feld, das nur Leerzeichen trägt, ist kein Inhalt: es wird `None`,
    # damit das Portal den Abschnitt weglässt statt eine leere Zeile zu zeigen.
    def clean(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    today_str = (today or date.today()).isoformat()
    first = {"status": "open", "date": today_str}
    if run_id:
        first["run_id"] = run_id
    if v2:
        finding = finding_id or finding_ref
        entry = {"id": f"M-{backlog['next_id']:03d}"}
        if run_id:
            entry["created_run_id"] = run_id
        entry.update({
            "title": title,
            "discipline": discipline,
            "type": "test" if confidence == "hypothesis" else "measure",
            "confidence": confidence,
            "leverage": leverage,
            "effort": effort,
            "responsible": responsible,
            "data_source": data_source,
            "check_rule": check_rule,
            "target_metric": clean(target_metric),
            "intent": clean(intent),
            "effect": clean(effect),
            "needs": clean(needs),
            "approval": approval,
            "shops": [shop],
            "by_shop": {shop: {
                "status": "open",
                "history": [first],
                "finding_run": (finding_run or run_id) if finding else None,
                "finding_id": finding or None,
                "evidence": evidence,
                "evidence_text": clean(evidence_text),
            }},
        })
        return {**backlog, "next_id": backlog["next_id"] + 1,
                "measures": [*backlog["measures"], entry]}

    entry = {
        "id": f"M-{backlog['next_id']:03d}",
        "title": title,
        "discipline": discipline,
        "evidence": evidence,
        "confidence": confidence,
        "leverage": leverage,
        "effort": effort,
        "responsible": responsible,
        "data_source": data_source,
        "check_rule": check_rule,
        "target_metric": clean(target_metric),
        "finding_ref": finding_ref or finding_id,
        "approval": approval,
        "intent": clean(intent),
        "effect": clean(effect),
        "needs": clean(needs),
        "evidence_text": clean(evidence_text),
        # Eine Hypothese wird nie zur Maßnahme, sie wird zum Test.
        "type": "test" if confidence == "hypothesis" else "measure",
        "status": "open",
        "history": [first],
    }
    if run_id:
        entry["created_run_id"] = run_id
    return {
        **backlog,
        "next_id": backlog["next_id"] + 1,
        "measures": [*backlog["measures"], entry],
    }


def set_status(backlog: dict, id: str, status: str, *,
               today: date | None = None, run_id: str | None = None,
               note: str | None = None, shop: str | None = None) -> dict:
    """Ändert den Status einer Maßnahme und hängt einen Eintrag an ihre
    Historie an, statt sie zu ersetzen: ein früherer Statuswechsel bleibt
    sichtbar, auch nach dem zehnten Folgelauf.

    `run_id` ist der Lauf, der den Wechsel gemessen hat, `note` der Satz,
    woran. Beide sind freiwillig und stehen nur im Eintrag, wenn sie übergeben
    wurden: ein leeres Feld wäre die Behauptung, es gäbe einen Lauf, und das
    Portal zeigt lieber "Urheber nicht belegt" als ein leeres Feld.

    In der Liste einer Marke (v2) gilt der Wechsel nur für `shop` und landet
    unter `by_shop.<shop>`. Ein Store, der nicht in `shops` der Maßnahme
    steht, ist ein Fehler: ob sie dort gilt, prüft ein Lauf, nicht ein
    Statuswechsel (Spec Abschnitt 8).
    """
    if status not in STATUS:
        raise ValueError(f"unbekannter Status: {status!r}, erlaubt sind {STATUS}")

    today_str = (today or date.today()).isoformat()
    entry = {"status": status, "date": today_str}
    if run_id:
        entry["run_id"] = run_id
    if note:
        entry["note"] = note
    v2 = is_v2(backlog)
    if v2:
        _require_shop(shop, "set_status()")
    new_measures = []
    found = False
    for measure in backlog["measures"]:
        if measure["id"] != id:
            new_measures.append(measure)
            continue
        found = True
        if not v2:
            new_measures.append({
                **measure,
                "status": status,
                "history": [*measure["history"], entry],
            })
            continue
        by_shop = measure.get("by_shop") or {}
        if shop not in (measure.get("shops") or []) or shop not in by_shop:
            raise ValueError(
                f"{id} gilt nicht für den Store {shop!r} (shops: "
                f"{measure.get('shops')}). Ein Statuswechsel nimmt keinen Store auf.")
        current = by_shop[shop]
        new_measures.append({
            **measure,
            "by_shop": {**by_shop, shop: {
                **current,
                "status": status,
                "history": [*(current.get("history") or []), entry],
            }},
        })
    if not found:
        raise ValueError(f"unbekannte ID: {id!r}")

    return {**backlog, "measures": new_measures}


def set_approval(backlog: dict, id: str, approval: str) -> dict:
    """Trägt unsere Empfehlung zu dieser Maßnahme nach.

    **Kein Statuswechsel und kein Eintrag in der Historie.** Die Historie hält
    gemessene Zustände; die Empfehlung ist unser Urteil, und das kann sich
    ändern, ohne dass sich am Shop etwas bewegt hat. Beides in eine Zeitleiste zu werfen hieße, dem Kunden eine
    Messung zu zeigen, die keine ist.
    """
    if approval not in APPROVAL:
        raise ValueError(
            f"unbekannte Empfehlungsstufe: {approval!r}, erlaubt sind {APPROVAL}")

    new_measures = []
    found = False
    for measure in backlog["measures"]:
        if measure["id"] == id:
            found = True
            new_measures.append({**measure, "approval": approval})
        else:
            new_measures.append(measure)
    if not found:
        raise ValueError(f"unbekannte ID: {id!r}")

    return {**backlog, "measures": new_measures}


def prioritize(backlog: dict, shop: str | None = None) -> list[dict]:
    """Ordnet die Maßnahmen nach Spec Abschnitt 9.

    `shop` beschränkt die Liste einer Marke (v2) auf die Maßnahmen, deren
    `shops` diesen Store nennen; ohne `shop` rechnet sie über alle. In v1
    ändert `shop` nichts, die Liste gehört ohnehin einem Store.

    Drei Gruppen, in dieser Reihenfolge:

    1. Befunde der Disziplin `data_quality`, unabhängig von den drei Achsen.
    2. Die übrigen Maßnahmen (`type == "measure"`), sortiert nach Sicherheit
       vor Hebel vor Aufwand.
    3. Tests (`type == "test"`), am Ende und unsortiert nach den drei Achsen:
       eine Hypothese wird nie priorisiert.

    Innerhalb einer Gruppe ist die Sortierung stabil, eine gleiche Rangfolge
    behält also die Reihenfolge, in der die Maßnahmen angelegt wurden.
    """
    measures_list = backlog["measures"]
    if shop and is_v2(backlog):
        measures_list = [m for m in measures_list if shop in (m.get("shops") or [])]
    tests = [m for m in measures_list if m["type"] == "test"]
    actual = [m for m in measures_list if m["type"] == "measure"]
    priority = sorted(
        (m for m in actual if m["discipline"] == PRIORITY_DISCIPLINE), key=_rank)
    remainder = sorted(
        (m for m in actual if m["discipline"] != PRIORITY_DISCIPLINE), key=_rank)
    return [*priority, *remainder, *tests]


def _rank(measure: dict) -> tuple[int, int, int]:
    """Sortierschlüssel: Sicherheit vor Hebel vor Aufwand, jeweils aufsteigend
    nach Rang, also von "am verlässlichsten"/"am größten Hebel"/"am
    geringsten Aufwand" zuerst."""
    return (
        _CONFIDENCE_RANK[measure["confidence"]],
        _LEVERAGE_RANK[measure["leverage"]],
        _EFFORT_RANK[measure["effort"]],
    )


def check(measure: dict, snapshots: dict, shop: str | None = None,
          exclusions: dict | None = None) -> str:
    """Wertet die Prüfregel einer Maßnahme gegen die Ergebnisse dieses Laufs aus.

    `snapshots` sind die Prüfergebnisse, die dieser Lauf für einzelne
    Maßnahmen tatsächlich ermitteln konnte: ein Dict von Maßnahmen-ID auf
    das Ergebnis, `True` heißt die Prüfregel ist erfüllt, `False`, sie ist
    es nicht. Eine Maßnahme, deren Prüfregel von einer in diesem Lauf nicht
    fälligen Quelle abhängt, taucht darin schlicht nicht auf: wer den Lauf
    fährt, trägt nur ein, was er anhand frischer Daten wirklich geprüft hat.

    **Der Fall, der zählt, ist "unchecked".** Fehlt die Maßnahme in
    `snapshots`, oder trägt sie gar keine Prüfregel, bleibt ihr Status
    unangetastet: diese Funktion gibt "unchecked" zurück, nie "open" als
    Ersatzwert. Ein Statuswechsel, der nur daher kommt, dass in diesem Lauf
    niemand gemessen hat, wäre eine Falschaussage in einem Backlog, nach dem
    ein Kunde arbeitet. Der Aufrufer erkennt daran: nur bei "implemented"
    oder "open" darf er `set_status()` aufrufen, bei "unchecked" lässt er
    den bisherigen Status stehen.

    Eine Maßnahme aus der Liste einer Marke (mit `by_shop`) braucht `shop`,
    den Store, in dem dieser Lauf gemessen hat. Gilt sie dort nicht, ist sie
    "unchecked": ein Lauf in UK misst keine Maßnahme, die nur für EU gilt.

    **Ein ausgenommener Store wird nicht geprüft (D10).** `exclusions` sind
    die Meldungen der Marke aus dem Cockpit (`portal.exclusions()`):
    Maßnahmen-ID auf die Stores, in denen sie verworfen oder überholt gemeldet
    ist. Steht `shop` dort, oder steht der Store in der Datei auf verworfen
    oder überholt, ist das Ergebnis "unchecked", und der Lauf öffnet die
    Maßnahme dort nicht wieder. In v1 gilt die Meldung für den einen Store.
    """
    if "by_shop" in measure:
        _require_shop(shop, "check()")
        if shop not in (measure.get("shops") or []):
            return "unchecked"
        if ((measure.get("by_shop") or {}).get(shop) or {}).get("status") in EXCLUDING_STATUS:
            return "unchecked"
    if exclusions and is_excluded(exclusions, measure.get("id"), shop):
        return "unchecked"
    if not measure.get("check_rule"):
        return "unchecked"
    if measure["id"] not in snapshots:
        return "unchecked"
    return "implemented" if snapshots[measure["id"]] else "open"


def is_excluded(exclusions: dict | None, measure_id: str | None, shop: str | None) -> bool:
    """Hat die Marke diese Maßnahme für diesen Store verworfen oder überholt gemeldet?

    `exclusions` wie aus `portal.exclusions()`. Ohne `shop` (Liste eines
    Stores, v1) zählt jede Meldung zur Maßnahme.
    """
    shops = (exclusions or {}).get(measure_id) or ()
    return bool(shops) and (shop is None or shop in shops)


def project(backlog: dict, shop: str | None) -> dict:
    """Die Sicht eines Stores auf die Liste, im Zuschnitt von v1.

    Für eine Liste der Marke (v2): nur die Maßnahmen, die für `shop` gelten,
    jede mit den Feldern aus `by_shop.<shop>` an der Maßnahme selbst (Status,
    Verlauf, `finding_run`, `finding_id`, Beleg). Report, QA und Score lesen
    damit unverändert `status` und `history`, sehen aber nur ihren Store. Sonst
    zeigte ein Report für UK die Maßnahmen von EU als offen (Spec Abschnitt 11).
    Eine Liste im Format v1 kommt unverändert zurück.

    Nur zum Lesen: gespeichert wird immer das Dokument, nie die Projektion.
    """
    if not is_v2(backlog):
        return backlog
    if not shop:
        raise ValueError("project() braucht den Store, um die Liste einer Marke "
                         "auf ihn zuzuschneiden")
    out = []
    for measure in backlog.get("measures") or []:
        by_shop = measure.get("by_shop") or {}
        if shop not in (measure.get("shops") or []) or shop not in by_shop:
            continue
        flat = {k: v for k, v in measure.items() if k != "by_shop"}
        flat.update(by_shop[shop])
        flat["shop"] = shop
        out.append(flat)
    return {"next_id": backlog.get("next_id"), "measures": out,
            "projected_from": VERSION, "shop": shop}


def consistency_problems(backlog: dict) -> list[str]:
    """Was an der Liste einer Marke nicht zusammenpasst, als Liste von Sätzen.

    Regel 2 aus Spec 5.1: jeder Store in `shops` hat einen Eintrag unter
    `by_shop`, und umgekehrt. Dazu die Dinge, an denen ein Leser sonst still
    vorbeiliest: doppelte IDs, ein `next_id`, der eine vorhandene ID wieder
    vergeben würde, und ein Store-Eintrag ohne Status oder Verlauf.
    """
    if not is_v2(backlog):
        return []
    problems = []
    seen = set()
    highest = 0
    for measure in backlog.get("measures") or []:
        mid = measure.get("id") or "?"
        if mid in seen:
            problems.append(f"{mid} steht zweimal in der Liste")
        seen.add(mid)
        try:
            highest = max(highest, int(str(mid).split("-", 1)[1]))
        except (IndexError, ValueError):
            problems.append(f"{mid} ist keine Kennung der Form M-001")
        shops = measure.get("shops")
        by_shop = measure.get("by_shop")
        if not isinstance(shops, list) or not shops:
            problems.append(f"{mid}: shops ist keine Liste von Stores")
            shops = []
        if not isinstance(by_shop, dict):
            problems.append(f"{mid}: by_shop fehlt")
            by_shop = {}
        if len(set(shops)) != len(shops):
            problems.append(f"{mid}: ein Store steht zweimal in shops")
        for shop in shops:
            if shop not in by_shop:
                problems.append(f"{mid}: {shop} steht in shops, hat aber keinen "
                                "Eintrag unter by_shop")
        for shop, entry in by_shop.items():
            if shop not in shops:
                problems.append(f"{mid}: by_shop.{shop} gehört zu keinem Store in shops")
            if not isinstance(entry, dict) or entry.get("status") not in STATUS:
                problems.append(f"{mid}: by_shop.{shop} ohne gültigen Status")
            elif not entry.get("history"):
                problems.append(f"{mid}: by_shop.{shop} ohne Verlauf")
    next_id = backlog.get("next_id")
    if not isinstance(next_id, int) or next_id <= highest:
        problems.append(f"next_id ist {next_id!r}, die höchste Kennung ist M-{highest:03d}. "
                        "Die nächste neue Maßnahme bekäme eine vergebene ID.")
    return problems


#: Was dieser Prozess zuletzt gelesen oder geschrieben hat, je Datei: der
#: Hash des Inhalts. `save()` vergleicht damit, ob seitdem ein anderer
#: geschrieben hat. Liegt die Datei nicht hier, hat dieser Prozess sie nie
#: gelesen, und es gibt nichts zu vergleichen.
_SEEN: dict[str, str] = {}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key(path: Path) -> str:
    return str(path.resolve())


def locked(workspace: Path, timeout: float | None = None):
    """Die Sperre der Marke für `load()`, Ändern und `save()` am Stück.

    ```python
    with measures.locked(workspace):
        backlog = measures.load_or_empty(workspace)
        backlog = measures.create(backlog, ..., shop=shop, run_id=run_id)
        measures.save(workspace, backlog)
    ```
    """
    return brand_mod.lock(workspace, timeout=timeout)


def update(workspace: Path, change, timeout: float | None = None) -> dict:
    """Liest, ändert und schreibt die Liste unter der Sperre der Marke.

    `change` bekommt das Dokument und gibt das neue zurück, etwa
    `lambda b: measures.set_status(b, "M-007", "implemented", shop="eu", run_id=...)`.
    """
    with locked(workspace, timeout=timeout):
        backlog = change(load_or_empty(workspace))
        save(workspace, backlog)
        return backlog


def load(workspace: Path) -> dict:
    """Lädt den Bestand. Eine fehlende Datei ist ein Fehler, kein leerer
    Bestand: wer lädt, erwartet einen bereits geschriebenen Stand.

    Mit `brand_workspace` in der Config liest das die Datei der Marke, sonst
    die des Stores (`audit.brand.reporting_dir()`).
    """
    path = _path(workspace)
    data = path.read_bytes()
    backlog = json.loads(data.decode("utf-8"))
    _SEEN[_key(path)] = _digest(data)
    return backlog


def peek(workspace: Path) -> dict:
    """Liest den Bestand nur zum Anzeigen, `empty()`, wenn es keinen gibt.

    Anders als `load()` merkt sich das nichts für `save()`: wer nur liest
    (Report, QA, `render()`), soll den Stand nicht als Grundlage einer
    Änderung ausgeben, die er nie gemacht hat.
    """
    p = _path(workspace)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty()
    except json.JSONDecodeError as error:
        raise ValueError(f"{p} ist beschädigt ({error}).") from error


def load_or_empty(workspace: Path) -> dict:
    """Der Einstieg für einen Lauf: `empty()`, wenn noch nie geschrieben wurde.

    Eine beschädigte Datei heißt Abbruch mit Ansage, nie ein stiller
    Neuanfang: der würde die gesamte Statushistorie jeder bereits
    angelegten Maßnahme wegwerfen. Die Datei einer Marke fehlt nie still:
    zeigt `brand_workspace` auf einen Ordner ohne sie, bricht schon die
    Pfadauflösung ab.
    """
    try:
        return load(workspace)
    except FileNotFoundError:
        return empty()
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{_path(workspace)} ist beschädigt ({error}). Wird nicht still neu "
            "angelegt, weil das die Statushistorie jeder Maßnahme wegwerfen würde. "
            "Datei prüfen und entweder reparieren oder löschen."
        ) from error


def save(workspace: Path, backlog: dict) -> Path:
    """Schreibt den Bestand atomar: erst daneben, dann umbenennen.

    Ein mitten im Schreiben abgebrochener Lauf darf keine halb geschriebene
    Datei hinterlassen, sonst existiert eine Maßnahme, deren `history` und
    `status` nicht zusammenpassen. `os.replace` ist innerhalb eines
    Dateisystems atomar: danach existiert der alte oder der neue Stand, nie
    ein halber.

    Unter der Sperre der Marke und mit drei Prüfungen, die je einen stillen
    Verlust verhindern:

    - Im Ordner der Marke steht nur v2, im Store nur v1. Sonst läse das
      Cockpit eine Liste im falschen Zuschnitt.
    - `next_id` sinkt nie unter den Wert auf der Platte (Spec 5.1, Regel 6).
    - Hat ein anderer die Datei seit dem letzten `load()` dieses Prozesses
      geschrieben, bricht das ab, statt dessen Maßnahmen zu überschreiben.
    """
    if not isinstance(backlog, dict) or "measures" not in backlog:
        # prioritize() nimmt das Dokument und gibt eine Liste zurück. Wer den
        # Rückgabewert zuweist und ihn hierher reicht, schreibt die Liste in
        # measures.json; load() liefert danach eine Liste, und der nächste Lauf
        # fällt an ganz anderer Stelle um. Am 06.09.2026 im ersten echten Lauf
        # genau so passiert.
        typ = type(backlog).__name__
        raise ValueError(
            f"save() erwartet das Backlog-Dokument, bekommen hat es {typ}. "
            "Häufigste Ursache: der Rückgabewert von prioritize() wurde "
            "zugewiesen. prioritize() liefert die sortierte Liste für die "
            "Ausgabe, nicht das Dokument; gespeichert wird immer das Dokument."
        )
    if "projected_from" in backlog:
        raise ValueError("save() hat die Sicht eines Stores bekommen (project()). "
                         "Gespeichert wird immer das ganze Dokument der Marke.")
    in_brand = brand_mod.has_brand_files(workspace)
    if in_brand and not is_v2(backlog):
        raise ValueError(
            "Im Ordner der Marke steht nur eine Liste im Format v2. Dieses "
            "Dokument hat kein version: 2; vermutlich stammt es aus der Datei "
            "eines Stores.")
    if not in_brand and is_v2(backlog):
        raise ValueError(
            "Eine Liste im Format v2 gehört in den Ordner der Marke. In der "
            "Config des Stores fehlt brand_workspace.")
    problems = consistency_problems(backlog)
    if problems:
        raise ValueError("Die Liste der Marke passt nicht zusammen, nichts "
                         "geschrieben:\n- " + "\n- ".join(problems))

    path = _path(workspace)
    with locked(workspace):
        if path.exists():
            on_disk = path.read_bytes()
            seen = _SEEN.get(_key(path))
            if seen is not None and seen != _digest(on_disk):
                raise ValueError(
                    f"{path} hat sich seit dem Lesen geändert, ein anderer Lauf "
                    "hat geschrieben. Nichts überschrieben. Neu laden "
                    "(load_or_empty), die Änderung wiederholen und unter "
                    "measures.locked() speichern.")
            try:
                disk_next = json.loads(on_disk.decode("utf-8")).get("next_id")
            except (ValueError, AttributeError):
                disk_next = None
            if isinstance(disk_next, int) and backlog.get("next_id", 0) < disk_next:
                raise ValueError(
                    f"next_id würde von {disk_next} auf {backlog.get('next_id')} "
                    "sinken. Eine ID wird nie wiederverwendet, nichts geschrieben.")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(backlog, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        _SEEN[_key(path)] = _digest(data)
    return path


#: Anzeigewörter für `measures.md`. Die Werte im JSON sind englisch, weil sie
#: technisch sind; das Dokument liest der Kunde, und dort steht Deutsch. Ohne
#: diese Zuordnung stünde in einer deutschen Tabelle "Hebel: low".
LABELS = {
    "leverage": {"high": "hoch", "medium": "mittel", "low": "niedrig"},
    "effort": {"small": "klein", "medium": "mittel", "large": "groß"},
    "status": {
        "open": "offen", "in_progress": "in Arbeit", "implemented": "umgesetzt",
        "rejected": "verworfen", "obsolete": "hinfällig",
    },
    "discipline": {
        "data_quality": "Datenqualität", "commerce": "Handel", "traffic": "Traffic",
        "seo": "SEO", "seo_technical": "SEO technisch", "geo": "GEO", "sea": "SEA",
        "cro": "Conversion", "content": "Content", "tech": "Technik",
        "trust": "Trust und Compliance",
        "consistency": "Abweichung zwischen Stores",
    },
}


def _label(feld: str, value) -> str:
    """Das deutsche Anzeigewort, oder der Wert selbst, falls keins hinterlegt
    ist. Ein unbekannter Wert verschwindet so nicht, er steht nur unübersetzt
    da: eine fehlende Zeile wäre schlimmer als eine englische."""
    if value is None:
        return "-"
    return LABELS.get(feld, {}).get(value, str(value))


#: Anzeige für den Betreiber, solange `PTAI_OPERATOR_NAME` nirgends steht.
DEFAULT_OPERATOR_NAME = "Dienstleister"


def responsible_label(value: str | None, brand: str | None = None,
                      workspace: str | os.PathLike = ".") -> str:
    """Wer eine Maßnahme umsetzt, so wie es im Kundendokument steht.

    Die eine Anzeige für `measures.md` und den großen Audit. Bis zum 11.09.2026
    hießen dieselben Werte in `measures.md` "Path to AI" und "Dritter", im Audit
    "Path to AI" und "Dritter Dienstleister".

    - `"Path to AI"` zeigt `PTAI_OPERATOR_NAME`, gesucht über `audit.env` im
      Workspace, sonst "Dienstleister". Beim Kunden eines fremden Betreibers
      stünde sonst Path to AI als Verantwortlicher (Spec 2026-09-11, E3, D7).
    - `"Customer"` zeigt die Marke, wenn eine übergeben wird, sonst "Kunde".
    - `"Third Party"` zeigt "Dritter Dienstleister".

    Ein leerer Wert gibt einen leeren Text, der Aufrufer entscheidet, ob die
    Zeile entfällt. Ein unbekannter Wert bleibt unübersetzt stehen, wie bei
    `_label()`: eine fehlende Angabe wäre schlimmer als eine englische.
    """
    if not value:
        return ""
    if value == "Path to AI":
        return env.get("PTAI_OPERATOR_NAME", workspace) or DEFAULT_OPERATOR_NAME
    if value == "Customer":
        return brand or "Kunde"
    if value == "Third Party":
        return "Dritter Dienstleister"
    return str(value)


def render(workspace: Path) -> Path:
    """Erzeugt `measures.md`, die lesbare Fassung von `measures.json`.

    Wird aus der JSON generiert, nie von Hand gepflegt, dieselbe
    Formdisziplin wie `baseline.render()`. Zwei Abschnitte: zuerst die
    priorisierte Tabelle der echten Maßnahmen, danach ein eigener Abschnitt
    für die Tests. Eine Hypothese wird nie priorisiert (siehe
    `prioritize()`); stünde sie in derselben Tabelle wie die Maßnahmen, sähe
    sie danach aus. Jede Zeile zeigt Status und das Datum des letzten
    Statuswechsels, damit sichtbar ist, wo eine Maßnahme gerade steht und
    seit wann.

    Für die Liste einer Marke steht der Status je Store in der Zeile
    ("eu: offen, uk: umgesetzt"), der letzte Wechsel ist der jüngste über alle
    Stores. Die Datei liegt neben `measures.json`, also im Ordner der Marke.
    """
    backlog = peek(workspace)
    prioritized = prioritize(backlog)
    actual = [m for m in prioritized if m["type"] == "measure"]
    tests = [m for m in prioritized if m["type"] == "test"]

    lines = ["# Maßnahmen", "", "## Priorisierte Maßnahmen", ""]
    lines.extend(_render_table(actual, "Keine Maßnahmen.", workspace))
    lines.append("## Tests")
    lines.append("")
    lines.extend(_render_table(tests, "Keine Tests.", workspace))
    markdown = "\n".join(lines).rstrip("\n") + "\n"
    return _write_atomic(_path(workspace).with_name("measures.md"), markdown)


def _render_table(entries: list[dict], empty_text: str,
                  workspace: str | os.PathLike = ".") -> list[str]:
    """Rendert eine Liste von Maßnahmen als Tabelle, oder `empty_text`, wenn
    die Liste leer ist. Eine leere Tabelle (nur Kopfzeile, keine Zeile) sähe
    wie ein Rendering-Fehler aus, ein Satz ist eindeutig."""
    if not entries:
        return [empty_text, ""]
    lines = [
        "| ID | Titel | Disziplin | Hebel | Aufwand | Verantwortlich | Status | Letzter Wechsel |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in entries:
        last_change = _last_change(entry)
        lines.append(
            f"| {entry['id']} | {entry['title']} | "
            f"{_label('discipline', entry['discipline'])} | "
            f"{_label('leverage', entry['leverage'])} | "
            f"{_label('effort', entry['effort'])} | "
            f"{responsible_label(entry['responsible'], workspace=workspace) or '-'} | "
            f"{_status_text(entry)} | {last_change} |"
        )
    lines.append("")
    return lines


def _status_text(entry: dict) -> str:
    """Der Status für `measures.md`: einer in v1, einer je Store in v2."""
    if "by_shop" not in entry:
        return _label("status", entry["status"])
    return ", ".join(f"{shop}: {_label('status', entry['by_shop'][shop]['status'])}"
                     for shop in entry.get("shops") or [] if shop in entry["by_shop"])


def _last_change(entry: dict) -> str:
    """Das Datum des letzten Statuswechsels, in v2 über alle Stores."""
    if "by_shop" not in entry:
        return entry["history"][-1]["date"]
    dates = [h.get("date") or "" for item in entry["by_shop"].values()
             for h in item.get("history") or []]
    return max(dates, default="-") or "-"


def _write_atomic(path: Path, content: str) -> Path:
    """Schreibt `content` atomar nach `path`: erst daneben, dann umbenennen.
    Dieselbe Mechanik wie in `baseline.py`, hier nur für `measures.md`
    gebraucht; `measures.json` schreibt weiterhin `save()` selbst.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return path


def _path(workspace: Path) -> Path:
    """Der eine Ort, an dem der Pfad zur measures.json gebildet wird.

    Mit `brand_workspace` in der Config die Datei der Marke, sonst die des
    Stores; die Regeln dafür stehen in `audit.brand`.
    """
    return brand_mod.file_path(workspace, "measures.json")


def file_path(workspace: Path) -> Path:
    """Wo `measures.json` dieses Workspace liegt, für Werkzeuge, die kopieren."""
    return _path(workspace)
