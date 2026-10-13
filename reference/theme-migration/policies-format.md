# Vorgaben einer Marke: Format von `policies.json`

Seit 0.3.11. Eine Marke mit mehreren Stores entscheidet einmal, was in allen Stores gleich sein soll, und
diese Entscheidungen gelten im Lauf jedes Stores (`theme.policies apply`, beim Start von `theme-migration` und in
`theme-launch`). Die Datei liegt im Ordner der Marke, nie im Plugin und nie in einem öffentlichen Repo. Seit
0.3.15 entscheidet die Marke offene Vorgaben auch im Cockpit; `import` trägt diese Antworten hier ein (Abschnitt
"Antworten aus dem Cockpit").

```json
{
  "version": "2026-01-05.1",
  "reference_shop": "beispielshop",
  "decided_by": "Vorname Nachname",
  "decided_at": "2026-01-05",
  "rules": [
    {
      "key": "cookie_banner",
      "subject": "Cookie-Banner",
      "rule": "same_as_reference",
      "target": "Banner A",
      "keep": [["banner-a", "app:banner-a"]],
      "drop": ["app:banner-b"],
      "note": "Wechsel in der Migration"
    },
    {"key": "translation", "subject": "Übersetzung", "rule": "open", "note": "erst im Referenz-Store klären"},
    {"key": "languages", "subject": "Sprachen", "rule": "may_differ", "note": "je Marke"},
    {"key": "bundles", "subject": "Beispielbundle", "rule": "same_as_reference", "target": "wie im Referenz-Store",
     "keep": [["app:beispielbundle", "beispielbundle"]],
     "decided_by": "Erika Muster", "decided_at": "2026-01-13T09:12:00+00:00"}
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `version` | eindeutig je Fassung, Datum und laufende Nummer am Tag (`2026-01-05.1`); eine neue Fassung bekommt eine neue Version |
| `reference_shop` | der Store, dessen Stand gilt, wo `same_as_reference` steht |
| `decided_by`, `decided_at` | wer die Vorgaben entschieden hat und wann; steht an jeder Entscheidung im Lauf, sofern die Regel keine eigenen trägt |
| `rules[].key` | Merkmal, eindeutig, englisch |
| `rules[].subject` | Bezeichnung für Menschen |
| `rules[].rule` | `same_as_reference`, `open` oder `may_differ` |
| `rules[].target` | Zielwert in Worten, erscheint im Cockpit als "bis zum Launch: …" |
| `rules[].keep`, `rules[].drop` | Dienst-IDs wie in `apps.json` (`app:<handle>`), nur bei `same_as_reference`. Ein Eintrag darf eine Liste von Schreibweisen desselben Dienstes sein, etwa `["cookiefirst", "app:cookiefirst-cookie-consent"]`, weil die Inventare der Stores ihn verschieden benennen. Beim Behalten genügt eine vorhandene Schreibweise; fehlt jede, entsteht ein Punkt zum Einbauen |
| `rules[].note` | Begründung oder offene Frage |
| `rules[].decided_by`, `rules[].decided_at` | optional: wer diese Regel entschieden hat und wann, gesetzt von `import` für eine Antwort aus dem Cockpit. Sie gehen statt der Angaben der Datei an die Entscheidungen im Lauf |

## Was `apply` im Lauf eines Stores tut

1. Kopie nach `migration/policies.json` mit `applied_at`.
2. Je Dienst in `keep` oder `drop` ein Eintrag in `migration/mapping/decisions.json` mit `source: policy`,
   `decided_by` aus der Datei und `replaces` mit den früheren Entscheidungen zu diesem Dienst.
3. Dieselbe Entscheidung in `migration/inventory/apps.json`, damit der Generator sie beim nächsten Neubau
   liest (`--apps`).
4. Ein Dienst in `keep`, der im Inventar fehlt, wird ein Punkt `blocker` in der Liste offener Punkte: er
   muss vor der Testrunde eingebaut sein.
5. Im Migrationslauf `policies_version` und `policies_applied_at`; Schritt 3 steht danach auf
   nacharbeiten, bis neu gebaut ist.

Eine Vorgabe öffnet nie eine Frage an das Team. Dieselbe Version zweimal anzuwenden ändert nichts, auch
`applied_at` nicht (Ausgabe `unchanged: true`); sonst verlangte Schritt 3 nach jedem Start einen neuen Neubau.

## Antworten aus dem Cockpit (`import`)

Seit 0.3.15. Eine Vorgabe ohne Regel oder mit `rule: open` steht als Frage in `policy_questions` im Setup des
Referenz-Stores (`reference/setup-format.md`). Das Cockpit zeigt sie im Setup auf der Karte "Vorgaben der Marke";
entscheiden können alle Mitglieder der Marke und der Betreiber. Die Skill `theme-migration` holt die Antworten beim
Start über das Werkzeug `get_setup` (`cockpit_answer` je Frage) und trägt sie ein:

```bash
python3 -m theme.policies import --brand-workspace <ordner mit policies.json> --file <antworten.json | -> \
  [--workspace <store>]
