# Launch

Stand 11.11.2026. Gilt für Phase 9. Der Launch ist der Schritt, in dem das neue Theme veröffentlicht
wird. Seit 10.11.2026 als geführter Launch in vier Schritten (`theme-migration`, Phase 9, Modul
`scripts/theme/launch.py`):

1. **Prüfen:** `launch check` zeigt jeden Go-Punkt als Haken-Liste (✅ erledigt, ❌ fehlt, ⏸ blockiert mit
   Grund, ✋ manuell zu bestätigen) mit einer Zeile Beleg und der Summe am Ende.
2. **Fragen:** nur wenn alles grün ist, "Jetzt Launch durchführen?" mit neuem und altem Theme und dem
   Rückfall-Theme. Fehlt etwas, keine Frage, sondern was fehlt und wer es erledigt.
3. **Veröffentlichen nach dem Ja** der Person der Marke: Schlussprüfung, `shopify theme publish`,
   Zurücklesen der Rolle `MAIN`, Stand mit ihrem Namen.
4. **Prüfen danach:** "Jetzt kommt der Launch-Check After.", dieselbe Haken-Liste, am Ende der Stand.

Bis 10.11.2026 galt: Die Skills veröffentlichen nie, den Klick macht ein Mensch im Admin. Die
Migrationen davor liefen chaotisch, und der Ablauf stand verteilt auf Phase 9 von `theme-migration`,
`launch-check` und diese Liste.

Die Prüfpunkte führt die Skill `launch-check` aus (seit 06.10.2026): je Punkt ein Status mit Beleg,
eine Go/No-Go-Empfehlung, mit `--after` die Prüfungen am Launch-Tag. Sie läuft mit und ohne
Migrationslauf, auch für einen Launch ohne Theme-Wechsel. Eine Änderung an dieser Liste zieht dort
eine Änderung nach sich (`scripts/theme/launch_check.py`).

## Zeitpunkt

| Regel | Warum |
|---|---|
| nicht freitags, nicht vor Wochenende oder Feiertag | bei einem Fehler fehlen sonst die Leute zur Behebung |
| Montag bis Donnerstag, in einer Zeit mit wenig Traffic | Fehler treffen weniger Besucher |
| nicht in der Saisonspitze und nicht in den Wochen davor (Black Friday, Weihnachtsgeschäft) | weder Zeit noch Ruhe für einen Fehler; Sichtbarkeit fällt in Tagen, die Erholung dauert Monate |
| nicht während großer Kampagnen | Umsatz und Messung |
| nicht während laufender Preis- oder A/B-Tests | zu viele gleichzeitige Änderungen machen die Fehlersuche unmöglich, und der Test wird wertlos |
| Ansprechpartner auf beiden Seiten anwesend | Entscheidungen im Ernstfall |

## Vorbereitung, Tage vorher

1. **Abnahme (G4) entschieden** und in der Liste offener Punkte (`migration/open-items.json`) kein
   Punkt für G4 oder G5 offen: jeder erledigt mit Beleg oder namentlich mit Datum verschoben. Ein
   offener Punkt ist ein No-Go, keine Frage.
   Dazu seit 11.11.2026: ein vollständiger Bildvergleich vor G4, jede Beispielseite am Rechner (1440) und
   am Handy (390) als ganze Seite, links das veröffentlichte Theme (Theme-Nachweis mit Rolle `main`),
   rechts der Entwurf, jedes Paar angesehen (`visual_compare check` ohne Befund), und kein Testpunkt der
   Abnahme ohne Bilder vom Entwurf erledigt. Beides prüft `run_state gate` selbst.
2. **Jede Quelle in der Liste:** Prüfberichte, auch außerhalb des Workspace
   (`theme_migration.report_paths`), die Prüfliste aus Phase 2 (`theme_migration.acceptance_checklist`)
   und die Abnahme halten nichts Offenes, das in der Liste fehlt (`open_items sources`). Am
   07.10.2026 ging ein Shop live, dessen Prüfliste nie abgehakt war und dessen Prüfbericht offene
   Punkte führte, die kein Schritt las.
3. **SEO-Ausgabe wie live** (`seo-parity.md`): strukturierte Daten, hreflang, Open Graph, Title,
   Description und Canonical je Seitentyp und je Sprache, im Mitschnitt verglichen. Die bekannten
   Lücken von Horizon schließt das Grundpaket beim Bau.
