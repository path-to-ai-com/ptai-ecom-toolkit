---
name: crawl-site
description: Vollständigen Site-Crawl über sitemap.xml und interne Links ziehen (Statuscodes, Weiterleitungsketten, Titles, Descriptions, H1, Canonicals, hreflang, robots.txt, interne Verlinkung und Klicktiefe, Wortzahl, strukturierte Daten, Bilder, eingebundene Fremdskripte) und als Snapshot ablegen. Nutzen, wenn der Audit oder ein monatlicher Report frische Crawl-Daten braucht, oder wenn der Nutzer explizit einen Site-Crawl für eine Domain will. Liest reporting/config.json im Kunden-Workspace.
---

# crawl-site: vollständigen Site-Crawl ziehen

Crawlt eine Domain über den aufgelösten Sitemap-Baum und die Breitensuche über interne
Links: Statuscode, vollständige Weiterleitungskette und Ladezeit je URL, dazu die
SEO-Kopfdaten aus `parse_page` (Title, Description, Canonical, hreflang, H1, Bilder,
strukturierte Daten, interne Links, eingebundene Skript-Quellen) und die Klicktiefe
ab der Startseite. Wird vom
Audit- und Report-Lauf aufgerufen, funktioniert aber auch solo.

**Kadenz: monatlich (Spec Abschnitt 3).** Ein Crawl ist teuer (bis zu `--max-urls`
Seitenabrufe mit Verzögerung dazwischen) und ändert sich zwischen zwei Reports selten
genug, dass ein monatlicher Rhythmus reicht. In `reporting/config.json` unter
`cadences.crawl` überschreibbar, ein Lauf mit "alles ziehen"-Schalter zieht ihn auch
außer der Reihe.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `domain` (z. B. `https://www.example.com`) und
  `sources.crawl` nicht `false`

Steht `sources.crawl` auf `false`, oder ist `domain` nicht gesetzt: Crawl als
"nicht verfügbar (Grund)" melden und aufhören. Ein Fehlschlag hier legt nie den
Gesamtlauf (Audit oder Report), das gilt für die Quelle als Ganzes genauso wie für
jede einzelne URL innerhalb des Crawls.

## Ablauf

1. `reporting/config.json` lesen: `domain`, `sources.crawl`, und den Umfang über
   `audit.config.crawl_budget(config)`. Der liefert immer ein Paar aus
   `crawl_max_urls` und `crawl_delay_sec`, mit Vorgaben, wenn die Felder fehlen.

   **Den Umfang nie aus dem Prompt nehmen.** Er hängt am Shop und nicht am
   Lauf: wie viele URLs die Sitemap führt, wie viele davon Sprachdubletten
   sind, wie schnell der Shop antwortet. Das ist jedes Mal dieselbe Antwort,
   und wer sie im Prompt mitgibt, gibt sie beim nächsten Lauf entweder wieder
   mit oder fällt still auf die Vorgabe zurück.
