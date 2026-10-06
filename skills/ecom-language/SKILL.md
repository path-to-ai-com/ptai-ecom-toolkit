---
name: ecom-language
description: Fachsprache für jedes E-Commerce-Dokument mit Zahlen und Aufbau eines Befunds. Enthält die fünf Elemente eines Befunds (Zustand, Einordnung, Ursache, Folge, Empfehlung), die Regel "Fachbegriff verwenden und beim ersten Auftreten erklären", das Vokabular mit Erklärsätzen und die Liste der Laienwörter, die in keinem Kundendokument stehen dürfen. ptai-ecom:audit, ptai-ecom:report und die Analyse-Agents des Audits laden sie vor dem ersten Befund; sie gilt ebenso für Angebote und Analysen mit E-Commerce-Zahlen. Verwenden, sobald ein Befund, eine Kennzahl oder eine Maßnahme formuliert wird. Nicht verwenden für Mails und Nachrichten und nicht für den Aufbau eines Reports insgesamt.
---

# ecom-language: Fachsprache und Aufbau eines Befunds

Leser sind Geschäftsführer oder E-Commerce-Verantwortliche. Sie kennen Geschäft und Tools; umschriebene Fachbegriffe machen einen Report für sie unbrauchbar.

## Grundregel

1. Den Fachbegriff verwenden.
2. Beim ersten Auftreten im Dokument in einem Halbsatz erklären, danach nicht mehr.
3. Kein Laienwort erfinden, nicht umschreiben, nicht weglassen.

Beispiel für die Bauform:

> Im Produkt-Schema, den strukturierten Daten, aus denen Google den Preis für
> Shopping-Einträge liest, ist das Feld `priceValidUntil` bei jedem geprüften Produkt exakt auf
> das Abrufdatum gesetzt.

## Die fünf Elemente eines Befunds

Quelle: IIA Audit Report Writing Toolkit, Standardform für Prüfberichte. Jeder Befund enthält alle fünf.

| Element | Was es beantwortet | Woran man merkt, dass es fehlt |
|---|---|---|
| **Zustand** | Was ist der Fall, mit Zahl und Zeitraum | Der Titel nennt keine Zahl |
| **Einordnung** | Woran gemessen, was wäre normal | "4,7 Prozent" steht da, und niemand weiss, ob das gut ist |
| **Ursache** | Warum ist es so | Die Empfehlung wirkt geraten |
| **Folge** | Was heisst das geschäftlich | Der Leser fragt "und?" |
| **Empfehlung** | Was ist konkret zu tun, wo | Es bleibt bei "sollte optimiert werden" |

Die Einordnung fehlt am häufigsten und ist am wichtigsten. Drei Formen, in dieser Rangfolge:

1. **Gegen eine Benchmark**, mit Quelle und Abrufdatum. Belegte Bänder: `${CLAUDE_PLUGIN_ROOT}/reference/metrics.md`. Es sind Fremdquellen; sie ordnen ein, sie bewerten nicht.
2. **Gegen den eigenen Datensatz**, wenn keine Benchmark existiert: Nachbarstufe im Funnel, Vorjahresmonat, übriges Sortiment.
3. **Mit der Angabe, dass keine existiert**, zum Beispiel: "Für die Add-to-Cart-Rate gibt es keine belastbare Branchen-Benchmark, deshalb der interne Vergleich." Das gilt als vollständige Einordnung; nie eine Schwelle erfinden.

## Befundtitel

- Der Titel ist die vollständige Aussage mit Zahl.
- Kein Thema, kein Halbsatz.

| Nicht | Sondern |
|---|---|
| Zwischen Produktansicht und Warenkorb-Zugabe bricht der Kaufweg am stärksten ein | Nur 4,7 Prozent der Produktansichten führen zu einer Warenkorb-Zugabe |
| Mehrere Skripte fremder Anbieter fehlen in der Datenschutzerklärung | Acht von zwölf eingebundenen Drittanbieter-Diensten fehlen in der Datenschutzerklärung |
| Auf allen geprüften Seiten läuft ein Werkzeug für Bewertungen | Trustpilot blendet auf allen geprüften Produktseiten Bewertungen ein |
| Alle fünf Schritte des Kaufwegs werden gemessen, keiner steht auf null | Alle fünf Funnel-Stufen senden Events, die Messkette ist vollständig |

## Verbotene Laienwörter in Kundendokumenten

Jedes Vorkommen ist ein Fehler. Die linke Spalte enthält Formulierungen aus früheren Dokumenten.

| Laienwort | Was stattdessen dasteht |
|---|---|
| ein Werkzeug, Testwerkzeug | der Produktname (Klaviyo, Doofinder, Trustpilot), sonst die Kategorie: A/B-Testing-Tool, E-Mail-Marketing-Tool |
| Menschen, echte Menschen | Sessions, Unique Visitors, Nutzer, je nachdem was gezählt wurde |
| mehrere, einige, viele, praktisch alle | die Zahl: acht von zwölf, 284 von 333 |
| Skripte fremder Anbieter | Drittanbieter-Dienste, Third-Party-Scripts |
| Trichter | Funnel |
| Ladezeit-Werte | Core Web Vitals, oder die einzelne Metrik: LCP, INP, CLS |
| Suchmaschinen-Vorschautext | Meta-Description |
| Haupt-Adresse einer Seite | Canonical-URL |
| KI-Suche allgemein | die Plattform: ChatGPT, Perplexity, Google AI Overviews |
| Besuche, die bis zur Kasse kamen | Sessions mit `begin_checkout`, oder Checkout-Einstiege |

