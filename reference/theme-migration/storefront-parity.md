# Gleichstand der Storefront

Stand 08.10.2026. Gilt für Phase 6, bevor ein Entwurf zur Testfreigabe geht. Die Prüfer Gestaltung und
Funktion aus `verify-checklist.md` arbeiten diese Liste Zeile für Zeile ab, zusätzlich zu ihren
Bildpaaren je Template.

Bei der ersten Migration von Broadcast auf Horizon kamen nach der Testfreigabe rund 30 Korrekturen
dazu, verteilt über zwei Wochen und bis in die Tage nach dem Launch. Keine davon hatte die Prüfung
gefunden. Gefunden haben sie das Team in der Testrunde oder der Betreiber beim Durchklicken. Fast alle
waren Abweichungen in Schrift, Maß oder Verhalten eines einzelnen Elements, das auf der Seite
vorhanden war und deshalb im Bildpaar der ganzen Seite nicht auffiel. Deshalb prüft diese Liste je
Element, nicht je Seite.

## So wird geprüft

- Jede Zeile am Entwurf und live, Desktop in Chromium bei 1440 px und iPhone in WebKit (402 × 750),
  mit `preview_theme_id` und Theme-Nachweis wie in `verify-checklist.md`.
- **Gemessen wird am gerenderten Element** (`getComputedStyle` und `getBoundingClientRect`), nie aus
  Einstellungen oder Stylesheets gelesen. Schriften: `document.fonts` und die tatsächlich geladene
  Schrift, weil Shopify abgekündigte Schriften still ersetzt und Regeln im alten Stylesheet oft kein
  Element treffen.
- Je Zeile ein Bildpaar, ausgeschnitten auf das Element, und selbst angesehen.
- Ergebnis je Zeile: `ok` (Abweichung unter 0,5 px, gleiche Schrift, gleiche Farbe), `Befund`,
  `entschieden` (steht in `decisions.json`) oder `nicht geprüft` mit Grund.
- Die Tabelle mit dem Ergebnis je Zeile steht in `findings.md` des Prüfers. Ein Befund nennt die
  Zeilennummer (`SP-nn`) in seiner Beschreibung.
- Zeilen, die das Quell-Theme nicht hat, sind `n/a` mit einem Satz Grund, nicht gestrichen.

## Header und Navigation

| Nr | Element | Was messen | Prüfer | Fehlerbild aus der ersten Migration |
|---|---|---|---|---|
| SP-01 | Ankündigungsleiste | Art (statisch, Slider, Laufschrift), Höhe, Tempo, Pause bei Hover, ob die Texte verlinken | Gestaltung | Live eine Laufschrift von 45 px, im Entwurf eine statische Leiste. Horizons Laufschrift ist in der Header-Gruppe nicht erlaubt, eigene Section nötig. Die Links des alten Themes waren nur ein Seitenfilter |
| SP-02 | Header | Höhe, Position des Logos, Größe und Strichstärke der Icons | Gestaltung | Horizon zentriert das Logo fest, live stand es über 100 px rechts der Mitte. Icons kleiner und dünner als live |
| SP-03 | Menü, erste Ebene | Schriftfamilie, Größe, Gewicht, Laufweite, Unterstrich bei Hover und aktiv | Gestaltung | Menüschrift dünner und ohne Laufweite |
| SP-04 | Mega-Menü am Rechner, jedes Panel | Schrift der Links und Gruppentitel, Spaltenpositionen, Kampagnenbilder bis zum Rand, Kampagnentitel (Größe, Gewicht, Großschreibung, Laufweite), Zeile unter der Kampagne, Panelhöhe, Schatten, Einblenden | Gestaltung | Links 16 px Regular statt 14 px Light mit 1,1 px Laufweite, Kampagnentitel 23 statt 25,65 px, Bilder eingerückt, Schatten am Panel, die Zeile unter einer Kampagne fehlte |
| SP-05 | Menüpunkte ohne Ziel | Klick auf einen Punkt mit URL `#`: kein Sprung, keine Änderung der Adresse, kein Farbwechsel bei Hover | Funktion | Das alte Theme schluckte den Klick, Horizon hängte `#` an und sprang nach oben. Erst nach dem Launch gefunden |
| SP-06 | Menü am Handy | Logik der Ebenen (eigene Ebene je Gruppe, Akkordeon, flach), Breite der Schublade, Zeilenhöhe, Pfeil, Kopf der Ebene | Gestaltung | Horizon zeigt die dritte Ebene flach, 23 gleichrangige Einträge unter einem Punkt |
| SP-07 | Umschaltpunkt Menü | Fensterbreite, ab der die Handy-Navigation erscheint | Gestaltung | Live ab etwa 1270 px, Horizon viel schmaler. Als Entscheidung vorlegen |

