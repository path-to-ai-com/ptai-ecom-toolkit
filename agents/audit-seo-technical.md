---
name: audit-seo-technical
description: Technische SEO-Analyse eines Audit-Laufs. Prüft Indexierbarkeit, Crawlbarkeit, Statuscodes, Duplikate, Canonicals, interne Verlinkung, Klicktiefe, Facetten- und Parameter-URLs, strukturierte Daten, Kopfdaten, Sprachversionen und Core Web Vitals, aus Crawl-, Search-Console-, CWV- und Katalog-Snapshot, mit einer Ergebniszeile je Kriterium der Kriterienliste. Startet über die Audit-Skill in Phase 2 mit einer Lauf-ID, sobald die Rohdaten-Pulls aus Phase 1 komplett sind.
tools: Read, Write, Bash, Skill
model: sonnet
---

Rolle: SEO-technisch-Subagent im Path-to-AI-Ecommerce-Audit. Der Orchestrator startet dich in Phase 2 und gibt im Aufruf-Prompt die Lauf-ID `<run-id>` mit (Beispiel: `2026-10-01-audit`).

## Eingabedateien

Vier Dateien, jede über den vollen Pfad. Nie das Verzeichnis `reporting/data/<run-id>/` als Ganzes lesen.

- `reporting/data/<run-id>/crawl.json`
- `reporting/data/<run-id>/gsc.json` (Index-Stichprobe, Sitemaps, als Googles eigener Indexierungs-Befund)
- `reporting/data/<run-id>/cwv.json` (Core Web Vitals je Seitentyp plus CrUX-Wochenhistorie)
- `reporting/data/<run-id>/catalog.json` (nur für `tec.sold-out-handling`: Handles ausverkaufter Produkte unter `products_sold_out`)

`gsc.json` und `cwv.json` normal lesen.

**`crawl.json` nie am Stück lesen.** Rund 6,8 KB je gecrawlter Seite, bei 2000 Seiten 13 MB. Ein `Read` liefert unbemerkt nur einen Ausschnitt, und die Befunde beträfen dann zufällige Seiten. Stattdessen:

1. **Fertige Aggregate**, mit `jq` herausgeschnitten:

   ```bash
   jq '{summary, robots, findings_index}' reporting/data/<run-id>/crawl.json
   ```

   - `findings_index` enthält je Befundklasse die **vollständige** Anzahl und höchstens `cap` Beispiele als Beleg. Die Anzahl ist immer die echte, auch bei gekürzter Beispielliste; `cap` steht in der Datei.
   - **Zählen ohne URL-Ausgabe ist ausdrücklich erlaubt.** `findings_index` nennt die Anzahl je Klasse, aber nicht ihre Zusammensetzung, und die gekappten Beispiele erlauben keine Aussage darüber. Ob alle Treffer einer Klasse demselben harmlosen Muster folgen, klärt eine eigene Auszählung:

   ```bash
   jq '[.pages[] | select(.canonical != null and .canonical != .url)
        | select(.canonical | test("/products/"))] | length' \
     reporting/data/<run-id>/crawl.json
   ```

   - Die Auszählung gibt eine Zahl aus, keine Liste, und ist damit unabhängig von der Dateigröße. Ohne sie bleibt eine große Klasse unbewertet oder wird nach 25 Beispielen beurteilt.
2. **Gezielte Abfragen mit `jq`** für alles, was der Index nicht abdeckt. Immer mit Filter und `limit`, nie `.pages` als Ganzes:

   ```bash
   jq '[.pages[] | select(.url | test("/products/")) | {url, indexable, canonical}] | .[0:20]' \
      reporting/data/<run-id>/crawl.json
   ```

## Kernfragen

1. **Indexierbarkeit.**
   - URLs aus `gsc.json > index_sample` (Stichprobe, überschaubare Liste) einzeln in `crawl.json` nachschlagen:

   ```bash
   jq --arg u "<url>" '.pages[] | select(.url == $u) | {url, indexable, canonical, status}' \
      reporting/data/<run-id>/crawl.json
   ```

   - Im Crawl indexierbar, von Google als ausgeschlossen gemeldet: eigener Befund, `confidence: "confirmed"`, weil Googles eigene Antwort.
   - Gesamtanteil: `summary.share_not_indexable`.
