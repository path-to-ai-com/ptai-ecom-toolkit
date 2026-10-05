---
name: audit-light
description: E-Commerce-Audit allein aus der Shop-URL fahren, ohne Kundenzugänge, als Lead-Magnet. Löst zuerst den Kundenordner unter PTAI_ACCOUNTS_ROOT auf und legt einen fehlenden Kunden an, über workos:lead nur, falls installiert, sonst selbst, zieht dann die vier zugangsfreien Quellen (Crawl, Screenshots, Core Web Vitals, GEO), lässt sechs Linsen parallel darauf laufen, prüft jeden Beleg live gegen die Seite und rendert einen Report im Path-to-AI-CI. Nutzen bei /ptai-ecom:audit-light, bei einem Audit-Lead aus dem Funnel, oder wenn der Nutzer einen Shop prüfen will, zu dem er keine Zugänge hat. Wiederholbar, hält nirgends an. Für einen Kunden mit Zugängen ist ptai-ecom:audit der richtige Skill, nicht dieser.
---

# audit-light: Audit allein aus der Shop-URL

Der Audit für einen Lead. Er kennt vom Shop nur, was jeder sehen kann, und genau
das ist sein Zweck: er läuft, bevor eine Geschäftsbeziehung existiert.

**Abgrenzung zu `audit`.** Der große Audit zieht 15 Quellen, hält an zwei Gates
an, läuft genau einmal je Shop und schreibt eine eingefrorene Baseline. Er
braucht Shopify, GA4, Search Console und ein Werbekonto. Dieser Skill zieht die
neun Quellen, die ohne Kundenzugang auskommen, hält nirgends an und ist beliebig
oft wiederholbar. Wird der Lead Kunde, ergänzt `audit --backfill` die sechs
Kundenquellen im selben Account.

**Argument:** die `audit-id` eines Funnel-Leads **oder** eine Shop-URL.

```
/ptai-ecom:audit-light 00000000-0000-0000-0000-000000000000   # Lead aus dem Funnel
/ptai-ecom:audit-light https://shop.example.de                # eigener Lauf, ohne Lead
/ptai-ecom:audit-light <arg> --with-dfs                        # die fünf bezahlten Quellen dazu
/ptai-ecom:audit-light <arg> --brand "Beispielshop"            # Marke vorgeben, gilt vor entity.md und Startseite
/ptai-ecom:audit-light <arg> --run 2026-09-07-light          # abgebrochenen Lauf fortsetzen
```

**Der Normalfall ist die ID.** Leads kommen über `/audit/` in die Supabase-Tabelle
`audits`, und die Zeile hält Shop-URL, Mailadresse und Eingangsdatum. Nur mit der
ID kann `audit-light-send` den Report später an den richtigen Menschen schicken.
Eine URL ohne ID ist ein Lauf ohne Empfänger: der Report landet im Account, aber
verschickt wird er nicht.

---

## Was nicht verhandelbar ist

**Jeder Befund braucht eine Belegstelle.** Eine erreichbare URL, ein wörtliches
Zitat von der Seite, oder ein konkretes Element. Kein Beleg, kein Befund. Vier
belegte Befunde schlagen zehn erfundene, und der Lead prüft den ersten nach.

**`ok` ist ein Ergebnis.** Ein Shop ohne Mangel in einem Bereich bekommt `ok`,
keine künstlich aufgeblasene Warnung.

**Keine Geschäftszahlen über den Shop.** Umsatz je Seite, Traffic, "Bestseller",
"umsatzstärkste Produktseite" sind von außen nicht belegbar. Erlaubt ist
"prominenteste Seite laut Navigation" mit dem Beleg, wo sie verlinkt ist.
Öffentlich belegte Unternehmenszahlen mit Quelle und Jahr bleiben erlaubt.

**HTML sieht nicht alles.** Review-Widgets, Siegel, Badges und Galeriebilder
werden oft erst im Browser gerendert. Ein "fehlt"-Befund über so etwas braucht
den Screenshot als Beleg. Ohne den: weglassen, oder ehrlich als Prüfauftrag mit
`confidence: "low"` formulieren. Und nie behaupten, etwas sei "nirgends"
vorhanden, wenn nur die Erstansicht geprüft wurde.

**Der Report empfiehlt nie eine Vergleichsseite.** Keine "[Marke] vs
[Wettbewerber]"-Seiten, keine "[Wettbewerber]-Alternative". Händler lehnen das
ab. Die Wettbewerbsanalyse fließt in Positionierung und Markt, nie in Befunde,
Triage oder Fahrplan.

**Werkzeuge:** Seitenabrufe über `curl`, Screenshots über `capture-screens`.
**Verboten sind `WebFetch` und alle Browser-Werkzeuge** (`mcp__Claude_Browser__*`,
`mcp__claude-in-chrome__*`): sie lösen pro Domain einen Freigabe-Dialog aus, und
ein Lauf berührt die Shop-Domain plus ein Dutzend Wettbewerber-Domains.
`WebSearch` ist erlaubt. Diesen Absatz in jeden Subagent-Prompt kopieren.

```bash
curl -sSL -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" --max-time 25 <url>
```

---

## Stufe -2: Argument auflösen

