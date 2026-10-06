---
name: pull-ga4
description: Zieht GA4-Daten für den Kunden-Report oder den Wochen-Puls (Kanäle, Landingpages, E-Commerce-Funnel) und legt sie als Snapshot ab. Einsetzen, wenn ein Monats-Report oder Puls GA4-Zahlen braucht oder der Nutzer ausdrücklich GA4- oder Analytics-Daten für einen Zeitraum abrufen will. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-ga4: GA4-Snapshot ziehen

Zieht per Analytics Data API diese Sichten für einen Zeitraum: Kanäle, Kampagnen, Geräte, Länder, Landingpages, Funnel, interne Suchbegriffe. Ablage als Snapshot im Kunden-Workspace. Aufruf durch Report- und Puls-Lauf oder einzeln.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `ga4_property_id` und `sources.ga4` ungleich `false`.
- `.env` im Workspace-Root mit `PTAI_GOOGLE_CREDENTIALS` (Pfad zum Service-Account-JSON).

Fehlt etwas oder steht `sources.ga4` auf `false`: GA4 als "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf (Report/Puls) scheitert nie daran.

## Mehrere Properties

- Ein Shop kann denselben Kauf an mehrere GA4-Properties senden. Häufig: ein serverseitiges Werkzeug (Littledata, Elevar, Analyzify) neben dem clientseitigen Tag, mit eigener Property.
- Der Pull zieht genau eine Property. Ohne Vergleich bleibt die andere unsichtbar, und ein Kaufausfall in der gezogenen Property wird fälschlich als Messausfall gemeldet.

```
--compare-properties 987654321,123456789
```

- Liste aus `reporting/config.json > ga4_compare_properties`.
- Je Property steht unter `compare_properties` eine Monatsreihe aus Sitzungen, Käufen und Umsatz plus Währung der Property.
- Die Analysen nutzen weiter die Hauptproperty. Der Vergleich beantwortet nur: **welche Property stimmt mit dem Shop überein?**

## Käufe und Umsatz

**Käufe**

- Quelle: Metrik `ecommercePurchases`, im Snapshot als `purchases`. **Nie `transactions`.**
- `transactions` zählt auch `refund`-Ereignisse; serverseitige Connectoren wie Littledata senden Refunds.
- Prüfung am 11.09.2026 an zwei Properties: `ecommercePurchases` = Zahl der `purchase`-Ereignisse in jedem Monat; `transactions` = Käufe plus Refunds.
- **Snapshots vor dem 11.09.2026 enthalten `transactions`** samt Refunds. Kein Script liest das Feld als Käufe; der Report zeigt dafür "nicht messbar". Für alte Läufe Käufe neu ziehen, `transactions` nicht umdeuten.

**Umsatz**

- **`purchase_revenue` = Umsatz minus Erstattungen, in der Währung der Property.** `purchaseRevenue` war am 11.09.2026 in jedem Monat `grossPurchaseRevenue` minus `refundAmount`.
- Property ohne `refund`-Ereignisse: Bruttoumsatz. Property mit: Nettoumsatz.
- Erstattungen zählen am Datum des `refund`-Ereignisses, nicht der Bestellung.
- Währung = Berichtswährung der Property, nicht die des Shops (gefunden: Property in USD neben Shop in Euro). Sie steht als `currency` im Snapshot und je Vergleichs-Property.
- **Umsatz nur gegen Shopify vergleichen, wenn `currency` die Shop-Währung ist.**

## Ablauf

1. `reporting/config.json` lesen (`ga4_property_id`), `.env` sourcen (`PTAI_GOOGLE_CREDENTIALS`).
2. Zeitraum festlegen:
   - Standard: letzter voller Monat (Erster bis Letzter des Vormonats).
   - Puls-Modus: letzte volle Woche, Montag bis Sonntag.
3. Vergleichszeitraum nur im Erstlauf:
   - Vormonats-Snapshot vorhanden (jüngster `reporting/data/`-Ordner mit `ga4.json`, deren `period` granularity `month` über den vollen Vormonat hat; `-pulse`-Dateien ignorieren): keinen Vergleich ziehen, der Report vergleicht gegen den Snapshot.
   - Kein Snapshot vorhanden: den Monat davor als `--compare-start/--compare-end` mitgeben.
