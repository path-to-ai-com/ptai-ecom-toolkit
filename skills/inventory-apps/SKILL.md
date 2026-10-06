---
name: inventory-apps
description: Erfasst jede App und jeden Fremddienst eines Shopify-Shops mit Einbindungsweg, aus zwölf Quellen statt nur aus der Admin-API: Browser-Mitschnitt auf allen Beispielseiten, Web Pixels und Skript-Tags aus dem ausgelieferten HTML, App-Embeds und App-Blöcke aus dem Theme, fest eingebauter Code und Reste, Tag Manager vollständig aufgelöst, Shop-Metafelder, Checkout und Backend, App-Proxies, Consent; dazu Tracking je Messziel mit doppelten Events und die Plattform-Fristen. Nutzen bei "welche Apps hängen im Theme", "App-Inventar", "Tracking-Inventar", "was überlebt den Theme-Wechsel", "Dienste aufnehmen", in Phase 2 einer Theme-Migration und vor jedem größeren Section-Umbau. Nicht verwenden für die Prüfung des Entwurfs gegen live (ptai-ecom:verify-theme) und nicht für die Shop-Technik im Audit (ptai-ecom:pull-shopify-tech). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# inventory-apps: App- und Tracking-Inventar

Ein neues Theme enthält keine App-Einbindungen. Bewertungen, Suche, Consent, Formulare und ein großer
Teil des Trackings fehlen nach dem Wechsel. Diese Skill:

- erfasst jede Einbindung anhand ihrer Spuren im Shop, nicht anhand von App-Namen
- speichert je Messziel alle Absender

Arbeitsverzeichnis: der Kunden-Workspace.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit** (`shopify-plugin:shopify-admin`
für jede Abfrage), nie aus dem Gedächtnis.

Referenzen in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/`:

- `apps-and-tracking.md`: Quellen, Datenmodell, was nach einem Wechsel erhalten bleibt, Regeln aus
  Fehlern
- `platform-deadlines.md`: Fristen

## Voraussetzungen

- `reporting/config.json` mit `shopify_store`, `domain` und dem Block `theme_migration`.
- Sicherung des Live-Themes (`snapshot-theme`) und `migration/inventory/pages.json` (`inventory-theme`).
- `uv` für Playwright im Browser-Mitschnitt, wie bei `capture-screens`.
- Lesezugang mit `read_themes`; für Checkout und Backend zusätzlich die lesenden Scopes aus der
  Referenz. Fehlt ein Scope, steht die Quelle als `not_readable` mit Grund.

## Ablauf

**Die Admin-API zeigt nur Objekte der eigenen App.** Ein leeres `scriptTags` oder ein `ACCESS_DENIED`
bei `appInstallations` beweist nichts. Jede Quelle hat im Ergebnis eine Abdeckung: `complete`,
`partial` oder `not_readable` mit Grund, nie 0.

1. **Zuerst der Browser-Mitschnitt**, ohne Einwilligung, je Beispielseite in Chromium Desktop und WebKit
   Mobil, frischer Kontext, bis zum Seitenende, zweimal:

   ```bash
   uv run --quiet --with playwright==1.58.0 python \
     "${CLAUDE_PLUGIN_ROOT}/scripts/browser/capture_network.py" \
     --pages migration/inventory/pages.json \
     --out "migration/inventory/network/<date>-declined" --consent declined
   ```

   - Erfasst: Anfragen inklusive iframes und Worker, Skripte, Cookies, Storage, neue Globals, Daten an
     fremde Hosts.
   - Höchstens zwei Browser gleichzeitig auf der Storefront.
   - Zweiter Lauf mit `--consent accepted` nur nach ausdrücklicher Freigabe durch das Team.

2. **Ausgeliefertes HTML** der Beispielseiten speichert der Mitschnitt unter
   `migration/inventory/network/<date>-declined/html/`. Der Scan liest daraus:
   - `webPixelsConfigList`: alle verbundenen Web Pixels mit `apiClientId`
   - `asyncLoad`: die Skript-Tags aller Apps

   Für das Live-Theme ist keine Vorschau nötig; eine Testansicht nur im Browser.

3. **Tag Manager vollständig auflösen.**
   - Je Container-ID `gtm.js?id=GTM-...` abrufen und als `migration/inventory/gtm/GTM-<id>.js` ablegen.
   - Einzelprüfung eines Containers:
     `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.gtm resolve --gtm <datei> --out <json>`.
   - Der Scan liest daraus `resource` mit `tags`, `macros`, `predicates`, `rules`: je aktivem Tag
     Funktion, aufgelöste Kennung und Auslöser.
   - Eine Suche nur nach IDs genügt nicht, weil Kennungen dort auch ohne Präfix stehen.

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

   Das Modul liest:
   - App-Embeds aus `config/settings_data.json` (`current.blocks`, Typ `shopify://apps/...`, Feld
     `disabled`)
   - App-Blöcke aus JSON-Templates und Section-Groups, gezählt gegen die zugewiesenen Templates aus
     `templates.json`
   - fest eingebauten Code und Reste: Hosts aus Mitschnitt und HTML, dazu `gtag(`, `fbq(`, `dataLayer`,
     `_learnq`, `ttq.`, `uetq`
   - Zuordnung der Hosts zu Anbietern über
     `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/hosts.json`

   Weiter:
   - `survives_theme_switch` leitet das Modul aus dem Einbindungsweg ab, nie von Hand setzen.
   - `--gtm` und `--network` sind wiederholbar, ein Eintrag je Container bzw. je Mitschnitt.
   - Daten aus Admin-API oder vom Team als Datei übergeben: `--app-names` (Schritt 5), `--metafields`
     (Schritt 6), `--admin-apps` (Liste aus dem Admin, wenn das Team sie liefert).
   - Exit 1 bedeutet Befunde: unbekannte Hosts, doppelte Events, Skript-Tags, Reste oder defekte
     Einbindungen.
   - Ein Dienst, der nur im Mitschnitt erscheint, steht als `network_only`, bis sein Weg geklärt ist.

