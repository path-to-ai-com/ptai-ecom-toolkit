---
name: check-geo
description: Prüft die GEO- bzw. AI-Sichtbarkeit der Kunden-Brand (Google-AI, ChatGPT, Perplexity) samt Crawler-Matrix aus robots.txt und llms.txt-Status und legt das Ergebnis als Snapshot ab. Der Weg folgt geo_method in der Config: api (Standard, per Script über OpenAI, Perplexity, Gemini-Grounding), browser oder off; der Lauf fragt nie nach. Einsetzen, wenn der Monats-Report GEO-Zahlen braucht oder der Nutzer ausdrücklich wissen will, ob Brand oder Domain in AI-Antworten vorkommen. Liest reporting/config.json und .env im Kunden-Workspace.
---

# check-geo: GEO-Sichtbarkeit prüfen

- Arbeitet das GEO-Query-Set aus der Config ab. Je Query und Plattform:
  - Nennt die AI-Antwort die Brand?
  - Ist die Domain als Quelle zitiert oder verlinkt?
- Dazu Crawler-Matrix aus `robots.txt` und llms.txt-Status per `curl` (nie ein Browser nötig).
- Weg laut `geo_method` in der Config:

| Wert | Weg |
|---|---|
| `api` | Standard, Script `geo_api.py` |
| `browser` | Browser-Protokoll unten |
| `off` | kein Lauf |

- Die Entscheidung fällt im Setup, nie im Lauf. In Report- oder Puls-Läufen stellt GEO keine Fragen und öffnet nichts unangekündigt.
- Aufruf durch den Monats-Report oder einzeln.
- Keine Historien-API: der Vormonats-Snapshot ist die einzige Vergleichsbasis, daher ist das Protokoll fest.
- Query-Set und Wettbewerberliste werden mit dem ersten Lauf eingefroren (Regel 9); jeder weitere Lauf nutzt diese Baseline, egal was später in der Config steht.

## Voraussetzungen

Im Kunden-Workspace (aktuelles Arbeitsverzeichnis):

- `reporting/config.json` mit:
  - `brand`, `domain`
  - `geo_queries` mit drei Gruppen: `brand`, `category`, `problem` (`problem` = Fragen ohne Markenbezug, die zur Kategorie führen, etwa "wo bekomme ich Outdoorjacken her")
  - `competitors` (Wettbewerberliste, leer erlaubt)
  - `sources.geo` ungleich `false`
  - `geo_method` (`api`, `browser` oder `off`). Fehlt das Feld (ältere Config): wie `api`, wenn mindestens ein GEO-Key gefunden wird (Workspace-`.env` oder zentral), sonst wie `browser`.
  - optional `google_domain` (nur Browser-Weg des Google-Checks, Standard `google.de`)
- Bei `geo_method: "api"`: API-Keys in der `.env` des Workspace oder zentral in `~/.config/ptai-ecom/.env`, jeder einzeln optional:

| Key | Plattform |
|---|---|
| `PTAI_OPENAI_KEY` | `chatgpt` |
| `PTAI_PERPLEXITY_KEY` | `perplexity` |
| `PTAI_GEMINI_KEY` | `google-ai` |

  Plattform ohne Key: "nicht angeschlossen", nie im Browser ersetzen.
- `python3` (3.10 oder neuer) für `geo_api.py`, `curl` für robots.txt und llms.txt.
- Bei `geo_method: "browser"`: Browser-Werkzeug in der Session; für ChatGPT eine eingeloggte Session auf chatgpt.com (Login macht der Mensch, nie der Agent).

Config fehlt oder `sources.geo` auf `false`: GEO als "nicht verfügbar (Grund)" melden und stoppen. Der Gesamtlauf (Report/Puls) scheitert nie daran. Ein fehlender Key blockiert nichts, und keine dieser Weichen löst eine Frage aus; alles steht in der Config.

