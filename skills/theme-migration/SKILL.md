---
name: theme-migration
description: Führt eine Shopify-Theme-Migration von Setup bis Nachsorge, von einem bestehenden Theme (Vintage oder Online Store 2.0) auf ein aktuelles 2.0-Theme wie Horizon, ohne Verlust eines zugewiesenen Templates, einer Funktion, einer App-Einbindung, des Trackings, der SEO-Ausgabe oder einer Live-Änderung. Phasen 0 bis 10 (Setup, Sicherung, Bestandsaufnahme, Zuordnung, Neubau, Upload, Prüfung, Abgleich, Abnahme, Launch, Nachsorge) über die Skills snapshot-theme, inventory-theme, inventory-apps, compare-themes, map-theme, build-theme, upload-theme, verify-theme, sync-live-theme, test-round und launch-check. Speichert Phasen, Gates und Theme-IDs in reporting/runs/<date>-migration/state.json, ist wiederaufnehmbar und fragt vor jedem der Gates G1 bis G5. Veröffentlicht nie; das macht ein Mensch. Nutzen bei /ptai-ecom:theme-migration, "Theme-Migration", "Theme-Wechsel", "auf Horizon umziehen", "neues Theme ohne Verlust", "Relaunch auf neuem Theme", "wo stehen wir in der Migration", "Launch vorbereiten", "Nachsorge nach dem Launch". Nicht verwenden für ein neues Design ohne Theme-Wechsel und nicht für den Audit (ptai-ecom:audit), der vorab laufen kann. Liest reporting/config.json im Kunden-Workspace.
---

# theme-migration: die Migration führen

Ziel: das Shopify-Theme eines Shops auf ein aktuelles Online-Store-2.0-Theme umstellen. Erhalten
bleiben jedes zugewiesene Template, jede Funktion, jede App-Einbindung, das Tracking, die SEO-Ausgabe
und jede Änderung, die während des Umbaus im Live-Shop entsteht. Referenz-Ziel ist die Horizon-Familie;
das Verfahren gilt für jedes Quell-Theme und jedes 2.0-Ziel-Theme.

- Elf Phasen, fünf Gates.
- Diese Skill ruft die Fachskills auf, schreibt den Stand und legt an jedem Gate vor. Sie rechnet und
  baut selbst nichts.
- Arbeitsverzeichnis: der Kunden-Workspace mit `reporting/`, wie bei jeder Skill dieses Plugins. Das
  Ziel-Theme liegt in einem eigenen Repo daneben.

## Was immer gilt

- **Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit:** Abfrage, Mutation, Liquid,
  Schema, CLI-Flag. Nie aus dem Gedächtnis, sonst entsteht ein Theme auf dem Stand der
  Trainingsdaten. Gilt für jede aufgerufene Skill und jeden Subagent.
- **Veröffentlichen macht immer ein Mensch.** Keine Skill ruft `themePublish`, `shopify theme publish`,
  `shopify theme push --live` oder `--publish` auf. Diese Skill bereitet vor und wartet.
- **Schreiben nur in ein Theme mit der Rolle `UNPUBLISHED`**, nur durch `upload-theme`, mit dem Schutz
  vor jedem Schreiben. Das Live-Theme bleibt unverändert.
- **Durchlaufen bis zum nächsten Gate.** Ein Aufruf arbeitet alle Phasen nacheinander ab, ohne
  zwischen den Phasen nachzufragen. Angehalten wird nur an den Gates G1 bis G5, wenn eine Person etwas
  tun muss, das Claude nicht kann (Anmeldung im Browser, fehlender Zugang, Testrunde), oder bei einem
  Fehler, der sich nicht selbst beheben lässt. Nach jedem Gate geht es von selbst weiter.
- **Kein Gate ohne Frage.** Vorlegen, eine klare Frage stellen, auf eine ausdrückliche Antwort warten.
  Keine Antwort sind: Schweigen, Zustimmung zu einem anderen Thema, eine Freigabe aus einem früheren
  Gate.
