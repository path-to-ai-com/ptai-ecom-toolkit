---
name: theme-migration
description: Führt das Team einer Marke durch die Vorbereitung einer Shopify-Theme-Migration bis "Bereit für die Abnahme", von einem bestehenden Theme (Vintage oder Online Store 2.0) auf ein aktuelles 2.0-Theme wie Horizon, ohne Verlust eines zugewiesenen Templates, einer Funktion, einer App-Einbindung, des Trackings, der SEO-Ausgabe oder einer Live-Änderung. Neun feste Schritte (Shop gesichert, Abstimmung, Neubau, Entwurf hochgeladen, Kontrolle des Entwurfs, Abnahme, Abgleich vor dem Launch, Launch, Kontrolle nach dem Launch) über die Skills snapshot-theme, inventory-theme, inventory-apps, compare-themes, map-theme, build-theme, upload-theme, verify-theme, sync-live-theme und test-round. Hält den Stand in reporting/runs/<date>-migration/state.json und migration.json, führt alle offenen Punkte in einer Liste (migration/open-items.json) und die Fragen an das Team in migration/questions.json, holt deren Antworten beim Start aus dem Cockpit (get_migration), fragt nur bei echtem Zielkonflikt und hält alles andere als entschieden mit Herkunft fest, übernimmt beim Start die Vorgaben der Marke mit ihren Bausteinen aus dem Cockpit (get_policies, policies sync) und wendet sie an, ohne nachzufragen, baut Bausteine mit Präfix und Werten des eigenen Stores ein und holt nie Code aus einem anderen Store-Repo, und fragt nie nach Termin, Änderungsstopp oder Portal; Launch und Nachsorge macht der Betreiber mit ptai-ecom:theme-launch. Veröffentlicht nie. Nutzen bei /ptai-ecom:theme-migration, "Theme-Migration", "Theme-Wechsel", "auf Horizon umziehen", "neues Theme ohne Verlust", "wo stehen wir in der Migration", "Transkript ablegen", "Session im Repo ablegen". Nicht verwenden für ein neues Design ohne Theme-Wechsel, nicht für den Audit (ptai-ecom:audit) und nicht für Launch oder Nachsorge (ptai-ecom:theme-launch). Liest reporting/config.json im Kunden-Workspace.
---

# theme-migration: die Migration führen

Ziel: das Shopify-Theme eines Shops auf ein aktuelles Online-Store-2.0-Theme umstellen. Erhalten
bleiben jedes zugewiesene Template, jede Funktion, jede App-Einbindung, das Tracking, die SEO-Ausgabe
und jede Änderung, die während des Umbaus im Live-Shop entsteht. Referenz-Ziel ist die Horizon-Familie;
das Verfahren gilt für jedes Quell-Theme und jedes 2.0-Ziel-Theme.

