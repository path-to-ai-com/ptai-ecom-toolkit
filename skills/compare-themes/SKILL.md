---
name: compare-themes
description: Misst die Gestaltung eines Shopify-Themes am gerenderten Shop oder vergleicht zwei Themes je Beispielseite. Modus --measure: Schriften, Farben, Radien, Buttons, Abstände und Breakpoints des Live-Themes je Textrolle und Komponente als design.json. Modus --compare: ganze Seiten als Bildpaare am Rechner (1440 px, Chromium) und am Handy (390 px, WebKit als iPhone), Stilwerte, SEO-Ausgabe, Wortzahl und Netzwerk-Hosts, links immer das veröffentlichte Theme, rechts der Entwurf, mit einer Vergleichsseite; der vollständige Bildvergleich aller Beispielseiten ist Pflicht vor Gate G4. Nutzen bei "Design messen", "Style Guide aus dem Shop", "Bildpaare", "Bildvergleich", "live gegen Entwurf", "sieht der Entwurf aus wie heute", "vergleich die Themes", in Phase 2 und Phase 6 einer Theme-Migration und vor Gate G4. Nicht verwenden für die vollständige Prüfung aller Disziplinen (ptai-ecom:verify-theme) und nicht für Screenshots eines einzelnen Shops (ptai-ecom:capture-screens). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# compare-themes: Gestaltung messen und Themes vergleichen

Maßstab einer Migration ist, dass der Shop aussieht wie vorher. Diese Skill:

- misst die Gestaltung des Live-Themes am gerenderten Shop
- stellt zwei Themes Seite für Seite gegenüber
- misst immer die Auslieferung, nie die Einstellungen

Arbeitsverzeichnis: der Kunden-Workspace.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit**, nie aus dem Gedächtnis. Die
Messung läuft im Browser; Theme-IDs, Theme-Daten oder Schema-Werte aus dem Shop kommen über die
Shopify-Skills.

## Voraussetzungen

- `reporting/config.json` mit `domain`, `drive_path` und dem Block `theme_migration` (`live_theme_id`,
  für `--compare` auch `draft_theme_id`).
- `migration/inventory/pages.json` (`inventory-theme`).
- `uv` für Playwright, wie bei `capture-screens`.

## Regeln für jede Messung

- **Vorschau nur im Browser** mit `?preview_theme_id=<id>` und **Theme-Nachweis** auf jeder Seite
  (`Shopify.theme.id` im HTML gleich der erwarteten ID). Seiten ohne passenden Nachweis verwerfen. Ein
  Abruf per `curl` ohne Cookie liefert den Live-Shop.
- Auch das Live-Theme mit seiner ID aufrufen. Shopify speichert eine Vorschau per Cookie; nach dem Öffnen
  des Entwurfs zeigt die normale URL sonst weiter den Entwurf.
- `pb=0` blendet die Vorschauleiste für Messungen aus.
- Consent-Banner über `${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/consent.py` ablehnen, damit
  beide Seiten gleich aussehen.
- **Höchstens zwei Browser gleichzeitig auf einer Storefront**, einige Sekunden Abstand zwischen zwei
  Seitenaufrufen. Mehr löst eine Drosselung aus, und fehlende Bilder fallen erst im Bericht auf.
- WebKit im iPhone-Format ist Pflicht, nicht nur Chromium.

## Modus `--measure <theme>`

Misst die Gestaltung eines Themes (Standard: das Live-Theme) je Beispielseite.

1. Messen:

   ```bash
   uv run --quiet --with playwright==1.58.0 python \
     "${CLAUDE_PLUGIN_ROOT}/scripts/browser/measure_styles.py" \
     --pages migration/inventory/pages.json \
     --out migration/inventory/design.json --theme <live-theme-id>
   ```

   Erfasst:
   - je Textrolle (Überschriften, Fließtext, Preise, Navigation, Buttons, Labels) Schriftfamilie, Größe,
     Gewicht, Zeilenhöhe und Laufweite
   - Farben je Rolle, Radien, Buttons
   - Abstände an wiederkehrenden Komponenten
   - Breakpoints

