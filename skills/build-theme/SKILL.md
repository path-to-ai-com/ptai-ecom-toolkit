---
name: build-theme
description: Das neue Shopify-Theme lokal bauen, ohne den Shop anzufassen: Ziel-Repo mit dem Upstream (etwa Horizon) als Remote aufsetzen und Version festhalten, Templates, Section-Groups und settings_data.json per Generator aus Sicherung, Inventaren und Mapping erzeugen, zuerst in ein Testverzeichnis und gegen den Repo-Stand gedifft, eigene Funktionen als Dateien mit Präfix bauen, Eingriffe in Dateien des Ziel-Themes verzeichnen, Theme Check und Limits prüfen. Nutzen bei "neues Theme bauen", "Templates erzeugen", "Generator laufen lassen", "Ziel-Repo aufsetzen", "Horizon aufsetzen", "Korrektur einbauen", in Phase 4 einer Theme-Migration und in jeder Runde der Schleife aus Neubau, Upload und Prüfung. Nicht verwenden für das Hochladen (ptai-ecom:upload-theme) und nicht für die Zuordnung selbst (ptai-ecom:map-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# build-theme: das neue Theme bauen

Baut das Ziel-Theme lokal und reproduzierbar: aus eingefrorenen Quellen, über einen Generator, mit
jeder Eingabe per Prüfsumme belegt. Handarbeit in `templates/` gibt es nicht; was dort von Hand
korrigiert wird, dreht der nächste Lauf zurück.

Arbeitsverzeichnis ist der Kunden-Workspace. Das Ziel-Theme liegt in einem eigenen Repo
(`theme_migration.target_repo`), das nur das Theme enthält: eine GitHub-Anbindung im Shopify-Admin
akzeptiert nur die Standardstruktur, und ein sauberes Theme-Repo lässt sich per `git merge` vom
Upstream aktualisieren. Generator, Mapping und Verzeichnis der Eingriffe liegen im Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit.** Liquid, Schemas,
Block-Typen und Einstellungen entstehen über `shopify-plugin:shopify-liquid` und werden mit dessen
Validator geprüft, Flags der CLI über `shopify-plugin:shopify-use-shopify-cli`. Nie aus dem Gedächtnis:
ein Neubau aus Erinnerung landet auf dem Stand der Trainingsdaten und ist danach selbst ein Fall für
die nächste Migration.

Regeln aus Fehlern stehen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/customizations.md`,
Abschnitte 5 und 6.

## Voraussetzungen

- `reporting/config.json` mit dem Block `theme_migration` (`target_theme`, `target_repo`,
  `file_prefix`).
- **Gate G2 entschieden** und `migration/mapping/mapping.json` vorhanden. Den Schritt "Ziel-Repo
  aufsetzen" darf `map-theme` vorher anstoßen, weil er nichts erzeugt und nichts in den Shop schreibt.
- Die Sicherung des Live-Themes und die Inventare unter `migration/inventory/`.
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
- Horizon hat keine Tags und keine Releases. Die Version steht als Commit-Titel und in
  `theme_info.theme_version`; `main` kann unveröffentlichte Funktionen enthalten. Den Commit der
  gewählten Version als `target_theme.ref` und die Version als `target_theme.version` in die
  Konfiguration, nach Rückfrage.
- Gibt es kein öffentliches Repo (Themes aus dem Theme Store außerhalb der Horizon-Familie), liegt das
  unveränderte ZIP als Branch `upstream`; ein Update kommt als neues ZIP auf diesen Branch und wird
  gemergt.
- Das Repo des Teams kommt als Remote `origin` dazu. Gearbeitet wird auf `main`.

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

`--living` erzeugt nur Templates, die einem Objekt zugewiesen sind, dazu die Grundtypen; jedes
übersprungene steht im Report. Ein alternatives Template (`collection.<name>`) folgt der Zuordnung
seines Grundtyps, wenn es nicht einzeln im Mapping steht.

Der Generator schreibt `templates/*.json`, `sections/*-group.json` und `config/settings_data.json`
nach `--out`, dazu `report.json` mit verworfenen Einstellungen, gesetzten Standardwerten,
`build`-Fällen und Limit-Verstößen. `sources.lock` hält Herkunft und SHA-256 jeder Eingabe.

**Regeln des Generators**, jede aus einem belegten Fehler, geprüft in seinen Tests:

- Ein fehlender Schlüssel heißt Schema-Standard, nie "aus".
- Nur Einstellungen schreiben, die im Schema des Ziel-Blocks stehen; jede verworfene wird gemeldet.
- Block-IDs stabil und gültig erzeugen.
- Eigenes CSS je Section höchstens 500 Zeichen, sonst in eine eigene Datei.
- Limits vor dem Schreiben prüfen.

### 3. Diffen, dann ersetzen

- Das Testverzeichnis gegen den Stand im Ziel-Repo diffen, JSON normalisiert.
- Jede Abweichung muss aus einer Änderung an Mapping, Overrides, Quelle oder Generator-Regel kommen.
  Eine Abweichung ohne solche Ursache heißt: im Repo steht etwas, das der Generator nicht kennt, etwa
  eine Editor-Änderung nach dem Launch. Dann nicht ersetzen, sondern zuerst die Rückrichtung aus
  `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/post-launch.md`.
- Erst wenn sich nur die beabsichtigten Stellen unterscheiden, die erzeugten Dateien ins Ziel-Repo
  übernehmen.
- Jede Zeile in `report.json` (verworfene Einstellung, Limit-Verstoß) ist entweder behoben oder im
  Mapping begründet. Ein Limit-Verstoß hält den Lauf an.

### 4. Eigene Funktionen

- Was das Mapping als `build` oder `rebuild` führt, entsteht als **eigene Datei mit Präfix**:
  `sections/<file_prefix>-*.liquid`, `blocks/<file_prefix>-*.liquid`, `snippets/<file_prefix>-*.liquid`,
  `assets/<file_prefix>-*.css`, `assets/<file_prefix>-*.js`. Über `shopify-plugin:shopify-liquid`
  erzeugt und mit dessen Validator geprüft.
- Vorhandene Sections des Ziel-Themes erweitern statt nachbauen: das CSS aus `{% stylesheet %}` lädt
  nur für Dateien, die auf der Seite gerendert werden.
- Braucht eine Section Werte ihrer Theme-Blöcke, bekommt sie eine eigene Einstellung; sie liest die
  Einstellungen ihrer Blöcke nicht.
- **Ein Eingriff in eine Datei des Ziel-Themes ist die Ausnahme.** Er trägt im Code einen Kommentar mit
  `<file_prefix>:` und eine Zeile in `migration/customizations.md` mit Datei, Änderung, Grund und
  Prüfung nach dem Update.

### 5. Übersetzungen vorbereiten

Aus `migration/inventory/translations.json` und den Section- und Block-IDs, die der Generator vergeben
hat, entsteht `migration/build/translations.json`: je neuer Schlüssel die Übersetzung des alten Werts.
Die Datei wird im selben Commit wie jede Vorlagenänderung neu gebaut; läuft sie hinterher, zeigen neue
Schlüssel in der Zielsprache stumm den Text der Primärsprache. Registriert wird erst in `upload-theme`.

### 6. Prüfen

```bash
shopify theme check --path <target-repo>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.limits check --theme-dir <target-repo>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations check \
  --target-repo <target-repo> --prefix <file_prefix> --register migration/customizations.md
```

- Theme Check ohne Fehler. Eine Warnung wird gelesen, nicht übersprungen.
- Limits: 25 Sections je Template, 50 Blöcke je Section, 1250 je Template oder Section-Group, 8 Ebenen, 300 Dateien in
  `blocks/`, 512 KB je JSON-Template, 1,5 MB `settings_data.json` und Locale, 256 KB Liquid, 3.400
  Schlüssel je Locale.
- Die Prüfung der Eingriffe ohne Befund: jede geänderte Datei des Ziel-Themes steht im Verzeichnis,
  jede Zeile im Verzeichnis hat ihre Änderung.

### 7. Committen

- Im Ziel-Repo die erzeugten und eigenen Dateien namentlich stagen, eine Botschaft je Runde, die den
  Anlass nennt.
- Im Workspace `sources.lock`, `translations.json`, `customizations.md` und die geänderten
  Mapping-Dateien.

## Updates des Ziel-Themes

Aktualisiert wird im Ziel-Repo per `git merge upstream/<ref>`, nie über den Update-Hinweis im
Shopify-Admin. Vorher:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations check \
  --target-repo <target-repo> --prefix <file_prefix> --register migration/customizations.md \
  --against upstream/<ref>
```

Das zeigt, welche verzeichneten Eingriffe das Update berührt. Nach dem Launch kommt davor die
Rückrichtung der Editor-Änderungen.

## Ergebnis

Ein Ziel-Repo auf `main` mit dem Upstream als Remote, erzeugten Inhalten, eigenen Dateien mit Präfix
und verzeichneten Eingriffen; Theme Check, Limits und die Prüfung der Eingriffe ohne Befund;
`migration/build/sources.lock` und `translations.json` im Workspace. Hochgeladen ist noch nichts.

## Fehlerbilder

- **Korrektur nur im Template:** der nächste Lauf dreht sie zurück. Korrigiert wird im Mapping oder in
  der Generator-Regel, dann neu erzeugt.
- **Editor-Änderungen still überschrieben:** direkt ins Repo erzeugt statt ins Testverzeichnis.
- **Verworfene Einstellungen nicht gelesen:** Shopify verwirft unbekannte Einstellungen ohne Fehler
  auch beim Upload; `report.json` ist die einzige Stelle, an der es vorher auffällt.
- **Mehr als 500 Zeichen CSS je Section:** Shopify lehnt nur diese Datei ab, der Rest des Pakets
  landet. Der Generator lagert aus.
- **Farb-Mapping auf `color_scheme` für Horizon ab 4:** falsch, es gibt nur `color_palette`.
- **Eingriff ohne Kommentar und Verzeichnis:** beim nächsten Update unauffindbar. Die Prüfung der
  Eingriffe meldet ihn.
- **Theme Check meldet abgekündigte Schriften** (`DeprecatedFontsOnSettingsData`): die gemessene Schrift
  aus `design.json` als Schriftstapel übernehmen statt der abgekündigten Einstellung.