Enthält das Argument `://` oder einen Punkt, ist es eine URL. Sonst ist es eine
`audit-id`, und dann kommt die Shop-URL aus der Datenbank:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/db.mjs" get <audit-id>
```

Aus der Zeile brauchst du `shop_url` (der Shop), `email` (der Empfänger) und
`created_at` (wann der Lead reinkam). Alle drei gehören in den Lauf: die `email`
und das Datum als Kontext, falls der Kunde noch angelegt werden muss, die
`audit_id` in die Lauf-Config, damit `audit-light-send` den Lauf wiederfindet.

Steht die Zeile schon auf `sent`, wurde für diesen Lead bereits ein Report
verschickt. Das verbietet nichts, aber sag es, bevor du losläufst.

## Stufe -1: Kunde auflösen

Ein Lauf beginnt nie ohne Kundenordner. Die Ergebnisse gehören zum Kunden, nicht
in ein Repo. Die Kundenordner liegen unter `PTAI_ACCOUNTS_ROOT`, Vorgabe
`~/ptai-ecom/accounts`, gesucht wie jeder Wert des Betreibers: Umgebung, `.env`
im aktuellen Verzeichnis, `~/.config/ptai-ecom/.env`.

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

Ist `workos:lead` installiert, übernimmt sie die Recherche und legt den Ordner an. **Der Lauf hält
dabei nicht an.** Die drei Stellen, an denen sie sonst nachfragt, sind bei einem
Funnel-Lead bereits entschieden, und du gibst sie ihr deshalb vor:

| Was er sonst fragt | Was hier gilt |
|---|---|
| Firmenname und Quelle | Quelle ist der Audit-Funnel. Die Firma steht im Impressum der Shop-Domain, die ist eindeutig und muss nicht erraten werden |
| warm oder kalt, `entity_type`, `status` | Wer selbst ein Formular ausfüllt, ist ein eingehender Lead: `entity_type: lead`, `status: kontaktiert`, `letzter_kontakt` = das Eingangsdatum |
| Widersprüche zu Gesprächsnotizen | Gibt es nicht, der Account entsteht ja gerade erst |

Übergib ihm wörtlich diesen Block, mit den Werten aus Stufe -2:

> Funnel-Lead aus dem Audit-Formular auf path-to-ai.com. Shop `<shop_url>`,
> Absender `<email>`, eingegangen am `<created_at>`. Leg den Account an mit
> `entity_type: lead`, `status: kontaktiert`, `source: Audit-Funnel
> path-to-ai.com/audit/`, `letzter_kontakt: <created_at>`, `domains: <host>`.
> Die Firma bestimmst du aus dem Impressum von `<shop_url>`; das ist die
> maßgebliche Quelle, die Domain ist eindeutig, es gibt nichts zu verwechseln.
> **Stell keine Rückfragen.** Was du nicht belegen kannst, trägst du als "nicht
> gefunden" ein und nennst es am Ende in einer Zeile. Ein leeres Feld ist
> ehrlich, ein angehaltener Lauf ist nutzlos.

Das ist keine Ausnahme von der Ehrlichkeitsregel, sondern ihre Anwendung: der
Lead-Skill sagt selbst "lieber eine Lücke als eine geratene Zahl". Die Lücke
kommt in die `entity.md` und in die Übergabe am Ende, nicht in eine Frage
mittendrin.

**Mit `workos:lead`, falls installiert, recherchiert dieser Skill selbst keine
Firmendaten.** Er gibt den Auftrag weiter, wartet auf den fertigen Ordner und
löst danach erneut auf. Bleibt es bei `none`, schreibt `workos:lead` in einen
anderen Ordner als `PTAI_ACCOUNTS_ROOT`: abbrechen und beide Ordner nennen,
statt einen zweiten Kunden anzulegen.

### Kein Kunde, `workos:lead` nicht installiert: selbst anlegen

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.account create '<shop-url>' [--brand='<marke>']
```

Das Skript löst noch einmal auf und legt nur an, wenn es bei `none` bleibt:
`<PTAI_ACCOUNTS_ROOT>/<slug>/entity.md` mit der Marke als Überschrift und dem
Host unter `domains:`. Der Slug ist das Label vor der Endung,
`shop.beispiel-shop.de` wird `beispiel-shop`.

**Die Marke** kommt in dieser Reihenfolge: `--brand`, sonst bei einem
vorhandenen Kunden die Überschrift seiner `entity.md`, sonst für einen neuen
Kunden die Startseite, `og:site_name` oder der erste Teil des `<title>`, genau
einmal abgerufen und vor dem Anlegen. Nach genau diesem Namen sucht `check-geo`
in den AI-Antworten. Die Zeile `marke aus:` sagt, woher er stammt. Steht dort
`marke aus: slug`, war die Startseite nicht lesbar; Stufe 0 holt das nach.

| Exit | Was zu tun ist |
|---|---|
| 0 | weiter mit `slug` und `drive_path` aus der Ausgabe |
| 3 | **abbrechen**: der Kundenordner für diesen Slug existiert schon, siehe unten |
| 4 | **abbrechen**: `PTAI_ACCOUNTS_ROOT` zeigt auf keinen Ordner |

### Mehrdeutig oder belegt: das ist ein Fehler, keine Frage

`ambiguous` heißt, zwei `entity.md` beanspruchen dieselbe Domain. Das ist ein
kaputter CRM-Zustand, keine Entscheidung über den Audit, und der Lauf würde die
Daten eines Kunden in den Ordner eines anderen legen. Also: abbrechen, beide
Slugs nennen, der Betreiber räumt auf.

Exit 3 beim Anlegen ist derselbe Fall von der anderen Seite: zwei Shops teilen
das Label vor der Endung, etwa `beispiel.de` und `beispiel.at`. Ob der Host in
die `domains:` des vorhandenen Kunden gehört, in der Listenform, die die Datei
schon nutzt, oder ein eigener Kunde mit Suffix `-2` ist, weiß kein Muster. Der
Lauf fragt nicht, er bricht ab und gibt die Meldung wörtlich weiter; sie nennt
beide Wege.

### Kundenordner und Arbeitsverzeichnis

Ab hier heißt der Kundenordner `<account_dir>`: der `drive_path` aus der Ausgabe
oben, ein absoluter Pfad. Darin liegen `audit-runs/`, `material/` und
`deliverables/`. **Wechsle jetzt dorthin:**

```bash
cd "<account_dir>"
```

Die Pulls lesen auch eine `.env` im aktuellen Verzeichnis. Ein Lauf, der in
einem Kunden-Workspace gestartet wurde, zöge sonst dessen Schlüssel für einen
fremden Lead, etwa dessen eigenes DataForSEO-Konto. Die Aufrufe unten laufen
deshalb in `<account_dir>`; wer einen davon an einen Subagenten gibt, stellt
`cd "<account_dir>" &&` davor, denn ein Subagent erbt das Verzeichnis nicht.

**Lauf-Ordner** ist ab hier `<account_dir>/audit-runs/<heute>-light/`. Existiert
er schon und `--run` wurde nicht gesetzt, hänge ein `-2` an: ein zweiter Lauf am
selben Tag überschreibt nie den ersten.

---

## Stufe 0: Aufnahme

Keine Agents. Vier Skripte, deren Ergebnisse alle Linsen als gemeinsame Wahrheit
lesen. Das ist der Punkt: vorher hat jede Linse den Shop selbst abgerufen und
kam zu leicht anderen Aussagen.

**1. Lauf-Config bauen.** Sie ersetzt die `reporting/config.json`, die ein Lead
nicht hat.

```bash
python3 -c "
import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import lightconf
cfg = lightconf.build('<shop-url>', '<slug>', brand=<'<marke aus --brand>' oder None>, with_dfs=<True|False>, audit_id='<audit-id oder None>')
lightconf.write(cfg, '<run>/run-config.json')
"
```

**2. Crawl zuerst**, weil die Seitentypen daraus kommen.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/crawl-site/scripts/crawl.py" \
  --domain https://<host> --out "<run>/data" --max-urls 300
