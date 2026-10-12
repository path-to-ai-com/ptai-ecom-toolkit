# Vorgaben einer Marke: Format von `policies.json`

Seit 0.3.11. Eine Marke mit mehreren Stores entscheidet einmal, was in allen Stores gleich sein soll, und
der Betreiber wendet diese Entscheidungen auf den Lauf jedes Stores an (`theme.policies apply`, Skill
`theme-launch`). Die Datei liegt beim Betreiber im Workspace der Marke, nie im Plugin und nie in einem
öffentlichen Repo.

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
    {"key": "languages", "subject": "Sprachen", "rule": "may_differ", "note": "je Marke"}
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `version` | eindeutig je Fassung; eine neue Fassung bekommt eine neue Version |
| `reference_shop` | der Store, dessen Stand gilt, wo `same_as_reference` steht |
| `decided_by`, `decided_at` | wer die Vorgaben entschieden hat und wann; steht an jeder Entscheidung im Lauf |
| `rules[].key` | Merkmal, eindeutig, englisch |
| `rules[].subject` | Bezeichnung für Menschen |
| `rules[].rule` | `same_as_reference`, `open` oder `may_differ` |
| `rules[].target` | Zielwert in Worten, erscheint im Cockpit als "bis zum Launch: …" |
| `rules[].keep`, `rules[].drop` | Dienst-IDs wie in `apps.json` (`app:<handle>`), nur bei `same_as_reference`. Ein Eintrag darf eine Liste von Schreibweisen desselben Dienstes sein, etwa `["cookiefirst", "app:cookiefirst-cookie-consent"]`, weil die Inventare der Stores ihn verschieden benennen. Beim Behalten genügt eine vorhandene Schreibweise; fehlt jede, entsteht ein Punkt zum Einbauen |
| `rules[].note` | Begründung oder offene Frage |

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

Eine Vorgabe öffnet nie eine Frage an das Team. Dieselbe Version zweimal anzuwenden ändert nichts.
