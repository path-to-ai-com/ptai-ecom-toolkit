# Mapping-Format der Theme-Migration

Das Mapping sagt dem Generator (`theme.generate`), wie aus den Templates, Section-Groups und
globalen Einstellungen des alten Themes die des neuen werden. Es ist die einzige Stelle, an der
diese Zuordnung steht: Jede Korrektur kommt ins Mapping oder in die Overrides, nie nur in eine
erzeugte Datei, sonst dreht der nächste Lauf sie zurück.

Ablage im Workspace des Shops:

| Datei | Inhalt |
|---|---|
| `migration/mapping/mapping.json` | die Zuordnung, meist aus der Bibliothek übernommen |
| `migration/mapping/overrides.json` | Abweichungen dieses Shops, gleiches Format plus `instances` |
| `reference/theme-migration/mappings/<quelle>__<ziel>.json` | Bibliothek im Toolkit, nur Namen öffentlicher Themes |

## Aufbau

```json
{
  "source": {"theme": "Quellthema", "version": "5.x"},
  "target": {"theme": "Horizon", "version": "4.x"},
  "sections": {
    "<section-typ-der-quelle>": {
      "action": "configure",
      "target": "<section-typ-des-ziels>",
      "settings": {
        "<schlüssel-der-quelle>": {"to": "<schlüssel-des-ziels>", "transform": "identity"},
        "<anderer-schlüssel>": {"to": "text", "transform": "text_to_richtext", "block": "text", "block_id": "title"}
      },
      "set": {"<schlüssel-des-ziels>": "<fester wert>"},
      "blocks": {
        "<blocktyp-der-quelle>": {
          "target": "<blocktyp-des-ziels>",
          "parent": "<behälterblock im ziel, optional>",
          "static": false,
          "settings": {},
          "set": {},
          "blocks": {}
        },
        "@app": {"target": "@app", "parent": "<behälterblock, optional>"}
      },
      "custom_css": ["<regel>"],
      "notes": ""
    }
  },
  "settings_data": {"<schlüssel-der-quelle>": {"to": "<schlüssel-des-ziels>", "transform": "identity"}},
  "templates": {"<template-name>": {"action": "configure"}},
  "section_groups": {"<gruppe-der-quelle>": {"action": "configure", "target": "<gruppe-des-ziels>"}}
}
```

Ein Feld, das hier nicht steht, beachtet der Generator nicht und meldet es im Report unter
`mapping_findings` ("unbekanntes Feld, nicht beachtet").

### `sections`

Ein Eintrag je Section-Typ der Quelle (Dateiname ohne `.liquid`). Die Schlüssel:

- `action`: `configure` (gibt es im Ziel, wird erzeugt), `build` (braucht eine eigene Datei mit
  Präfix, wird nicht erzeugt und steht im Report) oder `drop` (entfällt bewusst). Ohne Angabe gilt
  `configure`. `build` braucht eine Begründung in `notes` (oder `reason`).
- `target`: Section-Typ im Ziel. Ohne Angabe derselbe Name.
- `settings`: eine Zeile je Einstellung der Quelle, siehe unten.
- `set`: feste Werte für Einstellungen des Ziels, die keine Einstellung der Quelle trägt, etwa
  `{"recommendation_type": "complementary"}`. Auch sie werden gegen das Schema des Ziels geprüft.
- `blocks`: ein Eintrag je Blocktyp der Quelle, siehe unten.
- `custom_css`: eigenes CSS für die Section als Liste von Regeln, oder `"source"`, um das CSS der
  Quelle zu übernehmen. Ohne Angabe wird CSS der Quelle nicht übernommen und als `build` gemeldet,
  weil seine Selektoren zum alten Theme gehören. Höchstens 500 Zeichen je Section.
- `notes`: Erklärung für Menschen, der Generator liest sie nur als Begründung.

### Eine Zeile in `settings`

