---
name: capture-screens
description: Nimmt für den Audit-Lauf Screenshots aller Seitentypen (Desktop und Mobil) plus einen automatisiert durchlaufenen Kaufprozess bis zur Zahlungsauswahl auf und indexiert sie in runs/<run-id>/screens.json; dazu Belegbilder zu Befunden aus den Aufnahme-Aufträgen im Lauf (shoot_proof.py). Einsetzen, wenn der Audit-Orchestrator (/ptai-ecom:audit) Phase 1 durchläuft oder der Nutzer ausdrücklich Screenshots vom Kunden-Shop will. Einziger nicht wiederholbarer Pull: ohne Bild ist der Vorher-Zustand weg, sobald der Kunde sein Theme ändert. Liest reporting/config.json im Kunden-Workspace.
---

# capture-screens: Screenshots je Seitentyp und der Kaufprozess

- Je konfiguriertem Seitentyp zwei Screenshots (Desktop und Mobil), danach der Kaufprozess bis zur Zahlungsauswahl.
- Beides dokumentiert den visuellen Vorher-Zustand des Shops (Spec Abschnitt 7).
- Einmaliger Pull: ein Theme-Wechsel beim Kunden löscht den Vorher-Zustand; die übrigen Quellen (Shopify, GA4, GSC, CWV) liefern ihn nicht nach.
- Darum Vorrang vor allen anderen Pulls, sobald das Theme-Ende des Kunden feststeht.

## Ablageorte

- **Bilddateien in den Kundenordner (`drive_path`), nie nach `reporting/`.** `reporting/` wird im Kunden-Repo committet, Shop-Screenshots gehören dort nicht hin.
- Nur der Index `screens.json` liegt im Workspace.
- **Ausnahme Belegbilder zu Befunden** (Abschnitt Belegbilder): sie gehören zu einer Fassung eines Laufs, gehen mit ihm ins Portal und liegen in `reporting/runs/<run-id>/proof/`, von Git ignoriert. Quelle ist der Bucket, nicht das Repo.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit `account_slug`, `drive_path`, optional `page_types` (fehlende Typen erlaubt, siehe unten).
- Headless Browser für die automatischen Aufnahmen: bevorzugt die Headless Shell von Playwright, Chrome oder Chromium gehen auch.
- `jq` installiert (baut die JSON-Ausgabe von `shoot.sh`).
- Schreibzugriff auf den Kundenordner aus `drive_path`.

Fehlt `account_slug` oder `drive_path`, oder ist `drive_path` relativ, lehnt `scripts/audit/config.py: validate()` den Lauf schon vor dieser Skill ab. Ohne Ziel kämen die Bilder ins Repo, entgegen der PII-Regel aus Spec Abschnitt 13.

## Ablage

| Was | Wo |
|---|---|
| Bilder | `<drive_path>/material/<datum>-audit-screenshots/` |
| Index | `reporting/runs/<run-id>/screens.json` |

- `drive_path` aus `config.json` = absoluter Pfad zum Kundenordner (Beispiel: `/pfad/zum/kundenordner/beispielshop`), meist `<PTAI_ACCOUNTS_ROOT>/<account_slug>`.
- `<datum>` = Tagesdatum des Laufs, `YYYY-MM-DD`.
- `run-id` kommt vom Orchestrator, wenn die Skill Teil eines Audit- oder Report-Laufs ist (`skills/audit/SKILL.md`); solo einmalig selbst bestimmen (Schritt 1).
- **Die Analysen lesen Screenshots nur über diesen Index, nie über ein Directory-Listing.** Ein Bild ohne Eintrag existiert für sie nicht.

## Ablauf

1. **Lauf-ID bestimmen**, falls nicht vom Orchestrator übergeben:

   ```bash
   python3 -c "
   import sys
   sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   from audit import run
   from datetime import date
   print(run.run_id(date.today(), 'audit'))
   "
   ```

   Innerhalb eines laufenden Audits oder Reports dessen Lauf-ID übernehmen, nie neu berechnen; sonst verteilen sich Bilder eines Laufs bei einem Mitternachtsübergang auf zwei `runs/`-Ordner.

2. **Zielordner bestimmen:** `drive_path` aus `reporting/config.json` lesen, `material/$(date +%F)-audit-screenshots/` anhängen, mit `mkdir -p` anlegen. `drive_path` ist absolut, keine Wurzel davor.

