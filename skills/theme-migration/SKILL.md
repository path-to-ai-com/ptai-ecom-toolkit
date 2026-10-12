---
name: theme-migration
description: Führt das Team einer Marke durch die Vorbereitung einer Shopify-Theme-Migration bis "bereit für die Testrunde", von einem bestehenden Theme (Vintage oder Online Store 2.0) auf ein aktuelles 2.0-Theme wie Horizon, ohne Verlust eines zugewiesenen Templates, einer Funktion, einer App-Einbindung, des Trackings, der SEO-Ausgabe oder einer Live-Änderung. Neun feste Schritte (Shop gesichert, Abstimmung, Neubau, Entwurf hochgeladen, Kontrolle des Entwurfs, Testrunde, Abgleich vor dem Launch, Launch, Kontrolle nach dem Launch) über die Skills snapshot-theme, inventory-theme, inventory-apps, compare-themes, map-theme, build-theme, upload-theme, verify-theme, sync-live-theme und test-round. Hält den Stand in reporting/runs/<date>-migration/state.json und migration.json, führt alle offenen Punkte in einer Liste (migration/open-items.json) und die Fragen an das Team in migration/questions.json, wendet die Vorgaben der Marke an, ohne nachzufragen, und fragt nie nach Termin, Änderungsstopp oder Portal; Launch und Nachsorge macht der Betreiber mit ptai-ecom:theme-launch. Veröffentlicht nie. Nutzen bei /ptai-ecom:theme-migration, "Theme-Migration", "Theme-Wechsel", "auf Horizon umziehen", "neues Theme ohne Verlust", "wo stehen wir in der Migration", "Transkript ablegen", "Session im Repo ablegen". Nicht verwenden für ein neues Design ohne Theme-Wechsel, nicht für den Audit (ptai-ecom:audit) und nicht für Launch oder Nachsorge (ptai-ecom:theme-launch). Liest reporting/config.json im Kunden-Workspace.
---

# theme-migration: die Migration führen

Ziel: das Shopify-Theme eines Shops auf ein aktuelles Online-Store-2.0-Theme umstellen. Erhalten
bleiben jedes zugewiesene Template, jede Funktion, jede App-Einbindung, das Tracking, die SEO-Ausgabe
und jede Änderung, die während des Umbaus im Live-Shop entsteht. Referenz-Ziel ist die Horizon-Familie;
das Verfahren gilt für jedes Quell-Theme und jedes 2.0-Ziel-Theme.