4. **Abgleich vor dem Launch** höchstens sieben Tage alt, direkt vor dem Termin neu; kein Änderungsstopp
   (`change-freeze.md`). Termin steht beim Team.
5. **Abgleich II** (`sync-live-theme`): jede Änderung seit Abgleich I entschieden und im Entwurf.
6. **Vergleichswerte direkt vorher ziehen:** `pull-gsc`, `pull-ga4`, `pull-cwv`, Crawl des
   Live-Themes, Rankings, Conversion je Seitentyp und Gerät. Verglichen wird nach dem Launch mit
   diesen Werten, nicht mit einer Baseline von vor Wochen: Saison und Wachstum dazwischen würden
   jeden Vergleich verfälschen.
7. **App-Embeds im Entwurf aktiviert** und App-Blöcke platziert. Embeds gelten je Theme; was im
   Entwurf eingeschaltet ist, ist nach dem Veröffentlichen eingeschaltet.
8. **Theme-Übersetzungen** auf dem Entwurf registriert und nicht `outdated`.
9. **Tracking und Pagination je Seitentyp wie im alten Theme**, im Mitschnitt bis zum Seitenende:
   dieselben Dienste (bewusst gestrichene stehen mit Grund in der Entscheidungsliste) und nicht mehr
   Analyse-Ereignisse je Seite. Lädt eine Liste beim Scrollen nach und schreibt dabei `page=N` in die
   Adresse, kann jede nachgeladene Seite als eigener Seitenaufruf oder eigene Suche zählen. Am
   07.10.2026 übersehen: auf einer Suchseite vervielfachte das die Suchereignisse in Analyse und
   Attribution.
10. **Kein neuer Werbe- oder Analyseaufruf vor der Einwilligung** im Entwurf gegen live, gezählt je
   Dienst über `hosts.json` (Microsoft Advertising an `bat.bing.com` und `bat.bing.net`).
11. **Pixel-Liste des Shops festgehalten** (`webPixelsConfigList`, `<lauf>/web-pixels-before.json`):
   Pixel überleben den Theme-Wechsel, und nach dem Launch wird gegen genau diese Liste verglichen. Eine
   Vorschau des alten Themes zeigt danach schon die neue Liste.
12. **Jedes Custom Pixel, das entfällt oder ersetzt wird, gesichert und gelesen**: Code und Notiz unter
   `migration/inventory/pixels/` (`apps-and-tracking.md`, "Custom Pixels sichern"). Ein Pixel, das nur
   in der Kasse sendet, sieht kein Mitschnitt; ohne Sicherung kein Go.
13. **Keine App-Einträge im Entwurf, die nicht hochgeladen wurden**: neue Zeilen mit `render`,
   `include` oder `script` in `layout/theme.liquid` und neue oder wieder eingeschaltete App-Embeds gegen
   das Ziel-Repo.
14. **Go/No-Go-Kriterien schriftlich**: was muss stimmen, damit veröffentlicht wird.
15. **Rückfallkriterien schriftlich** (`rollback.md`): welcher Einbruch über welchen Zeitraum führt zum
   Zurückschalten, wer entscheidet. Im Ernstfall wird nicht diskutiert. Eingetragen mit
   `bin/theme launch rollback` nach `migration/rollback.json`; das Cockpit zeigt sie im Blatt der Migration.
16. **Liste dessen, was ein Rückfall nicht zurückdreht**, dem Team gezeigt (`rollback.md`; im Cockpit
   unter Rückfall, was nur diesen Launch betrifft, zuerst).
17. **Kommunikation:** Termin, Stopp und Rückfallkriterien an alle Beteiligten.

## Go/No-Go (Gate G5)

Go nur, wenn alles davon stimmt:

- G4 entschieden, kein offener Punkt für G4 oder G5 in der Liste offener Punkte, keine Quelle mit
  Offenem außerhalb der Liste (`run_state gate --gate G5-go-live` verweigert sonst)
- SEO-Ausgabe ohne Lücke gegen live
- Abgleich II ohne offene Änderung, Schlussprüfung direkt vorher ohne Änderung
- Vergleichswerte von diesem oder dem Vortag liegen vor
- Pixel-Liste festgehalten, jedes entfallende Custom Pixel gesichert und gelesen
- Rückfall-Theme liegt in der Theme-Bibliothek, ID notiert
- Ansprechpartner erreichbar, Zeitpunkt nach den Regeln oben