5. **App-Namen auflösen.** Jede `apiClientId` aus den Pixeln und jede App aus Block-Typen über
   `app(id: "gid://shopify/App/<id>")` in Klarnamen übersetzen. Ob `installation` für fremde Apps lesbar
   ist, ist nicht belegt; dann bleibt `installed` auf `unknown`.

6. **Namensräume der Shop-Metafelder** lesen. Sie zeigen konfigurierte Apps ohne Einbindung und ein
   zweites Consent-System. Felder, deren Inhalt nicht zum Namen passt, gesondert prüfen.

7. **Checkout und Backend nur erfassen:** Payment- und Delivery-Customizations, Validierungen,
   App-Rabatte, Versanddienste, welche App Bestellungen anlegt. Sie bleiben beim Wechsel erhalten; die
   Erfassung verhindert doppelte Messung beim Neuaufbau.

8. **App-Proxies** aus Crawl und Mitschnitt (`/apps/`, `/a/`, `/community/`, `/tools/`).

9. **Consent:**
   - Voreinstellung und Verhalten vor und nach Einwilligung
   - Consent Mode (`google_tag_data.ics.entries` mit `default` und `update`, `gcs` in Google-Aufrufen)
   - Konfiguration der Consent-App
   - je Zeile in `before_consent`, ob der Dienst ohne Einwilligung sendet

10. **Admin-Liste beim Team anfordern**, wenn sie fehlt: Apps im Admin und Kundenereignisse (getrennte
    Pixel stehen nur dort). Nur so sind reine Backend-Apps sichtbar. Ohne die Liste steht die Quelle als
    `not_readable`.

11. **Jeden unbekannten Host auflösen.** Jede fremde Domain bekommt Anbieter und Zweck, recherchiert,
    nie weggelassen. Ein Host mit `unknown` blockiert Gate G1. Allgemein gültige Zuordnungen (öffentlicher
    Anbieter, kein Shop-Bezug) als Vorschlag für `hosts.json` melden.

12. **Tracking je Messziel:** `tracking.json` mit einer Zeile je Ziel (GA4 `G-`, Google Ads `AW-` mit
    Label, Meta-Pixel, UET, TikTok und weitere), allen Absendern, ihrem Weg und ihren Events je Ziel.
    - **Jedes Event mit mehr als einem Absender ist ein Befund.**
    - Welche Events ein Absender sendet, steht in seiner Konfiguration je Event, nicht in der Liste der
      Tag-IDs.

13. **Fristen:** jeden Skript-Tag und jeden Rest von Shopify Scripts und Additional Scripts mit Frist als
    Eintrag nach `risks.json`. Die Datei vor dem Schreiben frisch lesen und nur den eigenen Teil ändern,
    weil `inventory-theme` dort ebenfalls schreibt.

14. **Entscheidungsliste vorbereiten.**
    - Jede Zeile von `apps.json` beginnt mit `decision: "open"`.
    - **Jede Zeile kommt in die Liste, über die das Team vor Gate G1 entscheidet**, auch unstrittige.
    - Die Skill schlägt je Zeile `keep`, `replace` oder `drop` mit Grund vor; das Team entscheidet.

15. **Ergebnis melden:** Zahl der Dienste und Einbindungen, Anteil, der beim Wechsel verloren geht,
    doppelte Events je Ziel, Dienste, die ohne Einwilligung senden, Skript-Tags mit Frist, offene Quellen
    mit Grund, unbekannte Hosts.

## Ergebnis

- `migration/inventory/apps.json`, `tracking.json` und der eigene Teil von `risks.json`, je mit
  `.md`-Ansicht.
- Der Mitschnitt unter `migration/inventory/network/`.
- Im Workspace committet, namentlich gestagt.
- Bilder und Screenshots im Kundenordner, nie im Repo.

## Fehlerbilder

- **Nur die Admin-Liste erfasst:** zeigt Installationen, nicht die Einbindungsorte.
- **Null Skript-Tags laut Admin-API als Beleg gewertet:** falsch, die API zeigt nur die der eigenen App.
  Quelle ist `asyncLoad` im HTML.
- **Tracking je App statt je Ziel erfasst:** doppelte Absender an dasselbe Ziel bleiben unsichtbar.
- **Mitschnitt nur auf der Startseite:** Widgets unterscheiden sich auf Produkt-, Kollektions-,
  Warenkorb- und Kontoseiten. Alle Beispielseiten mitschneiden.
- **Gedrosselt (HTTP 429, Bot-Abfrage):** mehr als zwei Browser oder zu schnelle Aufrufe. Pausieren, dann
  nacheinander mit Abstand.
- **Vorschau per `curl`:** liefert den Live-Shop. Testansichten nur im Browser mit Theme-Nachweis.
- **Dienst nur im technischen Inventar:** fehlt in der Entscheidungsliste und wird im neuen Theme nie
  geprüft. Jede Zeile in die Liste.