## Produktseite

| Nr | Element | Was messen | Prüfer | Fehlerbild aus der ersten Migration |
|---|---|---|---|---|
| SP-08 | Produkttitel | geladene Schrift, Größe, Zeilenhöhe, Desktop und Handy | Gestaltung | In den Einstellungen stand eine abgekündigte Schrift, ausgeliefert wurde ein Ersatz |
| SP-09 | Preis | Größe, Gewicht, Farbe; Aktionspreis mit Farbe, Streichpreis und Rabatt-Badge | Gestaltung | Preis in Fließtextgröße 16 px Regular statt 19 px Light, Aktionspreis nicht rot, Badge fehlte |
| SP-10 | Sterne | mit oder ohne Anzahl, Form des leeren Sterns, Abstand zum Preis | Gestaltung | Anzahl angezeigt, live nicht |
| SP-11 | Steuer- und Versandhinweis | Größe Desktop und Handy | Gestaltung | 16 px statt 10 px, am Handy statt 8 px. Die Einstellung ging beim Upload still verloren |
| SP-12 | Variantenauswahl, je Optionstyp | **zuerst alle Optionsnamen des Shops per Admin-API auszählen**, dann je Option: Darstellung (Kreis, Kasten, Liste), Position von Bezeichnung und gewähltem Wert, Linien, Farbkreis mit Ring, Strich und Sale-Punkt | Gestaltung | Nur „Größe“ bekam Kreise, „Länge“ bei über tausend Ketten blieb bei Horizons breiten Kästen. Bezeichnung und Auswahl untereinander statt nebeneinander |
| SP-13 | Zustände einer Variante | ausverkauft gewählt und nicht gewählt: lesbar, durchgestrichen | Gestaltung | Gewählte ausverkaufte Größe weiß auf weiß |
| SP-14 | Schnellkauf-Fenster | SP-08 bis SP-13 im Fenster, dazu nichts überlappt den Preis | Gestaltung | Linien der Variantenauswahl lagen über dem Preis. Erst nach dem Launch gefunden |
| SP-15 | Zahlungslogos | Anzahl und Auswahl wie live | Gestaltung | Horizon zeigt alle freigeschalteten Zahlarten, 16 statt 6 |
| SP-16 | App-Blöcke im Kaufbereich | auf einem Produkt ohne Daten der App: leere Kästen und Linien | Gestaltung | Leerer grauer Kasten einer Bundle-App, live genauso. Ausblenden statt übernehmen |
| SP-17 | Brotkrumen | Kategorie im Pfad nach Einstieg über eine Kategorie, eine Zeile, Kürzung mit drei Punkten, Großschreibung | Funktion | Kategorie fehlte, weil Horizons Karten die kanonische Produkt-URL verlinken. Lange Titel brachen zweizeilig um |

## Kategorie und Produktkarten