Die Entscheidung trifft die Person der Marke nach Abstimmung mit Path to AI, und sie wird mit Namen
festgehalten. In einem Migrationslauf ist G5 selbst ein Go-Punkt (`go-decision`): solange es offen ist,
ist die Haken-Liste nicht grün, und niemand wird gefragt, ob jetzt veröffentlicht werden soll.

## Veröffentlichen

**Das macht die Skill, nach dem ausdrücklichen Ja der Person der Marke.** Gefragt wird nur, wenn die
Haken-Liste vom selben Tag ganz grün ist, G5 eingeschlossen. Das Ja gilt mit Namen; ein Sammelname
("Team") zählt nicht, so wenig wie bei einem Gate.

In dieser Reihenfolge, alles in `launch publish --approved-by "<Name>"`:

1. **Schlussprüfung** von `sync-live-theme` (`sync --final`): `updatedAt` des Live-Themes und die
   Template-Zuweisungen gegen den Abgleich vor dem Launch. Jede Änderung seitdem hält den Launch an, es
   wird nicht veröffentlicht.
2. **Sicherung des Entwurfs:** `layout/theme.liquid` und `config/settings_data.json`, genau wie sie
   veröffentlicht werden, nach `reporting/runs/<date>-launch-check/published-draft/`. Gegen diese
   Sicherung prüft der Launch-Check danach, ob sich eine App beim Veröffentlichen eingetragen hat.
   Scheitert der Abruf, steht der Grund in `launch.json`; verglichen wird dann mit dem Ziel-Repo.
3. **Veröffentlichen** über die Shopify CLI: `shopify theme publish --store <shop> --theme <neue ID>
   --path <ziel-repo> --force --no-input`. Flags am 10.11.2026 gegen CLI 4.9.4 geprüft; vor einer
   Änderung erneut über die Skill `shopify-use-shopify-cli`. Angemeldet wie beim Upload über
   `cli-theme`.
4. **Zurücklesen:** das neue Theme hat die Rolle `MAIN`, das alte ist Entwurf. Erst das zählt als
   veröffentlicht, nicht die Meldung der CLI.
5. **Stand festhalten:** `published_at`, neue `live_theme_id`, `rollback_theme_id` und
   `launch_approved_by` im Migrationslauf, `live_theme_id` in der Config, alles in
   `reporting/runs/<date>-launch-check/launch.json`.

Andere Wege, nur wenn das Team sie ausdrücklich will, dann durch einen Menschen im Admin:

| Weg | Wann |
|---|---|
| Shopify Rollouts, zeitgesteuert | Veröffentlichen zu einem festen Zeitpunkt ohne jemanden vor dem Bildschirm; jemand muss trotzdem erreichbar sein |
| Rollouts, temporär oder prozentual | gestufter Launch an einen Teil der Besucher, mit automatischer Rückkehr; Shopify legt eine Sicherungskopie an |
| Rollouts, Experiment | A/B-Test zweier Themes, laut Hilfe-Seite standardmäßig 90 Tage mit 50/50 und automatischer Rückkehr am Ende |

Rollouts gibt es seit 05.06.2026 unter Märkte, Rollouts, nicht für Vintage-Themes. Laut Hilfe-Seite
Rollouts ab Basic und Experimente ab Grow; vor dem Einsatz im Admin des Shops prüfen, ob die Option
dort steht. Auch dann läuft die Schlussprüfung unmittelbar vorher (`sync --final`), und der Stand wird
danach mit `run_state set` festgehalten.

## Prüfungen am Launch-Tag

Direkt nach dem Veröffentlichen ("Jetzt kommt der Launch-Check After."), als Haken-Liste über
`launch check --after`, in dieser Reihenfolge:

1. Das veröffentlichte Theme ist das erwartete (ID, Rolle `MAIN`), das alte liegt als Entwurf. Keine
   App hat sich beim Veröffentlichen in `layout/theme.liquid` oder als App-Embed eingetragen
   (`app-injections-after`, gegen die Sicherung des Entwurfs): gehört der Eintrag zu einer gestrichenen
   App, ist das ein Befund, sonst eine Frage. Abschalten in der App entfernt eine eingetragene Zeile
   nicht; sie wird von Hand entfernt und die App abgeschaltet oder deinstalliert.
