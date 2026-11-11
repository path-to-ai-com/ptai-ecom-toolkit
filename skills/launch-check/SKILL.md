---
name: launch-check
description: Prüft vor einem Livegang alle Launch-Voraussetzungen und gibt aus, was noch fehlt, als wiederholbarer Prüflauf mit Go/No-Go-Empfehlung. Je Punkt der Launch-Checkliste ein Status (ok, missing, blocked, manual, n/a) mit einer Zeile Beleg, Verantwortlichem und Links auf Entwurf und Live: Zeitpunkt (Wochentag, Feiertag, Saisonspitze, Kampagnen, Preis- und A/B-Tests), Abnahme und offene Befunde aus jedem Prüfbericht (auch außerhalb des Workspace über theme_migration.report_paths), Prüfliste aus Phase 2, Abgleich mit dem Live-Stand, Änderungsstopp, Entwurf und Rückfall-Theme, App-Embeds, App-Einträge gegen den hochgeladenen Stand, Theme-Übersetzungen, Tracking je Seite per Mitschnitt, Werbe- und Analyseaufrufe vor Einwilligung, Pixel-Liste des Shops und Sicherung der Custom Pixels, Pagination und Analyse-Ereignisse je Seitentyp, SEO (robots.txt, noindex, Canonicals, Statuscodes, strukturierte Daten, hreflang, Open Graph, Title und Description je Seitentyp und Sprache gegen live), Vergleichswerte von heute oder gestern, Go/No-Go- und Rückfallkriterien, Kommunikation, Plattform-Fristen. Mit --after die Prüfungen direkt nach dem Veröffentlichen, mit Testbestellung nach Freigabe (Kasse bis zur Zahlung, Kauf je Ziel in Shopify, GA4 je Property, Google Ads je Kauf-Conversion, Meta, Storno), Tracking nach Einwilligung, App-Einträgen seit dem Veröffentlichen und Pixel-Liste vorher gegen nachher. Führt Phase 9 der Theme-Migration eigenständig aus, auch ohne Migrationslauf und für Launches ohne Theme-Wechsel (größere Theme-Änderung, neuer Shop). Nutzen bei /ptai-ecom:launch-check, "Launch-Check", "sind wir bereit für den Livegang", "was fehlt noch bis zum Launch", "Go/No-Go", "Prüfung nach dem Veröffentlichen", in Phase 9 einer Theme-Migration. Zeigt jeden Go-Punkt als Haken-Liste (bin/theme launch check: ✅ erledigt, ❌ fehlt, ⏸ blockiert, ✋ manuell, Summe am Ende); in einer Migration ist G5 selbst ein Go-Punkt. Schreibt nichts in den Shop und veröffentlicht nicht selbst; veröffentlicht wird im geführten Launch von theme-migration nach dem Ja der Person der Marke. Liest reporting/config.json im Kunden-Workspace.
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

**Die Quelle für offene Punkte ist die eine Liste** `migration/open-items.json` (Skill
`theme-migration`, Abschnitt "Die Liste offener Punkte"), sobald es sie gibt oder ein Migrationslauf
besteht:

- `acceptance-open-items`: jeder offene Punkt der Gates G4 und G5 ist `missing`; fehlt die Liste in
  einem Migrationslauf, `blocked`.
- `acceptance-sources`: Prüfberichte (`report_paths`, jüngster unter `migration/verify/`), die
  Prüfliste aus Phase 2 und die jüngste Abnahme sind nur noch Quellen für die Liste. Was dort offen
  steht und in der Liste fehlt, ist `missing`; eine konfigurierte Quelle, die sich nicht finden lässt,
  `blocked`.
- Deckt eine bestandene Prüfung dieses Laufs einen offenen Punkt ab (etwa hreflang), steht das im
  Beleg; erledigt wird er erst in der Liste, mit `open_items close-covered`.

Ohne Liste und ohne Migrationslauf (Launch ohne Theme-Wechsel) gilt die Auswertung je Bericht,
Prüfliste und Abnahme wie unten beschrieben.

Sie ersetzt `theme-migration` nicht, sondern führt deren Phase 9 als eigenständigen Prüflauf aus:
beliebig oft, mit oder ohne Migrationslauf, auch für einen Launch ohne Theme-Wechsel.

