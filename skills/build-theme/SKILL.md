---
name: build-theme
description: Baut das neue Shopify-Theme lokal, ohne in den Shop zu schreiben: Ziel-Repo mit dem Upstream (etwa Horizon) als Remote aufsetzen und Version festhalten, Templates, Section-Groups und settings_data.json per Generator aus Sicherung, Inventaren und Mapping erzeugen, zuerst in ein Testverzeichnis und gegen den Repo-Stand gedifft, eigene Funktionen als Dateien mit Präfix bauen, Eingriffe in Dateien des Ziel-Themes verzeichnen, Theme Check und Limits prüfen. Nutzen bei "neues Theme bauen", "Templates erzeugen", "Generator laufen lassen", "Ziel-Repo aufsetzen", "Horizon aufsetzen", "Korrektur einbauen", in Phase 4 einer Theme-Migration und in jeder Runde der Schleife aus Neubau, Upload und Prüfung. Nicht verwenden für das Hochladen (ptai-ecom:upload-theme) und nicht für die Zuordnung selbst (ptai-ecom:map-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# build-theme: das neue Theme bauen

Baut das Ziel-Theme lokal und reproduzierbar: aus eingefrorenen Quellen, über einen Generator, jede
Eingabe mit Prüfsumme. Keine Handarbeit in `templates/`; der nächste Lauf macht sie rückgängig.

- Arbeitsverzeichnis: der Kunden-Workspace. Generator, Mapping und Verzeichnis der Eingriffe liegen dort.
- Das Ziel-Theme liegt in einem eigenen Repo (`theme_migration.target_repo`), das nur das Theme enthält.
  Gründe: die GitHub-Anbindung im Shopify-Admin akzeptiert nur die Standardstruktur, und ein reines
  Theme-Repo lässt sich per `git merge` vom Upstream aktualisieren.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit.** Liquid, Schemas, Block-Typen und
Einstellungen über `shopify-plugin:shopify-liquid` erzeugen und mit dessen Validator prüfen, CLI-Flags
über `shopify-plugin:shopify-use-shopify-cli`. Nie aus dem Gedächtnis, sonst entsteht ein Theme auf dem
Stand der Trainingsdaten.

Regeln aus Fehlern: `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/customizations.md`, Abschnitte 5
und 6.

## Voraussetzungen

- `reporting/config.json` mit dem Block `theme_migration` (`target_theme`, `target_repo`,
  `file_prefix`).
- **Gate G2 entschieden** und `migration/mapping/mapping.json` vorhanden. Ausnahme: den Schritt
  "Ziel-Repo aufsetzen" darf `map-theme` vorher anstoßen, weil er nichts erzeugt und nichts in den Shop
  schreibt.
- Sicherung des Live-Themes und Inventare unter `migration/inventory/`.
- Shopify CLI für `shopify theme check`.

## Ablauf

### 1. Ziel-Repo aufsetzen

Nur beim ersten Lauf.

```bash
git clone --origin upstream <upstream-url> <target-repo>
git -C <target-repo> log upstream/main --oneline -30
git -C <target-repo> switch -c main <ref>
git -C <target-repo> show <ref>:config/settings_schema.json
```

- `<upstream-url>` ist `target_theme.upstream`, für Horizon `https://github.com/Shopify/horizon.git`.
- Horizon hat keine Tags und keine Releases. Die Version steht im Commit-Titel und in
  `theme_info.theme_version`; `main` kann unveröffentlichte Funktionen enthalten.
- Nach Rückfrage den Commit der gewählten Version als `target_theme.ref` und die Version als
  `target_theme.version` in die Konfiguration schreiben.
- Ohne öffentliches Repo (Themes aus dem Theme Store außerhalb der Horizon-Familie): das unveränderte ZIP
  als Branch `upstream`. Ein Update kommt als neues ZIP auf diesen Branch und wird gemergt.
- Das Repo des Teams als Remote `origin` hinzufügen. Gearbeitet wird auf `main`.

### 2. Erzeugen, zuerst in ein Testverzeichnis

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.generate \
  --mapping migration/mapping/mapping.json \
  --overrides migration/mapping/overrides.json \
  --source migration/snapshots/<date>-<theme-id> \
  --target-schemas <target-repo> \
  --out migration/build/out/<date> \
  --lock migration/build/sources.lock \
  --living migration/inventory/templates.json
```

- `--living` erzeugt nur Templates, die einem Objekt zugewiesen sind, plus die Grundtypen; jedes
  übersprungene steht im Report.
- Ein alternatives Template (`collection.<name>`) folgt der Zuordnung seines Grundtyps, wenn es nicht
  einzeln im Mapping steht.
- Ausgabe nach `--out`: `templates/*.json`, `sections/*-group.json`, `config/settings_data.json`, dazu
  `report.json` mit verworfenen Einstellungen, gesetzten Standardwerten, `build`-Fällen und
  Limit-Verstößen.
- `sources.lock` speichert Herkunft und SHA-256 jeder Eingabe.

**Regeln des Generators**, jede durch seine Tests abgesichert:

- Ein fehlender Schlüssel bedeutet Schema-Standard, nie "aus".
- Nur Einstellungen schreiben, die im Schema des Ziel-Blocks stehen; jede verworfene wird gemeldet.
- Block-IDs stabil und gültig erzeugen.
- Eigenes CSS je Section höchstens 500 Zeichen, sonst in eine eigene Datei.
- Limits vor dem Schreiben prüfen.

### 3. Diffen, dann ersetzen

1. Das Testverzeichnis gegen den Stand im Ziel-Repo diffen, JSON normalisiert.
2. Jede Abweichung muss aus einer Änderung an Mapping, Overrides, Quelle oder Generator-Regel stammen.
   Eine Abweichung ohne solche Ursache bedeutet: im Repo steht etwas, das der Generator nicht kennt, etwa
   eine Editor-Änderung nach dem Launch. Dann nicht ersetzen, sondern zuerst die Rückrichtung aus
   `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/post-launch.md`.
3. Erst wenn sich nur die beabsichtigten Stellen unterscheiden, die erzeugten Dateien ins Ziel-Repo
   übernehmen.
4. Jede Zeile in `report.json` (verworfene Einstellung, Limit-Verstoß) ist behoben oder im Mapping
   begründet. Ein Limit-Verstoß stoppt den Lauf.

### 4. Eigene Funktionen

- Was das Mapping als `build` oder `rebuild` führt, entsteht als **eigene Datei mit Präfix**:
  `sections/<file_prefix>-*.liquid`, `blocks/<file_prefix>-*.liquid`, `snippets/<file_prefix>-*.liquid`,
  `assets/<file_prefix>-*.css`, `assets/<file_prefix>-*.js`. Über `shopify-plugin:shopify-liquid`
  erzeugt und mit dessen Validator geprüft.
- Vorhandene Sections des Ziel-Themes erweitern statt nachbauen: das CSS aus `{% stylesheet %}` lädt nur
  für Dateien, die auf der Seite gerendert werden.
- Braucht eine Section Werte ihrer Theme-Blöcke, bekommt sie eine eigene Einstellung; sie liest nicht die
  Einstellungen ihrer Blöcke.
- **Ein Eingriff in eine Datei des Ziel-Themes ist die Ausnahme.** Pflicht dafür: Kommentar mit
  `<file_prefix>:` im Code und eine Zeile in `migration/customizations.md` mit Datei, Änderung, Grund und
  Prüfung nach dem Update.

### 5. Übersetzungen vorbereiten

- Aus `migration/inventory/translations.json` und den vom Generator vergebenen Section- und Block-IDs
  entsteht `migration/build/translations.json`: je neuer Schlüssel die Übersetzung des alten Werts.
- Die Datei im selben Commit wie jede Vorlagenänderung neu bauen. Wird sie später gebaut, zeigen neue
  Schlüssel in der Zielsprache ohne Fehlermeldung den Text der Primärsprache.
- Registriert wird erst in `upload-theme`.

### 6. Prüfen

```bash
shopify theme check --path <target-repo>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.limits check --theme-dir <target-repo>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations check \
  --target-repo <target-repo> --prefix <file_prefix> --register migration/customizations.md
```

- Theme Check ohne Fehler. Jede Warnung lesen, nicht überspringen.
- Limits: 25 Sections je Template, 50 Blöcke je Section, 1250 je Template oder Section-Group, 8 Ebenen,
  300 Dateien in `blocks/`, 512 KB je JSON-Template, 1,5 MB `settings_data.json` und Locale, 256 KB
  Liquid, 3.400 Schlüssel je Locale.
- Prüfung der Eingriffe ohne Befund: jede geänderte Datei des Ziel-Themes steht im Verzeichnis, jede
  Zeile im Verzeichnis hat ihre Änderung.

### 7. Committen

- Im Ziel-Repo die erzeugten und eigenen Dateien namentlich stagen; eine Commit-Message je Runde, die den
  Anlass nennt.
- Im Workspace `sources.lock`, `translations.json`, `customizations.md` und die geänderten
  Mapping-Dateien.

## Updates des Ziel-Themes

Aktualisieren im Ziel-Repo per `git merge upstream/<ref>`, nie über den Update-Hinweis im
Shopify-Admin. Vorher:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations check \
  --target-repo <target-repo> --prefix <file_prefix> --register migration/customizations.md \
  --against upstream/<ref>
```

- Die Ausgabe zeigt, welche verzeichneten Eingriffe das Update berührt.
- Nach dem Launch zuvor die Rückrichtung der Editor-Änderungen ausführen.

## Ergebnis

- Ziel-Repo auf `main` mit dem Upstream als Remote, erzeugten Inhalten, eigenen Dateien mit Präfix und
  verzeichneten Eingriffen.
- Theme Check, Limits und Prüfung der Eingriffe ohne Befund.
- `migration/build/sources.lock` und `translations.json` im Workspace.
- Noch nichts hochgeladen.

## Fehlerbilder

- **Korrektur nur im Template:** der nächste Lauf macht sie rückgängig. Im Mapping oder in der
  Generator-Regel korrigieren, dann neu erzeugen.
- **Editor-Änderungen überschrieben:** direkt ins Repo erzeugt statt ins Testverzeichnis.
- **Verworfene Einstellungen nicht gelesen:** Shopify verwirft unbekannte Einstellungen auch beim Upload
  ohne Fehler; nur `report.json` zeigt sie vorher.
- **Mehr als 500 Zeichen CSS je Section:** Shopify lehnt nur diese Datei ab und übernimmt den Rest des
  Pakets. Der Generator lagert aus.
- **Farb-Mapping auf `color_scheme` für Horizon ab 4:** falsch, es gibt nur `color_palette`.
- **Eingriff ohne Kommentar und Verzeichnis:** beim nächsten Update nicht auffindbar. Die Prüfung der
  Eingriffe meldet ihn.
- **Theme Check meldet abgekündigte Schriften** (`DeprecatedFontsOnSettingsData`): die gemessene Schrift
  aus `design.json` als Schriftstapel übernehmen statt der abgekündigten Einstellung.