- **`state.json` schreibt nur diese Skill**, keine Fachskill und kein Subagent.
- **Jede Aussage über den Shop verlinkt die betroffene Seite**, bei einem Unterschied Entwurf und Live,
  beide mit `?preview_theme_id=<id>`. Auch der Link auf den heutigen Shop enthält seine ID, weil Shopify
  eine Vorschau per Cookie speichert.
- **Bilder im Kundenordner**, nie im Workspace.
- **Jeden Befund an der Ursache beheben**, im Mapping oder in der Generator-Regel, nie nur in der
  erzeugten Datei.
- **Nach jeder abgeschlossenen Phase committen und pushen**, im Workspace und, ab Phase 4, im
  Ziel-Repo, wenn ein Remote eingerichtet ist. Die Person muss das nicht anstoßen. Commit-Botschaft
  englisch, etwa `migration: phase 1 snapshot done`.

## Voraussetzungen

- Keine. Fehlt etwas (Programme, Ordner der Marke, Config, Zugang zum Shop), richtet Phase 0,
  Schritt 0 es ein. Ein Team soll nach der Installation der beiden Plugins nur diese Skill aufrufen
  müssen.
- Lesezugang (`cli-grant`, `portal` oder `staff`) und Schreibweg (`cli-theme` oder `admin-api`), beide in
  Phase 0 geprüft. Anforderungen des Schreibwegs und die offene Frage:
  `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/access-write.md`.
- Audit vorab (`audit`) ist optional. Er liefert Baseline und Maßnahmen-Backlog und ersetzt keine Phase.

Checklisten und Regeln: `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`, Übersicht in dessen
`README.md`.

## Konfiguration

```json
"theme_migration": {
  "live_theme_id": "000000000000",
  "source_theme": {"name": "", "version": "", "architecture": "os2"},
  "target_theme": {
    "name": "Horizon",
    "version": "",
    "upstream": "https://github.com/Shopify/horizon.git",
    "ref": ""
  },
  "target_repo": "../beispielshop-theme",
  "draft_theme_id": null,
  "file_prefix": "beispiel",
  "access": {"read": "cli-grant", "write": "cli-theme"},
  "page_sample": "auto",
  "freeze": {"from": null, "until": null}
}
```

- `architecture`: `os2` oder `vintage`, gesetzt nach `inventory-theme`.
- `access.read`: `cli-grant` (`shopify store execute`), `portal` (Cockpit, nur lesend), `staff`
  (`shopify theme pull` mit Konto).
- `access.write`: `cli-theme` (`shopify theme push --unpublished` mit Konto, bevorzugt) oder `admin-api`
  (`themeCreate` und `themeFilesUpsert` über `store execute`).
- `file_prefix`: Präfix eigener Dateien im Ziel-Theme; kurz, Kleinbuchstaben, kein Bindestrich am Ende.
- `page_sample`: `auto` bedeutet je zugewiesenem Template eine Beispiel-URL, mit Search Console die
  meistbesuchte.
- Sprachen und Märkte liest die Skill aus dem Shop, nicht aus der Konfiguration.

Die Skripte lesen die Konfiguration. Der Migrationsstand speichert zusätzlich, welche IDs wann galten.