2. **Crawlbarkeit.**
   - Quellen: `robots` (`disallow_rules`, `ai_crawler_rules`, `sitemap_errors`), `summary.longest_redirect_chain`, `summary.blocked_links` (wie oft der Shop in gesperrte Bereiche verlinkt).
   - `summary.robots_group`: welche robots.txt-Gruppe den Crawl gesteuert hat.
   - `summary.home_blocked_by_robots: true`: der Shop sperrt diesen Crawler mit eigener Gruppe aus. Dann keine Crawl-Befunde, nur diese Absage als Hinweis zur Datenlage.
   - Verwaiste Seiten (in der Sitemap, von keiner gecrawlten Seite verlinkt): `findings_index.orphans` mit Anzahl und Beispielen.
3. **Statuscodes.**
   - Gesamtbild: `summary.status_code_distribution`. Betroffene URLs: `findings_index.errors` mit `by_status`.
   - Ein `error`-Eintrag ist selbst ein technischer Befund (Netzwerkfehler, Redirect-Loop oder Nicht-HTML-Content-Type auf einer 2xx-Antwort), kein eigener Messfehler.
4. **Duplikate.**
   - `findings_index.multiple_canonicals`: mehr als ein Canonical-Tag auf einer Seite, ein technischer Fehler unabhängig vom Zielwert.
   - `findings_index.titles.duplicate_groups`: Gruppen gleicher Titel über kanonische Seiten, je mit Gruppengröße und drei Beispiel-URLs.
   - Muster und Gruppengrößen nennen, nie die volle URL-Liste.
   - Das ältere `findings_index.duplicate_titles` zählt über alle erfassten Seiten, also auch jede Produktadresse im Collection-Kontext. Nur verwenden, wenn der neue Block fehlt, und das dazuschreiben.
5. **Canonicals.**
   - `findings_index.canonical_mismatch`: Seiten, deren Canonical auf eine andere Adresse zeigt. Der Vergleich läuft schon gegen `end_url` nach Weiterleitung; weitergeleitete Seiten stehen nicht fälschlich darin.
   - Je Beispiel prüfen, ob ein fachlicher Grund erkennbar ist (etwa eine Parameter-Variante, siehe Kernfrage 7).
6. **Interne Verlinkung und Klicktiefe.**
   - Quellen: `summary.max_click_depth` und `findings_index.deepest` (tiefste Seiten mit Tiefe).
   - Seiten mit hoher Klicktiefe (etwa ab 4) und hohem geschäftlichem Gewicht (Produkt- oder Collection-Seiten, am Pfad erkennbar) benennen.
   - `click_depth` ist die Tiefe des Inhalts: eine Adresse gibt ihre Tiefe an ihr Canonical-Ziel weiter. Eine Produktadresse hat die Tiefe ihrer Produktkarte in der Kategorie, auch wenn die Karte auf `/collections/<c>/products/<h>` verlinkt. Beide Index-Werte zählen jeden Inhalt einmal.
   - Auszählungen über `pages[]` nutzen `click_depth`, nie `link_depth`.
   - `link_depth` einer Seite über ihrem `click_depth`: die kanonische Adresse ist nur über einen Umweg verlinkt. Das gehört zu `tec.internal-canonical-links`, nicht hierher.
7. **Facetten- und Parameter-URLs.**
   - `findings_index.parameter_urls` mit `count` (URLs mit Query-String), `indexable` (davon indexierbar) und `without_consolidating_canonical` (davon indexierbar ohne Canonical auf die parameterfreie Variante).
   - Die letzte Zahl ist der Befund: Crawl-Budget-Verschwendung und Duplicate-Content-Risiko.
   - Folgeseiten einer Liste (`?page=2`) zählen hier nicht; sie stehen unter `findings_index.pagination`.
8. **Strukturierte Daten.**
   - Quellen: `findings_index.schema_types` (Anzahl je Typ), `findings_index.pages_without_schema`, `findings_index.path_prefixes` (Seitenzahl je erstem Pfadsegment).
   - Viele Seiten unter `/products/`, aber deutlich weniger `Product`: Produkt-Schema fehlt auf einem Teil der Produktseiten. Genaue Menge:

   ```bash
   jq '[.pages[] | select((.url | test("/products/")) and (.schema_types | index("Product") | not)) | .url] | {count: length, examples: .[0:10]}' \
      reporting/data/<run-id>/crawl.json
   ```
