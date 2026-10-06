---
name: pull-shopify-catalog
description: Zieht den Produktkatalog eines Shopify-Shops (Produkte, Varianten, SEO-Felder, Bilder mit Alt-Text, Preise, Einkaufspreise, Collections) und legt ihn als aggregierten Snapshot ab. Einsetzen, wenn ein Audit den Baseline-Block Katalog braucht oder der Nutzer wissen will, wie vollständig Produktdaten und SEO-Felder gepflegt sind. Werkzeug ist die Shopify CLI, kein eigener Auth-Weg. Liest reporting/config.json im Kunden-Workspace.
---

# pull-shopify-catalog: Katalog-Snapshot ziehen

Holt den Produktkatalog über die Shopify CLI und berechnet einen aggregierten Snapshot:

- Pflegegrad von SEO-Feldern, Alt-Texten, SKUs, Einkaufspreisen
- Verteilung von Beschreibungslängen und Preisen

## Arbeitsteilung

| Teil | Wer | Warum |
|---|---|---|
| Rohseiten holen | diese Skill über die CLI | nur die CLI hat den Auth-Kontext |
| Snapshot rechnen | Script `catalog_build.py` | getesteter Rechenteil, dort entstehen sonst falsche Zahlen |

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und `sources.catalogue` ungleich `false`.
- Shopify CLI installiert, Store authentifiziert.
- Scopes `read_products` und `read_inventory` (letzterer für `unitCost`).
- **Scope- und Union-Regel: `pull-shopify/SKILL.md`**, hier nicht wiederholt. Bei Re-Auth immer die Vereinigung senden, nie nur die neuen Scopes.

## Drosselung

- Gleiche Regel wie in `pull-shopify`; beide Pulls teilen das Punktebudget der Admin-API.
- Rund die Hälfte der Calls wird beim ersten Versuch gedrosselt.
- **Exit-Code prüfen, nicht nur stdout lesen**, dann warten und wiederholen. Ablauf: `pull-shopify/SKILL.md`, Abschnitt Ablauf, Schritt 4.
- Teuerster Teil ist die Seitenschleife (2.000 Produkte = acht Seiten zu 250, jede kann gedrosselt werden).
- Die Schleife wartet nach einem gedrosselten Versuch und bricht **nicht** ab. Ein Abbruch ergäbe einen halben Katalog, der vollständig aussieht, mit durchweg falschen Zahlen.

## Ablauf

1. `reporting/config.json` lesen, Auth nach der Regel aus `pull-shopify` sichern.
2. Produkte seitenweise holen. `description` verwenden, **nicht** `descriptionHtml`: der Snapshot braucht nur die Länge, und Rohtext ist kürzer als Markup.

   ```graphql
   query($cursor: String) {
     products(first: 250, after: $cursor) {
       pageInfo { hasNextPage endCursor }
       nodes {
         handle title status productType vendor description
         seo { title description }
         images(first: 50) { nodes { url altText } }
         variants(first: 100) {
           nodes { sku price availableForSale inventoryItem { unitCost { amount } } }
         }
       }
     }
   }
   ```

