---
name: pull-dfs-rankings
description: Zieht über DataForSEO die Ranking-Keywords einer Domain, den Share of Voice gegen die Wettbewerber und auf Wunsch die Sichtbarkeitshistorie und legt alles als Snapshot ab. Einsetzen, wenn ein Audit oder Report den organischen Ranking-Bestand braucht oder der Nutzer wissen will, für wie viele Keywords ein Shop rankt und wo er gegenüber dem Wettbewerb steht. Jeder Aufruf kostet, Obergrenze aus config.json > dfs_budget_usd. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-dfs-rankings: Ranking-Bestand und Sichtbarkeit ziehen

Zieht in einen Snapshot:

- organischen Ranking-Bestand der Domain
- geschätzten Traffic je Domain gegen die Wettbewerber (Share of Voice)
- optional die Sichtbarkeitshistorie

Aufruf durch den Audit-Lauf oder einzeln.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `domain`, `market` (`location_code` und `language_code`), `dfs_budget_usd` und `sources.dfs_rankings` ungleich `false`.
- `competitors` in der Config liefert die Vergleichsdomains für den Share of Voice.
- `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env`.

Fehlt etwas oder steht `sources.dfs_rankings` auf `false`: "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf scheitert nie daran.

## Kosten

**Jeder Aufruf kostet, Rechnung an den Betreiber.** Messung 12.08.2026 (interne Endpoint-Bewertung):

| Teil | Endpunkt | Kosten | Wann |
|---|---|---:|---|
| Bestand | `ranked_keywords/live` | 0,0144 USD | jeder Lauf |
| Share of Voice | `bulk_traffic_estimation/live` | 0,0126 USD je 5 Domains | jeder Lauf |
| Historie | `historical_rank_overview/live` | **0,127 USD** | nur mit `--with-history` |

- Historie: teuerste Labs-Abfrage, rund das Neunfache des Bestands. Laut Exploration einmalig nützlich, nicht für den Monats-Report. Nur im Erstlauf ziehen, nicht in der Kadenz.
- Im laufenden Betrieb ersetzt der Share of Voice die Historie; die Zeitreihe entsteht über die Läufe.
- Deckel aus `config.json > dfs_budget_usd`, Prüfung **vor** jedem Aufruf.
- Deckel erreicht: Abbruch vor dem Aufruf, Quelle `skipped` mit Grund, nicht `failed`.
- Jeder Aufruf schreibt eine Zeile in `reporting/dfs-ledger.jsonl` mit Tag, Endpunkt und echtem Betrag.
- `--sandbox` läuft gegen `sandbox.dataforseo.com`, kostenlos, mit **Dummy-Werten**. Nur als Rauchtest der Verkabelung, nie als Zahlenquelle. Ein solcher Snapshot hat `"sandbox": true` und kommt in keinen Kundenordner.

## `top_keywords` enthält nur Spitzenpositionen

- Messung an einem Shop (07.09.2026): **alle 500 gelieferten `top_keywords` lagen in den Top 10**, obwohl der Bestand ein Vielfaches umfasste.
- Positionen 11 bis 100 fehlen in der Liste.
- Eine Chancenliste "knapp vor Seite eins" lässt sich daraus nicht bilden; das Ergebnis wäre eine leere Tabelle ohne Fehlermeldung.
- **Striking-Distance-Begriffe aus der Search Console ziehen:** `gsc.json > top_queries[]` mit `position` zwischen 8 und 25, absteigend nach `impressions`. Gemessene Positionen, Impressionen als Gewicht, keine Zusatzkosten.
- `summary.ranked_keywords_total` zählt den vollständigen Bestand; nur die gelieferten Zeilen sind die Spitze.

## Ablauf

