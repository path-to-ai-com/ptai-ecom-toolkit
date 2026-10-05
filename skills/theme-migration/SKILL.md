---
name: theme-migration
description: Eine Shopify-Theme-Migration von Anfang bis Nachsorge führen, ein bestehendes Theme (Vintage oder Online Store 2.0) auf ein aktuelles 2.0-Theme wie Horizon, ohne dass ein lebendes Template, eine Funktion, eine App-Einbindung, Tracking, SEO-Ausgabe oder eine Live-Änderung verloren geht. Führt durch die Phasen 0 bis 10 (Setup, Sicherung, Bestandsaufnahme, Zuordnung, Neubau, Upload, Prüfung, Abgleich, Abnahme, Launch, Nachsorge), ruft dafür die Skills snapshot-theme, inventory-theme, inventory-apps, compare-themes, map-theme, build-theme, upload-theme, verify-theme, sync-live-theme und test-round auf, hält Phasen, Gates und Theme-IDs in reporting/runs/<date>-migration/state.json, ist wiederaufnehmbar und fährt nie über eines der Gates G1 bis G5, ohne zu fragen. Veröffentlicht nie; das macht ein Mensch. Nutzen bei /ptai-ecom:theme-migration, "Theme-Migration", "Theme-Wechsel", "auf Horizon umziehen", "neues Theme ohne Verlust", "Relaunch auf neuem Theme", "wo stehen wir in der Migration", "Launch vorbereiten", "Nachsorge nach dem Launch". Nicht verwenden für ein neues Design ohne Theme-Wechsel und nicht für den Audit (ptai-ecom:audit), der vorab laufen kann. Liest reporting/config.json im Kunden-Workspace.
---

# theme-migration: die Migration führen

Ein Shop-Team hebt sein bestehendes Shopify-Theme auf ein aktuelles Online-Store-2.0-Theme, und
nichts geht dabei verloren: kein lebendes Template, keine Funktion, keine App-Einbindung, kein
Tracking, keine SEO-Ausgabe, keine Änderung, die während des Umbaus im Live-Shop passiert ist.
Bezugsziel ist die Horizon-Familie; das Verfahren gilt für jedes Quell-Theme und jedes 2.0-Ziel-Theme.

Diese Skill führt durch elf Phasen und fünf Gates. Sie ruft die Fachskills auf, hält den Stand fest
und legt an jedem Gate an, bevor es weitergeht. Selbst rechnet und baut sie nichts.

Arbeitsverzeichnis ist der Kunden-Workspace (dort liegt `reporting/`), wie bei jeder Skill dieses
Plugins. Das Ziel-Theme liegt in einem eigenen Repo daneben.

## Was immer gilt

- **Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**: jede Abfrage,
  jede Mutation, jedes Liquid, jedes Schema, jedes Flag der CLI. Nie aus dem Gedächtnis. Eine
  Migration, die aus Erinnerung baut, baut den Stand der Trainingsdaten und ist danach selbst wieder
  ein Fall für die nächste Migration. Das gilt für jede aufgerufene Skill und jeden Subagent.
- **Veröffentlichen ist immer ein Mensch.** Keine Skill ruft `themePublish`, `shopify theme publish`,
  `shopify theme push --live` oder `--publish` auf. Diese Skill bereitet vor und wartet.
- **Geschrieben wird nur in ein Theme mit der Rolle `UNPUBLISHED`**, und nur von `upload-theme`, mit
  Schutz vor jedem Schreiben. Das Live-Theme wird nie verändert.
- **Kein Gate ohne Frage.** An jedem Gate legt die Skill vor, stellt eine klare Frage und wartet auf
  eine ausdrückliche Antwort. Schweigen, ein "mach mal" zu etwas anderem oder eine Freigabe aus einem
  früheren Gate gilt nicht.
- **Genau ein Schreiber für den Stand:** diese Skill. Keine Fachskill und kein Subagent schreibt
  `state.json`.
- **Jede Aussage über den Shop trägt einen Link auf die konkrete Seite**, bei einem Unterschied beide:
  Entwurf und Live, beide mit `?preview_theme_id=<id>`. Auch der Link auf den heutigen Shop trägt seine
  ID, weil Shopify sich eine Vorschau per Cookie merkt.
- **Bilder liegen im Kundenordner**, nie im Workspace.
- **Jeder Befund wird an der Ursache behoben**, im Mapping oder in der Generator-Regel, nie nur in der
  erzeugten Datei.

## Voraussetzungen

