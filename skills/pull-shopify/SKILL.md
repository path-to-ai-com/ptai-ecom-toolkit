---
name: pull-shopify
description: Zieht Shopify-Shop-Daten für den Kunden-Report oder den Wochen-Puls (Umsatz, Bestellungen, AOV, Top-Produkte, Sessions, Bestand, Kundentyp) und legt sie als Snapshot ab. Einsetzen, wenn ein Monats-Report oder Puls Shop-KPIs braucht oder der Nutzer ausdrücklich Shopify-Zahlen für einen Zeitraum abrufen will. Werkzeug ist die Shopify CLI (store execute), kein Script. Liest reporting/config.json im Kunden-Workspace.
---

# pull-shopify: Shopify-Snapshot ziehen

Zieht per Shopify CLI für einen Zeitraum Umsatz, Bestellungen, AOV, Top-Produkte, Sessions und Bestand und legt alles als Snapshot im Kunden-Workspace ab.

- Kein Script. Diese Session baut die Snapshot-Datei selbst aus den CLI-Antworten nach dem Schema unten.
- ShopifyQL läuft über das Admin-GraphQL-Feld `shopifyqlQuery` (dokumentierter Weg; rohes ShopifyQL direkt in `--query` ist nicht dokumentiert).
- Bestand über eine normale Admin-GraphQL-Query.
- Aufruf durch Report- und Puls-Lauf oder einzeln.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `shopify_store` (echte myshopify.com-Domain, nie ein Alias) und `sources.shopify` ungleich `false`.
- Shopify CLI installiert (`shopify version`). Sonst: `npm install -g @shopify/cli@latest`.
- Store-Auth für die Domain vorhanden (Scope-Regel unten).

Fehlt etwas oder steht `sources.shopify` auf `false`: Shopify als "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf (Report/Puls) scheitert nie daran.

## Shop aus dem Cockpit

Gilt, wenn `reporting/config.json` einen Block `portal` hat (geschrieben von `/ptai-ecom:setup --from-portal`); dann hat der Kunde Shopify im Cockpit verbunden.

- **Keine Store-Auth.** Die Scope-Regel entfällt, `shopify store auth` wird nie aufgerufen. Die Cockpit-App hat ihre Scopes bei der Installation erhalten.
- **Jeder Aufruf läuft über das Cockpit.** Statt `shopify store execute --store <shopify_store> --json` überall:

  ```bash
  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.portal shopify-execute
  ```

  mit denselben `--query` oder `--query-file`.
- Ausgabe und Exit-Code wie bei der CLI: Daten ohne `data`-Hülle auf stdout; bei Drosselung oder Fehler Exit 1, Meldung auf stderr.
- Regeln zu Exit-Code, Wiederholung und `parseErrors` (Schritt 4) gelten unverändert.
- Historie-Check (Schritt 2) liest den Grant ebenso über `currentAppInstallation { accessScopes { handle } }`.
- Cockpit meldet "nicht verbunden": Shopify ist für diesen Lauf nicht verfügbar. Nie auf die CLI ausweichen; für diesen Kunden-Store gibt es keine CLI-Anmeldung.

## Scope-Regel (hart): vor jeder Re-Auth die Union senden

- Die CLI vereinigt Scopes nicht verlässlich.
- Eine Auth mit nur `--scopes read_reports,read_products` reduziert den Grant auf genau diese zwei; Themes, Content, Files, Inventory sind danach weg.
- Der Zustimmungsdialog zeigt nur Zugewinne, nie Verluste. Der Verlust zeigt sich erst, wenn ein anderer Workflow scheitert.

**Benötigte Scopes für den vollen Audit-Umfang:**

| Scope | Wofür |
|---|---|
| `read_reports` | ShopifyQL, Umsatz, Sessions |
| `read_products` | Katalog, Varianten, Bilder |
| `read_orders` | Bestellungen der letzten 60 Tage |
| `read_all_orders` | volle Bestellhistorie. Ohne diesen Scope entsteht still eine 60-Tage-Baseline |
| `read_inventory` | Bestand, tote Artikel |
| `read_themes` | Theme und Version |
| `read_script_tags` | eingebundene Fremdskripte |
| `read_discounts`, `read_price_rules` | Rabattstruktur |
| `read_locales`, `read_markets` | Sprach- und Marktkonfiguration |