3. Jede Antwortseite **unverändert** in eine Liste sammeln, als JSON-Array nach `/tmp` schreiben, nicht nach `reporting/`. Rohtext gehört nicht ins Kunden-Repo, dorthin kommt nur `catalog.json`.
4. Collections analog über `collections(first: 250, after: $cursor)` mit `handle`, `title`, `description`, `seo`.
5. Aggregieren:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-shopify-catalog/scripts/catalog_build.py" \
     --pages /tmp/catalog-pages.json --collections /tmp/catalog-collections.json \
     --out "reporting/data/<run-id>"
   ```

6. Melden: Produkte, Varianten, Anteil mit vollständigen SEO-Feldern, Anteil Bilder mit Alt-Text, jeden Hinweis aus `notes` wörtlich.

## Feldnamen vor dem ersten Lauf prüfen

- Admin-GraphQL-Namen hängen an der API-Version. Eine falsch benannte Verschachtelung liefert `null` statt eines Fehlers.
- Vor dem ersten Lauf gegen die Referenz der eingesetzten Version prüfen, vor allem `seo` am Produkt und `inventoryItem.unitCost.amount` an der Variante.
- Werkzeug: Shopify-Dev-MCP, nicht das Gedächtnis.
- Absicherung im Script: `check_shape()` meldet jedes Feld, das in **keinem** Produkt vorkommt, als unvollständige Abfrage.
  - Einzelne Produkte ohne SEO-Felder = Befund über den Shop.
  - Feld in keinem Produkt = Fehler in der Query; sonst stünde "kein Produkt hat SEO-Felder" im Snapshot.

## Snapshot-Schema

`<out>/catalog.json`:

```json
{
  "source": "catalogue",
  "summary": {
    "products_total": 174, "products_active": 168,
    "products_without_seo_title": 12, "products_without_seo_description": 40,
    "products_without_description": 3, "products_without_image": 1,
    "products_with_missing_alt": 96,
    "description_length_p10": 0, "description_length_p50": 230,
    "description_length_p90": 1400,
    "images_total": 512, "images_with_alt": 96, "share_images_with_alt": 0.1875,
    "variants_total": 3370, "variants_without_sku": 4, "variants_without_cost": 3370,
    "products_with_duplicate_description": 18, "duplicate_description_groups": 6,
    "products_sold_out": 9,
    "collections_total": 22, "collections_without_description": 14
  },
  "products_without_seo_title": ["handle", "..."],
  "products_without_seo_title_truncated": false,
  "products_without_seo_description": ["..."],
  "products_with_missing_alt": ["..."],
  "products_without_cost": ["..."],
  "products_sold_out": ["..."],
  "duplicate_descriptions": [{"count": 4, "handles": ["handle", "..."]}],
  "duplicate_descriptions_truncated": false,
  "notes": ["..."]
}
```

### Regeln zum Schema

- **Kein Fließtext.** Aus der Beschreibung wird `description_length`, nie der Inhalt; bei 2.000 Produkten würde Fließtext den Kontext eines Analyse-Agenten sprengen.
- **Doppelte Beschreibungen über Fingerabdruck:**
  - SHA-1 der Beschreibung je Produkt, klein geschrieben, Leerraum vereinheitlicht.
  - Gezählt nur unter aktiven Produkten; der Text kommt nicht in den Snapshot.
  - Höchstens fünf Handles je Gruppe, Liste auf 50 Gruppen gekappt.
  - Meist übernommener Herstellertext (Kriterium `con.duplicate-product-copy`).
- **Ausverkauft = keine Variante verkäuflich** (`availableForSale`), nur unter aktiven Produkten.
  - Fehlt das Feld in den Rohdaten: `products_sold_out` = `null`, nicht 0.
  - Ausverkauft ist ein Betriebszustand, kein Befund. Die Analyse prüft nur die technische Behandlung (Kriterium `tec.sold-out-handling`).
- **Kein Urteil über "dünn".** Der Pull liefert die Längenverteilung (p10, p50, p90) und die Zahl der Produkte **ohne** Beschreibung. Die Schwelle steht im Kennzahlen-Katalog, das Urteil fällt die Analyse.
- **Einkaufspreis: `null` ≠ `0.00`.**
  - `null` = "cost per item nicht gepflegt".
  - `0.00` = gepflegter Wert (Zugabe, Werbeartikel).
  - Zusammengezählt wäre die Lücke zu hoch.
  - Hat **keine** Variante einen Einkaufspreis: Hinweis in `notes`, Marge und Deckungsbeitrag nicht berechenbar (Spec Abschnitt 19).
- **Anteile ohne Nenner sind `null`.** Ein Katalog ohne Bilder hat keinen Alt-Text-Anteil; 0 hieße "kein Bild hat Alt-Text".
- **Listen auf 200 gekappt.** Der Zähler im `summary` nennt die volle Menge, `_truncated` zeigt die Kürzung. Für mehr fragt die Analyse die Rohseiten gezielt ab.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Gedrosselt** | Warten, wiederholen; nie als "keine Daten" werten. |
| **`check_shape`-Hinweis in `notes`** | Abfrage unvollständig, Katalog nicht leer. Feldnamen prüfen und neu ziehen, bevor der Snapshot in eine Analyse geht. |
| **Kein Einkaufspreis** | Kein Fehler, Vermerk; die Marge entfällt. |