| Feld | Bedeutung |
|---|---|
| `to` | Schlüssel im Ziel; fehlt er, heißt er wie in der Quelle; bei `drop` darf er `null` sein |
| `transform` | eine Transformation aus der festen Liste; ohne Angabe `identity` |
| `values`, `key`, `replace`, `variant` | Parameter der Transformation |
| `block` | der Wert gehört nicht an die Section oder den Block selbst, sondern an einen Kindblock dieses Typs; verschachtelt als Pfad `a/b` |
| `block_id` | ID des Kindblocks, wenn mehrere Kindblöcke desselben Typs entstehen (Überschrift und Untertitel als zwei `text`-Blöcke) |
| `note` | was beim Übertrag verloren geht oder von Hand zu prüfen ist; nur Doku |

**Kindblöcke aus Einstellungen.** Mit `block` sucht der Generator unter dem Knoten einen Kindblock
dieses Typs (mit `block_id` genau diese ID) und legt ihn an, wenn es ihn nicht gibt. Rendert das
Liquid des Elternteils einen statischen Block dieses Typs (`{% content_for 'block', type:
'_product-details', id: 'details' %}`), wird er dort als statischer Block angelegt, mit der ID aus
dem Liquid, `"static": true` und ohne Eintrag in `block_order`. Sonst entsteht ein dynamischer Block
mit der ID aus `block_id` (oder aus dem Typ), der am Elternteil erlaubt sein muss. Ein Pfad
`a/b` wird Ebene für Ebene so aufgelöst. Kindblöcke aus Einstellungen stehen in `block_order` vor
den übertragenen Blöcken der Quelle. Hat die Einstellung keinen Wert oder kennt der Kindblock den
Ziel-Schlüssel nicht, entsteht kein leerer Block.

### Ein Eintrag in `blocks`

Dieselben Felder wie eine Section (`action`, `target`, `settings`, `set`, verschachtelte `blocks`,
`notes`), dazu:

- `parent`: der Block steht im Ziel in einem Behälterblock dieses Typs, etwa ein Preis in
  `_product-details` oder eine Zeile in einer Gruppe. Den Behälter sucht oder legt der Generator an
  wie bei `block` (statisch, wenn das Liquid ihn so rendert); alle Blöcke mit demselben `parent`
  landen im selben Behälter.
- `static: true`: der Zielblock ist ein statischer Block des Elternteils. Die ID kommt aus dem
  Liquid; gibt es dort mehrere statische Blöcke dieses Typs, nennt `static_id` die richtige.
  Statische Blöcke stehen mit `"static": true` im JSON und nie in `block_order`.

Ohne `static` wird ein Block dynamisch und muss im Ziel an seinem Platz erlaubt sein (`@theme` für
öffentliche Blöcke, ausdrücklich genannt für private mit `_`, oder als Block direkt im Schema).

App-Blöcke (`shopify://apps/...`) werden unverändert übernommen, wenn das Ziel an ihrem Platz `@app`
aufnimmt, sonst stehen sie als `build` im Report. Ein Eintrag `"@app"` mit `parent` setzt sie in
einen Behälter. App-Sections werden ebenfalls unverändert übernommen.

### `settings_data`

Zeilen für die globalen Einstellungen (`config/settings_data.json`, Teil `current`), gelesen gegen
`config/settings_schema.json` beider Themes. Fehlt der Schlüssel `settings_data` im Mapping, wird
die Datei nicht erzeugt. `presets` übernimmt der Generator aus dem Ziel-Repo. App-Embeds
(`current.blocks`) schreibt er nicht, sondern listet sie im Report unter `app_embeds`: Ein Embed ist
nur auf dem Theme aktiv, auf dem es eingeschaltet wurde, und wird dort neu aktiviert. `block` gibt
es hier nicht.

### `templates`

Je JSON-Template (Name ohne `templates/` und `.json`, etwa `product.beispiel` oder
`customers/account`) eine `action`. `"*"` gilt für alle, die nicht einzeln stehen. Ein Template
ohne Eintrag wird nicht erzeugt und als `build` gemeldet: Welche Templates leben, ergibt sich aus den
Zuweisungen der Objekte, nicht aus der Dateiliste, und diese Entscheidung steht im Mapping. Der Name
bleibt im Ziel derselbe, weil die Zuweisung (`templateSuffix`) am Objekt hängt.

