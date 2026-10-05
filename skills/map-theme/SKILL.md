---
name: map-theme
description: Die Zuordnung eines Shopify-Quell-Themes auf ein Online-Store-2.0-Ziel-Theme erzeugen, aus der build-theme baut, und jede Entscheidung mit Person und Datum festhalten: je lebendes Template ein Ziel, je Section- und Block-Typ ein Ausgang (configure, build, drop) mit Transformation je Einstellung, je Funktion rebuild, native, app oder drop, die gemessene Gestaltung auf die Einstellungen des Ziel-Themes (Horizon ab 4 mit color_palette statt Farbschemata), je behaltene App der Weg im neuen Theme. Nutzt fertige Zuordnungen aus der Mapping-Bibliothek, wo es sie gibt. Nutzen bei "Mapping alt auf neu", "Zuordnung der Sections", "welche Section wird was", "was bauen wir nach", in Phase 3 einer Theme-Migration und nach jedem Befund, dessen Ursache in der Zuordnung liegt. Nicht verwenden für das Erzeugen der Dateien (ptai-ecom:build-theme) und nicht für die Bestandsaufnahme (ptai-ecom:inventory-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# map-theme: Zuordnung alt zu neu

Das Mapping ist die einzige Stelle, an der festgelegt wird, was aus dem alten Theme im neuen wird.
Der Generator baut nur daraus. Eine Korrektur, die nicht hier oder in einer Generator-Regel steht,
dreht der nächste Lauf zurück.

Arbeitsverzeichnis ist der Kunden-Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit.** Schemas,
Section- und Block-Typen, Einstellungstypen (etwa `color_palette`) und ihr Verhalten werden über
`shopify-plugin:shopify-liquid` und die Doku geprüft, nie aus dem Gedächtnis.

Regeln zu Funktionen und stillen Abweichungen stehen in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/customizations.md`, die Wege je App in
`apps-and-tracking.md`, beide im selben Ordner.

## Voraussetzungen

- Die Bestandsaufnahme unter `migration/inventory/` (`templates.json`, `customizations.json`,
  `functions.json`, `apps.json`, `design.json`, `translations.json`).
- **Gate G1 entschieden**: je App, Funktion und Template übernehmen, ersetzen oder streichen, in
  `migration/mapping/decisions.json`. Ohne G1 baut diese Skill keine Zuordnung, sie würde Entscheidungen
  vorwegnehmen.
- Das Ziel-Theme lokal, mit Schemas: das Ziel-Repo aus `theme_migration.target_repo` mit dem Upstream
  in der Version `target_theme.ref`. Fehlt es, zuerst `build-theme`, Schritt "Ziel-Repo aufsetzen";
  der Schritt schreibt nichts in den Shop.

## Ablauf

1. **Schemas beider Themes lesen.**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c "
   import json, sys
   from theme import schema
   source = schema.extract(sys.argv[1])
   target = schema.extract(sys.argv[2])
   json.dump({'source': source, 'target': target}, open('migration/mapping/schemas.json', 'w'), indent=2)
   " migration/snapshots/<date>-<theme-id> <target-repo>
   ```

   Je Section und Block: Einstellungen mit `id`, `type`, `default`, erlaubte Blöcke, `presets`.

2. **Mapping-Bibliothek prüfen.** Gibt es für Quell-Theme und Ziel-Theme in passender Hauptversion
   eine fertige Zuordnung unter
   `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/mappings/<source>__<target>.json`, ist sie die
   Grundlage. Sie enthält nur Section- und Einstellungsnamen der öffentlichen Themes. Was in diesem Shop
   abweicht, kommt nach `migration/mapping/overrides.json`, nie in die Bibliothek. Gibt es keine,
   entsteht ein Entwurf aus beiden Schemas, den ein Mensch prüft.

3. **Templates.** Je lebendes Template (`templates.json`) ein Ziel: eine Datei im Ziel-Theme mit
   demselben Suffix. Templates ohne Objekt entfallen, außer das Team hat bei G1 anders entschieden.
   Zuweisungen auf Suffixe ohne Datei bekommen entweder eine Datei oder werden dem Team als
   Datenpflege gemeldet. Markt-Varianten werden mitgeführt.

4. **Sections und Blöcke.** Je Section-Typ, der in einem lebenden Template vorkommt, ein Ausgang:

   | Ausgang | Wann |
   |---|---|
   | `configure` | das Ziel-Theme hat eine passende Section; Einstellungen werden übertragen |
   | `build` | gibt es nicht und wird gebraucht; eigene Datei mit Präfix `<file_prefix>-` |
   | `drop` | wird nicht gebraucht oder ist Altlast |

   Je Einstellung eine Transformation aus der festen Liste: `identity`, `map_values`, `px_to_number`,
   `bool_invert`, `font_handle`, `color_to_palette`, `drop`. **Was keine Transformation abbildet, wird
   `build` mit Begründung, nie stilles Raten.** Vorher:

   - die tatsächlich benutzten Schlüssel je Section-Typ in den lebenden Templates zählen; Quell-Themes
     speichern dieselbe Einstellung unter verschiedenen Namen
   - im alten Code nachlesen, worauf eine Einstellung wirkt (nur Handy, nur Desktop, Textcontainer oder
     Seitenbreite)
   - für jede sichtbare Einstellung den Schalter suchen, der sie sichtbar macht; übertragen wird, was
     live zu sehen ist
   - ein fehlender Schlüssel im alten Template heißt Schema-Standard der alten Section, nie "aus"

5. **Funktionen.** Je Eintrag in `functions.json` und je Anpassung der Klasse Funktion:
   `native`, `app`, `rebuild` oder `drop`, mit Begründung. **Nativ ersetzen schlägt nachbauen.** Was
   das Ziel-Theme anders macht (Verhalten nach dem Hinzufügen zum Warenkorb, Kachel-Links und
   Brotkrumen, Filter-Layout, Menü-Ebenen am Handy), wird dem Team als Entscheidung vorgelegt, nicht
   still festgelegt.

6. **Gestaltung.** `design.json` auf die Einstellungen des Ziel-Themes: Farben, Typografie, Buttons,
   Radien, Abstände. **Ab Horizon 4.0.0 gibt es keine Farbschemata mehr, sondern eine `color_palette`**
   mit 2 bis 20 Farben; ein Mapping auf `color_scheme` ist für aktuelles Horizon falsch. Die Version
   steht in `target_theme.version`. Was das Ziel-Theme nicht abbilden kann, wird `build` oder eine
   bewusste Abweichung, die das Team bei G2 entscheidet.

7. **Apps.** Je Zeile mit `decision: keep` in `apps.json` der Weg im Ziel-Theme
   (`target_integration`): Embed aktivieren, Block auf welchem Template platzieren, Code als eigene
   Datei portieren. Was ein entfernter Tag Manager geladen hat, braucht einen eigenen Weg.

8. **Schreiben**, im Format, das `build-theme` liest:

   ```json
   {
     "source": {"theme": "<source-theme>", "version": "<x>"},
     "target": {"theme": "Horizon", "version": "<y>"},
     "sections": {
       "<source-section-type>": {
         "action": "configure",
         "target": "<target-section-type>",
         "settings": {"<source-key>": {"to": "<target-key>", "transform": "identity"}},
         "blocks": {"<source-block-type>": {"target": "<target-block-type>", "settings": {}}},
         "notes": ""
       }
     },
     "settings_data": {"<source-key>": {"to": "<target-key>", "transform": "identity"}},
     "templates": {"<template-name>": {"action": "configure"}}
   }
   ```

   - `migration/mapping/mapping.json`: Bibliothek plus Shop-Teil, maschinenlesbar.
   - `migration/mapping/overrides.json`: was dieser Shop von der Bibliothek abweicht.
   - `migration/mapping/decisions.json`: je Entscheidung `id`, `subject`, `kind` (`app`, `function`,
     `template`, `section`, `design`, `sync`), `decision`, `reason`, `decided_by`, `decided_at`,
     `source` (`G1`, `G2`, `test-round`, `sync`). Neue Einträge werden angehängt, nie überschrieben.
   - `migration/mapping/mapping.md`: für das Team, je Seitentyp was bleibt, was nachgebaut wird, was
     entfällt, und offen die Punkte, die eine Entscheidung brauchen.

9. **Probelauf**, ohne etwas zu ersetzen. Der Generator schreibt in ein Testverzeichnis; sein
   `report.json` zeigt verworfene Einstellungen, Standardwerte, `build`-Fälle und Limit-Verstöße vor G2:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.generate \
     --mapping migration/mapping/mapping.json \
     --overrides migration/mapping/overrides.json \
     --source migration/snapshots/<date>-<theme-id> \
     --target-schemas <target-repo> \
     --out <scratch-dir>/generate-dry-run \
     --lock <scratch-dir>/generate-dry-run/sources.lock
   ```

   Jede verworfene Einstellung bekommt eine Zeile im Mapping oder eine Begründung.

10. **Für Gate G2 vorlegen:** `mapping.md`, jede `build`-Entscheidung, jedes `drop` einer Funktion,
    jede bewusste Gestaltungsabweichung, jedes geänderte Verhalten. Die Entscheidung trifft ein Mensch;
    festgehalten wird sie von `theme-migration`.

## Nach einem Befund

Liegt die Ursache eines Befunds aus `verify-theme` oder der Testrunde in der Zuordnung, wird hier
korrigiert, nie in der erzeugten Datei. Ändert die Korrektur eine Entscheidung, die bei G1 oder G2
gefallen ist, entscheidet ein Mensch neu, und der neue Eintrag in `decisions.json` nennt den alten.

## Ergebnis

`migration/mapping/` mit `mapping.json`, `overrides.json`, `decisions.json`, `mapping.md` und
`schemas.json`, committet im Workspace, namentlich gestagt.

## Fehlerbilder

- **G1 nicht entschieden:** nicht starten. Die Zuordnung würde Entscheidungen vorwegnehmen.
- **Keine Bibliothek für dieses Quell-Theme:** Entwurf aus beiden Schemas, jede Zeile von einem
  Menschen geprüft. Eine erfundene Zuordnung ist schlimmer als ein offener Punkt.
- **Mapping auf `color_scheme` für Horizon ab 4:** falsch, es gibt nur noch `color_palette`.
- **Shop-Eigenes in die Bibliothek geschrieben:** gehört nach `overrides.json`. Die Bibliothek enthält
  nichts aus einem Shop.
- **Eine Einstellung mit falscher Reichweite übertragen:** im alten Code nachlesen, auf welche Breite
  sie wirkt, und die Section einmal am Desktop und am Handy gegen live vergleichen.
- **Gestaltung aus `settings_data.json` gemappt:** maßgeblich ist `design.json`, die Messung.