2. **Schriften mit den Einstellungen abgleichen.** Für abgekündigte Bibliotheksschriften liefert Shopify
   einen Ersatz aus; die Einstellung nennt dann eine nicht sichtbare Schrift. Maßgeblich ist die
   berechnete Schrift je Element. Abweichungen zwischen Einstellung und Messung als Hinweis in
   `design.json`.

3. `design.md` als `.md`-Ansicht schreiben: je Rolle die gemessenen Werte, je Komponente ein Satz. Diese
   Datei ist der Maßstab für Neubau und Prüfung.

## Modus `--compare <a> <b>`

Vergleicht zwei Themes je Beispielseite: `<a>` ist immer das veröffentlichte Theme, `<b>` der Entwurf.

1. **Referenz festlegen.** Die ID des veröffentlichten Themes (Rolle `MAIN`) über die Shopify-Skills
   abfragen, nicht aus der Erinnerung und nicht nur aus der Config. Weicht sie von `live_theme_id` der
   Config ab, die Config nachziehen.

2. **Bildpaare** am Rechner (1440 px, Chromium) und am Handy (390 px, WebKit als iPhone), aus dem
   Workspace:

   ```bash
   uv run --quiet --with playwright==1.58.0 python \
     "${CLAUDE_PLUGIN_ROOT}/scripts/browser/shoot_pair.py" \
     --pages migration/inventory/pages.json \
     --a <live-theme-id> --b <draft-theme-id> \
     --out "<drive_path>/migration/pairs/<date>"
   ```

   - Bilder im Kundenordner (`drive_path`), nie im Repo. Je Seite und Breite die ganze Seite und die
     Erstansicht.
   - Der Theme-Nachweis jeder Seite muss die verlangte ID zeigen. Links muss er außerdem die Rolle `main`
     tragen; sonst meldet die Ausgabe `reference_ok: false` und der Vergleich zählt nicht.
   - Das Skript schreibt neben die Bilder `pairs.json` und in den Workspace
     `migration/verify/<date>/pairs.json` (Referenz, Abdeckung je Seite und Breite, ohne Bilder). Diesen
     Eintrag liest Gate G4. Eine nachgeholte Seite am selben Tag ergänzt ihn.
   - Exit 1 heißt: mindestens ein Bild mit falschem Theme, Fehler oder `incomplete`, oder die Referenz ist
     nicht das veröffentlichte Theme. Diese Seiten nachholen (`--only <id>`), nicht übergehen.

3. **Stilwerte** des Entwurfs mit `measure_styles.py --theme <draft-theme-id>` messen und mit
   `design.json` vergleichen.

4. **SEO-Ausgabe und Wortzahl** je Seite aus dem gerenderten HTML beider Themes, gegen `seo.json`.

5. **Netzwerk-Hosts** je Seite: `capture_network.py --theme <id>` für beide Themes. Jede Fremd-Domain der
   Live-Seite ist im Entwurf vorhanden oder bewusst entfernt (Entscheidung in `apps.json`).

6. **Vergleichsseite** mit allen Bildpaaren, je Seite und Breite links alt, rechts neu, als ganze Seite:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/browser/compose.py" \
     --pairs "<drive_path>/migration/pairs/<date>" \
     --out "<drive_path>/migration/pairs/<date>/compare.html"
   ```

   Oben stehen Referenz und Abdeckung ("n von m Aufnahmen gültig").

7. **Jedes Bildpaar selbst ansehen, die ganze Seite, nicht nur die Erstansicht.**
   - Eine Pixel-Differenz allein ist kein Befund, eine fehlende kein Beweis.
   - Unsichtbare Fehler (berechnete, aber nicht sichtbare Abdunklung, eine Regel ohne Treffer) zeigt nur
     das Bild.
   - "Wie heute" gilt für das ganze Element, nicht nur für das beanstandete Detail.

8. `migration/verify/<date>/compare.json` schreiben, je Seite und Gerät:
   - Bildpaar (Pfad im Kundenordner)
   - Stilabweichungen, SEO-Abweichungen
   - Wortzahl alt und neu
   - Hosts nur live und nur im Entwurf
   - je Abweichung: entschieden (`decisions.json`) oder Befund

9. Ergebnis melden: Link auf die Vergleichsseite und je Abweichung das Linkpaar Entwurf und Live, beide
   mit `preview_theme_id`.

## Pflicht vor Gate G4

Seit 11.11.2026 hält `run_state gate --gate G4-acceptance` an, bis ein vollständiger Bildvergleich vorliegt:
jede Seite aus `migration/inventory/pages.json` am Rechner und am Handy, links das veröffentlichte Theme,
rechts der aktuelle Entwurf (`draft_theme_id`), jede Aufnahme mit Theme-Nachweis. Je Seite und Breite zählt
die jüngste Aufnahme aus allen `migration/verify/<date>/pairs.json`. Stand prüfen:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" visual_compare check
```

