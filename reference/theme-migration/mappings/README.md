# Mapping-Bibliotheken

Eine Mapping-Bibliothek ist die fertige Zuordnung eines verbreiteten Quell-Themes auf ein
Ziel-Theme: für jede Section des Quell-Themes ein Ausgang, für jede Einstellung eine
Transformation, dazu die globalen Einstellungen, die Standard-Templates und die Section-Gruppen.
`map-theme` liest sie als Ausgangspunkt, `build-theme` erzeugt daraus die Vorlagen. Was ein
einzelner Shop anders braucht, steht nicht hier, sondern in `migration/mapping/overrides.json`
im Workspace des Shops.

Eine Bibliothek enthält nur Namen von Sections, Blöcken und Einstellungen der öffentlichen
Themes. Kein Liquid, kein CSS, keine Texte aus den Themes und nichts aus einem Shop.

| Datei | Quelle | Ziel | geprüft gegen |
|---|---|---|---|
| `broadcast-5__horizon-4.json` | Broadcast 5.x | Horizon 4.x | Broadcast 5.0.0, Horizon 4.2.0 (Commit `5acd1b6`) |

Der Dateiname ist `<quelle>-<hauptversion>__<ziel>-<hauptversion>.json`.

## Format

Grundlage ist das Mapping-Format der Theme-Migration:

```json
{
  "source": {"theme": "Broadcast", "version": "5.x", "checked_version": "5.0.0"},
  "target": {"theme": "Horizon", "version": "4.x", "checked_version": "4.2.0"},
  "sections": {
    "section-hero": {
      "action": "configure",
      "target": "hero",
      "settings": {"image_1": {"to": "image_1", "transform": "identity"}},
      "blocks": {"button": {"target": "button", "settings": {}}},
      "set": {},
      "notes": ""
    },
    "section-map": {"action": "build", "notes": "Begründung"},
    "api-cart-items": {"action": "drop", "notes": "Begründung"}
  },
  "settings_data": {"text_color": {"to": "color_palette", "transform": "color_to_palette", "key": "foreground"}},
  "templates": {"product": {"action": "configure"}},
  "section_groups": {"group-header": {"action": "configure", "target": "header-group"}}
}
```

**Ausgänge.** `configure` heißt, das Ziel-Theme hat ein Bauteil dafür (`target`), und die
Einstellungen werden übertragen. `build` heißt, es gibt keine Entsprechung, ein eigenes Bauteil
mit Präfix entsteht; die Begründung in `notes` ist Pflicht. `drop` heißt, das Bauteil entfällt,
ebenfalls mit Begründung. Dieselben drei Ausgänge gibt es je Block, je Template und je
Section-Gruppe. Ein Block ohne `action` ist `configure`.

**Felder einer Einstellungszuordnung.**

| Feld | Bedeutung |
|---|---|
| `to` | Einstellung im Ziel; bei `drop` `null` |
| `transform` | eine der Transformationen unten |
| `values` | bei `map_values`: Quellwert auf Zielwert; Wahrheitswerte als `"true"` und `"false"` |
| `key` | bei `color_to_palette`: der Schlüssel in der Palette (Buchstabe, dann Buchstaben, Ziffern, Unterstriche) |
| `block` | der Wert gehört nicht an die Section oder den Block selbst, sondern an einen Kindblock dieses Typs; verschachtelt als Pfad `a/b`. Statische Blöcke des Ziels (etwa `_product-details`) werden so erreicht |
| `block_id` | trennt mehrere Kindblöcke desselben Typs, etwa Überschrift und Text als zwei `text`-Blöcke |
| `note` | was beim Übertrag verloren geht oder von Hand zu prüfen ist |

**Felder eines Blocks.** `target` (Ziel-Block, auch `@app`), `parent` (der Block steht in einem
Behälterblock dieses Typs, etwa `_accordion-row` in `accordion`), `static` (der Zielblock ist ein
statischer Block der Section und steht nicht in deren Blockliste), `settings`, `set`, `notes`.

**`set`** setzt feste Werte im Ziel, die keine Quell-Einstellung trägt, etwa
`recommendation_type: complementary` oder `media_type_1: video`.

## Transformationen

Die Liste ist fest. Was keine davon abbildet, wird `build` mit Begründung, nie stilles Raten.

| Transformation | Wirkung |
|---|---|
| `identity` | Wert unverändert übernehmen |
| `map_values` | Wert über die Tabelle `values` übersetzen; ein Wert ohne Eintrag wird gemeldet und fällt auf den Standard des Ziels |
| `px_to_number` | Pixelangabe als Text (`"24px"`) in eine Zahl |
| `bool_invert` | Wahrheitswert umkehren (aus "ausblenden" wird "anzeigen") |
| `font_handle` | Schrift-Handle der Shopify-Schriftbibliothek übernehmen (`poppins_n5`), Gültigkeit prüfen |
| `color_to_palette` | Farbe als Eintrag `key` in die `color_palette` des Ziels; Farben mit Alphakanal nimmt die Palette nicht |
| `drop` | Einstellung entfällt, `note` sagt warum |

