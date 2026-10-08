# SEO-Gleichstand

Stand 08.10.2026. Ein Theme-Wechsel ist der häufigste Anlass für einen Sichtbarkeitseinbruch, und der
Einbruch wird erst Wochen später sichtbar. Verglichen wird alt gegen neu je Seitentyp und je
veröffentlichter Sprache, vor dem Launch und noch einmal am Launch-Tag.

Am 07.10.2026 ging eine Migration live, obwohl ein Prüfbericht fünf der Lücken unten unter "Vor dem
Launch" führte und die Prüfliste aus Phase 2 nie abgehakt war; eine sechste fand die Search Console am
Tag danach. Seitdem schließt das Horizon-Grundpaket diese Lücken beim Bau, und `launch-check` prüft
sie automatisch und blockiert den Launch.

## Grundlage

- `seo.json` aus der Bestandsaufnahme: die Ausgabe des Live-Themes je Beispielseite, aus `crawl-site`
  und dem gerenderten HTML.
- Die Prüfliste "Muss nach dem Umbau wieder da sein" aus Phase 2, eine Zeile `- [ ] **Pnn**` je
  Punkt, ihr Pfad in `theme_migration.acceptance_checklist`. Sie ist die Abnahme der SEO-Ausgabe.
- Die Schutzliste: alle URLs mit relevanten Klicks im maximalen Zeitraum der Search Console, dazu die
  Seiten mit externen Verweisen. Keine davon darf verschwinden oder ihren Canonical ändern.
- Der Export der bestehenden Redirects.

## Vergleich je Seitentyp

| Prüfpunkt | Erwartung im Entwurf |
|---|---|
| Statuscode | wie live, keine neue Weiterleitung, kein 404 auf einer Seite der Schutzliste |
| Canonical | selbstreferenzierend wie live |
| Meta-Robots | kein `noindex` oder `nofollow`, das live nicht stand |
| Title und Meta-Description | vorhanden wie live, gleich oder bewusst geändert |
| H1 bis H6 | genau eine H1, dieselbe Überschrift wie live als H1 |
| hreflang | dieselben Sprachen und `x-default` wie live, je Sprache genau einmal, der Eintrag der eigenen Sprache gleich der Canonical, keine unveröffentlichte Sprache |
| strukturierte Daten | dieselben Typen und Felder wie live; Product-JSON-LD genau einmal; `description` an jeder Variante einer `ProductGroup` |
| Open Graph | jede `og:`-Angabe wie live, `og:type` je Seitentyp gleich, `og:image` auch ohne Seitenbild |
| interne Links | ohne Weiterleitung, Menüs und Footer mit denselben Zielen |
| Bild-Alt-Texte | vorhanden wie live |
| Wortzahl je URL | nicht deutlich kleiner als live |
| `robots.txt` | gleiche Ausgabe wie live |
| Sitemap | erreichbar, gleiche Unterkarten |

Was ein zulässiger Unterschied ist, entscheidet ein Mensch. Nicht jede Abweichung ist eine
Verschlechterung, aber jede wird benannt; eine gewollte steht abgehakt oder verschoben mit Person und
Datum in der Prüfliste.

## Bekannte Lücken von Horizon

Diese Liste zuerst prüfen. Jeder Punkt ist bei einem Wechsel auf ein Theme der Horizon-Familie belegt.
Die Punkte 1 bis 6 schließt das Horizon-Grundpaket beim Bau (Abschnitt unten), nicht die Abnahme;
`launch-check` prüft sie automatisch und wertet jede Lücke als No-Go.

