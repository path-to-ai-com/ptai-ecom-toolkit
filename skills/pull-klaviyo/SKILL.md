---
name: pull-klaviyo
description: Zieht Klaviyo-CRM-Daten für den Kunden-Report oder den CRM-Automation-Case (Flows, Kampagnen mit Betreff, Preview, Absender und Volltext, Report-Metriken, Listen, Segmente, Formulare) und legt sie als Snapshot ab. Einsetzen, wenn ein Report oder Audit Klaviyo-Zahlen braucht, ein CRM-/Voice-Profil aus echten Kampagnen- und Flow-Texten entstehen soll oder der Nutzer ausdrücklich einen Klaviyo-Pull für einen Zeitraum will. Liest reporting/config.json und .env im Kunden-Workspace. Pilot, am 11.09.2026 an einem echten Account validiert.
---

# pull-klaviyo: Klaviyo-Snapshot ziehen

Zieht per Klaviyo-REST-API (JSON:API, `https://a.klaviyo.com/api/`) für einen Zeitraum:

- Flows und Kampagnen
- Report-Metriken je Flow und Kampagne
- Metrik-Aggregate für Placed Order
- Listen, Segmente, Formulare

Ablage als Snapshot im Kunden-Workspace. Aufruf durch Report- und Audit-Lauf oder einzeln.

## Content der Nachrichten

- Kampagnen und Flow-Nachrichten (SEND_MESSAGE-Actions) enthalten zusätzlich den Content:
  - Betreffzeile, Preview-Text, Absender (`from_email`, `from_label`) aus der Nachricht
  - `body_text`: verknüpftes Template-HTML als Klartext (stdlib `html.parser`, ohne Layout)
- Zweck: Marken-Content für ein CRM-Voice-Profil (Betreff, Anrede, CTA, Ton).
- Das ist keine Kunden-PII und fällt nicht unter die Sperre für Profil-Export (unten).
- `--skip-content`: nur Metadaten, ohne Text.

## Pilot-Status

- Validierungslauf am 11.09.2026 an einem echten Account abgeschlossen, mit Volltext aus Kampagnen- und Flow-Nachrichten.
- Alle Endpunkte liefern, auch die Report-Endpunkte (`campaign-values-reports`, `flow-values-reports`, `metric-aggregates`). Antwortform siehe Fehlerbilder.
- Offen:
  - `account` bleibt `null` ohne `accounts:read`-Scope.
  - `profile_count` bei Listen und Segmenten ist auf dieser API-Revision nicht abrufbar.
  - Benchmarks für Flow-Kennzahlen sind gegen diesen Lauf nicht geprüft.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `sources.klaviyo: true`.
- `.env` im Workspace-Root mit `PTAI_KLAVIYO_KEY`:
  - Private API Key mit Read-only-Scopes: Accounts, Campaigns, Flows, Lists, Segments, Metrics, Profiles, Events, Forms, Templates, Tags, Coupons.
  - Anlegen in Klaviyo unter Settings > API Keys > Create Private API Key. Scopes danach nicht mehr änderbar.

Fehlt etwas oder steht `sources.klaviyo` auf `false`: Klaviyo als "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf (Report/Audit) scheitert nie daran.

### Kein Profil-Export

- Die Profiles-API liefert Namen, Mailadressen und Telefonnummern.
- `reporting/` wird ins Git-Repository des Kunden committet; ein Profil-Export wäre dort ein Datenleck (gleiche Regel wie `pull-shopify`, Abschnitt Kohorten).
- Das Script zieht nie einzelne Profile, nur aggregierte Zähler: Listen- und Segmentgrößen, Suppression-Zähler über den System-Segment-Filter.

## Ablauf

1. `reporting/config.json` lesen (`sources.klaviyo`), `.env` sourcen (`PTAI_KLAVIYO_KEY`). Zeitraum:
   - Bestand Flows/Kampagnen: Standard letzte 365 Tage.
   - Report-Endpunkte: zusätzlich ein 90-Tage-Fenster.
