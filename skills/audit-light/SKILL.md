---
name: audit-light
description: Führt einen E-Commerce-Audit nur anhand der Shop-URL durch, ohne Kundenzugänge, als Lead-Magnet. Bestimmt zuerst den Kundenordner unter PTAI_ACCOUNTS_ROOT und legt einen fehlenden Kunden an, über workos:lead nur, falls installiert, sonst selbst. Zieht dann die vier zugangsfreien Quellen (Crawl, Screenshots, Core Web Vitals, GEO), lässt sechs Linsen parallel darauf laufen, prüft jeden Beleg live gegen die Seite und rendert einen Report im Path-to-AI-CI. Auslöser sind /ptai-ecom:audit-light, ein Audit-Lead aus dem Funnel oder der Wunsch, einen Shop ohne Zugänge zu prüfen. Wiederholbar, hält an keiner Stelle an. Für einen Kunden mit Zugängen ist ptai-ecom:audit die richtige Skill, nicht diese.
---

# audit-light: Audit allein aus der Shop-URL

- Audit für einen Lead, bevor eine Geschäftsbeziehung besteht.
- Verwendet nur öffentlich sichtbare Informationen über den Shop.

| | `audit` | `audit-light` |
|---|---|---|
| Quellen | 15 | die neun ohne Kundenzugang |
| Zugänge | Shopify, GA4, Search Console, Werbekonto | keine |
| Gates | hält an zwei Gates an | hält nirgends an |
| Wiederholung | genau einmal je Shop, eingefrorene Baseline | beliebig oft |

Wird der Lead Kunde, ergänzt `audit --backfill` die sechs Kundenquellen im selben Account.

**Argument:** die `audit-id` eines Funnel-Leads **oder** eine Shop-URL.

```
/ptai-ecom:audit-light 00000000-0000-0000-0000-000000000000   # Lead aus dem Funnel
/ptai-ecom:audit-light https://shop.example.de                # eigener Lauf, ohne Lead
/ptai-ecom:audit-light <arg> --with-dfs                        # die fünf bezahlten Quellen dazu
/ptai-ecom:audit-light <arg> --brand "Beispielshop"            # Marke vorgeben, gilt vor entity.md und Startseite
/ptai-ecom:audit-light <arg> --run 2026-09-07-light          # abgebrochenen Lauf fortsetzen
```

- Normalfall ist die ID. Leads kommen über `/audit/` in die Supabase-Tabelle `audits`; die Zeile enthält Shop-URL, Mailadresse und Eingangsdatum.
- Nur mit der ID findet `audit-light-send` später den Empfänger.
- Eine URL ohne ID ergibt einen Lauf ohne Empfänger: der Report liegt im Account, wird aber nicht verschickt.

---

## Feste Regeln

**Belege**

- Jeder Befund braucht eine Belegstelle: erreichbare URL, wörtliches Zitat von der Seite oder ein benanntes Element. Ohne Beleg kein Befund.
- Wenige belegte Befunde statt vieler unbelegter; der Lead prüft den ersten nach.
- `ok` ist ein gültiges Ergebnis. Ohne Mangel in einem Bereich `ok` vergeben, keine künstliche Warnung.

**Keine Geschäftszahlen über den Shop**

- Umsatz je Seite, Traffic, "Bestseller", "umsatzstärkste Produktseite" sind von außen nicht belegbar und verboten.
- Erlaubt: "prominenteste Seite laut Navigation" mit Beleg, wo sie verlinkt ist.
- Erlaubt: öffentlich belegte Unternehmenszahlen mit Quelle und Jahr.

**Grenzen des HTML**

- Review-Widgets, Siegel, Badges und Galeriebilder erscheinen oft erst im Browser.
- Ein "fehlt"-Befund dazu braucht den Screenshot als Beleg. Ohne Screenshot: weglassen oder als Prüfauftrag mit `confidence: "low"` formulieren.
- Nie "nirgends vorhanden" behaupten, wenn nur die Erstansicht geprüft wurde.

**Keine Vergleichsseiten**

- Der Report empfiehlt nie "[Marke] vs [Wettbewerber]"- oder "[Wettbewerber]-Alternative"-Seiten; Händler lehnen das ab.
- Die Wettbewerbsanalyse geht nur in Positionierung und Markt, nie in Befunde, Triage oder Fahrplan.

**Werkzeuge** (diesen Absatz in jeden Subagent-Prompt kopieren):

- Seitenabrufe über `curl`, Screenshots über `capture-screens`.
- Verboten: `WebFetch` und alle Browser-Werkzeuge (`mcp__Claude_Browser__*`, `mcp__claude-in-chrome__*`). Sie lösen je Domain einen Freigabe-Dialog aus, und ein Lauf berührt die Shop-Domain und ein Dutzend Wettbewerber-Domains.
- Erlaubt: `WebSearch`.

```bash
curl -sSL -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" --max-time 25 <url>
```

---

## Stufe -2: Argument auflösen

Enthält das Argument `://` oder einen Punkt, ist es eine URL. Sonst ist es eine `audit-id`; die Shop-URL kommt dann aus der Datenbank:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/db.mjs" get <audit-id>
```

Aus der Zeile übernehmen:

| Feld | Verwendung |
|---|---|
| `shop_url` | der Shop |
| `email` | Empfänger; Kontext, falls der Kunde angelegt werden muss |
| `created_at` | Eingangsdatum des Leads; Kontext, falls der Kunde angelegt werden muss |

Die `audit_id` kommt in die Lauf-Config, damit `audit-light-send` den Lauf findet.

Steht die Zeile schon auf `sent`, wurde bereits ein Report verschickt. Das ist erlaubt, aber vor dem Start melden.

## Stufe -1: Kunde auflösen

- Kein Lauf ohne Kundenordner; Ergebnisse gehören zum Kunden, nicht in ein Repo.
- Kundenordner liegen unter `PTAI_ACCOUNTS_ROOT`, Vorgabe `~/ptai-ecom/accounts`.
- Suchreihenfolge wie bei jedem Betreiber-Wert: Umgebung, `.env` im aktuellen Verzeichnis, `~/.config/ptai-ecom/.env`.

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.account '<shop-url>'
```