Ebenso verboten sind Begriffe der Pipeline:

- Nie `crawl.json`, `jq`, DataForSEO, run-id, Snapshot, Pull.
- Der Beleg nennt die Quelle in Kundensprache, zum Beispiel "Quelltext der Startseite", "GA4-Funnel, Sessions je Ereignis", "Crawl vom 08.09.2026".

## Vokabular

Bei Bedarf nachschlagen. Spalte 2 ist der Erklärsatz für das erste Auftreten.

### Traffic und Messung

| Begriff | Erklärsatz beim ersten Auftreten |
|---|---|
| Session | eine zusammenhängende Besuchsfolge eines Nutzers, die nach 30 Minuten Inaktivität endet |
| Unique Visitor | ein einzelner Besucher, unabhängig davon, wie oft er wiederkommt |
| Bounce Rate | der Anteil der Sessions mit nur einer Seitenansicht und ohne Interaktion |
| Attribution | die Zuordnung eines Kaufs zu dem Kanal, über den der Nutzer kam |
| Consent Layer | das Einwilligungsfenster, das vor dem Laden nicht notwendiger Dienste erscheint |
| Server-side Tracking | die Messung über den eigenen Server statt über ein Skript im Browser |

### Conversion

| Begriff | Erklärsatz beim ersten Auftreten |
|---|---|
| Conversion Rate | der Anteil der Sessions, die zu einer Bestellung führen |
| Conversion Funnel | die Stufenfolge von der Produktansicht bis zum Kauf |
| Add-to-Cart-Rate | der Anteil der Sessions mit Produktansicht, in denen ein Artikel in den Warenkorb gelegt wird |
| Cart Abandonment Rate | der Anteil der gefüllten Warenkörbe, die nicht zur Bestellung führen |
| AOV, Bestellwert | der durchschnittliche Umsatz je Bestellung |
| Repeat-Rate | der Anteil der Bestellungen von Kunden, die schon einmal gekauft haben |
| Viewport, above the fold | der Bereich, der ohne Scrollen sichtbar ist |
| PDP, PLP | Produktdetailseite und Produktlistenseite, also Kategorieseite |

### Sichtbarkeit

| Begriff | Erklärsatz beim ersten Auftreten |
|---|---|
| SERP | die Trefferliste einer Suchmaschine |
| Impression Share | der Anteil der möglichen Einblendungen, den eine Anzeige tatsächlich bekommt |
| Share of Voice | der Anteil an der Gesamtsichtbarkeit einer Wettbewerbsgruppe |
| Canonical-Tag | das Element, das Google mitteilt, welche von mehreren ähnlichen Seiten die Haupt-URL ist |
| Hreflang | die Auszeichnung, die Google sagt, welche Sprachversion für welches Land gilt |
| Orphan Page | eine Seite, auf die kein interner Link zeigt, die also nur über die Sitemap auffindbar ist |
| Klicktiefe | die Zahl der Klicks von der Startseite bis zu einer Seite |
| Crawl-Budget | die Zahl der Seiten, die eine Suchmaschine je Durchgang abruft |
| Structured Data, Schema | ein maschinenlesbares Datenformat im Quelltext, aus dem Google Preis, Verfügbarkeit und Bewertungen liest |
| GEO | die Sichtbarkeit in den ausformulierten Antworten von ChatGPT, Perplexity und Google AI, nicht in der klassischen Trefferliste |

### Technik

| Begriff | Erklärsatz beim ersten Auftreten |
|---|---|
| Core Web Vitals | Googles drei Messwerte für Ladeerlebnis: LCP, INP und CLS |
| LCP | wie lange es dauert, bis der grösste sichtbare Inhalt geladen ist |
| INP | wie lange die Seite braucht, bis sie auf eine Eingabe reagiert |
| CLS | wie stark der Inhalt beim Laden verspringt |
| Third-Party-Script | ein Skript, das der Shop von einem fremden Server nachlädt |

## Maßnahme mit Kennzahl

Jede Maßnahme hat immer diese vier Angaben:

| Angabe | Beispiel |
|---|---|
| Kennzahl | Add-to-Cart-Rate, mobil |
| Ausgangswert | 4,7 Prozent (alle Geräte, zwölf Monate bis zum Stichtag) |
| Prüfregel | Button ohne Scrollen sichtbar bei 390 x 844 px, Consent-Layer offen |
| Messbar ab | vier Wochen nach Livegang, gegen denselben Vorjahreszeitraum |

"Messbar ab" ist Pflicht, weil sonst nach zwei Wochen gegen Rauschen gemessen und die Maßnahme fälschlich als wirkungslos bewertet wird.

## Prüfen

Vor der Freigabe, in dieser Reihenfolge:

1. Jeder Fachbegriff beim ersten Auftreten erklärt, nicht später?
2. Kein Laienwort aus der Tabelle? Automatisch mit `python3 -m audit.qa` aus `${CLAUDE_PLUGIN_ROOT}/scripts`, sonst per Suche.
3. Jeder Befund mit allen fünf Elementen, vor allem der Einordnung?
4. Jeder Titel mit seiner Zahl?
5. Jeder Beleg mit Quelle in Kundensprache statt Dateiname aus der Pipeline?

## Grenzen

Regelt Vokabular und Aufbau eines Befunds. Nicht geregelt: Aufbau eines Reports insgesamt, Ton in Mails und Posts, Titel und Einstieg eines Reports.