## Stand der Migration

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state init
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state show
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state phase --phase <phase> --status running
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state gate --gate <gate> --decided-by "<Name>" --note "<text>"
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key <key> --value <value>
```

- Datei: `reporting/runs/<date>-migration/state.json`. `init` legt sie an (Lauf-ID standardmäßig
  `<heute>-migration`, sonst `--run-id`). Alle anderen Befehle nehmen ohne `--run-id` den jüngsten
  Migrationslauf.
- Ausgabe je Aufruf: eine JSON-Zeile mit `next_phase`, `blocked_by`, Phasen, Gates und Werten. Exit 2
  mit `{"error": ...}` bedeutet Fehler.
- **Phasen:** `0-setup`, `1-snapshot`, `2-inventory`, `3-mapping`, `4-build`, `5-upload`, `6-verify`,
  `7-sync-1`, `8-acceptance`, `9-launch`, `10-aftercare`. Status `open`, `running`, `done`, `failed`,
  `skipped`.
- **Gates** und die Phase, die erst danach beginnen darf:

  | Gate | Entscheidung | sperrt |
  |---|---|---|
  | `G1-decisions` | je App, Funktion und Template übernehmen, ersetzen oder streichen | `3-mapping` |
  | `G2-mapping` | Zuordnung und Gestaltungsentscheidungen | `4-build` |
  | `G3-first-upload` | erster Upload in den Shop | `5-upload` |
  | `G4-acceptance` | Abnahme nach der Testrunde | `9-launch` |
  | `G5-go-live` | Go/No-Go und Veröffentlichen durch einen Menschen | `10-aftercare` |

  `phase ... --status running` oder `done` scheitert, solange ein vorgelagertes Gate offen ist. Ein Gate
  braucht den Namen der Person, die entschieden hat, nie den Namen der Skill.
- **Werte** für `set`: `live_theme_id`, `draft_theme_id`, `snapshot`, `last_sync`, `freeze_from`,
  `freeze_until`, `published_at`.

### Einstieg und Wiederaufnahme

1. `show` aufrufen. Kein Lauf: `init`, dann Phase 0. Lauf vorhanden: bei `next_phase` fortsetzen.
2. Zeigt `blocked_by` ein Gate, zuerst das Gate bearbeiten, nicht die Phase.
3. Eine Phase mit `running` oder `failed` erneut betreten. Vorhandene Ergebnisse ihrer Fachskill lesen
   statt neu erzeugen, sofern sie nicht veraltet sind.
4. Zu Beginn jeder Sitzung den Stand nennen: Phase, offenes Gate, Entwurfs-ID, letzter Abgleich,
   Änderungsstopp.

## Phase 0: Setup

Schritt 0 läuft vor dem ersten `run_state`-Aufruf, weil es den Workspace erst herstellt.

0. **Rechner und Ordner einrichten.** Jeden Punkt prüfen und nur Fehlendes einrichten, jede
   Installation vorher in einem Satz ankündigen:
   - Programme: Node.js ab 22.12, Git, GitHub CLI (`gh`), Shopify CLI (`npm install -g @shopify/cli@latest`), `uv`. Fehlt
     etwas, mit dem Paketweg des Betriebssystems installieren (Mac: Homebrew, sonst offizieller
     Installer; Windows: WinGet).
   - Übermittlung an Shopify abschalten: `~/.config/shopify-ai-toolkit/opt-out` anlegen, falls nicht
     vorhanden.
   - Shop und Ordner: Liegt im Arbeitsverzeichnis schon ein Git-Repo mit `CLAUDE.md` und Shop-Adresse,
     dort weiterarbeiten. Sonst als Erstes nach der Shop-Adresse fragen: "Wie lautet die
     myshopify-Adresse eures Shops? Ihr findet sie im Shopify-Admin unter Einstellungen > Domains,
     sie endet auf .myshopify.com." Danach bei GitHub anmelden (`gh auth login` im Browser) und unter
     den Repos, auf die die Person Zugriff hat (`gh repo list` und `gh api
     user/repos?affiliation=collaborator,organization_member`), den Arbeitsordner zu diesem Shop
     suchen: ein Repo ohne Endung `-horizon`, dessen `CLAUDE.md` genau diese Adresse nennt. Gefunden:
     klonen, das zugehörige `<repo>-horizon` daneben, dort weiterarbeiten. Nicht gefunden: einen neuen
     Ordner `<shop>` als Git-Repo anlegen und die Adresse in dessen `CLAUDE.md` schreiben.
   - Config: Fehlt `reporting/config.json`, sie im Mindestumfang selbst schreiben, ohne `setup`
     aufzurufen: Shop-Adresse aus Schritt 0, Marke und Domain aus der `CLAUDE.md` des Repos oder aus dem Shop, alle
     Quellen außer Shopify unter `sources` auf `false`, `account_slug` und `drive_path` nach
     `setup`, Abschnitt Config. Dann `config.validate()`.
   - Zugang zum Shop: `shopify store auth` mit der Vereinigung der vorhandenen und der benötigten
     Scopes (`reference/theme-migration/access-write.md`), die Person bestätigt im Browser. Prüfen mit
     `shopify theme list --store <shop>`.
   - Danach `run_state init` und `phase --phase 0-setup --status running`.

1. **Konfiguration:** `config.validate()` gegen `reporting/config.json`. Fehlt der Block
   `theme_migration`, mit dem Betreiber anlegen. Live-Theme-ID aus der Theme-Liste, nie aus dem
   Gedächtnis.
2. **Lesezugang prüfen:** Theme-Liste über den Weg aus `access.read` abrufen; je Theme Rolle, Name,
   `updatedAt`.
3. **Schreibweg prüfen:** bei `cli-theme` `shopify theme list --store <shopify_store>` mit dem Konto; bei
   `admin-api` im Grant prüfen, dass `write_themes`, `read_translations`, `write_translations` enthalten
   sind. Ob die Ausnahme für den Admin-Weg greift, zeigt erst die Erstanlage nach G3.
4. **Freie Theme-Plätze:** 20 je Store, auf Plus 100. Liste voll: das Team bitten, nach Sicherung des
   Originals ein Theme freizugeben. Nie selbst löschen.
5. **Ziel-Theme und Version:** das Ziel-Repo jetzt nach `build-theme`, Abschnitt "Ziel-Repo aufsetzen",
   anlegen; dieser Schritt schreibt nichts in den Shop. Aktuelle Version: Commit-Titel und
   `theme_info.theme_version`. Ab Horizon 4.0.0 gibt es `color_palette` statt Farbschemata.
6. **Plattform-Fristen** vorab beim Team erfragen: Kundenkonten klassisch oder neu, Skript-Tags im
   ausgelieferten HTML, Reste von Shopify Scripts und Additional Scripts
   (`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/platform-deadlines.md`). Vollständige Erhebung in
   Phase 2.
7. **GitHub-Anbindung prüfen:** die Theme-Karte im Admin zeigt Repo und Branch, falls das Live-Theme mit
   GitHub verbunden ist. Dann wird jede Editor-Änderung ein Commit auf diesem Branch; das Team muss
   diesen Branch vom Ziel-Repo unterscheiden.
8. **Kurz melden und weiterarbeiten:** "Zugang und Ziel-Theme stehen: Lesen über ..., Schreiben über
   ..., Ziel ... in Version ..., freie Plätze ..., Fristen ..." Dann `phase --phase 0-setup --status
   done` und ohne Rückfrage mit Phase 1 weiter.

## Phase 1: Sicherung

`phase --phase 1-snapshot --status running`, dann `snapshot-theme` für das Live-Theme und mit
`--original` für die Vergleichsbasis. Danach:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key live_theme_id --value <live-theme-id>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key snapshot --value migration/snapshots/<date>-<theme-id>
```