Quellen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`: `launch-checklist.md`, dazu
`rollback.md`, `change-freeze.md`, `apps-and-tracking.md`, `translations.md`, `seo-parity.md` und
`post-launch.md`.

Arbeitsverzeichnis: der Kunden-Workspace mit `reporting/`, wie bei jeder Skill dieses Plugins.

## Was immer gilt

- **Schreibt nie in den Shop und veröffentlicht nicht selbst.** Keine Mutation, kein `themePublish`, kein
  `shopify theme publish` in dieser Skill. Veröffentlicht wird seit 10.11.2026 im geführten Launch
  (`theme-migration`, Phase 9: `bin/theme launch publish`), nur wenn diese Prüfung grün ist und die Person
  der Marke ausdrücklich Ja gesagt hat. Ohne Migrationslauf veröffentlicht ein Mensch im Admin.
- **Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit**, nie aus dem Gedächtnis. Die
  Abfragen des Moduls sind gegen das Admin-Schema 2026-04 validiert. Neue Abfragen vorher mit
  `shopify-plugin:shopify-admin` prüfen, CLI-Flags mit `shopify-plugin:shopify-use-shopify-cli`.
- **Jede Aussage über den Shop verlinkt die betroffene Seite**, bei einem Unterschied Entwurf und Live,
  jeweils mit `?preview_theme_id=<id>`. Auch der Link auf das Live-Theme enthält seine ID, weil Shopify
  eine Vorschau per Cookie speichert.
- **Die Vorschau eines Entwurfs ist nur im Browser verlässlich.** Ein Abruf ohne Browser liefert den
  Live-Shop. Seiten des Entwurfs deshalb aus einem Mitschnitt lesen, nie per `curl`.
- **Höchstens zwei Browser gleichzeitig auf der Storefront**, sonst folgen HTTP 429 und eine
  Bot-Abfrage, und der Bericht sieht trotzdem vollständig aus. Abrufe ohne Browser laufen nacheinander
  mit vier Sekunden Abstand; vor dem Launch sind es nur `robots.txt` und, wenn der Mitschnitt kein HTML
  trägt, die Startseite des Live-Shops für die Pixel-Liste.
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

Ein Mensch entscheidet; die Entscheidung wird mit Namen gespeichert, in einer Migration als Gate G5. In
einem Migrationslauf steht G5 deshalb selbst als Punkt `go-decision` in der Liste: offen ist er `manual`
mit der Frage an die Person der Marke, entschieden `ok` mit Name und Datum. Grün, also `Go`, ist ein
Migrationslauf erst mit G5.

## Die Haken-Liste

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" launch check [--after] [Argumente des Prüflaufs]
```

Führt den Prüflauf aus (dieselben Argumente wie `launch_check`, dieselben Dateien) und gibt statt der
JSON-Zeile die Liste aus, die der Person gezeigt wird:

```
✅ Abgleich vor dem Launch
   letzter Abgleich 2026-11-10, vor 0 Tagen
⏸ Vergleichswerte
   kein Zugang zu GA4
✋ Go/No-Go entschieden (G5)
   Go für den Launch am 12.11.2026? ...

1 von 3 grün
Entfällt für diesen Launch: Kundenkonten
```

- Je Punkt Symbol und Titel, darunter eine Zeile Beleg; bei ✋ steht dort die Frage. ✅ ist `ok`,
  ❌ `missing`, ⏸ `blocked`, ✋ `manual`. `n/a` zählt nicht mit und steht in der Zeile "Entfällt".
- Vor dem Launch: alles grün heißt Exit 0, und darunter steht "Jetzt Launch durchführen?" mit neuem und
  altem Theme und dem Rückfall-Theme. Sonst Exit 1, keine Frage, sondern je fehlendem Punkt, was zu tun
  ist, und "Wer:". "diese Sitzung" ist, wer den Prüflauf ausführt (bis 0.3.26 hieß das Betreiber).
- Mit `--after` dieselbe Liste für die Prüfungen nach dem Veröffentlichen, am Ende der Stand
  (`published_at` mit dem Namen der Person, die Ja gesagt hat, neue `live_theme_id`, Rückfall-Theme).
