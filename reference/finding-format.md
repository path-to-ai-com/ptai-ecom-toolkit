# Befund-Format

Die eine Quelle für das Format eines Befunds mit Beleg. Es gilt für das Audit
Light (`content.json`, `chapters[].findings[]`) und für den vollen Audit
(`findings/<discipline>.json`). Gelesen wird es vom Renderer des Audit Light
(`scripts/report/sales/report-pdf-full.mjs`) und vom Kundenportal
(`lib/finding-format.ts`, geprüft mit `npm run check-findings`). Ändert sich
ein Feld, ändert es sich hier und nirgends sonst; Skills und Agents verweisen
auf diese Datei, statt Felder zu wiederholen.

Herleitung: die Spec zu den Befund-Karten im Kundenportal vom 02.10.2026,
Abschnitte 18 bis 21. Beispiele: `reference/finding-format/`,
gültige unter `valid/`, je ein Verstoß unter `invalid/`. Beide Repos testen
gegen diese Dateien.

## Was neu ist

Für Altformate und Audit Light sind die folgenden Felder optional. Ein alter
Befund ohne sie bleibt gültig und wird wie bisher gezeigt. Neue volle Audits
und Reports folgen zusätzlich dem Abschnitt „Verbindliche Befundform, Version 2“.

| Feld | Inhalt |
|---|---|
| `url` | die eine Seite im Shop, um die es geht; nur `https`. Fehlt, wenn der Befund den ganzen Shop betrifft |
| `facts` | ein bis vier kurze Fakten |
| `proof` | der Beleg aus Bausteinen: Bild, Handy-Ausschnitt, Kennzahl, Zitat, Liste, Tabelle, Verteilung |
| `evidence_text` | der Beleg als Satz für den Kunden, mit den Zahlen, die ihn tragen; nie ein Pfad |
| `decision` | zwei Wege mit Empfehlung |
| `items` | Pfad der Liste der Einzelobjekte im Lauf, `items/<id>.csv` (seit 15.10.2026, nur voller Audit) |

Der rohe Beleg `evidence` (`datei.json > pfad`) bleibt, wo er ist. Er ist für
uns zum Nachprüfen und erscheint in keiner Ansicht für den Kunden.

## `facts`

Ein Eintrag ist `{"kind": ..., "text": ...}` oder `{"now": true, "text": ...}`.

| `kind` | Bedeutung | Label im Audit Light |
|---|---|---|
| `effect` | die Folge für den Kunden, nicht der Mechanismus | WARUM ES ZÄHLT |
| `cause` | die Ursache, wenn sie belegt ist | URSACHE |
| `present` | was schon da ist | VORHANDEN |
| `open` | was noch offen ist | OFFEN |
| `next` | der nächste Schritt | NÄCHSTER SCHRITT |
| `now: true` | was ohne Entscheidung sofort geht | SOFORT UMSETZBAR |

Regeln: ein bis vier Einträge, jede Art höchstens einmal, `text` ein ganzer Satz
mit höchstens 160 Zeichen. `kind` legt die Bedeutung fest; jede Oberfläche setzt
ihr eigenes Wort dafür. Das Audit Light nimmt weiter ein freies `label` an, `kind`
hat Vorrang.

**Der volle Audit schreibt `effect` (Pflicht) und `cause` (wenn belegt), sonst
nichts.** Kein `now`: jeder Befund hat dort genau eine Maßnahme, und sie ist die
Handlung. Eine zweite hervorgehobene Handlung daneben ließe den Kunden etwas
anderes lesen, als er freigibt.

## `proof`

```json
{"layout": "split", "columns": [{"label": "...", "blocks": [ ... ]}]}
```

`proof` darf auch die Liste der Spalten allein sein. Eine oder zwei Spalten,
höchstens drei Bilder (`image` und `phone` zusammen) je Befund, höchstens vier
Markierungen je Bild. `layout` ist `wide`, `split` oder `phone`; fehlt es, gilt:
eine Spalte `wide`, ein `phone` vorn `phone`, sonst `split`.

| Baustein | Felder |
|---|---|
| `metric` | `value`, `unit`, `label`; im vollen Audit stattdessen `ref`: Index in `metrics` des Befunds |
| `note` | `text` |
| `quote` | `text`, `source` |
| `chips` | `groups: [{label, own, items: [string oder {text, own}]}]`; `own` markiert die eigenen |
| `rows` | `rows: [{label, sub, text}]` oder statt `text` ein `quote` |
| `pairs` | `rows: [{from, to}]` |
| `grid` | `columns: [string]`, `rows: [{label, cells: [both, brand, other, domain, none, x, check]}]`, `legend` |
| `dist` | `parts: [{value, label, tone}]`, `total`; `tone` ist `bad`, `good` oder neutral |
| `image` | siehe unten |
| `phone` | siehe unten |