| Ergebnis | Was zu tun ist |
|---|---|
| `exact`, `subdomain` | weiter mit `slug` und `drive_path` aus der Ausgabe |
| `none` | anlegen, ohne Rückfrage: über `workos:lead`, falls installiert, sonst selbst, siehe unten |
| `ambiguous` | **abbrechen und melden**, siehe unten |
| Exit 4 | **abbrechen** und die Meldung zeigen: `PTAI_ACCOUNTS_ROOT` zeigt auf keinen Ordner |

### Kein Kunde, `workos:lead` installiert

Ist `workos:lead` installiert, recherchiert sie und legt den Ordner an. Der Lauf hält
dabei nicht an. Ihre drei sonstigen Rückfragen sind bei einem Funnel-Lead schon entschieden und werden vorgegeben:

| Was sie sonst fragt | Was hier gilt |
|---|---|
| Firmenname und Quelle | Quelle ist der Audit-Funnel. Die Firma steht im Impressum der Shop-Domain; die Domain ist eindeutig. |
| warm oder kalt, `entity_type`, `status` | Eingehender Lead (Formular selbst ausgefüllt): `entity_type: lead`, `status: kontaktiert`, `letzter_kontakt` = Eingangsdatum |
| Widersprüche zu Gesprächsnotizen | Entfällt, der Account ist neu. |

Diesen Auftrag mit den Werten aus Stufe -2 übergeben:

> Funnel-Lead aus dem Audit-Formular auf path-to-ai.com. Shop `<shop_url>`,
> Absender `<email>`, eingegangen am `<created_at>`. Lege den Account an mit
> `entity_type: lead`, `status: kontaktiert`, `source: Audit-Funnel
> path-to-ai.com/audit/`, `letzter_kontakt: <created_at>`, `domains: <host>`.
> Bestimme die Firma aus dem Impressum von `<shop_url>`; das ist die maßgebliche
> Quelle, die Domain ist eindeutig. **Stell keine Rückfragen.** Nicht Belegbares
> als "nicht gefunden" eintragen und am Ende in einer Zeile nennen.

- Lücken kommen in die `entity.md` und in die Übergabe am Ende, nicht in eine Rückfrage während des Laufs.
- Mit `workos:lead`, falls installiert, recherchiert diese Skill selbst keine Firmendaten: Auftrag übergeben, auf den fertigen Ordner warten, erneut auflösen.
- Bleibt es danach bei `none`, schreibt `workos:lead` in einen anderen Ordner als `PTAI_ACCOUNTS_ROOT`: abbrechen und beide Ordner nennen, keinen zweiten Kunden anlegen.

### Kein Kunde, `workos:lead` nicht installiert: selbst anlegen

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.account create '<shop-url>' [--brand='<marke>']
```

- Das Skript löst erneut auf und legt nur bei `none` an: `<PTAI_ACCOUNTS_ROOT>/<slug>/entity.md` mit der Marke als Überschrift und dem Host unter `domains:`.
- Slug ist das Label vor der Endung: `shop.beispiel-shop.de` wird `beispiel-shop`.

Herkunft der Marke, in dieser Reihenfolge:

1. `--brand`
2. bei einem vorhandenen Kunden die Überschrift seiner `entity.md`
3. bei einem neuen Kunden die Startseite: `og:site_name` oder der erste Teil des `<title>`, genau einmal vor dem Anlegen abgerufen

- `check-geo` sucht in den AI-Antworten nach genau diesem Namen.
- Die Zeile `marke aus:` nennt die Herkunft. `marke aus: slug` bedeutet: Startseite war nicht lesbar; Stufe 0 korrigiert das.

| Exit | Was zu tun ist |
|---|---|
| 0 | weiter mit `slug` und `drive_path` aus der Ausgabe |
| 3 | **abbrechen**: der Kundenordner für diesen Slug existiert schon, siehe unten |
| 4 | **abbrechen**: `PTAI_ACCOUNTS_ROOT` zeigt auf keinen Ordner |

### Mehrdeutig oder belegt: Fehler, keine Frage

- `ambiguous`: zwei `entity.md` beanspruchen dieselbe Domain. Das ist ein kaputter CRM-Zustand, keine Audit-Entscheidung; der Lauf würde Daten eines Kunden in den Ordner eines anderen schreiben. Abbrechen, beide Slugs nennen; der Betreiber bereinigt.
- Exit 3 beim Anlegen: zwei Shops teilen das Label vor der Endung, etwa `beispiel.de` und `beispiel.at`. Ob der Host in die `domains:` des vorhandenen Kunden gehört (in der Listenform der Datei) oder ein eigener Kunde mit Suffix `-2` wird, lässt sich nicht automatisch entscheiden. Nicht fragen, abbrechen und die Meldung unverändert weitergeben; sie nennt beide Wege.

### Kundenordner und Arbeitsverzeichnis

- `<account_dir>` ist ab hier der `drive_path` aus der Ausgabe oben, ein absoluter Pfad. Er enthält `audit-runs/`, `material/` und `deliverables/`.
- Jetzt dorthin wechseln:

```bash
cd "<account_dir>"
```

- Grund: die Pulls lesen auch eine `.env` im aktuellen Verzeichnis. Aus einem Kunden-Workspace gestartet, würde der Lauf dessen Schlüssel für einen fremden Lead verwenden, etwa dessen eigenes DataForSEO-Konto.
- Alle Aufrufe unten laufen in `<account_dir>`. Bei Übergabe an einen Subagenten `cd "<account_dir>" &&` voranstellen; Subagenten erben das Verzeichnis nicht.
- Lauf-Ordner: `<account_dir>/audit-runs/<heute>-light/`. Existiert er schon und fehlt `--run`, `-2` anhängen; ein zweiter Lauf am selben Tag überschreibt nie den ersten.

---

## Stufe 0: Aufnahme

- Keine Agents. Vier Skripte erzeugen die gemeinsame Datengrundlage aller Linsen, damit alle Linsen von denselben Daten ausgehen.

**1. Lauf-Config bauen.** Ersetzt die `reporting/config.json`, die ein Lead nicht hat.

```bash
python3 -c "
import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import lightconf
cfg = lightconf.build('<shop-url>', '<slug>', brand=<'<marke aus --brand>' oder None>, with_dfs=<True|False>, audit_id='<audit-id oder None>')
lightconf.write(cfg, '<run>/run-config.json')
"
```

**2. Crawl zuerst**, weil die Seitentypen aus ihm kommen.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
  --domain https://<host> --out "<run>/data" --max-urls 300
```

