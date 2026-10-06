---
name: setup
description: Geführter Setup-Wizard für ptai-ecom. Prüft Rechner und Anschlüsse mit check_env.sh, gruppiert nach Pflicht, Empfohlen und Optional, und führt in zwei Teilen durch alles Fehlende. Teil 1 einmal je Rechner: Schlüssel des Betreibers zentral in ~/.config/ptai-ecom/.env (DataForSEO, PageSpeed, GEO, Google-Ads-Token). Teil 2 je Kunde im Workspace: Config, Dienstkonto, GA4, Search Console, Shopify. Schreibt reporting/config.json und bietet zum Schluss den ersten Lauf an. Auslöser sind die Ersteinrichtung, eine fehlende oder defekte Quelle oder /ptai-ecom:setup. Idempotent und jederzeit erneut aufrufbar.
---

# setup: geführter Anschluss-Wizard

- Einstieg für einen neuen Kunden-Workspace. Setzt kein Vorwissen beim Nutzer voraus.
- Zeigt, was fehlt, und führt durch jeden Anschluss, bis der erste Report laufen kann.
- Idempotent: jeder neue Aufruf beginnt beim Check und setzt bei den fehlenden oder defekten Punkten an. Nichts wird doppelt eingerichtet, nichts geht verloren.
- Arbeitsverzeichnis ist der Kunden-Workspace (dort, wo `reporting/` liegen soll).

## Shop aus dem Cockpit (`--from-portal <brand> <shop>`)

Gilt, wenn der Kunde Shopify, Google Analytics und Search Console selbst im Cockpit verbunden hat. Die Zugänge liegen dann im Cockpit, nicht im Workspace, und diese Befehle ersetzen die Fragen nach Domain, Store, Properties und Dienstkonto:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.portal setup --brand <brand> --shop <shop>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.portal check --brand <brand> --shop <shop>
```

- `setup` schreibt in `reporting/config.json` die Werte aus dem Cockpit (Domain, `shopify_store`, `ga4_property_id`, `gsc_site`, `google_ads_customer_id`, die Schalter unter `sources`, den Block `portal`) und lässt alle anderen Felder unverändert.
- In die `.env` kommt `PTAI_GOOGLE_CREDENTIALS=portal:<brand>/<shop>` statt eines Pfads. GA4, Search Console und Google Ads holen damit ihren Zugang je Abruf beim Cockpit, gültig für eine Stunde.
- `check` zeigt je Quelle den Stand im Cockpit und holt jeden Zugang einmal, ohne einen Wert auszugeben.
- Anmeldung mit `PTAI_PORTAL_URL` und `PTAI_PORTAL_TOKEN` aus `~/.config/ptai-ecom/.env`. Fehlen sie, bricht der Befehl ab.
- Kein Rückfall: Eine im Cockpit nicht verbundene Quelle steht in der Config auf `false`; ein Pull darauf bricht ab, statt ein Dienstkonto zu verwenden.
- Kein Zugang aus dem Cockpit wird in `reporting/` gespeichert.
- Was das Cockpit nicht kennt (`cwv_urls`, `account_slug`, `drive_path`, `market`), fragt der Wizard normal ab; dafür beginnt der Ablauf unten beim Check.

## Ablauf

1. **Check ausführen und Haken-Liste zeigen:**

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/check_env.sh" .
   ```

   - Ausgabe gruppiert nach Rechner, Pflicht, Empfohlen, Optional und Workspace.
   - Unter jeder offenen Quelle steht, was ohne sie fehlt. Am Ende "Pflicht vollständig." oder "Pflicht offen: ..." und die offenen empfohlenen und optionalen Quellen.
   - Der Exit-Code zählt nur offene Punkte in Rechner, Pflicht und Workspace.
   - Die Liste unverändert zeigen, dann kurz einordnen, was erledigt und was offen ist.
   - Die Stufe jeder Quelle steht nur in `scripts/audit/tiers.py`.
   - Offene Zeilen unter Rechner vor Teil 1 erledigen. Jede nennt, was fehlt; die Shopify-CLI steht unter "Shopify", der Browser unter "PDF und Screenshots".
   - Ohne python3 ab 3.10 laufen die Test-Calls aus Teil 1 und 2 nicht.

