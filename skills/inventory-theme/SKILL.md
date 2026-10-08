---
name: inventory-theme
description: Schreibt die Bestandsaufnahme eines Shopify-Themes vor einem Theme-Wechsel, aus der Sicherung und dem Shop: Typ und Basis (Vintage oder Online Store 2.0), Templates und ihre Nutzung laut Zuweisungen, Anpassungen gegen das Original in vier Klassen, Funktionsliste je Seitentyp, Metafelder und Metaobjekte mit Lesestellen, Übersetzungen, SEO-Ausgabe je Seitentyp, Kundenkonten und die Beispielseiten für alle Vergleiche. Nutzen bei "Bestandsaufnahme Theme", "welche Templates leben", "was ist am Theme angepasst", "Funktionsliste", "Theme-Inventar", in Phase 2 einer Theme-Migration und vor jedem größeren Umbau ohne Theme-Wechsel. Nicht verwenden für Apps und Tracking (ptai-ecom:inventory-apps), für die Messung der Gestaltung (ptai-ecom:compare-themes) und für die Sicherung selbst (ptai-ecom:snapshot-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# inventory-theme: Bestandsaufnahme des Quell-Themes

Die Bestandsaufnahme ist die Vorgabe für den Neubau und die Grundlage seiner Prüfung. Sie erfasst:

- was am Theme individuell ist und welche Funktionen es hat
- welche Templates Objekten zugewiesen sind
- was das Theme aus dem Shop liest

Die Funktionsliste ist Pflicht, weil Funktionen des Basis-Themes in keiner Anpassungsliste stehen und
nach dem Wechsel trotzdem fehlen können.

Arbeitsverzeichnis: der Kunden-Workspace.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit**
(`shopify-plugin:shopify-admin`, `shopify-plugin:shopify-custom-data`, `shopify-plugin:shopify-liquid`),
nie aus dem Gedächtnis, auch bei lesenden Abfragen.

Referenzen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`:

- `inventory-checklist.md`: Checkliste mit Gründen und Fehlerbildern
- `customizations.md`: Regeln für Anpassungen
- `translations.md`: Übersetzungen
- `seo-parity.md`: SEO-Ausgabe

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und dem Block `theme_migration`.
- Vollständige Sicherung des Live-Themes unter `migration/snapshots/<date>-<theme-id>/`
  (`snapshot-theme`). Ohne sie startet die Skill nicht.
- Für die Anpassungen das Original als zweite Sicherung (`snapshot-theme --original`). Fehlt es, laufen
  alle anderen Teile, und die Anpassungen sind als nicht bestimmbar markiert.
- Lesezugang mit `read_themes`, `read_products`, `read_content`, `read_locales`, `read_markets`, für
  Übersetzungen `read_translations`. Fehlt ein Scope, ist der betroffene Teil "nicht lesbar" mit Grund,
  nie 0.

## Ablauf

- Ergebnisse unter `migration/inventory/`, zu jeder JSON-Datei eine `.md`-Ansicht mit demselben Namen.
- Jeder Teil läuft isoliert: scheitert einer, steht er mit Grund als `not_readable`, die anderen laufen
  weiter.

1. **Typ und Basis** aus der Sicherung prüfen:
   - JSON- oder Liquid-Templates
   - Section-Groups (`sections/*-group.json`)
   - `@app` im Schema der Main-Section
   - `{{ content_for_index }}` in einem Vintage-`index.liquid`
   - Theme-Name und Version aus `theme_info` in `config/settings_schema.json`

   Ergebnis `os2` oder `vintage`. Der Wert gehört nach `theme_migration.source_theme.architecture`; die
   Skill schlägt die Änderung vor und schreibt sie nicht selbst.

2. **Templates und Nutzung:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.templates usage \
     --snapshot migration/snapshots/<date>-<theme-id> \
     --out migration/inventory/templates.json
   ```

   Das Modul liest `templateSuffix` aller Produkte, Kollektionen, Seiten, Blogs und Artikel und
   speichert:
   - je Template-Datei die Zahl der Objekte
   - Templates ohne Objekt (`files_without_objects`)
   - Zuweisungen auf Suffixe ohne Datei (`assigned_without_file`)
   - Markt-Varianten

   **Die Zahl der zugewiesenen Templates kommt nur aus dieser Datei, nie aus der Dateiliste.**

3. **Anpassungen gegen das Original:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations diff \
     --original migration/snapshots/original-<zip-name> \
     --current migration/snapshots/<date>-<theme-id> \
     --out migration/inventory/customizations-candidates.json
   ```

   1. Nur der Code-Teil, CSS normalisiert.
   2. Vorher das Original nach Marken- und Domainspuren des Shops und nach Fremd-Skripten durchsuchen und
      Treffer ausnehmen; Apps schreiben auch in unveröffentlichte Themes.
   3. Jeden Kandidaten einordnen als **Funktion, Gestaltung, App-Rest oder Altlast**, mit Datei und
      Zeilen, Wirkung im Shop, sichtbar genutzt ja oder nein. Ergebnis `customizations.json`.
   4. **Eine Funktion zählt erst, wenn ihre Wirkung im Live-Shop gemessen ist:** jede Anpassung mit
      sichtbarer Wirkung an einer zugewiesenen Seite im Browser nachprüfen.
   5. Erst nach der Einordnung zählen.

4. **Funktionsliste je Seitentyp.** Jede zugewiesene Seite aus Schritt 2 durchgehen:
   - was eine Besucherin dort tun kann (Variantenwahl, Warenkorb, Filter, Sortierung, Suche, Formulare,
     Karussells, Sonderfunktionen)
   - Quelle (`theme`, `app`, `customization`) und Fundstelle
   - was nach dem Hinzufügen zum Warenkorb passiert

   Ergebnis `functions.json`, eine Zeile je Funktion und Seitentyp mit `id`, `page_type`, `function`,
   `source`, `evidence`. `verify-theme` nutzt diese Liste später als Prüfliste.

5. **Metafelder und Metaobjekte:**
   - Definitionen je Besitzertyp, Metaobjekt-Definitionen
   - belegte Namensräume (Stichprobe; eine Fehlanzeige nur nach Vollscan)
   - Lesestellen im Code **und in den JSON-Templates** (dynamische Quellen, `raw_content`)
   - Schreibweise der Schlüssel an der ausgelieferten Seite prüfen: Liquid löst case-sensitiv auf, die
     Admin-API nicht
   - verwaiste Felder in beide Richtungen markieren

   Ergebnis `metafields.json`.

6. **Übersetzungen:**
   - Sprachen und Märkte aus dem Shop, nicht aus `locales/`
   - Übersetzungs-App, Umleitungen im Theme-Code, Schreiber je Sprache
   - Theme-Übersetzungen des Live-Themes je Theme-Ressourcentyp mit Schlüssel, Ausgangswert und
     Übersetzung
   - Zahl der Übersetzungen, die im neuen Theme neu registriert werden müssen

   Ergebnis `translations.json`. Einzelheiten in `translations.md`.

7. **SEO-Ausgabe je Seitentyp.** Crawl des Live-Shops über `crawl-site` in den Daten-Ordner des
   Migrationslaufs:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
     --domain <domain> --out "reporting/data/<date>-migration"
   ```

   Dazu das gerenderte HTML der Beispielseiten im Browser. Je Seitentyp erfassen:
   - Title, Meta-Description, H1 bis H6, Canonical, Meta-Robots
   - strukturierte Daten (doppeltes Product-JSON-LD markieren)
   - Quelle von hreflang, Ausgabe von `/robots.txt`, Wortzahl je URL

   Dazu die Schutzliste aus Sitemap, Crawl und Search Console (`pull-gsc`, maximaler Zeitraum) und den
   Export der bestehenden Redirects. Ergebnis `seo.json`.

   Daraus entsteht die Prüfliste "Muss nach dem Umbau wieder da sein", je Punkt eine Zeile
   `- [ ] **P01** ...`. Sie ist die Abnahme der SEO-Ausgabe: ihren Pfad als
   `theme_migration.acceptance_checklist` in die Config schreiben, sonst steht `launch-check` mit
   dieser Zeile auf `blocked`. Ein Punkt gilt dort als erledigt, wenn er abgehakt ist, mit Person und
   Datum verschoben (`verschoben von <Name> am <JJJJ-MM-TT>`) oder durch eine bestandene automatische
   Prüfung abgedeckt (`seo-parity.md`, Abschnitt Automatisch im Launch-Check).

8. **Kundenkonten** klassisch oder neu (Admin-Einstellung, `templates/customers/*`). Klassische Konten mit
   Frist als Eintrag `customer_accounts` nach `risks.json`. Die Datei vor dem Schreiben frisch lesen und
   nur den eigenen Eintrag ändern, weil `inventory-apps` dort ebenfalls schreibt.

9. **Beispielseiten** `pages.json` aus der Template-Nutzung:
   - bei `page_sample: "auto"` je zugewiesenem Template eine URL
   - mit Search-Console-Snapshot die meistbesuchte, sonst die erste mit Inhalt
   - dazu je veröffentlichter Sprache jeder Seitentyp einmal und je Markt-Pfad eine Seite; der
     SEO-Vergleich in `launch-check` ist ohne eine Sprache unvollständig und steht dann auf `blocked`.
     `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.seo_parity pages --pages <pages.json> --locales de,en`
     ergänzt die Sprachen (Primärsprache zuerst)

   ```json
   {"base_url": "https://beispielshop.example", "pages": [
     {"id": "home", "template": "index", "path": "/", "locale": "de"}]}
   ```

   Alle Vergleiche (`compare-themes`, `inventory-apps`, `verify-theme`) nutzen diese Liste.

10. **Ergebnis melden**, kurz und in Zahlen: Typ und Basis, zugewiesene Templates gegen Template-Dateien,
    Anpassungen je Klasse, Funktionen je Seitentyp, verwaiste Metafelder, neu zu registrierende
    Übersetzungen, Auffälligkeiten der SEO-Ausgabe, offene Teile mit Grund.

## Vintage-Themes

Bei `vintage` zusätzlich erfassen:

- die statischen Sections aus `config/settings_data.json` (`sections`, `content_for_index`)
- je Seitentyp die Inhalte im Liquid-Code der Templates

Diese Inhalte kommen nicht über eine Einstellung ins neue Theme, sondern über das Mapping, und müssen
deshalb vollständig erfasst sein.

## Ergebnis

- `migration/inventory/` mit `templates.json`, `customizations.json`, `functions.json`,
  `metafields.json`, `translations.json`, `seo.json`, `pages.json` und dem eigenen Teil von `risks.json`,
  je mit `.md`-Ansicht.
- Im Workspace committet, namentlich gestagt.
- Bilder nie im Workspace, sondern im Kundenordner.

## Fehlerbilder

- **Keine Sicherung:** nicht starten, `snapshot-theme` anbieten.
- **Original fehlt:** Anpassungen als nicht bestimmbar vermerken, nicht gegen eine vermutete Version
  diffen. Ein Diff gegen die falsche Version macht jede Zeile zur Abweichung.
- **Inhalts-Teil mitgedifft** (`templates/*.json`, `settings_data.json`, `locales/`, `sections/*.json`):
  tausende Scheinbefunde. Nur den Code-Teil diffen.
- **Anpassung aus dem Code gelesen statt gemessen:** der Neubau führt dann ein Verhalten ein, das es nie
  gab.
- **Gestaltungswerte aus `settings_data.json`:** die Datei enthält ungenutzte Einstellungen. Gestaltung
  misst `compare-themes --measure` am gerenderten Shop.
- **Scope fehlt:** der Teil steht als `not_readable` mit Grund. Bei erneuter Anmeldung gilt die
  Union-Regel aus `pull-shopify`.
- **Gedrosselt:** Exit-Code prüfen, warten, erneut. Eine leere Antwort bedeutet nie "keine Daten".
- **Sicherung älter als einige Tage:** vor Befunden an einzelnen Dateien `sync-live-theme` ausführen,
  damit kein Befund auf einem überholten Stand beruht.
