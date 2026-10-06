---
name: crawl-site
description: Zieht einen vollständigen Site-Crawl über sitemap.xml und interne Links (Statuscodes, Weiterleitungsketten, Titles, Descriptions, H1, Canonicals, hreflang, robots.txt, interne Verlinkung und Klicktiefe, Wortzahl, strukturierte Daten, Bilder, eingebundene Fremdskripte) und legt ihn als Snapshot ab. Einsetzen, wenn der Audit oder ein monatlicher Report frische Crawl-Daten braucht oder der Nutzer ausdrücklich einen Site-Crawl für eine Domain will. Liest reporting/config.json im Kunden-Workspace.
---

# crawl-site: vollständigen Site-Crawl ziehen

Crawlt eine Domain über den aufgelösten Sitemap-Baum plus Breitensuche über interne Links. Je URL:

- Statuscode, vollständige Weiterleitungskette, Ladezeit
- SEO-Kopfdaten aus `parse_page`: Title, Description, Canonical, hreflang, H1, Bilder, strukturierte Daten, interne Links, eingebundene Skript-Quellen
- Klicktiefe ab der Startseite

Aufruf durch Audit- und Report-Lauf oder einzeln.

**Kadenz: monatlich (Spec Abschnitt 3).**

- Ein Crawl ist teuer (bis zu `--max-urls` Abrufe mit Pause dazwischen) und ändert sich zwischen zwei Reports selten.
- Überschreibbar in `reporting/config.json` unter `cadences.crawl`.
- Ein Lauf mit "alles ziehen"-Schalter zieht ihn auch außer der Reihe.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `domain` (z. B. `https://www.example.com`) und `sources.crawl` ungleich `false`.

`sources.crawl` auf `false` oder `domain` fehlt: Crawl als "nicht verfügbar (Grund)" melden und stoppen. Ein Fehlschlag legt nie den Gesamtlauf (Audit oder Report) lahm; das gilt für die Quelle als Ganzes und für jede einzelne URL.

## Ablauf

1. `reporting/config.json` lesen: `domain`, `sources.crawl`, Umfang über `audit.config.crawl_budget(config)`. Liefert immer `crawl_max_urls` und `crawl_delay_sec`, mit Vorgaben, wenn die Felder fehlen.
   - **Umfang nie aus dem Prompt nehmen.** Er hängt am Shop (Zahl der Sitemap-URLs, Sprachdubletten, Antwortzeit), nicht am Lauf. Aus dem Prompt fiele er im nächsten Lauf still auf die Vorgabe zurück.
