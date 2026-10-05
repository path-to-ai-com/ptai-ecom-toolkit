"""Ein erfundener Shop für die Tests von `scripts/theme`. Kein Test.

`FakeShop` beantwortet die GraphQL-Operationen des Pakets am Operationsnamen,
ohne Netz, und bildet die im Feld beobachteten Eigenheiten nach, gegen die die
Regeln gebaut sind:

* Die durchblätternde Abfrage mit Inhalt kann zu früh enden (`body_page_cut`)
  und einzelne Dateien nie mit Inhalt liefern (`never_body`).
* Ein Upsert serialisiert JSON neu und setzt vor `settings_data.json` einen
  Kommentarkopf (`reserialize_json`); `checksumMd5` weicht danach ab.
* Ein ZIP-Import kann Dateien still weglassen (`drop_on_create`).

Shop `beispiel.myshopify.com`, Theme-IDs aus Nullen und Einsen.
"""
import base64
import hashlib
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

from theme.shopify import ShopifyError, is_mutation

GID = "gid://shopify/OnlineStoreTheme/"
LIVE_ID = GID + "000000000000"
DRAFT_ID = GID + "111111111111"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "theme" / "beispiel-theme"


def fixture_files() -> dict[str, bytes]:
    """Das erfundene Theme als `{pfad: bytes}`."""
    return {p.relative_to(FIXTURE).as_posix(): p.read_bytes() for p in sorted(FIXTURE.rglob("*")) if p.is_file()}


