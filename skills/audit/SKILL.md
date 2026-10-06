---
name: audit
description: Fährt den einmaligen Ecommerce-Audit eines Shops, als Nullpunkt vor einem Relaunch oder als erste vollständige Bestandsaufnahme. Zieht jede verfügbare Quelle über ihre volle Historie statt über einen Berichtsmonat, startet die Analysen als eigene Subagents, verdichtet die Befunde zu einem priorisierten Maßnahmen-Backlog, friert die Baseline blockweise ein und rendert das Kunden-PDF. Verwenden bei /ptai-ecom:audit, bei einem Erstaudit, bei einer Bestandsaufnahme vor einem Theme- oder Relaunch oder wenn der Nutzer den Nullpunkt für einen Shop will. Stoppt zweimal (Gate A nach den Rohdaten, Gate B nach den Analysen) und setzt erst nach ausdrücklicher Freigabe fort. Ein vollständiger Lauf je Shop; ein zweiter Aufruf wird verweigert und verweist auf report, auf --backfill (leere Baseline-Blöcke nachtragen), auf --reanalyze (Phase 2 bis 4 auf denselben Rohdaten wiederholen, wenn sich eine Analyse geändert hat) oder auf --rerun <discipline> (eine einzelne Analyse nachholen, deren Zugang erst nach dem Audit kam, und ihr Ergebnis in Befunde, Backlog und Gesamtreport desselben Laufs einarbeiten). Liest reporting/config.json im Kunden-Workspace, schreibt reporting/runs/<run-id>/ (Zustand, Datenlage, Screenshots-Index, Befunde, Kunden-PDF) sowie reporting/baseline/01/ und reporting/measures.json.
---

# audit: der Ecommerce-Audit-Orchestrator

- Der Audit setzt den Nullpunkt eines Shops und läuft genau einmal (Spec Abschnitt 3).
- Kein Vergleichswert, kein Vormonat; je Quelle der maximal verfügbare Zeitraum.
- Ergebnis: die Baseline, gegen die jeder spätere `/ptai-ecom:report` vergleicht, und ein priorisierter Maßnahmen-Backlog.
- Die Skill steuert fünf Phasen (0 bis 4, Spec Abschnitt 6) über zwei Skripte, fünfzehn Pull-Skills, elf Analyse-Subagents und zwei Module, die Baseline und Backlog schreiben.
- Sie ruft selbst keine API auf und rechnet keine Kennzahl. Sie legt fest, wer wann läuft, führt den Zustand und hält zweimal an, bevor etwas zum Kunden geht.
- Arbeitsverzeichnis: der Kunden-Workspace mit `reporting/`, wie bei jeder Skill dieses Plugins.
- Abgrenzung zu `report`: `report` läuft nach Kadenz und vergleicht dreifach (Vorlauf, Baseline, Vorjahr). `audit` läuft einmal ohne Vergleich und setzt den Nullpunkt für `report`.
- Gemeinsam mit `report`: dieselben Pull-Skills, dasselbe `state`-Modul, dieselbe Lauf-ID-Mechanik (`scripts/audit/run.py`, `state.py`).

## Voraussetzungen

- `reporting/config.json` existiert, und `scripts/audit/config.py:
  validate()` liefert eine leere Fehlerliste.
  - Pflichtfelder: `brand`, `domain`, `cwv_urls`, `sources`, `account_slug`, `drive_path`, `market`.
  - `shopify_store`, `ga4_property_id` und `gsc_site` sind nur Pflicht, solange ihre Quelle an ist (`config.SOURCE_FIELDS`).
  - Ob eine Quelle Pflicht, empfohlen oder optional ist: `scripts/audit/tiers.py`.
  - Config fehlt oder `validate()` schlägt fehl: nichts raten, nichts anlegen. In zwei Sätzen nennen, was fehlt, und die Skill `setup` anbieten. Bei Ja übernimmt der Wizard, bei Nein hier enden.
  - Dieselbe Regel gilt in Phase 0. Sie steht hier vorab, weil ohne Config auch die Prüfung auf eine bestehende Baseline nicht läuft.
- `config.hints()` blockiert nicht. Vor dem Start einmal zeigen.
  - Dort steht nur, was ein Mensch entscheiden muss.
  - Wettbewerber und Keyword-Seeds gehören nicht in die Hinweise, kein Pull liest sie. Wettbewerber ermittelt `pull-dfs-competitors` über die Überschneidung in den Suchergebnissen, Keywords holt `pull-dfs-keywords` aus der Search Console.
  - Keinen Hinweis ergänzen, der eine Arbeit verlangt, deren Ergebnis niemand liest.
- Werkzeuge:
  - headless Browser für `capture-screens` und das Kunden-PDF in Phase 4; bevorzugt die Headless Shell von Playwright, Chrome oder Chromium gehen auch
  - bei `geo_method: browser` ein Browser-Werkzeug in der Session für `check-geo`
  - `jq` für `capture-screens`
  - `curl` und `jq` für `pull-cwv`
  - Shopify CLI für `pull-shopify`
  - `PTAI_GOOGLE_CREDENTIALS` in der `.env` des Workspace
  - Betreiber-Schlüssel (PageSpeed, DataForSEO, GEO, Ads-Token) dort oder zentral in `~/.config/ptai-ecom/.env`
- Fehlerbilder einzelner Quellen stehen in der jeweiligen Pull-Skill.

## Ein Audit läuft genau einmal je Shop

Als erster Schritt, vor dem genauen Lesen der Config, prüfen, ob der Shop schon eine Baseline hat:

```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import baseline

if not baseline.numbers('.'):
    print('kein-baseline')
elif baseline.is_fresh('.'):
    print('frische-generation')
elif baseline.is_complete('.'):
    print('vollstaendig')
else:
    print('unvollstaendig')
"
```

| Ausgabe | Bedeutung | Vorgehen |
|---|---|---|
| `kein-baseline` | noch nie ein Audit gelaufen | weiter mit Phase 0 |
| `frische-generation` | eine frühere Baseline wurde abgelöst, die geltende Generation hat noch keinen Block | weiter mit Phase 0 wie beim Erstlauf; wann eine Ablösung richtig ist, steht unter "Wenn die Messung selbst falsch war" |
| `vollstaendig` | alle zehn Blöcke stehen | **verweigern**, auf `/ptai-ecom:report` verweisen, keine Phase starten; ein zweiter voller Audit liefert nichts, was `report` nicht ohnehin liefert |
| `unvollstaendig` | Baseline existiert, mindestens ein Block ist leer (häufig `seo_visibility`, `sea` und `catalogue`, deren Zugänge oft nach dem Erstlauf kommen) | **verweigern**, auf `--backfill` verweisen; der Modus füllt nur, was `baseline.empty_blocks()` als leer meldet, und ändert keinen geschriebenen Block (Mechanik unter "Der Nachtrag-Modus: `--backfill`") |

- Die Verweigerung gilt für den Aufruf ohne Schalter.
- Ruft der Nutzer ausdrücklich `/ptai-ecom:audit --backfill`, `--reanalyze` oder `--rerun <discipline>` auf, gilt statt der Verweigerung der jeweilige Modus.

### Wenn der erste Lauf verworfen werden soll

Anlass: Seit dem Lauf haben sich Regeln, Quellen oder Config geändert.

- **Nicht `--backfill` verwenden.** Er füllt nur leere Blöcke und lässt die nach altem Stand geschriebenen stehen; die Baseline bestünde dann unbemerkt aus zwei Ständen.
- **Archivieren, nicht überschreiben.** Die Zahlen des Laufs müssen nachvollziehbar bleiben, falls er schon einem Termin zugrunde lag.

```bash
ARCH="reporting/archiv/<run-id>-verworfen"
mkdir -p "$ARCH"
mv "reporting/data/<run-id>"  "$ARCH/data"
mv "reporting/runs/<run-id>"  "$ARCH/runs"
mv reporting/baseline         "$ARCH/baseline"
mv reporting/measures.json    "$ARCH/measures.json"
mv reporting/measures.md      "$ARCH/measures.md"
```

- Im Archivordner ein `README.md` anlegen, das in drei Sätzen den Grund des Verwerfens nennt.
- Diese drei Dateien bleiben an ihrem Platz:

| Datei | Grund |
|---|---|
| `reporting/config.json` | Zugänge und Einstellungen gelten weiter |
| `reporting/context.json` | das Kundenwissen gehört dem Kunden, keinem Lauf |
| `reporting/dfs-ledger.jsonl` | das Belegbuch wächst über alle Läufe und wird nie verschoben; der neue Lauf bezahlt die bezahlten Quellen erneut, und das soll im Ledger stehen |

- Danach meldet die Prüfung oben `kein-baseline`, der nächste Aufruf läuft normal.

### Wenn die Messung selbst falsch war: eine neue Generation

Anlass: Die Messung des Shops war nachweislich fehlerhaft, die Baseline beschreibt einen Zustand, den es nie gab. Beispiele: ein zweiter Absender zählte jedes Ereignis doppelt, ein Bot-Netz vervielfachte die Sitzungen, ein Tag feuerte nie.

- **Nicht archivieren.** Der Lauf ist der Beleg für den Fehler und enthält die Zahlen, die der Kunde bis dahin gesehen hat; später muss nachlesbar sein, wie weit die Messung abwich.
- **Eine neue Generation anlegen.** Die alte bleibt vollständig erhalten, die neue beginnt leer und nennt in ihrem Kopf, welche sie ablöst und warum.

```bash
python3 -c "
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import baseline
print(baseline.supersede('.', 'Ein zweiter Absender zählte vom 30.04. bis zum 14.09.2026 jedes Funnel-Ereignis doppelt. Die Blöcke der Generation 01 stehen auf diesen Zahlen.'))
"
```

- Der Grund ist Pflicht und in ganzen Sätzen. Er erscheint über jeder Fassung der `baseline.md` und erklärt, warum ab hier gegen andere Zahlen gemessen wird.
- Danach meldet die Prüfung oben `frische-generation`; der nächste Aufruf läuft wie ein Erstlauf, ohne dass ein Ordner verschoben wurde.
- **Alter der Zahlen ist nie ein Anlass.** Die Baseline ist der eingefrorene Nullpunkt und veraltet nicht; wer sie wegen frischerer Zahlen ersetzt, verliert den Vergleichspunkt. Einziger Anlass: die Messung war belegt falsch.

### Wenn nur die Auswertung neu laufen soll: `--reanalyze`

Anlass: Die Rohdaten eines Laufs sind gut, die Auswertung hat sich geändert (neue Analyse, schärfere Prüfliste, korrigierte Regel). Phase 2 bis 4 laufen erneut **auf denselben Snapshots**.

- `--backfill` passt nicht: er ändert keine geschriebenen Blöcke.
- Verwerfen passt nicht: es verwirft die Rohdaten und bezahlt die bezahlten Quellen erneut.
- Die Pulls laufen nicht mit, auch wenn sie billig waren: ein neuer Pull misst einen anderen Zeitpunkt und verschiebt damit den Nullpunkt, gegen den jeder spätere Report vergleicht.

Ablauf:

```bash
# 1. Die bisherige Fassung beiseitelegen und den Backlog zurücksetzen.
python3 -m audit.revision --workspace . --run-id <run-id>

# 2. Die Phasen 2 bis 4 wieder öffnen, Phase 0 und 1 bleiben `done`.
python3 -c "
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import state
run_state = state.load('.', '<run-id>')
print(run_state.reopen_from('2-analyses'))
run_state.save()
"
```

3. Diese Skill erneut aufrufen. `next_phase()` liefert `2-analyses`, der Lauf setzt dort an, als wäre Phase 1 gerade fertig.

Was `revision` verschiebt und was bleibt:

| Was | Wohin | Grund |
|---|---|---|
| `findings/`, `audit.pdf`, `audit.html`, `audit-web.html` | nach `runs/<run-id>/revisions/NN/` | das ist die Fassung; ohne sie lässt sich später nicht erklären, warum eine Zahl anders lautet als im Termin |
| `measures.json`, `measures.md` | **Kopie** ins Archiv | der Backlog gilt über alle Läufe, das Original bleibt |
| `report-text.json` | **bleibt** | enthält die von einem Menschen geschriebenen Sätze; sie gelten dem Lauf, nicht der Fassung |
| die Snapshots in `data/<run-id>/` | bleiben unverändert | auf ihnen läuft der ganze Modus |

- **Der Backlog wird gesiebt, nicht geleert.**
  - Eine Maßnahme mit Status `open` und nur dem einen Eintrag, den `create()` selbst schreibt, ist unberührt: sie entsteht neu und wird entfernt.
  - Hat sie einen gesetzten Status oder eine Historie, bleibt sie.
  - Stellt eine neue Analyse denselben Befund erneut, entsteht eine Dublette; das ist gewollt, eine verlorene Entscheidung wiegt schwerer.
  - `next_id` zählt hinter den behaltenen weiter, keine Kennung wird doppelt vergeben.
- **Die Baseline bleibt unverändert.** `baseline.write_block()` schreibt nur in leere Blöcke. Ein zweiter Durchgang von Phase 3 lässt die sieben gefüllten stehen und füllt nur nach, was beim ersten Mal leer blieb. Der Nullpunkt gehört dem Messzeitpunkt, nicht der Auswertung.

### Wenn eine Disziplin nachkommt: `--rerun <discipline>`

Anlass: Einer Analyse fehlte beim Audit ein Zugang. Sie steht im Report als "nicht erhoben", meist mit einer Maßnahme "Zugang einrichten". Kommt der Zugang später, läuft nur diese Disziplin nach.

- Ihr Ergebnis geht **in denselben Lauf**: in seine Befunde, in den Backlog, in den Gesamtreport. Ein eigener Lauf daneben wird vom Report nicht gelesen, die Maßnahme zur Lücke bliebe offen.
- Die anderen Modi passen nicht: `--backfill` schreibt nur Baseline-Blöcke, keine Befunde; `--reanalyze` wiederholt alle Analysen samt Synthese; ein voller Lauf wird verweigert.
- `<discipline>` ist der Dateiname der Befunde ohne `.json`, etwa `sea`, `seo-content`, `data-quality`. Die Tabelle in Phase 2 nennt je Subagent seine Eingabedateien, die Tabelle in Phase 1 je Pull seinen Quell-Schlüssel.
- Der Lauf ist der, dessen Report die Lücke zeigt, kein neuer.

**1. Nur die fehlenden Quellen ziehen.**

- Ziel: `reporting/data/<run-id>/` des ursprünglichen Laufs.
- Je Quelle `run_state.set_source(key, "done", file=..., today=today)` und `run_state.save()`.
- `pulled_at` enthält damit den Tag des Nachlaufs; der Report setzt unter den Abschnitt "Nacherhoben am" (`report_build._rerun_note()`, bisher in `sec_sea` aufgerufen; eine andere Sektion bekommt den Aufruf beim ersten Nachlauf ihrer Disziplin).
- Die Kennzahlen dieses Abschnitts rechnen über den Zeitraum des Nachlaufs (bei Ads `detail_period`), nicht über das Fenster des Laufs, damit sie zu den Befunden passen. Der Abschnitt nennt beide Angaben.
- Die übrigen Eingabedateien der Analyse bleiben unverändert. Sie stammen vom Audit-Tag; ein Befund auf ihrer Grundlage nennt dieses Datum.

**2. Die Fassung kopieren, nicht verschieben:**

```bash
python3 -m audit.revision --workspace . --run-id <run-id> --copy
```

- `--copy` lässt Befunde, Report, `report-text.json` und Backlog im Lauf und legt eine Kopie nach `revisions/NN/`.
- Ohne `--copy` würden alle Befunde verschoben, der Gesamtreport bestünde aus einer Disziplin, und der Backlog würde gesiebt, sodass unberührte Maßnahmen anderer Disziplinen verschwinden.

**3. Nur diesen einen Subagenten starten**, mit der Lauf-ID wie in Phase 2 und diesem Zusatz im Prompt (sinngemäß):

> Das ist ein Nachlauf. Die vorige Fassung deiner Befunde liegt in
> `reporting/runs/<run-id>/revisions/NN/findings/<discipline>.json`. Ein
> Befund, der weiter gilt, übernimmt Kennung und `statement` unverändert.
> Ein neuer Befund bekommt eine Kennung hinter der höchsten bisherigen. Ein
> Befund, der nur die jetzt geschlossene Lücke beschrieb, entfällt, ebenso
> die `blocked_questions`, die jetzt beantwortet sind.

**4. Die Kennungen prüfen**, bevor etwas weiterläuft:

```bash
python3 -m audit.rerun --workspace . --run-id <run-id> \
    --discipline <discipline> --previous reporting/runs/<run-id>/revisions/NN/findings/<discipline>.json
```

- Exit 1: eine Kennung bezeichnet jetzt einen anderen Befund. Umnummerieren, nicht weitermachen; eine Maßnahme verweist über `finding_ref` auf genau diese Kennung, im Portal stünde sonst ein fremder Befund darunter.
- Beim Umnummerieren auch Verweise in Texten nachziehen ("siehe SEA-05").
- Ohne Fehler listet das Script neue Befunde, weggefallene Befunde und verwaiste Maßnahmen.
- Danach Abnahme und Belegprüfung wie nach Phase 2 (`audit.qa`, `audit.evidence`) für diesen Lauf.

**5. Den Backlog fortschreiben, nicht neu aufbauen.**

- `measures.create()` nur für die neuen Befunde, mit allen Feldern aus Phase 3, Schritt 3.
- Jede verwaiste Maßnahme bekommt über `measures.set_status()` mit `run_id` und `note` ein Urteil:
  - `implemented`, wenn der Nachlauf die beschriebene Lücke geschlossen hat ("Zugang steht seit dem …, die offenen Kernfragen sind in SEA-03 bis SEA-09 beantwortet")
  - sonst `obsolete`, wenn die Analyse den Befund nicht mehr stützt
- Maßnahmen zu gebliebenen Befunden bleiben unverändert.
- Eine erledigte oder verworfene Maßnahme ändert der Nachlauf nie.

**6. Die Baseline nur füllen, wenn sie diesem Lauf gehört.**

- Den Block der Disziplin schreiben (Mechanik wie `--backfill`) nur, wenn beides gilt:
  - die geltende Generation gehört diesem Lauf, ihre geschriebenen Blöcke nennen `as_of.run_id` dieses Laufs
  - der Block ist leer
- Ist die Generation abgelöst oder noch frisch: **nichts** schreiben. Ein einzelner Block in einer frischen Generation markiert sie als begonnen, und die Prüfung oben verweigert dann ihren vollen Lauf. Der Block kommt mit dem Lauf der geltenden Generation.

**7. Den Report nachziehen.**

- In `report-text.json` die Sätze der Disziplin anpassen: `section_messages` ihrer Sektion, dazu `takeaways` und `problems`, wenn sie eine Kennung oder Aussage dieser Disziplin enthalten.
- Danach Phase 4 wie gewohnt (`audit.report_build`).
- Die übrigen Sätze bleiben, ein Mensch hat sie geschrieben.

**8. Veröffentlichen nur mit Freigabe**, wie jede Fassung (`audit.publish`, danach `release`). Hochladen ändert Report und Backlog, die der Kunde womöglich schon gelesen hat.

**Artefakte:** `reporting/runs/<run-id>/findings/<discipline>.json` neu, `revisions/NN/` als Kopie der vorigen Fassung, `measures.json` fortgeschrieben, `audit.html`, `audit-web.html` und `audit.pdf` neu gebaut, je nach Schritt 6 ein Baseline-Block.

## Einstieg und Wiederaufnahme

