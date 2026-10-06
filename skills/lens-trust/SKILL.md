---
name: lens-trust
description: Prüft Vertrauen und Pflichtangaben eines Shops von außen: Impressum, Widerrufsbelehrung, AGB, Datenschutzerklärung, Preisangaben samt Grundpreis, Versandkostenhinweis, Bewertungen am Kaufpunkt und Prüfsiegel. Stellt fest, was vorhanden und auffindbar ist, und bewertet ausdrücklich nicht juristisch. Einsetzen als Linse L4 in ptai-ecom:audit-light oder wenn der Nutzer wissen will, ob ein Shop die Angaben zeigt, die ein deutscher Käufer erwartet. Liefert belegte Befunde mit Deep-Link.
---

# lens-trust: Pflichtangaben und Vertrauen, von außen

Mängel bei Pflichtangaben sind für Händler riskant und meist mit wenig Aufwand behebbar (Beispiel: fehlendes Impressum).

## Grundregel: feststellen, nicht urteilen

| Erlaubt | Verboten |
|---|---|
| "vorhanden" | "rechtswidrig" |
| "nicht auffindbar" | "abmahnfähig" |
| "unvollständig gegenüber der üblichen Praxis" | "verstößt gegen" |

- Der Report ist kein Rechtsrat. Ein falsches Rechtsurteil im Anschreiben an einen kalten Lead wiegt schwerer als ein fehlender Befund.
- Richtig: *"Auf der Produktseite ist kein Grundpreis je Kilogramm ausgewiesen. Bei Waren nach Gewicht ist das üblich und sollte anwaltlich geprüft werden."*
- Falsch: *"Verstoß gegen die Preisangabenverordnung."*

## Grenzen der Linse

- **Keine inhaltliche Prüfung von Rechtstexten.** Ob eine Widerrufsbelehrung inhaltlich ausreicht, entscheidet ein Anwalt. Geprüft wird: existiert, erreichbar, nennt die üblichen Bestandteile.
- **Hinter der Kasse ungeprüft**, solange kein Testkauf stattfindet. Pflichtangaben im Bestellprozess (Button-Beschriftung, Bestellübersicht) sind dann `not_checkable` mit diesem Grund.
- **Siegel-Echtheit nur bei verlinktem Siegel prüfbar.** Ein Bild ohne Link ist ein Befund, kein Betrugsvorwurf.

## Prüfpunkte

### 1. Impressum

- Aus dem Footer jeder Seite mit höchstens einem Klick erreichbar?
- Enthält: Firmenname mit Rechtsform, Anschrift, vertretungsberechtigte Person, Kontaktmöglichkeit; bei eingetragener Gesellschaft Register und Nummer?
- Firmenname deckungsgleich mit dem Auftritt im Shop? Gehört die Marke laut Impressum einer fremd klingenden GmbH: kein Mangel, aber ein Gesprächspunkt.

| Mangel | Schweregrad |
|---|---|
| kein Impressum auffindbar | `crit` |
| Einzelangaben fehlen | `warn` |

### 2. Widerruf, AGB, Datenschutz

Je Dokument: aus dem Footer erreichbar, eigene URL, ohne Login lesbar.

- **Widerrufsbelehrung:** vorhanden? Frist genannt? Muster-Formular oder Hinweis darauf?
- **AGB:** vorhanden und datiert?
- **Datenschutzerklärung:** vorhanden? Nennt sie die eingesetzten Dienste?
  - Gegencheck: der Crawl-Snapshot listet die eingebundenen Fremdskripte. Lädt der Shop etwa Google Analytics, ohne es zu nennen, ist das ein Befund.
  - Stärkster Fund dieser Gruppe, weil belegbar: Skript-Host aus `crawl.json`, Volltext der Erklärung, keine Erwähnung.

### 3. Cookie-Dialog

- Erscheint er, bevor nicht notwendige Dienste laden?
- "Ablehnen" gleichwertig sichtbar wie "Akzeptieren", oder erst auf einer zweiten Ebene?
- Laden Tracking-Skripte vor der Einwilligung? Im Crawl sichtbar, wenn ein Skript-Host ohne Interaktion auftaucht.

**Diesen Befund hart nachprüfen.** Aus Screenshots abgeleitete Cookie-Befunde können falsch sein. Liegt nur das Bild vor, nicht der Ladevorgang: Prüfauftrag mit `confidence: "low"`.

### 4. Preisangaben

- Bei jedem Preis: Mehrwertsteuer enthalten, Versand zusätzlich?
- **Grundpreis:** bei Waren nach Gewicht, Volumen, Länge oder Stückzahl je Einheit ausgewiesen (je Kilogramm, je Liter, je 100 Stück)? Fehlt häufig, billig zu beheben.
- Streichpreise: Bezug erkennbar?

### 5. Versandkosten

- Eigene Seite mit Kosten und Lieferzeiten, aus dem Footer erreichbar?
- Hinweis auch am Preis, nicht nur in der Fußzeile?
- Überschneidung mit `lens-purchase-path` Punkt 3 ist gewollt: dort Conversion-Fund, hier Pflichtangaben-Fund. **Beim Konsolidieren wird daraus ein Befund**, der stärkere Beleg zählt.

### 6. Bewertungen am Kaufpunkt

- Bewertungen auf der Produktseite oder nur auf einer Unterseite?
- Zahl der Bewertungen genannt, oder nur Sterne?
- Herkunft und Prüfung angegeben?
- Durchschnitt für Suchmaschinen lesbar? Gegencheck mit dem Schema-Befund von L1: Sterne im Bild ohne `aggregateRating` in den strukturierten Daten ist ein häufiger, gut belegbarer Fund.

**Ohne Screenshot kein Absenz-Befund.** Review-Widgets rendern fast immer erst im Browser.

### 7. Siegel und Mitgliedschaften

- Welche gezeigt (Trusted Shops, Käufersiegel, Zahlungsanbieter, eigene Garantien)?
- Verlinkt und beim Aussteller nachprüfbar? Nicht verlinktes Siegel = `warn`, da es nur prüfbar wirkt.
- Am Kaufpunkt oder nur im Footer?

### 8. Kontaktweg

- Telefonnummer, Mailadresse oder Formular ohne Suchen auffindbar?
- Angaben zu Erreichbarkeit oder Antwortzeit?

## Ausgabe

Zwei Dateien nach `<run>/findings/`:

| Datei | Inhalt |
|---|---|
| `L4-trust.json` | Array mit denselben Feldern wie die übrigen Linsen: `severity`, `title`, `detail`, `recommendation`, `evidence`, `url`, `impact`, `effort`, `confidence`, `lens: "trust"` |
| `L4-trust.coverage.json` | jeder der acht Punkte in `checked` oder in `not_checkable` mit Grund |

**Pflicht im Report, sobald diese Linse einen Mangel meldet:**

1. Hinweis, dass es eine Feststellung und keine Rechtsprüfung ist.
2. Empfehlung, die betroffenen Punkte anwaltlich prüfen zu lassen.

Beides in `recommendation`, nicht in eine Fußnote.