## Wie eine Bibliothek entsteht

1. **Beide Themes unverändert besorgen.** Das Quell-Theme in der Version, für die die Bibliothek
   gilt, ohne Anpassungen eines Shops (ein unverändertes Theme im Store, ein ZIP vom Hersteller
   oder ein Entwicklungs-Store). Das Ziel-Theme aus dem Upstream, Version aus
   `config/settings_schema.json`, `theme_info.theme_version`.
2. **Schema-Auszüge ziehen.** Je Theme ein Auszug mit allen Sections, Theme-Blöcken, globalen
   Einstellungen, Templates und Section-Gruppen, nur Namen und Typen. Das Format steht im Kopf
   von `scripts/theme/mapping_check.py`. Die Auszüge bleiben lokal: sie sind aus fremdem Code
   abgeleitet und gehören nicht ins Repo.
3. **Je Section des Quell-Themes einen Ausgang wählen.** Zuerst die Frage, welches Bauteil des
   Ziel-Themes dieselbe Aufgabe erfüllt. Bei Horizon ist das oft kein eigenes Bauteil, sondern
   `section` mit Blöcken (`group`, `text`, `image`, `button`); die Arbeit verschiebt sich von
   "Layout bauen" zu "Layout zusammensetzen".
4. **Je Einstellung eine Transformation.** Gegen das Schema des Ziels: Gibt es die Einstellung,
   passt der Typ, passen die Optionen und der Wertebereich? Jede `drop`-Zuordnung bekommt eine
   `note`, damit `map-theme` dem Team sagen kann, was fehlt.
5. **Schema-Fakten über die Shopify-Skills prüfen**, nicht aus dem Gedächtnis: Einstellungstypen,
   statische Blöcke, die Palette. Für Horizon ab 4.0.0 gilt: keine Farbschemata, sondern eine
   `color_palette` (2 bis 20 Farben, Hex ohne Alphakanal), auf die andere Farbeinstellungen per
   `{{ settings.color_palette.<key> }}` verweisen. Eine Zuordnung auf `color_scheme` ist dort
   falsch, der Test prüft das.