- `reporting/config.json`, gültig nach `config.validate()`, mit dem Block `theme_migration`. Fehlt die
  Config: `setup` anbieten und aufhören. Fehlt nur der Block: in Phase 0 anlegen.
- Shopify CLI, `git`, `python3` ab 3.10, `uv` für Playwright.
- Lesezugang zum Shop (`cli-grant`, `portal` oder `staff`) und ein Schreibweg (`cli-theme` oder
  `admin-api`), beides in Phase 0 geprüft. Was der Schreibweg braucht und welche Frage offen ist, steht
  in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/access-write.md`.
- Ein Audit vorab ist optional (`audit`); er liefert Baseline und Maßnahmen-Backlog, ersetzt aber
  keine Phase hier.

Alle Checklisten und Regeln liegen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`; die Übersicht
steht in deren `README.md`.

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
  (`shopify theme pull` mit Konto). `access.write`: `cli-theme` (`shopify theme push --unpublished` mit
  Konto, bevorzugt) oder `admin-api` (`themeCreate` und `themeFilesUpsert` über `store execute`).
- `file_prefix`: Präfix für eigene Dateien im Ziel-Theme, kurz, klein, ohne Bindestrich am Ende.
- `page_sample`: `auto` heißt je lebendem Template eine Beispiel-URL, mit Search Console die
  meistbesuchte.
- Sprachen und Märkte liest die Skill aus dem Shop, nicht aus der Konfiguration.

Die Konfiguration ist die Quelle für die Skripte. Der Stand der Migration hält zusätzlich fest, welche
IDs wann galten.

## Stand der Migration

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state init
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state show
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state phase --phase <phase> --status running
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state gate --gate <gate> --decided-by "<Name>" --note "<text>"
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key <key> --value <value>
```

- Datei `reporting/runs/<date>-migration/state.json`. `init` legt sie an (Lauf-ID Standard:
  `<heute>-migration`, sonst `--run-id`), jeder andere Befehl nimmt ohne `--run-id` den jüngsten
  Migrationslauf. Jeder Aufruf gibt eine JSON-Zeile mit `next_phase`, `blocked_by`, Phasen, Gates und
  Werten aus; Exit 2 mit `{"error": ...}` heißt Fehler.
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

  `phase ... --status running` oder `done` scheitert, solange ein Gate davor offen ist. Ein Gate braucht
  den Namen der Person, die entschieden hat, nie den Namen der Skill.
- **Werte** für `set`: `live_theme_id`, `draft_theme_id`, `snapshot`, `last_sync`, `freeze_from`,
  `freeze_until`, `published_at`.

### Einstieg und Wiederaufnahme

1. `show` aufrufen. Kein Lauf: `init`, dann Phase 0. Ein Lauf: bei `next_phase` weitermachen.
2. Steht `blocked_by` auf einem Gate, ist das Gate die nächste Handlung, nicht die Phase.
3. Eine Phase mit `running` oder `failed` wird erneut betreten; was ihre Fachskill schon abgelegt hat,
   wird gelesen, nicht neu erzeugt, solange es nicht veraltet ist.
4. Zu Beginn jeder Sitzung kurz sagen, wo die Migration steht: Phase, offenes Gate, Entwurfs-ID,
   letzter Abgleich, Änderungsstopp.

## Phase 0: Setup

`phase --phase 0-setup --status running`, dann:

1. **Konfiguration:** `config.validate()` gegen `reporting/config.json`. Fehlt der Block
   `theme_migration`, mit dem Betreiber anlegen; Live-Theme-ID kommt aus der Theme-Liste, nie aus dem
   Gedächtnis.
2. **Lesezugang mit einer Probe:** Theme-Liste über den Weg aus `access.read`. Rolle, Name,
   `updatedAt` je Theme.
3. **Schreibweg mit einer Probe:** bei `cli-theme` `shopify theme list --store <shopify_store>` mit dem
   Konto; bei `admin-api` den Grant lesen, `write_themes`, `read_translations`, `write_translations`
   stehen darin. Ob die Ausnahme für den Admin-Weg greift, zeigt erst die Erstanlage nach G3.
4. **Freie Theme-Plätze:** 20 je Store, auf Plus 100. Bei voller Liste das Team bitten, ein Theme
   freizugeben, nachdem das Original gesichert ist. Nie selbst löschen.
5. **Ziel-Theme und Version:** das Ziel-Repo nach `build-theme`, Abschnitt "Ziel-Repo aufsetzen",
   gleich hier anlegen; es schreibt nichts in den Shop. Die aktuelle Version steht als Commit-Titel und
   in `theme_info.theme_version`. Ab Horizon 4.0.0 gibt es `color_palette` statt Farbschemata.
6. **Plattform-Fristen** vorab: Kundenkonten klassisch oder neu, Skript-Tags im ausgelieferten HTML,
   Reste von Shopify Scripts und Additional Scripts beim Team erfragen
   (`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/platform-deadlines.md`). Vollständig erhoben wird in
   Phase 2.
7. **GitHub-Anbindung:** ist das Live-Theme mit GitHub verbunden? Die Theme-Karte im Admin zeigt Repo
   und Branch. Dann landet jede Editor-Änderung als Commit, und das Team darf das Ziel-Repo nicht mit
   diesem Branch verwechseln.
8. **Vorlegen und fragen:** "Zugang und Ziel-Theme stehen: Lesen über ..., Schreiben über ..., Ziel
   ... in Version ..., freie Plätze ..., Fristen ... Weiter mit der Sicherung?" Erst nach einem Ja:
   `phase --phase 0-setup --status done`.

## Phase 1: Sicherung

`phase --phase 1-snapshot --status running`, dann `snapshot-theme` für das Live-Theme und mit
`--original` für die Vergleichsbasis. Danach:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key live_theme_id --value <live-theme-id>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key snapshot --value migration/snapshots/<date>-<theme-id>
```

