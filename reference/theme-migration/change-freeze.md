# Änderungsstopp

Stand 05.10.2026. Ein Shop steht während einer Migration nicht still, und er soll es auch nicht. Was
das Team am Live-Theme ändert, fehlt aber im Entwurf, weil der Generator aus der Sicherung baut.
Deshalb läuft der Abgleich zweimal (`sync-live-theme`), und zwischen den beiden Läufen gilt ein
Änderungsstopp für alles, was am Theme hängt.

## Zeitraum

| Von | Bis |
|---|---|
| Abschluss von Abgleich I (Phase 7), also wenn der Entwurf zur Abnahme geht | Veröffentlichen des neuen Themes (Phase 9) |

Der Zeitraum steht im Stand der Migration (`freeze_from`, `freeze_until`) und in der Konfiguration
(`theme_migration.freeze`). Verschiebt sich der Launch, verschiebt sich `freeze_until` mit, und das
Team erfährt es am selben Tag.

## Was eingefroren ist und was frei bleibt

| Eingefroren | Warum |
|---|---|
| Theme-Editor des Live-Themes (Sections, Blöcke, Einstellungen, Templates) | Theme-Inhalte gehen nicht mit, jede Änderung müsste in den Entwurf nachgezogen werden |
| Code des Live-Themes | dasselbe |
| neue Template-Zuweisungen auf Suffixe, die es im Entwurf nicht gibt | das Objekt fiele nach dem Launch auf das Standard-Template |
| App-Installationen und -Deinstallationen | eine neue App bindet sich nur ins Live-Theme ein, eine Deinstallation entfernt Blöcke aus allen Themes |
| Locale-Texte und Theme-Übersetzungen | hängen an der Theme-ID |
| Änderungen über eine verbundene GitHub-Anbindung | landen im Live-Theme |
| Änderungen durch Dritte: Agentur, Apps mit Schreibrecht ins Theme | dasselbe, nur unbemerkt |

| Frei | Warum |
|---|---|
| Produkte, Preise, Bestände | liegen im Admin, beide Themes teilen sie |
| Rabatte, Kollektionen ohne neues Template | dasselbe |
| Seiten und Blog | dasselbe |

**Daten erst nach dem Launch.** Geplante Massenänderungen an Shop-Daten (Texte, Titel, Menüs,
Weiterleitungen, Rechtstexte) laufen nicht während des Stopps, auch wenn sie frei wären. Sie wirken
sofort im laufenden Shop, ein Fehler trifft jede Seite, und ändern sich Daten und Theme im selben
Zeitraum, lässt sich eine Bewegung in Rankings oder Conversion keinem von beiden zuordnen. Sie werden
als Dateien vorbereitet und vom Team freigegeben und nach dem Launch in datierten Blöcken umgesetzt.
Ausnahme: ein Fehler in einem Rechtstext wird sofort korrigiert.

## Ausnahmen während des Stopps

Eine dringende Änderung am Live-Theme (ein Fehler, eine rechtlich nötige Anpassung, eine Aktion, die
nicht warten kann) ist erlaubt, wenn sie angekündigt wird. Sie wird dann in den Entwurf übernommen,
bevor Abgleich II läuft, und steht in `delta.md` mit Entscheidung.

## Text an das Team

Vorlage für die Ankündigung, Anrede "ihr" und "euch", der Betreiber spricht als "ich":

> Ab <freeze_from> bis zum Launch am <freeze_until> bitte keine Änderungen mehr im Theme-Editor und im
> Code des heutigen Themes, keine neuen Apps installieren oder entfernen und keine Texte in den
> Sprachdateien ändern. Produkte, Preise, Bestände, Rabatte, Seiten und Blog könnt ihr wie gewohnt
> pflegen. Braucht ihr trotzdem eine Änderung am Theme, sagt mir vorher Bescheid, dann übernehme ich
> sie in das neue Theme.

Die Nachricht schickt der Betreiber, nicht die Skill.

## Prüfung

Abgleich II vor dem Veröffentlichen zeigt jede Änderung am Live-Theme seit Abgleich I, dazu die
Template-Zuweisungen, App-Embeds, Pixel, Skript-Tags und Hosts. Eine Änderung, die nicht angekündigt
war, ist kein Vorwurf, sondern ein Punkt in `delta.md`. Jede Änderung nach Abgleich II hält den
Launch an.
