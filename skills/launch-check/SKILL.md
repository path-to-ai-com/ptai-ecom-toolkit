---
name: launch-check
description: Prüft vor einem Livegang alle Launch-Voraussetzungen und gibt aus, was noch fehlt, als wiederholbarer Prüflauf mit Go/No-Go-Empfehlung. Je Punkt der Launch-Checkliste ein Status (ok, missing, blocked, manual, n/a) mit einer Zeile Beleg, Verantwortlichem und Links auf Entwurf und Live: Zeitpunkt (Wochentag, Feiertag, Saisonspitze, Kampagnen, Preis- und A/B-Tests), Abnahme und offene Befunde aus jedem Prüfbericht (auch außerhalb des Workspace über theme_migration.report_paths), Prüfliste aus Phase 2, Abgleich mit dem Live-Stand, Änderungsstopp, Entwurf und Rückfall-Theme, App-Embeds, Theme-Übersetzungen, Tracking je Seite per Mitschnitt, Pagination und Analyse-Ereignisse je Seitentyp, SEO (robots.txt, noindex, Canonicals, Statuscodes, strukturierte Daten, hreflang, Open Graph, Title und Description je Seitentyp und Sprache gegen live), Vergleichswerte von heute oder gestern, Go/No-Go- und Rückfallkriterien, Kommunikation, Plattform-Fristen. Mit --after die Prüfungen direkt nach dem Veröffentlichen. Führt Phase 9 der Theme-Migration eigenständig aus, auch ohne Migrationslauf und für Launches ohne Theme-Wechsel (größere Theme-Änderung, neuer Shop). Nutzen bei /ptai-ecom:launch-check, "Launch-Check", "sind wir bereit für den Livegang", "was fehlt noch bis zum Launch", "Go/No-Go", "Prüfung nach dem Veröffentlichen", in Phase 9 einer Theme-Migration. Schreibt nichts in den Shop und veröffentlicht nie. Liest reporting/config.json im Kunden-Workspace.
---

# launch-check: bereit für den Livegang?

Typische Launch-Fehler sind einzelne vergessene Punkte: ein Embed, das im Entwurf nie eingeschaltet
wurde, eine eigene `robots.txt`, die mit dem alten Theme entfällt, ein Tag-Manager-Container, der im
neuen Theme fehlt, ein Termin am Freitag vor einem Feiertag. Diese Skill:

- geht die Launch-Checkliste Punkt für Punkt durch
- prüft automatisch, was automatisch prüfbar ist
- stellt für den Rest eine klare Frage an die zuständige Person
- gibt eine Go/No-Go-Empfehlung

Ein offener Befund, ein offener Punkt der Prüfliste und eine Lücke der SEO-Ausgabe sind nie eine
Frage, sondern `missing`; ein Bericht, der sich nicht finden lässt, ist `blocked`. Am 07.10.2026 ging
ein Shop live, weil hier stattdessen gefragt wurde, ob alles erledigt sei.

Sie ersetzt `theme-migration` nicht, sondern führt deren Phase 9 als eigenständigen Prüflauf aus:
beliebig oft, mit oder ohne Migrationslauf, auch für einen Launch ohne Theme-Wechsel.

