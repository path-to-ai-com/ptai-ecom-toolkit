---
name: report
description: Erzeugt den Monats-Report für den Kunden-Workspace. Orchestriert alle Quellen-Pulls (Shopify, GA4, Search Console, Core Web Vitals, GEO), vergleicht mit dem Vormonats-Snapshot, schreibt reporting/reports/YYYY-MM-monthly.md und rendert das Kunden-PDF im Path-to-AI-CI. Auslöser sind /ptai-ecom:report oder der Wunsch nach Monatsreport, Kundenreport oder Report-PDF. Liest reporting/config.json im Kunden-Workspace.
---

# report: Monats-Report mit PDF

- Ein Lauf zieht alle angeschlossenen Quellen, schreibt den Markdown-Report mit sechs Kapiteln und rendert daraus das Kunden-PDF im Path-to-AI-CI.
- Nicht angeschlossene oder gescheiterte Quellen blockieren nie. Sie stehen im Report als "nicht verfügbar (Grund)", der Rest läuft weiter.

## Voraussetzungen

Arbeitsverzeichnis ist der Kunden-Workspace (enthält `reporting/`).

- `reporting/config.json` (angelegt von der Skill `setup`) mit mindestens einer Quelle auf `true` unter `sources`.
- Für das PDF ein headless Browser: bevorzugt die Headless Shell von Playwright, sonst Chrome oder Chromium. Fehlt er, den Markdown-Report trotzdem schreiben und den PDF-Schritt als Fehler melden (Hinweis auf `/ptai-ecom:setup`); den Lauf nie ganz abbrechen.

Config fehlt komplett (typisch, wenn `/ptai-ecom:report` als Erstes aufgerufen wird):

1. Nichts raten, nichts anlegen.
2. In zwei Sätzen sagen, was fehlt und warum der Report ohne Config nicht möglich ist.
3. Anbieten, jetzt die Skill `setup` zu starten. Bei Ja übernimmt der Wizard, bei Nein hier aufhören.
4. Keine Meldung ohne nächsten Schritt, kein leerer Report.

Config vorhanden, aber keine Quelle liefert (alle aktiven Quellen scheitern an Secrets oder Auth):

1. Keinen Report schreiben, der nur aus "nicht verfügbar" besteht.
2. Die betroffenen Quellen mit Grund auflisten und anbieten, das Setup zu starten.
3. Liefert mindestens eine Quelle Zahlen, läuft der Report normal; die übrigen Quellen stehen als "nicht verfügbar (Grund)".

## Ablauf

1. **Config lesen, Berichtsmonat bestimmen.** Default: letzter voller Monat (Erster bis Letzter des Vormonats von heute). Nennt der Nutzer einen Monat, gilt dieser volle Kalendermonat; die Datumsgrenzen dann ausdrücklich an die Pulls geben (`SINCE`/`UNTIL` bzw. `--start`/`--end`).
2. **Vormonats-Snapshot suchen** (Semantik unten). Ergebnis je Quelle: ein Vormonats-Ordner oder Erstlauf.
3. **Alle aktiven Quellen nacheinander ziehen:** Skills `pull-shopify`, `pull-ga4`, `pull-gsc`, `pull-cwv`, `check-geo`, jeweils nur bei `sources.<quelle>: true`.
   - Den Vergleichsmonat nur dann live mitziehen (`--compare-start/--compare-end` bzw. `comparison`-Teil-Pulls), wenn Schritt 2 für die Quelle keinen Vormonats-Snapshot gefunden hat.
   - Fehler bleiben je Quelle isoliert: die Quelle wird "nicht verfügbar (Grund)", die anderen laufen weiter.
   - Fallen alle Quellen aus: mit klarer Meldung abbrechen, kein leeres PDF bauen.
