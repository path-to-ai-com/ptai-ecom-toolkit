"""Schutz vor jedem Schreiben: nur der Entwurf, nur UNPUBLISHED, frisch gelesen, Live-Theme unverändert."""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import guard  # noqa: E402


def shop_with_draft(role: str = "UNPUBLISHED") -> fake.FakeShop:
    shop = fake.shop_with_live()
    shop.add_theme(fake.DRAFT_ID, role, {})
    return shop


class TestZiel(unittest.TestCase):
    def test_der_entwurf_mit_rolle_unpublished_darf_beschrieben_werden(self):
        theme = guard.check_write_target(shop_with_draft(), "111111111111", "111111111111")
        self.assertEqual(theme["role"], "UNPUBLISHED")

    def test_das_live_theme_wird_verweigert_auch_wenn_es_als_entwurf_eingetragen_ist(self):
        with self.assertRaisesRegex(guard.GuardError, "MAIN"):
            guard.check_write_target(shop_with_draft(), "000000000000", "000000000000")

    def test_eine_andere_id_als_der_entwurf_wird_verweigert(self):
        shop = shop_with_draft()
        shop.add_theme(fake.GID + "222222222222", "UNPUBLISHED")
        with self.assertRaisesRegex(guard.GuardError, "nicht der Entwurf"):
            guard.check_write_target(shop, "222222222222", "111111111111")

    def test_ohne_eingetragenen_entwurf_wird_nicht_geschrieben(self):
        with self.assertRaisesRegex(guard.GuardError, "draft_theme_id"):
            guard.check_write_target(shop_with_draft(), "111111111111", None)

    def test_andere_rollen_als_unpublished_werden_verweigert(self):
        for role in ("DEVELOPMENT", "DEMO", "LOCKED", "ARCHIVED"):
            with self.subTest(role=role), self.assertRaisesRegex(guard.GuardError, role):
                guard.check_write_target(shop_with_draft(role), "111111111111", "111111111111")

    def test_die_rolle_wird_bei_jedem_aufruf_frisch_gelesen(self):
        shop = shop_with_draft()
        guard.check_write_target(shop, "111111111111", "111111111111")
        shop.themes[fake.DRAFT_ID]["role"] = "MAIN"  # jemand hat den Entwurf veröffentlicht
        with self.assertRaises(guard.GuardError):
            guard.check_write_target(shop, "111111111111", "111111111111")
        self.assertEqual(len(shop.ops("ThemeState")), 2)

    def test_ein_geloeschter_entwurf_wird_verweigert(self):
        with self.assertRaisesRegex(guard.GuardError, "gibt es"):
            guard.check_write_target(fake.shop_with_live(), "111111111111", "111111111111")


class TestLiveTheme(unittest.TestCase):
    def test_aenderung_am_live_theme_bricht_ab(self):
        shop = shop_with_draft()

        def write():
            shop.touch(fake.LIVE_ID, "snippets/icon.liquid", b"anders")
            return "geschrieben"

        with self.assertRaisesRegex(guard.GuardError, "geändert"):
            guard.guarded(shop, "111111111111", "111111111111", write)

    def test_wechsel_des_live_themes_bricht_ab(self):
        before = {"id": fake.LIVE_ID, "updated_at": "a"}
        with self.assertRaisesRegex(guard.GuardError, "gewechselt"):
            guard.assert_live_unchanged(before, {"id": fake.GID + "222222222222", "updated_at": "a"})

    def test_ohne_aenderung_laeuft_das_schreiben_durch(self):
        result, protocol = guard.guarded(shop_with_draft(), "111111111111", "111111111111", lambda: 42)
        self.assertEqual(result, 42)
        self.assertEqual(protocol["live_before"], protocol["live_after"])


class TestNieVeroeffentlichen(unittest.TestCase):
    def test_kein_modul_ruft_theme_publish_auf(self):
        """Jede Zeichenkette im Code außer Docstrings: keine Operation `themePublish`, kein `publish`-Befehl."""
        hits = []
        for path in sorted((ROOT / "scripts" / "theme").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body
                          and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    if re.search(r"themePublish|\bpublish\b", node.value):
                        hits.append(f"{path.name}: {node.value[:60]}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
