# Herkunft der Fixtures für den Generator

Alles in diesem Ordner ist von Hand für die Tests erfunden. Kein Code, kein
Schema und keine Einstellung stammt aus einem kommerziellen Theme oder aus
einem Shop.

- `source/` ist ein erfundenes Quell-Theme ("Quellthema"): Sections mit
  Blöcken direkt im Schema, wie ältere 2.0-Themes sie haben, ein
  `color_scheme`-Feld, eine Section-Group, ein Liquid-Template (`gift_card`)
  und eine `settings_data.json` mit Kommentarkopf und einem App-Embed.
- `target/` ist ein erfundenes Ziel-Theme ("Zielthema") im Aufbau eines
  aktuellen 2.0-Themes: Theme-Blöcke in `blocks/`, private Blöcke mit `_`,
  statische Blöcke über `content_for 'block'`, `@theme` und `@app` in den
  Sections und statt Farbschemata eine `color_palette`.
- `mapping.json` ordnet beide nach dem Format aus
  `reference/theme-migration/mapping-format.md` einander zu und enthält mit
  Absicht Fälle, die der Report melden muss (eine nicht zugeordnete Section,
  eine `build`-Section, ein Ziel-Schlüssel ohne Schema, eine ungültige
  Block-ID).

Namen, Texte und Farben sind Platzhalter. Shop `beispiel`, App-Kennungen
`beispiel-*` mit Null-UUID.