4. **Vergleichs-Präzedenz: Snapshot schlägt Live.** Existiert ein Vormonats-Snapshot, ist er die einzige Vergleichsbasis; `comparison`-Blöcke in neu gezogenen Dateien ignorieren. Grund: APIs korrigieren Zahlen nachträglich, und der neue Report darf dem alten nicht widersprechen.
5. **Markdown-Report schreiben:** `reporting/reports/YYYY-MM-monthly.md` mit den sechs Kapiteln (unten), am Ende der Schluss (Abschnitt "Schluss" unten).
6. **PDF rendern** (Ablauf unten), Ergebnis neben dem Markdown.
7. **Zusammenfassung an den Nutzer:** Kernbefunde (Executive-Sätze in Kurzform), wichtigste Maßnahme, nicht verfügbare Quellen, Pfade zu `.md` und `.pdf`.

Der Lauf liest nur. In Kundensysteme (Shop, GA4, GSC) wird nie geschrieben.

## Vormonats-Snapshot: die Such-Semantik

Vormonat ist der Kalendermonat vor dem Berichtsmonat (Berichtsmonat Juli 2026, Vormonat Juni 2026).

| Quellen | Regel |
|---|---|
| Mit `period` (`shopify.json`, `ga4.json`, `gsc.json`) | Je Datei der jüngste Ordner unter `reporting/data/`, dessen Datei einen `period` mit granularity `month` über den vollen Vormonat hat (start am Ersten, end am Letzten des Vormonats). `-pulse`-Dateien ignorieren, sie sind nie Vergleichsbasis. Normalerweise ergeben alle drei denselben Ordner. |
| Ohne `period` (`cwv.json`, `geo.json`) | Den Ordner übernehmen, den die Quellen mit `period` ergeben haben (bei Abweichung den jüngsten davon). Nie separat nach der jüngsten `cwv.json` oder `geo.json` suchen, sie kann von einem Puls-Tag oder Zwischenlauf stammen. Fehlt die Datei im gewählten Ordner, hat die Quelle keinen Vormonats-Vergleich. |
| Kein passender Ordner | Erstlauf für diese Quelle; der Pull zieht den Vergleichsmonat live mit (so auch in den Pull-Skills beschrieben). |

## Zahlen-Regeln (hart)

- Jede Zahl im Report stammt aus einem Snapshot-Feld. Nichts schätzen, nichts erfinden, keine Benchmarks aus dem Modellwissen.
- Branchenvergleiche nur qualitativ und ausdrücklich als Einschätzung gekennzeichnet, nie als Zahl.
- Deutsche Formate: `12.480 €`, `3,1 %`, Deltas mit Vorzeichen (`+8,2 %`).
- Runden ohne Schein-Präzision: Umsatz auf Euro, Conversion Rate auf eine Nachkommastelle.
- Vergleichsbasis 0 oder fehlend: kein Prozent-Delta, stattdessen absolute Differenz oder kein Delta.
- Fehlt der Vergleich für eine Quelle ganz: Delta-Spalte komplett weglassen, keine leeren Zellen.

**Conversion-Präzedenz:**

1. Berichtete Conversion Rate = `totals.orders` geteilt durch `sessions.sessions`, beides aus `shopify.json`. Sessions ebenfalls von dort.
2. Nicht `sessions.conversion_rate` verwenden. Das Feld zählt nur Bestellungen, die Shopify einer Session zuordnen konnte, liegt deshalb systematisch zu tief und passt nicht zur Bestellzahl daneben.
3. Weicht `sessions.conversion_rate` stark von der gerechneten Rate ab, ist das ein Befund zur Zuordnung, kein Rechenfehler: ein Satz ins Traffic-Kapitel, wie viele Bestellungen keiner Session zugeordnet sind.
4. Fehlt `sessions` ganz: Funnel und Conversion aus `ga4.json` (`funnel`, Conversion = purchase geteilt durch sessions), mit dem Hinweis im Report, dass GA4 untererfasst.
5. Fehlt beides: Conversion nicht berechenbar. Das steht als Satz im Shop-Kapitel, keine Ersatzzahl.

## Kennzahlen-Katalog (verbindlich)

