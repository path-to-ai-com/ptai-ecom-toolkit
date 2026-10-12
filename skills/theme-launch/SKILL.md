---
name: theme-launch
description: Betreiber-Teil einer Shopify-Theme-Migration, nachdem das Team mit ptai-ecom:theme-migration bis "bereit für die Testrunde" vorbereitet hat. Wendet die Vorgaben der Marke auf den Lauf eines Stores an (policies apply), stellt die Testrunde ins Cockpit, entscheidet mit der Person der Marke die Abnahme (G4), zieht direkt vor dem Launch den Stand des Live-Themes neu (Abgleich vor dem Launch), führt Go/No-Go (G5), Veröffentlichen durch einen Menschen, Prüfungen am Launch-Tag und die Kontrolle nach dem Launch (Nachsorge). Nur mit PTAI_OPERATOR=1; run_state verweigert diese Schritte sonst. Kein Änderungsstopp. Nutzen bei /ptai-ecom:theme-launch, "Launch vorbereiten", "Go/No-Go", "Theme veröffentlichen", "Abnahme der Testrunde", "Vorgaben der Marke anwenden", "Nachsorge nach dem Launch". Nicht verwenden für die Vorbereitung bis zur Testrunde (ptai-ecom:theme-migration). Liest reporting/config.json im Kunden-Workspace.
---

# theme-launch: Vorgaben, Abnahme, Launch und Nachsorge

Das Team einer Marke bereitet mit `theme-migration` vor bis "bereit für die Testrunde" und arbeitet die
Testrunde ab. Alles, was einen Termin, eine Freigabe über mehrere Stores oder das Veröffentlichen
betrifft, macht der Betreiber mit dieser Skill. Grund: In drei parallelen Migrationen einer Marke führte
der Skill jedes Team bis zum Launch. Daraus entstanden Termine, Änderungsstopps und Fragen nach dem
Portal, die niemand entschieden hatte.

Arbeitsverzeichnis: der Kunden-Workspace des Stores mit `reporting/`. Jeder Befehl mit
`PTAI_OPERATOR=1`:

```bash
export PTAI_OPERATOR=1
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
```

Es gelten alle Regeln aus "Was immer gilt" in `theme-migration`, vor allem: jede Shopify-Arbeit über
die Shopify-Skills des Shopify AI Toolkit, veröffentlichen macht immer ein Mensch, eine Sitzung je Lauf.

## Vorgaben der Marke anwenden