| # | Lücke | Geschlossen durch | Geprüft in |
|---|---|---|---|
| 1 | **hreflang** fehlt auf jeder Seite, wenn das alte Theme es fest im Layout hatte und der Schalter "Automatic hreflang tags" im Admin aus ist | `<prefix>-hreflang` oder der Schalter, nie beides | `seo-hreflang` |
| 2 | **`og:image`** fehlt auf Seiten ohne eigenes Bild, live diente das Logo als Rückfall | `<prefix>-og-image-fallback` | `seo-open-graph` |
| 3 | **`og:type product.group`** auf Kategorien; Horizon setzt dort `website` | Eingriff in `snippets/meta-tags.liquid` | `seo-open-graph` |
| 4 | **`aggregateRating`** im Produkt-Markup; Horizons `structured_data` kennt keine Bewertung | `<prefix>-product-structured-data` | `seo-structured-data` |
| 5 | **`WebSite` mit `SearchAction`** auf der Startseite | `<prefix>-website-structured-data` | `seo-structured-data` |
| 6 | **`description` an jeder Variante.** Horizons `structured_data` gibt eine `ProductGroup` aus und setzt die Beschreibung nur an die Gruppe; die Search Console meldet danach jede Variante in den Händlereinträgen als "Missing field description". Am Tag nach einem Launch gefunden, vorher von keinem Vergleich | `<prefix>-product-structured-data` | `seo-structured-data`, absolut, auch ohne Live-Stand |
| 7 | eine eigene `robots.txt.liquid` geht mit dem Theme verloren; die Live-Ausgabe von `/robots.txt` vorher sichern | Datei übernehmen | `robots` |
| 8 | **eine zweite H1:** das Logo als H1 auf der Startseite, oder eine H1 im HTML einer Kollektionsbeschreibung oder eines SEO-Metafelds, sobald Horizon den Kollektionstitel als H1 setzt | im Theme die H1 im Text als H2 mit H1-Optik; die Daten bleiben. Dabei entscheiden, welche Überschrift live die H1 war | `verify-theme` |

Weitere stille Verluste:

- Kommt die Bewertung aus einer App, entsteht leicht doppeltes Product-JSON-LD, das Rich Results
  unterdrücken kann. `seo-structured-data` meldet es, wenn live nur eines stand.
- Ohne eigene SEO-Beschreibung kürzt Shopify die automatische Meta-Description nach 320 Zeichen hart,
  mitten im Wort. Im Theme auf das letzte Satzende kürzen; eine gepflegte Beschreibung bleibt
  unverändert.
- **"Aufgeräumte" Templates verlieren still Text:** entfernte Kollektionstexte, Inhalte in
  geschlossenen Akkordeons, gekürzte Beschreibungen. Die Wortzahl je URL alt gegen neu ist die
  Gegenprobe.
- Inhalte, die nur per JavaScript rendern, im gerenderten HTML prüfen.

## Automatisch im Launch-Check

`launch-check` vergleicht je Seite des Mitschnitts das HTML des Live-Themes mit dem des Entwurfs
(`scripts/theme/seo_parity.py`), mit `--after` das veröffentlichte Theme mit dem Mitschnitt von vorher.
Es ruft dafür nichts selbst ab: das HTML kommt aus `capture_network.py`, also aus dem Browser, der als
einziger die Vorschau verlässlich zeigt, und die Storefront sieht keinen zweiten Abrufer.

**Regel: was live da ist und im Entwurf fehlt, ist `missing`.** Dazu eine Regel unabhängig vom
Live-Stand: eine `ProductGroup` mit Varianten ohne `description` ist immer `missing`.

| Zeile | Was verglichen wird |
|---|---|
| `seo-structured-data` | Typen der obersten JSON-LD-Einträge (`Product` und `ProductGroup` zählen gleich); am Produkt `name`, `description`, `image`, Kennung (`sku`, `gtin*`, `mpn`), `brand`, vollständige `offers` (`price`, `priceCurrency`, `availability`, bei einer Gruppe an jeder Variante) und `aggregateRating`; `Organization` mit `name`, `url`, `logo`, `sameAs`; `WebSite` mit `potentialAction`; `BreadcrumbList`; Produkt-JSON-LD mehr als einmal; unlesbare Blöcke |
| `seo-hreflang` | Werte je Seite gegen live (auch `x-default`), doppelte Werte, der Eintrag der eigenen Sprache (aus `html lang`) gleich der Canonical, keine Sprache, die im Shop nicht veröffentlicht ist. Ein Fehler, den live schon hatte, steht als Hinweis |
| `seo-open-graph` | `og:type` gleich wie live, jede `og:`-Angabe, die live hat, auch im Entwurf |
| `seo-head` | `title`, Meta-Description und Canonical vorhanden, wenn live vorhanden |

