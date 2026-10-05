"""Normalisierte Fassungen und Prüfsummen für den inhaltlichen Vergleich.

**Warum nie `checksumMd5` für JSON.** Shopify serialisiert JSON-Dateien eines
Themes beim Schreiben neu und setzt vor `config/settings_data.json` einen
Kommentarkopf (`/* ... */`). Größe und `checksumMd5` weichen danach immer vom
lokalen Stand ab, auch wenn der Inhalt stimmt; im Feld lagen nach einem
Upsert alle JSON-Dateien daneben, inhaltlich waren alle richtig. Verglichen
wird deshalb die normalisierte Fassung: Kommentarkopf entfernt, geparst,
sortiert und kompakt serialisiert.

Zwei weitere Angleichungen stammen aus demselben Feldlauf: Shopify lässt
leere `blocks: {}` und `block_order: []` weg, und eine ganze Zahl kann als
`1.0` oder `1` zurückkommen. Beides ändert nichts an der Darstellung und wird
vor dem Vergleich angeglichen; jeder andere Wert bleibt, wie er ist.
"""
import hashlib
import json
import re

_LEADING_COMMENT = re.compile(r"\A\s*/\*.*?\*/", re.S)


def strip_json_comment(text: str) -> str:
    """Entfernt BOM und jeden Kommentarblock am Anfang, sonst nichts."""
    if text.startswith("﻿"):
        text = text[1:]
    while True:
        match = _LEADING_COMMENT.match(text)
        if not match:
            return text.strip()
        text = text[match.end():]


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(child) for key, child in value.items()
                if not ((key == "blocks" and child == {}) or (key == "block_order" and child == []))}
    if isinstance(value, list):
        return [_canonical(child) for child in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def parse_json(text: str):
    """JSON einer Theme-Datei lesen, Kommentarkopf vorher entfernt."""
    return json.loads(strip_json_comment(text))


def normalized_json(text: str) -> str:
    """Geparst, angeglichen, sortiert, kompakt. Wirft `ValueError` bei ungültigem JSON."""
    return json.dumps(_canonical(parse_json(text)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_SPACE = re.compile(r"\s+")
_CSS_PUNCT = re.compile(r"\s*([{}:;,>])\s*")


def normalized_css(text: str) -> str:
    """CSS ohne Kommentare und überzählige Leerzeichen, für den Code-Diff gegen das Original.

    Groß- und Kleinschreibung bleibt: in Selektoren, URLs und `content` ist sie
    Inhalt. Ein `;` direkt vor `}` fällt weg, weil es nichts bewirkt.
    """
    text = _CSS_COMMENT.sub("", text)
    text = _CSS_SPACE.sub(" ", text)
    text = _CSS_PUNCT.sub(r"\1", text)
    return text.replace(";}", "}").strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_bytes(data: bytes) -> str:
    """Wie `checksumMd5` bei Shopify; taugt nur für Dateien, die Shopify nicht neu schreibt."""
    return hashlib.md5(data).hexdigest()


def is_json_path(path: str) -> bool:
    return path.lower().endswith(".json")


def content_hash(path: str, body) -> dict:
    """Prüfsummen einer Theme-Datei.

    `sha256` über die unveränderten Bytes. Für JSON zusätzlich
    `sha256_normalized`; ist die Datei kein gültiges JSON, steht dort `None`
    und `json_valid` auf `False`, denn ein ZIP-Import lässt ungültiges JSON
    still weg.
    """
    data = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    result = {"sha256": sha256_bytes(data)}
    if is_json_path(path):
        try:
            result["sha256_normalized"] = sha256_text(normalized_json(data.decode("utf-8")))
            result["json_valid"] = True
        except (ValueError, UnicodeDecodeError):
            result["sha256_normalized"] = None
            result["json_valid"] = False
    return result


def same_content(path: str, left, right) -> bool:
    """Inhaltlich gleich: JSON normalisiert, alles andere byteweise."""
    a = left.encode("utf-8") if isinstance(left, str) else bytes(left)
    b = right.encode("utf-8") if isinstance(right, str) else bytes(right)
    if a == b:
        return True
    if not is_json_path(path):
        return False
    try:
        return normalized_json(a.decode("utf-8")) == normalized_json(b.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