- `--json` gibt eine Zeile mit `green`, `recommendation`, `counts` und `ask` aus.
- Die ausführliche Fassung mit Aktion, Links und Verantwortlichem bleibt `launch-check.md`.

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
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
   ```

   Liefert IDs, letzten Abgleich und Gates. Den Launch-Termin übergibt der Betreiber mit
   `--launch-date`; ohne ihn steht der Termin als offene Frage im Bericht.

2. **Seitenliste festlegen.**
   - `migration/inventory/pages.json`, falls vorhanden.
   - Sonst `$RUN/pages.json` anlegen: je Seitentyp eine Seite (Startseite, Kategorie, Produkt, Seite,
     Blogartikel, Suche), mit Search Console die meistbesuchte.
   - **Jede veröffentlichte Sprache** braucht ihre Seiten, sonst ist der SEO-Vergleich unvollständig
     und steht auf `blocked`. Ergänzen, Primärsprache zuerst:

     ```bash
     "${CLAUDE_PLUGIN_ROOT}/bin/theme" seo_parity pages --pages "$RUN/pages.json" --locales de,en
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
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" launch_check \
     --launch-date <YYYY-MM-DD> [--live-theme-id <id>] [--draft-theme-id <id>]
   ```

   - Das Modul findet die Mitschnitte unter `$RUN/capture/` selbst; andere Pfade über `--network-old` und
     `--network-new`.
   - Es schreibt `$RUN/launch-check.json` und `$RUN/launch-check.md` und gibt eine JSON-Zeile mit
     Empfehlung und Zahl je Status aus.

5. **Vorlegen.** Zuerst die Haken-Liste: `bin/theme launch check` mit denselben Argumenten statt
   `launch_check` (Abschnitt "Die Haken-Liste"), unverändert gezeigt. Dann `missing` und `blocked` mit
   Beleg, Link und Verantwortlichem aus `launch-check.md`. Jeden Punkt `missing` vorher selbst ansehen.
   - Was laut Entscheidungsliste entfällt (`drop` oder `replace` in `migration/inventory/apps.json` oder
     `migration/mapping/decisions.json`), steht als `ok` mit der Entscheidung als Beleg.
   - Erscheint eine gewollte Streichung trotzdem als `missing`, fehlt sie in der Liste: mit Person, Datum
     und Grund in `decisions.json` nachtragen (`kind: app`), nie im Bericht übergehen.
   - Eine eigene Subdomain eines Dienstes (CNAME oder A-Eintrag, etwa ein Attributions-Endpunkt) gehört
     über `hosts` in ihre Zeile von `apps.json`; sonst erscheint sie als eigener Host und der
     Ausweich-Endpunkt des Dienstes als neu.

6. **Folgeschritte empfehlen, nicht selbst starten:**
   - `live-sync` auf `missing`: `sync-live-theme` (Abgleich II)
   - offene Punkte der Liste: beheben und mit Beleg erledigen (`open_items done`) oder mit Person und
     Datum verschieben (`open_items defer`), dann `verify-theme` für die betroffenen Prüfer; ohne
     Liste im Bericht als erledigt markieren
   - Punkte, die eine bestandene Prüfung dieses Laufs abdeckt: `open_items close-covered
     --launch-check $RUN/launch-check.json`, dann neu prüfen
   - `acceptance-sources` auf `missing`: jede genannte Quelle mit `open_items import` übernehmen
   - Lücken in `seo-structured-data`, `seo-hreflang`, `seo-open-graph`: Horizon-Grundpaket prüfen
     (`build-theme`, `seo-parity.md`), hochladen, neu mitschneiden
   - alte Vergleichswerte: `pull-gsc`, `pull-ga4`, `pull-cwv` und `crawl-site` direkt vor dem Launch
   - `custom-pixel-backup` auf `missing`: den Code des Pixels im Admin (Einstellungen, Kundenereignisse)
     lesen und nach `migration/inventory/pixels/<name>.js` sichern, daneben `<name>.md` mit Pixel-ID,
     Sendet, Wo und An (`apps-and-tracking.md`, "Custom Pixels sichern"); erst dann entfernen
   - `app-injections` auf `missing` oder `manual`: Zeile oder Embed im Entwurf ansehen, entfernen oder
     ins Ziel-Repo übernehmen, dann neu hochladen
   - `tracking-pre-consent` auf `missing`: Auslöser der Anfrage im Browser suchen (Initiator), die App
     oder das Tag an die Einwilligung binden, neu mitschneiden
   - `web-pixels` auf `blocked`: Mitschnitt des Live-Themes mit HTML ziehen; ohne die Liste fällt nach
     dem Launch kein entferntes Pixel auf

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

Direkt nach dem Veröffentlichen (im geführten Launch nach "Jetzt kommt der Launch-Check After."), in
dieser Reihenfolge:

1. **Mitschnitt des veröffentlichten Themes** nach `$RUN/capture/after-declined` mit
   `--theme <new-live-theme-id>`, dieselbe Seitenliste.
2. **Mitschnitt mit Einwilligung**, wenn das Team ihn freigegeben hat (Frage `tracking-consent` vor dem
   Launch): `--consent accepted` nach `$RUN/capture/after-accepted`. Fehlt der Mitschnitt des alten
   Themes mit Einwilligung, lässt er sich jetzt noch ziehen: das alte Theme ist ein Entwurf und läuft als
   Vorschau (`--theme <old-live-theme-id> --consent accepted --out $RUN/capture/old-accepted`).
   - Bekannte Dialoge, gemessen am 10.11.2026: CookieFirst über den Knopf
     `[data-cookiefirst-action='accept']` und, wenn der Banner nicht sichtbar ist, über
     `CookieFirst.acceptAllCategories()`; Pandectes über `.cc-btn.cc-allow` ("Das ist O.K.").
   - Ein Durchlauf, in dem der Dialog nicht bedient wurde (`no_dialog`, `stuck` in `consent_result`),
     zählt nie als Durchlauf mit Einwilligung; der Punkt steht dann auf `blocked`.
3. **Testbestellung, nur nach ausdrücklicher Freigabe durch das Team.** Die Frage steht als
   `test-order` im Bericht. Nach dem Ja geht das Skript die Kasse bis zur Zahlung durch, in einem
   sichtbaren Fenster:

   ```bash
   uv run --quiet --with playwright==1.58.0 python "${CLAUDE_PLUGIN_ROOT}/scripts/browser/walk_checkout.py" \
     --pages "$RUN/pages.json" --out "$RUN/test-order" --approved-by "<Name aus dem Team>" \
     [--product-path /products/<handle>] [--contact <kontakt.json>]
   ```

   - Stufen: Produktseite, Cookie-Dialog (zustimmen, damit Kauf-Pixel in Consent-Regionen senden),
     In den Warenkorb über den Knopf des Themes, Warenkorb mit Steuer- und Versandhinweis, Kasse mit
     Steuer, Versand und Zahlung. Je Stufe ein Bild unter `$RUN/test-order/`.
   - Vor der Kasse setzt das Skript das Warenkorb-Attribut `_ptai_test_order` (daran findet der Prüflauf
     die Bestellung) und die Notiz "Testbestellung launch-check …, wird storniert" fürs Lager.
   - `--contact`: JSON des Teams mit Testadresse (`email`, `first_name`, `last_name`, `address1`,
     `postal_code`, `city`, `country_code`), nie im Repo. Damit erscheinen die Versandarten schon im
     Durchlauf; ohne trägt der Mensch die Adresse ein.
   - **Die Bestellung setzt ein Mensch ab.** Das Skript gibt nie Zahlungsdaten ein und klickt nie auf
     "Jetzt kaufen"; es wartet bis zu 20 Minuten auf die Dankeseite, dann 15 Sekunden auf die Kauf-Pixel.
     Ob mit echter Zahlung und späterer Erstattung oder mit einem Rabattcode über 100 Prozent, entscheidet
     das Team; den Shop am Launch-Tag in den Testmodus der Zahlung zu stellen, gehört nicht dazu.
   - `--headless` ist ein Probelauf bis zur Zahlung, ohne Bestellung.
4. **Prüflauf:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" launch check --after \
     [--network-old reporting/runs/<pre-launch-run>/capture/old-declined/network.json \
      --network-old reporting/runs/<pre-launch-run>/capture/old-accepted/network.json]
   ```

   - Nach dem geführten Launch stehen altes und neues Theme im Migrationslauf (`rollback_theme_id`,
     `live_theme_id`); der Prüflauf liest sie selbst. Sonst `--live-theme-id <alte ID>` (Rückfall-Theme)
     und `--draft-theme-id <neue ID>` übergeben.
   - Die Mitschnitte des alten Themes vom Tag vor dem Launch über `--network-old` übergeben, wenn sie
     nicht im Ordner von heute liegen, je Consent-Zustand einmal.
   - Den Durchlauf der Testbestellung findet der Prüflauf unter `$RUN/test-order/walk.json`, sonst den
     jüngsten der letzten sieben Tage; anders über `--test-order <walk.json>`.
