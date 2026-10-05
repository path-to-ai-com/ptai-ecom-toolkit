# Herkunft der Fixtures für `theme.apps` und `theme.gtm`

Alles in diesem Ordner ist von Hand geschrieben und synthetisch. Nichts stammt aus
einem echten Shop, einem kommerziellen Theme oder einem echten Tag-Manager-Container.

- **Shop:** `beispiel.myshopify.com`, Domain `beispielshop.example`, Theme-ID
  `000000000000`. Die Kennungen (`G-BEISPIEL01`, `AW-000000000`, `GTM-BEISP01`,
  `100000000000001`, `BSP123`) sind erfunden und folgen nur der Form der echten.
- **`theme/`:** ein Mini-Theme mit genau den Fällen, die das Inventar unterscheiden
  muss: App-Embeds in `config/settings_data.json` mit Shopifys Kommentarkopf (eins
  aktiv, eins deaktiviert, eins einer unbekannten App mit Messkennung), App-Blöcke
  in einer Section-Group und in Templates (eins auf einem Template ohne Objekte,
  eins deaktiviert über die Section), fest eingebauter Code (Tag Manager, gtag,
  Meta-Pixel, ein unbekannter Host, ein Rest einer früheren App, Code in einer
  Custom-Liquid-Section), ein Link auf einen App-Proxy und Kommentare, die keinen
  Host ergeben dürfen.
- **`html/home-desktop-1.html`:** eine ausgelieferte Startseite im Aufbau, den
  Shopify für `Shopify.theme`, `asyncLoad` und `webPixelsConfigList` verwendet:
  zwei App-Pixel (einer mit Meta-Kennung, einer mit Google-Events je Ziel) und ein
  Custom Pixel, zwei Skript-Tags.
- **`network.json`:** ein Mitschnitt im Format von `scripts/browser/capture_network.py`
  mit einem gültigen Aufruf am Rechner, einem am iPhone und einem mit falschem
  Theme, der nicht zählen darf. Enthält eine doppelt gesendete GA4-Seitenansicht
  (Seite und Pixel-Rahmen), einen Skript-Tag mit 404, eine Anfrage aus dem Rahmen
  des Custom Pixels und eine Subdomain des Shops als Mess-Endpunkt.
- **`gtm.js`:** ein Container im Aufbau von `gtm.js` mit Google-Tag, GA4-Event,
  Google-Ads-Conversion mit nackter Kennung, UET, einem Meta-Pixel in eigenem HTML,
  einem pausierten Tag und einem Tag ohne Auslöser.
- **`templates.json`, `app-names.json`, `metafields.json`, `admin-apps.json`:**
  die Dateien, die sonst die Skill aus dem Shop oder vom Team liefert, im Format,
  das `theme.apps scan` erwartet.
