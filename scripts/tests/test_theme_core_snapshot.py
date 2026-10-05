"""Sicherung: vollständig erst, wenn die Inhalte die Metadatenliste decken; Dateien unverändert."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import manifest, snapshot  # noqa: E402
from theme.normalize import sha256_bytes  # noqa: E402


def many_files(count: int = 70) -> dict[str, bytes]:
    files = fake.fixture_files()
    files.update({f"assets/extra-{i:03d}.css": f".e{i} {{}}\n".encode() for i in range(count)})
    return files


class TestVollstaendigkeit(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name) / "snapshots"

    def test_endet_die_paginierung_zu_frueh_wird_ueber_filenames_nachgefordert(self):
        files = many_files()
        shop = fake.shop_with_live(files)
        shop.body_page_cut = 1  # nach der ersten Seite meldet Shopify fälschlich das Ende
        target, result, report = snapshot.capture(shop, "live", self.out, store="beispiel.myshopify.com")
        self.assertTrue(result["complete"])
        self.assertEqual(report["findings"], [])
        self.assertTrue(shop.ops("ThemeFilesByName"), "Nachfordern über filenames")
        self.assertEqual(set(result["files"]), set(files))
        self.assertEqual(result["expected_files"], len(files))
        for name, data in files.items():
            self.assertEqual((target / name).read_bytes(), data, f"{name} unverändert")

    def test_fehlt_ein_inhalt_ist_die_sicherung_unvollstaendig(self):
        shop = fake.shop_with_live()
        shop.never_body = {"assets/beispiel.css"}
        _, result, report = snapshot.capture(shop, "live", self.out)
        self.assertFalse(result["complete"])
        self.assertEqual(result["missing"], ["assets/beispiel.css"])
        self.assertEqual(report["findings"][0]["rule"], "incomplete")
        self.assertNotIn("assets/beispiel.css", result["files"])

    def test_binaerdateien_kommen_auch_ueber_die_url(self):
        shop = fake.shop_with_live()
        shop.url_files = {"assets/beispiel.png"}
        target, result, _ = snapshot.capture(shop, "live", self.out, fetch_url=shop.fetch_url)
        self.assertTrue(result["complete"])
        self.assertEqual((target / "assets/beispiel.png").read_bytes(), fake.fixture_files()["assets/beispiel.png"])

    def test_aenderung_waehrend_der_sicherung_ist_ein_befund(self):
        shop = fake.shop_with_live()
        shop.hooks["ThemeFileBodies"] = lambda s, v: s.touch(fake.LIVE_ID, "snippets/icon.liquid", b"<svg></svg>")
        _, _, report = snapshot.capture(shop, "live", self.out)
        self.assertIn("theme_changed_during_snapshot", [f["rule"] for f in report["findings"]])


class TestManifest(unittest.TestCase):
    def test_manifest_traegt_metadaten_und_inhaltspruefsummen(self):
        with tempfile.TemporaryDirectory() as tmp:
            shop = fake.shop_with_live()
            target, _, _ = snapshot.capture(shop, "live", Path(tmp), store="beispiel.myshopify.com")
            data = manifest.load_manifest(target / "manifest.json")
        self.assertEqual(data["theme_id"], "000000000000")
        self.assertEqual(data["theme_role"], "MAIN")
        self.assertEqual(data["store"], "beispiel.myshopify.com")
        entry = data["files"]["config/settings_data.json"]
        self.assertEqual(entry["sha256"], sha256_bytes(fake.fixture_files()["config/settings_data.json"]))
        self.assertIn("sha256_normalized", entry)
        self.assertIn("checksum_md5", entry)
        self.assertNotIn("sha256_normalized", data["files"]["snippets/icon.liquid"])
        self.assertTrue(target.name.endswith("-000000000000"))

    def test_eine_vorhandene_sicherung_wird_nie_ueberschrieben(self):
        with tempfile.TemporaryDirectory() as tmp:
            shop = fake.shop_with_live()
            first, _, _ = snapshot.capture(shop, "live", Path(tmp))
            second, _, _ = snapshot.capture(shop, "live", Path(tmp))
        self.assertNotEqual(first, second)


class TestThemePlaetze(unittest.TestCase):
    def test_volle_theme_plaetze_werden_gewarnt(self):
        shop = fake.shop_with_live()
        for i in range(19):
            shop.add_theme(f"{fake.GID}1000000000{i:02d}", "UNPUBLISHED")
        with tempfile.TemporaryDirectory() as tmp:
            _, _, report = snapshot.capture(shop, "live", Path(tmp))
        self.assertTrue(report["theme_capacity"]["full"])
        self.assertTrue(report["warnings"])

    def test_auf_plus_sind_hundert_plaetze_frei(self):
        shop = fake.shop_with_live()
        shop.plus = True
        for i in range(19):
            shop.add_theme(f"{fake.GID}1000000000{i:02d}", "UNPUBLISHED")
        with tempfile.TemporaryDirectory() as tmp:
            _, _, report = snapshot.capture(shop, "live", Path(tmp))
        self.assertEqual(report["theme_capacity"]["limit"], 100)
        self.assertEqual(report["warnings"], [])


class TestCli(unittest.TestCase):
    def run_main(self, argv, transport):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = snapshot.main(argv, transport=transport)
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1, "genau eine JSON-Zeile auf stdout")
        return code, json.loads(lines[0])

    def test_cli_exit_null_bei_vollstaendiger_sicherung_eins_bei_luecke(self):
        ws = fake.temp_workspace(self)
        code, summary = self.run_main(["--theme", "live", "--out", str(ws / "migration/snapshots"),
                                       "--workspace", str(ws)], fake.shop_with_live())
        self.assertEqual(code, 0)
        self.assertTrue(summary["complete"])
        shop = fake.shop_with_live()
        shop.never_body = {"layout/theme.liquid"}
        code, summary = self.run_main(["--theme", "000000000000", "--out", str(ws / "migration/snapshots"),
                                       "--workspace", str(ws)], shop)
        self.assertEqual(code, 1)
        self.assertFalse(summary["complete"])

    def test_original_aus_zip_ohne_oberordner_und_ohne_fremddateien(self):
        ws = fake.temp_workspace(self)
        archive = ws / "beispiel-original.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, data in fake.fixture_files().items():
                bundle.writestr(f"beispiel-1.0.0/{name}", data)
            bundle.writestr("beispiel-1.0.0/README.md", "nicht Teil des Themes")
        code, summary = self.run_main(["--theme", "live", "--out", str(ws / "snaps"), "--original-zip", str(archive),
                                       "--workspace", str(ws)], fake.shop_with_live())
        self.assertEqual(code, 0)
        original = Path(summary["original"])
        self.assertTrue((original / "templates/index.json").is_file())
        self.assertFalse((original / "README.md").exists())
        self.assertEqual(manifest.load_manifest(original / "manifest.json")["theme_role"], "ORIGINAL")


if __name__ == "__main__":
    unittest.main()