4. Script aufrufen. **Zielordner ist der Daten-Ordner des laufenden Audits oder Reports** (`reporting/data/<run-id>`); ohne Lauf-ID der heutige Daten-Ordner wie im Beispiel (siehe Snapshot-Schema):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ga4/scripts/ga4_pull.py" \
     --property <ga4_property_id> \
     --creds "$PTAI_GOOGLE_CREDENTIALS" \
     --start YYYY-MM-01 --end <letzter Tag des Monats> \
     --out "reporting/data/$(date +%F)"
   ```

   Optionen:

   | Option | Wirkung |
   |---|---|
   | `--compare-start YYYY-MM-DD --compare-end YYYY-MM-DD` | Vergleich (Erstlauf) |
   | `--pulse` | Wochen-Puls, schreibt `ga4-pulse.json` mit granularity `week` |
   | `--config reporting/config.json` | Bot-Filter, siehe unten |

   **Hat die `config.json` einen `bot_filter`-Block, `--config` an jeden Aufruf hängen.** Sonst zieht der Lauf ungefiltert und vergleicht später gefiltert gegen ungefiltert.
5. Dem Nutzer melden: Sessions, Nutzer, Umsatz, Funnel-Schritte, Top-Kanal. Bei Vergleich die Richtung (mehr/weniger). Bei `--max-history` zusätzlich `history_from` (gemessener Beginn der Historie).

## Maximalzeitraum

Einmalige Baseline über die volle verfügbare Historie: `--max-history` statt `--start`. `--end` ist optional (Standard: gestern, wie bei `--check`).

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ga4/scripts/ga4_pull.py" \
  --property <ga4_property_id> \
  --creds "$PTAI_GOOGLE_CREDENTIALS" \
  --max-history \
  --out "reporting/data/$(date +%F)"
```

- Zielordner wie bei jedem Lauf, im Audit `reporting/data/<run-id>` statt des Tagesordners im Beispiel.
- Ausgabe: `ga4-max-history.json` mit granularity `max_history`, neben einem eventuell vorhandenen `ga4.json`.
- Nicht kombinierbar mit `--start`, `--compare-start`/`--compare-end` und `--pulse`; das Script bricht mit Fehlermeldung ab.
- Die Aufbewahrungseinstellung (2 oder 14 Monate) betrifft vor allem nutzer- und ereignisbezogene Abfragen. Aggregierte Standarddimensionen (Kanal, Kampagne, Gerät, Land) reichen oft weiter zurück, je Property verschieden.
- Darum wird der Beginn gemessen: das Script fragt einen sehr weiten Zeitraum ab und nimmt den ersten Tag mit Zeilen.
- Dieser Tag steht als `history_from` im Snapshot, ohne Bot-Filter gemessen, damit eine Kundenregel die Messung nicht verzerrt.

## Bot-Filter

- Automatisierter Traffic erscheint in GA4 als normale Session: Sessions steigen, Verweildauer sinkt, Funnel-Basis steigt.
- Die GA4-Bot-Erkennung deckt nur die IAB-Liste ab; headless Chrome und Scraper kommen durch.
- Darum ein kundenspezifischer Filter in `reporting/config.json`:

```json
"bot_filter": {
  "enabled": true,
  "since": "2026-08-26",
  "note": "Warum, mit den Zahlen, die den Verdacht belegen",
  "exclude": [
    {
      "reason": "Direct und Unassigned von ausserhalb DACH: automatisierter Traffic",
      "country_not_in": ["Germany", "Austria", "Switzerland"],
      "channel_in": ["Direct", "Unassigned"]
    }
  ]
}
```

### Regellogik

- Bedingungen innerhalb einer Regel: UND.
- Regeln untereinander: ODER.
- Passende Sessions fallen aus allen Sichten (Kanäle, Kampagnen, Geräte, Länder, Landingpages, Funnel, interne Suchbegriffe).
- Erlaubte Bedingungen: `country_in`, `country_not_in`, `channel_in`, `channel_not_in`, `device_in`, `source_in`, `operating_system_in`, `browser_in`, `screen_resolution_in`.
- Ohne `enabled: true` keine Wirkung.
- `history_from` bei `--max-history` bleibt ungefiltert (siehe oben).

### Regeln für Regeln