- Neun feste Schritte für die Marke, darunter elf Phasen und fünf Gates des Plugins (Abschnitt "Stand
  der Migration").
- Das Team arbeitet bis "Bereit für die Abnahme" und behebt danach die Befunde der Abnahme. Termin,
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
  und das Veröffentlichen der Abnahme im Cockpit macht der Betreiber. Fragt die Person danach, so
  antworten und weiterarbeiten.
- **Eine Sitzung je Lauf.** `run_state` hält den Lauf für die Sitzung, die ihn zuletzt geschrieben hat
  (`session.lock`). Meldet es eine andere Sitzung, die andere schließen lassen; nur wenn sie sicher
  beendet ist, `run_state claim --force`.
- **Durchlaufen bis zur nächsten Frage.** Ein Aufruf arbeitet alle Phasen nacheinander ab, ohne
  zwischen den Phasen nachzufragen. Angehalten wird nur, wenn eine Frage an das Team offen ist, wenn eine
  Person etwas tun muss, das Claude nicht kann (Anmeldung im Browser, fehlender Zugang), oder bei einem
  Fehler, der sich nicht selbst beheben lässt.
- **Standard statt Frage.** Was zu entscheiden ist, entscheidet zuerst die Regel: wie heute, wie im
  Referenz-Store der Marke oder nach den Vorgaben der Marke. Gefragt wird nur bei einem echten
  Zielkonflikt, den keine Regel auflöst. Was eine Regel entscheidet, steht im Cockpit unter
  "Entscheidungen" bei "Entschieden" (`ruled add`), mit Herkunft ("Vorgabe", "Unverändert",
  "Referenz-Store", "Path to AI", "Im Shop festgestellt"); das Team kann dort "Änderung anfragen".
- **Fragen an das Team nur über `questions`**, höchstens zehn je Gate, jede mit Erklärung, Vergleich
  heute und Entwurf, wo es einen sichtbaren Unterschied gibt, und Empfehlung mit Grund (Abschnitt
  "Fragen an das Team"). Beantwortet werden sie im Cockpit; Claude stellt sie nicht in der Sitzung zur
  Antwort, sondern verweist auf das Blatt der Migration im Cockpit (Reiter "Entscheidungen", Gruppe
  "Ausstehend"). Antworten trägt nur eine Person aus `theme_migration.people` ein; "Team", "vorläufig"
  oder "später" ist keine Antwort, die Frage bleibt offen. Claude entscheidet nie an Stelle der Person.
- **Die Vorgaben der Marke gelten als entschieden.** Das Cockpit ist ihre einzige Quelle: beim Start der
  Migration holt `get_policies` die gültige Fassung, `policies sync` schreibt sie nach
  `migration/policies.json` und die Bausteine nach `migration/policy-modules/`, `policies apply` trägt sie
  in den Lauf ein. Sie überholen frühere Entscheidungen des Laufs und öffnen keine Frage an das Team; ihre
  Folgen sind Bau- und Prüfarbeit. Offene Vorgaben entscheidet die Marke im Cockpit unter Setup, Karte
  "Vorgaben der Marke", nicht in der Sitzung.
- **Nur das eigene Repo.** Gearbeitet wird im Workspace dieses Stores und seinem Ziel-Repo, dazu mit der
  Verbindung zum Cockpit. Nie Code, Vorlagen oder Dateien aus dem Repo eines anderen Stores holen, auch
  nicht aus dem Referenz-Store; was alle Stores gleich haben sollen, kommt als Baustein aus dem Cockpit.
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
  oder `deferred` mit Person und Datum. Prüfberichte, Prüfliste und Abnahme schreiben hinein, sie
  führen keinen eigenen Stand.
- **Ein Gate hält an, es fragt nicht.** `run_state gate` verweigert G1 und G2 bei offener Frage, G4 und
  G5 bei offenem Punkt ihres Gates. Erst wenn nichts mehr anhält, wird das Gate entschieden, mit dem
  Namen der Person aus `theme_migration.people`.
- **Befehle über den Starter** `"${CLAUDE_PLUGIN_ROOT}/bin/theme" <modul> ...`. Er findet Python auch
  unter Windows und setzt `PYTHONPATH` und `PYTHONUTF8` (`reference/theme-migration/windows.md`).
- **Jede Frage an das Team ins Journal**, ebenso jede Wartezeit auf einen Menschen, jede Handarbeit
  und jeden Fehler, der Zeit kostet: `run_state log`. Ohne Journal lässt sich ein Lauf nicht auswerten.

## Voraussetzungen

- Keine. Fehlt etwas (Programme, Config, Zugang zum Shop), richtet Phase 0,
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
  `- [ ] **P01** ...`. Mit ihr wird die SEO-Ausgabe abgenommen; sie steht nach Phase 2 vollständig in der
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
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state version
```

- Datei: `reporting/runs/<date>-migration/state.json`. `init` legt sie an (Lauf-ID standardmäßig
  `<heute>-migration`, sonst `--run-id`). Alle anderen Befehle nehmen ohne `--run-id` den jüngsten
  Migrationslauf.
- Nach jedem Befehl außer `version` schreibt `run_state` `migration.json` neben `state.json`: die neun
  Schritte, die zwei Meilensteine, die offenen und die beantworteten Fragen, die Punkte ohne Frage
  (`ruled`), die Übergabe der letzten Sitzung (`now`, `after`, `operator_tasks`), den Namen des
  Workspace-Repos und die Vorgaben. Das Cockpit liest nur diese Datei. Format:
  `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/questions-format.md`.
- `version` liest nur und vergleicht die Version des Plugins im Lauf mit der installierten (Abschnitt
  "Start der Migration").
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
| 6 | Abnahme | `8-test-round`, G4 | Phase erledigt, G4 entschieden (Betreiber) |
| 7 | Abgleich vor dem Launch | `7-sync`, Abgleich in `9-launch` | letzter Abgleich nach der Abnahme und höchstens sieben Tage alt |
| 8 | Launch | G5, `9-launch` | nur Betreiber |
| 9 | Kontrolle nach dem Launch | `10-aftercare` | nur Betreiber |

Stand je Schritt: `done`, `rework` (Phasen erledigt, Bedingung verletzt), `running`, `open`, dazu ein
Satz Beleg. Der aktuelle Schritt ist der erste, der nicht erledigt ist.

**Meilensteine:**

- **Bereit für die Abnahme** (nach Schritt 5): Neubau nach den Vorgaben, Entwurf hochgeladen, alle
  neun Prüfer gelaufen, kein `blocker` offen, jede veröffentlichte Nebensprache registriert.
  `phase --phase 8-test-round --status running` verweigert vorher.
- **Bereit für den Launch** (nach Schritt 7): Abnahme bewertet, Fehler behoben, kein Punkt für G4 oder G5
  offen, Abgleich höchstens sieben Tage alt, alles gepusht.

**Phasen** `0-setup`, `1-snapshot`, `2-inventory`, `3-mapping`, `4-build`, `5-upload`, `6-verify`,
`7-sync`, `8-test-round`, `9-launch`, `10-aftercare`, Status `open`, `running`, `done`, `failed`,
`skipped`. **Gates** und die Phase, die erst danach beginnen darf:

| Gate | Entscheidung | sperrt | wer |
|---|---|---|---|
| `G1-decisions` | die Fragen der Abstimmung beantwortet | `3-mapping` | Person der Marke |
| `G2-mapping` | Zuordnung und Gestaltungsentscheidungen | `4-build` | Person der Marke |
| `G3-first-upload` | Entwurf anlegen und laufend aktualisieren, einmal in Phase 0 | `5-upload` | Person der Marke |
| `G4-acceptance` | Ergebnis der Abnahme | `9-launch` | Betreiber mit der Person der Marke |
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
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions ask --gate <G1-decisions|G2-mapping|G4-acceptance> \
  --text "<Frage>" --context "<worum es geht, was schon feststeht>" \
  --option "<A>" --option "<B>" [--other "<Option mit Freitext>"] \
  --recommendation "<A>" --reason "<Grund der Empfehlung>" \
  [--compare "<Seite>" "<Link heute mit preview_theme_id>" "<Link Entwurf mit preview_theme_id>"] \
  [--decider "<Name>"]
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions ask ... --no-recommendation --reason "<worauf es bei der Entscheidung ankommt>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions withdraw --id <Q-001> --source <as_today|as_reference|policy|operator|check> --text "<was gilt>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions import --file <antworten.json>
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions answer --id <Q-001> --by "<Name>" --text "<Antwort>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" questions list --status open
"${CLAUDE_PLUGIN_ROOT}/bin/theme" ruled add --source <as_today|as_reference|policy|operator|check> --text "<was gilt>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" ruled revoke --id <R-001> --reason "<Grund, etwa die angefragte Änderung>"
```

- Dateien `migration/questions.json` und `migration/ruled.json`, Format in
  `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/questions-format.md`. Höchstens zehn offene Fragen je
  Gate.
- **Erst die Regel, dann die Frage.** Bevor eine Frage entsteht, prüfen, ob sie entschieden ist:
  - eine Vorgabe der Marke regelt sie: `ruled add --source policy`
  - der Referenz-Store der Marke (`reference_shop` der Vorgaben) hat sie gelöst und nichts spricht für
    diesen Store dagegen: `--source as_reference`. Was der Referenz-Store tut, zeigen sein Setup im
    Cockpit und sein Shop, nie sein Repo.
  - der heutige Shop tut es so, und der Entwurf kann es genauso: `--source as_today`
  - eine Prüfung im Shop hat es geklärt, etwa ein Pixel, das nichts mehr sendet: `--source check`
  - der Betreiber hat es festgelegt: `--source operator`
- Der Text eines Punkts sagt in einem Satz, was gilt, in der Sprache des Kunden, etwa "Kontaktformular
  mit Betreff, Einwilligung und Captcha wie heute". Was die Generator-Regeln ohnehin entscheiden (toter
  Code, Template ohne Objekt, genutzt und unstrittig), steht nur in `decisions.json`, nicht hier.
