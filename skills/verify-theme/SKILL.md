---
name: verify-theme
description: Prüft den Entwurf eines neuen Shopify-Themes, bevor ein Mensch ihn sieht, gegen das Live-Theme und gegen die Bestandsaufnahme, mit neun Prüfern als Subagents (Struktur, Inhalt, SEO, Gestaltung, Funktion, Apps und Tracking, Performance, Barrierefreiheit nach WCAG 2.2 und BFSG, Sprachen), höchstens zwei gleichzeitig auf der Storefront; Befunde mit Linkpaar, Schwere und Ursache, behoben an der Ursache. Mit --test-round erzeugt sie danach über test-round die Abnahme für das Team, je Seitentyp und je offener Abweichung ein Testpunkt mit Linkpaar Entwurf und Live. Nutzen bei "prüf den Entwurf", "Prüfbericht", "ist der Entwurf fertig für die Abnahme", "Abnahme für das neue Theme", "Abnahme vorbereiten", in Phase 6 und Phase 8 einer Theme-Migration. Nicht verwenden für einen einzelnen Bildvergleich (ptai-ecom:compare-themes) und nicht für eine Abnahme ohne Theme-Wechsel (ptai-ecom:test-round). Schreibt nichts in den Shop und schickt nichts ab. Liest reporting/config.json im Kunden-Workspace.
---

# verify-theme: den Entwurf prüfen

Eine reine Code-Prüfung genügt nicht, weil mehrere Risiken eines Theme-Wechsels ohne Fehlermeldung
auftreten. Diese Skill:

- lässt je Disziplin einen Prüfer gegen das Live-Theme und die Bestandsaufnahme laufen
- sammelt die Befunde und führt jeden auf seine Ursache zurück
- erzeugt danach die Abnahme für das Team

Arbeitsverzeichnis: der Kunden-Workspace.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit**, auch in jedem Prüfer: jede
Abfrage, jede Schema-Prüfung, jede Validierung von Liquid. Nie aus dem Gedächtnis. Jeder Prüfer bekommt
diese Regel wörtlich in seinen Auftrag.

