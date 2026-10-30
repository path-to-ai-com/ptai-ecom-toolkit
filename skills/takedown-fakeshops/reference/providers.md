# Melden je Anbieter

Wie man einen Fake-Shop bei jedem Anbieter meldet, der sich nicht automatisch melden lässt. Quelle für die Skill und für die öffentliche Meldeseite der Website. Nur Belegtes eintragen, mit Datum; was noch nicht gesehen wurde, steht unter "offen". Jede neue Meldung, die etwas Neues zeigt (ein Feld, eine Antwort, eine Ablehnung), wird hier nachgetragen.

## Wer ist zuständig

Ein Fake-Shop hängt an zwei Firmen:

- **Registrar:** bei ihm ist die Domain registriert. Sperrt er sie, ist sie weltweit weg (NXDOMAIN). Wirksamster Hebel; Registrare sind über ihren Vertrag mit der ICANN verpflichtet, Missbrauchsmeldungen anzunehmen.
- **Hoster:** auf seinem Server läuft die Seite. Nimmt er sie vom Netz, ist die Seite weg, die Domain bleibt.

Beide samt Abuse-Adresse findet `check-fakeshops` über RDAP. Von Hand: https://lookup.icann.org (Domain eingeben, Registrar und Abuse-Kontakt stehen in der Antwort).

Screenshots von Formularen für die Meldeseite nur mit Testdaten (Yves, 29.10.2026): kein echter Name, keine echte Mailadresse, keine Domain einer echten Marke oder eines echten Fakes. Beispielwerte: Name "Max Muster", Mail "max@beispielmarke.de", Marke "Beispielmarke" mit Shop "beispielmarke.de", Fake "beispielmarkepro.shop".

Zusätzlich, ohne Abschalten: Google Safe Browsing zeigt eine Warnung im Browser, bevor jemand den Shop betritt.

## Nachricht zum Kopieren

Englisch, weil die Abuse-Teams international arbeiten. Platzhalter in spitzen Klammern. Seit 29.10.2026 ohne Rabatt und ohne Firma (Yves): Der Rabatt ist je Fake verschieden und für die Meldung nicht nötig, als Absender genügt die Marke.

```
Subject: Suspected fake shop impersonating <MARKE>: <FAKE-DOMAIN>

Hello abuse team,

I am reporting the following website. It uses the brand name <MARKE> (official shop: <OFFIZIELLE-DOMAIN>), presents its products at implausible discounts and shows no company details or legal notice. <MARKE> does not operate or authorise this site.

- https://<FAKE-DOMAIN>/

Please suspend the domain and take the site offline, and preserve the account data for law enforcement. Screenshots are available on request.

Thank you,
<NAME>
<MARKE>
<E-MAIL>
```

Per Gmail als reine Textmail verschickt, werden die Adressen zu google.com/url-Umleitungen (28.10.2026). Darum die Domain zusätzlich ohne `https://` nennen oder als HTML senden.

## Google Safe Browsing

- Formular: https://safebrowsing.google.com/safebrowsing/report_phish/ (mit `?hl=de` auf Deutsch; die Feldnamen unten gelten für diese Fassung)
- Felder (gesehen 28.10.2026): URL, Kommentar (optional), Häkchen "Ich bin kein Roboter", Knopf "Senden".
- Felder (gesehen 29.10.2026, deutsche Fassung, das Formular hat sich seit dem 28.10. geändert):

| Feld | Eintrag |
|---|---|
| Art der Meldung (Pflicht) | "Diese Seite ist nicht sicher", ist vorausgewählt. Die andere Wahl ist "Diese Seite ist sicher" |
| Art der Bedrohung | "Social Engineering". Zur Wahl stehen None, Social Engineering, Malware, Unerwünschte Software |
| Kategorie der Bedrohung | "Phishing im Einzelhandel". Erst wählbar nach der Art der Bedrohung; bei Social Engineering stehen dort unter anderem Phishing im Einzelhandel, Sonstiges Phishing und Anderer Betrug |
| Betreffende URL (Pflicht) | `https://<FAKE-DOMAIN>/` |
| Weitere Informationen | der Kommentar unten, höchstens 800 Zeichen |

- Kein Häkchen mehr; die Robot-Prüfung läuft unsichtbar über reCAPTCHA (29.10.2026). Knopf "Senden".
- **Offen:** ob "Phishing im Einzelhandel" die passende Kategorie ist; gewählt nach der Liste vom 29.10.2026, noch in keiner echten Meldung verwendet.
- Eine URL je Meldung.
- Kommentar: ein Satz, etwa "Fake shop impersonating <MARKE> (official shop: <OFFIZIELLE-DOMAIN>), no company details, products at implausible discounts."
- Nach dem Senden zeigt die Seite keine verlässliche Bestätigung.
- Wirkung: Warnung in Chrome und anderen Browsern. Google nimmt nichts vom Netz. Die automatische Melde-API von Google schließt Fake-Shops ohne Phishing aus.

## Cloudflare

- Formular: https://abuse.cloudflare.com/
- Nur sinnvoll, wenn die Seite über Cloudflare-Server läuft (IP gehört zu AS13335). Cloudflare prüft nur URLs, die auf eigene IPs zeigen; nutzt der Fake Cloudflare nur für DNS, ist der Hoster zuständig.
- Typ: Phishing. Mehrere URLs je Meldung möglich.
- Im Kommentar um den Namen des Hosters bitten; Cloudflare nennt ihn nach einer vollständigen Meldung. Vorlage für den Kommentar (Meldeseite, 29.10.2026): der Text der Nachricht zum Kopieren ab "I am reporting", dazu der Satz "Please also tell me the name of the hosting provider."
- Lädt nicht in einem automatisierten Browser (28.10.2026).
- **Offen:** die einzelnen Felder und die Antwort von Cloudflare, beim nächsten echten Formular erfassen.