- **Gefragt wird nur bei echtem Zielkonflikt**: wenn "wie heute" und das Ziel-Theme oder zwei Ziele der
  Marke nicht zugleich gehen und keine Regel entscheidet. Dann immer mit
  - `--context`: worum es geht und was schon feststeht, jedes Fachwort erklärt, mit ihr und euch
  - `--compare` je betroffener Seite: Link heute und Link Entwurf, beide mit `?preview_theme_id=<id>`
  - `--option` je Antwort, `--other` für eine Antwort mit Freitext, etwa "Eine andere Person"
  - `--recommendation` mit einer der Optionen und `--reason` mit dem Grund, oder ausdrücklich
    `--no-recommendation` und in `--reason`, worauf es bei der Entscheidung ankommt
  - `--decider`, wenn nicht jede Person aus `theme_migration.people` entscheiden soll
- Ist eine gestellte Frage doch durch eine Regel entschieden, `questions withdraw` mit Herkunft und Text:
  die Frage verschwindet aus "Ausstehend", ihr Ergebnis steht unter "Entschieden" mit Herkunft und hält
  kein Gate an.
- **Beantwortet wird im Cockpit.** Neue Fragen in der Sitzung nennen und auf das Blatt der Migration im
  Cockpit verweisen (Reiter "Entscheidungen", Gruppe "Ausstehend"), nicht auf eine Antwort warten;
  danach committen und pushen. Antwortet die Person trotzdem in der Sitzung, `questions answer` wie
  bisher, mit ihrem Namen.