- Neun feste Schritte für die Marke, darunter elf Phasen und fünf Gates des Plugins (Abschnitt "Stand
  der Migration").
- Das Team arbeitet bis "bereit für die Testrunde" und behebt danach die Befunde der Testrunde. Termin,
  Launch und Nachsorge macht der Betreiber mit `theme-launch`.
- Diese Skill ruft die Fachskills auf, schreibt den Stand und stellt die Fragen an das Team. Sie rechnet
  und baut selbst nichts.
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
- **Nie nach Termin, Änderungsstopp oder Portal fragen.** Einen Änderungsstopp gibt es nicht: das Team
  arbeitet am Live-Theme weiter, vor dem Launch wird der Stand neu gezogen. Termin, Launch, Nachsorge
  und das Veröffentlichen der Testrunde im Cockpit macht der Betreiber. Fragt die Person danach, so
  antworten und weiterarbeiten.
- **Eine Sitzung je Lauf.** `run_state` hält den Lauf für die Sitzung, die ihn zuletzt geschrieben hat
  (`session.lock`). Meldet es eine andere Sitzung, die andere schließen lassen; nur wenn sie sicher
  beendet ist, `run_state claim --force`.
- **Durchlaufen bis zur nächsten Frage.** Ein Aufruf arbeitet alle Phasen nacheinander ab, ohne
  zwischen den Phasen nachzufragen. Angehalten wird nur, wenn eine Frage an das Team offen ist, wenn eine
  Person etwas tun muss, das Claude nicht kann (Anmeldung im Browser, fehlender Zugang), oder bei einem
  Fehler, der sich nicht selbst beheben lässt.
- **Fragen an das Team nur über `questions`**, höchstens zehn je Gate, jede mit Optionen und
  Empfehlung. Was die Vorgaben der Marke oder feste Regeln entscheiden, wird nicht gefragt. Antworten
  trägt nur eine Person aus `theme_migration.people` ein; "Team", "vorläufig" oder "später" ist keine
  Antwort, die Frage bleibt offen. Claude entscheidet nie an Stelle der Person.
- **Die Vorgaben der Marke gelten als entschieden.** `migration/policies.json` legt der Betreiber ins
  Repo (`theme.policies apply`). Sie überholen frühere Entscheidungen des Laufs und öffnen keine Frage an
  das Team; ihre Folgen sind Bau- und Prüfarbeit.
- **`state.json` schreibt nur diese Skill**, keine Fachskill und kein Subagent.
- **Jede Aussage über den Shop verlinkt die betroffene Seite**, bei einem Unterschied Entwurf und Live,
  beide mit `?preview_theme_id=<id>`. Auch der Link auf den heutigen Shop enthält seine ID, weil Shopify
  eine Vorschau per Cookie speichert.
- **Bilder im Kundenordner**, nie im Workspace.
- **Jeden Befund an der Ursache beheben**, im Mapping oder in der Generator-Regel, nie nur in der
  erzeugten Datei.
- **Nach jeder abgeschlossenen Phase und jedem Gate committen und pushen**, im Workspace und, ab
  Phase 4, im Ziel-Repo, wenn ein Remote eingerichtet ist. Vorher die Transkripte ablegen (Abschnitt
  "Journal und Transkripte"). Die Person muss das nicht anstoßen. Commit-Botschaft englisch, etwa
  `migration: phase 1 snapshot done`.
- **Eine Liste offener Punkte je Migration:** `migration/open-items.json` (Abschnitt "Die Liste offener
  Punkte"). Was vor einem Gate erledigt sein muss, steht dort und nur dort, mit `open`, `done` und Beleg
  oder `deferred` mit Person und Datum. Prüfberichte, Prüfliste und Testrunde schreiben hinein, sie
  führen keinen eigenen Stand.
- **Ein Gate hält an, es fragt nicht.** `run_state gate` verweigert G1 und G2 bei offener Frage, G4 und
  G5 bei offenem Punkt ihres Gates. Erst wenn nichts mehr anhält, wird das Gate entschieden, mit dem
  Namen der Person aus `theme_migration.people`.
- **Befehle über den Starter** `"${CLAUDE_PLUGIN_ROOT}/bin/theme" <modul> ...`. Er findet Python auch
  unter Windows und setzt `PYTHONPATH` und `PYTHONUTF8` (`reference/theme-migration/windows.md`).
- **Jede Frage an das Team ins Journal**, ebenso jede Wartezeit auf einen Menschen, jede Handarbeit
  und jeden Fehler, der Zeit kostet: `run_state log`. Ohne Journal lässt sich ein Lauf nicht auswerten.

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
  "people": ["Vorname Nachname"],
  "report_paths": ["{drive_path}/projects/<projekt>"],
  "acceptance_checklist": "migration/inventory/seo-checklist.md"
}
```

- `architecture`: `os2` oder `vintage`, gesetzt nach `inventory-theme`.
- `access.read`: `cli-grant` (`shopify store execute`), `portal` (Cockpit, nur lesend), `staff`
  (`shopify theme pull` mit Konto).
- `access.write`: `cli-theme` (`shopify theme push --unpublished` mit Konto, bevorzugt) oder `admin-api`
  (`themeCreate` und `themeFilesUpsert` über `store execute`).
- `file_prefix`: Präfix eigener Dateien im Ziel-Theme; kurz, Kleinbuchstaben, kein Bindestrich am Ende.
- `people`: die Personen der Marke, die Fragen beantworten und Gates G1 bis G3 entscheiden, mit vollem
  Namen. Phase 0 fragt danach. Ein Sammelname wie "Team" gilt nicht.
- `page_sample`: `auto` bedeutet je zugewiesenem Template eine Beispiel-URL, mit Search Console die
  meistbesuchte.
- `report_paths`: Prüfberichte außerhalb des Workspace, etwa im Projektordner des Accounts. Sie sind
  Quellen für die Liste offener Punkte: ihre Punkte kommen per `open_items import` hinein, und
  `launch-check` sowie die Gates G4 und G5 halten an, solange dort etwas offen steht, das in der Liste
  fehlt.
- `acceptance_checklist`: die Prüfliste "Muss nach dem Umbau wieder da sein" aus Phase 2, Zeilen
  `- [ ] **P01** ...`. Sie ist die Abnahme der SEO-Ausgabe und steht nach Phase 2 vollständig in der
  Liste offener Punkte (Gate G4). Ohne sie schließt Phase 2 nicht ab.
- Sprachen und Märkte liest die Skill aus dem Shop, nicht aus der Konfiguration.

Die Skripte lesen die Konfiguration. Der Migrationsstand speichert zusätzlich, welche IDs wann galten.

## Stand der Migration

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state init
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state phase --phase <phase> --status running
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state gate --gate <gate> --decided-by "<Name>" --note "<text>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key <key> --value <value>
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state upgrade
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state claim --force
```

- Datei: `reporting/runs/<date>-migration/state.json`. `init` legt sie an (Lauf-ID standardmäßig
  `<heute>-migration`, sonst `--run-id`). Alle anderen Befehle nehmen ohne `--run-id` den jüngsten
  Migrationslauf.
- Nach jedem Befehl schreibt `run_state` `migration.json` neben `state.json`: die neun Schritte, die
  zwei Meilensteine, die offenen Fragen und die Vorgaben. Das Cockpit liest nur diese Datei.
- Ausgabe je Aufruf: eine JSON-Zeile mit `current_step`, `steps`, `ready_for_test_round`,
  `ready_for_launch`, `open_questions`, `next_phase`, `blocked_by`, Phasen, Gates und Werten. Exit 2 mit
  `{"error": ...}` bedeutet Fehler. `upgrade_needed` heißt: Lauf aus einer Version vor 0.3.11, zuerst
  `upgrade`.

**Die neun Schritte**, wie die Marke sie sieht:

| # | Schritt | Phasen und Gates | erledigt, wenn |
|---|---|---|---|
| 1 | Shop gesichert | `0-setup`, `1-snapshot` | beide erledigt |
| 2 | Abstimmung | `2-inventory`, G1 | Phase erledigt, G1 entschieden, keine Frage für G1 offen |
| 3 | Neubau | `3-mapping`, G2, `4-build` | Phasen erledigt, G2 entschieden, Vorgaben der Marke eingetragen und danach neu gebaut |
| 4 | Entwurf hochgeladen | G3, `5-upload` | Phase erledigt, `draft_theme_id` gesetzt |
| 5 | Kontrolle des Entwurfs | `6-verify` | Phase erledigt, alle neun Prüfer gelaufen, kein `blocker` offen |
| 6 | Testrunde | `8-test-round`, G4 | Phase erledigt, G4 entschieden (Betreiber) |
| 7 | Abgleich vor dem Launch | `7-sync`, Abgleich in `9-launch` | letzter Abgleich nach der Testrunde und höchstens sieben Tage alt |
| 8 | Launch | G5, `9-launch` | nur Betreiber |
| 9 | Kontrolle nach dem Launch | `10-aftercare` | nur Betreiber |

Stand je Schritt: `done`, `rework` (Phasen erledigt, Bedingung verletzt), `running`, `open`, dazu ein
Satz Beleg. Der aktuelle Schritt ist der erste, der nicht erledigt ist.

**Meilensteine:**

- **Bereit für die Testrunde** (nach Schritt 5): Neubau nach den Vorgaben, Entwurf hochgeladen, alle
  neun Prüfer gelaufen, kein `blocker` offen, jede veröffentlichte Nebensprache registriert.
  `phase --phase 8-test-round --status running` verweigert vorher.
- **Bereit für den Launch** (nach Schritt 7): Testrunde erledigt, kein Punkt für G4 oder G5 offen, Abgleich
  höchstens sieben Tage alt, alles gepusht.

**Phasen** `0-setup`, `1-snapshot`, `2-inventory`, `3-mapping`, `4-build`, `5-upload`, `6-verify`,
`7-sync`, `8-test-round`, `9-launch`, `10-aftercare`, Status `open`, `running`, `done`, `failed`,
`skipped`. **Gates** und die Phase, die erst danach beginnen darf:

| Gate | Entscheidung | sperrt | wer |
|---|---|---|---|
| `G1-decisions` | die Fragen der Abstimmung beantwortet | `3-mapping` | Person der Marke |
| `G2-mapping` | Zuordnung und Gestaltungsentscheidungen | `4-build` | Person der Marke |
| `G3-first-upload` | Entwurf anlegen und laufend aktualisieren, einmal in Phase 0 | `5-upload` | Person der Marke |
| `G4-acceptance` | Abnahme nach der Testrunde | `9-launch` | Betreiber mit der Person der Marke |
| `G5-go-live` | Go/No-Go | `10-aftercare` | Betreiber |

- `phase ... --status running` oder `done` scheitert, solange ein vorgelagertes Gate offen ist.
- Phasen `9-launch` und `10-aftercare`, Gates G4 und G5 und der Wert `published_at` verweigern ohne
  `PTAI_OPERATOR=1`. Das Team setzt sie nie.
- **Was die Liste offener Punkte anhält** (Exit 2 mit dem Grund, nie eine Frage):

  | Aufruf | hält an, solange |
  |---|---|
  | `phase --phase 2-inventory --status done` | die Prüfliste fehlt oder ein Punkt daraus nicht in der Liste steht |
  | `phase --phase 6-verify --status done` | ein Punkt `blocker` offen ist oder der jüngste Prüfbericht unter `migration/verify/` Offenes hält, das in der Liste fehlt |
  | `gate --gate G4-acceptance` | ein Punkt für G4 offen ist oder eine Quelle Offenes hält, das in der Liste fehlt |
  | `gate --gate G5-go-live` | ein Punkt für G4 oder G5 offen ist, oder wie bei G4 eine Quelle |

- **Werte** für `set`: `live_theme_id`, `draft_theme_id`, `snapshot`, `last_sync`, `published_at`
  (Betreiber), `policies_version` und `policies_applied_at` (schreibt `policies apply`).
- `show` nennt unter `open_items` die Zahl offener Punkte je Gate.

### Fragen an das Team

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions ask --gate <G1-decisions|G2-mapping|G4-acceptance> --text "<Frage>" --option "<A>" --option "<B>" --recommendation "<Empfehlung mit Grund>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions answer --id <Q-001> --by "<Name>" --text "<Antwort>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions list --status open
```

- Datei `migration/questions.json`. Höchstens zehn offene Fragen je Gate.
- Eine Frage ist eine Entscheidung, die nur die Marke treffen kann. Was Vorgaben oder feste Regeln
  entscheiden (toter Code, Template ohne Objekt, genutzt und unstrittig), wird nicht gefragt, sondern mit
  Regel in `decisions.json` eingetragen.
- Die offenen Fragen stehen in `migration.json` und erscheinen im Cockpit unter Offene Aufgaben. Die
  Person kann sie dort oder in der Sitzung beantworten; Claude trägt die Antwort mit ihrem Namen ein.
- Jede Frage zusätzlich als `question` ins Journal, jede Antwort als `answer`.

### Vorgaben der Marke

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies check
```

- `migration/policies.json` legt der Betreiber ins Repo (`policies apply --source <datei>`), committet
  und pusht. Format: `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/policies-format.md`.
- `apply` trägt jede Vorgabe in `decisions.json` (`source: policy`, ersetzt ältere) und `apps.json` ein,
  damit der nächste Neubau sie liest. Ein Dienst, der beibehalten werden soll und im Inventar fehlt,
  steht als `blocker` in der Liste offener Punkte.
- Eine Vorgabe mit `rule: open` hält die Vorbereitung nicht an; sie steht im Cockpit als Entscheidung des
  Betreibers.
- Nach einem `apply` steht Schritt 3 auf `rework`, bis neu gebaut ist.

### Die Liste offener Punkte

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items import --kind <checklist|report|findings|test-round> --path <datei>
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items add --title "<text>" --severity <severity> [--gate <gate>] [--owner "<Name>"] [--link <url>]
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items done --id <id> --evidence "<Beleg>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items defer --id <id> --by "<Name>" --at <JJJJ-MM-TT> --reason "<text>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items reopen --id <id> --reason "<text>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items gate --gate <gate>
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items sources
"${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items list --status open
```

- Datei `migration/open-items.json`, fest, unabhängig von der Lauf-ID; daneben die Ansicht
  `migration/open-items.md`, nach jedem Schreiben neu erzeugt, nie von Hand ändern. `run_state init`
  legt beide an.
- Je Punkt: `id`, `title`, `description`, `severity` (`blocker`, `before_launch`, `after_launch`),
  `gate` (`G4-acceptance`, `G5-go-live`, `after_launch`), `status` (`open`, `done`, `deferred`),
  `owner`, `evidence`, bei `deferred` dazu `deferred_by` und `deferred_at`, `source`, `source_ids`,
  `links`.
- `done` nur mit Beleg: was geprüft wurde, wo, mit Datum, möglichst mit Link. `deferred` nur mit der
  Person, die verschoben hat, und dem Datum der Entscheidung.
- Ohne `--gate` folgt das Gate der Schwere: `blocker` liest G4, `before_launch` G5, `after_launch` die
  Nachsorge. Prüfliste und Testrunde lesen immer G4, weil sie die Abnahme sind.
- `import` legt neue Punkte an und ergänzt bei bekannten nur Kennungen und Links. Gleich ist ein Punkt,
  wenn eine Kennung passt (`id` oder `source_ids`). Sagt die Quelle etwas anderes als die Liste, steht
  das als `drift` in der Ausgabe; die Liste gilt, eine Änderung geht über `done`, `defer` oder
  `reopen`.
- Eine Kennung ordnet nur zu, wenn sie genau einen Punkt bezeichnet. Eine Sammelkennung, die im selben
  Import an mehreren verschiedenen Punkten hängt (etwa die Prüflistenzeile LC-2.7 an sechs
  Testpunkten), oder die in der Liste mehrere Punkte kennen, ohne dass einer sie als `id` führt, legt
  nichts zusammen. Sie steht als `ambiguous` in der Ausgabe und bleibt in `source_ids` als Herkunft.
  Einen Eintrag dort prüfen: sind die Punkte wirklich verschieden, ist nichts zu tun.
- `sources` zeigt jede Quelle (Prüfliste, `report_paths`, jüngster Prüfbericht, jüngste Testrunde) mit
  allem, was dort offen steht und in der Liste fehlt. Vor jedem Gate laufen lassen.
- Ein Punkt "vor dem Launch", der nur im Gespräch, in einer Mail oder in Notion auftaucht, kommt per
  `add` in die Liste. Eine neue Liste daneben entsteht nicht.

### Journal und Transkripte

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state log --kind <kind> --text "<text>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" sessions archive
```

- `journal.jsonl` neben `state.json`. `phase`, `gate` und `set` schreiben ihr Ereignis selbst.
- `log` mit `--kind`:
  - `question`: jede Frage an das Team, im Wortlaut, auch an einem Gate
  - `answer`: die Antwort in einem Satz, mit Name
  - `wait`: Warten auf einen Menschen, etwa Anmeldung im Browser oder fehlender Zugang
  - `manual`: Arbeit, die ein Mensch statt Claude macht, mit Grund
  - `error`: ein Fehler, der einen zweiten Anlauf oder einen Umweg gekostet hat
  - `note`: alles andere, das für die Auswertung zählt, etwa wie viele Subagents parallel liefen
- `sessions archive` legt alle Claude-Sessions dieses Workspaces und seines `-horizon`-Repos
  bereinigt unter `reporting/runs/<run-id>/sessions/` ab, Subagents eingeschlossen, mit
  `index.json`. Token und Schlüssel werden vorher geschwärzt. Es läuft vor jedem Commit nach einer
  Phase oder einem Gate und auf Zuruf ("Transkript ablegen"). Danach committen und pushen:
  `migration: sessions archived`.
- Eine Session ist erst vollständig, wenn sie beendet ist. Deshalb am Ende eines Arbeitstags noch
  einmal ablegen lassen.

### Einstieg und Wiederaufnahme

1. `show` aufrufen. Kein Lauf: `init`, dann Phase 0. `upgrade_needed`: `upgrade`, dann weiter. Lauf
   vorhanden: bei `next_phase` fortsetzen.
2. Zeigt `blocked_by` ein Gate oder `open_questions` eine Zahl, zuerst die Fragen, nicht die Phase.
3. Eine Phase mit `running` oder `failed` erneut betreten. Vorhandene Ergebnisse ihrer Fachskill lesen
   statt neu erzeugen, sofern sie nicht veraltet sind.
4. Zu Beginn jeder Sitzung den Stand in Schritten nennen, etwa "Schritt 5 von 9: Kontrolle des
   Entwurfs, nacharbeiten: 3 von 9 Prüfern gelaufen", dazu offene Fragen und Entwurfs-ID mit Link.

## Phase 0: Setup

Schritt 0 läuft vor dem ersten `run_state`-Aufruf, weil es den Workspace erst herstellt.

0. **Rechner und Ordner einrichten.** Jeden Punkt prüfen und nur Fehlendes einrichten, jede
   Installation vorher in einem Satz ankündigen:
   - **Fragen gebündelt:** Alles, was Phase 0 von der Person braucht, in einer Nachricht: Shop-Adresse,
     die Namen der Personen, die entscheiden (`theme_migration.people`), Freigabe G3 ("Darf Claude einen
     unveröffentlichten Entwurf anlegen und laufend aktualisieren? Das Live-Theme bleibt unverändert.")
     und, wo nötig, die App-Liste aus Einstellungen > Apps als eingefügter Text. Danach nur noch Aktionen
     im Browser (Anmeldungen), keine Einzelfragen. Jede Frage als `question` ins Journal, sobald der Lauf
     existiert. Nach dem Ja `gate --gate G3-first-upload --decided-by "<Name>"`.
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
   - Danach `run_state init` und `phase --phase 0-setup --status running`. `init` legt auch die Liste
     offener Punkte an. Auch wenn einzelne Schritte später in getrennten Sessions laufen: jede
     Migration läuft ab der ersten Bestandsaufnahme als dieser Lauf, nie als lose Folge von
     Einzelskills.

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
6. **Plattform-Fristen** nicht erfragen: Kundenkonten, Skript-Tags, Reste von Shopify Scripts und
   Additional Scripts erhebt Phase 2 aus dem Shop
   (`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/platform-deadlines.md`). Was sich dort nicht lesen
   lässt, steht als Zeile in der Entscheidungsliste für G1.
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
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key live_theme_id --value <live-theme-id>
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key snapshot --value migration/snapshots/<date>-<theme-id>
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
5. Prüfliste in die Liste offener Punkte: Pfad in `theme_migration.acceptance_checklist` eintragen,
   dann `open_items import --kind checklist --path <prüfliste>`. Jeder Punkt liest Gate G4.

- Skript-Teile ohne Browser dürfen parallel laufen.
- Teile mit Browser: höchstens zwei Browser gleichzeitig auf der Storefront.
- `phase --phase 2-inventory --status done`, wenn alle Teile vorliegen oder mit Grund als nicht lesbar
  markiert sind. Der Aufruf scheitert, solange die Prüfliste fehlt oder nicht vollständig in der Liste
  steht.

### Gate G1: Abstimmung

Entscheidungsliste `migration/inventory/decisions.md` als vollständige Dokumentation, mit:

- jeder Zeile aus `apps.json`, auch unstrittigen, mit `keep`, `replace` oder `drop`
- jeder Funktion aus `functions.json` und jeder Anpassung der Klasse Funktion
- den Templates: zugewiesen, ohne Objekt, Zuweisungen ohne Datei
- den Fristen aus `risks.json`, etwa Skript-Tags und klassische Kundenkonten

Kein Host darf `unknown` sein. Jede Zeile trägt, woher ihre Entscheidung kommt: `policy` (Vorgabe der
Marke), `rule` mit Regel (toter Code `drop`, Template ohne Objekt `drop`, genutzt und unstrittig `keep`)
oder `question`. Nur die Zeilen `question` gehen als Fragen an das Team, höchstens zehn
(`questions ask --gate G1-decisions`). Die Liste selbst wird nicht zur Abstimmung vorgelegt.

Antworten mit Person und Datum nach `migration/mapping/decisions.json` (`source: G1`) und als
`decision` nach `apps.json`. Sind alle Fragen für G1 beantwortet:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state gate --gate G1-decisions --decided-by "<Name>" --note "<kurz>"
```

## Phase 3: Zuordnung

`phase --phase 3-mapping --status running`, dann `map-theme` einschließlich Probelauf des Generators.

### Gate G2: Zuordnung

Dokumentation `migration/mapping/mapping.md`:

- je Seitentyp, was bleibt, nachgebaut wird oder entfällt
- jede `build`-Entscheidung
- jede bewusste Gestaltungsabweichung
- jedes geänderte Verhalten
- die im Probelauf verworfenen Einstellungen

Was davon die Marke entscheiden muss, etwa ein geändertes Verhalten an Warenkorb, Filter oder Menü, geht
als Frage an das Team (`questions ask --gate G2-mapping`), höchstens zehn. Sind sie beantwortet,
`gate --gate G2-mapping --decided-by "<Name>"`, dann `phase --phase 3-mapping --status done`.

## Phase 4: Neubau

`phase --phase 4-build --status running`, dann `build-theme` mit `--apps migration/inventory/apps.json`,
damit die Entscheidungen aus G1 und die Vorgaben der Marke greifen, bei Horizon mit dem SEO-Grundpaket
(`seo-parity.md`). Abschluss: Theme Check, Limits, Prüfung der Eingriffe und `theme.horizon_base check`
ohne Befund. `phase --phase 4-build --status done`.

G3 ist in Phase 0 entschieden. Der Upload hält nur an, wenn kein Theme-Platz frei ist.

## Phase 5: Upload

`phase --phase 5-upload --status running`, dann `upload-theme`: Erstanlage, Zurücklesen,
Theme-Übersetzungen. Danach:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key draft_theme_id --value <draft-theme-id>
```

Die App-Embeds sind mit dem Upload im Entwurf. Nur ein Embed, das Shopify verworfen hat, geht als
Aufgabe an das Team. `phase --phase 5-upload --status done`.

## Phase 6: Prüfung

`phase --phase 6-verify --status running`, dann `verify-theme` mit allen neun Prüfern, je Prüfer der
feste Ordner `migration/verify/<date>/<prüfer>/`: `structure`, `content`, `seo`, `design`, `function`,
`apps_tracking`, `languages`, `performance`, `accessibility`. Schritt 5 zählt, welche davon ein
Ergebnis haben; fehlt einer, steht der Schritt auf `rework`, auch wenn das Budget knapp war. Dann den
fehlenden Prüfer in einer neuen Sitzung nachholen, nicht überspringen.

**Phasen 4 bis 6 bilden eine Schleife:**

1. Jeden Befund an seine Ursache geben: Mapping (`map-theme`), Generator-Regel oder eigene Datei
   (`build-theme`).
2. Danach `upload-theme` und die betroffenen Prüfer.
3. Phasen 4 und 5 bleiben `done`; die Schleife läuft innerhalb von Phase 6.
4. Ändert eine Korrektur eine Entscheidung aus G1 oder G2, entscheidet ein Mensch neu: neuer Eintrag in
   `decisions.json`, der den alten nennt.

`verify-theme` übernimmt jeden Prüfbericht in die Liste offener Punkte (`open_items import --kind
findings`). Ein behobener Befund wird dort mit Beleg erledigt, nicht nur im nächsten Prüfbericht
weggelassen.

Abschluss: kein Punkt `blocker` mehr offen in der Liste. `phase --phase 6-verify --status done`
scheitert sonst, ebenso, wenn der jüngste Prüfbericht Offenes hält, das in der Liste fehlt.

## Phase 7: Abgleich

`phase --phase 7-sync --status running`, dann `sync-live-theme`. Beliebig oft wiederholbar, mindestens
einmal vor der Testrunde, damit sie gegen den aktuellen Stand läuft.

1. Jede Änderung seit der letzten Sicherung entscheiden (`take`, `adapt`, `drop`).
2. Übernommene Änderungen durch Neubau, Upload und die betroffenen Prüfer führen.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key last_sync --value <date>
```

`phase --phase 7-sync --status done`. Kein Änderungsstopp: direkt vor dem Launch zieht der Betreiber
den Stand noch einmal (`theme-launch`).

## Phase 8: Testrunde

Erst wenn `show` `ready_for_test_round: true` meldet; `phase --phase 8-test-round --status running`
verweigert sonst und nennt, was fehlt. Dann `verify-theme --test-round`:

- Testrunde über `test-round` als Datei im Repo: je Seitentyp und je offener Abweichung ein Testpunkt mit
  Linkpaar, Checkout-Szenarien als Punkte
- ins Cockpit stellt sie der Betreiber; das Team testet dort
- Rückmeldungen zuerst nachstellen, dann beheben, jede Korrektur an ihrer Ursache
- jeder Testpunkt mit `status` kommt in die Liste offener Punkte (`open_items import --kind
  test-round`, Gate G4); entschieden und erledigt wird dort, danach `open_items sync-test-round --path
  <test.json>`
- was nur die Marke entscheiden kann ("wie heute oder wie Horizon"), als Frage für G4
  (`questions ask --gate G4-acceptance`)

Sind alle Punkte erledigt oder mit Person und Datum verschoben und alle Fragen beantwortet, meldet die
Skill: "Testrunde abgearbeitet. Abnahme, Termin und Launch übernimmt der Betreiber." G4 entscheidet der
Betreiber mit der Person der Marke in `theme-launch`.

## Ergebnis

- Ein Entwurf, bereit für die Testrunde, danach die abgearbeitete Testrunde.
- Im Workspace: Sicherungen, Inventare, Zuordnung mit allen Entscheidungen und ihrer Herkunft, die
  beantworteten Fragen, Prüfberichte, Abgleiche, die Liste offener Punkte mit Beleg oder Verschiebung je
  Punkt, `state.json` und `migration.json`.

## Fehlerbilder

- **`run_state` meldet ein offenes Gate oder offene Fragen:** die Fragen stellen, nie die Phase erzwingen
  und nie an Stelle der Person antworten.
- **`run_state` meldet eine andere Sitzung:** nur eine Sitzung je Lauf. Die andere schließen lassen;
  `claim --force` nur, wenn sie sicher beendet ist.
- **`upgrade_needed`:** Lauf aus einer Version vor 0.3.11. `run_state upgrade` benennt die Phasen um und
  entfernt den Änderungsstopp; danach committen.
- **Phase 9, 10, G4 oder G5 verweigert:** das ist die Regel. Die Vorbereitung endet bei "bereit für die
  Testrunde"; den Rest macht der Betreiber.
- **Jemand fragt nach Termin oder Änderungsstopp:** Termin legt der Betreiber mit der Marke fest, einen
  Stopp gibt es nicht. Antworten und weiterarbeiten.
- **`run_state` verweigert ein Gate oder einen Abschluss wegen offener Punkte:** das ist die Regel,
  kein Fehler. Punkte abarbeiten oder mit Person und Datum verschieben, nie die Liste umgehen, eine
  Quelle aus der Config nehmen oder eine Prüfliste abhaken, ohne zu prüfen.
- **Offenes steht in einer zweiten Liste** (Notizen, Notion, Mail, ein Bericht ohne Abschnitt "Vor
  dem Launch"): per `open_items add` in die eine Liste, die zweite nicht weiterführen.
- **Beschädigte `state.json`:** das Modul legt sie bewusst nicht neu an, damit die gespeicherten
  Freigaben erhalten bleiben. Datei prüfen und reparieren, nicht löschen.
- **Kein Schreibweg:** `access-write.md` an den Betreiber; Standard ist Weg 1 mit einem Konto mit
  Themes-Recht. Phasen 0 bis 4 laufen ohne Schreibweg.
- **20 von 20 Themes belegt:** das Team entscheidet, welches Theme nach Sicherung gelöscht wird.
- **Team hat am Live-Theme gearbeitet:** Normalfall. `sync-live-theme` vor Befunden an einzelnen
  Dateien und vor der Testrunde; vor dem Launch macht es der Betreiber.
- **Live-Theme während eines Uploads geändert:** `upload-theme` bricht ab; erst klären, dann fortsetzen.
- **Korrektur nur in einer erzeugten Datei:** an die Ursache zurückführen, sonst macht der nächste Lauf
  sie rückgängig.
- **Jemand bittet um Veröffentlichen:** die Skill veröffentlicht nicht, auch nicht auf Wunsch. Sie nennt
  den Weg im Admin.