Ein unbekannter Baustein ist kein Fehler im Lauf, er wird in der Ansicht
ausgelassen und von `check-findings` gemeldet.

### Bilder

| Feld | `image` | `phone` | Inhalt |
|---|---|---|---|
| `src` | Pflicht | Pflicht | die Bilddatei; beim `phone` der Streifen für die Karte |
| `full_src` | | ja | die ganze Seite für die große Ansicht |
| `alt` | Pflicht | Pflicht | was zu sehen ist und was markiert ist |
| `title` | Pflicht | Pflicht | Überschrift der großen Ansicht |
| `width`, `height` | Pixel der Datei | CSS-Pixel der Seite (Vorgabe 390 und 1700) | |
| `fold` | | ja | Ende der Erstansicht in CSS-Pixeln der Seite, 0 ohne |
| `markers` | | ja | `[{y, label, text}]`, `y` in CSS-Pixeln der Seite |
| `rings` | ja | | `[{left, top, width, height}]` in Prozent des Bildes, 0 bis 100 |
| `addition` | ja | | unsere vorgeschlagene Zeile unter dem Bild |
| `caption` | ja | | Bildunterschrift |
| `device` | ja | ja | `mobil` oder `desktop`, dieselben Werte wie in `screens.json` |
| `captured_at` | ja | ja | Datum der Aufnahme |
| `page_url` | ja | ja | die Seite, auf der das Bild entstand |
| `capture` | ja | ja | der Aufnahme-Auftrag, siehe unten |

**Pfade** sind relativ zum Lauf-Ordner. Im vollen Audit liegen Belegbilder unter
`proof/`, etwa `proof/cro-01-1-mobil.jpg`, und kein Pfad enthält `..`. Das Audit
Light nimmt für sein PDF auch absolute Pfade an; das Portal nicht.

**Ein Bild entsteht nur, wenn es den beschriebenen Zustand zeigt.** Ist der
Mangel beim Aufnehmen schon behoben, gibt es kein Bild, und der Beleg kommt aus
Zahlen.

### Aufnahme-Auftrag `capture`

Im vollen Audit schreibt der Agent nicht das Bild, sondern was zu sehen sein
soll; `capture-screens/scripts/shoot_proof.py` nimmt es auf und schreibt das
Ergebnis daneben. Der Auftrag bleibt stehen, damit sich das Bild neu aufnehmen
lässt.

| Feld | Inhalt |
|---|---|
| `url` | die Seite |
| `device` | `mobil` oder `desktop`; beim `phone` immer `mobil` |
| `consent` | `declined` (Vorgabe): Cookie-Dialog ablehnen, auch über die zweite Ebene, sonst Fehler. `shown`: den Dialog bewusst aufnehmen |
| `crop` | `image`: das Element, auf das zugeschnitten wird, `{text}` oder `{selector}` |
| `rings` | `image`: Elemente, die markiert werden, je `{text}` oder `{selector}` |
| `markers` | `phone`: `[{target: {text} oder {selector}, text}]` |
| `absent` | was nicht da sein darf; ist es da, ist der Mangel behoben, und es entsteht kein Bild |

Ein Ziel muss genau ein sichtbares Element treffen, sonst ist der Auftrag
gescheitert und bleibt offen. Ein Lauf mit offenem Auftrag wird nicht
hochgeladen.

## Text

Alle Texte sind Klartext. Entities werden decodiert. In `quote.text` und
`rows[].quote` sind genau zwei Marken erlaubt, immer paarweise: `<mark>` für eine
Hervorhebung und `<ins>` für unsere Ergänzung, damit ein Vorschlag nie wie der
Wortlaut des Shops aussieht. Alles andere, auch zitiertes Markup wie `<title>`,
ist sichtbarer Text.

## `decision`

```json
{"question": "... oder ...?", "options": [{"title", "text", "effort", "result"}, {...}],
 "recommended": 0, "reason": "A, weil ..."}
```

Nur wo es zwei echte, verschiedene Wege gibt. `recommended` ist 0 oder 1. Im
Audit Light darf eine Option ein `image` tragen.

**Im vollen Audit** entsteht die Maßnahme aus der empfohlenen Option (Phase 3
der Skill `audit`); die andere zeigt das Portal in der Herleitung als Geprüfte
Alternative. Optionen tragen dort kein Bild.