2. Ist die Quelle fällig (Kadenz `month`, siehe `audit/run.py`) oder erzwungen, das
   Script aufrufen, Zielordner ist der Daten-Ordner des laufenden Audits oder Reports:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
     --domain <domain> \
     --out "reporting/data/<run-id>" \
     [--max-urls 5000] [--delay 0.2]
   ```

   Ist die Quelle nicht fällig, den letzten vorhandenen `crawl.json`-Snapshot mit
   seinem Datum übernehmen, kein neuer Abruf, kein Delta (Spec Abschnitt 3: "nicht
   fällige Quellen erzeugen kein Delta").
3. Kernzahlen an den Nutzer melden: Anzahl gecrawlter URLs, Statuscode-Verteilung,
   Anteil nicht indexierbar, Anteil ohne Description, maximale Klicktiefe, längste
   Weiterleitungskette. Auffälligkeiten benennen (viele 404, tiefe Klicktiefe,
   KI-Crawler in robots.txt blockiert).

## Snapshot-Schema

Das Script schreibt `<out>/crawl.json`:

```json
{
  "domain": "https://www.example.com",
  "collected_at": "2026-09-05T07:33:05+00:00",
  "robots": {
    "found": true,
    "sitemaps": ["https://www.example.com/sitemap.xml"],
    "disallow_rules": {"*": ["/admin", "/cart"], "GPTBot": ["/"]},
    "ai_crawler_rules": {"GPTBot": "disallow", "ClaudeBot": "allowed"},
    "sitemap_errors": [{"sitemap": "...", "reason": "..."}]
  },
  "summary": {
    "url_count": 842,
    "status_code_distribution": {"200": 810, "404": 12, "error": 3},
    "share_not_indexable": 0.02,
    "share_without_description": 0.15,
    "pages_with_multiple_h1": 4,
    "images_without_alt": 37,
    "longest_redirect_chain": 2,
    "max_click_depth": 5,
    "blocked_links": 6,
    "robots_group": "*",
    "home_blocked_by_robots": false,
    "third_party_script_hosts": ["cdn.intelligems.io", "cdn.judge.me", "www.googletagmanager.com"],
    "max_urls": 5000,
    "hit_url_limit": false
  },
  "findings_index": {
    "cap": 25,
    "orphans": {"count": 0, "examples": ["..."]},
    "errors": {"count": 0, "by_status": {"404": 0}, "examples": [{"url", "status"}]},
    "multiple_canonicals": {"count": 0, "examples": [{"url", "canonical_count"}]},
    "canonical_mismatch": {"count": 0, "examples": [{"url", "canonical"}]},
    "duplicate_titles": {"count": 0, "groups": [{"title", "count", "examples"}]},
    "deepest": [{"url", "click_depth"}],
    "parameter_urls": {"count": 0, "indexable": 0,
                       "without_consolidating_canonical": 0, "examples": ["..."]},
    "schema_types": {"Product": 0},
    "pages_without_schema": {"count": 0, "examples": ["..."]},
    "path_prefixes": {"/products/": 0},
    "inline_tag_ids": {"G-XXXXXXXXXX": 300, "GTM-XXXXXXX": 300},
    "canonical_pages": 0,
    "h1": {"multiple": {"count": 0, "examples": []}, "missing": {"count": 0, "examples": []}},
    "titles": {"missing": {"count": 0, "examples": []},
               "too_long": {"count": 0, "examples": [], "max_chars": 60},
               "duplicate_groups": {"count": 0, "pages": 0, "groups": [{"text", "count", "examples"}]}},
    "descriptions": {"missing": {"count": 0, "examples": []},
                     "duplicate_groups": {"count": 0, "pages": 0, "groups": []}},
    "non_canonical_linked": {"count": 0, "examples": [], "share_of_crawl": 0.0,
                             "collection_product_urls": 0},
    "pagination": {"count": 0, "examples": [], "indexable": 0,
                   "canonical_to_first_page": {"count": 0, "examples": []}},
    "hreflang": {"pages_with_hreflang": 0, "languages": {"de": 0},
                 "missing_x_default": {"count": 0, "examples": []},
                 "missing_self_reference": {"count": 0, "examples": []},
                 "targets_not_crawled": {"count": 0, "examples": []},
                 "targets_not_indexable": {"count": 0, "examples": []},
                 "not_reciprocal": {"count": 0, "examples": []}},
    "product_markup": {"pages": 0, "missing": {"has_offers": {"count": 0, "examples": []}},
                       "multiple_nodes": {"count": 0, "examples": []},
                       "availability": {"InStock": 0}},
    "organization_markup": {"pages": 0, "home_url": "...", "home": null,
                            "with_return_policy": 0, "with_shipping_service": 0}
  },
  "pages": [
    {
      "url": "https://www.example.com/products/x",
      "status": 200,
      "redirects": [{"url": "...", "status": 301}],
      "end_url": "https://www.example.com/products/x/",
      "load_time_sec": 0.29,
      "click_depth": 2,
      "link_depth": 3,
      "title": "...", "description": "...", "canonical": "...", "canonical_count": 1,
      "hreflang": {}, "h1": ["..."], "images": {"total": 9, "without_alt": 0, "empty_alt": 0},
      "schema_types": ["Product"], "indexable": true,
      "markup": {"product": {"has_name": true, "has_image": true, "has_brand": true,
                             "has_identifier": true, "has_offers": true,
                             "price": "49.90", "currency": "EUR", "availability": "InStock",
                             "has_shipping_details": false, "has_return_policy": false,
                             "has_aggregate_rating": true, "has_variants": false, "count": 1}},
      "script_sources": ["//cdn.judge.me/y.js", "/assets/theme.js", "https://cdn.intelligems.io/x.js"],
      "internal_links": ["..."], "word_count": 340
    }
  ]
}
```

**`hit_url_limit` sagt, ob der Lauf an `--max-urls` aufgehört hat.** Dann sind
verwaiste Seiten und nie erreichte hreflang-Ziele kein Befund über den Shop,
sie können hinter der Grenze liegen. Ein Snapshot von vor dem 27.09.2026 trägt
das Feld nicht.

**Gerenderte Gegenprobe:** `scripts/render_check.py --crawl <crawl.json> --url
<adresse> ...` rendert bis zu zehn Seiten mit der Headless Shell aus
`scripts/lib/find_chrome.sh` und vergleicht Typen und Produktfelder mit dem
Crawl-Eintrag (`same`, `only_rendered`, `only_static`, `render_failed`). Die
Analyse nutzt das, bevor sie fehlende Auszeichnung als Befund schreibt.

**`inline_tag_ids` zählt Container- und Mess-IDs, die im Seitenquelltext
stehen, statt über ein `src`-Attribut geladen zu werden.** Genau die häufigsten
Doppelzähler (Tag Manager, GA4, Ads-Conversion) bauen sich per Inline-Snippet
ein und tauchen deshalb in `script_sources` und in
`summary.third_party_script_hosts` grundsätzlich nicht auf. Ohne diese Zeile
heißt "kein Hinweis auf doppelte Tags" in Wahrheit "nicht messbar". Zwei
GA4-IDs mit ähnlicher Seitenzahl sind der belegte Fall einer doppelten Messung.
Gespeichert werden ausschließlich die IDs, nie Skript-Inhalte.

**Die Blöcke ab `canonical_pages` gehören zur Kriterienliste vom 27.09.2026**
(`audit-seo-technical`, `audit-geo`). Ihre Zählregel steht im Code, nicht in
einer Abfrage des Agents, damit zwei Läufe auf demselben Snapshot dieselbe Zahl
liefern. Grundgesamtheit für H1, Title, Description und Produktauszeichnung
sind die indexierbaren Seiten, die auf sich selbst kanonisieren, jede Adresse
nur einmal (Startseite mit und ohne Schrägstrich, Weiterleitung und Ziel),
ohne die Folgeseiten einer Liste, die H1 und Description mit Seite 1 teilen.
Ohne diese Abgrenzung zählte eine Produktadresse im Collection-Kontext als
eigene Dublette ihrer kanonischen Seite; an einem echten Shop war das mehr als
das Zwölffache. `markup` stammt aus statischem HTML: per JavaScript
eingefügtes JSON-LD fehlt, deshalb prüft die Analyse gerendert gegen, bevor
sie "fehlt" schreibt. Ein Snapshot von vor dem 27.09.2026 hat diese Blöcke
nicht; dann sind die Kriterien dazu nicht messbar, nicht erfüllt.

**Von einer gefundenen Adresse bleibt nur `?page=<n>` ab Seite 2 stehen**,
jede andere Query fällt weg (`variant`, `sort_by`, Filter, Tracking). Eine
Folgeseite einer Kategorie ist eine eigene Seite mit eigenen Produktlinks.
Bis zum 02.10.2026 fiel auch `page` weg; ein Snapshot von davor enthält keine
Folgeseite, und jedes Produkt, das erst ab Seite 2 verlinkt ist, steht darin
als unverlinkt oder zu tief. Folgeseiten zählen unter `pagination`, nicht
unter `parameter_urls`. Sie kosten Budget: eine Kategorie mit 24 Seiten
belegt 24 Abrufe von `--max-urls`.

**`findings_index` ist der Zugang für die Analyse, nicht `pages`.** Die
Seitenliste trägt rund 6,8 KB je gecrawlter Seite, ein Shop mit 2000 Seiten
ergibt 13 MB; kein Analyse-Agent liest das am Stück, und ein abgeschnittener
Ausschnitt erzeugt Befunde über zufällig sichtbare Seiten. Der Index trägt je
Befundklasse die **vollständige** Anzahl und höchstens `cap` Beispiele als
Beleg. Wer mehr braucht, fragt `pages` gezielt mit `jq` ab, immer mit Filter
und Grenze.

Zwei Zahlen je Klasse sind bewusst getrennt: `count` ist die echte Menge,
`examples` ist die gekürzte Belegliste. Ein Befund nennt `count`, nie die
Länge von `examples`.

`robots.ai_crawler_rules` deckt eine feste, im Script gepflegte Liste bekannter
KI-Crawler ab (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot und weitere);
diese Liste veraltet und wird bei Bedarf nachgezogen. Die Auswertung ist bewusst kein
vollständiger robots.txt-Interpreter nach RFC 9309 (keine Wildcard- oder
Präzedenzregeln), sondern hält die wörtlichen Gruppen und ihre `Disallow`-Zeilen fest.

**Den Crawl selbst lenkt genau eine Gruppe.** Gibt es eine Gruppe für `ptai-audit`,
gilt nur sie, sonst gilt `*`, und gibt es beides nicht, gilt keine Regel. So schreibt
es RFC 9309 vor, und so sperrt die IT eines Shops einen bestimmten Bot aus. Die
eigene Gruppe wird unabhängig von Groß- und Kleinschreibung gefunden, auch als
`ptai-audit/1.0`; `ptai` oder `ptai-audit-beta` sind andere Namen. Welche Gruppe
gegriffen hat, steht in `summary.robots_group` (`"ptai-audit"`, `"*"` oder `null`).
Eine URL, deren Pfad eine `Disallow`-Regel dieser Gruppe trifft, wird nie abgerufen
und zählt in `summary.blocked_links`. `Allow` wertet das Script nicht aus, es ruft
im Zweifel also weniger ab, nicht mehr.

**Sperrt die Gruppe `ptai-audit` die Startseite, etwa mit `Disallow: /`, läuft kein
Crawl.** Abgerufen wird dann nur robots.txt, `pages` bleibt leer,
`summary.home_blocked_by_robots` steht auf `true`, und das Script endet mit Exit 1.
Das ist eine Absage des Shops an diesen Crawler, kein leerer Shop und kein Befund
über den Shop: melden, nicht auswerten. Ein `Disallow: /` unter `*` wirkt anders:
dort ruft der Crawl die Startseite weiter ab, weil ein Shop, der sich aus jeder
Suchmaschine aussperrt, selbst der Befund ist.

**`click_depth` ist die Tiefe des Inhalts ab der Startseite, nie die Position in der
Sitemap.** Jeder interne Link zählt einen Klick. Zusätzlich reicht eine Seite, die auf
eine andere erfasste Adresse kanonisiert, ihre Tiefe an diese weiter, ohne weiteren
Klick: wer sie erreicht, hat deren Inhalt vor sich. Shopify-Themes verlinken
Produktkarten als `/collections/<c>/products/<h>`, das ist schon die Produktseite mit
Canonical auf `/products/<h>`; die kanonische Adresse bekommt so die Tiefe der
Produktkarte statt eine Ebene mehr. Das gilt für jedes Canonical, nicht nur für dieses
Muster. Eine Weiterleitung zählt nicht mit, eine nicht abgerufene Seite (429,
Bot-Challenge) reicht nichts weiter, und ein Canonical-Ziel, das weder verlinkt ist
noch in der Sitemap steht, wird nicht abgerufen.

**`link_depth` ist die reine Linktiefe**, die kürzeste Zahl interner Links ab der
Startseite, also der Wert, der bis zum 02.10.2026 `click_depth` hieß. `click_depth` ist
nie größer. Weichen beide ab, liegt der Inhalt über eine andere Adresse näher an der
Startseite als die Adresse selbst. Beide entstehen nach dem Abruf aus dem erfassten
Graphen (`internal_links` und `canonical` je Seite).

Eine Seite, die auf keinem Weg von der Startseite erreicht wird, bekommt
`click_depth: null`, das ist selbst ein Befund (verwaiste, aber indexierte Seite).

**`summary.max_click_depth` und `findings_index.deepest` zählen jeden Inhalt einmal.**
Eine Adresse, deren Canonical-Ziel selbst im Crawl steht, fällt dort heraus, ihr Inhalt
steht unter dem Ziel mit höchstens derselben Tiefe. Sonst stünde jedes Produkt zweimal
unter den tiefsten Seiten, als Collection-Adresse und als Produktadresse.

Ein regulärer 404 oder 500 ist kein `error` in diesem Sinn, sondern selbst der
Befund: der Statuscode steht in `status`, nur ohne die SEO-Kopfdaten aus
`parse_page`, weil es dafür keinen auswertbaren Seiteninhalt gibt. `error`
erscheint nur bei einem echten Netzwerkfehler, einer Redirect-Kette über der
internen Grenze (Redirect-Loop) oder einem Nicht-HTML-Content-Type auf einer
2xx-Antwort.

## Setup-Check

`--check` ruft nur robots.txt und die Sitemap-Wurzel(n) ab und meldet, wie viele
URLs zu erwarten sind, ohne eine einzige Seite zu crawlen. Gedacht für den
Setup-Wizard und Gate A, um vor einem langen Lauf die Größenordnung zu kennen:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
  --domain <domain> --check
```

