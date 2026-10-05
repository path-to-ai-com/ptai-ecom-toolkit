#!/usr/bin/env python3
"""Was von aussen hereinkam, und worauf es zeigt.

Der Audit misst und leitet daraus Massnahmen ab. Daneben laeuft ein zweiter
Strom: der Kunde meldet selbst etwas, in einer Liste, in einem Termin, in einer
Mail. Im September 2026 waren das 29 Punkte aus einer intern gefuehrten
Aufgabenliste, abgeglichen gegen 70 Massnahmen. Jedes Mal stellt sich dieselbe
Frage: existiert das schon als Massnahme? Ohne sichtbare Antwort entstehen
Dubletten, und niemand sieht, dass zwei Eintraege dasselbe meinen.

Diese Datei haelt diesen zweiten Strom, gebaut wie `context.py`: eine JSON-Datei
im Kunden-Workspace, fortlaufende Kennungen, angehaengt statt ersetzt.

Drei Regeln tragen das Modul:

1. **Die Verknuepfung steht nur hier.** Ein Punkt kann auf mehrere Massnahmen
   fallen, eine Massnahme kann mehrere Punkte einsammeln. Stuende dieselbe
   Beziehung zusaetzlich in `measures.json`, gaebe es zwei Wahrheiten, und die
   erste, die nur einseitig gepflegt wird, faellt niemandem auf. `measures.py`
   weiss deshalb nichts von diesem Modul, nur umgekehrt.
2. **Keine Verknuepfung ohne Grund.** Dieselbe Regel wie "keine Massnahme ohne
   Beleg" in `measures.py`: eine Gleichsetzung ohne Grund ist eine Behauptung,
   und beim naechsten Abgleich kann niemand mehr pruefen, ob sie stimmt.
3. **Vermutet ist nicht sicher.** `certainty` unterscheidet die Zuordnung, die
   feststeht, von der, die der Kunde erst entscheiden muss. Eine vermutete
   traegt zusaetzlich die offene Frage im Wortlaut, sonst weiss niemand, was
   eigentlich zu entscheiden ist.

**Der Zustand eines Punktes wird abgeleitet, nie gespeichert** (`state()`): ein
Statusfeld muesste jemand nachziehen, und genau das passiert nicht.

**Was aus der Quelle kommt, steht getrennt von dem, was wir daraus machen.**
`original` hält die Angaben im Wortlaut der Quelle (`ORIGINAL_FIELDS`), alles
andere am Punkt ist unsere Einordnung: der Titel in unseren Worten, die Notiz,
die Verknüpfungen. Bis zum 24.09.2026 kam von einer Zeile der Aufgabenliste nur
der übersetzte Titel mit, und im Portal stand fast nichts von dem, was der Kunde
geschrieben hatte.

**Welche Maßnahmen aus einem Punkt entstanden sind, steht am Punkt**
(`created_measures`), nicht am Link. Eine Anforderung, die in einer bestehenden
Maßnahme aufgeht, und eine, für die wir eine neue angelegt haben, sahen bis zum
24.09.2026 gleich aus. Der Unterschied trägt eine zweite Aussage: eine neu
angelegte Maßnahme ist aus einer Kundenaussage entstanden und nicht aus einer
Messung, und das Portal zeigt ihren Status erst dann als gemessen, wenn ein Lauf
ihn mit seiner Lauf-ID geschrieben hat (`measures.set_status(..., run_id=...)`).
Die Herkunft ist eine Tatsache, die bleibt: sie übersteht `unlink()` und
`mark_out_of_scope()`. Am selben Tag hing sie noch am Link, und als eine
Anforderung aus dem Projekt genommen und ihre Verknüpfung gelöst wurde, stand die
daraus angelegte Maßnahme wieder als gemessene Maßnahme aus dem Audit da.

**Eine Frage von uns ist kein Vorschlag.** `clarification` hält unsere offene
Frage an den Kunden, was eine Anforderung überhaupt meint, im Wortlaut, wie er
sie liest. Sie hängt an keiner Maßnahme und ergibt den Zustand "to_clarify".
Anlass am 29.09.2026: von einer Zeile der Aufgabenliste kam nur der Titel mit,
sie hing als Vermutung an einer Maßnahme, die kaum passte, und die Frage dazu
konnte der Kunde nicht beantworten, weil sie eine Zuordnung voraussetzte, die er
selbst nicht kannte. Was außerhalb des Projekts liegt, braucht keine Frage;
beides zugleich ist ein Fehler.

**Was hier nicht passiert: ein Statuswechsel.** Eine Verknuepfung sagt "das ist
dieselbe Sache", nie "das ist damit erledigt". Ob eine Massnahme umgesetzt ist,
entscheidet allein die Pruefregel im Folgelauf.
"""
import json
import os
from datetime import date
from pathlib import Path

