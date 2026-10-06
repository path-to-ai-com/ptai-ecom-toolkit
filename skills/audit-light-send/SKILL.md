---
name: audit-light-send
description: Verschickt den fertigen Report eines audit-light-Laufs an den Lead als Teaser-Mail im Path-to-AI-CI mit dem PDF im Anhang und setzt den Lead in Supabase auf sent. Auslöser sind /ptai-ecom:audit-light-send oder der Auftrag, den geprüften Audit-Report zu versenden. Voraussetzung: Lauf abgeschlossen, Report geprüft. Ein Dry-Run ohne Lead hat keinen Empfänger und wird nicht versendet.
---

# audit-light-send: Report an den Lead

Dies ist der Lead-Funnel von Path to AI. Vor der ersten Mail in einer anderen Umgebung einrichten:
- eigenes Supabase-Projekt mit den Tabellen `audits` und `findings` im Format, das `${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/db.mjs` liest und schreibt
- Resend-Konto mit verifiziertem Absender
- `PTAI_MAIL_FROM` und `PTAI_MAIL_REPLY_TO` setzen, beide ohne Vorgabewert
- `${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/report-email.mjs` anpassen; die Teaser-Mail stellt Yves vor und verlinkt seinen Kalender
- Das Formular auf path-to-ai.com, das Leads in `audits` schreibt, ist nicht Teil des Plugins.

## Argumente

- `audit-id`: UUID der Lead-Zeile in der Supabase-Tabelle `audits`.
- Optional `--run <lauf-ordner>`: genau dieser Lauf wird verwendet.

Ohne Lead-Zeile gibt es keinen Empfänger. Einen selbst gestarteten Lauf gegen eine fremde Domain nicht verschicken; dessen Report liegt im Account und in `deliverables/`.

## Voraussetzungen

- Lauf abgeschlossen, im Lauf-Ordner liegen `content.json` und `report.pdf`.
- Das PDF vollständig angesehen, nicht nur überflogen; der Empfänger beurteilt Path to AI danach.
- `RESEND_API_KEY`, `SUPABASE_URL` und `SUPABASE_SERVICE_ROLE_KEY` in `~/.config/ptai-ecom/.env`. Die Skripte lesen die Datei selbst, `--env-file` ist nicht nötig. Prüfen mit `python3 -m audit.env`.
- `PTAI_MAIL_FROM` (Absender im Format `Name <adresse>`, bei Resend verifiziert) und `PTAI_MAIL_REPLY_TO` (Adresse für Antworten der Leads) in derselben Datei oder in der Umgebung.
- `python3 -m audit.env` zeigt die Quelle dieser beiden Werte, meldet sie aber nie als fehlend. Fehlt einer, bricht `send-report.mjs` vor dem Versand mit einer Meldung ab.

## Ablauf

1. **Lauf-Ordner bestimmen.** Mit `--run`: `RUN_DIR=<lauf-ordner>`. Sonst unter `PTAI_ACCOUNTS_ROOT` beim Kunden suchen, nicht in einem Repo. Es gilt der jüngste Lauf mit dieser ID, auch ein zweiter vom selben Tag (`<datum>-light-2`):

```bash
ACCOUNTS_ROOT=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c 'from audit import account; print(account.accounts_root())')
RUN_DIR=$(grep -l "<audit-id>" "$ACCOUNTS_ROOT"/*/audit-runs/*-light*/run-config.json 2>/dev/null \
          | sed 's#/run-config.json$##' | LC_ALL=C sort -r | head -1)
```

   `LC_ALL=C` beibehalten: andere Sortierungen ignorieren Bindestriche und sortieren `-light` vor `-light-2`.

   Ist `RUN_DIR` leer, den Kunden über die Shop-URL der Lead-Zeile bestimmen und in seinem Ordner suchen:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/db.mjs" get <audit-id>
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.account '<shop_url>'
ls -d "<drive_path aus der Ausgabe>"/audit-runs/*-light*
```

2. **Kein zweites Beleg-Gate.** Das Gate in `audit-light` Stufe 2 hat jeden unbestätigten Befund bereits korrigiert oder gestrichen. Nichts zur Freigabe vorlegen, auch keine Liste aus `verify.json`.

3. **Senden.**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/report/sales/send-report.mjs" \
  <audit-id> "$RUN_DIR/content.json" "$RUN_DIR/report.pdf"
```

   Das Skript erzeugt die Teaser-Mail (Score-Schnappschuss, drei Befunde, Soft-CTA, Abbinder), hängt das PDF an, sendet über Resend an die Adresse der Lead-Zeile und setzt `status='sent'` und `sent_at`.

4. **Versand beim Kunden vermerken, wenn es dort eine `entity.md` gibt.** Pfad: `"$RUN_DIR/../../entity.md"`.
   - Existiert sie: eine Zeile unter `## Audits` mit Datum, Hinweis auf den versendeten Report und Pfad zum Lauf, damit beim nächsten Kontakt bekannt ist, dass der Lead schon einen Report hat.
   - Fehlt die Datei, nichts anlegen. Lauf-Ordner und `status='sent'` in Supabase belegen den Versand.

## Felder aus `content.json` für die Mail

- `exec.scores`: Score-Schnappschuss.
- `exec.teaserFindings`: Block mit den drei Punkten. Pflichtfeld, weil die Mail bei fehlendem Feld ohne Fehler mit leerem Block rausgeht.
- Format: genau drei Einträge `{title, body}`, `body` ein bis zwei Sätze, nur Plaintext. Die Mail escaped HTML, Tags erscheinen sonst als Text.

## Fehlerbilder

| Meldung | Ursache und Vorgehen |
|---|---|
| `Versand abgebrochen: PTAI_MAIL_FROM fehlt` (oder `PTAI_MAIL_REPLY_TO`) | Absenderangaben fehlen in Umgebung und `~/.config/ptai-ecom/.env`. Eintragen und erneut senden; es wurde noch nichts verschickt. |
| `audit not found` | Die UUID passt zu keiner Zeile: Tippfehler oder Dry-Run ohne Lead. |
| Resend antwortet 4xx | Meist ungültige Empfängeradresse. Vor jedem neuen Versuch die Lead-Zeile prüfen; jeder Versuch verschickt eine echte Mail. |
| `status` ist bereits `sent` | Der Report ist verschickt. Nicht ohne Rückfrage ein zweites Mal senden. |
