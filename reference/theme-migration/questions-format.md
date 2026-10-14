# Fragen, Punkte ohne Frage und Übergabe: Format

Seit 0.3.14. Das Team einer Marke beantwortet die Fragen der Migration im Cockpit, nicht in der Sitzung.
Dafür trägt jede Frage alles, was die Person zum Entscheiden braucht, und was eine Regel entscheidet,
steht sichtbar daneben. Drei Dateien im Workspace des Stores, alle unter `migration/`, alle im Repo:

| Datei | Wer schreibt | Modul |
|---|---|---|
| `questions.json` | `questions ask`, `answer`, `import`, `withdraw` | `theme.questions` |
| `ruled.json` | `ruled add`, `ruled revoke`, `questions withdraw` | `theme.ruled` |
| `next.json` | `handover write`, am Ende jeder Sitzung | `theme.handover` |

`run_state` liest alle drei nach jedem Befehl in `migration.json`, die einzige Datei, die das Cockpit
liest. Von Hand ändert man keine davon; eine beschädigte Datei hält den Export an, statt still neu
angelegt zu werden.

## Die Regel für Fragen

Standard ist "wie heute", "wie im Referenz-Store der Marke" oder die Vorgabe der Marke. Gefragt wird nur
bei einem echten Zielkonflikt, den keine Regel auflöst, und dann immer mit Erklärung, Vergleich heute und
Entwurf und Empfehlung mit Grund. Was eine Regel entscheidet, steht in `ruled.json` und im Blatt der
Migration im Cockpit unter "Entscheidungen" bei "Entschieden", mit Herkunft; das Team kann dort
"Änderung anfragen". Offene Fragen stehen dort unter "Ausstehend".

## `questions.json`

```json
{
  "questions": [
    {
      "id": "Q-004",
      "gate": "G2-mapping",
      "text": "Gestaltung vor oder nach der Abnahme angleichen?",
      "context": "Der Entwurf weicht an 12 Stellen sichtbar vom heutigen Shop ab, etwa beim Kaufknopf. Angeglichen wird alles vor dem Launch. Offen ist nur, ob schon vor der Abnahme.",
      "compare": [
        {"label": "Produktseite",
         "live_url": "https://beispielshop.test/products/ring?preview_theme_id=000000000000",
         "draft_url": "https://beispielshop.test/products/ring?preview_theme_id=000000000002"}
      ],
      "options": ["Vor der Abnahme", "Nach der Abnahme"],
      "other": null,
      "recommendation": "Vor der Abnahme",
      "reason": "Sonst meldet ihr in der Abnahme dieselben Abweichungen noch einmal.",
      "decider": ["Erika Muster"],
      "status": "answered",
      "asked_at": "2026-01-12T15:00:00+00:00",
      "answer": "Vor der Abnahme",
      "answered_by": "Erika Muster",
      "answered_at": "2026-01-13T09:12:00+00:00",
      "answered_via": "cockpit"
    }
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `id` | `Q-001`, fortlaufend je Lauf |
| `gate` | `G1-decisions` (Schritt 2), `G2-mapping` (Schritt 3) oder `G4-acceptance` (Schritt 6) |
| `text` | die Frage in einem Satz |
| `context` | worum es geht und was schon feststeht, in der Sprache des Kunden (ihr, euch). Pflicht |
| `compare` | Seitenpaare heute und Entwurf, `label`, `live_url`, `draft_url`, beide Links mit `?preview_theme_id=<id>`, sonst zeigt Shopify das Theme aus dem Cookie. Leer, wenn es nichts zu sehen gibt |
| `options` | die Antworten zum Anklicken |
| `other` | Beschriftung einer Antwort mit Freitext, etwa "Eine andere Person", sonst `null`. Zusammen mit `options` mindestens zwei Antworten |
| `recommendation` | eine der `options`, oder `null` für ausdrücklich keine Empfehlung (`--no-recommendation`) |
| `reason` | der Grund der Empfehlung, ohne Empfehlung worauf es bei der Entscheidung ankommt. Pflicht |
| `decider` | wer entscheidet, Namen aus `theme_migration.people`; leer heißt jede Person von dort |
| `status` | `open`, `answered` oder `withdrawn` |
| `answer`, `answered_by`, `answered_at` | die Antwort, die Person und der Zeitpunkt |
| `answered_via` | `cockpit` (übernommen mit `questions import`) oder `session` (`questions answer`); fehlt bei Antworten vor 0.3.14 und gilt dann als `session` |
| `withdrawn_at`, `ruled_id` | bei `withdrawn`: wann, und unter welchem Punkt in `ruled.json` das Ergebnis steht |

Fragen aus älteren Läufen ohne `context`, `compare`, `other`, `reason` und `decider` bleiben lesbar; in
`migration.json` stehen die fehlenden Felder als `null` oder leere Liste.

### Antworten aus dem Cockpit

Das Werkzeug `get_migration` des Cockpits hängt an jede offene Frage `cockpit_answer`. Daraus entsteht die
Eingabe für `questions import --file <datei>` (oder `--file -` für stdin):

```json
[{"id": "Q-004", "value": "Vor der Abnahme", "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00"}]
```

Übernommen wird eine Antwort nur, wenn `by` in `theme_migration.people` steht, die Frage im Repo offen ist
und die Antwort etwas entscheidet ("vorläufig" oder "später" nicht). Eine im Repo eingetragene Antwort
gilt; eine spätere im Cockpit ändert sie nicht. Ausgabe:

```json
{"imported": [{"id": "Q-004", "value": "Vor der Abnahme", "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00"}],
 "skipped": [{"id": "Q-005", "by": "Max Beispiel", "reason": "Max Beispiel steht nicht in theme_migration.people (Erika Muster)."}]}