- Antworten aus dem Cockpit übernimmt der Start der Migration (`questions import`). Eine im Repo
  eingetragene Antwort gilt; eine spätere im Cockpit ändert sie nicht.
- Jede Frage zusätzlich als `question` ins Journal, jede Antwort als `answer`, mit Name und Herkunft
  (Cockpit oder Sitzung).

### Vorgaben der Marke

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies sync --file -
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies apply --source migration/policies.json
```

- Quelle ist das Cockpit: `get_policies` gibt die gültige Fassung der Marke zurück, die Datei des Betreibers
  plus die Antworten aus dem Setup, je Regel mit ihren Bausteinen. Format und Ausgabe:
  `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/policies-format.md`.
- `sync` schreibt `migration/policies.json` und je Baustein `migration/policy-modules/<key>/<datei>`, löscht
  dort, was die Marke gestrichen hat, und meldet Version vorher und nachher, geänderte Regeln
  (`rules_changed`) und geschriebene Bausteine (`modules_written`). Danach `apply`, committen und pushen.
- `apply` trägt jede Vorgabe in `decisions.json` (`source: policy`, ersetzt ältere) und `apps.json` ein,
  damit der nächste Neubau sie liest. Ein Dienst, der beibehalten werden soll und im Inventar fehlt,
  steht als `blocker` in der Liste offener Punkte. Dieselbe Fassung zweimal ändert nichts.
- Hat sich die Fassung oder ein Baustein geändert (`apply_needed`), steht Schritt 3 danach auf `rework`,
  bis neu gebaut ist.
- Eine Vorgabe mit `rule: open` hält die Vorbereitung nicht an; entschieden wird sie im Cockpit unter Setup
  auf der Karte "Vorgaben der Marke" ("Abweichung erlauben" oder "An <Referenz-Store> angleichen").
- Den Befehl `policies import` mit `--brand-workspace` (Antworten in `policies.json` im Ordner der Marke)
  nutzt nur der Betreiber in `theme-launch`, diese Skill nicht.

**Bausteine.** Eine Regel kann `modules` tragen: Dateien unter `migration/policy-modules/<key>/`, mit denen
jeder Store die Regel gleich umsetzt, etwa den Tag Manager als eigenen Code. Ein Baustein ist eine Vorlage
mit Beschreibung, kein fertiger Code eines Stores. Eingebaut wird er im Neubau (Phase 4), solange die Regel
`same_as_reference` heißt; bei `may_differ` bleibt der Store, wie er ist, bei `open` ist nichts entschieden.

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
  Nachsorge. Prüfliste und Testpunkte der Abnahme lesen immer G4, weil sie zur Abnahme gehören.
- `import` legt neue Punkte an und ergänzt bei bekannten nur Kennungen und Links. Gleich ist ein Punkt,
  wenn eine Kennung passt (`id` oder `source_ids`). Sagt die Quelle etwas anderes als die Liste, steht
  das als `drift` in der Ausgabe; die Liste gilt, eine Änderung geht über `done`, `defer` oder
  `reopen`.
- Eine Kennung ordnet nur zu, wenn sie genau einen Punkt bezeichnet. Eine Sammelkennung, die im selben
  Import an mehreren verschiedenen Punkten hängt (etwa die Prüflistenzeile LC-2.7 an sechs
  Testpunkten), oder die in der Liste mehrere Punkte kennen, ohne dass einer sie als `id` führt, legt
  nichts zusammen. Sie steht als `ambiguous` in der Ausgabe und bleibt in `source_ids` als Herkunft.
  Einen Eintrag dort prüfen: sind die Punkte wirklich verschieden, ist nichts zu tun.
- `sources` zeigt jede Quelle (Prüfliste, `report_paths`, jüngster Prüfbericht, jüngste Abnahme) mit
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

### Start der Migration

Jede Sitzung beginnt so, in dieser Reihenfolge und bevor irgendetwas geschrieben wird. Gibt es noch
keinen Workspace oder Lauf (erste Sitzung), entfallen die Punkte, die einen voraussetzen; dann weiter mit
Phase 0.

1. **Version prüfen:** `run_state version`. Exit 1 mit `plugin_outdated: true` heißt, der Lauf stammt
   aus einer neueren Version des Plugins als der installierten. Anhalten und sagen: "Der Lauf stammt aus
   ptai-ecom `<run_version>`, installiert ist `<installed_version>`. Bitte zuerst das Plugin
   aktualisieren und Claude Code neu starten." Nicht weiterarbeiten, auch nicht lesend an einer Phase.
2. **Neuesten Stand holen** im Workspace und im Ziel-Repo (`theme_migration.target_repo`), je:
   `git status --porcelain` muss leer sein, dann `git pull --ff-only`. Ungesicherte Änderungen oder ein Pull, der nicht vorspulen kann (Konflikt,
   abweichende Commits): anhalten und sagen, in welchem Repo und was dort steht. Nie stashen,
   zurücksetzen oder zusammenführen, ohne dass die Person es sagt. Hat der Pull den Lauf geändert,
   Schritt 1 wiederholen.
3. **Verbindung zum Cockpit prüfen:** Gibt es in dieser Sitzung das Werkzeug `get_migration` des
   Cockpits? Wenn nicht, sagen: "Claude ist nicht mit dem Cockpit verbunden. Verbindet Claude unter
   `https://portal.path-to-ai.com/<brand>/connections`, damit ich eure Antworten aus dem Cockpit lesen
   kann." `<brand>` ist `portal.brand` der Config, sonst `account_slug`. Ohne Verbindung geht es nur
   weiter, wenn keine Frage offen ist (`questions list --status open` leer); sonst anhalten, es sei
   denn, die Person beantwortet die offenen Fragen hier in der Sitzung (`questions answer`).