2. Script aufrufen. **Zielordner ist der Daten-Ordner des laufenden Audits oder Reports** (`reporting/data/<run-id>`); ohne Lauf-ID der heutige Ordner:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-klaviyo/scripts/klaviyo_pull.py" \
     --out "reporting/data/$(date +%F)"
   ```

   - `PTAI_KLAVIYO_KEY` aus der gesourcten `.env` nehmen, nie als `--api-key`-Argument; sonst steht er im Klartext in der Prozessliste (`ps`), sichtbar für alle Nutzer der Maschine.
   - `--api-key` nur als Rückfallweg, mit Warnung auf stderr.

   Optionen:

   | Option | Wirkung |
   |---|---|
   | `--days 365` | Bestandsfenster für Flows/Kampagnen, Standard 365 |
   | `--report-days 90` | Fenster der Report-Endpunkte, Standard 90 |
   | `--check` | nur Auth-Test, siehe unten |
   | `--skip-content` | kein Betreff/Text/Template-Pull, nur Metadaten; deutlich weniger API-Calls, aber kein Voice-Profil möglich |

3. Dem Nutzer melden:
   - Zahl aktiver Flows
   - Zahl Kampagnen im Fenster
   - Flow-Anteil am E-Mail-Umsatz, falls Reports geliefert haben
   - größte Liste und größtes Segment
   - Zahl gezogener Kampagnen- und Flow-Nachrichten mit Text
   - Auffälligkeiten: leere Reports, fehlende Scopes, Templates ohne HTML

## Snapshot-Schema

`reporting/data/<run-id>/klaviyo.json`. Jeder Teil scheitert isoliert: das Feld wird `null`, Begründung in `notes`, der Lauf bricht nie ab (Muster wie `pull-shopify`).

```json
{
  "period": {"inventory_days": 365, "report_days": 90, "pulled_at": "2026-09-14T10:00:00Z"},
  "account": {"id": "...", "timezone": "...", "public_api_key": "..."},
  "metrics": [{"id": "...", "name": "Placed Order", "integration": "Shopify"}],
  "flows": [
    {
      "id": "...", "name": "Welcome Series", "status": "live",
      "trigger_type": "List", "created": "...", "updated": "...",
      "actions": [
        {
          "id": "...", "action_type": "SEND_MESSAGE", "status": "live",
          "messages": [
            {"id": "...", "subject": "...", "preview_text": "...",
             "from_email": "...", "from_label": "...", "body_text": "..."}
          ]
        }
      ]
    }
  ],
  "campaigns": [
    {
      "id": "...", "name": "...", "status": "Sent", "channel": "email",
      "send_time": "...", "created_at": "...",
      "messages": [
        {"id": "...", "subject": "...", "preview_text": "...",
         "from_email": "...", "from_label": "...", "body_text": "..."}
      ]
    }
  ],
  "flow_reports": {
    "by_flow": [
      {"flow_id": "...", "recipients": 0, "open_rate": 0.0, "click_rate": 0.0,
       "conversion_rate": 0.0, "conversion_value": 0.0, "revenue_per_recipient": 0.0,
       "unsubscribe_rate": 0.0, "spam_complaint_rate": 0.0, "bounce_rate": 0.0}
    ],
    "raw_response_shape_confirmed": true
  },
  "campaign_reports": {
    "by_campaign": [
      {"campaign_id": "...", "recipients": 0, "open_rate": 0.0, "click_rate": 0.0,
       "conversion_rate": 0.0, "conversion_value": 0.0, "revenue_per_recipient": 0.0,
       "unsubscribe_rate": 0.0, "spam_complaint_rate": 0.0, "bounce_rate": 0.0}
    ],
    "raw_response_shape_confirmed": true
  },
  "placed_order_aggregate": {
    "by_attributed_channel": [{"$attributed_channel": "Email", "month": "2026-08", "count": 0, "sum_value": 0.0}],
    "by_attributed_flow": [{"$attributed_flow": "...", "month": "2026-08", "count": 0, "sum_value": 0.0}],
    "raw_response_shape_confirmed": true
  },
  "lists": [{"id": "...", "name": "...", "profile_count": 0}],
  "segments": [{"id": "...", "name": "...", "profile_count": 0}],
  "forms": [{"id": "...", "name": "...", "status": "..."}],
  "notes": {
    "profiles": "kein Einzelprofil-Export, nur aggregierte Zaehler (Listen/Segmente)"
  }
}
```

- `raw_response_shape_confirmed` setzt das Script je Report-Block:
  - `true`, wenn es Zeilen in der am 11.09.2026 bestätigten Antwortform gelesen hat
  - `false`, wenn der Aufruf scheiterte, die Metrik-ID fehlte, keine Zeile kam oder die Antwort eine andere Form hatte; außer bei leerer Antwort steht der Grund in `notes`, bei abweichender Form liegt die Antwort zusätzlich unter `raw`
- `notes` enthält jede methodische Abweichung, nicht nur Totalausfälle (wie `pull-shopify`): gekürzte Zeiträume, fehlende Scopes, Endpunkte mit 404 oder 403.

## Setup-Check

`--check` testet Auth plus einen Mini-Call gegen `/api/accounts` (Exit 0/1):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-klaviyo/scripts/klaviyo_pull.py" --check
```

## Fehlerbilder

### Flow-Summen nie aus `flow-values-reports`

- `flow-values-reports` liefert nicht alle Flows. Am 12.09.2026 fehlten sendende Flows mit Umsatz, darunter Welcome-Flows.
- Folge: der Flow-Anteil am E-Mail-Umsatz erscheint viel zu niedrig.
- **Flow-Versände und Flow-Umsatz immer über `metric-aggregates` gegenrechnen:**
  - `Received Email` nach `$flow` (count)
  - `Placed Order` nach `$attributed_flow` (sum_value)
