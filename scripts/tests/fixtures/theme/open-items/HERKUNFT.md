# Herkunft der Fixtures unter `fixtures/theme/open-items/`

Von Hand erfunden für `test_theme_open_items.py`, nach dem Muster eines Pilots vom 08.10.2026, ohne
dessen Texte. Domain `beispielshop.example`, keine Zahl aus einem echten Lauf.

Alle drei bilden eine Sammelkennung nach: die Zeile LC-2.7 der Launch-Prüfliste ("Testrunde, offene
Punkte") verweist auf sechs Testpunkte, und jede Quelle trägt LC-2.7 an jedem dieser Punkte.

- `launch-checklist.md` ist ein Bericht mit Abschnitt "Vor dem Launch", eine Zeile je Prüfpunkt,
  darunter die Sammelzeile LC-2.7.
- `findings-umbrella.json` sind die sechs Testpunkte als `findings.json`, jeder mit eigener `id` und
  `source_ids: ["LC-2.7"]`, in verschiedenen Status.
- `test-round-report.md` ist ein Bericht, dessen Zeilen alle mit LC-2.7 beginnen; die Kennung des
  Testpunkts steht erst im Text.