from audit import measures

#: Dateiname im Kunden-Workspace, relativ zu dessen Wurzel.
FILE = "reporting/feedback.json"

#: Kennungs-Praefix, damit ein Punkt im Portal und im Gespraech eindeutig
#: referenzierbar ist wie ein Befund oder eine Massnahme.
PREFIX = "FB"

#: Wie sicher eine Zuordnung ist. Bewusst zwei Werte: entweder steht sie fest,
#: oder sie ist die Vorlage fuer eine Entscheidung des Kunden. Ein Mittelwert
#: waere im Portal nicht darstellbar, ohne dass er wie Sicherheit aussieht.
CERTAINTY = {
    "confirmed": "dieselbe Sache, die Zuordnung steht fest",
    "proposed": "koennte dieselbe Sache sein, der Kunde entscheidet",
}

#: Zustand eines Punktes, abgeleitet aus dem, was in der Datei steht.
#: "created" heißt: jede Verknüpfung zeigt auf eine Maßnahme, die aus diesem
#: Punkt angelegt wurde (`created_measures`). Ist auch nur eine bestehende
#: darunter, bleibt es "assigned"; welche neu ist, zeigt das Portal je Maßnahme.
#: "to_clarify" heißt: wir haben eine Frage an den Kunden, was der Punkt meint
#: (`clarification`), seit dem 29.09.2026.
STATES = ("open", "assigned", "created", "to_decide", "to_clarify", "out_of_scope")

#: Die Angaben, die aus der Quelle mitkommen, in der Reihenfolge, in der das
#: Portal sie zeigt. Die Werte bleiben im Wortlaut der Quelle, auch wenn er
#: englisch oder knapp ist: übersetzt und eingeordnet wird im Titel und in der
#: Notiz, nie hier. Ein neues Feld braucht zugleich seine Beschriftung im
#: Portal, deshalb wird ein unbekannter Schlüssel abgelehnt statt still
#: durchgereicht.
ORIGINAL_FIELDS = ("title", "section", "shop", "priority", "goal", "notes")


def feedback_path(workspace: str = ".") -> Path:
    """Der volle Pfad zur Feedback-Datei eines Workspace."""
    return Path(workspace) / FILE


def load(workspace: str = ".") -> list[dict]:
    """Liest die Punkte. Fehlt die Datei, ist das kein Fehler: ein Shop ohne
    Rueckmeldung von aussen ist der Normalfall beim ersten Lauf."""
    p = feedback_path(workspace)
    if not p.exists():
        return []
    try:
        daten = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{FILE} ist kein gueltiges JSON: {exc}") from exc
    entries = daten.get("entries") if isinstance(daten, dict) else daten
    return list(entries or [])


def validate(entries: list[dict]) -> list[str]:
    """Prueft die Punkte auf das, was das Portal zwingend braucht."""
    errors = []
    gesehen = set()
    for i, e in enumerate(entries, 1):
        wo = e.get("id") or f"Eintrag {i}"
        if not e.get("id"):
            errors.append(f"{wo}: keine id")
        elif e["id"] in gesehen:
            errors.append(f"{wo}: id doppelt vergeben")
        else:
            gesehen.add(e["id"])
        if not (e.get("title") or "").strip():
            errors.append(f"{wo}: kein title, niemand weiss worum es geht")
        if not (e.get("source") or "").strip():
            errors.append(f"{wo}: keine source, spaeter ist nicht mehr "
                          "nachvollziehbar, wer das gesagt hat")
        errors.extend(_link_errors(wo, e))
        errors.extend(_scope_errors(wo, e))
        errors.extend(_clarification_errors(wo, e))
        errors.extend(_original_errors(wo, e))
        errors.extend(_created_errors(wo, e))
    return errors