Die Liste wächst mit dem Audit-Scope. Die Union-Regel bleibt: bei Re-Auth immer alle bestehenden plus alle gelisteten Scopes senden, nie nur die neuen.

1. **Auth-Status prüfen:** `shopify store auth list --json` (dokumentierte Form; `auth:list` mit Doppelpunkt ist dasselbe Kommando).
   - Store-Domain aus der Config fehlt: Erst-Auth, direkt mit der vollständigen Scope-Liste.
   - Hat das Kundenprojekt eine dokumentierte Scope-Liste (CLAUDE.md des Kunden-Repos, Notizen im Kundenordner), diese verwenden.
2. **Bestehenden Grant lesen** (Store authentifiziert):

   ```bash
   shopify store execute --store <shopify_store> --json \
     --query 'query { currentAppInstallation { accessScopes { handle } } }' 2>/dev/null
   ```

   - Deckt die Liste alle Scopes der Tabelle ab: keine Re-Auth.
   - Scheitert der Call wegen abgelaufenem Online-Token (etwa 24h Laufzeit): bisherigen Scope-Satz aus der CLI-Konfiguration lesen, nicht raten. macOS: `~/Library/Preferences/shopify-cli-store-nodejs/config.json`, je Store-Domain mit Scopes.
3. **Re-Auth nur mit Union:** Vereinigung aus bestehenden und benötigten Scopes in einer einzigen `--scopes`-Liste:

   ```bash
   shopify store auth --store <shopify_store> \
     --scopes <bestehende Scopes>,read_reports,read_products,read_orders,read_all_orders,read_inventory,read_themes,read_script_tags,read_discounts,read_price_rules,read_locales,read_markets
   ```

## Ablauf

1. `reporting/config.json` lesen (`shopify_store`). Zeitraum:
   - Standard: letzter voller Monat (Erster bis Letzter des Vormonats).
   - Puls-Modus: letzte volle Woche, Montag bis Sonntag.
   - `SINCE`/`UNTIL` mit expliziten Datumsgrenzen, beide inklusiv.
2. Auth nach der Scope-Regel sicherstellen, dann zwei Historie-Prüfungen (siehe "Historie prüfen").
3. Vergleichszeitraum nur im Erstlauf:
   - Vormonats-Snapshot vorhanden (jüngster `reporting/data/`-Ordner mit `shopify.json`, deren `period` granularity `month` über den vollen Vormonat hat; `-pulse`-Dateien ignorieren): keinen Vergleich ziehen, der Report vergleicht gegen den Snapshot.
   - Kein Snapshot: dieselben Teil-Pulls (ohne Bestand) zusätzlich für den Monat davor ausführen, als `comparison` ablegen.
4. Teil-Pulls ausführen (siehe "Teil-Pulls").
5. Snapshot schreiben: `reporting/data/<run-id>/shopify.json`, solo `reporting/data/<heute>/shopify.json` (siehe "Zielordner"), im Puls-Modus `shopify-pulse.json` (granularity `week`). Diese Session schreibt das JSON selbst aus den CLI-Antworten, exakt nach dem Schema unten.
6. Dem Nutzer melden:
   - Umsatz, Bestellungen, AOV
   - Sessions und Conversion Rate, sofern vorhanden
   - Top-Produkt
   - Repeat-Rate, sofern `customer_type` vorhanden
   - Add-to-Cart-Sessions, Abandoned Carts, Verfügbarkeits-Quote
   - bei Vergleich die Richtung (mehr/weniger)
   - Widerspricht die zugeordnete Conversion der Bestellzahl: ausdrücklich melden, nicht nur im Snapshot ablegen.

## Historie prüfen (Ablauf Schritt 2)

### Scope-Prüfung

1. Im gelesenen Grant (`currentAppInstallation { accessScopes { handle } }`, Scope-Regel Schritt 2) prüfen, ob `read_all_orders` enthalten ist.
2. Der Zustimmungsdialog kann den Scope trotz Anfrage stillschweigend verweigern, etwa wenn die App für „Protected Customer Data" nicht freigegeben ist. Sonst fällt das erst an leeren Kohorten- und Repeat-Rate-Zahlen auf.
3. Fehlt `read_all_orders`: Bestellhistorie auf 60 Tage begrenzt. Das ist ein Befund, keine stille Kurz-Baseline.
4. Melden als „Historie auf 60 Tage begrenzt, `read_all_orders` fehlt" und als `notes.order_history` in den Snapshot schreiben (Schritt 5).