```

Exit 0, wenn alles übernommen ist, 1, wenn etwas übersprungen wurde, 2 bei einem Fehler (Datei fehlt, kein
JSON, keine Liste).

## `ruled.json`

```json
{
  "ruled": [
    {"id": "R-001", "text": "Kontaktformular mit Betreff, Einwilligung und Captcha wie heute", "source": "as_today",
     "at": "2026-01-12T15:10:00+00:00", "question_id": "Q-002"},
    {"id": "R-002", "text": "Zuletzt angesehen entfällt", "source": "check", "at": "2026-01-12T15:12:00+00:00",
     "revoked_at": "2026-01-13T10:00:00+00:00", "revoke_reason": "Änderung angefragt von Erika Muster: wird genutzt"}
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `id` | `R-001`, fortlaufend je Lauf |
| `text` | was gilt, in einem Satz für das Team |
| `source` | `policy` (Vorgabe der Marke), `as_today` (wie heute), `as_reference` (wie im Referenz-Store), `operator` (vom Betreiber eingetragen), `check` (Prüfung im Shop). Das Cockpit zeigt als Herkunft "Vorgabe", "Unverändert", "Referenz-Store", "Path to AI" und "Im Shop festgestellt" |
| `at` | wann der Punkt entstand |
| `question_id` | die zurückgezogene Frage, aus der er entstand; fehlt bei `ruled add` |
| `revoked_at`, `revoke_reason` | wenn eine angefragte Änderung ("Änderung anfragen" im Cockpit, `objections` in `get_migration`) den Punkt doch zur Frage macht (`ruled revoke`) |

Derselbe Text mit derselben Herkunft entsteht nur einmal. In `migration.json` stehen nur die geltenden
Punkte, je `id`, `text` und `source`.

## `next.json`

```json
{
  "now": "Abstimmung",
  "after": "Beantwortet die zwei Fragen im Cockpit und startet die Migration danach neu. Claude baut den Entwurf dann um und prüft ihn.",
  "operator_tasks": ["Wir lesen die Liste der installierten Apps im Shopify-Admin."],
  "step": 2,
  "written_at": "2026-01-12T17:30:00+00:00"
}
```

| Feld | Bedeutung |
|---|---|
| `now` | im Kopf des Blatts nach dem Schritt ("Schritt 3 von 9: <now>"), meist der Name des aktuellen Schritts |
| `after` | der Text unter "Migration fortsetzen", in der Sprache des Kunden (ihr, euch) |
| `operator_tasks` | was der Betreiber tun muss, bevor es weitergeht; leer heißt nichts |
| `step` | der Schritt (1 bis 9), in dem die Übergabe geschrieben wurde; `handover write` setzt ihn |
| `written_at` | wann |

Steht der Lauf in einem anderen Schritt als `step`, gilt die Übergabe nicht mehr. Ohne Datei oder mit
veralteter gilt in `migration.json`: `now` ist der Name des aktuellen Schritts, `after` leer,
`operator_tasks` leer.

## In `migration.json`

Neu seit 0.3.14, das Schema bleibt 1:

| Feld | Herkunft |
|---|---|
| `repo` | Name des Workspace-Repos ohne Besitzer: Basis des Remote `origin` ohne `.git`, sonst der Ordnername |
| `now`, `after`, `operator_tasks` | `next.json`, mit dem Rückfall oben |
| `ruled` | die geltenden Punkte aus `ruled.json`, je `id`, `text`, `source` |
| `questions` | jede offene und jede beantwortete Frage mit `id`, `gate`, `step`, `text`, `context`, `compare`, `options`, `other`, `recommendation`, `reason`, `decider` und `answer` (`{value, by, at, via}` oder `null`). Zurückgezogene Fragen fehlen; ihr Ergebnis steht in `ruled` |

Seit 0.3.16 heißt Schritt 6 "Abnahme" und der Meilenstein davor "Bereit für die Abnahme" (vorher
"Testrunde"). Bezeichner bleiben (`test_round`, `ready_for_test_round`, Phase `8-test-round`). Steht in
`next.json`, `ruled.json` oder `questions.json` eines bestehenden Laufs noch "Testrunde", zeigt
`migration.json` dort "Abnahme" (Mehrzahl "Abnahmen"), in `text`, `context`, `options`, `other`,
`recommendation`, `reason` und `answer.value` jeder Frage, in `text` jedes Punkts und in `now`, `after` und
`operator_tasks`. Die Dateien selbst bleiben, wie die Sitzung sie geschrieben hat; neue Sätze schreibt die
Skill mit "Abnahme".
