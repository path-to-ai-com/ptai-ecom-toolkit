---
name: theme-launch
description: Teil von Path to AI in einer Shopify-Theme-Migration, die das Team der Marke mit ptai-ecom:theme-migration selbst bis zum Launch führt. Path to AI hat keinen Shop-Zugang und arbeitet nie im Repo eines Stores; es begleitet. Liest den Stand aller Stores einer Marke aus GitHub (theme stores status), lädt Vorgaben und Bausteine der Marke ins Cockpit, stellt die Abnahme aus dem Repo ins Cockpit, beantwortet die Fragen des Teams und bespricht Abnahme (G4) und Go-Live (G5) mit der Person der Marke, die beides in ihrer Sitzung einträgt. Nutzen bei /ptai-ecom:theme-launch, "wo stehen die Migrationen", "Stand aller Stores", "Abnahme ins Cockpit stellen", "Vorgaben der Marke hochladen", "Frage aus der Migration beantworten", "Abnahme besprechen", "Go/No-Go besprechen". Nicht verwenden, um im Shop oder im Repo eines Stores zu bauen, und nicht für die Migration selbst (ptai-ecom:theme-migration).
---

# theme-launch: Path to AI begleitet die Migration

Das Team einer Marke führt die Migration mit `theme-migration` in seiner eigenen Sitzung, vom Sichern des
Shops bis zum Launch und zur Kontrolle danach. Path to AI begleitet: liest den Stand, beantwortet Fragen,
hält Vorgaben und Bausteine im Cockpit aktuell, stellt die Abnahme ins Cockpit und bespricht Abnahme und
Go-Live mit der Person der Marke.

Grund für diese Aufteilung, seit 0.3.27: Bis 0.3.26 lagen Abnahme, Launch und Nachsorge hier, beim Betreiber.
Shop-Zugang hatte aber nur das Team. Jede Aufgabe im Shop lief deshalb über eine Nachricht, eine neue Sitzung
beim Team, einen Upload und das Zurückholen des Stands, und kein Lauf kam über die Abnahme hinaus (drei
Migrationen einer Marke, Oktober 2026).

## Was Path to AI nicht macht

- Nicht im Shop arbeiten: kein Theme, kein Admin, keine App, keine Übersetzung, kein Pixel.
- Nicht im Repo eines Stores bauen oder committen. Ein Fehler, den das Team meldet, wird in diesem Plugin
  behoben; das Team startet die Migration danach neu.
- Keine Aufgabe annehmen, die den Shop braucht. Steht eine solche Aufgabe bei Path to AI, ist sie falsch
  zugeordnet: dem Team als Punkt mit Person zurückgeben.

## Stand aller Stores

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" stores status --repo <owner/store-repo> [--repo <owner/store-repo> ...]
```

- Liest je Repo die jüngste `migration.json` von `main` über `gh`, ohne zu klonen, und gibt je Store eine
  Zeile aus: Schritt, wer zuständig ist, offene Fragen, Aufgaben für Path to AI, letzter Push. `--json` für
  eine JSON-Zeile je Store.
- Die Repos sind die Workspace-Repos der Stores (mit `reporting/`), nicht die Theme-Repos.
- Das ist die Quelle für "wo stehen wir". Keine lokale Kopie lesen, sie ist meist veraltet.
- Steht dort eine Aufgabe für Path to AI, ist sie eine von drei Arten: etwas im Cockpit, eine Frage an Path
  to AI oder ein Gespräch über G4 oder G5. Alles andere gehört dem Team.

## Fragen des Teams

- Eine Frage steht in der Übergabe als "Frage an Path to AI: …" und kommt zusätzlich als Nachricht vom Team.
  Vor der Antwort `stores status` und, wo die Frage auf Belege zeigt, die Dateien im Repo lesen
  (`gh api repos/<repo>/contents/<pfad>`).
- Antwort an das Team in Alltagssprache: was sie tun, in welcher Reihenfolge, und dass sie danach die
  Migration neu starten. Ist die Ursache ein Fehler der Skill, erst das Plugin korrigieren, dann antworten.
- Nichts zusagen, was einen Shop-Zugang braucht.

## Vorgaben der Marke anwenden

Die Vorgaben liegen beim Betreiber im Workspace der Marke (`policies.json` und Bausteine unter
`policy-modules/`, Format `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/policies-format.md`), nie im
Plugin. Die Stores lesen sie seit 0.3.16 nur aus dem Cockpit (`get_policies`, `policies sync` beim Start von
`theme-migration`). Nach jeder Änderung an der Datei oder an einem Baustein deshalb hochladen:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.publish --workspace <store-workspace> \
  --policies-only --target "$(mktemp -d)" --upload
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies apply --source <pfad>/policies.json
"${CLAUDE_PLUGIN_ROOT}/bin/theme" policies check --source <pfad>/policies.json
```

- `--policies-only` lädt nur `policies.json` und jede Datei unter `policy-modules/` hoch und prüft vorher
  Format, Bausteine und das Blatt jeder Vorgabe im Cockpit. Maßnahmen und Anforderungen der Marke bleiben
  unberührt. Jeder Store übernimmt die Fassung beim nächsten Start seiner Migration.