Quellen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`: `launch-checklist.md`, dazu
`rollback.md`, `change-freeze.md`, `apps-and-tracking.md`, `translations.md`, `seo-parity.md` und
`post-launch.md`.

Arbeitsverzeichnis: der Kunden-Workspace mit `reporting/`, wie bei jeder Skill dieses Plugins.

## Was immer gilt

- **Schreibt nie in den Shop und veröffentlicht nie.** Keine Mutation, kein `themePublish`, kein
  `shopify theme publish`. Den Klick macht ein Mensch im Admin.
- **Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit**, nie aus dem Gedächtnis. Die
  Abfragen des Moduls sind gegen das Admin-Schema 2026-04 validiert. Neue Abfragen vorher mit
  `shopify-plugin:shopify-admin` prüfen, CLI-Flags mit `shopify-plugin:shopify-use-shopify-cli`.
- **Jede Aussage über den Shop verlinkt die betroffene Seite**, bei einem Unterschied Entwurf und Live,
  jeweils mit `?preview_theme_id=<id>`. Auch der Link auf das Live-Theme enthält seine ID, weil Shopify
  eine Vorschau per Cookie speichert.
- **Die Vorschau eines Entwurfs ist nur im Browser verlässlich.** Ein Abruf ohne Browser liefert den
  Live-Shop. Seiten des Entwurfs deshalb aus einem Mitschnitt lesen, nie per `curl`.
- **Höchstens zwei Browser gleichzeitig auf der Storefront**, sonst folgen HTTP 429 und eine
  Bot-Abfrage, und der Bericht sieht trotzdem vollständig aus. Abrufe ohne Browser (nur mit
  `--after`) laufen nacheinander mit vier Sekunden Abstand.
- **Nicht Prüfbares steht als `blocked` mit Grund, nie als `ok`.** Eine Antwort auf eine Frage gilt nur
  mit dem Namen der antwortenden Person.

## Die Status

| Status | Bedeutung |
|---|---|
| `missing` | geprüft, fehlt oder verletzt eine Regel; muss vor dem Launch erledigt sein |
| `blocked` | nicht prüfbar, weil eine Voraussetzung fehlt (Zugang, Entwurfs-ID, Mitschnitt) |
| `manual` | braucht einen Menschen; der Punkt enthält die Frage und wer sie beantwortet |
| `ok` | geprüft und erfüllt |
| `n/a` | trifft für diesen Launch nicht zu |

**Empfehlung:**

- `No-Go`, sobald ein Punkt `missing` ist
- `Offen`, solange Punkte `blocked` oder `manual` sind
- `Go` nur, wenn alles `ok` oder `n/a` ist

Ein Mensch entscheidet; die Entscheidung wird mit Namen gespeichert, in einer Migration als Gate G5.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und `domain`, eingerichtet über `setup`. Fehlt sie: `setup`
  anbieten und beenden.
- Lesezugang zum Shop wie in `theme-migration`, Phase 0 (`cli-grant` über `shopify store execute` oder
  `portal`). Für die Sprachen braucht der Grant `read_locales`, für Übersetzungen `read_translations`.
- Live- und Entwurfs-ID in dieser Reihenfolge: aus dem Migrationslauf (`run_state`), aus
  `theme_migration` der Config, über `--live-theme-id` und `--draft-theme-id`. IDs aus der Theme-Liste,
  nie aus dem Gedächtnis.
- `uv` für Playwright (Mitschnitt).
- Prüfberichte außerhalb des Workspace und die Prüfliste aus Phase 2 im Block `theme_migration` der
  Config:

  ```json
  "report_paths": ["{drive_path}/projects/<projekt>"],
  "acceptance_checklist": "migration/inventory/seo-checklist.md"
  ```

  - `report_paths`: Dateien, Ordner (ihre `*.md` und `findings.json`, nicht rekursiv) oder Muster;
    `~` und `{drive_path}` werden aufgelöst, relative Pfade gelten ab dem Workspace. Gelesen werden in
    Markdown die Abschnitte "Vor dem Launch" und "Blocker", in `findings.json` die Schweren `blocker`
    und `before_launch`, dazu immer der jüngste Bericht unter `migration/verify/`.
  - Erledigt ist ein Punkt mit Statusspalte (`Status` oder `Stand`), die mit `erledigt`, `behoben`,
    `done` oder ähnlich beginnt, als `- [x]` oder mit `Status: erledigt` im Text. Verschoben nur mit
    Person und Datum: `verschoben von <Name> am <JJJJ-MM-TT>`, in einer Tabelle auch `verschoben
    <Datum>` mit dem Namen in der Spalte `Wer`. Alles andere ist offen.
  - `acceptance_checklist`: die Prüfliste "Muss nach dem Umbau wieder da sein" mit Zeilen
    `- [ ] **P01** ...`. Fehlt sie bei einem Migrationslauf, steht der Punkt auf `blocked`.

## Ablauf vor dem Launch

Lauf-ID `<heute>-launch-check`, Ordner `reporting/runs/<heute>-launch-check/`, im Folgenden `$RUN`.

1. **Stand lesen.** Bei vorhandenem Migrationslauf `run_state show`:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state show
   ```

   Liefert IDs, letzten Abgleich, Änderungsstopp und Gates. Den Launch-Termin erfragen, wenn er weder dort
   (`freeze_until`) noch in der Config steht.

