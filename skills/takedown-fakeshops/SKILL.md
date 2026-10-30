---
name: takedown-fakeshops
description: Meldet die offenen Fake-Shops einer Marke aus der Liste von check-fakeshops. Baut je Empfänger eine Mail an Registrar und Hoster (Abuse-Adressen aus RDAP, alle Domains eines Empfängers in einer Mail), verschickt sie direkt und hält jede Meldung in der Liste fest. Die Formulare von Google Safe Browsing und Cloudflare füllt sie im Browser aus; das Häkchen gegen Roboter setzt ein Mensch. Auslöser sind /ptai-ecom:takedown-fakeshops, "melde die Fake-Shops von X" oder offene Meldungen nach einem Lauf von check-fakeshops.
---

# takedown-fakeshops: Fake-Shops melden

**Argument:** Shop-URL oder Domain der Marke.

## Grundsätze

- **Mails gehen direkt raus, ohne Entwurf.** Entschieden von Yves am 28.10.2026: Ein Fake-Shop kostet jeden Tag Kunden, ein Entwurf, der liegen bleibt, schützt niemanden. Die Sicherung sitzt davor: gemeldet wird nur, was im Screenshot bestätigt ist.
- **Im Namen der Marke nur mit Auftrag.** Ohne schriftlichen Auftrag der Marke meldet der Absender in eigenem Namen "zum Schutz der Kunden" und schreibt "to our knowledge" statt einer Aussage für die Marke. Mit Auftrag `--on-behalf`.
- **Nur bestätigte Fakes.** Gemeldet wird, was `check-fakeshops` im Schritt "Ansehen und urteilen" bestätigt hat (`reviewed: true` in der Liste). Unbestätigte Vorurteile werden nicht gemeldet; vorher `check-fakeshops` laufen lassen.
- Was nicht geht, geprüft am 28.10.2026: Die Melde-API von Google (Web Risk Submission) schließt Fake-Shops ohne Phishing aus; die API von Cloudflare braucht eine eigene Freischaltung. Beide bleiben Formulare. Cloudflare prüft nur Shops hinter Cloudflare-IPs; nutzt ein Fake Cloudflare nur für DNS, ist der Hoster zuständig, und der bekommt die Mail.

- **Wissen je Anbieter** (Felder, Fallstricke, Antworten der Abuse-Teams) steht in `reference/providers.md`. Jede Meldung, die etwas Neues zeigt, wird dort nachgetragen; die öffentliche Meldeseite der Website übernimmt ihre Anleitungen von dort.

## Ablauf

Befehle aus `${CLAUDE_PLUGIN_ROOT}/scripts` mit `PYTHONPATH=.`.

### 1. Liste finden

- Kunde auflösen wie in `check-fakeshops`, Schritt 1. Liste `<drive_path>/fakeshops/fakeshops.json`.
- Keine Liste oder letzter Lauf älter als sieben Tage: abbrechen und `check-fakeshops` empfehlen. Eine Meldung über einen Shop, der schon weg ist, kostet Glaubwürdigkeit beim Abuse-Team.
- Offene Domains ohne `reviewed: true`: nicht melden, im Abschluss nennen.

### 2. Absender und Auftrag

- Absender aus der Umgebung, Suchreihenfolge wie überall (Umgebung, `.env` im aktuellen Verzeichnis, `~/.config/ptai-ecom/.env`): Firma aus `PTAI_OPERATOR_NAME`, Person aus `PTAI_OPERATOR_CONTACT`, Adresse aus `PTAI_OPERATOR_EMAIL`. Fehlt einer: abbrechen und melden, welcher.
- Auftrag der Marke: steht in der `entity.md` des Kunden ein Feld `fakeshop_mandate: true`, mit `--on-behalf`. Sonst ohne.

### 3. Paket bauen

```bash
PYTHONPATH=. python3 -m fakeshops.takedown --state <liste> --out-dir <lauf> \
  --sender-name "<Name>" --sender-org "<Firma>" --sender-email <adresse> [--on-behalf]
```

Erzeugt `takedown.json` und `takedown.md` im Ordner des letzten Laufs.

- Schon gemeldete Wege fehlen im Paket: Eine Domain, die bei einem Empfänger oder in einem Formular schon gemeldet ist, kommt dort nicht noch einmal hinein; erst wenn ein abgeschalteter Fake wieder erreichbar ist, wird neu gemeldet. `previously_reported` nennt sie.
- Der Text behauptet nur, was die Befunde aller Seiten einer Mail tragen (Rabatt, fehlendes Impressum). Passt die Einleitung trotzdem nicht zur Seite, etwa bei einem falschen Gewinnspiel, den Satz vor dem Versand anpassen, die Belegzeilen bleiben.
- Unterseiten auf einer Plattform (etwa `name.code.blog` bei WordPress.com) gehen nur an den Hoster; der Registrar der Plattform-Domain ist nicht zuständig.