5. **Storno und Erstattung** als Frage an das Team (`test-order-refund`), sobald alle Ziele geprüft sind.
   Der nächste Lauf liest den Stand aus der Bestellung selbst.
6. **Am Folgetag erneut**, wenn GA4 noch `blocked` steht: der GA4-Bericht braucht bis zu 48 Stunden. Der
   Lauf am Folgetag findet den Durchlauf vom Launch-Tag wieder.
7. Ergebnis `$RUN/launch-check-after.json` und `.md`. Geprüft:
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
   - App-Einträge seit dem Veröffentlichen (`app-injections-after`): neue Zeilen mit `render`, `include`
     oder `script` in `layout/theme.liquid` und neue oder wieder eingeschaltete App-Embeds gegen die
     Sicherung des Entwurfs, die `launch publish` direkt vor dem Veröffentlichen anlegt
     (`published-draft/`), ohne sie gegen das Ziel-Repo. Gestrichene App: `missing`; sonst eine Frage
   - fremde Hosts je Seite gegen den Stand vorher
   - Tracking nach Einwilligung je Seitentyp gegen den Mitschnitt vorher (`tracking-consent-after`), dazu
     ob die Einwilligung `Shopify.customerPrivacy` (analytics, marketing) und den Consent Mode erreicht
   - Werbe- und Analyseaufrufe vor der Einwilligung, neu gegen vorher (`tracking-pre-consent-after`), je
     Dienst über `hosts.json`: Microsoft Advertising zählt an `bat.bing.com` und an `bat.bing.net`
   - die Pixel-Liste des Shops (`webPixelsConfigList`) gegen die von vor dem Launch (`web-pixels-after`):
     aus `web-pixels-before.json` des Laufs davor, sonst aus einem Mitschnitt des alten Themes von vor dem
     Launch oder dem HTML der Bestandsaufnahme. Ein fehlendes Pixel ist `missing`, außer es ist bewusst
     entfernt und, als Custom Pixel, gesichert; ein Pixel mit einem Messziel weniger ist eine Frage
   - Pagination und Analyse-Ereignisse je Seitentyp gegen den Mitschnitt vorher
   - die Testbestellung: Freigabe, Kasse bis zur Zahlung, je Ziel ob der Kauf ankommt, Storno und
     Erstattung (Abschnitt unten)
   - jede veröffentlichte Sprache einmal
   - die Sitemap
   - als Fragen: Einreichen der Sitemap, Festhalten des Stands