## Was der volle Audit je Befund schreibt

Zusätzlich zu den Feldern von heute (`id`, `statement`, `metrics`,
`explanation`, `benchmark`, `effect`, `why`, `fix`, `evidence`, `severity`,
`confidence`, `effort`):

- `facts` mit `effect` und, wenn belegt, `cause`;
- `evidence_text`;
- `url`, wo eine Seite gemeint ist;
- `proof` mit Kennzahlen als `ref` auf `metrics`, mit Tabelle, Verteilung, Liste
  oder Zitat; Bilder als `capture` nur die Agents für Conversion, Content und
  Vertrauen;
- `decision` nur bei zwei echten Wegen;
- `items`, wenn der Befund eine Menge von Einzelobjekten nennt (Seiten, Bilder, Links, Produkte, URLs).

## `items`

Die Liste, nicht nur die Zahl. Nennt ein Befund "37 Backlinks", muss die Marke
wissen, welche; sonst ist die Maßnahme daraus nicht umsetzbar.

- Datei `items/<id>.csv` im Lauf-Ordner, UTF-8 mit BOM, Kopfzeile, eine Zeile
  je Objekt. Die Spalten kommen aus der Quelle (etwa `url_from`, `url_to`),
  dahinter immer `checked_at` (Datum der Prüfung dieser Zeile, `YYYY-MM-DD`)
  und `status` (`open` oder `done`). Nach einer Neuprüfung von Adressen
  kommt `checked_status` dazu, der HTTP-Status dieser Prüfung.
- Die Zahl der Zeilen ist die Zahl im Befund.
- Erzeugt mit `python3 -m audit.readiness items`, neu geprüft mit
  `python3 -m audit.readiness recheck`. Die Maßnahme trägt denselben Pfad in
  `items`, in der Liste einer Marke je Store unter `by_shop.<store>`.
- Die Liste geht mit dem Lauf 1:1 in den Bucket.

Eine Kennzahl im Beleg wiederholt keine Zahl der Aussage in anderer Rundung.

## Prüfung

`npm run check-findings -- <run-folder>` im Portal prüft diesen Vertrag, vor
jedem Hochladen. `qa.py` prüft nur, was aus der Pipeline kommt, dazu die
Sprache der neuen Texte. `publish` verweigert einen Lauf mit offenem Auftrag
oder fehlender Datei unter `proof/`.

## Verbindliche Befundform, Version 2

Neue volle Audits und Reports schreiben `finding_format: 2` an die Wurzel jeder
Datei `findings/*.json`. `audit.state.new()` setzt denselben Wert automatisch
in `state.json`. Er gilt für alle Befunde des Laufs, auch wenn eine Befunddatei
ihren eigenen Formatstand vergisst. Dateien ohne eigenen Formatstand erben den
des Laufs. Widersprechende oder unbekannte Versionen werden abgewiesen.

Ein alter Lauf ohne Formatstand und ohne die neuen Felder bleibt gültig. Laden
und Wiederaufnehmen stempeln ihn nicht nachträglich um. Schon eines der neuen
Felder aktiviert die vollständige v2-Prüfung auch ohne Formatstand. Der
Formatstand ist eine Vertragsangabe, keine Sicherheitsgrenze gegen einen
Schreiber, der Laufdateien absichtlich manipuliert. Neue Läufe immer über
`audit.state.new` beziehungsweise `load_or_new` anlegen, nie durch Kopieren
einer alten `state.json` oder freies Erstellen eines Laufordners.

Die bisherigen Felder bleiben für PDF und heutige Cockpit-Ansicht erhalten.
Die folgenden Felder sind die eindeutige Quelle für den späteren einheitlichen
Befund; keine Ansicht muss die Grafik aus `proof.columns` erraten.
Audit Light behält seinen bisherigen Vertrag; sein PDF wird hier nicht umgebaut.

| Pflichtfeld je Befund | Inhalt |
|---|---|
| `primary_metric` | `{value, unit, label, basis, period}`; `value` ist eine endliche JSON-Zahl, auch 0 oder negativ, alles andere nichtleerer Klartext. `label` benennt die Zahl, `basis` den Bezug, `period` den belegten Zeitraum oder Aufnahmetag. Prozent und Prozentpunkte ausdrücklich unterscheiden. |
| `visualization` | genau eine der vier Arten unten; Werte immer numerisch, nie lokalisierte Zahlenstrings |
| `reasoning` | genau `{cause, effect, recommendation}` mit je einem abgeschlossenen Satz: Ursache, Auswirkung, Empfehlung, in dieser Reihenfolge |

