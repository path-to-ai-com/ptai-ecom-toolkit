---
name: pull-dfs-keywords
description: Zieht über DataForSEO Suchvolumen, Wettbewerb und Klickpreis für eine Begriffsliste aus den Keyword-Seeds der Config und den Top-Queries der Search Console und schreibt das Ergebnis als Snapshot. Einsetzen, wenn ein Audit Volumen zu Katalog- und Kategoriebegriffen braucht oder der Nutzer wissen will, wie oft ein Begriff gesucht wird. Kosten fallen je Anfrage an, nicht je Keyword; Obergrenze aus config.json > dfs_budget_usd. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-dfs-keywords: Suchvolumen zu einer Begriffsliste

Holt Suchvolumen, Wettbewerbsgrad und Klickpreis für alle Begriffe des Laufs:

- Keyword-Seeds aus der Config
- Top-Queries aus `gsc.json` desselben Laufs

Referenz-Fixture: `scripts/tests/fixtures/dfs/search_volume.json` (Aufnahme 07.09.2026, 0,09 USD).

## Kosten je Anfrage

- Eine Anfrage kostet gleich viel, ob mit einem oder tausend Keywords.
- Darum: erst sammeln, dann entdoppeln, dann in Blöcken zu 1.000 senden. Ein Aufruf je Keyword wäre tausendmal so teuer.
- Entdoppeln ohne Rücksicht auf Groß- und Kleinschreibung: "Regenjacke" und "regenjacke" sind für den Endpunkt ein Keyword und würden in zwei Blöcken doppelt bezahlt.
- Begriffe über 80 Zeichen vorher entfernen; ein API-Fehler kostet die ganze bezahlte Anfrage.

## Voraussetzungen

- `reporting/config.json` mit `keyword_seeds`, `market`, `dfs_budget_usd`, `sources.dfs_keywords` ungleich `false`.
- `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env`.
- **Erst nach `pull-gsc` starten**, der Pull nutzt dessen Top-Queries.

## Ablauf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-dfs-keywords/scripts/keywords_pull.py" \
  --seeds "<keyword_seeds, kommagetrennt>" \
  --gsc "reporting/data/<run-id>/gsc-max-history.json" \
  --workspace . --out "reporting/data/<run-id>" \
  --run-id <run-id> --run-date <YYYY-MM-DD> \
  --account-slug <account_slug> --budget-cap <dfs_budget_usd> \
  --location-code <market.location_code> --language-code <market.language_code>
```

## Snapshot-Schema

`<out>/dfs-keywords.json`:

```json
{
  "summary": {"keywords_returned": 412, "keywords_with_volume": 380,
               "keywords_without_data": 12, "search_volume_total": 184300},
  "keywords": [{"keyword", "search_volume", "competition", "competition_index",
                 "cpc", "monthly": [{"month": "2026-08", "search_volume"}]}],
  "keywords_truncated": false,
  "notes": ["..."]
}
```

### Regeln zum Schema

| Wert | Bedeutung | Zähler |
|---|---|---|
| `search_volume: null` | Google liefert keine Zahl, im Report "ungemessen" | `keywords_without_data` |
| `search_volume: 0` | kein Suchvolumen, im Report "toter Begriff" | `keywords_with_volume` |

- Sortierung: Volumen absteigend, ungemessene Begriffe am Ende.
- Liste auf 1.000 gekappt; `keywords_returned` nennt die Gesamtmenge.
- **Abgebrochener Block = Lücke, keine Null.** Stoppt der Budgetdeckel mitten in der Blockfolge, vermerkt `notes`, dass die Begriffe der restlichen Blöcke **ungemessen** sind. Bereits gezogene Begriffe bleiben im Snapshot.

## Antwortformat des Endpunkts

- Zeilen liegen **flach in `result`**, nicht unter `result[0].items` wie bei den DataForSEO-Labs-Endpunkten. `dfs_pull.unwrap()` findet hier nichts und ergibt null Keywords im Snapshot.
- Feldnamen: `keyword`, `search_volume`, `competition`, `competition_index`, `cpc`, `monthly_searches` mit `year`, `month`, `search_volume`.
- Die Monatsreihe hat zwölf Einträge.
- `tag` wird gespiegelt.
- Preis: **0,09 USD** für vier Keywords, also je Anfrage. `ESTIMATE_USD["dfs_keywords"]` steht auf 0,15 inklusive Zuschlag.
- Offen: ob der Preis bei tausend Keywords je Anfrage gleich bleibt. Laut Doku ja, gemessen nur für vier.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Keine Begriffe** | Abbruch mit Meldung; eine leere Anfrage kostet so viel wie eine volle. |
| **Budgetdeckel erreicht** | Vor dem ersten Block: Abbruch. Mitten in der Blockfolge: Vermerk plus die bereits gezogenen Begriffe. |
| **Zugangsdaten fehlen** | Meldung nennt `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD`. |
