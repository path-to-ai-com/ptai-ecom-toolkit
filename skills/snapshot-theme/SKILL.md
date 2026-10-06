---
name: snapshot-theme
description: Sichert ein Shopify-Theme vollständig und unverändert, jede Datei mit Inhalt, Größe, Zeitstempel und SHA-256 im Manifest, als eigener Commit im Workspace; optional zusätzlich das unveränderte Original des Quell-Themes als Vergleichsbasis. Nutzen bei "Theme sichern", "Snapshot vom Theme", "Theme-Stand festhalten", "Live-Theme ziehen", "Original besorgen", vor der ersten Änderung an einem Theme, in Phase 1 einer Theme-Migration und nach dem Launch für die Rückrichtung der Editor-Änderungen ins Repo. Nicht verwenden für den Abgleich gegen eine frühere Sicherung (ptai-ecom:sync-live-theme) und nicht für die Bestandsaufnahme der Inhalte (ptai-ecom:inventory-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# snapshot-theme: ein Theme vollständig sichern

Die Sicherung ist Rückfallebene, Quelle des Generators und der einzige Nachweis des Ausgangszustands.
Nach der ersten Änderung am Theme lässt sie sich nicht mehr herstellen.

- Zieht ein Theme (Standard: das Live-Theme) mit Inhalt und Zeitstempel je Datei.
- Legt es als eigenen, unveränderten Commit ab.
- Arbeitsverzeichnis: der Kunden-Workspace mit `reporting/`, wie bei jeder Skill dieses Plugins.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit** (etwa
`shopify-plugin:shopify-admin` für Abfragen, `shopify-plugin:shopify-use-shopify-cli` für die CLI), nie
aus dem Gedächtnis. Gilt auch für lesende Abfragen, weil sich Feldnamen und Verhalten der Theme-API mit
der API-Version ändern.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und dem Block `theme_migration`, darin `access.read`
  (`cli-grant`, `portal` oder `staff`). Ohne den Block reicht für eine einfache Sicherung
  `shopify_store`; die Skill nimmt dann `cli-grant`.
- Lesezugang mit `read_themes`.
  - Weg `cli-grant`: Scope-Union-Regel aus `pull-shopify` (Abschnitt "Scope-Regel").
  - Weg `portal`: jeder Aufruf über das Cockpit, ohne Rückfall auf die CLI.
- Git im Workspace. Die Sicherung wird committet.

## Ablauf

1. **Theme-Liste lesen, Ziel nach ID bestimmen**, nie nach Namen: Rolle, Name, `updatedAt`,
   `themeStoreId`. Namen sind im Admin änderbar, und ein Entwicklungs-Theme kann wie das Live-Theme
   heißen.
   - Freie Plätze zählen: 20 Themes je Store, auf Plus 100.
   - Liste voll: warnen, bevor ein Duplikat oder Upload nötig wird, und das Team bitten, kein Theme
     ohne Rückfrage zu löschen. Löschen ist bei Shopify endgültig.

2. **Sichern:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.snapshot \
     --theme live --out migration/snapshots
   ```

   - Für jedes andere Theme statt `live` die Theme-ID.
   - Das Modul liest Store und Zugangsweg aus `reporting/config.json`.
   - Es zieht zuerst die Metadaten aller Dateien (seitenweise zu 50), dann die Inhalte, fordert Fehlendes
     gezielt über `filenames` nach und holt Binärdateien über ihre URL.
   - Ausgabe: `migration/snapshots/<date>-<theme-id>/` mit allen Dateien und `manifest.json`; auf stdout
     eine JSON-Zeile mit der Zusammenfassung.
   - Exit 0: vollständig. Exit 1: Befunde. Exit 2: Fehler.

3. **Vollständigkeit prüfen.** Vollständig erst, wenn die Inhaltsliste die reine Metadatenliste deckt.
   Meldet die Zusammenfassung fehlende Dateien: erneut aufrufen, bis nichts fehlt, oder die Lücke mit
   Dateinamen melden. Nie eine unvollständige Sicherung als vollständig ablegen; im Repo ist der
   Unterschied nicht sichtbar.

4. **Manifest prüfen.** Je Datei Pfad, Größe, `updated_at`, `sha256`, bei JSON zusätzlich
   `sha256_normalized` (Kommentarkopf entfernt, geparst, sortiert). `checksumMd5` von Shopify ist für
   JSON kein Vergleichswert, weil Shopify JSON beim Schreiben neu serialisiert.

5. **Commit im Workspace**, Dateien unverändert, nie formatieren, namentlich gestagt:

   ```bash
   git add migration/snapshots/<date>-<theme-id>
   git commit -m "Snapshot theme <theme-id> (<theme-name>) as of <date>"
   ```

   Im selben Commit nichts anderes ändern; nur ein unveränderter Stand taugt als Rückfallebene.

6. **Ergebnis melden:** Theme-ID, Name, Rolle, Zahl der Dateien, Basis und Version aus
   `config/settings_schema.json` (`theme_info`: `theme_name`, `theme_version`, `theme_author`), freie
   Theme-Plätze, Pfad der Sicherung. Ist `theme_info` leer oder erkennbar falsch, das melden statt zu
   raten.

## Das Original (`--original`)

Anpassungen lassen sich nur gegen das unveränderte Quell-Theme in derselben Version bestimmen. Quellen in
dieser Reihenfolge:

1. **Ein unverändertes Theme im Store.** Ob ein Theme Original, Arbeitsstand oder alter Zwischenstand
   ist, entscheidet ein Abgleich der Prüfsummen und Größen von `layout/theme.liquid`,
   `config/settings_data.json` und `config/settings_schema.json` über alle Themes, nicht der Name.
   Gefunden: mit `--theme <id>` sichern wie oben und dem Team sagen, dass dieses Theme nicht gelöscht
   werden darf.
2. **Ein ZIP vom Team** (vom Theme-Anbieter, in der laufenden Version):

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.snapshot \
     --theme live --out migration/snapshots --original-zip <path-to-original.zip>
   ```

3. **Ein Entwicklungs-Store**, in den das Theme frisch aus dem Theme Store installiert wird.

- Ein Original aus dem Store ist kein Werksstand: installierte Apps schreiben in jedes Theme, auch in
  unveröffentlichte. Die Skill vermerkt das; die Gegenprobe macht `inventory-theme`.
- Fehlt das Original ganz, vermerkt `inventory-theme` die Anpassungen als nicht bestimmbar.
- Weitere Themes im Store, die nach letzter Agenturarbeit oder einer abgebrochenen Migration aussehen,
  ebenfalls sichern und als solche vermerken.

## Nach dem Launch: Rückrichtung

Vor jedem Generatorlauf und vor jedem Upstream-Merge das dann live laufende Ziel-Theme sichern
(`--theme live`). Diff und Übernahme ins Ziel-Repo:
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/post-launch.md`, Abschnitt "Rückrichtung".

## Ergebnis

- `migration/snapshots/<date>-<theme-id>/` mit allen Dateien und `manifest.json`, als eigener Commit.
- Bei `--original` eine zweite Sicherung als Vergleichsbasis.
- Eine Meldung mit Theme-ID, Basis, Version, freien Plätzen und Vollständigkeit.

Den Migrationsstand (`snapshot`, `live_theme_id`) schreibt `theme-migration`, nicht diese Skill; es gibt
genau einen Schreiber.

## Fehlerbilder

- **Paginierung endet zu früh, ohne Fehler.** Mit angefordertem Inhalt kann die Verbindung am
  alphabetischen Ende der Liste abbrechen oder einzelne Knoten ohne Meldung auslassen. Das Modul gleicht
  deshalb gegen eine reine Metadatenliste ab. Bleibt eine Lücke offen: für genau diese Datei die
  REST-Asset-Schnittstelle als Ersatzweg (über die Shopify-Skills prüfen).
- **Gedrosselt:** Exit-Code prüfen, warten, erneut. Eine leere Antwort bedeutet nie "keine Dateien".
- **`shopify theme pull` scheitert mit "you don't have access to this dev store"**, obwohl `read_themes`
  im Grant steht: die Theme-Befehle der CLI nutzen den Kontologin, nicht den Grant. Das Modul nutzt
  deshalb die Admin-API. `theme pull` bräuchte ein Konto mit Themes-Recht
  (`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/access-write.md`).
- **Falsches Theme gesichert:** nach Namen gearbeitet. Immer die ID aus der Theme-Liste.
- **Sicherung veraltet ohne Hinweis:** das Team arbeitet am Live-Theme weiter. Vor jedem Befund an einer
  einzelnen Datei prüft `sync-live-theme` die Änderungen seither. Geänderte Dateien kommen als neue
  datierte Sicherung hinzu; die erste bleibt unverändert.
- **Volle Theme-Liste:** nicht selbst aufräumen. Das Team entscheidet nach Sicherung des Originals,
  welches Theme gesichert und gelöscht wird.
