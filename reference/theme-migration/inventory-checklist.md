# Bestandsaufnahme vor dem Umbau

Stand 05.10.2026. Gilt für die Phasen 1 und 2. Alles hier ist nach dem ersten Handgriff am Theme
verloren und nicht mehr rekonstruierbar: ein Audit lässt sich in zwei Wochen nachholen, ein Bild des
alten Themes nicht. Deshalb läuft diese Aufnahme vollständig, bevor gebaut wird.

Jede Abfrage an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit, nie aus dem
Gedächtnis.

## Was beim Theme-Wechsel mitkommt und was nicht

Die Aufnahme braucht nur zu halten, was am Theme hängt. Was im Admin liegt, bleibt ohnehin.

| Bleibt, weil es im Admin liegt | Geht verloren, weil es im Theme liegt |
|---|---|
| Produkte, Kollektionen, Menüs, Seiten, Blog, Dateien | `config/settings_data.json` mit allen Einstellungen des Theme-Editors |
| Metafelder und Metaobjekte (die Daten) | Section- und Block-Inhalte der JSON-Templates und Section-Groups |
| Template-Zuweisungen (`templateSuffix` am Objekt) | die Template-Dateien selbst, damit jedes Layout |
| Redirects, Filter (Search & Discovery) | Locale-Texte und die Theme-Übersetzungen |
| Web Pixels, Checkout, Functions, App-Proxies | eigener Code, `robots.txt.liquid`, eingefügter Tracking-Code |
| Store-Übersetzungen (Produkte, Seiten, Menüs) | App-Blöcke und App-Embeds |

Ein offizielles Werkzeug, das Einstellungen zwischen zwei verschiedenen Themes überträgt, gibt es
nicht. Quelle: https://help.shopify.com/en/manual/online-store/themes/adding-themes

## Die Checkliste

| # | Prüfpunkt | Warum | Wie | Ergebnis |
|---|---|---|---|---|
| 1 | Live-Theme vollständig sichern | Rückfallebene, Quelle des Generators, einziger Beleg des Vorher-Zustands | `snapshot-theme`, Dateiliste gegen eine reine Metadatenliste geprüft | `migration/snapshots/<date>-<theme-id>/` mit `manifest.json` |
| 2 | Freie Theme-Plätze | 20 Themes je Store, auf Plus 100. Ein Duplikat oder Upload braucht einen Platz | Theme-Liste lesen | Warnung bei voller Liste, bevor jemand aufräumt |
| 3 | Original des Quell-Themes | ohne Original ist keine Anpassung bestimmbar | unverändertes Theme im Store, ZIP vom Team, Entwicklungs-Store | `snapshot-theme --original` oder Vermerk "nicht bestimmbar" |
| 4 | Typ und Basis | Vintage und 2.0 brauchen verschiedene Wege | JSON-Templates, Section-Groups, `@app` in der Main-Section; `theme_info` in `config/settings_schema.json` | `architecture` in der Konfiguration |
| 5 | Templates und Nutzung | eine Template-Datei beweist nur, dass ein Layout existiert | `templateSuffix` aller Produkte, Kollektionen, Seiten, Blogs, Artikel | `templates.json` |
| 6 | Anpassungen gegen das Original | nur so ist klar, was nachgebaut werden muss | Diff des Code-Teils, siehe `customizations.md` | `customizations.json` |
| 7 | Funktionen je Seitentyp | eine Funktion des Basis-Themes taucht in keiner Anpassungsliste auf und fehlt trotzdem nach dem Wechsel | jede lebende Seite durchgehen: was kann eine Besucherin dort tun, mit Quelle | `functions.json`, später die Prüfliste |
| 8 | Metafelder und Metaobjekte | die Daten bleiben, ihre Ausgabe geht verloren | Definitionen, belegte Felder, Lesestellen im Code und in den JSON-Templates | `metafields.json` |
| 9 | Übersetzungen | Theme-Übersetzungen hängen am Theme | siehe `translations.md` | `translations.json` |
| 10 | SEO-Ausgabe je Seitentyp | das neue Theme darf nichts davon still verlieren | `crawl-site` plus gerendertes HTML der Beispielseiten, siehe `seo-parity.md` | `seo.json` |
| 11 | URL-Inventar und Schutzliste | Grundlage jeder Paritätsprüfung, auch bei gleichen URLs | Sitemap, Crawl, Search Console mit maximalem Zeitraum, bestehende Redirects exportieren | Teil von `seo.json` |
| 12 | Apps und Tracking | jede Einbindungsart überlebt den Wechsel anders | siehe `apps-and-tracking.md` | `apps.json`, `tracking.json` |
| 13 | Gestaltung | Messlatte für "sieht aus wie vorher" | `compare-themes --measure` am gerenderten Shop | `design.json` |
| 14 | Kundenkonten | klassische Konten sind Theme-Templates und abgekündigt | Admin, Einstellungen, Kundenkonten; `templates/customers/*` | Vermerk in `risks.json` |
| 15 | Checkout | gehört nicht zum Theme, wird nur aufgenommen | Admin, Checkout-Einstellungen | Vermerk, kein Umbau |
| 16 | Plattform-Fristen | Skript-Tags, Scripts, Additional Scripts, Kundenkonten | siehe `platform-deadlines.md` | `risks.json` |
| 17 | Vergleichswerte | ohne Vorher-Wert ist kein Verlust nach dem Launch zuzuordnen | `pull-gsc`, `pull-ga4`, `pull-cwv`, Rankings, Conversion je Seitentyp und Gerät | Snapshots unter `reporting/data/` |
| 18 | Bilder des alten Themes | Referenz für den Abgleich von Gestaltung und Funktion | `capture-screens`, Bildpaare über `compare-themes` | im Kundenordner, nie im Repo |
| 19 | Beispielseiten | jeder Vergleich braucht dieselben Seiten | je lebendem Template eine URL, mit Search Console die meistbesuchte | `pages.json` |