## Protokoll-Regeln (hart, für die Vergleichbarkeit)

Die Snapshots sind nur als Zeitreihe nützlich.

1. **Queries wörtlich aus der Config.** Exakt wie in `geo_queries`. Nie umformulieren, ergänzen oder verbessern; eine andere Formulierung ist eine andere Zeitreihe.
2. **Feste Plattformen, feste Werte.** Genau drei, im Snapshot genau diese Strings: `google-ai`, `chatgpt`, `perplexity`. Je Query und Plattform genau eine Zeile, auch wenn nicht prüfbar. Zeilenzahl = Anzahl Queries mal drei.
3. **Felder je Zeile:**
   - `brand_mentioned`: Brand aus `config.brand` in der Antwort genannt, jede Schreibweise zählt.
   - `domain_cited`: Domain aus `config.domain` in Quellen oder Links der Antwort, Subdomains zählen mit.
   - `other_citations`: zitierte Fremd-Domains derselben Antwort, ohne eigene, dedupliziert (Ableitung unten). Steht in derselben Zeile, damit der Report den Share of Voice ohne zweiten Lauf rechnet.
   - `evidence`: ein Satz zum Inhalt der Antwort plus bis zu 3 Citation-Hosts.
4. **Ein Lauf je Query und Plattform, keine Wiederholung wegen des Inhalts.** AI-Antworten sind per API und Browser nicht deterministisch; Nachfassen bis zu einem besseren Ergebnis verzerrt die Zeitreihe. Wiederholung nur bei technischem Fehlschlag (API-Fehler, Seite nicht geladen).
5. **Nur, was zurückkam.** API-Pfad: nur `answer_text` und `citations` aus dem Script-Output. Browser-Pfad: nur, was auf dem Bildschirm stand. Kein Ergebnis aus Modellwissen, nichts vermuten oder erfinden. Unsicherheit ins `evidence`, nicht in einen geratenen Boolean.
6. **Nicht prüfbar = `null`, nicht `false`.**
   - Plattform nicht erreichbar (API-Fehler nach Wiederholung, kein Login, Captcha): jede betroffene Zeile `"brand_mentioned": null, "domain_cited": null`, `"evidence": "nicht prüfbar: <Grund>"`.
   - Kein Key und kein Browser: `"evidence": "nicht angeschlossen: kein API-Key"`.
   - So bleibt die Zeilenstruktur konstant, und ein Ausfall ist von einem echten Nein unterscheidbar.
7. **Gleiche Methode, Monat für Monat.**
   - Jede Zeile hat `method` (`api` oder `browser`).
   - Verglichen wird nur innerhalb derselben Kombination aus Plattform und Methode.
   - Ein Methodenwechsel (etwa `browser` auf `api`) wird im Report als Satz benannt, nie vermischt.
   - Browser-Weg: Google-SERP-Check ausgeloggt im Desktop-Viewport, jeden Monat gleich; Abweichungen ins `evidence`.
8. **Der Lauf fragt nie.** In Report- und Puls-Läufen keine Fragen, nichts unangekündigt öffnen. Methode, Query-Set, Umfang stehen vorher in der Config oder fallen im Setup. Fehlende Voraussetzungen ergeben `null`-Zeilen oder "nicht verfügbar (Grund)", nie eine Rückfrage.
9. **Query-Set und Wettbewerber sind mit der Baseline eingefroren.**
   - Erster Lauf (kein `geo.json`-Snapshot mit `query_set`, siehe Ablauf): beide Listen unverändert aus der Config übernehmen und als `query_set` und `competitors` in den Snapshot schreiben. Das ist die Baseline.
   - Jeder weitere Lauf: beide Listen wörtlich aus dem jüngsten Snapshot übernehmen, nie aus der aktuellen Config neu bilden, unverändert weiterschreiben.
   - Weicht die Config ab (Query ergänzt, entfernt, umformuliert; Wettbewerber geändert): die eingefrorene Liste bleibt maßgeblich, die Abweichung steht als `config_drift`-Satz im Snapshot und im Kernergebnis. Ohne diese Meldung bliebe eine gebrochene Zeitreihe unbemerkt.