2. Quelle fällig (Kadenz `month`, siehe `audit/run.py`) oder erzwungen: Script aufrufen, Zielordner = Daten-Ordner des laufenden Audits oder Reports:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
     --domain <domain> \
     --out "reporting/data/<run-id>" \
     [--max-urls 5000] [--delay 0.2]
   ```

   Nicht fällig: letzten vorhandenen `crawl.json`-Snapshot mit seinem Datum übernehmen, kein neuer Abruf, kein Delta (Spec Abschnitt 3: "nicht fällige Quellen erzeugen kein Delta").
3. Dem Nutzer melden: Zahl gecrawlter URLs, Statuscode-Verteilung, Anteil nicht indexierbar, Anteil ohne Description, maximale Klicktiefe, längste Weiterleitungskette. Auffälligkeiten nennen (viele 404, große Klicktiefe, KI-Crawler in robots.txt blockiert).

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

### `hit_url_limit`

- Zeigt, ob der Lauf an `--max-urls` gestoppt hat.
- Dann sind verwaiste Seiten und nicht erreichte hreflang-Ziele kein Befund über den Shop; sie können hinter der Grenze liegen.
- Snapshots vor dem 27.09.2026 haben das Feld nicht.

### Gerenderte Gegenprobe

- `scripts/render_check.py --crawl <crawl.json> --url <adresse> ...` rendert bis zu zehn Seiten mit der Headless Shell aus `scripts/lib/find_chrome.sh`.
- Vergleicht Typen und Produktfelder mit dem Crawl-Eintrag: `same`, `only_rendered`, `only_static`, `render_failed`.
- Die Analyse nutzt das, bevor sie fehlende Auszeichnung als Befund schreibt.

### `inline_tag_ids`

- Zählt Container- und Mess-IDs im Seitenquelltext, die nicht über ein `src`-Attribut geladen werden.
- Die häufigsten Doppelzähler (Tag Manager, GA4, Ads-Conversion) werden per Inline-Snippet eingebaut und erscheinen nie in `script_sources` oder `summary.third_party_script_hosts`. Ohne diesen Block hieße "kein Hinweis auf doppelte Tags" nur "nicht messbar".
- Zwei GA4-IDs mit ähnlicher Seitenzahl = doppelte Messung.
- Gespeichert werden nur die IDs, nie Skript-Inhalte.

### Blöcke ab `canonical_pages`

- Gehören zur Kriterienliste vom 27.09.2026 (`audit-seo-technical`, `audit-geo`).
- Zählregel im Code, nicht in einer Agent-Abfrage, damit zwei Läufe auf demselben Snapshot dieselbe Zahl liefern.
- Grundgesamtheit für H1, Title, Description und Produktauszeichnung:
  - indexierbare Seiten mit Canonical auf sich selbst
  - jede Adresse einmal (Startseite mit und ohne Schrägstrich, Weiterleitung und Ziel)
  - ohne Folgeseiten einer Liste, die H1 und Description mit Seite 1 teilen
- Ohne diese Abgrenzung zählt eine Produktadresse im Collection-Kontext als Dublette ihrer kanonischen Seite (an einem Shop mehr als das Zwölffache).
- `markup` stammt aus statischem HTML. Per JavaScript eingefügtes JSON-LD fehlt; die Analyse prüft gerendert gegen, bevor sie "fehlt" schreibt.
- Snapshots vor dem 27.09.2026 haben diese Blöcke nicht; die Kriterien gelten dann als nicht messbar, nicht als nicht erfüllt.

### Query-Parameter und Folgeseiten

- Von einer gefundenen Adresse bleibt nur `?page=<n>` ab Seite 2; jede andere Query fällt weg (`variant`, `sort_by`, Filter, Tracking).
- Eine Folgeseite ist eine eigene Seite mit eigenen Produktlinks.
- Snapshots vor dem 02.10.2026 enthalten keine Folgeseiten; Produkte, die erst ab Seite 2 verlinkt sind, erscheinen dort als unverlinkt oder zu tief.
- Folgeseiten zählen unter `pagination`, nicht unter `parameter_urls`.
- Sie verbrauchen Budget: eine Kategorie mit 24 Seiten belegt 24 Abrufe von `--max-urls`.

### `findings_index` statt `pages`

- Die Analyse liest `findings_index`, nicht `pages`.
- `pages` hat rund 6,8 KB je Seite (2000 Seiten = 13 MB). Ein Agent liest das nicht am Stück; ein abgeschnittener Ausschnitt ergibt Befunde über zufällig sichtbare Seiten.
- Der Index enthält je Befundklasse die **vollständige** Anzahl und höchstens `cap` Beispiele als Beleg.
- Mehr Detail: `pages` gezielt mit `jq` abfragen, immer mit Filter und Grenze.
- `count` = echte Menge, `examples` = gekürzte Belegliste. Ein Befund nennt `count`, nie die Länge von `examples`.

### robots.txt

- `robots.ai_crawler_rules` deckt eine im Script gepflegte Liste bekannter KI-Crawler ab (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot und weitere). Die Liste veraltet und wird bei Bedarf ergänzt.
- Kein vollständiger robots.txt-Interpreter nach RFC 9309 (keine Wildcard- oder Präzedenzregeln). Festgehalten werden die wörtlichen Gruppen und ihre `Disallow`-Zeilen.

**Gruppe für den Crawl selbst (genau eine, nach RFC 9309):**

1. Gruppe für `ptai-audit` vorhanden: nur sie gilt.
2. Sonst `*`.
3. Keine von beiden: keine Regel.

- Die eigene Gruppe wird ohne Rücksicht auf Groß- und Kleinschreibung gefunden, auch als `ptai-audit/1.0`. `ptai` oder `ptai-audit-beta` sind andere Namen.
- Greifende Gruppe in `summary.robots_group` (`"ptai-audit"`, `"*"` oder `null`).
- URL, deren Pfad eine `Disallow`-Regel dieser Gruppe trifft: nie abgerufen, zählt in `summary.blocked_links`.
- `Allow` wertet das Script nicht aus; im Zweifel ruft es weniger ab, nicht mehr.

**Startseite für `ptai-audit` gesperrt (etwa `Disallow: /`):**

- Kein Crawl. Nur robots.txt wird abgerufen, `pages` bleibt leer, `summary.home_blocked_by_robots` = `true`, Exit 1.
- Das ist eine Absage des Shops an diesen Crawler, kein leerer Shop und kein Befund: melden, nicht auswerten.
- `Disallow: /` unter `*` wirkt anders: die Startseite wird weiter abgerufen, denn ein Shop, der sich aus allen Suchmaschinen aussperrt, ist selbst der Befund.

### Klicktiefe

**`click_depth` = Tiefe des Inhalts ab der Startseite, nie die Position in der Sitemap.**

- Jeder interne Link zählt einen Klick.
- Kanonisiert eine Seite auf eine andere erfasste Adresse, gibt sie ihre Tiefe ohne weiteren Klick an diese weiter.
- Beispiel Shopify: Produktkarten verlinken `/collections/<c>/products/<h>` mit Canonical auf `/products/<h>`; die kanonische Adresse erhält die Tiefe der Produktkarte, nicht eine Ebene mehr. Gilt für jedes Canonical.
- Weiterleitungen zählen nicht mit.
- Nicht abgerufene Seiten (429, Bot-Challenge) geben nichts weiter.
- Ein Canonical-Ziel, das weder verlinkt noch in der Sitemap ist, wird nicht abgerufen.

**`link_depth` = reine Linktiefe** (kürzeste Zahl interner Links ab Startseite).

- Hieß bis zum 02.10.2026 `click_depth`.
- `click_depth` ist nie größer. Weichen beide ab, ist der Inhalt über eine andere Adresse näher an der Startseite.
- Beide entstehen nach dem Abruf aus dem erfassten Graphen (`internal_links` und `canonical` je Seite).
- Seite ohne Weg von der Startseite: `click_depth: null`. Das ist ein Befund (verwaiste, aber indexierte Seite).

**`summary.max_click_depth` und `findings_index.deepest` zählen jeden Inhalt einmal.** Adressen, deren Canonical-Ziel im Crawl steht, fallen heraus; ihr Inhalt steht unter dem Ziel mit höchstens derselben Tiefe. Sonst stünde jedes Produkt doppelt unter den tiefsten Seiten.

### Statuscodes und `error`

- Regulärer 404 oder 500 ist kein `error`, sondern selbst der Befund: Statuscode in `status`, ohne SEO-Kopfdaten aus `parse_page` (kein auswertbarer Inhalt).
- `error` nur bei:
  - Netzwerkfehler
  - Redirect-Kette über der internen Grenze (Redirect-Loop)
  - Nicht-HTML-Content-Type auf einer 2xx-Antwort

## Setup-Check

`--check` ruft nur robots.txt und die Sitemap-Wurzel(n) ab und meldet die erwartete URL-Zahl, ohne eine Seite zu crawlen. Für Setup-Wizard und Gate A, um vor einem langen Lauf die Größenordnung zu kennen:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
  --domain <domain> --check
```

