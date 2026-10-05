---
name: pull-ads
description: SEA-Zahlen aus einem Google-Ads-Konto ziehen (Ausgaben je Monat, ROAS, Impression Share und was ihn begrenzt, Kampagnen, Anzeigengruppen, tatsächliche Suchbegriffe und Ausgaben ohne Conversion) und als Snapshot ablegen. Nutzen, wenn ein Audit den Baseline-Block SEA braucht oder der Nutzer wissen will, wofür das Werbebudget tatsächlich ausgegeben wird. Braucht die Google Ads API im Cloud-Projekt des Betreibers mit mindestens der Stufe Explorer und einen Lesezugang des Dienstkontos zum Kundenkonto; liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-ads: SEA-Snapshot ziehen

Zieht Ausgaben, Leistung und Verschwendung aus einem Google-Ads-Konto und legt
alles als Snapshot ab.

## Stand: am 02.10.2026 gegen ein echtes Konto geprüft

**Der erste echte Lauf hat zwei Rechenfehler gefunden, beide behoben.** Der
Impression Share stand im Nenner auf allen Impressionen des Monats, auch aus
Zeilen ohne Share, und die Suchbegriffe hatten keine Bezugsgröße für den
Anteil ohne Conversion. Die Summen aus Klicks, Conversions und Kosten stimmten
für einen Zeitraum von sieben Tagen auf den Cent mit der Oberfläche von Google
Ads überein. Die Verifikationsliste unten ist abgearbeitet, der Vorbehalt in
`notes` ist seitdem entfallen.

## Zwei verschiedene Zugänge, und nur einer kommt vom Kunden

| | Wem gehört es | Woher |
|---|---|---|
| **Freigabe der Google Ads API** | dem Betreiber | das Cloud-Projekt, dem das Dienstkonto gehört: API aktivieren und "Apply for access", mindestens Stufe Explorer (`reference/access.md` Teil A, Schritt 6) |
| **Zugang zum Werbekonto** | dem Kunden | der Kunde fügt die **Dienstkonto-Mailadresse** als Nutzer mit "Nur Lesen" hinzu |

Beides ist nötig. Der Zugriff läuft über dasselbe Dienstkonto wie GA4 und GSC,
mit dem Scope `adwords`; eine Personenadresse als Ads-Nutzer reicht **nicht**,
weil die API über das Dienstkonto geht.

**Ein Entwicklertoken gibt es seit dem 09.09.2026 nicht mehr.** Google hat es
abgeschafft, die Zugriffsstufe hängt seitdem am Cloud-Projekt, und ein
Verwaltungskonto ist nicht mehr nötig. Bis zum 02.10.2026 verlangte dieser
Pull trotzdem `PTAI_GOOGLE_ADS_TOKEN` und brach ohne ab, obwohl Google den
Header ignoriert.

**Woran man sieht, welche Seite fehlt:** Die Fehlerzeile nennt Googles Grund.
`SERVICE_DISABLED` heißt, die API ist im Cloud-Projekt nicht aktiviert.
`CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` heißt, das Projekt steht noch auf
der Teststufe; das Dienstkonto kann das Kundenkonto dann schon sehen, darf es
aber nicht abfragen. Beides ist Sache des Betreibers. Fehlt dagegen die
Nutzer-Freigabe im Werbekonto, ist es Sache des Kunden.

## Voraussetzungen

- `reporting/config.json` mit `sources.ads` nicht `false` und
  `google_ads_customer_id`, der Kundennummer des Werbekontos mit oder ohne
  Bindestriche (Beispiel: `"123-456-7890"`)

  **Der Feldname war bis zum 07.09.2026 nirgends festgelegt.** Diese Skill
  verlangte "die Kundennummer des Werbekontos", aber weder `config.py` noch die
  Config-Vorlage im Setup-Wizard kannten ein Feld dafuer. Sobald der Zugang
  steht, haette der Nachtrag an einem Feld gestanden, das niemand benennen
  kann.
- `PTAI_GOOGLE_CREDENTIALS` in der `.env` des Workspace

Fehlt die Freigabe oder der Zugang: als "nicht verfügbar (Grund)" melden und
aufhören. Der Baseline-Block SEA bleibt dann leer und wird später mit
`--backfill` nachgetragen. **Das ist der dokumentierte Normalfall**, kein
Fehler: solange der Zugang nicht steht, kommt die SEA-Baseline aus einem
Berichtsexport des Kunden (Spec Abschnitt 4).

## Ablauf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ads/scripts/ads_pull.py" \
  --customer-id <kundennummer> --creds "$PTAI_GOOGLE_CREDENTIALS" \
  --max-history --out "reporting/data/<run-id>"