```

**`--domain` will die vollständige URL mit Schema, nicht den Host.** Das Script
hängt nichts an: mit `beispielshop.de` bekommt jeder Abruf
`unknown url type: 'beispielshop.de'`, und der Lauf endet mit einer `crawl.json`
über eine einzige Seite mit Status `error`. **Eine Erfolgsmeldung kommt
trotzdem**, sie lautet dann "1 URLs, 0 mit Status 200". Belegt am 17.09.2026 in
einem Lauf, in dem genau diese Zeile als erfolgreicher Crawl gelesen wurde. Prüf nach dem Crawl `summary.url_count` und
`summary.status_code_distribution`, bevor du weitergehst.

`--max-urls 300` statt der 5000 des großen Audits: hier zählt Tiefe vor Breite,
und ein ungebremster Crawl kostet ein Vielfaches des restlichen Laufs.

**3. Seitentypen nachtragen und die GEO-Fragen ableiten.** Beides ohne Rückfrage.
Die Kategorie- und Problemfragen liest du aus dem Crawl ab: Titel und
Beschreibung der Startseite, die Kategorienamen, ein, zwei Produkttitel. Daraus
formulierst du drei Kategoriefragen (wonach jemand sucht, der die Marke nicht
kennt) und drei Problemfragen (das Problem, das die Produkte lösen), beide **ohne
Markennamen**, in der Sprache des Marktes.

Beispiel für einen Shop mit Massagegeräten: Kategorie "Welche Marken für
Faszienrollen taugen etwas?", Problem "Was hilft gegen Nackenverspannungen im
Homeoffice?". Nicht: "Ist Wohlfuehlbad gut?", das ist die Markengruppe und
steht schon drin.

**Die gesetzten Fragen gehören in den Report** unter Quellen und Methodik. Sie
sind die Messvorschrift der GEO-Zahl: wer sie nicht sieht, kann die Zahl nicht
einordnen.

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

Gibt `missing()` etwas zurück, ist der Lauf noch nicht bereit. Leere Liste heißt
weiter. **Der Lauf hält hier nicht an und fragt nichts**, er entscheidet und
schreibt auf, was er entschieden hat.

**Stand in Stufe -1 `marke aus: slug`**, ist `brand` nur der Slug. Dann jetzt die
Marke aus Titel und Impressum im Crawl ablesen, in `run-config.json` `brand` und
`geo_queries.brand` neu setzen (`lightconf.brand_queries('<marke>', '<host>')`)
und die Überschrift in `<account_dir>/entity.md` angleichen, bevor `check-geo`
läuft. Sonst misst GEO die Sichtbarkeit eines Slugs statt einer Marke.

**4. Betreiber-Schlüssel prüfen.** `pull-cwv` und `check-geo` brauchen sie, und
ein Lauf für einen Lead hat keinen Workspace, aus dem sie kämen:

```bash
cd "<account_dir>" && python3 -c "
import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from audit import env; env.export_env('<account_dir>')
for name, origin in env.status('<account_dir>'): print(f'{name:<26} {origin}')
"
```

Sie kommen aus `~/.config/ptai-ecom/.env`, in dieser Reihenfolge: Umgebung, dann
`.env` im Kundenordner, dann die zentrale Datei. Einstellungen wie
`PTAI_ACCOUNTS_ROOT` stehen auf `nicht gesetzt`, wenn ihre Vorgabe greift, und
zählen nicht. Steht ein Schlüssel auf
`FEHLT`, läuft der Audit trotzdem: die betroffene Plattform wird `null`, nicht
`false`, und der Report weist sie als nicht geprüft aus. **`FEHLT` ist kein Grund
abzubrechen, aber ein Grund, es im Report zu sagen.**

**5. Die drei übrigen Quellen**, parallel. Jede über ihre eigene Skill, weil
jede eigene Fehlerbilder hat:

| Quelle | Skill | Anmerkung |
|---|---|---|
| Screenshots | `capture-screens` | `checkout_capture: false`, siehe unten |
| Core Web Vitals | `pull-cwv` | Feldwerte vor Laborwerten, `field_data: null` heißt zu wenig Traffic und ist kein Fehler |
| GEO | `check-geo` | misst, ob die Marke in ChatGPT, Perplexity und Google-AI auftaucht |

**Die Aufrufe, wörtlich.** Beim ersten echten Lauf sind an genau diesen drei
Stellen Fehler passiert, die keine Fehlermeldung erzeugt haben, sondern stille
Lücken. Also:

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

**Der Cookie-Dialog gehört ins Bild und in die Grenzen.** Auf einem deutschen
Shop liegt er auf jeder Aufnahme. Auf dem Desktop verdeckt er meist nichts
Wesentliches, **auf dem Handy oft die untere Bildhälfte samt Kaufbereich**. Was
er verdeckt, ist `not_checkable` und nie ein Befund: "kein Kaufbutton auf dem
Handy sichtbar" wäre dann eine Aussage über den Screenshot, nicht über den Shop.
Der Dialog selbst ist ein eigener Befund für L4, positiv wie negativ.

**Wenn der Markenname zugleich das Produktwort ist**, zählt keine automatische
Markennennung. Bei LEDERTASCHE antwortet Perplexity auf "Was ist LEDERTASCHE?" mit
"Eine Ledertasche ist ein Etui zur Aufbewahrung von Armbanduhren", und jede
Zählung wertet das als Treffer. Prüfe das, bevor du die GEO-Zahlen weitergibst:
steht der Markenname auch als gewöhnliches Wort in den eigenen Kategorienamen,
ist `brand_mentioned` unbrauchbar. **Belastbar ist dann `domain_cited`**, und der
Report sagt, warum.

**Der Kaufweg bleibt aus.** `capture-screens` kann ihn automatisiert bis zur
Zahlungsauswahl durchlaufen, aber bei einem kalten Lead ohne Geschäftsbeziehung
legt niemand einen Testwarenkorb mit Platzhalterdaten in dessen Kasse. Beim
großen Audit ist der Kunde einverstanden, hier nicht. Mit `--checkout` bewusst
zuschaltbar.

**Bezahlte Quellen.** Die fünf DataForSEO-Pulls sind aus, weil der Audit ein
kostenloser Lead-Magnet ist. Mit `--with-dfs` an, dann greift der Deckel
`dfs_budget_usd` und jeder Aufruf landet im `dfs-ledger.jsonl`.

**Eine ausgefallene Quelle bricht den Lauf nie ab.** Sie wird als "nicht
verfügbar (Grund)" notiert und taucht so im Report unter Quellen und Methodik
auf. Ein Lauf mit drei von vier Quellen ist ein ehrlicher Lauf, ein Lauf, der
eine Lücke verschweigt, ist keiner.

---

## Stufe 1: Sechs Linsen, parallel

Alle sechs `Agent`-Aufrufe **in einer Nachricht**. Jede Linse liest die Snapshots
aus `<run>/data/` und die Screenshots aus `<account_dir>/material/`, ruft die Seite nur noch
für eigene Stichproben ab.

| Linse | Prüft | Skill laden, fremde nur falls installiert |
|---|---|---|
| L1 Auffindbarkeit | Indexierbarkeit, Statuscodes, Canonicals, interne Struktur, Product-, Offer-, Organization-, FAQ- und Breadcrumb-Schema | `claude-seo:seo-technical`, `claude-seo:seo-schema` |
| L2 KI-Sichtbarkeit | den GEO-Snapshot deuten, dazu Crawler-Zugang aus der robots.txt und Zitierfähigkeit der Seiten | `claude-seo:seo-geo` |
| L3 Kaufstrecke | Kaufbutton, Verfügbarkeit, Lieferzeit, Versandkosten vor der Kasse, Gastbestellung, Zahlarten, Schrittzahl, Mobil | `ptai-ecom:lens-purchase-path` |
| L4 Vertrauen und Recht | Impressum, Widerruf, AGB, Datenschutz, Preisangaben mit Grundpreis, Versandkostenangabe, Bewertungen am Kaufpunkt, Siegel | `ptai-ecom:lens-trust` |
| L5 Sortiment | Filter und Sortierung, Varianten, Produkttexte, Bildanzahl und -qualität, Cross-Selling, ausverkaufte Artikel | `ptai-ecom:lens-assortment` |
| L6 Markt und Position | Wettbewerberfeld, Positionierungsachsen, Fähigkeiten-Matrix, Marke gegen Startseite und Über-uns | `pm-market-research:competitive-analysis`, `marketing:brand-review` |

> **Die Skill wird geladen, nicht nur genannt.** Jeder Agent ruft seine Skill
> ausdrücklich über das Skill-Werkzeug auf. Ein Prompt, der einen Skillnamen nur
> als Überschrift trägt, bekommt die Methode nie zu sehen, und dann ist die
> "kuratierte Linse" nur ein Etikett.
>
> `claude-seo:*`, `pm-market-research:competitive-analysis` und
> `marketing:brand-review` gehören nicht zum Plugin. Ist eine davon nicht
> installiert, prüft die Linse nach der Spalte "Prüft" ohne sie, und der Report
> nennt das unter Quellen und Methodik.

**Prompt-Gerüst je Linse** (Werkzeug-Absatz von oben mitkopieren):

> Du prüfst den öffentlichen Shop `<domain>` durch eine Linse. Lies zuerst
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
> **Der Leser ist Geschäftsführer, kein SEO.** Jeden Fachbegriff beim ersten
> Auftreten in einem Halbsatz erklären. Liefere neben den Mängeln ein bis zwei
> belegte `ok`-Befunde: was nachweislich läuft und bleiben soll.
>
> Schreibe zwei Dateien nach `<run>/findings/`:
>
> `L<n>-<lens>.json` , Array mit genau diesen Feldern je Befund:
> `severity` (crit|warn|ok), `title`, `detail`, `recommendation`, `evidence`,
> `url` (der eine klickbare Deep-Link, bei seitenweiten Funden weglassen),
> `impact`, `effort`, `confidence` (high|medium|low), `lens`.
>
> `L<n>-<lens>.coverage.json`: `{"checked": [...], "not_checkable": [{"what", "reason"}]}`.
> Das ist keine Formalie: eine Linse, die nichts findet, weil sie geblockt wurde,
> sieht im Score sonst aus wie ein guter Shop.

**L4 stellt fest, sie bewertet nicht juristisch.** Ein Befund lautet "vorhanden"
oder "nicht auffindbar", nie "rechtswidrig". Der Report ist kein Rechtsrat.

---

## Stufe 2: Beleg-Gate

**Ein** Agent, bevor irgendetwas erzählt wird. Im alten Command lief diese
Prüfung nach dem Rendern, und jeder widerlegte Befund erzwang Neuschreiben,
Score-Neuberechnung und einen zweiten Render.

> Lies alle `<run>/findings/L*.json`. Für **jeden** Befund mit `url`:
> 1. Die URL live abrufen (`curl`, siehe Werkzeug-Absatz).
> 2. Claim-Typ bestimmen: *Präsenz* (etwas wird als vorhanden zitiert) oder
>    *Absenz* ("keine FAQ", "fehlt", "0 …").
> 3. Präsenz mit Stellenbezug ("im Title", "im Product-JSON-LD") im **richtigen
>    Element** prüfen, nicht irgendwo auf der Seite. Absenz: ist das Ding
>    wirklich weg? Live gefunden heißt Widerspruch.
> 4. **4xx, Bot-Block oder verdächtig kurzer Body sind `unreachable`, nie
>    "bestätigt".** Eine Absenz-Behauptung aus einem fehlgeschlagenen Abruf gilt
>    als unbestätigt.
>
> Schreibe `<run>/verify.json`: je Befund `{title, url, verify, claimType,
> suggestion}` mit `verify` aus `confirmed | quote-not-found | contradicted |
> unreachable`. Zu jedem Nicht-`confirmed` einen konkreten Vorschlag: neues
> Wording, `drop`, oder `keep` mit Begründung.

Danach setzt die Pipeline die Vorschläge selbst um: `drop` fliegt raus,
`contradicted` ohne korrigierte Fassung ebenso, `reword` übernimmt die korrigierte
Fassung, `keep` bleibt. Korrigiertes nach `contradicted` geht mit
`confidence: "medium"` weiter, alles aus `unreachable` und `quote-not-found` mit
`"low"`. Nur was übrig bleibt, geht in Stufe 3.

**Yves gibt diese Liste nicht frei.** Das Urteil über einen Beleg ist Arbeit des
Audits. Yves am 11.09.2026: *"Ich bin doch nicht der Experte. Dafür sind doch die
Skills da, die im Audit sind."*

---

## Stufe 3: Konsolidierung und Score

Drei Agents parallel, einer je Säule. Jeder liest die Befunde seiner Linsen,
dedupliziert (gleicher Fund aus zwei Linsen wird einer, der beste Beleg
gewinnt), rankt nach Wirkung durch Aufwand und schreibt ein Kapitel-Intro von
zwei bis vier Sätzen. **Erster Satz: was in diesem Bereich nachweislich gut
dasteht.**

| Säule | Linsen | Gewicht |
|---|---|---|
| Akquisition | L1, L2 | 0,30 |
| Conversion Rate Optimierung | L3, L5, dazu die Core Web Vitals | 0,45 |
| Trust und Compliance | L4 | 0,25 |

L6 speist keinen Score. Eine Marktposition ist keine Note; sie liefert Quadrant,
Matrix und das Markt-Narrativ.

**Die Säulen-Datei trägt dieselben Befund-Felder wie die Linsen, keins weniger:**
`severity`, `title`, `body`, `evidence`, `recommendation`, `url`, `impact`,
`effort`, `confidence`, `lens`. Dazu `persists: true` bei einem Befund, den die
Maßnahmen dieses Bereichs nicht abstellen. Zwei Felder fallen beim
Zusammenführen regelmäßig hinten runter, und beide fallen still:

- **`url` ist der eine klickbare Deep-Link.** Der Renderer macht daraus im PDF
  die Zeile "zur Stelle ansehen", und ohne ihn ist im ganzen Report kein
  einziger Beleg anklickbar. Genau das ist die erste Frage der Übergabe.
  Beim Zusammenlegen zweier Befunde entscheidet der Agent, welcher der beiden
  Links die Sache besser zeigt; bei einem seitenweiten Fund bleibt das Feld
  weg, statt auf eine beliebige Seite zu zeigen. Belegt am 17.09.2026: dieser
  Abschnitt zählte nur `skills` und `methoden` auf, und alle drei Säulen-Agents
  haben `url` weggelassen, weil es im Vertrag nicht stand.
- **`lens` trägt genau den kurzen Linsennamen**, kleingeschrieben und ohne
  Präfix: `auffindbarkeit`, `ki-sichtbarkeit`, `kaufstrecke`, `sortiment`,
  `vertrauen`. Die Score-Engine vergleicht das Feld **exakt** gegen diese
  Zeichenketten (`score.mjs`, `saeuleVon`). Steht dort "L1 Auffindbarkeit",
  landet der Befund in keiner Säule, jede Säule kommt auf 100 Punkte, und es
  gibt keine Fehlermeldung. Das Feld `ohne_saeule` in der Score-Ausgabe listet
  genau diese Zeilen auf, und es wird nach jedem Lauf angesehen.

**`impact` ist ein ganzer Satz, kein Stufenwort.** Der Renderer setzt ihn im PDF
als eigene Zeile mit dem Label "Wirkung". Steht dort "hoch", verbraucht eine
beschriftete Zeile Platz für eine Angabe, die Farbstrich und Schwere-Badge
schon zweimal daneben zeigen. Der Satz benennt, was sich geschäftlich ändert,
**wenn die Empfehlung umgesetzt ist**, nicht was heute schiefgeht, und hängt wo
möglich an einer Zahl aus demselben Befund.

### Die ausführlichen Befunde sind Entscheidungsvorlagen

**Die `topN` Befunde je Kapitel (Vorgabe 4) bekommen drei weitere Felder:
`facts`, `proof` und, wo es zwei echte Wege gibt, `decision`.** Der Leser ist
Geschäftsführer und will wissen, was er entscheiden soll, nicht einen Absatz
lesen, in dem die Messwerte stehen. Das Feedback aus einem Gespräch am
30.09.2026: Entscheidungsvorlagen statt Informationen, ein Entweder-oder. Am
01.10.2026 entstanden zwei Audits in diesem Format, aber nur als Einzelskripte
im Kundenordner, und der nächste Lauf am 02.10.2026 kam wieder mit der
Textlatte. Yves: *"Da sind immer noch die riesigen Texte."* Seitdem kann der
Renderer das Format selbst, und dieser Vertrag erzeugt es.

**Das vollständige Format steht in `reference/finding-format.md`**, gemeinsam
mit dem vollen Audit und dem Kundenportal. Was hier folgt, ist die Kurzfassung
für das Audit Light; widerspricht sie dem Vertrag, gilt der Vertrag.

`body`, `recommendation`, `impact` und `evidence` bleiben gefüllt. Sie stehen im
PDF zugeklappt unter "+ Herleitung und Belege" und im Portal zum Aufklappen. Was
neu dazukommt, ist das, was der Leser zuerst sieht:

- **`facts`**, zwei bis vier Zeilen `{label, text}`, je höchstens 160 Zeichen,
  ein ganzer Satz. `WARUM ES ZÄHLT` ist Pflicht und nennt die Folge für den
  Kunden, nicht den Mechanismus. Dazu nach Bedarf `URSACHE`, `VORHANDEN`,
  `OFFEN`, `NÄCHSTER SCHRITT`. Was ohne Entscheidung sofort geht, steht als
  `{now: true, text}` und wird "SOFORT UMSETZBAR". Statt des Labels geht
  `{kind, text}` mit `effect`, `cause`, `present`, `open` oder `next`; der
  Renderer setzt das Label dann selbst, und das Portal versteht dieselbe Datei.
- **`proof`**, der Beleg als Bild: `{columns: [{label, blocks: [...]}]}`, eine
  oder zwei Spalten. Jede Zahl darin ist gemessen. Blocktypen:
  `metric` `{value, unit, label}`, `note` `{text}`, `quote` `{text, source}`
  (mit `<ins>` für eine vorgeschlagene Ergänzung, `<mark>` für eine Abweichung),
  `chips` `{groups: [{label, items, own}]}`, `rows` `{rows: [{label, sub, text|quote}]}`,
  `pairs` `{rows: [{from, to}]}`, `grid` `{columns, rows: [{label, cells}]}` mit
  Zellen `both|brand|other|domain|none|x|check`, `dist` `{total, parts: [{value, label, tone}]}`,
  `image` `{src, alt, rings, addition, caption}` und `phone`
  `{src, width, height, fold, markers: [{y, label, text}]}`. Steht ein `phone`
  vorn, stehen Kennzahlen und `facts` rechts daneben.
- **`decision`**, nur wo es zwei echte, verschiedene Wege gibt, nie als
  Pflichtfeld: `{question, options: [{title, text, effort, result, image}, {…}],
  recommended: 0|1, reason}`. Die Frage ist ein ganzer Satz mit "oder". `reason`
  beginnt mit dem empfohlenen Buchstaben ("A, weil …") und hat einen Satz.
  Typisch sind zwei bis vier Entscheidungen im ganzen Report, nicht je Befund
  eine. Ein Befund, der nur eine sinnvolle Maßnahme hat, bekommt keine
  `decision`, sondern eine Zeile `SOFORT UMSETZBAR`.

Belegbilder liegen als Dateien vor, `src` relativ zur `content.json` oder
absolut; der Renderer bettet sie ein. Für Handy und Kaufbereich taugen nur
Aufnahmen ohne Cookie-Dialog, siehe Stufe 4. Ein Befund mit `decision` bekommt
im PDF eine eigene Seite, einer ohne bleibt kompakt. Ton und Länge: ein Befund
mit Entscheidung passt auf eine Seite, ein kompakter auf eine halbe.

**Jede Säulen-Datei trägt zwei getrennte Herkunftslisten, nie eine gemischte.**
`skills` sind die Skills, die die Linsen in Stufe 1 **tatsächlich über das
Skill-Werkzeug geladen haben**, mit vollem Namen (`claude-seo:seo-technical`,
`ptai-ecom:lens-trust`). `methoden` ist die Messgrundlage, also was geprüft wurde
und woher die Zahlen kommen. Der Renderer setzt sie als "Geprüft mit" und
"Grundlage" nebeneinander.

**Welche Skills geladen wurden, wird nachgesehen, nicht aus dem eigenen Prompt
abgeschrieben.** Ein Agent, der die Skill nicht aufgerufen hat, taucht sonst im
Report als geprüft auf. Der Nachweis steht in den Agenten-Protokollen des Laufs:

```bash
for f in <agent-ids>; do printf "%-20s " "$f"
  grep -o '"name":"Skill","input":{"skill":"[^"]*"' \
    "$HOME/.claude/projects/<projekt>/<session>/subagents/agent-$f.jsonl" \
    | sed 's/.*skill":"//' | sort -u | tr '\n' ' '; echo; done
