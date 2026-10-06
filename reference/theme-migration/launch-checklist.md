# Launch

Stand 05.10.2026. Gilt für Phase 9. Der Launch ist der Schritt, in dem ein Mensch das neue Theme
veröffentlicht. Die Skills bereiten vor, prüfen und beobachten; sie veröffentlichen nie.

Ausführbar ist diese Liste als Skill `launch-check` (seit 06.10.2026): je Punkt ein Status mit Beleg,
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

1. **Abnahme (G4) entschieden**, alle Befunde `blocker` und `before_launch` erledigt.
2. **Änderungsstopp läuft** (`change-freeze.md`), Termin steht beim Team.
3. **Abgleich II** (`sync-live-theme`): jede Änderung seit Abgleich I entschieden und im Entwurf.
4. **Vergleichswerte direkt vorher ziehen:** `pull-gsc`, `pull-ga4`, `pull-cwv`, Crawl des
   Live-Themes, Rankings, Conversion je Seitentyp und Gerät. Verglichen wird nach dem Launch mit
   diesen Werten, nicht mit einer Baseline von vor Wochen: Saison und Wachstum dazwischen würden
   jeden Vergleich verfälschen.
5. **App-Embeds im Entwurf aktiviert** und App-Blöcke platziert. Embeds gelten je Theme; was im
   Entwurf eingeschaltet ist, ist nach dem Veröffentlichen eingeschaltet.
6. **Theme-Übersetzungen** auf dem Entwurf registriert und nicht `outdated`.
7. **Go/No-Go-Kriterien schriftlich**: was muss stimmen, damit veröffentlicht wird.
8. **Rückfallkriterien schriftlich** (`rollback.md`): welcher Einbruch über welchen Zeitraum führt zum
   Zurückschalten, wer entscheidet. Im Ernstfall wird nicht diskutiert.
9. **Liste dessen, was ein Rückfall nicht zurückdreht**, dem Team gezeigt (`rollback.md`).
10. **Kommunikation:** Termin, Stopp und Rückfallkriterien an alle Beteiligten.

## Go/No-Go (Gate G5)

Go nur, wenn alles davon stimmt:

- G4 entschieden, keine offenen Befunde `blocker` oder `before_launch`
- Abgleich II ohne offene Änderung, Schlussprüfung direkt vorher ohne Änderung
- Vergleichswerte von diesem oder dem Vortag liegen vor
- Rückfall-Theme liegt in der Theme-Bibliothek, ID notiert
- Ansprechpartner erreichbar, Zeitpunkt nach den Regeln oben

Die Entscheidung trifft ein Mensch und sie wird mit Namen festgehalten.

## Veröffentlichen

**Das macht ein Mensch im Admin.** Die Skill nennt den Weg und wartet.

| Weg | Wann |
|---|---|
| Veröffentlichen in der Theme-Bibliothek | der Normalfall; das alte Theme wandert zu den Entwürfen, keine Änderung geht verloren |
| Shopify Rollouts, zeitgesteuert | Veröffentlichen zu einem festen Zeitpunkt ohne jemanden vor dem Bildschirm; jemand muss trotzdem erreichbar sein |
| Rollouts, temporär oder prozentual | gestufter Launch an einen Teil der Besucher, mit automatischer Rückkehr; Shopify legt eine Sicherungskopie an |
| Rollouts, Experiment | A/B-Test zweier Themes, laut Hilfe-Seite standardmäßig 90 Tage mit 50/50 und automatischer Rückkehr am Ende |

Rollouts gibt es seit 05.06.2026 unter Märkte, Rollouts, nicht für Vintage-Themes. Laut Hilfe-Seite
Rollouts ab Basic und Experimente ab Grow; vor dem Einsatz im Admin des Shops prüfen, ob die Option
dort steht.

Unmittelbar vor dem Klick läuft die Schlussprüfung von `sync-live-theme`: `updatedAt` des
Live-Themes und die Template-Zuweisungen. Jede Änderung seit Abgleich II hält den Launch an.

## Prüfungen am Launch-Tag

Direkt nach dem Veröffentlichen, in dieser Reihenfolge:

1. Das veröffentlichte Theme ist das erwartete (ID, Rolle `MAIN`), das alte liegt als Entwurf.
2. `robots.txt` wie vorher, kein `noindex` oder `nofollow`.
3. Statuscodes und Canonicals der Top-Seiten aus der Schutzliste, Redirects der Top-Seiten.
4. Apps und Embeds auf dem veröffentlichten Theme: Mitschnitt je Seitentyp gegen die Liste, weil die
   Vorschau andere Bedingungen hatte.
5. Tracking mit einer Testbestellung, **nur nach ausdrücklicher Freigabe durch das Team**: Pixel,
   Checkout, Dankeseite, Events in GA4 und Werbekonten. Danach stornieren und erstatten.
6. Jede Sprache und jeder Markt-Pfad einmal.
7. Sitemap in der Search Console neu einreichen.
8. Den Stand festhalten: `published_at`, neue `live_theme_id`, ID des Rückfall-Themes.

Ab dem Umschalten laufen Umsatz, Conversion Rate, Fehlerseiten und Kaufabbrüche unter Beobachtung,
die ersten 48 Stunden eng (`post-launch.md`).

## Quellen

- https://help.shopify.com/en/manual/online-store/themes/managing-themes/publishing-themes
- https://changelog.shopify.com/posts/schedule-publish-and-a-b-test-new-themes-and-checkout-and-customer-account-configurations
- https://help.shopify.com/en/manual/markets/rollouts/rollout-types
- https://help.shopify.com/en/manual/markets/rollouts/requirements-and-considerations
- https://moz.com/blog/website-migration-guide (Fachquelle)
- https://auth0.com/docs/get-started/architecture-scenarios/business-to-consumer/launch/launch-day
