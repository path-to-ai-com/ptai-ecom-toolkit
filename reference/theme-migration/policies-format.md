# Vorgaben einer Marke: Format von `policies.json`

Seit 0.3.11. Eine Marke mit mehreren Stores entscheidet einmal, was in allen Stores gleich sein soll, und
diese Entscheidungen gelten im Lauf jedes Stores (`theme.policies apply`, beim Start von `theme-migration` und in
`theme-launch`). Die Datei liegt im Ordner der Marke, nie im Plugin und nie in einem öffentlichen Repo. Seit
0.3.15 entscheidet die Marke offene Vorgaben auch im Cockpit; `import` trägt diese Antworten hier ein (Abschnitt
"Antworten aus dem Cockpit").

Seit 0.3.16 ist das Cockpit die einzige Quelle der Vorgaben für die Stores. Der Betreiber lädt `policies.json` und
den Ordner `policy-modules/` aus dem Ordner der Marke mit `audit.publish --policies-only` hoch (Abschnitt "Im
Cockpit"). Das Werkzeug `get_policies` gibt die gültige Fassung zurück, Datei plus Antworten aus dem Cockpit, und
`sync` schreibt sie beim Start von `theme-migration` in das Repo des Stores (Abschnitt "Fassung aus dem Cockpit").
Ein Store braucht dafür weder den Ordner der Marke noch ein anderes Repo.

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
     "decided_by": "Erika Muster", "decided_at": "2026-01-13T09:12:00+00:00"},
    {"key": "tag_manager", "subject": "Tag Manager", "rule": "same_as_reference", "target": "Tag Manager als eigener Code",
     "modules": [{"name": "Tag Manager", "path": "policy-modules/tag_manager/README.md",
                  "description": "Einbindung des Tag Managers im Theme wie im Referenz-Store"},
                 {"name": "Tag Manager", "path": "policy-modules/tag_manager/snippets/tag-manager.liquid",
                  "description": "Snippet mit Platzhalter für die Container-ID"}]}
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `version` | eindeutig je Fassung, Datum und laufende Nummer am Tag (`2026-01-05.1`); eine neue Fassung bekommt eine neue Version |
| `reference_shop` | der Store, dessen Stand gilt, wo `same_as_reference` steht |
| `decided_by`, `decided_at` | wer die Vorgaben entschieden hat und wann; steht an jeder Entscheidung im Lauf, sofern die Regel keine eigenen trägt. Fehlen sie, braucht jede Regel `same_as_reference` oder `may_differ` eigene (Fassung aus dem Cockpit ohne Datei des Betreibers) |
| `rules[].key` | Merkmal, eindeutig, englisch |
| `rules[].subject` | Bezeichnung für Menschen |
| `rules[].rule` | `same_as_reference`, `open` oder `may_differ` |
| `rules[].target` | Zielwert in Worten; im Cockpit steht er im Blatt einer Vorgabe nur, wenn keine Zeile des Setups zu ihr gehört. Sonst zeigt das Blatt je Store das Ziel zum Launch aus dem Setup des Referenz-Stores |
| `rules[].keep`, `rules[].drop` | Dienst-IDs wie in `apps.json` (`app:<handle>`), nur bei `same_as_reference`. Ein Eintrag darf eine Liste von Schreibweisen desselben Dienstes sein, etwa `["cookiefirst", "app:cookiefirst-cookie-consent"]`, weil die Inventare der Stores ihn verschieden benennen. Beim Behalten genügt eine vorhandene Schreibweise; fehlt jede, entsteht ein Punkt zum Einbauen |
| `rules[].note` | Notiz für den Betreiber und Claude, etwa die Zeile einer eigenen Tabelle. Im Cockpit steht sie nie; dort erklären `context` und `reason` die Regel |
| `rules[].decided_by`, `rules[].decided_at` | optional: wer diese Regel entschieden hat und wann, gesetzt von `import` für eine Antwort aus dem Cockpit. Sie gehen statt der Angaben der Datei an die Entscheidungen im Lauf |
| `rules[].context` | Pflicht vor dem Hochladen, seit 0.3.18: worum es geht, in zwei bis drei Sätzen für das Team der Marke, in der Sprache von E-Commerce-Leuten, mit ihr und euch. Steht im Cockpit als erster Absatz im Blatt der Vorgabe |
| `rules[].reason` | Pflicht vor dem Hochladen: warum so entschieden; bei `open` warum empfohlen, ohne Empfehlung, worauf es bei der Entscheidung ankommt. Im Cockpit "Begründung" oder "Empfehlung" |
| `rules[].recommendation` | optional, nur bei `open`: `same_as_reference` oder `may_differ`; im Dropdown trägt diese Option "Empfohlen" |
| `rules[].outcomes` | Pflicht vor dem Hochladen: je Option (`same_as_reference`, `may_differ`) ein Satz, was sie für genau diese Vorgabe bewirkt, mit den Namen der Stores, etwa "AT und CH laden den Tag Manager zum Launch direkt im Theme". Steht im Cockpit unter dem Wert im Dropdown |
| `rules[].needs` | Pflicht vor dem Hochladen: je Option eine Liste `{"shops": [<slug>], "text": "<Satz>"}`, was das Team der Marke tun muss, etwa ein Konto anlegen; leer, wenn nichts. Im Cockpit "Eure Mitwirkung" mit den Stores als Pille. Was Path to AI tun muss, steht hier nicht |
| `rules[].modules` | optional, seit 0.3.16: Bausteine, mit denen ein Store die Regel im Theme umsetzt, je `{"name", "path", "description"}`. `name` steht im Cockpit an der Regel ("Baustein: <name>"), `description` (optional) sagt in einem Satz, was die Datei ist. `path` ist immer `policy-modules/<key>/<datei>`, auch mit Unterordnern, nie mit `..` oder Backslash; die Datei liegt im Ordner `policy-modules/` neben `policies.json`. Ein Baustein ist eine Vorlage mit Beschreibung (`README.md`), kein Code eines bestimmten Stores |

