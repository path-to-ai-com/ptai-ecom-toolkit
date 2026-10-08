---
name: pulse
description: Erzeugt den Wochen-Puls für den Kunden-Workspace, ein kompaktes Markdown mit den konfigurierten Puls-KPIs und dem Delta zur Vorwoche; kommentiert werden nur auffällige Werte. Auslöser sind /ptai-ecom:pulse oder der Wunsch nach einem wöchentlichen Kurzstatus, Wochen-Update oder Puls für Shop-, Traffic- oder SEO-Zahlen. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pulse: Wochen-Puls

- KPI-Tabelle der letzten vollen Woche gegen die Vorwoche, Kommentar nur zu auffälligen Werten.
- Kein Executive-Summary-Absatz, keine Kapitel, kein PDF; nur Tabelle und wenige Sätze.
- Zieht nur die Quellen, die die konfigurierten `pulse_kpis` brauchen.
- Schreibt eigene `-pulse.json`-Snapshots; diese sind nie Vergleichsbasis für den Monats-Report.

## Voraussetzungen

Arbeitsverzeichnis ist der Kunden-Workspace.

- `reporting/config.json` (angelegt von der Skill `setup`).
  - Fehlt sie: nichts raten, nichts anlegen. In zwei Sätzen sagen, was fehlt, und anbieten, jetzt die Skill `setup` zu starten. Bei Nein hier aufhören.
  - Dasselbe gilt, wenn die Config existiert, aber keine konfigurierte KPI eine liefernde Quelle hat. Kein Puls nur aus Lücken.
- `pulse_kpis` ist optional. Fehlt der Schlüssel, gilt der Default-Satz aus der Spec: `sessions`, `revenue`, `orders`, `conversion_rate`, `aov`, `gsc_clicks`, `gsc_impressions`.
- Jede konfigurierte KPI braucht ihre Quelle unter `sources` auf `true` (Tabelle unten). Ist für keine KPI eine Quelle aktiv: kein Puls, auf `/ptai-ecom:setup` verweisen.
- `.env` mit den Secrets der aufgerufenen Pull-Skills (`PTAI_GOOGLE_CREDENTIALS` für GA4/GSC). Details stehen in den Pull-Skills.

Der Lauf liest nur und schreibt nie in Kundensysteme.

## Ablauf

### 1. Config lesen, benötigte Quellen ableiten

`pulse_kpis` mit dieser Tabelle abgleichen. Jede KPI kommt nur aus der dort genannten Quelle. Unbekannte Schlüssel mit Warnung überspringen, die übrigen KPIs normal verarbeiten.

| KPI-Schlüssel | Label | Prim. Quelle (Feld) | Fallback |
|---|---|---|---|
| `sessions` | Sessions | `shopify.json`: `sessions.sessions` | `ga4.json`: `totals.sessions` |
| `revenue` | Umsatz | `shopify.json`: `totals.total_sales` | keine |
| `orders` | Bestellungen | `shopify.json`: `totals.orders` | keine |
| `conversion_rate` | Conversion Rate | `shopify.json`: `totals.orders` / `sessions.sessions` | `ga4.json`: `funnel.purchase.sessions` / `funnel.sessions` |
| `aov` | AOV | `shopify.json`: `totals.average_order_value` | keine |
| `gsc_clicks` | GSC-Klicks | `gsc.json`: `totals.clicks` | keine |
| `gsc_impressions` | GSC-Impressionen | `gsc.json`: `totals.impressions` | keine |

Conversion-Präzedenz (Verweis: `skills/report/SKILL.md`, Abschnitt "Zahlen-Regeln (hart)"):

1. Conversion Rate = `totals.orders` geteilt durch `sessions.sessions`, beides aus `shopify.json`. Nie `sessions.conversion_rate`: das Feld zählt nur Bestellungen, die Shopify einer Session zuordnen konnte, und liegt zu tief (Formel in `reference/metrics.md`).
2. Fehlt `sessions` in `shopify.json`: aus `ga4.json`.
3. Fehlt beides: KPI "nicht berechenbar", keine Ersatzzahl.

Benötigte Pull-Skills:

| Pull-Skill | Wenn konfiguriert |
|---|---|
| `pull-shopify` | eine von `sessions`, `revenue`, `orders`, `conversion_rate`, `aov` |
| `pull-ga4` | `sessions` oder `conversion_rate` (Fallback-Daten müssen vorliegen, falls Shopify keine Sessions liefert) |
| `pull-gsc` | `gsc_clicks` oder `gsc_impressions` |

- `pull-cwv` und `check-geo` laufen im Puls nie; Core Web Vitals und GEO sind laut Spec keine Puls-KPIs.
- Steht eine benötigte Quelle in `sources` auf `false`: die abhängigen KPI-Zeilen als "nicht verfügbar (Quelle nicht aktiv)" ausgeben, den Pull dieser Quelle auslassen, den Rest normal ausführen.