- Ein Baustein ist eine Vorlage mit `README.md`: was er tut, wo er ins Theme gehört, welche Werte ein
  Store einsetzt. Nie den eingebauten Code eines Stores als Baustein hochladen; Präfix und Werte setzt
  jeder Store selbst ein.

- Angewendet werden die Vorgaben in der Sitzung des Teams: `theme-migration` holt beim Start die gültige
  Fassung (`get_policies`, `policies sync`) und führt `apply` aus. Path to AI wendet nichts im Repo eines
  Stores an. Die Befehle `apply` und `check` darunter nur im eigenen Workspace der Marke zum Prüfen.
- Bis alle Stores einer Marke live sind, ändert sich eine Vorgabe nur, wenn sie einen Launch verhindert.
  Jede neue Fassung setzt Schritt 3 jedes Stores auf nacharbeiten.
- Eine offene Vorgabe (`rule: open`) entscheidet der Betreiber; sie hält die Vorbereitung nicht an.

## Ins Cockpit

Den Stand der Migration meldet die Sitzung des Teams selbst (`report_migration`). Das Setup eines Stores
und, wenn eine Sitzung nicht melden konnte, den Stand veröffentlicht Path to AI mit `audit.publish`, aus
einem frischen Klon des Store-Repos (unten), Aufruf
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

## Abnahme ins Cockpit

Die Abnahme entsteht im Repo des Stores (`theme-migration`, Phase 8). Die Sitzung des Teams pusht sie und
trägt "Abnahme vom <Datum> ins Cockpit stellen" als Aufgabe ein. Path to AI holt den Stand von `main` und
stellt sie ins Cockpit, ohne im Repo zu committen:

```bash
W="$(mktemp -d)/store"; gh repo clone <owner/store-repo> "$W" -- --depth 1
cd ~/Developer/path-to-ai/ptai-portal && npm run check-test-round -- "$W/reporting/runs/<run-id>/test.json"
set -a; . ~/Developer/path-to-ai/ptai-portal/.env.local; set +a
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.publish --workspace "$W" --run-id <run-id> \
  --target "$(mktemp -d)" --upload
```

Danach freigeben (`audit.release`) und dem Team sagen, dass sie im Cockpit testen können. Rückmeldungen
arbeitet das Team in seiner Sitzung ab; eine neue Fassung der Abnahme kommt auf demselben Weg.

## Abnahme und Go-Live besprechen

- G4 und G5 entscheidet die Person der Marke nach einem Gespräch mit Path to AI und trägt sie in ihrer
  Sitzung ein, mit dem Vermerk "abgestimmt mit Path to AI am <Datum>".
- Vorlage für G4: `migration/open-items.md` im Repo (Abschnitt Abnahme), die entschiedenen Abweichungen,
  jeder verschobene Punkt mit Person und Datum.
- Vorlage für G5: der jüngste `reporting/runs/<date>-launch-check/launch-check.md` mit den Go-Kriterien und
  `ready_for_launch` aus `stores status --json`. G5 ist dort selbst ein Go-Punkt (`go-decision`); steht nur
  noch er offen, ist der Entwurf bereit für das Gespräch.
- Den Termin legt das Team fest. Path to AI prüft, dass es an dem Tag erreichbar ist.

## Der Launch selbst

Seit 10.11.2026 veröffentlicht die Sitzung des Teams selbst (`theme-migration`, Phase 9): Haken-Liste,
"Jetzt Launch durchführen?" nur bei allem grün, nach dem Ja der Person der Marke Schlussprüfung,
`shopify theme publish` und Zurücklesen, dann sofort "Jetzt kommt der Launch-Check After." mit derselben
Liste. Path to AI veröffentlicht nicht und klickt nicht im Admin; es ist am Launch-Tag erreichbar und liest
danach `reporting/runs/<date>-launch-check/launch.json` und `launch-check-after.md` aus dem Repo. Bis
10.11.2026 veröffentlichte ein Mensch der Marke im Admin, und die Skills prüften davor und danach.

## Fehlerbilder

- **Eine Sitzung des Teams verweigert G4, G5, Phase 9 oder 10 mit "macht der Betreiber":** das Team hat ein
  Plugin vor 0.3.27. Aktualisieren lassen.
- **Die Sitzung des Teams nennt am Launch-Tag nur den Weg im Admin, statt zu fragen:** das Plugin kennt den
  geführten Launch noch nicht (`bin/theme launch` fehlt). Dann gilt der Ablauf von damals: Launch-Check,
  Go, Klick im Admin durch die Person der Marke, `launch-check --after`.
- **`stores status` zeigt einen alten Push:** die letzte Sitzung hat nicht gepusht. Das Team die Migration
  neu starten lassen; sie pusht am Ende jeder Sitzung.
- **Eine Aufgabe für Path to AI braucht den Shop:** an das Team zurückgeben, als Punkt mit Person. Die
  Skill des Teams legt solche Aufgaben seit 0.3.27 nicht mehr an; ältere Übergaben können sie noch tragen.
