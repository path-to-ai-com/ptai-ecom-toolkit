---
name: test-round
description: Schreibt die Abnahme vor einem Launch als `test.json` in den Workspace der Brand. Die Abnahme ist die Anleitung, nach der das Team des Kunden einen neuen Shop, ein neues Theme oder eine größere Änderung testet, mit den Schwerpunkten, die das Team bewertet und kommentiert. Regelt Anrede, Begriffe und die Prüfung vor dem Veröffentlichen. Auslöser sind "Abnahme", "Testrunde" (der frühere Name), "Testanleitung", "test.json", "lass das Team testen" sowie jede Änderung an einer bestehenden Abnahme, auch das Ergänzen einer einzelnen Auflösung (`resolution`). Nicht verwenden für Audit und Monats-Report (ptai-ecom:audit, ptai-ecom:report).
---

# Abnahme

- Lauf-Art `kind: test`, Lauf-ID `JJJJ-MM-TT-test`.
- Datei: `reporting/runs/<run-id>/test.json` im Workspace der Brand.
- `publish` lädt die Datei ohne Änderung hoch.
- Das Portal liest die Datei nur. Bewertungen und Kommentare des Teams speichert es separat.

## Aufbau

| Ebene | Felder |
|---|---|
| Datei | `title`, `intro`, optional `preview` (`label`, `url`), `sections`, `groups` |
| `sections` | je `id`, `title`, `body` |
| `groups` | je `id`, `title`, optional `lead`, `options`, `items` |
| Punkt in `items` | `id` nach Muster `TP-01`, `title`, `text`, optional `state`, `status`, `resolution` |
| `resolution` | `text`, `images`, `links` |

- Alle Texte in Markdown.
- Höchstens sechs Bilder je `resolution`; bei mehr meldet `check-test-round` einen Fehler.

## Offene Punkte im Kundenprojekt

1. Alles Offene eines Kundenprojekts, das das Team sehen soll, steht in der Abnahme: Aufgaben, Fragen, Entscheidungen, auch solche, die nur der Betreiber umsetzt.
2. Dafür keine Liste in Notion und kein Paperclip-Ticket. Paperclip nur für Arbeit, die Agents bauen.
3. Das Team sieht alle Punkte. Die Punkte mit `status: decision` sind die Agenda des Termins mit dem Team.
4. Auftrag "leg das in der Abnahme ab" oder "nimm das in der Abnahme mit auf": einen Punkt mit `status` schreiben. Gibt es schon einen passenden Punkt, diesen ergänzen, sonst einen neuen anlegen.
5. Neue Punkte entstehen nur hier, das Portal legt keine an; das Team kommentiert nur.
6. Schreiben mehrere Sessions in dieselbe Datei: vor jedem Schreiben die Datei neu lesen und nur den eigenen Punkt ändern.

## Die Abnahme in einer Migration

In einer Theme-Migration gibt es eine Liste offener Punkte, `migration/open-items.json` (Skill `theme-migration`, Abschnitt "Die Liste offener Punkte"). Die Abnahme ist die Ansicht für das Team, der Stand steht in der Liste. Keine Liste ohne Verbraucher: die Testpunkte liest Gate G4, die Entscheidung über die Abnahme.

1. Nach jedem Schreiben der Abnahme jeden Punkt mit `status` in die Liste übernehmen:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items import --kind test-round --path reporting/runs/<run-id>/test.json
   ```

2. Erledigt, verschoben oder wieder offen wird ein Punkt in der Liste (`open_items done`, `defer`, `reopen`), mit Beleg oder mit Person und Datum. Eine `resolution` allein erledigt nichts.
3. Danach den Stand der Liste in die Abnahme zurückschreiben, damit das Portal dasselbe zeigt, und erst dann veröffentlichen:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" open_items sync-test-round --path reporting/runs/<run-id>/test.json
   ```

4. Ohne Migration (neuer Shop, größere Änderung ohne Theme-Wechsel) gilt die Abnahme allein, wie bisher.

## Umsetzungsstand

