---
name: compare-themes
description: Misst die Gestaltung eines Shopify-Themes am gerenderten Shop oder vergleicht zwei Themes je Beispielseite. Modus --measure: Schriften, Farben, Radien, Buttons, Abstände und Breakpoints des Live-Themes je Textrolle und Komponente als design.json. Modus --compare: Bildpaare Desktop (Chromium) und iPhone (WebKit), Stilwerte, SEO-Ausgabe, Wortzahl und Netzwerk-Hosts zweier Themes, meist Live gegen Entwurf, mit einer Vergleichsseite. Nutzen bei "Design messen", "Style Guide aus dem Shop", "Bildpaare", "live gegen Entwurf", "sieht der Entwurf aus wie heute", "vergleich die Themes", in Phase 2 und Phase 6 einer Theme-Migration. Nicht verwenden für die vollständige Prüfung aller Disziplinen (ptai-ecom:verify-theme) und nicht für Screenshots eines einzelnen Shops (ptai-ecom:capture-screens). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
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

Vergleicht zwei Themes je Beispielseite, meist `<a>` Live und `<b>` Entwurf.

1. **Bildpaare** Desktop (Chromium) und iPhone (WebKit):

   ```bash
   uv run --quiet --with playwright==1.58.0 python \
     "${CLAUDE_PLUGIN_ROOT}/scripts/browser/shoot_pair.py" \
     --pages migration/inventory/pages.json \
     --a <live-theme-id> --b <draft-theme-id> \
     --out "<drive_path>/migration/pairs/<date>"
   ```

   Bilder im Kundenordner (`drive_path`), nie im Repo.

2. **Stilwerte** des Entwurfs mit `measure_styles.py --theme <draft-theme-id>` messen und mit
   `design.json` vergleichen.

3. **SEO-Ausgabe und Wortzahl** je Seite aus dem gerenderten HTML beider Themes, gegen `seo.json`.

4. **Netzwerk-Hosts** je Seite: `capture_network.py --theme <id>` für beide Themes. Jede Fremd-Domain der
   Live-Seite ist im Entwurf vorhanden oder bewusst entfernt (Entscheidung in `apps.json`).

5. **Vergleichsseite** mit allen Bildpaaren:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/browser/compose.py" \
     --pairs "<drive_path>/migration/pairs/<date>" \
     --out "<drive_path>/migration/pairs/<date>/compare.html"
   ```

6. **Jedes Bildpaar selbst ansehen.**
   - Eine Pixel-Differenz allein ist kein Befund, eine fehlende kein Beweis.
   - Unsichtbare Fehler (berechnete, aber nicht sichtbare Abdunklung, eine Regel ohne Treffer) zeigt nur
     das Bild.
   - "Wie heute" gilt für das ganze Element, nicht nur für das beanstandete Detail.

7. `migration/verify/<date>/compare.json` schreiben, je Seite und Gerät:
   - Bildpaar (Pfad im Kundenordner)
   - Stilabweichungen, SEO-Abweichungen
   - Wortzahl alt und neu
   - Hosts nur live und nur im Entwurf
   - je Abweichung: entschieden (`decisions.json`) oder Befund

8. Ergebnis melden: Link auf die Vergleichsseite und je Abweichung das Linkpaar Entwurf und Live, beide
   mit `preview_theme_id`.

## Ergebnis

- `--measure`: `migration/inventory/design.json` und `design.md`.
- `--compare`: Bildpaare und Vergleichsseite im Kundenordner, `migration/verify/<date>/compare.json` im
  Workspace.

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
