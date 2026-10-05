"""Theme-Dateien lesen, nachfordern, in Paketen schreiben und zurücklesen.

Jede Abfrage hier ist mit dem Validator der Skill `shopify-admin` gegen das
Admin-Schema 2026-04 geprüft (05.10.2026). Scopes: `read_themes` zum Lesen;
`themeFilesUpsert` verlangt laut Doku `write_themes` und eine Ausnahme von
Shopify.

**Warum Metadaten und Inhalte getrennt gezogen werden.** Die durchblätternde
Abfrage mit Inhalt endete im Feld zu früh: `hasNextPage` meldete `false`,
obwohl am alphabetischen Ende noch Dateien folgten, und einzelne Knoten fehlten
still. Eine Sicherung, die nur zählt, was sie bekommen hat, bemerkt das nicht.
Deshalb erst die reine Metadatenliste als Referenz, dann die Inhalte, dann
gezielt über `filenames` nachfordern, was fehlt. Vollständig ist erst, was die
Referenz deckt.

**Warum Code vor Templates.** Ein Template, das eine Section oder einen Block
nennt, den es im Theme noch nicht gibt, wird abgelehnt oder verliert Inhalt.
`upload_order` schreibt deshalb Assets, Locales, Snippets, Blöcke, Sections und
Layout zuerst, dann Section-Groups und Templates und `settings_data.json`
zuletzt.
"""
import base64
import time
import urllib.request
from pathlib import Path

from theme.normalize import is_json_path, md5_bytes, same_content
from theme.shopify import ShopifyError, theme_gid

#: Verzeichnisse, die Shopify als Theme-Dateien kennt. Alles andere (README,
#: .git, Generatoren) gehört nicht in Paket oder Vergleich.
RUNTIME_DIRS = ("assets", "blocks", "config", "layout", "locales", "sections", "snippets", "templates")

#: Höchstzahl Dateien je `themeFilesUpsert` laut Doku.
UPSERT_LIMIT = 50
PAGE_SIZE = 50
BY_NAME_BATCH = 20

THEMES_QUERY = """query ThemeList {
  themes(first: 250) {
    nodes { id name role updatedAt themeStoreId processing processingFailed }
  }
}"""

SHOP_PLAN_QUERY = """query ShopPlan {
  shop { plan { shopifyPlus } }
}"""

THEME_QUERY = """query ThemeState($id: ID!) {
  theme(id: $id) { id name role updatedAt themeStoreId processing processingFailed }
}"""

FILES_META_QUERY = """query ThemeFileMetadata($id: ID!, $after: String) {
  theme(id: $id) {
    id
    files(first: 50, after: $after) {
      nodes { filename size contentType checksumMd5 updatedAt }
      pageInfo { hasNextPage endCursor }
      userErrors { filename code }
    }
  }
}"""

_BODY = """body {
          __typename
          ... on OnlineStoreThemeFileBodyText { content }
          ... on OnlineStoreThemeFileBodyBase64 { contentBase64 }
          ... on OnlineStoreThemeFileBodyUrl { url }
        }"""

FILES_BODY_QUERY = """query ThemeFileBodies($id: ID!, $after: String) {
  theme(id: $id) {
    id
    files(first: 50, after: $after) {
      nodes {
        filename size checksumMd5 updatedAt
        %s
      }
      pageInfo { hasNextPage endCursor }
      userErrors { filename code }
    }
  }
}""" % _BODY

FILES_BY_NAME_QUERY = """query ThemeFilesByName($id: ID!, $filenames: [String!]) {
  theme(id: $id) {
    id
    files(first: 20, filenames: $filenames) {
      nodes {
        filename size checksumMd5 updatedAt
        %s
      }
      userErrors { filename code }
    }
  }
}""" % _BODY

UPSERT_MUTATION = """mutation UpsertThemeFiles($themeId: ID!, $files: [OnlineStoreThemeFilesUpsertFileInput!]!) {
  themeFilesUpsert(themeId: $themeId, files: $files) {
    upsertedThemeFiles { filename }
    job { id done }
    userErrors { code field filename message }
  }
}"""

JOB_QUERY = """query JobState($id: ID!) {
  job(id: $id) { id done }
}"""


class UpsertError(ShopifyError):
    """`themeFilesUpsert` hat `userErrors` gemeldet; der Lauf hält an."""

    def __init__(self, message: str, errors: list, written: list):
        super().__init__(message)
        self.errors = errors
        self.written = written


def list_themes(transport) -> list[dict]:
    data = transport.execute(THEMES_QUERY)
    return list(((data.get("themes") or {}).get("nodes")) or [])


def is_plus(transport) -> bool | None:
    """Ob der Shop auf Plus läuft; `None`, wenn die Abfrage nicht beantwortet wird."""
    try:
        data = transport.execute(SHOP_PLAN_QUERY)
    except ShopifyError:
        return None
    plan = ((data.get("shop") or {}).get("plan")) or {}
    value = plan.get("shopifyPlus")
    return value if isinstance(value, bool) else None


