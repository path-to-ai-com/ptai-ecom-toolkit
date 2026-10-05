---
name: inventory-apps
description: Jede App und jeden Fremddienst eines Shopify-Shops mit Einbindungsweg erfassen, aus zwölf Quellen statt aus der Admin-API allein: Browser-Mitschnitt auf allen Beispielseiten, Web Pixels und Skript-Tags aus dem ausgelieferten HTML, App-Embeds und App-Blöcke aus dem Theme, fest eingebauter Code und Reste, Tag Manager vollständig aufgelöst, Shop-Metafelder, Checkout und Backend, App-Proxies, Consent; dazu Tracking je Messziel mit doppelten Events und die Plattform-Fristen. Nutzen bei "welche Apps hängen im Theme", "App-Inventar", "Tracking-Inventar", "was überlebt den Theme-Wechsel", "Dienste aufnehmen", in Phase 2 einer Theme-Migration und vor jedem größeren Section-Umbau. Nicht verwenden für die Prüfung des Entwurfs gegen live (ptai-ecom:verify-theme) und nicht für die Shop-Technik im Audit (ptai-ecom:pull-shopify-tech). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# inventory-apps: App- und Tracking-Inventar

Ein neues Theme bringt keine App-Einbindung mit. Bewertungen, Suche, Consent, Formulare und ein
großer Teil des Trackings fehlen nach dem Wechsel, und ohne Inventar kann niemand sagen, was vorher wo
hing. Diese Skill erhebt jede Einbindung von den Spuren aus, nicht nach Namen, und hält je Messziel
fest, wer dorthin sendet.

Arbeitsverzeichnis ist der Kunden-Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**
(`shopify-plugin:shopify-admin` für jede Abfrage), nie aus dem Gedächtnis.

Quellen, Datenmodell, was einen Wechsel überlebt und die Regeln aus Fehlern stehen in
`${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/apps-and-tracking.md`, die Fristen in
`platform-deadlines.md` im selben Ordner.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store`, `domain` und dem Block `theme_migration`.
- Sicherung des Live-Themes (`snapshot-theme`) und `migration/inventory/pages.json`
  (`inventory-theme`).
- `uv` für Playwright im Browser-Mitschnitt, wie bei `capture-screens`.
- Lesezugang mit `read_themes`; für Checkout und Backend zusätzlich die lesenden Scopes aus der
  Referenz. Ein fehlender Scope macht die Quelle zu `not_readable` mit Grund.

## Ablauf

**Die Admin-API zeigt nur, was der eigenen App gehört.** Ein leeres `scriptTags` oder ein
`ACCESS_DENIED` bei `appInstallations` beweist nichts. Jede Quelle trägt im Ergebnis ihre Abdeckung:
`complete`, `partial` oder `not_readable` mit Grund, nie 0.

1. **Browser-Mitschnitt zuerst**, ohne Einwilligung, je Beispielseite in Chromium Desktop und WebKit
   Mobil, frischer Kontext, bis zum Seitenende, zweimal:

   ```bash
   uv run --quiet --with playwright==1.58.0 python \
     "${CLAUDE_PLUGIN_ROOT}/scripts/browser/capture_network.py" \
     --pages migration/inventory/pages.json \
     --out "migration/inventory/network/<date>-declined" --consent declined
   ```

   Erfasst werden Anfragen samt iframes und Workern, Skripte, Cookies, Storage, neue Globals und
   Daten an fremde Hosts. Höchstens zwei Browser gleichzeitig auf der Storefront. Ein zweiter Lauf mit
   `--consent accepted` nur nach ausdrücklicher Freigabe durch das Team.

2. **Ausgeliefertes HTML** der Beispielseiten legt der Mitschnitt selbst ab
   (`migration/inventory/network/<date>-declined/html/`). Daraus liest der Scan `webPixelsConfigList` (alle verbundenen Web
   Pixels mit `apiClientId`) und `asyncLoad` (die Skript-Tags aller Apps). Das Live-Theme braucht dafür
   keine Vorschau; eine Testansicht dagegen nur im Browser.

3. **Tag Manager vollständig auflösen.** Für jede Container-ID `gtm.js?id=GTM-...` abrufen und als
   `migration/inventory/gtm/GTM-<id>.js` ablegen. Einzeln prüfen lässt sich ein Container mit
   `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.gtm resolve --gtm <datei> --out <json>`. Der Scan liest daraus `resource` mit `tags`, `macros`,
   `predicates`, `rules`: je aktivem Tag Funktion, aufgelöste Kennung und Auslöser. Nur nach IDs zu
   suchen reicht nicht; Kennungen stehen dort auch ohne Präfix.

4. **Scan über Theme, HTML, Mitschnitt und Tag Manager:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.apps scan \
     --snapshot migration/snapshots/<date>-<theme-id> \
     --html "migration/inventory/network/<date>-declined/html" \
     --network "migration/inventory/network/<date>-declined/network.json" \
     --gtm migration/inventory/gtm/GTM-<id>.js \
     --templates migration/inventory/templates.json \
     --own-host <shop-domain> \
     --out migration/inventory/apps.json
   ```

   Das Modul liest App-Embeds aus `config/settings_data.json` (`current.blocks`, Typ
   `shopify://apps/...`, Feld `disabled`), App-Blöcke aus JSON-Templates und Section-Groups (gezählt
   gegen die lebenden Templates aus `templates.json`), fest eingebauten Code und Reste (Hosts aus
   Mitschnitt und HTML, dazu `gtag(`, `fbq(`, `dataLayer`, `_learnq`, `ttq.`, `uetq`) und ordnet Hosts
   über `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/hosts.json` einem Anbieter zu.
   `survives_theme_switch` leitet es aus dem Einbindungsweg ab, nie von Hand. `--gtm` und `--network`
   sind wiederholbar (ein Eintrag je Container bzw. je Mitschnitt). Was nur aus der Admin-API oder vom
   Team kommt, geht als Datei hinein: `--app-names` (aus Schritt 5), `--metafields` (Schritt 6),
   `--admin-apps` (die Liste aus dem Admin, wenn das Team sie liefert). Exit 1 heißt Befunde: unbekannte
   Hosts, doppelte Events, Skript-Tags, Reste oder kaputte Einbindungen. Ein Dienst, der nur im
   Mitschnitt auftaucht, steht als `network_only`, bis sein Weg geklärt ist.

