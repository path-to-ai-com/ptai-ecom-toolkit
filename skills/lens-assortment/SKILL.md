---
name: lens-assortment
description: Prüft Sortiment und Produktdaten eines Shops von außen: Filter und Sortierung auf der Kategorieseite, Varianten, Produkttexte, Bildanzahl und Bildqualität, Cross-Selling, Umgang mit ausverkauften Artikeln. Einsetzen als Linse L5 in ptai-ecom:audit-light oder wenn der Nutzer wissen will, ob ein Shop sein Sortiment auffindbar und kaufbar macht. Übernimmt den Produktseiten-Teil aus claude-seo:seo-ecommerce, ohne dessen kostenpflichtige Marktplatz-Abfragen. Liefert belegte Befunde mit Deep-Link.
---

# lens-assortment: Sortiment und Produktdaten

Prüft, ob der Kunde zum gewünschten Produkt findet und dort genug Information für die Kaufentscheidung bekommt. Liegt zwischen "der Shop wird gefunden" und "der Kauf klappt".

## Herkunft aus `claude-seo:seo-ecommerce`

| Abschnitt | Inhalt | Übernommen |
|---|---|---|
| 1 | Produktseiten-Analyse ohne DataForSEO: Title, Meta-Description, Überschriften-Struktur, Bilder, interne Verlinkung, Contentqualität | ja |
| 2 | Google Shopping | **nein**, braucht die kostenpflichtige Merchant-API |
| 3 | Amazon | **nein**, braucht die kostenpflichtige Merchant-API |

Werden Shopping-Fragen gebraucht, deckt sie `pull-dfs-shopping` ab; dann steht die Antwort als Snapshot im Lauf, nicht als Vermutung im Befund.

## Grenzen der Linse

- **Keine Aussage über Absatz.** Verkaufszahlen stehen in Shopify, nicht im Shop.
  - Verboten: "Bestseller", "umsatzstärkste Seite".
  - Erlaubt: "prominenteste laut Navigation", mit Beleg, wo verlinkt.
- **Keine vollständige Katalogprüfung.** Geprüft werden die Seitentypen des Laufs plus Stichproben, nicht 3.000 Produkte. Befunde über den ganzen Katalog brauchen Zahlen aus dem Crawl-Snapshot.
- **Galeriebilder zeigt auch der Screenshot nur teilweise.** Nie "nur ein Bild" behaupten, wenn nur die Erstansicht vorlag.

## Prüfpunkte

### 1. Kategorieseite

- **Filter** vorhanden, und passend zu dem, wonach dieser Markt sucht? (Modeshop ohne Größenfilter, Werkzeugshop ohne Filter nach Anwendung: gleicher Fund in zwei Märkten.)
- Zahl der Filter: drei reichen oft nicht für ein Sortiment ab einigen hundert Artikeln.
- **Sortierung** vorhanden und sinnvoll vorbelegt?
- Produkte pro Ansicht, Weg zu weiteren (Paginierung, Nachladen, "Mehr anzeigen")?
- Eigener Text auf der Kategorieseite, der den Inhalt erklärt? Beleg: Wortzahl aus dem Crawl.

Schweregrad `crit`: Kategorie mit vielen Artikeln ohne jeden Filter.

### 2. Varianten

- Auswahl von Größe, Farbe, Ausführung: wie, und ist die Wahl erkennbar?
- Wechselt das Bild mit der Variante?
- Ändert sich der Preis sichtbar bei unterschiedlich teuren Varianten?
- Nicht lieferbare Varianten: ausgegraut oder kommentarlos verschwunden?

### 3. Produkttexte

- Beschreibung vorhanden, oder nur Stichpunkte aus dem Datenblatt?
- Eigentext oder Herstellertext?
  1. Eine markante Textzeile wörtlich per `WebSearch` suchen.
  2. Erscheint sie bei mehreren Händlern: Herstellertext.
  3. **Das ist ein belegter Fund**, relevant für die Auffindbarkeit.
- Beantwortet der Text die Fragen vor dem Kauf (Maße, Material, Pflege, Kompatibilität, Lieferumfang)?
- Crawl liefert die Wortzahl je Seite: Produktseiten unter 100 Wörtern sind ein belegbarer Befund über den Katalog, nicht nur über die Stichprobe.

### 4. Bilder

- Anzahl je Produkt; mehr als die Vorderansicht (Detail, Rückseite, Größenverhältnis, im Einsatz)?
- Zoom-Funktion?
- **Alt-Texte:** der Crawl zählt Bilder ohne Alt-Text. Befund für Auffindbarkeit und Zugänglichkeit, mit der Zahl aus dem Snapshot belegen.
- Einheitlicher Bildstil? (Freisteller und Milieu gemischt wirkt unfertig.)

### 5. Ausverkaufte Artikel

- Nicht lieferbares Produkt: Seite bleibt mit Hinweis, Weiterleitung oder 404?
- Benachrichtigung bei Verfügbarkeit oder Hinweis auf Alternativen?
- Crawl liefert die Statuscode-Verteilung: viele 404 in Produktpfaden belegen, dass ausgelistete Artikel ersatzlos verschwinden und aufgebaute Sichtbarkeit verloren geht.

### 6. Cross-Selling

- Verwandte oder ergänzende Artikel gezeigt, und passend?
- Wo: Produktseite, Warenkorb, gar nicht?
- Grund des Vorschlags erkennbar (Zubehör, Set, ähnlich)?

### 7. Produktseiten-SEO

Aus `claude-seo:seo-ecommerce` Abschnitt 1, gegen den Crawl-Snapshot:

| Prüfung | Beleg aus dem Crawl |
|---|---|
| Title mit Produktname und unterscheidender Eigenschaft, oder überall gleich aufgebaut? | doppelte Titles |
| Meta-Description vorhanden? | Anteil ohne Description |
| Genau eine H1? | Seiten mit mehreren H1 |
| Interne Verlinkung und Klicktiefe bis zum Produkt | maximale Tiefe, verwaiste Seiten |

**Diese Punkte aus dem Snapshot nehmen, nicht aus eigenen Abrufen.** Sie gelten für den ganzen Katalog und sind damit stärker als jede Stichprobe.

## Ausgabe

Zwei Dateien nach `<run>/findings/`:

| Datei | Inhalt |
|---|---|
| `L5-assortment.json` | Array, Felder wie in den übrigen Linsen: `severity`, `title`, `detail`, `recommendation`, `evidence`, `url`, `impact`, `effort`, `confidence`, `lens: "assortment"` |
| `L5-assortment.coverage.json` | die sieben Punkte, aufgeteilt in `checked` und `not_checkable` mit Grund |

**Zahlen aus dem Crawl in die `evidence`.** Beleg: "37 Bilder ohne Alt-Text bei 842 gecrawlten Seiten". Kein Beleg: "Viele Bilder ohne Alt-Text".
