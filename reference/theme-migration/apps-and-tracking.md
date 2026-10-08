# Apps und Tracking

Stand 05.10.2026. Die teuerste Lücke beim Theme-Wechsel: ein neues Theme bringt keine
App-Einbindung mit. Bewertungen, Suche, Consent, Newsletter-Formulare und ein großer Teil des
Trackings fehlen danach, und ohne Inventar kann niemand sagen, was vorher wo hing.

Jede Abfrage an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit, nie aus dem
Gedächtnis.

## Die Admin-API ist die schwächste Quelle

`appInstallations`, `scriptTags`, `webPixel`, `shopifyFunctions`, `cartTransforms` und
`webhookSubscriptions` zeigen nur, was der eigenen App gehört. Ein leeres Ergebnis dort beweist
nichts. Die Liste aller installierten Apps gibt es nur im Admin.

## Die Quellen, keine reicht allein

Abdeckung je Quelle steht im Ergebnis als `complete`, `partial` oder `not_readable` mit Grund.
"Nicht lesbar" ist nie 0.

| # | Quelle | Was sie zeigt | Grenze |
|---|---|---|---|
| 1 | Browser-Mitschnitt je Beispielseite, Chromium Desktop und WebKit Mobil, frischer Kontext, bis zum Seitenende, zweimal | Anfragen samt iframes und Workern, Skripte, Cookies, Storage, neue Globals, Daten an fremde Hosts | ohne Einwilligung laden App-Pixel in Consent-Regionen nicht; Kasse nur mit Testkauf; Server-Dienste unsichtbar |
| 2 | `webPixelsConfigList` und `asyncLoad` im ausgelieferten HTML | alle verbundenen Web Pixels mit `apiClientId`; die Skript-Tags aller Apps | getrennte Pixel stehen nur im Admin unter Kundenereignisse; das Format von `content_for_header` ist nicht zugesichert |
| 3 | `app(id:)` mit der `apiClientId` | Klarnamen der Apps | ob `installation` für fremde Apps lesbar ist, ist nicht geprüft |
| 4 | App-Embeds in `config/settings_data.json` unter `current.blocks`, Typ `shopify://apps/...`, Feld `disabled` | jedes Embed, das einmal aktiviert wurde | nur auf dem Theme aktiv, auf dem es eingeschaltet wurde |
| 5 | App-Blöcke in JSON-Templates und Section-Groups | Fundstelle je Block, gezählt gegen die lebenden Templates | liegen in den Inhalten des alten Themes und gehen mit ihnen verloren |
| 6 | Theme-Code | fest eingebauter Code und Reste deinstallierter Apps | Hosts aus 1 und 2 gezielt suchen, dazu `gtag(`, `fbq(`, `dataLayer`, `_learnq`, `ttq.`, `uetq`, `clarity(` |
| 7 | Tag Manager | jedes Tag mit Funktion, Kennung und Auslöser | nur vollständig aufgelöst: `gtm.js?id=GTM-...` enthält `resource` mit `tags`, `macros`, `predicates`, `rules` |
| 8 | Shop-Metafeld-Namensräume | Apps, die konfiguriert, aber nirgends eingebunden sind; ein zweites Consent-System | Felder, deren Inhalt nicht zum Namen passt, gesondert prüfen |
| 9 | Checkout und Backend (Functions, Rabatte, Versand, Bestellquellen) | überleben den Wechsel, werden nur aufgenommen | welche Checkout-Erweiterungen im Profil hängen, ist nicht lesbar |
| 10 | App-Proxies aus Crawl und Mitschnitt (`/apps/`, `/a/`, `/community/`, `/tools/`) | Proxy-Pfade | keine Liste in der Admin-API |
| 11 | Consent | Voreinstellung und Verhalten vor und nach Einwilligung, Consent Mode | mit Einwilligung nur nach Freigabe durch das Team |
| 12 | Liste der installierten Apps aus dem Admin, vom Team geliefert | der einzige Weg zu reinen Backend-Apps ohne jede Spur | braucht das Team |