Liquid-Templates (Vintage) kann der Generator nicht übertragen, ihr Inhalt steckt im Code. Sie
stehen als `build` im Report, außer `gift_card` und `robots.txt`, die jedes 2.0-Theme als Liquid hat.

### `section_groups`

Je Section-Group der Quelle (Name ohne `sections/` und `.json`) eine `action` und als `target` die
Gruppe des Ziels; `"*"` gilt für alle übrigen. Mehrere Gruppen der Quelle dürfen auf dieselbe Gruppe
des Ziels zeigen, etwa ein Pre-Footer auf die Footer-Gruppe. Dann werden ihre Sections
zusammengeführt: `"position": "start"` stellt eine Quelle an den Anfang, sonst folgen die Quellen in
der Reihenfolge des Mappings. Trägt eine Section dieselbe ID wie eine schon übernommene, bekommt sie
den Namen ihrer Quell-Gruppe vorangestellt (`renamed_section_ids`). `type` und `name` der Gruppe
kommen aus der Gruppe im Ziel-Repo. Der Report nennt jede Zusammenführung unter `merged_groups`.

### `overrides.json`

Gleiches Format wie das Mapping; es wird je Schlüssel über das Mapping gelegt, auf drei Ebenen:
Eine Section ersetzt die Felder des Section-Eintrags gleichen Namens, ein Block die des
Block-Eintrags, und eine Zeile in `settings` ersetzt die Zeile gleichen Namens ganz (auch `values`
einer alten Zeile entfallen). Alles andere bleibt aus der Bibliothek. `set` wird je Schlüssel
zusammengeführt, `settings_data`, `templates` und `section_groups` je Eintrag ersetzt. Dazu kommt
`instances` für einzelne Sections in einer Datei:

```json
{
  "sections": {"hero": {"settings": {"overlay": {"to": "toggle_overlay", "transform": "identity"}}}},
  "instances": {
    "templates/index.json": {
      "hero_1": {"set": {"section_height": "custom"}},
      "promo_2": {"action": "drop", "reason": "Aktion ist vorbei"}
    }
  }
}
```

## Transformationen

Die Liste ist fest und getestet. Parameter stehen in derselben Zeile. Kann eine Transformation einen
Wert nicht sicher abbilden, schreibt der Generator nichts und meldet einen `build`-Fall mit Pfad und
Wert. Es wird nie geraten.

| Transformation | Wirkung | Parameter | verweigert |
|---|---|---|---|
| `identity` | Wert unverändert | | |
| `map_values` | Wert über eine Tabelle | `values` | Wert ohne Zeile |
| `px_to_number` | `"24px"` zu `24` | | andere Einheiten, Wahrheitswerte |
| `bool_invert` | `true` zu `false` und umgekehrt | | Nicht-Wahrheitswerte |
| `font_handle` | Schrift-Handle prüfen, ersetzen | `replace`, `variant` | alles, was kein Handle ist |
| `color_to_palette` | Farbe in die `color_palette` | `key` | Transparenz, Nicht-Hex, außerhalb `settings_data` |
| `text_to_richtext` | Klartext maskiert in Absätze `<p>`, jede Zeile einer | | Nicht-Text |
| `drop` | bewusst nicht übernehmen | | |

Dynamische Quellen (`{{ product.metafields.x.y }}`) gehen nur durch `identity` und `drop`.

**richtext ohne eigene Zeile.** Ist das Ziel vom Typ `richtext` und der Wert Text ohne Wurzelelement
(`<p>`, `<ul>`, `<ol>` oder eine Überschrift), fasst der Generator ihn auch bei `identity` in
Absätze, maskiert, wenn die Quelle Klartext war, und vermerkt das unter `adjusted`. Umgekehrt
verliert ein einzelner Absatz in ein `inline_richtext`-Ziel seine Hülle; mehrere Absätze passen dort
nicht hinein und stehen unter `dropped`.

