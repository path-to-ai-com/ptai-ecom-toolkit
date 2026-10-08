# Theme-Migration: Referenzen

Stand 05.10.2026. Diese Dateien halten die Checklisten, Plattform-Fakten und Regeln, nach denen die
elf Skills der Theme-Migration arbeiten. Die Skills lesen sie an der Stelle, an der sie gebraucht
werden; hier steht, welche Datei wofür da ist.

Ziel einer Migration ist ein bestehendes Shopify-Theme auf einem aktuellen Online-Store-2.0-Theme,
ohne dass etwas verloren geht: kein lebendes Template, keine Funktion, keine App-Einbindung, kein
Tracking, keine SEO-Ausgabe und keine Änderung, die während des Umbaus im Live-Shop passiert ist.
Bezugsziel ist die Horizon-Familie von Shopify, die Regeln gelten für jedes Quell-Theme (Vintage
oder 2.0) und jedes 2.0-Ziel-Theme.

## Grundregel für jede Datei hier

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**, lesend wie
schreibend: Admin-GraphQL, Flags der CLI, Liquid, Schemas, Block-Typen. Nie aus dem Gedächtnis. Eine
Migration, die aus Erinnerung baut, baut den Stand der Trainingsdaten und ist danach selbst wieder ein
Fall für die nächste Migration. Steht in einer Datei hier eine Abfrage oder ein Befehl, ist das die
Richtung, nicht der geprüfte Wortlaut: vor dem Einsatz gegen die aktuelle Doku und das Schema prüfen.

## Die Dateien

| Datei | Wofür | Gelesen von |
|---|---|---|
| `inventory-checklist.md` | was vor dem Umbau festgehalten wird, warum und wie: Sicherung, Templates, Anpassungen, Funktionen, Metafelder, URLs, Gestaltung, Vergleichswerte | `snapshot-theme`, `inventory-theme`, `compare-themes` |
| `apps-and-tracking.md` | die Quellen für das App-Inventar, das Datenmodell, was einen Theme-Wechsel überlebt, Tracking je Messziel, Consent, Neu-Anbindung | `inventory-apps`, `map-theme`, `verify-theme` |
| `customizations.md` | Anpassungen gegen das Original: Diff-Regeln, die vier Klassen, Wirkung messen, Entscheidung je Funktion, stille Abweichungen im Ziel-Theme, Verzeichnis der Eingriffe | `inventory-theme`, `map-theme`, `build-theme` |
| `translations.md` | was am Theme hängt und was am Shop, Translate & Adapt, Langify, Theme-Übersetzungen je Theme-ID, Registrieren mit Digest | `inventory-theme`, `upload-theme`, `verify-theme` |
| `seo-parity.md` | die SEO-Ausgabe alt gegen neu je Seitentyp und Sprache, Schutzliste, bekannte Lücken von Horizon, was `launch-check` automatisch prüft, das Horizon-Grundpaket | `inventory-theme`, `build-theme`, `verify-theme`, `launch-check`, `theme-migration` |
| `verify-checklist.md` | die Prüfer, ihre Regeln, Schwerestufen, Barrierefreiheit nach WCAG 2.2 und BFSG, Performance | `verify-theme` |
| `storefront-parity.md` | Gleichstand je Element vor der Testfreigabe: Header, Menü, Kaufbereich, Variantenauswahl, Karten, Filter, Suche, Warenkorb, gemessen am gerenderten Shop | `verify-theme` |
| `change-freeze.md` | was zwischen den beiden Abgleichen eingefroren ist und was frei bleibt | `sync-live-theme`, `theme-migration` |
| `launch-checklist.md` | Zeitpunkt, Go/No-Go, Rollouts, Prüfungen am Launch-Tag | `theme-migration`, `launch-check` |
| `rollback.md` | wann und wie zurückgeschaltet wird, und was ein Rückfall nicht zurückdreht | `theme-migration`, `launch-check` |
| `post-launch.md` | Prüfplan nach dem Launch und die Rückrichtung der Editor-Änderungen ins Repo | `theme-migration`, `snapshot-theme` |
| `platform-deadlines.md` | Fristen der Plattform mit Stand und Quelle: Skript-Tags, Shopify Scripts, Additional Scripts, Kundenkonten | `inventory-apps`, `theme-migration` |
| `access-write.md` | Schreibzugang ins Theme: Konto mit Themes-Recht, Admin-Weg mit Scopes, die offene Frage der Ausnahme | `theme-migration`, `upload-theme` |

Dazu kommen drei Ablagen, die eigene Bausteine des Toolkits pflegen:

| Ablage | Wofür |
|---|---|
| `hosts.json` | Zuordnung von Host zu Anbieter und Zweck für das App-Inventar. Ein Host, der dort fehlt, bleibt `unknown` und wird aufgelöst, bevor Gate G1 durch ist |
| `horizon-base/` | das Horizon-Grundpaket: vier SEO-Snippets mit Platzhalter-Präfix `beispiel-`, die `theme.horizon_base install` beim Bau ins Ziel-Repo kopiert. Beschreibung und Eingriffe in `seo-parity.md` |
| `mappings/` | fertige Zuordnungen für verbreitete Quell-Themes auf ein Ziel-Theme, `<source>__<target>.json`, nur Section- und Einstellungsnamen der öffentlichen Themes. Wie eine Bibliothek entsteht und geprüft wird, steht in `mappings/README.md` |

## Phasen und Gates im Überblick

| Phase | Inhalt | Skill | Gate |
|---|---|---|---|
| 0 Setup | Konfiguration, Lese- und Schreibweg, freie Theme-Plätze, Ziel-Theme und Version, Fristen | `theme-migration` | Zugang und Ziel-Theme stehen |
| 1 Sicherung | Live-Theme vollständig sichern, Original als Vergleichsbasis | `snapshot-theme` | |
| 2 Bestandsaufnahme | Theme, Apps, Gestaltung, SEO-Ausgabe, Vergleichswerte | `inventory-theme`, `inventory-apps`, `compare-themes`, `crawl-site`, Pulls | **G1** Entscheidung je App, Funktion, Template |
| 3 Zuordnung | Mapping alt zu neu, Gestaltung auf Einstellungen | `map-theme` | **G2** Zuordnung freigegeben |
| 4 Neubau | Ziel-Repo, Generator, Theme Check, Limits | `build-theme` | **G3** erster Upload freigegeben |
| 5 Upload | unveröffentlichtes Theme, Zurücklesen, Übersetzungen | `upload-theme` | |
| 6 Prüfung | Prüfer je Disziplin, Befunde zurück in 3 bis 5 | `verify-theme` | |
| 7 Abgleich I | Live-Änderungen seit der Sicherung | `sync-live-theme` | Entscheidung je Änderung |
| 8 Abnahme | Testrunde mit dem Team | `verify-theme`, `test-round` | **G4** Abnahme |
| 9 Launch | Änderungsstopp, Abgleich II, Vergleichswerte, Go/No-Go, Veröffentlichen durch einen Menschen | `sync-live-theme`, `launch-check`, `theme-migration` | **G5** Go/No-Go |
| 10 Nachsorge | Prüfplan, Rückrichtung ins Repo | `theme-migration` | |

**Veröffentlichen ist immer ein Mensch.** Keine Skill ruft `themePublish` oder `shopify theme
publish` auf, und keine schreibt in ein Theme mit einer anderen Rolle als `UNPUBLISHED`.