Gilt, wenn keine Verweigerung greift: der Lauf startet oder setzt fort.

1. **`today` einmal bestimmen** (`date.today()`) und durch den ganzen Lauf reichen.
   - Kein Aufruf von `set_source()` oder `write_block()` ermittelt das Datum selbst.
   - Grund: Phase 1 allein dauert 30 bis 60 Minuten (Spec Abschnitt 6). Ein Lauf über Mitternacht bekäme sonst für Quellen desselben Laufs verschiedene Kalendertage, und `run.is_due()` und die Kadenz-Logik rechnen gegen diese Grenze.
2. **Lauf-ID bilden:** `run.run_id(today, "audit")`, zum Beispiel `2026-10-01-audit`.
3. **Zustand laden oder anlegen.**
   - `state` ist das Modul, `run_state` das geladene Objekt.
   - `set_source`, `set_phase`, `source_open` und `save` sind Methoden **am Objekt**, nicht am Modul. Ein Aufruf am Modul endet in einem AttributeError mitten in Phase 1; ein Test prüft die Trennung.

   ```bash
   python3 -c "
   import sys
   from datetime import date
   sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   from audit import state, run
   today = date.today()
   run_id = run.run_id(today, 'audit')
   run_state = state.load_or_new('.', run_id, 'audit', period=run.period('audit', today))
   print(run_state.next_phase())
   "
   ```

   `run.period('audit', today)` liefert `None`: ein Audit hat keinen Berichtszeitraum und zieht je Quelle maximal (Spec Abschnitt 3, 5).
4. **`next_phase()` bestimmt den Einstieg.**
   - `None`: alle fünf Phasen stehen auf `done`, nichts zu tun (Grenzfall, die Verweigerung oben fängt ihn normalerweise ab).
   - Sonst eine der fünf Phasen in dieser Reihenfolge: `0-setup`, `1-raw-data`, `2-analyses`, `3-synthesis`, `4-deliverables`.
   - Eine abgebrochene Phase (Status `open` oder `running`) wird erneut betreten, eine `done`-Phase nie wiederholt.
5. **In Phase 1 entscheidet die Quelle, nicht die Phase.**
   - `run_state.source_open(source)` ist `False`, sobald die Quelle in einem früheren Anlauf `done` gemeldet hat. Sie wird nicht erneut gezogen, auch wenn Phase 1 noch nicht `done` ist.
   - So kostet eine bezahlte DataForSEO-Abfrage (spätere Stufe) oder ein gelaufener Shopify-Pull beim zweiten Anlauf nichts.

### Genau ein Schreiber für den Zustand

- Die Pulls in Phase 1 dürfen parallel laufen (siehe Parallelität).
- **`run_state.save()` ruft nur diese Orchestrator-Ebene auf, nie ein Pull, und immer nacheinander, nie zwei Aufrufe gleichzeitig.**
- Jeder Pull, ob Hintergrundprozess oder Subagent, meldet nur sein Ergebnis zurück (Dateipfad bei Erfolg, Grund bei Fehlschlag). Er lädt und speichert `state.json` nie selbst.
- Grund (auch in `state.py`): zwei Prozesse mit je eigenem Stand überschreiben einander über `os.replace`. Der letzte gewinnt, die Einträge der anderen fehlen, deren Quellen gelten beim nächsten Anlauf als offen und werden erneut gezogen und bei bezahlten Quellen erneut bezahlt.
- Ablauf je Ergebnis: warten, sofort `run_state.set_source(source, status, file=..., reason=..., today=today)` eintragen, direkt danach `run_state.save()`, erst dann das nächste Ergebnis annehmen.
- `today` ist immer der Wert aus Schritt 1, nie eine neu gelesene Uhrzeit.

## Phase 0: Setup

**Schritte:**

1. `config.validate()` gegen die gelesene `reporting/config.json`.
   - Fehlerliste nicht leer: `setup` anbieten und hier enden. Die Phase bleibt `open`, nicht `failed`, damit ein späterer Aufruf hier wieder ansetzt.
   - `config.hints()` einmal zeigen, blockiert nicht.
2. Den Check ausführen:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/check_env.sh" .
   ```

3. **Exit-Code 0:** Nennen die Schlusszeilen offene empfohlene oder optionale Quellen ("Offen, empfohlen: ..."), die Liste einmal ohne Rückfrage zeigen. Weiter.
4. **Exit-Code größer 0:**
   - Zeigen: die offenen Punkte aus Rechner, Pflicht und Workspace, die "Ohne ... fehlt"-Sätze aus dem Check und die offenen empfohlenen Quellen als Liste.
   - Dann genau eine Frage: trotzdem starten? Bei Ja weiter, bei Nein `setup` anbieten, die Phase bleibt `open`.
   - "Pflicht vollständig." heißt nur, dass jede Pflichtquelle laufen kann. Ein offener Punkt unter Pflicht (etwa ein versionierter Schlüssel des Dienstkontos) kommt trotzdem in die Liste vor der Frage.

- **Phase 0 markiert keine Quelle.** `run_state.source_open()` liefert für jeden Status außer `done` True; Phase 1 zöge eine als `skipped` markierte Quelle trotzdem und überschriebe den Eintrag. Eine fehlende Quelle scheitert in Phase 1 einzeln mit ihrem echten Grund, Gate A zeigt ihn.
- **Die Frage kommt einmal je Shop**, vor jedem Pull und jeder bezahlten Abfrage. Die Kaufweg-Frage gehört dagegen ins Setup, nicht in diesen Lauf.

**Artefakt:** keins von dieser Skill.

**Bei Erfolg:** `run_state.set_phase('0-setup', 'done')`, `run_state.save()`.

## Phase 1: Rohdaten

- Gezogen wird jede Quelle aus `run.SOURCE_CADENCE`, für die `run_state.source_open(source)` noch `True` liefert.
- Die Lauf-Kadenz ist `"audit"`, daher liefert `run.is_due()` für jede Quelle sofort `True` (erste Bedingung der Funktion: `cadence == "audit"`).
- Kadenz je Quelle und `last_pulled` sind im Audit ohne Belang; nur `source_open()` entscheidet.

### Zwei Ordner, zwei Zwecke

| Ordner | Inhalt |
|---|---|
| `reporting/data/<run-id>/` | Rohdaten-Snapshots je Quelle; dieselben Dateien lesen die Analysen und später `report` |
| `reporting/runs/<run-id>/` | der Lauf: `state.json`, das Gate-A-Blatt, der Screenshots-Index, die Befunde je Disziplin |

- `reporting/dfs-ledger.jsonl` liegt **außerhalb** der Lauf-Ordner und wächst über alle Läufe.
  - Eine Zeile je bezahltem DataForSEO-Aufruf, mit Tag, Endpunkt und echtem Betrag.
  - Nie löschen, nie überschreiben. Aus ihr ergeben sich die Kosten je Kunde und Lauf ohne Fremdsystem (Spec Abschnitt 13).

**Zielordner der Pulls: immer `reporting/data/<run-id>`.**

- `pull-gsc`, `pull-ga4` und `pull-cwv` zeigen in ihrer Ablauf-Beschreibung `--out "reporting/data/$(date +%F)"` (nur Tagesdatum, ohne Kadenz-Suffix). Das stammt aus der Zeit vor der Lauf-ID-Konvention und gilt für `report` und den Wochen-Puls, **nicht für den Audit**.
- Im Audit `--out` auf `reporting/data/<run-id>` setzen, wie `crawl-site` es schon dokumentiert.
- Die elf Analyse-Subagents in Phase 2 erwarten `reporting/data/<run-id>/shopify.json` und so weiter, nie `reporting/data/<heute>/...`.
- Schreibt ein Pull in den Tages-Ordner, liefert Phase 2 eine leere Analyse ohne jede Fehlermeldung.

### Wer heute schon zieht, wer noch nicht gebaut ist

| Quelle (Schlüssel) | Skill | Betriebsart in diesem Lauf |
|---|---|---|
| `shopify` | `pull-shopify` | Die Session baut den Snapshot selbst (kein Script). `SINCE` auf ein Datum weit vor jeder realistischen Shop-Gründung (praktisch `2010-01-01`), `UNTIL` gestern. **ShopifyQL liefert auch für Zeiträume ohne Daten eine Zeile je Intervall**, bei `TIMESERIES month` einen Eintrag je Monat seit `SINCE`, meist auf Null. Diese Zeilen unverändert übernehmen und in `notes.by_month` festhalten, wie viele Umsatz haben; ungefiltert als Monate gezählt verfälschen sie jeden Durchschnitt und jede Saisonalität. Ob die Historie so weit zurückreicht, meldet Schritt 2 der Skill selbst (`read_all_orders`-Prüfung, `notes.order_history` im Snapshot bei Kappung auf 60 Tage) |
| `ga4` | `pull-ga4` | Script, `--max-history --audit-checks`, schreibt `ga4-max-history.json` mit gemessenem `history_from`. **`--compare-properties` aus `config.compare_properties()` immer mitgeben**, wenn der Shop mehr als eine Property beliefert; ohne den Vergleich ist keine Aussage über fehlende oder doppelte Käufe haltbar. **`--audit-checks` bei jedem Audit**: prüft auf Bot-Profile und einen zweiten Absender je Mess-ID und zieht die Zahlen ohne Profil und nur mit dem ersten Absender dazu, bevor Phase 2 eine GA4-Rate rechnet (Abschnitt "Bot-Profile und Absender" in `pull-ga4`). Ohne den Schalter stehen Befunde auf Bot-Sitzungen und doppelt gezählten Ereignissen |
| `gsc` | `pull-gsc` | Script, `--max-history`, schreibt `gsc-max-history.json` mit gemessenem `history_from` |
| `cwv` | `pull-cwv` | Script, kein Zeitraum-Schalter nötig (rollierendes 28-Tage-Fenster plus CrUX-Wochenhistorie sind bereits das Maximum) |
| `geo` | `check-geo` | Script bei `geo_method: "api"`; bei `"browser"` Foreground mit Login durch den Menschen; bei `"off"` kein Snapshot, Quelle `skipped` |
| `crawl` | `crawl-site` | Script, `--out` ist bereits run-id-basiert dokumentiert. **Umfang und Pause kommen aus `audit.config.crawl_budget(config)`**, nie aus dem Prompt: `--max-urls` und `--delay` damit belegen. Ein ungebremster Crawl kostet ein Vielfaches des übrigen Laufs (Spec Abschnitt 3, "Was ein Lauf kostet") |
| `screens` | `capture-screens` | Script für die Seitentypen, Browser-Werkzeuge für den Kaufweg, läuft automatisiert. **`config.checkout_capture()` entscheidet, nicht der Lauf:** `True` nimmt den Kaufweg auf, `False` lässt ihn aus und weist die Lücke aus, `None` heißt, die Config beantwortet die Frage nicht |

Quellen aus Stufe 2:

| Quelle (Schlüssel) | Skill | Betriebsart in diesem Lauf |
|---|---|---|
| `catalogue` | `pull-shopify-catalog` | Die Session sammelt die CLI-Seiten, dann `catalog_build.py`. **Nach `pull-shopify`**, gleiche Auth, gleiches Punktebudget |
| `shop_tech` | `pull-shopify-tech` | Die Session holt einen Block über die CLI, dann `shop_tech_build.py` mit `--crawl` auf die `crawl.json` desselben Laufs. **Nach `crawl-site`** |
| `ads` | `pull-ads` | Script. Ohne Freigabe des Cloud-Projekts oder ohne Kontozugang: `skipped` mit Grund, Block SEA bleibt leer. Seit dem 02.10.2026 gegen ein echtes Konto geprüft |
| `dfs_rankings` | `pull-dfs-rankings` | Script, zwei bezahlte Aufrufe (Bestand, Share of Voice), die Historie nur mit `--with-history` |
| `competitors` | `pull-dfs-competitors` | Script, ein bezahlter Aufruf. Seeds sind `geo_queries.category`, **nie Markenbegriffe** |
| `shopping` | `pull-dfs-shopping` | Script, task-basiert mit Wartezeit. **Zuerst starten**, er dauert am längsten |
| `dfs_keywords` | `pull-dfs-keywords` | Script, ein bezahlter Aufruf je 1.000 Begriffe. **Nach `pull-gsc`**, er übernimmt dessen Top-Queries. Ungeprüft gegen die echte API |
| `backlinks` | `pull-dfs-backlinks` | Script, fünf bezahlte Aufrufe, quartalsweise fällig. Ungeprüft gegen die echte API |

- `esp`, `meta` und `reviews` haben noch keine Pull-Skill (Stufe 3).
- Keine Pulls: `cwv_lab` holt `pull-cwv` mit, `measures` führt Phase 3.
- Für jede noch nicht gebaute Quelle: `run_state.set_source(source, "skipped", reason="Pull noch nicht gebaut", today=today)`. Das ist kein Fehler, sondern der dokumentierte Ausbaustand; Gate A weist es wie jede andere Lücke aus.

### Reihenfolge innerhalb von Phase 1

1. **`pull-dfs-shopping` zuerst anstoßen.** Task-basiert mit Wartezeit, alles andere läuft parallel weiter.
2. **`pull-gsc` vor `pull-dfs-keywords`**, sobald dieser gebaut ist; er übernimmt die Top-Queries von `pull-gsc`.
3. **`crawl-site` vor `pull-shopify-tech`.** `pull-shopify-tech` liest Skript-Hosts und Mess-IDs aus `crawl.json`, statt selbst zu crawlen.
4. **`pull-shopify` vor `pull-shopify-catalog`.** Dieselbe Auth; die Scope-Prüfung steht in `pull-shopify`.

Scheitert eine Vorbedingung, kein Abbruch: der abhängige Pull läuft ohne diesen Teil und schreibt einen Vermerk.

### DataForSEO kostet Geld, und deshalb gibt es eine dritte Bahn

- Die DataForSEO-Pulls laufen **nacheinander**, nie parallel.
  - Grund: der Budgetdeckel wird gegen die Summe in `reporting/dfs-ledger.jsonl` geprüft. Zwei parallele Pulls sehen denselben Stand, halten beide den Deckel für eingehalten und geben beide aus; der Deckel greift um die parallel ausgegebene Summe zu spät.
- Jeder DataForSEO-Pull bekommt:
  - `--budget-cap` aus `config.json > dfs_budget_usd`
  - `--location-code` und `--language-code` aus `config.market()`
  - `--run-id`, `--run-date`, `--account-slug` und `--workspace`
- **Die beiden Markt-Schalter haben keinen Vorgabewert.** Ein still angenommenes Deutschland liefert für einen Shop in einem anderen Markt plausible Zahlen aus dem falschen Land.

Meldet ein Pull `BudgetExceeded`:

- Diese Quelle wird `skipped` mit dem Grund aus der Meldung, **nicht** `failed`. Der Deckel ist eine Entscheidung, kein Defekt.
- Die **übrigen DataForSEO-Quellen ebenfalls `skipped`**, mit demselben Grund und ohne weiteren Versuch; das Ergebnis steht schon fest.
- Alle anderen Quellen laufen normal weiter.
- Gate A weist die Lücke aus wie jede andere, mit der bis dahin verbrauchten Summe aus dem Ledger.

**Der Deckel ist die Bremse, nicht die Sandbox.**

- Zum Ausprobieren `--budget-cap` klein setzen und echt laufen lassen.
- `--sandbox` liefert Dummy-Werte und testet nur die Verkabelung. Ein Snapshot daraus enthält `"sandbox": true` und gehört in keinen Kundenordner.

### Parallelität, zwei Bahnen

**Bahn 1: Skript-Pulls im Hintergrund.**

- `pull-ga4`, `pull-gsc`, `pull-cwv`, `crawl-site`, `check-geo` bei `geo_method: "api"`, dazu `pull-shopify` (kein Script, aber auch kein Mensch nötig).
- Dürfen gleichzeitig laufen, als parallele Hintergrundprozesse oder parallele Subagents, je einer pro Quelle.
- Jeder bekommt Lauf-ID, Quelle und Zielordner und meldet nur sein Ergebnis zurück (Regel oben: `state.json` nie selbst schreiben).

**Bahn 2: Foreground, nacheinander, weil sie einen Browser steuern.**

- `capture-screens` (Kaufweg bis zur Zahlungsauswahl, automatisiert, in einem sichtbaren Browser) und `check-geo` bei `geo_method: "browser"`.
- Sie laufen in der Hauptsitzung statt in einem Hintergrund-Subagent, weil ein Browser nicht von mehreren Stellen parallel steuerbar ist.
- Sie blockieren die übrigen Pulls nicht.

**Der Kaufweg wird nie im Lauf erfragt.**

- Die Aufnahme legt einen echten Testwarenkorb im Produktivshop an. Daraus entsteht ein Abandoned-Checkout-Datensatz, auf den ein E-Mail-Werkzeug eine Warenkorbabbrecher-Strecke auslösen kann.
- Diese Entscheidung fällt einmal je Kunde im Setup, nicht als Rückfrage mitten in Phase 1.
- `config.checkout_capture()` liefert `None`, wenn das Feld fehlt. Dann:
  - der Kaufweg läuft **nicht**
  - die Lücke steht in Abschnitt 13
  - am Ende von Phase 1 einmal melden: *"checkout_capture fehlt in der Config, der Kaufweg blieb aus. Mit `true` im Setup kommt er beim nächsten Lauf dazu."*
  - keine Frage dazu stellen

**Nur ein Schritt braucht einen Menschen:** der Login bei `check-geo` mit `geo_method: "browser"` ("macht der Mensch, nie der Agent", check-geo/SKILL.md).

- Der Kaufweg braucht keinen: er liest vor jedem Schritt die Seite, bricht bei einer unerwarteten Stufe ab statt zu raten und hält an der Zahlungsart-Auswahl.
- `checkout_capture: false` in der Config überspringt ihn ganz.

**Fehler bleiben je Quelle isoliert** (Grundregel des Plugins, `CLAUDE.md`):

- `run_state.set_source(source, "failed", reason=..., today=today)`, die übrigen Quellen laufen weiter.
- Erst wenn jede Quelle scheitert, hat Gate A nichts zu zeigen; das ist dann selbst der Befund.

### `screens.json` ist ein eigener Schritt dieser Phase, kein Nebeneffekt

- `capture-screens` schreibt laut eigenem Ablauf `reporting/runs/<run-id>/screens.json` selbst. Darauf nicht verlassen.
- **Diese Orchestrator-Ebene schreibt oder prüft den Index selbst**, direkt nachdem `capture-screens` fertig ist.
- Quelle: die Bild-Einträge und die `not_configured`-Liste aus Schritt 4 bis 6 von `capture-screens`.
- Felder: `page_type`, `device`, `captured_at`, `source_url`, `path`, optional `manual`.
- Erst danach gilt die Quelle als erledigt: `run_state.set_source("screens", "done", file="reporting/runs/<run-id>/screens.json", today=today)`.
- Ohne diesen Schritt finden die Analysen in Phase 2 (und eine spätere Content-Analyse) keine Bilder, ohne dass ein Fehler erscheint.
- Bei `geo_method: "off"` gilt diese Vorsicht sinngemäß nicht, dort entsteht bewusst kein Snapshot.

**Bei Erfolg der Phase:** `run_state.set_phase('1-raw-data', 'done')`, `run_state.save()`. Direkt danach Gate A.

## Gate A: Datenlage-Blatt

**Artefakt:** `reporting/runs/<run-id>/source-status.md`.

- Diese Orchestrator-Ebene schreibt es aus dem `sources`-Teil von `state.json` und, wo nötig, aus der jeweiligen Snapshot-Datei; "abgeschnitten" steht nur im Snapshot, nicht in state.json.
- Je gezogener Quelle eine Zeile: Status, Grund, gemessener Beginn der Historie, sofern vorhanden.

| Quelle | Status | Grund | Historie ab |
|---|---|---|---|
| ga4 | vorhanden | | 2024-03-01 (`history_from`) |
| gsc | abgeschnitten | API-Grenze, mehr als 16 Monate liefert Google nie | 2025-06-01 (`history_from`) |
| shopify | abgeschnitten | `read_all_orders` fehlt im Grant, Historie hart auf 60 Tage begrenzt | siehe `notes.order_history` |
| geo | vorhanden | | keine Historie möglich, dieser Lauf ist Messpunkt 1 |
| cwv | vorhanden | | 28 Tage Feld, rund 25 Wochen CrUX-Historie |
| crawl | vorhanden | | (kein Zeitraum, Momentaufnahme) |
| screens | vorhanden | | (kein Zeitraum, Momentaufnahme) |

Statuswerte:

| Status | `state.json` | Bedingung |
|---|---|---|
| **vorhanden** | `done` | der Snapshot hat keine einschränkende Notiz |
| **abgeschnitten** | `done` | der Snapshot hat eine Einschränkung (`shopify.json > notes.order_history`, oder ein `history_from` deutlich nach der Anmeldung der GA4-Property bzw. der Search Console); Grund wörtlich aus dieser Notiz |
| **fehlend** | `failed` | Grund ist der gemeldete Fehlergrund der Quelle |
| **übersprungen** | `skipped` | die Pull-Skill existiert in dieser Stufe noch nicht (`esp`, `meta` und `reviews`, siehe oben) oder `geo_method: "off"` hat GEO abgeschaltet |

- Übersprungene Quellen als kurze Liste unter der Tabelle, nicht als Tabellenzeile je Quelle. Die Tabelle bleibt den gezogenen Quellen vorbehalten, bis zu fünfzehn.

**Die Zeile ga4 enthält die beiden Prüfungen aus `--audit-checks`.**

- Ein auffälliges Bot-Profil mit Anteil und Zeiträumen in den Grund (`bot_profiles.profiles[].share_of_sessions`, `.windows`).
- Doppelt gezählte Stufen mit Beginn und, wo gemessen, Ende (`senders.double_counted_events`, `senders.onset`, `senders.ended`).
- Steht `senders.ended`, ist die Doppelzählung vorbei und der Zeitraum zerfällt in Abschnitte. Das in den Grund schreiben, sonst gilt die Warnung scheinbar auch für die letzten Tage.
- Beides bestimmt, auf welchen Zahlen Phase 2 rechnet; der Mensch soll es vor der Freigabe sehen, nicht erst im Report.
- Ist eine der beiden Prüfungen nicht gelaufen (`bot_profiles.checked` oder `senders.measurable` falsch): ga4 auf **abgeschnitten**, die Notiz als Grund; jede GA4-Rate stünde sonst auf ungeprüften Sitzungen.

**Dann hält der Lauf an.**

1. Datenlage zeigen.
2. Ausdrücklich fragen, ob Phase 2 (Analysen) starten soll.
3. **Nie von selbst mit Phase 2 fortfahren, auch nicht, wenn alle gezogenen Quellen "vorhanden" melden.** Dieses Gate gehört zum Kern der Skill.
4. Bei "nein" oder ohne Antwort bleibt `state.json` unverändert, Phase `1-raw-data` auf `done`. Ein späterer Aufruf von `/ptai-ecom:audit` setzt über `next_phase()` bei Phase 2 an, ohne eine Quelle erneut zu ziehen.

## Phase 2: Analysen

- Die Analyse-Subagents starten parallel, je einer pro Disziplin: ein Aufruf pro Subagent in derselben Nachricht, damit sie gleichzeitig laufen.
- Jeder bekommt im Aufruf-Prompt die Lauf-ID.
- Jeder liest nur die feste Dateiliste aus seiner eigenen Definition unter `reporting/data/<run-id>/`, nie das ganze Verzeichnis (Spec Abschnitt 13: "Die Analysen lesen nicht alles").
- Alle elf Subagents sind aktiv (`agents/audit-*.md`, Ziel-Ausbaustufe aus Spec Abschnitt 8).

| Subagent | Disziplin | Liest |
|---|---|---|
| `audit-data-quality` | Datenqualität und Messung | `shopify.json`, `ga4.json`, `gsc.json`, `crawl.json` |
| `audit-commerce` | Handel und Wirtschaftlichkeit | `shopify.json` |
| `audit-traffic` | Traffic und Kanäle | `ga4.json`, `gsc.json`, `geo.json` |
| `audit-seo-technical` | SEO technisch | `crawl.json`, `gsc.json`, `cwv.json`, `catalog.json` |
| `audit-seo-content` | SEO Inhalte und Sortiment | `dfs-rankings.json`, `dfs-keywords.json`, `dfs-competitors.json`, `catalog.json`, `gsc.json`, `crawl.json` |
| `audit-geo` | GEO | `geo.json`, `crawl.json` |
| `audit-sea` | SEA | `ads.json`, `dfs-shopping.json`, `dfs-rankings.json`, `catalog.json` |
| `audit-conversion` | Shop und Conversion | `ga4.json`, `screens.json`, `crawl.json`, `shop-tech.json`, **plus `lens-purchase-path`** |
| `audit-content-brand` | Content und Marke | `catalog.json`, `crawl.json`, `screens.json`, **plus `lens-assortment`** |
| `audit-competition` | Wettbewerb | `dfs-competitors.json`, `dfs-backlinks.json`, `dfs-shopping.json`, `dfs-rankings.json`, `geo.json` |
| `audit-trust` | Trust und Compliance | `crawl.json`, `screens.json`, `shop-tech.json`, **plus `lens-trust`** |

### Drei Analysen laden eine Linse

| Subagent | Linse | Inhalt der Linse |
|---|---|---|
| `audit-conversion` | `lens-purchase-path` | Sieben-Punkte-Rahmen aus `marketing-skills:cro` |
| `audit-content-brand` | `lens-assortment` | Produktseiten-Teil aus `claude-seo:seo-ecommerce` |
| `audit-trust` | `lens-trust` | acht Pflichtangaben-Punkte und die Regel, dass eine Feststellung kein Rechtsurteil ist |

- Nur diese drei haben `Skill` im Frontmatter. Ein Subagent mit `tools: Read, Write, Bash` kann keine Skill laden; ein Skillname im Prompt bliebe dann ohne Wirkung.
- Ohne geladene Linse arbeitet die Analyse mit frei formulierten Fragen und übersieht Punkte, auch wenn alle Screenshots vorliegen.
- **Im großen Audit schreibt die Linse keine eigene Datei.**
  - In `audit-light` liefert sie `L<n>-<lens>.json` im Verkaufs-Schema mit `crit`, `warn` und `ok`.
  - Hier schreibt der Subagent, nach dem Befund-Schema seiner eigenen Definition. Die Übersetzung steht dort.
- **`audit-trust` ist die Disziplin für `lens-trust`.**
  - Pflichtangaben passten in keine der zehn Disziplinen und haben deshalb die elfte (`trust`).
  - Eigene Sektion im Report: Nummer 6, direkt hinter der Conversion, weil beide fragen, was einen Menschen vom Kauf abhält.

### Was der Kunde eingeordnet hat, geht mit in jeden Prompt

- Der Audit misst von außen und kennt fachliche Gründe nicht (Beispiel: Produkte sind nicht kaufbar, weil sie ausverkauft sind, nicht wegen eines technischen Fehlers).
- `reporting/context.json` enthält die Aussagen des Kunden zu früheren Befunden.
- Phase 2 hängt sie an den Prompt jedes Subagents:

```bash
python3 -c "
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import context
eintraege = context.load('.')
fehler = context.validate(eintraege)
if fehler:
    print('FEHLER in reporting/context.json:'); print('\n'.join(fehler))