- **Muster beschreiben, nie ein ganzes Land.** Ein Länder-Ausschluss entfernt echte Besuche (Beispiel: ein reiner US-Ausschluss hätte bei Beispielshop elf echte Organic-Search-Sessions mit 40,7 Sekunden und 4,27 Seiten pro Besuch entfernt). Herkunft plus Kanal trifft nur die Bots.
- **Nie einen ganzen Kanal ausschließen.** Sonst fallen die echten Besuche samt Käufen raus, während Bots in anderen Kanälen (etwa Unassigned) bleiben. Bots sind oft ein Geräteprofil, kein Kanal.
- Den Filtervorschlag liefert `--audit-checks` als `bot_profiles.filter_proposal` mit `enabled: false`. Ein Mensch übernimmt ihn, nachdem er Anteil, Engagement, Käufe und Zeiträume des Profils gelesen hat.
- **Zahlen vor und nach Einführung des Filters sind nicht vergleichbar.** Jeder gefilterte Snapshot enthält die Regeln unter `filters`, die Config das Datum `since`. Ein Report, der über diese Grenze vergleicht, nennt sie, statt den Sprung als Entwicklung darzustellen.

## Bot-Profile und Absender (`--audit-checks`)

- Pflicht in jedem Audit, nicht für Report und Puls.
- Mit `--pulse` bricht das Script ab; ein zweiter Absender zählt erst ab einer Woche.
- Hängt drei Abschnitte an den Snapshot, bevor eine Analyse eine Rate aus GA4 rechnet.
- Grund: Bot-Profile und doppelte Absender verzerren Add-to-Cart-Rate, Conversion Rate und Einstiegsseiten-Befunde und sind im Hauptteil nicht erkennbar.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ga4/scripts/ga4_pull.py" \
  --property <ga4_property_id> \
  --creds "$PTAI_GOOGLE_CREDENTIALS" \
  --max-history --audit-checks \
  --out "reporting/data/<run-id>"
