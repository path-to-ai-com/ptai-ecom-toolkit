---
name: test-round
description: Die Testrunde vor einem Launch als `test.json` im Workspace der Brand schreiben, also die Anleitung, mit der das Team des Kunden einen neuen Shop, ein neues Theme oder eine größere Änderung testet, dazu die Schwerpunkte, die es bewertet und kommentiert. Hält Anrede, Begriffe und Prüfung vor dem Veröffentlichen. Nutzen bei "Testrunde", "Testanleitung", "test.json", "lass das Team testen" und bei jeder Änderung an einer bestehenden Testrunde, auch wenn nur eine Auflösung (`resolution`) dazukommt. Nicht verwenden für Audit und Monats-Report (ptai-ecom:audit, ptai-ecom:report).
---

# Testrunde

Eine Testrunde ist eine eigene Lauf-Art (`kind: test`, Lauf-ID
`JJJJ-MM-TT-test`). Sie liegt als `reporting/runs/<run-id>/test.json` im
Workspace der Brand, `publish` lädt die Datei unverändert hoch. Das Portal
liest sie nur: was das Team je Punkt auswählt und schreibt, speichert das
Portal getrennt davon.

## Aufbau

`title`, `intro`, optional `preview` (`label`, `url`), `sections` (je `id`,
`title`, `body`) und `groups` (je `id`, `title`, optional `lead`, `options`,
`items`). Ein Punkt in `items` trägt `id` im Muster `TP-01`, `title`, `text`
und optional `state`, `status` und `resolution` mit `text`, `images` und
`links`. Texte sind Markdown. Eine `resolution` trägt höchstens sechs Bilder,
`check-test-round` lehnt mehr ab.

## Die eine Stelle für Offenes

**Bei einem Kundenprojekt steht alles Offene in der Testrunde**: Aufgaben,
Fragen und Entscheidungen, auch die, die nur der Betreiber umsetzt. Keine
eigene Liste in Notion und kein Paperclip-Ticket dafür; Paperclip bleibt für
Arbeit, die Agents bauen. Das Team darf alles sehen, und der Betreiber geht im
Termin die Punkte auf `decision` durch, das ist die Agenda. Entschieden am
29.09.2026.

Sagt der Betreiber in einer Session "leg das in der Testrunde ab" oder "nimm
das in der Testrunde mit auf", entsteht ein Punkt mit `status`: ein neuer,
wenn es keinen passenden gibt, sonst eine Ergänzung am bestehenden. Das Portal
legt keine Punkte an, das Team kommentiert nur. Arbeiten mehrere Sessions an
derselben Datei, wird sie vor jedem Schreiben frisch gelesen und nur der
eigene Punkt geändert.

## Umsetzungsstand

**Jeder Punkt, an dem etwas zu tun ist, trägt `status`.** Das Portal zählt
ihn im Fortschritt auf dem Überblick, als eigenen Balken neben den
Maßnahmen (entschieden am 29.09.2026).

| `status` | Wann |
|---|---|
| `open` | die Aufgabe steht fest, ist aber noch nicht angefangen |
| `in_progress` | ich setze um |
| `decision` | wartet auf eine Entscheidung des Teams, auch wenn sie im nächsten Termin fällt |
| `done` | nichts mehr zu tun: behoben, entschieden und umgesetzt, oder bleibt wie heute |

Ein Punkt ohne `status` zählt nicht, etwa ein Schwerpunkt, den das Team ohne
Auffälligkeit bewertet hat. `state` ist freier Text für das Badge am Punkt
("Wie heute") und muss zum `status` passen; ohne `state` zeigt das Portal die
Anzeige des `status`. **Bei jeder neuen Auflösung und nach jedem Termin
`status` mitziehen**, sonst zeigt der Überblick einen alten Stand.

## Anrede

**Das Team wird mit "ihr" und "euch" angesprochen, nie mit "du".** Wo der
Betreiber handelt, steht "ich", nie "wir": "ich arbeite die Punkte ein",
"das Menü habe ich angepasst". "Wir" steht nur dort, wo Betreiber und Team
etwas gemeinsam tun ("im Wochentermin gehen wir die Punkte durch").
Dieselbe Regel gilt im Audit und im Monats-Report. Entschieden am 28.09.2026.

## Begriffe

Die Testrunde steht im Portal neben dessen Oberfläche, deshalb heißen die
Dinge dort genauso:

| Nicht | Sondern |
|---|---|
| Stand eines Punkts, "setzt den Stand" | Bewertung, "bewertet" |
| Rückmeldung, "schreibt als Rückmeldung" | Kommentar, "kommentiert" |
| Lauf | Testrunde |
| freigegeben | veröffentlicht |

Beispiel für den `lead` einer Gruppe: "Bewertet jeden Schwerpunkt, sobald ihr
ihn angeschaut habt, und schreibt Auffälligkeiten als Kommentar darunter."
Bis zum 28.09.2026 stand dort "Setzt je Schwerpunkt den Stand ... und schreibt
Auffälligkeiten als Rückmeldung darunter", während das Portal daneben
"Bewertung" und "Kommentar" sagte.

**Die `options` sind Statuswerte**, die das Portal als Bewertung anzeigt:
Fachbegriffe, höchstens 60 Zeichen, keine Umgangssprache. Ist
`workos:ui-text` installiert, gilt sie für diese Werte und für jeden `title`
und `lead`.

## Links

**Jeder Punkt, der etwas im Shop beschreibt, verlinkt die konkrete Seite**,
nicht die Startseite, im `text` oder in `resolution.links`. Geht es um einen
Unterschied, stehen beide Links nebeneinander: "In der Testansicht ansehen"
mit der ID des Entwurfs und "Im heutigen Shop ansehen" mit der ID des
Live-Themes, beide als `?preview_theme_id=<id>`.

**Auch der Link auf den heutigen Shop trägt eine Theme-ID.** Shopify merkt
sich eine Vorschau per Cookie. Wer vorher die Testansicht geöffnet hat, sieht
unter der normalen Shop-URL weiter den Entwurf und hält ihn für den heutigen
Shop. Belegt am 29.09.2026 in einer Testrunde, in der alle Links "Im heutigen
Shop ansehen" nach einem Klick auf die Testansicht den Entwurf zeigten. Die
beiden IDs stehen in der `CLAUDE.md` des Theme-Repos der Brand.
`check-test-round` meldet jeden Link auf den Shop ohne Theme-ID als Fehler.

## Prüfen und veröffentlichen

1. Jeden Text gegen Anrede und Begriffe oben lesen, auch jede `resolution`.
2. Die Datei im Portal-Repo prüfen: `npm run check-test-round`. Eine Datei mit
   Fehler zeigt das Portal gar nicht, nicht teilweise.
3. Veröffentlichen erst auf ausdrückliches Go des Betreibers. Aus
   `scripts/`: `python3 -m audit.publish --workspace <brand-repo> --run-id
   <run-id> --target <leerer Ordner> --note "<ein Satz>" --upload`. Die
   Zugangsdaten kommen aus `ptai-portal/.env.local` (`SUPABASE_URL` ist dort
   `NEXT_PUBLIC_SUPABASE_URL`). `~/.config/ptai-ecom/.env` zeigt auf ein
   anderes Supabase-Projekt ohne den Bucket `runs`; damit bricht der Upload mit
   HTTP 400 beim Lesen des Manifests ab. Belegt am 29.09.2026.
