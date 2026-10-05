"""Abgleich: Änderungen im Live-Theme seit der Sicherung, Inhalt entscheidet, nicht der Zeitstempel."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import manifest, snapshot, sync, templates  # noqa: E402


class TestAbgleich(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.shop = fake.shop_with_live()
        self.first, _, _ = snapshot.capture(self.shop, "live", self.root / "snapshots")
        self.last = self.first / "manifest.json"

    def test_ohne_aenderung_kein_befund_und_nichts_neu_gezogen(self):
        delta, code = sync.sync(self.shop, self.last, self.root / "sync")
        self.assertEqual(code, 0)
        self.assertEqual((delta["changed"], delta["added"], delta["removed"]), ([], [], []))
        self.assertEqual(self.shop.ops("ThemeFilesByName"), [])
        new = manifest.load_manifest(Path(delta["snapshot"]) / "manifest.json")
        self.assertEqual(manifest.diff_manifests(manifest.load_manifest(self.last), new)["unchanged"],
                         len(fake.fixture_files()))

    def test_geaendert_neu_geloescht_und_nur_neu_serialisiert(self):
        settings = json.loads(fake.fixture_files()["config/settings_data.json"])
        self.shop.touch(fake.LIVE_ID, "config/settings_data.json",
                        ("/* auto */\n" + json.dumps(settings, indent=4)).encode())
        self.shop.touch(fake.LIVE_ID, "snippets/icon.liquid", b"<svg class=\"neu\"></svg>\n")
        self.shop.touch(fake.LIVE_ID, "snippets/app-rest.liquid", b"<script></script>\n")
        self.shop.touch(fake.LIVE_ID, "templates/page.alt.json", None)
        delta, code = sync.sync(self.shop, self.last, self.root / "sync")
        self.assertEqual(code, 1)
        self.assertEqual(delta["changed"], ["snippets/icon.liquid"])
        self.assertEqual(delta["added"], ["snippets/app-rest.liquid"])
        self.assertEqual(delta["removed"], ["templates/page.alt.json"])
        self.assertEqual(delta["touched_without_change"], ["config/settings_data.json"])
        saved = json.loads((self.root / "sync" / "delta.json").read_text())
        self.assertEqual(saved["changed"], ["snippets/icon.liquid"])
        new_dir = Path(delta["snapshot"])
        self.assertEqual((new_dir / "snippets/icon.liquid").read_bytes(), b"<svg class=\"neu\"></svg>\n")
        self.assertTrue((new_dir / "templates/index.json").is_file(), "unveränderte Dateien aus der alten Sicherung")
        self.assertNotEqual(new_dir, self.first)

    def test_lokal_veraenderte_alte_sicherung_wird_nicht_uebernommen(self):
        (self.first / "snippets/icon.liquid").write_text("lokal verändert")
        delta, _ = sync.sync(self.shop, self.last, self.root / "sync")
        self.assertEqual((Path(delta["snapshot"]) / "snippets/icon.liquid").read_bytes(),
                         fake.fixture_files()["snippets/icon.liquid"])

    def test_gewechseltes_live_theme_ist_ein_befund(self):
        self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
        self.shop.add_theme(fake.GID + "222222222222", "MAIN", fake.fixture_files())
        delta, code = sync.sync(self.shop, self.last, self.root / "sync")
        self.assertTrue(delta["live_theme_switched"])
        self.assertEqual(code, 1)

    def test_template_zuweisungen_werden_gegen_die_bestandsaufnahme_gehalten(self):
        self.shop.suffixes = {"products": ["beispiel"] * 2}
        before = templates.usage(self.shop, self.first)
        path = self.root / "templates.json"
        path.write_text(json.dumps(before))
        self.shop.suffixes = {"products": ["beispiel"] * 3 + ["neu"]}
        delta, code = sync.sync(self.shop, self.last, self.root / "sync", templates_json=path)
        self.assertEqual(code, 1)
        changed = {c["template"]: c for c in delta["assignments"]["changed"]}
        self.assertEqual((changed["product.beispiel"]["objects_before"], changed["product.beispiel"]["objects_after"]),
                         (2, 3))
        self.assertEqual(delta["assignments"]["new_assigned_without_file"],
                         [{"type": "product", "suffix": "neu", "objects": 1}])

    def test_cli(self):
        ws = fake.temp_workspace(self)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync.main(["--last", str(self.last), "--out", str(ws / "migration/sync/heute"),
                              "--workspace", str(ws), "--templates", str(ws / "fehlt.json")], transport=self.shop)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["changed"], 0)


if __name__ == "__main__":
    unittest.main()