## Dynadot (Registrar)

- **Keine Meldung per Mail.** abuse@dynadot.com antwortet automatisch: "we do not accept, nor monitor, abuse reports via email" (28.10.2026).
- Formular: https://www.dynadot.com/report-abuse
- Lädt nicht in einem automatisierten Browser (29.10.2026).
- Feld "Abuse type" (gesehen 29.10.2026): Spam Abuse, Copyright Infringement, Phishing, Trademark/Cybersquatting, Child Sexual Abuse Imagery, Non-Consensual Sexually Explicit Imagery, Online Pharmacy, Fake Whois, Defamation: Libel, Malware/Botnet.
- **"Phishing" wählen.** Dynadot zählt Phishing zum "DNS Abuse", bei dem Registrare handeln müssen. "Trademark/Cybersquatting" kann in der Regel nur der Markeninhaber melden und läuft eher über das UDRP-Verfahren für Domainstreitigkeiten.
- **Eine Domain je Formular.** Bei mehreren Domains das Formular mehrfach ausfüllen.
- Bedingung für Phishing laut Formular: "The website must be live and contain a login area." Die Fake-Shops der Masche vom Oktober 2026 haben alle einen Kundenbereich unter `/account`; diesen Pfad angeben.
- Felder nach "Phishing" (gesehen 29.10.2026):

| Feld | Eintrag |
|---|---|
| Full Name, Email Address, Confirm Email Address | Absender |
| Phone Number | optional, leer lassen |
| Domain Name Involved | die Fake-Domain, ohne `https://` |
| Official Website | die offizielle Domain der Marke |
| VPN/Proxy location(s) and/or user-agent(s) required to view abuse | "N/A. No proxy needed. The site loads slowly (up to 60 seconds). If a browser shows a protocol error, it loads via HTTP/1.1, e.g. with curl." Die Fakes der Masche vom Oktober 2026 brachen in Chromium mit HTTP/2 ab; ohne den Hinweis sieht der Prüfer womöglich nur eine Fehlerseite |
| Full Domain Path | `https://<FAKE-DOMAIN>/`, die Startseite mit der kopierten Marke. Erscheint ein zweites Feld, dort `https://<FAKE-DOMAIN>/account` |
| Upload Files | optional; Screenshot der Startseite |
| Comments | optional; die Nachricht zum Kopieren, gekürzt auf diese Domain |
| Verification | Cloudflare-Prüfung, klickt der Mensch |

- **Wartezeit, steigend:** Nach zwei Meldungen sperrt Dynadot das Formular für rund fünf Minuten, nach der sechsten für eine Stunde (29.10.2026). Mehr als sechs Domains gehen nicht an einem Stück; über den Tag verteilen.
- Bestätigung (gesehen 29.10.2026): grüner Hinweis "Submission successful!" über dem Formular, keine Mail, keine Vorgangsnummer. Das Formular bleibt ausgefüllt; für die nächste Domain nur "Domain Name Involved", "Official Website", "Full Domain Path" und "Comments" ändern und die Cloudflare-Prüfung neu anklicken.

### Vorlage für die Meldeseite

So, Feld für Feld, steht es auf der öffentlichen Meldeseite. Platzhalter in spitzen Klammern; jeder Block ist einzeln kopierbar. Die Werte für die eigenen Fakes stehen im Report der Marke.

- Abuse type: **Phishing**
- Full Name: Name der meldenden Person
- Email Address, Confirm Email Address: ihre Adresse; dorthin gehen Rückfragen
- Phone Number: leer lassen
- Domain Name Involved: `<FAKE-DOMAIN>`, ohne `https://`, eine Domain je Formular
- Official Website: `<OFFIZIELLE-DOMAIN>`
- VPN/Proxy location(s) and/or user-agent(s):

```
N/A. No proxy needed. The site loads slowly (up to 60 seconds). If a browser shows a protocol error, it loads via HTTP/1.1, e.g. with curl.
```

- Full Domain Path: `https://<FAKE-DOMAIN>/`
- Upload Files: Screenshot der Startseite des Fakes, falls vorhanden
- Comments:

```
Fake shop impersonating <MARKE> (official shop: <OFFIZIELLE-DOMAIN>). It copies the brand name, logo and products, advertises implausible discounts, shows no company details or legal notice and has a customer login and a checkout. <MARKE> does not operate or authorise this site.
```

- Cloudflare-Prüfung anklicken, "Submit". Nach zwei Meldungen fünf Minuten warten, nach der sechsten eine Stunde.

## Spaceship (Registrar)

- Meldung per Mail an abuse@spaceship.com wird angenommen (28.10.2026).
- Antwort binnen Sekunden mit Vorgangsnummer im Betreff (Form "[SPS-IHT-0000]"). Bei Rückfragen auf diese Mail antworten, die Nummer im Betreff lassen.
- Spaceship meldet sich nur, wenn Angaben fehlen.
- Ob die Domain gesperrt ist: https://www.spaceship.com/domains/whois/; Status clientHold oder serverHold heißt gesperrt.
- Weitere Kontaktdaten zu Domaininhaber, Hoster oder Mailanbieter nennt Spaceship über das RrSG ACID Tool: https://acidtool.com/

## Hoster per Mail

- Abuse-Adresse aus RDAP oder von https://lookup.icann.org.
- Malakmadze Web LLC (AS199242), Hoster der Masche vom Oktober 2026: abuse@rashost.com. **Offen:** bis 29.10.2026 keine Antwort.
