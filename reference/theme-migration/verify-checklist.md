# Prüfung des Entwurfs

Stand 08.10.2026. Gilt für Phase 6 und für die Vorbereitung der Abnahme in Phase 8. Ein Umzug, der
nur den Code betrachtet, sieht erfolgreich aus und ist es nicht: mehrere Risiken eines Theme-Wechsels
fallen ohne jede Fehlermeldung aus. Deshalb prüfen mehrere Prüfer je Disziplin, gegen das Live-Theme
und gegen die Bestandsaufnahme.

## Die Prüfer

| Prüfer | Gegenstand | Gegen | Storefront |
|---|---|---|---|
| Struktur | Theme Check, Limits, jede Zuweisung hat ihre Datei, Laufzeitprüfung der JSON-Dateien gegen die Schemas | `templates.json` | nein |
| Inhalt | Texte, Bilder, Links je Beispielseite, Wortzahl | Live-Theme | ja |
| SEO | Crawl des Entwurfs gegen den des Live-Themes, `seo-parity.md` | `seo.json` | ja |
| Gestaltung | Bildpaare Desktop (Chromium) und iPhone (WebKit), Stilwerte; "wie heute" gilt für das ganze Element; die Zeilen Gestaltung aus `storefront-parity.md` | `design.json` | ja |
| Funktion | jede Funktion der Liste ausgeführt: Variantenwahl, Warenkorb, Filter, Suche, Formulare, Sonderfunktionen; die Zeilen Funktion aus `storefront-parity.md` | `functions.json` | ja |
| Apps und Tracking | Mitschnitt Entwurf gegen Live, jede Fremd-Domain da oder bewusst weg, Consent in beiden Zuständen, keine doppelten Events | `apps.json`, `tracking.json` | ja |
| Performance | Lighthouse dreimal, Median, Startseite, Produkt, Kollektion, mit `pb=0` | Vergleichswerte | ja |
| Barrierefreiheit | axe und Lighthouse, dazu die manuelle Liste unten | WCAG 2.2 | ja |
| Sprachen | jede Sprache und jeder Markt-Pfad, Theme-Übersetzungen vorhanden | `translations.json` | ja |

**Höchstens zwei Prüfer gleichzeitig auf der Storefront.** Mehr lösen HTTP 429 und eine
Bot-Abfrage aus; danach fehlen Bilder und Warenkorbtests, und der Bericht sieht vollständig aus.
Prüfer ohne Storefront (Struktur, Code, Admin-API) laufen parallel dazu.

## Regeln für jeden Prüfer

Diese Regeln stehen wörtlich im Auftrag jedes Prüfers.

1. Nur lesen. Nichts im Shop abschicken, keine Bestellung, kein Formular, kein Newsletter.
2. Jede Abfrage an Shopify über die Shopify-Skills des Shopify AI Toolkit, nie aus dem Gedächtnis.
   Skripte der Shopify-Skills mit `OPT_OUT_INSTRUMENTATION=true` aufrufen, damit keine Pfade oder
   Kundendaten in eine Telemetrie gehen.
3. Browser über Playwright (`uv run --quiet --with playwright==1.58.0 python ...`), nie über einen
   installierten Desktop-Browser.
4. Vorschau mit `?preview_theme_id=<id>` und Theme-Nachweis auf jeder Seite (`Shopify.theme.id`). Eine
   Seite ohne passenden Nachweis zählt nicht. Für Messungen `pb=0` anhängen.
5. Consent-Banner über `skills/capture-screens/scripts/consent.py` ablehnen, damit beide Seiten gleich
   aussehen.
6. Einige Sekunden zwischen zwei Seitenaufrufen.
7. Eigenes Unterverzeichnis je Prüfer unter `migration/verify/<date>/<checker>/`.
8. Nichts erfinden. Was nicht prüfbar war, steht als nicht geprüft mit Grund im Ergebnis, nie als
   bestanden.
9. Jede Aussage über den Shop trägt einen Link auf die konkrete Seite, bei einem Unterschied beide
   Links: Entwurf und Live, beide mit `preview_theme_id`.
10. Bereits entschiedene Abweichungen (`decisions.json`) sind kein Befund.

## Befunde

Ein Befund in `migration/verify/<date>/findings.json` trägt Prüfer, Seitentyp, Linkpaar,
Beschreibung, Schwere, Ursache (Mapping, Generator-Regel, eigene Datei, App, Daten) und, bei
Gestaltung, das Bildpaar im Kundenordner.

| Schwere | Bedeutung |
|---|---|
| `blocker` | verhindert die Testfreigabe |
| `before_launch` | muss vor dem Launch behoben sein |
| `after_launch` | darf nach dem Launch folgen, mit Termin |
| `info` | Hinweis ohne Handlung |

**Ein Befund wird an der Ursache behoben**, im Mapping oder in der Generator-Regel, nie nur in der
erzeugten Datei. Danach laufen Neubau, Upload und die betroffenen Prüfer erneut.

## Gestaltung