2. **Teil 1, Betreiber, einmal je Rechner.**
   - Nur wenn der Check PageSpeed-Key, DataForSEO oder GEO-Keys als offen meldet, und nur für diese Punkte.
   - Jeder Punkt lässt sich mit "jetzt nicht" überspringen; der nächste Setup-Lauf zeigt ihn wieder.
   - Fehlt `~/.config/ptai-ecom/.env`: Ordner und Datei anlegen, mit leeren Zeilen für `PTAI_PSI_KEY`, `PTAI_DFS_LOGIN`, `PTAI_DFS_PASSWORD`, `PTAI_OPENAI_KEY`, `PTAI_PERPLEXITY_KEY`, `PTAI_GEMINI_KEY`, `PTAI_ACCOUNTS_ROOT`, `PTAI_OPERATOR_NAME`, `PTAI_OPERATOR_CONTACT`, `PTAI_OPERATOR_EMAIL`, `PTAI_OPERATOR_BOOKING_URL` und `PTAI_CLOSING_FILE`; Rechte `600` (`chmod 600`).
   - Eine leere Zeile gilt als nicht gesetzt.

   Reihenfolge:

   1. Google-Cloud-Projekt mit den fünf APIs, falls noch keins existiert (`${CLAUDE_PLUGIN_ROOT}/reference/access.md` Teil A, Schritte 1 und 2).
   2. PageSpeed-Key (Abschnitt "PSI-Key" unten).
   3. DataForSEO (Abschnitt "DataForSEO" unten).
   4. GEO-Keys (Abschnitt "GEO" unten, Teil "Keys anlegen").
   5. Nur wenn der Google-Ads-Test-Call an der Freigabe des Cloud-Projekts scheitert: am Ende die Freigabe anbieten (`${CLAUDE_PLUGIN_ROOT}/reference/access.md` Teil A, Schritt 6), mit dem Hinweis, dass die Freigabe bei Google liegen kann und der Audit ohne Google Ads läuft. Eine fehlende Freigabe allein löst Teil 1 nicht aus.
   6. Sechs Einstellungen, alle nur auf Wunsch. Keine davon löst Teil 1 aus.

   | Einstellung | Vorgabe | Wirkung |
   |---|---|---|
   | `PTAI_ACCOUNTS_ROOT` | `~/ptai-ecom/accounts` | Ordner mit den Kundenordnern; audit-light legt neue Kunden dort an. Im Check nur als Hinweis. |
   | `PTAI_OPERATOR_NAME` | "Dienstleister" | Eigener Name oder Firmenname als Verantwortlicher in Maßnahmen und Report. Nur wenn ausdrücklich gesetzt, zusätzlich Zeile Unternehmen im Schluss von Audit, Monats-Report und audit-light. Im Check nur als Hinweis. |
   | `PTAI_OPERATOR_CONTACT` | keine | Ansprechbare Person, etwa ein Name; Zeile Ansprechpartner im Schluss. |
   | `PTAI_OPERATOR_EMAIL` | keine | Mailadresse; Zeile E-Mail im Schluss. |
   | `PTAI_OPERATOR_BOOKING_URL` | keine | Terminlink, nur mit `https://` oder `http://`; Zeile Termin im Schluss. |
   | `PTAI_CLOSING_FILE` | keine | Pfad zu einer eigenen Schlussseite als HTML-Datei außerhalb des Plugins. Gesetzt und lesbar: Audit, Monats-Report und audit-light enden mit dieser Seite statt mit den Zeilen. |

   - Der Schluss zeigt eine Zeile je gesetztem und gültigem Wert, ohne weiteren Satz. Ohne gültige Einstellung endet jedes Dokument nur mit der Herkunftszeile.
   - Anforderungen an `PTAI_CLOSING_FILE`: genau ein `<section>`-Element als volle A4-Seite, alle Selektoren unter dessen Klasse, alle Bilder und Schriften als `data:`-URIs (README, Abschnitt "Eigene Marke").

3. **Teil 2, Kunden-Workspace, je Kunde.**
   - Config schreiben oder aktualisieren (Vorlage unten). Nie Secrets in die Config.
   - Jede offene Zeile unter Pflicht und Workspace mit der passenden Anleitung unten abarbeiten.
   - Klicks in Konsolen und Adminflächen macht der Mensch. Der Wizard erklärt den Weg und prüft nach jedem Schritt per Test-Call oder erneutem Check.
   - Ein Schritt ist erst erledigt, wenn sein Haken auf `[x]` steht.
   - Anleitungen kurz und im Imperativ, ohne Theorie, ohne Vorab-Warnungen.
   - Schließt der Kunde eine Quelle nicht an: **jeden** ihrer Lauf-Quellen-Schlüssel unter `sources` auf `false` setzen, bei Shopify also `shopify`, `catalogue` und `shop_tech`; kein Feld leer lassen. Zuordnung in `tiers.py` (`run_sources`).

4. **Was nur der Kunde freischalten kann, wird zur Anforderung, nicht zur offenen Zeile.**
   - `check_env.sh` gibt dafür am Ende einen eigenen Block aus mit der Überschrift "Das kann der Kunde freischalten, nicht du".
   - Hintergrund: eine Analytics-Property kann nur mit Administratorrechten geteilt werden, eine Search-Console-Property nur von einem Eigentümer. Beides liegt beim Kunden, auch wenn der Operator die Quelle selbst öffnen kann.
   - Hat der Block mindestens einen Eintrag: eine **Anforderung an den Kunden** erstellen, auf Basis von `${CLAUDE_PLUGIN_ROOT}/reference/access.md` Teil B, aber **nur mit den Punkten, die der Check gerade als offen meldet**.
   - Je Punkt: Dienstkonto-Adresse, Klickweg mit Direktlink, ein Satz zum Zweck des Zugangs.
   - Platzhalter `<betreiber-mail>`, `<dienstkonto-mail>`, `<shop-domain>` und `<datum>` füllen; die eigene Mailadresse beim Betreiber erfragen.
   - Den Text als Entwurf an den Nutzer geben. Nichts senden.