- `--domain` braucht die vollständige URL mit Schema, nicht den Host. Mit `beispielshop.de` scheitert jeder Abruf mit `unknown url type: 'beispielshop.de'`, und `crawl.json` enthält eine einzige Seite mit Status `error`.
- Das Script meldet auch dann Erfolg, mit "1 URLs, 0 mit Status 200".
- Nach dem Crawl `summary.url_count` und `summary.status_code_distribution` prüfen, bevor es weitergeht.
- `--max-urls 300` statt 5000 wie im großen Audit: Tiefe vor Breite, und ein unbegrenzter Crawl kostet ein Vielfaches des übrigen Laufs.

**3. Seitentypen ergänzen und GEO-Fragen ableiten**, beides ohne Rückfrage.

- Grundlage aus dem Crawl: Titel und Beschreibung der Startseite, Kategorienamen, ein bis zwei Produkttitel.
- Drei Kategoriefragen: wonach jemand sucht, der die Marke nicht kennt.
- Drei Problemfragen: das Problem, das die Produkte lösen.
- Beide **ohne Markennamen**, in der Sprache des Marktes.
- Beispiel Massagegeräte: Kategorie "Welche Marken für Faszienrollen taugen etwas?", Problem "Was hilft gegen Nackenverspannungen im Homeoffice?". Nicht "Ist Wohlfuehlbad gut?"; das ist die Markengruppe und schon enthalten.
- Die gesetzten Fragen gehören in den Report unter Quellen und Methodik; sie sind die Messvorschrift der GEO-Zahl.

```bash
python3 -c "
import sys, json; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import lightconf
cfg = json.load(open('<run>/run-config.json'))
cfg = lightconf.add_page_types(cfg, '<run>/data/crawl.json')
cfg = lightconf.set_geo_queries(cfg,
    ['<Kategoriefrage 1>', '<2>', '<3>'],
    ['<Problemfrage 1>', '<2>', '<3>'])
lightconf.write(cfg, '<run>/run-config.json')
print(lightconf.missing(cfg))
"
```

- Gibt `missing()` etwas zurück, ist der Lauf noch nicht bereit. Leere Liste: weiter.
- Der Lauf hält hier nicht an und fragt nichts; er entscheidet und dokumentiert die Entscheidung.
- War in Stufe -1 `marke aus: slug`, ist `brand` nur der Slug. Dann vor `check-geo`:
  1. Marke aus Titel und Impressum im Crawl ablesen.
  2. In `run-config.json` `brand` und `geo_queries.brand` neu setzen (`lightconf.brand_queries('<marke>', '<host>')`).
  3. Überschrift in `<account_dir>/entity.md` angleichen.
  Sonst misst GEO die Sichtbarkeit eines Slugs statt einer Marke.

**4. Betreiber-Schlüssel prüfen.** `pull-cwv` und `check-geo` brauchen sie; ein Lead-Lauf hat keinen Workspace als Quelle.

```bash
cd "<account_dir>" && python3 -c "
import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import env; env.export_env('<account_dir>')
for name, origin in env.status('<account_dir>'): print(f'{name:<26} {origin}')
"
```

- Quelle `~/.config/ptai-ecom/.env`; Reihenfolge: Umgebung, `.env` im Kundenordner, zentrale Datei.
- Einstellungen wie `PTAI_ACCOUNTS_ROOT` stehen auf `nicht gesetzt`, wenn ihre Vorgabe gilt, und zählen nicht.
- Ein Schlüssel auf `FEHLT`: der Audit läuft trotzdem. Die betroffene Plattform wird `null`, nicht `false`, und der Report weist sie als nicht geprüft aus.
- `FEHLT` ist kein Abbruchgrund, muss aber im Report stehen.

**5. Die drei übrigen Quellen**, parallel, jede über ihre eigene Skill (eigene Fehlerbilder):

| Quelle | Skill | Anmerkung |
|---|---|---|
| Screenshots | `capture-screens` | `checkout_capture: false`, siehe unten |
| Core Web Vitals | `pull-cwv` | Feldwerte vor Laborwerten, `field_data: null` heißt zu wenig Traffic und ist kein Fehler |
| GEO | `check-geo` | misst, ob die Marke in ChatGPT, Perplexity und Google-AI auftaucht |

Die Aufrufe genau so übernehmen; an diesen Stellen entstehen sonst Lücken ohne Fehlermeldung:

```bash
# Core Web Vitals: jede URL ein EIGENES Argument. Ein String mit Leerzeichen
# kommt als eine einzige URL an, das Script misst dann eine Seite statt fünf
# und meldet trotzdem Erfolg.
cd "<account_dir>" && bash "${CLAUDE_PLUGIN_ROOT}/skills/pull-cwv/scripts/psi_pull.sh" "<run>/data" - \
  "https://.../" "https://.../collections/x" "https://.../products/y" "https://.../cart" "https://.../blogs/news"

# Screenshots: je Seitentyp ein Aufruf. Das Script schreibt seine Indexzeile als
# `IMAGES_JSON: [...]`, NICHT als nacktes JSON. Wer nach Zeilen sucht, die mit
# "{" beginnen, baut einen leeren Index und merkt es nicht.
cd "<account_dir>" && bash "${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/shoot.sh" \
  --url "<url>" --name "<seitentyp>" --target "<account_dir>/material/<datum>-audit-screenshots"
```

**Cookie-Dialog**

- Auf deutschen Shops ist er auf jeder Aufnahme. Er gehört ins Bild und in die Grenzen.
- Desktop: verdeckt meist nichts Wesentliches. Handy: oft die untere Bildhälfte samt Kaufbereich.
- Was er verdeckt, ist `not_checkable`, nie ein Befund ("kein Kaufbutton auf dem Handy sichtbar" wäre eine Aussage über den Screenshot, nicht über den Shop).
- Der Dialog selbst ist ein eigener Befund für L4, positiv oder negativ.

**Markenname gleich Produktwort**