**`identity`**

```json
"title": {"to": "heading"}
```

**`map_values`**: Text wird direkt nachgeschlagen, andere Werte als JSON (`"true"`, `"12"`).

```json
"width": {"to": "section_width", "transform": "map_values",
          "values": {"wrapper--full": "full-width", "wrapper": "page-width"}}
"sticky": {"to": "sticky_header", "transform": "map_values", "values": {"true": "always", "false": "never"}}
```

**`px_to_number`**

```json
"padding_top": {"to": "padding-block-start", "transform": "px_to_number"}
```

**`bool_invert`**

```json
"hide_title": {"to": "show_title", "transform": "bool_invert"}
```

**`font_handle`**: `replace` ersetzt ganze Handles, etwa eine abgekündigte Schrift durch ihren
Ersatz (die Liste kommt aus der Prüfung des Shops, Theme Check meldet abgekündigte Schriften als
`DeprecatedFontsOnSettingsData`); `variant` setzt Stil und Gewicht neu.

```json
"type_header_font": {"to": "type_font_heading", "transform": "font_handle",
                     "replace": {"alte_schrift_n4": "neue_schrift_n4"}, "variant": "n7"}
```

**`color_to_palette`**: Horizon hat ab 4.0 keine Farbschemata mehr, sondern eine `color_palette`
mit 2 bis 20 Farben, Hex ohne Transparenz. Ein Mapping auf `color_scheme` ist dort falsch. Die Zeile
nennt die Palette als `to` und den Farbnamen als `key`. Der Generator beginnt mit dem Standard der
Palette aus dem Ziel und trägt die Farben ein.

```json
"color_primary": {"to": "colors", "transform": "color_to_palette", "key": "primary"},
"color_accent": {"to": "colors", "transform": "color_to_palette", "key": "accent"}
```

**`text_to_richtext`**

```json
"subheading": {"to": "text", "transform": "text_to_richtext", "block": "text", "block_id": "subheading"}
```

**`drop`**

```json
"show_legacy_badge": {"transform": "drop"}
```

## Was der Generator dabei immer tut

- **Ein fehlender Schlüssel heißt Schema-Standard.** Fehlt eine Einstellung im Template der Quelle,
  gilt ihr `default` aus dem Schema der Quelle, bei einer Checkbox ohne `default` `false`. Der Wert
  wird dann wie jeder andere transformiert. Im Report unter `defaults_applied`.
- **Nur, was das Ziel-Schema kennt.** Ein Schlüssel außerhalb des Schemas, ein Wert außerhalb der
  Optionen eines `select` oder ein falscher Typ wird nicht geschrieben und steht unter `dropped`.
  Shopify würde ihn sonst beim Speichern still verwerfen. Werte eines `range` außerhalb von
  `min`/`max` oder neben der Schrittweite werden angepasst und unter `adjusted` gemeldet.
- **Ein expliziter Wert der Quelle ohne Zeile im Mapping** steht unter `dropped` mit
  "nicht im Mapping". Wer ihn nicht braucht, schreibt `drop`.
- **Block-IDs**: Gültige IDs bleiben. Ungültige (etwa mit `--` oder `__`) bekommen eine ID aus dem
  lesbaren Teil plus einer Prüfsumme ihres Pfads, bei jedem Lauf dieselbe (`renamed_block_ids`).
  Section-IDs werden nie umbenannt, weil Übersetzungen an ihnen hängen; eine ungültige Section-ID
  ist ein `build`-Fall.
- **Limits** vor dem Schreiben: 25 Sections je Template oder Group, 50 dynamische Blöcke je Section
  (oder `max_blocks`), 1250 je Datei, 8 Ebenen, 512 KB je Datei, 1,5 MB für `settings_data.json`.
  Eine Datei darüber wird nicht geschrieben.