```

`--login-customer-id` nur, wenn der Zugriff über ein Verwaltungskonto läuft.
`--check` prüft nur Zugang und Währung, ohne Snapshot.

Der Kontobeginn wird **gemessen, nicht angenommen**: `--max-history` fragt ab
2010 und nimmt den frühesten Tag mit Daten, wie `pull-gsc` und `pull-ga4`.

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

**Die Währung steht im Snapshot, nicht in der Annahme.** Ein Euro-Betrag aus
einem Konto in Franken fällt in keiner Tabelle auf.

**Beträge kommen als Micros.** `cost_micros` durch eine Million; `null` bleibt
`null`, weil "kein Wert" etwas anderes ist als "null ausgegeben".

**Der Impression Share ist Summe der Impressionen durch Summe der möglichen**,
je Zeile `impressions / share`, nur über Zeilen, die einen Share tragen. Die
beiden Verlustanteile sind mit den möglichen Impressionen gewichtet. Ein
Mittelwert über die tatsächlichen Impressionen überschätzt den Share, sobald
eine Kampagne mit kleinem Share viele mögliche Impressionen hat.
`search_impression_share_coverage` sagt, welcher Anteil der Impressionen aus
Zeilen mit Share stammt; ein Monat mit niedriger Abdeckung (etwa ein Tag, für
den Google den Share noch nicht geliefert hat) ist kein belastbarer Wert. Ein
Monat ohne Share bekommt `null`, nicht 0, denn 0 hieße "nie ausgeliefert".

**Kampagnen, Anzeigengruppen und Suchbegriffe laufen über `detail_period`**,
bei `--max-history` die letzten zwölf vollständigen Monate. Die Monatsreihe
geht über die ganze Historie, die Frage "wofür geht das Geld heute" nicht.

**`cost_total` ist die Bezugsgröße für die Verschwendung**, nicht die Summe
der Monatsausgaben. Die Suchbegriff-Ansicht deckt Suche und Shopping ab, nicht
Performance Max, und Google blendet seltene Begriffe aus.

**Ein Monat ohne Ausgaben hat keinen ROAS**, also `null`. Eine 0 läse sich als
"nichts eingebracht".

**"Ausgaben ohne Conversion" zählt Bruchteile mit.** Google zählt Conversions
als Dezimalzahl; 0,5 ist eine Conversion und keine Verschwendung. Die Summe geht
über alle Suchbegriffe, die Liste ist auf 300 gekappt.

**Nur die Kampagnen-Abfrage ist fatal.** Ohne sie gibt es keine SEA-Baseline.
Anzeigengruppen und Suchbegriffe scheitern isoliert: statt des Blocks steht ein
`error`-Eintrag im Snapshot, genau wie `sitemaps` in `gsc_pull.py`.

## Vor dem ersten echten Lauf zu verifizieren

1. **Zugriffsstufe des Cloud-Projekts.** Auf der Teststufe darf das Projekt
   ausschließlich Testkonten abfragen. Für einen Kundenaudit reicht das nicht.
   Prüfen: `--check` gegen das echte Kundenkonto. Meldet es
   `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION`, ist die Stufe das Problem,
   nicht der Code. Am 02.10.2026 genau so gesehen.
2. **API-Version.** Am 02.10.2026 belegt: v21 antwortet mit einer nackten 404,
   v22 bis v25 antworten, v26 gibt es noch nicht. `DEFAULT_VERSION` steht
   seitdem auf v25. `--api-version` übersteuert.
3. **Feldnamen der vier Abfragen.** Am 02.10.2026 belegt: alle vier liefern,
   die drei Impression-Share-Metriken kommen zusammen mit `segments.date`, und
   Share plus beide Verlustanteile ergeben je Monat 1. Für den jüngsten Tag
   liefert Google den Share teils noch nicht, siehe Abdeckung oben.
4. **`login-customer-id`.** Bei direktem Nutzerzugang des Dienstkontos nicht
   nötig, am 02.10.2026 belegt. Nur beim Zugriff über ein Verwaltungskonto.
5. **Dienstkonto statt Personenzugang.** Die Dienstkonto-Mail muss als Nutzer im
   Kundenkonto stehen. Am 02.10.2026 belegt, dass das greift: nach der
   Freigabe durch den Kunden listet `customers:listAccessibleCustomers` das
   Konto für das Dienstkonto, auch solange das Projekt noch auf der
   Teststufe steht.
6. **Währung.** `--check` gibt sie aus. Passt sie nicht zum Shop, ist jede
   spätere Zahl im Report falsch beschriftet.
7. **Historienanfang.** Am 02.10.2026 plausibel gemessen, der erste Monat mit
   Daten lag gut zehn Jahre zurück.
8. **Summen gegen die Oberfläche.** Am 02.10.2026 für sieben Tage auf den Cent
   gleich (Klicks, Conversions, Kosten, mit und ohne entfernte Kampagnen).

Die Fixtures bleiben von Hand gebaut: aufgezeichnete Antworten enthielten
Kampagnennamen und Zahlen eines Kunden und gehören deshalb nicht ins Repo.

**Vor dem Befund: welche Conversion-Aktion zählt.** `metrics.conversions`
summiert alle Aktionen, die `include_in_conversions_metric` tragen. Zählt dort
mehr als ein Kauf-Absender oder ein Schritt vor dem Kauf, sind Conversions und
ROAS überhöht. Prüfen über `segments.conversion_action_name` auf `customer`;
der Pull zieht das nicht selbst.

## Fehlerbilder

- **HTTP 404 ohne Begründung:** die API-Version ist abgestellt. Auf die
  aktuelle Version heben, `--api-version` übersteuert.
- **Berechtigung verweigert:** meist die Zugriffsstufe des Cloud-Projekts oder
  die fehlende Dienstkonto-Freigabe im Kundenkonto, nicht der Code. Die
  Fehlerzeile nennt Googles Grund, siehe oben.
- **Anzeigengruppen oder Suchbegriffe scheitern:** `error`-Eintrag im Snapshot,
  der Rest bleibt vollständig.
