# Anpassungen: bestimmen, einordnen, migrieren

Stand 05.10.2026. Beantwortet die Frage, die jedes Team mit einem alten Custom-Theme stellt: "Ist
unsere Arbeit nach dem Wechsel weg?" Die Antwort lautet nein, aber nur mit dieser Liste. Ohne sie
ist sie eine Behauptung.

Liquid, Schemas und Block-Typen entstehen über die Shopify-Skills des Shopify AI Toolkit, nie aus
dem Gedächtnis.

## 1. Bestimmen: Diff gegen das Original

1. **Original in derselben Version besorgen.** Ein unverändertes Theme im Store, ein ZIP vom Team
   oder ein Entwicklungs-Store (`snapshot-theme --original`). Fehlt es, werden die Anpassungen als
   "nicht bestimmbar" vermerkt, statt gegen eine falsche Version zu raten. Ein Diff gegen die falsche
   Version macht jede Zeile zur Abweichung.
2. **Ein Original aus dem Store ist kein Werksstand.** Installierte Apps schreiben in jedes Theme des
   Stores, auch in unveröffentlichte. Vor dem Diff das Original nach Marken- und Domainspuren und
   nach Fremd-Skripten durchsuchen und die Treffer ausnehmen, sonst zählen sie als "vom Team
   gestrichen".
3. **Nur der Code-Teil geht in den Diff:** `layout/`, `sections/*.liquid`, `blocks/`, `snippets/`,
   `assets/`, `config/settings_schema.json`.
4. **Der Inhalts-Teil gehört nicht hinein:** `templates/*.json`, `config/settings_data.json`,
   `locales/` und `sections/*.json` (Section-Groups samt Markt-Varianten). Das sind Inhalte des
   Teams, keine Anpassungen, und sie erzeugen tausende Scheinbefunde.
5. **CSS erst normalisieren, dann zählen.** Ein neu gebautes Stylesheet meldet im rohen Diff ein
   Vielfaches dessen, was wirklich neu ist. Verglichen wird über die Selektoren.

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations diff \
  --original migration/snapshots/<original-snapshot> \
  --current migration/snapshots/<date>-<live-theme-id> \
  --out migration/inventory/customizations-candidates.json