5. **Abschluss-Angebot:** "Ersten Lauf jetzt starten?" (Skill `report` oder `audit`).
   - Offene empfohlene Quellen blockieren nichts; sie erscheinen als "nicht verfügbar (Grund)", der Rest läuft.
   - Fehlt eine Pflichtquelle, fragt der Audit vor dem Start selbst noch einmal nach.

## Config-Vorlage

`reporting/config.json` im Kunden-Workspace. Nur kundenspezifische Werte, keine Secrets:

```json
{
  "brand": "Beispielshop",
  "domain": "https://beispielshop.de",
  "shopify_store": "beispielshop-de.myshopify.com",
  "ga4_property_id": "000000000",
  "ga4_compare_properties": [],
  "gsc_site": "sc-domain:beispielshop.de",
  "cwv_urls": ["https://beispielshop.de/", "https://beispielshop.de/products/BELIEBIG"],
  "account_slug": "beispielshop",
  "drive_path": "/pfad/zum/kundenordner/beispielshop",
  "geo_brand_terms": ["Beispielshop", "Beispiel Shop"],
  "geo_queries": {
    "brand": ["Beispielshop", "Beispielshop Outdoorjacken"],
    "category": ["Outdoorjacke kaufen", "Outdoorjacken nach Maß", "Kinderset"],
    "problem": []
  },
  "google_domain": "google.de",
  "geo_method": "api",
  "checkout_capture": true,
  "sources": {
    "shopify": true, "catalogue": true, "shop_tech": true,
    "ga4": true, "gsc": true, "ads": true, "cwv": true, "crawl": true, "geo": true,
    "dfs_rankings": true, "dfs_keywords": true, "competitors": true,
    "shopping": true, "backlinks": true
  },
  "pulse_kpis": ["sessions", "revenue", "orders", "conversion_rate", "aov", "gsc_clicks", "gsc_impressions"],
  "page_types": { "product": "https://beispielshop.de/products/BELIEBIG", "collection": "https://beispielshop.de/collections/BELIEBIG" },
  "cadences": {},
  "market": { "location_code": 2276, "language_code": "de" },
  "dfs_budget_usd": 10.0,
  "crawl_max_urls": 5000,
  "crawl_delay_sec": 0.3,
  "google_ads_customer_id": null
}
```

**`shopify_store`:** die echte myshopify.com-Domain, nie ein Alias.

**`geo_brand_terms`:**
- Schreibweisen, an denen `check-geo` eine Marken-Erwähnung in einer AI-Antwort erkennt.
- Getrennt von `brand` halten. `brand` ist der Name auf dem Dokument und wird gelegentlich geändert (Zusatz, Schreibweise, Vermerk für einen Testlauf); jede solche Änderung würde sonst ohne Fehlermeldung den Erwähnungs-Abgleich brechen.
- Fehlt das Feld, gilt `brand`.
- Varianten eintragen, etwa mit und ohne Umlaut.

**`ga4_compare_properties`:**
- Weitere GA4-Properties, die derselbe Shop beliefert. Häufigster Fall: ein serverseitiges Tool wie Littledata, Elevar oder Analyzify neben dem clientseitigen Tag, mit eigener Property.
- Der Audit zieht `ga4_property_id` vollständig und von jeder Property hier nur eine Monatsreihe aus Sitzungen, Käufen und Umsatz, um zu erkennen, welche zum Shop passt.
- Im Zweifel eintragen. Ohne den Vergleich ist keine Aussage über fehlende oder doppelt gezählte Käufe zuverlässig, und ein falscher Befund dazu steht auf der ersten Seite.
- Lädt der Shop mehr als eine `G-...`-Mess-ID im Quelltext, gibt es eine zweite Property.

**`gsc_site`:** exakt die Property-Form aus der Search Console (Unterscheidung im GSC-Abschnitt unten).

**`account_slug` und `drive_path`:**
- Pflicht für den Audit. Ohne sie kennt der Lauf den Kundenordner für Screenshots und Deliverables nicht und legt sie im Repo ab, was die PII-Regel verletzt.
- `account_slug`: Name des Kundenordners unter `PTAI_ACCOUNTS_ROOT`.
- `drive_path`: absoluter Pfad dorthin.
- Beide gibt `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.account create <domain> --brand=<brand>` aus; der Befehl findet einen vorhandenen Kunden und legt nur einen fehlenden an.

**`google_domain`:** optional, Default `google.de`. Google-Domain für den GEO-SERP-Check im Browser-Weg; für nicht-deutsche Brands die passende Locale-Domain (etwa `google.com`).

**`checkout_capture`:**
- Die eine Frage, die der Wizard stellen muss. Er stellt sie hier, damit der Audit sie nicht während des Laufs stellt.
- Steuert, ob der Audit den Kaufweg bis zur Zahlungsart-Auswahl fotografiert.
- Folge: ein echter Testwarenkorb im Produktivshop und damit ein Abandoned-Checkout-Datensatz, auf den ein E-Mail-Tool eine Warenkorbabbrecher-Strecke auslösen kann.
- Fehlt das Feld, läuft der Kaufweg nicht, und die Lücke steht im Report.
- Standard `true`.
- `false`, wenn die Kasse ein Konto verlangt oder der Kunde keinen Testwarenkorb will. Die Seitentyp-Aufnahmen laufen dann trotzdem.