- Formeln, Quellfelder, Diagnose-Schwellen und Benchmark-Bänder: `${CLAUDE_PLUGIN_ROOT}/reference/metrics.md`.
- Der Report verwendet keine eigene Formel und keine eigene Schwelle.
- Hat eine Kennzahl dort einen Parameter (etwa die Mindest-Impressionen für Striking-Distance-Queries), gilt genau dieser Wert.
- Benchmarks sind immer Fremdquelle mit Datum, nie eigene Messung. Die Quelle steht in Klammern hinter der Einordnung, etwa "(Benchmark: karbonanalytics.com, abgerufen 2026-08-11, Fremdquelle)".
- Eine Benchmark ordnet ein und bewertet nicht: "liegt unter dem Median der Shopify-Shops", nicht "zu niedrig".
- Fehlt ein Wert im Katalog, nichts schätzen. Ohne Benchmark nur der Vergleich zum eigenen Vormonat. Keine Zahl aus dem Modellwissen, auch nicht als grobe Größenordnung.
- Ist eine Diagnose nach Katalog nicht berechenbar (Feld `null`, zu wenige Vergleichszeilen, Nenner 0): ihren Block im Kapitel durch einen Satz mit Begründung ersetzen, keine leere Tabelle.

## Fehler-Shapes je Quelle (alle abfangen, nie crashen)

Die Snapshots melden Teilausfälle in festen Formen. Jede Form behandeln; ein unerwartetes Shape führt zu einer Note im Report, nie zu einem Abbruch.

**`shopify.json`**

- Kern-Felder (`top_products`, `top_collections`, `sessions`, `products`, `customer_type` u. a.) können `null` sein; der Grund steht in `notes`. Im Report die Note in einem Satz wiedergeben, keine leeren Tabellen.
- `customer_type` `null`: keine Repeat-Rate, kein Ersatzwert.
- `products` `null`: keine Sortiments-Diagnosen.
- `total_inventory` und `status` je Produkt können `null` sein: Spalte leer lassen oder weglassen. Für das Bestandsrisiko gilt `null` als "Bestand unbekannt", nie als unauffällig.
- `comparison` gibt es nur beim Erstlauf. Fehlt er und gibt es keinen Vormonats-Snapshot: kein Delta.
- Genullte Felder in `comparison` haben ihren Grund in einem eigenen `notes`-Eintrag dort: betroffenes Delta weglassen.

**`ga4.json`**

- `comparison` fehlt oder ist `{"error": ...}`: kein Delta.
- `channels[].purchases` kann `null` sein (Property hat die Metrik abgelehnt, Grund unter `notes.purchases`): Spalte Conversion Rate in der Kanal-Tabelle komplett weglassen, keine leeren Zellen, keine 0 als Ersatz.
- Snapshots von vor dem 11.09.2026 haben statt `purchases` nur `transactions`. Darin zählt GA4 Refunds mit; das Feld nie als Käufe lesen.
- `purchase_revenue` steht in `currency`, der Währung der Property. Weicht sie von der Shop-Währung ab: kein Umsatzvergleich mit Shopify.

**`gsc.json`**

- `sitemaps` ist eine Liste oder `{"error": ...}`.
- `index_sample`-Einträge können `{"url", "error"}` sein: je URL als "Prüfung fehlgeschlagen" ausweisen, nie als "nicht indexiert".
- `comparison` fehlt oder ist `{"error": ...}`: kein Delta.

**`cwv.json`**

- `pages`-Einträge können `{"url", "error"}` sein; die URL fehlt dann mit Grund.
- `field_data` `null` ist kein Fehler, sondern zu wenig CrUX-Traffic: als "keine Feld-Daten (zu wenig Traffic)" ausweisen und den Lab-Score trotzdem verwenden.

**`geo.json`**

- `brand_mentioned`/`domain_cited` können `null` sein (nicht prüfbar): nie als `false` zählen, aus allen Quoten herausrechnen, Zeilen separat als "nicht prüfbar" ausweisen.
- Zeilen haben ein `method`-Feld (`api` oder `browser`).
- Nicht angeschlossene Plattformen stehen mit `null`/`null` und `evidence` "nicht angeschlossen: kein API-Key".
- `crawlers` ist das Objekt mit acht Schlüsseln oder `{"error": ...}`.
- `llms_txt` ist boolesch.
- `other_citations` ist immer eine Liste, bei nicht prüfbaren Zeilen leer. Fehlt das Feld ganz (Snapshot aus älterem Lauf): Share of Voice mit einem Satz weglassen, nicht aus `evidence` ableiten.