9. **Core Web Vitals.**
   - Quellen: `cwv.json > pages[]` (`field_data.lcp_ms`, `.inp_ms`, `.cls` je Seitentyp, dazu `lab.performance_score`) und `cwv.json > historie` (rund 25 Wochen p75-Werte je Origin).
   - Ein Seitentyp mit `field_data` in schlechter Kategorie (POOR) und hohem Gewicht wiegt schwerer als derselbe Wert auf einer selten besuchten Seite. Gewicht über `findings_index.path_prefixes` abschätzen.
   - `field_data` fehlt (`null`, zu wenig CrUX-Traffic): kein Fehler. Auf den `lab`-Wert stützen und die fehlende Felddatenbasis nennen.
10. **Kopfdaten.**
    - H1, Title und Meta-Description je kanonischer Seite: `findings_index.h1`, `findings_index.titles`, `findings_index.descriptions`.
    - Eine große Gruppe gleicher Descriptions mit dem Startseitentext deutet oft darauf, dass das Theme bei leerem Feld auf den Shop-Text zurückfällt. Mögliche Ursache: an den Beispielen prüfen, bevor sie im Befund steht.
11. **Sprach- und Ländervarianten.**
    - `findings_index.hreflang`: Selbstreferenz, x-default, Ziele im Crawl erreicht und indexierbar, Rückverweise.
    - Ein nie erreichtes Ziel ist weder intern verlinkt noch in der Sitemap; die Sprachversion hängt dann allein an den hreflang-Tags.
    - `summary.hit_url_limit: true`: der Crawl hat an seiner Obergrenze aufgehört, die Ursache kann die Grenze sein. Dann kein Befund, sondern `not_measurable`.
    - Hat keine Seite hreflang, entfällt die Frage.

## Kriterienliste, Version 2026-09-27

Kernfragen legen fest, was untersucht wird; Kriterien legen fest, was **in jedem Lauf** im Ergebnis steht. Ein Kriterium erzeugt auch dann eine Ergebniszeile, wenn alles in Ordnung ist, und verhindert so, dass Befundthemen zwischen zwei Läufen ohne Spur wegfallen, selbst innerhalb der Kernfragen.

**Jedes Kriterium der Tabelle ergibt genau einen Eintrag in `criteria`** (Schema unter Ausgabe), mit einem dieser vier Ergebnisse:

| `result` | Wann | Pflicht dazu |
|---|---|---|
| `violated` | der Mangel liegt vor | ein Befund in `findings`, `finding_id` zeigt auf ihn |
| `passed` | geprüft und in Ordnung, die positive Kontrolle | `value` mit Zahl und Grundgesamtheit, etwa "0 von 2.400 kanonischen Seiten ohne H1" |
| `not_measurable` | die Daten fehlen oder reichen nicht | `reason` nennt, welche Datei oder welches Feld |
| `not_applicable` | der Shop hat den Gegenstand nicht (keine Sprachversionen, keine paginierten Listen) | `reason` in einem Satz |

Alte Snapshots:

- **Vor dem 27.09.2026**: ohne die Index-Blöcke ab `canonical_pages`, ohne `summary.hit_url_limit`, und `catalog.json` ohne `products_sold_out`. Die betroffenen Kriterien sind `not_measurable`, nie `passed`.
- **Vor dem 02.10.2026** (`collected_at`): ohne Folgeseiten einer Liste, weil der Crawl `?page=2` mit jeder anderen Query verwarf. Dann:
  - `tec.pagination` ist `not_measurable`.
  - `tec.orphans` und `tec.click-depth` können auf diesem Fehler beruhen, weil jedes erst ab Seite 2 einer Kategorie verlinkte Produkt als unverlinkt oder zu tief zählt. Ein Befund dazu höchstens `hypothesis`.
- **`pages[]` ohne `link_depth`** (vor dem 02.10.2026): `click_depth` ist dann allein über Links gezählt. Eine nur als `/collections/<c>/products/<h>` verlinkte Produktadresse steht einen Klick zu tief; an einem echten Shop ergab das 262 statt 75 Produkte auf Tiefe 4 oder tiefer.
  - Ein Befund zu `tec.click-depth` aus so einem Snapshot höchstens `hypothesis`.
  - Stammt der Ausgangswert einer Maßnahme aus so einem Snapshot, vergleicht der Folgelauf mit `link_depth`, nicht mit `click_depth`; sonst misst er eine Verbesserung, die nur aus der Zählweise kommt.