```

Am 16.09.2026 stand in allen drei Kapiteln die Messgrundlage im Feld `skills`,
weil der Orchestrator sie als "die genutzten Methoden" angefordert hatte. Yves:
*"Wurden da jetzt wirklich Skills geladen, weil da stehen: keine mehr?"* Sie
waren geladen, alle acht; nur stand es nirgends. Ein Report, der die eigene
Methode belegen soll, darf an dieser Stelle nicht raten.

Danach den Score rechnen lassen, nicht schätzen. Das zweite Argument ist der
Ordner mit den `L<n>-<lens>.coverage.json`-Dateien aus Stufe 1, `<run>/findings/`
selbst; ohne dieses Argument bleibt `coverage` leer und die Abdeckungs-Regel
unten greift nie:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/score.mjs" <run>/findings.json <run>/findings
```

**Abdeckungs-Regel.** Meldet ein `coverage.json` seine Pflicht-Checks als nicht
ausführbar, bekommt die Säule keinen Score, sondern eine im Report ausgewiesene
Lücke. Die Engine rechnet 100 minus Strafpunkte, ohne Boden und Deckel; eine Linse,
die geblockt wurde, käme sonst auf denselben Höchstwert wie ein wirklich guter Shop.

---

## Stufe 4: Report

`content.json` schreiben (Struktur exakt wie
`${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/report-content.sample.full.json`),
dann rendern:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/render.mjs" \
     "<run>/content.json" "<run>/report.html"