Exit 0 bei Erfolg. Exit 1, wenn keine einzige Sitemap-Wurzel erreichbar war
(Domain vermutlich falsch oder nicht erreichbar), oder wenn die Gruppe `ptai-audit`
in robots.txt die Startseite sperrt; dann wird die Sitemap gar nicht erst abgerufen,
weil der Crawl keine ihrer URLs abrufen würde.

## Der Lauf meldet sich, alle 20 Sekunden

Das Script schreibt seinen Fortschritt nach stderr, unabhängig davon, wie
schnell der Shop antwortet:

```
Sitemap: 3 Wurzel(n), wird aufgeloest ...
Sitemap: 4200 URLs, 0 Fehler.
Crawl startet: 4200 bekannte URLs, Budget 150 Seiten, Pause 0.3s. Meldung alle 20s.
Crawl: 3 Seiten in 0:20 (9/min), Pause 2.4s, 8 mal gedrosselt, 3 geparkt, noch 147 offen, fertig in rund 16 min
```

**Diese Zeilen sind der einzige Weg, einen langsamen Lauf von einem hängenden
zu unterscheiden.** Wer den Crawl im Hintergrund startet, liest sie und
entscheidet danach; wer ihn ohne sie startet, rät. Am 08.09.2026 lief ein
Crawl drei Stunden ohne eine einzige Zeile, und niemand konnte sagen, ob er
arbeitet. Er tat es, nur sehr langsam.