else:
    print(context.as_prompt(eintraege))
"
```

- Meldet die Prüfung Fehler: **die Datei reparieren, bevor Phase 2 startet**, nicht überspringen. Eine still wirkungslose Kundenaussage gilt auf beiden Seiten als angekommen.
- Ist die Ausgabe leer: den Abschnitt im Prompt ganz weglassen. Ein leerer Abschnitt suggeriert, es gäbe Kundenwissen, das nicht gepasst hat.
- Was der Subagent damit tut, steht in seiner Definition (Ausgabeschema-Punkt 8):
  - Ein Befund, den ein Eintrag erklärt, wird nicht erneut gestellt; er entfällt oder wird auf die nicht erklärte Teilmenge eingeengt.
  - Widerspricht ein Eintrag den Zahlen, gelten die Zahlen, und der Widerspruch steht sichtbar im Befund.

**Einträge entstehen aus dem Gespräch, nicht über eine Oberfläche.**

- Der Kunde antwortet auf einen Befund mit dessen Kennung ("HDL-07 stimmt so nicht, die sind ausverkauft"), im Chat, per Mail oder im Termin.
- Wer den Audit führt, legt daraus einen Eintrag an:

```bash
python3 -c "
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import context
print(context.add('.',
    'Die nicht kaufbaren Produkte sind ausverkauft, kein technischer Fehler.',
    ['HDL-07', 'HDL-08'], 'reason', 'Termin 08.09.2026, Mara'))
"
```

| `kind` | Bedeutung |
|---|---|
| `reason` | der fachliche Grund hinter einem Zustand |
| `decision` | bewusst so, soll so bleiben |
| `planned` | läuft schon |
| `correction` | unsere Messung war falsch |

- Einträge nur anhängen, nie ersetzen. Eine geänderte Einschätzung ist ein neuer Eintrag, der den alten benennt.

**Weitere Regeln für Phase 2:**

- **Ein Subagent startet auch, wenn seine Quellen in Phase 1 fehlten.** Er meldet die Lücke als `blocked_questions`; Gate B braucht diese Meldung, um zu zeigen, was der fehlende Zugang kostet. Nicht vorher aussortieren.
- **`audit-conversion`, `audit-content-brand` und `audit-trust` lesen Screenshots** (Bilddateien im Kundenordner, nicht nur JSON). Keine Sonderbehandlung nötig; sie laufen länger als die übrigen acht, das ist kein Hänger.
- `audit-data-quality` steht im fertigen Report zuerst: ist die Messung kaputt, ist jede Zahl der übrigen zehn eine Behauptung, kein Befund (Spec Abschnitt 8, Pilot-Beleg: 70 Prozent Zuordnungslücke zwischen Shopify und GA4).

**Modell je Subagent:**

- Zehn der elf haben `model: sonnet` im Frontmatter: sie rechnen und klassifizieren gegen ein festes Ausgabeschema (Anteile bilden, Statuscodes einordnen, Kanalanteile gegen Schwellen halten, `null` von 0 unterscheiden).
- `audit-data-quality` hat bewusst keinen Eintrag und erbt das Session-Modell, meist das stärkere. Er deutet Widersprüche zwischen vier Quellen (ist die Lücke zwischen Shopify-Bestellungen und GA4-Purchase-Events ein Zuordnungsverlust oder ein anderer Bestellweg?) und entscheidet damit über die Gültigkeit aller übrigen Analysen. Das fehlende `model:` ist Absicht.
- `scripts/tests/test_agent_frontmatter.py` hält diese Tabelle und die Agent-Dateien synchron und prüft, dass kein Agent eine Eingabedatei nennt, die kein Pull schreibt.
- Der Orchestrator läuft immer im Session-Modell; eine `SKILL.md` kennt kein `model:`-Frontmatter.

**Artefakt:** `reporting/runs/<run-id>/findings/<disziplin>.json`, von jedem Subagent selbst geschrieben.

- Dateien: `data-quality.json`, `commerce.json`, `traffic.json`, `seo-technical.json`, `seo-content.json`, `geo.json`, `sea.json`, `conversion.json`, `content-brand.json`, `competition.json`, `trust.json`.
- Fünf Felder je Befund: `statement`, `evidence`, `effect`, `confidence`, `effort`, dazu `blocked_questions`.
- Seit dem 02.10.2026 schreiben alle elf zusätzlich `facts`, `evidence_text`, `url` und `proof` nach dem Vertrag `reference/finding-format.md`. Conversion, Content und Vertrauen legen in `proof` zusätzlich Bild-Aufträge an.
- Agents mit Kriterienliste (`audit-seo-technical`, `audit-seo-content`, `audit-geo`, seit 27.09.2026) schreiben zusätzlich `criteria_version` und `criteria`: je Kriterium genau eine Zeile mit `violated`, `passed`, `not_measurable` oder `not_applicable`.
- Ein Kriterium erzeugt seine Zeile auch, wenn alles in Ordnung ist. Das macht den prüfbaren Teil wiederholbar; ohne Liste teilten zwei Läufe desselben Moduls auf demselben Shop nur gut ein Drittel ihrer Befundthemen.

**`findings/geo.json` ist nicht `data/<run-id>/geo.json`.** Gleicher Dateiname, anderer Ordner: das eine ist der Befund des Subagenten, das andere der gelesene Rohdaten-Snapshot. Phase 3 liest den Befund.

**Bei Fehler:**

- Ein Subagent, der abstürzt oder keine Datei schreibt, bleibt isoliert. Die übrigen laufen weiter, Gate B weist die fehlende Disziplin mit Grund aus; der Lauf stoppt nicht.
- Fehlt einem Subagenten eine Eingabedatei (Quelle in Phase 1 "fehlend" oder "übersprungen"), nennt er das als eigenen Punkt, nie als geratene Zahl.

**Der Prompt nennt den Befund-Vertrag mit vollem Pfad.** Jeder Agent liest `reference/finding-format.md` vor dem ersten Befund. Im Kunden-Workspace fehlt die Datei; der Aufruf-Prompt nennt deshalb `${CLAUDE_PLUGIN_ROOT}/reference/finding-format.md`, wie bei `measures.py` in Phase 3.

### Belegbilder: `shoot_proof.py`

**Nach den Analysen, vor der Abnahme.**

- Die Agents für Conversion, Content und Vertrauen schreiben keine Bilder, sondern Aufträge (`capture` in einem `image`- oder `phone`-Baustein).
- Das Skript nimmt sie auf, lehnt dabei den Cookie-Dialog ab und schreibt das Ergebnis neben den Auftrag:

```bash
uv run --quiet --with playwright==1.58.0 python \
  "${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/shoot_proof.py" \
  --run reporting/runs/<run-id>
