---
name: pull-dfs-shopping
description: Zieht über die DataForSEO Merchant API, ob eine Brand bei Google Shopping gelistet ist und wie ihre Preise gegen die dort gelisteten Anbieter liegen, und schreibt das Ergebnis als Snapshot. Einsetzen, wenn ein Audit die Shopping-Präsenz der Brand und die Preise des Wettbewerbs dort braucht. Arbeitet task-basiert mit Wartezeit, jede Aufgabe kostet, Obergrenze aus config.json > dfs_budget_usd. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-dfs-shopping: Shopping-Präsenz und Preislandkarte

Fragt Google Shopping je Keyword ab. Ergebnis:

- Ist die Brand gelistet?
- Welche Preise hat der Wettbewerb?

## Task-basierter Ablauf

Dies ist der einzige task-basierte Pull.

1. `task_post` legt je Keyword eine Aufgabe an.
2. Warten.
3. `task_get/advanced` holt das Ergebnis.

| Schritt | Kosten |
|---|---|
| `task_post` | rund 0,001 USD je Aufgabe (Messung 12.08.2026) |
| `task_get/advanced` | keine |

- Ledger: eine Zeile je Post, keine je Abholung.
- Laufzeit deutlich länger als bei den anderen Pulls, darum an den **Anfang** von Phase 1 setzen.
- Kadenz: quartalsweise.

## Voraussetzungen

- `reporting/config.json` mit `brand`, `market`, `dfs_budget_usd`, `sources.shopping` ungleich `false` und den zu prüfenden Keywords.
- `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env`.

## Ablauf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-dfs-shopping/scripts/shopping_pull.py" \
  --keywords "<kommagetrennt, höchstens 20>" --brand "<config.brand>" \
  --workspace . --out "reporting/data/<run-id>" \
  --run-id <run-id> --run-date <YYYY-MM-DD> \
  --account-slug <account_slug> --budget-cap <dfs_budget_usd> \
  --location-code <market.location_code> --language-code <market.language_code>
```

## Snapshot-Schema

`<out>/dfs-shopping.json`:

```json
{
  "summary": {"keywords_checked": 1, "offers_total": 40, "own_offers": 0,
               "competitor_offers": 40, "carousel_entries": 3,
               "currencies": ["EUR"], "brand_match": "beispielshop"},
  "keywords": [{"keyword", "offers": [{"seller", "title", "price", "currency",
                                        "old_price", "rank_absolute", "own"}],
                 "offers_truncated": true, "offers_total": 40,
                 "own_price_vs_median": null}],
  "notes": ["..."]
}
```

### Regeln zum Schema

- **Angebot ist nur `google_shopping_serp`.** `google_shopping_carousel` sind Kategoriekacheln ohne Preis und Verkäufer (in der geprüften Antwort 3 von 43 Einträgen). Sie zählen separat als `carousel_entries`, sonst wäre die Angebotszahl zu hoch. Ohne sie gilt `own_offers + competitor_offers == offers_total`.
- **`own_price_vs_median` ist `null` ohne eigenes Angebot.** Eine 0 hieße "gleich teuer wie der Markt", nicht "nicht gelistet".
- Verglichen wird das **günstigste** eigene Angebot mit dem Median der übrigen Anbieter, da Käufer das günstigste zuerst sehen.
- **Mehrere Währungen werden vermerkt.** Über zwei Währungen gibt es keinen Preisabstand; `currencies` listet die enthaltenen.
- **Kein eigenes Angebot ist ein Befund, kein Fehler.** `own_offers: 0` bei 40 fremden Angeboten bedeutet: der Wettbewerb ist bei Shopping sichtbar, die Brand nicht.

## Marken-Erkennung (Heuristik)

- Eigenes Angebot = Verkäuferfeld enthält den Markennamen aus `config.brand`, Groß- und Kleinschreibung egal.
- Verkauft ein Shop unter mehreren Namen oder über Reseller, wird er **unterzählt**.
- Der Snapshot vermerkt das in `notes`, damit die Analyse es nicht als Tatsache nimmt.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Budgetdeckel erreicht** | Abbruch vor dem `task_post`, nichts ausgegeben. |
| **Aufgabe abgelehnt** | Übersprungen, nicht abgefragt; sonst würde sie dreißigmal gepollt und den Lauf zehn Minuten aufhalten. |
| **Nicht rechtzeitig abgeholt** | Betroffene Keywords stehen in `notes` als **ungemessen**, nicht als "ohne Angebote". Davon hängt ab, ob die Analyse einen Befund oder eine Lücke schreibt. |