**Die drei Zahlen, die zählen:**

| Zahl | Was sie sagt | Wann sie ein Problem meldet |
|---|---|---|
| Tempo (`/min`) | wie viele Seiten der Lauf schafft | unter 30/min: der Shop drosselt |
| `Pause` | die aktuelle Wartezeit je Seite | über `--delay`: der Shop drosselt gerade |
| `gedrosselt` | wie oft 429 kam, über den ganzen Lauf | wächst weiter: `--delay` war zu klein |

**Die geschätzte Restzeit rechnet mit dem bisherigen Tempo** und wird deshalb
kürzer, sobald die Drosselung nachlässt. Sie ist eine Größenordnung, keine
Zusage.

## Bot-Erkennung: wenn 429 gar keine Drosselung ist

**Zwei völlig verschiedene Dinge kommen als HTTP 429 an, und der Unterschied
entscheidet über Stunden.** Eine Drosselung sagt "zu schnell", und langsamer
werden hilft. Eine Bot-Challenge sagt "du siehst aus wie ein Skript", und
langsamer werden hilft nie: die Abweisung kommt in Millisekunden zurück, egal
wie lange der Crawl vorher gewartet hat.

**Das Signal ist der Antwort-Header,** nicht der Statuscode. Cloudflare setzt
`Cf-Mitigated`; ein 429 von Cloudflare ohne `Retry-After` ist der zweite Fall,
weil eine echte Drosselung fast immer nennt, wann es wieder geht. Das Script
prüft beides (`bot_challenge()`), zählt solche Seiten getrennt in
`summary.bot_challenge_pages` und wiederholt sie **nicht**: sie erhöhen die
Pause nicht und wandern nicht in den Nachlauf.