## Ablauf

### 1. Config lesen und Methode bestimmen

Lesen: `brand`, `domain`, `geo_queries`, `competitors`, `geo_method`, optional `google_domain` und `geo_brand_terms`.

**Query-Set und Wettbewerber (Regel 9):** jüngsten `reporting/data/<datum>/geo.json`-Snapshot suchen (gleiche Suche wie für den Vormonats-Vergleich).

- Kein Snapshot, oder der jüngste hat kein `query_set` (ältere Snapshots): dieser Lauf ist die Baseline. Query-Set = Vereinigung der drei Gruppen aus `geo_queries` (`brand`, `category`, `problem`), Wettbewerber = `competitors`, beides unverändert aus der Config.
- Snapshot mit `query_set`: dessen `query_set` und `competitors` gelten wörtlich, unabhängig von der aktuellen Config.
- In beiden Fällen geltendes Set gegen die Config abgleichen. Bei Abweichung bleibt das geltende Set maßgeblich, die Abweichung wird `config_drift` (Regel 9), sonst `config_drift` = `null`.

Jede Query behält ihre Gruppe (`brand`, `category`, `problem`) für das Feld `group`.

`geo_method` ohne Rückfrage befolgen (Regel 8):

| `geo_method` | Vorgehen |
|---|---|
| `"off"` | Check endet hier. An den Report nur die Zeile, dass GEO bewusst abgeschaltet ist und über `/ptai-ecom:setup` aktiviert werden kann. |
| `"api"` | Gefundene Keys prüfen mit `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.env .` (Quelle je Schlüssel, nie der Wert). Plattformen mit Key laufen über das Script (Schritt 4); ohne Key `null`/`null`-Zeilen mit "nicht angeschlossen: kein API-Key", nie Browser-Ersatz, auch wenn ein Browser da ist. |
| `"browser"` | Alle drei Plattformen über das Browser-Protokoll (Schritt 5). Ohne Browser-Werkzeug: GEO "nicht verfügbar (geo_method browser, aber kein Browser-Werkzeug in der Session)". |
| Feld fehlt (ältere Config) | Wie `"api"`, wenn mindestens ein Key gefunden wird, sonst wie `"browser"`. |

Aufwands-Grenze: empfohlen höchstens etwa 8 Queries gesamt. API-Läufe sind billig, Browser-Läufe teuer. Ein zu großes Set wird im Setup verkleinert oder auf `api` umgestellt, nie im Lauf besprochen (Regel 8).

### 2. Crawler-Matrix

Ohne Browser: `curl -s <domain>/robots.txt` ziehen, je Crawler den Status bestimmen.

- Geprüfte Crawler, genau diese Schlüssel: `GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `ClaudeBot`, `Claude-Web`, `PerplexityBot`, `Google-Extended`, `CCBot`.
- `GPTBot` ist nur der Trainings-Crawler von OpenAI; Live-Zitate der ChatGPT-Suche laufen über `OAI-SearchBot` und `ChatGPT-User`, daher beide in der Matrix.

| Status | Bedingung |
|---|---|
| `erlaubt` | Eigene User-agent-Gruppe mit explizitem Allow oder ohne greifendes Disallow, und keine Pauschal-Sperre greift. Partielles Disallow (etwa `Disallow: /admin`) zählt als `erlaubt`, die Zeile steht als `rule` dabei. |
| `blockiert` | `Disallow: /` in der eigenen Gruppe oder in der `*`-Gruppe, wenn keine eigene existiert. |
| `nicht erwähnt` | Keine eigene Gruppe, `*` blockiert nicht; dann entscheidet `*`, das steht als Begründung dabei. |

- Je Crawler die entscheidende Zeile als `rule` schreiben, z. B. `{"GPTBot": {"status": "blockiert", "rule": "Disallow: /"}}`.
- robots.txt mit HTTP 404: keine Regeln, alle Crawler `nicht erwähnt` mit `"rule": "robots.txt nicht vorhanden (HTTP 404)"`.

### 3. llms.txt

`curl -sI <domain>/llms.txt`. HTTP 200 = `true`, alles andere `false`.

### 4. API-Checks (`geo_method: "api"`)

Je Query aus Schritt 1 auf jeder Plattform mit Key, nach den Protokoll-Regeln:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/check-geo/scripts/geo_api.py" \
  --platform <google-ai|chatgpt|perplexity> \
  --query "<Query wörtlich>"
```