- **Testverzeichnis**: `--out` darf nicht im Ziel-Repo liegen. Der Report vergleicht jede Datei mit
  dem Stand im Ziel-Repo (`diff`), damit Änderungen aus dem Theme-Editor nicht still überschrieben
  werden.

## Ein Mapping prüfen

1. **Aufbau.** Der Generator prüft das Mapping vor jedem Lauf (Aktionen, bekannte
   Transformationen, `values` bei `map_values`, `color_to_palette` nur in `settings_data`). Ein
   Fehler beendet den Lauf mit Exit-Code 2, bevor etwas geschrieben wird.
2. **Gegen die Schemas.** Jede Zeile wird gegen beide Themes gehalten: Schlüssel der Quelle, die es
   im Schema der Quelle nicht gibt, Ziel-Schlüssel, die im Ziel fehlen, Blocktypen ohne Schema. Das
   steht im Report unter `mapping_findings` und findet Tippfehler und Zeilen für eine andere
   Version des Themes.
   Ohne Lauf geht dieselbe Prüfung über Schema-Auszüge, etwa für eine Bibliothek:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.schema export \
     --theme-dir <quell-theme> --out <quell-auszug.json>
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.schema export \
     --theme-dir <ziel-theme> --out <ziel-auszug.json>
   ```

   Die Auszüge liest `theme.mapping_check` (siehe `reference/theme-migration/mappings/README.md`).
   Sie bleiben lokal, weil sie aus fremdem Code abgeleitet sind.
3. **Ein Lauf ins Testverzeichnis:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.generate \
     --mapping migration/mapping/mapping.json --overrides migration/mapping/overrides.json \
     --source migration/snapshots/<date>-<theme-id> --target-schemas <target-repo> \
     --out migration/build/out --lock migration/build/sources.lock
   ```

   Die Zusammenfassung steht als eine JSON-Zeile auf stdout, alles Weitere in
   `migration/build/out/report.json`. Exit-Code 0 heißt ohne Befund, 1 mit Befunden.
4. **Den Report lesen**, in dieser Reihenfolge:
   - `build`: jeder Fall braucht eine Entscheidung (Zeile ergänzen, `drop`, oder eigene Datei mit
     Präfix bauen).
   - `dropped` mit `intended: false`: Zeile korrigieren oder bewusst `drop` setzen.
   - `limit_violations`: die Datei fehlt in der Ausgabe.
   - `mapping_findings` und `schema_errors`.
   - `adjusted`, `defaults_applied`, `renamed_block_ids`, `app_items`, `app_embeds`: kein Befund,
     aber durchsehen.
   - `diff`: Unterscheidet sich eine Datei vom Ziel-Repo an Stellen, die das Mapping nicht erklärt,
     stammt die Abweichung aus dem Editor. Erst ins Mapping oder die Overrides holen, dann ersetzen.
5. **Gerendert prüfen.** Ein Lauf ohne Befund beweist nur, dass die Dateien zum Schema passen. Ob
   eine Einstellung im Ziel dieselbe Wirkung hat (Breite, Reichweite am Handy, Sichtbarkeit), zeigt
   erst das Bildpaar Live gegen Entwurf aus `compare-themes`.

`sources.lock` hält jede Eingabe mit SHA-256 fest: Mapping, Overrides, jede gelesene Datei der
Sicherung und des Ziel-Repos. Ändert sich eine Prüfsumme, ist der Lauf mit dem alten Stand nicht
mehr nachvollziehbar und wird wiederholt.

## Eine Bibliothek anlegen

Eine Datei unter `reference/theme-migration/mappings/` enthält nur Section-, Block- und
Einstellungsnamen öffentlicher Themes, keinen Code und nichts aus einem Shop. Sie entsteht aus den
Schemas des unveränderten Quell-Themes und des Ziel-Themes in der genannten Version und gilt als
geprüft, wenn ein Lauf gegen eine unveränderte Sicherung des Quell-Themes keine
`mapping_findings` hat und jeder `build`-Fall eine Begründung trägt.