- Dann ist keine automatische Markennennung verwertbar. Beispiel: auf "Was ist LEDERTASCHE?" erklärt Perplexity, was eine Ledertasche ist, und jede Zählung wertet das als Treffer.
- Vor der Weitergabe der GEO-Zahlen prüfen: steht der Markenname auch als gewöhnliches Wort in den eigenen Kategorienamen, ist `brand_mentioned` unbrauchbar.
- Dann gilt nur `domain_cited`, und der Report nennt den Grund.

**Kaufweg aus**

- `capture-screens` kann den Kaufweg bis zur Zahlungsauswahl durchlaufen, legt dabei aber einen Testwarenkorb mit Platzhalterdaten in der Kasse an. Bei einem kalten Lead ohne Einverständnis nicht; im großen Audit ist der Kunde einverstanden.
- Mit `--checkout` bewusst zuschaltbar.

**Bezahlte Quellen**

- Die fünf DataForSEO-Pulls sind aus, weil der Audit ein kostenloser Lead-Magnet ist.
- Mit `--with-dfs` an. Dann gilt der Deckel `dfs_budget_usd`, und jeder Aufruf wird in `dfs-ledger.jsonl` protokolliert.

**Ausgefallene Quellen**

- Brechen den Lauf nie ab.
- Werden als "nicht verfügbar (Grund)" notiert und erscheinen so im Report unter Quellen und Methodik.
- Ein Lauf mit drei von vier Quellen ist gültig; eine verschwiegene Lücke nicht.

---

## Stufe 1: Sechs Linsen, parallel

- Alle sechs `Agent`-Aufrufe **in einer Nachricht**.
- Jede Linse liest die Snapshots aus `<run>/data/` und die Screenshots aus `<account_dir>/material/` und ruft die Seite nur für eigene Stichproben ab.

| Linse | Prüft | Skill laden, fremde nur falls installiert |
|---|---|---|
| L1 Auffindbarkeit | Indexierbarkeit, Statuscodes, Canonicals, interne Struktur, Product-, Offer-, Organization-, FAQ- und Breadcrumb-Schema | `claude-seo:seo-technical`, `claude-seo:seo-schema` |
| L2 KI-Sichtbarkeit | den GEO-Snapshot deuten, dazu Crawler-Zugang aus der robots.txt und Zitierfähigkeit der Seiten | `claude-seo:seo-geo` |
| L3 Kaufstrecke | Kaufbutton, Verfügbarkeit, Lieferzeit, Versandkosten vor der Kasse, Gastbestellung, Zahlarten, Schrittzahl, Mobil | `ptai-ecom:lens-purchase-path` |
| L4 Vertrauen und Recht | Impressum, Widerruf, AGB, Datenschutz, Preisangaben mit Grundpreis, Versandkostenangabe, Bewertungen am Kaufpunkt, Siegel | `ptai-ecom:lens-trust` |
| L5 Sortiment | Filter und Sortierung, Varianten, Produkttexte, Bildanzahl und -qualität, Cross-Selling, ausverkaufte Artikel | `ptai-ecom:lens-assortment` |
| L6 Markt und Position | Wettbewerberfeld, Positionierungsachsen, Fähigkeiten-Matrix, Marke gegen Startseite und Über-uns | `pm-market-research:competitive-analysis`, `marketing:brand-review` |

- Jeder Agent ruft seine Skill ausdrücklich über das Skill-Werkzeug auf. Nur den Namen im Prompt zu nennen reicht nicht; dann fehlt die Methode.
- `claude-seo:*`, `pm-market-research:competitive-analysis` und `marketing:brand-review` gehören nicht zum Plugin. Fehlt eine, prüft die Linse nach der Spalte "Prüft" ohne sie, und der Report nennt das unter Quellen und Methodik.

**Prompt-Gerüst je Linse** (Werkzeug-Absatz von oben mitkopieren):

> Prüfe den öffentlichen Shop `<domain>` durch eine Linse. Lies zuerst
> `<run>/data/crawl.json` und die weiteren Snapshots, sieh dir die Screenshots
> unter `<account_dir>/material/<datum>-audit-screenshots/` per Read an. Lade die
> Skill `<skill>`, falls installiert, und arbeite nach ihrer Methode, sonst nach
> der Liste, was die Linse prüft.
>
> **Severity:** `crit` ist eine **totale oder strukturelle** Lücke an einem
> Kernsignal (kein zitierfähiger Antwortsatz für die KI-Suche, fehlendes oder
> falsches Produkt-Schema, kein Kauf-Button ohne Scrollen, unsichtbarer Social
> Proof am Kaufpunkt, fehlende Pflichtangabe). `warn` ist ein teilweiser Mangel.
> Die **vollständige Abwesenheit** eines Kernsignals ist nie `warn`.
>
> **Leser ist ein Geschäftsführer, kein SEO.** Jeden Fachbegriff beim ersten
> Auftreten in einem Halbsatz erklären. Neben den Mängeln ein bis zwei belegte
> `ok`-Befunde liefern: was nachweislich funktioniert und bleiben soll.
>
> Schreibe zwei Dateien nach `<run>/findings/`:
>
> `L<n>-<lens>.json` , Array mit genau diesen Feldern je Befund:
> `severity` (crit|warn|ok), `title`, `detail`, `recommendation`, `evidence`,
> `url` (der eine klickbare Deep-Link, bei seitenweiten Funden weglassen),
> `impact`, `effort`, `confidence` (high|medium|low), `lens`.
>
> `L<n>-<lens>.coverage.json`: `{"checked": [...], "not_checkable": [{"what", "reason"}]}`.
> Pflicht: ohne sie sieht eine geblockte Linse im Score aus wie ein guter Shop.

**L4 stellt fest und bewertet nicht juristisch.** Befunde lauten "vorhanden" oder "nicht auffindbar", nie "rechtswidrig". Der Report ist kein Rechtsrat.

---

## Stufe 2: Beleg-Gate

**Ein** Agent, vor jeder Konsolidierung und vor dem Rendern, damit widerlegte Befunde kein Neuschreiben, keine Score-Neuberechnung und keinen zweiten Render erzwingen.

