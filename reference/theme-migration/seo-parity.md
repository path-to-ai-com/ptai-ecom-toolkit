# SEO-Gleichstand

Stand 05.10.2026. Ein Theme-Wechsel ist der häufigste Anlass für einen Sichtbarkeitseinbruch, und der
Einbruch wird erst Wochen später sichtbar. Verglichen wird alt gegen neu je Seitentyp, vor dem Launch
und noch einmal am Launch-Tag.

## Grundlage

- `seo.json` aus der Bestandsaufnahme: die Ausgabe des Live-Themes je Beispielseite, aus `crawl-site`
  und dem gerenderten HTML.
- Die Schutzliste: alle URLs mit relevanten Klicks im maximalen Zeitraum der Search Console, dazu die
  Seiten mit externen Verweisen. Keine davon darf verschwinden oder ihren Canonical ändern.
- Der Export der bestehenden Redirects.

## Vergleich je Seitentyp

| Prüfpunkt | Erwartung im Entwurf |
|---|---|
| Statuscode | wie live, keine neue Weiterleitung, kein 404 auf einer Seite der Schutzliste |
| Canonical | selbstreferenzierend wie live |
| Meta-Robots | kein `noindex` oder `nofollow`, das live nicht stand |
| Title und Meta-Description | gleich oder bewusst geändert |
| H1 bis H6 | genau eine H1, dieselbe Überschrift wie live als H1 |
| hreflang | genau einmal, über `content_for_header` |
| strukturierte Daten | dieselben Typen; Product-JSON-LD genau einmal |
| interne Links | ohne Weiterleitung, Menüs und Footer mit denselben Zielen |
| Bild-Alt-Texte | vorhanden wie live |
| Wortzahl je URL | nicht deutlich kleiner als live |
| `robots.txt` | gleiche Ausgabe wie live |
| Sitemap | erreichbar, gleiche Unterkarten |

Was ein zulässiger Unterschied ist, entscheidet ein Mensch. Nicht jede Abweichung ist eine
Verschlechterung, aber jede wird benannt.

## Typische stille Verluste

Diese Liste zuerst prüfen. Jeder Punkt ist bei einem Wechsel auf ein Theme der Horizon-Familie belegt.

- **hreflang** stand im alten Theme fest im Layout und kommt im neuen nur über `content_for_header`,
  wenn Märkte und Sprachen konfiguriert sind. Das neue Theme darf keine zweite Ausgabe bauen.
- Das Rückfallbild für `og:image` und `og:type` auf Kategorieseiten.
- `aggregateRating` im Produkt-Markup: Horizons strukturierte Daten geben eine `ProductGroup` ohne
  Bewertung aus. Kommt die Bewertung aus einer App, entsteht leicht doppeltes Product-JSON-LD, das
  Rich Results unterdrücken kann.
- Die `WebSite`-Auszeichnung.
- Eine eigene `robots.txt.liquid` geht mit dem Theme verloren. Die Live-Ausgabe von `/robots.txt`
  vorher sichern und vergleichen.
- **Eine zweite H1:** das Logo als H1 auf der Startseite, oder eine H1 im HTML einer
  Kollektionsbeschreibung oder eines SEO-Metafelds, sobald das neue Theme den Kollektionstitel als H1
  setzt. Lösung im Theme (H1 im Text als H2 mit H1-Optik), die Daten bleiben. Dabei entscheiden, welche
  Überschrift live die H1 war.
- Ohne eigene SEO-Beschreibung kürzt Shopify die automatische Meta-Description nach 320 Zeichen hart,
  mitten im Wort. Im Theme auf das letzte Satzende kürzen; eine gepflegte Beschreibung bleibt
  unverändert.
- **"Aufgeräumte" Templates verlieren still Text:** entfernte Kollektionstexte, Inhalte in
  geschlossenen Akkordeons, gekürzte Beschreibungen. Die Wortzahl je URL alt gegen neu ist die
  Gegenprobe.
- Inhalte, die nur per JavaScript rendern, im gerenderten HTML prüfen.

## Redirects

- Redirects greifen nur auf URLs, die 404 liefern. Feste Pfade wie `/products` oder `/collections`
  lassen sich nicht umleiten.
- Für Markt-Unterordner gelten Redirects nicht automatisch; je Unterordner eigene.
- Limit 100.000, auf Plus 20 Millionen. Redirects nach einer Umstellung mindestens ein Jahr stehen
  lassen.
- Bleiben die URLs gleich, braucht es keinen neuen Redirect. Die bestehenden bleiben trotzdem
  unangetastet.

## Regeln für den Vergleich

- **Vorschau nur im Browser** mit `?preview_theme_id=<id>` und Theme-Nachweis auf der Seite
  (`Shopify.theme.id` im HTML). Ein Abruf per `curl` ohne Cookie liefert den Live-Shop. Auch der
  Vergleichslink auf den heutigen Shop trägt die ID des Live-Themes, weil Shopify sich eine Vorschau
  per Cookie merkt.
- Der Crawl des Entwurfs läuft gegen dieselbe Seitenliste wie der Crawl des Live-Themes.
- **Die Storefront verträgt keine parallelen Prüfungen von einem Rechner.** Höchstens zwei Browser
  gleichzeitig, mit einigen Sekunden zwischen zwei Seitenaufrufen; Warenkorb-Schnittstellen
  nacheinander. Code-, HTML- und Admin-API-Prüfungen dürfen parallel laufen.
- **Offen:** ob Testansichten über `preview_theme_id` indexierbar sind. Bis das geprüft ist, keinen
  Link auf eine Testansicht öffentlich setzen.

## Am Launch-Tag und danach

- Spot-Check direkt nach dem Veröffentlichen: `robots.txt`, Canonicals und Statuscodes der Top-Seiten,
  kein `noindex`, Redirects der Top-Seiten.
- Sitemap in der Search Console neu einreichen.
- Zweite Messung gegen dieselbe Liste nach dem Prüfplan in `post-launch.md`.

## Quellen

- https://shopify.dev/docs/storefronts/themes/seo/hreflang
- https://help.shopify.com/en/manual/markets/seo
- https://shopify.dev/docs/storefronts/themes/seo/robots-txt
- https://shopify.dev/docs/storefronts/themes/seo/metadata
- https://help.shopify.com/en/manual/online-store/menus-and-links/url-redirect
- https://developers.google.com/search/docs/crawling-indexing/site-move-no-url-changes
- https://searchengineland.com/guide/site-redesign-seo-checklist (Fachquelle)
- https://skalum.agency/en/seo-traffic-drop-after-redesign/ (Agenturquelle)