2. `robots.txt` wie vorher und für `*` und Googlebot offen; kein `noindex` oder `nofollow`, das im alten
   Theme nicht stand. Shopify sperrt einzelne Crawler ganz (etwa `Nutch`) und setzt auf Suchseiten
   selbst den Header `X-Robots-Tag: noindex`; beides ist Plattform-Standard und unabhängig vom Theme.
3. Statuscodes und Canonicals der Top-Seiten aus der Schutzliste, Redirects der Top-Seiten;
   strukturierte Daten, hreflang und Open Graph gegen den Mitschnitt von vorher.
4. Apps, Embeds und Analyse-Ereignisse auf dem veröffentlichten Theme: Mitschnitt je Seitentyp gegen
   den Mitschnitt vorher, weil die Vorschau andere Bedingungen hatte. Dasselbe im Zustand "alle
   akzeptiert", wenn das Team den Mitschnitt mit Einwilligung freigegeben hat: dieselben Dienste wie
   vorher, und die Einwilligung erreicht Shopify (`customerPrivacy`) und den Consent Mode. Ein
   Mitschnitt, in dem der Cookie-Dialog nicht bedient wurde, zählt nicht; am 15.10.2026 wurde der
   Pandectes-Dialog so übersehen. Ohne Einwilligung sendet kein Werbe- oder Analysedienst neu
   (`tracking-pre-consent-after`, je Dienst über `hosts.json`, also `bat.bing.com` und `bat.bing.net`).
   Die Pixel-Liste des Shops gegen die von vor dem Launch (`web-pixels-after`): ein fehlendes Pixel ist
   ein Befund, außer es ist bewusst entfernt und, als Custom Pixel, gesichert.
5. Kasse und Kauf mit einer Testbestellung, **nur nach ausdrücklicher Freigabe durch das Team**: das
   Skript geht die Kasse bis zur Zahlung durch (Warenkorb, Steuer- und Versandhinweis, Versand), die
   Bestellung setzt ein Mensch ab. Danach je Ziel ein Status mit Beleg: Bestellung in Shopify, GA4 über
   die Transaktions-ID im Bericht, Google Ads, Meta und die übrigen Pixel über den Kauf-Aufruf von der
   Dankeseite (die Konten selbst zeigen eine Testbestellung ohne Anzeigenklick nicht). **Jede
   GA4-Property und jede Google-Ads-Kauf-Conversion, die der Shop vorher bediente**, ist ein eigener
   Punkt (aus Bestandsaufnahme, Mitschnitt, Pixel-Konfiguration und gesicherten Custom Pixels); ein Kauf
   an irgendeine Property genügt nicht. Läuft der Kauf über den Server, bestätigt ein Mensch ihn im
   Echtzeitbericht jeder Property. Was sich ohne Zugang nicht prüfen lässt, steht als nicht prüfbar, nie
   als erfüllt. Danach storniert und erstattet das Team; der nächste Lauf liest den Stand aus der
   Bestellung.
6. Jede Sprache und jeder Markt-Pfad einmal.
7. Sitemap in der Search Console neu einreichen.
8. Den Stand festhalten: `published_at`, neue `live_theme_id`, ID des Rückfall-Themes und wer Ja gesagt
   hat. Nach dem geführten Launch steht er schon im Migrationslauf; der Punkt `record-after` bestätigt es.

Ab dem Umschalten laufen Umsatz, Conversion Rate, Fehlerseiten und Kaufabbrüche unter Beobachtung,
die ersten 48 Stunden eng (`post-launch.md`).

## Quellen

- https://help.shopify.com/en/manual/online-store/themes/managing-themes/publishing-themes
- `shopify theme publish --help` und `shopify theme list --help`, Shopify CLI 4.9.4, abgerufen am 10.11.2026
- https://changelog.shopify.com/posts/schedule-publish-and-a-b-test-new-themes-and-checkout-and-customer-account-configurations
- https://help.shopify.com/en/manual/markets/rollouts/rollout-types
- https://help.shopify.com/en/manual/markets/rollouts/requirements-and-considerations
- https://moz.com/blog/website-migration-guide (Fachquelle)
- https://auth0.com/docs/get-started/architecture-scenarios/business-to-consumer/launch/launch-day
- https://developers.google.com/analytics/devguides/reporting/data/v1/realtime-api-schema (Echtzeit ohne
  `transactionId`)
- https://support.cookiefirst.com/hc/en-us/articles/360011568738-Cookie-Banner-Public-API-documentation