> Lies alle `<run>/findings/L*.json`. Für **jeden** Befund mit `url`:
> 1. Die URL live abrufen (`curl`, siehe Werkzeug-Absatz).
> 2. Claim-Typ bestimmen: *Präsenz* (etwas wird als vorhanden zitiert) oder
>    *Absenz* ("keine FAQ", "fehlt", "0 …").
> 3. Präsenz mit Stellenbezug ("im Title", "im Product-JSON-LD") im **richtigen
>    Element** prüfen, nicht irgendwo auf der Seite. Absenz: prüfen, ob das
>    Element fehlt. Live gefunden heißt Widerspruch.
> 4. **4xx, Bot-Block oder verdächtig kurzer Body sind `unreachable`, nie
>    "bestätigt".** Eine Absenz-Behauptung aus einem fehlgeschlagenen Abruf gilt
>    als unbestätigt.
>
> Schreibe `<run>/verify.json`: je Befund `{title, url, verify, claimType,
> suggestion}` mit `verify` aus `confirmed | quote-not-found | contradicted |
> unreachable`. Zu jedem Nicht-`confirmed` einen Vorschlag: neues Wording,
> `drop`, oder `keep` mit Begründung.

Danach die Vorschläge selbst umsetzen:

| Ergebnis | Wirkung |
|---|---|
| `drop` | Befund entfällt |
| `contradicted` ohne korrigierte Fassung | Befund entfällt |
| `reword` | korrigierte Fassung übernehmen |
| `keep` | bleibt |
| korrigiert nach `contradicted` | weiter mit `confidence: "medium"` |
| aus `unreachable` oder `quote-not-found` | weiter mit `"low"` |

- Nur die übrigen Befunde gehen in Stufe 3.
- Der Betreiber gibt diese Liste nicht frei; das Urteil über Belege gehört zum Audit.

---

## Stufe 3: Konsolidierung und Score

Drei Agents parallel, einer je Säule. Jeder:

1. liest die Befunde seiner Linsen
2. dedupliziert (gleicher Fund aus zwei Linsen wird einer, der beste Beleg bleibt)
3. sortiert nach Wirkung durch Aufwand
4. schreibt ein Kapitel-Intro von zwei bis vier Sätzen; **erster Satz: was in diesem Bereich nachweislich gut ist**

| Säule | Linsen | Gewicht |
|---|---|---|
| Akquisition | L1, L2 | 0,30 |
| Conversion Rate Optimierung | L3, L5, dazu die Core Web Vitals | 0,45 |
| Trust und Compliance | L4 | 0,25 |

L6 geht in keinen Score; eine Marktposition ist keine Note. L6 liefert Quadrant, Matrix und das Markt-Narrativ.

**Felder der Säulen-Datei:** dieselben wie bei den Linsen, vollständig: `severity`, `title`, `body`, `evidence`, `recommendation`, `url`, `impact`, `effort`, `confidence`, `lens`. Dazu `persists: true` bei einem Befund, den die Maßnahmen dieses Bereichs nicht beheben. Zwei Felder gehen beim Zusammenführen leicht verloren, ohne Fehlermeldung:

- **`url`** ist der eine klickbare Deep-Link. Der Renderer erzeugt daraus im PDF die Zeile "zur Stelle ansehen"; ohne ihn ist kein Beleg im Report anklickbar.
  - Beim Zusammenlegen zweier Befunde wählt der Agent den Link, der die Sache besser zeigt.
  - Bei einem seitenweiten Fund das Feld weglassen, statt auf eine beliebige Seite zu zeigen.
- **`lens`** enthält genau den kurzen Linsennamen, kleingeschrieben, ohne Präfix: `auffindbarkeit`, `ki-sichtbarkeit`, `kaufstrecke`, `sortiment`, `vertrauen`.
  - Die Score-Engine vergleicht **exakt** (`score.mjs`, `saeuleVon`). Bei "L1 Auffindbarkeit" gehört der Befund zu keiner Säule, jede Säule erhält 100 Punkte, ohne Fehlermeldung.
  - Das Feld `ohne_saeule` in der Score-Ausgabe listet solche Zeilen; nach jedem Lauf prüfen.

**`impact`** ist ein ganzer Satz, kein Stufenwort.

- Der Renderer zeigt ihn im PDF als eigene Zeile mit Label "Wirkung". Ein Wort wie "hoch" wiederholt nur Farbstrich und Schwere-Badge.
- Der Satz beschreibt, was sich geschäftlich ändert, **wenn die Empfehlung umgesetzt ist**, nicht was heute falsch ist.
- Wo möglich an eine Zahl aus demselben Befund knüpfen.

### Ausführliche Befunde als Entscheidungsvorlagen

- Die `topN` Befunde je Kapitel (Vorgabe 4) erhalten zusätzlich `facts`, `proof` und, wo es zwei echte Wege gibt, `decision`.
- Ziel: der Geschäftsführer sieht, was zu entscheiden ist (Entweder-oder), statt eines Absatzes mit Messwerten.
- Vollständiges Format: `reference/finding-format.md`, gemeinsam mit dem vollen Audit und dem Kundenportal. Hier steht die Kurzfassung für audit-light; bei Widerspruch gilt `reference/finding-format.md`.
- `body`, `recommendation`, `impact` und `evidence` bleiben gefüllt. Sie stehen im PDF zugeklappt unter "+ Herleitung und Belege" und im Portal zum Aufklappen.

Neue Felder, die der Leser zuerst sieht:

- **`facts`**: zwei bis vier Zeilen `{label, text}`, je höchstens 160 Zeichen, je ein ganzer Satz.
  - `WARUM ES ZÄHLT` ist Pflicht und nennt die Folge für den Kunden, nicht den Mechanismus.
  - Nach Bedarf `URSACHE`, `VORHANDEN`, `OFFEN`, `NÄCHSTER SCHRITT`.
  - Was ohne Entscheidung sofort umsetzbar ist: `{now: true, text}`, wird zu "SOFORT UMSETZBAR".
  - Statt Label auch `{kind, text}` mit `effect`, `cause`, `present`, `open` oder `next`; der Renderer setzt das Label, das Portal liest dieselbe Datei.