1. `reporting/config.json` lesen: `domain`, `market`, `competitors`, `dfs_budget_usd`. Zugangsdaten sucht das Skript selbst.
2. Script aufrufen. **Zielordner ist der Daten-Ordner des laufenden Audits** (`reporting/data/<run-id>`):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-dfs-rankings/scripts/rankings_pull.py" \
     --target <domain ohne Protokoll> \
     --competitors "<competitors, kommagetrennt>" \
     --workspace . --out "reporting/data/<run-id>" \
     --run-id <run-id> --run-date <YYYY-MM-DD> \
     --account-slug <account_slug> --budget-cap <dfs_budget_usd> \
     --location-code <market.location_code> --language-code <market.language_code>
   ```

   Optional: `--with-history` für die Sichtbarkeitshistorie (siehe Kosten), `--sandbox` für einen kostenlosen Rauchtest.
3. Dem Nutzer melden: Zahl der Ranking-Keywords, Top-3, Top-10, geschätzter Traffic, Position im Share of Voice, verbrauchter Betrag.

## Snapshot-Schema

`<out>/dfs-rankings.json`:

```json
{
  "source": "dfs_rankings", "endpoint": "...", "tag": "<kunde>/<datum>/dfs_rankings",
  "cost_usd": 0.027, "sandbox": false, "run_id": "...", "pulled_at": "...",
  "summary": {
    "ranked_keywords_total": 396, "ranked_keywords_delivered": 20,
    "top_3": 141, "top_10": 216, "top_100": 396,
    "etv": 13857.4, "is_new": 215, "is_up": 57, "is_down": 20, "is_lost": 0,
    "serp_features_in_sample": {"organic": 20}
  },
  "top_keywords": [{"keyword", "rank_absolute", "rank_group", "search_volume",
                     "cpc", "competition_level", "etv", "url", "serp_type",
                     "last_updated_time"}],
  "top_keywords_truncated": false,
  "share_of_voice": [{"domain", "etv", "ranked_keywords"}],
  "visibility_history": [{"month": "2026-08", "ranked_keywords", "etv"}],
  "notes": ["..."]
}
```

### Regeln zum Schema

1. **`ranked_keywords_total` = Bestand, `ranked_keywords_delivered` = Liefermenge.** Die API liefert höchstens tausend Zeilen je Aufruf, kennt aber den Bestand (geprüfte Antwort: 396 gegen 20). Den Zähler nie aus der Listenlänge bilden.
2. **Positionsbänder aus `metrics.organic`, nicht aus den Zeilen.** Die API liefert `pos_1`, `pos_2_3`, `pos_4_10` usw. über den Bestand. Die API-Bänder sind **disjunkt**; im Snapshot stehen sie kumuliert, da "Top 3" im Report kumulativ gelesen wird.
3. **Fehlt `metrics.organic`, sind die Bänder `null`, nicht 0.** Eine 0 hieße "kein Keyword in den Top 3".
4. **`rank_absolute` ist ein Datenbankwert, keine Live-Position.** Er wich am 12.08.2026 im Gegencheck von der Live-SERP ab. `last_updated_time` wird je Keyword mitgeliefert, `notes` weist darauf hin. Im Report nie als tagesaktuelle Position zeigen.

## Gegenprüfung mit der Search Console

Prüfung am 07.09.2026 gegen die Search Console derselben Domain als unabhängige Messung:

| Frage | Ergebnis |
|---|---|
| Gibt es überhaupt eine Schnittmenge? | Ja. Null Schnittmenge hieße, `location_code` oder `language_code` messen den falschen Markt |
| Liegen die Positionen in derselben Größenordnung? | Ja, Median-Abweichung rund **zwei Ränge** |
| Gibt es Ausreißer? | Ja, einer von zwölf weicht um mehr als 20 Ränge ab |
| Passt das Suchvolumen zu den Impressionen? | Ja, kein einziger Widerspruch: kein Keyword mit Volumen und Top-10-Position hatte null Impressionen |
| Ist `etv` eine Trafficzahl oder ein Preis? | **Trafficzahl.** Die Summe der Zeilen-`etv` ergibt exakt `summary.etv`, und die Größenordnung passt zu den GSC-Impressionen |

- Der Ausreißer folgt aus Regel 4: `rank_absolute` ist ein Datenbankwert mit eigenem `last_updated_time`.
- Bei rund zwei Rängen Median-Abweichung als Trend verwendbar, nie als tagesaktuelle Position.
- **Nicht gegengeprüft:** die Sichtbarkeitshistorie (`--with-history`); es fehlt eine zweite Quelle mit Monatsauflösung über denselben Zeitraum.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Budgetdeckel erreicht** | Abbruch vor dem Aufruf, Quelle "nicht verfügbar (Budgetdeckel)", der Lauf läuft weiter. |
| **Share of Voice oder Historie scheitern** | Ranking-Bestand bleibt, Snapshot ohne den Teil, Warnung auf der Konsole. |
| **Zugangsdaten fehlen** | Meldung nennt `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD`, Exit ungleich 0. |
| **Leeres Ergebnis** | Kein Fehler, sondern Befund: `ranked_keywords_total: 0` und leere Liste. |