Output: JSON mit `platform`, `answer_text`, `citations`, `model`. Daraus mechanisch:

**`domain_cited`**

- Host-Teil der Config-Domain (ohne Schema) gegen die Hosts der `citations` prüfen.
- Subdomain-tolerant: `www.example.de` und `shop.example.de` zählen für `example.de`.

**`brand_mentioned`**

- Case-insensitiver Substring von `config.geo_brand_terms` in `answer_text`; fehlt das Feld, gilt `brand`.
- **Nicht `brand` nutzen, solange `geo_brand_terms` gesetzt ist.** `brand` ist der Anzeigename und hat teils Zusätze, mit denen der Abgleich still nichts findet.
- Sanity-Blick der Session: offensichtliche Varianten (etwa Umlaut-Schreibweisen) zählen als Erwähnung, Vermerk im `evidence`.
- **Ist der Markenname zugleich Gattungsbegriff des Produkts, taugt der Substring-Abgleich nicht:** `brand_mentioned` = `null` statt `true` (Beispiel: eine Marke "Ledertasche" erscheint in jeder Antwort als Gattungswort). Dann zählt nur eine Nennung, die erkennbar den Anbieter meint; Begründung ins `evidence`, damit der Report keine Sichtbarkeit behauptet, die es nicht gibt.

**`other_citations`**

1. Je `citations`-Eintrag den Host ziehen: Schema, `www.`, Pfad und Query entfernen.
2. Eigene Domain samt Subdomains entfernen.
3. Dubletten entfernen, Reihenfolge der Antwort behalten.
4. Einträge, die schon eine blanke Domain sind, unverändert übernehmen (bei Google steht die Quelldomain neben der Redirect-URL, das Script nimmt sie mit).
5. Google-Redirect-Hosts der Grounding-API (etwa `vertexaisearch.cloud.google.com`) sind keine Quelle und entfallen; ein echter Domain-Eintrag daneben zählt.
6. Keine Citation = `[]`, nie `null`.

**`evidence`**

- Ein Satz zum Inhalt der Antwort plus bis zu 3 Citation-Hosts.
- Beispiel: "Antwort nennt drei Anbieter, Beispielshop nicht darunter; Quellen: wikipedia.org, fachportal.example, ndr.de".

**`brand_excerpt`**

- Bei `brand_mentioned` = `true`: Stelle mit der Brand **wörtlich** aus `answer_text`, höchstens 300 Zeichen; sonst `null`.
- Nicht zusammenfassen. Das Feld ist der Beleg für das Kriterium `geo.answer-accuracy` im Agent `audit-geo` (beschreibt die Antwort Marke, Sortiment und Preise richtig?); eine Zusammenfassung lässt sich nicht gegen den Shop prüfen.

**Technischer Fehlschlag (Exit 1):** einmal wiederholen (Regel 4); erneut gescheitert: Zeile "nicht prüfbar: API-Fehler: <Meldung>".

### 5. Browser-Protokoll (`geo_method: "browser"`)

Alle drei Plattformen im Browser der Session, `method: "browser"`.