Referenzen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`:

- `verify-checklist.md`: Prüfer, Regeln, Schwerestufen, Barrierefreiheit, Performance
- `storefront-parity.md`: Gleichstand je Element, von den Prüfern Gestaltung und Funktion Zeile für
  Zeile abgearbeitet
- `seo-parity.md`: SEO-Liste
- `apps-and-tracking.md`: Apps und Tracking

## Voraussetzungen

- `reporting/config.json` mit `domain`, `drive_path` und dem Block `theme_migration` mit `live_theme_id`
  und `draft_theme_id`.
- Ein hochgeladener Entwurf mit `n von n gleich` (`upload-theme`).
- Die Bestandsaufnahme unter `migration/inventory/` und die Entscheidungen in
  `migration/mapping/decisions.json`.
- `uv` für Playwright.
- Die Liste offener Punkte `migration/open-items.json` (legt `run_state init` an; ohne Migrationslauf
  `open_items init`). Diese Skill führt keinen eigenen Stand: ihr Prüfbericht ist Rohausgabe, offen,
  erledigt und verschoben steht in der Liste.

## Ablauf

1. **Prüfrahmen schreiben:** `migration/verify/<date>/CONTEXT.md`, die Datei, die jeder Prüfer zuerst
   liest. Inhalt:
   - Store und Domain, Live- und Entwurfs-ID
   - Vorschau-Mechanik: `?preview_theme_id=<id>`, Theme-Nachweis über `Shopify.theme.id`, `pb=0`,
     Vorschau-Cookie
   - Beispielseiten (`pages.json`)
   - Entscheidungen des Teams; bereits entschiedene Abweichungen sind kein Befund
   - bekannte offene Punkte aus `migration/open-items.json` mit ihrer `id`; ein Befund zu einem dieser
     Punkte trägt dessen `id`, damit er beim Übernehmen kein zweiter Punkt wird
   - Regeln für jeden Prüfer aus `verify-checklist.md`

2. **Prüfer als Subagents starten.** Je Prüfer ein `Agent`-Aufruf mit dem Typ `general-purpose`, der
   Skills laden kann. Ein installierter, auf Shopify spezialisierter Agent darf den Prüfer übernehmen.
   **Höchstens zwei Prüfer gleichzeitig auf der Storefront**; Prüfer ohne Storefront laufen parallel.
   Reihenfolge:

   | Welle | Prüfer |
   |---|---|
   | 1 | Struktur (ohne Storefront), Inhalt, SEO |
   | 2 | Gestaltung, Funktion |
   | 3 | Apps und Tracking, Sprachen |
   | 4 | Performance, Barrierefreiheit |

   - Die nächste Welle startet, wenn beide Storefront-Prüfer der vorigen fertig sind.
   - Warenkorbtests laufen nacheinander, nie zwei zugleich.

   Ein Subagent erbt das Arbeitsverzeichnis nicht. Jeder Auftrag setzt deshalb `cd "<workspace>" &&` vor
   jeden Befehl und nennt:

   - Prüfer und Gegenstand, die Zeile aus der Prüfer-Tabelle
   - den Pfad zu `CONTEXT.md` und zu `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/verify-checklist.md`
   - für Gestaltung und Funktion zusätzlich `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/storefront-parity.md`
     mit dem Auftrag, jede Zeile des eigenen Prüfers mit Ergebnis in `findings.md` zu führen
   - die Eingabedateien (`seo.json`, `design.json`, `functions.json`, `apps.json`, `tracking.json`,
     `translations.json`, `templates.json`, je nach Prüfer)
   - die Werkzeuge: `crawl-site` für SEO, `compare-themes --compare` für Gestaltung,
     `scripts/browser/capture_network.py` für Apps und Tracking, Lighthouse dreimal mit Median für
     Performance, axe und Lighthouse für Barrierefreiheit, `shopify theme check` und `theme.limits` für
     Struktur
   - das Ausgabeziel `migration/verify/<date>/<checker>/findings.json` plus `findings.md`, mit festem
     Ordnernamen je Prüfer: `structure`, `content`, `seo`, `design`, `function`, `apps_tracking`,
     `languages`, `performance`, `accessibility`. Schritt 5 der Migration zählt genau diese Ordner; ein
     anderer Name zählt nicht als gelaufen
   - den Satz: "Lade für jede Abfrage an Shopify zuerst die passende Shopify-Skill des Shopify AI
     Toolkit und schreib nichts aus dem Gedächtnis. Nur lesen, nichts abschicken. Was du nicht prüfen
     konntest, steht als nicht geprüft mit Grund, nie als bestanden."

3. **Zusammenführen** in `migration/verify/<date>/findings.json`, je Befund:
   - Prüfer, Seitentyp
   - Linkpaar (Entwurf und Live, beide mit `preview_theme_id`)
   - Beschreibung
   - Schwere: `blocker`, `before_launch`, `after_launch`, `info`
   - Ursache: `mapping`, `generator_rule`, `own_file`, `app`, `data`
   - bei Gestaltung der Pfad des Bildpaars im Kundenordner

   Doppelte Befunde verschiedener Prüfer zusammenlegen. Ein gescheiterter Prüfer steht mit Grund als
   nicht geprüft; die übrigen Ergebnisse gelten. Optional je Befund `id` (Kennung eines bekannten
   Punkts) und `gate`; ohne `gate` folgt es der Schwere (`blocker` G4, `before_launch` G5,
   `after_launch` Nachsorge). `info` kommt nicht in die Liste.

   Danach in die Liste offener Punkte übernehmen:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items import --kind findings --path migration/verify/<date>/findings.json
   ```

   Die Ausgabe nennt neue Punkte (`created`) und Abweichungen (`drift`): ein Befund, den die Liste
   schon als erledigt führt und der wieder auftritt, wird mit `open_items reopen --id <id> --reason
   "<text>"` wieder offen, nie still übergangen.

4. **Nachprüfen** der Befunde `blocker` und `before_launch`: nacheinander, ein Prüfer, mit Abstand
   zwischen den Aufrufen. Nicht nachstellbare Befunde werden `info` mit Vermerk.

5. **Vorlegen.** Je Schwere die Zahl und die Befunde mit Linkpaar, je Prüfer die Abdeckung. Jedes
   Bildpaar mit Befund vor der Aufnahme in den Bericht selbst ansehen.

6. **Zurück an die Ursache.** Jeden Befund dort beheben, wo er entsteht:
   - im Mapping (`map-theme`)
   - in der Generator-Regel oder einer eigenen Datei (`build-theme`)
   - danach `upload-theme` und die betroffenen Prüfer erneut
   - **nie nur in der erzeugten Datei**, sonst macht der nächste Lauf die Korrektur rückgängig
   - Befunde mit Ursache `data` als Datenpflege an das Team, nicht ins Theme
   - ist die Nachprüfung bestanden, den Punkt in der Liste mit Beleg erledigen: `open_items done --id
     <id> --evidence "<was geprüft, wo, Datum, Link>"`. Ein Befund, der im nächsten Bericht nur fehlt,
     ist nicht erledigt.

Die Schleife endet, wenn in der Liste kein Punkt `blocker` mehr offen ist (`open_items list --status
open --severity blocker`). Danach Abgleich I (`sync-live-theme`),
dann die Abnahme.

