# Rückfall

Stand 05.10.2026. Der Rückfall wird vor dem Launch geplant, nicht gesucht, wenn er gebraucht wird.
Er ist ein Klick, aber er dreht weniger zurück, als die meisten annehmen.

## Die Rückfallebene

- Das alte Theme bleibt nach dem Veröffentlichen als Entwurf in der Theme-Bibliothek. **Es wird nicht
  gelöscht**, auch nicht nach Wochen, sondern erst nach der Stabilisierung und mit Freigabe des Teams.
  Löschen ist bei Shopify endgültig.
- Bei einem Launch über Rollouts legt Shopify zusätzlich eine Sicherungskopie an; ein temporärer
  Rollout kehrt automatisch zurück.
- Die Sicherung aus Phase 1 und jede spätere datierte Sicherung liegen im Workspace. Sie sind
  Rückfallebene für Dateien, nicht für den Shop.

## Wann zurückgeschaltet wird

Die Kriterien stehen vor dem Launch schriftlich fest, mit der Person, die entscheidet. Beispiele für
ihre Form, die Schwellen legt das Team fest:

- Conversion Rate über einen festgelegten Zeitraum um einen festgelegten Anteil unter den
  Vergleichswerten direkt vor dem Launch, ohne andere Erklärung (Kampagne, Saison, Ausfall eines
  Zahlungsanbieters)
- Kaufabschluss in einem Gerätetyp oder einer Zahlart nicht möglich
- Fehlerseiten oder Statuscodes der Top-Seiten außerhalb der Erwartung
- ein Tracking-Ausfall, der Werbekampagnen blind optimieren lässt

Was live behoben werden kann, wird live behoben. Der Rückfall ist für den Fall, dass die Behebung
länger dauert als der Schaden tragbar ist.

## Wie zurückgeschaltet wird

1. Ein Mensch veröffentlicht das alte Theme in der Theme-Bibliothek oder beendet den Rollout.
2. Prüfungen wie am Launch-Tag (`launch-checklist.md`), gegen das alte Theme.
3. Den Stand festhalten: Zeitpunkt, Grund, wer entschieden hat.
4. Die Ursache am Entwurf beheben, an der Ursache (Mapping oder Generator-Regel), dann neu prüfen.
5. Vor einem zweiten Launch läuft der Abgleich erneut, weil das Team inzwischen am wieder
   veröffentlichten alten Theme gearbeitet haben kann.

## Was ein Rückfall nicht zurückdreht

Ein Zurückschalten wechselt nur das Theme. Alles, was im Admin geändert wurde, bleibt geändert:

- **Template-Zuweisungen.** Wurde ein Objekt auf ein Template umgestellt, das es nur im neuen Theme
  gibt, rendert es im alten Theme das Standard-Template.
- Redirects, Menüs, Seiten, Metafelder und Metaobjekte, Filter.
- Store-Übersetzungen.
- Checkout-Einstellungen, Pixel, Functions, Rabatte.
- **App-Deinstallationen.** Eine zwischenzeitlich deinstallierte App hat ihre Blöcke aus allen Themes
  entfernt, auch aus dem alten. Eine Neuinstallation stellt Blöcke und Einstellungen nicht wieder her.
- **App-Embeds** gelten je Theme. Im alten Theme sind sie so aktiv wie vor dem Launch; was nur im
  neuen Theme eingeschaltet wurde, fehlt dort.
- **Skript-Tags.** Seit 01.10.2026 lassen sich keine neuen anlegen oder ändern. Wurde ein Skript-Tag
  beim Umbau entfernt, kommt er nicht wieder, und ab 01.03.2027 lädt Shopify keine mehr
  (`platform-deadlines.md`).
- Änderungen, die das Team nach dem Launch im neuen Theme gemacht hat, fehlen im alten.
- Daten, die nach dem Launch gesammelt wurden (Bestellungen, Events), bleiben, wie sie entstanden sind.

Diese Liste sieht das Team vor dem Launch, nicht danach.

## Quellen

- https://help.shopify.com/en/manual/online-store/themes/managing-themes/publishing-themes
- https://help.shopify.com/en/manual/online-store/themes/managing-themes/duplicating-themes
- https://help.shopify.com/en/manual/markets/rollouts/rollout-types
- https://shopify.dev/docs/apps/build/online-store/theme-app-extensions/configuration
- https://shopify.dev/docs/apps/build/online-store/script-tag-deprecation/storefront

Ein offizielles Dokument mit genau dieser Liste gibt es nicht; sie ist aus dem abgeleitet, was am
Theme hängt und was im Admin liegt.