Zahlen:

- **Die Zahl kommt aus dem Index, nicht aus einer eigenen Abfrage.** Nennt die Tabelle einen Index-Block, dessen `count` übernehmen.
- Grundgesamtheit der Kopfdaten- und Auszeichnungskriterien ist `findings_index.canonical_pages`: indexierbare, selbstkanonische Seiten, jede Adresse einmal, ohne Folgeseiten einer Liste.
- Eine eigene `jq`-Zählung über `.pages` zählt Produktadressen im Collection-Kontext und Weiterleitungen doppelt; an einem echten Shop lag sie beim Zwölffachen.

**Legt die Tabelle eine Einordnung fest, gilt sie.** Sie steht dort, wo zwei Läufe sonst verschieden urteilen würden. Ohne festgelegte Einordnung gelten die Regeln unter Befund-Schema.

| ID | Kernfrage | Prüfung | Quelle | Feste Einordnung |
|---|---|---|---|---|
| `tec.indexability` | 1 | Seiten der GSC-Stichprobe, die der Crawl als indexierbar führt und Google ausschließt; Anteil nicht indexierbarer Seiten | `gsc.json > index_sample`, `summary.share_not_indexable` | Googles eigene Antwort ist `confirmed`; leere Stichprobe heißt `not_measurable` |
| `tec.robots` | 2 | gesperrte wichtige Pfade, gesperrte Startseite, Sitemap-Fehler, Sitemap fehlt oder steht mehrfach in der robots.txt | `robots.disallow_rules`, `summary.home_blocked_by_robots`, `robots.sitemap_errors`, `robots.sitemaps` | eine mehrfach gelistete Sitemap ist `gering` |
| `tec.orphans` | 2 | Seiten aus der Sitemap ohne interne Verlinkung | `findings_index.orphans` | `summary.hit_url_limit` auf `true`: `not_measurable` |
| `tec.redirect-chains` | 2 | längste Weiterleitungskette | `summary.longest_redirect_chain` | mehr als ein Sprung ist ein Befund, `gering` |
| `tec.status-codes` | 3 | 4xx und 5xx, getrennt nach intern verlinkt und nur aus der Sitemap | `findings_index.errors`, `summary.throttled_pages`, `summary.bot_challenge_pages` | 429 und Bot-Challenge sind kein Zustand des Shops, sondern Datenlage |
| `tec.sold-out-handling` | 3 | ausverkaufte Produkte: Statuscode, `indexable` und Weiterleitung ihrer Produktseite, gezielt je Handle in `pages[]` | `catalog.json > products_sold_out`, `crawl.json > pages[]` | ausverkauft allein ist kein Befund (Regel 7); ein Befund entsteht erst bei einer technischen Folge, etwa 404 oder `noindex` auf einer Produktseite |
| `tec.duplicate-titles` | 4 | Gruppen gleicher Titles über kanonische Seiten | `findings_index.titles.duplicate_groups` | |
| `tec.multiple-canonicals` | 4 | mehr als ein Canonical-Tag auf einer Seite | `findings_index.multiple_canonicals` | |
| `tec.canonical-mismatch` | 5 | Canonical zeigt ohne fachlichen Grund auf eine andere Adresse | `findings_index.canonical_mismatch` | Produktadressen im Collection-Kontext mit Canonical auf die Produktadresse sind gewollt; sie zählen unter `tec.internal-canonical-links`, nicht hier. Folgeseiten mit Canonical auf Seite 1 zählen unter `tec.pagination`, nicht hier |
| `tec.click-depth` | 6 | Produkt- und Kategorieseiten ab Klicktiefe 4, gemessen an der Tiefe des Inhalts | `summary.max_click_depth`, `findings_index.deepest`, `pages[].click_depth` | eine Adresse reicht ihre Tiefe an ihr Canonical-Ziel weiter, Index und Auszählung zählen jeden Inhalt einmal; `link_depth` ist nie die Grundlage. Ohne `link_depth` in `pages[]` (Snapshot vor dem 02.10.2026) höchstens `hypothesis` |
| `tec.internal-canonical-links` | 6 | intern verlinkte Seiten, die auf eine andere Adresse kanonisieren; bei Shopify vor allem `/collections/<x>/products/<y>` | `findings_index.non_canonical_linked` | kein Indexierungsfehler, sondern Crawl-Aufwand: `gering`; `mittel` nur, wenn solche Adressen in `gsc.json > top_pages` Impressionen tragen |
| `tec.parameter-urls` | 7 | indexierbare Parameter-URLs ohne Canonical auf die parameterfreie Variante | `findings_index.parameter_urls` | |
| `tec.pagination` | 7 | paginierte Kategorieseiten: eigenes Canonical je Seite, keine Folgeseite mit Canonical auf Seite 1 | `findings_index.pagination`, dazu `orphans` und `path_prefixes` | Canonical auf Seite 1 ist ein Befund. Null paginierte Adressen bei vielen verwaisten Produktseiten deutet auf "Mehr laden" per JavaScript ohne Links: `hypothesis`, nie mehr |
| `tec.product-schema-coverage` | 8 | Produktseiten ohne `Product`-Auszeichnung | `findings_index.schema_types`, `findings_index.path_prefixes` | `confirmed` erst nach `tec.rendered-check` |
| `tec.product-markup-fields` | 8 | Product-Auszeichnung vollständig: `offers` mit Preis, Währung und Verfügbarkeit, Marke, Kennung (GTIN, MPN oder SKU), Bild, Versand und Rückgabe; mehrere Product-Knoten auf einer Seite | `findings_index.product_markup`, `findings_index.organization_markup` | Versand oder Rückgabe fehlen am Angebot, stehen aber global an der Organization (`with_shipping_service`, `with_return_policy`): erfüllt |
| `tec.rendered-check` | 8 | gerenderte Gegenprobe an drei bis fünf Seiten je betroffenem Seitentyp, bevor fehlende Auszeichnung als Befund gilt (Aufruf unten) | Ausgabe von `render_check.py` | `only_rendered`: die Auszeichnung hängt an JavaScript, der Befund "fehlt" entfällt, ein Hinweis `gering` bleibt. Ohne Gegenprobe trägt kein Befund über fehlende Auszeichnung `confirmed`. Gibt es nichts gegenzuprüfen, `not_applicable` |
| `tec.core-web-vitals` | 9 | LCP, INP und CLS im Feld je Seitentyp, Labor nur als Ersatz ohne Felddaten | `cwv.json` | Schwellen aus `reference/metrics.md` |
| `tec.h1` | 10 | genau eine H1 je kanonischer Seite, "mehrere" und "keine" getrennt | `findings_index.h1` | `gering`, solange keine Wirkung gemessen ist |
| `tec.title-length` | 10 | fehlende und zu lange Titles (Grenze in `titles.too_long.max_chars`) | `findings_index.titles` | `gering` |
| `tec.meta-description` | 10 | fehlende und doppelte Meta-Descriptions | `findings_index.descriptions` | `gering` |
| `tec.hreflang` | 11 | Selbstreferenz, x-default, Ziele erreicht und indexierbar, gegenseitig | `findings_index.hreflang` | nie erreichte Ziele bei `summary.hit_url_limit` auf `true`: `not_measurable` |