def _link_errors(wo: str, e: dict) -> list[str]:
    """Die Pruefungen an den Verknuepfungen eines Punktes."""
    errors = []
    verknuepft = set()
    for link in e.get("links") or []:
        ziel = link.get("measure") or "?"
        if ziel in verknuepft:
            errors.append(f"{wo}: {ziel} steht zweimal, eine Massnahme wird "
                          "je Punkt einmal verknuepft")
        verknuepft.add(ziel)
        art = link.get("certainty")
        if art not in CERTAINTY:
            errors.append(f"{wo}, {ziel}: certainty ist {art!r}, erlaubt sind "
                          f"{', '.join(sorted(CERTAINTY))}")
        if not (link.get("why") or "").strip():
            errors.append(f"{wo}, {ziel}: kein why. Eine Gleichsetzung ohne "
                          "Grund ist eine Behauptung.")
        if art == "proposed" and not (link.get("question") or "").strip():
            errors.append(f"{wo}, {ziel}: kein question. Eine Vermutung ohne "
                          "Frage ist nicht entscheidbar.")
    return errors


def _created_errors(wo: str, e: dict) -> list[str]:
    """Die Prüfungen an den Maßnahmen, die aus dem Punkt angelegt wurden."""
    if "created_measures" not in e:
        return []
    created = e["created_measures"]
    if not isinstance(created, list) or not all(isinstance(c, str) and c for c in created):
        return [f"{wo}: created_measures ist keine Liste von Maßnahmen-Kennungen"]
    errors = []
    for measure_id in sorted({c for c in created if created.count(c) > 1}):
        errors.append(f"{wo}: {measure_id} steht zweimal in created_measures")
    for link in e.get("links") or []:
        if link.get("measure") in created and link.get("certainty") != "confirmed":
            errors.append(f"{wo}, {link.get('measure')}: in created_measures, aber "
                          "nur vermutet verknüpft. Wer eine Maßnahme aus dem Punkt "
                          "anlegt, hat die Zuordnung entschieden.")
    return errors


def _original_errors(wo: str, e: dict) -> list[str]:
    """Die Prüfungen an den Angaben aus der Quelle."""
    if "original" not in e:
        return []
    original = e["original"]
    if not isinstance(original, dict):
        return [f"{wo}: original ist kein Objekt"]
    errors = []
    for key, value in original.items():
        if key not in ORIGINAL_FIELDS:
            errors.append(f"{wo}: original.{key} ist unbekannt, erlaubt sind "
                          f"{', '.join(ORIGINAL_FIELDS)}")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{wo}: original.{key} ist leer. Eine leere Angabe "
                          "zeigt das Portal als Beschriftung ohne Wert.")
    return errors


def _scope_errors(wo: str, e: dict) -> list[str]:
    """Aussschluss und Verknuepfung schliessen sich aus."""
    if "out_of_scope" not in e:
        return []
    if not (e.get("out_of_scope") or "").strip():
        errors = [f"{wo}: out_of_scope ohne Grund. Ohne ihn prueft der naechste "
                  "Abgleich dieselbe Zeile erneut."]
    else:
        errors = []
    if e.get("links"):
        errors.append(f"{wo}: out_of_scope und links zugleich. Was ausserhalb "
                      "liegt, hat keine Massnahme.")
    return errors


def _clarification_errors(wo: str, e: dict) -> list[str]:
    """Die Prüfungen an unserer Frage an den Kunden."""
    if "clarification" not in e:
        return []
    value = e["clarification"]
    errors = []
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{wo}: clarification ist leer. Eine Klärung ohne Frage "
                      "zeigt das Portal als offene Frage ohne Inhalt.")
    if "out_of_scope" in e:
        errors.append(f"{wo}: clarification und out_of_scope zugleich. Was "
                      "außerhalb liegt, braucht keine Frage.")
    return errors


def state(entry: dict) -> str:
    """Der Zustand eines Punktes, abgeleitet aus der Datei.

    Kein gespeichertes Statusfeld: es muesste bei jeder Verknuepfung
    nachgezogen werden, und die erste vergessene Nachfuehrung waere im Portal
    eine Falschaussage.
    """
    if (entry.get("out_of_scope") or "").strip():
        return "out_of_scope"
    if (entry.get("clarification") or "").strip():
        return "to_clarify"
    links = entry.get("links") or []
    if not links:
        return "open"
    if any(link.get("certainty") == "proposed" for link in links):
        return "to_decide"
    created = entry.get("created_measures") or []
    if all(link.get("measure") in created for link in links):
        return "created"
    return "assigned"