4. **Antworten übernehmen:** `get_migration` mit `brand` aus `portal.brand` und `shop` aus
   `portal.shop` aufrufen; fehlt einer der beiden, nennt `list_shops` des Cockpits die Slugs. Aus jeder
   Frage mit `cockpit_answer` einen Eintrag `{"id", "value", "by", "at"}` bilden und alle zusammen
   eintragen:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" questions import --file - <<'JSON'
   [{"id": "Q-004", "value": "Vor der Abnahme", "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00"}]
   JSON
   ```

   Ausgabe: `imported` und `skipped` je mit Grund, Exit 1, wenn etwas übersprungen wurde. Eine
   übersprungene Antwort bleibt offen; den Grund der Person nennen (etwa: Name nicht in
   `theme_migration.people`). Jede übernommene Antwort als `answer` ins Journal, etwa "Q-004: Vor der
   Abnahme, Erika Muster, im Cockpit". Danach `run_state show`, damit `migration.json` die Antworten
   trägt.
5. **Vorgaben der Marke übernehmen:** `get_policies` des Cockpits mit `brand` aus `portal.brand` (sonst
   `account_slug`) aufrufen und die Ausgabe unverändert an `sync` geben, danach `apply`:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" policies sync --file - <<'JSON'
   <Ausgabe von get_policies>
   JSON
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" policies apply --source migration/policies.json
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
   ```

   - Ausgabe von `sync`: `previous_version` und `version`, `rules_changed`, `modules_written`,
     `modules_removed`, `modules_missing`, `still_open`, `apply_needed`. Exit 1 heißt: ein Baustein kam ohne
     Inhalt (`modules_missing`); die übrige Fassung ist geschrieben, den Baustein als `--operator-task` in der
     Übergabe festhalten ("Baustein <name> fehlt im Cockpit") und weiterarbeiten. Jede geänderte Regel und jeden geschriebenen Baustein
     als `note` ins Journal, etwa "Vorgaben 2026-01-13.1 aus dem Cockpit: bundles may_differ ->
     same_as_reference, Baustein Tag Manager neu".
   - `apply` immer aufrufen; dieselbe Fassung ändert nichts. Bei `apply_needed` steht Schritt 3 danach auf
     nacharbeiten, bis neu gebaut ist. Eine angeglichene Regel mit App behält die App (`keep`); fehlt sie
     im Inventar dieses Stores, legt `apply` einen Punkt `blocker` zum Einbauen an, der vor der Abnahme
     erledigt sein muss.
   - Meldet `sync` `changed: true` oder `apply` `unchanged: false`: die geänderten Dateien unter `migration/`
     committen und pushen, etwa `policies: synced 2026-01-13.1 from the cockpit`.
   - `available: false`: die Marke führt keine Vorgaben im Cockpit; nichts zu tun.
   - Offen sind die Regeln aus `still_open`. Ist der eigene Store nicht der Referenz-Store
     (`reference_shop`), jede nennen und auf das Cockpit verweisen: entschieden wird unter Setup auf der
     Karte "Vorgaben der Marke", Claude übernimmt die Entscheidung beim nächsten Start. Eine offene Vorgabe
     hält die Migration nicht an.
   - Ohne Verbindung zum Cockpit (Schritt 3) oder ohne das Werkzeug `get_policies` (älteres Cockpit) gilt
     die Fassung in `migration/policies.json` weiter; nichts übernehmen und weiterarbeiten.