Keine erfundene Ursache: Ist sie nicht belegt, sagt `cause` ausdrücklich
„Die Ursache ist mit den vorhandenen Daten nicht geklärt.“ und behauptet keinen
Mechanismus. Eine Korrelation bleibt eine Korrelation. `effect` formuliert nur
belegte Auswirkungen oder kennzeichnet eine mögliche Folge. Die Satzprüfung
prüft Satzzeichen und gängige Abkürzungen, keine inhaltliche Wahrheit.

### Grafikarten

Alle numerischen Vergleichs- und Anteilwerte sind endlich und mindestens 0.
`unit` gilt für **alle** Werte derselben Grafik, einschließlich ihrer Grenze.
`period` steht an jeder Zahlengrafik ausdrücklich; die verglichenen Werte
müssen sachlich und zeitlich vergleichbar sein. `role: focus` bezeichnet die
untersuchte Reihe, `reference` die Basis, unabhängig von Rang und Betrag.

- `comparison`: `{type: "comparison", unit, period, values: [{label, value, role}, …], threshold: {value, label, criterion}}`.
  Mindestens zwei Werte, darunter `focus` und `reference`. `criterion` nennt
  das belegte Prüfkriterium als Satz. Die Grenze wird in die gemeinsame Einheit
  umgerechnet: Bei 2.096 Bestellungen und höchstens 5 % Abweichung ist
  `threshold.value` **2200.8 Käufe**, nicht 5. Die Hauptzahl darf dagegen 41 %
  sein. Alle Balken starten bei null und nutzen dieselbe Skala.
- `share`: `{type: "share", unit, period, total, parts: [{label, value, role}, …]}`.
  Mindestens zwei Teile, positive Gesamtsumme; Summe der Teile entspricht
  `total`. Für 48 % und 52 % ist die Einheit `%` und `total: 100`; bei
  Umsatzbeträgen stattdessen dieselbe Währung für Teile und Gesamtsumme.
- `trend`: `{type: "trend", unit, period, points: [{date: "YYYY-MM-DD", value}, …], marker?: {date, label}}`.
  Mindestens zwei echte Kalendertage, eindeutig und streng aufsteigend, Werte
  dürfen negativ sein. Ein optionaler markierter Zeitpunkt nennt einen
  vorhandenen Messpunkt. Fehlende Messungen werden ausgelassen, nie zu 0.
- `image`: `{type: "image", proof_ref: {column, block}, comparison?: {unit, period, values, threshold?}}`.
  Die nullbasierten Indizes zeigen auf genau ein `image` oder `phone` in
  `proof.columns` (oder der bisherigen Spaltenliste). Dessen bestehende Regeln
  für Pfad, Alternativtext, Aufnahme und Markierungen gelten weiterhin.
  `comparison` erlaubt den zusätzlichen Handy/Desktop-Vergleich von CRO-01,
  ohne dieselbe Bilddatei zweimal zu speichern. Seine Grenze ist optional,
  eine übergebene Grenze muss aber vollständig sein.

Zusätzliche Kennzahlen bleiben als kleine Zeile in `metrics`, Methode,
Prüfkriterium, Quelle und geprüfte Alternative in den bisherigen Feldern.
`reasoning` hat keine weiteren Felder und ersetzt als zukünftiger Lesetext die
überlappenden Erläuterungen; bis zur Anzeige-Umstellung müssen alte und neue
Texte inhaltlich übereinstimmen.

### Beispiele und Prüfung

`reference/finding-format/valid/presentation-v2.json` beschreibt die erfundene
Demo-Marke Nordwerk: MES-01 für Screenshot 02 (Vergleich), CRO-01 für 03
(Belegbild und Gerätevergleich), HDL-01 für 04 (Umsatzanteil). Es sind
isolierte Vertragsbeispiele, keine umgeschriebenen Laufdateien. Eine echte
Bildaufnahme wird erst im Lauf ergänzt. `presentation-trend-v2.json` belegt die
vierte Art; `presentation-invalid.json` enthält gemeinsame Negativfälle für
Python und TypeScript. Beide Repos halten bytegleiche Kopien dieser Beispiele.

Vor Upload prüfen `audit.qa`, `audit.publish` und im Portal
`npm run check-findings -- <run-folder>` die neuen Pflichtangaben. Fehler nennen
Datei, Befundkennung und Feld. `publish` hält vor dem ersten Kopieren an, ohne
Upload, Veröffentlichung oder automatische Ergänzung fehlender Zahlen.