### Empirische Probe

- Der Scope allein belegt die Historie nicht.
- Bei einem auf Shopify migrierten Shop tragen importierte Bestellungen das Importdatum als `createdAt`, nicht das Kaufdatum. Die älteste Bestellung kann Jahre nach dem ersten Umsatzmonat liegen, und die Monate um den Import zeigen ein Vielfaches der realen Bestellzahl.

1. Älteste Bestellung laut Admin-API holen:

   ```bash
   # aelteste Bestellung laut Admin-API
   shopify store execute --store <shopify_store> --json --query 'query {
     orders(first: 1, sortKey: CREATED_AT, reverse: false) {
       nodes { createdAt }
     }
   }' 2>/dev/null
   ```

2. Mit dem ersten Monat mit Umsatz aus der Zeitreihe (Teil-Pulls) vergleichen.
3. Liegen beide weit auseinander, ist der Shop migriert. Dann:
   - **Historie nur über ShopifyQL, nie über einen Admin-API-Datumsfilter.**
   - `notes.order_history` enthält beide Daten und den Hinweis, dass Admin-seitige Datumsfilter vor dem Importdatum falsche Zahlen liefern.

## Teil-Pulls (Ablauf Schritt 4)

### Grundregeln

- Jeder Teil scheitert isoliert: Feld `null` plus Begründung in `notes`, nie Abbruch des Laufs.
- stdout von `store execute --json` ist reines JSON, Fortschritt geht auf stderr, daher überall `2>/dev/null`.
- **Darum bei jedem Call den Exit-Code prüfen.**
  - Die Admin-API arbeitet mit Punktebudget; ShopifyQL-Abfragen über die volle Historie sind teuer. Rund die Hälfte der Calls wird beim ersten Versuch gedrosselt.
  - Bei Drosselung: Meldung auf stderr, Exit 1, nichts auf stdout. Mit `2>/dev/null` sieht das aus wie "keine Daten".

  ```bash
  if ! antwort="$(shopify store execute ... 2>/dev/null)"; then
    # gedrosselt oder Netzwerkfehler: warten und erneut versuchen
    sleep 20 && antwort="$(shopify store execute ... 2>/dev/null)" || true
  fi
  ```

- Zwei Wiederholungen mit wachsender Pause (20, dann 40 Sekunden) genügen erfahrungsgemäß.
- Scheitert ein Teil-Pull danach weiter: Feld `null` plus Begründung in `notes`.
- **Eine leere Antwort ohne Exit-Code-Prüfung geht nie als "keine Daten" in den Snapshot.**
- Nach jedem ShopifyQL-Call `parseErrors` prüfen. Nicht leer = Query kaputt: gegen die ShopifyQL-Referenz korrigieren, erneut ausführen.

### Umsatz-Totals

Zahlen aus `tableData.rows`, Spaltennamen aus `tableData.columns`, beides 1:1 übernehmen, nie selbst rechnen:

```bash
shopify store execute --store <shopify_store> --json --query 'query {
  shopifyqlQuery(query: """
    FROM sales
    SHOW total_sales, net_sales, orders, average_order_value
    SINCE 2026-07-01 UNTIL 2026-07-31
  """) { tableData { columns { name dataType } rows } parseErrors }
}' 2>/dev/null
```

### Zeitreihe

- Gleiche Query plus `TIMESERIES month`; im Puls `TIMESERIES day` über die Woche.
- AOV nie aus der Zeitreihe mitteln, er kommt aus der Totals-Query.

```bash
shopify store execute --store <shopify_store> --json --query 'query {
  shopifyqlQuery(query: """
    FROM sales
    SHOW total_sales, net_sales, orders
    TIMESERIES month
    SINCE 2026-07-01 UNTIL 2026-07-31
  """) { tableData { columns { name dataType } rows } parseErrors }
}' 2>/dev/null
```

### Top-Produkte nach Umsatz

ShopifyQL, nicht GraphQL: der Admin-Enum `ProductSortKeys` kennt kein `BEST_SELLING`.

