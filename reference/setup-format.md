# Setup eines Stores: Format von `setup.json`

Seit 0.3.13. Das Cockpit zeigt unter "Setup" je Store Theme, Tracking und Einwilligung, Sprachen und Märkte und die
Apps im Theme, nebeneinander und gegen den Referenz-Store der Marke. Das Cockpit rechnet nichts selbst: Die Datei
trägt fertige Zeilen, das Cockpit vergleicht nur die Werte gleicher Schlüssel.

Ablage: ein Lauf `reporting/runs/<datum>-setup/` mit `state.json` (`cadence: "setup"`) und `setup.json`. `publish`
lädt nur `setup.json` hoch und gibt den Lauf sofort frei, wie den Wochenpuls (benannte Ausnahme von Grundregel 5,
entschieden am 12.10.2026). Ein neuer Lauf am selben Tag ersetzt den alten.

Geschrieben und geprüft wird über das Modul `theme.setup`: `validate --path <setup.json>` prüft eine Datei gegen
dieses Format, `from-shop-tech --path <shop-tech.json> --shop <slug>` baut die Live-Ansicht aus dem Technik-Abzug
und legt den Lauf an. Ein ungültiges Setup landet nie in einem Lauf.

```json
{
  "schema": 1,
  "shop": "beispielshop",
  "reference_shop": "beispielshop",
  "collected_at": "2026-10-12T11:00:00+00:00",
  "source": "aus dem Repo der Migration",
  "automatic": false,
  "views": {
    "live": {
      "theme": {"name": "Broadcast", "version": "5.0.0", "id": "000000000000"},
      "groups": [
        {"key": "theme", "label": "Theme", "rows": [
          {"key": "theme", "label": "Theme", "value": "Broadcast 5.0.0", "note": "von der Agentur angepasst"},
          {"key": "base_changes", "label": "Änderungen am Basis-Theme", "value": "59 Anpassungen",
           "compare": false, "hint": "je weniger, desto leichter das nächste Update"}
        ]},
        {"key": "apps", "label": "Apps im Theme", "rows": [
          {"key": "app:klaviyo", "label": "Klaviyo", "hint": "Marketing", "value": "eingebunden", "present": true}
        ]}
      ]
    },
    "draft": {
      "theme": {"name": "Horizon", "version": "4.2.0", "id": "000000000002"},
      "groups": [
        {"key": "tracking", "label": "Tracking und Einwilligung", "rows": [
          {"key": "cookie_banner", "label": "Cookie-Banner", "value": "Pandectes",
           "policy": {"kind": "gap", "text": "bis zum Launch: CookieFirst"}}
        ]}
      ]
    }
  }
}
```

| Feld | Bedeutung |
|---|---|
| `schema` | 1 |
| `shop` | Slug des Stores wie im Cockpit |
| `reference_shop` | Referenz-Store der Marke (`reference_shop` der Config), `null` bei einer Marke mit einem Store |
| `collected_at` | Zeitpunkt der Erhebung, ISO 8601 |
| `source` | woraus erhoben, in Worten, etwa "aus dem Repo der Migration" oder "aus dem Audit vom 7. Okt." |
| `automatic` | `true`, wenn die wöchentliche Erhebung mit dem Wochenpuls sie geschrieben hat; das Cockpit zeigt dann "automatisch erhoben" |
| `views.live` | das Setup des Live-Themes, immer vorhanden |
| `views.draft` | das Setup des Entwurfs, nur während einer Migration mit Entwurf |
| `theme` | `name`, `version`, `id` des Themes dieser Ansicht; `version` und `id` sind `null`, wenn die Quelle sie nicht kennt (`shop-tech.json` nennt nur den Namen) |
| `groups[].key`, `label` | Gruppe, feste Schlüssel: `theme`, `tracking`, `languages`, `apps`, `features` |
| `rows[].key` | Merkmal, eindeutig in der Ansicht; Apps als `app:<handle>` |
| `rows[].label` | Bezeichnung für Menschen |
| `rows[].value` | der Wert, der verglichen wird, als Text |
| `rows[].note` | Satz unter dem Wert, wird nicht verglichen |
| `rows[].hint` | Satz unter der Bezeichnung, etwa die Kategorie einer App |
| `rows[].compare` | `false` bei Mengen und Zählungen, die nie gleich sein müssen; Standard `true` |
| `rows[].present` | nur bei Apps: eingebunden oder nicht; eine App, die in einem Store fehlt, gilt dort als nicht eingebunden |
| `rows[].policy` | nur im Entwurf: Einordnung nach den Vorgaben der Marke, `kind` `gap` (bis zum Launch angleichen), `decide` (noch zu entscheiden) oder `allowed` (darf abweichen), `text` der Satz dazu. Das Cockpit zeigt sie nur, wo der Wert vom Referenz-Store abweicht |