def get_theme(transport, theme_id) -> dict | None:
    """Zustand eines Themes, frisch gelesen; `None`, wenn es die ID nicht gibt."""
    return transport.execute(THEME_QUERY, {"id": theme_gid(theme_id)}).get("theme")


def live_theme(themes: list[dict]) -> dict:
    """Das eine Theme mit Rolle MAIN."""
    main = [t for t in themes if t.get("role") == "MAIN"]
    if len(main) != 1:
        raise ShopifyError(f"erwartet genau ein Theme mit Rolle MAIN, gefunden {len(main)}")
    return main[0]


def _files_of(data: dict) -> dict:
    theme = data.get("theme")
    if not theme:
        raise ShopifyError("Theme nicht gefunden")
    return theme.get("files") or {}


def list_files(transport, theme_id) -> list[dict]:
    """Metadaten aller Dateien, seitenweise, ohne Inhalt. Die Referenzliste."""
    gid = theme_gid(theme_id)
    nodes, seen, after, cursors = [], set(), None, set()
    while True:
        files = _files_of(transport.execute(FILES_META_QUERY, {"id": gid, "after": after}))
        for node in files.get("nodes") or []:
            if node["filename"] in seen:
                raise ShopifyError(f"Datei doppelt über die Seiten hinweg: {node['filename']}")
            seen.add(node["filename"])
            nodes.append(node)
        page = files.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return nodes
        after = page.get("endCursor")
        if not after or after in cursors:
            raise ShopifyError("Seitenzeiger fehlt oder wiederholt sich")
        cursors.add(after)


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def decode_body(node: dict, fetch_url=None) -> bytes | None:
    """Inhalt eines Knotens in allen drei Formen; `None`, wenn keiner dabei ist."""
    body = node.get("body") or {}
    if "content" in body and body["content"] is not None:
        return body["content"].encode("utf-8")
    if "contentBase64" in body and body["contentBase64"] is not None:
        return base64.b64decode(body["contentBase64"])
    if body.get("url"):
        return (fetch_url or _download)(body["url"])
    return None


def fetch_by_names(transport, theme_id, names, *, fetch_url=None) -> dict[str, bytes]:
    """Inhalte gezielt über `filenames`, zu je 20."""
    gid = theme_gid(theme_id)
    names = sorted(set(names))
    result = {}
    for start in range(0, len(names), BY_NAME_BATCH):
        block = names[start:start + BY_NAME_BATCH]
        files = _files_of(transport.execute(FILES_BY_NAME_QUERY, {"id": gid, "filenames": block}))
        for node in files.get("nodes") or []:
            data = decode_body(node, fetch_url)
            if data is not None:
                result[node["filename"]] = data
    return result


def fetch_bodies(transport, theme_id, expected=None, *, fetch_url=None, rounds: int = 5):
    """Alle Inhalte; fehlt etwas gegenüber `expected`, wird gezielt nachgefordert.

    Gibt `(inhalte, fehlend)` zurück. `fehlend` ist leer, wenn die Inhalte die
    Referenzliste decken; nur dann ist eine Sicherung vollständig.
    """
    gid = theme_gid(theme_id)
    got: dict[str, bytes] = {}
    after, cursors = None, set()
    while True:
        files = _files_of(transport.execute(FILES_BODY_QUERY, {"id": gid, "after": after}))
        for node in files.get("nodes") or []:
            data = decode_body(node, fetch_url)
            if data is not None:
                got[node["filename"]] = data
        page = files.get("pageInfo") or {}
        after = page.get("endCursor")
        # Endet die Paginierung zu früh oder dreht sich, fängt das Nachfordern es auf.
        if not page.get("hasNextPage") or not after or after in cursors:
            break
        cursors.add(after)
    if expected is None:
        return got, []
    expected = set(expected)
    missing = sorted(expected - got.keys())
    for _ in range(rounds):
        if not missing:
            break
        got.update(fetch_by_names(transport, theme_id, missing, fetch_url=fetch_url))
        still = sorted(expected - got.keys())
        if still == missing:
            break
        missing = still
    return got, missing


def read_theme_dir(path) -> dict[str, bytes]:
    """Alle Theme-Dateien eines Ordners als `{"templates/index.json": bytes}`.

    Nur die Theme-Verzeichnisse, ohne versteckte Dateien. Ein Symlink ist ein
    Fehler: er zeigte beim Paketieren auf etwas außerhalb des Themes.
    """
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"{root} ist kein Ordner")
    files = {}
    for directory in RUNTIME_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for item in sorted(base.rglob("*")):
            if item.is_symlink():
                raise ValueError(f"Symlink im Theme nicht erlaubt: {item.relative_to(root).as_posix()}")
            if not item.is_file() or any(part.startswith(".") for part in item.relative_to(root).parts):
                continue
            files[item.relative_to(root).as_posix()] = item.read_bytes()
    return files