**`geo_method`:** GEO-Weg `api` (empfohlen), `browser` oder `off`. Entscheidung im GEO-Abschnitt unten. Report und check-geo folgen ihr ohne Rückfrage.

**`sources`:**
- Schaltet Quellen einzeln an und aus.
- Fehlender Schlüssel bedeutet an; nur `false` schaltet ab.
- Die Vorlage führt alle vierzehn auf, damit sichtbar ist, was läuft.
- Eine Quelle, die der Kunde (noch) nicht anschließt, bekommt `false` auf allen ihren Schlüsseln, kein halber Anschluss.

**`page_types`:**
- Je Seitentyp eine Beispiel-URL für Crawl, Core Web Vitals und Screenshots.
- Defaults: `start, collection, product, cart, search, blog`. Nur abweichende Typen überschreiben.

**`competitors` und `keyword_seeds`:**
- Kein Pull liest diese Felder. Nicht abfragen und nicht anmahnen.
- `pull-dfs-competitors` verwendet die Kategorie-Begriffe aus `geo_queries` und findet Wettbewerber über die Überschneidung in den Suchergebnissen.
- `pull-dfs-keywords` verwendet die Top-Anfragen aus der Search Console.
- In bestehenden Configs dürfen die Felder stehen bleiben; sie haben keine Wirkung.

**`cadences`:** überschreibt die Kadenz einzelner Quellen (`run`, `month`, `quarter`) gegenüber der Voreinstellung aus Abschnitt 3. Leer: jede Quelle behält ihre Voreinstellung.

**`market`:**
- Pflicht. Legt den Markt der DataForSEO-Abfragen fest.
- `location_code`: numerischer Standortcode (Deutschland 2276, Österreich 2040, Schweiz 2756, weitere in der DataForSEO-Standortliste).
- `language_code`: Sprachcode ("de", "en").
- Kein Vorgabewert. Ein stillschweigend angenommenes Deutschland liefert für einen Shop in einem anderen Markt plausibel wirkende Zahlen zum falschen Land.
- `google_domain` ist davon unabhängig und behält seinen eigenen Default, weil `report` und `pulse` es in laufenden Workspaces von dort lesen.

**`google_ads_customer_id`:**
- Kundennummer des Werbekontos, mit oder ohne Bindestriche.
- `null`, solange kein Zugang besteht. `pull-ads` meldet dann "nicht verfügbar", der Baseline-Block SEA bleibt leer und wird später mit `--backfill` nachgetragen. Das ist der dokumentierte Normalfall.

**`crawl_max_urls` und `crawl_delay_sec`:**
- Begrenzen den Crawl. Immer in die Config, nie in den Prompt eines Laufs; der Umfang hängt am Shop und bleibt gleich.
- Der passende Wert steht nach dem ersten Crawl in der Sitemap-Zeile des Laufs ("Sitemap: 4.200 URLs").
- Bei mehreren Sprachversionen deckt meist die Hälfte davon alles ab, was ein Relaunch betrifft.
- Antwortet der Shop langsam oder steht eine Bot-Erkennung davor: `crawl_delay_sec` erhöhen.

**`dfs_budget_usd`:** Kostendeckel für DataForSEO je Lauf in US-Dollar. Default 10.0, konservativ gewählt, weil der reale Wert erst nach dem ersten Lauf bekannt ist (Spec Abschnitt 20).

## Secrets (.env)

Secrets stehen in zwei Dateien, nie in der Config und nie in Git.

Zentral, einmal je Rechner, `~/.config/ptai-ecom/.env` (Rechte `600`):

```
PTAI_PSI_KEY=<API-Key>
PTAI_DFS_LOGIN=<DataForSEO-Login>
PTAI_DFS_PASSWORD=<DataForSEO-API-Passwort, nicht das Konto-Passwort>
PTAI_OPENAI_KEY=<optional, GEO über die ChatGPT-API>
PTAI_PERPLEXITY_KEY=<optional, GEO über die Perplexity-API>
PTAI_GEMINI_KEY=<optional, GEO über Gemini-Grounding>
PTAI_ACCOUNTS_ROOT=<optional, Ordner mit den Kundenordnern, Vorgabe ~/ptai-ecom/accounts>
PTAI_OPERATOR_NAME=<optional, eigener Name oder Firmenname in Maßnahmen und Report, Zeile Unternehmen>
PTAI_OPERATOR_CONTACT=<optional, Zeile Ansprechpartner im Schluss von Audit, Monats-Report und audit-light>
PTAI_OPERATOR_EMAIL=<optional, Zeile E-Mail im Schluss von Audit, Monats-Report und audit-light>
PTAI_OPERATOR_BOOKING_URL=<optional, Terminlink mit https://, Zeile Termin im Schluss von Audit, Monats-Report und audit-light>
PTAI_CLOSING_FILE=<optional, Pfad zur eigenen Schlussseite als HTML-Datei, ersetzt den Schluss aus den Zeilen>
```

Im Workspace, je Kunde, `<workspace>/.env`:

```
PTAI_GOOGLE_CREDENTIALS=<workspace>/secrets/google-sa.json
```

**Suchreihenfolge**

