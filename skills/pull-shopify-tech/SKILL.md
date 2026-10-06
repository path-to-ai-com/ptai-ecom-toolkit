---
name: pull-shopify-tech
description: Erfasst die technische Ausstattung eines Shopify-Shops (Theme und Version, Skript-Tags, Sprach- und Marktkonfiguration, Zahlungsarten) plus die Fremdtechnik aus dem Crawl desselben Laufs und schreibt das Ergebnis als Snapshot. Einsetzen, wenn ein Audit wissen muss, welche Werkzeuge im Shop eingebunden sind, ob doppelt gemessen wird oder welches Theme läuft. Werkzeug ist die Shopify CLI plus die vorhandene crawl.json. Liest reporting/config.json im Kunden-Workspace.
---

# pull-shopify-tech: Shop-Technik erfassen

Ein Snapshot aus zwei Quellen:

- Admin-API: Konfiguration des Shops
- Crawl: eingebundene Fremdtechnik

## Crawl wiederverwenden

- `crawl-site` erfasst in derselben Phase je Seite die Skript-Quellen (`script_sources`) und die inline eingebauten Container- und Mess-IDs (`inline_tag_ids`), aggregiert im `findings_index`. Diese Skill liest daraus.
- Kein zweiter Abruf der Seiten: doppelte Arbeit, und er könnte einen anderen Zustand sehen als der Crawl, gegen den die technische Analyse rechnet.
- Darum läuft dieser Pull **nach** `crawl-site`.
- Fällt der Crawl aus: Snapshot ohne Storefront-Teil, `crawl_pages_scanned` = `null`.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und `sources.shop_tech` ungleich `false`.
- Shopify CLI installiert, Store authentifiziert.
- Scopes `read_themes`, `read_script_tags`, `read_locales`, `read_markets`.
- Scope- und Union-Regel sowie Drosselung: `pull-shopify/SKILL.md`. **Exit-Code prüfen, warten, wiederholen**, nie eine leere Antwort als "keine Daten" werten. Beide Shopify-Pulls teilen dasselbe Punktebudget.
- Kadenz: quartalsweise (billige Abfrage, Shop ändert sich selten).

## Ablauf

1. Alle Blöcke in einer Abfrage holen:

   ```graphql
   query {
     themes(first: 20) { nodes { name role updatedAt } }
     scriptTags(first: 100) { nodes { src displayScope } }
     shopLocales { locale primary published }
     markets(first: 50) { nodes { name enabled primary } }
     shop { name currencyCode ianaTimezone }
   }
   ```

2. Antwort nach `/tmp` schreiben, dann aggregieren:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-shopify-tech/scripts/shop_tech_build.py" \
     --shop /tmp/shop-tech-raw.json \
     --crawl "reporting/data/<run-id>/crawl.json" \
     --out "reporting/data/<run-id>"
   ```

3. Melden: Theme, Zahl der Skript-Tags, Fremd-Hosts, Mess-IDs, jeden Hinweis aus `notes` wörtlich.

### Zahlarten nicht erhoben

- **`paymentSettings` existiert nicht auf `QueryRoot`** (geprüft 07.09.2026 an einem Store). Die Admin-API antwortet mit `undefinedField`, und GraphQL lehnt dann die ganze Abfrage ab, also **jeden** Block.
- Das Feld ist darum nicht in der Abfrage.
- Folge: Zahlarten sind im Audit nicht erhoben; die Fachsektion Shop im Kunden-PDF zeigt "nicht erhoben".
- Wer sie braucht: zuerst in der aktuellen Schema-Referenz den heutigen Namen prüfen (Kandidaten: `shop.paymentSettings`, oder gar nicht über die Admin-API), erst dann die Abfrage ergänzen.

## Feldnamen vor dem ersten Lauf prüfen

- `themes` gibt es in der Admin-GraphQL erst ab einer bestimmten API-Version.
- Offen: ob aktive Apps ohne zusätzlichen Scope lesbar sind.
- Nicht Lesbares kommt **nicht** in die Abfrage, sondern als offener Punkt in diese Skill.
- Prüfwerkzeug: Shopify-Dev-MCP.
- Absicherung im Script:
  - Block fehlt in der Antwort oder ist `null`: Vermerk in `notes`, **keine** Null. "Keine Skript-Tags installiert" ist ein Befund, "nicht lesbar" nicht.
  - Block kommt leer zurück: das ist eine Messung, kein Vermerk.

## Snapshot-Schema

`<out>/shop-tech.json`:

```json
{
  "source": "shop_tech",
  "summary": {"themes_total": 3, "script_tags_total": 4, "locales_total": 2,
               "markets_total": 1, "third_party_script_hosts": 12,
               "inline_tag_ids": 3, "crawl_pages_scanned": 300},
  "theme": {"name": "Dawn", "role": "MAIN", "updated_at": "..."},
  "themes": [{"name", "role"}],
  "script_tags": [{"src", "display_scope"}],
  "locales": [{"locale", "primary", "published"}],
  "markets": [{"name", "enabled", "primary"}],
  "payments": {"supported_digital_wallets": ["..."]},
  "storefront_script_hosts": {"connect.example": 300},
  "storefront_script_hosts_truncated": false,
  "storefront_inline_tag_ids": {"G-XXXX": 300, "GTM-YYYY": 300},
  "notes": []
}
```

### Regeln zum Schema

- **Mess-IDs zeigen das Konto**, Hosts nur den Anbieter.
  - Zwei GA4-IDs auf denselben 300 Seiten = doppelte Messung, ein Befund für die Analyse Datenqualität.
  - Je ID steht die Seitenzahl: drei von 300 Seiten = Rest, alle Seiten = aktiver zweiter Zähler.
- **`crawl_pages_scanned: null` = nicht gemessen**, 0 = gecrawlt ohne Fund. Davon hängt ab, ob die Analyse einen Befund oder eine Lücke schreibt.
- **Host-Liste auf 100 gekappt.** `third_party_script_hosts` im `summary` nennt die volle Menge, `_truncated` zeigt die Kürzung. Ohne Merker hielte der Leser 100 für alle.
- **Skript-Hosts zählen Seiten, nicht Einbindungen.** Zwei Snippets desselben Anbieters auf einer Seite = eine Seite. Gemessen wird die Verbreitung im Shop.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Gedrosselt** | Wie bei `pull-shopify`: warten, wiederholen. |
| **Block fehlt in der Antwort** | Vermerk in `notes`, kein Nullwert. Meist fehlt ein Scope oder der Feldname passt nicht zur API-Version. |
| **Kein Crawl im Lauf** | Storefront-Teil leer, `crawl_pages_scanned` = `null`, der Rest ist gültig. |