Abschluss: Sicherung vollständig und committet. Ein fehlendes Original ist ein Vermerk, kein Fehler.
`phase --phase 1-snapshot --status done`.

## Phase 2: Bestandsaufnahme

`phase --phase 2-inventory --status running`, dann in dieser Reihenfolge:

1. `inventory-theme`: Typ, Templates und Nutzung, Anpassungen, Funktionen, Metafelder, Übersetzungen,
   SEO-Ausgabe, Kundenkonten, `pages.json`.
2. `inventory-apps`: jede Einbindung, Tracking je Ziel, Consent, Fristen.
3. `compare-themes --measure <live-theme-id>`: Gestaltung des Live-Themes.
4. Vergleichswerte: `pull-gsc`, `pull-ga4`, `pull-cwv` in den Daten-Ordner des Migrationslaufs. Sie
   sind der Ausgangsstand für die Planung. Die Vergleichsbasis für die Zeit nach dem Launch wird direkt
   vor dem Launch neu gezogen.

- Skript-Teile ohne Browser dürfen parallel laufen.
- Teile mit Browser: höchstens zwei Browser gleichzeitig auf der Storefront.
- `phase --phase 2-inventory --status done`, wenn alle Teile vorliegen oder mit Grund als nicht lesbar
  markiert sind.