bash "${CLAUDE_PLUGIN_ROOT}/skills/report/scripts/render_pdf.sh" \
     "<run>/report.html" "<run>/report.pdf"
mkdir -p "<account_dir>/deliverables"
cp "<run>/report.pdf" "<account_dir>/deliverables/<datum>-path-to-ai-ecom-audit-<domain>.pdf"
```

**Der Dateiname des Deliverables ist kein interner Name.** Yves lädt das PDF herunter und
verschickt es weiter, und dann steht dieser Name im Postfach des Empfängers. Das Schema ist
deshalb fest und in allen Report-Skills gleich: **Datum, Absender und Dokumentart, Domain**, also
`2026-09-20-path-to-ai-ecom-audit-beispielshop.de.pdf`. Die Domain bleibt als Domain lesbar, mit
Punkt, damit der Empfänger auf einen Blick sieht, um welchen Shop es geht. `<datum>` ist das Datum
des Laufs, nicht das Datum des Kopierens.

**Die Datei im Lauf-Ordner heißt weiter `report.pdf`**, das ist der Arbeitsstand. Wer Yves eine
Datei schickt oder verlinkt, schickt die aus `deliverables/`, nie die aus dem Lauf-Ordner: sonst
landet bei ihm eine Datei namens `report.pdf`. Belegt am 21.09.2026, genau so passiert.

`audit-light-send` hängt denselben Namen an die Mail; er entsteht dort in `send-report.mjs` aus
`content.json`. Damit dort das Lauf-Datum steht und nicht das Versanddatum, trägt `content.json`
das Feld `meta.datei_datum` mit dem Datum des Laufs.

**Die Seite "Entscheidungen" baut der Renderer selbst.** Sobald ein Befund eine
`decision` trägt (Stufe 3), steht hinter der Zusammenfassung eine Seite mit
allen Entscheidungen, je Zeile Frage, Herkunft und beide Wege, der Vorschlag
markiert. Die Seite "Worauf es jetzt ankommt" (`triage`) entfällt dann; ihre
Spalte "Nicht verfolgen" zieht auf die Entscheidungsseite. Wer sie gezielt
setzen will, schreibt `decisions.avoid` als `[{title, text}]`; sonst liest der
Renderer die triage-Spalte, deren Label "NICHT" oder "IGNOR" enthält, mit
Einträgen der Form "Titel: Satz". `decisions.headline`, `decisions.lead` und
`decisions.pointer` überschreiben bei Bedarf die Vorgaben.

**Belegbilder vom Handy nur ohne Cookie-Dialog.** Die Aufnahmen aus Stufe 0
zeigen den Shop, wie ein Erstbesucher ihn sieht; auf dem Handy verdeckt der
Dialog dort oft die ganze Seite. Für `proof` werden die Seiten deshalb ein
zweites Mal aufgenommen, mit abgelehntem Dialog, und für den Belegtyp `phone`
gleich als Streifen in der gezeigten Höhe:

```bash
PY=$(for p in "$PTAI_PLAYWRIGHT_PYTHON" python3 python3.11 /opt/homebrew/opt/python@3.11/bin/python3.11; do
  [ -n "$p" ] && "$p" -c 'import playwright' 2>/dev/null && echo "$p" && break; done)