- **`proof`**: der Beleg als Bild, `{columns: [{label, blocks: [...]}]}`, eine oder zwei Spalten. Jede Zahl darin ist gemessen. Blocktypen:
  - `metric` `{value, unit, label}`
  - `note` `{text}`
  - `quote` `{text, source}` (mit `<ins>` für eine vorgeschlagene Ergänzung, `<mark>` für eine Abweichung)
  - `chips` `{groups: [{label, items, own}]}`
  - `rows` `{rows: [{label, sub, text|quote}]}`
  - `pairs` `{rows: [{from, to}]}`
  - `grid` `{columns, rows: [{label, cells}]}` mit Zellen `both|brand|other|domain|none|x|check`
  - `dist` `{total, parts: [{value, label, tone}]}`
  - `image` `{src, alt, rings, addition, caption}`
  - `phone` `{src, width, height, fold, markers: [{y, label, text}]}`; steht ein `phone` vorn, stehen Kennzahlen und `facts` rechts daneben.
- **`decision`**: nur bei zwei echten, verschiedenen Wegen, nie Pflicht: `{question, options: [{title, text, effort, result, image}, {…}], recommended: 0|1, reason}`.
  - `question` ist ein ganzer Satz mit "oder".
  - `reason` beginnt mit dem empfohlenen Buchstaben ("A, weil …") und hat einen Satz.
  - Typisch zwei bis vier Entscheidungen im ganzen Report, nicht eine je Befund.
  - Nur eine sinnvolle Maßnahme: keine `decision`, sondern eine Zeile `SOFORT UMSETZBAR`.

Belegbilder:

- Als Dateien, `src` relativ zur `content.json` oder absolut; der Renderer bettet sie ein.
- Für Handy und Kaufbereich nur Aufnahmen ohne Cookie-Dialog (Stufe 4).
- Befund mit `decision`: eigene Seite im PDF. Ohne: kompakt.
- Länge: Befund mit Entscheidung höchstens eine Seite, kompakter Befund höchstens eine halbe.

### Herkunftslisten

Jede Säulen-Datei hat zwei getrennte Listen, nie gemischt:

| Feld | Inhalt | Im PDF |
|---|---|---|
| `skills` | Skills, die die Linsen in Stufe 1 **über das Skill-Werkzeug geladen haben**, mit vollem Namen (`claude-seo:seo-technical`, `ptai-ecom:lens-trust`) | "Geprüft mit" |
| `methoden` | Messgrundlage: was geprüft wurde und woher die Zahlen kommen | "Grundlage" |

Die geladenen Skills aus den Agenten-Protokollen des Laufs ermitteln, nicht aus dem eigenen Prompt übernehmen; sonst erscheint ein Agent als geprüft, der die Skill nie aufgerufen hat:

```bash
for f in <agent-ids>; do printf "%-20s " "$f"
  grep -o '"name":"Skill","input":{"skill":"[^"]*"' \
    "$HOME/.claude/projects/<projekt>/<session>/subagents/agent-$f.jsonl" \
    | sed 's/.*skill":"//' | sort -u | tr '\n' ' '; echo; done
```

### Score