```

- Die Bilder liegen danach in `reporting/runs/<run-id>/proof/`, von Git ignoriert, und gehen mit `publish` in den Bucket.
- Einzelheiten: Skill `capture-screens`, Abschnitt Belegbilder.

**Rückgabewert 1: ein Auftrag ist offen.** Das Skript nennt Befund und Grund.

| Fall | Vorgehen |
|---|---|
| Ein Ziel trifft kein oder mehrere Elemente | den Auftrag in der Befund-Datei schärfen (etwa einen Text durch einen Selektor ersetzen) und das Skript erneut ausführen; es nimmt nur offene Aufträge auf |
| Etwas aus `absent` ist zu sehen | der Mangel ist behoben; den Bild-Baustein streichen; hält der Befund ohne Bild nicht mehr, entfällt er |
| Der Cookie-Dialog lässt sich nicht ablehnen | kein Bild mit Dialog; den Bild-Baustein streichen und den Befund aus den Zahlen belegen |

- `publish` lädt keinen Lauf mit offenem Auftrag hoch.
- Ein Befund ohne Bild ist gültig; ein Bild, das den beschriebenen Zustand nicht zeigt, nicht.

**Bei Erfolg:** `run_state.set_phase('2-analyses', 'done')`, `run_state.save()`. Direkt danach Gate B.

## Die Abnahme: `audit.qa`

**Läuft vor Gate B und noch einmal am Ende von Phase 4.** Die Prüfungen laufen als Script, weil Regeln in dieser Skill nur wirken, soweit eine Sitzung sie liest.

```bash
python3 -m audit.qa --workspace . --run-id <run-id> --phase 2
```

Prüft ohne Urteil:

- Schema und Pflichtfelder je Befund
- Schweregrad aus den drei erlaubten Stufen
- Ersatzumlaute
- Werkzeugsprache in Feldern, die der Kunde liest
- die Selbstprüfung des Crawlers
- gedrosselte Seiten
- ob der Shop eine GA4-Mess-ID lädt, die nicht zur gezogenen Property gehört

Ergebnis:

- **Rückgabewert 1: nicht freigeben.**
- Warnungen allein brechen nichts ab; sie verlangen einen Blick.
- Am Ende listet das Script, was ein Mensch mit Urteil entscheiden muss: die Zahlen der ersten Seite gegen die Wirklichkeit, die Kennungen, ob jedes Kapitel auch nennt, was gut ist.
- **Keine dieser Prüfungen in den Aufruf-Prompt schreiben.** Eine von Hand mitgegebene Prüfung fehlt beim nächsten Lauf.

### Die Belegprüfung: `audit.evidence`

Direkt nach `audit.qa`, ebenfalls als Script:

```bash
python3 -m audit.evidence --workspace . --run-id <run-id>
```

- `qa` prüft, ob ein Befund ein `evidence`-Feld **hat**. `evidence` prüft das Feld gegen den Lauf:
  - existiert die genannte Snapshot-Datei, und enthält sie den genannten Pfad?
  - nennt ein Befund ein Bild: steht es im Screenshot-Index, und liegt es auf der Platte?
- Das ist das Beleg-Gate aus `audit-light`, übertragen auf einen Lauf, der überwiegend aus Snapshots misst. Dort wird jeder Befund mit URL live gegen die Seite geprüft; hier zeigen Belege auf Felder wie `crawl.json > summary.max_click_depth`, geprüft wird die Auflösung, nicht ein Abruf.
- Ein Beleg ins Leere wirkt wie eine widerlegte Behauptung, sieht aber aus wie ein Beleg.

**Dieselbe Prüfung kontrolliert die Kriterienlisten.**

- Für jede Befund-Datei, deren Agent einen Abschnitt "Kriterienliste" hat, liest sie die erwarteten IDs aus der Agent-Datei.
- Sie meldet IDs, die fehlen, doppelt stehen, unbekannt sind, ein ungültiges Ergebnis haben oder als `violated` auf keinen Befund zeigen.
- Eine unvollständige Liste setzt den Exit-Code auf 1 wie ein Beleg ins Leere. Die Analyse wird wiederholt, nicht von Hand ergänzt.
- Die Zählung je Disziplin (verletzt, erfüllt, nicht messbar, entfällt) steht im Bericht und wird an Gate B vorgelegt.

Verdikte:

| Verdikt | Bewertung |
|---|---|
| `resolved` | in Ordnung, das Feld existiert |
| `prose` | in Ordnung, Beleg ohne Feldbezug (etwa eine eigene Messung); wird gezählt, nicht bemängelt |
| `external` | in Ordnung, Beleg ohne Feldbezug (etwa eine URL); wird gezählt, nicht bemängelt |
| `missing_field` | Fehler, nennt die Kennung des Befunds |
| `missing_file` | Fehler, nennt die Kennung des Befunds |
| `missing_image` | Fehler, nennt die Kennung des Befunds |

**Rückgabewert 1: dieser Befund geht nicht an den Kunden, bis der Beleg stimmt.** Genau zwei Auswege:

1. den Beleg auf das Feld richten, das die Zahl enthält
2. den Befund streichen

Den Beleg unverändert lassen und weitermachen ist keiner.

- Beispiel eines Fehlers: ein Befund nannte das Bild `checkout-warenkorb.png`, der Index führte `warenkorb-gefuellt.png`.

### Ein Aufruf, drei Dateien

```bash
python3 -m audit.report_build --workspace . --run-id <run-id> --pdf
```

- Schreibt `audit.html` (Druckfassung) und `audit-web.html` (Web-Fassung mit Navigation und Filter) und rendert das PDF.
- **Alle drei aus einem `content()`-Aufruf**, damit Zahlen und Befunde nicht zweimal abgeleitet werden und zwischen den Fassungen abweichen.
- Nicht in zwei Aufrufe aufteilen; sonst fehlt leicht eine Fassung, während der Lauf fertig aussieht.
- `--no-web` lässt die Web-Fassung weg, wenn nur die Druckfassung gebraucht wird.

## Gate B: Befunde vorlegen

Bevor etwas in Baseline oder Maßnahmen-Backlog geht (`baseline.md` und `measures.md` gehen ganz oder in Auszügen an den Kunden), die Befunde aus allen vorliegenden `findings/<disziplin>.json` zeigen:

- je Disziplin die Anzahl Befunde
- die mit `confidence: "hypothesis"` getrennt; sie werden nie Maßnahme, sondern Test (Spec Abschnitt 9)
- bei fehlenden Disziplinen der Grund aus Phase 2

**Getrennt davon die `blocked_questions` je Disziplin**, gruppiert nach der fehlenden Datei.

- Das sind Kernfragen, die mangels Eingabe offen blieben, keine Befunde über den Shop.
- Sie gehen nicht einzeln in den Backlog: fünf offene Fragen wegen einer fehlenden Datei sind eine Lücke, nicht fünf.
- Am Gate zeigen sie, wie viel des Audits diese Lücke kostet. Danach entscheidet sich, ob Phase 3 jetzt läuft oder nach dem Nachziehen der Quelle.

**Welche Analyse zu dünn ist, bestimmt das Script.**

- `audit.evidence` zählt je Disziplin Befunde gegen `blocked_questions` und benennt jede, die mindestens so viel offenlassen musste, wie sie beantwortet hat.
- Das ist die Abdeckungs-Regel aus `audit-light`, übertragen auf einen Lauf ohne Score. Dort bekommt eine geblockte Linse keinen Punktwert, sondern eine ausgewiesene Lücke, weil sie sonst dieselben 92 Punkte bekäme wie ein guter Shop.

Für eine so benannte Disziplin gibt es genau zwei Auswege:

1. **Die fehlende Quelle nachziehen** und die Analyse erneut laufen lassen. Regelfall, wenn die Lücke an einer Datei hängt, die es geben könnte.
2. **Die Lücke in den Report schreiben**, im Kapitel dieser Disziplin, in einem Satz, der sagt, was nicht geprüft werden konnte und warum.

**Ohne eins von beidem weiterzulaufen ist keiner.** Sonst liest sich das Kapitel wie ein Befund über den Shop, obwohl es ein Befund über den Lauf ist.

**Dann hält der Lauf erneut an** und fragt ausdrücklich, ob Phase 3 (Synthese) starten soll.

- Wie bei Gate A: kein automatisches Weiterlaufen.
- Bei "nein" bleibt `state.json` bei Phase `2-analyses` auf `done`; ein späterer Aufruf setzt über `next_phase()` bei Phase 3 an.

## Phase 3: Synthese

Reihenfolge:

1. Baseline blockweise schreiben (Schritt 1 und 2).
2. Befunde in den Maßnahmen-Backlog überführen (Schritt 3 und 4).

### Schritt 1: Baseline blockweise schreiben

Für jeden der zehn Blöcke aus `baseline.BLOCKS`, in dieser Reihenfolge:

| Block | Quelle(n) | Quell-Schlüssel im `state` | seit |
|---|---|---|---|
| `commerce` | `shopify.json` | `shopify` | ja |
| `traffic` | `ga4.json` | `ga4` | ja |
| `conversion` | `ga4.json` plus `shopify.json` | `ga4`, `shopify` | ja |
| `seo_search` | `gsc.json` plus `crawl.json` | `gsc`, `crawl` | ja |
| `seo_visibility` | `dfs-rankings.json` plus `dfs-keywords.json` plus `dfs-backlinks.json` | `dfs_rankings`, `dfs_keywords`, `backlinks` | ab Stufe 2 |
| `geo` | `geo.json` | `geo` | ja |
| `sea` | `ads.json` | `ads` | ab Stufe 2 |
| `tech` | `cwv.json` plus `crawl.json` | `cwv`, `crawl` | ja |
| `catalogue` | `catalog.json` | `catalogue` | ab Stufe 2 |
| `measurement` | errechnet aus `shopify.json` und `ga4.json`, kein eigener Pull | `shopify`, `ga4` | ja |

- Einen Block nur schreiben, wenn **alle** seine Quell-Schlüssel aus der Spalte "Quell-Schlüssel im `state`" auf `done` stehen; Prüfung je Schlüssel mit `not run_state.source_open(source)`.
- Fehlt eine Quelle: den Block nicht schreiben. Er bleibt leer für den Nachtrag-Modus (siehe "Ein Audit läuft genau einmal je Shop").
- Ein halb gefüllter Block ist schlimmer als ein leerer: er ist eingefroren und lässt sich nie mehr vervollständigen.
- `baseline.write_block()` verweigert ein leeres `values`; das bestätigt diese Regel.
- `seo_visibility`, `sea` und `catalogue` haben seit dem 07.09.2026 ihre Quell-Schlüssel (`dfs_rankings`, `dfs_keywords`, `backlinks`, `ads`, `catalogue`) und folgen derselben Regel. Ein fehlender Google-Ads-Zugang oder ein erreichter DataForSEO-Budgetdeckel ist kein Sonderfall, sondern eine ausgefallene Quelle wie jede andere.
- `measurement` hat keinen eigenen Pull, sondern wird aus zwei gezogenen Quellen errechnet (Schritt 2). Geschrieben wird er trotzdem erst, wenn `shopify` und `ga4` `done` sind.

**Jeder Block enthält seine Herkunft.**

- `write_block()` verlangt neben `values` ein `sources`-Dict: je Quell-Schlüssel des Blocks ein Eintrag mit `pulled_at` und, sofern die Quelle einen Zeitraum abdeckt, `period`.
- `pulled_at` steht in `run_state.sources[source]`, `period` im Snapshot der Quelle (`period`, bei den Maximalzeitraum-Pulls `period` plus `history_from`).
- Der Orchestrator stellt es zusammen:

```python
sources = {}
for source in block_source_keys:
    entry = run_state.sources[source]
    provenance = {"pulled_at": entry["pulled_at"]}
    snapshot = json.loads((data_dir / entry["file"]).read_text(encoding="utf-8"))
    if snapshot.get("period"):
        provenance["period"] = snapshot["period"]
    sources[source] = provenance

baseline.write_block(workspace, block, values, run_id=run_id, today=today,
                     sources=sources, trust=trust,
                     known_gaps=("repeat_rate", "return_rate"))
```

- Grund: Festschreibetag und Ziehtag sind im Erstlauf gleich, beim Nachtrag verschieden. Ohne Trennung liest ein späterer Vergleich das Festschreibedatum als Messzeitpunkt.
- Der abgedeckte Zeitraum gehört dazu, weil "Umsatz je Monat über die volle Historie" ohne Anfang und Ende keine Aussage ist.
- `baseline.render()` zeigt beides je Block als eigene Tabelle.

### Eine kaputte Messung wird eingefroren, nicht weggelassen

**Die Zahl einer falschen Messung kommt trotzdem in die Baseline.**

- Sie ist der Zustand, auf dem die Entscheidungen des Kunden beruhten.
- Ohne sie fehlt später die Erklärung für den Sprung nach der Reparatur der Messung.

**Gefährlich ist sie als Nenner.** Eine Conversion Rate aus einer um Faktor 3,6 überhöhten Sitzungszahl sieht aus wie eine Kennzahl, ist aber keine, und gibt den Fehler unsichtbar an jede Folgerechnung weiter. `write_block()` erzwingt die Unterscheidung über den Pflichtparameter `trust`:

```python
trust = {
    "sessions": {
        "status": "contaminated",
        "reason": "Analytics zählt 3,64-mal so viele Besuche wie der Shop "
                  "selbst als Menschen zählt",
        "break": "2026-06",
        "finding": "MES-03",
    },
    "conversion_rate": {"derived_from": ["sessions"]},
}
```

- Der erste Eintrag friert die kaputte Zahl bewusst ein.
- Der zweite scheitert mit `ContaminatedInput`, weil er sie als Nenner nutzt.

| Status | Bedeutung |
|---|---|
| `measured` | gemessen und brauchbar. Vorgabe, wenn ein Wert keinen Eintrag hat |
| `contaminated` | gemessen, aber nachweislich falsch. Braucht `reason`, möglichst `break` und `finding` |
| `not_measurable` | gar nicht messbar, der Wert ist `None` und gehört zusätzlich in `known_gaps` |

- **`trust={}` ist erlaubt und heißt "alles gemessen".** Wie beim Preistest wird kein Urteil erzwungen, sondern dass der Aufrufer hingesehen hat; eine durchgewunkene kaputte Messung ist dann sichtbar.
- **Das `break`-Datum ist Pflicht für den späteren Vergleich.** Der Report nach der Reparatur schreibt dann "die Reihe bricht im Juni 2026, davor und danach ist nicht vergleichbar" statt "Sitzungen minus 70 Prozent". Ohne Datum sieht eine reparierte Messung aus wie ein Einbruch.
- **Eine belastbare Ersatzquelle hat Vorrang.** Misst eine zweite Quelle dieselbe Sache sauber, kommt sie in den Block und die kaputte daneben. Beispiel Sitzungen: die Zählung des Shops, die automatisierten Verkehr selbst trennt, neben der Zahl aus Analytics. Der Nullpunkt enthält dann den echten Wert **und** den, den der Kunde bisher gesehen hat.

### Korrekturen nach dem Einfrieren

**Der Wert bleibt, der Vermerk wird ergänzt.**

- Ein geschriebener Block ist unveränderlich, das Wissen über seine Zahlen nicht (etwa: ein Betrag steht in anderer Währung, eine Begründung war zu grob).
- Weder den Wert ändern noch `reason` umschreiben.
- Stattdessen im Vermerk des Werts in `baseline.json` von Hand einen Eintrag unter `corrections` ergänzen, Datum als `JJJJ-MM-TT`:

```json
"revenue_analytics": {
  "status": "contaminated",
  "reason": "Zwei Mess-IDs zählen jeden Kauf doppelt.",
  "break": "2026-05",
  "finding": "MES-01",
  "corrections": [
    {"date": "2026-10-15",
     "note": "Doppelt gezählt wird nur ein Teil der Käufe, nicht jeder, belegt am 14.10.2026. Die Begründung oben ist damit überholt."}
  ]
}
```

- Neue Korrekturen ans Ende der Liste, ältere bleiben. So bleibt nachvollziehbar, was wann bekannt war, und die ursprüngliche Begründung lesbar.
- **Ein Wert ohne Vermerk, der sich später als falsch erweist,** bekommt einen neuen Eintrag mit `status`, `reason`, `break` und `finding` und eine Korrektur mit dem Tag, an dem der Fehler belegt wurde. Ohne dieses Datum wirkt es, als sei der Fehler schon beim Einfrieren bekannt gewesen.

Danach `baseline.render(workspace)` ausführen.

- `baseline.md` zeigt den Status in Klammern hinter der Zahl, darunter als Zitat Grund, Monat des Bruchs, Befund und jede Korrektur mit Datum. Bei `measured` heißt der Grund dort "Hinweis".
- Bei einer Zeitreihe oder Liste steht das Zitat zwischen Überschrift und Zahlen.
- Nennt ein Vermerk einen Wert, den es in `values` nicht gibt, oder einen unbekannten Status, bricht `render()` ab; ein vertippter Schlüssel ließe den Vermerk sonst still verschwinden.

**Die Datei mit Python `json` zurückschreiben:** `json.dumps(data, indent=2, ensure_ascii=False)` plus Zeilenumbruch, wie `baseline.py` sie anlegt. Andere Werkzeuge schreiben `0.0` als `0` und ändern damit Werte eingefrorener Blöcke in der Schreibweise.

### Die Sperre: ein laufender Test friert keine Conversion ein

**Die Sperre ist im Code verankert.**

- `baseline.write_block()` verlangt für `commerce` und `conversion` den Parameter `price_test`; ohne ihn scheitert der Aufruf.
- Der Wert kommt aus `gates.price_test_verdict(crawl, findings)`:

```python
from audit import gates, context

crawl = json.loads((data_dir / "crawl.json").read_text(encoding="utf-8"))
findings = json.loads((run_dir / "findings" / "data-quality.json").read_text(encoding="utf-8"))
verdict = gates.price_test_verdict(crawl, findings.get("findings"),
                                   context=context.load(workspace))

baseline.write_block(workspace, "conversion", values, run_id=run_id, today=today,
                     sources=sources, price_test=verdict)
```

- Pflichtangabe statt Schalter: ein Schalter, den der Aufrufer selbst auf "blockiert" setzen müsste, erzwingt nichts. **Die fehlende Prüfung ist der Fehler**; Vergessen scheitert damit.

| `verdict` | Was passiert |
|---|---|
| `checked: False` | Abbruch. "Nicht geprüft" ist keine Freigabe |
| `running: True` | `PriceTestRunning`, der Block wird ausgesetzt, Grund in den Gate-Bericht |
| `checked: True, running: False` | Block wird geschrieben, der Beleg kommt in sein `as_of` |

`gates.price_test_verdict()` prüft zwei Quellen:

1. inline eingebaute Kennungen und Fremdskripte aus `crawl.json` (ein Werkzeug wie Intelligems steht im Seitenquelltext)
2. die Befunde aus `findings/data-quality.json`, weil `audit-data-quality` in Kernfrage 6 gezielt danach sucht. Diese Quelle ist wichtiger: ein serverseitig ausgespielter Test hinterlässt im Quelltext nichts.

- **Ein negativer Befund ist kein Beweis.** Er heißt "kein bekanntes Werkzeug gefunden", und der Beleg im Block sagt das so.
- Die Markerliste `gates.PRICE_TEST_MARKERS` ist aus Beobachtung entstanden. Ein neu angetroffenes Werkzeug dort ergänzen.

**Ein geladenes Werkzeug ist nicht dasselbe wie ein laufender Preistest.**

- Die Prüfung sieht nur, dass ein Skript ausgeliefert wird, und sperrt dann.
- Ist es nachweislich kein Preistest, den Fund über einen Eintrag in `reporting/context.json` entkräften, mit `price-test` als Anker und der Art `correction` oder `decision`:

```bash
python3 -c "
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import context
print(context.add('.',
    'Von den angelegten Experiences läuft eine, und die testet Inhalte auf einer Seite, keine Preise. Mehrere Abrufe derselben Produktseite lieferten denselben Preis, in den Bestellungen des Messzeitraums kein automatischer Rabatt.',
    ['price-test'], 'correction', 'Eigene Prüfung der Anbieter-Konfiguration, TT.MM.JJJJ'))