```

Eingabe, je beantworteter Frage ein Eintrag aus `key`, `cockpit_answer` und, empfohlen, `options`, `subject` und
`app` der Frage:

```json
[{"key": "bundles", "value": "An Beispielshop angleichen", "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00",
  "options": ["Abweichung erlauben", "An Beispielshop angleichen"], "subject": "Beispielbundle",
  "app": "app:beispielbundle"}]
```

- `options[0]` heißt `may_differ`, `options[1]` `same_as_reference` mit `target` "wie im Referenz-Store", wenn die
  Regel noch kein Ziel hat. Nennt die Frage eine App (`app:<handle>`), behält die angeglichene Regel sie unter
  beiden Schreibweisen der Inventare: `keep: [["app:<handle>", "<handle>"]]`. `apply` legt dann in jedem Store,
  dessen Inventar die App nicht kennt, einen Punkt `blocker` zum Einbauen an. Eine `app` ohne `app:` wird
  übersprungen. Ohne `options` gelten die Knöpfe des Cockpits: "Abweichung erlauben" und "An …
  angleichen". Eine andere Antwort wird übersprungen.
- Fehlt die Regel, legt `import` sie an (`subject` aus der Eingabe, sonst `key`); sonst ändert es sie. Wechselt
  eine Regel auf `may_differ`, entfallen `target`, `keep` und `drop`, die es nur bei `same_as_reference` gibt.
- Die Regel trägt danach `decided_by` (`by`) und `decided_at` (`at`). Das Plugin kennt die Mitglieder der Marke
  nicht; im Cockpit antworten nur Mitglieder, deshalb wird jede Antwort mit Namen übernommen.
- Die neueste Antwort gilt: Eine neuere Antwort im Cockpit ändert eine früher übernommene. Eine Regel, die im Repo
  später entschieden wurde (`decided_at` der Regel, sonst der Datei; ein Datum ohne Uhrzeit gilt für den ganzen
  Tag), bleibt, und die Antwort steht unter `skipped`.
- Hat sich etwas geändert, bekommt die Datei eine neue `version`: heute mit der nächsten Nummer, an einem neuen
  Tag `.1`. `decided_by` und `decided_at` der Datei bleiben.

Ausgabe:

```json
{"path": "<ordner>/policies.json", "version": "2026-01-13.1", "previous_version": "2026-01-05.1",
 "imported": [{"key": "bundles", "rule": "same_as_reference", "previous": null, "value": "An Beispielshop angleichen",
               "by": "Erika Muster", "at": "2026-01-13T09:12:00+00:00", "app": "app:beispielbundle"}],
 "unchanged": [], "skipped": [],
 "still_open": [{"key": "translation", "subject": "Übersetzung"}],
 "apply_needed": [{"shop": "beispielshop-eu", "workspace": "<ordner>/beispielshop-eu",
                   "applied_version": "2026-01-05.1", "own": true}]}
```

- `unchanged`: Antworten, die schon so gelten; sie ändern nichts und sind kein Befund.
- `still_open`: Regeln, die weiter auf `open` stehen.
- `apply_needed`: die Stores, deren Kopie `migration/policies.json` nicht auf der Version der Datei steht, auch
  wenn dieser Aufruf nichts geändert hat. Gesucht wird in den Ordnern im Ordner von `policies.json` und daneben,
  je mit einer Kopie derselben Marke (gleicher `reference_shop`); `--workspace` (Standard `.`) zählt auch ohne
  Kopie, sobald es einen Ordner `migration/` hat, und steht dann mit `own: true`. Ein Store, der auf diesem Rechner
  nicht liegt, fehlt; er übernimmt die Vorgaben beim nächsten Start seiner Migration.

Exit 0, wenn nichts übersprungen wurde, 1, wenn etwas übersprungen wurde, 2 bei einem Fehler (Ordner ohne
`policies.json`, kein JSON, keine Liste).
