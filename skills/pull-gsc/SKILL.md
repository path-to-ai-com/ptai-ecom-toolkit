---
name: pull-gsc
description: Zieht Search-Console-Daten für den Kunden-Report oder den Wochen-Puls (Top-Queries, Top-Seiten, Tagesreihe, Sitemaps, Index-Stichprobe) und legt sie als Snapshot ab. Einsetzen, wenn ein Monats-Report oder Puls GSC-Zahlen braucht oder der Nutzer ausdrücklich Search-Console- oder GSC-Daten für einen Zeitraum abrufen will. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-gsc: Search-Console-Snapshot ziehen

Zieht per Search Console API:

- Suchleistung eines Zeitraums (Top-Queries, Top-Seiten, Tagesreihe)
- Indexierungs-Stand (Sitemaps, URL-Stichprobe)

Ablage als Snapshot im Kunden-Workspace. Aufruf durch Report- und Puls-Lauf oder einzeln.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `gsc_site` (z. B. `sc-domain:example.de`) und `sources.gsc` ungleich `false`.
- `cwv_urls` in der Config liefert die Index-Stichprobe.
- `.env` im Workspace-Root mit `PTAI_GOOGLE_CREDENTIALS` (Pfad zum Service-Account-JSON).

Fehlt etwas oder steht `sources.gsc` auf `false`: GSC als "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf (Report/Puls) scheitert nie daran.

## Ablauf

1. `reporting/config.json` lesen (`gsc_site`, `cwv_urls`), `.env` sourcen (`PTAI_GOOGLE_CREDENTIALS`).
2. Zeitraum festlegen:
   - Standard: letzter voller Monat (Erster bis Letzter des Vormonats).
   - Puls-Modus: letzte volle Woche, Montag bis Sonntag.
3. Vergleichszeitraum nur im Erstlauf:
   - Vormonats-Snapshot vorhanden (jüngster `reporting/data/`-Ordner mit `gsc.json`, deren `period` granularity `month` über den vollen Vormonat hat; `-pulse`-Dateien ignorieren): keinen Vergleich ziehen, der Report vergleicht gegen den Snapshot.
   - Kein Snapshot vorhanden: den Monat davor als `--compare-start/--compare-end` mitgeben.
