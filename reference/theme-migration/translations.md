# Übersetzungen

Stand 05.10.2026. Ein mehrsprachiger Shop verliert beim Theme-Wechsel keine Produktübersetzung,
aber jede Übersetzung, die am Theme hängt. Geht das neue Theme ohne sie live, stehen alle
Section-Texte in der Primärsprache.

Jede Abfrage und jede Mutation läuft über die Shopify-Skills des Shopify AI Toolkit, nie aus dem
Gedächtnis.

## Was am Shop hängt und was am Theme

| Am Shop, bleibt | Am Theme, muss neu registriert werden |
|---|---|
| `PRODUCT`, `COLLECTION`, `PAGE`, `ARTICLE`, `BLOG`, `MENU`, `LINK`, `FILTER`, `METAFIELD`, `METAOBJECT` und weitere Ressourcen | `ONLINE_STORE_THEME`, `ONLINE_STORE_THEME_JSON_TEMPLATE`, `ONLINE_STORE_THEME_SECTION_GROUP`, `ONLINE_STORE_THEME_SETTINGS_DATA_SECTIONS`, `ONLINE_STORE_THEME_SETTINGS_CATEGORY`, `ONLINE_STORE_THEME_LOCALE_CONTENT`, `ONLINE_STORE_THEME_APP_EMBED` |
| Shopifys Übersetzungsschicht, gelesen über `translatableResources` | Schlüssel mit Section- und Block-IDs des jeweiligen Themes, dazu `locales/*.json` |

Quelle: https://shopify.dev/docs/api/admin-graphql/2026-04/enums/TranslatableResourceType

**Theme-Übersetzungen hängen an der Theme-ID.** Ein neues Theme startet ohne sie, auch wenn es
dieselben Texte zeigt. Die Schlüssel verschachtelter Blöcke tragen die IDs der Section und aller
Eltern-Blöcke; ändern sich die IDs im Neubau, ändert sich der Schlüssel.

## Die Übersetzungsschicht ist die Schnittstelle, nicht die App

Die meisten Übersetzungs-Apps schreiben in Shopifys Übersetzungsschicht, und die Admin-API liest und
schreibt diese Schicht vollständig. "Die App hat keine API" ist deshalb kein Hindernis.

| App | Wo die Übersetzungen liegen | Was beim Theme-Wechsel zu tun ist |
|---|---|---|
| **Translate & Adapt** (Shopify) | Übersetzungsschicht; dokumentiert ist das nicht wörtlich, CSV-Export und API zeigen aber dieselbe Struktur | Store-Übersetzungen bleiben. Theme-Übersetzungen werden auf das neue Theme registriert. **Offen:** ob die App sie zwischen Themes kopiert; ein Community-Bericht sagt nein. Bis das am Entwicklungs-Store geprüft ist, gilt: selbst registrieren |
| **Langify** | laut App-Berechtigungen ebenfalls die Übersetzungsschicht | wie oben. Zusätzlich im Theme-Code nach Sprachumschaltern, eigenen Snippets und Metafeld-Umleitungen der App suchen; was das neue Theme ohnehin über die Schicht liest, wird nicht nachgebaut |
| Apps mit externer Auslieferung (Proxy, JavaScript) | beim Anbieter, nicht in Shopify | eigene Datenhaltung; bleibt außerhalb des Themes, Einbindung im neuen Theme prüfen. Ein Umstieg ist eine eigene Entscheidung, nicht Teil der Migration |

Translate & Adapt: https://help.shopify.com/en/manual/international/translate-adapt-app
Theme übersetzen: https://help.shopify.com/en/manual/online-store/themes/customizing-themes/language/translate-theme

## Bestandsaufnahme (Phase 2)

1. Veröffentlichte und unveröffentlichte Sprachen (`shopLocales`), Märkte und ihre Pfade.
   **Eine Sprachdatei im Theme beweist nicht, dass die Sprache im Shop veröffentlicht ist.**
2. Je Ressourcentyp: wie viele Objekte eine Übersetzung haben, wie viele `outdated` sind, ob
   marktspezifische Übersetzungen existieren.