def next_id(entries: list[dict]) -> str:
    """Die naechste freie Kennung, fortlaufend und dreistellig."""
    zahlen = []
    for e in entries:
        identifier = str(e.get("id") or "")
        if identifier.startswith(PREFIX + "-"):
            remainder = identifier.split("-", 1)[1]
            if remainder.isdigit():
                zahlen.append(int(remainder))
    return f"{PREFIX}-{max(zahlen, default=0) + 1:03d}"


def add(workspace: str, *, title: str, source: str, ref: str | None = None,
        note: str | None = None, original: dict | None = None,
        today: date | None = None) -> dict:
    """Legt einen Punkt an und schreibt die Datei.

    `source` ist Fliesstext und sagt, woher der Punkt kam ("Aufgabenliste vom
    17.09.2026, Mara Beispiel", "Termin 17.09.2026, Tom Beispiel"). `ref` ist
    der Schluessel im Quellsystem, falls es einen gibt, etwa die Kennung der
    Aufgabe dort. Er bleibt freiwillig: ein Punkt aus einem Termin hat keinen.

    `original` trägt die Angaben der Quelle im Wortlaut, mit den Schlüsseln aus
    `ORIGINAL_FIELDS`: aus einem Export etwa Titel, Bereich, Priorität,
    Notizen und Ziel der Zeile. `title` ist dagegen unser Titel, übersetzt oder
    geschärft. Leere Angaben fallen weg, ein unbekannter Schlüssel wird
    abgelehnt, siehe `_clean_original()`.

    Verknuepft wird nicht hier, sondern mit `link()`. Der Grund ist der
    haeufigste Fall: der Abgleich gegen den Bestand passiert im selben
    Arbeitsgang, aber die Entscheidung, auf welche Massnahme ein Punkt faellt,
    ist ein eigener Schritt mit eigener Begruendung.
    """
    if not (title or "").strip():
        raise ValueError("title darf nicht leer sein, sonst weiss niemand, "
                         "worum es geht")
    if not (source or "").strip():
        raise ValueError("source darf nicht leer sein, sonst ist spaeter nicht "
                         "nachvollziehbar, wer das gesagt hat")
    fields = _clean_original(original)
    entries = load(workspace)
    entry = {
        "id": next_id(entries),
        "received": (today or date.today()).isoformat(),
        "source": source.strip(),
        "title": title.strip(),
        "links": [],
    }
    if ref:
        entry["ref"] = str(ref).strip()
    if note:
        entry["note"] = note.strip()
    if fields:
        entry["original"] = fields
    entries.append(entry)
    _save(workspace, entries)
    return entry


def set_original(workspace: str, feedback_id: str, original: dict) -> dict:
    """Setzt die Angaben aus der Quelle an einem bestehenden Punkt.

    Der Weg für Punkte, die angelegt wurden, bevor `add()` die Quelle
    mitnahm, und für eine Quelle, die nachträglich ergänzt wurde. Ersetzt,
    was vorher dastand: die Angaben sind der Wortlaut der Quelle, und der
    gilt in seiner neuesten Fassung. Bleibt nach dem Bereinigen nichts
    übrig, verschwindet das Feld ganz, statt leer stehen zu bleiben.
    """
    fields = _clean_original(original)
    entries = load(workspace)
    entry = _find(entries, feedback_id)
    if fields:
        entry["original"] = fields
    else:
        entry.pop("original", None)
    _save(workspace, entries)
    return entry


def _clean_original(original: dict | None) -> dict:
    """Die Angaben aus der Quelle, geprüft und ohne leere Werte.

    Ein unbekannter Schlüssel ist ein Fehler und kein Hinweis: das Portal
    beschriftet nur, was in `ORIGINAL_FIELDS` steht, und ein fremdes Feld
    stünde dort unter seinem englischen Namen.
    """
    if not original:
        return {}
    unknown = [key for key in original if key not in ORIGINAL_FIELDS]
    if unknown:
        raise ValueError(f"unbekannte Angabe aus der Quelle: {', '.join(unknown)}. "
                         f"Erlaubt sind {', '.join(ORIGINAL_FIELDS)}.")
    fields = {}
    for key in ORIGINAL_FIELDS:
        value = original.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"original.{key} muss Text sein, ist {type(value).__name__}")
        if value.strip():
            fields[key] = value.strip()
    return fields


