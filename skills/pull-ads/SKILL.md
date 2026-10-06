---
name: pull-ads
description: Zieht SEA-Zahlen aus einem Google-Ads-Konto (Ausgaben je Monat, ROAS, Impression Share und seine Begrenzung, Kampagnen, Anzeigengruppen, Suchbegriffe, Ausgaben ohne Conversion) und legt sie als Snapshot ab. Einsetzen, wenn ein Audit den Baseline-Block SEA braucht oder der Nutzer wissen will, wofür das Werbebudget ausgegeben wird. Voraussetzung: Google Ads API im Cloud-Projekt des Betreibers mit mindestens Stufe Explorer und Lesezugang des Dienstkontos zum Kundenkonto. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-ads: SEA-Snapshot ziehen

Zieht Ausgaben, Leistung und Verschwendung aus einem Google-Ads-Konto in einen Snapshot.

## Prüfstand

- Geprüft am 02.10.2026 gegen ein echtes Konto.
- Klicks, Conversions und Kosten über sieben Tage stimmen auf den Cent mit der Google-Ads-Oberfläche überein.
- Die Prüfliste unten ist abgearbeitet; `notes` enthält keinen Vorbehalt mehr.

## Zugänge

Beide Zugänge sind nötig.

| | Wem gehört es | Woher |
|---|---|---|
| **Freigabe der Google Ads API** | dem Betreiber | das Cloud-Projekt, dem das Dienstkonto gehört: API aktivieren und "Apply for access", mindestens Stufe Explorer (`reference/access.md` Teil A, Schritt 6) |
| **Zugang zum Werbekonto** | dem Kunden | der Kunde fügt die **Dienstkonto-Mailadresse** als Nutzer mit "Nur Lesen" hinzu |

- Zugriff über dasselbe Dienstkonto wie GA4 und GSC, Scope `adwords`.
- Eine Personenadresse als Ads-Nutzer reicht **nicht**, die API läuft über das Dienstkonto.
- **Kein Entwicklertoken.** Google hat es zum 09.09.2026 abgeschafft; die Zugriffsstufe hängt am Cloud-Projekt, ein Verwaltungskonto ist nicht nötig. `PTAI_GOOGLE_ADS_TOKEN` wird nicht gebraucht, Google ignoriert den Header.

### Fehlende Seite erkennen

Die Fehlerzeile nennt Googles Grund:

| Grund | Bedeutung | Zuständig |
|---|---|---|
| `SERVICE_DISABLED` | API im Cloud-Projekt nicht aktiviert | Betreiber |
| `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` | Projekt auf Teststufe; das Dienstkonto sieht das Kundenkonto, darf es aber nicht abfragen | Betreiber |
| fehlende Nutzer-Freigabe im Werbekonto | | Kunde |

## Voraussetzungen

- `reporting/config.json` mit `sources.ads` ungleich `false` und `google_ads_customer_id` (Kundennummer des Werbekontos, mit oder ohne Bindestriche, Beispiel: `"123-456-7890"`).
- `PTAI_GOOGLE_CREDENTIALS` in der `.env` des Workspace.

Fehlt Freigabe oder Zugang:

1. "nicht verfügbar (Grund)" melden und stoppen.
2. Der Baseline-Block SEA bleibt leer und wird später mit `--backfill` nachgetragen.
3. **Das ist der dokumentierte Normalfall**, kein Fehler. Bis der Zugang steht, kommt die SEA-Baseline aus einem Berichtsexport des Kunden (Spec Abschnitt 4).

## Ablauf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ads/scripts/ads_pull.py" \
  --customer-id <kundennummer> --creds "$PTAI_GOOGLE_CREDENTIALS" \
  --max-history --out "reporting/data/<run-id>"
