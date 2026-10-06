<!-- naming-lint: schema (CWV-Snapshot, durch bestehende Kundenlaeufe eingefroren: cwv.json liegt in mehreren Kunden-Workspaces) -->
---
name: pull-cwv
description: Zieht Core-Web-Vitals-Daten (Feld- und Lab-Werte plus CrUX-Wochenhistorie) über die PageSpeed-Insights-API je Seitentyp für den Kunden-Report oder den Wochen-Puls und legt sie als Snapshot ab. Einsetzen, wenn ein Monats-Report oder Puls CWV-Zahlen braucht oder der Nutzer ausdrücklich Core-Web-Vitals- oder PageSpeed-Daten der Kunden-Site abrufen will. Liest reporting/config.json und .env im Kunden-Workspace.
---

# pull-cwv: Core-Web-Vitals-Snapshot ziehen

Zieht per PageSpeed Insights API je Seitentyp (aus `config.page_types()`, ersatzweise `cwv_urls`):

- CrUX-Feldwerte (LCP, INP, CLS)
- Lighthouse-Lab-Performance-Score
- CrUX-Wochenhistorie je Origin

Ablage als Snapshot im Kunden-Workspace. Aufruf durch Report- und Puls-Lauf oder einzeln.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `page_types` (URL je Seitentyp, gelesen über `config.page_types()`) und `sources.cwv` ungleich `false`.
- Fehlt `page_types` ganz: ersatzweise `cwv_urls`. Das ist dieselbe Liste, die `pull-gsc` als Index-Stichprobe nutzt; keine zweite Liste pflegen.
- `PTAI_PSI_KEY` in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env` (PageSpeed-Insights-API-Key, gilt auch für die CrUX-History-API).
- `curl` und `jq` installiert (dokumentierte Voraussetzung des Plugins).

Fehlt etwas oder steht `sources.cwv` auf `false`: CWV als "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf (Report/Puls) scheitert nie daran.

## Ablauf

1. `reporting/config.json` lesen, Seitentypen bevorzugt über `config.page_types()`:

   ```bash
   python3 -c "
   import json, sys
   sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   from audit import config
   cfg = json.load(open('reporting/config.json'))
   print(json.dumps(config.page_types(cfg), ensure_ascii=False))
   "
   ```

   - Ergebnis hat immer die sechs Schlüssel `start, collection, product, cart, search, blog`.
   - Nicht konfigurierter Typ: Wert `null`, der Schlüssel bleibt.
   - Fehlt `page_types` ganz: die alte Liste `cwv_urls` verwenden. Jede URL daraus erhält im Script den Platzhalter-Seitentyp `unnamed`.
   - Den Key findet das Skript selbst.

2. Kein Zeitraum nötig. CWV ist eine Momentaufnahme, kein Zeitraum-Pull wie GA4 oder GSC.

3. **Nur Seitentypen mit URL werden Argument.** Jedes Paar mit URL (ohne `null`) wird zu `<page_type>=<url>`. Erstes Argument ist der Zielordner: **Daten-Ordner des laufenden Audits oder Reports** (`reporting/data/<run-id>`); ohne Lauf-ID der heutige Daten-Ordner wie im Beispiel (siehe Snapshot-Schema):

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/pull-cwv/scripts/psi_pull.sh" \
     "reporting/data/$(date +%F)" - <page_type>=<url> [<page_type>=<url> ...]
   ```

   Ein Seitentyp ohne URL (`null`) wird kein Argument, erscheint aber als "nicht konfiguriert: <Seitentyp>" in der Meldung an den Nutzer (Schritt 4).

4. Dem Nutzer melden:
   - Performance-Score je Seitentyp
   - LCP, INP, CLS aus den Feldwerten, sofern vorhanden
   - Auffälligkeiten, etwa ein Seitentyp im POOR-Bereich
   - CrUX-Wochenhistorie je Origin, sonst der Grund aus dem `error`-Feld
   - jeden nicht konfigurierten Seitentyp aus Schritt 3, nie stillschweigend weglassen
   - fehlende Feld-Datenbasis einer URL als "keine CrUX-Daten (zu wenig Traffic)", nicht als Fehler

## Snapshot-Schema

### Zielordner

- Der Aufrufer bestimmt den Zielordner.
- Solo: Vorgabe `reporting/data/<heute>`. Dort legen auch `report` und `pulse` ab, solange sie ohne Lauf-ID laufen (Spec Abschnitt 14, Umstellung in Stufe 3).
- **In einem Audit oder Report mit Lauf-ID: `reporting/data/<run-id>`**, Datum plus Kadenz (`2026-10-01-audit`, `2026-11-01-month`). Das erste Script-Argument (`<out-dir>`) zeigt dorthin.
- Der Orchestrator gibt den Ordner vor. Bei manuellem Start während eines Laufs dieselbe Lauf-ID verwenden.
- Ein Snapshot im falschen Ordner fehlt der Analyse, und sie rechnet ohne Fehlermeldung weiter.

