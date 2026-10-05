---
name: match-feedback
description: Eine Liste von außen gegen den Maßnahmen-Bestand abgleichen und das Ergebnis als reporting/feedback.json schreiben, damit im Portal an jeder Maßnahme steht, welche Kundenanforderung sie beantwortet. Nutzen bei /ptai-ecom:match-feedback, wenn eine Kundenliste, ein Termin-Protokoll oder eine Mail mit Änderungswünschen hereinkommt, oder wenn der Nutzer nach Abgleich, Zuordnung, Dubletten oder "haben wir das schon als Maßnahme" fragt. Liest reporting/measures.json im Kunden-Workspace.
---

# match-feedback: was von außen kam, an die Maßnahme hängen

Feedback kommt laufend herein, aus einer Kundenliste, aus einem Termin, aus
einer Mail. Jedes Mal stellt sich dieselbe Frage: existiert das schon als
Maßnahme? Ohne sichtbare Antwort entstehen Dubletten, und niemand sieht, dass
zwei Einträge dasselbe meinen.

Dieser Skill beantwortet die Frage einmal pro Punkt und schreibt die Antwort
dorthin, wo das Portal sie liest: `reporting/feedback.json`, geschrieben über
`scripts/audit/feedback.py`. Die Verknüpfung steht nur dort, nie in
`measures.json`: ein Punkt kann auf mehrere Maßnahmen fallen, eine Maßnahme
mehrere Punkte einsammeln, und dieselbe Beziehung an zwei Stellen zu führen
erzeugt zwei Wahrheiten.

## Voraussetzungen

Arbeitsverzeichnis ist der Kunden-Workspace. Dort muss `reporting/measures.json`
liegen, sonst gibt es nichts, wogegen abgeglichen werden könnte; in dem Fall
sagen, dass zuerst ein Audit laufen muss, und hier aufhören.

Die Liste selbst kommt als Datei, als Export oder als Text im Gespräch. Sie wird
nie verändert und nie interpretiert: was in ihr steht, geht im Wortlaut als
`original` mit, getrennt von allem, was wir daraus machen. Unser Titel darf
übersetzen und schärfen, das Original daneben bleibt, wie der Kunde es
geschrieben hat. Was wir daraus schließen, steht im Grund der Verknüpfung.

## Der Ablauf

**1. Den Geltungsbereich klären, bevor irgendetwas angelegt wird.** Eine
Kundenliste deckt oft mehr ab als der Shop, an dem wir arbeiten: andere Marken,
andere Systeme, Themen hinter dem Shop. Steht das nicht ausdrücklich fest, wird
es gefragt und als Kontexteintrag festgehalten (`scripts/audit/context.py`).
Belegt an einer Liste mit 29 Aufgaben: 23 davon galten für alle Marken des
Hauses und nur eine ausdrücklich für den Shop, um den es ging.

**2. Jeden Punkt gegen den Bestand halten.** Für jeden Punkt der Liste den
Maßnahmen-Bestand durchsuchen und entscheiden, welcher der fünf Fälle vorliegt:

| Fall | Was geschieht |
|---|---|
| Deckt sich mit einer bestehenden Maßnahme | Punkt anlegen, Verknüpfung mit `certainty="confirmed"` |
| Überschneidet sich, aber nicht deckungsgleich | Punkt anlegen, Verknüpfung mit `certainty="proposed"` und der offenen Frage |
| Kommt in keiner Maßnahme vor | Maßnahme anlegen (`measures.py`), dann Punkt anlegen und `confirmed` mit `created=True` verknüpfen |
| Unklar, was der Punkt überhaupt meint | Punkt anlegen und `set_clarification()` mit unserer Frage an den Kunden |
| Gehört nicht in dieses Projekt | Punkt anlegen und `mark_out_of_scope()` mit dem Grund |

**Die Grenze zwischen den ersten beiden Fällen ist der Gegenstand, nicht das
Thema.** Zwei Punkte über dieselbe Seite sind nicht dieselbe Sache, wenn der
eine den Text meint und der andere das Bild. Im Zweifel `proposed`: eine
vermutete Zuordnung kostet eine Rückfrage, eine falsche feststehende kostet eine
Maßnahme, an der niemand mehr arbeitet.

**Eine Vermutung braucht einen Gegenstand, eine Klärung nicht.** Lässt sich aus
dem Punkt nicht sagen, was gemeint ist, etwa weil die Quelle nur einen Titel
trägt, wird er nicht an die nächstbeste Maßnahme gehängt, sondern bekommt mit
`set_clarification()` unsere Frage, im Wortlaut, wie der Kunde sie liest. Das
Portal zeigt ihn als "Klärung ausstehend" und die Frage unter "Frage an euch";
beantwortet wird sie im Termin. Danach nimmt `clear_clarification()` die Frage
zurück, und der Punkt wird verknüpft wie jeder andere. Belegt am 29.09.2026: eine
Anforderung hing als Vermutung an einer Maßnahme, die kaum passte, und die Frage
dazu konnte der Kunde nicht beantworten, weil sie eine Zuordnung voraussetzte.

