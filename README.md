<p>
  <a href="https://path-to-ai.com">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-reversed.svg">
      <img src="assets/brand/logo.svg" alt="Path to AI" width="220">
    </picture>
  </a>
</p>

# ptai-ecom-toolkit

**Audit, Report und Theme-Migration für Shopify-Shops, direkt in Claude Code.**

Elf Analyse-Agents werten Shopify, Google Analytics, Search Console, Google Ads und die AI-Suche gemeinsam aus und machen daraus Maßnahmen, die du direkt umsetzen kannst.

Wenn du für SEO oder Google Ads Agenturen bezahlst, bist du pro Disziplin schnell bei mehreren tausend Euro im Monat. Zurück kommen oft Reports voller Zahlen, und was du daraus tun sollst, musst du dir selbst überlegen.

„Was mache ich denn mit den Zahlen?“ Diese Frage hatte ich nach fast jedem Agentur-Report. Die Zahlen lagen in fünf Tools, und was als Nächstes zu tun war, stand in keinem davon.

Die Daten deines Shops liegen in Shopify, Google Analytics, Search Console und Google Ads, und jedes Tool zeigt seinen Ausschnitt. Was daraus folgt, sagt dir keines davon.

### Warum ich das gebaut habe

Mit Dienstleistern habe ich als E-Commerce-Verantwortlicher immer dasselbe erlebt. Reports kamen, Ideen nicht, und die Zahlen musste ich mir aus fünf Tools selbst zusammensuchen. Das Toolkit macht das, was ich damals von ihnen erwartet hätte.

### So funktioniert es

1. **Installieren:** zwei Befehle in Claude Code, kostenlos, deine Daten bleiben bei dir.
2. **Wählen, was du brauchst:** den Audit mit den Zugängen zu deinem Shop, den ersten Check nur mit der Adresse deines Shops oder den Wechsel auf ein neues Theme.
3. **Entscheiden:** Zu jeder Maßnahme steht, woraus sie folgt, und umgesetzt wird, was du freigibst. Ein neues Theme veröffentlichst immer du.

### Was du bekommst

**Elf Disziplinen, eine Liste**
SEO, AI-Suche, Google Ads, Conversion, Content, Wettbewerb und Pflichtangaben prüft je ein eigener Agent. Ihre Befunde landen in einer gemeinsamen Liste, sortiert nach Wirkung. Jede Maßnahme trägt den Beleg, damit du sie nachvollziehen kannst.

**Erster Check ohne Zugänge**
Du willst wissen, wo dein Shop steht, bevor du jemandem Zugänge gibst? `audit-light` braucht nur die Adresse deines Shops. Es zeigt dir, wie er bei Google und in ChatGPT gefunden wird, was auf dem Weg bis zur Zahlungsauswahl stört und ob Impressum, AGB und Versandangaben vorhanden sind. Das Ergebnis bekommst du als PDF.

**Neues Theme, dieselben Funktionen**
Wenn dein Theme seit Jahren kein Update gesehen hat, bringt dich das Toolkit auf ein aktuelles. Es erfasst vorher jede App, jeden Tracking-Tag und jede Anpassung, damit nach dem Wechsel noch alles da ist, was vorher lief. Gearbeitet wird in einem unveröffentlichten Theme, live geht es erst, wenn du es veröffentlichst.

### Für wen es ist

- E-Commerce-Verantwortliche, die zu jeder Zahl wissen wollen, was zu tun ist
- Founder und Geschäftsführer einer Shopify-Brand, bei denen niemand das Gesamtbild hält
- Investoren mit D2C-Portfolio, die mit den Zugängen einer Brand den Stand aus den echten Daten sehen wollen
- Teams, die ihr Theme auf ein aktuelles wechseln wollen

Nur für Shopify. Wer keine Zugänge geben kann, startet mit dem ersten Check über die Adresse des Shops.

