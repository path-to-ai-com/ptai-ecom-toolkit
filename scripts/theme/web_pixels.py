"""Web Pixels eines Shops: die Liste aus dem Storefront-HTML, ihr Stand vor dem Launch, die Sicherung der Custom Pixels.

Drei Aufgaben, alle lesend gegenüber dem Shop:

- **Pixel-Liste.** `webPixelsConfigList` aus dem ausgelieferten HTML (über `theme.apps.parse_web_pixels`),
  aus einem Mitschnitt oder einem Abruf der Live-Seite. Die Liste gilt für den ganzen Shop, nicht je
  Theme: eine Vorschau des alten Themes zeigt nach dem Launch schon den Stand danach. Deshalb hält der
  Launch-Check vor dem Launch die Liste in `<lauf>/web-pixels-before.json` fest, und nach dem Launch
  wird gegen genau diesen Stand verglichen.
- **Sicherung eines Custom Pixels**, bevor es entfernt oder ersetzt wird:
  `migration/inventory/pixels/<name>.js` mit dem Code aus dem Admin (Einstellungen, Kundenereignisse)
  und daneben `<name>.md`, eine kurze Notiz mit festen Zeilen:

  ```
  # <Name des Pixels>

  - Pixel-ID: <id aus webPixelsConfigList>
  - Sendet: <Ereignisse>
  - Wo: <Seiten, Kasse oder beides>
  - An: <Messziele, etwa GA4 G-…, Google Ads AW-…/Label>
  - Gesichert: <JJJJ-MM-TT>, gelesen von <Name>
  ```

  Gesichert heißt: der Code liegt nicht leer daneben. Gelesen heißt: die Zeilen Sendet, Wo und An sind
  ausgefüllt, jemand hat also verstanden, was das Pixel tut. `<name>` ist der Name des Pixels in
  kebab-case (`slug`); zugeordnet wird über die Pixel-ID der Notiz, sonst über den Dateinamen.
- **Messziele aus der Sicherung** (`tracking_ids.find_targets`): eine GA4-Property oder eine
  Google-Ads-Conversion, die nur das Pixel in der Kasse bediente, ist nach dem Launch ein eigenes Ziel
  der Testbestellung.

Seit 11.11.2026. Anlass: ein Custom Pixel wurde nach Plan gelöscht, weil angenommen war, der Tag
Manager lade doppelt. Es sendete aber nur in der Kasse, wo das Theme nicht hinkommt; danach fehlten
Käufe in einer von mehreren GA4-Properties und in der Google-Ads-Kauf-Conversion, und der Code war
nur zufällig noch abrufbar. Gefunden wurde es über den Vergleich der Pixel-Liste vorher gegen nachher.

Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from theme import apps, tracking_ids

#: Ablage der gesicherten Custom Pixels im Workspace.
BACKUP_DIR = Path("migration") / "inventory" / "pixels"
#: Datei im Lauf-Ordner des Launch-Checks vor dem Launch.
BEFORE_FILE = "web-pixels-before.json"
#: Zeilen der Notiz, klein geschrieben, zu ihrem Feld.
NOTE_FIELDS = {"pixel-id": "pixel_id", "pixel id": "pixel_id", "sendet": "sends", "wo": "where", "an": "to",
               "gesichert": "saved"}
#: Ohne diese drei Zeilen gilt eine Sicherung als nicht gelesen.
READ_FIELDS = ("sends", "where", "to")
READ_LABELS = {"sends": "Sendet", "where": "Wo", "to": "An"}
_NOTE_LINE = re.compile(r"^\s*[-*]?\s*([A-Za-zÄÖÜäöü][\w -]{0,20}?)\s*:\s*(.*?)\s*$")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})


# ---------------------------------------------------------------------------
# Pixel-Liste
# ---------------------------------------------------------------------------

def from_html(html: str | None) -> list[dict] | None:
    """Die verbundenen Pixel einer Seite; None, wenn die Seite keine Liste trägt."""
    if not html:
        return None
    return apps.parse_web_pixels(html)


def merge(lists) -> list[dict] | None:
    """Vereinigung über mehrere Seiten, je Pixel-ID einmal; None, wenn keine Seite eine Liste trug."""
    seen, found = {}, False
    for pixels in lists:
        if pixels is None:
            continue
        found = True
        for pixel in pixels:
            seen.setdefault(str(pixel.get("id") or ""), pixel)
    return [seen[k] for k in sorted(seen)] if found else None


def is_custom(pixel: dict) -> bool:
    return str(pixel.get("type") or "").upper() == "CUSTOM"


def label(pixel: dict) -> str:
    """Name für Menschen: Custom Pixel mit Namen, App-Pixel mit `apiClientId`."""
    pid = pixel.get("id")
    if is_custom(pixel):
        return f"Custom Pixel „{pixel['name']}“ ({pid})" if pixel.get("name") else f"Custom Pixel {pid}"
    client = pixel.get("api_client_id")
    return f"App-Pixel {pid}" + (f" (App {client})" if client else "")


def targets(pixel: dict) -> list[str]:
    """Messziele aus der Konfiguration eines Pixels, als `target_id` (mit Label, wo es eins gibt)."""
    out = []
    for target in tracking_ids.config_targets(pixel.get("configuration")):
        name = target["target_id"] + (f"/{target['label']}" if target.get("label") else "")
        if name not in out:
            out.append(name)
    return out


def purchase_targets(pixel: dict) -> list[dict]:
    """Messziele, an die die Konfiguration den Kauf schickt (`gtag_events` mit `type: purchase`)."""
    out = []
    for event, event_targets in tracking_ids.config_events(pixel.get("configuration")):
        if str(event).lower() == "purchase":
            out += event_targets
    return out


def save_before(path: Path, pixels: list[dict], source: str, captured_at: str) -> None:
    data = {"kind": "web-pixels", "captured_at": captured_at, "source": source, "pixels": pixels}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_before(path: Path) -> dict | None:
    """`web-pixels-before.json` als dict mit `pixels`, None ohne Datei oder bei kaputtem Inhalt."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("pixels"), list) else None