## Regeln, die aus Fehlern kommen

**Sicherung**

- Nach ID arbeiten, nie nach Namen. Namen ändern sich im Admin, und ein Entwicklungs-Theme kann wie
  das Live-Theme heißen.
- Die Paginierung über Theme-Dateien mit Inhalt kann zu früh enden, ohne Fehler, meist am
  alphabetischen Ende der Liste. Ein Knoten kann aus der Verbindung fallen, sobald ein
  Inhalts-Fragment angefordert ist. Vollständig ist eine Sicherung erst, wenn die Liste der Inhalte
  eine zweite, reine Metadatenliste deckt; Fehlendes wird gezielt über `filenames` nachgefordert.
- Der Body einer Theme-Datei kommt als Text, Base64 oder URL. Wer nur Text behandelt, verliert still
  die Binärdateien.
- `checksumMd5` taugt für JSON-Dateien nicht als Abgleich: Shopify serialisiert JSON neu und setzt
  vor `settings_data.json` einen Kommentarkopf. JSON wird normalisiert verglichen.
- Die Sicherung bleibt ein eigener, unveränderter Commit. Nie formatieren, nie im selben Commit
  weiterarbeiten.
- Das Original zuerst sichern und dem Team sagen, welches Theme nicht gelöscht werden darf. Löschen
  ist bei Shopify endgültig, und wer Platz schafft, kennt die Themes oft nicht.
- Welches der weiteren Themes im Store ein Arbeitsstand ist, entscheidet ein Abgleich der
  Prüfsummen von `layout/theme.liquid` und `config/settings_data.json`, nicht der Name.
- Das Live-Theme ändert sich während der Aufnahme weiter. Vor jedem Befund, der an einer einzelnen
  Datei hängt, das `updatedAt` je Datei gegen den Sicherungszeitpunkt prüfen; geänderte Dateien
  kommen als neue datierte Sicherung dazu, die erste bleibt unverändert.

**Templates**

- Die Zahl der lebenden Templates ergibt sich aus den Zuweisungen, nie aus der Dateiliste. Templates
  ohne Objekt entfallen im Neubau, außer das Team will sie behalten.
- Zuweisungen auf ein Suffix ohne Datei gesondert ausweisen. Ein Objekt, dessen Suffix im neuen
  Theme fehlt, rendert sehr wahrscheinlich das Standard-Template; belegt ist das Verhalten beim
  Löschen eines Templates, nicht ausdrücklich beim Theme-Wechsel.
- Markt-Varianten (`*.context.<market>.json`) gesondert führen.

**Metafelder**

- Die Definition sagt nicht, wie der Schlüssel der Werte geschrieben ist. Ein per API geschriebener
  Wert kann eine andere Schreibweise tragen.
- Liquid löst Metafeld-Schlüssel case-sensitiv auf, die Admin-API nicht. Ob ein Feld im Shop
  ankommt, zeigt nur die ausgelieferte Seite.
- Undefinierte Metafelder existieren trotzdem, meist aus einer Middleware. Eine Stichprobe zeigt
  Namensräume, eine Fehlanzeige trägt nur nach einem Vollscan.
- Lesestellen stehen auch in den JSON-Templates (`raw_content`, dynamische Quellen), nicht nur in
  Liquid. Hier wird der Inhalts-Teil ausnahmsweise durchsucht.
- Was von außen geschrieben wird, behält im Neubau seinen Schlüssel, sonst bricht die Schreibseite.
- Gepflegte Felder ohne Ausgabe sind fertiges Material für Filter und Detailangaben im neuen Theme.

**URLs und SEO**

- Nur die Sitemap reicht nicht: sie lässt Seiten aus, die nur verlinkt sind, und misst keinen Wert.
- Search Console mit maximalem Zeitraum ziehen, sonst fallen saisonale Seiten aus der Schutzliste.
- Bestehende Redirects exportieren. Eine gelöschte Weiterleitungskette bricht Verlinkungen, die
  seit Jahren funktionieren.

**Gestaltung**

- Gestaltung wird am gerenderten Shop gemessen, nie aus `settings_data.json` gelesen. Die Datei
  enthält tote Einstellungen aus früheren Versionen, und wirksame Werte, die dort fehlen, sind
  Schema-Standards des Herstellers.
- Schriften je Element berechnet messen. Shopify liefert für abgekündigte Bibliotheksschriften einen
  Ersatz aus; die Einstellung nennt dann eine Schrift, die niemand sieht. Theme Check meldet sie als
  `DeprecatedFontsOnSettingsData`.

**Vergleichswerte**

- Messwerte aus echten Besuchen und Laborwerte getrennt halten. Feldwerte rollieren über 28 Tage.
- Die Werte direkt vor dem Launch werden noch einmal gezogen (`launch-checklist.md`). Die Werte aus
  dieser Phase sind Ausgangsstand für die Planung, nicht die Vergleichsbasis nach dem Launch.

## Quellen

- https://help.shopify.com/en/manual/online-store/themes/adding-themes
- https://help.shopify.com/en/manual/online-store/themes/theme-structure/templates
- https://shopify.dev/docs/storefronts/themes/architecture/config/settings-data-json
- https://shopify.dev/docs/storefronts/themes/architecture/templates/json-templates
- https://shopify.dev/docs/storefronts/themes/os20
- https://shopify.dev/docs/storefronts/themes/architecture/limits
- https://moz.com/blog/website-migration-guide (Agentur- und Fachquelle)