## Abnahme (`--test-round`)

Erst nach der Prüfung und nach Abgleich I, damit das Team einen Stand sieht, der dem heutigen Live-Shop
entspricht.

1. **Abnahme über die Skill `test-round`** schreiben, Lauf-ID `<date>-test`, Datei
   `reporting/runs/<date>-test/test.json`. Anrede, Begriffe und Prüfung vor dem Veröffentlichen regelt
   `test-round`.
2. **Je Seitentyp ein Testpunkt** mit Linkpaar: "In der Testansicht ansehen" mit
   `?preview_theme_id=<draft-theme-id>` und "Im heutigen Shop ansehen" mit
   `?preview_theme_id=<live-theme-id>`. Auch der Link auf den heutigen Shop enthält seine ID, weil
   Shopify die Vorschau per Cookie speichert.
3. **Je offener Abweichung ein Testpunkt** mit `status: decision`: jede bewusste Abweichung, jedes
   geänderte Verhalten, jeder Befund `before_launch`, den das Team sehen soll.
4. **Checkout-Szenarien als Punkte**, weil der Checkout nicht automatisch getestet wird: je Zahlart und
   Versandregel, mit Rabattcode und Gutschein, eingeloggt und als Gast, mobil zuerst, mit dem Hinweis zum
   Stornieren der Testbestellungen.
5. **Für das Handy "Hide bar" vorgeben**, sonst verdeckt die Vorschauleiste Buttons in App-Fenstern.
6. **Testpunkte in die Liste offener Punkte**, wie in `test-round` beschrieben: `open_items import
   --kind test-round --path reporting/runs/<date>-test/test.json`. Jeder Punkt mit `status` liest Gate
   G4. Ein Testpunkt zu einem Befund, der schon in der Liste steht, wird dort ein eigener Punkt; er
   wird zusammen mit dem Befund erledigt, mit Verweis auf dessen `id` im Beleg.
7. Veröffentlichen erst nach ausdrücklichem Go des Betreibers, wie in `test-round` beschrieben.

**Rückmeldungen zuerst nachstellen, dann beheben:**

1. Jede Rückmeldung am Entwurf und live nachstellen, Desktop und WebKit im Handy-Format.
2. Danach einordnen: Korrektur am Theme, Datenpflege, App, live identisch oder Entscheidung für den
   nächsten Termin.
3. Korrekturen wie in Schritt 6 an der Ursache beheben.
4. Die Auflösung am Testpunkt enthält Bildpaar und Linkpaar.

## Ergebnis

- `migration/verify/<date>/findings.json` und `findings.md`, je Prüfer ein Unterordner, Bildpaare im
  Kundenordner. Rohausgabe dieses Laufs, kein Stand.
- Jeder Befund ab `after_launch` in `migration/open-items.json`.
- Mit `--test-round`: `reporting/runs/<date>-test/test.json`, jeder Testpunkt mit `status` in der Liste.
- Eine Meldung mit Zahl der Befunde je Schwere, Abdeckung je Prüfer und nächstem Schritt.

Den Migrationsstand schreibt `theme-migration`, weder diese Skill noch ein Prüfer.

## Fehlerbilder

- **Mehr als zwei Prüfer auf der Storefront:** HTTP 429 und Bot-Abfrage; danach fehlen Bilder und
  Warenkorbtests, obwohl der Bericht vollständig aussieht. Wellen einhalten.
- **Prüfer vergleicht zweimal dasselbe Theme:** Theme-Nachweis fehlt oder Vorschau per `curl`. Nur im
  Browser, beide IDs explizit.
- **Funktionsliste nicht abgehakt:** der Funktionsprüfer arbeitet `functions.json` Zeile für Zeile ab.
- **Nur Chromium:** manche Fehler zeigt nur WebKit. WebKit im iPhone-Format ist Pflicht.
- **Befund nur aus Stil- oder HTML-Messung:** Unsichtbares und Layoutfehler zeigt nur das Bildpaar.
- **Nur Bildpaare ganzer Seiten:** ein Element, das vorhanden, aber anders gesetzt ist (Menüschrift,
  Preisgröße, Variantenauswahl), fällt darin nicht auf. `storefront-parity.md` je Zeile abarbeiten; eine
  Zeile ohne Ergebnis in `findings.md` heißt, der Prüfer ist nicht fertig.
- **Korrektur in der erzeugten Datei:** der nächste Generatorlauf macht sie rückgängig. Ursache beheben.
- **Testbestellung ohne Testmodus:** ist eine echte Bestellung. Der Checkout gehört in die Abnahme und
  am Launch-Tag in eine Testbestellung nach Freigabe.
