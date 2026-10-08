---
name: upload-theme
description: Lädt das lokal gebaute Theme in ein unveröffentlichtes Shopify-Theme hoch und weist nach, dass der gesendete Inhalt angekommen ist: Schutz vor jedem Schreiben (nur Rolle UNPUBLISHED, Ziel-ID gegen draft_theme_id, Live-Theme vorher und nachher unverändert), Erstanlage über ein Konto mit Themes-Recht oder den Admin-Weg, danach nur geänderte Dateien, Code vor Templates, Zurücklesen jeder Datei mit inhaltlichem Vergleich, Theme-Übersetzungen mit frischen Digests registrieren. Nutzen bei "hochladen", "Entwurf anlegen", "ins Entwurfs-Theme pushen", "Testansicht aktualisieren", "Übersetzungen registrieren", in Phase 5 einer Theme-Migration und in jeder Runde der Schleife aus Neubau, Upload und Prüfung. Veröffentlicht nie und schreibt nie in das Live-Theme. Nicht verwenden für das Bauen (ptai-ecom:build-theme) und nicht für die Prüfung (ptai-ecom:verify-theme). Liest reporting/config.json im Kunden-Workspace.
---

# upload-theme: in ein unveröffentlichtes Theme hochladen

Einzige Skill des Toolkits, die in einen Shop schreibt, und nur in ein Theme mit der Rolle
`UNPUBLISHED`.

- Ruft nie `themePublish`, `shopify theme publish`, `shopify theme push --live` oder `--publish` auf.
- Veröffentlichen macht immer ein Mensch.
- Arbeitsverzeichnis: der Kunden-Workspace.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit:** Mutationen über
`shopify-plugin:shopify-admin` (vor dem ersten Einsatz gegen das aktuelle Schema geprüft), CLI-Flags über
`shopify-plugin:shopify-use-shopify-cli`. Nie aus dem Gedächtnis.

Referenzen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`:

- `access-write.md`: Zugangswege, Scopes, offene Frage der Ausnahme
- `translations.md`: Übersetzungen

## Voraussetzungen

- `reporting/config.json` mit `shopify_store`, `domain` und dem Block `theme_migration`, darin
  `access.write` (`cli-theme` oder `admin-api`) und nach der Erstanlage `draft_theme_id`.
- **Gate G3 entschieden** für die Erstanlage. Spätere Runden der Schleife brauchen kein neues Gate.
- Ein Ziel-Repo, in dem `build-theme` ohne Befund durchgelaufen ist: Theme Check, Limits, Prüfung der
  Eingriffe.
- Ein freier Theme-Platz für die Erstanlage (20 je Store, auf Plus 100).
- Weg `cli-theme`: ein Konto mit Themes-Recht. Ein Passwort aus Theme Access steht als
  `SHOPIFY_CLI_THEME_TOKEN` in der Umgebung, nie als Argument.
- Weg `admin-api`: Grant mit `write_themes`, `read_translations`, `write_translations` nach der
  Union-Regel aus `pull-shopify`.
- **Der Cockpit-Zugang lehnt Mutationen ab** und ist für diese Skill kein Weg.

## Der Schutz vor jedem Schreiben

Vor jedem Schreibvorgang, auch vor jedem einzelnen Paket:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c "
import json, sys
from theme import guard, shopify
config = json.load(open('reporting/config.json'))
transport = shopify.transport_from_config(config)
block = config['theme_migration']
print(json.dumps({
    'target': guard.check_write_target(transport, sys.argv[1], block['draft_theme_id']),
    'live': guard.live_fingerprint(transport),
}))
" <draft-theme-id>
```

- Ziel-ID gleich `draft_theme_id`, Rolle frisch gelesen `UNPUBLISHED`, nie `MAIN`. Sonst bricht
  `GuardError` ab, und nichts wird geschrieben.
- `updatedAt` des Live-Themes vorher speichern und nach dem Schreiben erneut lesen. Bei einer Änderung
  abbrechen und melden: das Live-Theme wurde von außen geändert, und ein Mensch klärt das, bevor
  weitergeschrieben wird.
- `theme.upload` und `theme.translations` rufen diesen Schutz selbst auf. Beim Weg `cli-theme` ruft ihn
  die Skill vor und nach jedem `shopify theme push`.

## Ablauf

### Erstanlage

1. **Name festlegen**, höchstens 50 Zeichen, eindeutig als Entwurf erkennbar: Ziel-Theme, das Wort
   Entwurf und das Datum. Eine Verwechslung mit dem Live-Theme muss ausgeschlossen sein.

2. **Paket und Limits:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.limits check --theme-dir <target-repo>
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.package \
     --theme-dir <target-repo> --out "migration/build/<date>-theme.zip"
   ```

   Das ZIP ist höchstens 50 MB groß und enthält ein Manifest mit Prüfsummen.

3. **Anlegen**, je nach `access.write`:

   - `admin-api`:

     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.upload create \
       --zip "migration/build/<date>-theme.zip" --name "<draft-name>"
     ```

     Staged Upload plus `themeCreate` mit Rolle `UNPUBLISHED`. Scheitert die Mutation an einer
     Berechtigung, greift die Ausnahme von Shopify nicht. Ersatz ist der Weg `cli-theme`, kein zweiter
     Versuch mit anderen Scopes.
   - `cli-theme`: Befehl ausgeben, Flags vorher über die Shopify-Skills prüfen, dann ausführen:

     ```bash
     shopify theme push --store <shopify_store> --path <target-repo> --unpublished --theme "<draft-name>" --json
     ```

4. **Neue ID** in `theme_migration.draft_theme_id` der Konfiguration schreiben und melden. Den
   Migrationsstand aktualisiert `theme-migration`.

### Aktualisieren