### Datei

Das Script schreibt `<out-dir>/cwv.json`:

```json
{
  "fetched_at": "2026-08-10T12:00:00Z",
  "strategy": "mobile",
  "pages": [
    {
      "page_type": "start",
      "url": "https://beispielshop.de/",
      "field_data": {
        "lcp_ms": 2100, "lcp_category": "AVERAGE",
        "inp_ms": 180, "inp_category": "FAST",
        "cls": 0.08, "cls_category": "FAST"
      },
      "lab": { "performance_score": 0.82, "lcp_ms": 2050.3, "cls": 0.07 }
    },
    { "page_type": "product", "url": "https://beispielshop.de/products/BELIEBIG", "error": "HTTP 403: ..." }
  ],
  "historie": [
    {
      "origin": "https://beispielshop.de",
      "wochen": [
        { "start": "2026-03-02", "ende": "2026-03-29", "lcp_ms": 2050, "inp_ms": 175, "cls": 0.07 }
      ]
    },
    { "origin": "https://blog.beispielshop.de", "error": "keine CrUX-Historie (HTTP 404: chrome ux report data not found)" }
  ]
}
```

### Regeln zum Schema

- Kein `period`-Block, kein `comparison`.
- Der Report vergleicht gegen den Vormonats-Snapshot (jüngster `reporting/data/`-Ordner mit `cwv.json`).
- `historie` ersetzt diesen Vergleich nicht: sie deckt rund 25 Wochen bis heute ab, keinen festen Vergleichszeitraum wie GA4 oder GSC.
- `page_type` stammt aus dem Argument `<page_type>=<url>`. Ein Argument ohne `=` erhält `unnamed`, damit alte Aufrufe ohne Seitentyp weiterlaufen.
- `field_data: null`: CrUX hat für die URL keine Feld-Datenbasis. Bei kleinen Sites normal, kein Fehler.
- `lab` ist unabhängig davon vorhanden, solange der Call gelungen ist.
- Scheitert der Call einer URL (HTTP-Fehler, Timeout, ungültige Antwort): Eintrag `{"page_type", "url", "error"}` statt `field_data`/`lab`. Die übrigen Einträge bleiben unberührt.
- `historie`: ein Eintrag je eindeutigem Origin der übergebenen URLs, nicht je Seitentyp. Seitentypen auf demselben Shop teilen einen Eintrag.
- Jeder `historie`-Eintrag hat entweder `wochen` (rund 25 aufsteigend sortierte Wochenwerte für LCP, INP, CLS als p75-Perzentile) oder ein `error`-Feld.
- `error` in `historie`: zu wenig CrUX-Traffic für den Origin, gleiche Ursache wie `field_data: null`, nur für die Zeitreihe.

## Setup-Check

`--check` testet Auth plus einen schnellen Call gegen `https://example.com/` (nur Performance-Kategorie). Ausgabe: eine OK- oder Fehlerzeile, Exit 0/1. Für den Setup-Wizard:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/pull-cwv/scripts/psi_pull.sh" --check -
```

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| `Fehler: 'jq' ist nicht installiert` oder `'curl' ist nicht installiert` | Nachinstallieren (`brew install jq`), erneut starten. |
| HTTP 400/403 vom PSI-Endpunkt | Meist ungültiger oder gesperrter API-Key. In der Google Cloud Console prüfen, ob die PageSpeed-Insights-API für den Key aktiv ist. |
| `error`-Eintrag statt `field_data`/`lab` bei einzelnen URLs | Nicht fatal, die übrigen URLs bleiben vollständig. |
| `field_data: null` | Kein Fehler: zu wenig CrUX-Traffic (typisch bei kleinen Sites). Der Report zeigt "keine Feld-Daten" und nutzt den Lab-Score. |
| `error`-Eintrag statt `wochen` in `historie` | Meist zu wenig CrUX-Traffic für den Origin (HTTP 404 der CrUX-History-API, Meldung etwa "chrome ux report data not found"), kein technischer Fehler. Übrige Origins und `pages` bleiben unberührt. |
| Seitentyp aus `config.page_types()` ohne URL | Kein Argument, aber immer die Meldung "nicht konfiguriert: <Seitentyp>" an den Nutzer (Ablauf Schritt 3/4). |