- **Vollständigkeit.** Fehlt im Mitschnitt die Startseite, eine Kategorie, ein Produkt oder eine
  veröffentlichte Sprache, ist der Vergleich unvollständig und steht auf `blocked`, nie auf `ok`.
  `theme.seo_parity pages` ergänzt die Seitenliste um je eine Fassung jeder weiteren Sprache unter
  `/<sprache><pfad>`:

  ```bash
  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.seo_parity pages --pages <pages.json> --locales de,en
  ```

- **Prüfliste aus Phase 2** (`acceptance-checklist`). Jeder Punkt `- [ ] **Pnn**` ist abgehakt,
  verschoben mit Person und Datum (`verschoben von <Name> am <JJJJ-MM-TT>`) oder abgedeckt: er nennt
  eine der Prüfungen (hreflang, `og:`, einen Schema-Typ wie `Product` oder `WebSite`, JSON-LD,
  Canonical oder noindex, Meta-Description, `robots.txt`) und jede genannte ist bestanden. Alles
  andere ist offen und damit No-Go. Die Zuordnung ist bewusst eng; ein Punkt ohne eines dieser
  Merkmale (genau ein `title`, `html lang`, Twitter-Karte) braucht einen Haken von Hand.
- **Prüfberichte** (`acceptance-findings`). Offene Punkte aus jedem Bericht unter `migration/verify/`
  und unter `theme_migration.report_paths` sind No-Go; ohne auffindbaren Bericht steht der Punkt auf
  `blocked`, nie als Frage. Was als erledigt oder verschoben zählt, steht in
  `scripts/theme/launch_findings.py`.

Was weiter ein Mensch prüft: Wortzahl, H1, interne Links, Alt-Texte, Redirects und die Schutzliste
(`crawl-site` gegen den Entwurf, `verify-theme`).

## Horizon-Grundpaket