- Ab dem Umschalten gilt der Prüfplan in `post-launch.md`.

### Testbestellung: je Ziel ein Status

Die Ziele kommen aus `theme_migration.purchase_destinations` der Config, sonst aus der Bestandsaufnahme
(`migration/inventory/apps.json`) und dem Mitschnitt des alten Themes. Was laut Entscheidungsliste
entfällt, wird nicht geprüft und steht im Beleg von `test-order`. Ein Ziel, das der Shop auf dem Server
beliefert (Littledata, Elevar, Conversions-API), ist im Browser unsichtbar und steht mit `via` in der
Config; Littledata und Elevar erkennt der Prüflauf für GA4 selbst:

```json
"purchase_destinations": {"google_analytics": {"via": "Littledata"}, "google_ads": {}, "meta": {}}
```

**Jede GA4-Property und jede Google-Ads-Kauf-Conversion ist ein eigener Punkt** (seit 11.11.2026):
`purchase-ga4-<g-id>` und `purchase-google-ads-<id>-<label>`, neben `purchase-google-analytics` und
`purchase-google-ads`. Gesammelt wird, was der Shop vor dem Launch bediente: `tracking.json` der
Bestandsaufnahme, die Anfragen im Mitschnitt des alten Themes, die Pixel-Konfiguration aus
`web-pixels-before.json` (für Google Ads nur Ziele des Ereignisses `purchase`) und jedes gesicherte Custom
Pixel unter `migration/inventory/pixels/`. Erfüllt ist ein Punkt nur mit einem Kauf-Aufruf an genau diese
Kennung; läuft der Kauf über den Server, ist er eine Frage nach dem Echtzeitbericht der Property. Eine
Property, die bewusst entfällt, steht mit der Kennung als Gegenstand in `decisions.json`. Festlegen lässt
sich die Liste mit `"google_analytics": {"ids": ["G-…"]}`.

Lesewege, recherchiert am 10.11.2026 (Modul `theme.test_order`):

| Punkt | Leseweg | `ok` nur, wenn |
|---|---|---|
| `checkout-walk` | Bilder und Text aus dem Durchlauf | Warenkorb und Kasse geladen, Steuer- und Versandhinweis gefunden, Versandarten und Zahlung gesehen oder durch die Bestellung belegt |
| `purchase-shopify` | Admin `orders`, Scope `read_orders`, über das Warenkorb-Attribut | die Bestellung mit der Kennung existiert |
| `purchase-google-analytics` | Data API `runReport` mit `transactionId` (Bestellname, Nummer, ID); Echtzeit nur als Hinweis, sie kennt keine `transactionId` | genau ein Kauf zur Bestellung im Bericht; ohne Lesezugang genügt ein `purchase`-Aufruf von der Dankeseite, außer der Kauf läuft über den Server |
| `purchase-ga4-<g-id>` | Aufruf von der Dankeseite; serverseitig eine Frage nach dem Echtzeitbericht | ein `purchase` an genau diese Property |
| `purchase-google-ads` | keiner: das Konto zählt nur Conversions nach einem Anzeigenklick | ein Conversion-Aufruf mit Label von der Dankeseite |
| `purchase-google-ads-<id>-<label>` | keiner | ein Conversion-Aufruf mit genau dieser Kennung und diesem Label |
| `purchase-meta` | keiner: Testereignisse gibt es nur in der Oberfläche | ein Aufruf `ev=Purchase` von der Dankeseite |
| `purchase-microsoft-ads`, `purchase-pinterest`, `purchase-tiktok` | keiner | der Kauf-Aufruf des Pixels von der Dankeseite |
| `test-order-refund` | Admin `orders` | storniert und erstattet (oder Betrag 0) |

- GA4 mehrfach im Bericht, oder ohne Lesezugang mehrfach im Browser gesendet: `missing`, ein doppelter
  Absender. Bei Werbe-Pixeln steht ein mehrfacher Aufruf als Hinweis im Beleg.
- GA4 noch nicht im Bericht: `blocked` bis 48 Stunden nach der Bestellung, danach `missing`.
- Kein Aufruf eines Pixels trotz erteilter Einwilligung: `missing`; ohne erteilte Einwilligung `blocked`.
- Ein Ziel über den Server ohne Leseweg: eine Frage an Betreiber und Team, mit dem Werkzeug, in dem der
  Kauf zu sehen ist.
- GA4 lesen braucht `ga4_property_id` in `reporting/config.json` und `PTAI_GOOGLE_CREDENTIALS`
  (Workspace-`.env` oder zentral); fehlt beides, steht der Grund im Beleg.
- Lehnt das Team die Testbestellung ab: in `launch-answers.json` `"test-order": {"status": "n/a", "by":
  "<Name>"}`; dann stehen alle Punkte der Testbestellung auf `n/a`.

## Was geprüft wird

