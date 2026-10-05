---
name: verify-theme
description: Den Entwurf eines neuen Shopify-Themes prüfen, bevor ein Mensch ihn sieht, gegen das Live-Theme und gegen die Bestandsaufnahme, mit neun Prüfern als Subagents (Struktur, Inhalt, SEO, Gestaltung, Funktion, Apps und Tracking, Performance, Barrierefreiheit nach WCAG 2.2 und BFSG, Sprachen), höchstens zwei gleichzeitig auf der Storefront; Befunde mit Linkpaar, Schwere und Ursache, die an der Ursache behoben werden. Mit --test-round erzeugt sie danach über test-round die Testrunde für das Team, je Seitentyp und je offener Abweichung ein Testpunkt mit Linkpaar Entwurf und Live. Nutzen bei "prüf den Entwurf", "Prüfbericht", "ist der Entwurf fertig für die Testrunde", "Testrunde für das neue Theme", "Abnahme vorbereiten", in Phase 6 und Phase 8 einer Theme-Migration. Nicht verwenden für einen einzelnen Bildvergleich (ptai-ecom:compare-themes) und nicht für eine Testrunde ohne Theme-Wechsel (ptai-ecom:test-round). Schreibt nichts in den Shop und schickt nichts ab. Liest reporting/config.json im Kunden-Workspace.
---

# verify-theme: den Entwurf prüfen

Ein Umzug, der nur den Code betrachtet, sieht erfolgreich aus und ist es nicht: mehrere Risiken eines
Theme-Wechsels fallen ohne Fehlermeldung aus. Diese Skill lässt je Disziplin einen Prüfer gegen das
Live-Theme und gegen die Bestandsaufnahme laufen, sammelt die Befunde und führt jeden an seine Ursache
zurück. Danach erzeugt sie die Testrunde für das Team.

Arbeitsverzeichnis ist der Kunden-Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**, auch in jedem
Prüfer: jede Abfrage, jede Schema-Prüfung, jede Validierung von Liquid. Nie aus dem Gedächtnis. Jeder
Prüfer bekommt das wörtlich in seinen Auftrag.

