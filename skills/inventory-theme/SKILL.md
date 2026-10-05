---
name: inventory-theme
description: Bestandsaufnahme eines Shopify-Themes vor einem Theme-Wechsel schreiben, aus der Sicherung und dem Shop: Typ und Basis (Vintage oder Online Store 2.0), Templates und ihre tatsächliche Nutzung über die Zuweisungen, Anpassungen gegen das Original in vier Klassen, Funktionsliste je Seitentyp, Metafelder und Metaobjekte samt Lesestellen, Übersetzungen, SEO-Ausgabe je Seitentyp, Kundenkonten und die Beispielseiten für alle Vergleiche. Nutzen bei "Bestandsaufnahme Theme", "welche Templates leben", "was ist am Theme angepasst", "Funktionsliste", "Theme-Inventar", in Phase 2 einer Theme-Migration und vor jedem größeren Umbau ohne Theme-Wechsel. Nicht verwenden für Apps und Tracking (ptai-ecom:inventory-apps), für die Messung der Gestaltung (ptai-ecom:compare-themes) und für die Sicherung selbst (ptai-ecom:snapshot-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# inventory-theme: Bestandsaufnahme des Quell-Themes

Die Liste, gegen die der Neubau arbeitet und gegen die er später geprüft wird. Sie hält fest, was am
Theme individuell ist und was es kann, welche Templates wirklich leben und was das Theme aus dem
Shop liest. Eine Funktion, die das Basis-Theme mitbringt, taucht in keiner Anpassungsliste auf und
fehlt nach dem Wechsel trotzdem; deshalb gehört die Funktionsliste dazu.

Arbeitsverzeichnis ist der Kunden-Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**
(`shopify-plugin:shopify-admin`, `shopify-plugin:shopify-custom-data`, `shopify-plugin:shopify-liquid`),
nie aus dem Gedächtnis, auch für jede lesende Abfrage.

Die Checkliste mit Gründen und Fehlerbildern steht in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/inventory-checklist.md`, die Regeln für Anpassungen in
`customizations.md`, für Übersetzungen in `translations.md`, für die SEO-Ausgabe in `seo-parity.md`,
alle im selben Ordner.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und dem Block `theme_migration`.
- Eine vollständige Sicherung des Live-Themes unter `migration/snapshots/<date>-<theme-id>/`
  (`snapshot-theme`). Ohne sie startet die Skill nicht.
- Für die Anpassungen das Original als zweite Sicherung (`snapshot-theme --original`). Fehlt es, läuft
  alles andere, und die Anpassungen stehen als nicht bestimmbar.
- Lesezugang mit `read_themes`, `read_products`, `read_content`, `read_locales`, `read_markets`, für
  Übersetzungen `read_translations`. Ein fehlender Scope macht den betroffenen Teil zu "nicht lesbar"
  mit Grund, nie zu 0.

## Ablauf

Ergebnisse liegen unter `migration/inventory/`, je JSON-Datei eine `.md`-Ansicht für Menschen mit
demselben Namen. Jeder Teil ist isoliert: scheitert einer, steht er mit Grund als `not_readable`, die
anderen laufen weiter.

1. **Typ und Basis.** Aus der Sicherung: JSON- oder Liquid-Templates, Section-Groups
   (`sections/*-group.json`), `@app` im Schema der Main-Section, `{{ content_for_index }}` in einem
   Vintage-`index.liquid`. Theme-Name und Version aus `theme_info` in `config/settings_schema.json`.
   Ergebnis `os2` oder `vintage`; der Wert gehört nach `theme_migration.source_theme.architecture` in
   der Konfiguration, und die Skill schlägt die Änderung vor, statt sie still zu schreiben.

2. **Templates und Nutzung:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.templates usage \
     --snapshot migration/snapshots/<date>-<theme-id> \
     --out migration/inventory/templates.json
   ```

   Das Modul liest `templateSuffix` aller Produkte, Kollektionen, Seiten, Blogs und Artikel und hält
   je Template-Datei die Zahl der Objekte, die Templates ohne Objekt (`files_without_objects`), die
   Zuweisungen auf Suffixe ohne Datei (`assigned_without_file`) und die Markt-Varianten. **Die Zahl der
   lebenden Templates kommt nur hierher, nie aus der Dateiliste.**

3. **Anpassungen gegen das Original:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations diff \
     --original migration/snapshots/original-<zip-name> \
     --current migration/snapshots/<date>-<theme-id> \
     --out migration/inventory/customizations-candidates.json
   ```

   Nur der Code-Teil, CSS normalisiert. Vorher das Original nach Marken- und Domainspuren des Shops
   und nach Fremd-Skripten durchsuchen und Treffer ausnehmen: Apps schreiben auch in unveröffentlichte
   Themes. Danach jeden Kandidaten einordnen in **Funktion, Gestaltung, App-Rest oder Altlast**, mit
   Datei und Zeilen, Wirkung im Shop, sichtbar genutzt ja oder nein. Ergebnis
   `customizations.json`. **Eine Funktion zählt erst, wenn ihre Wirkung im Live-Shop gemessen ist**:
   jede Anpassung mit sichtbarer Wirkung an einer lebenden Seite im Browser nachprüfen, bevor sie als
   Funktion zählt. Gezählt wird nach der Einordnung, nie vorher.

4. **Funktionsliste je Seitentyp.** Jede lebende Seite (aus Schritt 2) durchgehen: was kann eine
   Besucherin dort tun (Variantenwahl, Warenkorb, Filter, Sortierung, Suche, Formulare, Karussells,
   Sonderfunktionen), mit Quelle (`theme`, `app`, `customization`) und Fundstelle. Auch was nach dem
   Hinzufügen zum Warenkorb passiert. Ergebnis `functions.json`, eine Zeile je Funktion und Seitentyp
   mit `id`, `page_type`, `function`, `source`, `evidence`. Diese Liste ist später die Prüfliste von
   `verify-theme`.

5. **Metafelder und Metaobjekte.** Definitionen je Besitzertyp, Metaobjekt-Definitionen, belegte
   Namensräume (Stichprobe; eine Fehlanzeige nur nach Vollscan), Lesestellen im Code **und in den
   JSON-Templates** (dynamische Quellen, `raw_content`). Die Schreibweise der Schlüssel an der
   ausgelieferten Seite prüfen: Liquid löst case-sensitiv auf, die Admin-API nicht. Verwaiste Felder in
   beide Richtungen markieren. Ergebnis `metafields.json`.

6. **Übersetzungen.** Sprachen und Märkte aus dem Shop (nicht aus `locales/`), Übersetzungs-App,
   Umleitungen im Theme-Code, Schreiber je Sprache, die Theme-Übersetzungen des Live-Themes je
   Theme-Ressourcentyp mit Schlüssel, Ausgangswert und Übersetzung, und die Zahl, die im neuen Theme
   neu registriert werden muss. Ergebnis `translations.json`. Einzelheiten in `translations.md`.

7. **SEO-Ausgabe je Seitentyp.** Crawl des Live-Shops über `crawl-site` in den Daten-Ordner des
   Migrationslaufs:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
     --domain <domain> --out "reporting/data/<date>-migration"
   ```

   Dazu das gerenderte HTML der Beispielseiten im Browser. Je Seitentyp: Title, Meta-Description,
   H1 bis H6, Canonical, Meta-Robots, strukturierte Daten (doppeltes Product-JSON-LD markieren),
   Quelle von hreflang, Ausgabe von `/robots.txt`, Wortzahl je URL. Dazu die Schutzliste aus Sitemap,
   Crawl und Search Console (`pull-gsc`, maximaler Zeitraum) und der Export der bestehenden Redirects.
   Ergebnis `seo.json`.

8. **Kundenkonten** klassisch oder neu (Admin-Einstellung, `templates/customers/*`). Klassische Konten
   kommen mit Frist als Eintrag `customer_accounts` nach `risks.json`. Die Datei wird vor dem Schreiben
   frisch gelesen und nur der eigene Eintrag geändert, weil `inventory-apps` dort ebenfalls schreibt.

9. **Beispielseiten** `pages.json` aus der Template-Nutzung. Bei `page_sample: "auto"` je lebendem
   Template eine URL; liegt ein Search-Console-Snapshot vor, die meistbesuchte, sonst die erste mit
   Inhalt. Dazu je Sprache die Startseite und je Markt-Pfad eine Seite.

   ```json
   {"base_url": "https://beispielshop.example", "pages": [
     {"id": "home", "template": "index", "path": "/", "locale": "de"}]}
   ```

   Alle Vergleiche (`compare-themes`, `inventory-apps`, `verify-theme`) nutzen diese Liste.

10. **Ergebnis melden**, kurz und in Zahlen: Typ und Basis, lebende Templates gegen Template-Dateien,
    Anpassungen je Klasse, Funktionen je Seitentyp, verwaiste Metafelder, neu zu registrierende
    Übersetzungen, Auffälligkeiten der SEO-Ausgabe, offene Teile mit Grund.

## Vintage-Themes

Bei `vintage` zusätzlich: die statischen Sections aus `config/settings_data.json` (`sections`,
`content_for_index`) und die Inhalte, die im Liquid-Code der Templates stecken, je Seitentyp. Diese
Inhalte gehen nicht über eine Einstellung in das neue Theme, sondern über das Mapping, und gehören
deshalb vollständig in die Aufnahme.

## Ergebnis

`migration/inventory/` mit `templates.json`, `customizations.json`, `functions.json`,
`metafields.json`, `translations.json`, `seo.json`, `pages.json` und dem eigenen Teil von `risks.json`,
je mit `.md`-Ansicht. Die Dateien werden im Workspace committet, namentlich gestagt. Bilder gehören nie
in den Workspace, sondern in den Kundenordner.

## Fehlerbilder

- **Keine Sicherung:** nicht starten, `snapshot-theme` anbieten.
- **Original fehlt:** Anpassungen als nicht bestimmbar vermerken, nicht gegen eine vermutete Version
  diffen. Ein Diff gegen die falsche Version macht jede Zeile zur Abweichung.
- **Der Inhalts-Teil wird mitgedifft** (`templates/*.json`, `settings_data.json`, `locales/`,
  `sections/*.json`): tausende Scheinbefunde. Nur der Code-Teil gehört in den Diff.
- **Eine Anpassung wird aus dem Code gelesen statt gemessen:** der Neubau führt dann ein Verhalten
  ein, das es nie gab.
- **Gestaltungswerte aus `settings_data.json`:** die Datei enthält tote Einstellungen. Gestaltung misst
  `compare-themes --measure` am gerenderten Shop.
- **Ein Scope fehlt:** der Teil steht als `not_readable` mit Grund. Bei einer erneuten Anmeldung gilt
  die Union-Regel aus `pull-shopify`.
- **Gedrosselt:** Exit-Code prüfen, warten, erneut. Eine leere Antwort ist nie "keine Daten".
- **Die Sicherung ist älter als einige Tage:** vor Befunden an einzelnen Dateien `sync-live-theme`
  laufen lassen, damit kein Befund an einem überholten Stand hängt.