**Zuerst von den Spuren aus erheben, nicht nach Namen.** Eine Suche nach bekannten Apps findet nur,
was man schon kennt. Jede fremde Domain bekommt einen Anbieter und einen Zweck (`hosts.json`), ein
unbekannter Host bleibt `unknown` und wird recherchiert, bevor Gate G1 durch ist.

## Datenmodell

`apps.json` hält eine Zeile je Einbindung, gruppiert über `service_id`. Eine App kann mehrere
Einbindungen haben.

| Feld | Inhalt |
|---|---|
| `service_id`, `service_name`, `vendor` | Dienst und Anbieter |
| `app_id`, `app_handle` | aus Pixel oder Block-Typ, aufgelöst über `app(id:)` |
| `integration_type` | `app_embed`, `app_block`, `theme_code`, `script_tag`, `web_pixel_app`, `web_pixel_custom`, `checkout_extension`, `function`, `app_proxy`, `tag_manager`, `server_side`, `metafield_only` |
| `location` | Datei und Zeile, Templates, Block-UUID, Pixel-ID, Tag-ID |
| `state` | `active`, `disabled`, `broken` (Host antwortet mit 4xx), `leftover` |
| `survives_theme_switch` | aus `integration_type` abgeleitet, nie von Hand gesetzt |
| `before_consent` | `sends`, `loads`, `silent`, `not_measured` |
| `deprecation` | etwa Skript-Tag, Frist aus `platform-deadlines.md` |
| `decision` | `keep`, `replace`, `drop`, `open` |
| `target_integration` | Weg im neuen Theme |
| `verified_draft`, `verified_live` | Datum und Seitentyp |

`tracking.json` hält eine Zeile je Messziel (GA4 `G-`, Google Ads `AW-` mit Label, Meta-Pixel, UET,
TikTok und weitere) mit allen Absendern, ihrem Weg und ihren Events. **Jedes Event mit mehr als einem
Absender ist ein Befund.**

## Was einen Theme-Wechsel überlebt

| Einbindungsart | Überlebt | Handlung im neuen Theme |
|---|---|---|
| App-Block | nein | neu platzieren, nur auf lebenden Templates, Section mit `@app` |
| App-Embed | nein, je Theme aktiviert | `build-theme` übernimmt den Block mit Zustand in `settings_data.json` des Ziels; nach dem Upload zurücklesen |
| Theme-Code | nein | bevorzugt durch Embed oder Block der App ersetzen, sonst als eigene Datei mit Präfix portieren oder streichen |
| Skript-Tag | ja | läuft weiter, endet aber zur Frist; Nachfolger einplanen, meist ein Embed. Wird gestrichen, die App deinstallieren, sonst lädt sie weiter |
| Web Pixel, Checkout, Functions, Rabatte, Backend | ja | nur aufnehmen; Doppelmessung gegen neue Theme-Einbindungen prüfen |
| Tag Manager | hängt am Theme-Code | jedes Tag einzeln entscheiden; wird der Container entfernt, braucht jedes Tag einen eigenen Weg, auch das Consent-Signal an Google |
| App-Proxy | ja | Links im Theme auf denselben Pfad beibehalten |
| nur Metafelder | ja | klären, ob die App noch bezahlt wird und ob das neue Theme dieselben Felder liest |

Eine App, die deinstalliert wird, entfernt nur den Code aus ihrer Theme App Extension. Code, den sie
per Asset-API ins Theme geschrieben hat, bleibt liegen.

## Regeln, die aus Fehlern kommen

- **Tracking je Ziel aufnehmen, nicht je App.** Die Frage "was sendet diese App?" zeigt nicht, dass ein
  zweiter Absender dasselbe Ziel bedient. Die Frage "wer sendet an dieses Ziel?" zeigt es auf einen
  Blick.
