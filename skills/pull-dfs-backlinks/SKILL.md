---
name: pull-dfs-backlinks
description: Zieht über DataForSEO das Backlinkprofil einer Domain (Bestand, verweisende Domains, Ankertexte) samt normalisiertem Autoritäts-Score und Toxizitäts-Score im Vergleich zu den Wettbewerbern und schreibt das Ergebnis als Snapshot. Einsetzen, wenn ein Audit den Baseline-Block SEO Sichtbarkeit braucht oder der Nutzer Stärke und Sauberkeit des Linkprofils wissen will. Jeder Aufruf kostet, Obergrenze aus config.json > dfs_budget_usd. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-dfs-backlinks: Linkprofil, Autorität und Toxizität

Zieht das Backlinkprofil plus Autoritäts-Score und Toxizitäts-Score.

## Kennzahlen

- Rohe Backlink-Zahlen haben wenig Aussagekraft. Maßgeblich sind Autorität und Toxizität (Benchmark gegen Semrush und Ahrefs, interne Endpoint-Bewertung vom 12.08.2026); DataForSEO hat für beide ein Äquivalent.
- Beide Scores zusammen bestimmen die Maßnahme: hohe Toxizität heißt erst bereinigen, dann aufbauen. Niedrige Autorität allein heißt aufbauen.
- Fixtures aller Endpunkte liegen vor (Aufnahme 07.09.2026, rund 0,10 USD).

## Feld `dofollow` gibt es nicht

- Verweisende Domains haben **kein** Feld `dofollow`.
- Vorhanden sind `referring_pages` und `referring_pages_nofollow`.
- Wer `dofollow` liest, erhält in jeder Zeile `falsy` und eine Dofollow-Quote von **0,0**, auch bei einem Profil mit **83 Prozent** folgenden Links.

## Endpunkte und Kosten

Fünf Endpunkte, rund 0,12 USD.

| Teil | Endpunkt | Kosten | Wofür |
|---|---|---:|---|
| Profil | `backlinks/summary/live` | 0,024 USD | Bestand, Link-Typen, defekte Links |
| Domains | `backlinks/referring_domains/live` | 0,024 USD plus Zeilen | verweisende Domains |
| Anker | `backlinks/anchors/live` | 0,024 USD plus Zeilen | Ankertext-Verteilung |
| Autorität | `backlinks/bulk_ranks/live` | 0,024 USD je 5 Domains | eigener Score gegen Wettbewerber |
| Toxizität | `backlinks/bulk_spam_score/live` | 0,024 USD je 5 Domains | Disavow-Bedarf statt Linkaufbau |

- Kadenz: quartalsweise.
- Nur ein Fehler im Summary ist fatal. Scheitert einer der vier übrigen, wird der Snapshot ohne diesen Teil geschrieben.

## Voraussetzungen

- `reporting/config.json` mit `domain`, `competitors`, `dfs_budget_usd`, `sources.backlinks` ungleich `false`.
- `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env`.

## Ablauf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-dfs-backlinks/scripts/backlinks_pull.py" \
  --target <domain ohne Protokoll> \
  --competitors "<competitors, kommagetrennt, höchstens vier>" \
  --workspace . --out "reporting/data/<run-id>" \
  --run-id <run-id> --run-date <YYYY-MM-DD> \
  --account-slug <account_slug> --budget-cap <dfs_budget_usd> \
  --location-code <market.location_code> --language-code <market.language_code>