| Plattform | Vorgehen |
|---|---|
| **google-ai** | `https://www.<google_domain>/search?q=<Query URL-kodiert>` öffnen, ausgeloggt, Desktop-Viewport (Regel 7). Consent-Wall ablehnen (nur notwendige Cookies, wo angeboten). AI-Overview-Block rendert progressiv: vollständig fertig werden lassen, sonst falsche Negative. Quellen aufklappen bzw. Inline-Zitate aus dem sichtbaren Block lesen. Kein AI Overview ist kein Fehler: beide Booleans `false`, Beleg "kein AI Overview für diese Query". |
| **chatgpt** | chatgpt.com mit eingeloggter Session (Login macht der Mensch, nie der Agent). Query wörtlich als Prompt, Websuche aktivieren, wo angeboten. Antwort fertig werden lassen, dann lesen. |
| **perplexity** | perplexity.ai (ohne Login möglich), gleiches Vorgehen. |

- `other_citations` wie im API-Weg, nur aus dem Sichtbaren: Hosts der Quellen am Antwortblock, ohne eigene Domain, dedupliziert. Keine Quellen sichtbar: `[]`.
- `brand_excerpt` wörtlich aus dem sichtbaren Antwortblock, höchstens 300 Zeichen, `null` ohne Erwähnung.
- Captcha oder fehlender Login: nicht lösen, nicht einloggen; betroffene Zeilen "nicht prüfbar: <Grund>" nach Regel 6.

### Zielordner

- Der Aufrufer bestimmt den Zielordner.
- Solo: Vorgabe `reporting/data/<heute>`.
- **Innerhalb eines Audit- oder Report-Laufs: `reporting/data/<run-id>`**, Datum plus Kadenz (`2026-10-01-audit`, `2026-11-01-month`).
- Der Orchestrator gibt den Ordner vor. Bei manuellem Start während eines Laufs dieselbe Lauf-ID verwenden.
- Ein Snapshot im falschen Ordner fehlt der Analyse, und sie rechnet ohne Fehlermeldung weiter.

### 6. Snapshot schreiben

`reporting/data/<heute>/geo.json` exakt nach dem Schema unten, mit geltendem `query_set`, geltenden `competitors` und `config_drift` aus Schritt 1. Diese Session baut das JSON selbst aus den Script-Outputs und dem im Browser Gesehenen.

### 7. Kernergebnis melden

- Zahl der Queries mit Brand-Erwähnung und mit Domain-Zitat, je Gruppe brand/category/problem
- die drei häufigsten fremden Zitat-Domains
- je Plattform die Methode (api/browser/nicht angeschlossen)
- Crawler-Blocker und llms.txt-Status
- Auffälligkeiten (etwa Kategorie-Queries ganz ohne Erwähnung)
- `config_drift` gesetzt: an erster Stelle nennen; der Vergleich beruht auf der eingefrorenen Baseline, nicht auf der aktuellen Config.

## Snapshot-Schema

`reporting/data/<heute>/geo.json`:

