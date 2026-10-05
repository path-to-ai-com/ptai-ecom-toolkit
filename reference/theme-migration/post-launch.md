# Nachsorge

Stand 05.10.2026. Gilt für Phase 10. Nach dem Launch fällt ein Fehler in Rankings und Conversion
erst mit Verzögerung auf. Der Prüfplan legt fest, wann was gemessen wird, und die Rückrichtung hält
das Repo mit dem live laufenden Theme gleich.

## Prüfplan

Verglichen wird mit den Werten, die direkt vor dem Launch gezogen wurden (`launch-checklist.md`).

| Termin | Was | Womit |
|---|---|---|
| Tag 1 (Launch-Tag und der Tag danach) | Spot-Checks wie am Launch-Tag, Crawl des Live-Shops gegen den Crawl des Entwurfs, Umsatz, Conversion, Fehlerseiten und Kaufabbrüche eng beobachten, erste Testbestellung ausgewertet | `crawl-site`, `pull-ga4`, Shopify-Analysen |
| Woche 1 | täglich: Crawl-Fehler und 404 aus der Search Console, wichtige 404 umleiten, Soft-404 beheben; Rankings täglich | `pull-gsc`, Rank-Tracking |
| Woche 2 | Rankings weiter täglich; Conversion je Seitentyp und Gerät gegen die Vergleichswerte; Tracking am Datensatz gegen die Bestellungen | `pull-ga4`, `pull-gsc` |
| Woche 4 | wöchentlicher Review: Crawl-Statistik (ein Anstieg ist nach einem Launch normal), Seitenindexierung, Rich Results, Conversion je Seitentyp und Gerät; erster Report gegen die Werte vor dem Launch | `pull-gsc`, `pull-ga4`, `report` |
| Tag 28 | Core Web Vitals im Feld bewerten: CrUX und PageSpeed rollieren über 28 Tage, erst jetzt zeigt das Feld nur das neue Theme | `pull-cwv` |
| Woche 6 bis 12 | Erfolg der Migration bewerten: Sichtbarkeit Desktop und Mobil, Sitzungen und Conversion je Seitentyp und Gerät, eingereichte gegen indexierte URLs. Kleine Shops eher Woche 6, große eher Woche 12. Ein vorübergehender Rückgang durch Gewöhnung wiederkehrender Besucher ist möglich | `report`, `pull-gsc`, `pull-ga4` |

Danach: KPIs nach drei und sechs Monaten gegen die ursprünglichen Ziele. Redirects mindestens ein
Jahr stehen lassen.

Bei einer Bewegung zuerst prüfen, ob ein Google-Update, Saison oder eine Kampagne sie erklärt, bevor
sie der Migration zugeschrieben wird. Als grobe Erfahrung aus Agenturquellen, keine Norm: Fehler an
Redirects, `noindex` und `robots.txt` erholen sich in ein bis zwei Wochen, Inhalte und interne Links
in zwei bis sechs, Core Web Vitals ab vier.

## Aufräumen

- Geplante Änderungen an Shop-Daten, die während des Stopps vorbereitet wurden, jetzt in datierten
  Blöcken umsetzen, mit Sicherung vor jedem Block (`change-freeze.md`).
- Code alter Apps im alten Theme ist mit dem Wechsel aus dem Live-Shop verschwunden. Apps, die im
  neuen Theme nicht mehr gebraucht werden, mit Freigabe des Teams deinstallieren; nicht mehr
  gebrauchte Pixel trennen.
- Das alte Theme erst nach der Stabilisierung löschen, mit Freigabe des Teams. Löschen ist endgültig.
- Befunde der Schwere `after_launch` nach ihrem Termin abarbeiten.

## Rückrichtung: Editor-Änderungen zurück ins Repo

Nach dem Launch arbeitet das Team im Theme-Editor des neuen, live laufenden Themes. Diese Änderungen
stehen im Shop, nicht im Ziel-Repo. Ein erneuter Generatorlauf oder ein Upstream-Merge würde sie
überschreiben.

**Vor jedem Generatorlauf und vor jedem Upstream-Merge:**

1. Das live laufende Ziel-Theme sichern:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.snapshot --theme live --out migration/snapshots
   ```

2. Die neue Sicherung gegen das Ziel-Repo diffen, JSON normalisiert. Unterschiede in
   `templates/*.json`, `sections/*-group.json` und `config/settings_data.json` sind Arbeit des Teams.
3. Jede Änderung übernehmen: als Commit im Ziel-Repo und, wo der Generator die Datei erzeugt, als
   Änderung an Mapping oder Overrides, damit der nächste Lauf sie nicht zurückdreht.
4. Änderungen am Code des Themes über den Admin (Code-Editor, Apps) gesondert ansehen: sie gehören
   entweder als verzeichneter Eingriff in `migration/customizations.md` oder wieder heraus.
5. Erst danach generieren oder mergen. Erzeugt wird in ein Testverzeichnis und gegen den Repo-Stand
   gedifft, bevor etwas ersetzt wird.

Ist das Ziel-Theme mit GitHub verbunden, committet Shopify jede Admin-Änderung auf den verbundenen
Branch. Dann ist `git pull` dieses Branches der erste Schritt, und die Sicherung wird zur Gegenprobe.

## Updates des Ziel-Themes

- Aktualisiert wird im Ziel-Repo per `git merge upstream/<ref>`, nie über den Update-Hinweis im Admin;
  der übernimmt kollidierende Code-Änderungen nicht.
- Vorher die Rückrichtung oben, dann die Prüfung der Eingriffe mit `--against upstream/<ref>`
  (`customizations.md`), dann Neubau, Upload in ein unveröffentlichtes Theme, Prüfung, Veröffentlichen
  durch einen Menschen.

## Quellen

- https://moz.com/blog/website-migration-guide (Fachquelle)
- https://searchengineland.com/guide/site-redesign-seo-checklist (Fachquelle)
- https://developers.google.com/speed/docs/insights/v5/about
- https://support.google.com/webmasters/answer/9205520
- https://shopify.dev/docs/storefronts/themes/tools/github
- https://skalum.agency/en/seo-traffic-drop-after-redesign/ (Agenturquelle)