**Ganze Quelle fehlt** (Pull gescheitert, `sources` auf `false`, Datei fehlt): Kapitel bleibt mit dem Satz "nicht verfügbar (Grund)" statt Zahlen. Kapitel nie streichen; die Struktur ist jeden Monat gleich.

## Die sechs Kapitel

Markdown: H1 `<Brand> · Monats-Report <Monat JJJJ>`, je Kapitel ein H2, Reihenfolge wie im PDF.

### 1. Executive Summary

- Zuerst die Zahlen, dann wenig Text.
- Acht KPI-Kacheln in zwei Reihen zu vier (`kpi-grid kpi-grid--4`). Der Monat muss aus den Kacheln ohne Fließtext verständlich sein.
- Erste Reihe, fest: Umsatz, Bestellungen, Warenkorbwert, Sessions.
- Zweite Reihe, je Monat gewählt, für die Kernaussage: typischerweise Conversion Rate, die Kennzahl mit dem größten Sichtbarkeits-Hebel (Suchklicks, GEO Citation Rate) und ein bis zwei Raten, an denen die Hauptmaßnahme hängt (Produktansichtsrate, Add-to-Cart-Rate, Repeat-Rate). Was den Monat nicht erklärt, kommt nicht in die Reihe.

Harte Regeln:

- Genau acht Kacheln, keine Kachel ohne Wert.
- Jede Kachel hat den Vormonatswert als Caption. Ohne Vormonatswert (erster Snapshot einer Quelle) ist die Kennzahl keine Kachel.
- Keine Kachel dupliziert eine andere. Beispiel: "Davon im Shop" neben "Bestellungen" ist bei einem reinen Onlineshop dieselbe Zahl. Aufteilungen nur, wenn sie sich im Berichtsmonat unterscheiden.
- Ein Kennzahlname bezeichnet im ganzen Report dieselbe Zahl. Steht auf einer Kachel "Add-to-Cart-Rate 0,5 %", darf derselbe Name nicht an anderer Stelle mit 2,6 % stehen. Andernfalls den Bezug ausschreiben ("von den Sessions mit Produktansicht").
- Raten nebeneinander haben dieselbe Basis. Zwei Funnel-Raten in einer Reihe auf dieselbe Session-Zahl rechnen und diese im Fließtext darunter nennen.

Dazu höchstens drei bis vier kurze Sätze und ein dunkler Kernbefund-Callout, der einzige im Report.

### 2. Shop

Quelle `shopify.json`, Funnel-Zwischenstufen aus `ga4.json`.

- Umsatz (total_sales, net_sales), Bestellungen, AOV, Sessions und Conversion Rate, je mit Delta.
- Conversion Rate nach der Präzedenz im Katalog aus Bestellungen und Sessions. Bei einer Zuordnungslücke die zugeordnete Quote in einem hellen Callout daneben, mit Erklärung und Beleg aus `orders_by_source`.

**Micro-Conversion-Funnel** (eigener Block, nur session-basiert, Katalog gleichnamiger Abschnitt):

- Tabelle mit vier Spalten in dieser Reihenfolge: Stufe, Sessions Berichtsmonat, Sessions Vormonat, Übergangsrate Berichtsmonat.
- Stufen: "Sessions gesamt", "Produktansicht", "Add to Cart" (etablierte Kennzahlennamen, keine Umschreibungen).
- Die schwächste Übergangsrate bekommt `neg`.

Harte Regeln für den Funnel:

- Nie Ereigniszahlen als Personen ausgeben. Die Zeile Produktansicht kommt aus GA4 als Metrik `sessions` unter `eventName = view_item`, nie als `eventCount`.
- Übergangsrate = Anteil der vorherigen Stufe. Wird zusätzlich der Bezug auf alle Sessions genannt (etwa für die KPI-Kachel), den Bezug ausdrücklich dazuschreiben.
- Alle Zeilen einer Tabelle auf derselben Basis: GA4-Zeilen gegen GA4-Sessions, Shopify-Zeilen gegen Shopify-Sessions. Die jeweils andere Zahl in den Fließtext darunter.
- Keine Zeile aus der Kennzahlen-Tabelle darüber wiederholen. Umsatz und Bestellungen gehören nicht in den Funnel.
- Keine Kauf- und keine Checkout-Stufe, solange die Zuordnung die Bestellzahl nicht trifft (eine Kaufzeile mit 3 neben 10 Bestellungen weiter oben ist ein Widerspruch). Stattdessen ein Satz, warum die Stufen fehlen, einschließlich des Drawers ohne eigene URL, wenn `view_cart` fehlt.
- Gegenprobe nennen: Add-to-Cart-Zahl aus Shopify neben die aus GA4 stellen. Gleiche Größenordnung: Zahl belastbar, dieser Satz kommt in den Report. Starke Abweichung: Messproblem, kein Shop-Befund.
- Nur ein Kernbefund-Callout im Report, in der Executive Summary. Kein zweiter dunkler Callout im Shop-Kapitel.

**Abandoned Carts:** kleine Tabelle (Zeitraum, Anzahl, Warenwert) und zwei Sätze: Bedeutung der Zahl und ob sie relevant ist. Auffällige Häufungen an einem Tag als mögliche Tests nennen, mit dem Muster als Begründung und ausdrücklich als Vermutung.

**Top-Produkte:** Tabelle, Top 10 (Umsatz, Bestellungen, Bestand, Status). Steht bei einem Umsatzträger "unbekannt", ist der Pull unvollständig: nachfragen, nicht drucken (Katalog, Bestandsrisiko).

**Repeat-Rate** (Formel im Katalog, aus `customer_type`): ein Satz mit Einordnung gegen das DTC-Band, Benchmark als Fremdquelle mit Datum. Fehlt `customer_type`: Grund aus `notes`.

**Verfügbarkeit:** eigener Block, immer wenn die Warenkorb-Rate auffällig ist.

- Quote der bestellbaren Varianten.
- Produkte mit Lücken als Tabelle (Produkt, bestellbare Größen als "1 von 8").
- Ein Satz, ob Verfügbarkeit die niedrige Warenkorb-Rate erklärt oder nicht.
- Bestand 0 nie als Kaufhindernis werten; entscheidend ist `availableForSale`.
- Ein negatives Ergebnis ausschreiben; es schließt die naheliegendste Hypothese aus.

**Sortiments-Diagnosen** nach Katalog, nur mit Treffern:

- "Ware ohne Umsatz" und "Bestandsrisiko", je als kurze Tabelle, beide auf 10 Zeilen gekappt, mit Anzahl und gebundenen Stück über alle Treffer.
- Ohne Treffer ein Satz statt leerer Tabelle.
- Nach Warengruppen prüfen: verkauft ein Produkt einer Gruppe und die Geschwister nicht, ist das der wichtigste Befund des Kapitels und kommt in die Maßnahmen.

### 3. Traffic

Quelle `ga4.json`.

- Totals (Sessions, Nutzer, Umsatz), Kanal-Tabelle, Top-Landingpages mit Engagement-Rate, zwei bis drei Sätze zu den auffälligsten Verschiebungen.
- Kanal-Tabelle mit Spalte Conversion Rate (`purchases` geteilt durch `sessions` je Kanal, Formel und Mindestbasis im Katalog).
- Darunter ein Satz zum stärksten und zum schwächsten Kanal, je mit Zahl und Einordnung gegen die Kanal-Bänder des Katalogs, Benchmark als Fremdquelle mit Datum.
- Kanäle unter der Mindestbasis bleiben in der Tabelle, werden aber nicht kommentiert; dazu ein Halbsatz, dass die Rate bei wenigen Sessions zufällig ist.
- `purchases` `null` oder fehlend: Spalte und Satz entfallen.

### 4. SEO

Quellen `gsc.json` und `cwv.json`.

- GSC-Totals (Klicks, Impressionen, CTR, Position) mit Delta.
- Gewinner- und Verlierer-Queries nur, wenn Vergleichsdaten existieren (Match über den Query-String).
- Indexierung: Sitemap-Status und Auffälligkeiten der Index-Stichprobe (alles nicht Indexierte mit URL).
- Core Web Vitals je URL (LCP, INP, CLS mit Kategorie, Lab-Score).
- GSC-Daten kommen 2 bis 3 Tage verspätet. Liegen zwischen Monatsende und heute weniger als 4 Tage: Hinweis im Kapitel, dass die letzten Monatstage unvollständig sein können.