```bash
shopify store execute --store <shopify_store> --json --query 'query {
  shopifyqlQuery(query: """
    FROM sales
    SHOW net_sales, orders
    GROUP BY product_title
    SINCE 2026-07-01 UNTIL 2026-07-31
    ORDER BY net_sales DESC
    LIMIT 50
  """) { tableData { columns { name dataType } rows } parseErrors }
}' 2>/dev/null
```

**Zeile ohne `product_title` ist kein Produkt.**

- Ein migrierter Shop hat Bestellungen ohne Artikelbezug; ShopifyQL fasst sie in einer Zeile mit `product_title: null` zusammen.
- Diese Zeile kann den Großteil des Umsatzes tragen (gemessen: 67,6 Prozent des Nettoumsatzes) und stünde dann an der Spitze der Top-Produkte.
- Die Zeile bleibt unverändert im Snapshot, sie ist eine echte Messung.
- Betrag und Anteil gehören in `notes.top_products`.
- **Jede Sortimentsrechnung läuft nur über die benannten Zeilen**, mit dem benannten Umsatz als Nenner.
- Den unbenannten Anteil daneben ausweisen, nie stillschweigend mitrechnen, nie weglassen.

**`LIMIT` erhöhen, bis die Liste nachweislich vollständig ist.**

- Startwert `LIMIT 50` statt 10: die Sortiments-Diagnose "Ware ohne Umsatz" (Kennzahlen-Katalog) hält den vollen Produktbestand gegen die Umsatzzeilen; bei `LIMIT 10` zählte ein Produkt auf Rang 11 fälschlich als umsatzlos.
- Kommen genau so viele Zeilen wie das Limit, ist die Liste abgeschnitten: Limit erhöhen (Beispiel aus einem Lauf: 50, 1.000, 5.000), bis die Zeilenzahl unter dem Limit bleibt.
- Der Snapshot enthält die vollständige Liste, der Report zeigt die Top 10.
- Erreichte Zeilenzahl und benutztes Limit in `notes.top_products`.

### Sessions, Conversion Rate und Kaufweg

- Das `sessions`-Schema liefert `sessions`, `conversion_rate` und die Kaufweg-Stufen `sessions_with_cart_additions` und `sessions_that_reached_checkout` (am Pilot-Shop bestätigt).
- Die Query enthält einfache Anführungszeichen: in eine Datei schreiben, mit `--query-file` ausführen.

```graphql
query {
  shopifyqlQuery(query: """
    FROM sessions
    SHOW sessions, sessions_with_cart_additions,
         sessions_that_reached_checkout, conversion_rate
    WHERE human_or_bot_session = 'human'
    SINCE 2026-07-01 UNTIL 2026-07-31
  """) { tableData { columns { name dataType } rows } parseErrors }
}
```

```bash
shopify store execute --store <shopify_store> --json \
  --query-file <pfad>/sessions.graphql 2>/dev/null
```

- `WHERE`-Filter nie weglassen; ohne ihn zählen Bots mit (am Pilot-Shop im Juni rund 40 Prozent der Sessions).
- Ergebnis nach `sessions` (`sessions`, `conversion_rate`) und nach `session_funnel` (alle vier Felder).
- Fehler oder keine Daten: beide Felder `null` plus Note, der Report nimmt Traffic und Kaufweg aus GA4. Nicht fatal.
- **Die beiden unteren Kaufweg-Stufen sind bei kleinen Shops unzuverlässig:** nur roh ablegen, nie zu einer Quote verrechnen. Am Pilot-Shop gab es Monate mit weniger erreichten Checkouts als Bestellungen und mit weniger Warenkorb-Sessions als Checkouts.
- Widerspricht `sessions_that_reached_checkout` der Bestellzahl: Note in den Snapshot.

### Abandoned Carts

Admin GraphQL, Scope `read_orders`. Anführungszeichen im Filter, daher `--query-file`:

```graphql
query {
  abandonedCheckouts(first: 50, query: "created_at:>=2026-07-01 created_at:<=2026-07-31") {
    nodes {
      createdAt
      completedAt
      totalPriceSet { shopMoney { amount currencyCode } }
      lineItems(first: 5) { nodes { title quantity } }
    }
  }
}
```