2. **Seitenliste festlegen.**
   - `migration/inventory/pages.json`, falls vorhanden.
   - Sonst `$RUN/pages.json` anlegen: je Seitentyp eine Seite (Startseite, Kategorie, Produkt, Seite,
     Blogartikel, Suche), mit Search Console die meistbesuchte.
   - **Jede veröffentlichte Sprache** braucht ihre Seiten, sonst ist der SEO-Vergleich unvollständig
     und steht auf `blocked`. Ergänzen, Primärsprache zuerst:

     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.seo_parity pages --pages "$RUN/pages.json" --locales de,en
     ```

   - Format wie in `capture_network.py`:
     `{"base_url": "https://...", "pages": [{"id", "template", "path"}]}`.

3. **Mitschnitt beider Themes**, zuerst das Live-Theme, dann den Entwurf, nie beide zugleich. Jeder Lauf
   begrenzt sich selbst auf zwei Browser:

   ```bash
   uv run --quiet --with playwright==1.58.0 python "${CLAUDE_PLUGIN_ROOT}/scripts/browser/capture_network.py" \
     --pages "$RUN/pages.json" --out "$RUN/capture/old-declined" --theme <live-theme-id>
   uv run --quiet --with playwright==1.58.0 python "${CLAUDE_PLUGIN_ROOT}/scripts/browser/capture_network.py" \
     --pages "$RUN/pages.json" --out "$RUN/capture/new-declined" --theme <draft-theme-id>
   ```

   Standard ist ohne Einwilligung. Mit `--consent accepted` nach `old-accepted` und `new-accepted` nur,
   wenn das Team den Mitschnitt mit Einwilligung freigegeben hat.

4. **Prüflauf:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.launch_check \
     --launch-date <YYYY-MM-DD> [--live-theme-id <id>] [--draft-theme-id <id>]
   ```

   - Das Modul findet die Mitschnitte unter `$RUN/capture/` selbst; andere Pfade über `--network-old` und
     `--network-new`.
   - Es schreibt `$RUN/launch-check.json` und `$RUN/launch-check.md` und gibt eine JSON-Zeile mit
     Empfehlung und Zahl je Status aus.

5. **Vorlegen.** Zuerst die Empfehlung, dann `missing` und `blocked` mit Beleg, Link und Verantwortlichem.
   Jeden Punkt `missing` vorher selbst ansehen.
   - Was laut Entscheidungsliste entfällt (`drop` oder `replace` in `migration/inventory/apps.json` oder
     `migration/mapping/decisions.json`), steht als `ok` mit der Entscheidung als Beleg.
   - Erscheint eine gewollte Streichung trotzdem als `missing`, fehlt sie in der Liste: mit Person, Datum
     und Grund in `decisions.json` nachtragen (`kind: app`), nie im Bericht übergehen.
   - Eine eigene Subdomain eines Dienstes (CNAME oder A-Eintrag, etwa ein Attributions-Endpunkt) gehört
     über `hosts` in ihre Zeile von `apps.json`; sonst erscheint sie als eigener Host und der
     Ausweich-Endpunkt des Dienstes als neu.

