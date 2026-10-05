---
name: sync-live-theme
description: Feststellen, was sich im Live-Theme und auf Shop-Ebene seit der letzten Sicherung geändert hat, und was davon in den Entwurf muss: Dateien je Manifest über Zeitstempel und SHA-256 (JSON normalisiert), Template-Zuweisungen, App-Embeds, Pixel, Skript-Tags, Hosts und Theme-Übersetzungen, je Änderung die betroffene Generator-Quelle und die Entscheidung take, adapt oder drop. Läuft in einer Migration zweimal, vor der Abnahme und direkt vor dem Veröffentlichen, mit dem Änderungsstopp dazwischen und einer Schlussprüfung unmittelbar vor dem Klick; ohne Migration als Wachposten. Nutzen bei "was hat sich im Live-Theme geändert", "Abgleich mit dem Live-Stand", "Delta seit dem Snapshot", "Änderungsstopp", "letzter Abgleich vor dem Launch", in Phase 7 und Phase 9 einer Theme-Migration. Nicht verwenden für die erste Sicherung (ptai-ecom:snapshot-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# sync-live-theme: Abgleich mit dem Live-Stand

Während am neuen Theme gebaut wird, arbeitet das Team im laufenden Shop weiter: eine geänderte
Section, eine neue Kollektion mit eigenem Template, eine Aktion, eine neu installierte App. Das ist
der Normalfall und kein Fehler. Diese Änderungen stehen aber nicht in der Sicherung, aus der der
Generator baut, und fehlen deshalb im Entwurf. Diese Skill findet sie, ordnet jede einer
Generator-Quelle zu und legt die Entscheidung vor.

Arbeitsverzeichnis ist der Kunden-Workspace.

**Jeder Handgriff an Shopify läuft über die Shopify-Skills des Shopify AI Toolkit**, nie aus dem
Gedächtnis, auch für die lesenden Abfragen dieses Abgleichs.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und dem Block `theme_migration` (`live_theme_id`).
- Eine frühere Sicherung mit `manifest.json` (`snapshot-theme`) und, für die Shop-Ebene,
  `migration/inventory/templates.json`, `apps.json` und `translations.json`.

## Die Läufe

| Lauf | Wann | Umfang |
|---|---|---|
| **Abgleich I** | Phase 7, nach der Prüfung und vor der Abnahme | voll: Dateien und Shop-Ebene, Entscheidung je Änderung, Übernahme in den Entwurf |
| **Abgleich II** | Phase 9, direkt vor dem Launch, nach dem Änderungsstopp | voll, gegen die Sicherung von Abgleich I |
| **Schlussprüfung** | unmittelbar vor dem Veröffentlichen | nur `updatedAt` des Live-Themes und die Template-Zuweisungen; jede Änderung seit Abgleich II hält den Launch an |
| Wachposten | ohne Migration, auf Zuruf | voll, ohne Übernahme; Ergebnis ist nur `delta.md` |

## Ablauf eines vollen Laufs

1. **Dateien neu erheben:**

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.sync \
     --last migration/snapshots/<last-snapshot>/manifest.json \
     --out "migration/sync/<date>"
   ```

   Das Modul zieht die Metadaten des Live-Themes neu, hält jede Datei gegen das Manifest (`updated_at`,
   SHA-256, JSON normalisiert), holt geänderte und neue Dateien mit Inhalt, legt sie als neue datierte
   Sicherung ab und schreibt `delta.json` mit geänderten, neuen und gelöschten Dateien. Die frühere
   Sicherung bleibt unverändert. Zwei Manifeste lassen sich auch direkt vergleichen:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.manifest diff \
     migration/snapshots/<old>/manifest.json migration/snapshots/<new>/manifest.json \
     --out "migration/sync/<date>/manifest-diff.json"
   ```

2. **Shop-Ebene neu erheben**, über die Shopify-Skills:
   - Template-Zuweisungen gegen `templates.json` (das Modul vergleicht sie mit): neue Objekte mit
     eigenem Template, geänderte Zuweisungen, Zuweisungen auf Suffixe, die es im Entwurf nicht gibt.
   - App-Embeds aus der neuen `config/settings_data.json`, Web Pixels und Skript-Tags aus dem
     ausgelieferten HTML, fremde Hosts aus einem kurzen Mitschnitt der Beispielseiten, gegen
     `apps.json`.
   - Theme-Übersetzungen des Live-Themes gegen `translations.json`.

3. **Jede Änderung zuordnen:** welche Generator-Quelle sie betrifft (welche Datei der Sicherung,
   welche Vorlage, welcher Eintrag im Mapping), oder ob sie außerhalb des Generators liegt (eine neue
   App, eine Zuweisung, eine Übersetzung).

4. **`delta.md` schreiben**, eine Zeile je Änderung: was, wo, seit wann, betroffene Quelle, Vorschlag.
   Die Entscheidung trifft ein Mensch:

   | Entscheidung | Bedeutung |
   |---|---|
   | `take` | so übernehmen, wie sie live ist |
   | `adapt` | im neuen Theme anders lösen |
   | `drop` | nicht übernehmen, mit Grund |

   Jede Entscheidung kommt mit Person und Datum nach `migration/mapping/decisions.json`
   (`kind: sync`).

5. **Übernehmen:** die betroffenen Quellen ersetzen (die neue datierte Sicherung wird Quelle des
   Generators), Mapping oder Overrides anpassen, dann `build-theme`, `upload-theme` und die betroffenen
   Prüfer von `verify-theme` für genau diese Teile. Neue Apps laufen durch `inventory-apps` und brauchen
   eine Entscheidung wie bei G1. Geänderte Übersetzungen werden auf dem Entwurf neu registriert.

6. **Melden:** Zahl der Änderungen je Art, offene Entscheidungen, welche Teile neu gebaut und geprüft
   werden müssen. Die neue Sicherung ist ab jetzt die Vorlage für Abnahme und Launch.

Den Stand der Migration (`last_sync`, `snapshot`) schreibt `theme-migration`.

## Der Änderungsstopp

Zwischen Abgleich I und dem Veröffentlichen gilt ein Änderungsstopp für alles, was am Theme hängt.
Nach Abgleich I schlägt die Skill den Umfang und den Zeitraum vor:

- **Eingefroren:** Theme-Editor und Code des Live-Themes, neue Template-Zuweisungen auf Suffixe ohne
  Datei im Entwurf, App-Installationen und -Deinstallationen, Locale-Texte und Theme-Übersetzungen,
  Änderungen über eine verbundene GitHub-Anbindung und durch Dritte (Agentur, Apps mit Schreibrecht
  ins Theme).
- **Frei:** Produkte, Preise, Bestände, Rabatte, Seiten und Blog, weil sie im Admin liegen und beide
  Themes sie teilen.
- **Daten erst nach dem Launch:** geplante Massenänderungen an Shop-Daten werden vorbereitet, aber erst
  nach dem Launch umgesetzt.

Der Text an das Team steht in `${CLAUDE_PLUGIN_ROOT}/reference/theme-migration/change-freeze.md`. Die
Nachricht schickt der Betreiber, nicht die Skill. Eine angekündigte Ausnahme wird vor Abgleich II in den
Entwurf übernommen.

## Die Schlussprüfung

Unmittelbar vor dem Veröffentlichen, nach dem Go:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c "
import json
from theme import guard, shopify
config = json.load(open('reporting/config.json'))
print(json.dumps(guard.live_fingerprint(shopify.transport_from_config(config))))
"
```

Dazu die Template-Zuweisungen gegen den Stand von Abgleich II. Hat sich `updatedAt` des Live-Themes
oder eine Zuweisung seit Abgleich II geändert, **hält der Launch an**: dann folgt ein voller Lauf für die
geänderten Teile, nie ein Veröffentlichen mit bekannter Lücke.

## Ergebnis

`migration/sync/<date>/` mit `delta.json` und `delta.md`, eine neue datierte Sicherung unter
`migration/snapshots/`, Entscheidungen in `decisions.json`. Committet im Workspace, namentlich gestagt.

## Fehlerbilder

- **Abgleich nur über `updatedAt` des Themes:** zeigt, dass sich etwas geändert hat, nicht was. Der
  volle Lauf vergleicht je Datei.
- **Nur Theme-Dateien abgeglichen:** neue Zuweisungen, Apps und Übersetzungen fehlen dann trotzdem.
  Die Shop-Ebene gehört dazu.
- **JSON über `checksumMd5` verglichen:** Shopify serialisiert JSON neu, jeder Vergleich meldet
  Scheinänderungen. Das Modul vergleicht normalisiert.
- **Die erste Sicherung überschrieben:** sie bleibt unverändert, jeder Lauf legt eine neue an.
- **Änderung übernommen, aber nur in der erzeugten Datei:** der nächste Generatorlauf dreht sie zurück.
  Übernommen wird in Quelle oder Mapping.
- **Änderung während des Stopps:** kein Vorwurf, ein Punkt in `delta.md`. Nach Abgleich II hält jede
  Änderung den Launch an.
