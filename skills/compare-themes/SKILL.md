---
name: compare-themes
description: Misst die Gestaltung eines Shopify-Themes am gerenderten Shop oder vergleicht zwei Themes je Beispielseite. Modus --measure: Schriften, Farben, Radien, Buttons, Abstände und Breakpoints des Live-Themes je Textrolle und Komponente als design.json. Modus --compare: ganze Seiten als Bildpaare am Rechner (1440 px, Chromium) und am Handy (390 px, WebKit als iPhone), am Handy auch mit offenem Menü samt Prüfung auf fremde Elemente über der Schublade, Stilwerte, SEO-Ausgabe, Wortzahl und Netzwerk-Hosts, links immer das veröffentlichte Theme mit ID und Name (nach dem Launch das Rückfall-Theme), rechts der Entwurf, mit einer Vergleichsseite; der vollständige Bildvergleich aller Beispielseiten ist Pflicht vor Gate G4. Nutzen bei "Design messen", "Style Guide aus dem Shop", "Bildpaare", "Bildvergleich", "live gegen Entwurf", "sieht der Entwurf aus wie heute", "vergleich die Themes", in Phase 2 und Phase 6 einer Theme-Migration und vor Gate G4. Nicht verwenden für die vollständige Prüfung aller Disziplinen (ptai-ecom:verify-theme) und nicht für Screenshots eines einzelnen Shops (ptai-ecom:capture-screens). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
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
- **Höchstens zwei Browser gleichzeitig auf einer Storefront**, mindestens drei Sekunden Abstand zwischen
  zwei Seitenaufrufen (`--pace`, Standard 3). Mehr löst eine Drosselung aus. Antwortet Shopify mit HTTP 429
  oder der Warteseite "Nur einen Moment…", ist die Aufnahme `throttled`: kein Fehler des Shops, kein
  Befund, sie zählt nicht für G4; das Skript pausiert und wiederholt sie einmal.
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

1. **Referenz festlegen und nennen.** Vor jedem Vergleich:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" visual_compare reference
   ```

   - Liest die Theme-Liste des Shops und gibt die Referenz mit ID, Name und Vorschau-Link aus, etwa
     "Referenz: Theme 000000000000 „Beispiel Theme“, veröffentlicht". Diese Zeile steht am Anfang jedes
     Ergebnisses, jeder Nachricht und jeder Abnahme.
   - Vor dem Launch ist die Referenz das veröffentlichte Theme (Rolle `MAIN`), nach dem Launch das alte
     Theme, das bis dahin veröffentlicht war (`rollback_theme_id` mit `published_at` im Lauf), nie ein
     drittes.
   - Weicht `live_theme_id` der Config ab, meldet der Aufruf eine Warnung; die Config nachziehen.
   - **Vorschau-Links anderer Themes sind keine Vorlage**, auch nicht ein Link aus einem Chat oder einem
     älteren Bericht. Am 11.11.2026 wurden Schriften gegen ein älteres Theme verglichen und mussten
     zurückgenommen werden.

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
     tragen (nach dem Launch: die ID des Rückfall-Themes); sonst meldet die Ausgabe `reference_ok: false`
     und der Vergleich zählt nicht.
   - **Am Handy auch mit offenem Menü.** Nach der ganzen Seite lädt das Skript die Seite neu, öffnet das
     Menü über den Menüknopf im Kopfbereich und nimmt `<id>/mobile-<a|b>-menu.png` auf. An 240 Punkten über
     der Schublade prüft es, welches Element oben liegt. Ein fremdes Element (Teaser, Kampagnenleiste,
     Chat-Knopf) über der Schublade im Entwurf hält G4 an, außer es liegt im veröffentlichten Theme genauso
     darüber. Findet das Skript den Menüknopf nicht: `--menu-toggle '<css>'`. Anlass: Am Handy lagen ein
     E-Mail-Teaser (z-index 90000) und eine Countdown-Leiste über Horizons Schublade (z-index 18).
   - **Am Rechner auch mit offenem Untermenü** (seit 0.3.31). Ebenso am Rechner: neu laden, auf den
     ersten Menüpunkt mit Untermenü zeigen (Horizon, Broadcast und andere öffnen beim Zeigen), öffnet sich
     nichts, klicken (nie auf einen Link mit Ziel), `<id>/desktop-<a|b>-menu.png` aufnehmen und über dem
     Untermenü dieselbe Prüfung. Öffnet sich links ein Untermenü und rechts keins, oder liegt rechts etwas
     Fremdes darüber, hält G4 an; hat keines der Themes eins, ist es ein Hinweis. Findet das Skript den
     Menüpunkt nicht: `--menu-toggle-desktop '<css>'`. Anlass: Ein Mega-Menü am Rechner war nach dem Launch
     kaputt, der Bildvergleich hatte das Menü nur am Handy geöffnet. Geprüft an Broadcast und Horizon.
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
rechts der aktuelle Entwurf (`draft_theme_id`), jede Aufnahme mit Theme-Nachweis, am Handy rechts mit
offenem Menü ohne fremdes Element darüber. Dazu prüft G4 die Datenschicht je GA4-Property am Handy mit
langsamer Verbindung (`launch-check`, Abschnitt "Ablauf vor dem Launch", Schritt 3). Je Seite und Breite zählt
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
- **Gedrosselt (HTTP 429, Warteseite "Nur einen Moment…"):** mehr als zwei Browser oder zu schnelle
  Aufrufe. Die Aufnahme steht als `throttled`, kein Fehler des Shops. Mit `--parallel 1 --pace 10 --only
  <ids>` nachholen; ein Bild mit gescheitertem Nachladen nie als Befund am Theme werten.
- **"Menü offen: kein Menüknopf gefunden":** das Theme nutzt einen anderen Knopf. Selektor im Browser
  ansehen, mit `--menu-toggle '<css>'` nachholen.
- **"Menü offen: fremde Elemente über der Menü-Schublade":** ein App-Element liegt mit höherem z-index über
  dem Menü. Im Entwurf beheben (Ebene des Elements senken oder es bei offenem Menü ausblenden), neu
  aufnehmen.
- **"Untermenü offen: kein Menüpunkt mit Untermenü gefunden" oder "kein Untermenü sichtbar":** am Rechner
  den Menüpunkt im Browser ansehen und mit `--menu-toggle-desktop '<css>'` nachholen. Öffnet er sich im
  Entwurf wirklich nicht, ist das ein Befund am Theme.
- **Vor G5 noch einmal:** nach dem letzten Abgleich mit dem Live-Theme (Phase 9) alle Beispielseiten neu
  aufnehmen. `visual_compare check --after-sync` zeigt, ob der Vergleich danach vollständig ist; G5 hält
  sonst an.
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
  ist immer das veröffentlichte Theme mit seiner ID, nach dem Launch das Rückfall-Theme
  (`visual_compare reference`).
- **Nur die Erstansicht verglichen:** Fehler weiter unten (Newsletter, Footer, Breite von Inhaltsseiten)
  bleiben unsichtbar. Die Vergleichsseite zeigt die ganze Seite.