### 2. Zeitraum bestimmen

- Puls-Woche: die letzte vollständig abgeschlossene Kalenderwoche vor dem Ausführungstag, Montag bis Sonntag (ISO-Woche).
- Berechnung: Montag der laufenden Woche bestimmen, 7 Tage zurück ergibt den Montag der Puls-Woche, deren Sonntag liegt 6 Tage danach.
- Vorwoche: die Montag-bis-Sonntag-Spanne 7 Tage früher.
- Beispiel: Ausführung Montag 2026-08-10 ergibt Puls-Woche 2026-08-03 bis 2026-08-09 (2026-W32) und Vorwoche 2026-07-27 bis 2026-08-02 (2026-W31).
- ISO-Wochennummer für den Dateinamen aus dem Sonntag der Puls-Woche: macOS `date -j -f %Y-%m-%d <sonntag> +%G-W%V`, Linux `date -d <sonntag> +%G-W%V`.
- Es gibt keine gespeicherte Vergleichsbasis: jeder Puls-Lauf zieht aktuelle Woche und Vorwoche zusammen live.
- Die Regel "Snapshot schlägt Live" aus dem Monats-Report gilt hier nicht; sie gehört nur zur Vormonats-Snapshot-Suche.

### 3. Pull-Skills aufrufen

- Nur die Quellen aus Schritt 1.
- Jeweils mit `--pulse` und der Vorwoche als `--compare-start`/`--compare-end` im selben Aufruf, damit der `comparison`-Block in derselben `-pulse.json` steht (Schema wie beim Monats-Erstlauf, mit Wochengrenzen).
- Zielordner ist der Daten-Ordner von heute. Ein zweiter Lauf am selben Tag überschreibt ihn idempotent.