5. **App-Namen auflösen.** Jede `apiClientId` aus den Pixeln und jede App aus Block-Typen über
   `app(id: "gid://shopify/App/<id>")` zu Klarnamen. Ob `installation` für fremde Apps lesbar ist, ist
   nicht belegt; dann bleibt `installed` auf `unknown`.

6. **Shop-Metafeld-Namensräume** lesen. Sie zeigen Apps, die konfiguriert, aber nirgends eingebunden
   sind, und ein zweites Consent-System. Felder, deren Inhalt nicht zum Namen passt, gesondert prüfen.

7. **Checkout und Backend nur aufnehmen:** Payment- und Delivery-Customizations, Validierungen,
   App-Rabatte, Versanddienste, welche App Bestellungen anlegt. Sie überleben den Wechsel; aufgenommen
   werden sie, damit beim Neuaufbau nichts doppelt misst.

8. **App-Proxies** aus Crawl und Mitschnitt (`/apps/`, `/a/`, `/community/`, `/tools/`).

9. **Consent:** Voreinstellung und Verhalten vor und nach Einwilligung, Consent Mode
   (`google_tag_data.ics.entries` mit `default` und `update`, `gcs` in Google-Aufrufen), dazu die
   Konfiguration der Consent-App. Welcher Dienst ohne Einwilligung sendet, steht je Zeile in
   `before_consent`.

10. **Admin-Liste vom Team** anfordern, wenn sie fehlt: Apps im Admin und Kundenereignisse
    (getrennte Pixel stehen nur dort). Sie ist der einzige Weg zu reinen Backend-Apps. Kommt sie nicht,
    steht die Quelle als `not_readable`.

11. **Jeden unbekannten Host auflösen.** Jede fremde Domain bekommt einen Anbieter und einen Zweck,
    recherchiert und nie weggelassen. Ein Host, der `unknown` bleibt, blockiert Gate G1. Was dabei
    allgemein gilt (ein öffentlicher Anbieter, kein Shop-Bezug), gehört als Vorschlag in `hosts.json`.

12. **Tracking je Messziel:** `tracking.json` mit einer Zeile je Ziel (GA4 `G-`, Google Ads `AW-` mit
    Label, Meta-Pixel, UET, TikTok und weitere), allen Absendern, ihrem Weg und ihren Events je Ziel.
    **Jedes Event mit mehr als einem Absender ist ein Befund.** Welche Events ein Absender sendet, steht
    in seiner Konfiguration je Event, nicht in der Liste der Tag-IDs.

13. **Fristen:** jeder Skript-Tag, jeder Rest von Shopify Scripts und Additional Scripts mit Frist als
    Eintrag nach `risks.json`. Die Datei wird vor dem Schreiben frisch gelesen und nur der eigene Teil
    geändert, weil `inventory-theme` dort ebenfalls schreibt.

14. **Entscheidungsliste vorbereiten.** Jede Zeile von `apps.json` trägt zunächst
    `decision: "open"`. **Jede Zeile geht in die Liste, über die das Team vor Gate G1 entscheidet**,
    auch eine unstrittige. Die Skill schlägt je Zeile `keep`, `replace` oder `drop` mit Grund vor;
    entscheiden tut das Team.

15. **Ergebnis melden:** Zahl der Dienste und Einbindungen, Anteil, der den Wechsel nicht überlebt,
    doppelte Events je Ziel, Dienste, die ohne Einwilligung senden, Skript-Tags mit Frist, offene
    Quellen mit Grund, unbekannte Hosts.

## Ergebnis

`migration/inventory/apps.json`, `tracking.json` und der eigene Teil von `risks.json`, je mit
`.md`-Ansicht; der Mitschnitt unter `migration/inventory/network/`. Committet im Workspace,
namentlich gestagt. Bilder und Screenshots liegen im Kundenordner, nie im Repo.

## Fehlerbilder

- **Nur die Admin-Liste aufgenommen:** zeigt, was installiert ist, nicht wo es hängt.
- **Null Skript-Tags laut Admin-API gilt als Beleg:** falsch, die API zeigt nur die der eigenen App.
  Die Quelle ist `asyncLoad` im HTML.
- **Tracking je App statt je Ziel aufgenommen:** doppelte Absender an dasselbe Ziel bleiben unsichtbar.
- **Mitschnitt nur auf der Startseite:** Widgets hängen an Produkt-, Kollektions-, Warenkorb- und
  Kontoseiten verschieden. Alle Beispielseiten.
- **Gedrosselt (HTTP 429, Bot-Abfrage):** mehr als zwei Browser oder zu schnelle Aufrufe. Pausieren,
  dann nacheinander mit Abstand.
- **Vorschau per `curl`:** liefert den Live-Shop. Testansichten nur im Browser mit Theme-Nachweis.
- **Ein Dienst steht nur im technischen Inventar:** fehlt in der Entscheidungsliste und wird im neuen
  Theme nie geprüft. Jede Zeile in die Liste.
