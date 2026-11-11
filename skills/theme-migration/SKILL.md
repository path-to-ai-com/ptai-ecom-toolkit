---
name: theme-migration
description: Führt das Team einer Marke durch eine Shopify-Theme-Migration bis zum Launch und zur Kontrolle danach, von einem bestehenden Theme (Vintage oder Online Store 2.0) auf ein aktuelles 2.0-Theme wie Horizon, ohne Verlust eines zugewiesenen Templates, einer Funktion, einer App-Einbindung, des Trackings, der SEO-Ausgabe oder einer Live-Änderung. Neun feste Schritte (Shop gesichert, Abstimmung, Neubau, Entwurf hochgeladen, Kontrolle des Entwurfs, Abnahme, Abgleich vor dem Launch, Launch, Kontrolle nach dem Launch) über die Skills snapshot-theme, inventory-theme, inventory-apps, compare-themes, map-theme, build-theme, upload-theme, verify-theme, sync-live-theme und test-round. Hält den Stand in reporting/runs/<date>-migration/state.json und migration.json, führt alle offenen Punkte in einer Liste (migration/open-items.json) und die Fragen an das Team in migration/questions.json, holt deren Antworten beim Start aus dem Cockpit (get_migration), gibt den Stand nach jedem Push selbst ins Cockpit (report_migration), fragt nur bei echtem Zielkonflikt und hält alles andere als entschieden mit Herkunft fest, übernimmt beim Start die Vorgaben der Marke mit ihren Bausteinen aus dem Cockpit (get_policies, policies sync) und wendet sie an, ohne nachzufragen, baut Bausteine mit Präfix und Werten des eigenen Stores ein und holt nie Code aus einem anderen Store-Repo, fragt nie nach Änderungsstopp oder Portal und nach dem Termin erst, wenn der Entwurf bereit für den Launch ist; Path to AI begleitet und bekommt nur Aufgaben im Cockpit oder eine ausformulierte Frage. Führt den Launch selbst: zeigt jeden Go-Punkt als Haken-Liste, fragt nur bei allem grün "Jetzt Launch durchführen?", veröffentlicht nach dem Ja der Person der Marke mit ihrem Namen und prüft sofort danach. Nutzen bei /ptai-ecom:theme-migration, "Theme-Migration", "Theme-Wechsel", "auf Horizon umziehen", "neues Theme ohne Verlust", "wo stehen wir in der Migration", "Transkript ablegen", "Session im Repo ablegen". Nicht verwenden für ein neues Design ohne Theme-Wechsel, nicht für den Audit (ptai-ecom:audit). Liest reporting/config.json im Kunden-Workspace.
---

# theme-migration: die Migration führen

Ziel: das Shopify-Theme eines Shops auf ein aktuelles Online-Store-2.0-Theme umstellen. Erhalten
bleiben jedes zugewiesene Template, jede Funktion, jede App-Einbindung, das Tracking, die SEO-Ausgabe
und jede Änderung, die während des Umbaus im Live-Shop entsteht. Referenz-Ziel ist die Horizon-Familie;
das Verfahren gilt für jedes Quell-Theme und jedes 2.0-Ziel-Theme.