- Exit 0: Erfolg.
- Exit 1: keine Sitemap-Wurzel erreichbar (Domain vermutlich falsch oder nicht erreichbar).
- Exit 1: Gruppe `ptai-audit` sperrt die Startseite; die Sitemap wird dann nicht abgerufen, da der Crawl keine ihrer URLs abrufen würde.

## Fortschritt alle 20 Sekunden

Das Script schreibt den Fortschritt nach stderr, unabhängig vom Antworttempo des Shops:

```
Sitemap: 3 Wurzel(n), wird aufgeloest ...
Sitemap: 4200 URLs, 0 Fehler.
Crawl startet: 4200 bekannte URLs, Budget 150 Seiten, Pause 0.3s. Meldung alle 20s.
Crawl: 3 Seiten in 0:20 (9/min), Pause 2.4s, 8 mal gedrosselt, 3 geparkt, noch 147 offen, fertig in rund 16 min
```

- **Nur diese Zeilen unterscheiden einen langsamen von einem hängenden Lauf.** Bei Start im Hintergrund die Zeilen lesen und danach entscheiden.

| Zahl | Was sie sagt | Wann sie ein Problem meldet |
|---|---|---|
| Tempo (`/min`) | wie viele Seiten der Lauf schafft | unter 30/min: der Shop drosselt |
| `Pause` | die aktuelle Wartezeit je Seite | über `--delay`: der Shop drosselt gerade |
| `gedrosselt` | wie oft 429 kam, über den ganzen Lauf | wächst weiter: `--delay` war zu klein |