- Umgebung, dann Workspace-`.env`, dann zentrale Datei (`scripts/audit/env.py`).
- Jeder Betreiber-Schlüssel darf zusätzlich in der Workspace-`.env` stehen und hat dort Vorrang, etwa wenn ein Kunde ein eigenes DataForSEO-Konto mitbringt.
- `PTAI_GOOGLE_CREDENTIALS` steht nie zentral.

**DataForSEO**

- `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` sind der Zugang. Das Passwort ist das API-Passwort aus dem Bereich API Access, nie das Konto-Passwort.
- Der Zugang gehört dem Betreiber und steht zentral. Kosten je Kunde werden über den Tag und `reporting/dfs-ledger.jsonl` zugeordnet (Spec Abschnitt 13).
- Das Plugin liest nur diese beiden Namen. `DATAFORSEO_USERNAME` und `DATAFORSEO_PASSWORD` anderer DataForSEO-Tools zählen nicht.
- Stehen sie in der Workspace-`.env`: nur die Namen nennen (`grep -oE '^[[:space:]]*(export[[:space:]]+)?DATAFORSEO_[A-Z_]+' .env`), die Datei nicht ändern. Umtragen macht der Betreiber: Zeilen löschen und den Zugang, falls noch nicht geschehen, zentral eintragen.
- Ein `PTAI_DFS_*`-Paar in der Workspace-`.env` hat Vorrang vor dem zentralen und gehört nur dorthin, wenn der Kunde ein eigenes Konto mitbringt.

**Google Ads**

- Kein eigener Schlüssel; Google hat das Entwicklertoken am 09.09.2026 abgeschafft.
- Auf Betreiberseite zählt nur die Freigabe des Cloud-Projekts für echte Konten (`reference/access.md` Teil A, Schritt 6).
- Der Zugang zum Werbekonto des Kunden ist davon getrennt und kommt vom Kunden.
- Fehlt eines von beidem, meldet `pull-ads` "nicht verfügbar", und der Lauf geht weiter.
- Ein altes `PTAI_GOOGLE_ADS_TOKEN` in einer `.env` wird nicht mehr gelesen und kann stehen bleiben.

**Git-Schutz**

- `.env` muss in der `.gitignore` des Kunden-Workspace stehen. `check_env.sh` prüft das; fehlt der Eintrag, legt der Wizard die Zeile `.env` an, bevor ein Secret geschrieben wird.
- Vor dem Ablegen der Service-Account-JSON `secrets/` in die `.gitignore` **und** in `.git/info/exclude` eintragen (letzteres wirkt sofort und für alle Worktrees, auch vor dem Merge der `.gitignore`-Änderung).
- Mit `git check-ignore -v secrets/google-sa.json` nachweisen, dass die Regel greift; erst danach die Datei dorthin verschieben.

**Service-Account-JSON**

- Liegt immer im Kunden-Workspace unter `secrets/` im Workspace-Root, nie zentral. `PTAI_GOOGLE_CREDENTIALS` zeigt auf `<workspace>/secrets/google-sa.json`.
- Keine Ausnahme: kein `~/.config`, kein anderer zentraler Pfad, auch nicht, wenn dasselbe Dienstkonto mehrere Kunden bedient.
- Ob ein Dienstkonto für alle Kunden genutzt wird oder jeder Kunde ein eigenes bekommt, entscheidet der Betreiber. In beiden Fällen gibt es je Kunde einen eigenen JSON-Schlüssel an diesem Ort.

**Umgang mit Keys**

- Der Nutzer trägt jeden Key selbst in die zentrale Datei oder die Workspace-`.env` ein. Der Wizard fragt nie nach einem Key, weil ein Key im Chat im Sitzungsprotokoll gespeichert wird.
- Der Wizard legt die Datei mit leeren Zeilen an, nennt den Pfad und prüft nach dem Eintragen per Test-Call.
- Nur der Pfad zur Service-Account-JSON darf genannt werden; er ist kein Geheimnis.
- Sonst reicht der Wizard Secrets nur durch: er schreibt den vom Nutzer genannten Pfad in `.env` und nirgendwo sonst hin.
- Key-Werte nie in Ausgaben, Logs oder Zusammenfassungen wiedergeben. Den Inhalt der Service-Account-JSON nicht lesen.
- Logins in Browser oder Konsolen macht immer der Mensch.

## Was ins Repo gehört

- Der Workspace ist meist das Shop-Repo des Kunden.
- Kriterium ist die Wiederholbarkeit, nicht der Ordner: was ein späterer Lauf jederzeit neu ziehen kann, darf ignoriert bleiben.

| Gehört ins Repo | Darf ignoriert bleiben |
|---|---|
| `reporting/config.json` | `reporting/data/<run-id>/` eines **Report**-Laufs |
| `reporting/baseline/` | `reporting/**/*.pdf` (liegt im Kundenordner) |
| `reporting/measures.json` | `reporting/runs/**/proof/` (Belegbilder, liegen im Bucket) |
| `reporting/runs/<run-id>/` | |
| `reporting/data/<run-id>/` eines **Audit**-Laufs | |