- WebKit im iPhone-Format ist Pflicht, nicht nur Chromium. Manche Fehler zeigt nur WebKit.
- **Jedes Bildpaar wird angesehen.** Eine Pixel-Differenz allein ist kein Befund, eine fehlende
  Differenz kein Beweis. Unsichtbares (eine berechnete, aber nicht sichtbare Abdunklung) zeigt nur
  das Bild.
- Jedes lebende Template einmal gerendert neben live, nicht nur die beanstandeten.
- "Wie heute" gilt für das ganze Element: Maße, Schrift, Abstände jedes Teils messen.
- **Zusätzlich je Element `storefront-parity.md`, Zeile für Zeile.** Das Bildpaar einer ganzen Seite
  übersieht ein einzelnes Element, das vorhanden, aber anders gesetzt ist. Bei der ersten Migration kamen
  so rund 30 Korrekturen erst nach der Testfreigabe.

## Funktion

- Abgehakt wird gegen `functions.json`, Zeile für Zeile. Eine Liste, die nach dem Bau niemand abhakt,
  findet nichts.
- Grenzfälle in den Testdaten: lange Titel, lange Beschreibungen, viele Varianten, ausverkaufte
  Varianten, Rabatte, Menüs mit drei Ebenen, große Kollektionen mit Paginierung, Video.
- Was nach dem Hinzufügen zum Warenkorb passiert, wie live oder wie entschieden.

## Checkout

Der Checkout wird nicht automatisch getestet: eine Testbestellung ist eine echte Bestellung, wenn
kein Testmodus läuft, und der Testmodus nimmt andere Wege als der Echtbetrieb. Die Szenarien gehen
als Punkte in die Testrunde: je Zahlart und Versandregel einmal, mit Rabattcode und Gutschein,
eingeloggt und als Gast, mobil zuerst, Preis, Steuer und Versand je Markt, Bestätigungsmail,
Weitergabe an angeschlossene Systeme. Testbestellungen werden danach storniert und erstattet, damit
sie die Zahlen nach dem Launch nicht verfälschen.

## Barrierefreiheit

Für Online-Shops in der EU gilt seit 28.06.2025 das Barrierefreiheitsstärkungsgesetz (BFSG), ohne
Übergangsfrist für Shops; ausgenommen sind nur Kleinstunternehmen bei Dienstleistungen. Maßstab ist
WCAG 2.2. Der Theme Store verlangt Lighthouse Accessibility im Schnitt ab 90.

**Automatisch:** axe und Lighthouse je Seitentyp. Diese Werkzeuge finden nur einen Teil der Kriterien.

**Manuell, je Seitentyp:**

- alles per Tastatur bedienbar, sichtbarer Fokus, Fokus-Reihenfolge wie im DOM
- Fokus wird nicht von festen Leisten oder Bannern verdeckt (neu in WCAG 2.2)
- Zielgröße mindestens 24 × 24 px (neu in WCAG 2.2)
- Kontrast 4,5:1 für Text, 3:1 ab 18 pt und für Nicht-Text
- Alt-Text an jedem inhaltlichen Bild
- eindeutige IDs an Eingabefeldern mit `label for`
- Überschriften H1 bis H6 optisch unterscheidbar und in sinnvoller Reihenfolge
- Alternativen zum Ziehen (Slider, Karussell), Hilfe an gleicher Stelle, keine doppelte Eingabe,
  barrierefreie Anmeldung (neu in WCAG 2.2)
- Dialoge und Schubladen: Fokus springt hinein, Escape schließt, Fokus kehrt zurück

Das Ergebnis ist eine Feststellung, keine juristische Bewertung.

## Performance

- Lighthouse je Startseite, Produkt und Kollektion, Desktop und Mobil, mindestens drei Läufe, Median,
  mit `pb=0`.
- Der Theme Store verlangt im Schnitt Performance ab 60 über diese drei Seitentypen. Shopifys
  Speed-Score gewichtet Start 17 %, Produkt 40 %, Kollektion 43 %.
- Grenzwerte im Feld: LCP bis 2,5 s, INP bis 200 ms, CLS bis 0,1 bei p75. INP ist im Labor nicht
  messbar, TBT dient als Ersatz. Filterlastige Kollektionsseiten sind der häufigste INP-Verlierer.
- Theme Inspector for Chrome für die Liquid-Renderzeit, `shopify theme profile` als CLI-Weg.
- Verglichen wird gegen die Vergleichswerte des Live-Themes; Feldwerte des neuen Themes gibt es erst
  28 Tage nach dem Launch (`post-launch.md`).

## Quellen

- https://shopify.dev/docs/storefronts/themes/store/requirements
- https://shopify.dev/docs/storefronts/themes/best-practices/accessibility
- https://shopify.dev/docs/storefronts/themes/best-practices/performance/testing-for-performance
- https://shopify.dev/docs/storefronts/themes/tools/theme-check
- https://shopify.dev/docs/storefronts/themes/tools/theme-inspector
- https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- https://www.ihk.de/koeln/hauptnavigation/recht-steuern/barrierefreiheit-von-webseiten-dienstleistungen-und-produkten-5921172
- https://web.dev/articles/vitals
- https://help.shopify.com/en/manual/checkout-settings/test-orders