```

Das Modul liefert Kandidaten mit Datei, Art und Umfang. Die Einordnung macht die Skill, mit Urteil.

## 2. Einordnen: vier Klassen

| Klasse | Was es ist | Was im Neubau passiert |
|---|---|---|
| **Funktion** | echte Zusatzfunktion, im Shop sichtbar und wirksam | nachbauen, nativ ersetzen, über eine App lösen oder streichen; Entscheidung in `map-theme` |
| **Gestaltung** | Farben, Abstände, Typografie | über die Einstellungen des Ziel-Themes, nicht über Code |
| **App-Rest** | Einbindung einer App im Code | gehört in `apps.json`, hier nur verweisen |
| **Altlast** | auskommentierter Code, tote Snippets, Reste abgeschalteter Apps | wird gestrichen |

Je Anpassung festhalten: Datei und Zeilenbereich, Klasse, was sie im Shop tut, ob sie sichtbar
genutzt wird, wer sie fachlich beurteilen kann.

**Gezählt wird nach der Einordnung, nicht davor.** "400 Abweichungen" trägt keine Entscheidung,
"zwölf Funktionen, dreißig Gestaltungen, der Rest Altlast" schon. Bei alten Custom-Themes ist der
überwiegende Teil Gestaltung und Altlast, und der Umbau ist damit kleiner als befürchtet.

## 3. Wirkung messen

**Eine Funktion zählt erst, wenn ihre Wirkung im Live-Shop gemessen ist.** Code beweist nur, was
beabsichtigt war. Eine Zeile, die laut Code ausverkaufte Produkte ausblendet oder eine bestimmte
Seitengröße setzt, kann im gerenderten Shop beides nicht tun. Wer nach dem Code baut, führt im Neubau
ein Verhalten ein, das es nie gab.

- Jede Anpassung mit sichtbarer Wirkung an mindestens einer lebenden Seite im Browser nachmessen.
- Gespeicherte Werte beweisen nicht, dass etwas zu sehen ist. Vor dem Übertragen einer Einstellung
  den Schalter suchen, der sie sichtbar macht, und im gerenderten HTML zählen, ob das Element
  überhaupt ausgegeben wird. Nachgebaut wird, was live zu sehen ist.
- Gestaltungswerte kommen aus der Messung (`design.json`), nicht aus `settings_data.json`. Eine
  Einstellung, die weder im Schema noch als `settings.<id>` im Code steht, ist tot; eine wirksame
  Einstellung, die in `settings_data.json` fehlt, ist ein Schema-Standard des Herstellers.

## 4. Entscheiden je Funktion

| Ausgang | Wann |
|---|---|
| `native` | das Ziel-Theme oder die Plattform kann es inzwischen selbst. **Nativ ersetzen schlägt nachbauen** |
| `app` | eine vorhandene App deckt es ab, im Ziel-Theme als Block oder Embed |
| `rebuild` | gibt es nativ nicht und wird gebraucht; als eigene Datei mit Präfix |
| `drop` | wird nicht gebraucht oder wirkt nicht; dem Team mit Begründung vorgelegt |

Jede Zeile bekommt eine Entscheidung mit Begründung und Person in `migration/mapping/decisions.json`,
keine bleibt offen. Was eins zu eins nachgebaut wird, obwohl die Plattform es kann, lässt die
Abhängigkeit sofort zurückwachsen.

## 5. Stille Abweichungen im Ziel-Theme

Abweichungen, die lokal niemand meldet und die erst im Bildvergleich oder in der Testrunde
auffallen. Jede ist eine Regel aus einem belegten Fehler.

**Generator und Upload**

- Ein fehlender Schlüssel in einer Template-JSON heißt Schema-Standard der Section, nie "aus". Wer
  `get(key)` ohne Standard liest, erzeugt leere Seiten und fehlende Brotkrumen.
- Korrekturen gehören in die Generator-Regel oder das Mapping, nie nur in die erzeugte Datei. Der
  nächste Lauf dreht sie sonst zurück.
- Quell-Themes speichern dieselbe Einstellung je Section-Typ unter verschiedenen Namen. Vor dem
  Schreiben einer Regel die tatsächlichen Schlüssel in den lebenden Templates zählen.
- Die Reichweite einer Einstellung im alten Code nachlesen: wirkt sie nur am Handy, nur am Desktop,
  ist eine Breite ein Textcontainer oder die Seitenbreite.
- Shopify verwirft Einstellungen, die der Block nicht kennt, ohne Fehler. Nur Einstellungen schreiben,
  die im Schema des Ziel-Blocks stehen. Kommt eine Einstellung erst mit demselben Upload ins Schema,
  die Block-Datei zuerst hochladen, danach die Templates.
- Eigenes CSS je Section ist auf 500 Zeichen begrenzt. Mehr lehnt Shopify nur für diese Datei ab, der
  Rest des Pakets landet trotzdem. Längeres CSS kommt in eine eigene Datei.
- Ein Upload hält beim ersten `userErrors` an. Danach jede Datei zurücklesen.
- Produktverweise in alten Templates zeigen auf gelöschte oder archivierte Produkte und rendern als
  Platzhalterkarte. Alle Handles über die Admin-API prüfen und die Blöcke im Generator deaktivieren
  statt löschen. Die öffentliche Abfrage je Produkt drosselt nach wenigen Dutzend Aufrufen.
- Block-IDs stabil und gültig erzeugen; Shopify lehnt bestimmte Zeichenfolgen in IDs ab.

**Darstellung**

- Ziel-Themes füllen leere Medien mit Platzhaltern, wo das alte Theme nichts zeigte. Platzhalter im
  Shop ausblenden, im Theme-Editor lassen (`request.design_mode`).
- Kundensichtbare Wörter kommen aus den Sprachdateien. Status- und Button-Texte beider Themes
  gegeneinander lesen.
- Kacheln können auf die kanonische Produktadresse oder innerhalb der Kollektion verlinken. Davon
  hängen die Brotkrumen auf der Produktseite ab. Vor dem Bau entscheiden, der Canonical bleibt in
  beiden Fällen die Produktadresse.
- Was nach dem Hinzufügen zum Warenkorb passiert (Weiterleitung, Schublade, Bestätigung am Button),
  unterscheidet sich zwischen Themes. Im alten Theme nachsehen und dem Team als Entscheidung vorlegen.
- Filter-Layouts, Menü-Ebenen am Handy, Logo-Position im Header und Zahlungslogos weichen ab. Am
  gerenderten alten Theme messen und als Entscheidung vorlegen, wo das Ziel-Theme es nicht nativ kann.
- Zahlungslogos nur für Zahlarten, die im Shop aktiv sind, und in der Auswahl des alten Themes.
- Die Darstellung einer Variantenoption hängt am Optionstyp, nicht am Namen. Optionsnamen des Shops
  auszählen, nie eine Namensliste pflegen.
- Zeilen mit Karten oder Buttons brechen am Handy um. Breiten, Abstände und Schrift live am Handy
  und am Desktop messen und im Generator setzen.
- Eine Section liest die Einstellungen ihrer Theme-Blöcke nicht. Braucht sie die Werte, bekommt sie
  eine eigene Einstellung.
- Das CSS aus `{% stylesheet %}` lädt nur für Dateien, die auf der Seite gerendert werden. Eine
  vorhandene Section erweitern statt nachbauen.
- Ein Ziel-Theme kann in WebKit Skriptfehler werfen, die Chromium nicht zeigt (Horizon 4.1.5:
  `requestIdleCallback` global in `assets/predictive-search.js`). Jede Prüfung auch in WebKit.

**Prüfen**

- Ein HTML- oder Stilvergleich übersieht Layoutfehler und Unsichtbares (eine berechnete, aber nicht
  sichtbare Abdunklung, eine Regel, die ins Leere greift). Jedes lebende Template einmal gerendert
  neben live legen, Desktop und WebKit im Handy-Format, und jedes Bildpaar ansehen.
- **"Wie im heutigen Shop" gilt für das ganze Element**, nicht nur für das beanstandete Detail. Jedes
  Element der Section messen (Maße, Schrift, Abstände) und als Bildpaar ansehen, bevor es als
  erledigt gilt.
- Eine Rückmeldung aus der Testrunde ist erst nach dem Nachstellen ein Fehler. Am Entwurf und live
  nachstellen, Desktop und WebKit, dann als Korrektur, Datenpflege, App oder Entscheidung einordnen.
- Die Vorschauleiste von Shopify verdeckt am Handy Buttons in App-Fenstern. Testanleitungen fürs
  Handy geben "Hide bar" vor; eine Meldung zu einem App-Fenster wird erst ohne Leiste nachgestellt.

## 6. Updatefähig bleiben: das Verzeichnis der Eingriffe

- Das Ziel-Repo enthält nur das Theme, mit dem Upstream als Remote `upstream`. Updates kommen per
  `git merge`, nie über den Update-Hinweis im Shopify-Admin.
- **Eigenes kommt in eigene Dateien** mit Präfix (`<file_prefix>-*.liquid`, `<file_prefix>-*.css`).
- Ein Eingriff in eine Datei des Ziel-Themes ist die Ausnahme. Er trägt im Code einen Kommentar mit
  `<file_prefix>:` und eine Zeile in `migration/customizations.md` mit Datei, Änderung, Grund und
  Prüfung nach dem Update.
- Inhalte (`templates/*.json`, `sections/*-group.json`, `config/settings_data.json`) sind Daten des
  Teams, keine Eingriffe.
- Die Prüfung läuft vor jedem Commit, der eine Datei des Ziel-Themes ändert, ohne Befund:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations check \
  --target-repo <target-repo> --prefix <file_prefix> \
  --register migration/customizations.md
```

Mit `--against upstream/<ref>` zeigt dieselbe Prüfung vor einem Update, welche verzeichneten
Eingriffe das Update berührt.

## Quellen

- https://shopify.dev/docs/storefronts/themes/architecture/templates/json-templates
- https://shopify.dev/docs/storefronts/themes/architecture/settings/input-settings
- https://shopify.dev/docs/storefronts/themes/architecture/limits
- https://shopify.dev/docs/storefronts/themes/store/success/updates
- https://github.com/Shopify/horizon
