---
name: match-feedback
description: Gleicht eine Liste von außen mit dem Maßnahmen-Bestand ab und schreibt das Ergebnis nach reporting/feedback.json, damit das Portal an jeder Maßnahme die zugehörigen Kundenanforderungen zeigt. Auslöser sind /ptai-ecom:match-feedback, eine eingehende Kundenliste, ein Termin-Protokoll oder eine Mail mit Änderungswünschen sowie Fragen nach Abgleich, Zuordnung, Dubletten oder "haben wir das schon als Maßnahme". Liest reporting/measures.json im Kunden-Workspace.
---

# match-feedback: Feedback den Maßnahmen zuordnen

- Für jeden Punkt einer eingehenden Liste (Kundenliste, Termin, Mail) wird entschieden, ob es ihn schon als Maßnahme gibt.
- Ergebnis: `reporting/feedback.json`, geschrieben über `scripts/audit/feedback.py`.
- Die Verknüpfung steht nur in `feedback.json`, nie in `measures.json`. Ein Punkt kann zu mehreren Maßnahmen gehören, eine Maßnahme zu mehreren Punkten; eine zweite Stelle würde abweichende Stände erzeugen.

## Voraussetzungen

1. Arbeitsverzeichnis ist der Kunden-Workspace.
2. `reporting/measures.json` existiert. Fehlt sie: melden, dass zuerst ein Audit laufen muss, und abbrechen.
3. Die Liste kommt als Datei, Export oder Text im Gespräch.
4. Die Liste nie ändern und nie deuten. Ihr Wortlaut geht unverändert als `original` mit.
5. Unser `title` darf übersetzen und präzisieren; `original` bleibt im Wortlaut des Kunden.
6. Eigene Schlussfolgerungen stehen im Grund (`why`) der Verknüpfung.

## Ablauf

### 1. Geltungsbereich klären

- Bevor etwas angelegt wird, klären, welche Punkte den Shop dieses Projekts betreffen. Kundenlisten enthalten oft andere Marken, andere Systeme oder Themen außerhalb des Shops.
- Ist der Geltungsbereich nicht ausdrücklich festgelegt: nachfragen und die Antwort als Kontexteintrag speichern (`scripts/audit/context.py`).

### 2. Jeden Punkt mit dem Bestand abgleichen

Für jeden Punkt den Maßnahmen-Bestand durchsuchen und einen der fünf Fälle wählen:

| Fall | Was geschieht |
|---|---|
| Deckt sich mit einer bestehenden Maßnahme | Punkt anlegen, Verknüpfung mit `certainty="confirmed"` |
| Überschneidet sich, aber nicht deckungsgleich | Punkt anlegen, Verknüpfung mit `certainty="proposed"` und der offenen Frage |
| Kommt in keiner Maßnahme vor | Maßnahme anlegen (`measures.py`), dann Punkt anlegen und `confirmed` mit `created=True` verknüpfen |
| Unklar, was der Punkt überhaupt meint | Punkt anlegen und `set_clarification()` mit unserer Frage an den Kunden |
| Gehört nicht in dieses Projekt | Punkt anlegen und `mark_out_of_scope()` mit dem Grund |

Regeln für die Zuordnung:

- `confirmed` gegen `proposed` entscheidet der Gegenstand, nicht das Thema. Zwei Punkte zur selben Seite sind verschieden, wenn einer den Text und der andere das Bild betrifft.
- Im Zweifel `proposed`. Eine falsche feste Zuordnung hinterlässt eine Maßnahme, an der niemand weiterarbeitet.
- `proposed` setzt einen erkennbaren Gegenstand voraus. Ist unklar, was der Punkt meint (etwa weil die Quelle nur einen Titel hat), keine Vermutung an eine schwach passende Maßnahme hängen, sondern `set_clarification()` mit unserer Frage im Wortlaut für den Kunden.
- Das Portal zeigt solche Punkte als "Klärung ausstehend" und die Frage unter "Frage an euch". Beantwortet wird sie im Termin.
- Nach der Antwort `clear_clarification()` aufrufen und den Punkt normal verknüpfen.

### 3. Nur über die Funktionen schreiben

Die Datei nie von Hand bearbeiten; nur die Funktionen prüfen, was das Portal braucht.

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

`original`:

- Enthält die Angaben der Quelle zum Punkt, mit den Schlüsseln aus `feedback.ORIGINAL_FIELDS`: `title`, `section`, `shop`, `priority`, `goal`, `notes`.
- Bei einem Export: die ganze Zeile, jede Spalte auf ihr Feld; die Zeilenkennung in `ref`.
- Leere Spalten werden automatisch weggelassen.
- Eine Spalte ohne passendes Feld wird abgelehnt, weil das Portal keine Beschriftung dafür hat.
- Für bereits angelegte Punkte ergänzt `feedback.set_original()` die Angaben.

`created=True`:

- Pflicht an jeder Verknüpfung auf eine Maßnahme, die in diesem Abgleich aus dem Punkt entstanden ist.
- Ohne die Angabe zeigt das Portal sie als bestehende Maßnahme und ihren Status als gemessen, obwohl noch kein Lauf sie geprüft hat.
- Gespeichert wird die Herkunft am Punkt in `created_measures`, nicht am Link. So bleibt sie erhalten, wenn die Verknüpfung gelöst oder der Punkt aus dem Projekt genommen wird.
- Fehlt sie bei einem Punkt ohne Verknüpfung: mit `feedback.record_created()` ergänzen.

Prüfungen der Funktionen:

- `link()` lehnt ab: unbekannte Maßnahmen-Kennung, leeren Grund, Vermutung ohne Frage, `created` an einer Vermutung.
- `set_clarification()` lehnt ab: leere Frage, Punkt außerhalb des Projekts.
- `mark_out_of_scope()` entfernt eine offene Frage, weil ein Punkt außerhalb des Projekts keine Klärung braucht.

Wer die JSON von Hand schreibt, umgeht diese Prüfungen.

### 4. Prüfen und zählen

1. `feedback.validate()` über den fertigen Stand ausführen und Fehler beheben.
2. Zählen, wie viele Punkte zugeordnet, vermutet, zu klären, offen und außerhalb sind.
3. Die Zählung in die Antwort schreiben; sie belegt, dass kein Punkt der Liste fehlt.

### 5. Abgleich dokumentieren

- `feedback.json` enthält nur die Zuordnungen, nicht die Herleitung.
- Zusätzlich eine datierte Seite im Workspace anlegen: `reporting/<datum>-<quelle>-abgleich.md`, mit den Entscheidungen und ihren Gründen. Sie wird im Termin besprochen.
- Immer beides erstellen, nie nur eines.

## Grenzen

- Kein Status setzen. Eine Verknüpfung bedeutet "dieselbe Sache", nie "erledigt". Ob eine Maßnahme umgesetzt ist, entscheidet nur die Prüfregel im Folgelauf.
- Nichts hochladen. Die Datei wird erst mit dem nächsten `publish` sichtbar, einem separaten Schritt.
- Keine Aufgaben erfinden. In die Liste kommt nur, was der Kunde geschrieben hat. Unklare Punkte als Frage zurückgeben, nicht raten.