**Was die Messung kostet, wenn das fehlt.** Am 08.09.2026 lief ein Crawl drei
Stunden gegen eine Cloudflare-Challenge an, weil beides als 429 ankam. Der
gemessene Unterschied auf demselben Shop, gleiche Minute, gleiche Seiten:

| | vorher (alles als Drosselung) | nachher (Challenge erkannt) |
|---|---|---|
| Tempo | 9 Seiten/min | 65 Seiten/min |
| Pause nach 20 Sekunden | 2,4 s (von 0,3 hochgelaufen) | unverändert 0,5 s |
| Restzeit für 150 Seiten | rund 16 Minuten | unter einer Minute |
| abgewiesene Seiten | als "gedrosselt" gezählt, Grund unbekannt | als Bot abgewiesen, mit Grund |

**Der Weg heraus führt über den Kunden, nicht über den Crawler.** Eine
Bot-Erkennung zu umgehen ist genau das, wogegen sie gebaut ist. Die Ausnahme
ist eine befristete Freigabe der festen Ausgangsadressen des Betreibers
(`reference/access.md`, Teil A, Schritt 7), beschrieben für den Kunden in
Teil B unter "Optional", Abschnitt "Eure Firewall". Sie
gehört in die Zugangs-Anforderung, sobald ein Lauf abgewiesene Seiten meldet.

