# Nachsorge

Stand 05.10.2026, Fixes nach dem Launch seit 11.11.2026. Gilt für Phase 10 und für Korrekturen direkt
nach dem Veröffentlichen (Phase 9). Nach dem Launch fällt ein Fehler in Rankings und Conversion erst mit
Verzögerung auf. Der Prüfplan legt fest, wann was gemessen wird, der Fix-Ablauf, wie Korrekturen sicher
live gehen, und die Rückrichtung hält das Repo mit dem live laufenden Theme gleich.

## Prüfplan

Verglichen wird mit den Werten, die direkt vor dem Launch gezogen wurden (`launch-checklist.md`).

| Termin | Was | Womit |
|---|---|---|
| Tag 1 (Launch-Tag und der Tag danach) | Spot-Checks wie am Launch-Tag, Crawl des Live-Shops gegen den Crawl des Entwurfs, Umsatz, Conversion, Fehlerseiten und Kaufabbrüche eng beobachten, erste Testbestellung ausgewertet | `crawl-site`, `pull-ga4`, Shopify-Analysen |
| Woche 1 | täglich: Crawl-Fehler und 404 aus der Search Console, wichtige 404 umleiten, Soft-404 beheben; Rankings täglich | `pull-gsc`, Rank-Tracking |
| Woche 2 | Rankings weiter täglich; Conversion je Seitentyp und Gerät gegen die Vergleichswerte; Tracking am Datensatz gegen die Bestellungen | `pull-ga4`, `pull-gsc` |
| Woche 4 | wöchentlicher Review: Crawl-Statistik (ein Anstieg ist nach einem Launch normal), Seitenindexierung, Rich Results, Conversion je Seitentyp und Gerät; erster Report gegen die Werte vor dem Launch | `pull-gsc`, `pull-ga4`, `report` |
| Tag 28 | Core Web Vitals im Feld bewerten: CrUX und PageSpeed rollieren über 28 Tage, erst jetzt zeigt das Feld nur das neue Theme | `pull-cwv` |
| Woche 6 bis 12 | Erfolg der Migration bewerten: Sichtbarkeit Desktop und Mobil, Sitzungen und Conversion je Seitentyp und Gerät, eingereichte gegen indexierte URLs. Kleine Shops eher Woche 6, große eher Woche 12. Ein vorübergehender Rückgang durch Gewöhnung wiederkehrender Besucher ist möglich | `report`, `pull-gsc`, `pull-ga4` |

Danach: KPIs nach drei und sechs Monaten gegen die ursprünglichen Ziele. Redirects mindestens ein
Jahr stehen lassen.

Bei einer Bewegung zuerst prüfen, ob ein Google-Update, Saison oder eine Kampagne sie erklärt, bevor
sie der Migration zugeschrieben wird. Als grobe Erfahrung aus Agenturquellen, keine Norm: Fehler an
Redirects, `noindex` und `robots.txt` erholen sich in ein bis zwei Wochen, Inhalte und interne Links
in zwei bis sechs, Core Web Vitals ab vier.

## Aufräumen

- Geplante Änderungen an Shop-Daten, die während des Stopps vorbereitet wurden, jetzt in datierten
  Blöcken umsetzen, mit Sicherung vor jedem Block (`change-freeze.md`).
- Code alter Apps im alten Theme ist mit dem Wechsel aus dem Live-Shop verschwunden. Apps, die im
  neuen Theme nicht mehr gebraucht werden, mit Freigabe des Teams deinstallieren; nicht mehr
  gebrauchte Pixel trennen.
- Das alte Theme erst nach der Stabilisierung löschen, mit Freigabe des Teams. Löschen ist endgültig.
- Befunde der Schwere `after_launch` nach ihrem Termin abarbeiten.

## Fixes nach dem Launch

Stand 11.11.2026. Gilt ab dem Veröffentlichen (Phase 9, Schritt 5) und in Phase 10. Entstanden aus einem
Launch, nach dem in der ersten Stunde ein gutes Dutzend sichtbarer Fehler gemeldet wurde: fünf Chargen in
45 Minuten live, ohne eine Datei des Teams zu überschreiben. Der Ablauf ist seitdem Standard.

**Grundregeln**

- Am Live-Theme wird nie direkt gearbeitet. Die Module des Plugins schreiben nie in `MAIN` (`theme.guard`),
  auch nicht nach dem Launch.
- Erst die Ursache belegen, dann ändern: Bildpaar alt gegen live, berechnete Werte im Browser, bei Tracking
  der Auslöser-Stack und die Pixel-Liste vorher gegen nachher. Keine Korrektur auf Vermutung.
- Vorlage für Aussehen ist das Rückfall-Theme (`rollback_theme_id`), immer mit seiner ID im Link
  (`?preview_theme_id=<id>`), nie ein älteres Theme oder ein Repo-Stand.

**Ablauf**

