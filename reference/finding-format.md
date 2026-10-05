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

Alle Felder sind optional. Ein Befund ohne sie bleibt gültig und wird wie bisher
gezeigt.

| Feld | Inhalt |
|---|---|
| `url` | die eine Seite im Shop, um die es geht; nur `https`. Fehlt, wenn der Befund den ganzen Shop betrifft |
| `facts` | ein bis vier kurze Fakten |
| `proof` | der Beleg aus Bausteinen: Bild, Handy-Ausschnitt, Kennzahl, Zitat, Liste, Tabelle, Verteilung |
| `evidence_text` | der Beleg als Satz für den Kunden, mit den Zahlen, die ihn tragen; nie ein Pfad |
| `decision` | zwei Wege mit Empfehlung |

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
- `decision` nur bei zwei echten Wegen.

Eine Kennzahl im Beleg wiederholt keine Zahl der Aussage in anderer Rundung.

## Prüfung

`npm run check-findings -- <run-folder>` im Portal prüft diesen Vertrag, vor
jedem Hochladen. `qa.py` prüft nur, was aus der Pipeline kommt, dazu die
Sprache der neuen Texte. `publish` verweigert einen Lauf mit offenem Auftrag
oder fehlender Datei unter `proof/`.