1. **Änderungen im Entwurf prüfen:** `updatedAt` des Entwurfs mit der letzten Runde vergleichen. Wurde er
   im Theme-Editor geändert, zuerst seine JSON-Dateien ziehen und gegen das Ziel-Repo diffen, weil ein
   Upload `config/settings_data.json` und die JSON-Templates überschreibt.
2. **Nur geänderte Dateien**, aus dem Diff des Ziel-Repos seit der letzten hochgeladenen Fassung.
   **Code vor Templates:**
   1. zuerst Liquid, Blöcke, Snippets, Assets, Schema und Locales
   2. danach `templates/*.json`, `sections/*-group.json` und `config/settings_data.json`

   Kommt eine Einstellung erst mit diesem Upload ins Schema, muss die Block-Datei vor dem Template im
   Shop sein, sonst verwirft Shopify die Einstellung ohne Meldung.

   - `admin-api`, in Paketen zu höchstens 50 Dateien, bei `userErrors` anhalten:

     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.upload update \
       --theme <draft-theme-id> --dir <target-repo> --files <code-files>
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.upload update \
       --theme <draft-theme-id> --dir <target-repo> --files <template-files>
     ```

   - `cli-theme`, mit Schutz davor und danach:

     ```bash
     shopify theme push --store <shopify_store> --path <target-repo> --theme <draft-theme-id> --only <file> --nodelete
     ```

3. **Bei einem Fehler anhalten.** Bei einem Validierungsfehler lehnt Shopify nur die betroffene Datei ab
   und übernimmt den Rest; ein Paket ohne Abbruch ist also nicht fehlerfrei.

### Zurücklesen

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.upload verify \
  --theme <draft-theme-id> --dir <target-repo>
```

- Jede geschriebene Datei zurücklesen und inhaltlich vergleichen, JSON normalisiert (Kommentarkopf
  entfernt, sortiert).
- `checksumMd5` ist für JSON unbrauchbar, und ein ZIP-Import meldet Erfolg, auch wenn er ungültiges JSON
  ohne Meldung weggelassen hat.
- Ergebnis: `n von n gleich`. Jede Abweichung ist ein Befund und wird gemeldet, nie übergangen.
- Eine Abweichung in einem Template bedeutet meist: Shopify hat eine Einstellung verworfen, die der Block
  nicht kennt.

### Theme-Übersetzungen

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.translations register \
  --theme <draft-theme-id> --source migration/build/translations.json
```

- Übersetzbare Inhalte frisch **vom Entwurf** lesen, mit aktuellen Digests, dann über
  `translationsRegister` registrieren und zurücklesen.
- Nach jeder Änderung eines Ausgangswerts erneut registrieren, sonst liefert Shopify weiter die alte
  Übersetzung aus.
- **Store-Übersetzungen nie ändern.** Produkte, Seiten und Menüs gehören beiden Themes.

### App-Embeds prüfen

Die App-Embeds kommen mit `config/settings_data.json` aus `build-theme` in den Entwurf, kein Mensch schaltet
sie im Editor ein. Belegt in einer Migration im September 2026: die Embeds standen im ersten Neubau und
liefen im Entwurf.

1. Nach dem Zurücklesen jedes Embed aus dem Report von `build-theme` mit `carried: true` in der
   zurückgelesenen `settings_data.json` suchen.
2. Fehlt eines, hat Shopify den Block verworfen, meist weil die App nicht installiert ist oder die
   Erweiterung eine neue ID hat. Nur dann braucht es einen Menschen: App installieren oder im Editor
   einschalten. Danach die Datei ins Ziel-Repo zurückholen, damit der nächste Upload die Aktivierung
   nicht überschreibt.
3. Eine App, die nicht über ein Embed läuft (etwa eine Neuinstallation wie Analyzify), ist keine Aufgabe
   für den Entwurf, sondern eine Entscheidung aus G1. Sie steht nicht in der Meldung an das Team.

## Ergebnis

- Ein unveröffentlichtes Theme mit bekannter ID, Inhalt `n von n gleich`, Theme-Übersetzungen
  registriert, Live-Theme nachweislich unverändert.
- Die Testansicht als Link: `https://<domain>/?preview_theme_id=<draft-theme-id>`.
- Eine Meldung mit ID, Zahl der Dateien, Abweichungen, registrierten Übersetzungen und den Embeds, die
  Shopify verworfen hat (im Normalfall keines).

## Fehlerbilder

- **`GuardError`:** Ziel ist nicht der Entwurf oder nicht `UNPUBLISHED`. Nichts schreiben, melden. Die
  Prüfung nie umgehen.
- **Live-Theme während des Uploads geändert:** abbrechen, melden, `sync-live-theme` anbieten.
- **20 von 20 Themes belegt:** das Team entscheidet, welches Theme gesichert und gelöscht wird. Die
  Skill löscht nie ein Theme.
- **`FILE_VALIDATION_ERROR` bei einer Section:** meist mehr als 500 Zeichen eigenes CSS oder eine
  unzulässige Einstellung. Ursache im Generator oder in der eigenen Datei beheben, neu bauen.
- **Zurückgelesene Datei weicht ab:** eine Einstellung wurde verworfen. Schema des Ziel-Blocks prüfen,
  Block-Datei vor dem Template hochladen.
- **Übersetzung abgelehnt oder bleibt `outdated`:** Digest vom falschen Stand. Frisch vom Entwurf lesen
  und erneut registrieren.
- **Admin-Weg scheitert an der Berechtigung:** die Ausnahme greift nicht. Weg `cli-theme` mit einem
  Konto mit Themes-Recht.
- **Gedrosselt:** Exit-Code prüfen, warten, erneut. Ein halbes Paket ist kein Erfolg.