### Gate G1: Entscheidungen

Entscheidungsliste `migration/inventory/decisions.md` mit:

- jeder Zeile aus `apps.json`, auch unstrittigen, mit Vorschlag `keep`, `replace` oder `drop`
- jeder Funktion aus `functions.json` und jeder Anpassung der Klasse Funktion
- den Templates: zugewiesen, ohne Objekt (Vorschlag: entfallen), Zuweisungen ohne Datei
- den Fristen aus `risks.json`, etwa Skript-Tags und klassische Kundenkonten

Kein Host darf `unknown` sein. Frage: "Entscheidet ihr jede Zeile so oder anders?" Antworten mit Person
und Datum nach `migration/mapping/decisions.json` (`source: G1`) und als `decision` nach `apps.json`.
Dann:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state gate --gate G1-decisions --decided-by "<Name>" --note "<kurz>"
```

## Phase 3: Zuordnung

`phase --phase 3-mapping --status running`, dann `map-theme` einschließlich Probelauf des Generators.

### Gate G2: Zuordnung

Vorlage `migration/mapping/mapping.md`:

- je Seitentyp, was bleibt, nachgebaut wird oder entfällt
- jede `build`-Entscheidung
- jede bewusste Gestaltungsabweichung
- jedes geänderte Verhalten
- die im Probelauf verworfenen Einstellungen

Frage: "Ist die Zuordnung so freigegeben?" Nach dem Ja `gate --gate G2-mapping --decided-by "<Name>"`,
dann `phase --phase 3-mapping --status done`.

## Phase 4: Neubau

`phase --phase 4-build --status running`, dann `build-theme`. Abschluss: Theme Check, Limits und Prüfung
der Eingriffe ohne Befund. `phase --phase 4-build --status done`.

### Gate G3: erster Upload

Vorlage: Name des Entwurfs, Weg (`cli-theme` oder `admin-api`), freier Platz, Schutz vor jedem
Schreiben, Bestätigung, dass das Live-Theme unverändert bleibt. Frage: "Darf ich den Entwurf als
unveröffentlichtes Theme anlegen?" Nach dem Ja `gate --gate G3-first-upload --decided-by "<Name>"`.

## Phase 5: Upload

`phase --phase 5-upload --status running`, dann `upload-theme`: Erstanlage, Zurücklesen,
Theme-Übersetzungen. Danach:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key draft_theme_id --value <draft-theme-id>
```

Die Liste der Embeds, die ein Mensch im Theme-Editor des Entwurfs einschalten muss, an den Betreiber
geben. `phase --phase 5-upload --status done`.

## Phase 6: Prüfung

`phase --phase 6-verify --status running`, dann `verify-theme`.

**Phasen 4 bis 6 bilden eine Schleife:**

1. Jeden Befund an seine Ursache geben: Mapping (`map-theme`), Generator-Regel oder eigene Datei
   (`build-theme`).
2. Danach `upload-theme` und die betroffenen Prüfer.
3. Phasen 4 und 5 bleiben `done`; die Schleife läuft innerhalb von Phase 6.
4. Ändert eine Korrektur eine Entscheidung aus G1 oder G2, entscheidet ein Mensch neu: neuer Eintrag in
   `decisions.json`, der den alten nennt.

Abschluss: kein Befund `blocker` mehr offen. `phase --phase 6-verify --status done`.

## Phase 7: Abgleich I

`phase --phase 7-sync-1 --status running`, dann `sync-live-theme`, Abgleich I.

