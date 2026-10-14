---
name: sync-live-theme
description: Ermittelt, was sich im Live-Theme und auf Shop-Ebene seit der letzten Sicherung geändert hat und was davon in den Entwurf muss: Dateien je Manifest über Zeitstempel und SHA-256 (JSON normalisiert), Template-Zuweisungen, App-Embeds, Pixel, Skript-Tags, Hosts und Theme-Übersetzungen, je Änderung die betroffene Generator-Quelle und die Entscheidung take, adapt oder drop. Läuft in einer Migration vor der Abnahme, beliebig oft, und direkt vor dem Veröffentlichen, dazu eine Schlussprüfung unmittelbar vor dem Klick; ohne Migration als Wachposten. Es gibt keinen Änderungsstopp. Nutzen bei "was hat sich im Live-Theme geändert", "Abgleich mit dem Live-Stand", "Delta seit dem Snapshot", "letzter Abgleich vor dem Launch", in Phase 7 und Phase 9 einer Theme-Migration. Nicht verwenden für die erste Sicherung (ptai-ecom:snapshot-theme). Schreibt nichts in den Shop. Liest reporting/config.json im Kunden-Workspace.
---

# sync-live-theme: Abgleich mit dem Live-Stand

Während des Neubaus ändert das Team den laufenden Shop weiter, etwa eine Section, eine neue Kollektion
mit eigenem Template, eine Aktion oder eine neu installierte App. Das ist der Normalfall. Diese
Änderungen fehlen in der Sicherung, aus der der Generator baut, und damit im Entwurf. Diese Skill:

- findet die Änderungen
- ordnet jede einer Generator-Quelle zu
- legt die Entscheidung vor

Arbeitsverzeichnis: der Kunden-Workspace.

**Jede Shopify-Arbeit über die Shopify-Skills des Shopify AI Toolkit**, nie aus dem Gedächtnis, auch bei
den lesenden Abfragen dieses Abgleichs.

## Voraussetzungen

- `reporting/config.json` mit `shopify_store` und dem Block `theme_migration` (`live_theme_id`).
- Eine frühere Sicherung mit `manifest.json` (`snapshot-theme`) und, für die Shop-Ebene,
  `migration/inventory/templates.json`, `apps.json` und `translations.json`.

## Die Läufe

| Lauf | Wann | Umfang |
|---|---|---|
| **Abgleich** | Phase 7 (`7-sync`), nach der Kontrolle und vor der Abnahme, beliebig oft | voll: Dateien und Shop-Ebene, Entscheidung je Änderung, Übernahme in den Entwurf |
| **Abgleich vor dem Launch** | Phase 9, direkt vor dem Launch, durch den Betreiber (`theme-launch`) | voll, gegen die letzte Sicherung |
| **Schlussprüfung** | unmittelbar vor dem Veröffentlichen | nur `updatedAt` des Live-Themes und die Template-Zuweisungen; jede Änderung seit dem Abgleich vor dem Launch hält den Launch an |
| Wachposten | ohne Migration, auf Zuruf | voll, ohne Übernahme; Ergebnis ist nur `delta.md` |

## Ablauf eines vollen Laufs

1. **Dateien neu erheben:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" sync \
     --last migration/snapshots/<last-snapshot>/manifest.json \
     --out "migration/sync/<date>"
   ```

   Das Modul:
   - zieht die Metadaten des Live-Themes neu
   - vergleicht jede Datei mit dem Manifest (`updated_at`, SHA-256, JSON normalisiert)
   - holt geänderte und neue Dateien mit Inhalt und legt sie als neue datierte Sicherung ab
   - schreibt `delta.json` mit geänderten, neuen und gelöschten Dateien
   - lässt die frühere Sicherung unverändert

   Zwei Manifeste direkt vergleichen:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/theme" manifest diff \
     migration/snapshots/<old>/manifest.json migration/snapshots/<new>/manifest.json \
     --out "migration/sync/<date>/manifest-diff.json"
   ```

