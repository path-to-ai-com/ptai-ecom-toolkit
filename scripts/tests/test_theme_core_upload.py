"""Upload: nur in den Entwurf, höchstens 50 je Upsert, Code vor Templates, Halt bei userErrors, Zurücklesen."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import files as theme_files  # noqa: E402
from theme import package, upload  # noqa: E402


def local_theme(case, extra: int = 0) -> Path:
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    theme = Path(tmp.name) / "theme"
    shutil.copytree(fake.FIXTURE, theme)
    for i in range(extra):
        (theme / "assets" / f"extra-{i:03d}.css").write_text(f".e{i} {{}}\n")
    return theme


def shop_with_draft(draft_files: dict | None = None) -> fake.FakeShop:
    shop = fake.shop_with_live()
    shop.add_theme(fake.DRAFT_ID, "UNPUBLISHED", draft_files or {}, name="Entwurf")
    return shop


def config(draft: str | None = "111111111111") -> dict:
    return {"shopify_store": "beispiel.myshopify.com",
            "theme_migration": {"draft_theme_id": draft, "access": {"write": "admin-api"}}}


def upserted(shop) -> list[list[str]]:
    return [[f["filename"] for f in call[1]["files"]] for call in shop.ops("UpsertThemeFiles")]


class TestUpdate(unittest.TestCase):
    def test_pakete_zu_hoechstens_50_code_vor_templates_und_zuruecklesen(self):
        theme = local_theme(self, extra=100)
        shop = shop_with_draft()
        report, code = upload.update(config(), "111111111111", theme, transport=shop, sleep=lambda s: None)
        self.assertEqual(code, 0, report["findings"])
        batches = upserted(shop)
        self.assertEqual(len(batches), 3)
        self.assertTrue(all(len(b) <= 50 for b in batches))
        order = [name for batch in batches for name in batch]
        ranks = [theme_files.upload_order(n)[0] for n in order]
        self.assertEqual(ranks, sorted(ranks), "Code vor Templates")
        self.assertEqual(order[-1], "config/settings_data.json")
        self.assertLess(order.index("sections/hero.liquid"), order.index("templates/index.json"))
        self.assertEqual(len(report["readback"]["equal"]), report["readback"]["checked"])
        self.assertEqual(report["readback"]["checked"], len(order))

    def test_neu_serialisiertes_json_gilt_beim_zuruecklesen_als_gleich(self):
        shop = shop_with_draft()
        report, code = upload.update(config(), "111111111111", local_theme(self), transport=shop)
        stored = shop.themes[fake.DRAFT_ID]["files"]["config/settings_data.json"]["data"]
        self.assertTrue(stored.startswith(b"/*"), "der Fake setzt den Kommentarkopf wie Shopify")
        self.assertEqual(code, 0)
        self.assertIn("config/settings_data.json", report["readback"]["equal"])

    def test_nur_geaenderte_dateien_werden_geschrieben(self):
        theme = local_theme(self)
        shop = shop_with_draft(fake.fixture_files())
        (theme / "snippets" / "icon.liquid").write_text("<svg class=\"neu\"></svg>\n")
        report, code = upload.update(config(), "111111111111", theme, transport=shop)
        self.assertEqual(code, 0)
        self.assertEqual(upserted(shop), [["snippets/icon.liquid"]])
        self.assertEqual(report["written"], ["snippets/icon.liquid"])

    def test_der_schutz_laeuft_vor_jedem_paket(self):
        shop = shop_with_draft()
        upload.update(config(), "111111111111", local_theme(self, extra=60), transport=shop)
        # einmal zu Beginn, dann vor jedem der beiden Pakete
        self.assertEqual(len(shop.ops("ThemeState")), 3)
        self.assertEqual(len(shop.ops("ThemeList")), 4)

    def test_bei_user_errors_haelt_der_lauf_an(self):
        shop = shop_with_draft()
        shop.upsert_errors = {1: [{"code": "INVALID", "filename": "assets/extra-060.css", "message": "kaputt"}]}
        report, code = upload.update(config(), "111111111111", local_theme(self, extra=120), transport=shop)
        self.assertEqual(code, 1)
        self.assertEqual(len(shop.ops("UpsertThemeFiles")), 2, "kein drittes Paket nach dem Fehler")
        self.assertEqual(report["findings"][0]["rule"], "user_errors")
        self.assertEqual(len(report["written"]), 50)

    def test_aenderung_am_live_theme_zwischen_paketen_bricht_ab(self):
        shop = shop_with_draft()
        shop.hooks["UpsertThemeFiles"] = lambda s, v: s.touch(fake.LIVE_ID, "snippets/icon.liquid", b"anders")
        report, code = upload.update(config(), "111111111111", local_theme(self, extra=60), transport=shop)
        self.assertEqual(code, 1)
        self.assertEqual(len(shop.ops("UpsertThemeFiles")), 1)
        self.assertEqual(report["findings"][0]["rule"], "guard")

    def test_auf_das_live_theme_oder_eine_fremde_id_wird_nie_geschrieben(self):
        shop = shop_with_draft()
        with self.assertRaises(upload.GuardError):
            upload.update(config("000000000000"), "000000000000", local_theme(self), transport=shop)
        with self.assertRaises(upload.GuardError):
            upload.update(config(), "000000000000", local_theme(self), transport=shop)
        self.assertEqual(shop.ops("UpsertThemeFiles"), [])

    def test_cli_exit_zwei_beim_schutz_und_eine_json_zeile(self):
        ws = fake.temp_workspace(self, draft_theme_id="111111111111")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = upload.main(["update", "--theme", "000000000000", "--dir", str(local_theme(self)),
                                "--workspace", str(ws)], transport=shop_with_draft())
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out.getvalue())["ok"])

    def test_ohne_admin_api_schreibt_der_admin_weg_nicht(self):
        ws = fake.temp_workspace(self, draft_theme_id="111111111111", access={"write": "cli-theme"})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            code = upload.main(["update", "--theme", "111111111111", "--dir", str(local_theme(self)),
                                "--workspace", str(ws)])
        self.assertEqual(code, 2)
        self.assertIn("theme push", err.getvalue())


class TestCreate(unittest.TestCase):
    def setUp(self):
        self.ws = fake.temp_workspace(self)
        self.zip = self.ws / "migration" / "build" / "beispiel.zip"
        package.build_package(local_theme(self), self.zip)

    def test_staged_upload_theme_create_unpublished_und_zuruecklesen(self):
        shop = fake.shop_with_live()
        report, code = upload.create(config(None), self.zip, "Beispiel Entwurf", transport=shop, post=shop.post,
                                     sleep=lambda s: None, workspace=self.ws)
        self.assertEqual(code, 0, report["findings"])
        self.assertEqual(report["theme_id"], "111111111111")
        self.assertEqual(shop.ops("StageThemeArchive")[0][1]["input"][0]["mimeType"], "application/zip")
        self.assertIn("role: UNPUBLISHED", shop.create_queries[0])
        self.assertEqual(len(report["comparison"]["equal"]), len(fake.fixture_files()))
        saved = json.loads((self.ws / "reporting" / "config.json").read_text())
        self.assertEqual(saved["theme_migration"]["draft_theme_id"], "111111111111")
        self.assertEqual(saved["brand"], "Beispielmarke", "der Rest der Config bleibt")

    def test_still_weggelassene_datei_beim_import_ist_ein_befund(self):
        shop = fake.shop_with_live()
        shop.drop_on_create = {"templates/page.alt.json"}
        report, code = upload.create(config(None), self.zip, "Beispiel", transport=shop, post=shop.post,
                                     sleep=lambda s: None, workspace=self.ws)
        self.assertEqual(code, 1)
        self.assertEqual(report["comparison"]["missing"], ["templates/page.alt.json"])

    def test_volle_theme_plaetze_halten_vor_jeder_mutation_an(self):
        shop = fake.shop_with_live()
        for i in range(19):
            shop.add_theme(f"{fake.GID}1000000000{i:02d}", "UNPUBLISHED")
        report, code = upload.create(config(None), self.zip, "Beispiel", transport=shop, post=shop.post,
                                     workspace=self.ws)
        self.assertEqual(code, 1)
        self.assertEqual([c for c in shop.calls if c[2]], [], "keine Mutation")

    def test_mit_vorhandenem_entwurf_wird_kein_zweiter_angelegt(self):
        with self.assertRaisesRegex(upload.UploadError, "upload update"):
            upload.create(config(), self.zip, "Beispiel", transport=fake.shop_with_live(), workspace=self.ws)

    def test_ein_veraendertes_archiv_wird_nicht_hochgeladen(self):
        self.zip.write_bytes(self.zip.read_bytes() + b"x")
        shop = fake.shop_with_live()
        report, code = upload.create(config(None), self.zip, "Beispiel", transport=shop, workspace=self.ws)
        self.assertEqual(code, 1)
        self.assertEqual(shop.ops("StageThemeArchive"), [])


class TestVerify(unittest.TestCase):
    def test_nur_lesend_und_meldet_abweichungen(self):
        theme = local_theme(self)
        files = fake.fixture_files()
        files["snippets/icon.liquid"] = b"anders"
        del files["templates/page.alt.json"]
        files["snippets/nur-im-shop.liquid"] = b"x"
        shop = shop_with_draft(files)
        report, code = upload.verify("111111111111", theme, transport=shop)
        self.assertEqual(code, 1)
        self.assertEqual(report["comparison"]["different"], ["snippets/icon.liquid"])
        self.assertEqual(report["comparison"]["missing"], ["templates/page.alt.json"])
        self.assertEqual(report["comparison"]["extra"], ["snippets/nur-im-shop.liquid"])
        self.assertEqual([c for c in shop.calls if c[2]], [])

    def test_gleicher_stand_ist_ohne_befund(self):
        shop = shop_with_draft()
        upload.update(config(), "111111111111", local_theme(self), transport=shop)
        report, code = upload.verify("111111111111", local_theme(self), transport=shop)
        self.assertEqual(code, 0, report["findings"])


if __name__ == "__main__":
    unittest.main()