- Die Restzeit rechnet mit dem bisherigen Tempo und sinkt, sobald die Drosselung nachlässt. Größenordnung, keine Zusage.

## Bot-Erkennung: 429 ohne Drosselung

| | Drosselung | Bot-Challenge |
|---|---|---|
| Bedeutung | zu schnell | sieht aus wie ein Skript |
| langsamer werden | hilft | hilft nie; Abweisung kommt in Millisekunden |

**Erkennung über den Antwort-Header, nicht den Statuscode:**

- Cloudflare setzt `Cf-Mitigated`.
- 429 von Cloudflare ohne `Retry-After` = Bot-Challenge; echte Drosselung nennt fast immer den Zeitpunkt.
- Das Script prüft beides (`bot_challenge()`), zählt solche Seiten in `summary.bot_challenge_pages` und wiederholt sie **nicht**: keine höhere Pause, kein Nachlauf.

Messung am selben Shop, gleiche Minute, gleiche Seiten:

| | vorher (alles als Drosselung) | nachher (Challenge erkannt) |
|---|---|---|
| Tempo | 9 Seiten/min | 65 Seiten/min |
| Pause nach 20 Sekunden | 2,4 s (von 0,3 hochgelaufen) | unverändert 0,5 s |
| Restzeit für 150 Seiten | rund 16 Minuten | unter einer Minute |
| abgewiesene Seiten | als "gedrosselt" gezählt, Grund unbekannt | als Bot abgewiesen, mit Grund |

**Lösung über den Kunden, nicht über den Crawler.**

- Eine Bot-Erkennung wird nicht umgangen.
- Ausnahme: befristete Freigabe der festen Ausgangsadressen des Betreibers (`reference/access.md`, Teil A, Schritt 7), für den Kunden beschrieben in Teil B unter "Optional", Abschnitt "Eure Firewall".
- Gehört in die Zugangs-Anforderung, sobald ein Lauf abgewiesene Seiten meldet.

**Ausnahme nur für den User-Agent `ptai-audit` reicht nicht.**