- Snapshot-Feld `abandoned_checkouts` wie das Admin-Objekt; im Report heißt die Kennzahl **Abandoned Cart**. Feldnamen folgen der API, Anzeigenamen dem Sprachgebrauch.
- **Shopify hält abgebrochene Warenkörbe nur begrenzt vor.** Ein Filter über den vollen Audit-Zeitraum liefert nur die letzten Monate, `count` und `total_value` wirken trotzdem wie Werte über den ganzen Zeitraum.
- Abgedeckten Zeitraum aus dem ältesten `createdAt` der Antwort bestimmen und nach `notes.abandoned_checkouts` schreiben, jedes Mal, auch bei sauberem Call.
- In `abandoned_checkouts`: `count`, `total_value` (Summe über Zeilen mit `completedAt` = `null`), `currency`, Einzelzeilen.
- Nur nicht abgeschlossene zählen; ein Checkout mit `completedAt` ist eine Bestellung.
- Scheitert der Call: Feld `null` plus Note.

### Bestand und Verfügbarkeit

Admin GraphQL, Scope `read_products`. Ein Call über **alle aktiven Produkte**, keine Stichprobe:

```bash
shopify store execute --store <shopify_store> --json --query 'query {
  products(first: 250, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes {
      title handle status totalInventory tracksInventory
      variants(first: 100) {
        pageInfo { hasNextPage }
        nodes { title inventoryQuantity inventoryPolicy availableForSale }
      }
    }
  }
}' 2>/dev/null
```

- **Nie `products(first: 50, sortKey: TITLE)`.** Das ist der Anfang des Alphabets, keine Stichprobe, und verfehlt systematisch die Umsatzträger; deren Bestand stünde dann auf `null`.

Drei Snapshot-Felder aus dieser Antwort:

| Feld | Inhalt |
|---|---|
| `products` | je Produkt `product_title`, `handle`, `status`, `total_inventory`, `tracks_inventory`; Grundgesamtheit der Sortiments-Diagnosen im Kennzahlen-Katalog |
| `top_products[].total_inventory` und `.status` | per Titel-Match; ohne Match (abweichender Titel im Umsatzbericht, archiviertes Produkt) gezielt per `query: "title:*<Titel>*"` nachfragen statt `null` |
| `availability` | Aggregate über alle aktiven Produkte: `active_products`, `variants_total`, `variants_available`, `products_fully_unavailable`, `products_partially_available`, `zero_stock_active`, `zero_stock_still_buyable`, plus Listen `fully_unavailable_titles` und `partially_available` (Titel, `available_variants`, `total_variants`) |

- **`total_inventory: 0` heißt nicht „nicht kaufbar“.** Maßgeblich ist `availableForSale` je Variante, abhängig von `inventoryPolicy`:
  - `CONTINUE`: trotz Bestand 0 bestellbar (Fertigung auf Bestellung).
  - `DENY`: nicht bestellbar.
- Am Pilot-Shop waren fast alle Produkte mit Bestand 0 normal bestellbar; Bestand 0 als Kaufhindernis zu lesen wäre falsch.
- Mehr als 250 aktive Produkte: über `pageInfo.hasNextPage` und `endCursor` blättern, bis alle da sind. Aggregate nur über den vollen Bestand.
- **`pageInfo` steht in jeder Beispiel-Query**; ohne das Feld ist nicht feststellbar, ob Seiten fehlen.
- Meldet `variants(first: 100)` `hasNextPage` wahr, ist die Variantenliste des Produkts unvollständig und die Verfügbarkeits-Aggregate stimmen nicht.
- Zahl der geblätterten Seiten in `notes.availability`.

### Bestellungen nach Quelle

Admin GraphQL, Scope `read_orders`. Zweck: Abweichung zwischen Bestellzahl und zugeordneter Conversion einordnen.

- **Zählen, nicht exportieren.** Ein Zeilen-Export wären hunderte Seiten zu je 250 Bestellungen und ist verboten (Abschnitt "Kundentyp", Absatz "Kohorten und Repeat-Rate nur aus aggregierten Abfragen"). `ordersCount` liefert die Zahl je Quelle in einem Call ohne Bestellzeile:

```bash
shopify store execute --store <shopify_store> --json --query 'query {
  web: ordersCount(query: "source_name:web") { count precision }
  draft: ordersCount(query: "source_name:shopify_draft_order") { count precision }
  all: ordersCount(query: "") { count precision }
}' 2>/dev/null
```