6. **Folgeschritte empfehlen, nicht selbst starten:**
   - `live-sync` auf `missing`: `sync-live-theme` (Abgleich II)
   - offene Befunde: beheben und im Bericht als erledigt markieren oder mit Person und Datum
     verschieben, dann `verify-theme` für die betroffenen Prüfer
   - Lücken in `seo-structured-data`, `seo-hreflang`, `seo-open-graph`: Horizon-Grundpaket prüfen
     (`build-theme`, `seo-parity.md`), hochladen, neu mitschneiden
   - alte Vergleichswerte: `pull-gsc`, `pull-ga4`, `pull-cwv` und `crawl-site` direkt vor dem Launch

7. **Fragen stellen.**
   - Jeder Punkt `manual` enthält eine Frage und den Adressaten (`Betreiber`, `Team` oder beide).
   - Fragen an das Team gesammelt an den Betreiber; die Nachricht schickt er, nicht die Skill.
   - Eine ausdrückliche Antwort mit Name und Datum nach `reporting/launch-answers.json`; sie gilt ab dem
     nächsten Lauf:

   ```json
   {"answers": {
     "timing-campaigns": {"status": "ok", "by": "<Name>", "at": "<YYYY-MM-DD>", "note": "kein Sale bis Ende Oktober"}
   }}
   ```

   - Erlaubt sind `ok`, `missing` und `n/a`.
   - Eine Antwort ändert nur einen Punkt `manual`, nie einen Befund; ohne `by` zählt sie nicht.
   - Terminabhängige Antworten (Kampagnen, Tests, Ansprechpartner) vor jedem neuen Termin neu einholen.

8. **Wiederholen**, bis die Empfehlung `Go` ist oder ein Mensch bewusst anders entscheidet. Ein weiterer
   Lauf am selben Tag überschreibt die Ausgabe; ein neuer Tag legt einen neuen Ordner an.

In einer Migration ist `launch-check.md` die Vorlage für Gate G5. Den Migrationsstand schreibt
`theme-migration`, nicht diese Skill.

## Nach dem Veröffentlichen (`--after`)

Direkt nachdem ein Mensch veröffentlicht hat, in dieser Reihenfolge:

1. **Mitschnitt des veröffentlichten Themes** nach `$RUN/capture/after-declined` mit
   `--theme <new-live-theme-id>`, dieselbe Seitenliste.