- `ptai-audit` sendet nur dieses Script.
- `capture-screens` nutzt den Standard-User-Agent des Headless-Browsers (Desktop) und einen iOS-Safari-User-Agent (Mobil).
- Die Linsen und das Beleg-Gate von `audit-light` nutzen `curl` mit Chrome-User-Agent.
- Eine reine User-Agent-Ausnahme lässt Screenshots, Kaufstrecke und Belegprüfung gesperrt. Firewalls sperren curl, Headless Chromium und Playwright oft gleichermaßen.
- `ptai-audit` bleibt das Erkennungsmerkmal des Crawls im Log des Kunden.

**Bis zur Freigabe ist der Snapshot unvollständig und weist das aus:**

- Abgewiesene Seiten stehen mit `bot_challenge` und Grund in `pages`.
- `summary.bot_challenge_pages` zählt sie.
- Jeder Anteil im Snapshot bezieht sich auf die messbaren Seiten.

## Drosselung: 429 vom Shop

**429 heißt "später nochmal", nicht "gibt es nicht".**

1. Abgewiesene Seite im Hauptdurchgang **genau einmal** wiederholen.
2. Wieder abgewiesen: in den Nachlauf parken, Hauptdurchgang läuft weiter.
3. Nachlauf am Ende: zwei Runden mit der höchsten Pause.
4. Danach noch fehlend: `"throttled": true`, Zählung in `summary.throttled_pages`.

Regeln:

- Eine abgewiesene Antwort ist nie eine erledigte Seite. Sonst fehlen Seiten unbemerkt, und jeder Anteil bezieht sich auf einen unbekannten Rest.
- Pause absolut gedeckelt (`PAUSE_MAX`, 5 Sekunden), nicht an `--delay` gekoppelt. Eine Kopplung wie `delay * 16` ergäbe bei `--delay 0.6` 9,6 Sekunden je Versuch.
- Der Hauptdurchgang wartet nie auf eine einzelne Seite.

**`--delay` bewusst wählen:**

- Ein drosselnder Shop drosselt ab der ersten Minute; die Fortschrittszeile zeigt es nach 20 Sekunden.
- Steigt `Pause` dort über den gesetzten `--delay`: Lauf abbrechen, mit höherem `--delay` neu starten.
- `--delay 1.0` ohne Drosselung ist schneller fertig als `--delay 0.2` mit hochlaufender Pause.

**Aufgegebene Seiten am Ende = unvollständiger Snapshot**; `audit.qa` gibt eine Warnung aus.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| `sources.crawl: false` oder `domain` fehlt | Crawl als "nicht verfügbar (Grund)" melden, Rest des Laufs unberührt. |
| Einzelne URL scheitert (Netzwerkfehler, Timeout, Redirect-Loop) | Zeile mit `error` in `pages`, nie Abbruch. Gilt für URLs aus Sitemap und internen Links. |
| Einzelne Sitemap im Baum kaputt (ungültiges XML, 404 mit XML-Content-Type) | Eintrag in `robots.sitemap_errors`, die übrigen Äste werden aufgelöst. Die Sitemap-Auflösung läuft vor der Seitenschleife und ist genauso isoliert. |
| robots.txt fehlt oder ist nicht erreichbar | Kein Fehler, Rückfall auf `{domain}/sitemap.xml`. |
| `--check` findet keine erreichbare Sitemap-Wurzel | Exit 1 mit Grund; Signal an den Wizard, die Domain zu prüfen. |
| robots.txt sperrt `ptai-audit` per eigener Gruppe ab der Startseite | `crawl.json` mit leerem `pages` und `summary.home_blocked_by_robots: true`, Exit 1. Melden als "nicht verfügbar, vom Shop per robots.txt ausgeschlossen", keine Kernzahlen ableiten. |

- Eigener User-Agent `ptai-audit/1.0`, damit Kunde und Dritte den Bot erkennen.
- Beim Abruf gilt `Disallow` aus genau einer robots.txt-Gruppe (siehe Snapshot-Schema, robots.txt).