- **`precision` ist Pflicht.** Shopify kappt die Zählung und meldet dann `precision: AT_LEAST` statt `EXACT`. Ein Rückgabewert `10000` kann die Kappungsgrenze sein, keine Bestellzahl.
- **Meldet eine Zeile `AT_LEAST`: `orders_by_source` = `null`** plus Note mit der Kappung. Eine gekappte Zahl ist schlechter als keine.
- Sonst nach `orders_by_source` schreiben (`source_name`, `orders`).
- **Numerische Quellnamen lassen sich nicht filtern:** eine App-Quelle wie `12345678901` liefert über `source_name:` null Treffer, auch in Anführungszeichen. Ihre Zahl = `alle` minus Summe der benannten Quellen; die Herleitung in die Note.
- Deutung:
  - Fast alle Bestellungen `web`: niedrige zugeordnete Conversion = Zuordnungsverlust, kein anderer Bestellweg. In die Note.
  - **Mehrheit mit anderer Quelle:** der Schluss gilt nicht. Bei migrierten Shops der Normalfall; der Snapshot trennt dann Tracking-Verlust und anderen Bestellweg nicht. Note: Ursache offen, keine der beiden Deutungen.
- `ordersCount` hat keine Zeitdimension. Die Zahlen decken den vollen Zeitraum ab und lassen sich nicht auf das Sessions-Fenster schneiden; auch das in die Note, damit niemand sie gegen eine Monatsreihe hält.

### Kundentyp (für die Repeat-Rate)

```bash
shopify store execute --store <shopify_store> --json --query 'query {
  shopifyqlQuery(query: """
    FROM sales
    SHOW orders, total_sales
    GROUP BY customer_type
    SINCE 2026-07-01 UNTIL 2026-07-31
  """) { tableData { columns { name dataType } rows } parseErrors }
}' 2>/dev/null
```

- `customer_type` ist laut ShopifyQL-Referenz eine Dimension des `sales`-Schemas mit Werten wie `first-time` und `returning`.
- Zeilen 1:1 übernehmen, nie zusammenfassen oder umbenennen. Die Repeat-Rate rechnet der Report nach dem Kennzahlen-Katalog.
- **Nicht jeder Shop hat die Dimension.** Am Pilot-Shop: `Column Not Found: Column 'customer_type' not found`, ebenso für `returning_customer_type`, `customer_segment` und `billing_customer_type`; das `orders`-Dataset war nicht ansprechbar (`Invalid dataset in FROM clause - orders`).
- Bei diesem Fehler höchstens diese Alternativen probieren, dann stoppen: `"customer_type": null` plus Note, die Repeat-Rate entfällt im Report.
- Nie aus einem anderen Schema zusammenrechnen; das wäre eine andere Kennzahl unter demselben Namen.

**Kohorten und Repeat-Rate nur aus aggregierten Abfragen wie dieser.**

- Verboten im Snapshot: Bestell-Export auf Zeilenebene, Namen, Adressen, Mailadressen (Spec Abschnitt 13).
- `reporting/` wird ins Git-Repository des Kunden committet; eine Bestellzeile mit Klardaten wäre dort ein Datenleck.
- Die ShopifyQL-Aggregation liefert je Zeile nur `customer_type`, `orders` und `total_sales`, nie ein personenbezogenes Feld. Das gilt auch, wenn `read_all_orders` künftig eine Kohorten-Zeitreihe über die volle Historie liefert.

### Top-Collections

- Im `sales`-Schema wurde keine Collection-Dimension gefunden (vorhanden: `product_title`, `product_type`, `sales_channel`, Länder, Kundentyp).
- Vor dem Aufgeben die aktuelle Schema-Referenz prüfen (shopify.dev/docs/api/shopifyql, Abschnitt Schemas).
- Keine Dimension: `"top_collections": null` plus Note.
- Machbarkeit wird im Pilot validiert.

## Zielordner

- Der Aufrufer bestimmt den Zielordner.
- Solo: Vorgabe `reporting/data/<heute>`.
- **Innerhalb eines Audit- oder Report-Laufs: `reporting/data/<run-id>`**, Datum plus Kadenz (`2026-10-01-audit`, `2026-11-01-month`).
- Der Orchestrator gibt den Ordner vor. Bei manuellem Start während eines Laufs dieselbe Lauf-ID verwenden.
- Ein Snapshot im falschen Ordner fehlt der Analyse, und sie rechnet ohne Fehlermeldung weiter.

