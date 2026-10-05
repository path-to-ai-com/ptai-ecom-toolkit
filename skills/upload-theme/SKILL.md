---
name: upload-theme
description: Das lokal gebaute Theme in ein unveröffentlichtes Shopify-Theme hochladen und belegen, dass angekommen ist, was gesendet wurde: Schutz vor jedem Schreiben (nur Rolle UNPUBLISHED, Ziel-ID gegen draft_theme_id, Live-Theme vorher und nachher unverändert), Erstanlage über ein Konto mit Themes-Recht oder den Admin-Weg, danach nur geänderte Dateien, Code vor Templates, Zurücklesen jeder Datei mit inhaltlichem Vergleich, Theme-Übersetzungen mit frischen Digests registrieren. Nutzen bei "hochladen", "Entwurf anlegen", "ins Entwurfs-Theme pushen", "Testansicht aktualisieren", "Übersetzungen registrieren", in Phase 5 einer Theme-Migration und in jeder Runde der Schleife aus Neubau, Upload und Prüfung. Veröffentlicht nie und schreibt nie in das Live-Theme. Nicht verwenden für das Bauen (ptai-ecom:build-theme) und nicht für die Prüfung (ptai-ecom:verify-theme). Liest reporting/config.json im Kunden-Workspace.
---

# upload-theme: in ein unveröffentlichtes Theme hochladen

Die einzige Skill des Toolkits, die in einen Shop schreibt, und auch sie nur in ein Theme mit der
Rolle `UNPUBLISHED`. Sie ruft nie `themePublish` oder `shopify theme publish` auf, nie
`shopify theme push --live` oder `--publish`. Veröffentlichen ist immer ein Mensch.

Arbeitsverzeichnis ist der Kunden-Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**: Mutationen über
`shopify-plugin:shopify-admin` (vor dem ersten Einsatz gegen das aktuelle Schema geprüft), Flags der
CLI über `shopify-plugin:shopify-use-shopify-cli`. Nie aus dem Gedächtnis.

Zugangswege, Scopes und die offene Frage der Ausnahme stehen in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/access-write.md`, Übersetzungen in
`translations.md` im selben Ordner.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store`, `domain` und dem Block `theme_migration`, darin
  `access.write` (`cli-theme` oder `admin-api`) und, nach der Erstanlage, `draft_theme_id`.
- **Gate G3 entschieden** für die Erstanlage. Spätere Runden der Schleife brauchen kein neues Gate.
- Ein Ziel-Repo, in dem `build-theme` ohne Befund durchgelaufen ist: Theme Check, Limits, Prüfung der
  Eingriffe.
- Ein freier Theme-Platz für die Erstanlage (20 je Store, auf Plus 100).
- Beim Weg `cli-theme` ein Konto mit Themes-Recht; ein Passwort aus Theme Access steht als
  `SHOPIFY_CLI_THEME_TOKEN` in der Umgebung, nie als Argument. Beim Weg `admin-api` der Grant mit
  `write_themes`, `read_translations`, `write_translations` nach der Union-Regel aus `pull-shopify`.
  **Der Cockpit-Zugang lehnt Mutationen ab** und ist für diese Skill kein Weg.

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
  `GuardError` ab, und es wird nichts geschrieben.
- `updatedAt` des Live-Themes vorher festhalten und nach dem Schreiben erneut lesen. Eine Änderung
  bricht ab und wird gemeldet: dann hat jemand oder etwas das Live-Theme geändert, und das klärt ein
  Mensch, bevor weitergeschrieben wird.

Die Module `theme.upload` und `theme.translations` rufen diesen Schutz selbst auf. Beim Weg
`cli-theme` ruft ihn die Skill vor und nach jedem `shopify theme push`.

## Ablauf

### Erstanlage

1. **Name festlegen**, höchstens 50 Zeichen, eindeutig als Entwurf erkennbar: Ziel-Theme, das Wort
   Entwurf und das Datum. Niemand darf ihn mit dem Live-Theme verwechseln.

2. **Paket und Limits:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.limits check --theme-dir <target-repo>
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.package \
     --theme-dir <target-repo> --out "migration/build/<date>-theme.zip"
   ```

   Das ZIP ist höchstens 50 MB groß und trägt ein Manifest mit Prüfsummen.

3. **Anlegen**, je nach `access.write`:

   - `admin-api`:

     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.upload create \
       --zip "migration/build/<date>-theme.zip" --name "<draft-name>"
     ```

     Staged Upload plus `themeCreate` mit Rolle `UNPUBLISHED`. Scheitert die Mutation an einer
     Berechtigung, greift die Ausnahme von Shopify nicht; der Ersatz ist der Weg `cli-theme`, nicht ein
     zweiter Versuch mit anderen Scopes.
   - `cli-theme`: die Skill gibt den Befehl aus, prüft die Flags vorher über die Shopify-Skills und
     lässt ihn laufen:

     ```bash
     shopify theme push --store <shopify_store> --path <target-repo> --unpublished --theme "<draft-name>" --json
     ```