- Report-Endpunkte nur für die Nachrichten-Ebene nutzen, nie für Summen je Flow oder den Flow-Anteil.

### API-Verhalten (Tiefen-Pull 12.09.2026)

- Revision `2026-07-15` wird akzeptiert.
- Flow-Graphen (Trigger, Profilfilter, Splits, Wartezeiten): `GET /api/flows/{id}/?additional-fields[flow]=definition`.
- Report-Zeilen gruppieren nach `flow_id`, `send_channel`, `flow_message_id` (Kampagnen: `campaign_id`, `campaign_message_id`). Die Nachrichten-ID nie verwerfen, sonst ist keine Diagnose innerhalb eines Flows möglich.
- `profile_count` nur auf der Einzelressource `GET /api/segments/{id}/?additional-fields[segment]=profile_count`, gedrosselt auf etwa 15 je Minute.
- `metric-aggregates`:
  - `interval` kennt `year` nicht; `month` nehmen und summieren.
  - Monats-Buckets tragen den Monatsbeginn in UTC (`2025-08-31T22:00:00+00:00` ist September in Berlin). Das Datum nicht auf sieben Zeichen kürzen, sonst ist jeder Monat um einen zu früh beschriftet.
  - `by` akzeptiert nur Klaviyos feste Dimensionen (`$flow`, `$message`, `$attributed_flow`, `Inbox Provider`, `Bounce Type`, `Method` und wenige mehr), keine Shopify-Eigenschaften wie `Source Name`.
  - `Method` war beim Subscribe-Event leer.
- Kampagnen-Liste enthält `audiences.included/excluded`, `send_strategy`, `send_options`. `messages.channel` kennt `whatsapp` nicht als Filterwert.
- Metriken können doppelt existieren (`Added to Cart` aus Shopify und aus der API, `Active on Site` zweimal). Für Abdeckungs-Rechnungen die Metrik-ID nehmen, die der Flow im Graphen als Trigger nutzt, nie den ersten Namens-Treffer.

### Bestätigt im Pilot-Lauf (11.09.2026)

| Fall | Verhalten |
|---|---|
| `401 Unauthorized` | Key falsch oder abgelaufen. Neuen Private API Key beim Kunden anfragen; den Key nie im Chat austauschen, nur direkt in `.env`. |
| `403 Forbidden` bei einem Endpunkt | Read-Scope für die Ressource fehlt. Feld `null` plus Note, der Lauf läuft weiter. Am Pilot-Key fehlte `accounts:read`, nur `account` blieb `null`. |
| `429 Too Many Requests` | Rate-Limit (Burst und Steady je Endpunkt-Kategorie). Script wartet `Retry-After` Sekunden, ein zweiter Versuch; scheitert der, Feld `null` plus Note. |

- `campaign-values-reports`/`flow-values-reports` verlangen `conversion_metric_id` im Body (ohne: 400; mit: volle `REPORT_STATISTICS`-Liste). Das Script löst die ID über die Metrik "Placed Order" auf und überspringt den Report, wenn sie fehlt (ein `account`-Scope-Fehler wirkt bis hierhin).
- `/api/metrics/` akzeptiert kein `page[size]` (400 "'page_size' is not a valid field"); ohne Parameter kommt die volle Liste in einer Seite.
- `/api/lists/` und `/api/segments/`:
  - höchstens `page[size]=10`
  - `additional-fields=profile_count` wird abgelehnt ("additional-fields must be in []"), daher `profile_count` = `null` plus Note; andere Quelle für Listengrößen offen
  - 20 Seiten reichen für große Accounts nicht; im Script `max_pages=60`
- `metric-aggregates` liefert **Zeitreihen**: `dates` (Monatsliste) plus `data[].measurements.count`/`.sum_value` als parallele Arrays. Das Script zippt sie zu `{dimension, month, count, sum_value}`.
- Flow-Actions heißen `SEND_EMAIL`/`SEND_SMS`/`SEND_PUSH`, nie `SEND_MESSAGE` (kein kanal-neutraler Typ). `SEND_MESSAGE` bleibt als Fallback im Code, kam am echten Account nie vor.
- **Content liegt unterschiedlich tief:**
  - `campaign-message`: `attributes.definition.content.{subject,preview_text,from_email,from_label,...}`
  - `flow-message`: `attributes.content.{...}` ohne `definition`-Wrapper
  - Verwechselt ergibt das `subject: null` bei funktionierendem `body_text`.
- `/api/flow-actions/{id}/flow-messages/` lehnt `?include=template` ab ("'template' include is not currently supported for the requested operation on this resource"); `/api/campaign-messages/{id}/?include=template` funktioniert.
- Flow-Nachrichten lösen das Template daher über einen eigenen `/api/templates/{id}`-Call auf (`resolve_template_text`, Cache je Template-ID, da viele Flows ein Template teilen).
- A/B-Test-Actions oder -Kampagnen haben mehrere Nachrichten je Action. Das Feld heißt darum `messages` (Liste), nie `message`.