3. **Seitentypen lesen**, immer alle sechs Standardtypen, auch ohne Override:

   ```bash
   python3 -c "
   import json, sys
   sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   from audit import config
   cfg = json.load(open('reporting/config.json'))
   print(json.dumps(config.page_types(cfg), ensure_ascii=False))
   "
   ```

   Schlüssel immer `start, collection, product, cart, search, blog`. Typ ohne Override: `null`.

4. **Je Typ mit URL** (`null` ausgeschlossen, siehe Schritt 5):

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/shoot.sh" \
     --url "<url>" --name "<page-type>" --target "<Zielordner aus Schritt 2>"
   ```

   - Die Zeile `IMAGES_JSON: [...]` enthält die fertigen Einträge (Seitentyp, Gerät, Aufnahmezeit, Quell-URL, absoluter Pfad) für `screens.json`. Unverändert übernehmen, Pfad und Zeitstempel nie neu tippen.
   - Exit-Code = Zahl fehlgeschlagener Aufnahmen (0, 1 oder 2).
   - Bei über 0: stderr-Zeilen in die Meldung an den Nutzer, mit den übrigen Typen weitermachen.
   - Fehlgeschlagener Typ: kein Eintrag in `screens.json`, aber eine Zeile an den Nutzer ("Aufnahme fehlgeschlagen: <typ>, Grund: ...").

5. **Typ ohne URL (`null`) melden, nie stillschweigend überspringen.**
   - Kein Aufruf von `shoot.sh`.
   - Zeile "nicht konfiguriert: <Seitentyp>" an den Nutzer und Eintrag im Feld `not_configured` von `screens.json` (Schema unten).
   - Im Audit-Orchestrator steht dieselbe Information in `runs/<run-id>/source-status.md`; diese Skill schreibt die Datei nicht, sie meldet nur.

6. **`screens.json` schreiben:** alle Bild-Einträge plus Liste nicht konfigurierter Typen (Schema unten). Existiert die Datei schon (vorheriger Teillauf): ergänzen, nicht überschreiben, damit bereits fotografierte Typen im Index bleiben.

7. **Kaufprozess durchlaufen**, siehe unten.

8. **Dem Nutzer melden:**
   - Zahl fotografierter Typen (Desktop plus Mobil je Typ)
   - nicht konfigurierte Typen
   - fehlgeschlagene Typen
   - ob der Kaufprozess durchlaufen wurde
   - Ablageort der Bilder (voller Pfad)

## Der Kaufprozess

- Automatisiert mit den Browser-Werkzeugen, nicht mit `shoot.sh` (nur für Seitentyp-Aufnahmen). Ein Audit, der auf einen Menschen wartet, ist kein Werkzeug.
- **Vor jedem Schritt die Seite lesen, dann handeln.** Nie blind auf eine Koordinate klicken: Seiteninhalt abfragen (Accessibility-Baum oder Text), prüfen, dass die erwartete Stufe erreicht ist, dann den nächsten Schritt auslösen.

1. Ein reguläres Produkt **mit Bestand** öffnen, nie das Beispielprodukt aus `page_types.product`. Bestand aus `shopify.json > availability` oder von der Produktseite.
2. In den Warenkorb legen, Warenkorb-Ansicht (Drawer oder Seite) fotografieren: `checkout-warenkorb.png`.
3. Zur Kasse gehen, Kontakt- und Versandadresse mit Platzhalter-Daten füllen. Schritt Versandart-Auswahl fotografieren: `checkout-versand.png`.
4. Bis zur Zahlungsart-Auswahl gehen, dort **anhalten** und fotografieren: `checkout-zahlung.png`. Sichtbar: die angebotenen Zahlungsarten, keine ausgefüllten Zahlungsfelder.
5. Kasse verlassen, nichts abschicken.

### Verbote

Gelten unabhängig davon, wer den Ablauf steuert; nur mit ihnen ist die Automatisierung vertretbar.

- **Keine Zahlungsart wählen, nichts absenden, keine Zahlungsdaten eingeben.** Auch nicht bei Zahlungsarten ohne Kartendaten wie "Kauf auf Rechnung". Der Lauf endet an der Auswahl.
- **Keine echten personenbezogenen Daten**, weder vom Nutzer noch von einem Kunden. Nur erkennbare Platzhalter.
- **Kein Login.** Kaufweg als Gast. Verlangt der Shop ein Konto: Schritt abbrechen, als Befund melden, kein Konto anlegen.
- **Kein zweiter Versuch nach einem Fehlklick.** Führt ein Schritt nicht ans Ziel: abbrechen, erreichten Stand protokollieren.

### Folge im Shop

- Der verlassene Warenkorb erzeugt eine abgebrochene Session wie bei jedem Besucher.
- Er erscheint in `shopify.json > abandoned_checkouts`.
- Bei sehr wenigen Bestellungen als Anmerkung in den Lauf schreiben, damit niemand ihn für Kundenverhalten hält.

### Abschalten

- `checkout_capture` in `reporting/config.json` steuert diesen Teil.
- **Nie im Lauf nachfragen.** Die Aufnahme legt einen echten Testwarenkorb im Produktivshop an; die Freigabe gehört ins Setup, einmal je Kunde.
- `true` nimmt den Kaufweg auf, `false` lässt ihn aus.
- Fehlt das Feld oder ist es kein Wahrheitswert, liefert `config.checkout_capture()` `None`: der Kaufweg läuft nicht, und die Lücke wird im Report ausgewiesen.
- Die Seitentyp-Aufnahmen laufen in jedem Fall.
- Sinnvoll abzuschalten bei einer Kasse mit Kontopflicht und bei Kunden, die keinen Testwarenkorb wollen.

## screens.json-Schema

```json
{
  "run_id": "2026-10-01-audit",
  "created_at": "2026-10-01T09:12:03Z",
  "target_dir": "<drive_path>/material/2026-10-01-audit-screenshots",
  "images": [
    {
      "page_type": "start",
      "device": "desktop",
      "captured_at": "2026-10-01T09:12:01Z",
      "source_url": "https://beispielshop.de/",
      "path": "<drive_path>/material/2026-10-01-audit-screenshots/start-desktop.png"
    },
    {
      "page_type": "start",
      "device": "mobil",
      "captured_at": "2026-10-01T09:12:04Z",
      "source_url": "https://beispielshop.de/",
      "path": "<drive_path>/material/2026-10-01-audit-screenshots/start-mobil.png"
    },
    {
      "page_type": "checkout-zahlung",
      "device": "desktop",
      "captured_at": "2026-10-01T09:24:47Z",
      "source_url": "https://beispielshop.de/checkout/...",
      "path": "<drive_path>/material/2026-10-01-audit-screenshots/checkout-zahlung.png",
      "manual": true
    }
  ],
  "not_configured": ["warenkorb", "suche"]
}
```

- `manual: true` steht nur an den Bildern des Kaufwegs (Browser-Werkzeuge statt `shoot.sh`). Der Feldname bleibt, obwohl der Kaufweg automatisiert läuft.
- `not_configured` enthält jeden Seitentyp, für den `config.page_types()` `null` geliefert hat.
- Leere Liste = alle sechs Typen konfiguriert, nicht ausgefallene Prüfung.
- Das Feld steht immer, auch leer.

## Belegbilder zu Befunden

- Ein Belegbild zeigt dem Kunden im Portal, was ein Befund meint, etwa den Handy-Ausschnitt mit Ende der Erstansicht und Kaufbutton darunter oder den Cookie-Dialog mit markierten Knöpfen.
- Die Übersichtsaufnahmen oben taugen dafür nicht: ganzer Seitentyp, keine Markierung.

**Der Agent schreibt einen Auftrag, kein Bild.**

- In einem `image`- oder `phone`-Baustein steht `capture` mit Seite, Gerät, Ausschnitt, Markierungen und dem, was nicht da sein darf, dazu `alt` und `title`.
- Vertrag: `reference/finding-format.md`, Abschnitt "Aufnahme-Auftrag capture".
- Aufträge schreiben nur die Agents für Conversion, Content und Vertrauen.

`scripts/shoot_proof.py` nimmt die offenen Aufträge eines Laufs auf:

```bash
uv run --quiet --with playwright==1.58.0 python \
  "${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/shoot_proof.py" \
  --run reporting/runs/<run-id>