**GA4** (nur bei `sessions` oder `conversion_rate`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ga4/scripts/ga4_pull.py" \
  --property <ga4_property_id> \
  --creds "$PTAI_GOOGLE_CREDENTIALS" \
  --start 2026-08-03 --end 2026-08-09 \
  --compare-start 2026-07-27 --compare-end 2026-08-02 \
  --out "reporting/data/$(date +%F)" \
  --config reporting/config.json \
  --pulse
```

**GSC** (nur bei `gsc_clicks` oder `gsc_impressions`; ohne `--inspect-urls`, die Index-Stichprobe ist keine Puls-KPI):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-gsc/scripts/gsc_pull.py" \
  --site <gsc_site> \
  --creds "$PTAI_GOOGLE_CREDENTIALS" \
  --start 2026-08-03 --end 2026-08-09 \
  --compare-start 2026-07-27 --compare-end 2026-08-02 \
  --out "reporting/data/$(date +%F)" \
  --pulse
```

**Shopify** (kein Script; Ablauf aus `pull-shopify` mit Wochen- statt Monatsfenstern):

1. Query "Umsatz-Totals" (`SHOW total_sales, net_sales, orders, average_order_value SINCE <Montag> UNTIL <Sonntag>`) für Umsatz, Bestellungen und AOV.
2. Bei `sessions` oder `conversion_rate` zusätzlich die Query "Sessions und Conversion Rate".
3. Jede Query zweimal ausführen: aktuelle Woche und Vorwoche. Das Vorwochen-Ergebnis in einen `comparison`-Block (gleiche Struktur, eigener `period`).
4. Nicht ziehen: Zeitreihe (`TIMESERIES day`), Top-Produkte, Bestand. `by_month`, `top_products` und `top_collections` bleiben in `shopify-pulse.json` `null` mit `"notes"`-Eintrag "im Puls nicht gezogen".
5. Ausgabe: `reporting/data/<heute>/shopify-pulse.json`.

### 4. Werte, Deltas und Auffälligkeiten

- Jeden KPI-Wert nach der Tabelle in Schritt 1 aus der neuen `-pulse.json` lesen, Conversion-Präzedenz anwenden.
- Delta immer als relative Veränderung zur Vorwoche in Prozent, auch bei der Conversion Rate (relative Veränderung der Rate, keine Prozentpunkte), damit die Schwelle einheitlich gilt.
- Nullwerte, fehlende Felder und Fehler-Shapes je Snapshot-Datei: genau nach `skills/report/SKILL.md`, Abschnitt "Fehler-Shapes je Quelle".
- Jede Zahl stammt aus einem Snapshot-Feld; nichts schätzen, nichts erfinden.
- Deutsche Formate: `2.500 €`, `1,5 %`, Deltas mit Vorzeichen `+8,2 %`.
- Formeln und Schwellen nur aus `${CLAUDE_PLUGIN_ROOT}/reference/metrics.md`; keine eigene Logik, keine eigenen Grenzwerte. Die 20-Prozent-Schwelle steht dort als plugin-weite Auffälligkeits-Schwelle.

Eine KPI ist auffällig, wenn mindestens eines gilt:

- relatives Delta betragsmäßig `>= 20 %`
- Vorwochenwert oder aktueller Wert ist 0 (Null-Linie); ein Prozent-Delta ist dann nicht sinnvoll, die Null-Linie selbst ist die Auffälligkeit

Kommentare:

- Nur auffällige Zeilen bekommen einen Kommentar, ein bis zwei Sätze, aus der Zahl begründet.
- Alle anderen KPIs ohne Kommentar in der Tabelle.
- Keine auffällige KPI: ein Satz "keine Auffälligkeiten diese Woche" statt eines leeren Abschnitts.
- Fehlt der Nenner (zum Beispiel AOV ohne Bestellung in der Vorwoche): "nicht berechenbar" statt Delta, keine Division durch 0.

### 5. GSC-Nachlauf kennzeichnen

- GSC-Daten kommen 2 bis 3 Tage verspätet.
- Liegen zwischen dem Sonntag der Puls-Woche und dem Ausführungstag weniger als 4 Tage (gleiche Schwelle wie im Monats-Report): bei den GSC-KPIs vermerken, dass die Zahlen dieser Woche noch steigen können und das kein Fehler ist.

### 6. Markdown schreiben

Datei: `reporting/reports/YYYY-Www-pulse.md` (ISO-Woche der Puls-Woche, zum Beispiel `2026-W32-pulse.md`). Inhalt in dieser Reihenfolge:

1. H1 `<Brand> · Wochen-Puls KW <Nr>/<Jahr>`
2. eine Zeile mit dem Zeitraum
3. KPI-Tabelle
4. Sätze zu den Auffälligkeiten
5. bei Bedarf der GSC-Nachlauf-Hinweis
6. Trennlinie `---`
7. letzte Zeile exakt: `Erstellt mit ptai-ecom von [Path to AI](https://path-to-ai.com).` Nicht umformulieren, nicht kürzen, nichts danach.

### 7. Zusammenfassung an den Nutzer

- auffällige KPIs in Kurzform
- nicht verfügbare Quellen, falls vorhanden
- Pfad zur `.md`

## Ausgabe-Format

Beispiel für `reporting/reports/2026-W32-pulse.md` (illustrative Zahlen, kein Kundenstand):

```markdown
# Beispielshop · Wochen-Puls KW 32/2026

Zeitraum: 03.08. bis 09.08.2026 gegenüber Vorwoche 27.07. bis 02.08.2026.

| KPI | KW 32 | KW 31 | Delta |
|---|---|---|---|
| Sessions¹ | 340 | 298 | +14,1 % |
| Umsatz | 210 € | 0 € | Null-Linie |
| Bestellungen | 1 | 0 | Null-Linie |
| Conversion Rate¹ | 0,3 % | 0,0 % | Null-Linie |
| AOV | 210,00 € | keine | nicht berechenbar |
| GSC-Klicks | 61 | 54 | +13,0 % |
| GSC-Impressionen | 3.410 | 2.750 | +24,0 % |

¹ aus ga4.json (Fallback): shopify.json trägt unter sessions den Wert null.

**Auffälligkeiten:**

- Umsatz und Bestellungen sprangen von 0 auf 210 €/1 Bestellung: die erste
  Conversion seit der Vorwoche, bei diesem Volumen keine Trendaussage.
- GSC-Impressionen +24,0 % (2.750 auf 3.410), die Klicks zogen mit +13,0 %
  deutlich schwächer mit, ein Blick auf die Snippets der gewinnenden Seiten
  lohnt sich.

GSC-Zahlen für diese Woche können noch nachträglich steigen (Meldeverzug 2
bis 3 Tage).

---

Erstellt mit ptai-ecom von [Path to AI](https://path-to-ai.com).
```

## Fehlerbilder

| Fall | Vorgehen |
|---|---|
| Config fehlt | nicht raten, auf `/ptai-ecom:setup` verweisen, aufhören |
| `pulse_kpis` fehlt | kein Fehler, Default-Satz aus der Spec |
| Unbekannter Schlüssel in `pulse_kpis` | mit Warnung überspringen, übrige KPIs normal |
| Quelle einer KPI auf `sources: false` | betroffene Zeilen "nicht verfügbar (Quelle nicht aktiv)", Pull entfällt, Rest läuft |
| Einzelner Pull scheitert | abhängige Zeilen "nicht verfügbar (Grund)"; Shapes (`null`-Felder, `{"error": ...}`) in den Fehlerbildern der Pull-Skill und in `skills/report/SKILL.md`, Abschnitt "Fehler-Shapes je Quelle" |
| Conversion-Präzedenz erschöpft (Shopify- und GA4-Feld `null` oder nicht verfügbar) | "nicht berechenbar", kein Delta |
| Alle benötigten Quellen scheitern | kein Puls; abbrechen, Gründe je Quelle nennen, auf `/ptai-ecom:setup` verweisen, keine leere Tabelle |
| GSC-Meldeverzug | kein Fehler, nur Kennzeichnung nach Schritt 5 |