4. **Die neue ID** in `theme_migration.draft_theme_id` der Konfiguration schreiben und melden. Den Stand
   der Migration trägt `theme-migration` nach.

### Aktualisieren

1. **Hat jemand im Entwurf gearbeitet?** `updatedAt` des Entwurfs gegen die letzte Runde halten. Wurde
   er im Theme-Editor geändert, zuerst dessen JSON-Dateien ziehen und gegen das Ziel-Repo diffen: ein
   Upload überschreibt `config/settings_data.json` und die JSON-Templates.
2. **Nur geänderte Dateien**, aus dem Diff des Ziel-Repos seit der letzten hochgeladenen Fassung.
   **Code vor Templates:** zuerst Liquid, Blöcke, Snippets, Assets, Schema und Locales, danach
   `templates/*.json`, `sections/*-group.json` und `config/settings_data.json`. Kommt eine Einstellung
   erst mit diesem Upload ins Schema, muss die Block-Datei vor dem Template liegen, sonst verwirft
   Shopify die Einstellung still.

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

3. **Bei einem Fehler anhalten.** Shopify lehnt bei einem Validierungsfehler nur die betroffene Datei
   ab und übernimmt den Rest; ein Paket "ohne Abbruch" ist deshalb kein Paket ohne Fehler.

### Zurücklesen

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.upload verify \
  --theme <draft-theme-id> --dir <target-repo>
```

Jede geschriebene Datei wird zurückgelesen und inhaltlich verglichen, JSON normalisiert (Kommentarkopf
entfernt, sortiert). `checksumMd5` taugt für JSON nicht, und ein ZIP-Import meldet Erfolg, auch wenn er
ungültiges JSON still weggelassen hat. Ergebnis ist `n von n gleich`; jede Abweichung ist ein Befund
und wird gemeldet, nie übergangen. Eine Abweichung in einem Template heißt meist: Shopify hat eine
Einstellung verworfen, die der Block nicht kennt.

### Theme-Übersetzungen

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.translations register \
  --theme <draft-theme-id> --source migration/build/translations.json
```

- Die übersetzbaren Inhalte werden frisch **vom Entwurf** gelesen, mit aktuellen Digests, dann über
  `translationsRegister` registriert und zurückgelesen.
- Nach jeder Änderung eines Ausgangswerts erneut, sonst liefert Shopify weiter die alte Übersetzung
  aus.
- **Store-Übersetzungen nie anfassen.** Produkte, Seiten und Menüs gehören beiden Themes.

### Was ein Mensch im Entwurf tun muss

App-Embeds lassen sich nicht per Upload einschalten und von einer App nicht selbst aktivieren. Die
Skill listet aus `apps.json` jedes Embed mit `decision: keep`, das im Theme-Editor des Entwurfs unter
den App-Einbettungen eingeschaltet werden muss, und prüft danach `config/settings_data.json` des
Entwurfs. Danach die Datei ins Ziel-Repo zurückholen, damit der nächste Upload die Aktivierung nicht
überschreibt.

## Ergebnis

- Ein unveröffentlichtes Theme mit bekannter ID, Inhalt `n von n gleich`, Theme-Übersetzungen
  registriert, Live-Theme nachweislich unverändert.
- Die Testansicht als Link: `https://<domain>/?preview_theme_id=<draft-theme-id>`.
- Eine Meldung mit ID, Zahl der Dateien, Abweichungen, registrierten Übersetzungen und den
  Embeds, die ein Mensch einschalten muss.

## Fehlerbilder

- **`GuardError`:** Ziel ist nicht der Entwurf oder nicht `UNPUBLISHED`. Nichts schreiben, melden.
  Nie die Prüfung umgehen.
- **Live-Theme hat sich während des Uploads geändert:** abbrechen, melden, `sync-live-theme` anbieten.
- **20 von 20 Themes belegt:** das Team entscheidet, welches Theme gesichert und gelöscht wird. Die
  Skill löscht nie ein Theme.
- **`FILE_VALIDATION_ERROR` bei einer Section:** meist mehr als 500 Zeichen eigenes CSS oder eine
  unzulässige Einstellung. Ursache im Generator oder in der eigenen Datei beheben, neu bauen.
- **Zurückgelesene Datei weicht ab:** eine Einstellung wurde verworfen. Schema des Ziel-Blocks prüfen,
  Block-Datei vor dem Template hochladen.
- **Übersetzung wird abgelehnt oder bleibt `outdated`:** Digest vom falschen Stand. Frisch vom Entwurf
  lesen und erneut registrieren.
- **Der Admin-Weg scheitert an der Berechtigung:** die Ausnahme greift nicht. Weg `cli-theme` mit
  einem Konto mit Themes-Recht.
- **Gedrosselt:** Exit-Code prüfen, warten, erneut. Ein halbes Paket ist kein Erfolg.