### 4. Verschicken

- Je Eintrag in `mails` eine Mail mit dem Mail-Werkzeug der Session (etwa Gmail, `send_message`): Empfänger `to`, Betreff `subject`, Text `body` unverändert, dazu `html_body` als HTML-Fassung. Nur Klartext reicht nicht: Gmail schreibt darin jede Adresse zu einer google.com/url-Umleitung um (gesehen am 28.10.2026), und das Abuse-Team sieht die gemeldete Domain nicht mehr. Screenshots aus `<lauf>/screenshots/` anhängen, wenn das Werkzeug Anhänge kann; sonst bleibt der Satz "available on request" im Text.
- Nach jeder erfolgreich verschickten Mail sofort, je Domain der Mail:

```bash
PYTHONPATH=. python3 -m fakeshops.state reported --state <liste> --domain <d> --channel email --to <empfänger>
```

- Scheitert der Versand: nicht wiederholen, im Abschluss melden. Ohne Mail-Werkzeug: `takedown.md` ist das Paket, der Mensch schickt daraus.
- Antworten der Abuse-Teams am nächsten Tag lesen. Lehnt ein Registrar Mails ab und verweist auf ein Formular, trägt er sich in `REGISTRAR_FORMS` (`scripts/fakeshops/takedown.py`) ein; ab dann bekommt er keine Mail mehr, sondern ein Formular.

### 5. Formulare im Browser

Gilt nur für die Formulare in `forms`; Browser-Werkzeuge sonst nicht benutzen. Ohne Browser-Werkzeug in der Session: Formulare mit Link und Text in `takedown.md`, der Mensch füllt aus.

- **Google Safe Browsing** (`https://safebrowsing.google.com/safebrowsing/report_phish/`), eine URL je Formular: URL eintragen, Kommentar in einem Satz ("Fake shop impersonating <Marke>, official shop <domain>, no company details, products at <rabatt> % discount"). Das Häkchen gegen Roboter setzt der Mensch, nie die Skill, und er schickt ab. Ob es abgeschickt ist, bestätigt der Mensch; die Seite zeigt danach keinen verlässlichen Text (geprüft am 28.10.2026). Wirkung: eine Warnung in Chrome und anderen Browsern, kein Abschalten.
- **Cloudflare** (`https://abuse.cloudflare.com/`), nur für Domains in `forms` mit Kanal `cloudflare`, also Shops hinter Cloudflare-IPs. Typ Phishing, alle URLs in eine Meldung, Absender wie bei den Mails, Begründung aus der Mail. Im Kommentar um den Namen des Hosters bitten; Cloudflare nennt ihn nach einer vollständigen Meldung, danach geht eine Mail an dessen Abuse-Adresse. Das Formular lädt in einem automatisierten Browser nicht (geprüft am 28.10.2026, auch sichtbar); der Mensch füllt es aus, die Skill gibt ihm den Text aus `takedown.md`.
- **Registrar-Formulare** (Kanal `registrar_form`, etwa Dynadot unter `https://www.dynadot.com/report-abuse`): Registrare, die keine Mails annehmen. Begründung und Domains aus der Mail übernehmen. Die Seite von Dynadot lädt in einem automatisierten Browser nicht (geprüft am 29.10.2026); der Mensch füllt aus, die Skill gibt ihm den Text.
- Alle Formulare einer Runde nacheinander in Tabs vorbereiten, damit der Mensch die Häkchen in einem Durchgang setzt.
- Nach jedem abgeschickten Formular `reported` mit `--channel google`, `--channel cloudflare` oder `--channel registrar_form` je Domain.

### 6. Zurückstellen

Bewusst nicht melden (etwa: Marke klärt selbst mit ihrem Anwalt):

```bash
PYTHONPATH=. python3 -m fakeshops.state defer --state <liste> --domain <d> --by <person> --until <JJJJ-MM-TT> --reason "<grund>"
```

Ob eine Meldung gewirkt hat, zeigt der nächste Lauf von `check-fakeshops`: NXDOMAIN setzt die Domain auf `done` mit Datum.

## Abschluss

1. Zahl der verschickten Mails und an wen, dazu jede gescheiterte.
2. Formulare: abgeschickt, und welche noch auf ein Häkchen warten.
3. Domains ohne Abuse-Adresse und unbestätigte Domains.
4. Vorschlag für den nächsten Lauf von `check-fakeshops`, etwa in sieben Tagen, um die Wirkung zu sehen.