## Was `apply` im Lauf eines Stores tut

1. Kopie nach `migration/policies.json` mit `applied_at`.
2. Je Dienst in `keep` oder `drop` ein Eintrag in `migration/mapping/decisions.json` mit `source: policy`,
   `decided_by` aus der Datei und `replaces` mit den früheren Entscheidungen zu diesem Dienst.
3. Dieselbe Entscheidung in `migration/inventory/apps.json`, damit der Generator sie beim nächsten Neubau
   liest (`--apps`).
4. Ein Dienst in `keep`, der im Inventar fehlt, wird ein Punkt `blocker` in der Liste offener Punkte: er
   muss vor der Abnahme eingebaut sein.
5. Im Migrationslauf `policies_version` und `policies_applied_at`; Schritt 3 steht danach auf
   nacharbeiten, bis neu gebaut ist.

Eine Vorgabe öffnet nie eine Frage an das Team. Dieselbe Version zweimal anzuwenden ändert nichts, auch
`applied_at` nicht (Ausgabe `unchanged: true`); sonst verlangte Schritt 3 nach jedem Start einen neuen Neubau.
Bausteine (`modules`) trägt `apply` nicht ein; sie baut der Neubau ein (Skill `theme-migration`, Phase 4).

## Im Cockpit

Seit 0.3.16. Der Betreiber lädt die Vorgaben aus dem Ordner der Marke hoch:

```bash
python3 -m audit.publish --workspace <store> --policies-only --target <leerer ordner> --upload
```

`--policies-only` (seit 16.10.2026) lädt nur `policies.json`, die Bausteine und das Manifest. Maßnahmen und
Anforderungen der Marke bleiben im Bucket, wie sie sind, und die Prüfung der Maßnahmen (`audit.readiness`) läuft
nicht; eine neue Fassung der Vorgaben wartet so nicht auf die Maßnahmen. Im Manifest ersetzt die Fassung jeden
Eintrag der Vorgaben unter `files`, auch Bausteine, die es nicht mehr gibt. `--brand-only` lädt die Vorgaben
zusammen mit Maßnahmen und Anforderungen und hält an, solange eine Maßnahme der Marke nicht umsetzbar ist.