2. **Shop-Ebene neu erheben**, über die Shopify-Skills:
   - Template-Zuweisungen gegen `templates.json` (das Modul vergleicht sie mit): neue Objekte mit eigenem
     Template, geänderte Zuweisungen, Zuweisungen auf Suffixe, die im Entwurf fehlen.
   - App-Embeds aus der neuen `config/settings_data.json`, Web Pixels und Skript-Tags aus dem
     ausgelieferten HTML, fremde Hosts aus einem kurzen Mitschnitt der Beispielseiten, gegen `apps.json`.
   - Theme-Übersetzungen des Live-Themes gegen `translations.json`.

3. **Jede Änderung zuordnen:** betroffene Generator-Quelle (Datei der Sicherung, Vorlage, Eintrag im
   Mapping) oder außerhalb des Generators (neue App, Zuweisung, Übersetzung).

4. **`delta.md` schreiben**, eine Zeile je Änderung: was, wo, seit wann, betroffene Quelle, Vorschlag.
   Ein Mensch entscheidet:

   | Entscheidung | Bedeutung |
   |---|---|
   | `take` | so übernehmen, wie sie live ist |
   | `adapt` | im neuen Theme anders lösen |
   | `drop` | nicht übernehmen, mit Grund |

   Jede Entscheidung mit Person und Datum nach `migration/mapping/decisions.json` (`kind: sync`).

5. **Übernehmen:**
   - betroffene Quellen ersetzen; die neue datierte Sicherung wird Quelle des Generators
   - Mapping oder Overrides anpassen
   - dann `build-theme`, `upload-theme` und die betroffenen Prüfer von `verify-theme` für genau diese
     Teile
   - neue Apps durch `inventory-apps` führen; sie brauchen eine Entscheidung wie bei G1
   - geänderte Übersetzungen auf dem Entwurf neu registrieren

6. **Melden:** Zahl der Änderungen je Art, offene Entscheidungen, Teile, die neu gebaut und geprüft
   werden müssen. Die neue Sicherung ist ab jetzt die Grundlage für Abnahme und Launch.

Den Migrationsstand (`last_sync`, `snapshot`) schreibt `theme-migration`.

## Kein Änderungsstopp

Seit 0.3.11 gibt es keinen Stopp. Das Team arbeitet am Live-Theme weiter; jede Änderung kommt mit dem
nächsten Abgleich in den Entwurf. Direkt vor dem Launch läuft der Abgleich ein letztes Mal, danach hält
jede Änderung den Launch an (`reference/theme-migration/change-freeze.md`).

## Die Schlussprüfung

Unmittelbar vor dem Veröffentlichen, nach dem Go:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" PYTHONUTF8=1 python3 -c "
import json
from theme import guard, shopify
config = json.load(open('reporting/config.json'))
print(json.dumps(guard.live_fingerprint(shopify.transport_from_config(config))))
"
```

Dazu die Template-Zuweisungen gegen den Stand des Abgleichs vor dem Launch. Hat sich seitdem `updatedAt` des
Live-Themes oder eine Zuweisung geändert, **hält der Launch an**: ein voller Lauf für die geänderten
Teile folgt. Nie mit bekannter Lücke veröffentlichen.

## Ergebnis

- `migration/sync/<date>/` mit `delta.json` und `delta.md`.
- Eine neue datierte Sicherung unter `migration/snapshots/`.
- Entscheidungen in `decisions.json`.
- Im Workspace committet, namentlich gestagt.

## Fehlerbilder

- **Abgleich nur über `updatedAt` des Themes:** zeigt, dass sich etwas geändert hat, nicht was. Der volle
  Lauf vergleicht je Datei.
- **Nur Theme-Dateien abgeglichen:** neue Zuweisungen, Apps und Übersetzungen fehlen dann. Die
  Shop-Ebene gehört dazu.
- **JSON über `checksumMd5` verglichen:** Shopify serialisiert JSON neu; jeder Vergleich meldet
  Scheinänderungen. Das Modul vergleicht normalisiert.
- **Erste Sicherung überschrieben:** sie bleibt unverändert, jeder Lauf legt eine neue an.
- **Änderung nur in der erzeugten Datei übernommen:** der nächste Generatorlauf macht sie rückgängig. In
  Quelle oder Mapping übernehmen.
- **Änderung des Teams am Live-Theme:** Normalfall, ein Punkt in `delta.md`. Nach dem Abgleich vor dem
  Launch hält jede Änderung den Launch an.