```json
{
  "fetched_at": "2026-08-10T12:00:00Z",
  "query_set": {
    "brand": ["Beispielshop", "Beispielshop Outdoorjacken"],
    "category": ["Outdoorjacke kaufen", "Outdoorjacken nach Maß", "Kinderset"],
    "problem": ["Wo bekomme ich Outdoorjacken her"]
  },
  "competitors": ["mitbewerber-b.example"],
  "config_drift": null,
  "queries": [
    {
      "query": "Beispielshop",
      "group": "brand",
      "platform": "google-ai",
      "method": "api",
      "brand_mentioned": true,
      "domain_cited": false,
      "other_citations": ["wikipedia.org", "ndr.de"],
      "evidence": "Antwort beschreibt Beispielshop als Outdoor-Anbieter; Quellen: wikipedia.org, ndr.de; Domain nicht dabei",
      "brand_excerpt": "Beispielshop ist ein Hamburger Versender für Outdoor-Bekleidung mit Jacken ab rund 80 Euro."
    },
    {
      "query": "Outdoorjacke kaufen",
      "group": "category",
      "platform": "chatgpt",
      "method": "api",
      "brand_mentioned": null,
      "domain_cited": null,
      "other_citations": [],
      "evidence": "nicht angeschlossen: kein API-Key"
    },
    {
      "query": "Wo bekomme ich Outdoorjacken her",
      "group": "problem",
      "platform": "perplexity",
      "method": "api",
      "brand_mentioned": false,
      "domain_cited": false,
      "other_citations": ["mitbewerber-b.example"],
      "evidence": "Antwort nennt zwei Fachversender, Beispielshop nicht darunter; Quellen: mitbewerber-b.example"
    }
  ],
  "crawlers": {
    "GPTBot": {"status": "blockiert", "rule": "Disallow: /"},
    "OAI-SearchBot": {"status": "erlaubt", "rule": "Disallow: /admin (partiell)"},
    "ChatGPT-User": {"status": "nicht erwähnt", "rule": "keine eigene Gruppe, * erlaubt"},
    "ClaudeBot": {"status": "nicht erwähnt", "rule": "keine eigene Gruppe, * erlaubt"},
    "Claude-Web": {"status": "nicht erwähnt", "rule": "keine eigene Gruppe, * erlaubt"},
    "PerplexityBot": {"status": "erlaubt", "rule": "Allow: /"},
    "Google-Extended": {"status": "nicht erwähnt", "rule": "keine eigene Gruppe, * erlaubt"},
    "CCBot": {"status": "blockiert", "rule": "Disallow: /"}
  },
  "llms_txt": false
}
```

### Regeln zum Schema

**Vergleich**

- Kein `period`-Block, kein `comparison`.
- Der Report vergleicht gegen den Vormonats-Snapshot (jüngster `reporting/data/`-Ordner mit `geo.json`), nur Zeilen mit gleicher Plattform **und** gleicher Methode (Regel 7).

**`queries`**

- Immer Anzahl Queries mal drei Zeilen.
- `platform` immer einer der drei festen Werte, `group` immer `brand`, `category` oder `problem`, `method` immer `api` oder `browser`.
- Nicht angeschlossene Zeilen (`geo_method: "api"`, Plattform ohne Key): `method: "api"` plus Grund im `evidence`.
- Nicht prüfbare Zeilen: `null`/`null` plus Grund im `evidence`, nie `false`.

**`query_set`, `competitors`, `config_drift`**

- `query_set` und `competitors` = eingefrorene Baseline (Regel 9): wörtlich aus dem ersten Lauf, in jedem Snapshot unverändert weitergeschrieben.
- `config_drift` = `null`, solange die Config mit beiden übereinstimmt; sonst ein Satz zur Abweichung, etwa "Config enthält eine zusätzliche category-Query ('Outdoorjacke Herren'), die nicht Teil der eingefrorenen Baseline ist; es zählt weiterhin die eingefrorene Liste".
- Gesetzter `config_drift` gehört ins Kernergebnis.

**`other_citations`**

- Immer eine Liste, nie `null`; bei nicht prüfbaren und nicht angeschlossenen Zeilen leer.
- Reine Hosts ohne Schema und `www.` (`ndr.de`, nicht `https://www.ndr.de/artikel`), ohne eigene Domain, ohne Dubletten.
- Grundlage des Share of Voice (Formel im Kennzahlen-Katalog); eine Domain zählt höchstens einmal je Zeile.

**`google-ai`**

- API-Pfad: Gemini mit Google-Search-Grounding als Proxy für Googles AI-Schicht, nicht das AI-Overview-Modul der SERP.
- Browser-Weg: der AI-Overview-Block der SERP.
- Darum vergleicht der Report nur innerhalb derselben Methode.

**`crawlers`**