- Eine Tag-ID mit zwei Absendern ist nicht doppelt abgesichert: welche Events ein Absender schickt,
  steht in seiner Konfiguration je Event. Wer den zweiten abschaltet, nimmt womöglich das einzige
  Kaufsignal weg. Je Ziel und Event aufschlüsseln, bevor eine Abschaltung empfohlen wird.
- **Jede Zeile des Inventars geht in die Entscheidungsliste**, auch eine unstrittige. Ein Dienst, der
  nur im technischen Inventar steht, wird im neuen Theme nicht geprüft.
- Die Prüfung läuft je Seitentyp, nicht nur auf der Startseite.
- Consent zuerst prüfen: die Voreinstellung, nicht nur das Verhalten nach dem Klick. Eine
  Voreinstellung mit Region geht vor einer ohne, und lädt die Consent-App länger als
  `wait_for_update`, gilt die Voreinstellung.
- "Nach Einwilligung" im Tag Manager heißt oft "auf das Ereignis der Consent-App", und das Ereignis
  kann ohne Klick kommen. Nur der Mitschnitt ohne Einwilligung zeigt das.
- App-Pixel halten sich an die Customer Privacy API, Theme-Code und Tag Manager nicht.
- Consent-Werkzeuge greifen in Dialogfenster des neuen Themes ein, etwa über eine globale Regel für
  `dialog::backdrop`. Nach dem Einbinden jede Abdunklung im Bild prüfen.
- Vor jeder Neu-Anbindung den entschiedenen Stand im Inventar nachlesen, nie aus dem Gedächtnis. Was
  ein entfernter Verteiler wie der Tag Manager geladen hat, braucht einen eigenen Weg.

## Neu-Anbindung im Ziel-Theme

1. Reihenfolge: erst was Umsatz trägt (Suche, Bewertungen, Warenkorb), dann Consent, dann der Rest.
2. Je Einbindung festhalten: wiederhergestellt, auf welchem Seitentyp geprüft, mit welchem Ergebnis
   (`verified_draft`).
3. App-Embeds kommen per Upload in den Entwurf: der Block aus `settings_data.json` des Live-Themes,
   unverändert, im selben Shop. Eine App kann ein Embed nicht selbst einschalten; den Editor braucht es
   nur, wenn Shopify einen Block verworfen hat.
4. App-Blöcke, die leer rendern (ein Produkt ohne passende Daten), werden ausgeblendet, nicht
   übernommen, nur weil live dasselbe steht.

## Prüfung

- **Vor dem Launch:** Mitschnitt Live gegen Entwurf je Seitentyp, im Browser, mit `preview_theme_id`
  und Theme-Nachweis. Fertig heißt: jede Fremd-Domain aus dem Live-Shop ist im Entwurf da oder bewusst
  weg, Consent in beiden Zuständen, keine doppelten Events. Ein HTTP-Abruf ohne Browser taugt nicht:
  die Vorschau greift über Cookie und Weiterleitung, sonst liefert der Abruf den Live-Shop.
- **Am Launch-Tag:** derselbe Mitschnitt gegen das veröffentlichte Theme, dazu ein Testkauf nach
  Freigabe für Pixel, Checkout und Dankeseite.
- **Danach:** Abgleich der Datensätze in GA4 und Werbekonten gegen die Bestellungen.

## Quellen

- https://shopify.dev/docs/apps/build/online-store/theme-app-extensions/configuration
- https://shopify.dev/docs/apps/build/online-store/theme-app-extensions/migrate
- https://shopify.dev/docs/storefronts/themes/architecture/blocks/app-blocks
- https://shopify.dev/docs/apps/build/online-store/script-tag-deprecation/storefront
- https://shopify.dev/docs/apps/build/marketing/pixels
- https://shopify.dev/docs/api/web-pixels-api/standard-api/customerprivacy
- https://shopify.dev/docs/apps/build/online-store/app-proxies
- https://shopify.dev/docs/api/admin-graphql/2026-04/queries/appInstallations
- https://developers.google.com/tag-platform/security/guides/consent-debugging