```

- `--login-customer-id` nur beim Zugriff über ein Verwaltungskonto.
- `--check` prüft Zugang und Währung, ohne Snapshot.
- Kontobeginn wird **gemessen**: `--max-history` fragt ab 2010 und nimmt den frühesten Tag mit Daten, wie `pull-gsc` und `pull-ga4`.

## Snapshot-Schema

`<out>/ads.json`:

```json
{
  "source": "ads", "period": {"start", "end", "granularity"},
  "currency": "EUR", "history_from": "2023-04-01",
  "account": {"id", "name", "time_zone"}, "api_version": "v25",
  "by_month": [{"month": "2026-08", "impressions", "clicks", "cost",
                 "conversions", "conversions_value", "roas",
                 "search_impression_share",
                 "search_budget_lost_impression_share",
                 "search_rank_lost_impression_share",
                 "search_impression_share_coverage"}],
  "detail_period": {"start": "2025-09-01", "end": "2026-08-31"},
  "campaigns": [{"name", "status", "channel_type", "impressions", "clicks",
                  "cost", "conversions", "conversions_value", "roas"}],
  "summary_search_terms": {"search_terms_total", "terms_without_conversion",
                            "cost_without_conversion", "cost_total"},
  "search_terms_without_conversion": [{"term", "campaign", "cost", "clicks", "impressions"}]
}
```

### Regeln zum Schema

- **Währung aus dem Snapshot, nie annehmen.** Ein Konto in Franken mit Euro-Beschriftung fällt in keiner Tabelle auf.
- **Beträge kommen als Micros:** `cost_micros` durch eine Million. `null` bleibt `null` ("kein Wert" ist nicht "null ausgegeben").
- **Impression Share = Summe der Impressionen / Summe der möglichen Impressionen.**
  - Mögliche Impressionen je Zeile: `impressions / share`.
  - Nur Zeilen mit Share einrechnen.
  - Beide Verlustanteile mit den möglichen Impressionen gewichten.
  - Ein Mittelwert über die Impressionen überschätzt den Share, sobald eine Kampagne mit kleinem Share viele mögliche Impressionen hat.
- **`search_impression_share_coverage`** = Anteil der Impressionen aus Zeilen mit Share. Niedrige Abdeckung (etwa ein Tag, für den Google den Share noch nicht liefert) = kein belastbarer Wert.
- Monat ohne Share: `null`, nicht 0 (0 hieße "nie ausgeliefert").
- **Kampagnen, Anzeigengruppen und Suchbegriffe laufen über `detail_period`**, bei `--max-history` die letzten zwölf vollständigen Monate. Die Monatsreihe deckt die ganze Historie ab.
- **`cost_total` ist die Bezugsgröße für die Verschwendung**, nicht die Summe der Monatsausgaben. Die Suchbegriff-Ansicht deckt Suche und Shopping ab, nicht Performance Max; Google blendet seltene Begriffe aus.
- **Monat ohne Ausgaben: ROAS `null`**, nicht 0 (0 hieße "nichts eingebracht").
- **"Ausgaben ohne Conversion" berücksichtigt Bruchteile.** Conversions sind Dezimalzahlen; 0,5 ist eine Conversion, keine Verschwendung.
- Summe über alle Suchbegriffe, Liste auf 300 gekappt.
- **Nur die Kampagnen-Abfrage ist fatal**, ohne sie gibt es keine SEA-Baseline. Anzeigengruppen und Suchbegriffe scheitern isoliert: `error`-Eintrag statt Block, wie `sitemaps` in `gsc_pull.py`.

## Prüfliste

| # | Punkt | Prüfung und Stand (02.10.2026) |
|---|---|---|
| 1 | **Zugriffsstufe des Cloud-Projekts** | Teststufe erlaubt nur Testkonten, für einen Kundenaudit zu wenig. `--check` gegen das echte Kundenkonto; `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` heißt: Stufe, nicht Code. So aufgetreten. |
| 2 | **API-Version** | v21 antwortet mit nackter 404, v22 bis v25 antworten, v26 existiert noch nicht. `DEFAULT_VERSION` = v25, `--api-version` übersteuert. |
| 3 | **Feldnamen der vier Abfragen** | Alle vier liefern; die drei Impression-Share-Metriken kommen mit `segments.date`; Share plus beide Verlustanteile = 1 je Monat. Für den jüngsten Tag fehlt der Share teils (siehe Abdeckung). |
| 4 | **`login-customer-id`** | Bei direktem Nutzerzugang des Dienstkontos nicht nötig, nur über ein Verwaltungskonto. |
| 5 | **Dienstkonto statt Personenzugang** | Dienstkonto-Mail muss als Nutzer im Kundenkonto stehen. Nach Freigabe listet `customers:listAccessibleCustomers` das Konto, auch auf Teststufe. |
| 6 | **Währung** | `--check` gibt sie aus. Passt sie nicht zum Shop, ist jede Zahl im Report falsch beschriftet. |
| 7 | **Historienanfang** | Plausibel, erster Monat mit Daten gut zehn Jahre zurück. |
| 8 | **Summen gegen die Oberfläche** | Sieben Tage auf den Cent gleich (Klicks, Conversions, Kosten, mit und ohne entfernte Kampagnen). |

- Fixtures bleiben handgebaut; aufgezeichnete Antworten enthalten Kampagnennamen und Zahlen eines Kunden und gehören nicht ins Repo.

### Vor dem Befund: zählende Conversion-Aktion prüfen

- `metrics.conversions` summiert alle Aktionen mit `include_in_conversions_metric`.
- Zählt dort mehr als ein Kauf-Absender oder ein Schritt vor dem Kauf, sind Conversions und ROAS zu hoch.
- Prüfen über `segments.conversion_action_name` auf `customer`. Der Pull zieht das nicht selbst.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **HTTP 404 ohne Begründung** | API-Version abgestellt. Auf die aktuelle Version heben, `--api-version` übersteuert. |
| **Berechtigung verweigert** | Meist Zugriffsstufe des Cloud-Projekts oder fehlende Dienstkonto-Freigabe im Kundenkonto, nicht der Code. Googles Grund steht in der Fehlerzeile (siehe oben). |
| **Anzeigengruppen oder Suchbegriffe scheitern** | `error`-Eintrag im Snapshot, der Rest bleibt vollständig. |