Die Vorgaben liegen beim Betreiber im Workspace der Marke (`policies.json`, Format
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/policies-format.md`), nie im Plugin.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies apply --source <pfad>/policies.json
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies check --source <pfad>/policies.json
```

- `apply` schreibt `migration/policies.json`, trägt die Entscheidungen in `decisions.json` und
  `apps.json` ein und legt für fehlende Dienste Punkte `blocker` an. Danach im Repo des Stores
  committen und pushen; das Team zieht den Stand.
- Ändert sich eine Vorgabe, neue Version, erneut `apply` in jedem Store der Marke. Dieselbe Version
  zweimal ändert nichts.
- Eine offene Vorgabe (`rule: open`) entscheidet der Betreiber; sie hält die Vorbereitung nicht an.

## Ins Cockpit

Den Stand der Migration und das Setup eines Stores veröffentlicht der Betreiber mit `audit.publish`, Aufruf
wie in der `CLAUDE.md` des Cockpits (`ptai-portal`, Abschnitt "Lauf hochladen und freigeben"):

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.publish --workspace <store-workspace> \
  --run-id <lauf-id> --target "$(mktemp -d)" --upload
```

- Migration: `<lauf-id>` ist der Migrationslauf (`<datum>-migration`). Hoch geht nur `migration.json`, die
  `run_state` nach jedem Befehl schreibt.
- Setup: zuerst den Lauf anlegen, `"${CLAUDE_PLUGIN_ROOT}/bin/theme" setup from-shop-tech --path
  <shop-tech.json> --shop <slug>` (Format `${CLAUDE_PLUGIN_ROOT}/reference/setup-format.md`), dann
  `<datum>-setup` hochladen. Hoch geht nur `setup.json`.
- Beide sind sofort sichtbar, ohne `release` und ohne `--visible`, und ersetzen die vorige Fassung.
  Transkripte, Journal und `session.lock` bleiben im Repo. Fehlt die Datei im Lauf, bricht `publish` ab.

## Testrunde ins Cockpit

Die Testrunde entsteht im Repo des Stores (`theme-migration`, Phase 8). Der Betreiber prüft sie und
stellt sie wie bisher ins Cockpit; das Team testet dort. Rückmeldungen arbeitet das Team in seiner
Sitzung ab.

## Gate G4: Abnahme

Zuerst `open_items sources` und `open_items gate --gate G4-acceptance`. Steht dort etwas offen, ist das
kein Gate zum Vorlegen: die Punkte abarbeiten lassen, mit Beleg erledigen oder mit Person und Datum
verschieben. Offene Fragen für G4 (`questions list --status open --gate G4-acceptance`) beantwortet die
Person der Marke.

Vorlage an die Person der Marke, die entscheidet, wenn nichts mehr anhält: die Ansicht
`migration/open-items.md` (Abschnitt Abnahme), jede entschiedene Abweichung ("wie heute" oder
"anders"), jeder verschobene Punkt mit Person und Datum. Frage: "Nehmt ihr den Entwurf so ab?" Nach dem
Ja:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state gate --gate G4-acceptance --decided-by "<Name>"
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state phase --phase 8-test-round --status done
```

Den Launch-Termin legt der Betreiber danach mit der Marke fest.

## Phase 9: Launch

`phase --phase 9-launch --status running`. Checkliste:
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/launch-checklist.md`, Rückfall: `rollback.md`.

**Prüflauf über `launch-check --launch-date <JJJJ-MM-TT>`:**

- geht die Checkliste Punkt für Punkt durch und liest IDs, Abgleich und Gates aus diesem Lauf
- schreibt `reporting/runs/<date>-launch-check/launch-check.md` mit Go/No-Go-Empfehlung
- läuft zu Beginn der Phase, nach jedem der Schritte 1 bis 5 erneut, bis kein Punkt mehr `missing` ist,
  und mit `--after` in Schritt 8
- der Bericht ist die Vorlage für G5

1. **Zeitpunkt prüfen:** kein Freitag, nicht vor Feiertagen, nicht in der Saisonspitze und den Wochen
   davor, nicht während großer Kampagnen oder laufender Preis- und A/B-Tests; Ansprechpartner auf
   beiden Seiten erreichbar.
2. **Abgleich vor dem Launch** mit `sync-live-theme` gegen die letzte Sicherung: jede Änderung des Teams
   seit dem letzten Abgleich entschieden und im Entwurf. Es gibt keinen Änderungsstopp; das Team hat
   weitergearbeitet, das ist der Normalfall. `set --key last_sync --value <date>`.
3. **Vergleichswerte direkt vorher:** `pull-gsc`, `pull-ga4`, `pull-cwv`, Crawl des Live-Themes,
   Conversion je Seitentyp und Gerät. Nach dem Launch wird gegen diese Werte verglichen.
4. **Go/No-Go- und Rückfallkriterien schriftlich**, mit der Person, die im Ernstfall entscheidet, und
   der Liste dessen, was ein Rückfall nicht rückgängig macht.
5. **Rollouts als Option vorlegen:** zeitgesteuert, prozentual oder als Experiment; nicht für Vintage;
   Verfügbarkeit im Admin des Shops prüfen.

### Gate G5: Go/No-Go

Zuerst `open_items gate --gate G5-go-live`. Was `launch-check` als abgedeckt meldet, schließt
`open_items close-covered --launch-check reporting/runs/<date>-launch-check/launch-check.json` mit
Beleg; alles andere wird behoben oder mit Person und Datum verschoben. `show` muss
`ready_for_launch: true` melden.

Vorlage: die Go-Kriterien aus der Checkliste, je mit Stand, aus dem jüngsten `launch-check.md`. Frage:
"Go für das Veröffentlichen am <Datum> um <Uhrzeit>?" Nach dem Ja:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state gate --gate G5-go-live --decided-by "<Name>" --note "Rückfall-Theme <live-theme-id>"
```

6. **Schlussprüfung** durch `sync-live-theme` unmittelbar vor dem Klick: `updatedAt` des Live-Themes und
   die Template-Zuweisungen. Jede Änderung seit dem Abgleich vor dem Launch hält den Launch an, bis ein
   Lauf sie übernommen hat.
7. **Veröffentlichen durch einen Menschen** im Admin oder über Rollouts. Die Skill nennt Weg und Theme
   und wartet auf die Bestätigung, dass veröffentlicht ist.
8. **Prüfungen am Launch-Tag** über `launch-check --after`:
   - veröffentlichtes Theme ist das erwartete
   - `robots.txt`, Canonicals und Statuscodes der Top-Seiten, kein `noindex`
   - Apps und Embeds auf dem veröffentlichten Theme per Mitschnitt
   - Tracking mit einer Testbestellung **nur nach Freigabe**
   - jede Sprache
   - Sitemap neu einreichen
9. **Stand festhalten:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key published_at --value <timestamp>
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state set --key live_theme_id --value <new-live-theme-id>
   ```

   In der Konfiguration `live_theme_id` auf die neue ID setzen; die alte steht als Rückfall-Theme in
   der Notiz zu G5. `phase --phase 9-launch --status done`.

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

## Fehlerbilder

- **`run_state` verweigert ohne Betreiber:** `PTAI_OPERATOR=1` fehlt in dieser Sitzung.
- **Vorgaben im Lauf veraltet:** `policies check --source` meldet eine andere Version. Neu anwenden,
  committen, pushen; Schritt 3 steht danach auf nacharbeiten, bis neu gebaut ist.
- **`ready_for_launch` falsch:** `show` nennt die Bedingung. Nie G5 entscheiden, solange eine fehlt.
- **Änderung nach dem Abgleich vor dem Launch:** der Launch bleibt angehalten, bis ein Lauf die Änderung
  übernommen hat.
- **Jemand bittet um Veröffentlichen:** die Skill veröffentlicht nicht, auch nicht auf Wunsch. Sie nennt
  den Weg im Admin.