**3. Schreiben, nicht von Hand redigieren.** Die Datei entsteht ausschließlich
über die Funktionen, weil sie prüfen, was das Portal braucht:

```python
from audit import feedback

item = feedback.add(ws, title="Bewertungssterne in Kopfzeile und auf der Produktseite",
                    source="Aufgabenliste vom 17.09.2026, Mara Beispiel",
                    ref="4711",
                    original={"title": "Rating stars in header and on PDP",
                              "section": "UX & CRO", "priority": "High"})
feedback.link(ws, item["id"], "M-069", "confirmed",
              why="M-069 ist die Bewertungsangabe in der Ankündigungsleiste.")
feedback.link(ws, item["id"], "M-012", "proposed",
              why="Beides ist Weiterleitung und Duplikat.",
              question="Welche doppelt angelegten Kategorien sind gemeint?")
feedback.link(ws, "FB-015", "M-071", "confirmed", created=True,
              why="Als M-071 aufgenommen: die Suche selbst hat noch niemand geprüft.")
feedback.set_clarification(ws, "FB-014", "Was soll das Quiz am Ende empfehlen?")
feedback.mark_out_of_scope(ws, "FB-025", "Andere Marke, bleibt in eurer Liste.")
```

`original` nimmt, was die Quelle zu dem Punkt sagt, mit den Schlüsseln aus
`feedback.ORIGINAL_FIELDS`: `title`, `section`, `shop`, `priority`, `goal` und
`notes`. Aus einem Export ist das die ganze Zeile, jede Spalte auf ihr Feld
gelegt; die Kennung der Zeile geht in `ref`. Leere Spalten fallen von selbst
weg, eine Spalte ohne passendes Feld wird abgelehnt, weil das Portal sie nicht
beschriften kann. Für Punkte, die schon angelegt sind, trägt
`feedback.set_original()` die Angaben nach.

`created=True` gehört an jede Verknüpfung auf eine Maßnahme, die in diesem
Abgleich aus dem Punkt entstanden ist. Ohne die Angabe zeigt das Portal sie als
bestehende Maßnahme, der der Punkt zugeordnet wurde, und ihren Status als
gemessen, obwohl ihn noch kein Lauf geprüft hat. Festgehalten wird das am Punkt
in `created_measures`, nicht am Link: die Herkunft bleibt stehen, wenn die
Verknüpfung später gelöst oder der Punkt aus dem Projekt genommen wird. Fehlt
sie bei einem Punkt ohne Verknüpfung, trägt `feedback.record_created()` sie nach.

`link()` lehnt eine unbekannte Maßnahmen-Kennung ab, einen leeren Grund, eine
Vermutung ohne Frage und `created` an einer Vermutung. `set_clarification()`
lehnt eine leere Frage ab und einen Punkt außerhalb des Projekts;
`mark_out_of_scope()` nimmt eine offene Frage mit, weil was außerhalb liegt,
keine Klärung mehr braucht. Diese Fehler sind der
Grund, warum es die Funktionen gibt; wer sie umgeht und die JSON von Hand
schreibt, verliert genau die Prüfung.

**4. Prüfen und ablegen.** `feedback.validate()` über den fertigen Stand laufen
lassen, Fehler beheben, dann kurz auszählen, wie viele Punkte zugeordnet,
vermutet, zu klären, offen und außerhalb sind. Die Zählung gehört in die Antwort, sie ist
der Beleg, dass kein Punkt der Liste verloren ging.

**5. Der Abgleich selbst wird ein Dokument.** Die Datei trägt die Zuordnungen,
nicht die Herleitung. Eine datierte Seite im Workspace
(`reporting/<datum>-<quelle>-abgleich.md`) hält fest, was entschieden wurde und
warum, und wird im Termin besprochen. Beides zusammen, nicht eines statt des
anderen.

## Was dieser Skill nicht tut

**Keinen Status setzen.** Eine Verknüpfung sagt "das ist dieselbe Sache", nie
"das ist damit erledigt". Ob eine Maßnahme umgesetzt ist, entscheidet allein die
Prüfregel im Folgelauf.

**Nichts hochladen.** Sichtbar wird die Datei erst mit dem nächsten `publish`,
und das ist ein eigener, bewusster Schritt.

**Keine Aufgabe erfinden.** Was der Kunde nicht geschrieben hat, steht nicht in
der Liste. Unklare Punkte werden als Frage zurückgegeben, nicht geraten.