## Snapshot-Schema

`reporting/data/<run-id>/shopify.json` (oder `shopify-pulse.json`), solo unter `reporting/data/<heute>/`.

- Immer vorhanden, gescheiterte Teile als `null`: `period`, `totals`, `by_month`, `top_products`, `top_collections`, `sessions`, `session_funnel`, `abandoned_checkouts`, `orders_by_source`, `products`, `availability`, `customer_type`.
- `comparison` nur im Erstlauf.
- `notes` nur, wenn mindestens ein Feld genullt wurde (Ausnahmen unten).

```json
{
  "period": {"start": "2026-07-01", "end": "2026-07-31", "granularity": "month"},
  "totals": {"total_sales": 0, "net_sales": 0, "orders": 0, "average_order_value": 0},
  "by_month": [
    {"month": "2026-07", "total_sales": 0, "net_sales": 0, "orders": 0}
  ],
  "top_products": [
    {"product_title": "Outdoorjacke", "net_sales": 0, "orders": 0, "total_inventory": 0, "status": "ACTIVE"}
  ],
  "top_collections": null,
  "sessions": {"sessions": 0, "conversion_rate": 0.0},
  "session_funnel": {
    "sessions": 1782, "sessions_with_cart_additions": 9,
    "sessions_that_reached_checkout": 2, "conversion_rate": 0.0016835
  },
  "abandoned_checkouts": {
    "count": 1, "total_value": 24.9, "currency": "EUR",
    "items": [{"created_at": "2026-07-22", "total": 24.9, "line_items": ["Hammerring"]}]
  },
  "orders_by_source": [{"source_name": "web", "orders": 10}],
  "products": [
    {"product_title": "Beispielartikel", "handle": "beispielartikel", "status": "ACTIVE", "total_inventory": 12, "tracks_inventory": true}
  ],
  "availability": {
    "active_products": 174, "variants_total": 3370, "variants_available": 3323,
    "products_fully_unavailable": 1, "products_partially_available": 13,
    "zero_stock_active": 120, "zero_stock_still_buyable": 119,
    "fully_unavailable_titles": ["Beispielartikel Vier"],
    "partially_available": [
      {"title": "Hoodie, Grau", "available_variants": 1, "total_variants": 8}
    ]
  },
  "customer_type": [
    {"customer_type": "first-time", "orders": 0, "total_sales": 0},
    {"customer_type": "returning", "orders": 0, "total_sales": 0}
  ],
  "notes": {
    "top_collections": "keine Collection-Dimension im sales-Schema",
    "order_history": "Historie auf 60 Tage begrenzt, read_all_orders fehlt"
  },
  "comparison": {"totals, by_month, top_products, sessions, session_funnel, abandoned_checkouts, customer_type plus eigener period, nur beim Erstlauf": "..."}
}
```

### Regeln zum Schema

**`by_month`**

- Heißt in Monat und Puls gleich (einheitliches Schema).
- Im Puls hat jede Zeile `"date"` statt `"month"`, die Reihe ist täglich.

**Monats- und Puls-Felder**

- `products` = Vollerhebung aller aktiven Produkte, `availability` = Aggregate daraus, `customer_type` = Zeilen wie von ShopifyQL geliefert.
- Diese drei sind im Puls `null` plus Note ("im Puls nicht gezogen"); Repeat-Rate, Verfügbarkeit und Sortiment sind Monats-Diagnosen.
- `session_funnel` und `abandoned_checkouts` laufen auch im Puls (billig, liefern die Kaufweg-Aussage).

**`notes`**

- Je genulltem Feld eine Begründung; entfällt, wenn nichts `null` ist.
- Ausnahme `order_history`: wird auch ohne genulltes Feld geschrieben, da eine 60-Tage-Baseline kein leeres Feld, sondern ein verkürzter Zeitraum ist.
- **Zusätzlich jede methodische Abweichung, auch bei gefülltem Feld:** erhöhtes `LIMIT`, per Differenz ermittelter Quellname, kürzer vorgehaltener Zeitraum als angefragt, Felder mit verschiedenen Anfangsdaten. Ohne diese Einträge lässt sich die Bedeutung der Zahlen nicht rekonstruieren.
- Schlüssel = Name des betroffenen Felds.