# ---------------------------------------------------------------------------
# Sicherung der Custom Pixels
# ---------------------------------------------------------------------------

def slug(text: str) -> str:
    """Dateiname eines Pixels: kebab-case, ASCII, Umlaute ausgeschrieben."""
    text = str(text or "").translate(_UMLAUTS).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse_note(text: str) -> dict:
    """Die festen Zeilen der Notiz (`- Sendet: ...`) als Felder; der Titel steht unter `title`."""
    note = {}
    for line in (text or "").splitlines():
        if line.startswith("# ") and "title" not in note:
            note["title"] = line[2:].strip()
            continue
        match = _NOTE_LINE.match(line)
        if not match:
            continue
        field = NOTE_FIELDS.get(match.group(1).strip().lower())
        if field and match.group(2) and field not in note:
            note[field] = match.group(2)
    return note


def load_backups(workspace: Path) -> list[dict]:
    """Jede Sicherung unter `migration/inventory/pixels/`: Code, Notiz, Pixel-ID.

    Eine Notiz ohne Code daneben ist ein Eintrag ohne Code; ein Code ohne Notiz einer ohne Notiz.
    """
    folder = Path(workspace) / BACKUP_DIR
    if not folder.is_dir():
        return []
    stems = sorted({p.stem for p in folder.iterdir() if p.is_file() and p.suffix in (".js", ".md")})
    out = []
    for stem in stems:
        code_path, note_path = folder / f"{stem}.js", folder / f"{stem}.md"
        try:
            code = code_path.read_text(encoding="utf-8") if code_path.is_file() else None
        except (OSError, UnicodeDecodeError):
            code = None
        try:
            note = parse_note(note_path.read_text(encoding="utf-8")) if note_path.is_file() else None
        except (OSError, UnicodeDecodeError):
            note = None
        out.append({"stem": stem, "code": code, "note": note,
                    "code_path": (BACKUP_DIR / f"{stem}.js").as_posix(),
                    "note_path": (BACKUP_DIR / f"{stem}.md").as_posix(),
                    "pixel_id": re.sub(r"\D", "", str((note or {}).get("pixel_id") or "")) or None})
    return out


def find_backup(backups: list[dict], pixel_id, name: str | None = None) -> dict | None:
    """Die Sicherung eines Pixels: über die Pixel-ID der Notiz, sonst über den Dateinamen."""
    pid = str(pixel_id or "")
    for backup in backups:
        if pid and backup["pixel_id"] == pid:
            return backup
    stems = {s for s in (slug(name) if name else "", pid) if s}
    return next((b for b in backups if b["stem"] in stems), None)


def backup_state(backup: dict | None) -> tuple[bool, str]:
    """`(gesichert und gelesen, Beleg)` einer Sicherung."""
    if backup is None:
        return False, f"keine Sicherung unter {BACKUP_DIR.as_posix()}/"
    if not (backup["code"] or "").strip():
        return False, f"{backup['code_path']} fehlt oder ist leer"
    if backup["note"] is None:
        return False, f"{backup['code_path']} gesichert, aber die Notiz {backup['note_path']} fehlt"
    empty = [READ_LABELS[f] for f in READ_FIELDS if not str(backup["note"].get(f) or "").strip()]
    if empty:
        return False, f"{backup['code_path']} gesichert, aber nicht gelesen: in {backup['note_path']} fehlt " \
                      + ", ".join(empty)
    note = backup["note"]
    return True, f"gesichert in {backup['code_path']}; sendet {note['sends']}, wo {note['where']}, an {note['to']}"


def backup_targets(backups: list[dict]) -> list[tuple[dict, str]]:
    """Messziele im Code jeder Sicherung, mit der Datei als Herkunft."""
    out = []
    for backup in backups:
        for target in tracking_ids.find_targets(backup["code"] or ""):
            out.append((target, backup["code_path"]))
    return out