**Eine Ausnahme nur für den User-Agent `ptai-audit` reicht nicht.** Diesen
User-Agent sendet allein dieses Script. `capture-screens` ruft mit dem
Standard-User-Agent des Headless-Browsers (Desktop) und einem
iOS-Safari-User-Agent (Mobil) ab, die Linsen und das Beleg-Gate von
`audit-light` über `curl` mit einem Chrome-User-Agent. Eine reine
User-Agent-Ausnahme lässt deshalb Screenshots, Kaufstrecke und Belegprüfung
gesperrt. Belegt am 23.09.2026 an einem Shop, dessen Firewall alle Pfade eines
Länderverzeichnisses mit 403 sperrte, für curl, Headless Chromium und
Playwright gleichermaßen. `ptai-audit` bleibt das Erkennungsmerkmal des Crawls
im Log des Kunden.

**Bis dahin ist der Snapshot unvollständig, und das steht drin.** Die
abgewiesenen Seiten liegen mit `bot_challenge` und ihrem Grund in `pages`,
`summary.bot_challenge_pages` zählt sie, und jeder Anteil aus dem Snapshot
bezieht sich auf die messbaren Seiten. Das ist der Unterschied zu vorher, als
sie einfach fehlten.

## Drosselung: wenn der Shop mit 429 antwortet

**429 heißt "später nochmal", nicht "gibt es nicht".** Eine abgewiesene Seite
wird im Hauptdurchgang **genau einmal** wiederholt. Antwortet sie auch dann
nicht, wandert sie in den Nachlauf, und der Hauptdurchgang läuft weiter. Der
Nachlauf holt die geparkten Seiten am Ende in zwei Runden mit der höchsten
Pause; der Shop hatte bis dahin Zeit, sich zu erholen. Was auch dann fehlt,
trägt `"throttled": true` und zählt in `summary.throttled_pages`.