6. **Erfahrung aus Projekten nur als Regel.** Was ein Projekt gelernt hat ("ein fehlender
   Schlüssel heißt Schema-Standard"), fließt ein; Kampagnen, Sections einer Marke, App-Sonderfälle,
   Handles und IDs nie.
7. **Prüfen** (nächster Abschnitt) und das Ergebnis unten eintragen.

## Wie sie geprüft wird

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.mapping_check \
  --mapping "${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/mappings/broadcast-5__horizon-4.json" \
  --source-schema <quell-auszug.json> --target-schema <ziel-auszug.json> --out <befunde.json>
```

**Fehler** (Exit-Code 1) sind Zuordnungen, die beim Erzeugen still verloren gingen oder eine
ungültige Datei ergäben: eine Quell-Section ohne Ausgang, eine Section, die es in der Quelle
nicht gibt, ein Ziel-Bauteil oder eine Ziel-Einstellung, die es nicht gibt, ein Block, den sein
Behälter nicht annimmt (private Blöcke mit `_` nimmt `@theme` nicht an), eine unbekannte
Transformation, `build` oder `drop` ohne Begründung, ein Zielwert außerhalb der Optionen.

**Hinweise** (kein Einfluss auf den Exit-Code) sind Stellen für einen Menschen: Typwechsel,
Wertebereiche, die das Ziel nicht abdeckt, Quellwerte ohne Zuordnung, Einstellungen und Blöcke
der Quelle ohne Zuordnung.

Ohne Auszüge prüft `scripts/tests/test_theme_mapping_check.py` bei jedem Testlauf, dass die
Bibliothek gültiges JSON im Format ist, nur erlaubte Transformationen nutzt, jeder Ausgang
vollständig ist, nichts auf ein Farbschema zielt und die Abdeckung unten stimmt.

## Abweichungen eines Shops

Die Bibliothek beschreibt das unveränderte Theme. Was im Shop anders ist, gehört in
`migration/mapping/overrides.json` im Workspace des Shops, im selben Format:

- eigene Sections des Shops oder einer Agentur, die es im Original nicht gibt (meist `build`);
- ein anderer Ausgang, weil das Team in G1 anders entschieden hat (etwa `drop` statt `build`);
- eine andere Zuordnung einer Einstellung, weil das Bildpaar es verlangt.

Zusammengeführt wird je Schlüssel: ein Eintrag in `overrides.json` ersetzt den Eintrag gleichen
Namens der Bibliothek auf der Ebene Section, Block oder Einstellung, alles andere bleibt. Die
Bibliothek selbst wird für einen Shop nie geändert; eine Korrektur, die für jedes Projekt gilt,
kommt in die Bibliothek und wird neu geprüft.

## Abdeckung: Broadcast 5 auf Horizon 4

64 Sections im unveränderten Broadcast 5.0.0, jede mit Ausgang:

| Ausgang | Sections |
|---|---|
| `configure` | 47 |
| `build` | 7 |
| `drop` | 10 |
| Summe | 64 |

- **`build`:** `featured-posts` (einzeln gewählte Artikel), `popups`, `section-map`,
  `section-recent-products`, `section-tab-collections`, `section-text-with-products`,
  `subcollections`.
- **`drop`:** die fünf `api-*`-Sections (Horizon lädt echte Sections nach), die drei
  `customer-*`-Sections (klassische Kundenkonten, abgekündigt), `gift-card` (Horizon rendert
  `templates/gift_card.liquid` ohne Section) und `reviews` (bindet die abgekündigte App
  Shopify Product Reviews ein).
- **`configure`**, davon 19 auf `section` mit Blöcken: die Baukasten-Sections von Broadcast
  (Rich Text, Spalten, Custom Content, Newsletter, Aufklapper, Kundenstimmen, Kacheln,
  Kollektionslisten, Kontaktformular und weitere).

Blöcke in den konfigurierten Sections: 98 `configure`, 20 `build`, 7 `drop`. Einstellungen in
Sections und Blöcken: 391 `identity`, 102 `map_values`, 2 `bool_invert`, 418 `drop` mit `note`.
Globale Einstellungen: 106, davon 16 `identity`, 10 `color_to_palette`, 4 `map_values`,
3 `font_handle`, 73 `drop`. Die zehn Farben der Palette heißen `foreground`, `background`,
`background_secondary`, `accent`, `link`, `border`, `header_background`, `header_foreground`,
`footer_background`, `footer_foreground`; `foreground` und `background` sind die Schlüssel, auf
die die Standardwerte von Horizon verweisen. Templates: 13 `configure`, die sieben
`customers/*` `drop`. Section-Gruppen: Header, Footer und Pre-Footer `configure` (der Pre-Footer
wandert in die Footer-Gruppe), die Overlay-Gruppe mit den Popups `drop`.

Die vielen `drop` bei Einstellungen sind kein Verlust an Inhalt, sondern vor allem Gestaltung,
die Horizon zentral regelt: Schriftgrößen je Section (Horizon: Presets h1 bis h6), Textfarben je
Section (Horizon: Kontrast aus der Hintergrundfarbe), Buttongröße und Pfeile. Diese Werte holt
`compare-themes --measure` aus dem gerenderten Shop, nicht aus den Einstellungen.

## Prüfergebnis

Stand 05.10.2026, lokal gegen Auszüge aus Broadcast 5.0.0 und Horizon 4.2.0 (Commit `5acd1b6`):
**0 Fehler, 73 Hinweise.** Keine Quell-Section, kein Quell-Block und keine Quell-Einstellung ohne
Zuordnung.

| Hinweis | Zahl | Bedeutung |
|---|---|---|
| `type_mismatch` | 57 | Klartext (`text`, `textarea`) in ein `richtext`-Feld, dazu zwei Fälle `richtext` und `textarea` nach `inline_richtext` in der Ansageleiste. Der Generator muss Klartext in einen Absatz fassen beziehungsweise die Absatz-Hülle entfernen, sonst ist der Wert ungültig |
| `range_exceeds` | 9 | Abstände bis 200 px gegen 100 px in Horizon (sechs), Tempo von Ansagen und Slideshow, Produkte je Seite |
| `unmapped_values` | 7 | Symbole ohne gleichbedeutende Entsprechung in Horizon (fünf Stellen), Auswahlliste als Eingabefeld am Produkt (zwei) |

## Offene Punkte

- **Klartext nach richtext.** Die feste Liste hat keine Transformation dafür. Die Bibliothek nutzt
  `identity` mit `note`; der Generator muss beim Schreiben in ein `richtext`-Feld Klartext in
  `<p>` fassen, oder die Liste bekommt eine Transformation dafür.
- **Erweiterungen des Formats** (`block`, `block_id`, `parent`, `static`, `set`, `note`,
  `section_groups`) muss der Generator kennen. Kennt er eine nicht, verwirft er die Einstellung
  und meldet sie, es geht also nichts still verloren.
- **Wertebereiche.** Werte über dem Maximum des Ziels (Abstände über 100 px) meldet der Generator;
  eine Begrenzung auf das Maximum ist eine Gestaltungsentscheidung, keine Transformation.
- **Unverändertes Broadcast.** Geprüft gegen ein als unverändert geführtes Broadcast 5.0.0 aus
  einem Store. Vor der ersten Erprobung an einem fremden Shop gegen ein frisches Broadcast aus
  einem Entwicklungs-Store wiederholen.