- Neun feste Schritte für die Marke, darunter elf Phasen und fünf Gates des Plugins (Abschnitt "Stand
  der Migration").
- Das Team führt die Migration bis zum Launch und zur Kontrolle danach, in seiner eigenen Sitzung. Path
  to AI begleitet: beantwortet Fragen, stellt die Abnahme ins Cockpit, entscheidet Abnahme und Go-Live mit
  der Person der Marke. Shop-Zugang hat nur das Team; Path to AI arbeitet nie im Shop und nie im Repo
  des Stores.
- Diese Skill ruft die Fachskills auf, schreibt den Stand und stellt die Fragen an das Team. Sie rechnet
  und baut selbst nichts.
- Arbeitsverzeichnis: der Kunden-Workspace mit `reporting/`, wie bei jeder Skill dieses Plugins. Das
  Ziel-Theme liegt in einem eigenen Repo daneben.

## Was immer gilt

- **Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit:** Abfrage, Mutation, Liquid,
  Schema, CLI-Flag. Nie aus dem Gedächtnis, sonst entsteht ein Theme auf dem Stand der
  Trainingsdaten. Gilt für jede aufgerufene Skill und jeden Subagent.
- **Veröffentlicht wird nur im geführten Launch (Phase 9), nach dem ausdrücklichen Ja der Person der
  Marke.** Einziger Weg ist `bin/theme launch publish --approved-by "<Name>"`; er fragt nicht selbst,
  sondern verweigert, solange die Haken-Liste nicht grün ist. Keine Skill ruft `themePublish`,
  `shopify theme push --live` oder `--publish` auf, und `shopify theme publish` läuft nur in diesem
  Modul. Seit 10.11.2026; bis dahin veröffentlichte immer ein Mensch im Admin.
- **Schreiben nur in ein Theme mit der Rolle `UNPUBLISHED`**, nur durch `upload-theme`, mit dem Schutz
  vor jedem Schreiben. Das Live-Theme bleibt unverändert.
- **Nie nach Termin, Änderungsstopp oder Portal fragen.** Einen Änderungsstopp gibt es nicht: das Team
  arbeitet am Live-Theme weiter, vor dem Launch wird der Stand neu gezogen. Den Termin legt das Team
  fest, wenn der Entwurf bereit für den Launch ist (Phase 9); vorher fragt die Skill nicht danach. Die
  Abnahme stellt Path to AI ins Cockpit. Fragt die Person danach, so antworten und weiterarbeiten.
- **Eine Sitzung je Lauf.** `run_state` hält den Lauf für die Sitzung, die ihn zuletzt geschrieben hat
  (`session.lock`). Meldet es eine andere Sitzung, die andere schließen lassen; nur wenn sie sicher
  beendet ist, `run_state claim --force`.
- **Durchlaufen bis zur nächsten Frage.** Ein Aufruf arbeitet alle Phasen nacheinander ab, ohne
  zwischen den Phasen nachzufragen. Angehalten wird nur, wenn eine Frage an das Team offen ist, wenn eine
  Person etwas tun muss, das Claude nicht kann (Anmeldung im Browser, fehlender Zugang), oder bei einem
  Fehler, der sich nicht selbst beheben lässt.
- **Nie fragen, ob die Skill ihren eigenen nächsten Schritt machen soll.** Nachmessen, Abgleichen,
  Registrieren, Hochladen, Prüfen: Die Reihenfolge steht in dieser Skill, die Sitzung macht es einfach.
  Eine Frage an die Person gibt es nur, wenn sie etwas entscheiden kann, das ihren Shop betrifft, oder
  wenn sie etwas tun muss. Belegt am 03.11.2026: "Soll ich die zehn Testpunkte jetzt im Entwurf
  nachmessen?" mit der Alternative "Erst Abgleich" und "Soll ich access.write auf admin-api umstellen?".
  Beide Male konnte die Person das nicht beurteilen und fragte Path to AI, die Sitzung stand.
- **Jede Frage und jede Zusammenfassung in den Worten des Teams.** Keine Konfigurationsschlüssel, Theme-IDs,
  Dateinamen, Digests oder Befehle in der Frage und in den Knöpfen; was gemeint ist, beschreiben ("die
  englischen Texte im neuen Theme eintragen", nicht "161 Übersetzungen registrieren"). Technische Belege
  gehören ins Journal und in den Commit, nicht in die Frage.
- **Standard statt Frage.** Was zu entscheiden ist, entscheidet zuerst die Regel: wie heute, wie im
  Referenz-Store der Marke oder nach den Vorgaben der Marke. Gefragt wird nur bei einem echten
  Zielkonflikt, den keine Regel auflöst. Was eine Regel entscheidet, steht im Cockpit unter
  "Entscheidungen" bei "Entschieden" (`ruled add`), mit Herkunft ("Vorgabe", "Unverändert",
  "Referenz-Store", "Path to AI", "Im Shop festgestellt"); das Team kann dort "Änderung anfragen".
- **Fragen an das Team nur über `questions`**, höchstens zehn je Gate, jede mit Erklärung, Vergleich
  heute und Entwurf, wo es einen sichtbaren Unterschied gibt, und Empfehlung mit Grund (Abschnitt
  "Fragen an das Team"). Beantwortet werden sie im Cockpit; Claude stellt sie nicht in der Sitzung zur
  Antwort, sondern verweist auf das Blatt der Migration im Cockpit (Reiter "Entscheidungen", Gruppe
  "Ausstehend"). In der Sitzung trägt nur eine Person aus `theme_migration.people` eine Antwort ein; im
  Cockpit antworten die Mitglieder der Marke und Path to AI, und jede dieser Antworten gilt. "Team",
  "vorläufig" oder "später" ist keine Antwort, die Frage bleibt offen. Claude entscheidet nie an Stelle der
  Person.
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
- **Nach jedem Push den Stand ins Cockpit geben** (`report_migration`, Abschnitt "Stand im Cockpit"),
  auch nach einer neuen Frage und am Ende der Sitzung. Erst dann sieht das Team im Cockpit, was die Sitzung
  geändert hat; ohne Meldung zeigt das Cockpit den letzten Stand, den Path to AI hochgeladen hat.
- **Ins Cockpit nur nach bestätigter Meldung.** Auf das Cockpit verweisen ("steht im Cockpit", "beantwortet
  im Cockpit") nur, wenn `report_migration` in dieser Sitzung nach dem letzten Push `reported: true`
  zurückgegeben hat, und dann mit dem Link aus `sheet`. Sonst stehen neue Fragen dort nicht, und die
  Person sucht sie vergeblich. Ohne bestätigte Meldung die offenen Fragen in der Sitzung stellen
  (Abschnitt "Stand im Cockpit").
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
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state cockpit
```

- Datei: `reporting/runs/<date>-migration/state.json`. `init` legt sie an (Lauf-ID standardmäßig
  `<heute>-migration`, sonst `--run-id`). Alle anderen Befehle nehmen ohne `--run-id` den jüngsten
  Migrationslauf.
- Nach jedem Befehl außer `version` und `cockpit` schreibt `run_state` `migration.json` neben `state.json`: die neun
  Schritte, die zwei Meilensteine, die offenen und die beantworteten Fragen, die Punkte ohne Frage
  (`ruled`), die Übergabe der letzten Sitzung (`now`, `after`, `operator_tasks`), den Namen des
  Workspace-Repos und die Vorgaben. Das Cockpit liest nur diese Datei; dorthin kommt sie mit
  `report_migration` (Abschnitt "Stand im Cockpit"). Format:
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
| 6 | Abnahme | `8-test-round`, G4 | Phase erledigt, G4 entschieden (Person der Marke) |
| 7 | Abgleich vor dem Launch | `7-sync`, Abgleich in `9-launch` | letzter Abgleich nach der Abnahme und höchstens sieben Tage alt |
| 8 | Launch | G5, `9-launch` | G5 entschieden, veröffentlicht, Prüfungen am Launch-Tag |
| 9 | Kontrolle nach dem Launch | `10-aftercare` | Bewertung in Woche 6 bis 12, nichts offen |

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
| `G4-acceptance` | Ergebnis der Abnahme | `9-launch` | Person der Marke, nach Abstimmung mit Path to AI |
| `G5-go-live` | Go/No-Go | `10-aftercare` | Person der Marke, nach Abstimmung mit Path to AI |

- `phase ... --status running` oder `done` scheitert, solange ein vorgelagertes Gate offen ist.
- Seit 0.3.27 setzt das Team auch G4, G5, die Phasen `9-launch` und `10-aftercare` und `published_at`.
  Bis 0.3.26 brauchten sie `PTAI_OPERATOR=1`; ohne Shop-Zugang konnte Path to AI sie nie ausführen, und
  jeder Lauf blieb dort stehen.
- **Was die Liste offener Punkte anhält** (Exit 2 mit dem Grund, nie eine Frage):

  | Aufruf | hält an, solange |
  |---|---|
  | `phase --phase 2-inventory --status done` | die Prüfliste fehlt oder ein Punkt daraus nicht in der Liste steht |
  | `phase --phase 6-verify --status done` | ein Punkt `blocker` offen ist oder der jüngste Prüfbericht unter `migration/verify/` Offenes hält, das in der Liste fehlt |
  | `gate --gate G4-acceptance` | ein Punkt für G4 offen ist, eine Quelle Offenes hält, das in der Liste fehlt, ein Testpunkt ohne Bilder vom Entwurf erledigt ist, der Bildvergleich unvollständig ist (`visual_compare check`, am Handy auch mit Menü offen) oder die Datenschicht je GA4-Property am Handy mit langsamer Verbindung nicht belegt ist oder etwas verliert |
  | `gate --gate G5-go-live` | ein Punkt für G4 oder G5 offen ist, oder wie bei G4 eine Quelle |

- **Werte** für `set`: `live_theme_id`, `draft_theme_id`, `snapshot`, `last_sync`, `published_at`, `policies_version` und `policies_applied_at` (schreibt `policies apply`).
- `show` nennt unter `open_items` die Zahl offener Punkte je Gate.

### Stand im Cockpit

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state cockpit
```

- `cockpit` liest nur und gibt die Eingabe für das Werkzeug `report_migration` des Cockpits aus: `brand`
  (`portal.brand`, sonst `account_slug`), `shop` (`portal.shop`), `run_id` und `migration`, den Inhalt von
  `migration.json` des Laufs. Die Ausgabe unverändert an `report_migration` geben; nichts davon von Hand
  zusammensetzen.
- Seit 10.11.2026 trägt `migration.json` den Block `launch`: die Go-Liste aus dem jüngsten `launch check`
  (vor und nach dem Veröffentlichen), den Ablauf des Launches und den Rückfall aus
  `migration/rollback.json` (Modul `launch_status`).
- Gemeldet wird nach jedem Push des Workspace: nach jeder Phase und jedem Gate, nach jeder neuen Frage, bevor
  die Skill das Team ins Cockpit schickt, beim Start nach dem Übernehmen von Antworten und Vorgaben und am
  Ende der Sitzung. Vorher `run_state show`, damit `migration.json` den Stand trägt.
- Antwort: `reported`, `new_run` (ein neuer Lauf steht jetzt im Cockpit), `open_questions` (Fragen, die weder
  im Repo noch im Cockpit beantwortet sind) und `sheet`, der Link auf das Blatt der Migration. Den Link nennen,
  wenn die Skill auf das Cockpit verweist.
- `deciders_without_access` (seit Cockpit vom 16.10.2026): Personen aus `decider` einer offenen Frage, die im
  Cockpit keinen passenden Namen haben und dort keine Antwortmöglichkeiten sehen. Ist die Liste nicht leer,
  diese Fragen in der Sitzung stellen wie ohne Meldung (unten), die Namen in der Übergabe als
  `--operator-task` nennen ("Namen im Cockpit eintragen: <Name>") und sie nicht ins Cockpit schicken.
- Ohne Verbindung zum Cockpit, ohne das Werkzeug `report_migration` oder wenn das Cockpit die Meldung
  ablehnt, ist der Stand dieser Sitzung nicht im Cockpit. Dann:
  - nie auf das Cockpit verweisen, auch nicht für Fragen, die die Sitzung gestellt hat;
  - einmal je Sitzung sagen: "Das Cockpit zeigt den Stand dieser Sitzung noch nicht. Die offenen Fragen
    stelle ich euch deshalb hier." Fehlt nur das Werkzeug, obwohl Claude verbunden ist, dazu: "Startet für
    die nächste Migration eine neue Sitzung, dann meldet Claude den Stand wieder selbst.";
  - jede offene Frage (`questions list --status open`), deren `decider` die Person nennt oder die keinen
    `decider` hat, in der Sitzung stellen: Frage, worum es geht, Optionen, Empfehlung mit Grund, die
    Vergleichslinks. Die Antwort mit `questions answer` und dem Namen der Person eintragen, committen,
    pushen. Fragen für eine andere Person nennen und sagen, dass sie die Frage in ihrer nächsten Sitzung
    beantwortet;
  - `run_state log --kind error --text "Stand nicht im Cockpit: <Grund>"`, damit Path to AI es im Repo sieht.
  Der Start der nächsten Sitzung mit Verbindung meldet den Stand.
- Lehnt das Cockpit ab:
  - "newer state": Ein anderer Stand dieses Laufs ist jünger, meist aus einer anderen Sitzung. `git pull
    --ff-only` im Workspace, `run_state show`, noch einmal melden. Hilft das nicht, den Grund nennen.
  - "changed while reporting": noch einmal melden.
  - jeder andere Grund (Format, Store, älterer Lauf): nicht wiederholen, den Grund nennen und als `error` ins
    Journal.

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
- **Beantwortet wird im Cockpit, wenn die Fragen dort stehen.** Neue Fragen in der Sitzung nennen,
  committen, pushen und melden (`report_migration`). Erst nach `reported: true` auf das Blatt der
  Migration im Cockpit verweisen (Reiter "Entscheidungen", Gruppe "Ausstehend"), mit dem Link aus `sheet`;
  nicht auf eine Antwort warten. Ohne bestätigte Meldung die Fragen hier stellen (Abschnitt "Stand im
  Cockpit"). Antwortet die Person trotzdem in der Sitzung, `questions answer` wie
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
  steht als Punkt vor dem Launch in der Liste offener Punkte, nie als Blocker der Abnahme. Dieselbe Fassung
  zweimal ändert nichts.
- **Apps, die der Store heute nicht hat.** Es gilt: Was der Store heute hat, bekommt er mit derselben App
  wie der Referenz-Store; was er heute nicht hat, kommt nicht dazu. Nennt `apply` solche Punkte
  (`open_items_added` mit `POLICY-`), fragt die Skill die Person einmal für alle zusammen, nicht je App:
  "Diese Apps hat <Store> heute nicht: <Liste mit einem Halbsatz, was jede tut>. Sie kommen nicht dazu,
  außer der Store bietet die Funktion heute schon anders an, etwa über eigene Felder. Trifft das auf eine
  davon zu?" Für jede App ohne die Funktion `ruled add --source policy --text "<App> kommt in <Store>
  nicht dazu, der Store hat die Funktion heute nicht (<Person>, <Datum>)"` und den Punkt schließen. Für
  eine App mit Funktion bleibt der Punkt vor dem Launch, mit der Person als `--owner`, die sie installiert.
  Die Frage hält nichts an: Antwortet niemand, bleibt der Punkt vor dem Launch stehen.
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
- Ein Punkt "vor dem Launch", der nur im Gespräch, in einer Mail oder in einer Notiz auftaucht, kommt per
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
   Frage mit `cockpit_answer` einen Eintrag `{"id", "value", "by", "at", "role"}` bilden (`role` nur, wenn
   das Cockpit es angibt) und alle zusammen eintragen:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" questions import --file - <<'JSON'
   [{"id": "Q-004", "value": "Vor der Abnahme", "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00"}]
   JSON
   ```

   Ausgabe: `imported` und `skipped` je mit Grund, Exit 1, wenn etwas übersprungen wurde. Eine
   übersprungene Antwort bleibt offen; den Grund der Person nennen (etwa: Sammelname statt einer Person).
   Eine Antwort von Path to AI (`role: operator`) gilt wie die der Marke; im Journal steht sie mit dem
   Kennzeichen, etwa "Q-002: Vor der Abnahme, Pat Betreiber (Path to AI), im Cockpit". Jede übernommene Antwort als `answer` ins Journal, etwa "Q-004: Vor der
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
   - Trägt eine entschiedene Regel unter `needs` einen Eintrag für diesen Store (`portal.shop` in `shops`),
     ihn der Person nennen und als Punkt per `open_items add` mit `--owner` aus `theme_migration.people`
     anlegen, wenn er dort noch fehlt: Das muss das Team selbst liefern, etwa ein Konto oder eine Kennung.
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
7. **Stand melden:** Haben Schritt 4 oder 5 etwas geändert, committen und pushen. Dann den Stand ins Cockpit
   geben (`run_state cockpit`, `report_migration`, Abschnitt "Stand im Cockpit"), auch wenn sich nichts
   geändert hat: So steht der Stand einer früheren Sitzung ohne Verbindung spätestens jetzt im Cockpit.
8. **Weiterarbeiten:** Einstieg wie unten.

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
  --after "<was danach passiert, für das Team>" [--operator-task "<was Path to AI vorher tun muss>"]
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
```

- `handover write` schreibt `migration/next.json` neu: `now` für den Kopf des Blatts im Cockpit
  ("Schritt 3 von 9: <now>"), `after` für den Text unter "Migration fortsetzen", `operator_tasks` für
  das, was Path to AI tun muss, bevor es weitergeht (ohne `--operator-task` nichts). Mit einer Aufgabe
  steht im Cockpit "Zuständig: Path to AI".
- **Path to AI hat keinen Shop-Zugang und arbeitet nicht im Repo des Stores.** `--operator-task` gibt es
  deshalb nur für drei Dinge:
  - etwas im Cockpit: eine Vorgabe entscheiden oder ändern, einen Baustein bereitstellen, die Abnahme
    ins Cockpit stellen ("Abnahme vom <Datum> ins Cockpit stellen, Datei <Pfad>, gepusht");
  - eine Frage an Path to AI, die das Team mit der Skill nicht lösen kann (unten);
  - die gemeinsame Entscheidung über G4 oder G5 ("Abnahme mit <Person> besprechen").
  Alles, was im Shop, im Theme, im Admin oder in einer App passiert, ist nie eine Aufgabe von Path to AI,
  auch wenn das Team einen Zugang erst beschaffen muss: Übersetzungen registrieren, einen Pixel entfernen,
  CookieFirst einbauen, eine App installieren. Dafür einen Punkt per `open_items add` mit `--owner` aus
  `theme_migration.people` und ihn in `after` nennen. Ebenso, was die Marke selbst liefern muss: ein
  Konto bei einem Dienst, eine Kennung, eine Freigabe im eigenen Admin. Fehlt dem Team dafür ein Recht,
  sagt `after`, welches Recht bei welcher Person im Admin fehlt.
- **Frage an Path to AI.** Kommt das Team nicht weiter (ein Fehler, den die Skill nicht selbst behebt,
  eine Entscheidung, die keine Regel und keine Frage im Cockpit trägt), schreibt die Skill die Frage
  vollständig, damit Path to AI ohne Rückfrage und ohne den Stand zu suchen antworten kann: Store,
  Schritt, was versucht wurde, was genau fehlt, welche Antwort weiterhilft, und den Pfad der Belege im
  Repo. Sie steht als `--operator-task` mit "Frage an Path to AI: …" in der Übergabe. Dann nennt die
  Skill der Person dieselbe Frage als fertige Nachricht zum Weiterleiten, in Alltagssprache, ohne
  Befehle und Dateinamen außer dem Pfad der Belege: "Schickt Yves diese Nachricht: …". Erst pushen, dann
  die Nachricht nennen, damit Path to AI im Repo sieht, was in der Nachricht steht.
- **Ein verständlicher Halt.** Hält die Sitzung an, sagt sie der Person in einfachen Worten drei Dinge:
  worauf sie wartet, wer es liefert, mit Namen, und was das Team solange tun kann ("Erika Muster legt in
  Shopify unter Einstellungen > Apps das Recht … an. Danach die Migration neu starten. Bis dahin könnt ihr
  die zwei Fragen im Cockpit beantworten."). Gibt es nichts zu tun, sagt sie das ("Bis dahin ist für euch
  nichts zu tun."). Wartet sie auf Path to AI, nennt sie die Aufgabe so, wie sie im Cockpit heißt, und
  sagt, dass Path to AI sie unter Offene Aufgaben sieht; das Team muss nichts weiterleiten außer einer
  "Frage an Path to AI". Begriffe wie in der Oberfläche des Cockpits: Abnahme ist der Test des Entwurfs
  durch das Team, eine Maßnahme etwas aus einem Audit, eine Vorgabe eine Regel der Marke für alle Stores;
  nie das eine für das andere. Nie nur ein Befehl, eine Fehlermeldung oder eine Datei. Die Datei trägt den aktuellen Schritt; steht der Lauf später in einem anderen
  Schritt, gilt sie nicht mehr, und das Cockpit zeigt nur den Namen des Schritts.
- `after` in der Sprache des Kunden, mit ihr und euch, jedes Fachwort erklärt, etwa: "Beantwortet
  die zwei Fragen im Cockpit und startet die Migration danach neu. Claude baut den Entwurf dann um und
  prüft ihn. Findet die Prüfung nichts, was den Launch verhindert, ist er bereit für die Abnahme."
- `run_state show` danach schreibt `migration.json` mit der Übergabe neu.
- Dann Transkripte ablegen, committen und pushen (Abschnitt "Journal und Transkripte").
- Zuletzt den Stand ins Cockpit geben (`run_state cockpit`, `report_migration`, Abschnitt "Stand im
  Cockpit"), damit Kopf, Fragen und "Migration fortsetzen" im Blatt die Übergabe dieser Sitzung zeigen.

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
2. `inventory-apps`: jede Einbindung, Tracking je Ziel, Consent, Fristen. Jedes Custom Pixel wird mit
   Code und Notiz (sendet was, wo, an wen) unter `migration/inventory/pixels/` gesichert
   (`apps-and-tracking.md`, Abschnitt "Custom Pixels sichern"). Ein Custom Pixel, das entfernt oder ersetzt
   werden soll, ohne gesicherte und gelesene Datei hält den Go an (`custom-pixel-backup`). Nach einem
   Launch im November 2026 fehlten Käufe in einer GA4-Property, weil ein Kassen-Pixel auf eine falsche
   Annahme hin gelöscht wurde.
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

**Layout, nicht nur Inhalt.** Der Generator übersetzt seit 11.11.2026 auch Breite, Ausrichtung,
Textgröße, Abstände, Overlay-Deckkraft und Höhe je Section (`layout` im Mapping), setzt die
Typo-Presets und die Schrift der Zwischenüberschriften aus dem Quell-Theme (`typography`) und ergänzt
Pflicht-Sections je Template (`required_sections`, etwa `search-header`). Drei Fälle im Report sind
Arbeit für diesen Neubau, nicht für später: `type_scale_css` (genaue Schriftgrößen je Breakpoint in die
eigene CSS-Datei des Shops), `layout_css_too_long` (Regeln über 500 Zeichen dorthin) und
`required_section_missing` (Section aus dem Original-Theme übernehmen). `disabled_sections` nennt
Sections, die ausgeschaltet übernommen wurden, weil alle ihre Blöcke aus sind.

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
3. `delta.json` unter `hidden_by_blocks`: eine Section, die live an ist, deren Blöcke aber alle aus sind,
   blendet das alte Theme aus. Der Generator übernimmt sie ausgeschaltet; im Bildpaar prüfen, dass im
   Entwurf keine leere Fläche bleibt (nach einem Abgleich im November 2026 eine dunkle leere Leiste).

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key last_sync --value <date>
```

`phase --phase 7-sync --status done`. Kein Änderungsstopp: direkt vor dem Launch zieht die Sitzung
den Stand noch einmal (Phase 9).

## Phase 8: Abnahme

Erst wenn `show` `ready_for_test_round: true` meldet; `phase --phase 8-test-round --status running`
verweigert sonst und nennt, was fehlt. Dann `verify-theme --test-round`:

- Abnahme über `test-round` als Datei im Repo: je Seitentyp und je offener Abweichung ein Testpunkt mit
  Linkpaar, Checkout-Szenarien als Punkte
- ins Cockpit stellt sie Path to AI aus dem Repo: committen, pushen und in der Übergabe
  `--operator-task "Abnahme vom <Datum> ins Cockpit stellen, Datei <Pfad>"`; das Team testet dort
- Rückmeldungen zuerst nachstellen, dann beheben, jede Korrektur an ihrer Ursache
- jeder Testpunkt mit `status` kommt in die Liste offener Punkte (`open_items import --kind
  test-round`, Gate G4); entschieden und erledigt wird dort, danach `open_items sync-test-round --path
  <test.json>`
- eine Abweichung, die die Abnahme findet, wird wie heute behoben; eine Frage für G4 (`questions ask
  --gate G4-acceptance`) nur bei echtem Zielkonflikt, mit Vergleich der beiden Seiten
- ein Testpunkt wird nur mit Bildern vom Entwurf am Rechner und am Handy erledigt: `open_items done --id
  <id> --evidence <text> --desktop-image <bild> --mobile-image <bild>`. Am 11.11.2026 standen mehrere
  Testpunkte ohne Bild auf erledigt, deren Fehler erst nach dem Launch auffielen

Sind alle Punkte erledigt oder mit Person und Datum verschoben und alle Fragen beantwortet, weiter mit
Gate G4.

## Gate G4: Abnahme

Zuerst `open_items sources` und `open_items gate --gate G4-acceptance`. Steht dort etwas offen, ist das
kein Gate zum Vorlegen: die Punkte abarbeiten, mit Beleg erledigen oder mit Person und Datum verschieben.
Offene Fragen für G4 (`questions list --status open --gate G4-acceptance`) beantwortet die Person der Marke.

**Vollständiger Bildvergleich vor G4** (seit 11.11.2026): `compare-themes --compare` über alle Seiten aus
`migration/inventory/pages.json`, am Rechner (1440) und am Handy (390), jede als ganze Seite, links das
veröffentlichte Theme mit seiner ID im Link, rechts der Entwurf. Jedes Bildpaar selbst ansehen, nicht nur
die Testpunkte. `open_items gate --gate G4-acceptance` zeigt unter `visual_compare`, was fehlt, und unter
`done_without_images` jeden Testpunkt, der ohne Bilder vom Entwurf erledigt ist. Beides hält G4 an.

**Nachtrag vom 11.11.2026, ebenfalls vor G4:**

- Die Referenz steht mit ID und Name am Anfang jedes Vergleichs und jeder Abnahme
  (`visual_compare reference`). Vorschau-Links anderer Themes sind keine Vorlage.
- Am Handy nimmt der Bildvergleich auch den Zustand "Menü offen" auf; ein fremdes Element über der
  Menü-Schublade im Entwurf hält G4 an.
- **Datenschicht je GA4-Property:** je ein Durchlauf ohne Bestellung auf Live-Theme und Entwurf, am Handy
  in WebKit mit langsamer Verbindung (`launch-check`, Ablauf vor dem Launch, Schritt 3). Was das Live-Theme
  an eine Property sendet (`view_item`, `add_to_cart`, `begin_checkout`) und der Entwurf nicht, hält G4 an;
  ebenso ein fehlender Durchlauf. `open_items gate` zeigt das unter `datalayer`.

Hält nichts mehr an, bespricht die Person der Marke die Abnahme mit Path to AI. Vorlage dafür: die Ansicht
`migration/open-items.md` (Abschnitt Abnahme), jede entschiedene Abweichung ("wie heute" oder "anders"), jeder
verschobene Punkt mit Person und Datum. Bis zum Gespräch steht in der Übergabe
`--operator-task "Abnahme mit <Person> besprechen"`. Frage an die Person: "Nehmt ihr den Entwurf so ab?" Nach
dem Ja, mit beiden Namen:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state gate --gate G4-acceptance --decided-by "<Name>" --note "abgestimmt mit Path to AI am <Datum>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state phase --phase 8-test-round --status done
```

## Phase 9: Launch

`phase --phase 9-launch --status running`. Checkliste:
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/launch-checklist.md`, Rückfall: `rollback.md`.

Der Launch ist ein geführter Ablauf in vier Schritten: **prüfen, fragen, veröffentlichen, danach
prüfen**. Die Sitzung arbeitet ihn in dieser Reihenfolge ab und zeigt der Person jede Haken-Liste so,
wie der Befehl sie ausgibt. Bis 10.11.2026 stand er verteilt in dieser Phase, in `launch-check` und in der
Checkliste, und den Klick machte ein Mensch im Admin.

### Vorbereitung

1. **Termin vorschlagen und festlegen:** jetzt erst nach dem Termin fragen. Kein Freitag, nicht vor
   Feiertagen, nicht in der Saisonspitze und den Wochen davor, nicht während großer Kampagnen oder
   laufender Preis- und A/B-Tests; Ansprechpartner auf beiden Seiten erreichbar, auch Path to AI.
2. **Abgleich vor dem Launch** mit `sync-live-theme` gegen die letzte Sicherung: jede Änderung seit dem
   letzten Abgleich entschieden und im Entwurf. Es gibt keinen Änderungsstopp; das Team hat
   weitergearbeitet, das ist der Normalfall. `set --key last_sync --value <date>`.
3. **Vergleichswerte direkt vorher:** `pull-gsc`, `pull-ga4`, `pull-cwv`, Crawl des Live-Themes,
   Conversion je Seitentyp und Gerät, soweit die Zugänge im Workspace des Teams vorhanden sind. Fehlt ein
   Zugang, als `--operator-task` ("Vergleichswerte vor dem Launch ziehen: GA4, Search Console") festhalten;
   das zieht Path to AI über das Cockpit, nicht über den Shop.
4. **Go/No-Go- und Rückfallkriterien schriftlich**, mit der Person, die im Ernstfall entscheidet, und
   der Liste dessen, was ein Rückfall nicht rückgängig macht. Die Kriterien legt das Team fest; die
   Sitzung schlägt Formen aus `rollback.md` vor und trägt ein, was die Person bestätigt:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" launch rollback --decider "<Name>" --agreed-with "Path to AI" \
     --criterion "Kauf auf einem Gerät oder mit einer Zahlart nicht möglich | sofort" \
     --criterion "<wann> | <Frist>" --not-reverted "<was nur bei diesem Launch bleibt>"
   ```

   Schreibt `migration/rollback.json` (ein neuer Aufruf ersetzt die Datei ganz), committen und pushen.
   `--not-reverted` nur für das, was diesen Launch betrifft, etwa eine App, die beim Launch deinstalliert
   wird; was nie zurückgeht (Vorlagen-Zuweisungen, Menüs, Apps, Daten), ergänzt das Plugin selbst.
   `launch rollback` ohne Argumente zeigt den Stand.
5. **Rollouts nur auf Wunsch des Teams:** zeitgesteuert, prozentual oder als Experiment, nicht für
   Vintage. Dann veröffentlicht ein Mensch im Admin (`launch-checklist.md`, Veröffentlichen), und Schritt 3
   unten entfällt; Schlussprüfung und Prüfen danach bleiben.

### 1. Prüfen

Mitschnitt beider Themes wie in `launch-check` (Ablauf vor dem Launch, Schritte 2 und 3), dann:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" launch check --launch-date <JJJJ-MM-TT>
```

- Läuft den Launch-Check (`launch_check`, dieselben Argumente) und gibt jeden Go-Punkt als Haken-Liste
  aus: ✅ erledigt, ❌ fehlt, ⏸ blockiert mit Grund, ✋ manuell zu bestätigen, darunter je eine Zeile
  Beleg, am Ende die Summe ("8 von 8 grün") und in einer Zeile, was für diesen Launch entfällt.
- Die Liste unverändert zeigen. Was fehlt, folgt darunter mit "Wer:"; die Sitzung erledigt ihren Teil
  selbst (Abgleich, Neubau, Upload, Mitschnitt, offene Punkte nach "Folgeschritte" in `launch-check`)
  und prüft erneut, bis kein Punkt mehr fehlt.
- Fragen an das Team (`manual`) mit Name und Datum nach `reporting/launch-answers.json`, wie in
  `launch-check` beschrieben.
- Exit 0 heißt alles grün, Exit 1 nicht grün.
- Seit 11.11.2026 hält der Check die Pixel-Liste des Shops in `<lauf>/web-pixels-before.json` fest,
  prüft, ob sich im Entwurf eine App eingetragen hat, die nicht im Ziel-Repo steht (`app-injections`), ob
  ein Dienst vor der Einwilligung sendet (`tracking-pre-consent`, Microsoft an `bat.bing.com` und
  `bat.bing.net`) und ob jedes Custom Pixel, das entfällt, gesichert ist (`custom-pixel-backup`).
- **Nach jedem `launch check`** den Stand ins Cockpit (`run_state show`, dann `run_state cockpit` an
  `report_migration`, Abschnitt "Stand im Cockpit"). Das Cockpit zeigt im Blatt der Migration dieselbe
  Go-Liste mit Summe, den Ablauf (Vorbereiten, Prüfen, Go, Veröffentlichen, Prüfen danach, Beobachten)
  und den Rückfall; so hakt das Team dort mit ab, ohne eigene Seite daneben.

**Gate G5** ist selbst ein Go-Punkt (`go-decision`). Zuerst `open_items gate --gate G5-go-live`. Was
`launch-check` als abgedeckt meldet, schließt `open_items close-covered --launch-check
reporting/runs/<date>-launch-check/launch-check.json` mit Beleg; alles andere wird behoben oder mit Person
und Datum verschoben. `show` muss `ready_for_launch: true` melden. Steht danach nur noch G5 offen,
bespricht die Person der Marke die Liste mit Path to AI (Vorlage `launch-check.md`). Frage: "Go für den
Launch am <Datum> um <Uhrzeit>?" Nach dem Ja:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state gate --gate G5-go-live --decided-by "<Name>" --note "abgestimmt mit Path to AI am <Datum>"
```

Dann `launch check` erneut, am Launch-Tag direkt vor dem Termin.

### 2. Fragen

Nur wenn `launch check` mit Exit 0 endet, steht unter der Liste:

```
Jetzt Launch durchführen?
   Neues Theme: <neue ID> "<Name>", wird live
   Bisher live: <alte ID> "<Name>"
   Rückfall-Theme: <alte ID> "<Name>", bleibt als Entwurf in der Theme-Bibliothek
```

- Genau diese Frage an die Person der Marke stellen, mit Ja und Nein. Theme-IDs stehen hier ausnahmsweise
  in der Frage: es geht um genau diese zwei Themes.
- Ist nicht alles grün, gibt es keine Frage. Die Sitzung zeigt, was fehlt und wer es erledigt, und
  arbeitet weiter. Auch auf Wunsch wird nicht gefragt und nicht veröffentlicht.
- Ein Nein oder keine Antwort: nichts tun, im Journal festhalten (`run_state log --kind answer`).

### 3. Veröffentlichen nach dem Ja

Nur nach einem ausdrücklichen Ja der Person der Marke, mit ihrem Namen:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" launch publish --approved-by "<Name>"
```

- Verweigert ohne grünen Launch-Check von heute (höchstens zwölf Stunden alt), ohne G5, mit einem
  Sammelnamen oder einem Namen außerhalb von `theme_migration.people`.
- **Schlussprüfung** von `sync-live-theme` direkt davor (`sync --final`): `updatedAt` des Live-Themes und
  die Template-Zuweisungen gegen den Abgleich vor dem Launch. Jede Änderung hält an, es wird nicht
  veröffentlicht; dann `sync-live-theme` für die geänderten Teile, `launch check` und erneut fragen.
- **Veröffentlichen** mit `shopify theme publish --store <shop> --theme <neue ID> --path <ziel-repo>
  --force --no-input` (Flags über `shopify-plugin:shopify-use-shopify-cli` geprüft, CLI 4.9.4). Anmeldung
  wie beim Upload über `cli-theme`.
- **Sicherung des Entwurfs** direkt vor dem Veröffentlichen: `layout/theme.liquid` und
  `config/settings_data.json` nach `<lauf>/published-draft/`. Gegen diesen Stand prüft `launch check
  --after`, ob sich eine App beim Veröffentlichen eingetragen hat.
- **Zurücklesen:** das neue Theme hat die Rolle `MAIN`. Erst das zählt; die Meldung der CLI nicht.
- **Stand:** `published_at`, `live_theme_id` (neu), `rollback_theme_id` (alt) und `launch_approved_by`
  im Migrationslauf, `live_theme_id` in der Config, alles in `reporting/runs/<date>-launch-check/launch.json`.
- Exit 0 heißt veröffentlicht und bestätigt. Exit 1 mit "Nicht bestätigt": nicht erneut veröffentlichen,
  erst in der Theme-Bibliothek klären, was live ist.

### 4. Prüfen danach

Der Befehl endet mit "Jetzt kommt der Launch-Check After." Die Sitzung sagt genau das und macht sofort
weiter, ohne zu fragen:

0. Eine abgelöste Consent-App deinstalliert das Team sofort im Admin, nicht nur deaktivieren, und löscht
   ihre Datei unter Inhalte > Dateien (`launch-check`, Abschnitt "Nach dem Veröffentlichen", Schritt 0).
1. Mitschnitt des veröffentlichten Themes und, mit Freigabe, mit Einwilligung (`launch-check`, Abschnitt
   "Nach dem Veröffentlichen", Schritte 1 und 2), dazu die Durchläufe der Datenschicht auf beiden Themes.
2. Testbestellung **nur nach Freigabe**: `walk_checkout.py --approved-by "<Name>"` geht die Kasse bis zur
   Zahlung durch, die Person aus dem Team setzt die Bestellung im geöffneten Fenster ab.
3. Dann:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" launch check --after
   ```

   Dieselbe Haken-Liste für die Prüfungen nach dem Veröffentlichen: erwartetes Theme live,
   Rückfall-Theme als Entwurf, `robots.txt`, Statuscodes, `noindex` und Canonicals, SEO-Ausgabe, Apps und
   Tracking, Tracking nach Einwilligung, die Testbestellung je Ziel, jede Sprache, Sitemap, Stand
   festgehalten. Dazu seit 11.11.2026: jede App, die sich beim Veröffentlichen eingetragen hat
   (`app-injections-after`, Zeilen in `layout/theme.liquid` und App-Embeds gegen `published-draft/`),
   jedes fehlende Pixel gegen die Liste von vorher (`web-pixels-after`), jeder neue Werbe- oder
   Analyseaufruf vor der Einwilligung, und der Kauf in **jeder** GA4-Property und jeder
   Google-Ads-Kauf-Conversion, die der Shop vorher bediente (`purchase-ga4-<g-id>`,
   `purchase-google-ads-<id>-<label>`); läuft der Kauf über den Server, bestätigt ihn ein Mensch im
   Echtzeitbericht jeder Property, nicht nur in einem Tracking-Werkzeug. Altes und neues Theme kommen aus
   dem Stand (`rollback_theme_id`), nicht von Hand. Seit dem Nachtrag vom 11.11.2026 dazu: die
   abgelöste Consent-App ist deinstalliert und ihre Datei unter Inhalte > Dateien gelöscht
   (`consent-app-after`), die Datenschicht je Property auf dem veröffentlichten Theme gegen das
   Rückfall-Theme am Handy mit langsamer Verbindung (`funnel-ga4-<g-id>-after`) und die GA4-Echtzeit je
   Property gegen die Littledata-Property und die Bestellungen (`realtime-ga4-<g-id>`, braucht
   `theme_migration.ga4_properties`). Am Ende der festgehaltene Stand: `published_at` mit dem Namen, neue
   `live_theme_id`, Rückfall-Theme.
4. Was offen bleibt, abarbeiten und `launch check --after` wiederholen. Storno und Erstattung der
   Testbestellung fragt die Liste beim Team ab; steht GA4 noch auf `blocked`, am Folgetag erneut prüfen.
5. Sitemap in der Search Console neu einreichen (Frage in der Liste).

### 5. Fixes nach dem Launch

Fällt nach dem Veröffentlichen etwas auf, gilt der Ablauf aus `post-launch.md`, Abschnitt "Fixes nach dem
Launch". Kurz:

1. **Duplikat** des Live-Themes als Arbeitsstand, im selben Moment `snapshot --theme live` als Referenz;
   das Duplikat wird `draft_theme_id`. Am Live-Theme wird nie direkt gearbeitet.
2. **Getrennte Bereiche** mit getrennten Dateien, parallel möglich; gemeinsame Dateien
   (`settings_data.json`, `layout/theme.liquid`, eigene CSS-Datei, `locales/*`) ändert genau ein Bereich.
   Je Befund Ursache belegt und Bildpaar Rückfall-Theme gegen Duplikat in 1440 und 390 px. Referenz ist
   das Rückfall-Theme, also das bis zum Launch veröffentlichte, mit ID und Name genannt
   (`visual_compare reference`); nie ein drittes Theme aus der Bibliothek oder ein Vorschau-Link.
3. **Chargen:** eine feste Dateiliste geht live nach dem ausdrücklichen Go der verantwortlichen Person, je
   Charge zuerst die **Drift-Prüfung** (`sync --last <referenz>`; keine Datei der Charge darf seitdem live
   geändert sein), dann `shopify theme push --only … --nodelete` ins Live-Theme, dann **Zurücklesen**
   (`upload verify`) und Ansehen live.
4. Je Befund ein Punkt `after_launch` in der Liste, erledigt mit Bildbeleg; Ursachen aus Generator oder
   Mapping gehen als Regel ins Plugin oder in die Overrides.

`phase --phase 9-launch --status done`, committen, pushen, Stand ins Cockpit. Auch `launch check --after`
meldet seinen Stand nach jedem Lauf ins Cockpit wie oben.

## Phase 10: Kontrolle nach dem Launch

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

- Bei jedem Aufruf in Phase 10 den nächsten fälligen Termin und seine Aufgaben nennen, dazu die offenen
  Punkte der Liste mit Gate `after_launch` (`open_items list --status open --gate after_launch`).
- Was nach dem Launch auffällt, kommt per `open_items add --severity after_launch` in die Liste, eine
  Regression an einem erledigten Punkt per `open_items reopen`.
- Das alte Theme erst nach der Stabilisierung und mit Freigabe des Teams löschen.

**Rückrichtung:** Ab dem Launch arbeitet das Team im Editor des neuen Themes. Vor jedem Generatorlauf und
vor jedem Upstream-Merge:

1. `snapshot-theme` sichert das live laufende Ziel-Theme.
2. Der Diff gegen das Ziel-Repo zeigt die Änderungen des Teams.
3. Diese Änderungen übernehmen: ins Repo und, wo der Generator die Datei erzeugt, in Mapping oder
   Overrides.
4. Erst dann generieren oder mergen.

`phase --phase 10-aftercare --status done` erst nach der Bewertung in Woche 6 bis 12 und ohne offenen
Punkt in der Liste.

## Ergebnis

- Ein Entwurf, bereit für die Abnahme, danach die Abnahme mit bewerteten Testpunkten und behobenen Fehlern,
  der Launch durch das Team und die Kontrolle danach.
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
- **Kein Werkzeug `report_migration` oder das Cockpit lehnt die Meldung ab:** Abschnitt "Stand im
  Cockpit". Ohne Meldung zeigt das Cockpit den Stand der letzten Meldung oder des letzten `publish`.
- **Kein Werkzeug `get_policies`:** das Cockpit ist älter als dieses Plugin. Die Fassung im Repo gilt
  weiter; als `--operator-task` festhalten und weiterarbeiten.
- **Ein Wert für einen Baustein fehlt** (etwa die Container-ID): nicht raten und nicht aus einem anderen
  Store übernehmen; Punkt `blocker` in der Liste und weiterbauen.
- **`questions import` überspringt eine Antwort:** der Grund steht in `skipped`, etwa ein Sammelname oder
  "später". Die Frage bleibt offen; die Person im Cockpit neu antworten lassen oder in der Sitzung
  `questions answer` mit ihrem Namen.
- **`run_state version` meldet ein älteres Plugin:** erst aktualisieren lassen, nicht mit der älteren
  Fassung weiterschreiben.
- **`run_state` meldet eine andere Sitzung:** nur eine Sitzung je Lauf. Die andere schließen lassen;
  `claim --force` nur, wenn sie sicher beendet ist.
- **`upgrade_needed`:** Lauf aus einer Version vor 0.3.11. `run_state upgrade` benennt die Phasen um und
  entfernt den Änderungsstopp; danach committen.
- **Phase 9, 10, G4 oder G5 verweigert mit "macht der Betreiber":** das Plugin ist älter als 0.3.27.
  Aktualisieren lassen und die Migration neu starten.
- **Jemand fragt nach Termin oder Änderungsstopp:** einen Stopp gibt es nicht; den Termin legt das Team
  fest, sobald `ready_for_launch` erfüllt ist (Phase 9). Antworten und weiterarbeiten.
- **Eine Aufgabe braucht den Shop und steht bei Path to AI:** falsch zugeordnet, auch in Läufen vor
  0.3.27. Als Punkt mit `--owner` aus dem Team anlegen, die Übergabe ohne diese Aufgabe neu schreiben.
- **`run_state` verweigert ein Gate oder einen Abschluss wegen offener Punkte:** das ist die Regel,
  kein Fehler. Punkte abarbeiten oder mit Person und Datum verschieben, nie die Liste umgehen, eine
  Quelle aus der Config nehmen oder eine Prüfliste abhaken, ohne zu prüfen.
- **Offenes steht in einer zweiten Liste** (Notizen, Mail, ein Bericht ohne Abschnitt "Vor
  dem Launch"): per `open_items add` in die eine Liste, die zweite nicht weiterführen.
- **Beschädigte `state.json`:** das Modul legt sie bewusst nicht neu an, damit die gespeicherten
  Freigaben erhalten bleiben. Datei prüfen und reparieren, nicht löschen.
- **Kein Schreibweg:** `access-write.md` an die Person mit Admin-Rechten im Shop; Standard ist Weg 1 mit einem Konto mit
  Themes-Recht. Phasen 0 bis 4 laufen ohne Schreibweg.
- **20 von 20 Themes belegt:** das Team entscheidet, welches Theme nach Sicherung gelöscht wird.
- **Team hat am Live-Theme gearbeitet:** Normalfall. `sync-live-theme` vor Befunden an einzelnen
  Dateien, vor der Abnahme und direkt vor dem Launch (Phase 9).
- **Live-Theme während eines Uploads geändert:** `upload-theme` bricht ab; erst klären, dann fortsetzen.
- **Korrektur nur in einer erzeugten Datei:** an die Ursache zurückführen, sonst macht der nächste Lauf
  sie rückgängig.
- **Jemand bittet um Veröffentlichen, obwohl die Haken-Liste nicht grün ist:** die Skill veröffentlicht
  nicht, auch nicht auf Wunsch. Sie zeigt, was fehlt und wer es erledigt. `launch publish` verweigert
  ohnehin.
- **`launch publish` hält mit "die Schlussprüfung hält den Launch an":** das Live-Theme oder eine
  Template-Zuweisung hat sich seit dem Abgleich vor dem Launch geändert. `sync-live-theme` für die
  geänderten Teile, `launch check`, dann erneut fragen.
- **`launch publish` meldet einen fehlenden Theme-Ordner:** `theme_migration.target_repo` zeigt nicht auf
  das Ziel-Repo. Pfad in der Config setzen oder `--theme-dir` übergeben; `shopify theme publish` läuft nur
  in einem Ordner mit Theme-Struktur.
