---
name: lens-purchase-path
description: Prüft die Kaufstrecke eines Shops von außen, von der Produktseite über den Warenkorb bis zur Zahlungsauswahl, ohne Zugänge und ohne eine Bestellung auszulösen. Prüft Kaufbutton, Verfügbarkeit, Lieferzeit, Versandkosten vor der Kasse, Gastbestellung, Zahlarten, Schrittzahl und Bedienbarkeit auf dem Handy. Einsetzen als Linse L3 in ptai-ecom:audit-light, im großen Audit als Ergänzung zur GA4-gestützten Funnel-Analyse oder wenn der Nutzer wissen will, woran ein Kauf in einem fremden Shop scheitert. Liefert belegte Befunde mit Deep-Link, keine Vermutungen über Conversion-Zahlen.
---

# lens-purchase-path: der Weg zum Kauf, von außen

- Die Kaufstrecke ist der größte Hebel im E-Commerce und von außen am besten einsehbar.
- Jeder Prüfpunkt geht ohne Zugang und ohne ausgelöste Bestellung.

## Methode aus `marketing-skills:cro`

Übernommen: der Sieben-Punkte-Rahmen

1. Nutzenversprechen
2. Headline
3. CTA-Hierarchie
4. visuelle Hierarchie
5. Vertrauenssignale
6. Einwandbehandlung
7. Reibungspunkte

Nicht übernommen:

- seitentypische Frameworks für Homepage, Pricing, Feature und Blog (ein Shop hat PLP, PDP, Warenkorb und Kasse, keine Pricing-Page)
- Test-Ideen und A/B-Vorschläge (von außen weder vorschlagbar noch messbar)

## Grenzen der Linse (gehören in den Report)

- **Keine Abbruchquoten.** Ausstiege stehen in Analytics, nicht auf der Seite. Nie "hier springen 60 Prozent ab".
- **Keine ausgelöste Bestellung.** Prüfung bis zur Zahlungsauswahl, nie weiter. Ohne Geschäftsbeziehung zum Shop wird kein Testwarenkorb angelegt; dann reicht die Prüfung nur so weit, wie die Seiten ohne Warenkorb zeigen.
- **Browser-Elemente brauchen den Screenshot.** Sticky-Buttons, Varianten-Auswahl und Versandrechner fehlen oft im HTML. Ohne Screenshot-Beleg: weglassen oder als Prüfauftrag mit `confidence: "low"`.

## Prüfpunkte

### 1. Kaufbutton

Auf der Produktseite, Desktop **und** Mobil.

- Ohne Scrollen erreichbar? Häufigster Fund auf dem Handy: Button unter Galerie, Varianten und Trust-Leiste.
- Eindeutig Hauptaktion, oder Konkurrenz durch gleich laute Buttons ("Merkzettel", "Vergleichen", Chat-Blase)?
- Beschriftung benennt die Aktion ("In den Warenkorb") oder ist vage ("Weiter", "Auswählen")?

Schweregrad `crit`: Kaufbutton auf dem Handy ohne Scrollen nicht sichtbar oder nicht als Hauptaktion erkennbar. Beleg: Screenshot plus URL.

### 2. Verfügbarkeit und Lieferzeit

- Lieferbarkeit auf der Produktseite angegeben?
- Lieferzeit angegeben, präzise ("in 1 bis 3 Werktagen") oder Floskel ("schnelle Lieferung")?
- Bei Varianten: Angabe ändert sich mit der Auswahl oder gilt pauschal?

| Mangel | Schweregrad |
|---|---|
| Lieferzeit fehlt | `warn` |
| Verfügbarkeitsangabe fehlt bei erkennbarer Lagerhaltung | `crit` (der Kunde erfährt erst nach der Bestellung, dass er wartet) |

### 3. Versandkosten vor der Kasse

Wichtigster und am häufigsten verletzter Punkt.

- Versandkosten auf der Produktseite oder spätestens im Warenkorb, also **vor** der Dateneingabe?
- Versandkostenfreie Schwelle vorhanden und dort genannt, wo sie wirkt?
- Hinweis mit Betrag oder nur Link auf eine Versandseite?

Schweregrad `crit`: Versandkosten erst nach Eingabe der Adresse sichtbar. Das ist auch rechtlich heikel: hier als Befund, bei `lens-trust` als Prüfauftrag, nie als Rechtsurteil.

### 4. Warenkorb

- Nach dem Hinzufügen Rückweg zum Weiterkaufen, oder Sackgasse?
- Menge änderbar, Position entfernbar?
- Zwischensumme, Versand, Gesamtsumme getrennt?
- Hinweis auf Zahlarten schon hier?

### 5. Kasse

Ohne Bestellung, nur bis zur Zahlungsauswahl. Ist kein Testwarenkorb erlaubt, aus den öffentlichen Seiten ableiten.

- **Gastbestellung möglich?** Kontozwang ist einer der härtesten Abbruchgründe. `crit`, wenn ein Konto Pflicht ist.
- Schritte bis zur Zahlungsauswahl: einer ist gut, drei sind normal, fünf sind ein Befund.
- Zahl der Pflichtfelder? Adresse doppelt abgefragt (Liefer- und Rechnungsadresse ohne "gleich wie")?
- Position im Ablauf erkennbar?

### 6. Zahlarten

- Welche, und wo genannt: nur im Footer oder auch am Kaufpunkt?
- Fehlt eine für die Zielgruppe typische (Rechnung im Handwerk, PayPal und Klarna im Endkundengeschäft, SEPA bei Abos)?
- Zahlungsanbieter-Logos als Vertrauenssignal genutzt oder nur als Fußnote?

### 7. Handy

Der Shop wird mehrheitlich am Handy angesehen; der Screenshot liegt vor.

- Buttons und Formularfelder groß genug zum Treffen?
- Horizontales Scrollen nötig?
- Verdeckt Banner, Cookie-Dialog oder Chat-Blase den Kaufbutton? **Diesen Befund hart nachprüfen**, nicht nur aus dem Screenshot ablesen; eine Einblendung, die beim Screenshot zufällig oben lag, belegt keine dauerhafte Verdeckung.

## Ausgabe

Zwei Dateien nach `<run>/findings/`:

**`L3-purchase-path.json`**: Array, je Befund:

| Feld | Inhalt |
|---|---|
| `severity` | crit\|warn\|ok |
| `title` | Titel |
| `detail` | Sachverhalt mit Beleg |
| `recommendation` | nächster Schritt |
| `evidence` | URL, wörtliches Zitat oder benanntes Element |
| `url` | der eine klickbare Deep-Link |
| `impact` | Geschäftswirkung in einem Satz |
| `effort` | 0,5 Tag / 1 bis 2 Tage / 1 bis 2 Wochen |
| `confidence` | Sicherheit |
| `lens` | `"purchase-path"` |

**`L3-purchase-path.coverage.json`**: `{"checked": [...], "not_checkable": [{"what", "reason"}]}`.

- Jeder der sieben Punkte steht in genau einer der beiden Listen.
- Nicht prüfbar, weil die Kasse einen Login verlangt: in `not_checkable` mit diesem Grund, kein erfundener Befund.

**Ein bis zwei `ok`-Befunde sind Pflicht.** Der Leser soll sehen, was gut läuft; eine saubere Kaufstrecke wird als solche benannt.
