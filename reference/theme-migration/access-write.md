# Schreibzugang ins Theme

Stand 05.10.2026. Alle anderen Skills des Toolkits lesen nur. Die Theme-Migration braucht einen
Schreibweg, und nur `upload-theme` nutzt ihn, ausschließlich für ein Theme mit der Rolle
`UNPUBLISHED`. Veröffentlicht wird nie über diesen Zugang, sondern von einem Menschen im Admin.

Welche Flags und Mutationen heute gelten, wird vor dem Einsatz über die Shopify-Skills des Shopify AI
Toolkit geprüft, nie aus dem Gedächtnis.

## Zwei Wege

| | Konto mit Themes-Recht (`access.write: cli-theme`) | Admin-Weg (`access.write: admin-api`) |
|---|---|---|
| Wer | Staff-Konto mit dem Recht "Themes", Collaborator mit "Manage themes", Inhaber, oder ein Passwort der App Theme Access | der App-Zugang der Shopify CLI über `shopify store auth` |
| Werkzeug | `shopify theme push --unpublished`, `shopify theme push --theme <id> --only <files>`, `shopify theme list` | `stagedUploadsCreate` plus `themeCreate`, `themeFilesUpsert` über `shopify store execute --allow-mutations` |
| Dokumentiert | ja, der vorgesehene Weg für Theme-Arbeit | `write_themes` **plus eine Ausnahme von Shopify**; über den App-Zugang der CLI ging es im Feld trotzdem durch, dokumentiert ist das nicht |
| Für wen | **Standard für Teams**, die das Toolkit selbst einsetzen | Betreiber, bei denen der erste Weg nicht verfügbar ist |

**Der Lesezugang reicht für keinen der beiden.** Die Theme-Befehle der CLI laufen über den
Kontologin, nicht über den Grant von `shopify store auth`. Ein `shopify theme pull` kann deshalb mit
"you don't have access to this dev store" scheitern, obwohl `read_themes` im Grant steht. Das ist kein
fehlendes Recht, sondern der andere Anmeldeweg.

**Der Cockpit-Zugang lehnt Mutationen grundsätzlich ab.** Ein Shop, der nur über das Cockpit
angebunden ist, braucht für die Migration zusätzlich einen der beiden Wege oben. Es gibt keinen
Rückfall vom einen auf den anderen ohne Entscheidung des Betreibers.

## Weg 1: Konto mit Themes-Recht

1. Das Team legt ein Staff-Konto mit dem Recht "Themes" an oder lädt einen Collaborator mit "Manage
   themes" ein. Alternativ erzeugt jemand mit Themes-Recht in der App Theme Access ein Passwort; der
   Link dorthin läuft nach sieben Tagen oder nach einmaligem Ansehen ab.
2. Ein Passwort aus Theme Access geht nie als Argument in die Kommandozeile, sonst steht es in der
   Prozessliste. Es wird als Umgebungsvariable `SHOPIFY_CLI_THEME_TOKEN` gesetzt, aus der `.env` des
   Workspace, die nie committet wird.
3. Probe: `shopify theme list --store <shopify_store>` zeigt die Themes des Stores.
4. Ein Entwicklungs-Theme aus `shopify theme dev` wird bei `shopify auth logout` gelöscht. Für die
   Migration wird deshalb nie ein Entwicklungs-Theme als Entwurf genutzt, sondern ein unveröffentlichtes.

Quellen: https://shopify.dev/docs/storefronts/themes/tools/cli,
https://shopify.dev/docs/storefronts/themes/tools/theme-access,
https://shopify.dev/docs/api/shopify-cli/theme/theme-push

## Weg 2: Admin-Weg

**Scopes**, zusätzlich zu den lesenden aus `pull-shopify`:

| Scope | Wofür |
|---|---|
| `read_themes`, `write_themes` | Theme-Dateien lesen, Theme anlegen, Dateien schreiben |
| `read_translations`, `write_translations` | Theme-Übersetzungen lesen und auf den Entwurf registrieren |
| `read_locales`, `read_markets` | Sprachen und Märkte |
| `read_content` | Seiten und Blogs für die Template-Nutzung |

**Union-Regel, hart:** vor jeder erneuten Anmeldung den bestehenden Grant lesen
(`currentAppInstallation { accessScopes { handle } }`) und die Vereinigungsmenge aller bestehenden und
aller benötigten Scopes in einer `--scopes`-Liste senden, nie nur die neuen. Die CLI mergt Scopes nicht
verlässlich, und der Zustimmungsdialog zeigt nur Zugewinne, nie Verluste. Der Ablauf steht in der
Skill `pull-shopify`, Abschnitt "Scope-Regel".

```bash
shopify store auth --store <shopify_store> \
  --scopes <existing-scopes>,read_themes,write_themes,read_translations,write_translations,read_locales,read_markets,read_content
```

`shopify store auth` öffnet die Freigabe im Browser und wartet nur kurz; es braucht jemanden vor dem
Bildschirm, nie im Hintergrund starten.

Mutationen laufen über `shopify store execute` nur mit `--allow-mutations`. Jede Mutation geht durch
den Schutz von `upload-theme` (Rolle `UNPUBLISHED`, ID gegen `draft_theme_id`, Live-Theme vorher und
nachher unverändert).

Quellen: https://shopify.dev/docs/api/shopify-cli/store/store-auth,
https://shopify.dev/docs/api/shopify-cli/store/store-execute,
https://shopify.dev/docs/api/admin-graphql/2026-04/mutations/themeFilesUpsert,
https://shopify.dev/docs/api/admin-graphql/2026-04/mutations/themeCreate

## Probe in Phase 0

| Weg | Probe | Was sie beweist |
|---|---|---|
| `cli-theme` | `shopify theme list --store <shopify_store>` | Konto mit Themes-Recht ist angemeldet |
| `admin-api` | Grant lesen, `write_themes` und die Übersetzungs-Scopes stehen darin | die Scopes, nicht die Ausnahme |

Ob die Ausnahme für den Admin-Weg greift, zeigt erst die erste echte Mutation, also die Erstanlage des
Entwurfs nach Gate G3. Scheitert sie mit einer Berechtigungsmeldung, ist der Weg 1 der Ersatz, nicht
ein zweiter Versuch mit anderen Scopes.

## Offen

- **Ob merchant-eigene Custom Apps für `themeFilesUpsert` und `themeCreate` die Ausnahme brauchen.**
  Die Doku formuliert es pauschal, der App-Zugang der CLI kam im Feld ohne gesonderte Freigabe durch.
  Bis das geklärt ist, ist Weg 1 der Standard für Teams.
- Ob ein per ZIP oder CLI hochgeladenes Theme der Horizon-Familie Update-Hinweise im Admin bekommt.
  Für die Migration ohne Belang, weil Updates per `git merge` kommen.

## Text an das Team

Vorlage für die Anforderung, Anrede "ihr" und "euch", der Betreiber spricht als "ich". Platzhalter
`<betreiber-mail>` und `<shop-domain>` füllt der Betreiber, gesendet wird nichts von der Skill.

> Für den Umbau von <shop-domain> brauche ich zusätzlich zum lesenden Zugang das Recht, Themes
> anzulegen und zu bearbeiten. Dafür reicht ein Mitarbeiterzugang für <betreiber-mail> mit dem Recht
> "Themes" (Einstellungen, Benutzer, Mitarbeiter hinzufügen). Ich arbeite ausschließlich in einem
> unveröffentlichten Theme. Euer heutiges Theme fasse ich nicht an, und veröffentlicht wird das neue
> erst nach eurer Freigabe, von Hand im Admin.
