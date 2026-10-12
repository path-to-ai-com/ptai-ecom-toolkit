"""Pfad zur Marke je Rechner und der Abgleich über die Marke im Cockpit (D9, D11, 11.10.2026)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from audit import brand, measures

from tests import brand_support as bs


def clean_env():
    """Ohne eine `PTAI_BRAND_WORKSPACE` aus der Shell, die den Test verfälscht."""
    env = {k: v for k, v in os.environ.items() if k != brand.ENV_BRAND_WORKSPACE}
    return mock.patch.dict(os.environ, env, clear=True)


def other_brand(case, name="andere-marke") -> Path:
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    folder = Path(tmp.name).resolve() / name
    bs.write_json(folder / "reporting" / "measures.json",
                  {"version": 2, "brand": name, "next_id": 1, "measures": []})
    return folder


class TestPrecedence(unittest.TestCase):
    def setUp(self):
        patcher = clean_env()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.brand_ws = bs.make_brand(self, linked=False)
        self.store = self.brand_ws / "eu"

    def test_local_file_is_read_when_config_has_no_path(self):
        bs.write_json(self.store / "reporting" / brand.LOCAL_CONFIG_NAME,
                      {"brand_workspace": str(self.brand_ws)})
        self.assertEqual(measures.file_path(self.store), self.brand_ws / "reporting" / "measures.json")
        raw, origin = brand.brand_workspace_setting(self.store)
        self.assertTrue(origin.endswith(brand.LOCAL_CONFIG_NAME))

    def test_local_file_beats_config_and_env_beats_both(self):
        # config.json zeigt auf einen Windows-Pfad des Kundenteams, der hier nicht existiert.
        bs.write_json(self.store / "reporting" / "config.json",
                      {**bs.store_config("eu", None), "brand_workspace": "/c/Projekte/marke"})
        bs.write_json(self.store / "reporting" / brand.LOCAL_CONFIG_NAME,
                      {"brand_workspace": "/nirgends/marke"})
        with mock.patch.dict(os.environ, {brand.ENV_BRAND_WORKSPACE: str(self.brand_ws)}):
            self.assertEqual(brand.brand_workspace_setting(self.store)[0], str(self.brand_ws))
            self.assertEqual(measures.file_path(self.store), self.brand_ws / "reporting" / "measures.json")
        self.assertEqual(brand.brand_workspace_setting(self.store)[0], "/nirgends/marke")
        with self.assertRaises(brand.BrandFileError) as raised:
            measures.load_or_empty(self.store)
        self.assertIn(brand.LOCAL_CONFIG_NAME, str(raised.exception))

    def test_a_relative_local_path_aborts(self):
        bs.write_json(self.store / "reporting" / brand.LOCAL_CONFIG_NAME, {"brand_workspace": ".."})
        with self.assertRaisesRegex(brand.BrandFileError, "absoluter Pfad"):
            measures.load_or_empty(self.store)

    def test_the_local_file_overrides_only_the_path(self):
        bs.write_json(self.store / "reporting" / brand.LOCAL_CONFIG_NAME,
                      {"brand_workspace": str(self.brand_ws), "domain": "https://x.test"})
        with self.assertRaisesRegex(brand.BrandFileError, "domain"):
            measures.load_or_empty(self.store)

    def test_a_path_to_another_brand_aborts(self):
        # Die Umgebungsvariable gilt für jeden Workspace der Sitzung.
        with mock.patch.dict(os.environ, {brand.ENV_BRAND_WORKSPACE: str(other_brand(self))}):
            with self.assertRaisesRegex(brand.BrandFileError, "falsche Marke"):
                measures.load_or_empty(self.store)

    def test_the_local_path_also_lifts_the_second_counter_guard(self):
        # Ohne Pfad greift D9, mit Pfad aus der lokalen Datei nicht mehr.
        with self.assertRaises(brand.BrandFileError):
            measures.load_or_empty(self.store)
        bs.write_json(self.store / "reporting" / brand.LOCAL_CONFIG_NAME,
                      {"brand_workspace": str(self.brand_ws)})
        self.assertEqual(measures.load_or_empty(self.store)["brand"], bs.BRAND)


class TestSetLocal(unittest.TestCase):
    def setUp(self):
        patcher = clean_env()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.brand_ws = bs.make_brand(self, linked=False)
        self.store = self.brand_ws / "eu"
        subprocess.run(["git", "init", "-q", str(self.store)], check=True)

    def ignored(self) -> bool:
        return subprocess.run(["git", "-C", str(self.store), "check-ignore", "-q",
                               f"reporting/{brand.LOCAL_CONFIG_NAME}"]).returncode == 0

    def test_writes_the_file_and_ignores_it_in_the_clone(self):
        self.assertFalse(self.ignored())
        target = brand.set_local(self.store, self.brand_ws)
        self.assertEqual(bs.read(target), {"brand_workspace": str(self.brand_ws)})
        self.assertTrue(self.ignored())
        # .gitignore bleibt unberührt: das Repo des Kunden ändert sich nicht.
        self.assertFalse((self.store / ".gitignore").exists())
        self.assertEqual(measures.file_path(self.store), self.brand_ws / "reporting" / "measures.json")
        brand.set_local(self.store, self.brand_ws)
        exclude = (self.store / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.count(brand.LOCAL_CONFIG_NAME), 1)

    def test_refuses_a_wrong_brand_and_writes_nothing(self):
        with self.assertRaises(brand.BrandFileError):
            brand.set_local(self.store, other_brand(self))
        self.assertFalse((self.store / "reporting" / brand.LOCAL_CONFIG_NAME).exists())

    def test_refuses_a_tracked_local_file(self):
        local = self.store / "reporting" / brand.LOCAL_CONFIG_NAME
        bs.write_json(local, {"brand_workspace": "/c/Projekte"})
        subprocess.run(["git", "-C", str(self.store), "add", "-f", str(local)], check=True)
        with self.assertRaisesRegex(brand.BrandFileError, "getrackt"):
            brand.set_local(self.store, self.brand_ws)

    def test_cli(self):
        self.assertEqual(brand.main(["set-local", "--workspace", str(self.store),
                                     "--brand-workspace", str(self.brand_ws)]), 0)
        self.assertTrue(self.ignored())


class TestGuardUsesTheCockpitBrand(unittest.TestCase):
    """Stores, die früher eigene Marken waren, behalten ihren `account_slug`,
    veröffentlichen aber unter `portal.brand` der Marke. D9 vergleicht die Marke im Cockpit."""

    def setUp(self):
        patcher = clean_env()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.brand_ws = bs.make_brand(self, linked=False)

    def store(self, name, config):
        bs.write_json(self.brand_ws / name / "reporting" / "config.json", config)
        return self.brand_ws / name

    def test_old_account_slug_with_cockpit_brand_is_guarded(self):
        store = self.store("nordshop", {"account_slug": "nordshop", "brand": "Nordshop",
                                        "portal": {"brand": bs.BRAND, "shop": "nordshop"}})
        with self.assertRaisesRegex(brand.BrandFileError, "set-local"):
            measures.load_or_empty(store)

    def test_without_portal_the_account_slug_is_the_brand(self):
        store = self.store("suedshop", {"account_slug": bs.BRAND, "brand": "Suedshop"})
        with self.assertRaises(brand.BrandFileError):
            measures.load_or_empty(store)

    def test_a_matching_account_slug_alone_does_not_count_when_the_cockpit_brand_differs(self):
        store = self.store("x", {"account_slug": bs.BRAND, "brand": "X",
                                 "portal": {"brand": "andere-marke", "shop": "x"}})
        self.assertEqual(measures.load_or_empty(store), measures.empty())


if __name__ == "__main__":
    unittest.main()
