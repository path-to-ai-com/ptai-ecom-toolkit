---
name: snapshot-theme
description: Ein Shopify-Theme vollständig und unverändert sichern, jede Datei mit Inhalt, Größe, Zeitstempel und SHA-256 in einem Manifest belegt, als eigener Commit im Workspace; auf Wunsch zusätzlich das unveränderte Original des Quell-Themes als Vergleichsbasis. Nutzen bei "Theme sichern", "Snapshot vom Theme", "Theme-Stand festhalten", "Live-Theme ziehen", "Original besorgen", vor jedem ersten Handgriff an einem Theme, in Phase 1 einer Theme-Migration und nach dem Launch für die Rückrichtung der Editor-Änderungen ins Repo. Nicht verwenden für den Abgleich gegen eine frühere Sicherung (ptai-ecom:sync-live-theme) und nicht für die Bestandsaufnahme der Inhalte (ptai-ecom:inventory-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# snapshot-theme: ein Theme vollständig sichern

Die Sicherung ist Rückfallebene, Quelle des Generators und der einzige Beleg dafür, wie der Shop
vorher funktioniert hat. Nach dem ersten Handgriff am Theme ist sie nicht mehr herstellbar. Diese
Skill zieht ein Theme (Standard: das Live-Theme) so, dass jede Datei mit Inhalt und Zeitstempel belegt
ist, und legt sie als eigenen, unveränderten Commit ab.

Arbeitsverzeichnis ist der Kunden-Workspace (dort liegt `reporting/`), wie bei jeder Skill dieses
Plugins.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit** (etwa
`shopify-plugin:shopify-admin` für Abfragen, `shopify-plugin:shopify-use-shopify-cli` für die CLI),
nie aus dem Gedächtnis. Das gilt auch für lesende Abfragen: Feldnamen und Verhalten der Theme-API
ändern sich mit der API-Version.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und dem Block `theme_migration`, darin
  `access.read` (`cli-grant`, `portal` oder `staff`). Fehlt der Block, reicht für eine einfache
  Sicherung `shopify_store`; die Skill nimmt dann `cli-grant`.
- Lesezugang mit `read_themes`. Beim Weg `cli-grant` gilt die Scope-Union-Regel aus `pull-shopify`
  (Abschnitt "Scope-Regel"), beim Weg `portal` läuft jeder Aufruf über das Cockpit, ohne Rückfall auf
  die CLI.
- Git im Workspace. Die Sicherung wird committet.

## Ablauf

1. **Theme-Liste lesen und das Ziel nach ID bestimmen**, nie nach Namen: Rolle, Name, `updatedAt`,
   `themeStoreId`. Namen ändern sich im Admin, und ein Entwicklungs-Theme kann wie das Live-Theme
   heißen. Freie Plätze zählen: 20 Themes je Store, auf Plus 100. Bei voller Liste warnen, bevor ein
   Duplikat oder Upload nötig wird, und das Team bitten, nichts zu löschen, ohne vorher zu fragen.
   Löschen ist bei Shopify endgültig.

2. **Sichern:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.snapshot \
     --theme live --out migration/snapshots
   ```

   Statt `live` eine Theme-ID für jedes andere Theme. Das Modul liest Store und Zugangsweg aus
   `reporting/config.json`, zieht erst die Metadaten aller Dateien (seitenweise zu 50), dann die
   Inhalte, fordert Fehlendes gezielt über `filenames` nach, holt Binärdateien über ihre URL und
   schreibt `migration/snapshots/<date>-<theme-id>/` mit allen Dateien und `manifest.json`. Auf stdout
   steht eine JSON-Zeile mit der Zusammenfassung; Exit 0 heißt vollständig, 1 heißt Befunde, 2 heißt
   Fehler.

3. **Vollständigkeit prüfen.** Vollständig ist die Sicherung erst, wenn die Liste der Inhalte die
   reine Metadatenliste deckt. Meldet die Zusammenfassung fehlende Dateien, ist die Sicherung nicht
   fertig: erneut aufrufen, bis nichts mehr fehlt, oder die Lücke mit Dateinamen melden. Nie eine
   halbe Sicherung als ganze ablegen; sie sieht im Repo genauso aus.

4. **Manifest ansehen.** Je Datei Pfad, Größe, `updated_at`, `sha256`, bei JSON zusätzlich
   `sha256_normalized` (Kommentarkopf entfernt, geparst, sortiert). `checksumMd5` von Shopify taugt
   für JSON nicht als Abgleich, weil Shopify JSON beim Schreiben neu serialisiert.

5. **Commit im Workspace**, die Dateien unverändert, nie formatieren, namentlich gestagt:

   ```bash
   git add migration/snapshots/<date>-<theme-id>
   git commit -m "Snapshot theme <theme-id> (<theme-name>) as of <date>"
   ```

   Im selben Commit wird nichts anderes geändert. Die Sicherung ist nur als unveränderter Stand eine
   Rückfallebene.

6. **Ergebnis melden:** Theme-ID, Name, Rolle, Zahl der Dateien, Basis und Version aus
   `config/settings_schema.json` (`theme_info`: `theme_name`, `theme_version`, `theme_author`), freie
   Theme-Plätze, Pfad der Sicherung. Ist `theme_info` leer oder erkennbar falsch, das sagen statt
   raten.

## Das Original (`--original`)

Ohne das unveränderte Quell-Theme in derselben Version ist keine Anpassung bestimmbar. Quellen in
dieser Reihenfolge:

1. **Ein unverändertes Theme im Store.** Welches der Themes ein Original, ein Arbeitsstand oder ein
   alter Zwischenstand ist, entscheidet ein Abgleich der Prüfsummen und Größen von
   `layout/theme.liquid`, `config/settings_data.json` und `config/settings_schema.json` über alle
   Themes, nicht der Name. Gefunden: mit `--theme <id>` sichern wie oben. Dem Team sagen, dass
   dieses Theme nicht gelöscht werden darf.
2. **Ein ZIP vom Team** (vom Theme-Anbieter in der laufenden Version):

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.snapshot \
     --theme live --out migration/snapshots --original-zip <path-to-original.zip>
   ```

3. **Ein Entwicklungs-Store**, in den das Theme frisch aus dem Theme Store installiert wird.

Ein Original aus dem Store ist kein Werksstand: installierte Apps schreiben in jedes Theme, auch in
unveröffentlichte. Das vermerkt die Skill, die Gegenprobe macht `inventory-theme`. Fehlt das
Original ganz, vermerkt `inventory-theme` die Anpassungen als nicht bestimmbar, statt zu raten.

Die weiteren Themes im Store, die nach letzter Arbeit einer Agentur oder einer halbfertigen
Migration aussehen, werden ebenfalls gesichert und als solche vermerkt.

## Nach dem Launch: Rückrichtung

Vor jedem Generatorlauf und vor jedem Upstream-Merge sichert diese Skill das dann live laufende
Ziel-Theme (`--theme live`). Diff und Übernahme ins Ziel-Repo stehen in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/post-launch.md`, Abschnitt "Rückrichtung".

## Ergebnis

- `migration/snapshots/<date>-<theme-id>/` mit allen Dateien und `manifest.json`, als eigener Commit.
- Bei `--original` eine zweite Sicherung als Vergleichsbasis.
- Eine Meldung mit Theme-ID, Basis, Version, freien Plätzen und Vollständigkeit.

Den Stand der Migration (`snapshot`, `live_theme_id`) schreibt nicht diese Skill, sondern
`theme-migration`, damit es genau einen Schreiber gibt.

## Fehlerbilder

- **Die Paginierung endet zu früh, ohne Fehler.** Mit angefordertem Inhalt kann die Verbindung am
  alphabetischen Ende der Liste abbrechen oder einzelne Knoten still auslassen. Das Modul gleicht
  deshalb gegen eine reine Metadatenliste ab. Meldet es trotzdem eine Lücke, die nicht schließt:
  die REST-Asset-Schnittstelle für genau diese Datei ist der Ersatzweg (über die Shopify-Skills
  prüfen).
- **Gedrosselt:** Exit-Code prüfen, warten, erneut. Eine leere Antwort ist nie "keine Dateien".
- **`shopify theme pull` scheitert mit "you don't have access to this dev store"**, obwohl
  `read_themes` im Grant steht: die Theme-Befehle der CLI laufen über den Kontologin, nicht über den
  Grant. Das Modul nutzt deshalb die Admin-API; für `theme pull` bräuchte es ein Konto mit
  Themes-Recht (`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/access-write.md`).
- **Falsches Theme gesichert:** nach Namen gearbeitet. Immer die ID aus der Theme-Liste.
- **Die Sicherung veraltet unbemerkt.** Das Team arbeitet am Live-Theme weiter. Vor jedem Befund, der
  an einer einzelnen Datei hängt, prüft `sync-live-theme`, was sich seither geändert hat; geänderte
  Dateien kommen als neue datierte Sicherung dazu, die erste bleibt unverändert.
- **Volle Theme-Liste:** nicht selbst aufräumen. Das Team entscheidet, welches Theme gesichert und
  gelöscht wird, nachdem das Original gesichert ist.