- Snapshots eines Report-Laufs dürfen wegfallen; der nächste Lauf zieht sie neu.
- Snapshots eines Audit-Laufs nicht: `crawl.json` und die Core Web Vitals halten den Zustand vor einem Relaunch fest, den danach keine Abfrage wiederherstellt.
- Enthält die `.gitignore` ein pauschales `reporting/data/`: vor dem Audit eine Ausnahme ergänzen, etwa `!reporting/data/*-audit/`.
- Belegbilder (`proof/` im Lauf) sind Shop-Screenshots und gehören nicht ins Kunden-Repo. Ihre Quelle ist der Bucket; `publish` lädt sie mit dem Lauf hoch.
- Die Zeile `reporting/runs/**/proof/` erfasst auch die Bilder älterer Fassungen unter `revisions/`.
- `check_env.sh` prüft das mit `git check-ignore` und meldet jede Abweichung. Ist der Workspace kein git-Repo, meldet der Check auch das; dann wird nichts versioniert.

## Anschluss je Quelle

- Teil 1 verwendet die Abschnitte PSI-Key, DataForSEO und aus GEO "Keys anlegen".
- Teil 2 verwendet die übrigen Abschnitte und die GEO-Entscheidung.

Regeln für jede Durchleitung (intern, nicht dem Nutzer vorlesen):

- kurz und im Imperativ, ein Schritt pro Zeile
- keine Zeitangaben, keine Theorie, keine Vorab-Warnungen
- Fehlerfälle aus "Wenn bei Google etwas klemmt" **nur** zeigen, wenn der passende Fehler auftritt
- der Nutzer sieht nur die Schritte

### Google Service-Account (Basis für GA4 und GSC)

- GA4 und GSC nutzen denselben Service-Account.
- Klick-Anleitung für Google-Cloud-Projekt, die fünf APIs und Dienstkonto mit JSON-Schlüssel: `${CLAUDE_PLUGIN_ROOT}/reference/access.md`, Teil A, Schritte 1 bis 3. Hier nicht wiederholen, damit es nur eine Fassung gibt.
- Dort abschließen. Bestehen Projekt und Dienstkonto schon von einem früheren Kunden: nur einen neuen JSON-Schlüssel für diesen Kunden erzeugen.

Danach:

1. Der Nutzer meldet "Datei ist da". Der Wizard:
   - findet die neue JSON selbst im Downloads-Ordner
   - setzt vorher die Ignore-Regel und prüft sie per `git check-ignore` (Abschnitt Secrets)
   - verschiebt sie nach `<workspace>/secrets/google-sa.json`
   - trägt den Pfad als `PTAI_GOOGLE_CREDENTIALS` in `.env` ein
   - liest aus der Datei nur die Dienstkonto-Mail, sonst nichts
2. Weiter mit den nächsten zwei Abschnitten: die Dienstkonto-Mail (`...@...iam.gserviceaccount.com`, siehe `${CLAUDE_PLUGIN_ROOT}/reference/access.md` Teil A Schritt 3) in GA4 und GSC einladen, jeweils als eigene Durchleitung Schritt für Schritt.

### GA4: Dienstkonto einladen

Eigene Durchleitung nach denselben Regeln.

1. analytics.google.com öffnen, Property der Brand auswählen.
2. Unten links das Zahnrad "Verwaltung" (englisch "Admin").
3. Unter "Property, Property-Zugriffsverwaltung" (englisch "Property access management") auf das Plus, "Nutzer hinzufügen".
4. Dienstkonto-Mail einfügen, Rolle "Betrachter" (englisch "Viewer"), Häkchen "Per E-Mail benachrichtigen" ausschalten (das Konto ist eine Maschine und empfängt keine Mail), speichern.
5. Property-ID (nur die Zahl) unter "Property, Property-Einstellungen" (englisch "Property settings") oben rechts ablesen; der Wizard trägt sie als `ga4_property_id` in die Config ein.

   Direktlink statt Klickweg:
   - Zuerst Konto- und Property-Nummer erfragen. Beide stehen in der Adresszeile, sobald die Property einmal geöffnet ist (`#/a1234567p987654321/...`).
   - Dann den Link anbieten: `https://analytics.google.com/analytics/web/#/a<konto>p<property>/admin`.
   - Nicht `analytics.google.com/analytics/web/#/admin` verwenden; er öffnet die zuletzt genutzte Property statt der Zugriffsverwaltung der richtigen.
6. Nachprüfen:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-ga4/scripts/ga4_pull.py" \
     --property <ga4_property_id> --creds secrets/google-sa.json --check
   ```

   - Pfad aus Schritt 1 des Service-Account-Abschnitts, oder der Pfad aus `PTAI_GOOGLE_CREDENTIALS` in der `.env`, falls abweichend.
   - Fehlerbilder (403, google-auth): Skill `pull-ga4`.
   - Meldet `check_env.sh` zusätzlich einen fehlenden GA4-Tag auf der Live-Site: Hinweis an den Kunden. Ohne Tag misst GA4 nichts; das klärt der Kunde.

### GSC: Dienstkonto einladen

- Eigener Schritt mit eigener Zeile in der Haken-Liste, nicht Teil der Analytics-Runde. Die Search Console hat eine eigene Nutzerverwaltung; ein Analytics-Zugang schaltet dort nichts frei.
- Auch durchführen, wenn Analytics schon eingerichtet ist.
- Nutzer hinzufügen kann nur ein Eigentümer der Property. Wer nur Leserechte hat, sieht unter Einstellungen "You must be a property owner to view or change these settings". Das ist kein Setup-Fehler, sondern der Fall aus Ablauf-Schritt 4: Anforderung an den Kunden.
- Direktlink bei bekannter Property-Form: `https://search.google.com/search-console/users?resource_id=sc-domain%3Abeispielshop.de` (bei einer URL-Präfix-Property die URL-kodierte Adresse einsetzen).