"
```

- Der Eintrag kann nur entkräften, nie einen nicht gefundenen Test behaupten. Der Fund bleibt im Beleg des Blocks.
- **Eine Vermutung reicht nicht.** Erst prüfen, was das Werkzeug testet. Bei Intelligems: öffentliche Konfiguration des Shops unter `cdn.intelligems.io/configs/<id>.json`, Feld `hasTestPricing` der gestarteten Experiences.
- Ohne diese Prüfung bleibt die Sperre, auch wenn sie unbequem ist: Handel und Conversion sind die Blöcke, gegen die jeder spätere Relaunch gemessen wird.

Grund der Sperre:

- Unter einem laufenden Preistest sind Conversion Rate und Warenkorbwert ein Mischwert aus zwei oder mehr Varianten.
- Eingefroren vergliche jeder spätere Report gegen einen Durchschnitt über ein Experiment, nicht gegen einen Zustand des Shops.
- Der Befund allein reicht nicht: er geht in den Backlog, die verunreinigte Zahl bliebe trotzdem dauerhaft in der Baseline.

Aufheben und Umfang:

- Aufgehoben wird die Sperre über `--backfill`, sobald der Test beendet und ein sauberes Fenster gemessen ist. Der nachgetragene Block hat dann sein eigenes `as_of` und ist sichtbar ein späterer Messpunkt.
- **Die übrigen Blöcke sind nicht betroffen.** Ein Preistest verändert Conversion und Warenkorbwert, nicht die Zahl der Seiten im Crawl, die Core Web Vitals oder die GEO-Sichtbarkeit.

### Schritt 2: Die Kennzahlen je Block

- Quellfeld und Formel jeder Zahl stehen in `reference/metrics.md`; hier nur der Verweis.
- Diese Skill rechnet nicht selbst. Sie schlägt nach und übernimmt das Ergebnis in die `values` des Blocks.

| Block | Abschnitt in `reference/metrics.md` |
|---|---|
| `commerce` | 1. Shop (`shopify.json`): Umsatz brutto/netto, Bestellungen, AOV, Repeat-Rate |
| `traffic` | 2. Traffic (`ga4.json`): Sessions, Nutzer, Umsatz aus GA4. **Die Monatsreihe kommt aus `by_month[]`, die Kanalanteile daraus aus `by_month[].channels[]`**, nicht aus dem `channels[]` auf oberster Ebene: das ist die Summe über den ganzen Zeitraum, und Spec Abschnitt 10 verlangt "Sessions je Monat und Kanal". Beide unverändert übernehmen, ohne eigene Formel |
| `conversion` | 1. Shop: Conversion Rate gesamt, Micro-Conversion-Funnel; 2. Traffic: Conversion Rate je Kanal |
| `seo_search` | 3. SEO (`gsc.json`): Klicks, Impressionen, CTR, Position. **Je Monat aus `by_month[]`**, zusätzlich die Summe aus `totals`. Spec Abschnitt 10 verlangt "je Monat"; `daily` selbst wandert nicht in die Baseline, dafür ist es zu lang |
| `geo` | 5. GEO (`geo.json`): Brand-Erwähnungsquote, Citation Rate, Share of Voice, Crawler-Zugang, llms.txt |
| `tech` | 4. Core Web Vitals (`cwv.json`): LCP, INP, CLS, Lab-Performance-Score, je Seitentyp aus `pages[]` |
| `seo_visibility` | noch nicht im Katalog, siehe die drei Ausnahmen unten |
| `sea` | noch nicht im Katalog, siehe die drei Ausnahmen unten |
| `catalogue` | noch nicht im Katalog, siehe die drei Ausnahmen unten |
| `measurement` | noch nicht im Katalog, siehe Ausnahme unten |

**Bei Bot-Profil oder zweitem Absender verwenden `traffic` und `conversion` dieselben Zahlen wie Befunde und Report.** `ga4_variants.compare()` rechnet die Raten, die Felder stehen in `ga4.json`.

- **`conversion`:**
  - Gibt es `bot_profiles.without`, kommen Funnel und Conversion Rate je Kanal daraus.
  - Für Stufen und Käufe in `senders.double_counted_events` aus dessen `primary_sender`.
  - Keine Rate aus allen Sitzungen daneben stellen; ihr Nenner ist nachweislich zu hoch.
- **`traffic`:**
  - `by_month[]` gibt es nur aus allen Sitzungen; der Pull zieht keine Monatsreihe ohne das Profil.
  - Die Reihe trotzdem einfrieren, weil der Kunde diese Zahlen gesehen hat.
  - Die Sitzungen je Monat und Kanal bekommen `trust` `contaminated`: `reason` nennt das Profil und seinen Anteil an allen Sitzungen (`bot_profiles.profiles[].share_of_sessions`), `break` den Monat aus dem ersten `windows[].start`, `finding` die Kennung des Befunds zum Bot-Profil.
  - Sitzungen und Kanäle ohne das Profil für den Berichtszeitraum als eigene Werte daneben, aus `bot_profiles.without`.
  - Zählt der Kauf doppelt, bekommt der Umsatz aus GA4 dasselbe, mit `break` aus `senders.onset`.
  - **Hat der zweite Absender aufgehört (`senders.ended`), gibt es zwei Kanten:** den Monat aus `onset` und den Monat aus `ended`. Beide als `break` in die Reihe; ein Vergleich über eine der beiden misst die Umstellung der Messung, nicht die Arbeit.

**Nicht jeder Wert aus Spec Abschnitt 10 ist befüllbar.** Die Lücken stehen so auch in den Analyse-Subagents. Der Block wird trotzdem geschrieben, nur ohne die fehlenden Werte:

| Wert | Block | Regel |
|---|---|---|
| **Retourenquote und Kohorten** | `commerce` | fehlen; `shopify.json` hat in diesem Ausbaustand kein passendes Feld (`agents/audit-commerce.md`, Kernfrage 4 und 6) |
| **Sortimentskonzentration** | `commerce` | noch keine Zeile in `reference/metrics.md`. Bis dahin die Rechnung aus `agents/audit-commerce.md`, Kernfrage 5 (Anteil der Top-3- und Top-10-Titel an `totals.total_sales`), mit Zähler und Nenner, nie als Prozentzahl ohne Beleg |
| **Indexierte Seiten** | `seo_search` | noch keine Formel-Zeile. Auszählung aus `gsc.json > index_sample` (Anteil `verdict: PASS`) oder `crawl.json > pages[].indexable`, mit Angabe, welche Quelle gezählt wurde |
| **Conversion Rate je Gerät** | `conversion` | noch keine Formel-Zeile. `ga4.json > devices[]` führt `sessions`, `total_users`, `purchase_revenue` und `purchases`; Rate = `purchases / sessions` je Gerät, mit Zähler und Nenner. Nicht aus Shopify, dort gibt es keine Aufteilung nach Gerät. Hat ein Snapshot statt `purchases` nur `transactions` (Lauf vor dem 11.09.2026), bleibt der Wert leer, weil GA4 in `transactions` Refunds mitzählt. Nicht schätzen, nicht aus dem Kanal-Wert ableiten |
| **Anteil Nicht-Marken-Klicks** | `seo_search` | Klassifikation aus `agents/audit-traffic.md`, Kernfrage 5 (`gsc.json > top_queries` gegen `geo.json > query_set.brand`), noch ohne Katalog-Zeile |

- Diese fünf Lücken sind der dokumentierte Ausbaustand, kein Fehler. Der Katalog wächst mit den Aufgaben, die eine Formel brauchen, nicht auf Vorrat.

**Jede Lücke anmelden.**

- `write_block()` nimmt seit dem 06.09.2026 `known_gaps`. Jedes Feld mit `None`, das dort fehlt, führt zum Abbruch.
- Grund: ein falscher Quellfeldname liefert `None`, `render()` schreibt "nicht berechenbar", und der Block ist unveränderlich; aus einem Tippfehler würde eine gemessene Lücke.
- `known_gaps` trennt bewusst benannte Lücken von Fehlern.

**Einen fehlenden Wert weglassen, nie als Null schreiben.**

- Ein Block ist unveränderlich, sobald er steht. Eine 0 für Retourenquote oder Conversion Rate je Gerät bliebe für immer eine gemessene Null, und der erste Folgereport rechnet eine Bewegung, die nie stattfand.
- `baseline.render()` schreibt für einen fehlenden Wert "nicht berechenbar". In `values` steht er als `None`, nicht als Zahl und nicht als leerer String.

**Die drei Stufe-2-Blöcke stehen hier statt im Katalog.** Seit dem 07.09.2026 befüllbar; ihre Quellfelder kommen mit den übrigen Nachträgen in `reference/metrics.md`. Bis dahin gilt diese Fassung.

**Block `seo_visibility`** (Spec Abschnitt 10: "Anzahl Ranking-Keywords, Sichtbarkeitsverlauf, verweisende Domains"):

| Wert | Quellfeld | Anmerkung |
|---|---|---|
| Ranking-Keywords gesamt | `dfs-rankings.json > summary.ranked_keywords_total` | der Bestand, **nicht** `ranked_keywords_delivered` und nicht die Länge von `top_keywords` |
| Keywords in den Top 3, Top 10, Top 100 | `dfs-rankings.json > summary.top_3`, `.top_10`, `.top_100` | kumulativ, aus `metrics.organic` gerechnet. `null` heißt "nicht gemessen", nie 0 |
| Geschätzter organischer Traffic | `dfs-rankings.json > summary.etv` | Schätzwert der Datenbank, keine gemessene Sitzung |
| Sichtbarkeitsverlauf je Monat | `dfs-rankings.json > visibility_history[]` | nur vorhanden, wenn der Lauf mit `--with-history` lief. Fehlt er, bleibt der Wert weg, statt aus einem Punkt eine Reihe zu machen |
| Verweisende Domains | `dfs-backlinks.json > summary.referring_domains` | dazu `referring_main_domains`, das ist die Zahl ohne Subdomains |
| Autoritätswert | `dfs-backlinks.json > summary.rank` | DataForSEO-eigene Skala, nur gegen sich selbst über die Zeit vergleichbar |
| Suchvolumen der eigenen Begriffe | `dfs-keywords.json > summary.search_volume_total` | dazu `keywords_without_data`, sonst liest sich die Summe als Vollerhebung |

**Block `sea`** (Spec Abschnitt 10: "Ausgaben je Monat, ROAS, Impression Share, Anteil Ausgaben ohne Conversion"):

| Wert | Quellfeld | Anmerkung |
|---|---|---|
| Ausgaben je Monat | `ads.json > by_month[].cost` | Währung aus `ads.json > currency` mit in den Block, das Konto rechnet nicht zwingend in Euro |
| ROAS je Monat | `ads.json > by_month[].roas` | `null` bei Ausgaben von 0. Nie als 0 schreiben, sonst rechnet der erste Folgereport eine Erholung aus, die es nicht gab |
| Impression Share je Monat | `ads.json > by_month[].search_impression_share` | Summe der Impressionen durch Summe der möglichen, plus die beiden Verlustanteile `search_budget_lost_impression_share` und `search_rank_lost_impression_share` und die Abdeckung `search_impression_share_coverage` |
| Anteil Ausgaben ohne Conversion | `ads.json > summary_search_terms.cost_without_conversion` geteilt durch `summary_search_terms.cost_total` | Zähler, Nenner und `detail_period` mit in den Block. Nie durch die Summe aus `by_month[].cost`: die Monatsreihe geht über die ganze Historie und enthält Performance Max, die Suchbegriffe nicht |

**Block `catalogue`** (Spec Abschnitt 10: "Anzahl Produkte und Collections, Anteil mit vollständigen SEO-Feldern, Anteil Bilder mit Alt-Text"):

| Wert | Quellfeld | Anmerkung |
|---|---|---|
| Produkte gesamt und aktiv | `catalog.json > summary.products_total`, `.products_active` | |
| Collections gesamt | `catalog.json > summary.collections_total` | dazu `collections_without_description` |
| Anteil mit vollständigen SEO-Feldern | aus `catalog.json > summary.products_without_seo_title` und `.products_without_seo_description` gegen `products_total` | **Ein Produkt gilt nur als vollständig, wenn beide Felder da sind.** Die zwei Zähler überschneiden sich, ihre Summe ist deshalb keine Anzahl unvollständiger Produkte. Schreib beide Zähler und den Nenner in den Block, statt eine Summe zu bilden, die zu hoch ist |
| Anteil Bilder mit Alt-Text | `catalog.json > summary.share_images_with_alt` | schon gerechnet. `null` heißt "keine Bilder im Katalog", nicht "kein Bild hat Alt-Text": vor der Deutung `images_total` prüfen |
| Varianten ohne SKU und ohne Einkaufspreis | `catalog.json > summary.variants_without_sku`, `.variants_without_cost` gegen `variants_total` | trägt `catalog.json > notes` den Hinweis, dass keine einzige Variante einen Einkaufspreis hat, gehört er als `known_gap` in den Block: Marge ist für diesen Shop nicht berechenbar |

**Alle drei Blöcke nennen ihre Erhebungsgrenze.**

- DataForSEO-Werte kommen aus einer Datenbank, nicht aus einer Live-Messung (`dfs-rankings.json > notes` sagt das).
- Die Ads-Suchbegriffe decken nur Suche und Shopping ab (`ads.json > summary_search_terms.cost_total` gegen die Ausgaben).
- Die Shopping-Abdeckung ist eine Untergrenze über die geprüften Begriffe, keine Vollerhebung.
- Diese Vermerke gehören in die `sources` des Blocks, nicht in eine Fußnote. `baseline.render()` zeigt sie unter der Blocküberschrift; ohne sie liest der nächste Report die Zahlen als gemessen.

**Ausnahme: die Zuordnungslücke für den Block `measurement`.** Sie steht direkt hier, weil es in `reference/metrics.md` noch keine Zeile gibt; sie kommt in Task 21 in den Katalog.

| Punkt | Inhalt |
|---|---|
| Aussage | welcher Anteil der Shopify-Bestellungen in GA4 nicht als `purchase` ankommt |
| Formel | `1 - (ga4.json > funnel.purchase.events / shopify.json > totals.orders)`, in Prozent |
| Quellfeld | `shopify.json > totals.orders`, `ga4.json > funnel.purchase.events` |
| Beleg für die Formel | dieselbe Rechnung wie Kernfrage 1 in `agents/audit-data-quality.md`, dort mit dem Pilot-Beleg Beispielshop (drei von zehn Bestellungen zugeordnet, 70 Prozent Lücke, dieselbe Größenordnung in GA4) |
| Nicht verwechseln | mit der "Zuordnungslücke Bestellungen" aus `reference/metrics.md` Abschnitt 1. Diese misst die Lücke innerhalb von Shopifys eigener `sessions.conversion_rate` und gehört zum Block `conversion`. Der Block `measurement` enthält nur den Abgleich gegen GA4 |

### Schritt 3: Befunde werden Maßnahmen

Für jede Datei in `reporting/runs/<run-id>/findings/` und jeden Befund darin einmal `measures.create()` aufrufen.

- **`criteria` geht nicht durch `create()`.** Maßnahmen entstehen nur aus `findings`. Ein verletztes Kriterium hat seinen Befund dort, verknüpft über `finding_id`; ein erfülltes ist positive Kontrolle, keine Handlung. Sonst stünde jeder Mangel doppelt im Backlog.
- **`blocked_questions` gehen nicht durch `create()`.**
  - Daraus entsteht **höchstens eine** Maßnahme je fehlender Eingabe, nie eine je Frage.
  - Der Titel nennt die Handlung, die die Lücke schließt ("GA4-Property für das Dienstkonto freischalten lassen"), nicht die offene Frage.
  - Die betroffenen Kernfragen gehören in ihre `evidence`, damit sichtbar ist, was an dieser Freischaltung hängt.
  - Ohne diese Regel entstehen aus zwei fehlenden Zugängen viele Backlog-Zeilen mit derselben Forderung.
- **`create()` ändert `backlog` nicht, es liefert ein neues Dokument.** Den Rückgabewert zuweisen, sonst schreibt `save()` einen leeren Backlog ohne Fehlermeldung:

```python
backlog = measures.load_or_empty(workspace)
for finding in findings:
    backlog = measures.create(
        backlog, title=..., discipline=..., evidence=...,
        confidence=..., leverage=..., effort=..., responsible=...,
        data_source=..., check_rule=..., finding_ref=finding["id"],
        intent=..., effect=..., needs=..., evidence_text=...,
        today=today)
