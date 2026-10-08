# Herkunft der Fixtures unter `fixtures/theme/seo/`

Von Hand erfunden für `test_theme_seo_parity.py` und `test_theme_launch_findings.py`. Kein HTML
aus einem echten Shop, keine Zahl aus einem echten Lauf. Domain `beispielshop.example`, Sprachen
`de` (primär) und `en`.

- `live-*.html` bildet die Ausgabe eines älteren Themes nach: hreflang fest im Layout, `Product`
  mit einem Angebot je Variante und `aggregateRating`, `og:image` mit dem Logo als Rückfall,
  `og:type product.group` auf der Kategorie, `WebSite` mit `SearchAction` auf der Startseite.
- `draft-*.html` bildet die Ausgabe eines frischen Horizon-Entwurfs nach: Meta-Tags über mehrere
  Zeilen, `ProductGroup` mit Varianten ohne `description` und ohne Bewertung, kein hreflang, kein
  `og:image` ohne Seitenbild, `og:type website` auf der Kategorie, kein `WebSite`.
- `fixed-product.html` ist derselbe Produktentwurf mit dem Horizon-Grundpaket aus
  `reference/theme-migration/horizon-base/`: Beschreibung an jeder Variante, Bewertung, hreflang.
- `verify-findings.md` ist ein Prüfbericht mit Abschnitten "Blocker" und "Vor dem Launch",
  `checklist.md` eine Prüfliste der Form `- [ ] **P01**`.