Prüfer, Regeln, Schwerestufen, Barrierefreiheit und Performance stehen in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/verify-checklist.md`, die SEO-Liste in
`seo-parity.md`, Apps und Tracking in `apps-and-tracking.md`, alle im selben Ordner.

## Voraussetzungen

- `reporting/config.json` mit `domain`, `drive_path` und dem Block `theme_migration` mit
  `live_theme_id` und `draft_theme_id`.
- Ein hochgeladener Entwurf mit `n von n gleich` (`upload-theme`).
- Die Bestandsaufnahme unter `migration/inventory/` und die Entscheidungen in
  `migration/mapping/decisions.json`.
- `uv` für Playwright.

## Ablauf

1. **Prüfrahmen schreiben:** `migration/verify/<date>/CONTEXT.md`, die eine Datei, die jeder Prüfer
   zuerst liest. Darin: Store und Domain, Live- und Entwurfs-ID, die Vorschau-Mechanik
   (`?preview_theme_id=<id>`, Theme-Nachweis über `Shopify.theme.id`, `pb=0`, Vorschau-Cookie), die
   Beispielseiten (`pages.json`), die Entscheidungen des Teams (bereits entschiedene Abweichungen sind
   kein Befund), bekannte offene Punkte und die Regeln für jeden Prüfer aus `verify-checklist.md`.

2. **Prüfer als Subagents starten.** Je Prüfer ein `Agent`-Aufruf mit dem Typ `general-purpose`, der
   Skills laden kann. Ist ein auf Shopify spezialisierter Agent installiert, darf er den Prüfer
   übernehmen. **Höchstens zwei Prüfer gleichzeitig auf der Storefront**; Prüfer ohne Storefront laufen
   daneben. Reihenfolge:

   | Welle | Prüfer |
   |---|---|
   | 1 | Struktur (ohne Storefront), Inhalt, SEO |
   | 2 | Gestaltung, Funktion |
   | 3 | Apps und Tracking, Sprachen |
   | 4 | Performance, Barrierefreiheit |

   Die nächste Welle startet, wenn beide Storefront-Prüfer der vorigen fertig sind. Warenkorbtests
   laufen nacheinander, nie zwei zugleich.

   Ein Subagent erbt das Arbeitsverzeichnis nicht. Jeder Auftrag beginnt deshalb mit
   `cd "<workspace>" &&` vor jedem Befehl und nennt:

   - Prüfer und Gegenstand, die Zeile aus der Prüfer-Tabelle
   - den Pfad zu `CONTEXT.md` und zu `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/verify-checklist.md`
   - die Eingabedateien (`seo.json`, `design.json`, `functions.json`, `apps.json`, `tracking.json`,
     `translations.json`, `templates.json`, je nach Prüfer)
   - die Werkzeuge: `crawl-site` für SEO, `compare-themes --compare` für Gestaltung,
     `scripts/browser/capture_network.py` für Apps und Tracking, Lighthouse dreimal mit Median für
     Performance, axe und Lighthouse für Barrierefreiheit, `shopify theme check` und
     `theme.limits` für Struktur
   - das Ausgabeziel `migration/verify/<date>/<checker>/findings.json` plus `findings.md`
   - den Satz: "Lade für jede Abfrage an Shopify zuerst die passende Shopify-Skill des Shopify AI
     Toolkit und schreib nichts aus dem Gedächtnis. Nur lesen, nichts abschicken. Was du nicht prüfen
     konntest, steht als nicht geprüft mit Grund, nie als bestanden."

3. **Zusammenführen** in `migration/verify/<date>/findings.json`: je Befund Prüfer, Seitentyp,
   Linkpaar (Entwurf und Live, beide mit `preview_theme_id`), Beschreibung, Schwere (`blocker`,
   `before_launch`, `after_launch`, `info`), Ursache (`mapping`, `generator_rule`, `own_file`, `app`,
   `data`), bei Gestaltung der Pfad des Bildpaars im Kundenordner. Doppelte Befunde verschiedener
   Prüfer zusammenlegen. Ein Prüfer, der gescheitert ist, steht mit Grund als nicht geprüft, die
   übrigen Ergebnisse gelten.

4. **Nachprüfen** der Befunde `blocker` und `before_launch`, nacheinander, ein Prüfer, mit Abstand
   zwischen den Aufrufen. Was sich nicht nachstellen lässt, wird `info` mit Vermerk.

5. **Vorlegen.** Je Schwere die Zahl und die Befunde mit Linkpaar, je Prüfer die Abdeckung. Jedes
   Bildpaar, das einen Befund trägt, wird selbst angesehen, bevor es in den Bericht geht.

6. **Zurück an die Ursache.** Jeder Befund wird dort behoben, wo er entsteht: im Mapping (`map-theme`),
   in der Generator-Regel oder einer eigenen Datei (`build-theme`), danach `upload-theme` und die
   betroffenen Prüfer erneut. **Nie nur in der erzeugten Datei**, sonst dreht der nächste Lauf die
   Korrektur zurück. Befunde der Ursache `data` gehen als Datenpflege an das Team, nicht in das Theme.

Die Schleife endet, wenn kein Befund `blocker` mehr offen ist. Dann folgt Abgleich I
(`sync-live-theme`), danach die Testrunde.

## Testrunde (`--test-round`)

Erst nach der Prüfung und nach Abgleich I, damit das Team einen Stand sieht, der den Live-Shop von
heute abbildet.

1. **Testrunde über die Skill `test-round`** schreiben, Lauf-ID `<date>-test`, Datei
   `reporting/runs/<date>-test/test.json`. Anrede, Begriffe und Prüfung vor dem Veröffentlichen regelt
   `test-round`.
2. **Je Seitentyp ein Testpunkt** mit Linkpaar: "In der Testansicht ansehen" mit
   `?preview_theme_id=<draft-theme-id>` und "Im heutigen Shop ansehen" mit
   `?preview_theme_id=<live-theme-id>`. Auch der Link auf den heutigen Shop trägt seine ID; Shopify
   merkt sich die Vorschau per Cookie.
3. **Je offener Abweichung ein Testpunkt** mit `status: decision`: jede bewusste Abweichung, jedes
   geänderte Verhalten, jeder Befund `before_launch`, den das Team sehen soll.
4. **Checkout-Szenarien als Punkte**, weil der Checkout nicht automatisch getestet wird: je Zahlart und
   Versandregel, mit Rabattcode und Gutschein, eingeloggt und als Gast, mobil zuerst, mit dem Hinweis,
   wie Testbestellungen danach storniert werden.
5. **Für das Handy "Hide bar" vorgeben:** die Vorschauleiste verdeckt sonst Buttons in App-Fenstern.
6. Veröffentlichen erst auf ausdrückliches Go des Betreibers, wie in `test-round` beschrieben.

**Rückmeldungen werden erst nachgestellt, dann behoben.** Jede Rückmeldung am Entwurf und live
nachstellen, Desktop und WebKit im Handy-Format, und erst danach einordnen: Korrektur am Theme,
Datenpflege, App, live genauso, oder Entscheidung für den nächsten Termin. Eine Korrektur läuft wie in
Schritt 6 an ihre Ursache, und die Auflösung am Testpunkt trägt Bildpaar und Linkpaar.

## Ergebnis

- `migration/verify/<date>/findings.json` und `findings.md`, je Prüfer ein Unterordner, Bildpaare im
  Kundenordner.
- Mit `--test-round`: `reporting/runs/<date>-test/test.json`.
- Eine Meldung mit Zahl der Befunde je Schwere, Abdeckung je Prüfer und dem nächsten Schritt.

Den Stand der Migration schreibt `theme-migration`, nicht diese Skill und keiner der Prüfer.

## Fehlerbilder

- **Mehr als zwei Prüfer auf der Storefront:** HTTP 429 und eine Bot-Abfrage, danach fehlen Bilder und
  Warenkorbtests, und der Bericht sieht trotzdem vollständig aus. Wellen einhalten.
- **Prüfer vergleicht zweimal dasselbe Theme:** Theme-Nachweis fehlt oder Vorschau per `curl`. Nur im
  Browser, beide IDs explizit.
- **Funktionsliste nicht abgehakt:** der Funktionsprüfer arbeitet `functions.json` Zeile für Zeile ab,
  nicht nach Eindruck.
- **Nur Chromium:** manche Fehler zeigt nur WebKit. WebKit im iPhone-Format ist Pflicht.
- **Befund nur aus Stil- oder HTML-Messung:** Unsichtbares und Layoutfehler zeigt nur das Bildpaar.
- **Korrektur in der erzeugten Datei:** der nächste Generatorlauf dreht sie zurück. Ursache beheben.
- **Testbestellung ohne Testmodus:** ist eine echte Bestellung. Der Checkout gehört in die Testrunde
  und, am Launch-Tag, in eine Testbestellung nach Freigabe.