## Vorgaben ohne Regel: `policy_questions`

Seit 0.3.15, optional und nur im Setup des Referenz-Stores (`shop` gleich `reference_shop`). Eine Vorgabe der Marke,
die in `policies.json` noch keine Regel hat oder auf `open` steht, kommt hier als Frage hinein. Das Cockpit zeigt sie im
Setup auf der Karte "Vorgaben der Marke" mit den Knöpfen "Abweichung erlauben" und "An <Referenz-Store> angleichen";
entscheiden können alle Mitglieder der Marke. Die Antworten holt die Skill `theme-migration` beim Start über das
Werkzeug `get_setup` des Cockpits und trägt sie mit `theme.policies import` in `policies.json` ein
(`reference/theme-migration/policies-format.md`).

```json
"policy_questions": [
  {"key": "bundles", "subject": "Beispielbundle", "app": "app:beispielbundle",
   "text": "Beispielbundle: in allen Stores wie im Beispielshop?",
   "context": "Beispielbundle bietet Bundles an. Im Einsatz ist es heute nur im Beispielshop, in 3 Vorlagen.",
   "options": ["Abweichung erlauben", "An Beispielshop angleichen"],
   "recommendation": "Abweichung erlauben",
   "reason": "In den anderen Stores wäre es eine neue Funktion, keine Migration."}
]
```

| Feld | Bedeutung |
|---|---|
| `key` | Schlüssel der Regel in `policies.json`, eindeutig in der Liste |
| `subject` | Bezeichnung für Menschen, optional; wird beim Anlegen der Regel ihr `subject` |
| `app` | optional: Schlüssel der Zeile im Setup (`app:<handle>`), damit die Tabelle nach der Antwort die Einordnung zeigt. Bei "An <Referenz-Store> angleichen" behält die Regel diese App (`keep`); ein Store ohne sie bekommt einen Punkt zum Einbauen |
| `text` | die Frage in einem Satz |
| `context` | worum es geht und was schon feststeht, in der Sprache des Kunden. Pflicht |
| `options` | genau zwei Antworten, die Reihenfolge trägt die Bedeutung: `options[0]` heißt in `policies.json` `may_differ`, `options[1]` heißt `same_as_reference` |
| `recommendation` | eine der `options`, oder `null` für ausdrücklich keine Empfehlung. Das Feld steht immer |
| `reason` | der Grund der Empfehlung, ohne Empfehlung worauf es ankommt. Pflicht |

Jede Regel mit `rule: open` in `policies.json` braucht hier eine Frage, und jede Frage eine Zeile im Setup eines
Stores; `publish` prüft das vor jedem Upload (`reference/theme-migration/policies-format.md`, Abschnitt "Antworten
aus dem Cockpit"). Ein Setup, das hochgeht, prüft `publish` außerdem gegen dieses Format, auch wenn es von Hand
entstanden ist.

`get_setup` hängt an jede Frage `cockpit_answer` (`{value, by, at}`, die neueste Antwort im Cockpit, oder `null`) und
gibt Rückfragen dazu als `cockpit_questions` zurück. Beides steht nie in `setup.json`.