Zieh deinen ersten Audit noch heute: kostenlos, lokal in Claude Code, mit zwei Befehlen installiert (siehe [Installation](#installation)). Fragen und Feedback gerne an mich auf [LinkedIn](https://www.linkedin.com/in/yves-schleich/).

## Was drin ist

### Einrichten

| Skill | Funktion |
|---|---|
| `ptai-ecom:setup` | Richtet das Plugin ein: einmal je Rechner die Schlüssel für PageSpeed, DataForSEO und die GEO-Abfragen, danach je Shop die Zugänge zu Shopify, GA4 und Search Console. Zeigt vorher, was schon eingerichtet ist und was fehlt. |

### Audit und Report

| Skill | Funktion |
|---|---|
| `ptai-ecom:audit` | Vollständiger Audit mit den Zugängen des Shops: Umsatz, Traffic, SEO, AI-Suche, Google Ads, Conversion und Vertrauen. Ergebnis ist eine nach Wirkung sortierte Maßnahmenliste und ein PDF. |
| `ptai-ecom:audit-light` | Audit allein aus der Shop-URL, ohne Zugänge, als PDF: Auffindbarkeit bei Google und in der AI-Suche, Kaufprozess, Pflichtangaben, Sortiment und Wettbewerb. |
| `ptai-ecom:report` | Monatlicher Report als PDF mit Umsatz, Traffic, SEO, Ladezeiten und AI-Sichtbarkeit im Vergleich zum Vormonat, mit den Maßnahmen daraus. |
| `ptai-ecom:pulse` | Wöchentlicher Überblick über die wichtigsten Kennzahlen im Vergleich zur Vorwoche, mit Kommentar nur bei Auffälligkeiten. |

### Datenquellen

Audit und Report holen ihre Daten über diese Skills. Einzeln werden sie nur aufgerufen, wenn genau eine Quelle gebraucht wird. Die fünf DataForSEO-Skills kosten je Abfrage Geld; die Obergrenze steht in der Config.

| Skill | Quelle | Ergebnis |
|---|---|---|
| `ptai-ecom:pull-shopify` | Shopify | Umsatz, Bestellungen, Warenkorbwert, Top-Produkte, Sessions, Bestand, Neu- und Bestandskunden |
| `ptai-ecom:pull-shopify-catalog` | Shopify | Pflegestand der Produkte: SEO-Titel und -Beschreibungen, Bilder mit Alt-Text, Preise, Kollektionen |
| `ptai-ecom:pull-shopify-tech` | Shopify und Crawl | Theme, eingebundene Tools und Skripte, Sprachen, Märkte, Zahlungsarten |
| `ptai-ecom:pull-ga4` | Google Analytics 4 | Traffic-Quellen, Landingpages, Abbrüche im Kaufprozess |
| `ptai-ecom:pull-gsc` | Google Search Console | Suchbegriffe und Seiten je Tag, Sitemaps, Stichprobe zur Indexierung |
| `ptai-ecom:pull-cwv` | PageSpeed Insights | Core Web Vitals der wichtigsten Seitentypen mit Verlauf |
| `ptai-ecom:pull-ads` | Google Ads | Ausgaben, ROAS, verpasste Einblendungen mit Grund, Suchbegriffe ohne Umsatz |
| `ptai-ecom:pull-klaviyo` | Klaviyo | Flows, Kampagnen mit Betreff und Text, Listen, Segmente, Formulare |
| `ptai-ecom:pull-dfs-rankings` | DataForSEO | Rankings und Sichtbarkeit im Vergleich zum Wettbewerb |
| `ptai-ecom:pull-dfs-competitors` | DataForSEO | Wettbewerber zu den Kategorie-Begriffen, optional deren Begriffe ohne eigenes Ranking |
| `ptai-ecom:pull-dfs-keywords` | DataForSEO | Suchvolumen, Wettbewerb und Klickpreis der Produkt- und Kategoriebegriffe |
| `ptai-ecom:pull-dfs-shopping` | DataForSEO | Präsenz bei Google Shopping und Preise des Wettbewerbs |
| `ptai-ecom:pull-dfs-backlinks` | DataForSEO | Verlinkende Seiten, Stärke und Qualität des Linkprofils im Vergleich zum Wettbewerb |
| `ptai-ecom:check-geo` | ChatGPT, Perplexity, Google AI | Vorkommen der Marke in Antworten der AI-Suchen und Zugriff ihrer Crawler |

### Prüfungen von außen

Diese Skills brauchen keine Zugänge.

| Skill | Funktion |
|---|---|
| `ptai-ecom:crawl-site` | Crawlt den Shop: Fehlerseiten, Weiterleitungen, nicht indexierbare Seiten, Klicktiefe, strukturierte Daten. |
| `ptai-ecom:capture-screens` | Screenshots aller Seitentypen auf Desktop und Mobil sowie des Kaufprozesses bis zur Zahlungsauswahl. |
| `ptai-ecom:lens-purchase-path` | Prüft den Kaufprozess von der Produktseite bis zur Zahlungsauswahl, ohne eine Bestellung auszulösen. |
| `ptai-ecom:lens-trust` | Prüft Impressum, Widerruf, AGB, Datenschutz, Preis- und Versandangaben, Bewertungen und Siegel auf Vorhandensein und Auffindbarkeit. Keine juristische Prüfung. |
| `ptai-ecom:lens-assortment` | Prüft Filter, Varianten, Produkttexte, Bilder, Empfehlungen und den Umgang mit ausverkauften Artikeln. |

### Theme-Migration

Überführt ein bestehendes Shopify-Theme (Vintage oder Online Store 2.0) in ein aktuelles 2.0-Theme, zum Beispiel Horizon. `theme-migration` führt durch alle Phasen; die übrigen Skills sind auch einzeln nutzbar. Geschrieben wird nur in ein unveröffentlichtes Theme. Veröffentlicht wird von Hand, nie durch eine Skill.

| Skill | Funktion |
|---|---|
| `ptai-ecom:theme-migration` | Führt durch die Phasen Setup, Sicherung, Bestandsaufnahme, Zuordnung, Neubau, Upload, Prüfung, Abgleich, Abnahme, Launch und Nachsorge. Hält den Stand und die Freigaben fest. |
| `ptai-ecom:snapshot-theme` | Sichert ein Theme vollständig mit einem Manifest aller Dateien. |
| `ptai-ecom:inventory-theme` | Erfasst Theme-Typ, genutzte Templates, Anpassungen gegenüber dem Original, Funktionen je Seitentyp, Metafelder, Übersetzungen und SEO-Ausgabe. |
| `ptai-ecom:inventory-apps` | Erfasst alle Apps und Fremddienste mit Einbindungsweg, Tracking je Messziel und Consent-Verhalten. Kennzeichnet, was einen Theme-Wechsel nicht übersteht. |
| `ptai-ecom:compare-themes` | Misst die Gestaltung des Shops und vergleicht zwei Themes mit Bildpaaren, Stilwerten und SEO-Ausgabe. |
| `ptai-ecom:map-theme` | Erstellt die Zuordnung vom alten zum neuen Theme: Templates, Sections, Einstellungen, Gestaltung, Funktionen. |
| `ptai-ecom:build-theme` | Erzeugt das neue Theme aus Sicherung und Zuordnung in einem eigenen Repo, mit Prüfung durch Theme Check. |
| `ptai-ecom:upload-theme` | Lädt das Theme in ein unveröffentlichtes Theme hoch und prüft jede Datei nach dem Upload. |
| `ptai-ecom:verify-theme` | Prüft den Entwurf gegen das Live-Theme: Struktur, Inhalt, SEO, Gestaltung, Funktionen, Apps und Tracking, Ladezeit, Barrierefreiheit, Sprachen. Erstellt danach die Testrunde. |
| `ptai-ecom:sync-live-theme` | Zeigt Änderungen im Live-Shop seit der Sicherung und welche davon ins neue Theme übernommen werden müssen. |

### Hilfs-Skills

| Skill | Funktion |
|---|---|
| `ptai-ecom:ecom-language` | Einheitliche Fachsprache für Audit, Report und Analyse-Agents; jeder Fachbegriff wird beim ersten Auftreten erklärt. |
| `ptai-ecom:match-feedback` | Gleicht eine Liste mit Änderungswünschen mit den Maßnahmen aus dem Audit ab und ordnet jeden Wunsch zu. |
| `ptai-ecom:test-round` | Erstellt eine Testrunde vor einem Launch: Testanleitung und Prüfpunkte für das Team. |

Der Audit nutzt elf Analyse-Agents, je einen für eine Disziplin:
`audit-data-quality` (Messqualität), `audit-commerce` (Umsatz, Warenkorb, Wiederkäufer),
`audit-traffic` (Kanäle und Landingpages), `audit-seo-technical` (technisches SEO),
`audit-seo-content` (SEO-Inhalte), `audit-geo` (AI-Suche), `audit-sea` (Google Ads),
`audit-conversion` (Kaufprozess und Conversion), `audit-content-brand` (Content und Marke),
`audit-competition` (Wettbewerb) und `audit-trust` (Vertrauen und Pflichtangaben). Der Audit
startet sie selbst.

## Voraussetzungen

- Claude Code mit Plugin-Unterstützung.
- `python3` ab 3.10 mit `google-auth` und `requests` (`pip3 install --user google-auth requests`).
- `jq`, `curl` und `git`.
- Node.js ab 22 (für `audit-light` und die Shopify CLI).
- Shopify CLI (`npm install -g @shopify/cli@latest`).
- Headless-Browser für PDFs und Screenshots: bevorzugt die Headless Shell von Playwright (`npx playwright install chromium-headless-shell`), alternativ Google Chrome oder Chromium.
- Für die Browser-Skripte der Theme-Migration: `uv` (startet Playwright ohne eigene Installation).

## Installation

Das Plugin heißt `ptai-ecom`:

```text
/plugin marketplace add yves-s/ptai-ecom-toolkit
/plugin install ptai-ecom@ptai-ecom
```

Die Skills stehen danach als `/ptai-ecom:setup`, `/ptai-ecom:audit` usw. zur Verfügung. Aktualisieren mit `/plugin marketplace update ptai-ecom`.

## Setup in zwei Teilen

**Teil 1, einmal je Rechner.** `/ptai-ecom:setup` legt `~/.config/ptai-ecom/.env` mit den Rechten `600` an und fragt die Schlüssel ab: PageSpeed, DataForSEO und die GEO-Schlüssel. Google Ads braucht keinen eigenen Schlüssel, nur die freigeschaltete API im Cloud-Projekt. Dazu kommen sechs optionale Einstellungen:

| Einstellung | Vorgabe | Wofür |
|---|---|---|
| `PTAI_ACCOUNTS_ROOT` | `~/ptai-ecom/accounts` | Ordner mit einem Unterordner je Kunde, darin `entity.md`, Screenshots und Deliverables |
| `PTAI_OPERATOR_NAME` | `Dienstleister` | Name des Betreibers im Maßnahmenkatalog und im Audit; nur wenn gesetzt, steht er auch auf der letzten Seite von Audit, Report und `audit-light` |
| `PTAI_OPERATOR_CONTACT` | keine | Ansprechpartner auf der letzten Seite von Audit, Report und `audit-light` |
| `PTAI_OPERATOR_EMAIL` | keine | Mailadresse auf der letzten Seite von Audit, Report und `audit-light` |
| `PTAI_OPERATOR_BOOKING_URL` | keine | Terminlink mit `https://` auf der letzten Seite von Audit, Report und `audit-light` |
| `PTAI_CLOSING_FILE` | keine | Pfad zu einer HTML-Datei mit eigener letzter Seite; ersetzt die Seite aus den Einstellungen darüber |

Die letzte Seite zeigt je gesetztem und gültigem Wert eine Zeile. Ist kein Wert gesetzt, endet jedes Dokument mit der Herkunftszeile. Der Aufbau einer eigenen letzten Seite steht unter "Eigene Marke".

**Teil 2, je Shop.** Im Workspace des Shops schreibt das Setup `reporting/config.json`, legt das Dienstkonto für GA4 und Search Console unter `secrets/` ab und erstellt aus `reference/access.md`, Teil B, die Liste der noch fehlenden Zugänge zum Versand an den Shop. `scripts/check_env.sh` prüft Rechner und Workspace, ohne etwas zu ändern.

Für die Theme-Migration kommt im selben Workspace der Block `theme_migration` in `reporting/config.json` dazu, und es braucht Schreibzugriff auf Themes. Beides beschreibt `reference/theme-migration/access-write.md`.

## Einstufung der Quellen

| Stufe | Quelle | Ohne sie fehlt |
|---|---|---|
| Pflicht | Shopify | Handel, Katalog, Conversion und Messung |
| Pflicht | Google Analytics 4 | Traffic, Conversion und Messung, dazu die Datenqualitäts-Analyse, die im Report vorne steht |
| Pflicht | Google Search Console | SEO Suche, dazu die Keyword-Liste für DataForSEO |
| Empfohlen | DataForSEO | SEO-Sichtbarkeit, Wettbewerb und Shopping-Präsenz |
| Empfohlen | PageSpeed-Key | Core Web Vitals, der Block Technik bleibt leer |
| Empfohlen | GEO-Keys | GEO-Sichtbarkeit per API. Es bleibt der Browser-Weg mit Login in jedem Lauf |
| Optional | Google Ads | SEA. Betrifft nur Shops mit Suchanzeigen, und Google muss das Cloud-Projekt erst für echte Konten freigeben |

Eine fehlende Quelle bricht keinen Lauf ab; sie steht im Dokument als nicht verfügbar, mit Grund. Jeder bezahlte DataForSEO-Aufruf wird mit Kosten in `reporting/dfs-ledger.jsonl` protokolliert.

## Datenablage

```text
reporting/
  config.json                     Marke, IDs, Quellen-Schalter. Keine Secrets.
  data/<run-id>/<source>.json     Snapshots eines Laufs
  runs/<run-id>/                  state.json, source-status.md, findings/, screens.json
  baseline/01/                    baseline.json und baseline.md, blockweise eingefroren
  measures.json, measures.md      Maßnahmen-Backlog über alle Läufe
  dfs-ledger.jsonl                eine Zeile je bezahltem DataForSEO-Aufruf
migration/                        nur bei einer Theme-Migration
  snapshots/                      Sicherungen mit manifest.json
  inventory/                      Bestandsaufnahme, Apps, Tracking, Gestaltung
  mapping/                        Zuordnung alt zu neu und Entscheidungen
  sync/                           Abgleiche mit dem Live-Shop
```

Formeln, Schwellen und Benchmarks stehen in `reference/metrics.md`.

## Was nicht passiert

- **Kein Schreiben in Shop-Systeme**, mit einer Ausnahme: `upload-theme` schreibt in ein unveröffentlichtes Theme. Keine Skill veröffentlicht ein Theme.
- **Keine Secrets in Git.** `.env` und `secrets/` sind ignoriert, das Setup prüft das.
- **Keine Datenbank, keine Infrastruktur.** Die Historie liegt als Dateien unter `reporting/`.

## Eigene Marke

PDFs und Reports nutzen das Erscheinungsbild von Path to AI: Logo, Farben und Schriften unter `assets/brand/`. Audit, Report und `audit-light` enden mit derselben letzten Seite. Ohne weitere Einstellung stehen dort die Kontaktdaten des Betreibers aus den Einstellungen oben. Path to AI steht dort nur als Herkunft des Plugins, nicht als Absender (`scripts/audit/closing.py`, für `audit-light` `scripts/report/sales/report-pdf-full.mjs`). Für eine eigene Marke werden das Logo und `assets/brand/report.css` ersetzt.

Eine eigene letzte Seite ist eine HTML-Datei außerhalb des Plugins, auf die `PTAI_CLOSING_FILE` zeigt. Das Plugin setzt ihren Inhalt unverändert als letzte Seite ein, in der Web-Fassung des Audits mittig unter dem Inhalt. Anforderungen an die Datei:

- genau ein `<section>`-Element auf oberster Ebene, darin optional ein `<style>`-Element,
- nur Selektoren unter der eigenen Klasse dieses Elements,
- alle Bilder und Schriften als `data:`-URIs,
- eine volle A4-Seite im Hochformat: `break-before: page; width: 210mm; height: 297mm; box-sizing: border-box`,
- keine der Zeichenfolgen `<!-- CLOSING:start -->`, `<!-- CLOSING:end -->` und `__CLOSING__`; das Plugin markiert damit die letzte Seite, und Audit und Report lehnen eine Datei ab, die sie enthält.

Fehlt die Datei oder ist sie leer oder nicht lesbar, wird die Seite aus den Einstellungen verwendet, und eine Zeile auf stderr nennt den Grund.

## Tests

`bash scripts/run_tests.sh` startet die Python- und die JavaScript-Tests. Kein Test greift auf das Netz zu.

## Lizenz

MIT, siehe `LICENSE`. Ausgenommen sind der Name Path to AI und das Logo. Die Schriften stehen unter der SIL Open Font License 1.1, die Lizenztexte liegen in `assets/brand/fonts/LICENSES/`.