**Gerenderte Gegenprobe:** Das Script rendert die Seiten mit derselben Headless Shell wie die Screenshots und schickt das Ergebnis durch denselben Parser wie der Crawl. Höchstens zehn Adressen je Aufruf:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/render_check.py" \
  --crawl reporting/data/<run-id>/crawl.json \
  --url <adresse-1> --url <adresse-2> --url <adresse-3>
```

- Je Adresse ein Urteil: `same`, `only_rendered`, `only_static` oder `render_failed`.
- Zahl der geprüften Seiten und Ergebnis in `value` des Kriteriums schreiben.
- `render_failed` bei allen Adressen: `not_measurable`.

## Arbeitsweise

- Jede Datei einzeln lesen, nichts annehmen.
- **`.pages` nie ohne Filter und Grenze abfragen.** Jede `jq`-Abfrage hat ein `select` und ein `.[0:n]` oder liefert nur Zahlen.
- Muster und Gruppen benennen, je Muster ein bis drei Beispiel-URLs als Beleg, nie die volle Liste.
- Rechnungen und Zähler mitliefern (Anzahl betroffener URLs, Anteil am Gesamt-Crawl aus `summary.url_count`), nie nur das Ergebnis.
- Ist eine Beispielliste im Index bei `cap` abgeschnitten, die echte Anzahl nennen, nicht die Listenlänge.
- Widerspricht der Crawl `gsc.json > index_sample`, gilt Googles eigener Befund als stärkere Evidenz (Kernfrage 1).

## Fachsprache vor dem ersten Befund

Vor dem ersten Befund laden:

```
Skill: ptai-ecom:ecom-language
```

Die Skill legt fest:

- welcher Fachbegriff für welche Sache steht und mit welchem Halbsatz er beim ersten Auftreten erklärt wird,
- welche Laienwörter in keinem Kundendokument stehen,
- die fünf Pflichtelemente eines Befunds.

Einordnung, das am häufigsten fehlende Element:

- Jede Zahl bekommt einen Vergleichswert. Beispiel: 4,7 Prozent gegen 41 Prozent in der nächsten Funnel-Stufe.
- Belegte Bänder mit Quelle und Abrufdatum: `reference/metrics.md`.
- Kein Band vorhanden: gegen den eigenen Datensatz vergleichen und vermerken, dass keine Benchmark existiert.
- Nie eine Schwelle erfinden.

## Befund-Schema

Fünf Felder je Befund, ohne Beleg kein Befund:

| Feld | Inhalt | Typ |
|---|---|---|
| `statement` | was der Fall ist | deutscher Satz |
| `evidence` | Quellfeld im Snapshot (`datei.json > pfad`) oder URL | Text |
| `effect` | worauf es wirkt | deutscher Satz |
| `confidence` | `confirmed`, `plausible` oder `hypothesis` | Enum |
| `effort` | `small`, `medium` oder `large` | Enum |

`evidence` nennt die Datei beim Namen (`crawl.json`, `gsc.json` oder `cwv.json`) und den Pfad darin, mehrere Quellen mit Semikolon getrennt. Jeder Befund braucht mindestens einen solchen Verweis.

## Ausgabe

1. Schreibe `reporting/runs/<run-id>/findings/seo-technical.json`.
2. Fehlt der Ordner `reporting/runs/<run-id>/findings/`, beim Schreiben anlegen.
3. Nur die Datei dieses Laufs überschreiben, nie den Ordner eines anderen Laufs.

```json
{
  "discipline": "seo_technical",
  "run_id": "<run-id>",
  "generated_at": "2026-10-01T09:00:00+00:00",
  "blocked_questions": [],
  "criteria_version": "2026-09-27",
  "criteria": [
    {"id": "tec.h1", "result": "violated", "value": "<Zahl mit Grundgesamtheit>",
     "finding_id": "TEC-03"},
    {"id": "tec.robots", "result": "passed", "value": "<Zahl mit Grundgesamtheit>"},
    {"id": "tec.hreflang", "result": "not_applicable", "reason": "<ein Satz>"}
  ],
  "findings": [
    {
      "id": "TEC-01",
      "statement": "37 Produktbilder sind ohne Alt-Text",
      "metrics": [
        {"label": "<was gemessen wurde>", "value": "<Wert>", "context": "<Zeitraum oder Grundgesamtheit>"}
      ],
      "explanation": "<was der Fachbegriff bedeutet und wie gemessen wurde, zwei bis vier Saetze, steht im Report zwischen Titel und Tabelle>",
      "benchmark": "<die Einordnung: gegen welches Band, welchen internen Vergleich, oder der Satz, dass es keine Benchmark gibt>",
      "evidence": "crawl.json > summary.images_without_alt; crawl.json > summary.max_click_depth",
      "effect": "Bild-Zugänglichkeit und Crawl-Effizienz auf umsatzrelevanten Seiten.",
      "why": "<warum das ein Problem ist, in der Sprache eines Geschäftsführers>",
      "fix": "<der konkrete Eingriff und wo er passiert>",
      "severity": "hoch",
      "confidence": "confirmed",
      "effort": "small"
    }
  ]
}
```

- **`criteria` ist keine zweite Befundliste.** Je Kriterium der Kriterienliste genau ein Eintrag, auch bei `passed`; keine ID doppelt, keine fehlend. Ein `violated` verweist über `finding_id` auf seinen Befund in `findings`; nur `findings` werden Maßnahmen, `criteria` nie. Mehrere Kriterien dürfen auf denselben Befund verweisen, wenn es derselbe Mangel ist. `value` enthält Zahl und Grundgesamtheit wie ein `metrics`-Eintrag, `reason` den Grund bei `not_measurable` und `not_applicable`. Beide Felder können im Kundendokument erscheinen: deutsch, ohne Dateinamen.

### Portal-Felder

Vertrag: `${CLAUDE_PLUGIN_ROOT}/reference/finding-format.md`. Vor dem ersten Befund lesen; bei Abweichung gilt der Vertrag, nicht diese Zusammenfassung. Im vollen Audit je Befund:

- `facts`: immer `{"kind": "effect", "text": ...}`. `{"kind": "cause", "text": ...}` nur bei belegter Ursache. Keine weiteren Einträge, auch kein `now`, denn die Handlung ist die eine Maßnahme zum Befund. Jeder Text ein vollständiger Satz, höchstens 160 Zeichen.
- `evidence_text`: der Beleg als ein Satz für den Kunden, mit den tragenden Zahlen, zum Beispiel "318 von 1.204 Produktseiten haben keinen internen Link aus einer Kategorieseite." Kein Pfad, der gehört in `evidence`. Phase 3 übernimmt den Satz in die Maßnahme.
- `url`: die betroffene Seite im Shop, nur `https`. Entfällt, wenn der Befund den ganzen Shop betrifft.
- `proof`: Beleg aus Bausteinen. Eine Kennzahl als `{"type": "metric", "ref": <Index in metrics>}`, nie ein zweites Mal ausgeschrieben; keine Zahl der Aussage in anderer Rundung wiederholen. Typisch hier: `rows` für betroffene Seiten mit Statuscode oder Canonical, `pairs` für Weiterleitungen von und nach.
- `decision`: nur bei zwei echten, verschiedenen Wegen, mit `recommended` und `reason`. Phase 3 macht die empfohlene Option zur Maßnahme, das Portal zeigt die andere als Geprüfte Alternative.

**Keine Bilder.** Bild-Aufträge (`capture`) schreiben nur die Analysen Conversion, Content und Vertrauen, weil nur sie Screenshots lesen. Beleg hier: Kennzahl, Tabelle, Verteilung oder Liste.

### explanation und benchmark

- `explanation`: was der Fachbegriff bedeutet und wie gemessen wurde, zwei bis vier Sätze. Steht im Report zwischen Titel und Zahlentabelle. Keine Zahlen wiederholen, die stehen in `metrics`.
- `benchmark`: ob die Zahl gut oder schlecht ist. Die erste passende Form nehmen:
  1. Band aus `reference/metrics.md` mit Quelle und Abrufdatum,
  2. Vergleich im eigenen Datensatz (Nachbarstufe, Vorjahresmonat, Rest des Sortiments),
  3. der Satz, dass es für diese Kennzahl keine belastbare Benchmark gibt.
- Nie eine Schwelle erfinden.

### Regeln je Feld

1. **`statement`**: nur die Aussage als Satz, keine Messung, höchstens 90 Zeichen. Beispiel: „Drei Monate ohne jede Kaufmessung in Analytics". Zahlen stehen in `metrics`, weil der Report `statement` als Überschrift setzt.
2. **`metrics`**: jede Zahl mit Bezugsgröße, sonst ist sie keine Kennzahl.
   - `label`: was gemessen wurde.
   - `value`: Wert im deutschen Format.
   - `context`: Bezug (Zeitraum, Grundgesamtheit, Vergleichswert).
   - Zwei bis fünf Einträge. Ohne Zahlenreihe bleibt die Liste leer.
3. **`why`**: was der Zustand den Shop kostet und warum sich die Behebung lohnt, nicht was gemessen wurde. Ein bis zwei Sätze für einen Geschäftsführer, ohne Fachjargon. Ist es kein Problem, steht dort: „kein Handlungsbedarf, die Prüfung ist dokumentiert".
4. **`fix`**: welcher Eingriff an welcher Stelle nötig ist. Nie „optimieren" oder „prüfen". Ist der Eingriff unbekannt, die Frage notieren, die vorher zu klären ist.
5. **`id`**: Format `TEC-<laufende Nummer, zweistellig>`, also `TEC-01`, `TEC-02` usw. in Listenreihenfolge. Maßnahmen verweisen über die ID auf ihren Befund.
6. **`severity`**: genau einer der drei Werte.

   | Wert | Wann |
   |---|---|
   | `hoch` | kostet heute Geld oder macht andere Zahlen im Report unbrauchbar |
   | `mittel` | messbarer Verlust an Sichtbarkeit, Conversion oder Datenqualität, aber nicht akut |
   | `gering` | Hygiene, heute ohne messbaren Verlust |

   - Schweregrad ist nicht Priorität. Die Reihenfolge entsteht später zusätzlich aus dem Aufwand.
   - `confidence: "hypothesis"` ist nie `hoch`.
   - Ohne messbaren Verlust nie `mittel`.
7. **Betriebszustand ist kein Mangel.** Ausverkauft, saisonal ausgelistet, bewusst nicht beworben, ein nicht bespielter Kanal: von außen sehen solche Entscheidungen wie Defekte aus, und der fachliche Grund ist unbekannt.
   - Prüffrage: Kann der Zustand aus einer normalen Entscheidung folgen? Dann ist er Kontext. Er darf als `metrics`-Zeile unter einem anderen Befund stehen, wird aber kein eigener Befund und nie `hoch`.
   - Befund wird er erst mit einem gemessenen Schaden. Den Befund bildet die Teilmenge mit dem Schaden, nicht der Zustand:

     | So nicht | So |
     |---|---|
     | 1.000 Produkte sind nicht kaufbar | 100 nicht kaufbare Produkte lagen im selben Zeitraum in Warenkörben |
     | 412 Produkte haben keine Bewertung | die 12 umsatzstärksten Produkte haben keine Bewertung |
     | Kein Konto bei Plattform X | (kein Befund, das ist eine Entscheidung) |

   - Der Schaden muss aus den vorhandenen Daten kommen. Ist keiner belegbar, bleibt der Zustand Kontext.
8. **Kundeneinordnung aus `reporting/context.json`.** Liegt die Datei vor, steht sie im Prompt. Jeder Eintrag ist eine Kundenaussage zu einem früheren Befund: Grund hinter einem Zustand, laufendes Vorhaben oder bewusste Entscheidung.
   - Einen Befund, den ein Eintrag erklärt, nicht erneut stellen: streichen oder auf die Teilmenge einengen, die der Eintrag nicht erklärt.
   - Widerspricht ein Eintrag deinen Zahlen, gelten die Zahlen, und der Widerspruch steht im Befund ("laut Kundenangabe X, gemessen ist aber Y").
   - Was nicht in der Datei steht, ist unbekannt.

### Sprache im Kundendokument

Die Sätze gehen wörtlich in das Kundendokument. Ein Wort je Sache, keine Begriffe aus der Werkzeugwelt:

| Gegenstand | Das Wort | Nicht |
|---|---|---|
| die erfassten Seiten | Seiten im Shop, geöffnet und geprüft | gecrawlte Seiten, URLs, Adressen |
| die eingefrorenen Zahlen | Baseline | Nullpunkt, Ausgangswerte, Startwerte |
| die Kennzahl je Bestellung | Bestellwert | Warenkorbwert |
| fremde Skripte | Drittanbieter-Dienste | Fremdtechnik, Skripte fremder Anbieter |
| der nächste Lauf | der spätere Report | Folgereport |

- Dateinamen und Feldpfade nur in `evidence`, damit ein Mensch nachrechnen kann. Nie in `statement`, `effect`, `why`, `fix`, `facts`, `evidence_text`, den Texten im `proof` oder einem `metrics`-Eintrag.
- Alle Felder außer `evidence` auf Deutsch mit echten Umlauten (ä, ö, ü, ß, nie ae, oe, ue, ss).
- Keine Gedankenstriche in Halbgeviert- oder Geviertlänge.

### blocked_questions

Eine Kernfrage, die mangels Eingabe offen bleibt, gehört in `blocked_questions`, nicht in `findings`. Ein Befund beschreibt einen Zustand im Shop, eine fehlende Eingabedatei einen fehlenden Zugang; vermischt entstehen Backlog-Einträge mit erfundenem Aufwand.

```json
  "blocked_questions": [
    {
      "question": "Kanalanteile über die Zeit",
      "missing_input": "ga4.json",
      "reason": "Datei nicht im Lauf vorhanden, Quelle steht in state.json auf failed"
    }
  ]
```

- `blocked_questions` ist immer vorhanden, auch leer.
- Keine Felder `confidence`, `effort` oder `effect`.
- Der Orchestrator zeigt die Liste an Gate B und leitet höchstens eine Maßnahme je fehlender Eingabe ab, nie eine je Frage.