```

- Jeder Befund geht durch diesen Aufruf, unabhängig von seiner `confidence`.
- `create()` entscheidet allein aus `confidence`, ob eine Maßnahme (`type: "measure"`) oder ein Test (`type: "test"`) entsteht (Spec Abschnitt 9: "eine Hypothese wird nie priorisiert, sie wird als Test formuliert").
- Vor dem Aufruf nicht filtern; das macht das Modul.

Feste Feldabbildung von Befund auf `create()`-Parameter:

| Befund-Feld | `create()`-Parameter | Umformung |
|---|---|---|
| `statement` | `title` | als Handlung umformuliert ("Alt-Text ergänzen" statt "37 Bilder ohne Alt-Text") |
| `discipline` des **Dokuments**, nicht des einzelnen Befunds | `discipline` | Die Agents schreiben `{"discipline": ..., "run_id": ..., "generated_at": ..., "findings": [...]}`; der einzelne Befund hat das Feld nicht. `finding["discipline"]` liefert deshalb `None`, und `create()` wirft. Den Wert aus der obersten Ebene der Datei nehmen, er gilt für alle ihre Befunde, sonst unverändert. Die Agents schreiben bereits die Schreibweise, die `measures.LABELS` und `measures.PRIORITY_DISCIPLINE` kennen (`data_quality`, `seo_technical`). Die gültigen Werte stehen in `${CLAUDE_PLUGIN_ROOT}/scripts/audit/measures.py` unter `LABELS["discipline"]`; wer einen Subagenten darauf verpflichtet, gibt ihm diesen Pfad mit, im Kunden-Workspace fehlt die Datei. Hier nichts umschreiben: eine Umwandlung an dieser Stelle wäre eine Prosa-Regel, und eine Sitzung, die sie auslässt, erzeugt Datenqualitäts-Befunde, die nie nach oben priorisiert werden und im Kundendokument unübersetzt stehen. Die Dateinamen behalten Bindestriche; das ist Dateinamens-Konvention und betrifft den Feldwert nicht |
| `evidence` | `evidence` | unverändert übernommen |
| `confidence` | `confidence` | unverändert übernommen, entscheidet in `create()` über `type` |
| `effect` | `leverage` | gegen die Baseline-Zahlen eingeordnet (Spec Abschnitt 9): `high`, wenn die betroffene Kennzahl mindestens ein Drittel des relevanten Blocks ausmacht (Umsatz-, Session- oder Klickanteil) oder eine Diagnose-Schwelle aus `reference/metrics.md` klar reißt; `low`, wenn sie unter der plugin-weiten Auffälligkeits-Schwelle von 20 Prozent liegt oder eine Randgröße betrifft; sonst `medium`. Wo sich der Effekt rechnen lässt, steht die Rechnung im `effect`-Satz des Befunds selbst, sonst bleibt es beim Band, nie eine erfundene Zahl |
| `effort` | `effort` | unverändert übernommen |
| `decision`, wenn vorhanden | `title`, `intent` | Die Maßnahme entsteht aus der empfohlenen Option `options[recommended]`: deren `title`, als Handlung umformuliert, wird `title`; deren `text` wird `intent`. Die andere Option wird keine Maßnahme; das Portal zeigt sie in der Herleitung als Geprüfte Alternative. Will der Kunde sie, stellt er eine Rückfrage. Festgelegt am 02.10.2026 (Portal-Spec `2026-10-02-finding-cards-design.md`, Abschnitt 9) |
| `evidence_text`, wenn vorhanden | `evidence_text` | wörtlich übernommen. Befund und Maßnahme haben denselben Beleg-Satz; einen eigenen schreibt Phase 3 nur für einen Befund ohne |

Parameter, die erst hier entstehen:

- **`responsible`:** aus der Disziplin abgeleitet.
  - Was der Betreiber für den Kunden umsetzt (SEO, GEO, SEA, Shop und Conversion, Technik): `"Path to AI"`. Der gespeicherte Wert meint den Betreiber, nicht die Firma; im Kundendokument steht der Name aus `PTAI_OPERATOR_NAME`, sonst "Dienstleister" (`measures.responsible_label()`).
  - Rein geschäftliche Entscheidungen (Sortiment, Preis, Rückgabepolitik): `"Customer"`.
  - Fremdintegration (etwa ein Katalog-Feed aus einem ERP): `"Third Party"`.
  - Das ist eine Heuristik; passt sie im Einzelfall nicht, entscheidet die Sitzung nach Kontext.
  - **Der Auftragsumfang hat Vorrang vor der Disziplin.** Schließt der Auftrag eine Disziplin aus (etwa "Performance Marketing, Ads und Paid Social" im Angebot), bleiben ihre Maßnahmen für das Team relevant, liegen aber bei ihm: `"Customer"`, `intent` aus Sicht des Teams ("Ihr …"), und `needs` sagt in einem Satz, dass die Disziplin nicht Teil des Auftrags ist.
- **`data_source`:** wo das Feld, das die Maßnahme ändert, gepflegt wird, genau benannt (etwa "Shopify-Theme", "Shopify-Produktverwaltung", "GA4/GTM-Property", "DNS/Sitemap"), nie pauschal "Shopify". Verhindert Arbeit, die beim nächsten Sync verloren geht (Spec Abschnitt 9, Beispiel mit einem Middleware-System).
- **`check_rule`:** wie ein Folgelauf feststellt, ob die Maßnahme umgesetzt ist.
  - **Ohne `check_rule` wird `create()` für diesen Befund nicht aufgerufen.** Eine Maßnahme, deren Umsetzung nie feststellbar ist, bleibt für immer offen und blockiert den Backlog.
  - Lässt sich keine automatische Regel aus einem künftigen Snapshot-Feld formulieren: eine Frage an den Menschen, wörtlich als solche (etwa "Frage an den Kunden: ist die Rückgabepolitik seit dem Audit geändert worden?"), nie ein leerer Wert.
  - **Die Regel nennt den beobachtbaren Zustand, nie die Datei.** Sie steht im Kundendokument unter "Erledigt, wenn"; der Leser hat Fragen zu seinem Shop, nicht zu unseren Snapshots. Richtig: "Mehr als 100 verschiedene Seitentitel über die geprüften Seiten". Falsch: `"crawl.json: mehr als 100 verschiedene Title-Werte"`. Der Folgelauf weiß selbst, wo er nachsieht.
- **`intent`, `effect`, `needs`, `evidence_text`:** die Erklärung für den Kunden, siehe nächster Abschnitt. Technisch freiwillig, damit ein Folgelauf über einen alten Backlog nicht bricht; `qa.py` warnt für jede Maßnahme, der sie fehlen.
- **`finding_ref`:** die Kennung des Befunds, aus dem die Maßnahme folgt, also `finding["id"]`.
  - Ohne sie zeigt der Report eine Handlung ohne Herkunft, und der Leser kann sie nicht beauftragen, weil er nicht sieht, was gemeint ist und wo es gefunden wurde.
  - Ohne `finding_ref` bleibt nur eine Maßnahme, die aus einer Lücke in der Datenlage folgt und keinen Befund am Shop hat.

### Die vier Felder, die eine Maßnahme erklären

- **Eine Maßnahme muss ohne Rückfrage verständlich sein.** Das Kundenteam soll sie öffnen und verstehen, was gemeint ist.
- Titel, Beleg als Dateipfad, Prüfregel, Datenherkunft und Verantwortlicher reichen dafür nicht; sie sind die interne Sicht.
- Deshalb hat jede Maßnahme vier weitere Felder. Sie stehen im Portal in dieser Reihenfolge über den technischen Angaben, jedes mit genau einer Aufgabe:

| Feld | Was drinsteht | Länge |
|---|---|---|
| `evidence_text` | Der Beleg als Satz mit den Zahlen, die ihn tragen. "318 von 1.204 Produktseiten haben keinen internen Link aus einer Kategorie- oder Kollektionsseite." Nicht der Pfad, der bleibt in `evidence` | ein Satz |
| `intent` | Was wir vorhaben, als Handlung, und wo im Shop das passiert. "Wir verlinken die betroffenen Produktseiten aus den passenden Kategorieseiten heraus und ergänzen dafür die Kategorie-Templates im Theme." | ein bis zwei Sätze |
| `effect` | Was es bringt, oder was es kostet, wenn es so bleibt. **Keine erfundene Zahl**: die Richtung und der Mechanismus reichen, wo keine belegte Rechnung möglich ist | ein bis zwei Sätze |
| `needs` | Was wir dafür vom Kundenteam brauchen: eine Freigabe, einen Text, einen Zugang, eine Entscheidung. Leer, wenn wir es allein umsetzen können | ein Satz oder leer |

- Fachbegriffe verwenden und beim ersten Auftreten erklären; keine Laienwörter im Kundendokument; keine Zahl ohne Beleg.
- Ist die Skill `workos:ecom-language` installiert, enthält sie diese Regeln samt Vokabular; ohne sie gelten die Regeln hier.
- Die Maßnahme wiederholt den Befund nicht, sie baut auf ihm auf; der Befund steht im Portal über `finding_ref` direkt darüber.
- **Die Felder sind kein zweiter Report.** Steht in `intent` derselbe Satz wie im `fix` des Befunds, fehlt der Mehrwert. Dann kommt in `intent` der genaue Weg, den wir gehen, und in `effect` die Folge für den Shop.

### Schritt 4: Priorisieren und schreiben

Nachdem alle Befunde aus allen vorliegenden `findings/`-Dateien durch `create()` gelaufen sind: `measures.save(workspace, backlog)`.

**`prioritize()` hier nicht aufrufen und seinen Rückgabewert nie zuweisen.**

- `prioritize(backlog)` liefert eine **Liste** (die Sortierung für die Ausgabe), kein Dokument wie `create()`.
- `backlog = measures.prioritize(backlog)` und Speichern legt eine Liste in `measures.json` ab; `load()` liefert dann eine Liste, und der nächste Lauf scheitert an anderer Stelle.
- `save()` weist den falschen Typ inzwischen ab; die Reihenfolge oben gilt trotzdem.
- Sortiert wird erst beim Rendern in Phase 4; `render()` ruft `prioritize()` selbst auf.
- `prioritize()` stellt Befunde der Disziplin `data_quality` unabhängig von Sicherheit, Hebel und Aufwand an die Spitze (Spec Abschnitt 9); das macht das Modul, diese Skill ruft nur auf.

**Vorher zählen, danach nachzählen.**

- Zählen: Befunde in den `findings/`-Dateien und Einträge in `backlog["measures"]` danach.
- Beide Zahlen kommen in die Zusammenfassung am Ende des Laufs.
- Stehen Befunde da und der Backlog ist leer oder deutlich kürzer: abbrechen und den Grund nennen, nicht schreiben. Ein leeres `measures.md` sieht aus wie "nichts gefunden".
- Häufigster Grund: ein `create()`-Aufruf ohne zugewiesenen Rückgabewert (siehe Schritt 3); er wirft keine Ausnahme.
- Das Rendern zu `measures.md` (`measures.render()`) passiert erst in Phase 4. Wie bei der Baseline schreibt diese Phase den Zustand, Phase 4 leitet das lesbare Dokument ab.

**Artefakte:** `reporting/baseline/01/baseline.json` (neu oder um Blöcke ergänzt) und `reporting/measures.json`.

**Bei Fehler:**

- Scheitert ein einzelner `create()`-Aufruf mangels Beleg, ohne `check_rule` oder mit unbekanntem Wert (`ValueError` oder die `check_rule`-Pflicht oben): den Befund weglassen und protokollieren. Die übrigen Befunde und Blöcke laufen weiter.
- Ein geschriebener Block wird nie erneut geschrieben. `BlockAlreadyWritten` nie abfangen; das ist ein Denkfehler beim Aufrufer, keine Fehlerbehandlung.

**Bei Erfolg:** `run_state.set_phase('3-synthesis', 'done')`, `run_state.save()`.

## Phase 4: Deliverables

- Ein Befund-Titel ist ein Label, keine freie Formulierung.

**Schritt 1, die Markdown-Ableitungen.**

- `baseline.render(workspace)` schreibt `baseline.md` aus `baseline.json`.
- `measures.render(workspace)` schreibt `measures.md` aus `measures.json`.
- Beide sind reine Ableitungen, nie von Hand pflegen.

**Schritt 2, das Kunden-PDF.**

- Es folgt einem Skelett aus acht Elementen in fester Reihenfolge, festgelegt in `skills/audit/templates/audit.html` und `scripts/audit/report_build.py`.
- **Das Dokument baut `scripts/audit/report_build.py`, nicht die Sitzung.** Von Hand zusammengesetzt wird es bei jedem Lauf anders, und Korrekturen an der Darstellung gingen verloren.

| Was | Wer | Warum |
|---|---|---|
| Zahlen je Sektion, Befunde, Maßnahmen, Quellen, Kennzahlenleiste | das Script | Zahlen gehören in Code, damit sie nicht driften |
| Textelemente in `report-text.json` (neun Textfelder, Problem-Kacheln, ein Satz je Sektion) | die Sitzung | Text gehört an einen Menschen, damit er nicht generisch wird |
| Überschriften, Labels, Erklärzeilen | das Template | eine Zeile, die jeder Lauf neu schreibt, driftet |

| # | Element | Steckt im Template als | Gefüllt aus |
|---|---|---|---|
| 1 | Kopf | `__COVER_HEADLINE__` plus feste Dokumentzeile | Sitzung, schlichter Titel, siehe unten |
| 2 | Einstieg | `__INTRO__` | Sitzung, Ergebnis zuerst, siehe unten |
| 3 | Die größten Probleme | `__PROBLEMS__` | Sitzung, zwei bis vier Kacheln |
| 3b | Kennzahlenleiste | sechs `__KPI_*__` plus Notizen | Script |
| 3c | Path to AI E-Com Score | `__SCORES__` | Script |
| 4 | Zusammenfassung | fünf `__SUMMARY_*__` | Sitzung |
| 4b | Die wichtigsten Erkenntnisse | `__TAKEAWAYS__` | Sitzung, fünf Sätze mit Befund-Kennung |
| 4c | Die Befunde im Überblick | `__FINDINGS_OVERVIEW__` | Script |
| 5 | Inhalt | fest im Template | nichts, die fünfzehn Zeilen stehen |
| 6 | Fachsektionen | fünfzehn `SECTION:`-Marker (alle außer `sources`) | Script, siehe Tabelle darunter |
| 7 | Nächster Schritt | `__NEXT_STEP__` | Sitzung |
| 8 | Quellen | `SECTION:sources` | Script, aus `state.json > sources` |

- **Alle Überschriften, Labels und Erklärzeilen stehen fest im Template.** Sie gelten für jeden Shop und werden nie je Lauf neu formuliert.
- Der Lauf füllt Zahlen, Namen und Sektionsinhalte, sonst nichts.

### Die sechzehn Sektionen

Jede Sektion zeigt ihre eigenen Zahlen und direkt darunter die Befunde, die daraus folgen. Nicht alle Zahlen in eine gemeinsame Tabelle und alle Befunde in einen Block dahinter.

| Marker | Inhalt | Quelle |
|---|---|---|
| `SECTION:shop` | Tabelle Angabe / Wert / Quelle: Shop-System, Theme, Sprachen, Märkte, Zahlarten, Sortiment, Seiten im Shop, Zahlen ab, Drittanbieter-Dienste. **Die Spalte Quelle trägt Werkzeugnamen** (Shopify Admin, Search Console, eigener Durchgang), nie Dateinamen | `config.json`, `shop-tech.json`, `catalog.json`, `crawl.json`, `state.json` |
| `SECTION:measurement` | Die Zahlen zur Messqualität, dann die Befunde der Disziplin. Steht vorn, weil eine kaputte Messung jede Zahl danach zur Behauptung macht | `findings/data-quality.json`, `shopify.json`, `ga4.json`, `shop-tech.json` |
| `SECTION:commerce` | Umsatz, Bestellungen, Bestellwert, Saison und Verfügbarkeit, dann die Befunde | `findings/commerce.json`, `shopify.json`, `catalog.json` |
| `SECTION:traffic` | Kanaltabelle mit Sessions, Anteil, Bestellungen, Conversion und Umsatz je Kanal, dann die Befunde | `findings/traffic.json`, `ga4.json` |
| `SECTION:conversion` | Kaufweg je Stufe als Anteil aller Sitzungen, dazu die Geräte, dann die Befunde | `findings/conversion.json`, `ga4.json`, `screens.json` |
| `SECTION:trust` | Welche Pflichtseiten der Crawl gefunden hat und mit welchem Status, dazu der Vorbehalt, dass dies keine juristische Prüfung ist, dann die Befunde | `findings/trust.json`, `crawl.json` |
| `SECTION:seo` | Klicks und Impressionen, Ranking-Bestand, Sichtbarkeitsverlauf, stärkste Rankings, Chancen knapp vor Seite eins, Lücken zum Wettbewerb, dann die Befunde | `findings/seo-content.json`, `gsc.json`, `dfs-rankings.json`, `dfs-competitors.json`, `dfs-backlinks.json` |
| `SECTION:geo` | Sichtbarkeit je Plattform und Abfragegruppe, wer stattdessen zitiert wird, Crawler-Zugang, dann die Befunde | `findings/geo.json`, `geo.json` |
| `SECTION:tech` | Ladezeit je Seitentyp aus Feld und Labor, der eigene Durchgang durch den Shop, dann die Befunde | `findings/seo-technical.json`, `cwv.json`, `crawl.json` |
| `SECTION:catalogue` | Produkte, Varianten, Kategorien, gepflegte Felder, Bilder, dann die Befunde | `findings/content-brand.json`, `catalog.json` |
| `SECTION:competition` | Sichtbarkeit im Vergleich, Autorität, Linkprofil, Shopping-Präsenz, dann die Befunde | `findings/competition.json`, `dfs-rankings.json`, `dfs-backlinks.json`, `dfs-competitors.json`, `dfs-shopping.json` |
| `SECTION:sea` | Shopping-Präsenz und was das Werbekonto zeigt, dann die Befunde | `findings/sea.json`, `ads.json`, `dfs-shopping.json` |
| `SECTION:measures` | Die Reihenfolge der Umsetzung als Tabelle, eine Zeile je Maßnahme, mit dem Abschnitt, in dem sie ausführlich steht. Darunter nur die Maßnahmen ohne Befund am Shop | `measures.json` |
| `SECTION:gaps` | Tabelle Quelle / Status / Grund / Was dadurch offen bleibt | `source-status.md` plus die `blocked_questions` aller Disziplinen |
| `SECTION:method` | Wie der PTAI E-Com Score gerechnet wird: Strafpunkte, Gewichte, Grenzen, und was der Score nicht leistet. **Aus den Konstanten von `score.py` erzeugt, nicht getippt** | `scripts/audit/score.py` |
| `SECTION:sources` | Je Quelle eine `.source-row`: Werkzeug, Umfang, Stand | `state.json > sources`, Erhebungsdatum aus `pulled_at` |

**Zahlen in Blöcken, nicht im Fließtext.** Dieselben Regeln wie in `audit-light`:

- **Was in einer Sektion nachweislich gut läuft, als Kennzahlen-Leiste zeigen, nicht als Befundblock.** Ein Stärken-Befund als Block nimmt so viel Platz ein und wiegt so schwer wie ein kritischer. Drei bis vier Kacheln aus gemessenen Zahlen ersetzen ihn.
- **Ein Anteil gehört in einen Balken mit Zähler und Nenner daneben**, nicht in einen Satz. "759 von 765" ist im Fließtext eine Behauptung, die der Leser nachrechnen muss.
- **Die GEO-Messung gehört in ein Raster**: je Abfrage eine Zeile, je Plattform eine Spalte. Der Kernbefund ist ein Muster über alle Antworten.
  - Vorlage: `scripts/report/sales/report-pdf-full.mjs`, `geoGridSection`.
  - Zellwerte: `both`, `brand`, `domain`, `none`.

**Rechenregel für den Score:** auf den konsolidierten Befunden rechnen, nicht auf den Rohbefunden der Analysen. Wer zwei Analysen zusammenführt und trotzdem die ungefilterte Liste übergibt, zählt jede Dublette doppelt (in `audit-light` hat das zehn Punkte gekostet). Hier betrifft das `compute()` in `scripts/audit/score.py`: die Eingabe ist das, was im Report steht.

**Jede Fachsektion beginnt mit ihren Zahlen, dann folgen die Befunde.**

- Die Zahlen-Tabelle hat immer drei Spalten: Kennzahl, Wert, Bezug.
- Der Bezug ist Pflicht. "Klicks 120.000" ist keine Aussage; "Klicks aus der Google-Suche · 120.000 · in 16 Monaten, bei 4,8 Mio. Impressionen" ist eine.

**Jede Maßnahme steht bei ihrem Befund, nicht in einem eigenen Kapitel.** Sonst steht dieselbe Handlung zweimal im Report.

- **Der Maßnahmen-Block steht direkt unter dem Befund**, aus dem er folgt, in dessen Sektion. Keine Zeile "Woraus", der Befund steht direkt darüber.
- **Hat ein Befund eine Maßnahme, entfällt sein `fix`-Satz.** Die Maßnahme sagt dasselbe vollständiger, mit Zuständigkeit und Prüfregel. Ohne Maßnahme behält der Befund seinen Satz.
- **Abschnitt 12 ist der Plan, nicht die Wiederholung.**
  - Eine Tabelle in der Reihenfolge aus `measures.prioritize()`, je Zeile Nummer, Maßnahme, Hebel, Aufwand und der Abschnitt mit der ausführlichen Fassung.
  - Als Block stehen dort nur die Maßnahmen ohne Befund am Shop; sie folgen aus einer Lücke in der Datenlage und haben sonst keinen Ort.

**Eine Maßnahme ist ein Block, keine Tabellenzeile.**

- `measures.json` führt je Eintrag `evidence`, `data_source`, `check_rule` und `responsible`.
- Jeder Block nennt: den Befund, aus dem er folgt; was er bringt; wo gearbeitet wird; wer zuständig ist; woran ein Folgelauf die Erledigung erkennt.
- Ohne diese Angaben kann der Leser die Maßnahme nicht beauftragen.

**Die Kernzahl je Baseline-Block ist festgelegt.** Sonst wählt jeder Lauf eine andere, und die Übersichtstabelle vergleicht über zwei Läufe verschiedene Zahlen:

| Block | Kernzahl | Quellfeld im Block |
|---|---|---|
| Handel | Umsatz über den erhobenen Zeitraum | `commerce` > Umsatz brutto |
| Traffic | Sessions über den erhobenen Zeitraum | `traffic` > Sessions |
| Conversion | Conversion Rate gesamt | `conversion` > Conversion Rate |
| SEO Suche | Klicks über den erhobenen Zeitraum | `seo_search` > Klicks |
| SEO Sichtbarkeit | Ranking-Keywords gesamt | `seo_visibility` > Ranking-Keywords |
| GEO | Marke genannt bei Kategorie-Abfragen, als "x von y" | `geo` > Trefferquote Kategorie |
| SEA | Ausgaben über den erhobenen Zeitraum | `sea` > Ausgaben |
| Technik | LCP der Produktseite, Feldwert | `tech` > LCP Produktseite |
| Katalog | Anteil Bilder mit Alt-Text | `catalogue` > Anteil Bilder mit Alt-Text |
| Messung | Zuordnungslücke gegen GA4 | `measurement` > Zuordnungslücke |

- Leerer Block: in der Wert-Spalte "nicht erhoben", in der Stand-Spalte der Grund aus `state.json`; nie eine leere Zelle, nie eine Null.
- Die Zelle der Zuordnungslücke bekommt `class="neg"`, wenn sie über der Schwelle aus `reference/metrics.md` liegt; dann ist sie der Wert, der eine Maßnahme auslöst.

### Die Kennzahlenleiste

- Sechs Kacheln, drei mal zwei, gebaut von `report_build.key_figures()`.
- **Die Auswahl folgt der Umsatzgleichung**, nicht der Verfügbarkeit. Shopify formuliert sie als Sitzungen mal Conversion Rate mal Bestellwert mal Kauffrequenz. Umsatz ist das Ergebnis, die vier Faktoren sind die Hebel; ein Geschäftsführer fragt, welcher Faktor sich bewegt hat.

| Platzhalter | Wert | Warum diese Kachel |
|---|---|---|
| `__KPI_REVENUE__` | Umsatz im Auswertungsfenster | die Zielgröße |
| `__KPI_ORDERS__` | Bestellungen | das Zwischenglied der Gleichung |
| `__KPI_AOV__` | Ø Bestellwert | Hebel 3 |
| `__KPI_CR__` | Conversion Rate | Hebel 2 |
| `__KPI_SESSIONS__` | Sitzungen | Hebel 1 |
| `__KPI_SIXTH__` | Wiederkaufrate, sonst Retourenquote oder Rohertrag | Hebel 4, plus die Marge |

- Jede Kachel zeigt ihre Veränderung: `__KPI_REVENUE_NOTE__`, `__KPI_ORDERS_NOTE__`, `__KPI_AOV_NOTE__`, `__KPI_CR_NOTE__`, `__KPI_SESSIONS_NOTE__` und `__KPI_SIXTH_NOTE__`.
- `__KPI_SIXTH_LABEL__` enthält den Namen der sechsten Kennzahl, weil er von der Datenlage abhängt.
- `__KPI_SIXTH_CLASS__` setzt sie kleiner, wenn sie "nicht erhoben" sagt: eine fehlende Kennzahl wird gezeigt, aber nicht hervorgehoben.

**Nicht in die Leiste:**

- Suchklicks: ein Kanal-Input eine Ebene unter den Sitzungen, sie stehen im SEO-Kapitel.
- Zahl der Produkte und Anteil der kaufbaren: Bestandsfakten, kein Ergebnis; der Anteil ist zudem eine Aussage über Datenqualität.
- Dass `pull-shopify` eine Zahl ohne Zusatzzugang liefert, ist kein Grund für eine Kachel auf dem Deckblatt.

**Weitere Regeln:**

- **Der Zeitraum steht einmal über der Leiste** (`__KPI_PERIOD__`), nicht unter jeder Kachel.
- **Jede Zahl zeigt ihren Vergleich** (Stephen Few, "Common Pitfalls in Dashboard Design": ohne Vergleich ist eine Zahl nicht bewertbar).
  - Vergleichswert ist das Vorjahresfenster, nie ein Branchen-Benchmark.
  - Für die meisten Sortimente gibt es keine belastbare öffentliche Zahl, und eine gescrapte macht den Report angreifbar.
- **Die sechste Kachel nie durch eine verfügbare Ersatzzahl füllen.** Liefert keine Quelle Wiederkaufrate, Retourenquote oder Rohertrag: "nicht erhoben" und der Grund in Kundensprache. Eine fehlende Kennzahl mit Begründung ist ein Befund, eine ersatzweise eingesetzte ein Fehler.
- **Störmonate ausweisen, nicht glätten.**
  - Ein Monat mit auffällig erhöhten Sitzungen oder ohne gemessene Käufe verzerrt jeden Vergleich, der ihn enthält.
  - `window.build()` erkennt sie und rechnet Sitzungen, Bestellungen und Conversion zusätzlich über die identischen verbleibenden Monate beider Jahre.
  - Die Notiz der Kachel sagt, dass das geschehen ist.
- **Das Auswertungsfenster ist nicht die Baseline.**
  - Die Baseline friert die volle Historie ein, sie ist der Nullpunkt.
  - Das Fenster sind die letzten zwölf vollen Monate gegen die zwölf davor; es zeigt, wohin sich der Shop gerade bewegt.
  - `scripts/audit/window.py` rechnet es aus den Snapshots, nie die Sitzung.

### Wie eine Kennzahl heißt

Deutsch für Handelsgrößen, englisch für die eingeführten Akronyme. Das ist die Schreibweise der deutschen Oberflächen von Shopify, GA4 und Search Console; der Kunde kennt das Wort aus seinem Werkzeug.

| Im Report | Nicht |
|---|---|
| Sitzungen | Sessions, Visits |
| Conversion Rate | Konversionsrate, Umwandlungsrate |
| Ø Bestellwert, einmal ausgeschrieben mit "(AOV)" | Warenkorbwert |
| Bestellungen | Transaktionen, Orders |
| Umsatz, bei Bedarf Nettoumsatz | Revenue |
| Wiederkaufrate | Repeat Rate |
| Retourenquote | Return Rate |
| Warenkorbabbruchrate | Cart Abandonment Rate |
| Impressionen, Klickrate | Impressions, CTR (im Fließtext einmal erklärt) |
| Organische Suche, Bezahlte Suche, Verweis | Organic, Paid, Referral |
| Absprungrate, Interaktionsrate | Bounce Rate, Engagement Rate |
| CAC, CLV, ROAS, ROI | eingedeutschte Formen |

- **Klicks aus der Search Console:** kein deutscher Fachbegriff, Google schreibt im deutschen Leistungsbericht "Klicks". Im SEO-Kapitel bei der ersten Nennung "Klicks in der organischen Suche", danach "Klicks". Nicht auf das Deckblatt.
- **Die Stufen des Kaufwegs heißen wie in GA4**, mit einer Ausnahme: `add_to_cart` heißt dort "In den Einkaufswagen legen", eine Übersetzung, kein Handelsbegriff. Im Report "In den Warenkorb gelegt", passend zu Warenkorbabbruchrate und durchschnittlichem Warenkorb.

### Der Kaufweg ist kein Trichter

- **GA4 zählt je Stufe die Sitzungen, in denen das Ereignis mindestens einmal vorkam, unabhängig von der Reihenfolge.** Eine Sitzung kann den Warenkorb ansehen, ohne in derselben Sitzung etwas hineingelegt zu haben: gespeicherter Warenkorb vom letzten Besuch, Newsletter-Link direkt auf `/cart`, Klick auf das Warenkorb-Symbol.
- **Deshalb keine Spalte "Weiter von der Stufe davor".** Sie behauptet einen Weg, den die Zahlen nicht beschreiben, und kann über 100 Prozent liefern (etwa 237,6 Prozent für den Warenkorb).
- Jede Stufe zeigt stattdessen ihren **Anteil an allen Sitzungen**. Unter der Tabelle erklärt ein Satz, warum eine spätere Zeile größer sein kann als eine frühere; die Zahl, die den Leser stutzen lässt, wird dort erklärt, wo sie steht.
- **Eine Übergangsquote ist erlaubt, wo die Stufen zwingend aufeinander folgen** (Produkt ansehen und in den Warenkorb legen: ohne Produktansicht kein Warenkorb). Sie steht als eigener Satz, nicht als Spalte, damit sie als Ausnahme erkennbar bleibt.

### Die größten Probleme, als Zahl

- `__PROBLEMS__` sind zwei bis vier Kacheln, in denen **die Zahl selbst das Problem ist**.
- Muster: "3 Versandkostenschwellen, gleichzeitig", "0 Länder, bei denen die Preise übereinstimmen". Wer nur diese Zeile liest, weiß, worum es geht.

Je Kachel vier Felder in `report-text.json` unter `problems`:

| Feld | Inhalt |
|---|---|
| `value` | die Zahl, groß und allein lesbar |
| `label` | was sie zählt, zwei bis vier Wörter |
| `detail` | eine Zeile, die sagt, was daran das Problem ist |
| `finding_ref` | die Kennung des Befunds dahinter |

- **Welche Probleme gezeigt werden, entscheidet die Sitzung, nicht das Script.** Welche drei von 91 Befunden die wichtigsten sind, folgt nicht aus den Daten.
- Das Script prüft nur, dass jede Kachel auf einen existierenden Befund zeigt, und bricht sonst ab; eine Zahl auf Seite eins ohne Herkunft kann der Leser nicht nachschlagen.
- **Kennzahlenleiste und Problem-Kacheln ergänzen sich.** Die Kennzahlen zeigen, wie der Shop dasteht; die Problem-Kacheln zeigen, was ihn das kostet. Beide stehen auf Seite eins.
- **Die Problem-Kacheln stehen zuerst, direkt unter dem Einstieg.** Der Leser fragt "was ist los", bevor er fragt "wie steht der Shop da"; hinter der Zusammenfassung sucht er sie nicht mehr.
- **Jede Zahl enthält ihre Bezugsgröße im `value`, nicht erst in der Erklärzeile.**
  - "1.000" allein ist nicht bewertbar, "1.000 von 3.000" sofort.
  - Quelle: Nutzertests der Cochrane-Ergebnistabellen, fehlende Bezugsklasse als häufigste Fehlerquelle (Rosenbaum et al., Journal of Clinical Epidemiology 2010).
  - Ausnahme: der richtige Wert ist selbstverständlich. "0 Länder, bei denen die Preise übereinstimmen" braucht keinen Nenner, weil dort erkennbar "alle" stehen müsste.

### Der Path to AI E-Com Score

`__SCORES__` baut `scripts/audit/score.py`: eine Gesamtbewertung, vier Bereichswerte mit Zielmarke und je Fachsektion ein eigener Wert in ihrem Kopf.

- **Name im Dokument: "Path to AI E-Com Score"**, nicht "Health Score" und nicht "Gesamtbewertung". Ein Score mit Absender ist eine verantwortete Methode, die beim nächsten Lauf wiederkommt.
- **Dieselbe Rechenweise wie `scripts/report/sales/score.mjs`**, die Engine des audit-light; zwei Engines für dieselbe Frage würden sich widersprechen.
- Rechnung: 100 minus Strafpunkte je Befund, gewichtet nach Schweregrad (hoch 14, mittel 5, gering 1) und Sicherheit (belegt 1,0, plausibel 0,7, Verdacht 0,4), mit abnehmendem Ertrag.

| Bereich | Gewicht | Sektionen |
|---|---|---|
| Kaufen | 0,40 | Conversion, Katalog, Handel |
| Gefunden werden | 0,30 | SEO, GEO, Wettbewerb, Bezahlte Suche, Traffic |
| Technik | 0,15 | Technik und Ladezeit |
| Messung | 0,15 | Messung |

- Abschnitt 1 speist keinen Score: Shop und Technik ist eine Bestandsaufnahme, keine Bewertung.
- **Deckel bei 92, Boden bei 35.**
  - 100 würde behaupten, es gäbe nichts mehr zu finden; ein Audit prüft nur, was er prüfen kann.
  - Der Boden verhindert, dass eine gründlich geprüfte Sektion allein durch die Menge ihrer Befunde gegen null fällt.
- **Eine Sektion ohne Datengrundlage bekommt keinen Score, sondern "nicht bewertbar".** Sonst sieht ein ungeprüfter Bereich aus wie einer ohne Probleme. Ihr Gewicht verteilt sich auf die übrigen.

**Das Ziel ist der Stand nach Umsetzung, ohne künstliche Begrenzung, und liegt daher oft nahe am Deckel.**

- Die Aussage steckt im Abstand, nicht in der Höhe des Ziels: Messung 38 auf 89 ist ein Sprung von 51 Punkten, Bezahlte Suche 86 auf 92 einer von sechs.
- Unter dem Deckel halten das Ziel nur die Befunde **ohne** Maßnahme: Beobachtungen, Lücken in der Datenlage, Dinge außerhalb des eigenen Zugriffs. Sie verschwinden nicht durch Umsetzung.

**Die Rechnung steht im Report, nicht nur im Code.**

- Abschnitt 14 legt sie vollständig offen: Strafpunkte je Schweregrad, Faktor je Sicherheit, Bereichsgewichte, Deckel, Boden, abnehmender Ertrag, Entstehung des Ziels.
- **Der Abschnitt wird aus den Konstanten in `score.py` erzeugt, nicht daneben geschrieben.** Eine getippte Methodenbeschreibung veraltet mit der ersten Änderung an einem Gewicht, unbemerkt, weil das Dokument weiter rendert.
- **Dort steht auch die Grenze der Methode:**
  - Die Gewichte sind eine Kalibrierung, keine Messung, und stammen aus keiner Studie. Gewählt, damit ein schwerer Befund spürbar mehr wiegt als ein leichter und gründliches Prüfen den Wert nicht ruiniert.
  - Garantiert ist: dieselben Befunde ergeben immer denselben Wert, zwei Läufe desselben Shops sind vergleichbar.

**Vergleichsmaßstab:**

- Es gibt keinen belastbaren öffentlichen Benchmark für einen Shop dieser Größe und dieses Sortiments. Kursierende Branchenzahlen stammen aus Aggregator-Blogs; Shopify zitiert für Schmuck eine einzige Quelle über gut 400 Marken. Zu dünn für ein Kundendokument, und eine gescrapte Zahl macht den Report angreifbar.
- Verglichen wird gegen drei Dinge, die alle im Dokument stehen:
  1. 100, also einen Shop ohne Befunde
  2. das Ziel nach Umsetzung
  3. **ab dem nächsten Lauf den heutigen Wert**; dafür existiert die Baseline
- **Nie einen Branchen-Benchmark danebenstellen**, auch nicht zur Orientierung. Jede Zahl im Dokument wird zum Maßstab, und dieser wäre nicht belegt.

### Die wichtigsten Erkenntnisse und der Zustand je Bereich

**`__TAKEAWAYS__`:**

- Fünf Sätze, die den ganzen Report zusammenfassen, als `<ol>` mit fünf `<li>`.
- **Jeder nennt eine gemessene Zahl und die Kennung des Befunds dahinter**, damit der Leser zur Herleitung springen kann.
- Die Sitzung schreibt sie, nicht das Script; welche fünf von 92 Befunden die wichtigsten sind, folgt nicht aus den Daten.

**`__FINDINGS_OVERVIEW__`:**

- Baut das Script: je Bereich die Zahl der Befunde, wie viele schwer wiegen und in welchem Abschnitt sie stehen; darunter die schwerwiegenden einzeln mit Kennung.
- **Das ist Navigation, keine Bewertung.** Eine Punktzahl je Bereich wäre die einzige Zahl im Dokument ohne Beleg.
- Keine Kernzahl je Bereich ohne Zeitraum an dieser Stelle. Die Zahlen stehen in der Kennzahlenleiste und in den Fachsektionen, dort mit Zeitraum.

**Der Schweregrad hat drei definierte Stufen.** Kein Standard schreibt die Zahl der Stufen vor, wohl aber klare Definition und durchgängige Anwendung (IIA Global Internal Audit Standards 14.3). Drei Stufen nutzt die Nielsen Norman Group in Berichten.

| Stufe | Wann |
|---|---|
| hoch | kostet heute Geld oder macht andere Zahlen im Report unbrauchbar |
| mittel | messbarer Verlust an Sichtbarkeit, Conversion oder Datenqualität, aber nicht akut |
| gering | Hygiene, heute ohne messbaren Verlust |

- **Schweregrad ist nicht Priorität.** Der Schweregrad sagt, wie schwer ein Befund wiegt; die Reihenfolge der Umsetzung hängt zusätzlich vom Aufwand ab. Deshalb stehen Hebel und Aufwand getrennt am Maßnahmenblock (CVSS v4.0 User Guide: Base Scores messen Schwere und reichen allein nicht zur Risikobewertung).
- Fehlt `severity` im Befund, leitet `report_build.severity_rank()` ihn aus dem Hebel der Maßnahmen ab, die auf ihn verweisen, sonst aus der Sicherheit der Analyse. Ein bloßer Verdacht wird dabei nie "hoch".

### Die fünf Zeilen der Zusammenfassung

Die Labels stehen fest im Template, gefüllt werden nur die Werte, je ein bis zwei Sätze:

| Platzhalter | Was hineingehört |
|---|---|
| `__SUMMARY_WHAT__` | Gegenstand und Grundgesamtheit: welcher Shop, welcher Stichtag, welche Bereiche, je über den längsten Zeitraum der Quelle |
| `__SUMMARY_WHY__` | der Mechanismus, der den Nullpunkt nötig macht, nicht der Ablauf des Audits |
| `__SUMMARY_STATUS__` | die drei bis vier tragenden Zahlen aus der Kennzahlenleiste, als Satz |
| `__SUMMARY_PROBLEM__` | was aus dem stärksten Befund folgt, in der Sprache des Lesers |
| `__SUMMARY_POSSIBLE__` | der Weg raus, ohne Preis und ohne Ablauf |

### Ein Wort je Sache, im ganzen Dokument

Ein eingeführtes Wort wird durchgehend verwendet; Synonyme lassen den Leser einen Unterschied suchen, den es nicht gibt.

| Gegenstand | Das Wort | Nicht |
|---|---|---|
| die eingefrorenen Zahlen | Baseline | Nullpunkt, Ausgangswerte, Startwerte |
| der nächste Lauf | der spätere Report, der nächste Report | Folgereport |
| die Beziehung dazu | daran messen, damit vergleichen | dagegen vergleichen |
| Abschnitt 1 | Shop und Technik | Marke und Shop |
| Abschnitt 5 | Lücken in der Datenlage | Was nicht gemessen werden konnte |
| die Kennzahl je Bestellung | Ø Bestellwert, im Fließtext einmal "durchschnittlicher Bestellwert (AOV)" | Warenkorbwert |
| die erfassten Seiten | Seiten im Shop, geöffnet und geprüft | gecrawlte Seiten |
| fremde Skripte | Drittanbieter-Dienste | Fremdtechnik, Skripte fremder Anbieter |

- `baseline.json` und `baseline.md` behalten ihren Namen; das ist der technische Dateiname, kein Wort im Kundendokument.

### Der Report beantwortet Fragen zum Shop, nicht zum Werkzeug

- **Der Leser hat Fragen zu seinem Shop, nicht zur Messung.**
- Nicht Gegenstand des Reports: wie weit eine Schnittstelle zurückreicht, wie ein Wert berechnet wird, warum er nicht abgeleitet wurde, wie die Dateien eines Laufs heißen.
- Jeder solche Satz verdrängt einen Satz über den Shop und erzeugt eine Frage, die der Leser vorher nicht hatte.
- Beispiele für Verstöße: ein heller Kasten, der die Datenreichweite der Search Console erklärt, obwohl die Tabelle darüber das Startdatum schon zeigt; auf einer Kennzahl-Kachel der Hinweis "von Shopify berechnet, nicht abgeleitet" (eine Bauregel des Generators auf dem Deckblatt).
- **Prüffrage:** würdest du diesen Satz laut sagen, wenn du dem Kunden den Report über den Tisch schiebst?

### Gleichartiges wird gleich behandelt

- **Stehen mehrere Werte derselben Sorte nebeneinander und einer bekommt einen Kommentar, wirken die anderen unauffällig.** Entweder jeder gleichartige Wert bekommt seinen Vermerk oder keiner.
- Beispiel: Die Zeile "Historie ab" zeigt drei Startdaten aus drei Quellen; erklärt wird nur eines.
- Geprüft wird nie ein Element allein, sondern immer die Menge gleichartiger Elemente.
- **Prüffrage:** gibt es im Dokument einen zweiten Eintrag derselben Sorte, der diesen Vermerk genauso verdient hätte?

### Der helle Kasten und die Fußnote

**Der helle Kasten** ist die auffälligste Stelle seiner Sektion und wird zuerst gelesen.

- Er enthält nur eine Einordnung, die für die ganze Sektion gilt und ändert, was der Leser tut.
- Höchstens einer je Sektion.
- Nie eine Randbedingung an einer einzelnen Zahl.

**Was zu genau einer Zahl gehört, steht an dieser Zahl.** Drei Wege, in dieser Reihenfolge prüfen:

1. **Ein Zusatz in der Zelle.** Erste Wahl: `Search Console 06/2025 (Google gibt höchstens 16 Monate heraus)`.
2. **Eine Spalte**, wenn mehrere Zeilen einen Grund haben. Die Lücken-Tabelle hat dafür die Spalte "Grund".
3. **Eine Fußnote**, nur wenn beides nicht passt.

**Eine Fußnote nur, wenn der Leser den Wert ohne Anmerkung in der falschen Größenordnung liest.**

- Ein Zusatz in der Zelle ersetzt sie.
- Eine Bedingung, die schon in einer Spalte, einer Kachel-Notiz oder Abschnitt 5 steht, ersetzt sie ebenfalls; die Fußnote wiederholt nie, was das Dokument schon sagt.
- Die Fußnote ist eine Erlaubnis, kein Auftrag. Beispiel: die Datenreichweite der Search Console steht als Zusatz in der Zelle und ausführlich in Abschnitt 5, eine Fußnote dort wäre die dritte Nennung.

Form:

- hochgestellte Ziffer direkt hinter dem einzelnen Wert (`<span class="fn">1</span>`)
- Auflösung in einem `.table-note` direkt unter der Tabelle, die Tabelle bekommt `class="has-note"`
- Nummerierung je Tabelle neu ab 1, höchstens drei je Tabelle
- **nur in einer Tabelle, die auf eine Seite passt**; über einen Seitenumbruch zeigt die Marke im Druck auf nichts
- Läuft die Tabelle länger: eine Spalte ergänzen oder die Zeile teilen

### Kopf, Einstieg und Schlussblock

**Die Cover-Headline ist ein schlichter Titel:** Gegenstand und Shop, bei klarem Ergebnis dazu die Zahl, wie eine Fachperson einen Bericht betitelt. Keine Zuspitzung, kein Gegensatz aus zwei Kurzsätzen, kein Vorwurf (festgelegt am 05.10.2026).

**Der Einstieg beginnt mit dem Ergebnis, nicht mit dem Umfang.**

- Ein Einstieg, der mit dem Umfang der Arbeit beginnt ("Ich habe ... vollständig durchgemessen: 2.000 Seiten ...") und mit einer allgemeinen Floskel über den nächsten Sprint endet, ist falsch.
- Quellen der Regel: US-Army-Schreibvorschrift AR 25-50, Ziffer 1-38b (bottom line up front); Minto (Aussage oben, Belege darunter); Nielsen Norman Group (Inverted Pyramid); GAO Yellow Book.

**Vier Sätze, in dieser Reihenfolge:**

1. **Was gilt.** Der stärkste Befund des Laufs als Aussage über den Shop, mit seiner Zahl. Nicht Umfang, nicht Vorgehen, nicht das Dokument.
2. **Warum das so ist, oder was daran hängt.** Der Mechanismus in einem Satz.
3. **Woraus das folgt.** Jetzt der Umfang, genau und zählbar, als Beleg für Satz 1.
4. **Was der Leser damit tun kann.** Eine Handlung, die er ohne den Rest des Dokuments entscheiden kann. **Kein Terminversprechen, keine Floskel über den Sprint.** Prüffrage: könnte dieser Satz unter jedem beliebigen Report stehen? Dann ist er falsch.

**Ansprache:**

- Der Betreiber ist Subjekt in der ich-Form, wo er handelt, nie "wir".
- Der Leser ist das Team des Kunden: "ihr" und "euch", nie "du". Im Portal lesen mehrere Personen dasselbe Dokument, und die Oberfläche daneben spricht sie genauso an (festgelegt am 28.09.2026).
- Die festen Labels im Template folgen derselben Regel ("Was ihr hier seht").
- "Dieser Report zeigt" ist immer falsch.

**Zahlen:** Jede Zahl kommt aus dem Lauf, nie geschätzt. Steht die Zahl der Befunde noch nicht fest, den Einstieg zuletzt schreiben.

**Prüffrage für den Einstieg:** würdest du diesen Satz laut sagen, wenn du dem Kunden den Report über den Tisch schiebst?

**`__NEXT_STEP__`:** die eine konkrete Handlung plus der Zeitpunkt, an dem darüber gesprochen wird. Ein Absatz, keine Liste.

### Drei Regeln, die im Audit anders gelten als im Monats-Report

Sie stehen auch im Template und sind der Grund für ein eigenes Template statt `report.html`:

- **Kein Vergleich, keine Bewegung.** Ein Audit ist Messpunkt eins. "Gestiegen", "verbessert", "im Trend" haben hier keinen Beleg. Eine vorliegende Reihe beschreibt den Verlauf im erhobenen Zeitraum, nie eine Wirkung.
- **Ein fehlender Wert wird als fehlend gezeigt**, nie als 0 und nie weggelassen. Eine leere Zelle liest sich als Null, und eine Null ist eine Messung.
- **Kopf, Einstieg und Schlussblock erklären nie, was fehlt.** Was nicht gemessen werden konnte, steht in Abschnitt 5 und nur dort; im Kopf erzeugt es eine Einschränkung, an die der Kunde vorher nicht gedacht hat.

### Ablauf

1. **Das Script ohne `--text` aufrufen.** Es schreibt die Textvorlage in den Lauf-Ordner und bricht mit Rückgabewert 2 ab:

   ```bash
   python3 -m audit.report_build --workspace . --run-id <run-id> --pdf
   ```

   (aus `${CLAUDE_PLUGIN_ROOT}/scripts` heraus, oder mit
   `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/scripts`.)

2. **`reporting/runs/<run-id>/report-text.json` füllen.** Vollständige Liste der Schlüssel, die das Script erwartet:

   | Schlüssel | Form | Inhalt |
   |---|---|---|
   | `cover_headline` | Text | die Cover-Zeile, ohne Schlusspunkt |
   | `intro` | HTML | vier Sätze, Ergebnis zuerst, siehe unten |
   | `summary_what` | Text | Gegenstand und Grundgesamtheit |
   | `summary_why` | Text | der Mechanismus, der den Lauf nötig macht |
   | `summary_status` | Text | die tragenden Zahlen als Satz |
   | `summary_problem` | Text | was aus dem stärksten Befund folgt |
   | `summary_possible` | Text | der Weg raus, ohne Preis und ohne Ablauf |
   | `takeaways` | HTML `<ol>` | fünf Sätze, jeder mit Zahl und Befund-Kennung |
   | `next_step` | HTML | der konkrete Ask |
   | `problems` | Liste | zwei bis vier Kacheln, siehe unten |
   | `section_messages` | Objekt | je Fachsektion ein Satz, siehe unten |

   - Fehlt ein Schlüssel, bricht das Script ab und nennt ihn. Gewollt: ein Dokument mit leerem Einstieg geht nie an einen Kunden.
   - Alle elf Schlüssel sind Pflicht (`report_build.text_laden()`):
     - die neun Textfelder `cover_headline`, `intro`, die fünf `summary_*`, `takeaways`, `next_step`
     - `problems` mit zwei bis vier Einträgen, je Eintrag `value`, `label`, `detail` und `finding_ref`
     - `section_messages` mit einem Satz je Sektion, außer `gaps`, `method` und `sources`
   - Die Vorlage nennt zu jedem Feld, was hineingehört, und darunter unter `_zahlen_dieses_laufs` die sechs Kennzahlen der Kennzahlenleiste samt Zeitraum, die Liste aller Befund-Kennungen und die Zahl der Maßnahmen. **Diese Zahlen beim Schreiben verwenden**, sonst entsteht ein Statussatz ohne Beleg.
   - `cover_headline` und `next_step` sind schlichte Sätze, siehe "Kopf, Einstieg und Schlussblock". Beide dürfen HTML enthalten; `intro`, `takeaways` und `next_step` erwarten es (`<p>`, `<ol><li>`).

3. **Erneut aufrufen, jetzt baut das Script.** Es:
   - setzt die Pfade `__CSS_PATH__`, `__LOGO_PATH__`, `__LOGO_REVERSED_PATH__`, immer absolut, weil headless Chrome keine Plugin-relativen Pfade auflöst
   - setzt die drei Identitäts-Platzhalter: `__BRAND__` aus `config.json > brand`, `__RUN_LABEL__` als lesbarer Stand wie "Stand Oktober 2026" (nie die rohe Lauf-ID), `__GENERATED_DATE__` als `TT.MM.JJJJ`
   - füllt die sechs Kennzahlen mit ihren Notizen, die Befund-Übersicht (`__FINDINGS_OVERVIEW__`), die sechzehn Sektionen samt Befunden und den Maßnahmenteil
   - entfernt den BAUKASTEN
   - setzt zuletzt den Schluss `__CLOSING__` über `closing.apply` aus `scripts/audit/closing.py` ein
   - schreibt `reporting/runs/<run-id>/audit.html`
   - bricht ab und nennt ihn, wenn ein Platzhalter oder ein `SECTION:`-Marker übrig bleibt; ein Dokument mit sichtbarer Marker-Zeile geht nie an einen Kunden

   **Der Schluss kommt aus den Einstellungen des Betreibers.**
   - `PTAI_CLOSING_FILE` gesetzt und lesbar: die Schlussseite des Betreibers ersetzt das Schluss-Panel zwischen den Markierungen `CLOSING:start` und `CLOSING:end` (dieselbe Seite wie im Monats-Report und in `audit-light`); die Markierungen bleiben stehen.
   - Sonst der neutrale Schluss: je gesetztem und gültigem Wert aus `PTAI_OPERATOR_NAME`, `PTAI_OPERATOR_CONTACT`, `PTAI_OPERATOR_EMAIL` und `PTAI_OPERATOR_BOOKING_URL` eine Kontaktzeile, darunter immer die Herkunftszeile, kein weiterer Satz. Ohne gültige Einstellung nur die Herkunftszeile.
   - Datei fehlt, ist nicht lesbar oder leer: Hinweis auf stderr, der Audit endet neutral.
   - `audit-web.html` endet mit demselben Schluss, die Schlussseite dort als Blatt mittig unter dem Inhalt.

   **Die Sitzung baut das HTML nicht selbst.** Fehler im Aufbau im Script korrigieren, nicht in der erzeugten Datei; ein Fix an der Kopie ist beim nächsten Lauf weg.

4. **Das PDF rendert derselbe Aufruf**, kein eigener Schritt (Abschnitt "Ein Aufruf, drei Dateien"):
   - `--pdf` übergibt `audit.html` an den Renderer aus `report` (`skills/report/scripts/render_pdf.sh`) und schreibt `audit.pdf`. Ein Script für beide Dokumente, damit Chrome-Suche, A4-Einstellung und Größenprüfung nicht auseinanderlaufen.
   - Ohne `--pdf` gibt das Script den Render-Befehl nur aus.

5. **Die Web-Fassung schreibt derselbe Aufruf** nach `reporting/runs/<run-id>/audit-web.html`, außer mit `--no-web`:
   - `python3 -m audit.report_web --workspace . --run-id <run-id>` baut sie allein neu; im Ablauf ist das nicht nötig.
   - Eine einzelne Datei mit Sprungnavigation, Volltextsuche und Filter nach Schweregrad.
   - Zwei Fassungen entsprechen IIA Standard 15.1 (mehrere Fassungen einer Abschlusskommunikation für verschiedene Zielgruppen). Das PDF wird weitergegeben, in der Web-Fassung wird gearbeitet.

   **Zum Ansehen einen Server starten, nicht doppelklicken:**

   ```bash
   python3 -m http.server 8080 --directory reporting/runs/<run-id>
   ```

   - Dann `http://localhost:8080/audit-web.html` öffnen.
   - Über `file://` verhält sich die Seite nicht in jedem Browser gleich: Safari und einige Konfigurationen behandeln lokale Dateien strenger, die Navigation bleibt dann ohne Fehlermeldung stehen.
   - **Die Seite bleibt ohne Skript benutzbar.** Abschnittslinks sind gewöhnliche Anker, der Abstand zur Kopfleiste kommt aus `scroll-margin-top`. Das Skript ergänzt nur Markierung des aktuellen Abschnitts, Filter und Menü; jeder Baustein läuft in seinem eigenen `try`, damit ein Fehler die übrigen nicht stoppt.
   - **Der Inhalt kommt aus `report_build.content()`, nie aus einem zweiten Builder.** Zwei Builder ergeben zwei Wahrheiten, und eine nur in einem korrigierte Zahl fällt nicht auf.
   - Die Datei lädt nichts von außen: kein CDN, kein Skript, keine Schrift. Sie muss auch in einem Jahr aus einem Ordner heraus funktionieren.