- Alle acht Schlüssel; `status` ist `erlaubt`, `blockiert` oder `nicht erwähnt`; `rule` ist die entscheidende robots.txt-Zeile oder die kurze Begründung.
- Einzige Ausnahme: robots.txt nicht abrufbar. Dann statt der acht Schlüssel `{"error": "robots.txt nicht erreichbar nach 2 Versuchen: <Grund>"}` (Fehlerbilder), nie `null`.

## Setup-Check

Für den Setup-Wizard. `geo_method` wird im GEO-Abschnitt der Setup-Skill festgelegt; hier wird nur der gewählte Weg geprüft.

1. `api`: welche der drei Keys sind vorhanden? (`check_env.sh` zeigt sie samt Herkunft.) Je gesetztem Key ein Mini-Call:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/check-geo/scripts/geo_api.py" \
     --check <platform> -
   ```

   Eine OK- oder Fehlerzeile, Exit 0/1.
2. `browser`:
   - Browser-Werkzeug in der Session?
   - `google_domain` aus der Config lädt (Consent-Wall abgelehnt, SERP sichtbar)?
   - chatgpt.com zeigt eine eingeloggte Session? Sonst Hinweis an den Nutzer, sich einzuloggen; der Agent loggt sich nie selbst ein.
   - perplexity.ai lädt?
3. `off`: nichts zu prüfen.

Ausgabe: je Plattform der Stand (api, browser oder nicht angeschlossen). Eine angeschlossene Plattform plus Crawler-Matrix reicht für einen brauchbaren Snapshot.

## Fehlerbilder

| Fall | Verhalten |
|---|---|
| `geo_method: "off"` | Kein Lauf; der Report schreibt die Zeile, dass GEO bewusst abgeschaltet ist und über `/ptai-ecom:setup` aktiviert werden kann. |
| `geo_method: "api"`, Plattform ohne Key | Alle ihre Zeilen `null`/`null` mit "nicht angeschlossen: kein API-Key". Nie im Browser ersetzen, auch wenn einer da ist. Crawler-Matrix und llms.txt laufen per `curl` weiter; die Quelle gilt nicht als komplett ausgefallen. |
| API-Call scheitert (401, 429, Timeout, Netzfehler) | Einmal wiederholen (technisch, kein inhaltlicher Retry); erneut gescheitert: "nicht prüfbar: API-Fehler: <Meldung>". 401 heißt fast immer Key ungültig oder abgelaufen: im Kernergebnis melden. |
| `geo_method: "browser"`, kein Browser-Werkzeug | Quelle "nicht verfügbar (geo_method browser, aber kein Browser-Werkzeug in der Session)", ohne Rückfrage (Regel 8). |
| ChatGPT im Browser-Weg verlangt Login | Zeilen der Plattform nach Regel 6 auf `null`, fehlenden Login im Kernergebnis melden; kein Stopp, keine Frage im Lauf. Nie Zugangsdaten eingeben. |
| Captcha oder Bot-Erkennung im Browser-Weg | Nicht lösen, nicht umgehen; Zeilen "nicht prüfbar: Captcha". Nächster Monatslauf versucht es regulär erneut. |
| Kein AI Overview auf der Google-SERP (Browser-Weg) | Kein Fehler: beide Booleans `false`, Beleg "kein AI Overview für diese Query". |
| Browser-Antwort lädt endlos oder bricht ab | Einmal neu laden (technisch); erneut gescheitert: "nicht prüfbar: Seite lädt nicht". |
| robots.txt nicht erreichbar (Netzwerkfehler, kein 404) | `curl` einmal wiederholen; erneut gescheitert: `"crawlers": {"error": "robots.txt nicht erreichbar nach 2 Versuchen: <Grund>"}` schreiben, Grund melden. `llms_txt` bleibt boolesch: nur HTTP 200 ist `true`. |
| Wunsch, eine bessere Antwort nachzufassen | Ausgeschlossen. Regel 4: die erste Antwort zählt. |