Zwei Blöcke nach Katalog-Definition, beide Top 10:

- **Striking-Distance-Queries:** Tabelle mit Query, Position, Impressionen (Einblendungen), Klicks, nach Impressionen absteigend. Darunter ein Satz zur Lesart: Suchbegriffe knapp hinter den vorderen Plätzen, bei denen wenige Positionen viele Klicks bringen.
- **CTR-Lücken:** Tabelle mit Query, Position, Impressionen, eigener CTR und Median der eigenen Queries auf vergleichbarer Position, sortiert nach rechnerischer Klick-Lücke. Darunter ein Satz, dass der Vergleich nur innerhalb des eigenen Datensatzes läuft, damit niemand eine Marktzahl darin liest.

Zu wenige Queries über der Mindest-Impressionsgrenze für eine Diagnose: Block mit einem Satz weglassen.

### 5. GEO

Quelle `geo.json`.

- Je Gruppe (`brand`/`category`) und Plattform: wie oft die Brand erwähnt und die Domain zitiert wurde.
- Nicht prüfbare Zeilen separat ausweisen.
- Crawler-Matrix mit den blockierten Crawlern beim Namen.
- llms.txt-Status.
- **Citation Rate** je Gruppe (Formel im Katalog: zitierte Zeilen geteilt durch prüfbare Zeilen) als Zahl, eingeordnet nach den Katalog-Bändern (unter 15 % deutliche Lücke, 25 bis 40 % wettbewerbsfähig, über 40 % stark), Benchmark als Fremdquelle mit Datum.
- **Share of Voice:** die fünf häufigsten fremden Zitat-Domains derselben Queries aus `other_citations`, kurze Tabelle mit Domain und Anzahl der Zeilen, die eigene Domain in derselben Rangliste, dazu ein Satz, wer statt der Brand zitiert wird. Fehlt `other_citations` oder ist es überall leer: Block mit einem Satz weglassen.
- Veränderung zum Vormonat nur, wenn der Vormonats-Ordner eine `geo.json` hat, und nur über Zeilen, die in beiden Monaten prüfbar waren **und** mit derselben Methode erhoben wurden (`method`-Feld: gleiche Plattform und gleiche Methode).
- Hat eine Plattform die Methode gewechselt (etwa von `browser` auf `api`): ein Satz im Kapitel, kein stiller Vergleich.
- `geo_method` in der Config auf `off`: Kapitel besteht aus einem Satz, dass GEO bewusst abgeschaltet ist und über `/ptai-ecom:setup` aktiviert werden kann.
- Harte Regel: GEO stellt während eines Report- oder Puls-Laufs nie Fragen und öffnet nichts unangekündigt. Alle Entscheidungen (api/browser/off) stehen in der Config (`geo_method`); fehlende Voraussetzungen werden zu `null`-Zeilen oder "nicht verfügbar (Grund)".

### 6. Maßnahmen

- 3 bis 7 Punkte, priorisiert (1 zuerst).
- Jede Maßnahme mit drei Teilen: was tun; Begründung aus den Daten dieses Reports mit der Zahl; Impact hoch/mittel/niedrig mit einem Satz Begründung.
- Umsatz-Prognosen nur, wenn sie sich aus den Snapshot-Zahlen herleiten lassen, mit der Rechnung daneben.
- Naheliegende Kandidaten: Treffer aus Kapitel 4 und 2, also Striking-Distance-Queries (wenige Positionen bis in die Top 3, Nachfrage belegt) und Sortiments-Diagnosen (gebundenes Kapital im Lager oder ausverkaufter Umsatzträger).
- Diese Kandidaten sind kein Pflichtprogramm; Wichtigeres in diesem Monat steht oben.

## Schluss