`policies.json` und jede Datei unter `policy-modules/` gehen nach `brands/<brand>/` im Bucket und stehen im Manifest
unter `files`, neben `measures.json`. Gesucht wird `policies.json` im Ordner der Marke (`brand_workspace`), sonst
in genau einem Ordner direkt darin, etwa `shared/`; `policy-modules/` liegt daneben. Vor dem Hochladen prüft
`publish` das Format und dass jede Datei aus `modules` dort liegt; sonst geht nichts hoch. Dieselben Dateien
gehen auch mit jedem Lauf eines Stores der Marke hoch, weil `publish` die Liste `files` im Manifest jedes Mal
neu schreibt.

Das Cockpit zeigt die Vorgaben im Setup auf der Karte "Vorgaben der Marke" und hält Antworten in
`policy_responses`; die neueste Antwort je Regel gilt vor der Regel aus der Datei. `get_policies(brand)` gibt die
gültige Fassung zurück:

- `rules` im Format dieser Datei, jede Antwort aus dem Cockpit eingesetzt wie bei `import` (mit `decided_by`
  und `decided_at` der Antwort); eine offene Frage ohne Regel in der Datei steht als `rule: open`
- `version` (Datum der neuesten Änderung und laufende Nummer), `file_version` (Version der Datei),
  `reference_shop`, `reference_shop_name`, `decided_by` und `decided_at` der Datei (`null` ohne Datei), dazu
  die übrigen Felder am Kopf der Datei und `brand`
- je Baustein `name`, `path`, `description` und `content` mit dem Text der Datei, `null`, wenn sie im Bucket fehlt
- `open_rules` (offene Vorgaben) und `cockpit_questions` (Rückfragen des Teams, je `key`, `text`, `by`, `at`)

## Fassung aus dem Cockpit (`sync`)

Seit 0.3.16. Die Skill `theme-migration` liest beim Start `get_policies` und schreibt die Fassung in das Repo des
Stores, danach `apply` wie bisher:

```bash
python3 -m theme.policies sync --file <ausgabe von get_policies | -> [--workspace <store>]
python3 -m theme.policies apply --source migration/policies.json [--workspace <store>]
```

Eingabe, die Ausgabe von `get_policies` unverändert:

```json
{"brand": "beispielmarke", "version": "2026-01-13.2", "file_version": "2026-01-05.1",
 "reference_shop": "beispielshop", "reference_shop_name": "Beispielshop",
 "decided_by": "Vorname Nachname", "decided_at": "2026-01-05",
 "rules": [{"key": "tag_manager", "subject": "Tag Manager", "rule": "same_as_reference",
            "target": "Tag Manager als eigener Code",
            "modules": [{"name": "Tag Manager", "path": "policy-modules/tag_manager/README.md",
                         "description": "Einbindung des Tag Managers im Theme wie im Referenz-Store",
                         "content": "# Tag Manager\n..."}]},
           {"key": "wishlist", "subject": "Merkliste", "rule": "open"}],
 "open_rules": [{"key": "wishlist", "subject": "Merkliste", "text": "Merkliste: in allen Stores gleich?"}],
 "cockpit_questions": []}
```

- `migration/policies.json` bekommt nur die Felder dieses Formats: am Kopf `version`, `reference_shop`,
  `decided_by`, `decided_at`, je Regel `key`, `subject`, `rule`, `target`, `keep`, `drop`, `note`,
  `decided_by`, `decided_at`, `modules`, je Baustein `name`, `path`, `description`. Alles andere (`brand`,
  `file_version`, `reference_shop_name`, `open_rules`, `cockpit_questions`, unbekannte Felder) zählt nicht, ein
  Wert `null` heißt "fehlt". So ändert eine neue Rückfrage im Cockpit die Datei im Repo nicht. Jeder Baustein
  geht nach `migration/policy-modules/<key>/<datei>`. Dateien unter `migration/policy-modules/`, die die Fassung nicht mehr
  nennt, löscht `sync`; der Ordner ist ein Abbild der Bausteine der Marke.
- Nennt die Eingabe unter `brand` eine andere Marke als der Store (`portal.brand`, sonst `account_slug`), schreibt
  `sync` nichts. Ebenso bei einer Fassung, die dieses Format verletzt, oder einem Pfad außerhalb von
  `policy-modules/<key>/`.
- Ein Baustein mit `content: null` (Datei im Bucket fehlt) steht unter `modules_missing`; sein Verweis bleibt
  in `policies.json`, eine frühere Datei im Repo wird gelöscht, alles andere ist geschrieben. Exit 1.