Jeder Punkt mit offener Arbeit bekommt `status`. Das Portal zeigt den Fortschritt auf dem Überblick als eigenen Balken neben den Maßnahmen. In einer Migration kommt `done` aus der Liste offener Punkte (`sync-test-round`), nicht von Hand.

| `status` | Wann |
|---|---|
| `open` | die Aufgabe steht fest, ist aber noch nicht angefangen |
| `in_progress` | ich setze um |
| `decision` | wartet auf eine Entscheidung des Teams, auch wenn sie im nächsten Termin fällt |
| `done` | nichts mehr zu tun: behoben, entschieden und umgesetzt, oder bleibt wie heute |

- Punkte ohne `status` zählen nicht für den Fortschritt, zum Beispiel ein Schwerpunkt, den das Team ohne Befund bewertet hat.
- `state` ist freier Text für das Badge am Punkt (zum Beispiel "Wie heute") und muss zum `status` passen.
- Fehlt `state`, zeigt das Portal den Wert von `status`.
- Nach jeder neuen `resolution` und nach jedem Termin `status` aktualisieren, sonst zeigt der Überblick einen veralteten Stand.

## Anrede

- Das Team: "ihr" und "euch", nie "du".
- Handlungen des Betreibers: "ich", nie "wir" (zum Beispiel "ich arbeite die Punkte ein").
- "wir" nur für Handlungen von Betreiber und Team zusammen (zum Beispiel "im Wochentermin gehen wir die Punkte durch").
- Dieselbe Regel gilt für Audit und Monats-Report.

## Begriffe

Die Abnahme verwendet dieselben Begriffe wie die Oberfläche des Portals.

| Nicht | Sondern |
|---|---|
| Stand eines Punkts, "setzt den Stand" | Bewertung, "bewertet" |
| Rückmeldung, "schreibt als Rückmeldung" | Kommentar, "kommentiert" |
| Lauf | Abnahme |
| freigegeben | veröffentlicht |

- Muster für den `lead` einer Gruppe: "Bewertet jeden Schwerpunkt, sobald ihr ihn angeschaut habt, und schreibt Auffälligkeiten als Kommentar darunter."
- `options` sind Statuswerte, die das Portal als Bewertung zeigt: Fachbegriffe, höchstens 60 Zeichen, keine Umgangssprache.

## Links

1. Jeder Punkt über den Shop verlinkt die betroffene Seite, nicht die Startseite, im `text` oder in `resolution.links`.
2. Bei einem Unterschied zwei Links nebeneinander: "In der Testansicht ansehen" mit der ID des Entwurfs und "Im heutigen Shop ansehen" mit der ID des Live-Themes, beide als `?preview_theme_id=<id>`.
3. Auch der Link auf den heutigen Shop enthält die Theme-ID, weil Shopify eine Vorschau per Cookie speichert und die normale Shop-URL danach weiter den Entwurf zeigt.
4. Beide IDs stehen in der `CLAUDE.md` des Theme-Repos der Brand.
5. `check-test-round` meldet jeden Shop-Link ohne Theme-ID als Fehler.

## Prüfen und veröffentlichen

1. Jeden Text auf Anrede und Begriffe prüfen, auch jede `resolution`.
2. Im Portal-Repo `npm run check-test-round` ausführen. Eine Datei mit Fehler zeigt das Portal komplett nicht an.
3. Veröffentlichen nur nach ausdrücklichem Go des Betreibers. Aus `scripts/`: `python3 -m audit.publish --workspace <brand-repo> --run-id <run-id> --target <leerer Ordner> --note "<ein Satz>" --upload`.
4. Zugangsdaten aus `ptai-portal/.env.local`; `SUPABASE_URL` heißt dort `NEXT_PUBLIC_SUPABASE_URL`.
5. Nicht `~/.config/ptai-ecom/.env` verwenden: sie zeigt auf ein anderes Supabase-Projekt ohne den Bucket `runs`, der Upload bricht dann mit HTTP 400 beim Lesen des Manifests ab.