Fertig, wenn die Sicherung vollständig und committet ist; fehlt das Original, steht das als Vermerk,
nicht als Fehler. `phase --phase 1-snapshot --status done`.

## Phase 2: Bestandsaufnahme

`phase --phase 2-inventory --status running`, dann in dieser Reihenfolge:

1. `inventory-theme`: Typ, Templates und Nutzung, Anpassungen, Funktionen, Metafelder, Übersetzungen,
   SEO-Ausgabe, Kundenkonten, `pages.json`.
2. `inventory-apps`: jede Einbindung, Tracking je Ziel, Consent, Fristen.
3. `compare-themes --measure <live-theme-id>`: Gestaltung des Live-Themes.
4. Vergleichswerte: `pull-gsc`, `pull-ga4`, `pull-cwv` in den Daten-Ordner des Migrationslaufs. Sie sind
   Ausgangsstand für die Planung; die Vergleichsbasis nach dem Launch wird direkt vor dem Launch neu
   gezogen.

Skript-Teile ohne Browser dürfen parallel laufen; was einen Browser steuert, läuft mit höchstens zwei
Browsern gleichzeitig auf der Storefront. `phase --phase 2-inventory --status done`, wenn alle Teile
vorliegen oder mit Grund als nicht lesbar stehen.

### Gate G1: Entscheidungen

Vorlage als Entscheidungsliste (`migration/inventory/decisions.md`):

- jede Zeile aus `apps.json`, auch die unstrittigen, mit Vorschlag `keep`, `replace` oder `drop`
- jede Funktion aus `functions.json` und jede Anpassung der Klasse Funktion
- die Templates: lebend, ohne Objekt (Vorschlag: entfallen), Zuweisungen ohne Datei
- die Fristen aus `risks.json`, etwa Skript-Tags und klassische Kundenkonten

Kein Host darf `unknown` sein. Frage: "Entscheidet ihr jede Zeile so oder anders?" Die Antworten
kommen mit Person und Datum nach `migration/mapping/decisions.json` (`source: G1`) und als `decision`
nach `apps.json`. Dann:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state gate --gate G1-decisions --decided-by "<Name>" --note "<kurz>"
```

## Phase 3: Zuordnung

`phase --phase 3-mapping --status running`, dann `map-theme`, einschließlich Probelauf des Generators.

### Gate G2: Zuordnung

Vorlage `migration/mapping/mapping.md`: was je Seitentyp bleibt, nachgebaut wird oder entfällt, jede
`build`-Entscheidung, jede bewusste Gestaltungsabweichung, jedes geänderte Verhalten, die verworfenen
Einstellungen aus dem Probelauf. Frage: "Ist die Zuordnung so freigegeben?" Nach dem Ja
`gate --gate G2-mapping --decided-by "<Name>"`, dann `phase --phase 3-mapping --status done`.

## Phase 4: Neubau

`phase --phase 4-build --status running`, dann `build-theme`. Fertig, wenn Theme Check, Limits und die
Prüfung der Eingriffe ohne Befund sind. `phase --phase 4-build --status done`.

### Gate G3: erster Upload

Vorlage: Name des Entwurfs, Weg (`cli-theme` oder `admin-api`), freier Platz, der Schutz vor jedem
Schreiben, dass das Live-Theme unberührt bleibt. Frage: "Darf ich den Entwurf als unveröffentlichtes
Theme anlegen?" Nach dem Ja `gate --gate G3-first-upload --decided-by "<Name>"`.

## Phase 5: Upload

`phase --phase 5-upload --status running`, dann `upload-theme`: Erstanlage, Zurücklesen,
Theme-Übersetzungen. Danach:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key draft_theme_id --value <draft-theme-id>
```