Anlass: Bei einem Umzug auf Horizon fielen Layoutfehler erst nach dem Launch auf (Inhaltsseiten schmal und
links, Typografie, Suchseite ohne Suchfeld, Mega-Menü, Newsletter). Die Abnahme prüfte Testpunkte einzeln,
ein Bildvergleich aller Seiten fehlte, und als Vorlage lag zeitweise ein älteres Theme.

## Ergebnis

- `--measure`: `migration/inventory/design.json` und `design.md`.
- `--compare`: Bildpaare und Vergleichsseite im Kundenordner, im Workspace
  `migration/verify/<date>/pairs.json` (für Gate G4) und `migration/verify/<date>/compare.json`
  (Abweichungen je Seite).

## Fehlerbilder

- **Beide Seiten zeigen dasselbe Theme:** Theme-Nachweis fehlt oder stimmt nicht, meist wegen des
  Vorschau-Cookies. Seite verwerfen, frischen Kontext nehmen, beide IDs explizit setzen.
- **Gedrosselt (HTTP 429, Bot-Abfrage):** mehr als zwei Browser oder zu schnelle Aufrufe. Pausieren, dann
  nacheinander mit Abstand.
- **Banner verdeckt die Seite:** `consent.py` kennt das Consent-Werkzeug nicht. Selektor ergänzen statt
  mit Banner messen; ein Bildpaar mit Banner auf einer Seite ist unbrauchbar.
- **Vorschauleiste verdeckt Buttons am Handy:** `pb=0` fehlt.
- **Nur Chromium gemessen:** WebKit-Fehler bleiben unsichtbar. WebKit ist Pflicht.
- **Befund nur aus der Pixel-Differenz:** jedes Bildpaar selbst ansehen.
- **Ganzseiten-Bild nur so hoch wie das Fenster, nachgeladene Bilder leer (Horizon):** Horizon scrollt am
  Rechner nicht das Dokument, sondern `.page-wrapper`. `shoot_pair` scrollt seit 11.11.2026 auch im
  Container und gibt ihn für die Aufnahme frei (`capture.method: released`). Steht dort `resized`, wurde das
  Fenster auf Seitenhöhe gesetzt; Abschnitte mit voller Bildschirmhöhe sind festgesetzt (`pinned`). Bild
  trotzdem ansehen.
- **Footer leer (Horizon):** der Footer nutzt `content-visibility: auto` und rendert erst, wenn er im Bild
  war. `shoot_pair` erzwingt `content-visibility: visible` vor der Aufnahme.
- **`incomplete`:** das Ganzseiten-Bild zeigt nicht die ganze Seite. Seite nachholen; zählt nicht für G4.
- **Links ein älteres Theme:** `reference_ok: false`, die Seiten zeigen nicht die Rolle `main`. Referenz
  ist immer das veröffentlichte Theme mit seiner ID.
- **Nur die Erstansicht verglichen:** Fehler weiter unten (Newsletter, Footer, Breite von Inhaltsseiten)
  bleiben unsichtbar. Die Vergleichsseite zeigt die ganze Seite.
