# Fristen der Plattform

Stand 05.10.2026. Fristen, die eine Theme-Migration berühren. Jede gefundene Abhängigkeit kommt mit
Frist nach `migration/inventory/risks.json` und in die Entscheidungsliste vor Gate G1. Diese Datei
altert: vor jeder neuen Migration die Quellen erneut lesen und das Datum oben nachziehen.

| Was | Stand | Folge für die Migration | Quelle |
|---|---|---|---|
| **Skript-Tags im Storefront** | seit 01.10.2026 weder anlegbar noch änderbar, laufen aber weiter; ab 01.03.2027 lädt Shopify sie nicht mehr | jeder Skript-Tag braucht einen Nachfolger, meist ein App-Embed. Skript-Tags gibt es nur noch für Vintage-Themes. Wird einer gestrichen, die App deinstallieren, sonst lädt sie weiter. Ein entfernter Skript-Tag kommt nicht zurück | https://shopify.dev/docs/apps/build/online-store/script-tag-deprecation/storefront |
| Skript-Tags auf der Bestellstatusseite | seit 01.02.2025 nicht mehr anlegbar; abgeschaltet für Plus am 28.08.2025, für alle anderen am 26.08.2026 | nur noch aufnehmen, Ersatz sind Customer Account UI Extensions oder Web Pixels | https://shopify.dev/docs/apps/build/online-store/script-tag-deprecation/order-status |
| **Shopify Scripts** | Bearbeiten seit 15.04.2026 gesperrt, Ausführung seit 30.06.2026 beendet | was dort lief, läuft nicht mehr; Ersatz sind Functions. Aufnehmen, ob ein Rest im Theme darauf wartet | https://shopify.dev/changelog/posts/shopify-scripts-will-be-deprecated-on-june-30-2026 |
| **checkout.liquid und Additional Scripts** | checkout.liquid für Information, Versand und Zahlung nicht mehr unterstützt; checkout.liquid und Additional Scripts auf Dankes- und Bestellstatusseite für Plus seit 28.08.2025 abgeschaltet | gehört nicht zum Theme; Tracking, das dort lag, muss über Web Pixels laufen | https://shopify.dev/docs/storefronts/themes/architecture/layouts/checkout-liquid |
| Dankes- und Bestellstatusseiten | Upgrade-Frist 26.08.2026; nicht umgestellte Stores wurden automatisch umgestellt | Additional Scripts sind damit für alle aus; nur noch prüfen, ob die Messung des Kaufs heute über einen anderen Weg läuft | https://help.shopify.com/en/manual/checkout-settings/customize-checkout-configurations/upgrade-thank-you-order-status |
| **Klassische Kundenkonten** | seit 26.02.2026 abgekündigt, für neue Stores nicht mehr verfügbar, alle Händler müssen umstellen; ein Abschaltdatum für bestehende Stores ist nicht veröffentlicht | klassische Konten sind Theme-Templates (`templates/customers/*`), neue laufen unabhängig vom Theme. Läuft der Shop klassisch, entscheidet das Team vor G1, ob mit dem Theme umgestellt wird | https://shopify.dev/docs/apps/build/customer-accounts, https://shopify.dev/changelog/legacy-customer-accounts-are-deprecated |
| Checkout-Metafelder in UI Extensions | Umstieg auf Cart- und Order-Metafelder mit API 2026-04 | nur relevant, wenn Checkout-Erweiterungen eigene Felder lesen; nicht Teil des Themes | https://shopify.dev/changelog/release-notes/2026-04 |
| Rollouts | seit 05.06.2026 verfügbar, nicht für Vintage-Themes | Option für einen gestuften Launch (`launch-checklist.md`) | https://changelog.shopify.com/posts/schedule-publish-and-a-b-test-new-themes-and-checkout-and-customer-account-configurations |
| Barrierefreiheit (BFSG) | gilt seit 28.06.2025 für Online-Shops in der EU | das neue Theme wird gegen WCAG 2.2 geprüft (`verify-checklist.md`) | https://www.ihk.de/koeln/hauptnavigation/recht-steuern/barrierefreiheit-von-webseiten-dienstleistungen-und-produkten-5921172 |

## Ziel-Theme: Horizon

| Was | Stand | Folge |
|---|---|---|
| Versionen | keine Git-Tags und keine Releases; Versionen stehen als Commit-Titel und in `config/settings_schema.json` unter `theme_info.theme_version`. Stand 05.10.2026 ist 4.2.0 vom 18.09.2026 | Version und Commit beim Aufsetzen festhalten (`target_theme.ref`); `main` kann unveröffentlichte Funktionen enthalten |
| Farben | seit 4.0.0 vom 15.06.2026 keine Farbschemata mehr, stattdessen ein `color_palette` mit 2 bis 20 Farben | ein Mapping auf `color_scheme` ist für aktuelles Horizon falsch |
| Familie | Horizon, Fabric, Savor, Atelier und weitere teilen Unterbau und Versionsstand | dieselben Regeln gelten für jedes Theme der Familie |

Quellen: https://github.com/Shopify/horizon,
https://shopify.dev/docs/storefronts/themes/architecture/settings/input-settings,
https://changelog.shopify.com/posts/horizon-10-new-free-themes-by-shopify

## Wie die Fristen geprüft werden

- Skript-Tags aus `asyncLoad` im ausgelieferten HTML, nicht aus der Admin-API (die zeigt nur die der
  eigenen App).
- Kundenkonten im Admin unter Einstellungen, Kundenkonten, und an `templates/customers/*` im Theme.
- Shopify Scripts und Additional Scripts: das Team fragen und im Theme-Code nach Resten suchen.