6. **Das PDF sichtprüfen:**
   - Archivo Black in den Überschriften
   - Logo oben rechts
   - die sechs Kacheln der Kennzahlenleiste auf Seite eins
   - Zusammenfassung und Erkenntnisse auf Seite zwei
   - Tabellen sauber
   - Schlussseite am Ende
   - **Seitenzahl gegen den Umfang prüfen:** ein Audit dieser Größe hat 40 bis 60 Seiten. Deutlich mehr heißt fast immer, dass ein Block ohne Rasterpartner in einem Grid steht.

7. **Jede Zahl auf Seite eins gegen die Wirklichkeit prüfen, nicht nur gegen das Quellfeld.**
   - Eine Zahl kann mit dem Snapshot übereinstimmen und trotzdem falsch sein (Beispiel: der Crawler liest die Zahlungs-Icons im Seitenfuß als Seitentitel aus).
   - Ein einzelner Abruf zeigt das:

   ```bash
   curl -s https://<domain>/ | grep -o '<title>[^<]*'
   ```

   - Gilt für jeden Befund in Einstieg, Erkenntnissen, Problem-Kacheln oder Schlussblock: **erst nachsehen, dann hinschreiben.** Vier bis sechs Zahlen, fünf Minuten.
   - Ein Befund, der sich nicht in einer Minute gegenprüfen lässt, gehört nicht auf die erste Seite.
   - Meldet der Crawler etwas unter `crawl.json > summary.self_check`, dort zuerst nachsehen.