Den Score berechnen lassen, nie schätzen. Zweites Argument ist `<run>/findings/`, der Ordner mit den `L<n>-<lens>.coverage.json`-Dateien aus Stufe 1; ohne ihn bleibt `coverage` leer, und die Abdeckungs-Regel greift nicht:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/score.mjs" <run>/findings.json <run>/findings
```

**Abdeckungs-Regel**

- Meldet ein `coverage.json` seine Pflicht-Checks als nicht ausführbar, bekommt die Säule keinen Score, sondern eine im Report ausgewiesene Lücke.
- Grund: die Engine rechnet 100 minus Strafpunkte, ohne Boden und Deckel; eine geblockte Linse käme sonst auf den Höchstwert.

---

## Stufe 4: Report

`content.json` schreiben (Struktur exakt wie `${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/report-content.sample.full.json`), dann rendern:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/render.mjs" \
     "<run>/content.json" "<run>/report.html"
bash "${CLAUDE_PLUGIN_ROOT}/skills/report/scripts/render_pdf.sh" \
     "<run>/report.html" "<run>/report.pdf"
mkdir -p "<account_dir>/deliverables"
cp "<run>/report.pdf" "<account_dir>/deliverables/<datum>-path-to-ai-ecom-audit-<domain>.pdf"
```

**Dateiname des Deliverables**

- Der Name erscheint beim Empfänger, wenn das PDF weitergeschickt wird.
- Festes Schema, gleich in allen Report-Skills: **Datum, Absender und Dokumentart, Domain**, also `2026-09-20-path-to-ai-ecom-audit-beispielshop.de.pdf`.
- Die Domain bleibt mit Punkt lesbar.
- `<datum>` ist das Datum des Laufs, nicht das Datum des Kopierens.
- Im Lauf-Ordner heißt die Datei weiter `report.pdf` (Arbeitsstand).
- An den Betreiber immer die Datei aus `deliverables/` schicken oder verlinken, nie die aus dem Lauf-Ordner.
- `audit-light-send` verwendet denselben Namen für den Mailanhang; `send-report.mjs` bildet ihn aus `content.json`. Damit dort das Lauf-Datum statt des Versanddatums steht, enthält `content.json` das Feld `meta.datei_datum` mit dem Datum des Laufs.

**Seite "Entscheidungen"**

- Erzeugt der Renderer selbst, sobald ein Befund eine `decision` hat (Stufe 3).
- Steht hinter der Zusammenfassung: alle Entscheidungen, je Zeile Frage, Herkunft und beide Wege, Vorschlag markiert.
- Die Seite "Worauf es jetzt ankommt" (`triage`) entfällt dann; ihre Spalte "Nicht verfolgen" geht auf die Entscheidungsseite.
- Gezielt setzen: `decisions.avoid` als `[{title, text}]`. Sonst liest der Renderer die triage-Spalte, deren Label "NICHT" oder "IGNOR" enthält, mit Einträgen der Form "Titel: Satz".
- `decisions.headline`, `decisions.lead` und `decisions.pointer` überschreiben bei Bedarf die Vorgaben.

**Belegbilder vom Handy nur ohne Cookie-Dialog**

- Die Aufnahmen aus Stufe 0 zeigen die Erstansicht; auf dem Handy verdeckt der Dialog dort oft die ganze Seite.
- Für `proof` die Seiten ein zweites Mal aufnehmen, mit abgelehntem Dialog, für den Belegtyp `phone` gleich als Streifen in der gezeigten Höhe:

```bash
PY=$(for p in "$PTAI_PLAYWRIGHT_PYTHON" python3 python3.11 /opt/homebrew/opt/python@3.11/bin/python3.11; do
  [ -n "$p" ] && "$p" -c 'import playwright' 2>/dev/null && echo "$p" && break; done)
cd "<account_dir>" && "$PY" "${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/shoot_declined.py" \
  --target "<account_dir>/material/<datum>-audit-screenshots" \
  --url start=<url> --url product=<url> --url collection=<url> --strip product=1800
```

- Meldung "Kein Ablehnen-Knopf gefunden": das Consent-Tool ist unbekannt. Knopf im HTML suchen, Selektor in `DECLINE_SELECTORS` ergänzen, neu aufnehmen.
- Nie eine Aufnahme mit Dialog als Beleg verwenden.

**Letzte Seite**

- Kommt nicht aus `content.json`; ein Feld `closing` in `content.json` wird ignoriert.
- `PTAI_CLOSING_FILE` gesetzt: `render.mjs` setzt diese Datei unverändert als Schlussseite ein, dieselbe wie im Audit und im Monats-Report.
- Ohne die Einstellung: neutraler Schluss mit einer Kontaktzeile je gesetztem und gültigem Wert aus `PTAI_OPERATOR_NAME`, `PTAI_OPERATOR_CONTACT`, `PTAI_OPERATOR_EMAIL` und `PTAI_OPERATOR_BOOKING_URL`, darunter die Herkunftszeile.
- Suchreihenfolge: Umgebung, dann zentrale Datei (`PTAI_ENV_FILE`, sonst `~/.config/ptai-ecom/.env`); dieser Lauf hat keinen Workspace.
- Datei fehlt, nicht lesbar oder leer: `render.mjs` schreibt eine Zeile auf stderr und rendert den neutralen Schluss.
- Der Kleindruck zur Datengrundlage steht am Ende der letzten Inhaltsseite davor. Er endet mit `© <Jahr> <PTAI_OPERATOR_NAME>.`, gesucht wie der Schluss; ohne ausdrücklich gesetzten Namen entfällt dieser Satz.

**Sieben Feldfehler, die den Report zerstören:**

- **`market.callouts[].value` ist eine kurze Zahl, keine Überschrift.** Der Renderer setzt sie im Display-Schnitt über die halbe Spalte; ein Titel darin wird riesig und mitten im Wort abgeschnitten. Richtig: `"0"` mit `unit: "von 6"`, der Satz gehört in `body`.
- **Doppelt maskierte Zeichen aus den Subagents auflösen.** `&amp;` in einem Feld erscheint im PDF als `Muster &amp; Muster GbR`. Vor dem Rendern einmal über `content.json` gehen.
- **`meta.erstelltFuer` ist die Firma, nicht die Domain.** Fehlt es, nimmt der Renderer `shop`, und im Kopf jeder Seite steht eine URL statt eines Namens.
- **`chapters[].effort` ist ein Label, kein Satz.** Es erscheint im PDF nicht mehr; neben dem Befundtitel steht die Schwere. Feste Werteliste: Sehr gering, Gering, Gering bis mittel, Mittel, Gering bis hoch, Hoch, Kein Handlungsbedarf. Den Umfang des Aufwands ans Ende der `recommendation` schreiben.
- **`sources.groups[].items` sind Objekte mit `label`, keine Zeichenketten.** Der Renderer liest `it.label` und optional `it.url`. Eine Liste aus Strings ergibt leere Zeilen mit Trennlinien unter den Gruppentiteln, ohne Fehlermeldung.
- **HTML gilt nur in den Feldern, die der Renderer durch `safeHtml` schickt:** `cover.intro`, die Absätze in `exec.summary`, `chapters[].intro`, `chapters[].about`, `chapters[].findings[].body`, die Absätze in `market.narrative`, `market.callouts[].body`, `matrix.intro`, `matrix.takeaway`, `positioning.intro`, `positioning.positioningLine`, `geoGrid.intro` und `fahrplan.proj.text`. **Alles andere wird maskiert**; `<b>` und `<i>` erscheinen dort als sichtbarer Code. Betrifft auch `sources.methodik` und `evidence`: in einem Beleg das Element benennen und seinen sichtbaren Text zitieren, nicht sein Markup; die Zieladresse gehört in `url`.
- **`exec.teaserFindings` ist Pflicht, obwohl der Renderer es nicht ausgibt.** Es füllt den Drei-Punkte-Block der Teaser-Mail in `audit-light-send`; fehlt es, geht die Mail ohne Meldung mit leerem Block raus. Drei Einträge `{title, body}`, `body` ein bis zwei Sätze, **reiner Plaintext**: die Mail maskiert HTML und würde Tags als Text zeigen.

**Zeichenbudgets für einleitenden Fließtext**, vor dem Rendern zählen:

| Feld | Budget |
|---|---|
| `cover.intro` | bis 200 |
| jeder Absatz in `exec.summary` | bis 250, bei zwei Absätzen |
| jeder `chapters[].intro` und `geoGrid.intro` | bis 250 |
| jeder Absatz in `market.narrative` | bis 400 |
| Befundtexte | kein Budget |

**Fünf Blöcke für Zahlen statt Fließtext.** Alle optional. Jede Zahl darin ist im Lauf belegt, keine geschätzt.

- **`chapters[].signals`**: drei bis vier Kacheln je `{value, unit, label}`, unter der Kapitelüberschrift als Leiste "Was hier trägt".
  - Ersetzen die Stärken-Befunde als Text; ein `ok`-Befund braucht als Block so viel Platz wie ein kritischer.
  - Nach dem Setzen der Kacheln die `ok`-Befunde aus `findings` entfernen.
  - Eintrag ohne gemessene Zahl: keine Kachel, bleibt ein Befund.
- **`chapters[].bars`** mit `chapters[].barsTitle`: zwei bis vier Einträge je `{label, value, total, tone}`, `tone` aus `good`, `bad`, `neutral`.
  - Der Balken zeigt Zähler und Nenner im Klartext daneben.
  - Ein Anteil ohne belegten Nenner wird nicht gezeichnet.
- **`geoGrid`** auf oberster Ebene: Raster der KI-Sichtbarkeit, je Frage eine Zeile, je Plattform eine Spalte, Zellwerte `both`, `brand`, `other`, `domain`, `none`.
  - Muster über viele Antworten gehören in das Raster, nicht in einen Absatz.
  - Aufbau aus `geo.json > queries` über `brand_mentioned` und `domain_cited`, nie aus dem Fließtext eines früheren Reports.
  - Zellwert `other`: Marke genannt, als Quelle aber fremde Seiten (`other_citations` nicht leer, `domain_cited` false).
  - `brand`: Antworten ganz ohne Quellenliste.
  - Farben: Blau-Abstufung, je dunkler desto besser; rot nur `other`, der Zustand mit Handlungsbedarf.
- **`chapters[].score` und `chapters[].target`**: Bereichswert im Kapitelkopf, in der Optik der Säulenkarte auf Seite eins. Werte aus demselben Lauf der Score-Engine wie `exec.scores`, nie von Hand.
- **`chapters[].about`**: zwei bis drei Sätze direkt unter der Kapitelüberschrift, vor dem Score, für jedes Kapitel.
  - Inhalt: was der Bereich ist, was geprüft wurde, was das Kapitel enthält.
  - Kein Befund, keine Zahl, kein Urteil; das steht in `intro` darunter.
  - HTML wie in `intro`.
- **`chapters[].methoden`**: fünf kurze Einträge, nicht sieben lange. Steht am Kapitelende nach den Befunden, wie eine Quellenangabe. Ausführliches gehört in "Quellen und Methodik".

**Score auf den konsolidierten Befunden**

- Die Säulen-Agents in Stufe 3 führen Dubletten zusammen. `findings.json` aus Stufe 1 in die Engine zu geben, zählt jede Dublette doppelt.
- Score-Eingabe aus `chapters[].findings` bauen und jedem Eintrag seine `confidence` mitgeben; sonst rechnet die Engine mit dem Vorgabewert 0,7.

**Inhaltliche Regeln für den Report**

- **Kein Tech-Jargon in der Außenschicht** (`cover`, `exec`, `scores[].caption`, `market.callouts`): kein "JSON-LD", "Canonical", "DOM", keine Selektoren, keine Dateinamen. Technische Details gehören in die Befunde.
- **Der Aufmacher bezieht sich auf den stärksten Einzelfund**, nicht auf eine allgemeine These, und ist nie ein Vorwurf. Form: schlichter Satz mit Gegenstand und Zahl, wie eine Fachperson einen Befund benennt, kein zugespitzter Gegensatz.
- **Das Cover hat immer einen Aufmacher zum stärksten Befund**, nie eine Dokumentzeile. Die Übergabe legt ihn dem Betreiber zur Bestätigung vor.
- **Die Zusammenfassung argumentiert.** `exec.headline` nennt den stärksten Befund. `exec.summary` hat zwei Absätze: was funktioniert, dann das Muster der Lücken, beide mit Zahlen. Nie mit dem Prüfumfang beginnen ("Ich habe ... durchgesehen"); der steht unter Quellen und Methodik.
- **Scoring bleibt `exec.scoreStyle: "potenzial"`.** Eine andere Darstellung entscheidet der Betreiber.
- **Bereichsnamen wie im ausführlichen Audit:** Akquisition, Conversion Rate Optimierung, Trust und Compliance, darunter "Ziel X nach Umsetzung der Maßnahmen in diesem Bereich". Keine eigenen Namen wie "Gefunden werden" oder "Kaufen".

---

## Übergabe

1. Das Beleg-Gate hat in Stufe 2 entschieden. In einem Satz nennen, wie viele Befunde korrigiert und wie viele gestrichen wurden, ohne Liste zur Freigabe. `verify.md` bleibt als Beleg im Lauf-Ordner.
2. `<run>/report.pdf` öffnen und prüfen:
   - Jeder Befund belegt, jeder Beleg anklickbar?
   - Keine Umsatz- oder Traffic-Behauptung über eine Einzelseite?
   - Kein "sichtbares Element fehlt" ohne Screenshot-Beleg?
   - Jedes Kapitel mit mindestens einem Stärken-Befund?
   - "Quellen und Methodik" nennt die Sichtprüfung mit Datum und die GEO-Fragen?
   - Alles im A4-Layout, nichts abgeschnitten?
3. Wenn alles passt: `/ptai-ecom:audit-light-send <audit-id>`.

---

## Fehlerbilder

| Fall | Vorgehen |
|---|---|
| `audit.account` liefert `ambiguous` | Zwei Kunden haben dieselbe Domain. Nicht raten, den Betreiber fragen; meist ist einer eine Dublette. |
| `audit.account create` endet mit 3 | Kundenordner für den Slug existiert schon. Die Meldung nennt beide Wege; der Betreiber entscheidet manuell. |
| `audit.account` endet mit 4 | `PTAI_ACCOUNTS_ROOT` zeigt auf keinen Ordner. Pfad prüfen; bei einem Cloud-Ordner prüfen, ob er eingebunden ist. |
| `missing()` meldet `page_types` | Crawl lief nicht oder schrieb kein `crawl.json`. Ohne Seitentypen misst `pull-cwv` nur die Startseite. |
| `check-geo` oder `pull-cwv` melden "nicht angeschlossen" | Schlüssel fehlt. `python3 -m audit.env` zeigt je Schlüssel die Quelle, nie einen Wert. Fehlt er auch zentral, nach `~/.config/ptai-ecom/.env` eintragen. Betroffene Plattform wird `null`, nicht `false`, und der Report weist sie als nicht geprüft aus. Kein Abbruchgrund. |
| Chrome beendet sich nach dem PDF nicht | Bekannt, `render_pdf.sh` fängt es ab. Existiert das PDF und ist größer als 20 KB, war der Render erfolgreich. **Nicht ein zweites Mal rendern**, den Prozess nicht beenden und neu starten; das hat bereits einen Incident verursacht. |
| Lauf bricht mittendrin ab | Mit `--run <id>` im selben Ordner fortsetzen. Vorhandene Snapshots werden nicht neu gezogen, bezahlte Aufrufe also nicht doppelt bezahlt. |
