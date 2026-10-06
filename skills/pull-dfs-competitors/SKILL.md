---
name: pull-dfs-competitors
description: Ermittelt die Wettbewerber einer Brand aus der SERP-Überschneidung ihrer Kategorie-Keywords, zieht auf Wunsch die Keyword-Lücken zum stärksten Wettbewerber und schreibt das Ergebnis als Snapshot. Einsetzen, wenn ein Audit eine Wettbewerberliste braucht, der Nutzer wissen will, wer für die Kategorie-Begriffe rankt, oder ein Content-Gap gesucht ist. Jeder Aufruf kostet, Obergrenze aus config.json > dfs_budget_usd. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-dfs-competitors: Wettbewerber und Keyword-Lücken

Liefert:

- wer für die Kategorie-Keywords der Brand rankt
- optional: Keywords, für die der stärkste Wettbewerber rankt und die eigene Domain nicht

## Seed: Kategorie-Keywords, nicht die eigene Domain

Beide Endpunkte liefern "Wettbewerber" zum gleichen Preis. Vergleich aus der internen Exploration vom 12.08.2026:

| Endpunkt | Gesät mit | Ergebnis im Test | Urteil |
|---|---|---|---|
| `serp_competitors/live` | Kategorie-Keywords | 8 von 9 Wettbewerbern aus der manuellen Analyse wiedergefunden, plus zwei neue | **der richtige Weg** |
| `competitors_domain/live` | der eigenen Domain | ein soziales Netz, eine Stadt-Domain, eine Auktionsplattform | Rauschen |

- `competitors_domain` sucht Überschneidungen im **eigenen** Ranking-Set.
- Bei einer Brand ohne nennenswerte Rankings bleiben nur die Marken-Keywords, und die überschneiden sich vor allem mit Plattformen, auf denen die Marke ein Profil hat.
- **Diese Skill nutzt `competitors_domain` nicht.**

## Voraussetzungen

- `reporting/config.json` mit `domain`, `market`, `geo_queries.category` (Seed-Keywords), `dfs_budget_usd`, `sources.competitors` ungleich `false`.
- `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env`.

## Kosten

| Teil | Endpunkt | Kosten |
|---|---|---:|
| Wettbewerber | `serp_competitors/live` | 0,014 USD |
| Keyword-Lücken | `domain_intersection/live` | 0,016 USD, nur mit `--with-gaps` |

- Kadenz: quartalsweise.
- Deckel aus `dfs_budget_usd`, Prüfung vor jedem Aufruf.
- Jeder Aufruf schreibt eine Zeile in `reporting/dfs-ledger.jsonl`.
- `--with-gaps` ist standardmäßig aus: der Audit braucht zuerst die Liste, die Lücken setzen einen benannten Wettbewerber voraus.

## Ablauf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-dfs-competitors/scripts/competitors_pull.py" \
  --target <domain ohne Protokoll> \
  --seed-keywords "<geo_queries.category, kommagetrennt>" \
  --workspace . --out "reporting/data/<run-id>" \
  --run-id <run-id> --run-date <YYYY-MM-DD> \
  --account-slug <account_slug> --budget-cap <dfs_budget_usd> \
  --location-code <market.location_code> --language-code <market.language_code>
```

- **Keine Markenbegriffe in den Seeds.** Mit dem Markennamen kommen die Plattformen zurück, auf denen die Marke ein Profil hat.
- Kommen nur Plattformen zurück, vermerkt der Snapshot das in `notes`. Dann mit Kategorie-Begriffen neu säen.

## Snapshot-Schema

`<out>/dfs-competitors.json`:

```json
{
  "summary": {"competitors_found": 84, "competitors_delivered": 20,
               "competitors_without_platforms": 18, "seed_keywords": ["..."]},
  "competitors": [{"domain", "avg_position", "median_position", "rating",
                    "etv", "keywords_count", "visibility", "is_platform"}],
  "competitors_truncated": false,
  "keyword_gaps": [{"keyword", "search_volume", "competitor_rank", "competitor_url"}],
  "summary_gaps": {"keyword_gaps_found": 436, "keyword_gaps_delivered": 30,
                    "compared_against": "wettbewerb-a.example"},
  "notes": []
}
```

### Regeln zum Schema

| Feld | Bedeutung |
|---|---|
| `competitors_found` | Bestand laut API |
| `competitors_delivered` | Liefermenge dieses Aufrufs |
| `competitors_truncated` | ob **diese Skill** danach gekürzt hat |

- Ohne `competitors_delivered` wirkt "84 gefunden, 20 gelistet, nicht gekürzt" widersprüchlich.
- **Sortierung nach `avg_position` aufsteigend**, nicht nach API-Reihenfolge; die kann sich unbemerkt ändern. Domains ohne Position ans Ende.
- **Plattformen markieren, nicht löschen.** Ein Marktplatz vor der Brand ist selbst ein Befund. `is_platform` kennzeichnet sie, `competitors_without_platforms` zählt die Shops.
- **Eigene Domain entfernen.** Der Endpunkt liefert sie mit, sobald sie für die Seeds rankt; sonst stünde der Shop als eigener Wettbewerber im Report.

## Keyword-Lücken: Richtung

- `intersections: false` liefert Keywords, für die **`target1` rankt und `target2` nicht**.
- Lücke = "Wettbewerber rankt, wir nicht". Also **Wettbewerber auf `target1`**, eigene Domain auf `target2`.
- Vertauscht liefert der Aufruf die eigenen Stärken, die dann fälschlich als "Keyword-Lücken" im Report stünden.
- Position aus `first_domain_serp_element` lesen. `second_domain_serp_element` ist hier in jeder Zeile `null`, weil die eigene Domain dort nicht rankt.
- Lücken nur gegen einen **Shop** rechnen, nie gegen eine Plattform. Ist der Vergleichspartner eine Plattform, überspringt der Pull die Lücken mit Warnung.

## Liste ist ein Vorschlag

- Welche Domains als Wettbewerber gelten, entscheidet der Mensch.
- Die Entscheidung wird laut Spec Abschnitt 10 mit der Baseline eingefroren.
- Diese Skill schreibt **nie** in `config.json > competitors`.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Budgetdeckel erreicht** | Abbruch vor dem Aufruf, Quelle "nicht verfügbar (Budgetdeckel)", der Lauf läuft weiter. |
| **Keine Seed-Keywords** | Abbruch mit Meldung; ein leerer Aufruf kostet so viel wie ein voller. |
| **Nur Plattformen im Ergebnis** | Kein Fehler: Vermerk in `notes` plus Hinweis, mit Kategorie-Begriffen neu zu säen. |
| **Kein Shop für die Lücken** | Lücken übersprungen, Wettbewerber-Teil bleibt. |