| Gruppe | Punkt | Wie |
|---|---|---|
| Zeitpunkt | Wochentag, Feiertag, Saisonspitze | aus dem Termin: Montag bis Donnerstag, kein bundesweiter Feiertag am Tag und am Folgetag, nicht ab vier Wochen vor Black Friday bis Jahresende |
| Zeitpunkt | Kampagnen, Preis- und A/B-Tests, Ansprechpartner | Fragen; ein Testwerkzeug im Mitschnitt steht als Hinweis daneben |
| Abnahme | Liste offener Punkte (mit Liste oder Migrationslauf) | `migration/open-items.json`: kein Punkt mit Gate `G4-acceptance` oder `G5-go-live` offen; jede Quelle (Prüfliste, `report_paths`, jüngster Bericht unter `migration/verify/`, jüngste Abnahme) ohne Offenes, das in der Liste fehlt |
| Abnahme | G4, Befunde, Testpunkte der Abnahme (ohne Liste und ohne Migrationslauf) | Gate im Migrationslauf; jüngstes `migration/verify/*/findings.json` und jeder Bericht unter `theme_migration.report_paths` (offen: `blocker`, `before_launch`, Abschnitte "Vor dem Launch" und "Blocker" ohne Erledigt- oder Verschoben-Vermerk; kein Bericht: `blocked`); `reporting/runs/*-test/test.json` (offen: `open`, `in_progress`, `decision`) |
| Abnahme | Prüfliste aus Phase 2 (ohne Liste und ohne Migrationslauf) | `theme_migration.acceptance_checklist`: jede Zeile `- [ ] **Pnn**` abgehakt, verschoben mit Person und Datum oder durch eine bestandene SEO-Prüfung abgedeckt (`seo-parity.md`) |
| Abgleich | Live-Theme seit dem letzten Abgleich | `updatedAt` frisch gegen jüngstes `delta.json` oder `manifest.json` unter `migration/` |
| Abgleich | Abgleich vor dem Launch | `last_sync` im Lauf, höchstens sieben Tage alt; kein Änderungsstopp seit 0.3.11 |
| Entwurf | Entwurf, Rückfall-Theme | Rolle `UNPUBLISHED`, nicht in Verarbeitung; Live-Theme `MAIN`, ID notiert |
| Apps | App-Embeds | aktive Embeds aus `config/settings_data.json` beider Themes; gestrichen laut `apps.json` oder `decisions.json` ist `ok` mit Beleg |
| Apps | App-Einträge gegen den hochgeladenen Stand | Entwurf gegen Ziel-Repo (`theme_migration.target_repo`): neue Zeilen mit `render`, `include` oder `script` in `layout/theme.liquid`, neue oder wieder eingeschaltete App-Embeds; gehört der Eintrag zu einer App mit `drop` oder `replace`, `missing`, sonst eine Frage; ohne Ziel-Repo und ohne Migrationslauf `n/a` |
| Übersetzungen | Theme-Übersetzungen | je veröffentlichter Sprache: übersetzt, veraltet, Anteil neu gegen alt |
| Tracking | Hosts je Seite | Mitschnitt alt gegen neu, je Consent-Zustand; Shopify selbst und die Shop-Domain zählen nicht, ihre Subdomains schon (zugeordnet über `hosts` in `apps.json`); gestrichen laut Entscheidungsliste ist `ok` mit Beleg |
| Tracking | Mitschnitt mit Einwilligung | beide Themes mit `--consent accepted`, und in jedem Durchlauf hat der Dialog zugestimmt (`consent_result`); ein Ordner `*-accepted` allein genügt nicht |
| Tracking | Werbung und Analyse vor Einwilligung | Durchläufe ohne Einwilligung und Anfragen vor dem Klick (`consent_phase: pre`), je Dienst über `hosts.json` (Microsoft Advertising an `bat.bing.com` und `bat.bing.net`); ein Dienst, der neu vor der Einwilligung sendet, ist `missing`, einer, der nur neu lädt, ein Hinweis |
| Tracking | Pixel-Liste festgehalten | `webPixelsConfigList` aus dem HTML des Mitschnitts des Live-Themes, sonst aus einem Abruf der Startseite, nach `$RUN/web-pixels-before.json`; nicht lesbar `blocked` |
| Tracking | Custom Pixels gesichert | jedes Custom Pixel mit `drop` oder `replace` liegt unter `migration/inventory/pixels/` als `<name>.js` mit einer Notiz `<name>.md` (Pixel-ID, Sendet, Wo, An); sonst `missing` |
| Tracking | Pagination und Analyse-Ereignisse | je Seitentyp und Gerät: `page=N` in `final_url` (Nachladen beim Scrollen schreibt die Seite in die Adresse) und Anfragen je Analysedienst, Minimum neu gegen Maximum alt; ab 1,5-fach und 3 mehr ein Fehler, geändertes Nachladen allein eine Frage |
| Nach dem Launch | Tracking nach Einwilligung | je Seitentyp Dienste mit erteilter Einwilligung, neu gegen vorher; `Shopify.customerPrivacy` und Consent Mode nach der Zustimmung erteilt |
| Nach dem Launch | Testbestellung je Ziel | Durchlauf `walk_checkout.py`, Bestellung über Admin `orders`, GA4 über `transactionId`, Werbe-Pixel über den Aufruf von der Dankeseite, dazu jede GA4-Property und Google-Ads-Kauf-Conversion von vorher einzeln (Tabelle oben) |
| Nach dem Launch | App-Einträge seit dem Veröffentlichen | Live-Theme gegen `published-draft/` aus `launch publish`, sonst gegen das Ziel-Repo; Regeln wie vor dem Launch |
| Nach dem Launch | Pixel-Liste vorher gegen nachher | Liste des Live-Shops gegen `web-pixels-before.json`; fehlt ein Pixel ohne Entscheidung oder ein entferntes Custom Pixel ohne Sicherung, `missing` |
| SEO | robots.txt | `templates/robots.txt.liquid` in beiden Themes, Live-Ausgabe gesichert |
| SEO | Statuscodes, noindex, Canonicals | aus dem Mitschnitt des Entwurfs gegen den des Live-Themes |
| SEO | strukturierte Daten, hreflang, Open Graph, Title, Description, Canonical | `theme.seo_parity` je Seite des Mitschnitts: was live da ist und im Entwurf fehlt, ist `missing`; eine `ProductGroup` mit Varianten ohne `description` immer; fehlt ein Seitentyp (Startseite, Kategorie, Produkt) oder eine veröffentlichte Sprache im Mitschnitt, `blocked` |
| Vergleichswerte | GSC, GA4, CWV, Crawl | jüngste Datei unter `reporting/data/` vom Termin oder Vortag |
| Go/No-Go | Kriterien, Rückfallgrenzen, Kommunikation | Fragen |
| Go/No-Go | G5 entschieden (nur mit Migrationslauf) | Gate `G5-go-live` im Migrationslauf: mit Name `ok`, sonst `manual` mit der Frage an die Person der Marke |
| Plattform-Fristen | Kundenkonten, Skript-Tags | `customerAccountsV2` und `templates/customers/` im Entwurf; `asyncLoad` im HTML des Live-Themes |