3. Die Theme-Übersetzungen des Live-Themes je Theme-Ressourcentyp: Schlüssel, Ausgangswert,
   Übersetzung. Diese Werte sind die Quelle für das neue Theme. Ohne `read_translations` geht das nur
   über das Feld `translations(locale)` (Interface `HasPublishedTranslations`) und nur für
   veröffentlichte Sprachen.
4. Umleitungen im Theme finden: Snippets, die Übersetzungen aus eigenen Metafeldern, externen Diensten
   oder Verzweigungen auf die aktive Sprache holen. Liegen die Werte ohnehin in der Schicht, wird die
   Umleitung gestrichen.
5. Schreiber klären: wer schreibt heute in welche Sprache (App, Import aus ERP oder PIM, Dienst). Je
   Sprache genau ein Schreiber, sonst gewinnt der letzte Schreibvorgang. Die API zeigt nicht, wer
   geschrieben hat; das kommt vom Team.
6. Zahl der Theme-Übersetzungen, die im neuen Theme neu registriert werden müssen, in
   `translations.json`.

## Übertragen (Phase 4 und 5)

1. Alte Werte je Schlüssel den Schlüsseln des neuen Themes zuordnen. Die Zuordnung entsteht im
   Generator mit, weil er die neuen Section- und Block-IDs vergibt. Sprachdateien des neuen Themes
   gegen die alten auf Lücken prüfen.
2. Nach dem Upload die übersetzbaren Inhalte **vom Entwurf** lesen, mit frischen
   `translatableContentDigest`-Werten. Ein Digest gehört zum aktuellen Ausgangswert; ein alter Digest
   wird abgelehnt oder registriert gegen den falschen Stand.
3. Mit `translationsRegister` auf die Theme-ID des Entwurfs schreiben, in Paketen, Tempo nach dem
   Rate-Limit, bei `userErrors` anhalten.
4. Zurücklesen: jede registrierte Übersetzung ist vorhanden und nicht `outdated`.
5. **Store-Übersetzungen nie anfassen.** Sie gehören beiden Themes.

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.translations register \
  --theme <draft-theme-id> --source migration/build/translations.json
```

## Regeln, die aus Fehlern kommen

- **Ändert sich ein Ausgangswert, liefert Shopify weiter die alte Übersetzung aus**, bis neu
  registriert wird. Nach jeder Änderung an übersetzbaren Werten die betroffenen Schlüssel neu
  registrieren und in der Sprache nachmessen.
- Die Zuordnung der Übersetzungen wird im selben Commit wie jede Vorlagenänderung neu gebaut. Läuft
  sie hinterher, zeigen neue Schlüssel in der Zielsprache stumm den Text der Primärsprache.
- Eine unveröffentlichte Sprache fehlt in der Aufnahme, wenn nur über veröffentlichte Übersetzungen
  gelesen wurde.
- Handles übersetzen ist eine SEO-Entscheidung: für geänderte sprachspezifische Handles legt Shopify
  keine Weiterleitungen an.
- Eine selbstgebaute Übersetzungslösung über Metafelder stirbt mit dem Theme. Sie wird ersetzt, nicht
  nachgebaut.

## Prüfung je Sprache

- Jede Sprache und jeder Markt-Pfad im Browser mit `preview_theme_id`: Seitentitel und
  Meta-Beschreibung, H1, Kacheltitel, Warenkorb, Filter, Menü, Preisformat.
- Die Zeichenfolge `Translation missing` kommt im Quelltext nicht vor.
- hreflang steht genau einmal im Kopf (`seo-parity.md`).

## Limits

- Höchstens 3.400 Übersetzungen je Locale-Datei, 1.000 Zeichen je Wert, Locale-Dateien höchstens
  1,5 MB. https://shopify.dev/docs/storefronts/themes/architecture/locales
- Scopes für den Schreibweg: `read_translations`, `write_translations`, dazu lesend `read_themes`,
  `read_locales`, `read_markets` (`access-write.md`).
- Registrieren und Digests: https://shopify.dev/docs/apps/build/markets/manage-translated-content