**Zwei Fehler stecken in dieser Mechanik, beide am 08.09.2026 bezahlt:**

1. **Vorher galt eine abgewiesene Antwort als erledigte Seite.** Im ersten
   echten Lauf fehlte dadurch rund ein Drittel aller Seiten im Snapshot. Der
   sah aus wie ein fertiger Crawl, und jeder Anteil darin ("72 Prozent der
   Produktseiten haben mehrere H1") bezog sich in Wahrheit auf die
   verbliebenen zwei Drittel, ohne dass das irgendwo stand.
2. **Der erste Fix wiederholte dreimal je Seite mit einer Pause von
   `delay * 16`.** Bei `--delay 0.6` sind das 9,6 Sekunden, mal drei Versuche
   29 Sekunden für eine einzige Seite, und ein Lauf über 3.000 URLs hätte
   einen Tag gebraucht. Deshalb ist die Pause heute absolut gedeckelt
   (`PAUSE_MAX`, 5 Sekunden) statt an `--delay` gekoppelt, und deshalb hängt
   der Hauptdurchgang nie an einer Seite.

**`--delay` wählen, statt ihn zu erben.** Ein Shop, der drosselt, drosselt ab
der ersten Minute: die Fortschrittszeile zeigt es nach 20 Sekunden. Steigt die
Pause dort schon über den gesetzten `--delay`, den Lauf abbrechen und mit
höherem `--delay` neu starten, statt ihn stundenlang gegen die Bremse fahren
zu lassen. Ein Lauf mit `--delay 1.0`, der durchläuft, ist schneller fertig
als einer mit `--delay 0.2`, der sich hochschaukelt.

**Meldet der Lauf am Ende aufgegebene Seiten, ist der Snapshot
unvollständig**, und `audit.qa` weist das als Warnung aus.

## Fehlerbilder

- `sources.crawl: false` oder `domain` fehlt in der Config: Crawl als "nicht
  verfügbar (Grund)" melden, Rest des Laufs unberührt.
- Eine einzelne URL scheitert (Netzwerkfehler, Timeout, Redirect-Loop): landet als
  Zeile mit `error` in `pages`, beendet nie den Lauf. Das gilt für jede URL, egal
  ob sie aus der Sitemap oder aus einem internen Link stammt.
- Eine einzelne Sitemap im Baum ist kaputt (ungültiges XML, 404 mit
  XML-Content-Type): landet als Eintrag in `robots.sitemap_errors`, die übrigen
  Äste des Sitemap-Baums werden trotzdem aufgelöst. Das war explizit die
  Übergabe aus dem Parsing-Teil: die Sitemap-Auflösung läuft vor der Seitenschleife
  und braucht dieselbe Isolierung wie die Schleife selbst.
- robots.txt fehlt oder ist nicht erreichbar: kein Fehler, der Crawl fällt auf
  `{domain}/sitemap.xml` zurück.
- `--check` findet keine einzige erreichbare Sitemap-Wurzel: Exit 1 mit Grund,
  gedacht als Signal für den Wizard, dass die Domain selbst geprüft werden muss.
- robots.txt sperrt `ptai-audit` mit einer eigenen Gruppe ab der Startseite:
  `crawl.json` entsteht mit leerem `pages` und `summary.home_blocked_by_robots:
  true`, das Script endet mit Exit 1. Den Crawl als "nicht verfügbar, vom Shop per
  robots.txt ausgeschlossen" melden, keine Kernzahlen daraus ableiten.
- Eigener User-Agent `ptai-audit/1.0`, damit der Kunde und Dritte den Bot erkennen
  können. Beim Abruf gilt `Disallow` aus genau einer robots.txt-Gruppe (siehe oben,
  Abschnitt Snapshot-Schema).