Jede Migration auf Horizon bekommt beim Bau (`build-theme`, Schritt 4) vier Snippets aus
`reference/theme-migration/horizon-base/snippets/`, mit dem Präfix des Projekts statt `beispiel`:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.horizon_base install --target-repo <target-repo> --prefix <file_prefix>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.horizon_base check --target-repo <target-repo> --prefix <file_prefix> [--without-hreflang]
```

`install` überschreibt eine abweichende Datei im Ziel-Repo nur mit `--force`. `check` meldet fehlende
Snippets, fehlende Eingriffe und ein verbliebenes `structured_data` an der Produktseite.

| Snippet | Gibt aus |
|---|---|
| `<prefix>-product-structured-data` | Produkt-JSON-LD in der Form von Shopifys `structured_data` (`ProductGroup` mit `hasVariant`, bei nur der Standardvariante `Product`), dazu `description` an jeder Variante, `aggregateRating` aus den Standard-Metafeldern `reviews.rating` und `reviews.rating_count` (nur mit Bewertung und Anzahl über 0), `variesBy` mit Farbe und Größe |
| `<prefix>-hreflang` | je veröffentlichter Sprache ein `link rel="alternate"` aus `localization.available_languages`, gebaut aus `canonical_url`, dazu `x-default` auf die Primärsprache; keine Ausgabe auf 404, Passwort, Warenkorb, Kundenkonto und wenn die Canonical außerhalb der Startseite auf die Startseite zeigt |
| `<prefix>-og-image-fallback` | `og:image` mit `secure_url`, Breite und Höhe aus `shop.brand.logo`, sonst `settings.logo`, nur ohne `page_image` |
| `<prefix>-website-structured-data` | `WebSite` mit `name`, `url` und `SearchAction` über `routes.search_url`, nur auf der Startseite |

Dazu drei Eingriffe in Horizon-Dateien, je mit Kommentar `<prefix>:` und Zeile in
`migration/customizations.md`:

1. `sections/product-information.liquid`: den ganzen Block
   `<script type="application/ld+json">{{ closest.product | structured_data }}</script>` ersetzen durch
   `{% render '<prefix>-product-structured-data', product: closest.product %}`. Das Snippet schreibt
   seinen eigenen Skript-Block; bleibt der alte stehen, gibt es zwei Produkt-JSON-LD.
2. `snippets/meta-tags.liquid`: im `liquid`-Block zwischen den Zweigen `article` und `password`
   `elsif request.page_type == 'collection'` mit `assign og_type = 'product.group'`; am Ende von
   `if page_image` ein `else` mit `render '<prefix>-og-image-fallback'`.
3. `layout/theme.liquid`: direkt nach `render 'meta-tags'` die Aufrufe
   `render '<prefix>-hreflang'` (nur nach der Entscheidung unten) und
   `render '<prefix>-website-structured-data'`.

**hreflang: Schalter oder Snippet, nie beides.** Shopify gibt hreflang über `content_for_header`
automatisch aus, sobald einer Sprache ein Unterordner, eine Subdomain oder eine Domain zugeordnet ist,
samt `x-default`. Abschalten lässt sich das nur im Admin (Online Store, Preferences, "Automatic
hreflang tags"). Liquid kann den Schalter nicht lesen, und `content_for_header` zu durchsuchen meldet
Theme Check als `ContentForHeaderModification`. Deshalb beim Bau:

1. Im HTML des Entwurfs nach `hreflang` suchen.
2. Gibt Shopify die Tags aus: kein Snippet, `check --without-hreflang`.
3. Sonst das Snippet einbinden und den Schalter aus lassen. Wird der Schalter später eingeschaltet,
   vorher den Render-Aufruf entfernen; `seo-hreflang` meldet sonst doppelte Werte.

Grenzen: Sprachen auf eigener Domain deckt `<prefix>-hreflang` nicht ab; bei übersetzten Handles zeigt
ein Verweis auf das Handle der aktuellen Sprache, und Shopify leitet weiter. Das Suchfeld in den
Sitelinks zeigt Google seit dem 21.11.2024 nicht mehr; `WebSite` bleibt gültig, hält die Parität und
dient Google für den Websitenamen. Gerendert in einem echten Shop ist das Paket als Ganzes noch
nicht; die Produktauszeichnung ist aus einer im Feld geprüften Fassung abgeleitet. Nach dem ersten
Upload die Ausgabe im Rich Results Test und mit `launch-check` prüfen.

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
  gleichzeitig; Abrufe ohne Browser von einem einzigen Abrufer mit drei bis fünf Sekunden zwischen
  zwei Seitenaufrufen (`launch-check --after` wartet vier); Warenkorb-Schnittstellen nacheinander.
  Code-, HTML- und Admin-API-Prüfungen dürfen parallel laufen.
- **Offen:** ob Testansichten über `preview_theme_id` indexierbar sind. Bis das geprüft ist, keinen
  Link auf eine Testansicht öffentlich setzen.

## Am Launch-Tag und danach

- Spot-Check direkt nach dem Veröffentlichen: `robots.txt`, Canonicals und Statuscodes der Top-Seiten,
  kein `noindex`, Redirects der Top-Seiten.
- Strukturierte Daten, hreflang und Open Graph des veröffentlichten Themes gegen den Mitschnitt von
  vorher (`launch-check --after`, Zeilen `seo-*-after`).
- Sitemap in der Search Console neu einreichen; nach einigen Tagen die Händlereinträge und
  Produkt-Snippets in der Search Console auf neue Warnungen prüfen.
- Zweite Messung gegen dieselbe Liste nach dem Prüfplan in `post-launch.md`.

## Quellen

- https://shopify.dev/docs/storefronts/themes/seo/hreflang
- https://help.shopify.com/en/manual/markets/seo
- https://shopify.dev/docs/storefronts/themes/seo/robots-txt
- https://shopify.dev/docs/storefronts/themes/seo/metadata
- https://help.shopify.com/en/manual/online-store/menus-and-links/url-redirect
- https://developers.google.com/search/docs/crawling-indexing/site-move-no-url-changes
- https://developers.google.com/search/blog/2024/10/sitelinks-search-box
- https://searchengineland.com/guide/site-redesign-seo-checklist (Fachquelle)
- https://skalum.agency/en/seo-traffic-drop-after-redesign/ (Agenturquelle)