8. **Das Script meldet beim Bauen die Lesbarkeit** des Fließtexts: Wiener Sachtextformel, LIX und mittlere Satzlänge.
   - Das ist ein Regressionstest, kein Qualitätsnachweis; die Formeln messen Wort- und Satzlänge, nicht Verständnis.
   - Liegt ein Wert deutlich außerhalb des Bands: die Stelle ansehen, nicht Sätze mechanisch teilen.

9. **Die Abnahme ausführen**, jetzt über den ganzen Lauf:

    ```bash
    python3 -m audit.qa --workspace . --run-id <run-id> --phase 4
    ```

    - Zusätzlich zu Phase 2 prüft sie die Maßnahmen (zeigt jede auf einen existierenden Befund, hat jede eine Prüfregel) und das fertige Dokument (kein Platzhalter übrig, keine Ersatzumlaute, Lesbarkeit im Band).
    - Danach die Liste abarbeiten, die sie für den Menschen ausgibt.

10. **Zahlen gegenlesen:** jede Kachel, jede abgeleitete Größe, jeden Prozentwert gegen sein Quellfeld. Auffälligkeiten im Script korrigieren, nicht im HTML.

**Kein Browser auf dem Rechner:** `render_pdf.sh` bricht mit klarer Meldung ab.

- Kein Fehlschlag der Phase: `baseline.md` und `measures.md` stehen, das HTML ist fertig.
- Dem Nutzer den Render-Befehl zum Nachholen geben.
- Die Phase gilt als erledigt, das PDF als offener Punkt.

**Artefakte:** `reporting/baseline/01/baseline.md`, `reporting/measures.md`, `reporting/runs/<run-id>/audit.html`, `reporting/runs/<run-id>/audit.pdf`, `reporting/runs/<run-id>/audit-web.html`.

**Bei Erfolg:** `run_state.set_phase('4-deliverables', 'done')`, `run_state.save()`. Danach dem Nutzer zusammenfassen:

- welche Baseline-Blöcke stehen
- welche noch leer sind (und mit `--backfill` folgen)
- wie viele Maßnahmen priorisiert wurden, wie viele Tests
- die im Lauf verbrauchte DataForSEO-Summe aus `reporting/dfs-ledger.jsonl`
- Pfade zu `baseline.md`, `measures.md`, dem PDF und dem Screenshot-Zielordner im Kundenordner

## Der Nachtrag-Modus: `--backfill`

Gilt bei `/ptai-ecom:audit --backfill` auf einem Shop mit unvollständiger Baseline (siehe "Ein Audit läuft genau einmal je Shop"). Statt des vollen Fünf-Phasen-Zyklus füllt der Nachtrag nur, was fehlt, und ändert keinen geschriebenen Block.

**Schritte:**

1. `baseline.empty_blocks(workspace)` liefert die leeren Blöcke in der Reihenfolge von `baseline.BLOCKS`. Nur diese werden bearbeitet.
2. Für jeden leeren Block die Quell-Schlüssel aus der Tabelle in Phase 3, Schritt 1 nachschlagen ("Quell-Schlüssel im `state`").
   - Gezogen wird nur, was einer dieser Blöcke braucht, nie die volle Quellenliste aus Phase 1.
   - Eine Quelle, deren Block schon geschrieben ist, wird nicht gezogen.
3. Eigene Lauf-ID, eigener Zustand: `run.run_id(today, "audit")` und ein eigenes `state.json` unter `reporting/runs/<run-id>/`.
   - Die ermittelten Quellen laufen nach derselben Mechanik wie Phase 1: isoliert je Quelle, ein Schreiber für den Zustand (`run_state.set_source()` plus `run_state.save()` nach jedem Ergebnis).
4. Für jeden Block, dessen Quell-Schlüssel jetzt alle auf `done` stehen (`not run_state.source_open(source)` je Schlüssel, dieselbe Prüfung wie in Phase 3, Schritt 1):
   - Werte nach `reference/metrics.md` bilden.
   - `baseline.write_block(workspace, block, values, run_id=run_id,
   today=today, sources=sources)` aufrufen, `sources` wie in Phase 3, Schritt 1.
   - **Hier ist die Trennung entscheidend:** `today` ist der Nachtragstag, `pulled_at` der Tag, an dem die Quelle gezogen wurde; beide stehen danach getrennt in `baseline.md`.
   - Direkt danach `baseline.render(workspace)` erneut ausführen, damit `baseline.md` den nachgetragenen Block zeigt.

**Artefakt:** `reporting/baseline/01/baseline.json` und `baseline.md`, um die zuvor leeren Blöcke ergänzt.

- `reporting/measures.json` bleibt unverändert; eine neue Analyse der jetzt verfügbaren Quelle gehört nicht zu diesem Modus.

**Ein nachgetragener Block ist ein eigener, späterer Messpunkt.**

- Er hat sein eigenes `as_of` (Festschreibedatum, Lauf-ID und je Quelle Erhebungsdatum plus Zeitraum, siehe `baseline.write_block()`); `baseline.render()` zeigt beides unter der Blocküberschrift.
- Zwischen Erstlauf und Nachtrag hat sich der Shop verändert. Der nachgetragene Block hat diese Veränderung nie beobachtet; seine Zeitreihe beginnt an seinem eigenen Stichtag.
- Steht das nicht neben dem Wert, liest der nächste `/ptai-ecom:report`-Vergleich zwei verschiedene Nullpunkte als einen und rechnet eine Bewegung, die nie stattfand.
- Die Zusammenfassung am Ende des Nachtrags nennt deshalb je gefülltem Block sein `as_of` und sagt ausdrücklich, dass es ein späterer, eigener Messpunkt ist, kein Teil des Erstlauf-Nullpunkts.

**Regelfall: die drei Stufe-2-Blöcke.**

- `seo_visibility`, `sea` und `catalogue` bleiben in jedem Lauf leer, dessen Workspace die Zugänge nicht hatte; dafür ist `--backfill` gebaut.
- Seit dem 07.09.2026 haben alle drei einen Quell-Schlüssel und eine Formel-Tabelle (Phase 3, Schritt 2); der Nachtrag läuft bis zum geschriebenen Block durch.

| Block | Wartet auf | Vorbehalt |
|---|---|---|
| `seo_visibility` | `dfs_rankings`, `dfs_keywords`, `backlinks` | DataForSEO-Guthaben und Budgetdeckel. Der Sichtbarkeitsverlauf entsteht nur mit `--with-history` |
| `sea` | `ads` | Google-Ads-Zugang, Freigabe des Cloud-Projekts für echte Konten |
| `catalogue` | `catalogue` | Shopify-Admin-Zugang mit Katalog-Scope |

**Ein Nachtrag ohne Zugang tut nichts und meldet das.** Fehlt der Zugang weiterhin, bleibt der Block leer, und der Modus nennt den Grund aus `state.json`, statt still zu enden.

## Fehlerbilder

| Fehlerbild | Vorgehen |
|---|---|
| **Config fehlt oder ist ungültig** | siehe Voraussetzungen und Phase 0: `setup` anbieten, nicht raten |
| **Zweiter voller Aufruf auf einen Shop mit bestehender Baseline** | siehe "Ein Audit läuft genau einmal je Shop": verweigern, auf `report` oder `--backfill` verweisen |
| **Beschädigte `state.json` oder `baseline.json`** | beide Module werfen absichtlich (`ValueError`), nie ein stiller Neuanfang, der bezahlte Abfragen bzw. geschriebene, unveränderliche Blöcke verwerfen würde. Datei prüfen, reparieren oder gezielt löschen, nicht den ganzen Lauf-Ordner |
| **Einzelne Quelle in Phase 1 scheitert** | isoliert behandeln, `failed` mit Grund, die übrigen Quellen laufen weiter, Gate A weist es aus |
| **Alle Quellen scheitern** | Gate A zeigt nur "fehlend" und "übersprungen". Kein technischer Abbruch; die Rückfrage an Gate A ("weiterlaufen?") ist hier die Fehlerbehandlung, ohne Rohdaten liefert Phase 2 nichts Belastbares |
| **Einzelner Analyse-Subagent scheitert in Phase 2** | isoliert behandeln, Gate B weist die fehlende Disziplin mit Grund aus, die übrigen Befunde gehen normal in Phase 3 |
| **Unterbrochener Lauf** (Absturz, abgebrochene Sitzung, bewusstes Anhalten an einem Gate) | `state.json` bleibt auf der zuletzt abgeschlossenen Phase; ein erneuter Aufruf von `/ptai-ecom:audit` lädt über `state.load_or_new()` denselben Zustand und setzt über `next_phase()` genau dort fort; keine Quelle mit Status `done` wird erneut gezogen |
| **`--backfill` auf einen vollständigen Shop** | kein Block ist leer, nichts nachzutragen; derselbe Fall wie `vollstaendig` oben, Verweis auf `report` |