Am Ende des Markdown-Reports eine Trennlinie `---`, darunter unverändert die Ausgabe von

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.closing report-md .
```

im Workspace aufgerufen.

- Die Ausgabe enthält eine Kontaktzeile je gesetztem und gültigem Wert (Unternehmen, Ansprechpartner, E-Mail, Termin) und immer die Herkunftszeile, ohne weiteren Satz.
- Nicht umformulieren, nicht ergänzen, keine Kontaktdaten von Hand.
- Der Markdown-Report endet immer so, auch wenn `PTAI_CLOSING_FILE` gesetzt ist.
- Das HTML bekommt seinen Schluss erst nach dem Speichern (PDF rendern, Schritt 5), nie den Markdown-Text.

## PDF rendern

1. Template lesen: `${CLAUDE_PLUGIN_ROOT}/skills/report/templates/report.html`.
2. Platzhalter ersetzen, Pfade immer absolut (headless Chrome löst keine Plugin-relativen Pfade auf):
   - `__CSS_PATH__`: absoluter Pfad zu `${CLAUDE_PLUGIN_ROOT}/assets/brand/report.css`. Immer die Plugin-CSS verwenden: die Fonts liegen relativ dazu (`fonts/...`), eine kopierte CSS ohne `fonts/`-Ordner rendert ohne Fonts.
   - `__LOGO_PATH__`: absoluter Pfad zu `${CLAUDE_PLUGIN_ROOT}/assets/brand/logo.svg`.
   - `__BRAND__`, `__PERIOD_LABEL__` (z. B. "Juli 2026"), `__GENERATED_DATE__` (z. B. "10.08.2026").
   - `__CLOSING__` unverändert lassen, ebenso die Markierungen `CLOSING:start` und `CLOSING:end` um das Schluss-Panel. Den Schluss setzt Schritt 5 ein; nichts davon von Hand schreiben.
3. Die sechs `SECTION:`-Kommentare durch das Kapitel-HTML ersetzen, nur aus den Blöcken im BAUKASTEN-Kommentar des Templates (KPI-Zeile, Hero-KPI, Tabelle, Kernbefund dunkel, Hinweis hell, Eyebrow, Umbruch-Helfer). Keine eigenen Styles, keine neuen Klassen, damit jeder Monat gleich aussieht. Zahlenzellen und Zahlen-Spaltenköpfe bekommen `class="num"`.
4. Den BAUKASTEN-Kommentar aus dem gefüllten HTML entfernen (Bauanleitung, kein Inhalt). Dann als `reporting/reports/YYYY-MM-monthly.html` speichern; die Datei bleibt für Re-Render und Fehlersuche liegen.
5. Den Schluss einsetzen, im Workspace:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.closing apply reporting/reports/YYYY-MM-monthly.html .
   ```

   - Das Script schreibt die Datei um und meldet in einer Zeile, welchen Schluss es verwendet hat.
   - `PTAI_CLOSING_FILE` gesetzt und lesbar: die Schlussseite des Betreibers ersetzt das Schluss-Panel zwischen den Markierungen (dieselbe Seite wie im Audit und in `audit-light`); die Markierungen bleiben.
   - Sonst wird `__CLOSING__` zum neutralen Schluss: eine Kontaktzeile je gesetztem und gültigem Wert des Betreibers und immer die Herkunftszeile, ohne weiteren Satz.
   - Datei fehlt, ist nicht lesbar oder leer: zusätzlich ein Hinweis auf stderr.
   - Ein zweiter Aufruf auf derselben Datei ist unschädlich. Mit Schlussseite ersetzt er den Inhalt zwischen den Markierungen, auch einen früheren neutralen Schluss oder eine ältere Seite. Ohne Schlussseite füllt er `__CLOSING__`, solange der Platzhalter existiert; ist er schon ersetzt, bleibt die Datei unverändert, und die Zeile meldet, dass nur die Vorlage den neutralen Schluss neu erzeugt.
   - Enthält die Schlussseite eine der Markierungen oder `__CLOSING__`, bricht das Script mit Fehlermeldung ab und lässt die Datei unverändert.
