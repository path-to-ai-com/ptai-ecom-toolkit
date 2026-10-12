# Windows

Stand 12.10.2026. Was unter Windows (Git Bash, PowerShell) anders ist und was das Toolkit davon
selbst abfängt. Eigene Shims für Python, `PYTHONPATH`, `PYTHONUTF8` oder die Shopify CLI braucht es
nicht mehr.

## Der Starter `bin/theme`

`bin/theme <modul> [argumente]` startet `python -m theme.<modul>` mit den übrigen Argumenten. Dabei:

- sucht er Python ab 3.10 in der Reihenfolge `python3`, `python`, `py -3`; der Platzhalter aus dem
  Microsoft Store zählt nicht,
- setzt er `PYTHONPATH` auf `<plugin>/scripts`, für ein Windows-Python als Windows-Pfad,
- setzt er `PYTHONUTF8=1`, damit Umlaute in Dateien und Ausgaben nicht an der Codepage brechen,
- nimmt er die Plugin-Wurzel aus seinem eigenen Pfad, `CLAUDE_PLUGIN_ROOT` nur, wenn dort nichts
  liegt.

Exit-Code ist der des Moduls, 2, wenn Python oder das Modul fehlt. Fehlt Python, nennt die Meldung
den Installationsweg: `winget install Python.Python.3.12`, danach ein neues Terminal öffnen.

In Git Bash, auch im Bash-Werkzeug von Claude Code:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show
```

Das ist dasselbe wie `"${CLAUDE_PLUGIN_ROOT}/bin/theme" run_state show`
auf macOS und Linux.

In PowerShell ohne Bash von Hand, `<plugin>` ist der Ordner des Plugins:

```powershell
$env:PYTHONPATH = "<plugin>\scripts"; $env:PYTHONUTF8 = "1"
py -3 -m theme.run_state show
```

## Was die Bausteine selbst abfangen

- **Shopify CLI.** `theme.shopify` findet sie über `shutil.which`, unter Windows auch als
  `shopify.cmd`, und liest ihre Ausgabe als UTF-8. Stehen vor dem JSON Fortschritts- oder
  Warnzeilen, gilt das letzte vollständige JSON-Objekt. Fehlt die CLI: `npm install -g @shopify/cli`.
- **Zeilenenden der Sicherungen.** `theme.snapshot` trägt `migration/snapshots/** -text` in die
  `.gitattributes` des Workspace ein, einmal und nie doppelt. Ohne die Zeile schreibt Git mit
  `core.autocrlf` die gesicherten Dateien um, und die Prüfsummen im Manifest passen nicht mehr. Die
  `.gitattributes` mit der ersten Sicherung committen; eine Sicherung, die vorher committet wurde,
  im Zweifel neu ziehen.
- **Der Starter selbst** steht im Plugin mit LF-Zeilenenden fest (`.gitattributes` des Plugins);
  mit CRLF bräche bash beim ersten Befehl ab.

## Firmen-Proxy

Nur ein Hinweis, der Starter setzt beides nicht. Bricht ein Proxy TLS auf, scheitern Downloads an
der unbekannten Zertifizierungsstelle. Dann helfen:

- `UV_NATIVE_TLS=1` für Werkzeuge, die über uv laufen: uv nimmt den Zertifikatsspeicher des Systems.
- `NODE_OPTIONS=--use-system-ca` für Node-Werkzeuge wie die Shopify CLI; braucht eine Node-Version,
  die das Flag kennt.