def link(workspace: str, feedback_id: str, measure_id: str, certainty: str, *,
         why: str, question: str | None = None,
         created: bool | None = None) -> dict:
    """Verknuepft einen Punkt mit einer Massnahme und gibt ihn zurueck.

    Die Massnahme muss es geben. Ein Verweis auf eine Kennung, die nicht im
    Bestand steht, ist im Portal ein toter Link, und er faellt erst dem Kunden
    auf. Geprueft wird gegen `measures.json` desselben Workspace.

    Eine bereits vorhandene Verknuepfung auf dieselbe Massnahme wird ersetzt,
    nicht verdoppelt: genau so wird aus einer entschiedenen Vermutung eine
    bestaetigte Zuordnung.

    `created=True` heißt: die Maßnahme ist aus diesem Punkt angelegt worden,
    sie gab es vorher nicht. Das geht nur zusammen mit `confirmed` und landet
    in `created_measures` am Punkt, siehe `record_created()`. Ohne Angabe
    bleibt dort stehen, was stand: dass eine Maßnahme aus dem Punkt entstand,
    ist eine Tatsache über ihre Herkunft, und wer nur den Grund nachschärft,
    soll sie nicht nebenbei verlieren. `created=False` nimmt sie ausdrücklich
    zurück, etwa nach einem Irrtum beim Abgleich.
    """
    if certainty not in CERTAINTY:
        raise ValueError(f"certainty {certainty!r} unbekannt, erlaubt: "
                         f"{', '.join(sorted(CERTAINTY))}")
    if not (why or "").strip():
        raise ValueError("why darf nicht leer sein. Eine Gleichsetzung ohne "
                         "Grund ist eine Behauptung, und beim naechsten "
                         "Abgleich kann niemand mehr pruefen, ob sie stimmt.")
    if certainty == "proposed" and not (question or "").strip():
        raise ValueError("eine vermutete Zuordnung braucht question, sonst "
                         "weiss niemand, was zu entscheiden ist")
    if created and certainty != "confirmed":
        raise ValueError("created geht nur mit confirmed: wer eine Maßnahme aus "
                         "dem Punkt anlegt, hat die Zuordnung entschieden")

    _check_measure(workspace, measure_id)

    entries = load(workspace)
    entry = _find(entries, feedback_id)
    if (entry.get("out_of_scope") or "").strip():
        raise ValueError(f"{feedback_id} liegt ausserhalb des Projekts und "
                         "wird nicht verknuepft. Erst den Ausschluss "
                         "zuruecknehmen.")

    if (certainty == "proposed" and created is not False
            and measure_id in (entry.get("created_measures") or [])):
        raise ValueError(f"{measure_id} ist aus {feedback_id} angelegt und damit "
                         "keine Vermutung. Die Herkunft mit created=False "
                         "zurücknehmen, wenn sie ein Irrtum war.")

    neu = {"measure": measure_id, "certainty": certainty, "why": why.strip()}
    if certainty == "proposed":
        neu["question"] = question.strip()
    links = [l for l in (entry.get("links") or []) if l.get("measure") != measure_id]
    entry["links"] = [*links, neu]
    if created is True:
        _add_created(entry, measure_id)
    elif created is False:
        _remove_created(entry, measure_id)
    _save(workspace, entries)
    return entry


def record_created(workspace: str, feedback_id: str, measure_id: str) -> dict:
    """Hält fest, dass eine Maßnahme aus diesem Punkt angelegt wurde.

    Der gewöhnliche Weg ist `link(..., created=True)` im Abgleich. Diese
    Funktion ist für den Punkt ohne Verknüpfung auf die Maßnahme, etwa einen,
    der nach dem Anlegen aus dem Projekt genommen wurde: die Maßnahme bleibt
    trotzdem aus ihm entstanden, und nur mit diesem Eintrag weiß das Portal,
    dass ihr Status nie gemessen wurde. Ein zweiter Aufruf ändert nichts.
    """
    _check_measure(workspace, measure_id)
    entries = load(workspace)
    entry = _find(entries, feedback_id)
    _add_created(entry, measure_id)
    _save(workspace, entries)
    return entry


def _add_created(entry: dict, measure_id: str) -> None:
    created = list(entry.get("created_measures") or [])
    if measure_id not in created:
        entry["created_measures"] = [*created, measure_id]


def _remove_created(entry: dict, measure_id: str) -> None:
    created = [c for c in (entry.get("created_measures") or []) if c != measure_id]
    if created:
        entry["created_measures"] = created
    else:
        entry.pop("created_measures", None)