| Nr | Element | Was messen | Prüfer | Fehlerbild aus der ersten Migration |
|---|---|---|---|---|
| SP-18 | Produktkarte, in jedem Kontext | Einzug des Textes, Abstand Bild zu Sternen zu Titel, Schrift von Titel und Preis; auf weißem und auf farbigem Grund; in Kategorie, Suche, Startseite, Empfehlungen, zuletzt angesehen, Looks, Blog | Gestaltung | Text bündig statt 20 px eingerückt (Handy 12 px). Titel und Preis nicht in der Light-Schrift von live |
| SP-19 | Schärfe der Kartenbilder | geladene Bildbreite (`currentSrc`) bei Pixeldichte 1 und 2 | Gestaltung | Horizon rechnete `sizes` mit 180 px Mindestbreite, an Monitoren ohne Retina kam 240 statt 460 px. Vom Team gemeldet |
| SP-20 | Produkte je Seite | auf mehreren Kategorien zählen, ausverkaufte eingeschlossen, am gerenderten Shop, nicht aus Einstellungen oder Inventar | Funktion | Das Inventar behauptete, ausverkaufte Produkte würden ausgeblendet. Gezählt waren es 20 je Seite mit ausverkauften |
| SP-21 | Filter | Aufbau je Breite (Leiste, Schublade, Seitenleiste), Kästchen, Zeilenabstand, Button, Farbkreise am Farbfilter, Abdunklung im Bild sichtbar | Gestaltung | Horizons Seitenleiste statt Schublade, Farben nur als Text, Abdunklung berechnet, aber vom Consent-Tool unsichtbar gemacht |
| SP-22 | Buttons zu Unterkategorien | Breite, Abstand, Zahl der sichtbaren Buttons am Handy | Gestaltung | Am Handy nur der erste Button zu sehen, riesige Abstände |
| SP-23 | Sections unter dem Raster | Verhalten (Blättern, Wischen, Pfeile) **und** jeder Text in der Karte | Gestaltung | Erst nur das Blättern angeglichen; Titel, Untertitel und Link waren weiter anders |
| SP-24 | Shop the Look | Aufbau (Bild, Raster daneben), Hotspots nur mit gesetzten Positionen, keine Platzhalterkarten | Gestaltung | Gespeicherte Positionen waren Schema-Defaults, vier Punkte lagen übereinander in der Bildmitte |

## Suche und Warenkorb

| Nr | Element | Was messen | Prüfer | Fehlerbild aus der ersten Migration |
|---|---|---|---|---|
| SP-25 | Suchergebnisse | Seitenzahlen oder Nachladen wie live, Treffer je Seite, ob die Adresse sich beim Nachladen ändert | Funktion | Horizon lud endlos nach und schrieb jede Seite in die Adresse, Tracking zählte jede als Seitenaufruf. Erst nach dem Launch gefunden |
| SP-26 | Warenkorb | Überschrift (Text, Schrift), Zeilenpreis am Handy neben der Menge, Verhalten nach dem Hinzufügen | Gestaltung, Funktion | Überschrift „Dein Warenkorb“ statt „WARENKORB“, Zeilenpreis am Handy änderte sich nicht sichtbar mit der Menge |

## Über alle Seiten

| Nr | Element | Was messen | Prüfer | Fehlerbild aus der ersten Migration |
|---|---|---|---|---|
| SP-27 | Überschriften je Rolle | geladene Schrift, Größe, Zeilenhöhe von H1 bis H6 und der Einleitung der Startseite | Gestaltung | Einleitung in Didot aus einer Regel des alten Stylesheets, die live kein Element traf; gerendert war live Bodoni Moda |
| SP-28 | Status- und Button-Texte | Texte für ausverkauft, mehr lesen, Warenkorb, aus den Locale-Dateien beider Themes | Gestaltung | „Ausverkauft“ statt „Bald wieder da“, „Mehr lesen …“ statt „Mehr erfahren“ |
| SP-29 | Dialoge und Schubladen | Abdunklung im Bild sichtbar, bei eingebundenem Consent-Tool | Gestaltung | Das Consent-Tool setzt global `dialog::backdrop { opacity: 0 }` |

## Was nicht hier steht

Im selben Zeitraum kamen weitere Korrekturen dazu, die andere Listen abdecken:

- SEO-Ausgabe (H1, Meta-Description, strukturierte Daten, hreflang, `robots.txt`): `seo-parity.md`
- Tracking und Apps: `apps-and-tracking.md`
- Änderungen des Teams im Live-Theme während des Umbaus: `sync-live-theme`

## Pflege

- Findet eine Testrunde oder der Betreiber nach der Freigabe eine Abweichung, die hier keine Zeile
  hat, kommt sie als neue Zeile dazu: Element, was messen, Fehlerbild.
- Eine Zeile beschreibt ein Element, das jedes Theme hat, nicht den Sonderfall eines Kunden.
- Findet eine Zeile bei einer Migration nichts, bleibt sie trotzdem. Die Liste wird länger, nicht
  kürzer.