**`comparison`**

- Immer in derselben Datei, nie als eigene Datei oder eigener Ordner; eigener `period`, gleiche Struktur.
- Enthält `customer_type` (für das Delta der Repeat-Rate), `session_funnel`, `abandoned_checkouts`.
- Enthält nicht: `top_collections`, `products`, `availability`, Bestand. `total_inventory`, `status` und Verfügbarkeit sind Momentaufnahmen und stehen nur im Hauptteil.
- Scheitert ein Teil-Pull des Vergleichsmonats: Feld im `comparison` `null`, Grund in einem eigenen `notes`-Eintrag innerhalb von `comparison`.
- Puls-Dateien überschreiben nie die Monats-Vergleichsbasis.

## Setup-Check

Kein Script, drei Prüfungen für den Setup-Wizard:

1. `shopify version` läuft (CLI installiert).
2. `shopify store auth list --json` enthält die `shopify_store`-Domain aus der Config.
3. Mini-Query als Test-Call; Exit 0 und leere `parseErrors` = ok:

   ```bash
   shopify store execute --store <shopify_store> --json --query 'query {
     shopifyqlQuery(query: """FROM sales SHOW total_sales SINCE -1d""") { parseErrors }
   }' 2>/dev/null
   ```

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| `command not found: shopify` | `npm install -g @shopify/cli@latest`, erneut starten. |
| Store fehlt in `auth list` oder Online-Token (etwa 24h) abgelaufen | Auth nach der Scope-Regel, immer mit Union, nie eingeschränkt. |
| Access denied bei `shopifyqlQuery` | Grant ohne `read_reports`; bei der Produkt-Query fehlt `read_products`. Re-Auth mit Union. |
| `read_all_orders` fehlt im Grant trotz Union | Zustimmungsdialog hat den Scope stillschweigend verweigert; Re-Auth hilft nicht, solange die Freigabe fehlt. `"Historie auf 60 Tage begrenzt, read_all_orders fehlt"` melden, `notes.order_history` schreiben, kein Absturz. |
| `parseErrors` nicht leer | ShopifyQL-Query ungültig; gegen die Referenz (shopify.dev/docs/api/shopifyql) korrigieren, erneut. |
| `sessions` mit Fehler oder ohne Zeilen | Plan-abhängig: `"sessions": null` plus Note, Report verweist auf GA4. Nicht fatal. |
| `customer_type` mit Fehler oder ohne Zeilen | `"customer_type": null` plus Note, Repeat-Rate entfällt im Report. Nicht fatal. |
| Einzelner Teil-Pull kaputt | Feld `null` plus Note, übrige Teile laufen weiter. "Nicht verfügbar" gilt nur, wenn CLI oder Auth ganz fehlen. |
| Top-Produkt ohne Bestand nach Titel-Match | Nicht `null` lassen, gezielt per `query: "title:*<Titel>*"` nachfragen; der Bestand des Umsatzträgers ist für den Report am wichtigsten. |

### Shell-Quoting

- Queries mit einfachen Anführungszeichen oder Datums-Filtern (`sessions`, `abandonedCheckouts`, `orders`) immer per `--query-file`.
- In einer `--query`-Zeichenkette zerlegt die Shell `SINCE ... UNTIL ...`; ShopifyQL meldet dann einen ANTLR-Syntaxfehler, der wie ein Query-Fehler aussieht, aber keiner ist.
- **Diese Regel hat Vorrang vor den Beispielen oben.** Umsatz-, Zeitreihen- und Top-Produkt-Query zeigen `SINCE`/`UNTIL` inline in `--query`; das läuft, weil sie ohne einfache Anführungszeichen auskommen.
- Einfachste Regel: **jede** Query mit Datumsgrenzen per `--query-file`; das ist immer richtig.

### Am Pilot-Shop bestätigt

- `shopifyqlQuery`-Wrapper ist der richtige Weg; rohes ShopifyQL an `--query` ist nicht dokumentiert.
- Das `sessions`-Schema liefert Daten inklusive der beiden Kaufweg-Stufen.
- Keine Collection-Dimension; `top_collections` bleibt `null`.
- `customer_type` existiert dort nicht; die Repeat-Rate entfällt.