def _check_measure(workspace: str, measure_id: str) -> None:
    """Die Maßnahme muss im Bestand stehen, sonst ist der Verweis im Portal tot."""
    bestand = measures.load_or_empty(Path(workspace))
    if measure_id not in {m["id"] for m in bestand.get("measures", [])}:
        raise ValueError(f"{measure_id} steht nicht im Maßnahmen-Bestand. "
                         "Ein Verweis auf eine unbekannte Kennung ist im "
                         "Portal ein toter Verweis.")


def unlink(workspace: str, feedback_id: str, measure_id: str) -> dict:
    """Loest eine Verknuepfung wieder, etwa weil der Kunde widersprochen hat."""
    entries = load(workspace)
    entry = _find(entries, feedback_id)
    entry["links"] = [l for l in (entry.get("links") or [])
                      if l.get("measure") != measure_id]
    _save(workspace, entries)
    return entry


def mark_out_of_scope(workspace: str, feedback_id: str, reason: str) -> dict:
    """Stellt einen Punkt als ausserhalb des Projekts liegend fest.

    Er verschwindet damit nicht, er taucht nur in keiner Massnahme auf. Der
    Grund ist Pflicht: ohne ihn prueft der naechste Abgleich dieselbe Zeile
    erneut, und genau das soll die Liste ersparen.

    Eine offene Frage an den Kunden fällt dabei weg: was außerhalb liegt,
    braucht keine Klärung mehr.
    """
    if not (reason or "").strip():
        raise ValueError("ein Ausschluss braucht seinen Grund, sonst prueft "
                         "der naechste Abgleich dieselbe Zeile erneut")
    entries = load(workspace)
    entry = _find(entries, feedback_id)
    if entry.get("links"):
        raise ValueError(f"{feedback_id} ist mit einer Massnahme verknuepft "
                         "und liegt damit nicht ausserhalb. Erst die "
                         "Verknuepfung loesen.")
    entry["out_of_scope"] = reason.strip()
    entry.pop("clarification", None)
    _save(workspace, entries)
    return entry


def set_clarification(workspace: str, feedback_id: str, question: str) -> dict:
    """Hält unsere offene Frage an den Kunden fest, was der Punkt meint.

    Die Frage steht im Wortlaut, wie der Kunde sie liest, und macht den Punkt
    zu "to_clarify". Sie ist kein Vorschlag für eine Maßnahme; wer eine
    Zuordnung vermutet, nimmt `link(..., "proposed", question=...)`. Eine
    vorhandene Frage wird ersetzt. Entschieden am 29.09.2026.
    """
    if not (question or "").strip():
        raise ValueError("eine Klärung braucht ihre Frage, sonst weiß der "
                         "Kunde nicht, was er beantworten soll")
    entries = load(workspace)
    entry = _find(entries, feedback_id)
    if (entry.get("out_of_scope") or "").strip():
        raise ValueError(f"{feedback_id} liegt außerhalb des Projekts und "
                         "braucht keine Frage. Erst den Ausschluss "
                         "zurücknehmen.")
    entry["clarification"] = question.strip()
    errors = _clarification_errors(feedback_id, entry)
    if errors:
        raise ValueError("; ".join(errors))
    _save(workspace, entries)
    return entry


def clear_clarification(workspace: str, feedback_id: str) -> dict:
    """Nimmt die Frage zurück, etwa weil der Kunde sie im Termin beantwortet
    hat. Danach gilt wieder der Zustand aus den Verknüpfungen."""
    entries = load(workspace)
    entry = _find(entries, feedback_id)
    entry.pop("clarification", None)
    _save(workspace, entries)
    return entry


def for_measure(entries: list[dict], measure_id: str) -> list[dict]:
    """Alle Punkte, die auf diese Massnahme zeigen.

    Das ist der Rueckweg, den das Portal beim Lesen baut: gespeichert ist die
    Beziehung nur am Punkt.
    """
    return [e for e in entries
            if any(l.get("measure") == measure_id for l in (e.get("links") or []))]


def _find(entries: list[dict], feedback_id: str) -> dict:
    for e in entries:
        if e.get("id") == feedback_id:
            return e
    raise ValueError(f"unbekannte Kennung: {feedback_id!r}")


def _save(workspace: str, entries: list[dict]) -> Path:
    """Schreibt atomar: erst daneben, dann umbenennen. Ein abgebrochener Lauf
    darf keine halbe Datei hinterlassen, sonst ist jede Zuordnung futsch."""
    p = feedback_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.parent / (p.name + ".tmp")
    tmp.write_text(json.dumps({"entries": entries}, ensure_ascii=False,
                              indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p