6. **Rückfragen und angefragte Änderungen aufgreifen:** `get_migration` liefert `cockpit_questions`
   (Rückfragen zu einer Frage) und `objections` ("Änderung anfragen" zu einem entschiedenen Punkt), je
   mit Text, Person und Zeit; `get_policies` aus Schritt 5 liefert `cockpit_questions` zu den Vorgaben.
   Jede in der Sitzung
   nennen. Eine Rückfrage hier beantworten; danach kann die Person im Cockpit oder gleich in der Sitzung
   antworten. Eine angefragte Änderung prüfen: Bleibt die Regel richtig, sagen warum. Zeigt sie, dass es
   doch ein echter Zielkonflikt ist, `ruled revoke --id <R-…> --reason "Änderung angefragt von <Name>:
   …"` und die Frage stellen.
7. **Weiterarbeiten:** Einstieg wie unten.

### Einstieg und Wiederaufnahme

1. `show` aufrufen. Kein Lauf: `init`, dann Phase 0. `upgrade_needed`: `upgrade`, dann weiter. Lauf
   vorhanden: bei `next_phase` fortsetzen.
2. Zeigt `blocked_by` ein Gate oder `open_questions` eine Zahl, zuerst die Fragen, nicht die Phase:
   offene Fragen im Cockpit beantworten lassen, und an allem weiterarbeiten, das nicht an ihrem Gate
   hängt.
3. Eine Phase mit `running` oder `failed` erneut betreten. Vorhandene Ergebnisse ihrer Fachskill lesen
   statt neu erzeugen, sofern sie nicht veraltet sind.
4. Zu Beginn jeder Sitzung den Stand in Schritten nennen, etwa "Schritt 5 von 9: Kontrolle des
   Entwurfs, nacharbeiten: 3 von 9 Prüfern gelaufen", dazu offene Fragen und Entwurfs-ID mit Link.

### Ende der Sitzung