def temp_workspace(case, **migration) -> Path:
    """Workspace im Temp-Ordner mit `reporting/config.json`; wird nach dem Test entfernt."""
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    block = {"live_theme_id": "000000000000", "draft_theme_id": None,
             "access": {"read": "cli-grant", "write": "admin-api"}}
    block.update(migration)
    config = {"brand": "Beispielmarke", "shopify_store": "beispiel.myshopify.com", "theme_migration": block}
    (root / "reporting").mkdir()
    (root / "reporting" / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return root


def shop_with_live(files: dict[str, bytes] | None = None) -> "FakeShop":
    shop = FakeShop()
    shop.add_theme(LIVE_ID, "MAIN", fixture_files() if files is None else files, name="Live")
    return shop


def text_body(data: bytes) -> dict:
    try:
        return {"__typename": "OnlineStoreThemeFileBodyText", "content": data.decode("utf-8")}
    except UnicodeDecodeError:
        return {"__typename": "OnlineStoreThemeFileBodyBase64", "contentBase64": base64.b64encode(data).decode()}


class FakeShop:
    def __init__(self):
        self.themes: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.clock = 0
        self.plus = False
        self.body_page_cut: int | None = None
        self.never_body: set[str] = set()
        self.url_files: set[str] = set()
        self.reserialize_json = True
        self.suffixes: dict[str, list] = {}
        self.translatable: dict[str, dict] = {}
        self.upsert_errors: dict[int, list] = {}
        self.register_errors: dict[int, list] = {}
        self.hooks: dict[str, object] = {}
        self.drop_on_create: set[str] = set()
        self.uploaded: bytes | None = None
        self.create_queries: list[str] = []
        self.processing_polls = 1
        self._upserts = 0
        self._registers = 0

    # Aufbau

    def tick(self) -> str:
        self.clock += 1
        return f"2026-01-01T00:{self.clock // 60:02d}:{self.clock % 60:02d}Z"

    def add_theme(self, gid: str, role: str, files: dict[str, bytes] | None = None, name: str = "Beispiel") -> dict:
        stamp = self.tick()
        theme = {"id": gid, "name": name, "role": role, "updatedAt": stamp, "themeStoreId": None,
                 "processing": False, "processingFailed": False, "files": {}}
        for filename, data in (files or {}).items():
            theme["files"][filename] = {"data": data, "updatedAt": stamp}
        self.themes[gid] = theme
        return theme

    def touch(self, gid: str, filename: str, data: bytes | None) -> None:
        """Ändert eine Datei im Shop, wie es der Theme-Editor täte; `None` löscht sie."""
        theme = self.themes[gid]
        stamp = self.tick()
        if data is None:
            theme["files"].pop(filename, None)
        else:
            theme["files"][filename] = {"data": data, "updatedAt": stamp}
        theme["updatedAt"] = stamp

    def ops(self, name: str) -> list:
        return [call for call in self.calls if call[0] == name]

    # Transport

    def execute(self, query: str, variables: dict | None = None, *, mutation: bool = False) -> dict:
        if is_mutation(query) and not mutation:
            raise ShopifyError("Mutation ohne mutation=True abgelehnt")
        op = re.search(r"(?:query|mutation)\s+(\w+)", query).group(1)
        self.calls.append((op, variables or {}, mutation))
        if op == "CreateUnpublishedTheme":
            self.create_queries.append(query)
        hook = self.hooks.get(op)
        if hook:
            hook(self, variables or {})
        return getattr(self, "op_" + op)(variables or {})

    def fetch_url(self, url: str) -> bytes:
        gid, filename = url[len("https://cdn.beispielshop.example/"):].split("/", 1)
        return self.themes[GID + gid]["files"][filename]["data"]

    # Themes

    def _theme_view(self, theme: dict) -> dict:
        return {k: v for k, v in theme.items() if k != "files"}

    def op_ThemeList(self, variables):
        return {"themes": {"nodes": [self._theme_view(t) for t in self.themes.values()]}}

    def op_ShopPlan(self, variables):
        return {"shop": {"plan": {"shopifyPlus": self.plus}}}

    def op_ThemeState(self, variables):
        theme = self.themes.get(variables["id"])
        if theme and theme["processing"]:
            if self.processing_polls <= 0:
                theme["processing"] = False
            self.processing_polls -= 1
        return {"theme": self._theme_view(theme) if theme else None}

    # Dateien

    def _node(self, gid: str, filename: str, with_body: bool) -> dict:
        entry = self.themes[gid]["files"][filename]
        data = entry["data"]
        node = {"filename": filename, "size": str(len(data)), "contentType": "text/plain",
                "checksumMd5": hashlib.md5(data).hexdigest(), "updatedAt": entry["updatedAt"]}
        if with_body:
            if filename in self.never_body:
                node["body"] = {"__typename": "OnlineStoreThemeFileBodyText"}
            elif filename in self.url_files:
                node["body"] = {"__typename": "OnlineStoreThemeFileBodyUrl",
                                "url": f"https://cdn.beispielshop.example/{gid[len(GID):]}/{filename}"}
            else:
                node["body"] = text_body(data)
        return node

    def _page(self, gid: str, after, size: int, with_body: bool, page_cut: int | None):
        names = sorted(self.themes[gid]["files"])
        start = int(after) if after else 0
        chunk = names[start:start + size]
        has_next = start + size < len(names)
        if page_cut is not None and start // size + 1 >= page_cut:
            has_next = False
        return {"theme": {"id": gid, "files": {
            "nodes": [self._node(gid, n, with_body) for n in chunk],
            "pageInfo": {"hasNextPage": has_next, "endCursor": str(start + size) if chunk else None},
            "userErrors": []}}}

    def op_ThemeFileMetadata(self, variables):
        if variables["id"] not in self.themes:
            return {"theme": None}
        return self._page(variables["id"], variables.get("after"), 50, False, None)

    def op_ThemeFileBodies(self, variables):
        return self._page(variables["id"], variables.get("after"), 50, True, self.body_page_cut)

    def op_ThemeFilesByName(self, variables):
        gid = variables["id"]
        names = variables["filenames"]
        assert len(names) <= 20, "filenames je Abfrage höchstens 20"
        files = self.themes[gid]["files"]
        return {"theme": {"id": gid, "files": {
            "nodes": [self._node(gid, n, True) for n in names if n in files],
            "userErrors": [{"filename": n, "code": "NOT_FOUND"} for n in names if n not in files]}}}

    def _stored(self, filename: str, data: bytes) -> bytes:
        if not (self.reserialize_json and filename.endswith(".json")):
            return data
        from theme.normalize import parse_json
        text = json.dumps(parse_json(data.decode("utf-8")), indent=4, ensure_ascii=False)
        if filename == "config/settings_data.json":
            text = "/*\n * IMPORTANT: The contents of this file are auto-generated.\n */\n" + text
        return text.encode("utf-8")

    def op_UpsertThemeFiles(self, variables):
        index = self._upserts
        self._upserts += 1
        files = variables["files"]
        assert len(files) <= 50, "themeFilesUpsert höchstens 50 Dateien"
        if index in self.upsert_errors:
            return {"themeFilesUpsert": {"upsertedThemeFiles": [], "job": None,
                                         "userErrors": self.upsert_errors[index]}}
        theme = self.themes[variables["themeId"]]
        stamp = self.tick()
        for item in files:
            body = item["body"]
            data = body["value"].encode("utf-8") if body["type"] == "TEXT" else base64.b64decode(body["value"])
            theme["files"][item["filename"]] = {"data": self._stored(item["filename"], data), "updatedAt": stamp}
        theme["updatedAt"] = stamp
        return {"themeFilesUpsert": {"upsertedThemeFiles": [{"filename": f["filename"]} for f in files],
                                     "job": {"id": f"gid://shopify/Job/{index}", "done": False}, "userErrors": []}}

    def op_JobState(self, variables):
        return {"job": {"id": variables["id"], "done": True}}

    # Erstanlage

    def op_StageThemeArchive(self, variables):
        return {"stagedUploadsCreate": {"stagedTargets": [{
            "url": "https://upload.beispielshop.example/target", "resourceUrl": "https://upload.beispielshop.example/res",
            "parameters": [{"name": "key", "value": "tmp/beispiel.zip"}]}], "userErrors": []}}

    def post(self, url: str, body: bytes, content_type: str) -> int:
        boundary = content_type.split("boundary=", 1)[1].encode()
        for part in body.split(b"--" + boundary):
            if b'name="file"' in part:
                self.uploaded = part.split(b"\r\n\r\n", 1)[1][:-2]
        return 201

    def op_CreateUnpublishedTheme(self, variables):
        files = {}
        with zipfile.ZipFile(io.BytesIO(self.uploaded)) as bundle:
            for name in bundle.namelist():
                if name not in self.drop_on_create:
                    files[name] = self._stored(name, bundle.read(name))
        theme = self.add_theme(DRAFT_ID, "UNPUBLISHED", files, name=variables["name"])
        theme["processing"] = True
        return {"themeCreate": {"theme": self._theme_view(theme), "userErrors": []}}

    # Template-Zuweisungen

    def _suffix_page(self, field: str, variables) -> dict:
        values = self.suffixes.get(field, [])
        start = int(variables.get("after") or 0)
        chunk = values[start:start + 250]
        return {field: {"nodes": [{"templateSuffix": v} for v in chunk],
                        "pageInfo": {"hasNextPage": start + 250 < len(values), "endCursor": str(start + 250)}}}

    def op_ProductTemplates(self, variables):
        return self._suffix_page("products", variables)

    def op_CollectionTemplates(self, variables):
        return self._suffix_page("collections", variables)

    def op_PageTemplates(self, variables):
        return self._suffix_page("pages", variables)

    def op_BlogTemplates(self, variables):
        return self._suffix_page("blogs", variables)

    def op_ArticleTemplates(self, variables):
        return self._suffix_page("articles", variables)

    # Übersetzungen

    def op_ThemeTranslations(self, variables):
        resource = self.translatable.get(variables["resourceId"])
        if resource is None:
            return {"translatableResource": None}
        locale = variables["locale"]
        return {"translatableResource": {
            "resourceId": variables["resourceId"], "translatableContent": resource["content"],
            "translations": list(resource.setdefault("translations", {}).setdefault(locale, {}).values())}}

    def op_RegisterThemeTranslations(self, variables):
        index = self._registers
        self._registers += 1
        if index in self.register_errors:
            return {"translationsRegister": {"translations": [], "userErrors": self.register_errors[index]}}
        resource = self.translatable[variables["resourceId"]]
        digests = {c["key"]: c["digest"] for c in resource["content"]}
        done = []
        for item in variables["translations"]:
            if digests.get(item["key"]) != item["translatableContentDigest"]:
                return {"translationsRegister": {"translations": [], "userErrors": [
                    {"code": "INVALID_VALUE_FOR_HANDLE_TRANSLATION", "field": ["translations"],
                     "message": "Translatable content hash is invalid"}]}}
            store = resource.setdefault("translations", {}).setdefault(item["locale"], {})
            store[item["key"]] = {"key": item["key"], "value": item["value"], "locale": item["locale"],
                                  "outdated": False}
            done.append({"key": item["key"], "value": item["value"], "locale": item["locale"]})
        return {"translationsRegister": {"translations": done, "userErrors": []}}