- Ist alles wie in der Kopie (gleiche `version`, keine Regel und kein Baustein geändert), bleibt `applied_at`
  stehen, und `apply` danach ändert nichts. Sonst fällt `applied_at` weg: `apply` trägt die Fassung ein, und
  Schritt 3 verlangt einen Neubau, der auch geänderte Bausteine einbaut. Eine Regel gilt als geändert, wenn sich
  ein Feld außer `decided_by` und `decided_at` ändert.
- Führt die Marke keine Vorgaben (`rules` fehlt oder ist leer), schreibt `sync` nichts und meldet
  `available: false`.

Ausgabe:

```json
{"available": true, "path": "migration/policies.json", "version": "2026-01-14.1",
 "previous_version": "2026-01-13.1", "changed": true, "apply_needed": true,
 "rules_changed": [{"key": "translation", "subject": "Übersetzung", "change": "changed", "previous": "open",
                    "rule": "may_differ", "fields": ["rule"]}],
 "modules_written": [{"key": "tag_manager", "name": "Tag Manager",
                      "path": "migration/policy-modules/tag_manager/README.md"}],
 "modules_removed": [], "modules_missing": [],
 "still_open": []}
```

- `rules_changed`: je Regel `change` (`added`, `changed`, `removed`), die Regel vorher und nachher und bei
  `changed` die geänderten Felder.
- `modules_written`: neue oder geänderte Dateien; `modules_removed`: gelöschte; `modules_missing`: Bausteine,
  die das Cockpit ohne Inhalt geliefert hat.
- `apply_needed`: `apply` trägt danach etwas ein. `changed`: im Repo hat sich etwas geändert, also committen.
- `still_open`: Regeln, die weiter auf `open` stehen.

Exit 0, auch ohne Vorgaben der Marke, 1, wenn ein Baustein ohne Inhalt kam, 2 bei einem Fehler; dann ist
nichts geschrieben.

## Antworten aus dem Cockpit (`import`)

Seit 0.3.15. Eine Vorgabe ohne Regel oder mit `rule: open` steht als Frage in `policy_questions` im Setup des
Referenz-Stores (`reference/setup-format.md`). Das Cockpit zeigt sie im Setup auf der Karte "Vorgaben der Marke";
entscheiden können alle Mitglieder der Marke und der Betreiber.

Seit 15.10.2026 Pflicht, geprüft von `publish` vor jedem Upload: Jede Regel mit `rule: open` hat eine Frage, und
jede offene Regel und jede Frage findet mindestens eine Zeile im neuesten Setup eines Stores (über ihren `key`, die
`app` der Frage oder `keep` und `drop`). Sonst zeigte das Blatt der Vorgabe im Cockpit nur die Notiz und keine
Tabelle "In den Stores". Kein Text einer Frage verweist auf eine Zeile einer Tabelle ("Zeile 21"). Eine entschiedene
Regel ohne Zeile meldet `publish` nur als Hinweis. Von Hand prüfen:

```bash
python3 -m theme.policies sheets --source <policies.json> --setup <setup.json des Referenz-Stores> \
  [--setup <setup.json eines weiteren Stores> ...]
```

Eine Vorgabe, die zwei Dienste zusammenfasst, wird für die Frage in zwei Regeln geteilt: Eine Frage nennt genau eine
`app`, und jede bekommt im Cockpit ihre eigene Entscheidung. Die Skill `theme-migration` holt die Antworten beim
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

## Texte für die Marke (seit 0.3.18)

`audit.publish` hält vor dem Kopieren an, solange einer Regel `context`, `reason`, eine der beiden `outcomes`
oder `needs` fehlt oder einer dieser Texte auf eine Zeile einer Tabelle des Betreibers verweist ("Zeile 21").
Anlass: Am 16.10.2026 zeigte das Blatt "Google Tag Manager" im Cockpit nur "eigener Code im Theme wie <Referenz-Store>",
und niemand verstand, dass der Tag Manager damit ohne App lädt.

`sync` übernimmt die Texte ins Repo des Stores, zählt sie aber nicht als geänderte Regel: Eine neue Fassung,
die nur Texte ändert, verlangt keinen Neubau (`apply_needed: false`), und `apply` lässt `applied_at` stehen.