1. Jede Änderung seit der Sicherung entscheiden (`take`, `adapt`, `drop`).
2. Übernommene Änderungen durch Neubau, Upload und die betroffenen Prüfer führen.
3. Änderungsstopp vorschlagen (`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/change-freeze.md`):
   Umfang, Zeitraum, Text an das Team. Die Nachricht schickt der Betreiber.

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key last_sync --value <date>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key freeze_from --value <date>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key freeze_until --value <planned-launch-date>
```

Dieselben Daten in `theme_migration.freeze` der Konfiguration eintragen.
`phase --phase 7-sync-1 --status done`.

## Phase 8: Abnahme

`phase --phase 8-acceptance --status running`, dann `verify-theme --test-round`:

- Testrunde über `test-round`
- je Seitentyp und je offener Abweichung ein Testpunkt mit Linkpaar
- Checkout-Szenarien als Punkte
- Rückmeldungen zuerst nachstellen, dann beheben, jede Korrektur an ihrer Ursache

### Gate G4: Abnahme

Vorlage: offene Punkte der Testrunde, jede entschiedene Abweichung ("wie heute" oder "anders"), keine
offenen Befunde `blocker` oder `before_launch`. Frage: "Nehmt ihr den Entwurf so ab?" Nach dem Ja
`gate --gate G4-acceptance --decided-by "<Name>"`, dann `phase --phase 8-acceptance --status done`.

## Phase 9: Launch

`phase --phase 9-launch --status running`. Checkliste:
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/launch-checklist.md`, Rückfall: `rollback.md`.

**Prüflauf über `launch-check`:**

- geht die Checkliste Punkt für Punkt durch und liest IDs, Abgleich, Änderungsstopp und Gates aus
  diesem Lauf
- schreibt `reporting/runs/<date>-launch-check/launch-check.md` mit Go/No-Go-Empfehlung
- läuft zu Beginn der Phase, nach jedem der Schritte 1 bis 6 erneut, bis kein Punkt mehr `missing` ist,
  und mit `--after` in Schritt 9
- der Bericht ist die Vorlage für G5

1. **Zeitpunkt prüfen:** kein Freitag, nicht vor Feiertagen, nicht in der Saisonspitze und den Wochen
   davor, nicht während großer Kampagnen oder laufender Preis- und A/B-Tests; Ansprechpartner auf
   beiden Seiten erreichbar.
2. **Änderungsstopp bestätigt**, Termin beim Team.
3. **Abgleich II** mit `sync-live-theme` gegen die Sicherung von Abgleich I; jede Änderung entschieden
   und im Entwurf. `set --key last_sync --value <date>`.
4. **Vergleichswerte direkt vorher:** `pull-gsc`, `pull-ga4`, `pull-cwv`, Crawl des Live-Themes,
   Conversion je Seitentyp und Gerät. Nach dem Launch wird gegen diese Werte verglichen.
5. **Go/No-Go- und Rückfallkriterien schriftlich**, mit der Person, die im Ernstfall entscheidet, und
   der Liste dessen, was ein Rückfall nicht rückgängig macht.
6. **Rollouts als Option vorlegen:** zeitgesteuert, prozentual oder als Experiment; nicht für Vintage;
   Verfügbarkeit im Admin des Shops prüfen.

### Gate G5: Go/No-Go

Vorlage: die Go-Kriterien aus der Checkliste, je mit Stand, aus dem jüngsten `launch-check.md`. Frage:
"Go für das Veröffentlichen am <Datum> um <Uhrzeit>?" Nach dem Ja:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state gate --gate G5-go-live --decided-by "<Name>" --note "Rückfall-Theme <live-theme-id>"
```

7. **Schlussprüfung** durch `sync-live-theme` unmittelbar vor dem Klick: `updatedAt` des Live-Themes und
   die Template-Zuweisungen. Jede Änderung seit Abgleich II stoppt den Launch.
8. **Veröffentlichen durch einen Menschen** im Admin oder über Rollouts. Die Skill nennt Weg und Theme
   und wartet auf die Bestätigung, dass veröffentlicht ist.
9. **Prüfungen am Launch-Tag** über `launch-check --after`:
   - veröffentlichtes Theme ist das erwartete
   - `robots.txt`, Canonicals und Statuscodes der Top-Seiten, kein `noindex`
   - Apps und Embeds auf dem veröffentlichten Theme per Mitschnitt
   - Tracking mit einer Testbestellung **nur nach Freigabe**
   - jede Sprache
   - Sitemap neu einreichen
10. **Stand festhalten:**

    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key published_at --value <timestamp>
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key live_theme_id --value <new-live-theme-id>
    ```

    In der Konfiguration `live_theme_id` auf die neue ID setzen; die alte steht als Rückfall-Theme in
    der Notiz zu G5. `phase --phase 9-launch --status done`.

