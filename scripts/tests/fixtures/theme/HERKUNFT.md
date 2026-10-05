# Herkunft der Fixtures unter `fixtures/theme/`

Alles hier ist für die Tests von `scripts/theme/` von Hand erfunden. Kein
Code eines kommerziellen Themes, keine Datei aus einem echten Shop, keine Zahl
aus einem echten Lauf.

`beispiel-theme/` ist ein kleines Online-Store-2.0-Theme mit allem, woran die
Regeln greifen:

- Templates mit Standard und Suffix (`product.json`, `product.beispiel.json`),
  ein Template ohne Objekt (`page.alt.json`), eine Markt-Variante
  (`product.beispiel.context.eu.json`) und ein Kundenkonto-Template
  (`customers/account.json`), das keinem Objekt zugewiesen werden kann.
- Verschachtelte Blöcke in `templates/index.json` (Section `hero`, Block
  `row`, darin `text_1`), für den Schlüsselaufbau der Theme-Übersetzungen.
- `config/settings_data.json` ohne Kommentarkopf; den setzt erst der
  erfundene Shop in `tests/theme_fake_shop.py` beim Schreiben, wie Shopify es
  im Feld tut.
- `assets/beispiel.png` sind ein paar Bytes mit PNG-Signatur, kein Bild; sie
  sind kein gültiges UTF-8 und prüfen damit den Weg über `BASE64`.

Shop `beispiel.myshopify.com`, Domain `beispielshop.example`, Theme-IDs
`000000000000` (live) und `111111111111` (Entwurf).