Bevor eine Sitzung endet, auch wenn sie an einer offenen Frage anhält:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" handover write --now "<Schritt, an dem es jetzt steht>" \
  --after "<was danach passiert, für das Team>" [--operator-task "<was der Betreiber vorher tun muss>"]
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
```

- `handover write` schreibt `migration/next.json` neu: `now` für den Kopf des Blatts im Cockpit
  ("Schritt 3 von 9: <now>"), `after` für den Text unter "Migration fortsetzen", `operator_tasks` für
  das, was der Betreiber tun muss, bevor es weitergeht (ohne `--operator-task` nichts). Die Datei trägt den aktuellen Schritt; steht der Lauf später in einem anderen
  Schritt, gilt sie nicht mehr, und das Cockpit zeigt nur den Namen des Schritts.
- `after` in der Sprache des Kunden, mit ihr und euch, jedes Fachwort erklärt, etwa: "Beantwortet
  die zwei Fragen im Cockpit und startet die Migration danach neu. Claude baut den Entwurf dann um und
  prüft ihn. Findet die Prüfung nichts, was den Launch verhindert, ist er bereit für die Abnahme."
- `run_state show` danach schreibt `migration.json` mit der Übergabe neu.
- Dann Transkripte ablegen, committen und pushen (Abschnitt "Journal und Transkripte").

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
oder `question`. `question` wird eine Zeile nur bei echtem Zielkonflikt (Abschnitt "Fragen an das
Team"); was wie heute, wie im Referenz-Store oder nach einer Vorgabe entschieden ist und ohne diese Regel
eine Frage gewesen wäre, steht zusätzlich per `ruled add` unter "Entschieden". Nur die Zeilen
`question` gehen als Fragen an das Team, höchstens zehn (`questions ask --gate G1-decisions`). Die Liste
selbst wird nicht zur Abstimmung vorgelegt.

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

Ein geändertes Verhalten, etwa an Warenkorb, Filter oder Menü, wird gebaut wie heute oder wie im
Referenz-Store und per `ruled add` festgehalten. Eine Frage an das Team (`questions ask --gate
G2-mapping`, höchstens zehn) entsteht nur bei echtem Zielkonflikt, etwa wenn das Ziel-Theme das heutige
Verhalten nur mit einem Eingriff kann, der Updates erschwert. Sind die Fragen beantwortet,
`gate --gate G2-mapping --decided-by "<Name>"`, dann `phase --phase 3-mapping --status done`.

## Phase 4: Neubau

`phase --phase 4-build --status running`, dann `build-theme` mit `--apps migration/inventory/apps.json`,
damit die Entscheidungen aus G1 und die Vorgaben der Marke greifen, bei Horizon mit dem SEO-Grundpaket
(`seo-parity.md`). Abschluss: Theme Check, Limits, Prüfung der Eingriffe und `theme.horizon_base check`
ohne Befund. `phase --phase 4-build --status done`.

**Bausteine der Vorgaben einbauen.** Für jede Regel mit `rule: same_as_reference` und `modules` in
`migration/policies.json`:

1. Die `README.md` des Bausteins unter `migration/policy-modules/<key>/` lesen und jede Datei mit ihrer
   `description`. Sie sagen, was der Baustein tut, wo er ins Theme gehört und welche Werte der Store
   einsetzt.
2. Den Baustein als eigene Datei ins Ziel-Theme bauen, mit dem Präfix dieses Stores
   (`theme_migration.file_prefix`) im Dateinamen und in jedem Verweis, nie mit dem Präfix aus der Vorlage
   oder eines anderen Stores.
3. Die Werte dieses Stores einsetzen, etwa die Container-ID des Tag Managers aus dem heutigen Theme
   (`migration/inventory/`) oder aus dem Setup des Stores im Cockpit. Ist ein Wert nirgends belegt: nicht
   raten, einen Punkt `blocker` per `open_items add` anlegen und weiterbauen.
4. Jede Arbeit an Liquid und Schema über die Shopify-Skills, wie überall.
5. Im Journal festhalten, welcher Baustein mit welchen Werten eingebaut ist.

Nie Code aus dem Repo eines anderen Stores holen, auch wenn dort derselbe Baustein schon eingebaut ist.
Hat `sync` einen Baustein geschrieben oder gelöscht (`modules_written`, `modules_removed`), baut der
nächste Neubau ihn neu ein oder entfernt ihn.

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
einmal vor der Abnahme, damit sie gegen den aktuellen Stand läuft.

1. Jede Änderung seit der letzten Sicherung entscheiden (`take`, `adapt`, `drop`).
2. Übernommene Änderungen durch Neubau, Upload und die betroffenen Prüfer führen.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key last_sync --value <date>
```

`phase --phase 7-sync --status done`. Kein Änderungsstopp: direkt vor dem Launch zieht der Betreiber
den Stand noch einmal (`theme-launch`).

## Phase 8: Abnahme

Erst wenn `show` `ready_for_test_round: true` meldet; `phase --phase 8-test-round --status running`
verweigert sonst und nennt, was fehlt. Dann `verify-theme --test-round`:

- Abnahme über `test-round` als Datei im Repo: je Seitentyp und je offener Abweichung ein Testpunkt mit
  Linkpaar, Checkout-Szenarien als Punkte
- ins Cockpit stellt sie der Betreiber; das Team testet dort
- Rückmeldungen zuerst nachstellen, dann beheben, jede Korrektur an ihrer Ursache
- jeder Testpunkt mit `status` kommt in die Liste offener Punkte (`open_items import --kind
  test-round`, Gate G4); entschieden und erledigt wird dort, danach `open_items sync-test-round --path
  <test.json>`
- eine Abweichung, die die Abnahme findet, wird wie heute behoben; eine Frage für G4 (`questions ask
  --gate G4-acceptance`) nur bei echtem Zielkonflikt, mit Vergleich der beiden Seiten

Sind alle Punkte erledigt oder mit Person und Datum verschoben und alle Fragen beantwortet, meldet die
Skill: "Abnahme bewertet, Fehler behoben. Die Entscheidung über die Abnahme, Termin und Launch übernimmt
der Betreiber." G4 entscheidet der Betreiber mit der Person der Marke in `theme-launch`.

## Ergebnis

- Ein Entwurf, bereit für die Abnahme, danach die Abnahme mit bewerteten Testpunkten und behobenen Fehlern.
- Im Workspace: Sicherungen, Inventare, Zuordnung mit allen Entscheidungen und ihrer Herkunft, die
  beantworteten Fragen, die Punkte ohne Frage, Prüfberichte, Abgleiche, die Liste offener Punkte mit Beleg oder Verschiebung je
  Punkt, `state.json` und `migration.json`.

## Fehlerbilder

- **`run_state` meldet ein offenes Gate oder offene Fragen:** auf das Cockpit verweisen, die Antworten
  beim nächsten Start übernehmen (`questions import`), nie die Phase erzwingen und nie an Stelle der
  Person antworten.
- **Kein Werkzeug `get_migration`:** Claude ist nicht mit dem Cockpit verbunden. Hinweis mit dem Link aus
  "Start der Migration"; ohne Verbindung nur weiter, wenn keine Frage offen ist oder die Person in der
  Sitzung antwortet.
- **`policies sync` meldet einen Fehler** (andere Marke, Fassung ungültig, Baustein ohne Inhalt oder mit
  Pfad außerhalb seiner Regel): es ist nichts geschrieben, die Fassung im Repo gilt weiter. Den Fehler als
  `--operator-task` in der Übergabe festhalten ("Vorgaben im Cockpit prüfen: …") und weiterarbeiten.
- **Kein Werkzeug `get_policies`:** das Cockpit ist älter als dieses Plugin. Die Fassung im Repo gilt
  weiter; als `--operator-task` festhalten und weiterarbeiten.
- **Ein Wert für einen Baustein fehlt** (etwa die Container-ID): nicht raten und nicht aus einem anderen
  Store übernehmen; Punkt `blocker` in der Liste und weiterbauen.
- **`questions import` überspringt eine Antwort:** der Grund steht in `skipped`. Meist steht die Person
  nicht in `theme_migration.people`. In der Sitzung klären, ob sie für die Marke entscheidet; erst nach
  dem Ja eintragen und den Import wiederholen.
- **`run_state version` meldet ein älteres Plugin:** erst aktualisieren lassen, nicht mit der älteren
  Fassung weiterschreiben.
- **`run_state` meldet eine andere Sitzung:** nur eine Sitzung je Lauf. Die andere schließen lassen;
  `claim --force` nur, wenn sie sicher beendet ist.
- **`upgrade_needed`:** Lauf aus einer Version vor 0.3.11. `run_state upgrade` benennt die Phasen um und
  entfernt den Änderungsstopp; danach committen.
- **Phase 9, 10, G4 oder G5 verweigert:** das ist die Regel. Die Vorbereitung endet bei "bereit für die
  Abnahme"; den Rest macht der Betreiber.
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
  Dateien und vor der Abnahme; vor dem Launch macht es der Betreiber.
- **Live-Theme während eines Uploads geändert:** `upload-theme` bricht ab; erst klären, dann fortsetzen.
- **Korrektur nur in einer erzeugten Datei:** an die Ursache zurückführen, sonst macht der nächste Lauf
  sie rückgängig.
- **Jemand bittet um Veröffentlichen:** die Skill veröffentlicht nicht, auch nicht auf Wunsch. Sie nennt
  den Weg im Admin.