```

- Version 1.58.0 passt zu den Browsern im Playwright-Cache; jede andere lädt sie neu.
- `--refresh` nimmt alle Aufträge neu auf, `--only CRO-01` nur einen Befund.

| Thema | Regel |
|---|---|
| **Ablage** | `reporting/runs/<run-id>/proof/<id>-<n>-<gerät>.jpg`, beim `phone` zusätzlich `...-voll.jpg` für die große Ansicht. Das Skript schreibt das Ergebnis (`src`, Maße, Markierungen in Prozent, Ende der Erstansicht, Datum) neben den Auftrag in die Befund-Datei. Der Auftrag bleibt für Neuaufnahmen stehen. |
| **Cookie-Dialog** | `consent.py` lehnt ab, auch über die zweite Ebene ("Nein, anpassen", dann "Ablehnen"). Nicht ablehnbar: Auftrag bleibt offen. `consent: "shown"` nimmt den Dialog bewusst auf (Befund über den Dialog). `shoot_declined.py` nutzt dieselbe Ablehnung. |
| **Ziel** | Muss genau ein sichtbares Element treffen, sonst bleibt der Auftrag offen. Ein Text trifft den umgebenden Knopf oder Link, damit die Markierung den ganzen Knopf umfasst. |
| **`absent` sichtbar** | Mangel behoben, kein Bild. Der Befund braucht dann einen Beleg aus Zahlen oder entfällt. |
| **Exit 1** | Sobald ein Auftrag offen bleibt. `publish` lädt keinen Lauf mit offenem Auftrag oder fehlender Bilddatei hoch. |

- `audit.revision` legt `proof/` mit den Befunden in die Fassung; eine neue Fassung nimmt ihre Bilder neu auf.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| **Kein Browser gefunden** | `shoot.sh` bricht sofort ab (Exit 1, vor der ersten Aufnahme). Headless Shell installieren (`npx playwright install chromium-headless-shell`) oder Chrome bzw. Chromium, erneut aufrufen. |
| **`jq` fehlt** | Wie oben: `shoot.sh` bricht vor der ersten URL ab. |
| **Einzelne Aufnahme scheitert** (Timeout, 4xx/5xx, Netzwerk) | `shoot.sh` läuft weiter, die zweite Aufnahme desselben Typs ebenfalls; der Exit-Code zählt die Fehlschläge. Typ als fehlgeschlagen melden (Schritt 4), kein Eintrag in `screens.json`, nie ein erfundener Pfad. |
| **Ein Seitentyp mit `null`-URL** | Kein Fehler, kein `shoot.sh`-Aufruf, aber immer eine "nicht konfiguriert"-Zeile (Schritt 5). |

**URL nicht erreichbar (DNS, Timeout, TLS)**

- Headless Chrome endet trotzdem mit Exit 0 und schreibt ein Bild von Chromes eigener Fehlerseite ("Die Website ist nicht erreichbar").
- Weder Exit-Code noch Dateigröße verraten das; die Fehlerseite ist einige Zehn-KB groß wie eine echte Seite.
- `shoot.sh` erkennt sie an einer internen, sprach- und versionsstabilen Chromium-Markierung im DOM, verwirft das Bild und zählt die Aufnahme als fehlgeschlagen.
- Die Headless Shell von Playwright schreibt stattdessen ein leeres Bild mit leerem DOM; auch das verwirft `shoot.sh`.
- Eine vom Kunden-Server ausgelieferte Fehlerseite (eigene 404 des Shops) ist echter Seiteninhalt und wird normal fotografiert.

**Cookie-Consent-Banner im Bild**

- Erwartet, kein Fehler.
- Jede Aufnahme nutzt ein frisches, nicht angemeldetes Chrome-Profil ohne Einwilligung, der Banner erscheint daher auf jeder Aufnahme.
- Layout darunter: aus der zweiten Aufnahme desselben Laufs lesen, falls vorhanden; sonst bleibt der Banner Teil des dokumentierten Ist-Zustands.

**Kaufprozess mittendrin abgebrochen** (Verbindung weg, falsches Element, Kunde meldet sich)

- Bisherige Kassen-Screenshots behalten, sie bleiben gültig.
- Fehlenden Rest in der Meldung an den Nutzer als offen kennzeichnen.
- Kein zweiter Versuch ohne Rücksprache: ein zweiter Warenkorb mit demselben Produkt ist beim Kunden sichtbar.