## Was die Skill nicht automatisch prüfen kann

- Kampagnen, laufende Tests, Ansprechpartner, regionale Feiertage und andere Länder als Deutschland.
- Ob Go/No-Go- und Rückfallkriterien schriftlich vorliegen und das Team die Liste aus `rollback.md`
  gesehen hat; ob die Kommunikation verschickt ist.
- Checkout, Dankeseite und Kauf-Events ohne Testbestellung; die Bestellung selbst setzt immer ein Mensch
  ab, Storno und Erstattung macht das Team.
- Ob Google Ads, Meta und die übrigen Werbekonten einen Kauf verbuchen: es gibt keinen Leseweg, geprüft
  ist der Aufruf von der Dankeseite. Ein Absender auf dem Server ohne Leseweg bleibt eine Frage.
- Server-Side-Tagging über eine eigene Domain (eigener GTM-Server): solche Aufrufe erkennt der Prüflauf
  nicht als Kauf eines Ziels; das Ziel dann mit `via` eintragen.
- Tracking mit Einwilligung, solange das Team den Mitschnitt nicht freigegeben hat, und mit einem
  Cookie-Dialog, den `consent.py` nicht kennt.
- App-Blöcke in Templates (nur Embeds), Inhalte von Bewertungen oder Suche: das zeigt die Abnahme.
- Die volle Schutzliste der Top-Seiten aus der Search Console: geprüft wird die Seitenliste; die
  Schutzliste deckt `crawl-site` gegen den Entwurf ab.
- Markt-Pfade, die nicht dem Muster `/<sprache>` folgen, und ob Rollouts im Admin verfügbar sind.

## Ergebnis

`reporting/runs/<date>-launch-check/` mit:

- `launch-check.json`, je Punkt `id`, `group`, `title`, `status`, `evidence`, `action`, `owner`,
  `question`, `links`
- `launch-check.md` mit der Empfehlung oben und den Punkten je Status (`missing` und `blocked` zuerst)
- `pages.json`, `capture/`, `robots-live.txt` und `web-pixels-before.json` (Pixel-Liste vor dem Launch)
- nach dem geführten Launch `launch.json` und `published-draft/` (Layout und Einstellungen des Entwurfs,
  gesichert direkt vor dem Veröffentlichen)
- mit `--after` dieselben Dateien als `launch-check-after.*`, dazu `test-order/walk.json` und je Stufe
  der Kasse ein Bild `test-order/NN-<stufe>.png`

Es entstehen keine Bilder.

## Fehlerbilder

- **Alles `blocked`:** kein Shopify-Zugang. `shopify store auth` über die Shopify-Skills erneuern, dann
  erneut ausführen.
- **Tracking `blocked` mit falschem Theme:** der Mitschnitt zeigte nicht das erwartete Theme
  (Vorschau-Cookie, Weiterleitung). Neu mitschneiden, den Befund nie übergehen.