6. Rendern:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/report/scripts/render_pdf.sh" \
     "reporting/reports/YYYY-MM-monthly.html" \
     "reporting/reports/YYYY-MM-monthly.pdf"
   ```

   Das Script findet den Browser selbst, rendert A4 ohne Browser-Kopfzeilen und prüft, dass das PDF existiert und größer als 20 KB ist (grober Beleg für eingebettete Fonts).
7. PDF sichtprüfen (öffnen oder lesen): Archivo Black in den Überschriften, Logo oben rechts, Tabellen und KPI-Kacheln sauber, Schlussseite am Ende.

**Deliverable:** Ob das Kunden-PDF zusätzlich abgelegt wird (etwa im Account-Ordner eines Drive), regeln der Nutzer oder die Workspace-Regeln des Kunden-Repos, nicht dieses Plugin. Der Report meldet nur die Pfade.

## Ton und Sprach-Hygiene

Diese Regeln gelten für den Monats-Report. Leser ist eine Geschäftsführung, weder Analyst noch Laie.

**Anrede**

- Leser mit "ihr" und "euch" ansprechen, nie "du", auch nicht in festen Labels; das Portal spricht mehrere Leser mit "ihr" an.
- Handlungen des Betreibers in der ich-Form, nie "wir".
- Gilt ebenso im Audit (`ptai-ecom:audit`, Einstieg).

**Kennzahlennamen**

- Etablierte Namen beibehalten, nicht übersetzen: Conversion Rate, Sessions, Add-to-Cart-Rate, Produktansichtsrate, Engagement-Rate, AOV, Micro-Conversion-Funnel.
- Beim ersten Vorkommen im Kapitel ein Nebensatz, was die Kennzahl misst.
- Nie einen Metriknamen erfinden. Verboten sind Umschreibungen wie "Wie weit ein Besuch kommt", "Im Shop angekommen", "Davon mit etwas im Warenkorb", "Warenkorb-Zulage".
- Ohne etablierten Namen die Zeile mit einem vollständigen, sachlichen Substantiv benennen ("Abandoned Carts"), nie mit einem Satzfragment.

**Prosa**

- Kennzahlen beschreiben, nicht dramatisieren: "Die Add-to-Cart-Rate liegt bei 2,6 %", nicht "der Shop verliert die Leute zweimal, bevor es um Geld geht".
- Sätze, die ohne Zahl Dramatik behaupten, streichen.
- Jede Aussage hängt an einer Zahl aus den Snapshots oder ist als Einschätzung markiert.

**Tabellen**

- Funnel-Tabellen: Stufe, Zahl je Zeitraum, Übergangsrate zur vorherigen Stufe, in dieser Reihenfolge.
- Keine Zeile, die eine Kennzahl aus einer Tabelle weiter oben wiederholt. Stehen erste und letzte Zeile einer Funnel-Tabelle schon in der Kennzahlen-Tabelle, die Funnel-Tabelle weglassen.
- Erklärungsbedürftige Tabellen bekommen darunter einen Satz zur Lesart.
- Spaltenreihenfolge in allen Vergleichstabellen gleich, auch in Query- und Produkttabellen: Berichtsmonat, Vormonat, Delta.

## Fehlerbilder

| Fall | Vorgehen |
|---|---|
| Kein Browser | `render_pdf.sh` bricht mit Meldung ab. Der Markdown-Report ist fertig und bleibt das Deliverable; den PDF-Schritt als offen melden (Headless Shell von Playwright oder Chrome installieren, Script erneut ausführen). |
| PDF unter 20 KB | Fast immer sind `__CSS_PATH__` oder `__LOGO_PATH__` nicht durch absolute Pfade ersetzt oder die CSS zeigt auf eine Kopie ohne `fonts/`. Pfade prüfen, neu rendern. |
| Einzelne Quelle gescheitert | Kapitel mit "nicht verfügbar (Grund)" füllen, weiterlaufen. Gründe in den Fehlerbildern der Pull-Skill. |
| Alle Quellen gescheitert | Kein Report. Abbrechen, Gründe je Quelle auflisten, auf `/ptai-ecom:setup` verweisen. |
| Berichtsmonat liegt weiter zurück (Nachzügler-Lauf) | Pulls mit expliziten Datumsgrenzen aufrufen. Die Vormonats-Suche bezieht sich auf den Monat vor dem gewünschten Berichtsmonat, nicht auf heute. |