```

### `bot_profiles`: Geräteprofile mit Bot-Merkmalen

- Profil = Bildschirmauflösung + Betriebssystem + Gerätekategorie + Browser.
- Der Pull zieht Sitzungen je Tag und Profil, zählt Kandidaten über den ganzen Zeitraum nach, Urteil durch `audit/bots.py`.
- Auffällig, wenn alles zutrifft:
  - mindestens ein Prozent aller Sitzungen
  - Engagement Rate unter 20 Prozent
  - höchstens ein Kauf auf 10.000 Sitzungen
- `windows` = Zeiträume mit ungewöhnlichem Tagesanteil des Profils.
- Ist ein Profil auffällig, zieht der Pull den Hauptteil ein zweites Mal ohne diese Profile: `bot_profiles.without`, Regeln unter `filter`.

### `senders`: mehr als ein Absender je Mess-ID

- Ereignisse und Sitzungen je Tag, getrennt danach, ob `hostName` und `customEvent:app_name` gesetzt sind, plus Formate der Artikel-ID.
- Regeln in `audit/senders.py`.
- Gerechnet ohne die auffälligen Bot-Profile (`variant`), da ein Bot-Netz, das nur ein Absender zählt, die Überschneidung verdeckt.
- Ist `app_name` in der Property nicht als Dimension registriert, trennt nur der Hostname; Grund unter `notes`.

### `primary_sender`: Zahlen nur mit dem ersten Absender

- Gesetzt im Hauptteil und in `bot_profiles.without`, sobald ein zweiter Absender erkannt ist.
- Enthält den Kaufweg je Stufe; kommt der Kauf selbst doppelt, auch Käufe und Umsatz je Kanal und Gerät, immer aus `ecommercePurchases`.

### Teilfehler

- Keine dieser Abfragen blockiert den Snapshot.
- Scheitert eine: Grund unter `bot_profiles.note` oder `senders.note`, kein Befund; `bot_profiles.checked` bzw. `senders.measurable` sind dann falsch.
- Die Analysen lesen alle Varianten über `audit/ga4_variants.py`, das aus jeder Variante dieselben Raten rechnet.

## Snapshot-Schema

### Zielordner

- Der Aufrufer bestimmt den Zielordner.
- Solo: Vorgabe `reporting/data/<heute>`. Dort legen auch `report` und `pulse` ab, solange sie ohne Lauf-ID laufen (Spec Abschnitt 14, Umstellung in Stufe 3).
- **In einem Audit oder Report mit Lauf-ID: `reporting/data/<run-id>`**, Datum plus Kadenz (`2026-10-01-audit`, `2026-11-01-month`). `--out` zeigt dorthin.
- Der Orchestrator gibt den Ordner vor. Bei manuellem Start während eines Laufs dieselbe Lauf-ID verwenden.
- Ein Snapshot im falschen Ordner fehlt der Analyse, und sie rechnet ohne Fehlermeldung weiter.

### Datei

Das Script schreibt `<out>/ga4.json` (oder `ga4-pulse.json`, bei `--max-history` `ga4-max-history.json`):

```json
{
  "period": {"start": "...", "end": "...", "granularity": "month"},
  "currency": "Berichtswährung der Property, etwa EUR oder USD",
  "history_from": "nur bei --max-history: gemessener erster Tag mit Daten",
  "by_month": [{"month": "2025-01", "sessions": 0, "purchase_revenue": 0.0, "purchases": 0,
                "channels": [{"channel", "sessions", "total_users", "purchase_revenue", "purchases"}]}],
  "channels": [{"channel", "sessions", "total_users", "purchase_revenue", "purchases", "engaged_sessions"}],
  "campaigns": [{"campaign", "sessions", "total_users", "purchase_revenue", "purchases"}],
  "devices": [{"device", "sessions", "total_users", "purchase_revenue", "purchases"}],
  "countries": [{"country", "sessions", "total_users", "purchase_revenue", "purchases"}],
  "landing_pages": [{"landing_page", "sessions", "engagement_rate", "purchase_revenue", "purchases"}],
  "compare_properties": [{"property_id", "currency", "note",
                          "by_month": [{"month", "sessions", "purchases", "purchase_revenue"}]}],
  "site_search": [{"search_term", "events", "sessions"}],
  "funnel": {"sessions": 0,
             "view_item": {"events": 457, "sessions": 273},
             "add_to_cart": {"events": 10, "sessions": 7},
             "view_cart": {"events": 0, "sessions": 0},
             "begin_checkout": {"events": 3, "sessions": 3},
             "purchase": {"events": 3, "sessions": 3}},
  "totals": {"sessions", "total_users (null, wenn die Gesamtzeile fehlt)", "purchase_revenue"},
  "property": {"property_id", "display_name", "measurement_ids",
               "streams": [{"stream_id", "measurement_id"}], "note"},
  "bot_profiles": {"checked", "flagged", "note", "period", "dimensions", "daily_floor",
                   "profiles": [{"profile", "label", "sessions", "share_of_sessions",
                                 "engagement_rate", "purchases", "purchase_rate", "total_users",
                                 "channels", "windows", "checks", "signals", "flagged"}],
                   "filter_proposal": {"enabled": false, "exclude": ["je auffälligem Profil eine Regel"]},
                   "without": {"Hauptteil ohne die auffälligen Profile": "...", "filter", "primary_sender"}},
  "senders": {"measurable", "variant", "note", "notes", "period", "onset", "ended",
              "still_duplicating", "multiple_senders", "double_counted_events",
              "item_ids": {"basis", "multiple_formats", "formats"},
              "streams": [{"stream_id", "measurement_id", "multiple_senders",
                           "double_counted_events",
                           "events": {"view_item": {"status", "onset", "ended", "uplift",
                                                    "overlap", "primary", "second",
                                                    "senders"}}}]},
  "primary_sender": {"stream_id", "signatures", "funnel", "channels", "devices"},
  "notes": {"purchases": "nur, wenn die Property die Metrik ecommercePurchases abgelehnt hat",
            "site_search": "nur, wenn customEvent:search_term in der Property fehlt"},
  "comparison": { "gleiche Struktur, eigener period, nur bei --compare-*": "..." }
}
```

### Regeln zum Schema

**Funnel**

- Jeder Schritt hat `events` (Auslösungen) und `sessions` (Besuche mit dem Ereignis).
- **Jede Quote im Report rechnet mit `sessions`, nie mit `events`** (Kennzahlen-Katalog, Abschnitt Funnel). Beispiel Pilotmonat: 457 `view_item`-Ereignisse in 273 Sessions.
- `funnel.sessions` = alle Besuche, Basis der ersten Stufe.
- Fehlt ein Ereignis ganz (typisch `view_cart` bei Warenkorb-Drawer ohne eigene Adresse): Nullen. Kein Messfehler, der Schritt existiert im Shop nicht. Keine Abbruchquote daraus bilden.

**`purchases` je Kanal**

- Grundlage der Conversion Rate je Kanal (Formel und Schwelle im Kennzahlen-Katalog, `${CLAUDE_PLUGIN_ROOT}/reference/metrics.md`).
- Lehnt eine Property den Metrik-Namen ab: Kanal-Call fällt genau einmal auf die übrigen Metriken zurück, `purchases` = `null` in jedem Kanal (unbekannt, nie 0), Grund unter `notes.purchases`, Rest vollständig.
- `notes` fehlt, solange nichts genullt wurde.

**`comparison`**

- Immer in derselben Datei, nie als eigene Datei oder eigener Ordner, mit `purchases`.
- Puls-Dateien überschreiben nie die Monats-Vergleichsbasis.

**Aufschlüsselungen**

- `campaigns`, `devices`, `countries`: dieselben Sessions wie `channels`, nach Kampagne, Gerätekategorie und Land, gleiche Basiszahlen samt `purchases`.
- `site_search`: interne Suchbegriffe (Ereignis `view_search_results`, Parameter `search_term`), `events` = Suchen, `sessions` = Besuche mit Suche.
- Voraussetzung: `search_term` als Custom Dimension registriert. Fehlt sie, entfällt `site_search`, Grund unter `notes.site_search`, der Lauf läuft weiter.

**Nur in `ga4-max-history.json`**

- `history_from`, zugleich `period.start`, da der Lauf die gesamte gemessene Historie abdeckt.
- `by_month`: eine Zeile je Monat, jeweils mit Aufschlüsselung nach Kanal. Die Baseline braucht Sessions je Monat und Kanal. Feldname wie im Shopify-Snapshot, damit die Baseline beide Quellen gleich liest.

**Nutzerzahlen**

- **Die Monatssumme hat keine Nutzerzahl.** Sessions, Umsatz und Käufe addieren sich über Kanäle, `total_users` nicht: GA4 entdoppelt Nutzer je Dimensionskombination, ein Nutzer über Organic und E-Mail steht in beiden Kanalzeilen.
- **`totals` rechnet GA4, nicht der Pull.** Der Kanal-Call fordert `metricAggregations: ["TOTAL"]` an.
- Fehlt die Gesamtzeile: `total_users` = `null` statt einer zu hohen Summe. `sessions` und `purchase_revenue` fallen dann auf die Summe zurück, die für sie korrekt ist.

## Setup-Check

`--check` testet Auth plus eine 1-Tages-Mini-Query (Exit 0/1), für den Setup-Wizard:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ga4/scripts/ga4_pull.py" \
  --property <id> --creds "$PTAI_GOOGLE_CREDENTIALS" --check
```

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| `google-auth fehlt` | `pip3 install --user google-auth requests`, erneut starten. |
| 403/Permission denied | Service-Account-Mail ohne Lesezugriff auf die GA4-Property. In GA4 unter Verwaltung, Property-Zugriffsverwaltung freigeben. |
| `error`-Objekt unter `comparison` | Vergleichs-Pull gescheitert, nicht fatal, Hauptteil vollständig. Der Report zieht den Vergleich später live oder lässt die Delta-Spalte weg. |
| `notes.purchases` im Snapshot | Property hat `ecommercePurchases` abgelehnt. Nicht fatal, nur die Conversion Rate je Kanal fehlt; der Report lässt die Spalte weg. |
| `notes.site_search` oder `site_search` fehlt | Event-Parameter `search_term` nicht als Custom Dimension (`customEvent:search_term`) registriert. Nicht fatal. Bei Bedarf in GA4 unter Verwaltung, Benutzerdefinierte Definitionen einrichten. |
| `--max-history` bricht ab | Messung des Startdatums gescheitert (Auth/Netzwerk); dann ist auch der Hauptteil nicht verlässlich. |
| Offener Punkt Pilot | Dimension-Name `landingPage` vs. `landingPagePlusQueryString` wird im Pilot gegen die API validiert. `ecommercePurchases` ist seit dem 11.09.2026 an zwei Properties geprüft. |