## Phase 10: Nachsorge

`phase --phase 10-aftercare --status running`. Prüfplan:
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/post-launch.md`.

| Termin | Kern |
|---|---|
| Tag 1 | Spot-Checks, Crawl gegen den Entwurf, Umsatz, Conversion, Fehlerseiten eng beobachten |
| Woche 1 | täglich 404 und Crawl-Fehler, Rankings |
| Woche 2 | Conversion je Seitentyp und Gerät, Tracking am Datensatz |
| Woche 4 | wöchentlicher Review, erster Report gegen die Werte vor dem Launch |
| Tag 28 | Core Web Vitals im Feld |
| Woche 6 bis 12 | Erfolg der Migration bewerten |

- Bei jedem Aufruf in Phase 10 den nächsten fälligen Termin und seine Aufgaben nennen.
- Geplante Änderungen an Shop-Daten aus dem Änderungsstopp jetzt in datierten Blöcken umsetzen.
- Das alte Theme erst nach der Stabilisierung und mit Freigabe des Teams löschen.

**Rückrichtung:** Ab dem Launch arbeitet das Team im Editor des neuen Themes. Vor jedem Generatorlauf und
vor jedem Upstream-Merge:

1. `snapshot-theme` sichert das live laufende Ziel-Theme.
2. Der Diff gegen das Ziel-Repo zeigt die Änderungen des Teams.
3. Diese Änderungen übernehmen: ins Repo und, wo der Generator die Datei erzeugt, in Mapping oder
   Overrides.
4. Erst dann generieren oder mergen.

`phase --phase 10-aftercare --status done` erst nach der Bewertung in Woche 6 bis 12 und auf
Bestätigung des Betreibers.

## Ergebnis

- Ein veröffentlichtes, updatefähiges Ziel-Theme in einem eigenen Repo.
- Im Workspace: Sicherungen, Inventare, Zuordnung mit allen Entscheidungen, Prüfberichte, Abgleiche und
  der Migrationsstand mit jedem Gate, Person und Datum der Entscheidung.

## Fehlerbilder

- **`run_state` meldet ein offenes Gate:** Gate vorlegen und fragen, nie die Phase erzwingen.
- **Beschädigte `state.json`:** das Modul legt sie bewusst nicht neu an, damit die gespeicherten
  Freigaben erhalten bleiben. Datei prüfen und reparieren, nicht löschen.
- **Kein Schreibweg:** `access-write.md` an den Betreiber; Standard ist Weg 1 mit einem Konto mit
  Themes-Recht. Phasen 0 bis 4 laufen ohne Schreibweg.
- **20 von 20 Themes belegt:** das Team entscheidet, welches Theme nach Sicherung gelöscht wird.
- **Team hat am Live-Theme gearbeitet:** Normalfall. `sync-live-theme` vor Befunden an einzelnen
  Dateien, vor der Abnahme und vor dem Launch.
- **Live-Theme während eines Uploads geändert:** `upload-theme` bricht ab; erst klären, dann fortsetzen.
- **Korrektur nur in einer erzeugten Datei:** an die Ursache zurückführen, sonst macht der nächste Lauf
  sie rückgängig.
- **Änderung nach Abgleich II:** der Launch bleibt gestoppt, bis ein Lauf die Änderung übernommen hat.
- **Jemand bittet um Veröffentlichen:** die Skill veröffentlicht nicht, auch nicht auf Wunsch. Sie nennt
  den Weg im Admin.