Die Embeds, die ein Mensch im Theme-Editor des Entwurfs einschalten muss, gehen als Liste an den
Betreiber. `phase --phase 5-upload --status done`.

## Phase 6: Prüfung

`phase --phase 6-verify --status running`, dann `verify-theme`.

**Phasen 4 bis 6 sind eine Schleife.** Jeder Befund geht an seine Ursache: Mapping (`map-theme`),
Generator-Regel oder eigene Datei (`build-theme`), dann `upload-theme` und die betroffenen Prüfer. Die
Phasen 4 und 5 bleiben dabei `done`; die Schleife läuft innerhalb von Phase 6. Ändert eine Korrektur
eine Entscheidung von G1 oder G2, entscheidet ein Mensch neu (neuer Eintrag in `decisions.json`, der
den alten nennt). Fertig, wenn kein Befund `blocker` mehr offen ist. `phase --phase 6-verify --status
done`.

## Phase 7: Abgleich I

`phase --phase 7-sync-1 --status running`, dann `sync-live-theme`, Abgleich I. Jede Änderung seit der
Sicherung wird entschieden (`take`, `adapt`, `drop`) und, wo übernommen, durch Neubau, Upload und die
betroffenen Prüfer geführt. Danach den Änderungsstopp vorschlagen
(`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/change-freeze.md`): Umfang, Zeitraum, Text an das Team.
Die Nachricht schickt der Betreiber.

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key last_sync --value <date>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key freeze_from --value <date>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key freeze_until --value <planned-launch-date>
```

Dieselben Daten in `theme_migration.freeze` der Konfiguration. `phase --phase 7-sync-1 --status done`.

## Phase 8: Abnahme

`phase --phase 8-acceptance --status running`, dann `verify-theme --test-round`: die Testrunde über
`test-round`, je Seitentyp und je offener Abweichung ein Testpunkt mit Linkpaar, die
Checkout-Szenarien als Punkte. Rückmeldungen werden erst nachgestellt, dann behoben, jede Korrektur an
ihrer Ursache.

### Gate G4: Abnahme

Vorlage: offene Punkte der Testrunde, jede entschiedene Abweichung ("wie heute" oder "anders"), keine
offenen Befunde `blocker` oder `before_launch`. Frage: "Nehmt ihr den Entwurf so ab?" Nach dem Ja
`gate --gate G4-acceptance --decided-by "<Name>"`, dann `phase --phase 8-acceptance --status done`.

## Phase 9: Launch

`phase --phase 9-launch --status running`. Die Checkliste steht in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/launch-checklist.md`, der Rückfall in `rollback.md`.

1. **Zeitpunkt prüfen:** nicht freitags, nicht vor Feiertagen, nicht in der Saisonspitze und den Wochen
   davor, nicht während großer Kampagnen oder laufender Preis- und A/B-Tests, Ansprechpartner auf
   beiden Seiten da.
2. **Änderungsstopp bestätigt**, Termin beim Team.
3. **Abgleich II** mit `sync-live-theme` gegen die Sicherung von Abgleich I, jede Änderung entschieden
   und im Entwurf. `set --key last_sync --value <date>`.
4. **Vergleichswerte direkt vorher:** `pull-gsc`, `pull-ga4`, `pull-cwv`, Crawl des Live-Themes,
   Conversion je Seitentyp und Gerät. Verglichen wird nach dem Launch mit diesen Werten.
5. **Go/No-Go- und Rückfallkriterien schriftlich**, mit der Person, die im Ernstfall entscheidet, dazu
   die Liste dessen, was ein Rückfall nicht zurückdreht.
6. **Rollouts als Option** vorlegen: zeitgesteuert, prozentual oder als Experiment; nicht für Vintage,
   Verfügbarkeit im Admin des Shops prüfen.

### Gate G5: Go/No-Go

