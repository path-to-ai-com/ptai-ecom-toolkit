"""Paket: nur Theme-Dateien, nie ungültiges JSON, nie ein Schlüssel, Manifest passt zum Archiv."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import package  # noqa: E402


class TestPaket(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.theme = self.root / "theme"
        shutil.copytree(fake.FIXTURE, self.theme)
        (self.theme / "README.md").write_text("gehört nicht ins Theme")
        (self.theme / "migration").mkdir()
        (self.theme / "migration" / "build.py").write_text("print()")

    def test_nur_theme_dateien_und_manifest_passt(self):
        manifest = package.build_package(self.theme, self.root / "out" / "beispiel.zip")
        with zipfile.ZipFile(self.root / "out" / "beispiel.zip") as bundle:
            names = bundle.namelist()
        self.assertEqual(sorted(names), sorted(fake.fixture_files()))
        self.assertEqual(manifest["file_count"], len(names))
        self.assertTrue(package.manifest_path(self.root / "out" / "beispiel.zip").is_file())
        self.assertEqual(package.verify_package(self.root / "out" / "beispiel.zip"), fake.fixture_files())

    def test_dasselbe_theme_ergibt_dasselbe_archiv(self):
        a = package.build_package(self.theme, self.root / "a.zip")
        b = package.build_package(self.theme, self.root / "b.zip")
        self.assertEqual(a["archive_sha256"], b["archive_sha256"])

    def test_ungueltiges_json_wird_nicht_gepackt(self):
        (self.theme / "templates" / "page.alt.json").write_text('{"sections": ')
        with self.assertRaises(package.PackageError) as caught:
            package.build_package(self.theme, self.root / "x.zip")
        self.assertIn("invalid_json", {f["rule"] for f in caught.exception.findings})
        self.assertFalse((self.root / "x.zip").exists())

    def test_ein_zugangsschluessel_im_inhalt_wird_nicht_gepackt(self):
        (self.theme / "snippets" / "leck.liquid").write_text("shpat_" + "a1" * 16)
        with self.assertRaises(package.PackageError) as caught:
            package.build_package(self.theme, self.root / "x.zip")
        self.assertEqual([f["rule"] for f in caught.exception.findings], ["secret"])

    def test_ein_veraendertes_archiv_passt_nicht_mehr_zum_manifest(self):
        package.build_package(self.theme, self.root / "a.zip")
        with zipfile.ZipFile(self.root / "a.zip", "a") as bundle:
            bundle.writestr("snippets/neu.liquid", "neu")
        with self.assertRaises(package.PackageError):
            package.verify_package(self.root / "a.zip")

    def test_ein_symlink_im_theme_ist_ein_fehler(self):
        (self.theme / "snippets" / "link.liquid").symlink_to(self.root / "theme" / "README.md")
        with self.assertRaises(ValueError):
            package.build_package(self.theme, self.root / "x.zip")

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = package.main(["--theme-dir", str(self.theme), "--out", str(self.root / "c.zip")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["files"], len(fake.fixture_files()))
        (self.theme / "templates" / "index.json").write_text("{")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(package.main(["--theme-dir", str(self.theme), "--out", str(self.root / "d.zip")]), 1)


if __name__ == "__main__":
    unittest.main()