2. **Prüflauf:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.launch_check --after \
     --live-theme-id <old-live-theme-id> --draft-theme-id <new-live-theme-id> \
     [--network-old reporting/runs/<pre-launch-run>/capture/old-declined/network.json]
   ```

   - `--live-theme-id` ist hier die ID des **alten** Themes (Rückfall-Theme, Notiz zu G5).
   - Den Mitschnitt des alten Themes vom Tag vor dem Launch über `--network-old` übergeben, wenn er nicht
     im Ordner von heute liegt.
3. Ergebnis `$RUN/launch-check-after.json` und `.md`. Geprüft:
   - das veröffentlichte Theme ist das erwartete, das alte liegt als Entwurf vor
   - `robots.txt` antwortet und ist gleich wie vor dem Launch (verglichen mit `robots-live.txt` aus dem
     Lauf davor)
   - `robots.txt` je User-Agent-Gruppe: ein Fehler nur, wenn die Gruppe `*` oder Googlebot alles sperrt;
     ein `Disallow: /` für einen einzelnen anderen Crawler (bei Shopify etwa `Nutch`) steht als Hinweis
   - strukturierte Daten, hreflang, Open Graph und Kopfdaten des veröffentlichten Themes gegen den
     Mitschnitt des alten (`seo-*-after`), aus `capture/after-declined` gegen `--network-old`
   - Statuscodes, `noindex` und Canonicals der Seiten live. `noindex` im HTML ist ein Fehler, wenn es im
     Mitschnitt des alten Themes nicht stand. Der Header `X-Robots-Tag` kommt von Shopify, nicht vom Theme
     (etwa auf `/search`), und steht als Hinweis
   - fremde Hosts je Seite gegen den Stand vorher
   - Pagination und Analyse-Ereignisse je Seitentyp gegen den Mitschnitt vorher
   - jede veröffentlichte Sprache einmal
   - die Sitemap
   - als Fragen: Testbestellung, Einreichen der Sitemap, Festhalten des Stands

- Eine Testbestellung läuft **nur nach ausdrücklicher Freigabe durch das Team** und wird danach storniert
  und erstattet.
- Ab dem Umschalten gilt der Prüfplan in `post-launch.md`.

## Was geprüft wird

| Gruppe | Punkt | Wie |
|---|---|---|
| Zeitpunkt | Wochentag, Feiertag, Saisonspitze | aus dem Termin: Montag bis Donnerstag, kein bundesweiter Feiertag am Tag und am Folgetag, nicht ab vier Wochen vor Black Friday bis Jahresende |
| Zeitpunkt | Kampagnen, Preis- und A/B-Tests, Ansprechpartner | Fragen; ein Testwerkzeug im Mitschnitt steht als Hinweis daneben |
| Abnahme | G4, Befunde, Testrunde | Gate im Migrationslauf; jüngstes `migration/verify/*/findings.json` und jeder Bericht unter `theme_migration.report_paths` (offen: `blocker`, `before_launch`, Abschnitte "Vor dem Launch" und "Blocker" ohne Erledigt- oder Verschoben-Vermerk; kein Bericht: `blocked`); `reporting/runs/*-test/test.json` (offen: `open`, `in_progress`, `decision`) |
| Abnahme | Prüfliste aus Phase 2 | `theme_migration.acceptance_checklist`: jede Zeile `- [ ] **Pnn**` abgehakt, verschoben mit Person und Datum oder durch eine bestandene SEO-Prüfung abgedeckt (`seo-parity.md`) |
| Abgleich | Live-Theme seit dem letzten Abgleich | `updatedAt` frisch gegen jüngstes `delta.json` oder `manifest.json` unter `migration/` |
| Abgleich | Änderungsstopp | `freeze_from` und `freeze_until` im Lauf oder `theme_migration.freeze`, deckt den Termin |
| Entwurf | Entwurf, Rückfall-Theme | Rolle `UNPUBLISHED`, nicht in Verarbeitung; Live-Theme `MAIN`, ID notiert |
| Apps | App-Embeds | aktive Embeds aus `config/settings_data.json` beider Themes; gestrichen laut `apps.json` oder `decisions.json` ist `ok` mit Beleg |
| Übersetzungen | Theme-Übersetzungen | je veröffentlichter Sprache: übersetzt, veraltet, Anteil neu gegen alt |
| Tracking | Hosts je Seite | Mitschnitt alt gegen neu, je Consent-Zustand; Shopify selbst und die Shop-Domain zählen nicht, ihre Subdomains schon (zugeordnet über `hosts` in `apps.json`); gestrichen laut Entscheidungsliste ist `ok` mit Beleg |
| Tracking | Pagination und Analyse-Ereignisse | je Seitentyp und Gerät: `page=N` in `final_url` (Nachladen beim Scrollen schreibt die Seite in die Adresse) und Anfragen je Analysedienst, Minimum neu gegen Maximum alt; ab 1,5-fach und 3 mehr ein Fehler, geändertes Nachladen allein eine Frage |
| SEO | robots.txt | `templates/robots.txt.liquid` in beiden Themes, Live-Ausgabe gesichert |
| SEO | Statuscodes, noindex, Canonicals | aus dem Mitschnitt des Entwurfs gegen den des Live-Themes |
| SEO | strukturierte Daten, hreflang, Open Graph, Title, Description, Canonical | `theme.seo_parity` je Seite des Mitschnitts: was live da ist und im Entwurf fehlt, ist `missing`; eine `ProductGroup` mit Varianten ohne `description` immer; fehlt ein Seitentyp (Startseite, Kategorie, Produkt) oder eine veröffentlichte Sprache im Mitschnitt, `blocked` |
| Vergleichswerte | GSC, GA4, CWV, Crawl | jüngste Datei unter `reporting/data/` vom Termin oder Vortag |
| Go/No-Go | Kriterien, Rückfallgrenzen, Kommunikation | Fragen |
| Plattform-Fristen | Kundenkonten, Skript-Tags | `customerAccountsV2` und `templates/customers/` im Entwurf; `asyncLoad` im HTML des Live-Themes |

## Was die Skill nicht automatisch prüfen kann

- Kampagnen, laufende Tests, Ansprechpartner, regionale Feiertage und andere Länder als Deutschland.
- Ob Go/No-Go- und Rückfallkriterien schriftlich vorliegen und das Team die Liste aus `rollback.md`
  gesehen hat; ob die Kommunikation verschickt ist.
- Checkout, Dankeseite und Kauf-Events: nur mit einer Testbestellung nach Freigabe.
- Tracking mit Einwilligung, solange das Team den Mitschnitt nicht freigegeben hat.
- App-Blöcke in Templates (nur Embeds), Inhalte von Bewertungen oder Suche: das zeigt die Testrunde.
- Die volle Schutzliste der Top-Seiten aus der Search Console: geprüft wird die Seitenliste; die
  Schutzliste deckt `crawl-site` gegen den Entwurf ab.
- Markt-Pfade, die nicht dem Muster `/<sprache>` folgen, und ob Rollouts im Admin verfügbar sind.

## Ergebnis

`reporting/runs/<date>-launch-check/` mit:

- `launch-check.json`, je Punkt `id`, `group`, `title`, `status`, `evidence`, `action`, `owner`,
  `question`, `links`
- `launch-check.md` mit der Empfehlung oben und den Punkten je Status (`missing` und `blocked` zuerst)
- `pages.json`, `capture/` und `robots-live.txt`
- mit `--after` dieselben Dateien als `launch-check-after.*`

Es entstehen keine Bilder.

## Fehlerbilder

- **Alles `blocked`:** kein Shopify-Zugang. `shopify store auth` über die Shopify-Skills erneuern, dann
  erneut ausführen.
- **Tracking `blocked` mit falschem Theme:** der Mitschnitt zeigte nicht das erwartete Theme
  (Vorschau-Cookie, Weiterleitung). Neu mitschneiden, den Befund nie übergehen.
- **Hunderte fehlende Hosts:** Mitschnitte mit und ohne Einwilligung vermischt oder verschiedene
  Seitenlisten. Beide Themes mit derselben `pages.json` und demselben Consent-Zustand mitschneiden.
- **Befunde `blocked`, obwohl es einen Prüfbericht gibt:** er liegt außerhalb des Workspace.
  `theme_migration.report_paths` auf seinen Ordner setzen; ist der Ordner nicht eingebunden (Drive
  offline), steht er unter "nicht gefunden".
- **SEO-Zeilen `blocked` mit "Sprache nicht im Mitschnitt":** die Seitenliste hat keine Seite der
  Sprache. `theme.seo_parity pages` ergänzen, beide Themes neu mitschneiden.
- **`seo-hreflang` meldet doppelte Werte:** Shopifys automatische Tags und das Snippet
  `<prefix>-hreflang` laufen zugleich. Eines davon abschalten (`seo-parity.md`, Horizon-Grundpaket).
- **Rückfall-Theme `blocked` nach dem Launch:** die Live-Theme-ID zeigt schon auf das neue Theme.
  `--live-theme-id` mit der alten ID aus der Notiz zu G5.
- **Jemand bittet um Veröffentlichen:** die Skill veröffentlicht nicht, auch nicht auf Wunsch. Sie nennt
  den Weg im Admin (`launch-checklist.md`, Veröffentlichen).