Vorlage: die Go-Kriterien aus der Checkliste, je mit Stand. Frage: "Go für das Veröffentlichen am
<Datum> um <Uhrzeit>?" Nach dem Ja:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state gate --gate G5-go-live --decided-by "<Name>" --note "Rückfall-Theme <live-theme-id>"
```

7. **Schlussprüfung** von `sync-live-theme` unmittelbar vor dem Klick: `updatedAt` des Live-Themes und
   die Template-Zuweisungen. Jede Änderung seit Abgleich II hält den Launch an.
8. **Veröffentlichen durch einen Menschen** im Admin oder über Rollouts. Die Skill nennt Weg und Theme
   und wartet auf die Bestätigung, dass es geschehen ist.
9. **Prüfungen am Launch-Tag:** veröffentlichtes Theme ist das erwartete, `robots.txt`, Canonicals und
   Statuscodes der Top-Seiten, kein `noindex`, Apps und Embeds auf dem veröffentlichten Theme per
   Mitschnitt, Tracking mit einer Testbestellung **nur nach Freigabe**, jede Sprache, Sitemap neu
   einreichen.
10. **Stand festhalten:**

    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key published_at --value <timestamp>
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.run_state set --key live_theme_id --value <new-live-theme-id>
    ```

    In der Konfiguration wird `live_theme_id` die neue ID; die alte steht als Rückfall-Theme in der
    Notiz zu G5. `phase --phase 9-launch --status done`.

## Phase 10: Nachsorge

`phase --phase 10-aftercare --status running`. Der Prüfplan steht in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/post-launch.md`:

| Termin | Kern |
|---|---|
| Tag 1 | Spot-Checks, Crawl gegen den Entwurf, Umsatz, Conversion, Fehlerseiten eng beobachten |
| Woche 1 | täglich 404 und Crawl-Fehler, Rankings |
| Woche 2 | Conversion je Seitentyp und Gerät, Tracking am Datensatz |
| Woche 4 | wöchentlicher Review, erster Report gegen die Werte vor dem Launch |
| Tag 28 | Core Web Vitals im Feld |
| Woche 6 bis 12 | Erfolg der Migration bewerten |

Bei jedem Aufruf in Phase 10 nennt die Skill den nächsten fälligen Termin und was dort zu tun ist.
Geplante Änderungen an Shop-Daten aus dem Änderungsstopp werden jetzt in datierten Blöcken umgesetzt.
Das alte Theme wird erst nach der Stabilisierung und mit Freigabe des Teams gelöscht.

**Rückrichtung:** Ab dem Launch arbeitet das Team im Editor des neuen Themes. Vor jedem Generatorlauf
und vor jedem Upstream-Merge sichert `snapshot-theme` das live laufende Ziel-Theme, der Diff gegen das
Ziel-Repo zeigt die Änderungen des Teams, und sie werden übernommen, ins Repo und, wo der Generator die
Datei erzeugt, in Mapping oder Overrides. Erst dann wird generiert oder gemergt.

`phase --phase 10-aftercare --status done` erst nach der Bewertung in Woche 6 bis 12 und auf Bestätigung
des Betreibers.

## Ergebnis

Ein veröffentlichtes, updatefähiges Ziel-Theme in einem eigenen Repo; im Workspace die Sicherungen,
Inventare, Zuordnung mit allen Entscheidungen, Prüfberichte, Abgleiche und der Stand der Migration mit
jedem Gate, wer es wann entschieden hat.

## Fehlerbilder

- **`run_state` meldet ein offenes Gate:** das Gate vorlegen und fragen, nie die Phase erzwingen.
- **Beschädigte `state.json`:** das Modul legt sie absichtlich nicht still neu an, weil sonst die
  festgehaltenen Freigaben verloren gingen. Datei prüfen und reparieren, nicht löschen.
- **Kein Schreibweg:** `access-write.md` an den Betreiber, Weg 1 mit einem Konto mit Themes-Recht als
  Standard. Die Phasen 0 bis 4 laufen auch ohne Schreibweg.
- **20 von 20 Themes belegt:** das Team entscheidet, welches Theme nach Sicherung gelöscht wird.
- **Das Team hat am Live-Theme gearbeitet:** der Normalfall. `sync-live-theme` vor Befunden an einzelnen
  Dateien, vor der Abnahme und vor dem Launch.
- **Live-Theme hat sich während eines Uploads geändert:** `upload-theme` bricht ab; erst klären, dann
  weiter.
- **Korrektur nur in einer erzeugten Datei:** zurück an die Ursache, sonst dreht der nächste Lauf sie
  zurück.
- **Änderung nach Abgleich II:** der Launch hält an, bis ein Lauf die Änderung übernommen hat.
- **Jemand will veröffentlichen lassen:** die Skill veröffentlicht nicht, auch nicht auf Wunsch. Sie
  nennt den Weg im Admin.