cd "<account_dir>" && "$PY" "${CLAUDE_PLUGIN_ROOT}/skills/capture-screens/scripts/shoot_declined.py" \
  --target "<account_dir>/material/<datum>-audit-screenshots" \
  --url start=<url> --url product=<url> --url collection=<url> --strip product=1800
```

Meldet das Skript "Kein Ablehnen-Knopf gefunden", kennt es das Consent-Tool
nicht: den Knopf im HTML suchen, seinen Selektor in `DECLINE_SELECTORS`
ergänzen und neu aufnehmen. Nie die Aufnahme mit Dialog als Beleg nehmen.

**Die letzte Seite kommt nicht aus `content.json`.** Ist `PTAI_CLOSING_FILE`
gesetzt, setzt `render.mjs` diese Datei unverändert als Schlussseite ein,
dieselbe wie im Audit und im Monats-Report. Ohne die Einstellung endet der
Report mit dem neutralen Schluss: eine Kontaktzeile je gesetztem und gültigem
Wert aus `PTAI_OPERATOR_NAME`, `PTAI_OPERATOR_CONTACT`, `PTAI_OPERATOR_EMAIL`
und `PTAI_OPERATOR_BOOKING_URL`, darunter die Herkunftszeile. Gesucht wird in
der Umgebung, dann in der zentralen Datei (`PTAI_ENV_FILE`, sonst
`~/.config/ptai-ecom/.env`); einen Workspace hat dieser Lauf nicht. Fehlt die
Datei, ist sie nicht lesbar oder leer, schreibt `render.mjs` eine Zeile auf
stderr und rendert den neutralen Schluss. Ein Feld `closing` in `content.json`
wird ignoriert. Der Kleindruck zur Datengrundlage steht am Ende der letzten
Inhaltsseite davor. Er endet mit `© <Jahr> <PTAI_OPERATOR_NAME>.`, gesucht wie
der Schluss; ohne ausdrücklich gesetzten Namen entfällt dieser Satz.

**Sieben Feldfehler, die den Report in den ersten Läufen zerlegt haben:**

- **`market.callouts[].value` ist eine kurze Zahl, keine Überschrift.** Der
  Renderer setzt sie im Display-Schnitt über die halbe Spalte. Ein Befund-Titel
  darin wird riesig gesetzt und mitten im Wort abgeschnitten. Richtig ist `"0"`
  mit `unit: "von 6"`, der Satz gehört in `body`.
- **Doppelt maskierte Zeichen aus den Subagents auflösen.** Ein Agent, der
  `&amp;` in ein Feld schreibt, lässt im PDF `Muster &amp; Muster GbR` stehen.
  Vor dem Rendern einmal über `content.json` gehen.
- **`meta.erstelltFuer` ist die Firma, nicht die Domain.** Steht es nicht drin,
  fällt der Renderer auf `shop` zurück, und im Kopf jeder Seite steht dann eine
  URL statt eines Namens.
- **`chapters[].effort` ist ein Label, kein Satz.** Der Renderer setzte es bis
  zum 21.09.2026 als kleinen Kasten neben den Befundtitel, wo ein ganzer Satz
  gequetscht wurde und dasselbe sagte wie die Empfehlung darunter. Seitdem steht
  dort die Schwere, und `effort` erscheint im PDF nicht mehr. Feste Werteliste: Sehr
  gering, Gering, Gering bis mittel, Mittel, Gering bis hoch, Hoch, Kein
  Handlungsbedarf. Was der Aufwand konkret umfasst, gehört ans Ende der
  `recommendation`.
- **`sources.groups[].items` sind Objekte mit `label`, keine Zeichenketten.**
  Der Renderer liest `it.label` und optional `it.url`. Eine Liste aus Strings
  rendert als Folge leerer Zeilen mit Trennlinien: die Gruppentitel stehen da,
  darunter nichts. Es gibt keine Fehlermeldung, und im PDF sieht die Seite
  Quellen und Methodik nach einem Layoutfehler aus. Belegt am 17.09.2026.
- **HTML gilt nur in den Feldern, die der Renderer durch `safeHtml` schickt.**
  Das sind `cover.intro`, die Absätze in `exec.summary`, `chapters[].intro`,
  `chapters[].about`, `chapters[].findings[].body`, die Absätze in `market.narrative`,
  `market.callouts[].body`, `matrix.intro`, `matrix.takeaway`,
  `positioning.intro`, `positioning.positioningLine`, `geoGrid.intro` und
  `fahrplan.proj.text`. **Alles andere wird maskiert**, also stehen `<b>` und
  `<i>` dort im PDF als sichtbarer Code auf der Seite. Getroffen hat es am
  17.09.2026 `sources.methodik` und zwei `evidence`-Felder, in denen ein
  Subagent ein Anker-Element wörtlich zitiert hatte. In einem Beleg wird das
  Element deshalb benannt und sein sichtbarer Text zitiert, nicht sein Markup;
  die Zieladresse gehört ohnehin in `url`.
- **`exec.teaserFindings` steht in keinem gerenderten Report und ist trotzdem
  Pflicht.** Dieser Renderer setzt das Feld nicht, es trägt den Drei-Punkte-Block
  der Teaser-Mail in `audit-light-send`. Wer es weglässt, weil es im PDF nirgends
  auftaucht, verschickt eine Mail mit einem leeren Block, und auch das meldet
  nichts. Drei Einträge `{title, body}`, `body` ein bis zwei Sätze, **reiner
  Plaintext**: die Mail maskiert HTML und zeigte die Tags sonst als Text.

**Jeder einleitende Fließtext hat ein Zeichenbudget, und es wird gezählt, bevor gerendert wird.**
`cover.intro` bis 200, jeder Absatz in `exec.summary` bis 250 bei zwei Absätzen, jeder
`chapters[].intro` und `geoGrid.intro` bis 250, jeder Absatz in `market.narrative` bis 400.
Befundtexte haben kein Budget. Am 20.09.2026 war der Einstieg eines Laufs auf 4.057 Zeichen
gewachsen, jeder Absatz für sich belegt und richtig; im PDF schob die Zusammenfassung ihre eigene
Merksatzliste auf eine zweite, fast leere Seite. Yves: *"Wer soll den lesen? Den liest doch
niemand."* Ist die Skill `workos:report` installiert, hält sie Tabelle, Prüfbefehl und
Herleitung dazu; ohne sie gelten die Budgets hier.

**Fünf Blöcke tragen die Zahlen, damit der Fließtext sie nicht tragen muss.**
Am 16.09.2026 stand ein fertiger Report mit rund 59.000 Zeichen Befundtext und drei
Kapiteln aus reiner Prosa. Yves dazu: *"Das ist viel zu viel Text. Bspw. in den
Sektionen. Können wir da nicht noch mit weiteren visuellen Elementen arbeiten. Also
vielleicht grafisch anzeigen, was schon funktioniert oder andere reporting elemente
nutzen, wie graphen etc.?"* Alle fünf sind optional, und alle fünf verlangen dieselbe
Disziplin: **jede Zahl darin ist im Lauf belegt, keine ist geschätzt.**

- **`chapters[].signals`**, drei bis vier Kacheln je `{value, unit, label}`, gesetzt
  unter der Kapitelüberschrift als Leiste "Was hier trägt". **Sie ersetzen die
  Stärken-Befunde als Text:** ein `ok`-Befund kostet als Block so viel Platz wie ein
  kritischer und wiegt beim Lesen genauso schwer. Nach dem Setzen der Kacheln fliegen
  die `ok`-Befunde aus `findings` heraus. Ein Eintrag ohne gemessene Zahl gehört nicht
  in eine Kachel, sondern bleibt ein Befund.
- **`chapters[].bars`** mit `chapters[].barsTitle`, zwei bis vier Einträge je
  `{label, value, total, tone}`, `tone` aus `good`, `bad`, `neutral`. Der Balken zeigt
  immer Zähler und Nenner im Klartext daneben, damit die Grafik nichts verbirgt. Ein
  Anteil ohne belegten Nenner wird nicht gezeichnet.
- **`geoGrid`** auf oberster Ebene: das Raster der KI-Sichtbarkeit, je Frage eine
  Zeile, je Plattform eine Spalte, Zellwerte `both`, `brand`, `other`, `domain`, `none`. Der
  Kernbefund dieses Audits ist ein Muster über 27 Antworten, und ein Muster gehört in
  ein Raster, nicht in einen Absatz. Gebaut wird es aus `geo.json > queries` über
  `brand_mentioned` und `domain_cited`, nie aus dem Fließtext eines früheren Reports.
- **`chapters[].score` und `chapters[].target`**, der Bereichswert im Kapitelkopf, in
  derselben Optik wie die Säulenkarte auf Seite eins. Yves am 16.09.2026: *"Können wir
  noch den ptai score in jedes Kapitel integrieren. Damit man noch mal weiss, wie die
  einzelnen Unterpunkte scoren."* Die Werte kommen aus demselben Lauf der Score-Engine
  wie `exec.scores`, nie von Hand.
- **`chapters[].about`**, zwei bis drei Sätze direkt unter der Kapitelüberschrift, vor dem
  Score: was der Bereich ist, was darin geprüft wurde und was der Leser im Kapitel findet.
  Kein Befund, keine Zahl, kein Urteil; das trägt `intro` darunter. Gilt für jedes Kapitel.
  Eingeführt am 24.09.2026 nach einem Lauf, Yves: *"Was ist das eigentlich? Was
  wird in der Sektion ausgegeben? Was wurde hier geprüft?"* HTML wie in `intro`.
- **Zellwert `other` im `geoGrid`** heißt: die Marke wird genannt, als Quelle stehen aber
  fremde Seiten (`other_citations` nicht leer, `domain_cited` false). `brand` bleibt für
  Antworten ganz ohne Quellenliste. Ohne diese Trennung sahen im Raster eines Laufs
  ChatGPT ohne Quellen und Perplexity mit einem Händler und einem Wettbewerber als Quelle
  gleich aus. Yves:
  *"Das sieht ja aus, als würden die in AI echt gut dastehen, weil die Marke genannt wurde."*
  Die Farben laufen seit dem 24.09.2026 als Blau-Abstufung, je dunkler desto besser; rot ist
  nur `other`, der Zustand mit Handlungsbedarf.
- **`chapters[].methoden`**, fünf kurze Einträge, nicht sieben lange. Der Block steht
  seit dem 24.09.2026 am Kapitelende, nach den Befunden, wie eine Quellenangabe. Vor den
  Befunden brach er über den Seitenumbruch. Was ausführlich hingehört, steht in "Quellen
  und Methodik".

**Der Score wird auf den konsolidierten Befunden gerechnet, nicht auf den Linsen-Befunden.**
Die Säulen-Agents in Stufe 3 führen zusammen, was zwei Linsen gefunden haben; wer danach
`findings.json` aus Stufe 1 in die Engine gibt, zählt jede Dublette doppelt. Am 16.09.2026
kostete das einen Shop zehn Punkte (30 statt 40), und der Fehler fiel nur auf, weil Yves
die Zahl nicht glaubte. Bau die Score-Eingabe aus `chapters[].findings` und gib jedem
Eintrag seine `confidence` mit, sonst rechnet die Engine mit dem Vorgabewert 0,7.

**Ist `workos:report` installiert, lädt der Lauf sie für Tonfall und Prüfungen**,
bevor der erste Satz entsteht. Sie hält die vier Textarten im Report auseinander
und ruft `workos:voice` für Cover-Headline und Schlussblock. Wo sie dieser Skill
widerspricht, gilt diese Skill.

Was hier gilt, ob sie installiert ist oder nicht:

- **Kein Tech-Jargon in der Außenschicht** (`cover`, `exec`, `scores[].caption`,
  `market.callouts`). Kein "JSON-LD", "Canonical", "DOM", keine Selektoren, keine
  Dateinamen. Die Mechanik gehört in die Befunde, dort ist Tiefe erwünscht.
- **Der Aufmacher hängt am stärksten Einzelfund**, nicht an einer Hausthese, und
  er ist nie ein Vorwurf. Test: zuckt der Inhaber zusammen, oder denkt er "das
  schau ich mir an"?
- **Das Cover trägt immer einen Aufmacher zum stärksten Befund**, nie eine
  Dokumentzeile. Ist das Pitch-Gate noch nicht bestätigt, steht dort ein
  Vorschlag, und die Übergabe legt ihn zur Bestätigung vor.
- **Die Zusammenfassung argumentiert.** `exec.headline` spitzt den stärksten
  Befund zu, `exec.summary` hat zwei Absätze: was trägt, dann das Muster der
  Lücken, beide mit Zahlen. Sie beginnt nie mit dem Prüfumfang ("Ich habe ...
  durchgesehen"), der steht unter Quellen und Methodik.
- **Das Scoring bleibt `exec.scoreStyle: "potenzial"`.** Eine andere Darstellung
  entscheidet Yves.
- **Die Bereiche heißen wie im ausführlichen Audit:** Akquisition, Conversion Rate
  Optimierung, Trust und Compliance, darunter "Ziel X nach Umsetzung der Maßnahmen
  in diesem Bereich". Selbst gebaute Namen wie "Gefunden werden" oder "Kaufen" gibt
  es nicht.

Die letzten vier Regeln stammen aus einem Report vom 10. und 11.09.2026: Platzhalter
statt Headline, ein Einstieg, der nicht argumentiert, Ampel statt Score, selbst
gebaute Bereichsnamen.

---

## Übergabe

1. Das Beleg-Gate hat in Stufe 2 schon entschieden. Die Übergabe nennt in einem
   Satz, wie viele Befunde korrigiert und wie viele gestrichen wurden, ohne Liste
   zur Freigabe. `verify.md` bleibt als Beleg im Lauf-Ordner.
2. `<run>/report.pdf` öffnen und durchsehen:
   - Ist jeder Befund belegt und der Beleg anklickbar?
   - Steht irgendwo eine Umsatz- oder Traffic-Behauptung über eine Einzelseite?
   - Behauptet ein Befund, ein sichtbares Element fehle, ohne Screenshot-Beleg?
   - Hat jedes Kapitel mindestens einen Stärken-Befund?
   - Nennt "Quellen und Methodik" die Sichtprüfung mit Datum und die GEO-Fragen?
   - Passt alles ins A4-Layout, nichts abgeschnitten?
3. Passt es: `/ptai-ecom:audit-light-send <audit-id>`.

---

## Fehlerbilder

- **`audit.account` liefert `ambiguous`:** zwei Kunden tragen dieselbe Domain.
  Nicht raten, den Betreiber fragen. Meist ist einer eine Dublette.
- **`audit.account create` endet mit 3:** der Kundenordner für den Slug existiert
  schon. Die Meldung nennt beide Wege, der Betreiber entscheidet von Hand.
- **`audit.account` endet mit 4:** `PTAI_ACCOUNTS_ROOT` zeigt auf keinen Ordner.
  Pfad prüfen; liegt er in einem Cloud-Ordner, ob der eingebunden ist.
- **`missing()` meldet `page_types`:** der Crawl lief nicht oder schrieb kein
  `crawl.json`. Ohne Seitentypen misst `pull-cwv` nur die Startseite.
- **`check-geo` oder `pull-cwv` melden "nicht angeschlossen":** ein Schlüssel
  fehlt. `python3 -m audit.env` zeigt je Schlüssel die Quelle, ohne je einen Wert
  auszugeben. Fehlt er auch zentral, gehört er nach `~/.config/ptai-ecom/.env`.
  Die betroffene Plattform wird `null`, nicht `false`, und der Report weist sie
  als nicht geprüft aus. Kein Grund abzubrechen.
- **Chrome beendet sich nach dem PDF nicht:** bekannt, `render_pdf.sh` fängt es
  ab. Existiert die PDF und ist größer als 20 KB, ist der Render gelungen.
  **Nicht ein zweites Mal rendern** und nicht abschießen und neu starten, das war
  die Ursache eines eigenen Incidents.
- **Ein Lauf bricht mittendrin ab:** mit `--run <id>` in denselben Ordner
  fortsetzen. Vorhandene Snapshots werden nicht neu gezogen, bezahlte Aufrufe
  also nicht doppelt bezahlt.