```

- **Wettbewerber mitgeben.** Ein Autoritäts-Score von 154 ist allein keine Aussage; erst gegen 391 und 423 zeigt er einen aufholbaren Rückstand.
- Die eigene Domain hat im Snapshot `own: true`.

## Snapshot-Schema

`<out>/dfs-backlinks.json`:

```json
{
  "summary": {"backlinks", "referring_domains", "referring_main_domains",
               "referring_ips", "rank", "broken_backlinks", "broken_pages",
               "link_types", "referring_domains_nofollow"},
  "summary_domains": {"referring_domains_returned": 310, "dofollow_share": 0.83,
                       "domains_without_follow_data": 0},
  "referring_domains_top": [{"domain", "backlinks", "rank", "follows",
                              "referring_pages", "referring_pages_nofollow",
                              "spam_score", "first_seen"}],
  "referring_domains_truncated": true,
  "summary_anchors": {"anchors_returned": 480},
  "anchors_top": [{"anchor", "backlinks", "referring_domains"}],
  "authority": [{"domain", "rank", "own"}],
  "spam_score": [{"domain", "spam_score", "own"}],
  "notes": []
}
```

### Regeln zum Schema

- **Quoten über die volle Menge, nie über die gekürzte Liste.** `dofollow_share` rechnet über alle gelieferten Domains; die Liste ist auf 200 gekappt.
- **Domain folgt**, wenn `referring_pages` größer ist als `referring_pages_nofollow`, also mindestens eine Seite folgt.
- Fehlen beide Felder, ist der Status unbekannt: weder folgend noch nicht folgend, Zählung in `domains_without_follow_data`.
- **Ohne verweisende Domains ist die Dofollow-Quote `null`**, nicht 0; eine 0 hieße "keine einzige folgt".
- **Toxizitäts-Score: `null` = nicht gemessen, `0` = sauber.** Davon hängt ab, ob eine Disavow-Empfehlung in den Report kommt.
- **Leeres Ergebnis ist ein Befund**, kein Fehler: Nullen plus Vermerk.

## Antwortformat (an echten Antworten geprüft)

- `referring_domains`, `anchors`, `bulk_ranks` und `bulk_spam_score` liefern unter `result[0].items`; nur `summary` ist flach.
- `_items()` liest genau diese Form. Keine Toleranz für eine zweite Form, sonst bleibt eine dritte unbemerkt.
- **Autoritäts-Score läuft bis 1.000** (geprüft an zwei großen Vergleichsdomains, 680 und 812). Nicht als 0 bis 100 lesen.
- **Alle übergebenen Domains kommen zurück** (drei von drei).
- **Toxizitäts-Score ist eine ganze Zahl von 0 bis 100.**
- Preis: **0,024 USD je Aufruf**, fünf Aufrufe rund 0,12 USD. `ESTIMATE_USD["backlinks"]` steht auf 0,15 inklusive Zuschlag.

## Prüfstand der Zahlen

Struktur geprüft, Zahlen teilweise:

| Frage | Stand |
|---|---|
| Skala des Autoritäts-Scores | geprüft: bis 1.000, an zwei großen Vergleichsdomains (680 und 812) |
| Kommen alle übergebenen Domains zurück? | geprüft: drei von drei |
| Dofollow-Quote | jetzt korrekt gerechnet, aber gegen keine zweite Quelle gehalten |
| Zahl der verweisenden Domains | **offen** |

### Domain-Zahl manuell abgleichen

Die Search-Console-API hat keinen Endpunkt für den Links-Bericht.

1. In der Search Console unter Links die Zahl der verweisenden Domains ablesen.
2. Mit `summary.referring_domains` vergleichen.
3. DataForSEO findet in der Regel **mehr** (eigener Index).
4. Findet es **weniger**, prüfen: `target` falsch geschrieben (mit `www.`, mit Protokoll) oder `backlinks_status_type` filtert zu viel.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Budgetdeckel erreicht** | Abbruch vor dem Aufruf, Quelle "nicht verfügbar". |
| **Ein Teil scheitert** | Nur das Summary ist fatal; die übrigen vier hinterlassen eine Warnung und einen Snapshot ohne diesen Teil. |
| **Keine Wettbewerber in der Config** | Autorität und Toxizität nur für die eigene Domain; die Analyse behandelt sie als Wert ohne Maßstab. |