Eigene Durchleitung nach denselben Regeln:

1. search.google.com/search-console öffnen, oben links die Property der Brand auswählen.
2. Links unten "Einstellungen" (englisch "Settings").
3. "Nutzer und Berechtigungen" (englisch "Users and permissions"), Button "Nutzer hinzufügen".
4. Dienstkonto-Mail einfügen, Berechtigung "Uneingeschränkt" (englisch "Full"), damit auch die URL-Inspektion funktioniert, hinzufügen.
5. Der Wizard trägt `gsc_site` in die Config ein, mit der richtigen Property-Form: Domain-Property `sc-domain:example.de`, URL-Präfix-Property `https://example.de/` (mit Schema und Slash).
6. Nachprüfen:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/pull-gsc/scripts/gsc_pull.py" \
     --site <gsc_site> --creds secrets/google-sa.json --check
   ```

   Pfad aus Schritt 1 des Service-Account-Abschnitts, oder der Pfad aus `PTAI_GOOGLE_CREDENTIALS` in der `.env`, falls abweichend.

### Wenn bei Google etwas klemmt

Nur zeigen, wenn der jeweilige Fehler auftritt, nie vorab.

| Fehler | Ursache und Lösung |
|---|---|
| "Service account key creation is disabled" beim Key-Erstellen | Org-Policy `iam.disableServiceAccountKeyCreation` (Googles Secure-by-Default, gesetzt auf der Organisation, nicht auf dem Projekt). Lösung: auf Org-Ebene die Rolle "Organization Policy Administrator" haben, dann im **Projekt** unter "IAM & Admin, Organization policies" den Constraint öffnen, "Override parent's policy", Regel mit "Enforcement: Off", speichern. Es gibt zwei fast gleichnamige Constraints; maßgeblich ist der aus der Fehlermeldung, meist `iam.disableServiceAccountKeyCreation` (Managed Legacy), nicht `iam.managed.disableServiceAccountKeyCreation`. |
| 401 "API keys are not supported by this API" | GA4 oder GSC wurde mit einem API-Key abgefragt. API-Keys haben keine Identität und gelten nur für öffentliche Daten (wie beim PSI-Key); private Property-Daten gibt Google nur an eine eingeladene Identität. Die Console erlaubt trotzdem, einen API-Key anzulegen und auf diese APIs einzuschränken. Zurück zum Service-Account-Weg oben. |
| 403 beim GSC-Test-Call | Fast immer falsche Property-Form in `gsc_site` (GSC-Abschnitt) oder Mail noch nicht als Nutzer eingeladen. |

### PSI-Key (Core Web Vitals)

- Die API ist mit dem Google-Cloud-Projekt aus Teil 1 bereits aktiviert.
- Klick-Anleitung für den Key: `${CLAUDE_PLUGIN_ROOT}/reference/access.md`, Teil A, Schritt 4. Hier nicht wiederholen.

1. Der Nutzer trägt den Key selbst als `PTAI_PSI_KEY` in `~/.config/ptai-ecom/.env` ein, nicht im Chat. Der Key muss **zwei** APIs erlauben: PageSpeed Insights und Chrome UX Report. Ohne die zweite fehlt die Wochenhistorie der Core Web Vitals, und der Abruf meldet 403 "blocked".
2. Nachprüfen:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/pull-cwv/scripts/psi_pull.sh" --check -
   ```

### DataForSEO (Betreiber)

Eigene Durchleitung nach denselben Regeln:

1. Konto auf dataforseo.com anlegen.
2. Im Dashboard unter "API Access" Login und API-Passwort ablesen. Das API-Passwort ist nicht das Konto-Passwort. Es wird nur in den ersten 24 Stunden nach der Anmeldung angezeigt, danach über "Send by e-mail".
3. Der Nutzer trägt beides selbst als `PTAI_DFS_LOGIN` und `PTAI_DFS_PASSWORD` in `~/.config/ptai-ecom/.env` ein, nie im Chat.
4. Nachprüfen (kostenlos, zeigt den Kontostand):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dfs_client.py" --check
   ```

5. Ein Satz zum Guthaben: Das Startguthaben von 1 USD reicht nicht sicher für einen Audit; ein echter Lauf kostete gut 1 USD. Aufladen ab 50 USD, das Guthaben verfällt nicht. Deckel je Lauf: `dfs_budget_usd` in der Config, Vorgabe 10.

Quelle: DataForSEO Help Center, abgerufen am 11.09.2026.

### Shopify

1. CLI installieren, falls `check_env.sh` sie nicht findet: `npm install -g @shopify/cli@latest`.
2. Auth nur starten, wenn ein Mensch vor dem Bildschirm sitzt.
   - `shopify store auth` öffnet die Freigabeseite im Browser und wartet nur kurz auf den Rückruf. Danach bricht es mit "Timed out waiting for OAuth callback" ab, ohne eine später nutzbare URL.
   - Ohne sofortige Bestätigung scheitert der Schritt ohne Meldung, bei jedem Versuch.
   - Wie `capture-screens`: im Vordergrund, vorher ankündigen, nie im Hintergrund starten.
   - Zeigt die Freigabeseite "Oops, something went wrong. Unauthorized Access": meist ist das falsche Konto angemeldet, nicht ein Recht fehlt. Im Browser mit dem Konto mit Store-Zugriff anmelden und den Aufruf wiederholen.
   - Auth für die Store-Domain aus der Config, mindestens `read_reports,read_products`.
   - Es gilt die Scope-Union-Regel der Skill `pull-shopify` (Abschnitt "Scope-Regel"): vor jeder Re-Auth den bestehenden Grant lesen und die Vereinigungsmenge aller Scopes senden, nie nur die zwei Report-Scopes. Der vollständige Ablauf steht dort.
3. Nachprüfen: die drei Prüfungen im Abschnitt "Setup-Check" der Skill `pull-shopify` (CLI-Version, `auth list` enthält die Domain, Mini-Query).

### GEO

Eigene Durchleitung nach denselben Regeln, mit einer Ausnahme von "keine Theorie": vorweg in zwei Sätzen erklären, dass GEO misst, ob die Brand in AI-Antworten von ChatGPT, Perplexity und Google auftaucht (erwähnt ja/nein, als Quelle verlinkt ja/nein, monatlich), und dass klassische SEO-Tools das nicht abdecken.

Dann genau eine Entscheidungsfrage mit Empfehlung:

| Option | Inhalt |
|---|---|
| Per API, empfohlen | drei kleine Keys, einmal angelegt; danach läuft jeder Report vollautomatisch und vergleichbar |
| Per Browser | keine Keys; jeder Report-Lauf arbeitet mit Browser-Sitzungen, ChatGPT braucht den Login des Nutzers |
| Erstmal aus | jederzeit nachrüstbar |

- Die Wahl als `geo_method` in die Config schreiben (`api`, `browser` oder `off`), in Teil 2 je Kunde.
- `api`: nichts weiter, wenn der Check mindestens einen GEO-Key findet (zentral oder im Workspace). Sonst Keys wie unter "Keys anlegen (Teil 1)".
- `browser`: eine Zeile an den Nutzer, dass jeder Report-Lauf die drei Plattformen in Browser-Sitzungen prüft und er sich für ChatGPT vorher selbst einloggt (nie der Agent).
- `off`: nichts weiter.
- Die Wahl gilt für alle Report- und Puls-Läufe; der Report fragt nie nach.
- Ältere Configs ohne `geo_method`: die Skills behandeln sie wie `api`, wenn mindestens ein GEO-Key gesetzt ist, sonst wie `browser`. Ein `/ptai-ecom:setup`-Lauf trägt das Feld nach.

**Keys anlegen (Teil 1)**, drei Stück, jeder einzeln optional:

- Der Nutzer trägt jeden Key selbst in `~/.config/ptai-ecom/.env` ein, nie im Chat.
- Name im jeweiligen Portal: `ptai-ecom`.
- Für getrennten Widerruf je Kunde: eigenen Key mit Kundennamen anlegen und in die Workspace-`.env` eintragen; dort hat er Vorrang vor dem zentralen.

1. OpenAI (`PTAI_OPENAI_KEY`): https://platform.openai.com/api-keys öffnen, "Create new secret key".
2. Perplexity (`PTAI_PERPLEXITY_KEY`): https://www.perplexity.ai/account/api/group öffnen, Key erzeugen.
3. Gemini (`PTAI_GEMINI_KEY`): https://aistudio.google.com/apikey öffnen, "API-Schlüssel erstellen", möglichst über "Create API key in new project". Ein Key in einem bestehenden Projekt kann an dessen Einschränkungen scheitern und antwortet dann mit "Your project has been denied access".
4. Nachprüfen je gesetztem Key:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/check-geo/scripts/geo_api.py" \
     --check <chatgpt|perplexity|google-ai> -
   ```

   - Eine Plattform ohne Key erscheint im Report als "nicht angeschlossen".
   - Keys sind jederzeit über `/ptai-ecom:setup` nachrüstbar; ein fehlender Key blockiert das Setup nicht.

### PDF und Screenshots

- Monats-PDF und Audit-Screenshots brauchen einen headless Browser, bevorzugt die Headless Shell von Playwright; Google Chrome oder Chromium gehen auch.
- Meldet der Check unter Rechner "Browser: weder die Headless Shell von Playwright noch Google Chrome oder Chromium gefunden": `npx playwright install chromium-headless-shell` ausführen. Mehr ist nicht nötig.

## Abschluss

- Wenn die Haken-Liste vollständig ist oder der Nutzer bewusst mit einer Teilmenge weitermacht: ersten Lauf anbieten wie in Ablauf-Schritt 5.
- Für einen neuen Kunden ist das der Audit (Skill `audit`); er friert die Baseline unter `reporting/baseline/01/` ein.
- Danach monatlich der Report (Skill `report`).
- Bei späterem Start wieder `/ptai-ecom:setup` aufrufen; der Wizard beginnt erneut beim Check.