- **Hunderte fehlende Hosts:** Mitschnitte mit und ohne Einwilligung vermischt oder verschiedene
  Seitenlisten. Beide Themes mit derselben `pages.json` und demselben Consent-Zustand mitschneiden.
- **`acceptance-open-items` bleibt `missing`, obwohl im Bericht alles abgehakt ist:** die Liste ist
  die Quelle, nicht der Bericht. Jeden Punkt dort mit Beleg erledigen oder verschieben.
- **`acceptance-open-items` `blocked` in einem Migrationslauf:** die Liste fehlt. `open_items init`,
  dann jede Quelle importieren; eine von Hand geführte Liste im Format von `findings.json` mit
  `open_items import --kind findings` übernehmen.
- **Befunde `blocked`, obwohl es einen Prüfbericht gibt:** er liegt außerhalb des Workspace.
  `theme_migration.report_paths` auf seinen Ordner setzen; ist der Ordner nicht eingebunden (Drive
  offline), steht er unter "nicht gefunden".
- **SEO-Zeilen `blocked` mit "Sprache nicht im Mitschnitt":** die Seitenliste hat keine Seite der
  Sprache. `theme.seo_parity pages` ergänzen, beide Themes neu mitschneiden.
- **`seo-hreflang` meldet doppelte Werte:** Shopifys automatische Tags und das Snippet
  `<prefix>-hreflang` laufen zugleich. Eines davon abschalten (`seo-parity.md`, Horizon-Grundpaket).
- **Rückfall-Theme `blocked` nach dem Launch:** die Live-Theme-ID zeigt schon auf das neue Theme, und
  `rollback_theme_id` fehlt im Stand (von Hand veröffentlicht). `--live-theme-id` mit der alten ID, dann
  `run_state set --key rollback_theme_id --value <alte ID>`.
- **`tracking-consent` oder `tracking-consent-after` `blocked` mit `no_dialog`:** der Cookie-Dialog wurde
  nicht erkannt. Im Browser ansehen, Knopf in `skills/capture-screens/scripts/consent.py` ergänzen
  (`ACCEPT_SELECTORS`, für ein Tool mit JavaScript-API `ACCEPT_APIS`), neu mitschneiden.
- **`tracking-consent-after` `missing` mit "Shopify customerPrivacy marketing=''":** der Banner merkt sich
  die Einwilligung, gibt sie aber nicht an Shopify weiter; App- und Kassen-Pixel senden dann nicht.
  Anbindung des Consent-Tools an die Customer Privacy API prüfen.
- **`purchase-shopify` `missing`, obwohl die Dankeseite erreicht war:** die Bestellung trägt das
  Warenkorb-Attribut nicht (anderes Fenster, Express-Kasse). Im Admin von Hand suchen. Die Werbe-Pixel
  bewertet der Prüflauf trotzdem aus dem Mitschnitt der Dankeseite, GA4 über die Bestellnummer im
  `purchase`-Aufruf.
- **`purchase-google-analytics` bleibt `blocked`:** kein Lesezugang zu GA4 (Grund im Beleg) oder der
  Bericht ist noch nicht fertig. Zugang eintragen oder am Folgetag erneut prüfen.
- **`app-injections-after` `missing`:** eine gestrichene App hat sich beim Veröffentlichen wieder
  eingetragen. Die Zeile in `layout/theme.liquid` von Hand entfernen und das Embed ausschalten; die App
  abschalten oder deinstallieren, sonst trägt sie sich beim nächsten Veröffentlichen wieder ein.
  Abschalten in der App allein entfernt die Zeile nicht.
- **`web-pixels-after` `blocked`:** keine Pixel-Liste von vor dem Launch. Den Mitschnitt des alten Themes
  vom Tag davor über `--network-old` übergeben. Ein Mitschnitt des alten Themes nach dem Launch hilft
  nicht: die Liste gilt für den ganzen Shop und zeigt dort schon den Stand danach.
- **`purchase-ga4-<g-id>` `missing`, obwohl `purchase-google-analytics` erfüllt ist:** eine Property
  bekommt den Kauf, eine andere nicht. Meist sendete an sie ein Pixel nur in der Kasse; die Sicherung
  unter `migration/inventory/pixels/` zeigt, welches. Wiederherstellen, dann erneut testen.
- **Jemand bittet um Veröffentlichen:** diese Skill veröffentlicht nicht. In einer Migration führt
  `theme-migration` den Launch (Phase 9): Haken-Liste grün, Frage, Ja mit Namen, `launch publish`. Ohne
  Migrationslauf nennt sie den Weg im Admin (`launch-checklist.md`, Veröffentlichen).
- **`go-decision` bleibt `manual`:** G5 ist im Migrationslauf nicht eingetragen. Die Person der Marke
  entscheidet nach Abstimmung mit Path to AI, `run_state gate --gate G5-go-live`, dann neu prüfen.
