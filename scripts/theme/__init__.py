"""Bausteine der Theme-Migration (Spec 2026-10-05, Abschnitt 8.1).

Nur Standardbibliothek. Jedes Modul ist per
`PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.<modul>` aufrufbar,
schreibt sein Ergebnis als JSON-Datei und eine Zusammenfassung als genau eine
JSON-Zeile auf stdout. Exit-Code 0 heißt fertig ohne Befund, 1 heißt Befunde,
2 heißt Fehler.

Hier liegen nur die drei Hilfen, die jede CLI braucht: Config lesen, JSON
schreiben, Zusammenfassung ausgeben.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class ConfigError(RuntimeError):
    """`reporting/config.json` fehlt oder trägt nicht, was der Aufruf braucht."""


def load_config(workspace: str | os.PathLike = ".") -> dict:
    """`reporting/config.json` des Workspace als dict."""
    path = Path(workspace) / "reporting" / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"{path} fehlt; erst /ptai-ecom:setup laufen lassen") from exc
    except ValueError as exc:
        raise ConfigError(f"{path} ist kein gültiges JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError(f"{path} ist kein JSON-Objekt")
    return config


def migration_config(config: dict) -> dict:
    """Der Block `theme_migration`, leer, wenn er fehlt."""
    block = config.get("theme_migration")
    return block if isinstance(block, dict) else {}


def write_json(path: str | os.PathLike, data) -> Path:
    """Schreibt `data` lesbar eingerückt, legt den Ordner an und gibt den Pfad zurück."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def emit(summary: dict) -> None:
    """Die eine Zeile auf stdout, die eine Skill liest."""
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


def now_utc() -> str:
    """Zeitstempel in UTC, sekundengenau, wie Shopify ihn liefert."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