4. Script aufrufen.
   - **Zielordner ist der Daten-Ordner des laufenden Audits oder Reports** (`reporting/data/<run-id>`); ohne Lauf-ID der heutige Daten-Ordner wie im Beispiel (siehe Snapshot-Schema).
   - `--inspect-urls` = `cwv_urls` aus der Config, kommagetrennt in einem Argument (gleiche Stichprobe wie beim CWV-Pull, keine zweite Liste pflegen).

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-gsc/scripts/gsc_pull.py" \
     --site <gsc_site> \
     --creds "$PTAI_GOOGLE_CREDENTIALS" \
     --start YYYY-MM-01 --end <letzter Tag des Monats> \
     --inspect-urls "<cwv_urls, kommagetrennt>" \
     --out "reporting/data/$(date +%F)"
   ```

   Optionen:

   | Option | Wirkung |
   |---|---|
   | `--compare-start YYYY-MM-DD --compare-end YYYY-MM-DD` | Vergleich (Erstlauf) |
   | `--pulse` | Wochen-Puls, schreibt `gsc-pulse.json` mit granularity `week` |
   | `--max-history` | einmaliger Baseline-Pull über die ganze vorhandene Historie; ohne `--start`, das Script ermittelt den Beginn; schreibt `gsc-max-history.json` mit granularity `max_history`; nicht kombinierbar mit `--pulse` und `--compare-start`/`--compare-end` |

5. Dem Nutzer melden: Klicks, Impressionen, CTR, Position, Top-Query, Auffälligkeiten der Index-Stichprobe (alles Nicht-Indexierte). Bei Vergleich die Richtung (mehr/weniger).

## Snapshot-Schema

### Zielordner

- Der Aufrufer bestimmt den Zielordner.
- Solo: Vorgabe `reporting/data/<heute>`. Dort legen auch `report` und `pulse` ab, solange sie ohne Lauf-ID laufen (Spec Abschnitt 14, Umstellung in Stufe 3).
- **In einem Audit oder Report mit Lauf-ID: `reporting/data/<run-id>`**, Datum plus Kadenz (`2026-10-01-audit`, `2026-11-01-month`). `--out` zeigt dorthin.
- Der Orchestrator gibt den Ordner vor. Bei manuellem Start während eines Laufs dieselbe Lauf-ID verwenden.
- Ein Snapshot im falschen Ordner fehlt der Analyse, und sie rechnet ohne Fehlermeldung weiter.

### Datei

Das Script schreibt `<out>/gsc.json` (oder `gsc-pulse.json`, bei `--max-history` `gsc-max-history.json`):

```json
{
  "period": {"start": "...", "end": "...", "granularity": "month"},
  "totals": {"clicks", "impressions", "ctr", "position"},
  "top_queries": [{"query", "clicks", "impressions", "ctr", "position"}],
  "top_pages": [{"page", "clicks", "impressions", "ctr", "position"}],
  "query_pages": [{"query", "page", "clicks", "impressions", "ctr", "position"}],
  "top_countries": [{"country", "clicks", "impressions", "ctr", "position"}],
  "devices": [{"device", "clicks", "impressions", "ctr", "position"}],
  "search_types": [{"search_type", "clicks", "impressions", "ctr", "position"}],
  "daily": [{"date", "clicks", "impressions", "ctr", "position"}],
  "by_month": [{"month": "2026-08", "clicks", "impressions", "ctr", "position"}],
  "sitemaps": [{"path", "last_submitted", "is_pending", "errors", "warnings"}],
  "index_sample": [{"url", "verdict", "coverage_state", "last_crawl_time"}],
  "comparison": { "totals, top_queries, top_pages, top_countries, devices, search_types, daily plus eigener period, nur bei --compare-*": "..." },
  "history_from": "nur bei --max-history: gemessenes ältestes Datum mit Daten"
}
```

### Regeln zum Schema

**`comparison`**

- Immer in derselben Datei, nie als eigene Datei oder eigener Ordner.
- Ohne `sitemaps` und `index_sample`; beide sind Momentaufnahmen und stehen nur im Hauptteil.
- Puls-Dateien überschreiben nie die Monats-Vergleichsbasis.

**Teilfehler**

- Gescheiterte Inspektion: `{"url", "error"}` im `index_sample`.
- Gescheiterte Sitemap-Liste: `{"error": "..."}` unter `sitemaps`; Suchdaten bleiben unberührt.

**`by_month`**

- Tagesreihe, zu Kalendermonaten verdichtet, chronologisch, Monat zweistellig.
- Die Baseline verlangt Klicks, Impressionen, CTR und Position **je Monat** (Spec Abschnitt 10); aus einer Gesamtsumme lässt sich kein Vergleich gegen denselben Kalendermonat rechnen.
- CTR und Position neu rechnen, nie mitteln. Position = impressionsgewichteter Mittelwert, wie in `totals`.
- Monat ohne Impressionen: `position: null`, nicht 0 (0 stünde im Report besser als Platz 1).

**`query_pages`**

- Paare aus Anfrage und rankender Seite, Top 250 nach Klicks.
- Einzige Quelle für die Zuordnung Seite zu Anfrage.
- Scheitert dieser Abruf: `null`, der Rest bleibt gültig. Dann sind `con.query-page-type` und das zweite Signal der Kannibalisierung nicht messbar.

**`top_countries`, `devices`, `search_types`**

- `top_countries` und `devices` kommen aus API-Dimensionen, wie `top_queries` und `top_pages`.
- Suchtyp ist in der Search-Analytics-API nur Filter (`type`, ehemals `searchType`), keine Dimension. Daher ein Query je Typ (web, image, video, news, discover, googleNews).
- Typ ohne Daten im Zeitraum fehlt in der Liste.

**`history_from`**

- Nur in `gsc-max-history.json`.
- Gemessen: das Script fragt deutlich weiter zurück als die dokumentierten 16 Monate und nimmt das älteste Datum mit einer Zeile.
- Gleich `period.start`, da der Lauf die gesamte Historie abdeckt.

## Setup-Check

`--check` testet Auth plus eine 1-Tages-Mini-Query (Exit 0/1), für den Setup-Wizard:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-gsc/scripts/gsc_pull.py" \
  --site <gsc_site> --creds "$PTAI_GOOGLE_CREDENTIALS" --check
```

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| `google-auth fehlt` | `pip3 install --user google-auth requests`, erneut starten. |
| 403/Permission denied | Service-Account-Mail ohne Lesezugriff auf die Property. In der Search Console unter Einstellungen, Nutzer und Berechtigungen freigeben. |
| `error`-Objekt unter `sitemaps` oder `error`-Einträge im `index_sample` | Nicht fatal, der Rest ist vollständig. |
| `error`-Objekt unter `comparison` | Vergleichs-Pull gescheitert, nicht fatal, Hauptteil vollständig. Der Report zieht den Vergleich später live oder lässt die Delta-Spalte weg. |
| Offener Punkt Pilot | Ob der readonly-Scope `webmasters.readonly` für die URL-Inspection-API reicht, wird im Pilot gegen die API validiert. Scheitert die Stichprobe daran flächig: im Report "Index-Stichprobe nicht verfügbar". |