def write_theme_files(path, files: dict[str, bytes]) -> None:
    """Schreibt Dateien unverändert, Byte für Byte; nie formatiert."""
    root = Path(path)
    for name, data in files.items():
        target = root / name
        if ".." in Path(name).parts or Path(name).is_absolute():
            raise ValueError(f"Dateiname verlässt das Theme: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def body_input(name: str, data: bytes) -> dict:
    """Eingabe für `themeFilesUpsert`: Text als TEXT, alles andere als BASE64."""
    try:
        return {"filename": name, "body": {"type": "TEXT", "value": data.decode("utf-8")}}
    except UnicodeDecodeError:
        return {"filename": name, "body": {"type": "BASE64", "value": base64.b64encode(data).decode("ascii")}}


_ORDER = {"assets": 0, "locales": 1, "snippets": 2, "blocks": 3, "sections": 4, "layout": 5, "config": 6,
          "templates": 8}


def upload_order(name: str) -> tuple:
    """Code vor Templates: Rang, dann Name."""
    if name == "config/settings_data.json":
        return 9, name
    top = name.split("/", 1)[0]
    if top == "sections" and name.endswith(".json"):
        return 7, name
    return _ORDER.get(top, 6), name


def batches(names, size: int = UPSERT_LIMIT) -> list[list[str]]:
    """In Upload-Reihenfolge, je höchstens `size` (nie mehr als 50)."""
    size = min(size, UPSERT_LIMIT)
    ordered = sorted(names, key=upload_order)
    return [ordered[start:start + size] for start in range(0, len(ordered), size)]


def wait_for_job(transport, job_id, *, sleep=time.sleep, interval: float = 2, timeout: float = 300) -> None:
    """Wartet, bis der asynchrone Job fertig ist; ohne Job nichts zu tun."""
    if not job_id:
        return
    waited = 0.0
    while True:
        job = transport.execute(JOB_QUERY, {"id": job_id}).get("job") or {}
        if job.get("done"):
            return
        if waited >= timeout:
            raise ShopifyError(f"Job {job_id} nach {timeout:.0f} Sekunden nicht fertig")
        sleep(interval)
        waited += interval


def upsert_batch(transport, theme_id, files: dict[str, bytes], *, sleep=time.sleep) -> list[str]:
    """Ein Paket von höchstens 50 Dateien schreiben und den Job abwarten.

    Bei `userErrors` hält der Lauf an (`UpsertError`): ein halb geschriebenes
    Paket wird gemeldet, nicht überspielt.
    """
    if len(files) > UPSERT_LIMIT:
        raise ValueError(f"höchstens {UPSERT_LIMIT} Dateien je themeFilesUpsert, nicht {len(files)}")
    inputs = [body_input(name, files[name]) for name in sorted(files, key=upload_order)]
    data = transport.execute(UPSERT_MUTATION, {"themeId": theme_gid(theme_id), "files": inputs}, mutation=True)
    result = data.get("themeFilesUpsert") or {}
    written = [item["filename"] for item in result.get("upsertedThemeFiles") or []]
    errors = result.get("userErrors") or []
    if errors:
        raise UpsertError(f"themeFilesUpsert meldet {len(errors)} Fehler", errors, written)
    wait_for_job(transport, (result.get("job") or {}).get("id"), sleep=sleep)
    return written


def compare_remote(transport, theme_id, local: dict[str, bytes], names=None, *, fetch_url=None) -> dict:
    """Lokale Dateien gegen das Theme, inhaltlich.

    Nicht-JSON byteweise über `checksumMd5` (Shopify schreibt diese Dateien
    unverändert). JSON nie über die Prüfsumme, sondern über den zurückgelesenen
    Inhalt, normalisiert. Ohne `names` wird alles verglichen und `extra` nennt
    Dateien, die nur im Theme liegen.
    """
    remote = {node["filename"]: node for node in list_files(transport, theme_id)}
    targets = sorted(local if names is None else names)
    result = {"checked": len(targets), "equal": [], "different": [], "missing": [], "extra": []}
    json_names = []
    for name in targets:
        if name not in remote:
            result["missing"].append(name)
        elif is_json_path(name):
            json_names.append(name)
        elif md5_bytes(local[name]) == remote[name].get("checksumMd5"):
            result["equal"].append(name)
        else:
            result["different"].append(name)
    bodies = fetch_by_names(transport, theme_id, json_names, fetch_url=fetch_url) if json_names else {}
    for name in json_names:
        if name in bodies and same_content(name, local[name], bodies[name]):
            result["equal"].append(name)
        else:
            result["different"].append(name)
    if names is None:
        result["extra"] = sorted(remote.keys() - local.keys())
    for key in ("equal", "different"):
        result[key].sort()
    return result
