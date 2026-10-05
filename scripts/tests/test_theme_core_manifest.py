"""Manifeste vergleichen: Inhalt entscheidet, bei JSON normalisiert, nie die Prüfsumme von Shopify."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import manifest  # noqa: E402
from theme.normalize import content_hash  # noqa: E402

SETTINGS = {"current": {"beispiel_title": "Willkommen"}}


def entry(name: str, body: str, md5: str = "0" * 32) -> dict:
    return {"size": len(body), "updated_at": "", "checksum_md5": md5, **content_hash(name, body)}


def old_and_new():
    old = {"files": {
        "config/settings_data.json": entry("config/settings_data.json", json.dumps(SETTINGS)),
        "snippets/icon.liquid": entry("snippets/icon.liquid", "<svg></svg>"),
        "snippets/alt.liquid": entry("snippets/alt.liquid", "alt"),
        "templates/index.json": entry("templates/index.json", '{"order": []}'),
    }}
    new = {"files": {
        # nur neu serialisiert, mit Kopf und anderer Prüfsumme: unverändert
        "config/settings_data.json": entry("config/settings_data.json",
                                           "/* auto */\n" + json.dumps(SETTINGS, indent=4), md5="f" * 32),
        "snippets/icon.liquid": entry("snippets/icon.liquid", "<svg class=\"neu\"></svg>"),
        "templates/index.json": entry("templates/index.json", '{"order": ["hero"]}'),
        "sections/neu.liquid": entry("sections/neu.liquid", "neu"),
    }}
    return old, new


class TestDiff(unittest.TestCase):
    def test_geaendert_neu_geloescht_und_reserialisiertes_json_als_unveraendert(self):
        old, new = old_and_new()
        result = manifest.diff_manifests(old, new)
        self.assertEqual(result["changed"], ["snippets/icon.liquid", "templates/index.json"])
        self.assertEqual(result["added"], ["sections/neu.liquid"])
        self.assertEqual(result["removed"], ["snippets/alt.liquid"])
        self.assertEqual(result["unchanged"], 1)

    def test_gleiche_md5_beweist_bei_json_nichts(self):
        old = {"files": {"templates/a.json": entry("templates/a.json", '{"a": 1}', md5="a" * 32)}}
        new = {"files": {"templates/a.json": entry("templates/a.json", '{"a": 2}', md5="a" * 32)}}
        self.assertEqual(manifest.diff_manifests(old, new)["changed"], ["templates/a.json"])

    def test_schreiben_und_lesen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = manifest.write_manifest(tmp, {"store": "beispiel.myshopify.com", "theme_id": "000000000000",
                                                 "complete": True}, old_and_new()[0]["files"])
            data = manifest.load_manifest(path)
        self.assertEqual(data["theme_id"], "000000000000")
        self.assertTrue(data["complete"])
        self.assertEqual(list(data["files"]), sorted(data["files"]))
        for key in manifest.META_KEYS:
            self.assertIn(key, data)


class TestCli(unittest.TestCase):
    def test_exit_eins_bei_unterschieden_null_ohne(self):
        old, new = old_and_new()
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp, "a.json"), Path(tmp, "b.json")
            a.write_text(json.dumps(old)), b.write_text(json.dumps(new))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = manifest.main(["diff", str(a), str(b), "--out", str(Path(tmp, "d.json"))])
                same = manifest.main(["diff", str(a), str(a), "--out", str(Path(tmp, "e.json"))])
            self.assertEqual((code, same), (1, 0))
            self.assertEqual(json.loads(Path(tmp, "d.json").read_text())["added"], ["sections/neu.liquid"])
            self.assertEqual(json.loads(out.getvalue().splitlines()[0])["changed"], 2)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(manifest.main(["diff", str(a), str(Path(tmp, "fehlt.json")), "--out", "x"]), 2)


if __name__ == "__main__":
    unittest.main()