1. **Duplikat:** Das Live-Theme in der Theme-Bibliothek duplizieren (Admin oder `shopify theme duplicate`,
   Flags über `shopify-plugin:shopify-use-shopify-cli` prüfen) und im selben Moment das Live-Theme sichern:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" snapshot --theme live --out migration/snapshots
   ```

   Diese Sicherung ist die Referenz für die Drift-Prüfung. Das Duplikat wird für diese Arbeit der Entwurf
   (`run_state set --key draft_theme_id --value <duplikat>`), damit `upload-theme` nur dorthin schreibt.
   Vorschau im Browser immer mit frischem Kontext: Shopify hält die Vorschau per Cookie.
2. **Bereiche trennen:** Die Meldungen nach Dateien in Bereiche teilen, die keine Datei gemeinsam haben,
   etwa Inhaltsseiten (Templates), Kollektion, Produkt, Warenkorb und Suche (eigene Templates und Sections),
   Gestaltung (gemeinsame Dateien). Gemeinsame Dateien (`config/settings_data.json`, `layout/theme.liquid`,
   die eigene CSS-Datei des Shops, `locales/*`) ändert genau ein Bereich. Die anderen legen zusätzliches CSS
   als `custom_css` der jeweiligen Section im Template-JSON ab. Bereiche können parallel laufen, je mit
   eigenem Branch im Theme-Repo.
3. **Im Duplikat beheben:** Je Bereich nur die eigenen Dateien ins Duplikat schreiben (`upload-theme`, oder
   `shopify theme push --theme <duplikat> --only <datei> --nodelete`). Je Befund ein Bildpaar alt gegen
   Duplikat in 1440 und 390 px (`compare-themes`), Ursache in der Klasse des Incident-Reports (Generator,
   Mapping, Abnahme, Abgleich, Launch-Ablauf). Commit im Bereichs-Branch, dann Merge.
4. **Go je Charge:** Eine Charge ist eine feste Liste von Dateien aus geprüften Bereichen. Live geht sie nur
   nach dem ausdrücklichen Go der Person, die den Launch verantwortet, mit ihrem Namen im Journal
   (`run_state log --kind answer`).
5. **Drift-Prüfung direkt vor dem Live-Gang:** Hat seit der Referenz jemand im Live-Theme an einer Datei der
   Charge gearbeitet?

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" sync \
     --last migration/snapshots/<referenz>/manifest.json --out "migration/sync/<date>-charge-<n>"
   ```

   Steht eine Datei der Charge in `delta.json` unter `changed`, `added` oder `removed`, wird die Änderung des
   Teams zuerst in den eigenen Stand übernommen und neu geprüft. Sonst würde der Live-Gang sie überschreiben.
6. **Live-Gang:** nur die Dateien der Charge, nie das ganze Theme, nie `theme publish`:
   `shopify theme push --theme <live-id> --path <repo> --only <datei> [--only <datei> …] --nodelete`.
7. **Zurücklesen und ansehen:** `"${CLAUDE_PLUGIN_ROOT}/bin/theme" upload verify --theme <live-id> --dir
   <repo>`; jede Datei der Charge muss gleich sein. Dann die betroffenen Seiten live in 1440 und 390 px
   ansehen. Die Sicherung aus `sync` (Schritt 5, plus diese Charge) ist die Referenz der nächsten Charge.
8. **Festhalten:** je Charge Dateien, Ergebnis der Drift-Prüfung, Zurücklesen, Commit; je Befund ein Punkt in
   der Liste offener Punkte (`open_items add --severity after_launch`), erledigt mit Bildbeleg.
9. **Ursache zurückgeben:** Was der Generator oder das Mapping verursacht hat, geht als Regel ins Plugin
   (`mapping-format.md`, `theme.layout`) oder in die Overrides des Shops; ein Fehler im Ablauf in die Skill.
   Sonst bekommt der nächste Shop denselben Fehler.

## Rückrichtung: Editor-Änderungen zurück ins Repo

Nach dem Launch arbeitet das Team im Theme-Editor des neuen, live laufenden Themes. Diese Änderungen
stehen im Shop, nicht im Ziel-Repo. Ein erneuter Generatorlauf oder ein Upstream-Merge würde sie
überschreiben.

**Vor jedem Generatorlauf und vor jedem Upstream-Merge:**

1. Das live laufende Ziel-Theme sichern:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" snapshot --theme live --out migration/snapshots
   ```

2. Die neue Sicherung gegen das Ziel-Repo diffen, JSON normalisiert. Unterschiede in
   `templates/*.json`, `sections/*-group.json` und `config/settings_data.json` sind Arbeit des Teams.
3. Jede Änderung übernehmen: als Commit im Ziel-Repo und, wo der Generator die Datei erzeugt, als
   Änderung an Mapping oder Overrides, damit der nächste Lauf sie nicht zurückdreht.
4. Änderungen am Code des Themes über den Admin (Code-Editor, Apps) gesondert ansehen: sie gehören
   entweder als verzeichneter Eingriff in `migration/customizations.md` oder wieder heraus.
5. Erst danach generieren oder mergen. Erzeugt wird in ein Testverzeichnis und gegen den Repo-Stand
   gedifft, bevor etwas ersetzt wird.

Ist das Ziel-Theme mit GitHub verbunden, committet Shopify jede Admin-Änderung auf den verbundenen
Branch. Dann ist `git pull` dieses Branches der erste Schritt, und die Sicherung wird zur Gegenprobe.

## Updates des Ziel-Themes

- Aktualisiert wird im Ziel-Repo per `git merge upstream/<ref>`, nie über den Update-Hinweis im Admin;
  der übernimmt kollidierende Code-Änderungen nicht.
- Vorher die Rückrichtung oben, dann die Prüfung der Eingriffe mit `--against upstream/<ref>`
  (`customizations.md`), dann Neubau, Upload in ein unveröffentlichtes Theme, Prüfung, Veröffentlichen
  über den geführten Launch (`launch-checklist.md`) oder durch einen Menschen im Admin.

## Quellen

- https://moz.com/blog/website-migration-guide (Fachquelle)
- https://searchengineland.com/guide/site-redesign-seo-checklist (Fachquelle)
- https://developers.google.com/speed/docs/insights/v5/about
- https://support.google.com/webmasters/answer/9205520
- https://shopify.dev/docs/storefronts/themes/tools/github
- https://skalum.agency/en/seo-traffic-drop-after-redesign/ (Agenturquelle)
